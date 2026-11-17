# SPDX-License-Identifier: AGPL-3.0-or-later
"""Selecao de aneis oclusores a partir das demais pecas do pavimento."""
from __future__ import annotations

import math

import numpy as np

from obim_geometria.aneis import _area, _ponto_no_anel_arr, aneis_de_segmentos
from obim_geometria.corte_plano import cortar_malha_no_plano

_EPS_PLANO, _EPS_DIST, _TETO_PONTOS, _CHUNK = 1e-9, 1e-12, 80000, 512


def _validar_peca(peca) -> tuple[bool, tuple[np.ndarray, np.ndarray] | None]:
    """Valida (verts, tris). Retorna (True, None) se vazia e (False, None) se invalida."""
    try:
        verts, tris = peca
        v, t_raw = np.asarray(verts, dtype=np.float64), np.asarray(tris)
    except (TypeError, ValueError):
        return False, None
    if v.ndim != 2 or v.shape[1] != 3 or t_raw.ndim != 2 or t_raw.shape[1] != 3 or not np.issubdtype(t_raw.dtype, np.integer):
        return False, None
    if len(v) > 0 and (not np.isfinite(v).all() or float(np.abs(v).max()) > 1e12):
        return False, None
    if len(t_raw) == 0:
        return True, None
    t = t_raw.astype(np.int64, copy=False)
    return (False, None) if len(v) == 0 or int(t.min()) < 0 or int(t.max()) >= len(v) else (True, (v, t))

