# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24d (T3, ESPEC_T24bcde.md §3.3 e §4.2): integracao do cache de geometria no app.
NAO editar este arquivo na implementacao. Cobre os 7 mutantes da §3.3 com testes atomicos e stubs/fakes.

CONTRATO DE API (T24d — decisoes do oraculo e do PO para o implementador)
1. `app/openbim_app/desenho/planta.py`:
   - `Planta` (dataclass frozen): novos campos opcionais com defaults retrocompativeis:
     `via_cache: bool = False`, `queda: str | None = None`, `n_faltantes: int = 0`.
   - `gerar_planta(..., *, ..., pasta_cache_geometria: str | Path | None = None) -> Planta`:
     * Keyword-only; valida tipo: aceita `None`, `str` ou `Path` (outros tipos, inclusive `int`/`bool`/`list`,
       levantam `TypeError` ou `ValueError` antes de acionar o auxiliar). String vazia `""` equivale a `None`.
     * Documento salvo e limpo (`arq_cache is not None and sig_chave is not None`): envia
       `pedido["pasta_cache_geometria"] = str(pasta_cache_geometria)` ao auxiliar (`preparar`/`executar`).
     * Documento sujo (`caminho_ifc is None` ou arquivo inexistente) ou retry apos `auxiliar.Divergente`:
       NAO envia `"pasta_cache_geometria"` no pedido ao auxiliar.
     * Propaga `via_cache`, `queda`, `n_faltantes` da resposta do auxiliar e preserva `tempos` (incluindo
       `motor_s`, `cache_s`, `corte_s`), sem sobrescrever `Planta.faltantes` / `Planta.incompleta` (T19i1).
2. `app/openbim_app/desenho/cache.py`:
   - `CacheDesenho.chave(ifc, pedido, cancelar=None, *, arquivo=None, assinatura=None) -> str`:
     * Ignora `"pasta_cache_geometria"` em `pedido` nos dois modos (arquivo e grafo), assim como `"threads"`.
     * Mudar `OBIM_CACHE_DIR` ou `pasta_cache_geometria` nao altera a chave do cache de vista (T15p).
3. `app/openbim_app/desenho/gerente.py` (e `filho.py` opcional):
   - Decisao PO §4.2 item 3, opcao (b): `GerenteDesenho.__init__(..., construir_cache: bool = False, ...)`
     MANTEM `construir_cache=False` por padrao (preserva T23e e T26; `main_window.py` nao e conectado nesta fatia).
     * `construir_cache=False`: `aquecer`/`salvar` nunca inicia `filho.construir(...)`.
     * `construir_cache=True`: `aquecer`/`salvar` inicia `filho.construir(str(pasta_geometria()), ...)` em
       segundo plano; pedidos de planta subsequentes usam o cache assim que disponivel.
   - `GerenteDesenho.pedir(...)`:
     * NUNCA consulta `estado_construcao` (nem via `filho.estado_construcao()`, nem via `filho.executar(...)`)
       nem abre SQLite (`sqlite3.connect`) na thread de quem chama `pedir()`. Qualquer consulta/verificacao
       ocorre apenas na thread de fundo (`_rodar`/`_motor_padrao`).
     * Documento sujo (`revisao != revisao_salva`, `revisao is None`, `revisao_salva is None`, `caminho_ifc is None`
       ou inexistente) ou invalidado (`invalidar()` antes de `_motor`): nao entrega `pasta_cache_geometria`.
   - `_motor_padrao`:
     * Em `tipo == "planta"`, documento salvo e limpo (`caminho_ifc` + `assinatura_ifc` validos) com banco
       `cache_geometria.sqlite` disponivel em `pasta_geometria()` (ou `pasta_cache_geometria` explicito):
       repassa `pasta_cache_geometria=str(pasta)` para `gerar_planta`.
     * NAO bloqueia o caminho (B) apenas porque `pendentes > 0` ou `filho.construcao_ativa is True` quando o
       pavimento pedido ja esta completo no banco.
     * Em `tipo == "corte"`, NAO repassa `pasta_cache_geometria`.
     * Propaga `via_cache: bool`, `queda: str | None`, `n_faltantes: int` e `tempos` (incluindo `motor_s`)
       no dict `dados` retornado e emitido no sinal `GerenteDesenho.pronto`.
     * Guarda de refino: quando `r.via_cache` e `True`, NUNCA chama `refino.refinar_pesados` (nem emite
       `previa` de refino), mesmo com `pesados="silhueta"` ou `pesados` preenchido; quando `r.via_cache`
       e `False` e `pesados` nao vazio, `refino.refinar_pesados` continua rodando normalmente.
