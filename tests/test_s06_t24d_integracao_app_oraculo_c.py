# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24d_integracao_app_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24d_integracao_app_oraculo import NOME_BANCO, _FakeIfc, _SVG_OK, _arquivo_ifc, _criar_banco_valido, _esperar_fundo, _pedir_e_esperar, _resp_aux, _sel_fake, _stub_planta_env, qt_app  # noqa: F401



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
    "via_cache,queda,n_faltantes,secoes_parciais,motor_s",
    [
        (True, None, 0, 2, 0.123),
        (False, "cache_incompleto", 3, 0, 0.045),
    ],
)
def test_planta_propaga_telemetria_cache_e_queda(monkeypatch, tmp_path, via_cache, queda, n_faltantes, secoes_parciais, motor_s):
    """Mutante 5 (Planta): gerar_planta propaga via_cache, queda, n_faltantes, secoes_parciais e tempos['motor_s'] sem colidir com T19i1."""
    ifc = _stub_planta_env(monkeypatch)
    arq = _arquivo_ifc(tmp_path)

    pl = P.gerar_planta(
        ifc,
        "VISTA_GUID",
        caminho_ifc=arq,
        pasta_cache_geometria=tmp_path / "geo",
        executor=lambda _q: _resp_aux(via_cache=via_cache, queda=queda, n_faltantes=n_faltantes, secoes_parciais=secoes_parciais, motor_s=motor_s, cache_s=0.03),
    )
    assert pl.via_cache is via_cache
    assert pl.queda == queda
    assert pl.n_faltantes == n_faltantes
    assert type(pl.secoes_parciais) is int and pl.secoes_parciais == secoes_parciais
    assert pl.tempos["motor_s"] == pytest.approx(motor_s)
    assert pl.tempos["cache_s"] == pytest.approx(0.03)
    assert pl.faltantes == () and pl.incompleta is False


@pytest.mark.parametrize(
    "via_cache,queda,n_faltantes,secoes_parciais,motor_s",
    [
        (True, None, 0, 1, 0.11),
        (False, "secao_aberta", 0, 0, 0.08),
        (False, "cache_incompleto", 4, 0, 0.0),
    ],
)
def test_motor_padrao_e_sinal_pronto_propagam_telemetria(qt_app, monkeypatch, tmp_path, via_cache, queda, n_faltantes, secoes_parciais, motor_s):
    """Mutante 5 (gerente): _motor_padrao e sinal pronto carregam via_cache, queda, n_faltantes, secoes_parciais e tempos['motor_s']."""
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
            secoes_parciais=secoes_parciais,
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
    assert type(dados_dir["secoes_parciais"]) is int and dados_dir["secoes_parciais"] == secoes_parciais
    assert dados_dir["tempos"]["motor_s"] == pytest.approx(motor_s)

    # (b) sinal pronto do GerenteDesenho
    g = GerenteDesenho(cache=cache_v, filho_persistente=False)
    try:
        dados_sig = _pedir_e_esperar(qt_app, g, "planta", ifc, "VISTA_GUID", caminho_ifc=arq, revisao=1, revisao_salva=1)
        assert dados_sig["via_cache"] is via_cache
        assert dados_sig["queda"] == queda
        assert dados_sig["n_faltantes"] == n_faltantes
        assert type(dados_sig["secoes_parciais"]) is int and dados_sig["secoes_parciais"] == secoes_parciais
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
