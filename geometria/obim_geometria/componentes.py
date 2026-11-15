# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agrupamento de elementos por componentes conexos da pegada 2D real (XY)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import ifcopenshell
import ifcopenshell.geom
import numpy as np
from obim_geometria import nucleos
from shapely import STRtree, polygons, unary_union

FOLGA = 0.002
_AREA_MIN = 1e-12


def pegada_xy(verts, tris):
    """União 2D (Polygon | MultiPolygon | None) dos triângulos projetados em XY, sem folga."""
    try:
        v = np.asarray(verts, dtype=float)
        t = np.asarray(tris, dtype=int)
    except (TypeError, ValueError):
        return None
    if v.ndim != 2 or v.shape[0] == 0 or v.shape[1] < 2 or t.ndim != 2 or t.shape[0] == 0 or t.shape[1] != 3:
        return None
    val = (t >= 0).all(axis=1) & (t < v.shape[0]).all(axis=1)
    t = t[val]
    if t.shape[0] == 0:
        return None
    tri_xy = v[:, :2][t]
    tri_xy = tri_xy[np.isfinite(tri_xy).all(axis=(1, 2))]
    if tri_xy.shape[0] == 0:
        return None
    dx1 = tri_xy[:, 1, 0] - tri_xy[:, 0, 0]
    dy1 = tri_xy[:, 1, 1] - tri_xy[:, 0, 1]
    dx2 = tri_xy[:, 2, 0] - tri_xy[:, 0, 0]
    dy2 = tri_xy[:, 2, 1] - tri_xy[:, 0, 1]
    tri_xy = tri_xy[np.abs(dx1 * dy2 - dy1 * dx2) > 2.0 * _AREA_MIN]
    if tri_xy.shape[0] == 0:
        return None
    try:
        uniao = unary_union(polygons(tri_xy))
    except Exception:
        return None
    if uniao is None or uniao.is_empty:
        return None
    if uniao.geom_type in ("Polygon", "MultiPolygon"):
        return uniao if uniao.area > _AREA_MIN else None
    if hasattr(uniao, "geoms"):
        partes = [
            g for g in uniao.geoms
            if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty and g.area > _AREA_MIN
        ]
        if not partes:
            return None
        u = unary_union(partes)
        return u if not u.is_empty and u.geom_type in ("Polygon", "MultiPolygon") and u.area > _AREA_MIN else None
    return None


def agrupar(pegadas, folga: float = FOLGA) -> list[list[int]]:
    """Componentes conexos de `pegadas` (distância <= `folga`); saída determinística por menor índice."""
    n = len(pegadas)
    if n == 0:
        return []
    pai = list(range(n))

    def achar(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def unir(a: int, b: int) -> None:
        ra, rb = achar(a), achar(b)
        if ra != rb:
            if ra < rb:
                pai[rb] = ra
            else:
                pai[ra] = rb

    validos = [(i, g) for i, g in enumerate(pegadas) if g is not None and not g.is_empty]
    if len(validos) >= 2:
        geoms = [g for _, g in validos]
        pares = STRtree(geoms).query(geoms, predicate="dwithin", distance=float(folga))
        for a, b in zip(pares[0].tolist(), pares[1].tolist()):
            if a < b:
                unir(validos[a][0], validos[b][0])

    grupos: dict[int, list[int]] = {}
    for i in range(n):
        grupos.setdefault(achar(i), []).append(i)
    return sorted(grupos.values(), key=lambda g: g[0])


def _pegada_da_forma(sh):
    """Calcula a pegada 2D de uma forma já triangulada."""
    try:
        geo = sh.geometry
        if geo.verts and geo.faces:
            return pegada_xy(
                np.asarray(geo.verts, dtype=float).reshape(-1, 3),
                np.asarray(geo.faces, dtype=int).reshape(-1, 3),
            )
    except Exception:
        pass
    return None


def dividir_elementos(
    arquivo, elementos, folga: float = FOLGA, threads: int | None = None, formas: dict | None = None
) -> list[list]:
    """Agrupa `elementos` (`[id_step, guid]`) pela pegada XY no mundo, mantendo a ordem original."""
    elems = [list(e) for e in elementos]
    if not elems:
        return []
    if len(elems) == 1:
        return [elems]
    formas_uso = dict(formas) if isinstance(formas, dict) else {}
    faltam_ids = list(dict.fromkeys(
        id_step for id_step, _guid in elems if formas_uso.get(id_step) is None
    ))
    if faltam_ids:
        f = ifcopenshell.open(arquivo)
        cfg = ifcopenshell.geom.settings()
        cfg.set(cfg.USE_WORLD_COORDS, True)
        incl = []
        for id_step in faltam_ids:
            try:
                el = f.by_id(id_step)
                if el is not None and not el.is_a("IfcOpeningElement"):
                    incl.append(el)
            except Exception:
                pass
        try:
            if incl:
                it = ifcopenshell.geom.iterator(cfg, f, nucleos.limitar_threads(threads), include=incl)
                if it.initialize():
                    while True:
                        try:
                            sh = it.get()
                            geo = sh.geometry
                            if geo.verts and geo.faces:
                                formas_uso[sh.id] = sh
                        except Exception:
                            pass
                        if not it.next():
                            break
        except Exception:
            pass
    pares = [
        (id_step, formas_uso[id_step])
        for id_step in dict.fromkeys(i for i, _guid in elems)
        if formas_uso.get(id_step) is not None
    ]
    peg_por_id = {}
    if pares:
        with ThreadPoolExecutor(max_workers=nucleos.limitar_threads(threads)) as ex:
            for (id_step, _sh), peg in zip(pares, ex.map(_pegada_da_forma, (sh for _, sh in pares))):
                if peg is not None:
                    peg_por_id[id_step] = peg
    pegadas = [peg_por_id.get(id_step) for id_step, _guid in elems]
    return [[elems[i] for i in g] for g in agrupar(pegadas, folga=folga)]
