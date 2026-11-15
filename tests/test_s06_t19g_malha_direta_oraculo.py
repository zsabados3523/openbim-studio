# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19g: malha do mundo lida direto de IfcPolygonalFaceSet / IfcTriangulatedFaceSet, sem o núcleo geométrico (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19g-malha-direta.md. Não editar nesta tarefa.
Medido (casarão, SUBSOLO REBAIXADO): `formas_do_mundo` leva 79 s no iterador; a Lilie (202 mil triângulos) custa 70 s no núcleo e 1,1 s lendo as coordenadas direto (bbox idêntico, diferença 1e-15). Todas as peças pesadas são malhas prontas (mapeadas).
CONTRATO:
1. `obim_geometria.malha_direta.malha_mundo(el, escala=1.0)` -> `(verts, tris)` (np.ndarray (n,3) float e (m,3) int, em METROS no mundo: `escala` = metros por unidade do arquivo, `ifcopenshell.util.unit.calculate_unit_scale`)
   ou None quando o corpo não é só malha suportada (qualquer item que não seja IfcPolygonalFaceSet/IfcTriangulatedFaceSet, direto ou via IfcMappedItem aninhado) ou em qualquer erro. Cadeia: posicionamento do produto x operador do IfcMappedItem
   (escala uniforme e rotação) x coordenadas. Faces: triângulo vale como é; polígono convexo vira leque; polígono côncavo ou com furos (IfcIndexedPolygonalFaceWithVoids) é triangulado no plano da face (Newell) sem cobrir o furo
   (sugestão: `shapely.constrained_delaunay_triangles` no plano local); se não conseguir -> None para o elemento todo. A área total e a união 2D em XY batem com as do núcleo.
