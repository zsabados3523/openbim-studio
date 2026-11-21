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


@pytest.mark.parametrize(
    "caso,kw_doc",
    [
        ("sujo_revisao_diferente", {"usar_arq": True, "revisao": 2, "revisao_salva": 1}),
        ("sem_revisao", {"usar_arq": True, "revisao": None, "revisao_salva": 1}),
        ("sem_revisao_salva", {"usar_arq": True, "revisao": 1, "revisao_salva": None}),
        ("sem_caminho", {"usar_arq": False, "revisao": 1, "revisao_salva": 1}),
    ],
)
def test_gerente_nao_envia_pasta_cache_quando_sujo_ou_invalidado(qt_app, monkeypatch, tmp_path, caso, kw_doc):
    """Mutante 1 (gerente): sujo ou invalidado nao envia pasta_cache_geometria; salvo e limpo envia."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = C.pasta_geometria()
    _criar_banco_valido(pasta_geo)
    arq = _arquivo_ifc(tmp_path)
    ifc = _FakeIfc()
    capturados: list[dict] = []

    def _fake_gerar_planta(f, gid, **kw):
        capturados.append(dict(kw))
        return P.Planta(
            svg=_SVG_OK,
            n_paths=1,
            selecao=_sel_fake(),
            tempos={"geo_s": 0.0, "motor_s": 0.03},
            unidade_escala=1.0,
            altura_corte=1.2,
            caixas=(),
            via_cache=bool(kw.get("pasta_cache_geometria")),
            queda=None,
            n_faltantes=0,
        )

    monkeypatch.setattr(P, "gerar_planta", _fake_gerar_planta)
    g = GerenteDesenho(cache=C.CacheDesenho(tmp_path / "vista"), filho_persistente=False)
    try:
        # Controle positivo: documento salvo e limpo recebe pasta_cache_geometria
        _pedir_e_esperar(qt_app, g, "planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
        assert capturados[-1].get("pasta_cache_geometria") == str(pasta_geo)

        # Caso sujo: nunca envia pasta_cache_geometria (mesmo com banco presente)
        capturados.clear()
        _pedir_e_esperar(
            qt_app,
            g,
            "planta",
            ifc,
            "VISTA_GUID",
            caminho_ifc=arq if kw_doc["usar_arq"] else None,
            revisao=kw_doc["revisao"],
            revisao_salva=kw_doc["revisao_salva"],
        )
        assert not capturados[-1].get("pasta_cache_geometria"), f"{caso}: nao deve enviar pasta_cache_geometria"

        # Corrida de invalidar() entre pedir() e _motor: limpa tambem pasta_cache_geometria
        if caso == "sujo_revisao_diferente":
            capturados.clear()
            orig_vaga = g._adquirir_vaga

            def _vaga_invalida(ped, opcoes):
                g.invalidar()
                return orig_vaga(ped, opcoes)

            monkeypatch.setattr(g, "_adquirir_vaga", _vaga_invalida)
            _pedir_e_esperar(qt_app, g, "planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
            assert not capturados[-1].get("pasta_cache_geometria"), "invalidar() em voo nao pode enviar pasta_cache_geometria"
    finally:
        g.fechar()


def test_motor_padrao_nao_envia_pasta_cache_em_corte(monkeypatch, tmp_path):
    """Mutante 1 (escopo): _motor_padrao envia pasta_cache_geometria em planta salva, nunca em corte."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = C.pasta_geometria()
    _criar_banco_valido(pasta_geo)
    arq = _arquivo_ifc(tmp_path)
    ifc = _FakeIfc()
    kw_planta: list[dict] = []
    kw_corte: list[dict] = []

    def _fake_planta(f, gid, **kw):
        kw_planta.append(dict(kw))
        return P.Planta(
            svg=_SVG_OK, n_paths=1, selecao=_sel_fake(), tempos={"motor_s": 0.02},
            unidade_escala=1.0, altura_corte=1.2, caixas=(),
            via_cache=bool(kw.get("pasta_cache_geometria")), queda=None, n_faltantes=0,
        )

    def _fake_corte(f, gid, **kw):
        kw_corte.append(dict(kw))
        return SimpleNamespace(svg=_SVG_OK, n_paths=1, tempos={"motor_s": 0.02}, caixas=(), em_cache=())

    monkeypatch.setattr(P, "gerar_planta", _fake_planta)
    monkeypatch.setattr(CO, "gerar_corte", _fake_corte)
    cache_v = C.CacheDesenho(tmp_path / "vista")

    G._motor_padrao(
        "planta", ifc, "VISTA_GUID", {"caminho_ifc": arq},
        cancelar=threading.Event(), progresso=lambda _m: None, cache=cache_v,
    )
    G._motor_padrao(
        "corte", ifc, "VISTA_GUID", {"caminho_ifc": arq},
        cancelar=threading.Event(), progresso=lambda _m: None, cache=cache_v,
    )
    assert kw_planta[0].get("pasta_cache_geometria") == str(pasta_geo)
    assert "pasta_cache_geometria" not in kw_corte[0]


