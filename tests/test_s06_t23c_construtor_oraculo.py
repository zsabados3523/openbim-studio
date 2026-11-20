# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T23c: núcleo do construtor (sem processo), interface exata do cartão.

Cenas sintéticas (ifcopenshell.api) e tests/amostras/casa-simples.ifc (mm). Sem IFC real. Mutantes 1-16: lista no fim.
"""
import sqlite3
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element as uel
import numpy as np
import pytest

import obim_geometria.cache_geometria as C
from obim_geometria import construtor, malha_direta, silhueta
from obim_geometria.cache_geometria import abrir_cache, cabecalho_atual, chave_da_forma, documento_de

CASA = Path(__file__).parent / "amostras" / "casa-simples.ifc"
CUBO = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
TRI = [(1, 3, 2), (1, 4, 3), (5, 6, 7), (5, 7, 8), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 4, 8), (3, 8, 7), (4, 1, 5), (4, 5, 8)]
DOC = documento_de("casa.ifc")


def _cena(posicoes, prefixo=None, esc=1.0, solto=False, escalas=None):
    """Cubos (IfcTriangulatedFaceSet) nas `posicoes` (unidade do arquivo); `solto` = vértices repetidos por triângulo."""
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    p = api("root.create_entity", f, ifc_class="IfcProject")
    u = f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=prefixo, Name="METRE")
    api("unit.assign_unit", f, units=[u])
    ctx = api("context.add_context", f, context_type="Model")
    f.body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    s, b = api("root.create_entity", f, ifc_class="IfcSite"), api("root.create_entity", f, ifc_class="IfcBuilding")
    f.andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey")
    for filho, pai in ((s, p), (b, s), (f.andar, b)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)
    els = []
    for i, pos in enumerate(posicoes):
        k = esc * (escalas[i] if escalas else 1.0)
        pts = [tuple(c * k for c in q) for q in CUBO]
        idx = TRI
        if solto:
            pts = [pts[j - 1] for tr in TRI for j in tr]
            idx = [(3 * n + 1, 3 * n + 2, 3 * n + 3) for n in range(len(TRI))]
        fs = f.createIfcTriangulatedFaceSet(Coordinates=f.createIfcCartesianPointList3D(pts), CoordIndex=idx)
        e = api("root.create_entity", f, ifc_class="IfcBuildingElementProxy")
        rep = f.createIfcShapeRepresentation(f.body, "Body", "Tessellation", [fs])
        e.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
        m = np.eye(4)
        m[:3, 3] = pos
        api("geometry.edit_object_placement", f, product=e, matrix=m, is_si=False)
        api("spatial.assign_container", f, products=[e], relating_structure=f.andar)
        els.append(e)
    return f, els


def _parede_com_abertura(f, x=10.0):
    api = ifcopenshell.api.run

    def caixa(classe, dim, pos):
        e = api("root.create_entity", f, ifc_class=classe)
        rep = api("geometry.add_wall_representation", f, context=f.body, length=dim[0], height=dim[1], thickness=dim[2])
        e.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
        m = np.eye(4)
        m[:3, 3] = pos
        api("geometry.edit_object_placement", f, product=e, matrix=m, is_si=False)
        return e

    w = caixa("IfcWall", (5, 3, 0.2), (x, 0, 0))
    api("spatial.assign_container", f, products=[w], relating_structure=f.andar)
    op = caixa("IfcOpeningElement", (1, 1, 0.5), (x + 2, -0.1, 1))
    api("feature.add_feature", f, feature=op, element=w)
    return w, op


def _banco(tmp_path, nome="c"):
    return construtor.abrir_banco(tmp_path / nome)


def _lote(f, cache, els, memo=None, assinatura="s1", **kw):
    ids = [e if isinstance(e, int) else e.id() for e in els]
    return construtor.construir_lote(f, cache, ids, documento=DOC, assinatura=assinatura, memo={} if memo is None else memo, **kw)


def _distintas(els):
    return len({chave_da_forma(e, tesselacao=construtor.TESSELACAO) for e in els})


def _tris(v, t):
    p = [tuple(float(x) + 0.0 for x in np.round(q, 6)) for q in np.asarray(v, dtype=float)]
    return {tuple(sorted(p[i] for i in tr)) for tr in np.asarray(t, dtype=int)}


def _confere_mundo(f, cache, els):
    """A1/A7: malha local x matriz = malha de formas_do_mundo (1e-6 m) e caixa no mundo."""
    for el in els:
        oc = cache.ler_ocorrencia(el.GlobalId, DOC)
        assert oc is not None, el.GlobalId
        v, t = cache.ler_forma(oc.chave_forma)
        w = v @ oc.matriz[:3, :3].T + oc.matriz[:3, 3]
        g = silhueta.formas_do_mundo(f, [el])[el.id()].geometry
        rv, rt = np.asarray(g.verts, float).reshape(-1, 3), np.asarray(g.faces, int).reshape(-1, 3)
        assert _tris(w, t) == _tris(rv, rt)
        assert np.allclose(oc.caixa, [rv.min(0), rv.max(0)], atol=1e-6)


def _dump(cache):
    con = cache._con
    return (
        con.execute("SELECT chave, dtype_v, vertices, triangulos, checksum FROM formas ORDER BY chave").fetchall(),
        con.execute("SELECT * FROM ocorrencias ORDER BY documento, global_id").fetchall(),
        con.execute("SELECT * FROM memo ORDER BY documento, id_step").fetchall(),
    )


@pytest.fixture
def espia(monkeypatch):
    e = type("E", (), {"lotes": [], "ler": [], "chaves": 0})()
    real_g, real_l, real_c = C.CacheGeometria.gravar_lote, C.CacheGeometria.ler_forma, C.chave_da_forma

    def g(self, formas, ocorrencias, documento="", memo=None):
        e.lotes.append({"formas": dict(formas), "ocs": list(ocorrencias), "memo": memo})
        return real_g(self, formas, ocorrencias, documento, memo)

    def l(self, chave):  # noqa: E741
        e.ler.append(chave)
        return real_l(self, chave)

    def c(*a, **k):
        e.chaves += 1
        return real_c(*a, **k)

    monkeypatch.setattr(C.CacheGeometria, "gravar_lote", g)
    monkeypatch.setattr(C.CacheGeometria, "ler_forma", l)
    monkeypatch.setattr(C, "chave_da_forma", c)
    monkeypatch.setattr(construtor, "chave_da_forma", c, raising=False)
    return e


def test_priorizar_estavel_e_pura():  # mutante 1
    fila = [10, 4, 7, 1, 9, 3]
    orig = list(fila)
    assert construtor.priorizar(fila, [3, 7, 99]) == [7, 3, 10, 4, 1, 9]  # ordem da fila, não de `primeiro`
    assert construtor.priorizar(fila, [9, 10]) == [10, 9, 4, 7, 1, 3]
    assert construtor.priorizar(fila, []) == orig and construtor.priorizar(fila, [99]) == orig
    assert construtor.priorizar(fila, {1}) == [1, 10, 4, 7, 9, 3]
    assert fila == orig and construtor.priorizar([], [1]) == []


def test_soldar():  # mutantes 6 e 7
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1 + 1e-8, 0, 0], [0, 0, 5], [5e-5, 0, 0]], dtype=np.float32)
    t = np.array([[0, 1, 2], [0, 3, 2], [0, 1, 3], [1, 2, 4]], dtype=np.int64)  # 2o duplica o 1o; 3o degenerado (1 e 3 colam)
    sv, st = construtor.soldar(v, t)
    assert sv.dtype == np.float64 and sv.ndim == 2 and sv.shape[1] == 3 and st.dtype == np.int32 and st.shape[1] == 3
    assert len(np.unique(np.round(sv, 7), axis=0)) == len(sv)  # sem vértices repetidos
    assert not any(len(set(tr)) < 3 for tr in st.tolist())  # sem degenerados
    assert _tris(v[:3], [[0, 1, 2]]) <= _tris(sv, st) and len(st) in (2, 3)
    assert all(0 <= i < len(sv) for i in st.ravel())
    # 5e-5 (acima de 1e-6) NÃO cola em (0,0,0)
    sv2, st2 = construtor.soldar(np.array([[0, 0, 0], [5e-5, 0, 0], [0, 1, 0]], float), np.array([[0, 1, 2]]))
    assert len(sv2) == 3 and len(st2) == 1


def test_rss_mb():
    a = construtor.rss_mb()
    assert isinstance(a, float) and 10 < a < 1e6
    bloco = np.ones(25_000_000)  # 200 MB tocados
    assert construtor.rss_mb() > a + 100 and bloco.size


def test_banco_abre_com_cabecalho_proprio_e_limpa(tmp_path, monkeypatch):  # mutante 14 (abrir_banco)
    assert construtor.documento_de is C.documento_de
    assert isinstance(construtor.TESSELACAO, dict) and construtor.TESSELACAO
    pasta = tmp_path / "g"
    velho = time.time() - 40 * 86400
    c0 = abrir_cache(pasta, cabecalho_atual(tesselacao=construtor.TESSELACAO), relogio=lambda: velho)
    c0.gravar_forma("antiga", np.zeros((3, 3)), np.zeros((1, 3), np.int32))
    c0.fechar()
    c1 = abrir_cache(pasta, cabecalho_atual(tesselacao=construtor.TESSELACAO))
    c1.gravar_forma("nova", np.zeros((3, 3)), np.zeros((1, 3), np.int32))
    c1.fechar()
    chamadas = []
    real = C.CacheGeometria.limpar
    monkeypatch.setattr(C.CacheGeometria, "limpar", lambda self, idade_max_s=None, teto_bytes=None: (chamadas.append((idade_max_s, teto_bytes)), real(self, idade_max_s, teto_bytes))[1])
    with construtor.abrir_banco(pasta) as cb:  # cabeçalho igual: não recria; limpa o de 40 dias
        assert not cb.em_memoria and cb.ler_forma("antiga") is None and cb.ler_forma("nova") is not None
    assert chamadas == [(30 * 86400, chamadas[0][1])] and chamadas[0][1] in (5 * 10**9, 5 * 2**30)


def test_abrir_banco_e_construir_recusam_memoria(tmp_path):  # mutante 14
    arq = tmp_path / "arquivo"
    arq.write_text("x")
    with pytest.raises(ValueError, match="banco_em_memoria"):
        construtor.abrir_banco(arq / "sub")
    mem = abrir_cache(arq / "sub")
    assert mem.em_memoria
    f, els = _cena([(0, 0, 0)])
    with pytest.raises(ValueError):
        _lote(f, mem, els)
    assert mem._con.execute("SELECT COUNT(*) FROM ocorrencias").fetchone()[0] == 0


def test_fila_inicial_universo_e_ordem():  # mutante 9
    f = ifcopenshell.open(str(CASA))
    esperado = sorted(f.by_type("IfcWall"), key=lambda e: e.GlobalId)
    assert construtor.fila_inicial(f) == [e.id() for e in esperado]  # laje sem Representation fica fora
    g, els = _cena([(0, 0, 0), (3, 0, 0)])
    op = ifcopenshell.api.run("root.create_entity", g, ifc_class="IfcOpeningElement")
    op.Representation = els[0].Representation
    vazio = ifcopenshell.api.run("root.create_entity", g, ifc_class="IfcBuildingElementProxy")
    fila = construtor.fila_inicial(g)
    assert op.id() not in fila and vazio.id() not in fila
    assert fila == [e.id() for e in sorted(els, key=lambda e: e.GlobalId)]
    assert all(type(i) is int for i in fila)


def test_pavimento_de():
    f = ifcopenshell.open(str(CASA))
    assert construtor.pavimento_de(f.by_id(18)) == "32Wkzr6RrD7wcBy10C3LGW"
    g, els = _cena([(0, 0, 0)])
    parte = ifcopenshell.api.run("root.create_entity", g, ifc_class="IfcBuildingElementPart")
    ifcopenshell.api.run("aggregate.assign_object", g, products=[parte], relating_object=els[0])
    assert construtor.pavimento_de(els[0]) == g.andar.GlobalId == construtor.pavimento_de(parte)
    solta = ifcopenshell.api.run("root.create_entity", g, ifc_class="IfcBuildingElementProxy")
    assert construtor.pavimento_de(solta) is None


def test_matriz_mundo_com_escala():  # mutante 4
    f, (e,) = _cena([(5000, 200, 0)], prefixo="MILLI")
    m = construtor.matriz_mundo(e, 0.001)
    assert m.shape == (4, 4) and np.allclose(m[:3, 3], [5.0, 0.2, 0.0]) and np.allclose(m[:3, :3], np.eye(3)) and np.allclose(m[3], [0, 0, 0, 1])
    assert np.allclose(construtor.matriz_mundo(e, 1.0)[:3, 3], [5000, 200, 0])


def test_malha_local_e_malha_mundo_inalterada():
    f, (a, b) = _cena([(5, 0, 0), (7, 3, 1)], esc=2.0)
    va, ta = malha_direta.malha_local(a)
    assert _tris(va, ta) == _tris(np.array(CUBO) * 2.0, np.array(TRI) - 1)  # origem local, sem a placement
    assert np.allclose(malha_direta.malha_local(a, 0.5)[0], va * 0.5)
    vm, tm = malha_direta.malha_mundo(b)
    assert np.allclose(vm.min(0), [7, 3, 1]) and np.allclose(vm, malha_direta.malha_local(b)[0] + [7, 3, 1])
    w, op = _parede_com_abertura(f)
    assert malha_direta.malha_local(w) is None and malha_direta.malha_mundo(w) is None and malha_direta.malha_local(op) is None


def test_copias_uma_forma_local_e_caixa_no_mundo(tmp_path, espia):  # mutantes 3, 5, 11, 16 e 8
    pos = [(10 * i + 100, 7 * i, 3 * i + 1) for i in range(20)]
    f, els = _cena(pos)
    with _banco(tmp_path) as cache:
        r = _lote(f, cache, els[:1])
        assert (r["tesseladas"], r["falhas"]) == (1, 0)
        r = _lote(f, cache, els[1:])  # forma já no banco: caixa de cópia com no máx. 1 ler_forma por chave
        assert r["tesseladas"] == 0 and r["falhas"] == 0 and len(espia.ler) <= 1
        assert cache._con.execute("SELECT COUNT(*) FROM formas").fetchone()[0] == 1
        chave = chave_da_forma(els[0], tesselacao=construtor.TESSELACAO)
        v, t = cache.ler_forma(chave)
        assert _tris(v, t) == _tris(CUBO, np.array(TRI) - 1) and v.dtype == np.float64  # local, não mundo
        for e, p in zip(els, pos):
            oc = cache.ler_ocorrencia(e.GlobalId, DOC)
            assert oc.chave_forma == chave and oc.classe_ifc == "IfcBuildingElementProxy" and oc.pavimento == f.andar.GlobalId
            assert np.allclose(oc.matriz[:3, 3], p)
            assert np.allclose(oc.caixa, [p, np.array(p) + 1])  # caixa no mundo
    assert len([x for x in espia.lotes if x["ocs"]]) == 2


def test_vinte_copias_num_lote_tesselam_uma_vez(tmp_path, espia):  # mutantes 3, 11, 16
    f, els = _cena([(i * 3, 0, 0) for i in range(20)])
    with _banco(tmp_path) as cache:
        r = _lote(f, cache, els)
        assert r["tesseladas"] == 1 and r["falhas"] == 0 and r["gravadas"] == 20
        assert cache._con.execute("SELECT COUNT(*) FROM formas").fetchone()[0] == 1
        assert len(espia.ler) <= 1 and len(espia.lotes) == 1
        for e in els:
            assert np.allclose(cache.ler_ocorrencia(e.GlobalId, DOC).caixa[0], e.ObjectPlacement.RelativePlacement.Location.Coordinates)


def test_mundo_milimetros_iterador_e_direta(tmp_path):  # mutantes 4, 5, 11 (A7)
    f = ifcopenshell.open(str(CASA))
    g, els = _cena([(5000, 0, 0), (0, 2000, 500)], prefixo="MILLI", esc=1000.0)
    w, op = _parede_com_abertura(g)
    with _banco(tmp_path) as cache:
        r = _lote(f, cache, f.by_type("IfcWall"))
        assert r["tesseladas"] == _distintas(f.by_type("IfcWall")) == 2 and r["falhas"] == 0  # 4 paredes, 2 formas
        _confere_mundo(f, cache, f.by_type("IfcWall"))
        assert np.isclose(cache.ler_ocorrencia("3LNnHUIBXEnvnzMtAfenLD", DOC).matriz[0, 3], 6.0)  # 6000 mm
        r = _lote(g, cache, els + [w])  # direta (mm) + iterador com abertura
        assert r["tesseladas"] == 2 and r["falhas"] == 0  # os 2 cubos de mesmo tamanho dividem a forma
        _confere_mundo(g, cache, els + [w])
        assert np.isclose(cache.ler_ocorrencia(els[0].GlobalId, DOC).matriz[0, 3], 5.0)


def test_forma_soldada_dtypes(tmp_path):  # mutantes 6 e 7, nos dois caminhos
    f = ifcopenshell.open(str(CASA))
    g, (c,) = _cena([(1, 2, 3)], solto=True)  # direta com 36 vértices repetidos
    with _banco(tmp_path) as cache:
        _lote(f, cache, f.by_type("IfcWall"))
        _lote(g, cache, [c])
        formas = cache._con.execute("SELECT chave FROM formas").fetchall()
        assert len(formas) == 3  # 2 formas da casa + o cubo
        for (k,) in formas:
            v, t = cache.ler_forma(k)
            assert v.dtype == np.float64 and t.dtype == np.int32 and v.shape[1] == 3 and len(t)
            assert len(np.unique(np.round(v, 7), axis=0)) == len(v)
            assert not any(len(set(tr)) < 3 for tr in t.tolist())
        v, _ = cache.ler_forma(cache.ler_ocorrencia(c.GlobalId, DOC).chave_forma)
        assert len(v) == 8


def test_um_lote_uma_transacao_memo_dentro_e_falha(tmp_path, espia):  # mutante 8
    f, els = _cena([(i, 0, 0) for i in range(5)], escalas=[1, 2, 3, 4, 5])
    els = els[::-1]  # ordem de entrada invertida
    vazio = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingElementProxy")
    with _banco(tmp_path) as cache:
        eventos = []
        cache._con.set_trace_callback(lambda s: eventos.append(s.split()[0].upper()) if s.split() else None)
        memo = {}
        r = _lote(f, cache, els + [vazio], memo=memo)
        cache._con.set_trace_callback(None)
        assert eventos.count("BEGIN") == 1 and eventos.count("COMMIT") == 1
        assert len(espia.lotes) == 1 and espia.lotes[0]["memo"][0] == "s1"
        ids = [o.global_id for o in espia.lotes[0]["ocs"]]
        assert ids == sorted(ids) and len(ids) == 5  # ordenadas por GlobalId
        assert r["falhas"] == 1 and r["tesseladas"] == 5 and r["gravadas"] == 5  # mutante 10: o lote segue
        assert all(cache.ler_ocorrencia(e.GlobalId, DOC) for e in els)
        assert cache.ler_ocorrencia(vazio.GlobalId, DOC) is None
        esperado = {e.id(): chave_da_forma(e, tesselacao=construtor.TESSELACAO) for e in els}
        assert {k: memo[k] for k in esperado} == esperado and esperado.items() <= cache.memo_ler(DOC, "s1").items()
        assert set(r) >= {"tesseladas", "reaproveitadas", "falhas", "gravadas", "segundos"} and r["segundos"] >= 0


def test_erro_de_gravacao_nao_deixa_nada(tmp_path, monkeypatch):  # mutante 8 (atomicidade, memo dentro)
    f, els = _cena([(0, 0, 0), (3, 0, 0)])
    with _banco(tmp_path) as cache:
        def explode(self, *a, **k):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(C.CacheGeometria, "gravar_lote", explode)
        with pytest.raises(sqlite3.OperationalError):
            _lote(f, cache, els)
        monkeypatch.undo()
        assert cache._con.execute("SELECT (SELECT COUNT(*) FROM formas)+(SELECT COUNT(*) FROM ocorrencias)+(SELECT COUNT(*) FROM memo)").fetchone()[0] == 0


def test_segunda_chamada_e_retomada_nao_regrava(tmp_path, espia):  # mutantes 2, 13, 15
    f, els = _cena([(i, 0, 0) for i in range(4)], escalas=[1, 2, 3, 4])
    with _banco(tmp_path) as cache:
        memo = {}
        _lote(f, cache, els, memo=memo)
        n_chaves = espia.chaves
        espia.lotes.clear()
        r = _lote(f, cache, els, memo=memo)  # mesmo lote, memo válido
        assert r["tesseladas"] == 0 and r["gravadas"] == 0 and espia.chaves == n_chaves  # memo respeitado (13)
        assert sum(len(x["ocs"]) for x in espia.lotes) == 0 and len(espia.lotes) <= 1
        r = _lote(f, cache, els)  # memo novo (filho renasceu): recalcula chaves, mas não tessela nem regrava
        assert r["tesseladas"] == 0 and r["gravadas"] == 0 and espia.chaves == n_chaves + 4
        assert sum(len(x["ocs"]) for x in espia.lotes) == 0
        # tolerância 1e-9 na matriz: pula; 1e-6: regrava só essa
        oc = cache.ler_ocorrencia(els[0].GlobalId, DOC)
        oc.matriz = oc.matriz.copy()
        oc.matriz[0, 3] += 5e-10
        cache.gravar_ocorrencia(oc, DOC)
        espia.lotes.clear()
        assert _lote(f, cache, els, memo=memo)["gravadas"] == 0
        assert cache.ler_ocorrencia(els[0].GlobalId, DOC).matriz[0, 3] == oc.matriz[0, 3]
        oc.matriz[0, 3] += 1e-6
        cache.gravar_ocorrencia(oc, DOC)
        assert _lote(f, cache, els, memo=memo)["gravadas"] == 1
        assert [o.global_id for o in espia.lotes[-1]["ocs"]] == [els[0].GlobalId]
        assert abs(cache.ler_ocorrencia(els[0].GlobalId, DOC).matriz[0, 3]) < 1e-9


def test_memo_com_forma_ausente_tessela_sob_a_chave_do_memo(tmp_path, espia):  # mutante 13
    f, els = _cena([(0, 0, 0), (2, 0, 0)], escalas=[1, 2])
    with _banco(tmp_path, "a") as c1:
        memo = {}
        _lote(f, c1, els, memo=memo)
    espia.chaves = 0
    with _banco(tmp_path, "b") as c2:  # banco novo, memo do banco antigo
        r = _lote(f, c2, els, memo=dict(memo))
        assert espia.chaves == 0 and r["tesseladas"] == 2
        assert c2.formas_presentes(memo.values()) == set(memo.values())


def test_determinismo_threads(tmp_path):  # mutante 12 (A6)
    f = ifcopenshell.open(str(CASA))
    g, els = _cena([(i * 2, 0, 0) for i in range(8)], escalas=[1, 2, 3, 4, 5, 6, 7, 8])
    w, _ = _parede_com_abertura(g)
    dumps = []
    for n in (1, 4):
        with _banco(tmp_path, f"t{n}") as cache:
            _lote(f, cache, f.by_type("IfcWall"), threads=n)
            _lote(g, cache, els + [w], threads=n)
            dumps.append(_dump(cache))
    assert dumps[0] == dumps[1] and len(dumps[0][0]) == 2 + 8 + 1

# Mutantes (teste que derruba): 1 priorizar; 2 e 15 segunda_chamada_e_retomada; 3 copias/vinte_copias; 4 matriz_mundo e mundo_milimetros;
# 5 e 11 copias e mundo_milimetros; 6 e 7 soldar e forma_soldada_dtypes; 8 um_lote_uma_transacao e erro_de_gravacao; 9 fila_inicial;
# 10 um_lote (falha de peca); 12 determinismo; 13 segunda_chamada e memo_com_forma_ausente; 14 abrir_banco e recusam_memoria; 16 copias e vinte_copias.
