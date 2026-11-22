# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de planta pelo cache de geometria (T24c, ADR-010 P3)."""
from __future__ import annotations

import html
import math
import time

import numpy as np

from obim_geometria import (
    aneis,
    corte_plano,
    nucleos,
    oclusores,
    recorte,
    visibilidade,
)


_DELTAS_PLANO = (1e-5, -1e-5, 3.7e-5, -3.7e-5)


def _eps_plano(z_val: float) -> float:
    return max(1e-9, 1e-12 * max(1.0, abs(z_val)))


def _area_estavel(pts: np.ndarray) -> float:
    """Area com sinal (shoelace) transladada pelo primeiro ponto para evitar cancelamento float64."""
    arr = np.asarray(pts, dtype=np.float64)
    if len(arr) < 3:
        return 0.0
    x = arr[:, 0] - arr[0, 0]
    y = arr[:, 1] - arr[0, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]) + x[-1] * y[0] - x[0] * y[-1])


def _fmt6(v: float) -> str:
    """Formata coordenada com 6 casas decimais, normalizando -0.0 para 0.0."""
    return f"{round(float(v), 6) + 0.0:.6f}"


def _validar_malha(verts_raw, tris_raw) -> tuple[np.ndarray, np.ndarray] | None:
    """Valida malha (N,3) float64 finita e (M,3) int dentro dos limites."""
    try:
        v = np.asarray(verts_raw, dtype=np.float64)
        t_raw = np.asarray(tris_raw)
    except (TypeError, ValueError):
        return None
    if v.ndim != 2 or v.shape[1] != 3 or len(v) == 0:
        return None
    if t_raw.ndim != 2 or t_raw.shape[1] != 3 or len(t_raw) == 0:
        return None
    if not np.issubdtype(t_raw.dtype, np.integer):
        return None
    t = t_raw.astype(np.int64, copy=False)
    if int(t.min()) < 0 or int(t.max()) >= len(v):
        return None
    if not np.isfinite(v).all() or float(np.abs(v).max()) > 1e12:
        return None
    return v, t


def _anel_para_d(
    anel: np.ndarray,
    xs: list[float],
    ys: list[float],
    ox: float = 0.0,
    oy: float = 0.0,
) -> str | None:
    """Converte anel 2D em subpath SVG `M ... L ...` sem `Z` (eixo Y invertido)."""
    pts = np.asarray(anel, dtype=np.float64)
    if pts.ndim != 2 or len(pts) < 3 or pts.shape[1] < 2:
        return None
    coords_loc = [(float(p[0]), float(p[1])) for p in pts]
    if abs(coords_loc[0][0] - coords_loc[-1][0]) > 1e-12 or abs(coords_loc[0][1] - coords_loc[-1][1]) > 1e-12:
        coords_loc.append(coords_loc[0])
    coords = [(x + ox, -(y + oy)) for x, y in coords_loc]
    for x, y in coords:
        xs.append(x)
        ys.append(y)
    cmds = [f"M {_fmt6(coords[0][0])},{_fmt6(coords[0][1])}"]
    cmds.extend(f"L {_fmt6(x)},{_fmt6(y)}" for x, y in coords[1:])
    return " ".join(cmds)


def _poli_para_d(
    poli: np.ndarray,
    xs: list[float],
    ys: list[float],
    ox: float = 0.0,
    oy: float = 0.0,
) -> str | None:
    """Converte polilinha 2D em path SVG `M ... L ...` sem `Z` (eixo Y invertido)."""
    pts = np.asarray(poli, dtype=np.float64)
    if pts.ndim != 2 or len(pts) < 2 or pts.shape[1] < 2:
        return None
    coords = [(float(p[0]) + ox, -(float(p[1]) + oy)) for p in pts]
    for x, y in coords:
        xs.append(x)
        ys.append(y)
    cmds = [f"M {_fmt6(coords[0][0])},{_fmt6(coords[0][1])}"]
    cmds.extend(f"L {_fmt6(x)},{_fmt6(y)}" for x, y in coords[1:])
    return " ".join(cmds)


def _montar_svg(
    pav_guid: str,
    pecas_secao: list[tuple[str, str, list[np.ndarray], list[np.ndarray], float, float]],
    pols_proj: list[np.ndarray],
    *,
    ox: float = 0.0,
    oy: float = 0.0,
) -> tuple[str, int]:
    """Monta SVG deterministico compativel com `estilo.aplicar_estilo`."""
    xs: list[float] = []
    ys: list[float] = []
    partes_secao: list[str] = []
    n_paths = 0

    for gid, classe, fechados, abertos, px, py in pecas_secao:
        subpaths: list[str] = []
        for anel in fechados:
            sub = _anel_para_d(anel, xs, ys, ox=px, oy=py)
            if sub:
                subpaths.append(sub)
        for cadeia in abertos:
            sub = _poli_para_d(cadeia, xs, ys, ox=px, oy=py)
            if sub:
                subpaths.append(sub)
        if not subpaths:
            continue
        cls_esc = html.escape(classe, quote=True)
        gid_esc = html.escape(gid, quote=True)
        d_attr = " ".join(subpaths)
        partes_secao.append(f'<g class="{cls_esc}" ifc:guid="{gid_esc}"><path d="{d_attr}"/></g>')
        n_paths += 1

    proj_paths: list[str] = []
    for poli in pols_proj:
        d_proj = _poli_para_d(poli, xs, ys, ox=ox, oy=oy)
        if d_proj:
            proj_paths.append(f'<path d="{d_proj}"/>')
            n_paths += 1

    if xs and ys:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        vb = f"{_fmt6(min_x)} {_fmt6(min_y)} {_fmt6(max_x - min_x)} {_fmt6(max_y - min_y)}"
    else:
        vb = "0 0 1 1"

    pav_esc = html.escape(pav_guid, quote=True)
    linhas = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xmlns:ifc="http://www.ifcopenshell.org/ns" viewBox="{vb}">',
        f'<g class="IfcBuildingStorey" ifc:guid="{pav_esc}">',
        *partes_secao,
    ]
    if proj_paths:
        linhas.append('<g class="projection">')
        linhas.extend(proj_paths)
        linhas.append("</g>")
    linhas.append("</g>")
    linhas.append("</svg>")
    return "\n".join(linhas), n_paths