# ================================================================== Mutante 2: nunca na thread de pedir()


def test_pedir_nao_consulta_estado_construcao_nem_sqlite_na_thread_chamadora(qt_app, monkeypatch, tmp_path):
    """Mutante 2: pedir() nao bloqueia nem consulta estado_construcao/SQLite na thread chamadora."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = C.pasta_geometria()
    _criar_banco_valido(pasta_geo)
    arq = _arquivo_ifc(tmp_path)
    ifc = _stub_planta_env(monkeypatch)
    thread_pedir = threading.current_thread()

    threads_estado: list[threading.Thread] = []
    threads_executar: list[tuple[str, threading.Thread]] = []
    threads_sqlite: list[threading.Thread] = []

    orig_connect = sqlite3.connect

    def _spy_connect(*a, **kw):
        t = threading.current_thread()
        threads_sqlite.append(t)
        if t is thread_pedir:
            time.sleep(0.3)
        return orig_connect(*a, **kw)

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)

    class _FilhoLento:
        def __init__(self, arquivo, **kw):
            self.arquivo = str(arquivo)
            self.construcao_ativa = True

        def estado_construcao(self, *a, **kw):
            threads_estado.append(threading.current_thread())
            time.sleep(0.25)
            return {"ativo": True, "pendentes": 3, "feitos": 2, "parado": None, "erro": None}

        def executar(self, pedido, **kw):
            op = pedido.get("op", "")
            threads_executar.append((op, threading.current_thread()))
            if op == "estado_construcao":
                threads_estado.append(threading.current_thread())
                time.sleep(0.25)
                return {"ativo": True, "pendentes": 3, "feitos": 2, "parado": None, "erro": None}
            assert pedido.get("pasta_cache_geometria") == str(pasta_geo)
            return _resp_aux(via_cache=True, queda=None, n_faltantes=0, motor_s=0.06)

        aquecer = lambda self, **kw: {"aberto": True}
        construir = lambda self, pasta, **kw: {"aceito": True, "pendentes": 3}
        podar = salvar = invalidar = fechar = lambda self: None

    monkeypatch.setattr(G, "FilhoPersistente", _FilhoLento)
    g = GerenteDesenho(cache=C.CacheDesenho(tmp_path / "vista"), filho_persistente=True)
    prontos: list[tuple[str, dict]] = []
    falhas: list[tuple[str, str]] = []
    g.pronto.connect(lambda c, d: prontos.append((c, d)))
    g.falhou.connect(lambda c, m: falhas.append((c, m)))
    try:
        t0 = time.monotonic()
        g.pedir("planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
        dt_pedir = time.monotonic() - t0

        assert dt_pedir < 0.15, f"pedir() bloqueou {dt_pedir:.3f}s na thread chamadora"
        assert _girar_qt(qt_app, lambda: bool(prontos or falhas))
        assert not falhas, f"falhou: {falhas}"
        assert all(t is not thread_pedir for t in threads_estado), "estado_construcao rodou na thread de pedir()"
        assert all(t is not thread_pedir for _, t in threads_executar), "filho.executar rodou na thread de pedir()"
        assert all(t is not thread_pedir for t in threads_sqlite), "sqlite3.connect rodou na thread de pedir()"
        assert prontos[-1][1]["via_cache"] is True
    finally:
        g.fechar()


# ================================================================== Mutante 3: pavimento completo com pendentes > 0


def test_pavimento_completo_com_pendentes_positivos_usa_cache_stub(qt_app, monkeypatch, tmp_path):
    """Mutante 3 (stub): pendentes > 0 em outros pavimentos nao bloqueia caminho (B) para pavimento pronto."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = C.pasta_geometria()
    _criar_banco_valido(pasta_geo)
    arq = _arquivo_ifc(tmp_path)
    ifc = _stub_planta_env(monkeypatch)
    pedidos_desenho: list[dict] = []

    class _FilhoConstruindo:
        def __init__(self, arquivo, **kw):
            self.arquivo = str(arquivo)
            self.construcao_ativa = True

        def estado_construcao(self, *a, **kw):
            return {"ativo": True, "pendentes": 25, "feitos": 4, "parado": None, "erro": None}

        def executar(self, pedido, **kw):
            if pedido.get("op") == "estado_construcao":
                return self.estado_construcao()
            pedidos_desenho.append(dict(pedido))
            return _resp_aux(via_cache=True, queda=None, n_faltantes=0, motor_s=0.04)

        aquecer = lambda self, **kw: {"aberto": True}
        construir = lambda self, pasta, **kw: {"aceito": True, "pendentes": 25}
        podar = salvar = invalidar = fechar = lambda self: None

    monkeypatch.setattr(G, "FilhoPersistente", _FilhoConstruindo)
    g = GerenteDesenho(cache=C.CacheDesenho(tmp_path / "vista"), filho_persistente=True)
    try:
        dados = _pedir_e_esperar(qt_app, g, "planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
        assert len(pedidos_desenho) == 1
        assert pedidos_desenho[0].get("pasta_cache_geometria") == str(pasta_geo)
        assert dados["via_cache"] is True
        assert dados["queda"] is None
        assert dados["n_faltantes"] == 0
        assert dados["tempos"]["motor_s"] == pytest.approx(0.04)
    finally:
        g.fechar()


def test_pavimento_completo_com_pendentes_positivos_usa_cache_banco_real(qt_app, monkeypatch, tmp_path):
    """Mutante 3 (integracao sintetica): 2 pavimentos, so Terreo no SQLite (pendentes=1); Terreo sai via_cache=True."""
    import ifcopenshell.api
    import numpy as np
    from obim_geometria import caixas, construtor, desenho

    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = C.pasta_geometria()

    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject", name="P_T24D")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api("root.create_entity", f, ifc_class="IfcSite", name="S")
    bld = api("root.create_entity", f, ifc_class="IfcBuilding", name="B")
    pav1 = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    pav1.Elevation = 0.0
    pav2 = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Superior")
    pav2.Elevation = 3.0
    for pai, filhos in ((proj, [site]), (site, [bld]), (bld, [pav1, pav2])):
        api("aggregate.assign_object", f, relating_object=pai, products=filhos)

    def _parede(pav, nome: str, z: float):
        w = api("root.create_entity", f, ifc_class="IfcWall", name=nome)
        api("spatial.assign_container", f, relating_structure=pav, products=[w])
        rep = api("geometry.add_wall_representation", f, context=body, length=4.0, height=2.8, thickness=0.2)
        api("geometry.assign_representation", f, product=w, representation=rep)
        m = np.eye(4)
        m[2, 3] = z
        api("geometry.edit_object_placement", f, product=w, matrix=m, is_si=False)
        return w

    w_terreo = _parede(pav1, "W_TERREO", 0.0)
    _parede(pav2, "W_SUPERIOR", 3.0)
    gid_vista = vistas_ifc.criar_vista(f, "Planta_Terreo", "PLANTA", escala="1:50", origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 3.0))
    api("spatial.assign_container", f, relating_structure=pav1, products=[f.by_guid(gid_vista)])

    arq = tmp_path / "dois_pavimentos.ifc"
    f.write(str(arq))
    st = arq.stat()

    # Grava SOMENTE a parede do Terreo no cache SQLite (Superior fica pendente -> pendentes=1)
    db = construtor.abrir_banco(pasta_geo)
    try:
        res_lote = construtor.construir_lote(
            f,
            db,
            [w_terreo.id()],
            documento=construtor.documento_de(str(arq)),
            assinatura=f"{st.st_size}:{st.st_mtime_ns}",
            memo={},
        )
        assert res_lote["tesseladas"] == 1
    finally:
        db.fechar()

    chamadas_refino = []
    monkeypatch.setattr(R, "refinar_pesados", lambda *a, **kw: (chamadas_refino.append((a, kw)), a[2])[1])

    class _FilhoEmProcesso:
        def __init__(self, arquivo, **kw):
            self.arquivo = str(arquivo)
            self.construcao_ativa = True

        def estado_construcao(self, *a, **kw):
            return {"ativo": True, "pendentes": 1, "feitos": 1, "parado": None, "erro": None}

        def executar(self, pedido, **kw):
            op = pedido.get("op")
            if op == "estado_construcao":
                return self.estado_construcao()
            if op == "caixas":
                return caixas.processar(pedido)
            if op == "desenho":
                return desenho.processar(pedido)
            return {"ok": True}

        aquecer = lambda self, **kw: {"aberto": True}
        construir = lambda self, pasta, **kw: {"aceito": True, "pendentes": 1}
        podar = salvar = invalidar = fechar = lambda self: None

    monkeypatch.setattr(G, "FilhoPersistente", _FilhoEmProcesso)
    g = GerenteDesenho(cache=C.CacheDesenho(tmp_path / "vista"), filho_persistente=True)
    try:
        dados = _pedir_e_esperar(qt_app, g, "planta", f, gid_vista, caminho_ifc=arq, revisao=1, revisao_salva=1)
        assert dados["via_cache"] is True
        assert dados["queda"] is None
        assert dados["n_faltantes"] == 0
        assert dados["n_paths"] > 0
        assert isinstance(dados["tempos"]["motor_s"], float) and dados["tempos"]["motor_s"] >= 0.0
        assert chamadas_refino == [], "caminho (B) nao deve acionar refino.refinar_pesados"
    finally:
        g.fechar()


