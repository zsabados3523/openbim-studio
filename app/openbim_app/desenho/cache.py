# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cache em disco do desenho por vista (planta e corte).

Sem Qt, sem rede e sem geometria no processo principal: só biblioteca padrão e
leitura de atributos do IFC. A chave depende da versão do módulo, do pedido do
auxiliar (sem `threads`) e de uma assinatura recursiva de cada elemento.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

VERSAO_MODULO = "1"

_IDADE_PADRAO_S = 30 * 86400


def pasta_padrao() -> Path:
    """Pasta de cache do usuário. Não cria nada."""
    ambiente = os.environ.get("OBIM_CACHE_DIR")
    if ambiente:
        return Path(ambiente)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        raiz = Path(base) if base else Path.home() / "AppData" / "Local"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        raiz = Path(xdg) if xdg else Path.home() / ".cache"
    return raiz / "openbim-studio" / "desenho"


def _serializar(valor, vistos):
    """Converte um valor IFC (ou primitivo) em algo determinístico para o hash."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, bytes):
        return {"$bytes": valor.hex()}
    if isinstance(valor, (list, tuple)):
        return [_serializar(v, vistos) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _serializar(v, vistos) for k, v in valor.items()}
    if hasattr(valor, "is_a") and hasattr(valor, "id"):
        ident = valor.id()
        # id()==0: tipo simples/SELECT sem identidade; sempre serializa o valor.
        if ident > 0:
            if ident in vistos:
                return {"$ref": ident, "tipo": valor.is_a()}
            vistos.add(ident)
        atributos = {}
        try:
            total = len(valor)
        except Exception:
            total = 0
        for i in range(total):
            try:
                nome = valor.attribute_name(i)
            except Exception:
                nome = str(i)
            try:
                atributos[nome] = _serializar(valor[i], vistos)
            except Exception as e:  # atributo ilegível não deve derrubar o desenho
                atributos[nome] = {"$erro": type(e).__name__}
        return {"tipo": valor.is_a(), "atributos": atributos}
    return repr(valor)


def _seguro(fn, padrao=None):
    try:
        return fn()
    except Exception:
        return padrao


def _estilos(entidade, vistos):
    """Estilos (StyledByItem) dos itens de representação, inclusive via MappedItem."""
    saida = []
    reps = _seguro(lambda: entidade.Representation.Representations) or ()
    for rep in reps:
        itens = list(_seguro(lambda: rep.Items) or ())
        for item in list(itens):
            origem = _seguro(lambda: item.MappingSource.MappedRepresentation.Items)
            itens.extend(origem or ())
        for item in itens:
            for st in _seguro(lambda: item.StyledByItem) or ():
                saida.append(_serializar(st, vistos))
    return saida


def _relacoes(entidade, vistos):
    """Relações inversas que o motor usa (ver reduzido.py), por lado relacionado."""
    def colher(atributo, *lados):
        saida = []
        for rel in _seguro(lambda: getattr(entidade, atributo)) or ():
            for lado in lados:
                v = _seguro(lambda: getattr(rel, lado))
                if v is None:
                    continue
                saida.extend(v if isinstance(v, (list, tuple)) else [v])
        return [_serializar(x, vistos) for x in saida]

    return {
        "vaos": colher("HasOpenings", "RelatedOpeningElement"),
        "tipo": colher("IsTypedBy", "RelatingType"),
        "definido": colher("IsDefinedBy", "RelatingType", "RelatingPropertyDefinition"),
        "materiais": colher("HasAssociations", "RelatingMaterial"),
        "preenchimentos": colher("HasFillings", "RelatedBuildingElement"),
        "preenche": colher("FillsVoids", "RelatingOpeningElement"),
        "partes": colher("IsDecomposedBy", "RelatedObjects"),
        "projecoes": colher("HasProjections", "RelatedFeatureElement"),
        "estilos": _estilos(entidade, vistos),
    }


def _entidade(ifc, guid=None, ident=None):
    if guid is not None:
        e = _seguro(lambda: ifc.by_guid(str(guid)))
        if e is not None:
            return e
    if ident is not None:
        return _seguro(lambda: ifc.by_id(int(ident)))
    return None


def _assinatura_entidade(entidade):
    vistos: set[int] = set()
    return {"dados": _serializar(entidade, vistos), "rel": _relacoes(entidade, vistos)}


def _assinatura_elemento(ifc, entrada):
    ident = guid = None
    if isinstance(entrada, (list, tuple)):
        ident = entrada[0] if entrada else None
        guid = entrada[1] if len(entrada) > 1 else None
    bruta = list(entrada) if isinstance(entrada, (list, tuple)) else entrada
    entidade = _entidade(ifc, guid, ident)
    if entidade is None:
        return {"entrada": bruta}
    return {"entrada": bruta, **_assinatura_entidade(entidade)}


def _assinatura_contexto(ifc, pedido):
    """Vista (anotação e pavimento) e unidades do projeto."""
    vista = pedido.get("vista") or {}
    ctx = {}
    for chave in ("guid", "pavimento"):
        if vista.get(chave):
            e = _entidade(ifc, vista[chave])
            ctx[chave] = _assinatura_entidade(e) if e is not None else None
    projetos = _seguro(lambda: ifc.by_type("IfcProject")) or []
    if projetos:
        ctx["unidades"] = _serializar(_seguro(lambda: projetos[0].UnitsInContext), set())
    return ctx


class CacheDesenho:
    def __init__(self, pasta=None, *, idade_max_s: float = _IDADE_PADRAO_S):
        self.pasta = Path(pasta) if pasta is not None else pasta_padrao()
        self.idade_max_s = idade_max_s

    def _arquivo(self, chave: str) -> Path:
        return self.pasta / f"{chave}.json"

    def chave(self, ifc, pedido: dict) -> str:
        pedido = pedido or {}
        limpo = {k: v for k, v in pedido.items() if k != "threads"}
        elementos = [_assinatura_elemento(ifc, e) for e in pedido.get("elementos") or ()]
        material = json.dumps(
            {
                "versao": VERSAO_MODULO,
                "pedido": limpo,
                "elementos": elementos,
                "contexto": _assinatura_contexto(ifc, pedido),
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def obter(self, chave: str) -> dict | None:
        try:
            with open(self._arquivo(chave), "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            return None
        if not isinstance(dados, dict) or "svg" not in dados:
            return None
        return dados

    def guardar(self, chave: str, dados: dict) -> bool:
        try:
            self.pasta.mkdir(parents=True, exist_ok=True)
            destino = self._arquivo(chave)
            fd, tmp = tempfile.mkstemp(prefix=f".{chave}.", suffix=".tmp", dir=self.pasta)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, destino)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception:
            return False
        return True

    def limpar(self, idade_max_s: float | None = None) -> int:
        limite_s = self.idade_max_s if idade_max_s is None else idade_max_s
        try:
            if not self.pasta.is_dir():
                return 0
            limite = time.time() - float(limite_s)
            apagados = 0
            for arquivo in self.pasta.iterdir():
                try:
                    proprio = arquivo.suffix == ".json" or (
                        arquivo.suffix == ".tmp" and arquivo.name.startswith(".")
                    )
                    if proprio and arquivo.is_file() and arquivo.stat().st_mtime < limite:
                        arquivo.unlink()
                        apagados += 1
                except OSError:
                    continue
            return apagados
        except Exception:
            return 0