2. `malha_direta.FormaDireta`: `.id` (id STEP) e `.geometry` com `.verts` e `.faces` como arrays 1-D planos (como as formas do iterador).
3. `silhueta.formas_do_mundo(f, elementos, threads=None)`: para cada elemento tenta `malha_mundo(el, escala_do_arquivo)` primeiro; só os que devolvem None vão ao iterador (`include=` só eles; nenhum -> nem cria o iterador).
4. `silhueta.faces_e_silhueta` aceita a forma direta (sem laços Python por triângulo) e devolve a mesma silhueta que o núcleo (área igual)."""
from __future__ import annotations

import math

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pytest
import shapely
from shapely import Polygon, unary_union
import s06_t07_aux as X

import obim_geometria.silhueta as S

try:
    import obim_geometria.malha_direta as M
except ImportError:  # vermelho até a implementação
    M = None


def _m():
    if M is None:
        pytest.fail("módulo obim_geometria.malha_direta inexistente (a implementar na T19g)")
    return M


def _pt(f, *c):
    return f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in c))


def _dir(f, *c):
    return f.create_entity("IfcDirection", DirectionRatios=tuple(float(v) for v in c))


# polígonos no plano local (x, y): triângulo, quadrado convexo, "L" côncavo, quadrado com furo, estrela côncava de 12 pontos
def _poligonos_planos():
    tri = [(0, 0), (1, 0), (0, 1)]
    quad = [(2, 0), (3, 0), (3, 1), (2, 1)]
    ele = [(4, 0), (6, 0), (6, 1), (5, 1), (5, 3), (4, 3)]
    ext = [(7, 0), (10, 0), (10, 3), (7, 3)]
    furo = [(8, 1), (8, 2), (9, 2), (9, 1)]
    est = []
    for k in range(12):
        r = 1.5 if k % 2 == 0 else 0.6
        a = 2 * math.pi * k / 12
        est.append((12 + r * math.cos(a), 1.5 + r * math.sin(a)))
    return [(tri, []), (quad, []), (ele, []), (ext, [furo]), (est, [])]


def _faceset(f, plano="xy"):
    pts, faces = [], []
    def idx(p3):
        pts.append(tuple(float(c) for c in p3))
        return len(pts)
    for outer, furos in _poligonos_planos():
        mk = (lambda p: (p[0], p[1], 0.0)) if plano == "xy" else (lambda p: (p[0], 0.7, p[1]))
        co = [idx(mk(p)) for p in outer]
        if furos:
            inner = [[idx(mk(p)) for p in h] for h in furos]
            faces.append(f.create_entity("IfcIndexedPolygonalFaceWithVoids", CoordIndex=co, InnerCoordIndices=inner))
        else:
            faces.append(f.create_entity("IfcIndexedPolygonalFace", CoordIndex=co))
    lista = f.create_entity("IfcCartesianPointList3D", CoordList=pts)
    return f.create_entity("IfcPolygonalFaceSet", Coordinates=lista, Closed=False, Faces=faces)


def _triangulado(f):
    lista = f.create_entity("IfcCartesianPointList3D", CoordList=[(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 1.5)])
    return f.create_entity("IfcTriangulatedFaceSet", Coordinates=lista, Closed=True, CoordIndex=[(1, 2, 3), (1, 2, 4), (2, 3, 4), (1, 3, 4)])


def _elemento(f, pavs, item_fn, x=1.0, y=2.0, z=0.5, rot=0.5235987755982988):  # rot = 30 graus em Z
    e = X.caixa(f, "IfcBuildingElementProxy", "E", x, y, z, 1, 1, 1)
    X.conter(f, pavs[0], e)
    pl = e.ObjectPlacement.RelativePlacement
    pl.RefDirection = _dir(f, math.cos(rot), math.sin(rot), 0.0)
    rep = e.Representation.Representations[0]
    rep.Items = [item_fn(f, rep)]
    rep.RepresentationType = "Tessellation"
    return e


def _mapeado(inner_fn, esc=2.0, giro90=True, origem=(0.5, -0.25, 0.1)):
    def fn(f, rep):
        fonte = f.create_entity("IfcShapeRepresentation", ContextOfItems=rep.ContextOfItems, RepresentationIdentifier="Body", RepresentationType="Tessellation", Items=[inner_fn(f, rep)])
        mapa = f.create_entity("IfcRepresentationMap", MappingOrigin=f.create_entity("IfcAxis2Placement3D", Location=_pt(f, 0, 0, 0)), MappedRepresentation=fonte)
        a1, a2 = ((0, 1, 0), (-1, 0, 0)) if giro90 else ((1, 0, 0), (0, 1, 0))
        op = f.create_entity("IfcCartesianTransformationOperator3D", Axis1=_dir(f, *a1), Axis2=_dir(f, *a2), LocalOrigin=_pt(f, *origem), Scale=esc)
        return f.create_entity("IfcMappedItem", MappingSource=mapa, MappingTarget=op)
    return fn


def _nucleo(el):
    cfg = ifcopenshell.geom.settings()
    cfg.set(cfg.USE_WORLD_COORDS, True)
    g = ifcopenshell.geom.create_shape(cfg, el).geometry
    return np.asarray(g.verts, float).reshape(-1, 3), np.asarray(g.faces, int).reshape(-1, 3)


def _area3d(v, t):
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum()


def _uniao_xy(v, t):
    tri = v[:, :2][t]
    det = np.abs((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1]) - (tri[:, 1, 1] - tri[:, 0, 1]) * (tri[:, 2, 0] - tri[:, 0, 0]))
    return unary_union(list(shapely.polygons(tri[det > 1e-12])))


def _confere(el, escala=1.0):
    m = _m().malha_mundo(el, escala)
    assert m is not None, "malha suportada devolveu None"
    v, t = m
    kv, kt = _nucleo(el)
    assert v.ndim == 2 and v.shape[1] == 3 and t.ndim == 2 and t.shape[1] == 3 and t.min() >= 0 and t.max() < len(v)
    assert np.allclose(np.unique(np.round(v, 6), axis=0), np.unique(np.round(kv, 6), axis=0), atol=1e-6), "vértices do mundo diferem do núcleo"
    assert abs(_area3d(v, t) - _area3d(kv, kt)) <= 1e-6 * _area3d(kv, kt)
    ud, uk = _uniao_xy(v, t), _uniao_xy(kv, kt)
    assert ud.symmetric_difference(uk).area <= 1e-6 * max(1.0, uk.area), "união 2D em XY difere (furo coberto ou polígono côncavo mal triangulado)"


@pytest.mark.parametrize("plano", ["xy", "xz"])
def test_faceset_poligonal_com_concavo_e_furo_igual_ao_nucleo(plano):
    f, pavs = X.estrutura("IFC4", n_pav=1)
    _confere(_elemento(f, pavs, lambda f, rep: _faceset(f, plano)))


def test_faceset_triangulado_igual_ao_nucleo():
    f, pavs = X.estrutura("IFC4", n_pav=1)
    _confere(_elemento(f, pavs, lambda f, rep: _triangulado(f)))


@pytest.mark.parametrize("giro90", [True, False], ids=["giro90", "sem_giro"])
def test_mapeado_com_escala_e_giro(giro90):
    f, pavs = X.estrutura("IFC4", n_pav=1)
    _confere(_elemento(f, pavs, _mapeado(lambda f, rep: _faceset(f), esc=2.0, giro90=giro90)))


def test_mapeado_aninhado():
    f, pavs = X.estrutura("IFC4", n_pav=1)
    interno = _mapeado(lambda f, rep: _triangulado(f), esc=1.5, giro90=False, origem=(0.2, 0.3, 0.0))
    _confere(_elemento(f, pavs, _mapeado(lambda f, rep: interno(f, rep), esc=2.0, giro90=True)))


def test_unidade_milimetro():
    f, pavs = X.estrutura("IFC4", n_pav=1)
    e = _elemento(f, pavs, lambda f, rep: _faceset(f))
    X.em_milimetros(f)
    import ifcopenshell.util.unit as U
    esc = U.calculate_unit_scale(f)
    assert abs(esc - 0.001) < 1e-12
    _confere(e, esc)


def test_corpo_extrudado_nao_e_suportado():
    f, pavs = X.estrutura("IFC4", n_pav=1)
    e = X.caixa(f, "IfcBuildingElementProxy", "C", 0, 0, 0, 1, 1, 1)
    X.conter(f, pavs[0], e)
    assert _m().malha_mundo(e, 1.0) is None


def test_formas_do_mundo_direto_primeiro_iterador_so_para_o_resto(monkeypatch):
    f, pavs = X.estrutura("IFC4", n_pav=1)
    a = _elemento(f, pavs, lambda f, rep: _faceset(f))
    b = _elemento(f, pavs, lambda f, rep: _triangulado(f), x=20.0)
    c = X.caixa(f, "IfcBuildingElementProxy", "C", 40, 0, 0, 1, 1, 1)
    X.conter(f, pavs[0], c)
    incl = []
    orig = ifcopenshell.geom.iterator
    monkeypatch.setattr(ifcopenshell.geom, "iterator", lambda cfg, ff, n, include=None, **k: incl.append([e.id() for e in include]) or orig(cfg, ff, n, include=include, **k))
    formas = S.formas_do_mundo(f, [a, b, c], threads=1)
    assert sorted(formas) == sorted([a.id(), b.id(), c.id()]) and incl == [[c.id()]]
    for el in (a, b):
        g = formas[el.id()].geometry
        assert np.asarray(g.verts).ndim == 1 and len(g.verts) % 3 == 0 and len(g.faces) % 3 == 0 and len(g.faces) > 0
    # só direto: nenhum iterador
    incl.clear()
    S.formas_do_mundo(f, [a, b], threads=1)
    assert incl == []


def test_faces_e_silhueta_com_forma_direta_igual_ao_nucleo():
    f, pavs = X.estrutura("IFC4", n_pav=1)
    e = _elemento(f, pavs, lambda f, rep: _faceset(f))
    forma = S.formas_do_mundo(f, [e], threads=1)[e.id()]
    n_d, aneis_d, zmin_d = S.faces_e_silhueta(forma, 1)
    n_k, aneis_k, zmin_k = S.faces_e_silhueta(e, 1)
    assert aneis_d and aneis_k and abs(zmin_d - zmin_k) < 1e-9
    ud = unary_union([Polygon(a) for a in aneis_d]); uk = unary_union([Polygon(a) for a in aneis_k])
    assert ud.symmetric_difference(uk).area <= 1e-6 * max(1.0, uk.area)