# ================================================================== Mutante 4: CacheDesenho.chave ignora pasta_cache_geometria


def test_cache_chave_ignora_pasta_cache_geometria_grafo_e_arquivo(monkeypatch, tmp_path):
    """Mutante 4: CacheDesenho.chave ignora pasta_cache_geometria nos modos grafo e arquivo e ao mudar OBIM_CACHE_DIR."""
    ifc = _FakeIfc()
    arq = _arquivo_ifc(tmp_path)
    _, sig = C.resolver_assinatura(arq)
    base = {
        "protocolo": 1,
        "op": "desenho",
        "elementos": [[101, "WALL_1_GUID"], [102, "WALL_2_GUID"]],
        "vista": {"tipo": "PLANTA", "guid": "VISTA_GUID", "altura_corte_m": 1.2, "pavimento": "PAV_GUID", "escala": 1.0},
        "moveis_como_caixa": False,
    }
    p_a = {**base, "pasta_cache_geometria": str(tmp_path / "dir_a" / "geometria")}
    p_b = {**base, "pasta_cache_geometria": str(tmp_path / "dir_b" / "geometria")}
    p_none = {**base, "pasta_cache_geometria": None}
    p_diff = {**base, "moveis_como_caixa": True}

    cache = C.CacheDesenho(tmp_path / "vista")

    # Modo grafo
    assert cache.chave(ifc, base) == cache.chave(ifc, p_a) == cache.chave(ifc, p_b) == cache.chave(ifc, p_none)
    assert cache.chave(ifc, base) != cache.chave(ifc, p_diff)

    # Modo arquivo (assinatura inferida e explicita)
    assert cache.chave(ifc, base, arquivo=arq) == cache.chave(ifc, p_a, arquivo=arq) == cache.chave(ifc, p_b, arquivo=arq)
    assert cache.chave(ifc, base, arquivo=arq, assinatura=sig) == cache.chave(ifc, p_a, arquivo=arq, assinatura=sig)
    assert cache.chave(ifc, base, arquivo=arq) != cache.chave(ifc, p_diff, arquivo=arq)

    # Mudanca de OBIM_CACHE_DIR nao invalida chave do cache de vista
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "env_1"))
    k1 = cache.chave(ifc, {**base, "pasta_cache_geometria": str(C.pasta_geometria())}, arquivo=arq)
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "env_2"))
    k2 = cache.chave(ifc, {**base, "pasta_cache_geometria": str(C.pasta_geometria())}, arquivo=arq)
    assert k1 == k2


