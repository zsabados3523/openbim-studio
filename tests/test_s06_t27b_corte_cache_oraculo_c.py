# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T27b (parte 3/3): casos 15 a 23 e 25 (app, gerente, faixas, motor, tempo).

NAO editar este arquivo na implementacao. Auxiliares vem de `test_s06_t27b_corte_cache_oraculo`.
"""
from __future__ import annotations

import ast
import inspect
import sqlite3
import statistics
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import pytest

from obim_geometria import cache_geometria as CG
from obim_geometria import construtor, desenho, faixas, silhueta, visibilidade
from openbim_app.desenho import cache as CD
from openbim_app.desenho import corte as CO
from openbim_app.desenho import gerente as G
from openbim_app.desenho import planta as P
from test_s06_t27b_corte_cache_oraculo import (
    _add_caixa,
    _add_vista_corte_ifc,
    _assert_corte_equivalente,
    _cena_basica,
    _novo_ifc_base,
    _pedido_corte,
    _salvar_e_construir,
)


def _cena_com_vista_ifc(tmp_path: Path, nome: str = "app_corte.ifc"):
    """Cena sintetica com IfcAnnotation de CORTE gravada no IFC (para gerar_corte)."""
    f, body, pav = _novo_ifc_base()
    w1 = _add_caixa(f, body, pav, "IfcWall", "W1", (0.0, -0.2, 0.0), (4.0, 0.4, 2.8))
    w2 = _add_caixa(f, body, pav, "IfcWall", "W2", (0.0, 1.5, 0.0), (4.0, 0.3, 2.8))
    gid = _add_vista_corte_ifc(f, "C_APP", origem=(2.0, 0.0, 1.4), tamanho=(8.0, 6.0, 6.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome=nome)
    return SimpleNamespace(arq=arq, pasta=pasta, f=f2, gid=gid, w1=f2.by_guid(w1.GlobalId), w2=f2.by_guid(w2.GlobalId))


# ---------------------------------------------------------------- casos 15 a 20: app, gerente, chave, GIL


def test_caso15_gerar_corte_kwarg_validacao_e_sem_arquivo_salvo(tmp_path):
    """Caso 15 + 2.1: pasta_cache_geometria em gerar_corte, validacao de tipo e omissao sem arquivo salvo."""
    params = inspect.signature(CO.gerar_corte).parameters
    assert "pasta_cache_geometria" in params
    assert params["pasta_cache_geometria"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["pasta_cache_geometria"].default is None

    c = _cena_com_vista_ifc(tmp_path)
    chamadas: list[dict] = []

    def _exec(ped: dict) -> dict:
        chamadas.append(dict(ped))
        if ped.get("op") == "caixas_cache":
            return {"ok": True, "caixas_envolventes": {}}
        if ped.get("op") == "caixas":
            return {"ok": True, "caixas_envolventes": {c.w1.id(): [0, -0.2, 0, 4, 0.2, 2.8]}, "falhas_geometria": []}
        return {"ok": True, "svg": "<svg/>", "n_paths": 0, "tempos": {"geo_s": 0.0}, "caixas": []}

    for invalido in (123, True, ["/tmp/geo"]):
        chamadas.clear()
        with pytest.raises((TypeError, ValueError)):
            CO.gerar_corte(c.f, c.gid, caminho_ifc=c.arq, pasta_cache_geometria=invalido, executor=_exec)
        assert chamadas == []

    chamadas.clear()
    CO.gerar_corte(c.f, c.gid, caminho_ifc=None, pasta_cache_geometria=c.pasta, motor_visivel=True, executor=_exec)
    des = [q for q in chamadas if q.get("op") == "desenho"]
    assert len(des) == 1 and "pasta_cache_geometria" not in des[0]

    for val, esp in ((c.pasta, str(c.pasta)), (str(c.pasta), str(c.pasta)), ("", None), (None, None)):
        chamadas.clear()
        CO.gerar_corte(c.f, c.gid, caminho_ifc=c.arq, pasta_cache_geometria=val, motor_visivel=True, executor=_exec)
        des = [q for q in chamadas if q.get("op") == "desenho"]
        assert len(des) == 1 and des[0].get("pasta_cache_geometria") == esp


def test_caso16_divergencia_assinatura_retry_sem_pasta(tmp_path, monkeypatch):
    """Caso 16: apos auxiliar.Divergente, retry sem arquivo nao leva pasta e nao le banco."""
    c = _cena_com_vista_ifc(tmp_path, nome="div_corte.ifc")
    des_pedidos: list[dict] = []
    aberturas_db: list[tuple] = []
    orig_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: (aberturas_db.append(a), orig_connect(*a, **k))[1])

    def _exec(ped: dict) -> dict:
        if ped.get("op") == "caixas_cache":
            return {"ok": True, "caixas_envolventes": {}}
        if ped.get("op") == "caixas":
            return {"ok": True, "caixas_envolventes": {c.w1.id(): [0, -0.2, 0, 4, 0.2, 2.8]}, "falhas_geometria": []}
        des_pedidos.append(dict(ped))
        if len(des_pedidos) == 1:
            return {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "mudou", "rastro": ""}}
        return desenho.processar(ped)

    r = CO.gerar_corte(c.f, c.gid, caminho_ifc=c.arq, pasta_cache_geometria=c.pasta, motor_visivel=True, executor=_exec)
    assert r.n_paths > 0
    assert len(des_pedidos) == 2
    assert des_pedidos[0].get("pasta_cache_geometria") == str(c.pasta)
    assert "pasta_cache_geometria" not in des_pedidos[1]
    assert aberturas_db == []


def test_caso17a_chave_cache_desenho_ignora_pasta_geometria_corte(tmp_path):
    """Caso 17 (unitario): CacheDesenho.chave e identica com e sem pasta_cache_geometria em CORTE."""
    c = _cena_com_vista_ifc(tmp_path, nome="chave_corte.ifc")
    _, sig = CD.resolver_assinatura(c.arq)
    base = _pedido_corte(c.arq, [c.w1, c.w2])
    com = {**base, "pasta_cache_geometria": str(c.pasta)}
    cd = CD.CacheDesenho(tmp_path / "vista")
    assert cd.chave(c.f, base) == cd.chave(c.f, com)
    assert cd.chave(c.f, base, arquivo=c.arq, assinatura=sig) == cd.chave(c.f, com, arquivo=c.arq, assinatura=sig)


def test_caso17b_gerar_corte_hit_cache_desenho_com_e_sem_pasta(tmp_path):
    """Caso 17 (integrado): segundo gerar_corte com pasta_cache_geometria acerta o CacheDesenho."""
    c = _cena_com_vista_ifc(tmp_path, nome="hit_corte.ifc")
    cd = CD.CacheDesenho(tmp_path / "vista")
    n_des = []

    def _exec(ped: dict) -> dict:
        if ped.get("op") == "caixas_cache":  # T27c: cache sem caixas, a selecao cai na op "caixas"
            return {"ok": True, "caixas_envolventes": {}}
        if ped.get("op") == "caixas":
            return {"ok": True, "caixas_envolventes": {c.w1.id(): [0, -0.2, 0, 4, 0.2, 2.8]}, "falhas_geometria": []}
        n_des.append(dict(ped))
        return {
            "ok": True,
            "svg": '<svg xmlns="http://www.w3.org/2000/svg"><path d="M 0,0 L 1,0"/></svg>',
            "n_paths": 1,
            "tempos": {"geo_s": 0.0},
            "caixas": [],
        }

    r1 = CO.gerar_corte(c.f, c.gid, caminho_ifc=c.arq, cache=cd, pasta_cache_geometria=None, motor_visivel=True, executor=_exec)
    r2 = CO.gerar_corte(c.f, c.gid, caminho_ifc=c.arq, cache=cd, pasta_cache_geometria=c.pasta, motor_visivel=True, executor=_exec)
    assert len(n_des) == 1 and r1.svg == r2.svg


def test_caso18_gerente_motor_padrao_corte_e_planta(tmp_path, monkeypatch):
    """Caso 18: _motor_padrao repassa pasta_cache_geometria em corte e planta salvos e remove sem arquivo."""
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    pasta_geo = CD.pasta_geometria()
    with CG.abrir_cache(pasta_geo, CG.cabecalho_atual(tesselacao=construtor.TESSELACAO)):
        pass
    arq = tmp_path / "doc.ifc"
    arq.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    kw_corte: list[dict] = []
    kw_planta: list[dict] = []
    fake_res = SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=(), pesados=(), via_cache=False)
    monkeypatch.setattr(CO, "gerar_corte", lambda f, g, **k: (kw_corte.append(dict(k)), fake_res)[1])
    monkeypatch.setattr(P, "gerar_planta", lambda f, g, **k: (kw_planta.append(dict(k)), fake_res)[1])
    cd = CD.CacheDesenho(tmp_path / "vista")

    G._motor_padrao("corte", object(), "G1", {"caminho_ifc": arq}, cancelar=threading.Event(), progresso=lambda _: None, cache=cd)
    G._motor_padrao("planta", object(), "G2", {"caminho_ifc": arq}, cancelar=threading.Event(), progresso=lambda _: None, cache=cd)
    assert kw_corte[-1].get("pasta_cache_geometria") == str(pasta_geo)
    assert kw_planta[-1].get("pasta_cache_geometria") == str(pasta_geo)

    G._motor_padrao("corte", object(), "G1", {"pasta_cache_geometria": str(pasta_geo)}, cancelar=threading.Event(), progresso=lambda _: None, cache=cd)
    G._motor_padrao("planta", object(), "G2", {"pasta_cache_geometria": str(pasta_geo)}, cancelar=threading.Event(), progresso=lambda _: None, cache=cd)
    assert "pasta_cache_geometria" not in kw_corte[-1]
    assert "pasta_cache_geometria" not in kw_planta[-1]


def test_caso19_nao_reabre_ifc(tmp_path, monkeypatch):
    """Caso 19: exatamente 1 abertura por pedido; 0 aberturas com _abrir_ifc mantido do filho persistente."""
    cena = _cena_basica(tmp_path)
    aberturas: list[str] = []
    real_open = ifcopenshell.open
    monkeypatch.setattr(ifcopenshell, "open", lambda p, *a, **k: (aberturas.append(str(p)), real_open(p, *a, **k))[1])

    r1 = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    assert r1["ok"] is True and r1["n_pecas_cache"] == len(cena.lista)
    assert len(aberturas) == 1

    aberturas.clear()
    f_mantido = real_open(str(cena.arq))
    monkeypatch.setattr(desenho, "_abrir_ifc", lambda caminho, pavimento=None: f_mantido)
    r2 = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    assert r2["ok"] is True and r2["n_pecas_cache"] == len(cena.lista)
    assert aberturas == []


def test_caso20a_sem_imports_banco_em_corte_e_gerente_ast():
    """Caso 20 (AST): corte.py e gerente.py nao importam sqlite3, cache_geometria nem cache_leitura."""
    proibidos = {"sqlite3", "cache_geometria", "cache_leitura"}
    raiz = Path(__file__).resolve().parent.parent / "app" / "openbim_app" / "desenho"
    for arq in (raiz / "corte.py", raiz / "gerente.py"):
        arvore = ast.parse(arq.read_text(encoding="utf-8"), filename=str(arq))
        achados = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for al in no.names:
                    achados |= set(al.name.split(".")) & proibidos
            elif isinstance(no, ast.ImportFrom):
                if no.module:
                    achados |= set(no.module.split(".")) & proibidos
                for al in no.names:
                    achados |= set(al.name.split(".")) & proibidos
        assert not achados, f"{arq.name} importou modulos proibidos no pai: {sorted(achados)}"


def test_caso20b_sem_sqlite_no_processo_pai(tmp_path, monkeypatch):
    """Caso 20 (runtime): com sqlite3.connect bloqueado no pai, gerar_corte ainda funciona."""
    c = _cena_com_vista_ifc(tmp_path, nome="sem_gil.ifc")
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sqlite3 no pai")))

    def _exec(ped: dict) -> dict:
        if ped.get("op") == "caixas_cache":
            return {"ok": True, "caixas_envolventes": {}}
        if ped.get("op") == "caixas":
            return {"ok": True, "caixas_envolventes": {c.w1.id(): [0, -0.2, 0, 4, 0.2, 2.8]}, "falhas_geometria": []}
        return {"ok": True, "svg": "<svg/>", "n_paths": 0, "tempos": {"geo_s": 0.0}, "caixas": []}

    r = CO.gerar_corte(c.f, c.gid, caminho_ifc=c.arq, pasta_cache_geometria=c.pasta, motor_visivel=True, executor=_exec)
    assert r.svg == "<svg/>"


# ---------------------------------------------------------------- casos 21, 22, 23 e 25


def test_caso21_telemetria_aditiva(tmp_path):
    """Caso 21: chaves antigas e seus tipos preservados; novas chaves aditivas presentes."""
    cena = _cena_basica(tmp_path)
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista))
    novo = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    for k, v in antigo.items():
        assert k in novo and type(novo[k]) is type(v)
    for k, v in antigo["tempos"].items():
        assert k in novo["tempos"] and type(novo["tempos"][k]) is type(v)
    assert type(novo["n_pecas_cache"]) is int and novo["n_pecas_cache"] == len(cena.lista)
    assert type(novo["n_pecas_fallback"]) is int and novo["n_pecas_fallback"] == 0
    assert novo["queda_corte"] is None
    assert isinstance(novo["tempos"]["cache_s"], float) and novo["tempos"]["cache_s"] >= 0.0


def test_caso22_faixas_de_corte_com_pasta(tmp_path, monkeypatch):
    """Caso 22: faixas>1 e faixa isolada com pasta_cache_geometria continuam equivalentes ao antigo."""
    f, body, pav = _novo_ifc_base()
    pecas = [_add_caixa(f, body, pav, "IfcWall", f"F{i}", (i * 2.0, -0.2, 0.0), (1.0, 0.4, 2.5)) for i in range(6)]
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="faixas.ifc")
    els = [f2.by_guid(p.GlobalId) for p in pecas]
    caixas = {e.id(): [i * 2.0, -0.2, 0.0, i * 2.0 + 1.0, 0.2, 2.5] for i, e in enumerate(els)}
    monkeypatch.setattr(faixas, "rodar_filho", lambda q: desenho.processar(dict(q)))

    kw = {"origem": (5.5, 0.0, 1.25), "largura": 14.0, "altura": 6.0, "caixas_coords": caixas}
    ant_f2 = desenho.processar(_pedido_corte(arq, els, extra={"faixas": 2}, **kw))
    nov_f2 = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, extra={"faixas": 2}, **kw))
    _assert_corte_equivalente(ant_f2, nov_f2)

    faixa_u = {"u0": None, "u1": 0.0, "donos": [e.id() for e in els[:3]]}
    ant_fx = desenho.processar(_pedido_corte(arq, els, extra={"faixa": faixa_u}, **kw))
    nov_fx = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, extra={"faixa": faixa_u}, **kw))
    _assert_corte_equivalente(ant_fx, nov_fx)
    assert nov_fx["n_pecas_cache"] == len(els) and nov_fx["n_pecas_fallback"] == 0


def test_caso23_excecao_no_motor_cai_nativo_sem_inventar_cache(tmp_path, monkeypatch):
    """Caso 23: excecao em visibilidade.linhas_visiveis_vista -> tudo ao nativo, n_pecas_cache == 0."""
    cena = _cena_basica(tmp_path)
    monkeypatch.setattr(
        visibilidade, "linhas_visiveis_vista", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista))
    novo = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    assert antigo["ok"] is True and novo["ok"] is True
    assert novo["motor_pecas"] == [] and novo["svg"] == antigo["svg"]
    assert sorted(novo["enviados"]) == sorted(antigo["enviados"])
    assert novo["n_pecas_cache"] == 0


def test_caso25a_estrutural_nao_chama_formas_do_mundo_com_cache_completo(tmp_path, monkeypatch):
    """Caso 25 (estrutural): com todas as pecas no cache, silhueta.formas_do_mundo nao e chamada."""
    cena = _cena_basica(tmp_path)
    chamadas: list[list[int]] = []
    real_formas = silhueta.formas_do_mundo
    monkeypatch.setattr(
        silhueta,
        "formas_do_mundo",
        lambda f_, es, **k: (chamadas.append([e.id() for e in es]), real_formas(f_, es, **k))[1],
    )
    r = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    assert r["ok"] is True
    assert r["n_pecas_cache"] == len(r["motor_pecas"]) == len(cena.lista)
    assert r["n_pecas_fallback"] == 0
    assert chamadas == []


def test_caso25b_tempo_relativo_400_caixas_sem_absoluto(tmp_path):
    """Caso 25 (tempo relativo): 400 caixas, mediana de 5 rodadas (aquecimento descartado), novo <= 1.5x antigo."""
    f, body, pav = _novo_ifc_base()
    pecas = [
        _add_caixa(
            f,
            body,
            pav,
            "IfcColumn",
            f"C_{ix}_{iy}",
            (ix * 1.0, iy * 1.0 - 0.1, 0.0),
            (0.25 + 0.01 * (ix % 5), 0.25 + 0.01 * (iy % 5), 2.0),
        )
        for ix in range(20)
        for iy in range(20)
    ]
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="grande400.ifc")
    els = [f2.by_guid(p.GlobalId) for p in pecas]
    kw = {"origem": (10.0, 0.0, 1.0), "largura": 24.0, "altura": 4.0, "profundidade_corte": 25.0}
    ped_ant = _pedido_corte(arq, els, **kw)
    ped_nov = _pedido_corte(arq, els, pasta_cache=pasta, **kw)

    def _medir() -> tuple[float, float]:
        desenho.processar(ped_ant)
        r_nov = desenho.processar(ped_nov)
        assert r_nov["ok"] is True and r_nov["n_pecas_cache"] == len(r_nov["motor_pecas"]) == 400
        assert r_nov["n_pecas_fallback"] == 0
        t_ant, t_nov = [], []
        for _ in range(5):
            t0 = time.perf_counter()
            desenho.processar(ped_ant)
            t_ant.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            desenho.processar(ped_nov)
            t_nov.append(time.perf_counter() - t0)
        return statistics.median(t_ant), statistics.median(t_nov)

    med_ant, med_nov = _medir()
    if med_nov > 1.5 * med_ant:
        med_ant, med_nov = _medir()
    assert med_nov <= 1.5 * med_ant, f"mediana novo ({med_nov:.4f}s) > 1.5x antigo ({med_ant:.4f}s)"
