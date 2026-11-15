# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silhueta 2D de peças pesadas (união dos triângulos projetados em XY)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import ifcopenshell.geom
import ifcopenshell.util.unit
import numpy as np
from obim_geometria import malha_direta, nucleos
from shapely import polygons, union_all

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


def formas_do_mundo(f, elementos, threads: int | None = None) -> dict:
    """Lê malhas diretas ou triangula `elementos` em coordenadas do mundo (`{id_step: forma}`)."""
    formas = {}
    try:
        elems = [el for el in (elementos or ()) if el is not None]
        if f is None or not elems:
            return formas
        try:
            escala = float(ifcopenshell.util.unit.calculate_unit_scale(f))
        except Exception:
            escala = 1.0
        restantes, vistos = [], set()
        for el in elems:
            eid = el.id()
            if eid in vistos:
                continue
            vistos.add(eid)
            malha = malha_direta.malha_mundo(el, escala)
            if malha is not None:
                verts, tris = malha
                if len(verts) and len(tris):
                    formas[eid] = malha_direta.FormaDireta(eid, verts, tris)
                    continue
            restantes.append(el)
        if not restantes:
            return formas
        cfg = ifcopenshell.geom.settings()
        cfg.set(cfg.USE_WORLD_COORDS, True)
        it = ifcopenshell.geom.iterator(cfg, f, nucleos.limitar_threads(threads), include=restantes)
        if it.initialize():
            while True:
                try:
                    sh = it.get()
                    geo = getattr(sh, "geometry", None)
                    if geo is not None and geo.verts and geo.faces:
                        formas[sh.id] = sh
                except Exception:
                    pass
                if not it.next():
                    break
    except Exception:
        pass
    return formas


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
        verts = np.asarray(geo.verts, dtype=float).reshape(-1, 3)
        tris = np.asarray(geo.faces, dtype=int).reshape(-1, 3)
        zmin = float(verts[:, 2].min()) if len(verts) else None
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


def _so_poligonos(geom):
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom if geom.area > _AREA_MIN else None
    if hasattr(geom, "geoms"):
        partes = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty and g.area > _AREA_MIN]
        if partes:
            u = union_all(partes)
            return u if not u.is_empty and u.geom_type in ("Polygon", "MultiPolygon") and u.area > _AREA_MIN else None
    return None


def uniao_triangulos_xy(verts, tris, threads: int | None = None):
    """União 2D (Polygon | MultiPolygon | None) dos triângulos projetados em XY."""
    n_threads = nucleos.limitar_threads(threads)
    try:
        v, t = np.asarray(verts, dtype=float), np.asarray(tris, dtype=int)
    except (TypeError, ValueError):
        return None
    if v.ndim != 2 or v.shape[0] == 0 or v.shape[1] < 2 or t.ndim != 2 or t.shape[0] == 0 or t.shape[1] != 3:
        return None
    t = t[(t >= 0).all(axis=1) & (t < v.shape[0]).all(axis=1)]
    if t.shape[0] == 0:
        return None
    tri_xy = v[:, :2][t]
    tri_xy = tri_xy[np.isfinite(tri_xy).all(axis=(1, 2))]
    if tri_xy.shape[0] == 0:
        return None
    d1, d2 = tri_xy[:, 1] - tri_xy[:, 0], tri_xy[:, 2] - tri_xy[:, 0]
    tri_xy = tri_xy[np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) > 2.0 * _AREA_MIN]
    if tri_xy.shape[0] == 0:
        return None
    tri_xy = tri_xy[np.argsort(tri_xy[:, :, 0].sum(axis=1))]
    try:
        pols = polygons(tri_xy)
        n_partes = min(len(pols), 2 * n_threads)
        if n_threads == 1 or len(pols) < 64 or n_partes <= 1:
            uniao = union_all(pols)
        else:
            with ThreadPoolExecutor(max_workers=n_threads) as ex:
                uniao = union_all(list(ex.map(union_all, np.array_split(pols, n_partes))))
    except Exception:
        return None
    return _so_poligonos(uniao)


def silhueta_xy(verts, tris, threads: int | None = None) -> list[list[tuple[float, float]]]:
    """Anéis (exterior e furos) da união 2D dos triângulos projetados em XY."""
    return _aneis(uniao_triangulos_xy(verts, tris, threads=threads))