def test_gerar_planta_reaproveita_cache_vista_ao_mudar_pasta_geometria(monkeypatch, tmp_path):
    """Mutante 4 (integrado): hit de CacheDesenho em gerar_planta independe de pasta_cache_geometria."""
    ifc = _stub_planta_env(monkeypatch)
    arq = _arquivo_ifc(tmp_path)
    cache_v = C.CacheDesenho(tmp_path / "vista")
    chamadas = []

    def _exec(q: dict) -> dict:
        chamadas.append(dict(q))
        return _resp_aux(via_cache=True, queda=None, n_faltantes=0, motor_s=0.09)

    p1 = P.gerar_planta(ifc, "VISTA_GUID", caminho_ifc=arq, cache=cache_v, pasta_cache_geometria=tmp_path / "g1", executor=_exec)
    p2 = P.gerar_planta(ifc, "VISTA_GUID", caminho_ifc=arq, cache=cache_v, pasta_cache_geometria=tmp_path / "g2", executor=_exec)
    p3 = P.gerar_planta(ifc, "VISTA_GUID", caminho_ifc=arq, cache=cache_v, pasta_cache_geometria=None, executor=_exec)

    assert len(chamadas) == 1, "mudar pasta_cache_geometria nao pode invalidar o cache de vista"
    assert p1.svg == p2.svg == p3.svg
    assert p1.via_cache is True and p2.via_cache is True and p3.via_cache is True


