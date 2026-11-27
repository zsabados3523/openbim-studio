# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-T27c (parte A): equivalencia, queda, processo pai, espiao e frescor.

NAO editar este arquivo na implementacao. Auxiliares compartilhados em `t27c_aux.py`.
"""
from __future__ import annotations

import ast, math, sqlite3
from pathlib import Path

import ifcopenshell, ifcopenshell.api, ifcopenshell.guid, numpy as np, pytest

from obim_geometria import cache_geometria as CG, construtor, local
from openbim_app.desenho import corte as CO
from openbim_app.desenho.selecao import SessaoSelecao
from t27c_aux import (
    RAIZ, _STUB_DESENHO, _add_caixa, _add_faceset, _add_vista_corte, _assert_sel_eq,
    _cena_solda, _cena_variada, _comparar_cache, _espiar_caixas, _novo_ifc_base, _rodar_selecao, _salvar_e_construir, _sql,
)

def _add_caixa_rot(f, body, pav, classe, nome, pos, dim, rot_z: float):
    el = _add_caixa(f, body, pav, classe, nome, pos, dim)
    rad = math.radians(rot_z); c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=np.float64); m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c; m[:3, 3] = pos
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el

# ---------------------------------------------------------------- (1) Equivalencia

@pytest.mark.parametrize(
    ("vista_k", "prof", "espera_vazio"),
    [("y_largo", None, False), ("y_largo", 1.0, False), ("y_estreito", None, False), ("x_plano", None, False), ("obliquo", None, False), ("vazio", None, True)],
)
def test_01_equivalencia_planos_e_retangulos(tmp_path, vista_k, prof, espera_vazio):
    cena = _cena_variada(tmp_path)
    gid = cena.vistas[vista_k]
    ref, _ = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None, prof=prof)
    nov, _ = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=cena.pasta, prof=prof)
    _assert_sel_eq(nov, ref)
    assert nov.falhas_geometria == ref.falhas_geometria
    assert (nov.ids == ()) if espera_vazio else (0 < len(nov.ids) < len(cena.gids))

def test_02_equivalencia_borda_exata_inclusiva(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc_base()
    dentro = {
        "dentro": ((1.0, 0.5, 0.5), (1.0, 1.0, 1.5)), "borda_xmin": ((-1.0, 0.5, 0.5), (1.0, 1.0, 1.5)),
        "borda_xmax": ((4.0, 0.5, 0.5), (1.0, 1.0, 1.5)), "borda_ymin": ((1.0, -1.0, 0.5), (1.0, 1.0, 1.5)),
        "borda_ymax": ((1.0, 2.0, 0.5), (1.0, 1.0, 1.5)), "borda_zmin": ((1.0, 0.5, -1.0), (1.0, 1.0, 1.0)),
        "borda_zmax": ((1.0, 0.5, 3.0), (1.0, 1.0, 1.0)), "borda_quina": ((4.0, 2.0, 3.0), (1.0, 1.0, 1.0)),
    }
    fora = {"fora_x": ((4.0625, 0.5, 0.5), (1.0, 1.0, 1.5)), "fora_y": ((1.0, 2.0625, 0.5), (1.0, 1.0, 1.5)), "fora_z": ((1.0, 0.5, 3.0625), (1.0, 1.0, 1.0))}
    g_in = {n: _add_caixa(f, body, pav, "IfcWall", n, p, d).GlobalId for n, (p, d) in dentro.items()}
    g_out = {n: _add_caixa(f, body, pav, "IfcWall", n, p, d).GlobalId for n, (p, d) in fora.items()}
    gid_v = _add_vista_corte(f, "CBORDA", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0), angulo_graus=0.0)
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="borda.ifc")
    ref, chamadas_proc = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _espiar_caixas(monkeypatch)
    nov, pedidos = _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)
    assert ref.faixa == ((0.0, 0.0, 0.0), (4.0, 2.0, 3.0))
    assert nov.ids == ref.ids == tuple(sorted(f2.by_guid(g).id() for g in g_in.values()))
    assert all(f2.by_guid(g).id() not in nov.ids for g in g_out.values())
    ids_borda = {f2.by_guid(g).id() for n, g in g_in.items() if n != "dentro"}
    ids_folga = {f2.by_guid(g_in["dentro"]).id(), *(f2.by_guid(g).id() for g in g_out.values())}
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    assert ids_op == ids_borda, f"pecas na borda (dist <= 1e-5) devem cair em op 'caixas'; esperado={ids_borda}, recebido={ids_op}"
    assert ids_op.isdisjoint(ids_folga), f"pecas com margem folgada nao devem chamar op 'caixas': {ids_op & ids_folga}"
    assert chamadas_proc == [ids_borda], f"caixas.processar deveria receber so a borda {ids_borda}; recebido={chamadas_proc}"

def test_03_equivalencia_pecas_com_furos(tmp_path):
    f, body, pav = _novo_ifc_base()
    api = ifcopenshell.api.run
    w_jan = _add_caixa(f, body, pav, "IfcWall", "W_JAN", (0.0, 0.0, 0.0), (4.0, 0.25, 3.0))
    vao1 = _add_caixa(f, body, pav, "IfcOpeningElement", "V1", (1.5, -0.25, 1.0), (1.0, 0.75, 1.0), conter=False)
    jan = _add_caixa(f, body, pav, "IfcWindow", "J1", (1.5, 0.0, 1.0), (1.0, 0.25, 1.0), conter=False)
    api("feature.add_feature", f, feature=vao1, element=w_jan); api("feature.add_filling", f, opening=vao1, element=jan)
    w_rec = _add_caixa(f, body, pav, "IfcWall", "W_REC", (0.0, 1.0, 0.0), (4.0, 0.25, 3.0))
    vao2 = _add_caixa(f, body, pav, "IfcOpeningElement", "V2", (2.0, 0.5, -0.25), (2.25, 1.25, 3.5), conter=False)
    api("feature.add_feature", f, feature=vao2, element=w_rec)
    v_tudo, v_dir = _add_vista_corte(f, "CF_ALL", (2.0, -0.5, 1.5), (5.0, 4.0, 3.0)), _add_vista_corte(f, "CF_DIR", (3.5, -0.5, 1.5), (2.0, 4.0, 3.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="furos.ifc")
    with CG.abrir_cache(pasta, CG.cabecalho_atual(tesselacao=construtor.TESSELACAO)) as db:
        oc_rec = db.ler_ocorrencia(w_rec.GlobalId, documento=construtor.documento_de(arq))
        assert oc_rec is not None and oc_rec.caixa[1, 0] == pytest.approx(2.0, abs=1e-5)
    for gid_v, rec_entra in ((v_tudo, True), (v_dir, False)):
        ref, nov = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)[0]
        assert nov.ids == ref.ids and (f2.by_guid(w_rec.GlobalId).id() in nov.ids) is rec_entra
        assert f2.by_guid(w_jan.GlobalId).id() in nov.ids and f2.by_guid(vao1.GlobalId).id() not in nov.ids

def test_04_equivalencia_varias_ocorrencias_mesma_forma_matriz_diferente(tmp_path):
    f, body, pav = _novo_ifc_base()
    configs = [
        ((0.5, 0.5, 0.0), 0.0), ((1.5, 0.5, 0.0), 90.0), ((2.5, 1.0, 0.0), 45.0), ((3.5, 1.5, 0.5), 180.0),
        ((5.5, 0.5, 0.0), 0.0), ((0.5, 4.0, 0.0), 90.0), ((-2.5, 0.5, 0.0), 30.0), ((1.0, 1.0, 4.5), 0.0),
    ]
    gids = [_add_caixa_rot(f, body, pav, "IfcColumn", f"P{i}", p, (0.5, 0.25, 2.0), a).GlobalId for i, (p, a) in enumerate(configs)]
    v1, v2 = _add_vista_corte(f, "CM1", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0), angulo_graus=0.0), _add_vista_corte(f, "CM2", (0.5, 1.5, 1.5), (3.0, 3.0, 4.0), angulo_graus=-90.0)
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="instancias.ifc")
    assert _sql(pasta, "SELECT COUNT(*) FROM formas") == [(1,)] and _sql(pasta, "SELECT COUNT(*) FROM ocorrencias") == [(len(gids),)]
    for gid_v in (v1, v2):
        ref, nov = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)[0]
        assert nov.ids == ref.ids and 0 < len(nov.ids) < len(gids)

# ---------------------------------------------------------------- (2) Queda

def test_05_queda_pecas_ausentes_do_cache(tmp_path):
    f, body, pav = _novo_ifc_base()
    p0, p1 = _add_caixa(f, body, pav, "IfcWall", "CacheDentro1", (0.5, 0.5, 0.0), (1.0, 0.25, 2.5)), _add_caixa(f, body, pav, "IfcWall", "CacheDentro2", (2.0, 0.5, 0.0), (1.0, 0.25, 2.5))
    p2, p3 = _add_caixa(f, body, pav, "IfcWall", "CacheFora", (5.0, 0.5, 0.0), (1.0, 0.25, 2.5)), _add_caixa(f, body, pav, "IfcWall", "AusenteDentro", (1.0, 1.25, 0.0), (1.5, 0.25, 2.5))
    p4 = _add_caixa(f, body, pav, "IfcWall", "AusenteFora", (5.0, 1.25, 0.0), (1.0, 0.25, 2.5))
    gid_v = _add_vista_corte(f, "CPARC", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="parcial.ifc", ids_cache=[p0.id(), p1.id(), p2.id()])
    ref, nov = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)[0]
    assert nov.ids == ref.ids and f2.by_guid(p3.GlobalId).id() in nov.ids and f2.by_guid(p4.GlobalId).id() not in nov.ids

@pytest.mark.parametrize("modo", ["pasta_inexistente", "pasta_vazia", "banco_lixo", "cabecalho_incompativel"])
def test_06_queda_cache_ausente_ou_corrompido(tmp_path, modo):
    cena = _cena_variada(tmp_path)
    gid = cena.vistas["y_largo"]
    ref, lixo, alvo = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0], b"nao e um arquivo sqlite valido" * 100, tmp_path / modo
    if modo == "pasta_vazia":
        alvo.mkdir()
    elif modo == "banco_lixo":
        alvo.mkdir(); (alvo / CG.NOME_BANCO).write_bytes(lixo)
    elif modo == "cabecalho_incompativel":
        gid_p1, doc = cena.gids["P1"], construtor.documento_de(cena.arq)
        with CG.abrir_cache(cena.pasta, CG.cabecalho_atual(tesselacao=construtor.TESSELACAO)) as db_ok:
            oc_p1 = db_ok.ler_ocorrencia(gid_p1, documento=doc)
        assert oc_p1 is not None
        caixa_falsa = np.array([[50.0, 50.0, 0.0], [51.0, 51.0, 2.0]], dtype=np.float64)
        with CG.abrir_cache(alvo, CG.cabecalho_atual(versao_motor="999", tesselacao=construtor.TESSELACAO)) as db_inc:
            db_inc.gravar_lote({}, [CG.Ocorrencia(gid_p1, oc_p1.chave_forma, oc_p1.matriz, caixa_falsa, oc_p1.pavimento, oc_p1.classe_ifc)], documento=doc)
    nov, pedidos = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=alvo)
    assert nov.ids == ref.ids and len(nov.ids) > 0
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    assert cena.f.by_guid(cena.gids["P1"]).id() in ids_op
    if modo == "banco_lixo":
        assert (alvo / CG.NOME_BANCO).read_bytes() == lixo

def test_07_queda_ocorrencia_corrompida_no_banco(tmp_path):
    cena = _cena_variada(tmp_path)
    gid, alvo_gid = cena.vistas["y_largo"], cena.gids["P1"]
    ref = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0]
    [(blob,)] = _sql(cena.pasta, "SELECT caixa FROM ocorrencias WHERE global_id = ?", (alvo_gid,))
    corromp = bytearray(blob); corromp[0] ^= 0xFF
    _sql(cena.pasta, "UPDATE ocorrencias SET caixa = ? WHERE global_id = ?", (bytes(corromp), alvo_gid))
    nov, _ = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=cena.pasta)
    assert nov.ids == ref.ids and cena.f.by_guid(alvo_gid).id() in nov.ids

# ---------------------------------------------------------------- (3) Nao toca o pai

@pytest.mark.parametrize("rel", ["app/openbim_app/desenho/corte.py", "app/openbim_app/desenho/gerente.py", "app/openbim_app/desenho/selecao.py"])
def test_08_ast_modulos_pai_nao_importam_banco_nem_cache(rel):
    proibidos = {"sqlite3", "cache_geometria", "cache_leitura"}
    arvore = ast.parse((RAIZ / rel).read_text(encoding="utf-8"), filename=rel)
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados.update(p for al in no.names for p in al.name.split(".") if p in proibidos)
        elif isinstance(no, ast.ImportFrom):
            achados |= (set((no.module or "").split(".")) | {p for al in no.names for p in al.name.split(".")}) & proibidos
        elif isinstance(no, ast.Call) and no.args and isinstance(no.args[0], ast.Constant):
            fn = no.func.attr if isinstance(no.func, ast.Attribute) else getattr(no.func, "id", "")
            val = no.args[0].value
            if fn in ("import_module", "__import__") and isinstance(val, str) and (set(val.split(".")) & proibidos):
                achados.add(val)
    assert not achados, f"{rel} importa modulos proibidos no pai: {sorted(achados)}"

def test_09_leitura_do_banco_roda_so_no_filho_nunca_no_pai(tmp_path, monkeypatch):
    cena = _cena_variada(tmp_path)
    gid = cena.vistas["y_largo"]
    em_filho, aberturas_filho, pedidos_sel, real_connect = False, [], [], sqlite3.connect
    def _connect_vigiado(*a, **k):
        if not em_filho:
            raise AssertionError("sqlite3.connect chamado na thread do processo pai durante selecao")
        aberturas_filho.append(str(a[0]) if a else "")
        return real_connect(*a, **k)
    monkeypatch.setattr(sqlite3, "connect", _connect_vigiado)
    def _exec(ped: dict) -> dict:
        nonlocal em_filho
        if ped.get("op") == "desenho":
            return dict(_STUB_DESENHO)
        pedidos_sel.append(dict(ped)); em_filho = True
        try:
            return local.executar(ped)
        finally:
            em_filho = False
    CO.gerar_corte(cena.f, gid, caminho_ifc=cena.arq, pasta_cache_geometria=cena.pasta, ocultar_secundarias=False, executor=_exec)
    banco_esp = (cena.pasta / CG.NOME_BANCO).resolve()
    assert any(str(cena.pasta) in (p.get("pasta_cache_geometria"), p.get("pasta_cache")) for p in pedidos_sel), f"selecao nao enviou pasta do cache ao filho; pedidos={pedidos_sel}"
    assert any(Path(c).resolve() == banco_esp for c in aberturas_filho if c), f"filho nao leu {banco_esp} na selecao; aberturas={aberturas_filho}"

# ---------------------------------------------------------------- (4) Espiao op `caixas`

def test_10_espiao_cache_completo_nao_chama_op_caixas(tmp_path, monkeypatch):
    cena = _cena_variada(tmp_path)
    gid = cena.vistas["y_largo"]
    ref = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=None)[0]
    chamadas_proc, leituras_forma, real_ler = _espiar_caixas(monkeypatch), [], CG.CacheGeometria.ler_forma_estado
    monkeypatch.setattr(CG.CacheGeometria, "ler_forma_estado", lambda self, ch: (leituras_forma.append(ch), real_ler(self, ch))[1])
    sessao = SessaoSelecao()
    nov, pedidos = _rodar_selecao(cena.f, gid, cena.arq, pasta_cache=cena.pasta, sessao=sessao)
    pedidos_caixas = [p for p in pedidos if p.get("op") == "caixas"]
    assert nov.ids == ref.ids and len(nov.ids) > 0
    assert pedidos_caixas == [] and chamadas_proc == [] and leituras_forma == []
    assert set(nov.ids).issubset(sessao._caixas) and all(len(sessao._caixas[i]) == 6 for i in nov.ids)

def test_11_espiao_cache_parcial_op_caixas_so_para_ausentes(tmp_path, monkeypatch):
    f, body, pav = _novo_ifc_base()
    p0, p1 = _add_caixa(f, body, pav, "IfcWall", "EmCache1", (0.5, 0.5, 0.0), (1.0, 0.25, 2.5)), _add_caixa(f, body, pav, "IfcWall", "EmCache2", (2.0, 0.5, 0.0), (1.0, 0.25, 2.5))
    p2, p3 = _add_caixa(f, body, pav, "IfcWall", "Ausente1", (1.0, 1.25, 0.0), (1.0, 0.25, 2.5)), _add_caixa(f, body, pav, "IfcWall", "Ausente2", (2.5, 1.25, 0.0), (1.0, 0.25, 2.5))
    gid_v = _add_vista_corte(f, "CESP", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="espiao_parcial.ifc", ids_cache=[p0.id(), p1.id()])
    ids_cache, ids_aus = {f2.by_guid(p0.GlobalId).id(), f2.by_guid(p1.GlobalId).id()}, {f2.by_guid(p2.GlobalId).id(), f2.by_guid(p3.GlobalId).id()}
    ref, chamadas_proc, sessao = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _espiar_caixas(monkeypatch), SessaoSelecao()
    nov, pedidos = _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta, sessao=sessao)
    ids_op = {int(i) for p in pedidos if p.get("op") == "caixas" for i, _ in p.get("elementos", ())}
    assert nov.ids == ref.ids and ids_op.isdisjoint(ids_cache) and ids_aus.issubset(ids_op)
    assert len(chamadas_proc) == 1 and chamadas_proc[0] == ids_aus and (ids_cache | ids_aus).issubset(sessao._caixas)

# ---------------------------------------------------------------- (5) Frescor e geometria limite

def test_12_frescor_peca_movida_e_salva_sem_rebuild(tmp_path):
    f, body, pav = _novo_ifc_base()
    w_fix = _add_caixa(f, body, pav, "IfcWall", "W_FIX", (0.5, 0.5, 0.0), (1.0, 0.25, 2.5))
    w_entra, w_sai = _add_caixa(f, body, pav, "IfcWall", "W_ENTRA", (6.0, 0.5, 0.0), (1.0, 0.25, 2.5)), _add_caixa(f, body, pav, "IfcWall", "W_SAI", (2.0, 0.5, 0.0), (1.0, 0.25, 2.5))
    gid_v = _add_vista_corte(f, "CFRESC", (2.0, 0.0, 1.5), (4.0, 3.0, 2.0))
    arq, pasta, f_salvo = _salvar_e_construir(tmp_path, f, nome="frescor.ifc")
    for gid_w, nova_pos in ((w_entra.GlobalId, (2.0, 0.5, 0.0)), (w_sai.GlobalId, (6.0, 0.5, 0.0))):
        m = np.eye(4, dtype=np.float64); m[:3, 3] = nova_pos
        ifcopenshell.api.run("geometry.edit_object_placement", f_salvo, product=f_salvo.by_guid(gid_w), matrix=m, is_si=False)
    f_salvo.write(str(arq)); f2 = ifcopenshell.open(str(arq))
    ref, _ = _comparar_cache(f2, gid_v, arq, pasta)
    assert f2.by_guid(w_fix.GlobalId).id() in ref.ids and f2.by_guid(w_entra.GlobalId).id() in ref.ids and f2.by_guid(w_sai.GlobalId).id() not in ref.ids

@pytest.mark.parametrize("tipo", ["poly", "tri"])
def test_13_faceset_com_hasopenings_recortando_ponta(tmp_path, tipo):
    f, body, pav = _novo_ifc_base()
    dx, dy, dz = 4.0, 0.25, 3.0
    pts = [(0.0, 0.0, 0.0), (dx, 0.0, 0.0), (dx, dy, 0.0), (0.0, dy, 0.0), (0.0, 0.0, dz), (dx, 0.0, dz), (dx, dy, dz), (0.0, dy, dz)]
    kw = {"faces": ((1, 4, 3, 2), (5, 6, 7, 8), (1, 2, 6, 5), (2, 3, 7, 6), (3, 4, 8, 7), (4, 1, 5, 8))} if tipo == "poly" else {"tris": [(1, 4, 3), (1, 3, 2), (5, 6, 7), (5, 7, 8), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 4, 8), (3, 8, 7), (4, 1, 5), (4, 5, 8)]}
    w = _add_faceset(f, body, pav, "W_FS", (0.0, 0.0, 0.0), pts, **kw)
    vao = _add_caixa(f, body, pav, "IfcOpeningElement", "V_FS", (2.0, -0.25, -0.25), (2.25, 0.75, 3.5), conter=False)
    ifcopenshell.api.run("feature.add_feature", f, feature=vao, element=w)
    vistas = (_add_vista_corte(f, "CFS_DIR", (3.5, -0.5, 1.5), (2.0, 4.0, 3.0)), _add_vista_corte(f, "CFS_ALL", (2.0, -0.5, 1.5), (5.0, 4.0, 3.0)))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome=f"fs_{tipo}.ifc")
    for gid_v in vistas:
        _comparar_cache(f2, gid_v, arq, pasta)

def test_14_project_library_sem_unidade_com_mili_no_project(tmp_path):
    f, body, pav = _novo_ifc_base()
    next(u for u in f.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT").Prefix = "MILLI"
    f.create_entity("IfcProjectLibrary", GlobalId=ifcopenshell.guid.new(), Name="LibSemUnidade")
    _add_caixa(f, body, pav, "IfcWall", "W_MM", (1000.0, 500.0, 0.0), (1.0, 0.25, 2.0))
    gid_v = _add_vista_corte(f, "C_MM", (1500.0, 0.0, 1000.0), (2000.0, 3000.0, 2000.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="proj_lib_mili.ifc")
    _comparar_cache(f2, gid_v, arq, pasta)

def test_15_placement_refdirection_nao_ortogonal_a_axis(tmp_path):
    f, body, pav = _novo_ifc_base()
    w = _add_caixa(f, body, pav, "IfcWall", "W_NO", (1.0, 1.0, 0.0), (1.0, 1.0, 2.0))
    pl = w.ObjectPlacement.RelativePlacement
    pl.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    pl.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.5))
    gid_v = _add_vista_corte(f, "C_NO", (2.5, 0.0, 1.0), (1.1, 2.0, 3.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="nao_orto.ifc")
    _comparar_cache(f2, gid_v, arq, pasta)

def test_16_borda_exata_apos_solda_1e6(tmp_path):
    c = _cena_solda(tmp_path, "solda_borda.ifc", y_corte=0.0)
    ref, nov = _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=None)[0], _rodar_selecao(c.f, c.v2, c.arq, pasta_cache=c.pasta)[0]
    assert ref.faixa[0][0] == pytest.approx(1.0, abs=1e-12) and nov.ids == ref.ids
