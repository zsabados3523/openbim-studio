# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19g2: a leitura direta (T19g) reaproveita a triangulação local de fontes compartilhadas e roda em paralelo. Cartão: docs/state/cards/F0-S06/F0-S06-T19g2-malha-cache-paralelo.md. Não editar nesta tarefa.
Medido (casarão): `formas_do_mundo` 29,8 s; cada planta Lilie 8,6 s e cerca de 20 móveis 0,9 s, quase todos cópias da mesma IfcRepresentationMap. O custo é a triangulação local de polígonos côncavos (constrained_delaunay), repetida por instância.
CONTRATO:
1. `malha_direta.malha_mundo(el, escala=1.0, cache=None)`: `cache` é um dict opcional (compartilhado entre chamadas e threads). A triangulação LOCAL (vértices e triângulos antes das matrizes) de cada fonte de malha (IfcPolygonalFaceSet/IfcTriangulatedFaceSet, chave = id STEP da fonte) é calculada uma vez por cache; instâncias do mesmo IfcRepresentationMap com matrizes diferentes devolvem o resultado correto do mundo (igual ao núcleo) sem nova triangulação. Sem cache, o comportamento é o do T19g.
2. `silhueta.formas_do_mundo(f, elementos, threads)` cria um cache por chamada e processa os elementos suportados em ThreadPool (máx. `nucleos.limitar_threads(threads)` threads; 1 thread = sequencial). O resultado (ids, vértices, faces) é idêntico ao sequencial."""
from __future__ import annotations

import math
import threading

import numpy as np
import pytest
import s06_t07_aux as X
import test_s06_t19g_malha_direta_oraculo as G
from shapely import unary_union

import obim_geometria.malha_direta as M
import obim_geometria.silhueta as S


def _duas_instancias(f, pavs):
    """Duas instâncias do MESMO IfcRepresentationMap com matrizes diferentes."""
    a = G._elemento(f, pavs, G._mapeado(lambda f, rep: G._faceset(f), esc=2.0, giro90=True))
    mapa = a.Representation.Representations[0].Items[0].MappingSource
    b = G._elemento(f, pavs, G._mapeado(lambda f, rep: G._faceset(f), esc=1.0, giro90=False), x=30.0)
    rep = b.Representation.Representations[0]
    op = f.create_entity("IfcCartesianTransformationOperator3D", Axis1=G._dir(f, 1, 0, 0), Axis2=G._dir(f, 0, 1, 0),
                         LocalOrigin=G._pt(f, 3.0, -1.0, 0.25), Scale=1.5)
    rep.Items = [f.create_entity("IfcMappedItem", MappingSource=mapa, MappingTarget=op)]
    return a, b


def _conta_cdt(monkeypatch):
    n = []
    import shapely
    orig = shapely.constrained_delaunay_triangles
    monkeypatch.setattr(shapely, "constrained_delaunay_triangles", lambda *a, **k: n.append(1) or orig(*a, **k))
    return n


def test_fonte_compartilhada_e_triangulada_uma_vez_e_ambas_batem_com_o_nucleo(monkeypatch):
    f, pavs = X.estrutura("IFC4", n_pav=1)
    a, b = _duas_instancias(f, pavs)
    cache = {}
    n = _conta_cdt(monkeypatch)
    ma = M.malha_mundo(a, 1.0, cache)
    apos_a = len(n)
    mb = M.malha_mundo(b, 1.0, cache)
    assert apos_a > 0 and len(n) == apos_a, "a segunda instância da mesma fonte não pode triangular de novo"
    for el, m in ((a, ma), (b, mb)):
        v, t = m
        kv, kt = G._nucleo(el)
        assert np.allclose(np.unique(np.round(v, 6), axis=0), np.unique(np.round(kv, 6), axis=0), atol=1e-6)
        assert abs(G._area3d(v, t) - G._area3d(kv, kt)) <= 1e-6 * G._area3d(kv, kt)
        assert G._uniao_xy(v, t).symmetric_difference(G._uniao_xy(kv, kt)).area <= 1e-6 * max(1.0, G._uniao_xy(kv, kt).area)


def test_sem_cache_continua_igual_ao_t19g(monkeypatch):
    f, pavs = X.estrutura("IFC4", n_pav=1)
    a, b = _duas_instancias(f, pavs)
    n = _conta_cdt(monkeypatch)
    va, ta = M.malha_mundo(a, 1.0)
    vb, tb = M.malha_mundo(b, 1.0)
    assert len(n) >= 2, "sem cache cada chamada triangula"
    vc, tc = M.malha_mundo(a, 1.0, {})
    assert np.allclose(va, vc) and (ta == tc).all()


def test_cache_nao_mistura_fontes_diferentes():
    f, pavs = X.estrutura("IFC4", n_pav=1)
    a = G._elemento(f, pavs, lambda f, rep: G._faceset(f))
    b = G._elemento(f, pavs, lambda f, rep: G._triangulado(f), x=20.0)
    cache = {}
    for el in (a, b):
        v, t = M.malha_mundo(el, 1.0, cache)
        kv, kt = G._nucleo(el)
        assert abs(G._area3d(v, t) - G._area3d(kv, kt)) <= 1e-6 * G._area3d(kv, kt)


def test_formas_do_mundo_paralelo_igual_ao_sequencial_e_usa_varias_threads(monkeypatch):
    f, pavs = X.estrutura("IFC4", n_pav=1)
    els = []
    for k in range(6):
        e = G._elemento(f, pavs, G._mapeado(lambda f, rep: G._faceset(f), esc=1.0 + 0.1 * k, giro90=bool(k % 2)), x=10.0 * k)
        els.append(e)
    idents = set()
    orig = M.malha_mundo
    def espia(el, escala=1.0, cache=None):
        idents.add(threading.get_ident())
        import time; time.sleep(0.05)
        return orig(el, escala, cache)
    monkeypatch.setattr(M, "malha_mundo", espia)
    seq = S.formas_do_mundo(f, els, threads=1)
    assert len(idents) == 1
    idents.clear()
    par = S.formas_do_mundo(f, els, threads=4)
    assert len(idents) >= 2, "com threads=4 os elementos têm de ser lidos em mais de uma thread"
    assert sorted(seq) == sorted(par)
    for i in seq:
        assert np.allclose(np.asarray(seq[i].geometry.verts), np.asarray(par[i].geometry.verts)) and np.array_equal(np.asarray(seq[i].geometry.faces), np.asarray(par[i].geometry.faces))