# ================================================================== Mutante 5: telemetria em Planta e pronto


@pytest.mark.parametrize(
    "via_cache,queda,n_faltantes,motor_s",
    [
        (True, None, 0, 0.123),
        (False, "cache_incompleto", 3, 0.045),
    ],
)
def test_planta_propaga_telemetria_cache_e_queda(monkeypatch, tmp_path, via_cache, queda, n_faltantes, motor_s):
    """Mutante 5 (Planta): gerar_planta propaga via_cache, queda, n_faltantes e tempos['motor_s'] sem colidir com T19i1."""
    ifc = _stub_planta_env(monkeypatch)
    arq = _arquivo_ifc(tmp_path)

    pl = P.gerar_planta(
        ifc,
        "VISTA_GUID",
        caminho_ifc=arq,
        pasta_cache_geometria=tmp_path / "geo",
        executor=lambda _q: _resp_aux(via_cache=via_cache, queda=queda, n_faltantes=n_faltantes, motor_s=motor_s, cache_s=0.03),
    )
    assert pl.via_cache is via_cache
    assert pl.queda == queda
    assert pl.n_faltantes == n_faltantes
    assert pl.tempos["motor_s"] == pytest.approx(motor_s)
    assert pl.tempos["cache_s"] == pytest.approx(0.03)
    assert pl.faltantes == () and pl.incompleta is False


