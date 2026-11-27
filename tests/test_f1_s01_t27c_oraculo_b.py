# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-T27c (parte B): validacao, IFC2X3, banda 2 lados, sessao e mutantes.

NAO editar este arquivo na implementacao. Auxiliares compartilhados em `t27c_aux.py`.
"""
from __future__ import annotations

import json, math, multiprocessing, os, threading, time
from pathlib import Path

import ifcopenshell, ifcopenshell.api, ifcopenshell.guid, ifcopenshell.util.placement, ifcopenshell.util.unit
import numpy as np, pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from obim_geometria import cache_geometria as CG, caixas as geo_caixas, construtor, local, persistente
from openbim_app.desenho import auxiliar, corte as CO, filho as DF, selecao as SL
from openbim_app.desenho.gerente import GerenteDesenho
from openbim_app.desenho.selecao import SessaoSelecao
from t27c_aux import (
    RAIZ, _STUB_DESENHO, _add_caixa, _add_vista_corte, _assert_sel_eq, _cena_solda,
    _cena_variada, _espiar_caixas, _novo_ifc_base, _rodar_selecao, _salvar_e_construir,
)

@pytest.mark.parametrize(
    "caixa_ruim",
    [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0, float("nan"), 1.0, 1.0], [5.0, 0.0, 0.0, 1.0, 1.0, 1.0], [1.0, 5.0, 0.0, 2.0, 1.0, 2.0], [1.0, 1.0, 5.0, 2.0, 2.0, 1.0]],
    ids=["curta", "nan", "min_maior_max_x", "min_maior_max_y", "min_maior_max_z"],
)
def test_17_validacao_caixa_malformada_cai_em_op_caixas(tmp_path, caixa_ruim):
    cena = _cena_variada(tmp_path)
    p1 = cena.f.by_guid(cena.gids["P1"])
    gid, alvo_id = cena.vistas["y_largo"], p1.id()
    mat_p1 = np.asarray(ifcopenshell.util.placement.get_local_placement(p1.ObjectPlacement), dtype=np.float64).ravel().tolist()
    ref, pedidos = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0], []
    def _exec(ped: dict) -> dict:
        pedidos.append(dict(ped))
        if ped.get("op") == "caixas_cache":
            return {"ok": True, "caixas_envolventes": {str(alvo_id): caixa_ruim}, "matrizes": {str(alvo_id): mat_p1}}
        return dict(_STUB_DESENHO) if ped.get("op") == "desenho" else local.executar(ped)
    nov = CO.gerar_corte(cena.f, gid, caminho_ifc=cena.arq, pasta_cache_geometria=cena.pasta, ocultar_secundarias=False, executor=_exec).selecao
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    _assert_sel_eq(nov, ref); assert alvo_id in nov.ids and alvo_id in ids_op

def test_18_permission_error_pasta_cache_cai_em_op_caixas(tmp_path, monkeypatch):
    cena = _cena_variada(tmp_path)
    gid = cena.vistas["y_largo"]
    ref, real_is_file = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0], Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda self: (_ for _ in ()).throw(PermissionError("sem permissao")) if self.name == CG.NOME_BANCO else real_is_file(self))
    nov, pedidos = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=cena.pasta)
    _assert_sel_eq(nov, ref); assert any(p.get("op") == "caixas" for p in pedidos)

def test_19_mutante_m1_despacho_real_processo_e_persistente(tmp_path):
    cena = _cena_variada(tmp_path)
    gid = cena.vistas["y_largo"]
    ref = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0]
    _assert_sel_eq(SL.selecionar(cena.f, gid, caminho_ifc=cena.arq, pasta_cache_geometria=cena.pasta), ref)
    fp = DF.FilhoPersistente(cena.arq)
    try:
        _assert_sel_eq(SL.selecionar(cena.f, gid, caminho_ifc=cena.arq, pasta_cache_geometria=cena.pasta, filho=fp), ref)
    finally:
        fp.fechar()

def test_20_mutantes_m2_m3_m4_assinatura_erros_e_sem_sig(tmp_path):
    cena = _cena_variada(tmp_path)
    gid, alvo_gid = cena.vistas["y_largo"], cena.gids["P1"]
    alvo_id = cena.f.by_guid(alvo_gid).id()
    r_div = geo_caixas.processar_cache({"op": "caixas_cache", "arquivo": str(cena.arq), "assinatura": [1, 1], "pasta_cache_geometria": str(cena.pasta), "elementos": [[alvo_id, alvo_gid]]})
    assert r_div.get("ok") is False and r_div.get("erro", {}).get("tipo") == "Divergente"
    with pytest.raises(auxiliar.Divergente):
        SL.selecionar(cena.f, gid, caminho_ifc=cena.arq, assinatura_ifc=(1, 1), pasta_cache_geometria=cena.pasta, executor=local.executar)
    sessao = SessaoSelecao()
    sessao._erros[alvo_id] = ["RuntimeError: erro velho"]
    nov, _ = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=cena.pasta, sessao=sessao)
    assert alvo_id in nov.ids and nov.erros_geometria == () and alvo_id not in sessao._erros
    pedidos: list[dict] = []
    CO._gerar_corte_uma_vez(cena.f, gid, (), 1.0, None, None, 30.0, None, lambda p: (pedidos.append(dict(p)), dict(_STUB_DESENHO) if p.get("op") == "desenho" else local.executar(p))[1], cena.arq, None, False, None, 1, None, None, None, None, str(cena.pasta))
    assert all(p.get("op") != "caixas_cache" and "pasta_cache_geometria" not in p for p in pedidos)

@pytest.mark.parametrize("caixa_arr", [np.array([[0.0, 0.0, 0.0], [np.nan, np.inf, 2.0]]), np.array([[5.0, 0.0, 0.0], [1.0, 1.0, 2.0]])], ids=["nan_inf", "min_maior_max"])
def test_21_ocorrencia_invalida_checksum_valido_cai_em_op_caixas(tmp_path, monkeypatch, caixa_arr):
    cena = _cena_variada(tmp_path)
    gid, alvo_gid = cena.vistas["y_largo"], cena.gids["P1"]
    alvo_id, ref, doc = cena.f.by_guid(alvo_gid).id(), _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0], construtor.documento_de(cena.arq)
    with CG.abrir_cache(cena.pasta, CG.cabecalho_atual(tesselacao=construtor.TESSELACAO)) as db:
        oc = db.ler_ocorrencia(alvo_gid, documento=doc)
        assert oc is not None
        db.gravar_lote({}, [CG.Ocorrencia(alvo_gid, oc.chave_forma, oc.matriz, caixa_arr, oc.pavimento, oc.classe_ifc)], documento=doc)
    chamadas_proc = _espiar_caixas(monkeypatch)
    nov, _ = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=cena.pasta)
    _assert_sel_eq(nov, ref); assert alvo_id in nov.ids and chamadas_proc == [{alvo_id}]

# ---------------------------------------------------------------- (6) IFC2X3, banda 2 lados e M1-R2..M4-R2

def _novo_ifc2x3_base():
    api, f = ifcopenshell.api.run, ifcopenshell.file(schema="IFC2X3")
    pes, org = f.create_entity("IfcPerson", Id="u", FamilyName="Teste"), f.create_entity("IfcOrganization", Name="Org")
    app = f.create_entity("IfcApplication", ApplicationDeveloper=org, Version="1", ApplicationFullName="Teste", ApplicationIdentifier="t")
    oh = f.create_entity("IfcOwnerHistory", OwningUser=f.create_entity("IfcPersonAndOrganization", ThePerson=pes, TheOrganization=org), OwningApplication=app, ChangeAction="ADDED", CreationDate=0)
    proj = f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="P_2X3")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site, bld, pav = (api("root.create_entity", f, ifc_class=c, name=n) for c, n in (("IfcSite", "S"), ("IfcBuilding", "B"), ("IfcBuildingStorey", "Terreo")))
    pav.Elevation = 0.0
    for filho, pai in ((site, proj), (bld, site), (pav, bld)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)
    return f, body, pav

def test_22_ifc2x3_sintetico_com_cache(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc2x3_base()
    w1, w2 = _add_caixa(f, body, pav, "IfcWall", "W1", (0.5, 0.5, 0.0), (1.0, 0.25, 2.0)), _add_caixa(f, body, pav, "IfcWall", "W2", (2.0, 0.5, 0.0), (1.0, 0.25, 2.0))
    _add_caixa(f, body, pav, "IfcWall", "W_LONGE", (12.0, 12.0, 0.0), (1.0, 0.25, 2.0))
    gid_v = _add_vista_corte(f, "C2X3", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="sintetico_2x3.ifc")
    assert f2.schema == "IFC2X3"
    ref = SL.selecionar(f2, gid_v, caminho_ifc=arq, pasta_cache_geometria=None, executor=local.executar)
    assert ref.ids == tuple(sorted((f2.by_guid(w1.GlobalId).id(), f2.by_guid(w2.GlobalId).id())))
    chamadas_proc = _espiar_caixas(monkeypatch)
    nov_sel = SL.selecionar(f2, gid_v, caminho_ifc=arq, pasta_cache_geometria=pasta, executor=local.executar)
    nov_corte, pedidos = _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)
    _assert_sel_eq(nov_sel, ref); _assert_sel_eq(nov_corte, ref)
    assert [p for p in pedidos if p.get("op") == "caixas"] == [] and chamadas_proc == []

def test_23_ifc2x3_corpus_com_cache(tmp_path):
    arq_corpus = RAIZ / "corpus" / "bs-ifc2x3-building-architecture.ifc"
    if not arq_corpus.is_file():
        pytest.skip("corpus/bs-ifc2x3-building-architecture.ifc ausente neste checkout")
    f = ifcopenshell.open(str(arq_corpus))
    assert f.schema == "IFC2X3"
    scale = float(ifcopenshell.util.unit.calculate_unit_scale(f))
    pts = [ifcopenshell.util.placement.get_local_placement(e.ObjectPlacement)[:3, 3] for e in f.by_type("IfcElement") if getattr(e, "ObjectPlacement", None) is not None]
    ox, oy, oz = (tuple(float(v) for v in np.mean(pts, axis=0)) if pts else (0.0, 0.0, 0.0))
    gid_v = _add_vista_corte(f, "C2X3_CORP", (ox, oy - 25.0 / scale, oz), (50.0 / scale, 50.0 / scale, 50.0 / scale))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="corpus_2x3.ifc")
    ref = SL.selecionar(f2, gid_v, caminho_ifc=arq, pasta_cache_geometria=None, executor=local.executar)
    assert len(ref.ids) > 0
    _assert_sel_eq(SL.selecionar(f2, gid_v, caminho_ifc=arq, pasta_cache_geometria=pasta, executor=local.executar), ref)
    _assert_sel_eq(_rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)[0], ref)

def test_24_banda_borda_dois_lados_1e5_e_folga_no_cache(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc_base()
    espec_folga_in = (("dentro", (1.0, 0.5, 0.5), (1.0, 1.0, 1.5)), ("dentro_5mm", (3.995, 0.5, 0.5), (1.0, 1.0, 1.5)))
    espec_borda_in = (("tang_xmin", (-1.0, 0.5, 0.5), (1.0, 1.0, 1.5)), ("tang_ymax", (1.0, 2.0, 0.5), (1.0, 1.0, 1.5)), ("tang_zmax", (1.0, 0.5, 3.0), (1.0, 1.0, 1.0)), ("anel_in_5e6", (3.999995, 0.5, 0.5), (1.0, 1.0, 1.5)))
    g_folga_in = {n: _add_caixa(f, body, pav, "IfcWall", n, pos, dim).GlobalId for n, pos, dim in espec_folga_in}
    g_borda_in = {n: _add_caixa(f, body, pav, "IfcWall", n, pos, dim).GlobalId for n, pos, dim in espec_borda_in}
    g_anel_out = _add_caixa(f, body, pav, "IfcWall", "anel_out_5e6", (4.000005, 0.5, 0.5), (1.0, 1.0, 1.5)).GlobalId
    g_fora = _add_caixa(f, body, pav, "IfcWall", "fora_longe", (4.005, 0.5, 0.5), (1.0, 1.0, 1.5)).GlobalId
    gid_v = _add_vista_corte(f, "CTANG", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0), angulo_graus=0.0)
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="tang_anel.ifc")
    ref, chamadas_proc = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _espiar_caixas(monkeypatch)
    nov, pedidos = _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)
    ids_folga_in, ids_borda_in = {f2.by_guid(g).id() for g in g_folga_in.values()}, {f2.by_guid(g).id() for g in g_borda_in.values()}
    id_anel_out, id_fora = f2.by_guid(g_anel_out).id(), f2.by_guid(g_fora).id()
    ids_esp, ids_folga = ids_borda_in | {id_anel_out}, ids_folga_in | {id_fora}
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    assert ref.faixa == ((0.0, 0.0, 0.0), (4.0, 2.0, 3.0)) and nov.ids == tuple(sorted(ids_folga_in | ids_borda_in))
    _assert_sel_eq(nov, ref)
    assert id_anel_out not in nov.ids and id_fora not in nov.ids
    assert ids_op == ids_esp and ids_op.isdisjoint(ids_folga) and chamadas_proc == [ids_esp]

@pytest.mark.parametrize("extra_resp", [{}, {"matrizes": None}], ids=["sem_matrizes", "matrizes_none"])
def test_25_caixas_cache_sem_matrizes_ou_none_rejeita_caixa_valida(tmp_path, extra_resp):
    cena = _cena_variada(tmp_path)
    gid, alvo_id = cena.vistas["y_largo"], cena.f.by_guid(cena.gids["P1"]).id()
    ref, pedidos = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0], []
    def _exec(ped: dict) -> dict:
        pedidos.append(dict(ped))
        if ped.get("op") == "caixas_cache":
            return {"ok": True, "caixas_envolventes": {str(alvo_id): [50.0, 50.0, 0.0, 51.0, 51.0, 2.0]}, **extra_resp}
        return dict(_STUB_DESENHO) if ped.get("op") == "desenho" else local.executar(ped)
    nov = CO.gerar_corte(cena.f, gid, caminho_ifc=cena.arq, pasta_cache_geometria=cena.pasta, ocultar_secundarias=False, executor=_exec).selecao
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    assert alvo_id in ids_op and alvo_id in nov.ids; _assert_sel_eq(nov, ref)

def test_26_mutante_m1_r2_project_metros_library_milimetros_desliga_cache(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc_base()
    mm = f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    f.create_entity("IfcProjectLibrary", GlobalId=ifcopenshell.guid.new(), Name="LibMM", UnitsInContext=f.create_entity("IfcUnitAssignment", Units=[mm]))
    _add_caixa(f, body, pav, "IfcWall", "W_M", (1.0, 0.5, 0.0), (1.0, 0.25, 2.0))
    gid_v = _add_vista_corte(f, "C_LIB_MM", (1.5, 0.0, 1.0), (2.0, 3.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="proj_m_lib_mm.ifc")
    assert float(ifcopenshell.util.unit.calculate_unit_scale(f2)) == pytest.approx(1.0, abs=1e-12)
    ref, chamadas_proc = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _espiar_caixas(monkeypatch)
    nov, pedidos = _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)
    _assert_sel_eq(nov, ref)
    assert len(ref.ids) == 1 and all(p.get("op") != "caixas_cache" for p in pedidos) and any(p.get("op") == "caixas" for p in pedidos) and len(chamadas_proc) == 1

def test_27_mutante_m2_r2_caixas_cache_invalida_construcao_ativa(tmp_path):
    c1, c2 = _cena_variada(tmp_path / "c1"), _cena_variada(tmp_path / "c2")
    arq1, arq2 = c1.arq.resolve(), c2.arq.resolve()
    fp = DF.FilhoPersistente(arq1)
    try:
        assert fp.construir(tmp_path / "cache_bg1").get("aceito") is True
        pid_antes, ops_sel, real_exec = fp.pid, [], fp.executar
        assert pid_antes is not None and real_exec({"op": "estado_construcao", "arquivo": str(arq1)})["ativo"] is True
        fp.executar = lambda ped, **kw: (ops_sel.append(ped.get("op")), real_exec(ped, **kw))[1]
        sel = SL.selecionar(c2.f, c2.vistas["vazio"], caminho_ifc=arq2, pasta_cache_geometria=c2.pasta, filho=fp)
        fp.executar = real_exec
        assert sel.ids == () and ops_sel == ["caixas_cache"] and fp.pid == pid_antes
        assert real_exec({"op": "estado_construcao", "arquivo": str(arq1)})["ativo"] is False
    finally:
        fp.fechar()
    (r1, w1), (r2, w2), seq = multiprocessing.Pipe(False), multiprocessing.Pipe(False), 0
    th = threading.Thread(target=persistente.servir, args=(w2, r1), daemon=True); th.start()
    def _pedir(ped: dict) -> dict:
        nonlocal seq; seq += 1
        w1.send_bytes(json.dumps({**ped, "numero": seq, "protocolo": 1}).encode("utf-8"))
        while True:
            assert r2.poll(30.0)
            msg = json.loads(r2.recv_bytes())
            if msg.get("tipo") == "resposta" and msg.get("numero") == seq:
                return msg["dados"]
    try:
        assert r2.poll(30.0) and json.loads(r2.recv_bytes()).get("tipo") == "pronto"
        assert _pedir({"op": "construir", "arquivo": str(arq1), "pasta_cache": str(tmp_path / "cache_bg2")}).get("aceito") is True
        assert _pedir({"op": "estado_construcao", "arquivo": str(arq1)})["ativo"] is True
        arq1.write_bytes(arq1.read_bytes() + b"\n")
        st, p1 = os.stat(arq1), c1.f.by_guid(c1.gids["P1"])
        assert _pedir({"op": "caixas_cache", "arquivo": str(arq1), "assinatura": [int(st.st_size), int(st.st_mtime_ns)], "pasta_cache_geometria": str(c1.pasta), "elementos": [[p1.id(), p1.GlobalId]]}).get("ok") is True
        assert _pedir({"op": "estado_construcao", "arquivo": str(arq1)})["ativo"] is False
    finally:
        w1.send_bytes(json.dumps({"op": "encerrar"}).encode("utf-8")); th.join(timeout=10.0)
        for ch in (r1, w1, r2, w2): ch.close()

@pytest.mark.parametrize("pasta_ruim", [123, ["pasta"], object()], ids=["int", "list", "obj"])
def test_28_mutante_m3_r2_selecionar_direto_pasta_invalida_typeerror(tmp_path, pasta_ruim):
    cena = _cena_variada(tmp_path)
    with pytest.raises(TypeError):
        SL.selecionar(cena.f, cena.vistas["y_largo"], caminho_ifc=cena.arq, pasta_cache_geometria=pasta_ruim, executor=local.executar)

def test_29_mutante_m4_r2_processar_cache_preenche_faltantes(tmp_path):
    f, body, pav = _novo_ifc_base()
    ps = [_add_caixa(f, body, pav, "IfcWall", n, pos, (1.0, 0.25, 2.5)) for n, pos in (("C0", (0.5, 0.5, 0.0)), ("C1", (2.0, 0.5, 0.0)), ("A0", (1.0, 1.25, 0.0)), ("A1", (2.5, 1.25, 0.0)))]
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="faltantes.ifc", ids_cache=[ps[0].id(), ps[1].id()])
    el = [[f2.by_guid(p.GlobalId).id(), p.GlobalId] for p in ps]
    resp = geo_caixas.processar_cache({"op": "caixas_cache", "arquivo": str(arq), "pasta_cache_geometria": str(pasta), "elementos": el})
    assert resp.get("ok") is True and set(resp["caixas_envolventes"]) == {str(el[0][0]), str(el[1][0])} and set(resp["matrizes"]) == {str(el[0][0]), str(el[1][0])} and resp["faltantes"] == [el[2], el[3]]
    resp_ok = geo_caixas.processar_cache({"op": "caixas_cache", "arquivo": str(arq), "pasta_cache_geometria": str(pasta), "elementos": el[:2]})
    assert resp_ok.get("ok") is True and resp_ok["faltantes"] == []

# ---------------------------------------------------------------- (7) Rodada 4: sessao, 1 ULP, frescor 1e-4, mutantes R4

def test_30_sessao_reaproveita_caixa_cache_respeita_borda_vista_seguinte(tmp_path, monkeypatch):
    c = _cena_solda(tmp_path, "sessao_borda.ifc")
    s_ref = SessaoSelecao()
    ref1, ref2 = _rodar_selecao(c.f, c.v1, c.arq, pasta_cache=None, sessao=s_ref)[0], _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=None, sessao=s_ref)[0]
    assert ref1.ids == (c.id_solda,) and ref2.ids == (c.id_solda,) and ref2.faixa[0][0] == pytest.approx(1.0, abs=1e-12)
    chamadas_proc, s_nov = _espiar_caixas(monkeypatch), SessaoSelecao()
    nov1, ped1 = _rodar_selecao(c.f, c.v1, c.arq, pasta_cache=c.pasta, sessao=s_nov)
    assert nov1.ids == ref1.ids == (c.id_solda,) and chamadas_proc == [] and [p for p in ped1 if p.get("op") == "caixas"] == []
    nov2, _ = _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=c.pasta, sessao=s_nov)
    assert nov2.ids == ref2.ids == (c.id_solda,) and chamadas_proc == [{c.id_solda}]; _assert_sel_eq(nov2, ref2)

def test_31_borda_cache_maior_1_ulp_sintetico_nao_entra_peca_extra(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc_base()
    x_ulp = math.nextafter(4.0, 5.0)
    w_in, w_ulp = _add_caixa(f, body, pav, "IfcWall", "W_FOLGA", (1.0, 0.5, 0.5), (1.0, 1.0, 1.5)), _add_caixa(f, body, pav, "IfcWall", "W_ULP", (x_ulp, 0.5, 0.5), (1.0, 1.0, 1.5))
    w_fora = _add_caixa(f, body, pav, "IfcWall", "W_FORA", (4.05, 0.5, 0.5), (1.0, 1.0, 1.5))
    v_larga, v_tang = _add_vista_corte(f, "C_ULP_V1", (3.0, 0.0, 1.5), (6.0, 3.0, 2.0)), _add_vista_corte(f, "C_ULP_V2", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="ulp_sint.ifc")
    doc = construtor.documento_de(arq)
    with CG.abrir_cache(pasta, CG.cabecalho_atual(tesselacao=construtor.TESSELACAO)) as db:
        oc = db.ler_ocorrencia(w_ulp.GlobalId, documento=doc)
        assert oc is not None and float(oc.caixa[0, 0]) == x_ulp
        cx = oc.caixa.copy(); cx[0, 0] = 4.0  # cache maior que o kernel por 1 ULP
        db.gravar_lote({}, [CG.Ocorrencia(oc.global_id, oc.chave_forma, oc.matriz, cx, oc.pavimento, oc.classe_ifc)], documento=doc)
    id_in, id_ulp, id_fora = (f2.by_guid(el.GlobalId).id() for el in (w_in, w_ulp, w_fora))
    ref = _rodar_selecao(f2, v_tang, arq, pasta_cache=None)[0]
    assert ref.faixa == ((0.0, 0.0, 0.0), (4.0, 2.0, 3.0)) and ref.ids == (id_in,)
    chamadas_proc = _espiar_caixas(monkeypatch)
    nov, pedidos = _rodar_selecao(f2, v_tang, arq, pasta_cache=pasta)
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    _assert_sel_eq(nov, ref); assert ids_op == {id_ulp} and chamadas_proc == [{id_ulp}] and {id_in, id_fora}.isdisjoint(ids_op)
    chamadas_proc.clear(); s_nov = SessaoSelecao()
    assert id_ulp in _rodar_selecao(f2, v_larga, arq, pasta_cache=pasta, sessao=s_nov)[0].ids and chamadas_proc == []
    assert _rodar_selecao(f2, v_tang, arq, pasta_cache=pasta, sessao=s_nov)[0].ids == ref.ids and chamadas_proc == [{id_ulp}]

def test_32_borda_cache_maior_1_ulp_corpus_fzk_haus(tmp_path):
    arq_corpus = RAIZ / "corpus" / "kit-fzk-haus.ifc"
    if not arq_corpus.is_file():
        pytest.skip("corpus/kit-fzk-haus.ifc ausente neste checkout")
    f = ifcopenshell.open(str(arq_corpus))
    gid_v = _add_vista_corte(f, "CFZK_ULP", (11.305, 7.5, 1.4), (1.0, 4.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="fzk_ulp.ifc")
    ref, nov = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)[0]
    assert ref.faixa[1][0] == pytest.approx(11.805, abs=1e-12) and 31818 not in ref.ids and 31818 not in nov.ids
    _assert_sel_eq(nov, ref)

def test_33_mutante_frescor_deslocamento_1e4_rejeita_cache(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc_base()
    w_fix, w_micro = _add_caixa(f, body, pav, "IfcWall", "W_FIX", (1.0, 0.5, 0.5), (1.0, 1.0, 1.5)), _add_caixa(f, body, pav, "IfcWall", "W_MICRO", (4.00005, 0.5, 0.5), (1.0, 1.0, 1.5))
    gid_v = _add_vista_corte(f, "CMICRO", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0))
    arq, pasta, f_salvo = _salvar_e_construir(tmp_path, f, nome="frescor_1e4.ifc")
    m = np.eye(4, dtype=np.float64); m[:3, 3] = (3.99995, 0.5, 0.5)  # deslocamento de 1e-4 m (0,1 mm)
    ifcopenshell.api.run("geometry.edit_object_placement", f_salvo, product=f_salvo.by_guid(w_micro.GlobalId), matrix=m, is_si=False)
    f_salvo.write(str(arq)); f2 = ifcopenshell.open(str(arq))
    id_fix, id_micro = f2.by_guid(w_fix.GlobalId).id(), f2.by_guid(w_micro.GlobalId).id()
    ref = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0]
    assert ref.faixa == ((0.0, 0.0, 0.0), (4.0, 2.0, 3.0)) and ref.ids == tuple(sorted((id_fix, id_micro)))
    chamadas_proc = _espiar_caixas(monkeypatch)
    nov, _ = _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)
    _assert_sel_eq(nov, ref); assert id_micro in nov.ids and chamadas_proc == [{id_micro}]

def test_34_mutante_r4_restantes_borda_e_peca_nova_mesma_chamada(tmp_path, monkeypatch):
    # Mutante r4_restantes_sem_recalc (selecao.py ~L471): remover `or e.id() in recalcular_borda` -> W_SOLDA some de nov2.ids.
    c = _cena_solda(tmp_path, "r4_restantes.ifc", com_parede=True)
    esperados = tuple(sorted((c.id_solda, c.id_b)))
    ref2 = _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=None)[0]
    assert ref2.faixa[0][0] == pytest.approx(1.0, abs=1e-12) and ref2.ids == esperados
    chamadas_proc, s = _espiar_caixas(monkeypatch), SessaoSelecao()
    nov1, ped1 = _rodar_selecao(c.f, c.v1, c.arq, pasta_cache=c.pasta, sessao=s)
    assert nov1.ids == esperados and chamadas_proc == [] and [p for p in ped1 if p.get("op") == "caixas"] == []
    s.invalidar([c.id_b])  # W_B vira peca nova na vista 2 enquanto W_SOLDA cai na banda da borda
    nov2, ped2 = _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=c.pasta, sessao=s)
    ids_cache_v2 = {int(i) for p in ped2 if p.get("op") == "caixas_cache" for i, _ in p.get("elementos", ())}
    assert ids_cache_v2 == {c.id_b} and nov2.ids == ref2.ids == esperados and chamadas_proc == [{c.id_solda}]
    _assert_sel_eq(nov2, ref2)

def test_35_mutante_r4_gerente_invalidar_copia_do_cache(tmp_path, monkeypatch):
    # Mutante r4_gerente_sem_copia (gerente.py ~L437): remover `nova._do_cache = sessao._do_cache.copy()` -> W_SOLDA some de nov2.ids.
    QApplication.instance() or QApplication([])
    c = _cena_solda(tmp_path, "r4_gerente.ifc", com_parede=True)
    esperados = tuple(sorted((c.id_solda, c.id_b)))
    ref2 = _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=None)[0]
    assert ref2.faixa[0][0] == pytest.approx(1.0, abs=1e-12) and ref2.ids == esperados
    chamadas_proc, sels, prontos, falhas = _espiar_caixas(monkeypatch), [], [], []
    def _motor(tipo, ifc, gid, opcoes, *, cancelar, progresso, sessao_selecao=None):
        res = CO.gerar_corte(ifc, gid, sessao_selecao=sessao_selecao, ocultar_secundarias=False, executor=lambda p: dict(_STUB_DESENHO) if p.get("op") == "desenho" else local.executar(p), **opcoes)
        sels.append(res.selecao); return {"svg": res.svg, "n_paths": 0}
    g = GerenteDesenho(motor=_motor, filho_persistente=False)
    g.pronto.connect(lambda ch, _d: prontos.append(ch)); g.falhou.connect(lambda ch, m: falhas.append(f"{ch}:{m}"))
    def _pedir(gid: str):
        ch = g.pedir("corte", c.f, gid, caminho_ifc=c.arq, revisao=1, revisao_salva=1, pasta_cache_geometria=c.pasta)
        loop, t, fim = QEventLoop(), QTimer(), time.monotonic() + 15.0
        t.setInterval(5); t.timeout.connect(lambda: loop.quit() if (ch in prontos or falhas or time.monotonic() > fim) else None)
        t.start(); loop.exec(); t.stop()
        assert not falhas and ch in prontos; return sels[-1]
    try:
        assert _pedir(c.v1).ids == esperados and chamadas_proc == []
        g.invalidar(c.f, [c.id_b])
        nov2 = _pedir(c.v2)
        assert nov2.ids == ref2.ids == esperados and chamadas_proc == [{c.id_solda}]; _assert_sel_eq(nov2, ref2)
    finally:
        g.fechar()
