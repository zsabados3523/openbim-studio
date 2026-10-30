# SPDX-License-Identifier: AGPL-3.0-or-later
"""Classificação dos 6 casos de divergência ao abrir (ADR-003 §6, v2/02 §6.4). Só lê; nunca cria, apaga ou regrava arquivo."""
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element as UE

from . import obim_zip

D2 = "O modelo foi alterado em outro programa depois da última gravação. A documentação foi verificada: {} referências quebradas."
D2_OP = ("abrir painel de referências", "continuar")
D3, D3_OP = "A documentação é mais nova que o modelo.", ("abrir assim", "procurar outro IFC")
D4 = "Documentação não encontrada. As vistas e pranchas do modelo foram abertas com estilo e posição padrão."
D4_OP = ("localizar arquivo", "abrir só o modelo")
D5, D5_OP = "Esta documentação é de outro projeto e não foi vinculada.", ("escolher outro arquivo", "abrir só o modelo")
D6, D6_OP = "O modelo de {} não foi encontrado.", ("localizar o IFC",)


class LateralRecusado(ValueError):
    """Lateral ilegível, fora do formato ou de versão que só abre para leitura."""


@dataclass(frozen=True)
class Resultado:
    caso: str
    aviso: object = None
    opcoes: tuple = ()
    referencias_quebradas: int = 0
    ambiguas: tuple = ()
    vistas_preservadas: int = 0
    estilo_padrao: bool = False
    vinculado: bool = False
    via_obim: bool = False
    versao_lateral: object = None
    ifc: object = None
    obim: object = None


def _ler_obim(caminho):
    try:
        return obim_zip.ler(caminho)
    except obim_zip.ObimInvalido as e:
        raise LateralRecusado(f"{Path(caminho).name} recusado: {e}") from e


def _confere_lateral(caminho, leitura):
    if leitura.somente_leitura:
        raise LateralRecusado(f"{Path(caminho).name} é de versão que este programa só abre para leitura")


def _numero_documento(d):
    return d.DocumentId if "DocumentId" in d.get_info() else d.Identification


def _vistas(arquivo):
    return [a for a in arquivo.by_type("IfcAnnotation") if a.ObjectType == "DRAWING"]


def _problematicas(leitura, vistas_guids):
    n = 0
    lateral = leitura.lateral
    for ident in lateral.ids("vistas"):
        if lateral.obter("vistas", ident).get("vista_guid") not in vistas_guids:
            n += 1
    for ident in lateral.ids("viewports"):
        if lateral.obter("viewports", ident).get("vista_guid") not in vistas_guids:
            n += 1
    return n


def _pset(arquivo):
    projeto = arquivo.by_type("IfcProject")[0]
    return UE.get_psets(projeto).get("OBIM_Projeto"), projeto


def _par(ifc, obim, leitura, via_obim):
    arquivo = ifcopenshell.open(str(ifc))
    pset, projeto = _pset(arquivo)
    vistas = _vistas(arquivo)
    guids = {a.GlobalId for a in vistas}
    identificacoes = [_numero_documento(d) for d in arquivo.by_type("IfcDocumentInformation") if d.Scope == "SHEET"]
    contagem = Counter(identificacoes)
    ambiguas = tuple(sorted(i for i, c in contagem.items() if c > 1))
    repetidas = sum(c for c in contagem.values() if c > 1)
    manifesto = leitura.manifesto
    versao = leitura.versao_original
    base = dict(via_obim=via_obim, versao_lateral=versao, ifc=ifc, obim=obim, vistas_preservadas=len(vistas), ambiguas=ambiguas)
    if manifesto.get("ifc_projeto_globalid") != projeto.GlobalId or (pset is not None and manifesto.get("LadoId") != pset.get("LadoId")):
        return Resultado("D5", D5, D5_OP, estilo_padrao=True, vinculado=False, **base)
    if pset is not None and manifesto.get("Revisao") is not None and manifesto["Revisao"] > pset.get("Revisao", 0):
        return Resultado("D3", D3, D3_OP, vinculado=True, **base)
    if manifesto.get("ifc_sha256") == _sha256(ifc):
        return Resultado("D6" if via_obim else "D1", vinculado=True, **base)
    n = _problematicas(leitura, guids) + repetidas
    return Resultado("D2", D2.format(n), D2_OP, referencias_quebradas=n, vinculado=True, **base)


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _nome_seguro(nome):
    return bool(nome) and not any(c in nome for c in ("/", "\\")) and nome not in (".", "..")


def classificar(caminho, obim=None):
    entrada = Path(caminho)
    via_obim = entrada.suffix.lower() == ".obim"
    if via_obim:
        leitura = _ler_obim(entrada)
        _confere_lateral(entrada, leitura)
        nome = leitura.manifesto.get("ifc_nome")
        achado = entrada.parent / nome if isinstance(nome, str) and _nome_seguro(nome) else None
        if achado is None or not achado.exists():
            return Resultado("D6", D6.format(nome), D6_OP, via_obim=True, versao_lateral=leitura.versao_original, obim=entrada)
        return _par(achado, entrada, leitura, True)
    ifc = entrada
    obim_path = Path(obim) if obim is not None else ifc.with_suffix(".obim")
    if not obim_path.exists():
        arquivo = ifcopenshell.open(str(ifc))
        pset, _ = _pset(arquivo)
        vistas = len(_vistas(arquivo))
        if pset is None:
            return Resultado("D0", vistas_preservadas=vistas, ifc=ifc, obim=None)
        return Resultado("D4", D4, D4_OP, vistas_preservadas=vistas, estilo_padrao=True, ifc=ifc, obim=None)
    leitura = _ler_obim(obim_path)
    _confere_lateral(obim_path, leitura)
    return _par(ifc, obim_path, leitura, False)