@pytest.mark.parametrize(
    "via_cache,queda,n_faltantes,motor_s",
    [
        (True, None, 0, 0.11),
        (False, "secao_aberta", 0, 0.08),
        (False, "cache_incompleto", 4, 0.0),
    ],
)
def test_motor_padrao_e_sinal_pronto_propagam_telemetria(qt_app, monkeypatch, tmp_path, via_cache, queda, n_faltantes, motor_s):
    """Mutante 5 (gerente): _motor_padrao e sinal pronto carregam via_cache, queda, n_faltantes e tempos['motor_s']."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    _criar_banco_valido(C.pasta_geometria())
    arq = _arquivo_ifc(tmp_path)
    ifc = _FakeIfc()

    def _fake_planta(f, gid, **kw):
        return P.Planta(
            svg=_SVG_OK,
            n_paths=1,
            selecao=_sel_fake(),
            tempos={"geo_s": 0.0, "cache_s": 0.02, "motor_s": motor_s},
            unidade_escala=1.0,
            altura_corte=1.2,
            caixas=(),
            via_cache=via_cache,
            queda=queda,
            n_faltantes=n_faltantes,
        )

    monkeypatch.setattr(P, "gerar_planta", _fake_planta)
    cache_v = C.CacheDesenho(tmp_path / "vista")

    # (a) _motor_padrao direto (sem Qt)
    dados_dir = G._motor_padrao(
        "planta", ifc, "VISTA_GUID", {"caminho_ifc": arq},
        cancelar=threading.Event(), progresso=lambda _m: None, cache=cache_v,
    )
    assert dados_dir["via_cache"] is via_cache
    assert dados_dir["queda"] == queda
    assert dados_dir["n_faltantes"] == n_faltantes
    assert dados_dir["tempos"]["motor_s"] == pytest.approx(motor_s)

    # (b) sinal pronto do GerenteDesenho
    g = GerenteDesenho(cache=cache_v, filho_persistente=False)
    try:
        dados_sig = _pedir_e_esperar(qt_app, g, "planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
        assert dados_sig["via_cache"] is via_cache
        assert dados_sig["queda"] == queda
        assert dados_sig["n_faltantes"] == n_faltantes
        assert dados_sig["tempos"]["motor_s"] == pytest.approx(motor_s)
    finally:
        g.fechar()


# ================================================================== Mutante 6: refino.refinar_pesados nao roda com via_cache=True


def test_motor_padrao_nao_chama_refino_quando_via_cache_true(monkeypatch, tmp_path):
    """Mutante 6: quando via_cache=True, _motor_padrao nunca chama refino.refinar_pesados (nem previa de refino)."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    _criar_banco_valido(C.pasta_geometria())
    arq = _arquivo_ifc(tmp_path)
    ifc = _FakeIfc()
    chamadas_refino = []
    previas = []

    def _fake_planta(f, gid, **kw):
        # Mesmo que pesados venha nao vazio (defesa contra mutante), via_cache=True deve bloquear o refino
        return P.Planta(
            svg=_SVG_OK,
            n_paths=1,
            selecao=_sel_fake(),
            tempos={"geo_s": 0.0, "motor_s": 0.05},
            unidade_escala=1.0,
            altura_corte=1.2,
            caixas=(),
            pesados=({"guid": "WALL_1_GUID", "id": 101, "faces": 99999},),
            pedido={"protocolo": 1, "op": "desenho", "elementos": [[101, "WALL_1_GUID"]]},
            via_cache=True,
            queda=None,
            n_faltantes=0,
        )

    monkeypatch.setattr(P, "gerar_planta", _fake_planta)
    monkeypatch.setattr(R, "refinar_pesados", lambda *a, **kw: (chamadas_refino.append((a, kw)), a[2])[1])

    dados = G._motor_padrao(
        "planta",
        ifc,
        "VISTA_GUID",
        {"caminho_ifc": arq},
        cancelar=threading.Event(),
        progresso=lambda _m: None,
        cache=C.CacheDesenho(tmp_path / "vista"),
        previa=previas.append,
    )
    assert dados["via_cache"] is True
    assert chamadas_refino == [], "refino.refinar_pesados nao pode rodar quando via_cache=True"
    assert previas == [], "previa de refino nao pode disparar quando via_cache=True"