"""
from __future__ import annotations

import inspect
import os
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar as A
from openbim_app.desenho import cache as C
from openbim_app.desenho import corte as CO
from openbim_app.desenho import gerente as G
from openbim_app.desenho import planta as P
from openbim_app.desenho import refino as R
from openbim_app.desenho import selecao as S
from openbim_app.desenho.gerente import GerenteDesenho
from openbim_app.desenho.selecao import Selecao

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

NOME_BANCO = "cache_geometria.sqlite"
_SVG_OK = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M 0,0 L 1,1"/></svg>'


# ------------------------------------------------------------------ stubs/fakes sem IFC do PO nem Qt


class _FakeEl:
    """Entidade IFC minima para planta.py e CacheDesenho.chave (sem ifcopenshell)."""

    def __init__(self, ident: int, gid: str, tipo: str, **attrs):
        self._id = ident
        self._tipo = tipo
        self.GlobalId = gid
        self.ObjectPlacement = None
        self.Elevation = attrs.pop("Elevation", 0.0)
        self.Name = attrs.pop("Name", f"{tipo}_{ident}")
        self._attrs = [("GlobalId", gid), ("Name", self.Name), *attrs.items()]

    def id(self) -> int:
        return self._id

    def is_a(self, nome: str | None = None):
        return self._tipo if nome is None else (self._tipo == nome)

    def __len__(self) -> int:
        return len(self._attrs)

    def attribute_name(self, idx: int) -> str:
        return self._attrs[idx][0]

    def __getitem__(self, idx: int):
        return self._attrs[idx][1]


class _FakeIfc:
    """Modelo IFC minimo em memoria (sem geometria real)."""

    def __init__(self):
        self._proj = _FakeEl(1, "PROJ_GUID", "IfcProject", UnitsInContext="METRE")
        self._pav = _FakeEl(10, "PAV_GUID", "IfcBuildingStorey", Elevation=0.0, Name="Terreo")
        self._ann = _FakeEl(20, "VISTA_GUID", "IfcAnnotation", Name="Planta")
        self._w1 = _FakeEl(101, "WALL_1_GUID", "IfcWall", Name="Parede1")
        self._w2 = _FakeEl(102, "WALL_2_GUID", "IfcWall", Name="Parede2")
        self._por_id = {e.id(): e for e in (self._proj, self._pav, self._ann, self._w1, self._w2)}
        self._por_gid = {e.GlobalId: e for e in self._por_id.values()}

    def by_id(self, ident: int):
        return self._por_id[int(ident)]

    def by_guid(self, gid: str):
        return self._por_gid[str(gid)]

    def by_type(self, tipo: str):
        return [e for e in self._por_id.values() if e.is_a(tipo)]

    def write(self, caminho: str) -> None:
        Path(caminho).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")


def _sel_fake() -> Selecao:
    return Selecao(
        ids=(101, 102),
        tipo="PLANTA",
        pavimento=10,
        faixa=None,
        ocultos_por_classe={},
        sem_geometria=0,
        caixas_envolventes={
            101: (0.0, 0.0, 0.0, 4.0, 0.2, 3.0),
            102: (0.0, 2.0, 0.0, 4.0, 2.2, 3.0),
        },
    )


def _stub_planta_env(monkeypatch) -> _FakeIfc:
    """Isola planta.gerar_planta de ifcopenshell real e selecao real."""
    ifc = _FakeIfc()
    monkeypatch.setattr(vistas_ifc, "ler_vista", lambda _f, _g: {"tipo": "PLANTA"})
    monkeypatch.setattr(P, "_altura_corte", lambda _f, _a: 1.2)
    monkeypatch.setattr(P.ifcopenshell.util.unit, "calculate_unit_scale", lambda _f: 1.0)
    monkeypatch.setattr(S, "_validar_categorias", lambda _f, _c: None)
    monkeypatch.setattr(S, "selecionar", lambda _f, _g, **kw: _sel_fake())
    return ifc


def _resp_aux(
    *,
    via_cache: bool = True,
    queda: str | None = None,
    n_faltantes: int = 0,
    secoes_parciais: int = 0,
    motor_s: float = 0.07,
    cache_s: float = 0.02,
    corte_s: float = 0.01,
    pesados: list[dict] | None = None,
) -> dict:
    return {
        "ok": True,
        "svg": _SVG_OK,
        "n_paths": 1,
        "enviados": [101, 102],
        "caixas": [],
        "em_cache": [],
        "pesados": list(pesados or ()),
        "falhas_geometria": [],
        "tempos": {
            "abrir_s": 0.01,
            "geo_s": 0.0 if via_cache else 0.4,
            "write_s": 0.0 if via_cache else 0.1,
            "finalize_s": 0.0 if via_cache else 0.05,
            "cache_s": cache_s,
            "corte_s": corte_s,
            "motor_s": motor_s,
        },
        "via_cache": via_cache,
        "queda": queda,
        "n_faltantes": n_faltantes,
        "secoes_parciais": secoes_parciais,
    }


def _criar_banco_valido(pasta: Path) -> Path:
    """Cria `cache_geometria.sqlite` com cabecalho valido do construtor."""
    from obim_geometria import cache_geometria as CG
    from obim_geometria import construtor

    pasta.mkdir(parents=True, exist_ok=True)
    cache = CG.abrir_cache(pasta, cabecalho=CG.cabecalho_atual(tesselacao=construtor.TESSELACAO))
    cache.fechar()
    return pasta / CG.NOME_BANCO


def _arquivo_ifc(tmp_path: Path, nome: str = "modelo.ifc") -> Path:
    arq = tmp_path / nome
    arq.write_text("ISO-10303-21;\n/* fake ifc */\nEND-ISO-10303-21;\n", encoding="utf-8")
    return arq


@pytest.fixture(scope="module")
def qt_app():
    QtCore = pytest.importorskip("PySide6.QtCore")
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


def _girar_qt(qt_app, cond, timeout_s: float = 10.0) -> bool:
    fim = time.monotonic() + timeout_s
    while time.monotonic() < fim:
        qt_app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    qt_app.processEvents()
    return bool(cond())


def _esperar_fundo(g: GerenteDesenho, timeout_s: float = 10.0) -> None:
    fim = time.monotonic() + timeout_s
    while g._threads and time.monotonic() < fim:
        time.sleep(0.01)
    assert not g._threads


def _pedir_e_esperar(qt_app, g: GerenteDesenho, tipo: str, ifc, gid: str, **kw) -> dict:
    prontos: list[tuple[str, dict]] = []
    falhas: list[tuple[str, str]] = []
    g.pronto.connect(lambda c, d: prontos.append((c, d)))
    g.falhou.connect(lambda c, m: falhas.append((c, m)))
    chave = g.pedir(tipo, ifc, gid, **kw)
    assert _girar_qt(qt_app, lambda: bool(prontos or falhas)), "timeout aguardando sinal do gerente"
    assert not falhas, f"gerente falhou: {falhas}"
    assert prontos[-1][0] == chave
    return prontos[-1][1]


# ================================================================== Contrato / Interface


def test_contrato_assinaturas_e_defaults():
    """Contrato: defaults retrocompativeis em GerenteDesenho, gerar_planta e Planta."""
    params_g = inspect.signature(GerenteDesenho.__init__).parameters
    assert params_g["construir_cache"].default is False, "decisao PO (b): default construir_cache continua False"

    params_p = inspect.signature(P.gerar_planta).parameters
    assert "pasta_cache_geometria" in params_p
    assert params_p["pasta_cache_geometria"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params_p["pasta_cache_geometria"].default is None

    pl = P.Planta(
        svg=_SVG_OK,
        n_paths=1,
        selecao=_sel_fake(),
        tempos={"geo_s": 0.0},
        unidade_escala=1.0,
        altura_corte=1.2,
        caixas=(),
    )
    assert pl.via_cache is False
    assert pl.queda is None
    assert pl.n_faltantes == 0
    assert type(pl.secoes_parciais) is int and pl.secoes_parciais == 0


@pytest.mark.parametrize("invalido", [123, True, ["/tmp/geo"]])
def test_gerar_planta_rejeita_pasta_cache_geometria_invalida(monkeypatch, tmp_path, invalido):
    """Contrato: tipo invalido em pasta_cache_geometria falha antes de chamar o auxiliar."""
    assert "pasta_cache_geometria" in inspect.signature(P.gerar_planta).parameters
    ifc = _stub_planta_env(monkeypatch)
    arq = _arquivo_ifc(tmp_path)
    chamadas = []
    with pytest.raises((TypeError, ValueError)):
        P.gerar_planta(
            ifc,
            "VISTA_GUID",
            caminho_ifc=arq,
            pasta_cache_geometria=invalido,
            executor=lambda q: (chamadas.append(q), _resp_aux())[1],
        )
    assert chamadas == []


# ================================================================== Mutante 1: salvo/limpo vs sujo/Divergente/corte


@pytest.mark.parametrize("como_path", [False, True])
def test_planta_envia_pasta_cache_em_documento_salvo_e_limpo(monkeypatch, tmp_path, como_path):
    """Mutante 1 (positivo): documento salvo e limpo inclui pasta_cache_geometria no pedido ao auxiliar."""
    ifc = _stub_planta_env(monkeypatch)
    arq = _arquivo_ifc(tmp_path)
    pasta_geo = tmp_path / "geo"
    enviados: list[dict] = []

    P.gerar_planta(
        ifc,
        "VISTA_GUID",
        caminho_ifc=arq,
        pasta_cache_geometria=pasta_geo if como_path else str(pasta_geo),
        executor=lambda q: (enviados.append(dict(q)), _resp_aux())[1],
    )
    assert len(enviados) == 1
    assert enviados[0].get("pasta_cache_geometria") == str(pasta_geo)

    # String vazia ou None nao envia chave
    for vazio in ("", None):
        enviados.clear()
        P.gerar_planta(
            ifc,
            "VISTA_GUID",
            caminho_ifc=arq,
            pasta_cache_geometria=vazio,
            executor=lambda q: (enviados.append(dict(q)), _resp_aux(via_cache=False))[1],
        )
        assert "pasta_cache_geometria" not in enviados[0]


def test_planta_nao_envia_pasta_cache_em_documento_sujo_ou_inexistente(monkeypatch, tmp_path):
    """Mutante 1: documento sujo (caminho_ifc=None) ou arquivo inexistente nunca leva pasta_cache_geometria."""
    ifc = _stub_planta_env(monkeypatch)
    pasta_geo = tmp_path / "geo"

    for caminho in (None, tmp_path / "nao_existe.ifc"):
        enviados: list[dict] = []
        P.gerar_planta(
            ifc,
            "VISTA_GUID",
            caminho_ifc=caminho,
            pasta_cache_geometria=pasta_geo,
            executor=lambda q: (enviados.append(dict(q)), _resp_aux(via_cache=False))[1],
        )
        assert len(enviados) == 1
        assert "pasta_cache_geometria" not in enviados[0]


def test_planta_remove_pasta_cache_no_retry_apos_divergente(monkeypatch, tmp_path):
    """Mutante 1: retry apos auxiliar.Divergente usa IFC em memoria e nunca reenvia pasta_cache_geometria."""
    ifc = _stub_planta_env(monkeypatch)
    arq = _arquivo_ifc(tmp_path)
    pasta_geo = tmp_path / "geo"
    pedidos_recebidos: list[dict] = []

    def _exec(q: dict) -> dict:
        pedidos_recebidos.append(dict(q))
        if len(pedidos_recebidos) == 1:
            return {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "arquivo mudou", "rastro": ""}}
        return _resp_aux(via_cache=False, queda=None, n_faltantes=0, motor_s=0.05)

    pl = P.gerar_planta(
        ifc,
        "VISTA_GUID",
        caminho_ifc=arq,
        pasta_cache_geometria=pasta_geo,
        executor=_exec,
    )
    assert len(pedidos_recebidos) == 2
    assert pedidos_recebidos[0].get("pasta_cache_geometria") == str(pasta_geo)
    assert "pasta_cache_geometria" not in pedidos_recebidos[1], "retry apos Divergente nao pode levar pasta_cache_geometria"
    assert pl.divergente is True
    assert pl.via_cache is False
