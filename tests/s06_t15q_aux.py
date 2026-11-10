# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T15q: móvel em L (forma não retangular) em modelo pequeno, e leitura dos pontos do SVG."""
from __future__ import annotations

import re

import s06_t07_aux as X
from s06_t15i_aux import *  # noqa: F401,F403
from s06_t15i_aux import _criar_corte_xyz

L2 = [(0.0, 0.0), (2.0, 0.0), (2.0, 0.5), (0.5, 0.5), (0.5, 2.0), (0.0, 2.0)]  # L em 2 x 2 m, área 1,75 de 4,0

def movel_l(f, nome, loc, plano="XY", prof=1.0, cls="IfcFurniture"):
    """Móvel com perfil em L extrudado. plano XY: L na planta, altura `prof`. plano XZ: L na elevação (vista do corte), espessura `prof` em Y."""
    pts = [f.create_entity("IfcCartesianPoint", Coordinates=p) for p in L2 + [L2[0]]]
    perfil = f.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=f.create_entity("IfcPolyline", Points=pts))
    if plano == "XY":
        eixo = f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0, 0, 0))
    else:
        eixo = f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0, 0, 0), Axis=f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0)),
                               RefDirection=f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)))
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Position=eixo, Depth=prof,
                             ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=f.by_type("IfcGeometricRepresentationContext")[0],
                            RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    e = X.elemento(f, cls, nome)
    e.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, *loc)))
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    return e

def modelo_l(plano="XY", cls="IfcFurniture"):
    """Retorna (arquivo, gid_planta, gid_corte, móvel). Planta: L em x 1..3, y 1..3, z 0..1. Corte: L em x 1..3, z 0..2, y 1..1.6."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    movel = movel_l(f, "MovelL", (1.0, 1.0, 0.0) if plano == "XY" else (1.0, 1.6, 0.0), plano, 1.0 if plano == "XY" else 0.6, cls)
    X.conter(f, pavs[0], movel)
    return f, X.vista(f, "PLANTA", pavs[0], nome="PlantaL"), _criar_corte_xyz(f, "CorteL", 0.0, 6.0, 0.0, 4.0, 0.0, 3.5), movel

def vertices_svg(svg, nd=2):
    """Vértices distintos (arredondados) de todos os <path d=...> do corpo do SVG (fora do <style>). Só o móvel está no modelo."""
    corpo = svg.split("</style>", 1)[-1]
    pts = set()
    for d in re.findall(r'<path\b[^>]*\bd=["\']([^"\']+)["\']', corpo):
        n = [float(v) for v in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", d)]
        pts |= {(round(x, nd), round(y, nd)) for x, y in zip(n[0::2], n[1::2])}
    return pts

def canto_da_caixa_vazio(pts, nd=2):
    """True se algum canto da caixa envolvente dos vértices não é vértice (forma não retangular, como o L)."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cantos = {(round(a, nd), round(b, nd)) for a in (min(xs), max(xs)) for b in (min(ys), max(ys))}
    return not cantos <= pts

def caixa_2d(svg, guid):
    """True se há <g> do guid com um <path> retangular (a caixa 2D)."""
    return re.search(rf'<g\b[^>]*\bifc:guid=["\']{re.escape(guid)}["\']', svg) is not None