def test_motor_padrao_chama_refino_quando_via_cache_false_com_pesados(monkeypatch, tmp_path):
    """Mutante 6 (controle positivo): em queda (via_cache=False) com pesados, refino.refinar_pesados continua rodando."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    _criar_banco_valido(C.pasta_geometria())
    arq = _arquivo_ifc(tmp_path)
    ifc = _FakeIfc()
    chamadas_refino = []

    def _fake_planta(f, gid, **kw):
        return P.Planta(
            svg=_SVG_OK,
            n_paths=1,
            selecao=_sel_fake(),
            tempos={"geo_s": 0.5, "motor_s": 0.02},
            unidade_escala=1.0,
            altura_corte=1.2,
            caixas=(),
            pesados=({"guid": "WALL_1_GUID", "id": 101, "faces": 99999},),
            pedido={"protocolo": 1, "op": "desenho", "elementos": [[101, "WALL_1_GUID"]]},
            via_cache=False,
            queda="cache_incompleto",
            n_faltantes=1,
        )

    def _fake_refino(f, ped, dados, **kw):
        chamadas_refino.append((ped, dict(dados), kw))
        return {**dados, "refinadas": ["WALL_1_GUID"]}

    monkeypatch.setattr(P, "gerar_planta", _fake_planta)
    monkeypatch.setattr(R, "refinar_pesados", _fake_refino)

    dados = G._motor_padrao(
        "planta",
        ifc,
        "VISTA_GUID",
        {"caminho_ifc": arq},
        cancelar=threading.Event(),
        progresso=lambda _m: None,
        cache=C.CacheDesenho(tmp_path / "vista"),
    )
    assert len(chamadas_refino) == 1
    assert dados["via_cache"] is False
    assert dados["queda"] == "cache_incompleto"
    assert dados["n_faltantes"] == 1
    assert dados["tempos"]["motor_s"] == pytest.approx(0.02)


# ================================================================== Mutante 7: construir_cache default False + ciclo True


@pytest.mark.parametrize("kw_gerente", [{}, {"construir_cache": False}])
def test_construir_cache_default_false_nao_inicia_construtor(monkeypatch, tmp_path, kw_gerente):
    """Mutante 7: default construir_cache=False (e explicito False) nunca inicia filho.construir em aquecer/salvar."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    arq = _arquivo_ifc(tmp_path)
    eventos: list[str] = []

    class _FilhoEspiao:
        def __init__(self, arquivo, **kw):
            self.arquivo = str(arquivo)
            self.construcao_ativa = False

        def aquecer(self, **kw):
            eventos.append("aquecer")
            return {"aberto": True}

        def construir(self, pasta_cache, **kw):
            eventos.append("construir")
            return {"aceito": True, "pendentes": 0}

        podar = salvar = invalidar = fechar = lambda self: None

    monkeypatch.setattr(G, "FilhoPersistente", _FilhoEspiao)
    g = GerenteDesenho(motor=lambda *a, **k: {}, **kw_gerente)
    try:
        g.aquecer(arq, revisao=1, revisao_salva=1)
        _esperar_fundo(g)
        g.salvar(arq, revisao=2, revisao_salva=2)
        _esperar_fundo(g)
        assert eventos == ["aquecer", "aquecer"]
    finally:
        g.fechar()


