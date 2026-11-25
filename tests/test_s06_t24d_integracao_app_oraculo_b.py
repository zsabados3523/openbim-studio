# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24d_integracao_app_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24d_integracao_app_oraculo import _FakeIfc, _SVG_OK, _arquivo_ifc, _criar_banco_valido, _girar_qt, _pedir_e_esperar, _resp_aux, _sel_fake, _stub_planta_env, qt_app  # noqa: F401



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


def test_motor_padrao_envia_pasta_cache_em_corte(monkeypatch, tmp_path):
    """Mutante 1 (escopo): _motor_padrao envia pasta_cache_geometria em planta e em corte salvos (T27b)."""
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
    assert kw_corte[0].get("pasta_cache_geometria") == str(pasta_geo)


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
