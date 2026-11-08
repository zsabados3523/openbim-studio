# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15n: caixas por pontos do face set (sem tesselar), op `caixas`.
Ref: docs/state/cards/F0-S06/F0-S06-T15n-caixas-rapidas.md. Referência = o próprio iterator (USE_WORLD_COORDS), tolerância 1e-6 m.
Face set puro (também via IfcMappedItem) NÃO pode passar pelo iterator nem por create_shape; o resto cai no iterator.
"""

from __future__ import annotations

import math

import sys

from pathlib import Path

import pytest

import ifcopenshell

import ifcopenshell.geom

import s06_t07_aux as X

from s05_conteudo_aux import exigir

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"

if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

from obim_geometria import local  # noqa: E402

TOL = 1e-6

FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]

TRIS = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]

def _cantos(dx, dy, dz):
    return [(0, 0, 0), (dx, 0, 0), (dx, dy, 0), (0, dy, 0), (0, 0, dz), (dx, 0, dz), (dx, dy, dz), (0, dy, dz)]

def _pt(f, c):
    return f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in c))

def _dir(f, *r):
    return f.create_entity("IfcDirection", DirectionRatios=tuple(float(v) for v in r))

def _item(f, tipo, pts):
    if tipo in ("poly", "tri"):
        lista = f.create_entity("IfcCartesianPointList3D", CoordList=[tuple(float(v) for v in p) for p in pts])
        if tipo == "tri":
            return f.create_entity("IfcTriangulatedFaceSet", Coordinates=lista, CoordIndex=[tuple(i + 1 for i in t) for t in TRIS], Closed=True)
        return f.create_entity("IfcPolygonalFaceSet", Coordinates=lista, Closed=True,
                               Faces=[f.create_entity("IfcIndexedPolygonalFace", CoordIndex=tuple(i + 1 for i in q)) for q in FACES])
    P = [_pt(f, p) for p in pts]
    faces = [f.create_entity("IfcFace", Bounds=[f.create_entity("IfcFaceOuterBound", Bound=f.create_entity(
        "IfcPolyLoop", Polygon=[P[i] for i in q]), Orientation=True)]) for q in FACES]
    if tipo == "fbsm":
        return f.create_entity("IfcFaceBasedSurfaceModel", FbsmFaces=[f.create_entity("IfcConnectedFaceSet", CfsFaces=faces)])
    if tipo == "sbsm":
        return f.create_entity("IfcShellBasedSurfaceModel", SbsmBoundary=[f.create_entity("IfcOpenShell", CfsFaces=faces)])
    return f.create_entity("IfcFacetedBrep", Outer=f.create_entity("IfcClosedShell", CfsFaces=faces))  # "brep": fora da lista, vai ao iterator

def _forma(f, itens, tipo="Tessellation"):
    ctx = f.by_type("IfcGeometricRepresentationContext")[0]
    return f.create_entity("IfcShapeRepresentation", ContextOfItems=ctx, RepresentationIdentifier="Body", RepresentationType=tipo, Items=itens)

def _coloca(f, e, pav, loc, eixo=(0, 0, 1), ref=(1, 0, 0)):
    e.ObjectPlacement = f.create_entity("IfcLocalPlacement", PlacementRelTo=pav.ObjectPlacement, RelativePlacement=f.create_entity(
        "IfcAxis2Placement3D", Location=_pt(f, loc), Axis=_dir(f, *eixo), RefDirection=_dir(f, *ref)))

def peca(f, pav, nome, tipo, loc, dims=(2.0, 1.0, 0.5), eixo=(0, 0, 1), ref=(1, 0, 0), extra=None, cls="IfcBuildingElementProxy"):
    """Peça com Body só de face set (tipo: poly, tri, fbsm, sbsm, brep), colocação relativa ao pavimento, girada/inclinada."""
    pts = _cantos(*dims) + ([extra] if extra else [])
    e = X.elemento(f, cls, nome)
    _coloca(f, e, pav, loc, eixo, ref)
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[_forma(f, [_item(f, tipo, pts)])])
    X.conter(f, pav, e)
    return e

def mapeada(f, pav, nome, mapa, loc, alvo, escala=1.0, ref=(1, 0, 0)):
    e = X.elemento(f, "IfcBuildingElementProxy", nome)
    _coloca(f, e, pav, loc, ref=ref)
    item = f.create_entity("IfcMappedItem", MappingSource=mapa, MappingTarget=f.create_entity(
        "IfcCartesianTransformationOperator3D", Axis1=_dir(f, 0, 1, 0), Axis2=_dir(f, -1, 0, 0), LocalOrigin=_pt(f, alvo), Scale=escala))
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[_forma(f, [item], "MappedRepresentation")])
    X.conter(f, pav, e)
    return e

def mapa_de(f, tipo, dims=(2.0, 1.0, 0.5)):
    return f.create_entity("IfcRepresentationMap", MappingOrigin=f.create_entity("IfcAxis2Placement3D", Location=_pt(f, (0.2, 0.1, 0.0))),
                           MappedRepresentation=_forma(f, [_item(f, tipo, _cantos(*dims))]))

def base(esq="IFC4"):
    exigir()
    return X.estrutura(esq, off=(12.0, -7.0), base=1.5)

def abrir(f, tmp_path):
    arq = tmp_path / "m.ifc"
    f.write(str(arq))
    return str(arq), ifcopenshell.open(str(arq))

def ped(arq, g, *nomes):
    els = [e for n in nomes for e in g.by_type("IfcProduct") if e.Name == n]
    return {"op": "caixas", "arquivo": arq, "threads": 1, "elementos": [[e.id(), e.GlobalId] for e in els]}

def ref_iterator(arq, ids):
    """Caixas pelo iterator real (mundo, metros), sem passar pelo código testado."""
    g = ifcopenshell.open(arq)
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    it = ifcopenshell.geom.iterator(s, g, 1, include=[g.by_id(i) for i in ids])
    out = {}
    if it.initialize():
        while True:
            sh = it.get()
            v = sh.geometry.verts
            out[int(sh.id)] = [min(v[0::3]), min(v[1::3]), min(v[2::3]), max(v[0::3]), max(v[1::3]), max(v[2::3])]
            if not it.next():
                break
    return out

class Espia:
    """Conta construções do iterator (e os ids pedidos) e chamadas a create_shape."""

    def __init__(self, mp):
        self.incluidos: list = []
        self.create_shape: list = []
        real_it, real_cs = ifcopenshell.geom.iterator, ifcopenshell.geom.create_shape

        def it(*a, **k):
            inc = k.get("include")
            self.incluidos.append(None if inc is None else {e.id() for e in inc})
            return real_it(*a, **k)

        def cs(*a, **k):
            el = a[1] if len(a) > 1 else k.get("element")
            self.create_shape.append(el.id() if el is not None else None)
            return real_cs(*a, **k)

        mp.setattr(ifcopenshell.geom, "iterator", it)
        mp.setattr(ifcopenshell.geom, "create_shape", cs)

    @property
    def ids_iterator(self) -> set:
        assert None not in self.incluidos, "iterator sem include (modelo todo)"
        return set().union(*self.incluidos) if self.incluidos else set()

def iguais(res, ref, ids):
    assert res["ok"] is True, res
    for i in ids:
        got = res["caixas_envolventes"][str(i)]
        assert len(got) == 6 and all(isinstance(v, float) and math.isfinite(v) for v in got)
        assert got == pytest.approx(ref[i], abs=TOL), (i, got, ref[i])

def _girado(f, pav, nome, tipo):
    return peca(f, pav, nome, tipo, (3.1, -1.3, 0.7), eixo=(0, 0.6, 0.8), ref=(0.8, 0.0, -0.6))

__all__ = ['Espia', 'FACES', 'GEOMETRIA', 'Path', 'TOL', 'TRIS', 'X', '_cantos', '_coloca', '_dir', '_forma', '_girado', '_item', '_pt', 'abrir', 'base', 'exigir', 'ifcopenshell', 'iguais', 'local', 'mapa_de', 'mapeada', 'math', 'peca', 'ped', 'pytest', 'ref_iterator', 'sys']