def test_construir_cache_true_constroi_em_fundo_e_planta_usa_cache(qt_app, monkeypatch, tmp_path):
    """Mutante 7: construir_cache=True inicia construtor em segundo plano e planta usa cache assim que pronto."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = C.pasta_geometria()
    arq = _arquivo_ifc(tmp_path)
    ifc = _stub_planta_env(monkeypatch)
    thread_principal = threading.current_thread()
    eventos: list[tuple[str, threading.Thread, str | None]] = []

    class _FilhoCiclo:
        def __init__(self, arquivo, **kw):
            self.arquivo = str(arquivo)
            self.construcao_ativa = False

        def aquecer(self, **kw):
            eventos.append(("aquecer", threading.current_thread(), None))
            return {"aberto": True}

        def construir(self, pasta_cache, **kw):
            eventos.append(("construir", threading.current_thread(), str(pasta_cache)))
            _criar_banco_valido(Path(pasta_cache))
            self.construcao_ativa = False
            return {"aceito": True, "pendentes": 0}

        def estado_construcao(self, *a, **kw):
            return {"ativo": False, "pendentes": 0, "feitos": 2, "parado": None, "erro": None}

        def executar(self, pedido, **kw):
            if pedido.get("op") == "estado_construcao":
                return self.estado_construcao()
            eventos.append(("desenho", threading.current_thread(), pedido.get("pasta_cache_geometria")))
            return _resp_aux(via_cache=True, queda=None, n_faltantes=0, motor_s=0.05)

        podar = salvar = invalidar = fechar = lambda self: None

    monkeypatch.setattr(G, "FilhoPersistente", _FilhoCiclo)
    g = GerenteDesenho(cache=C.CacheDesenho(tmp_path / "vista"), construir_cache=True, filho_persistente=True)
    try:
        g.aquecer(arq, revisao=1, revisao_salva=1)
        _esperar_fundo(g)
        assert [e[0] for e in eventos] == ["aquecer", "construir"]
        assert eventos[1][1] is not thread_principal
        assert eventos[1][2] == str(pasta_geo)
        assert (pasta_geo / NOME_BANCO).is_file()

        dados = _pedir_e_esperar(qt_app, g, "planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
        assert eventos[-1][0] == "desenho"
        assert eventos[-1][2] == str(pasta_geo)
        assert dados["via_cache"] is True
        assert dados["queda"] is None
        assert dados["n_faltantes"] == 0
        assert dados["tempos"]["motor_s"] == pytest.approx(0.05)
    finally:
        g.fechar()


# MUTANTES (ESPEC_T24bcde.md §3.3):
# 1: test_planta_envia_pasta_cache_*, test_planta_nao_envia_pasta_cache_*, test_planta_remove_pasta_cache_no_retry_*,
#    test_gerente_nao_envia_pasta_cache_*, test_motor_padrao_nao_envia_pasta_cache_em_corte
# 2: test_pedir_nao_consulta_estado_construcao_nem_sqlite_na_thread_chamadora
# 3: test_pavimento_completo_com_pendentes_positivos_usa_cache_stub, *_banco_real
# 4: test_cache_chave_ignora_pasta_cache_geometria_grafo_e_arquivo, test_gerar_planta_reaproveita_cache_vista_*
# 5: test_planta_propaga_telemetria_cache_e_queda, test_motor_padrao_e_sinal_pronto_propagam_telemetria
# 6: test_motor_padrao_nao_chama_refino_quando_via_cache_true, *_via_cache_false_com_pesados
# 7: test_contrato_assinaturas_e_defaults, test_construir_cache_default_false_*, test_construir_cache_true_*