def _prep_anel(anel: np.ndarray):
    """Pre-calcula caixa, arestas e inclinacoes do anel para consultas vetorizadas."""
    x1, y1 = anel[:, 0], anel[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    ex, ey = x2 - x1, y2 - y1
    bb = (float(x1.min()), float(y1.min()), float(x1.max()), float(y1.max()))
    el2 = np.maximum(ex * ex + ey * ey, 1e-30)
    slope = np.divide(ex, ey, out=np.zeros_like(ex), where=ey != 0.0)
    return bb, x1, y1, x2, y2, ex, ey, el2, np.minimum(x1, x2), np.maximum(x1, x2), np.minimum(y1, y2), np.maximum(y1, y2), slope

def _agrupar_aneis(fechados: list[np.ndarray]):
    """Agrupa aneis fechados: cada furo vai ao menor anel externo que o contem."""
    exts, furos = [], []
    for anel in fechados:
        area = _area(anel)
        if abs(area) <= _EPS_DIST:
            return None
        prep = _prep_anel(anel)
        (exts.append((area, prep, [anel], [prep])) if area > 0.0 else furos.append((-area, prep, anel)))
    for abs_area, fprep, furo in furos:
        fbb = fprep[0]
        px, py = 0.5 * (float(furo[0, 0]) + float(furo[1, 0])), 0.5 * (float(furo[0, 1]) + float(furo[1, 1]))
        cands = [
            c for c in exts
            if c[0] > abs_area and c[1][0][0] <= fbb[0] + _EPS_PLANO and c[1][0][2] >= fbb[2] - _EPS_PLANO
            and c[1][0][1] <= fbb[1] + _EPS_PLANO and c[1][0][3] >= fbb[3] - _EPS_PLANO
            and _ponto_no_anel_arr(px, py, c[1][1], c[1][2], c[1][3], c[1][4])
        ]
        if not cands:
            return None
        pai = min(cands, key=lambda c: c[0])
        pai[2].append(furo)
        pai[3].append(fprep)
    return [(rings, preps) for _, _, rings, preps in exts]

def _testar_anel(pts: np.ndarray, prep, td: float | None = None, td2: float = 0.0) -> np.ndarray:
    """Testa vetorizadamente por blocos se pontos estao perto (td != None) ou dentro do anel."""
    bb, x1, y1, _, y2, ex, ey, el2, ex0, ex1, ey0, ey1, slope = prep
    mrg = 0.0 if td is None else td
    px, py = pts[:, 0], pts[:, 1]
    idx = np.flatnonzero((px >= bb[0] - mrg) & (px <= bb[2] + mrg) & (py >= bb[1] - mrg) & (py <= bb[3] + mrg))
    out = np.zeros(len(pts), dtype=bool)
    for s in range(0, len(idx), _CHUNK):
        sl = idx[s:s + _CHUNK]
        cx, cy = px[sl, None], py[sl, None]
        if td is not None:
            m = (ex1 >= float(cx.min()) - td) & (ex0 <= float(cx.max()) + td) & (ey1 >= float(cy[0, 0]) - td) & (ey0 <= float(cy[-1, 0]) + td)
            if np.any(m):
                dxp, dyp, exm, eym = cx - x1[m], cy - y1[m], ex[m], ey[m]
                u = np.clip((dxp * exm + dyp * eym) / el2[m], 0.0, 1.0)
                out[sl] = np.min((dxp - u * exm) ** 2 + (dyp - u * eym) ** 2, axis=1) <= td2
        else:
            m = (ex1 >= float(cx.min()) - _EPS_PLANO) & (ey1 > float(cy[0, 0])) & (ey0 <= float(cy[-1, 0]))
            if np.any(m):
                y1m = y1[m]
                out[sl] = (np.count_nonzero(((y1m > cy) != (y2[m] > cy)) & (cx < x1[m] + (cy - y1m) * slope[m]), axis=1) & 1) == 1
    return out

def _pontos_no_grupo(pts: np.ndarray, preps: list[tuple], td: float, td2: float) -> np.ndarray:
    """Mascara dos pontos dentro do externo (fora dos furos) ou a distancia <= td de alguma borda."""
    ebb, px, py = preps[0][0], pts[:, 0], pts[:, 1]
    idx = np.flatnonzero((px >= ebb[0] - td) & (px <= ebb[2] + td) & (py >= ebb[1] - td) & (py <= ebb[3] + td))
    out = np.zeros(len(pts), dtype=bool)
    if len(idx) == 0:
        return out
    sub, cov = pts[idx], np.zeros(len(idx), dtype=bool)
    for prep in preps:
        if not np.all(cov):
            cov[~cov] |= _testar_anel(sub[~cov], prep, td, td2)
    if not np.all(cov):
        rest = np.flatnonzero(~cov)
        in_idx = rest[_testar_anel(sub[rest], preps[0])]
        for hole in preps[1:]:
            if len(in_idx) > 0:
                in_idx = in_idx[~_testar_anel(sub[in_idx], hole)]
        cov[in_idx] = True
    out[idx] = cov
    return out

def _degrau_coberto(
    v_ab: np.ndarray, t_ab: np.ndarray, z_lim: float, grupos_prep: list[list[tuple]], mxy: float, caixa_xy: tuple[float, float, float, float]
) -> bool:
    """Confere se vertices e meios de arestas dos triangulos da fatia (z >= z_lim abaixo do corte) que cruzam a caixa XY estao nos grupos."""
    if len(t_ab) > 0:
        on_zlim = np.abs(v_ab[:, 2] - z_lim) <= _EPS_PLANO
        if np.any(on_zlim) and np.any(on_zlim[t_ab].all(axis=1)):
            return False
    v_fat, t_fat, _ = cortar_malha_no_plano(v_ab * np.array((1.0, 1.0, -1.0)), t_ab, -z_lim)
    if len(v_fat) == 0 or len(t_fat) == 0:
        return True
    td = mxy + _EPS_DIST
    bx0, by0, bx1, by1 = caixa_xy[0] - td, caixa_xy[1] - td, caixa_xy[2] + td, caixa_xy[3] + td
    v_xy = v_fat[:, :2]
    tri_xy = v_xy[t_fat]
    tri_min, tri_max = tri_xy.min(axis=1), tri_xy.max(axis=1)
    t_sel = t_fat[(tri_max[:, 0] >= bx0) & (tri_min[:, 0] <= bx1) & (tri_max[:, 1] >= by0) & (tri_min[:, 1] <= by1)]
    if len(t_sel) == 0:
        return True
    edges = np.concatenate([t_sel[:, (0, 1)], t_sel[:, (1, 2)], t_sel[:, (2, 0)]], axis=0)
    stride = np.int64(len(v_fat) + 1)
    ukeys = np.unique(np.minimum(edges[:, 0], edges[:, 1]) * stride + np.maximum(edges[:, 0], edges[:, 1]))
    pts = np.unique(np.vstack([v_xy[np.unique(t_sel)], 0.5 * (v_xy[ukeys // stride] + v_xy[ukeys % stride])]), axis=0)
    if not grupos_prep or len(pts) > _TETO_PONTOS:
        return False
    rem = pts[np.argsort(pts[:, 1])]
    for preps in grupos_prep:
        if len(rem) == 0:
            return True
        rem = rem[~_pontos_no_grupo(rem, preps, td, td * td)]
    return len(rem) == 0

def oclusores_da_peca(caixa_peca, outras, z, *, tol_z=1e-3, margem_xy=1e-3):
    """Retorna grupos de aneis fechados das pecas em `outras` que podem ocultar a peca em `z` (None => HLR)."""
    try:
        xmin_p, ymin_p, xmax_p, ymax_p, zmin_p = (float(c) for c in caixa_peca)
        zf, tz, mxy = float(z), float(tol_z), float(margem_xy)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (xmin_p, ymin_p, xmax_p, ymax_p, zmin_p, zf, tz, mxy)) or xmin_p > xmax_p or ymin_p > ymax_p or tz < 0.0 or mxy < 0.0:
        return None
    grupos: list[list[np.ndarray]] = []
    for peca in outras:
        valida, malha = _validar_peca(peca)
        if not valida:
            return None
        if malha is None:
            continue
        v, t = malha
        xy_min, xy_max = v[:, :2].min(axis=0), v[:, :2].max(axis=0)
        if float(xy_max[0]) + mxy < xmin_p or float(xy_min[0]) - mxy > xmax_p or float(xy_max[1]) + mxy < ymin_p or float(xy_min[1]) - mxy > ymax_p:
            continue
        z_min, z_max = float(v[:, 2].min()), float(v[:, 2].max())
        if z_min > zf + _EPS_PLANO or z_max <= zmin_p + tz:
            continue
        if z_max < zf - _EPS_PLANO or np.any(np.abs(v[:, 2] - zf) <= _EPS_PLANO):
            return None
        v_ab, t_ab, segs = cortar_malha_no_plano(v, t, zf)
        fechados, abertos = aneis_de_segmentos(segs)
        agrupados = None if abertos else _agrupar_aneis(fechados)
        if agrupados is None or not _degrau_coberto(v_ab, t_ab, zmin_p + tz, [p for _, p in agrupados], mxy, (xmin_p, ymin_p, xmax_p, ymax_p)):
            return None
        grupos.extend(rings for rings, _ in agrupados)
    return grupos
