# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silhueta 2D de peças pesadas (união dos triângulos projetados em XY)."""
from __future__ import annotations

import ifcopenshell.geom
import numpy as np
from shapely import polygons, unary_union

LIMIAR_PADRAO = 40000
_AREA_MIN = 1e-12


def eh_pesada(n_faces: int, limiar: int = LIMIAR_PADRAO) -> bool:
    return n_faces > limiar


def _forma(x):
    if hasattr(x, "geometry"):
        return x
    cfg = ifcopenshell.geom.settings()
    cfg.set(cfg.USE_WORLD_COORDS, True)
    return ifcopenshell.geom.create_shape(cfg, x)


def _n_faces(forma) -> int:
    return len(forma.geometry.faces) // 3


def contar_faces(x) -> int:
    """Triângulos de um `entity_instance` IFC ou de uma forma de `create_shape` (0 sem geometria)."""
    try:
        return _n_faces(_forma(x))
    except Exception:
        return 0


def faces_e_silhueta(x, limiar: int = LIMIAR_PADRAO, z_corte: float | None = None):
    """(n_faces, aneis, zmin) numa única criação de forma; `aneis` None se não pesada ou inteira acima do corte."""
    try:
        forma = _forma(x)
        geo = forma.geometry
        n_faces = _n_faces(forma)
        if not eh_pesada(n_faces, limiar):
            return n_faces, None, None
        vs, fs = geo.verts, geo.faces
        verts = [(vs[k], vs[k + 1], vs[k + 2]) for k in range(0, len(vs), 3)]
        tris = [(fs[k], fs[k + 1], fs[k + 2]) for k in range(0, len(fs), 3)]
        zmin = min((v[2] for v in verts), default=None)
        if z_corte is not None and zmin is not None and zmin > z_corte:
            return n_faces, None, zmin
        return n_faces, silhueta_xy(verts, tris), zmin
    except Exception:
        return 0, None, None


def _aneis(geom) -> list[list[tuple[float, float]]]:
    if geom is None or geom.is_empty:
        return []
    tipo = geom.geom_type
    if tipo == "Polygon":
        aneis = [list(geom.exterior.coords)[:-1]]
        aneis.extend(list(anel.coords)[:-1] for anel in geom.interiors)
        return aneis
    if hasattr(geom, "geoms"):
        saida = []
        for parte in geom.geoms:
            saida.extend(_aneis(parte))
        return saida
    return []


def silhueta_xy(verts, tris) -> list[list[tuple[float, float]]]:
    """Aneis (exterior e furos) da união 2D dos triângulos projetados em XY."""
    poligonos = []
    for a, b, c in tris:
        try:
            pts = [
                (float(verts[a][0]), float(verts[a][1])),
                (float(verts[b][0]), float(verts[b][1])),
                (float(verts[c][0]), float(verts[c][1])),
            ]
        except (IndexError, TypeError, ValueError):
            continue
        try:
            if not np.isfinite(np.asarray(pts, dtype=float)).all():
                continue
        except (TypeError, ValueError):
            continue
        try:
            pol = polygons(pts)
        except Exception:
            continue
        if pol.is_empty or abs(pol.area) <= _AREA_MIN:
            continue
        poligonos.append(pol)
    if not poligonos:
        return []
    try:
        uniao = unary_union(poligonos)
    except Exception:
        return []
    return _aneis(uniao)
