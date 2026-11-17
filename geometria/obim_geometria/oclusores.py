# SPDX-License-Identifier: AGPL-3.0-or-later
"""Selecao de aneis oclusores a partir das demais pecas do pavimento."""
from __future__ import annotations

import math

import numpy as np

from obim_geometria.aneis import _area, _ponto_no_anel_arr, aneis_de_segmentos
from obim_geometria.corte_plano import cortar_malha_no_plano

_EPS_PLANO = 1e-9
_EPS_DIST = 1e-12


def _validar_peca(peca) -> tuple[bool, tuple[np.ndarray, np.ndarray] | None]:
    """Valida (verts, tris). Retorna (True, None) se vazia e (False, None) se invalida."""
    try:
        verts, tris = peca
        v = np.asarray(verts, dtype=np.float64)
        t_raw = np.asarray(tris)
    except (TypeError, ValueError):
        return False, None
    if v.ndim != 2 or v.shape[1] != 3:
        return False, None
    if t_raw.ndim != 2 or t_raw.shape[1] != 3 or not np.issubdtype(t_raw.dtype, np.integer):
        return False, None
    if len(v) > 0 and (not np.isfinite(v).all() or float(np.abs(v).max()) > 1e12):
        return False, None
    if len(t_raw) == 0:
        return True, None
    if len(v) == 0:
        return False, None
    t = t_raw.astype(np.int64, copy=False)
    if int(t.min()) < 0 or int(t.max()) >= len(v):
        return False, None
    return True, (v, t)


def _prep_anel(anel: np.ndarray):
    x1, y1 = anel[:, 0], anel[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    ex, ey = x2 - x1, y2 - y1
    bb = (float(x1.min()), float(y1.min()), float(x1.max()), float(y1.max()))
    return bb, x1, y1, x2, y2, ex, ey, np.maximum(ex * ex + ey * ey, 1e-30)


def _agrupar_aneis(fechados: list[np.ndarray]):
    """Agrupa aneis fechados: cada furo vai ao menor anel externo que o contem."""
    exts, furos = [], []
    for anel in fechados:
        area = _area(anel)
        if abs(area) <= _EPS_DIST:
            return None
        prep = _prep_anel(anel)
        if area > 0.0:
            exts.append((area, prep, [anel], [prep]))
        else:
            furos.append((-area, prep, anel))

    for abs_area, fprep, furo in furos:
        fbb = fprep[0]
        px, py = 0.5 * (float(furo[0, 0]) + float(furo[1, 0])), 0.5 * (float(furo[0, 1]) + float(furo[1, 1]))
        cands = [
            c for c in exts
            if c[0] > abs_area
            and c[1][0][0] <= fbb[0] + _EPS_PLANO and c[1][0][2] >= fbb[2] - _EPS_PLANO
            and c[1][0][1] <= fbb[1] + _EPS_PLANO and c[1][0][3] >= fbb[3] - _EPS_PLANO
            and _ponto_no_anel_arr(px, py, c[1][1], c[1][2], c[1][3], c[1][4])
        ]
        if not cands:
            return None
        pai = min(cands, key=lambda c: c[0])
        pai[2].append(furo)
        pai[3].append(fprep)

    return [(rings, preps) for _, _, rings, preps in exts]


def _ponto_no_grupo(px: float, py: float, preps: list[tuple], tol_d: float, tol_d2: float) -> bool:
    """Verdadeiro se (px, py) esta dentro do externo (fora dos furos) ou a distancia <= tol_d de alguma borda."""
    ebb = preps[0][0]
    if px < ebb[0] - tol_d or px > ebb[2] + tol_d or py < ebb[1] - tol_d or py > ebb[3] + tol_d:
        return False
    for rbb, x1, y1, _, _, ex, ey, el2 in preps:
        if rbb[0] - tol_d <= px <= rbb[2] + tol_d and rbb[1] - tol_d <= py <= rbb[3] + tol_d:
            u = np.clip(((px - x1) * ex + (py - y1) * ey) / el2, 0.0, 1.0)
            dx, dy = px - (x1 + u * ex), py - (y1 + u * ey)
            if float(np.min(dx * dx + dy * dy)) <= tol_d2:
                return True
    ext = preps[0]
    if not _ponto_no_anel_arr(px, py, ext[1], ext[2], ext[3], ext[4]):
        return False
    return not any(
        h[0][0] <= px <= h[0][2] and h[0][1] <= py <= h[0][3]
        and _ponto_no_anel_arr(px, py, h[1], h[2], h[3], h[4])
        for h in preps[1:]
    )


def _degrau_coberto(
    v_ab: np.ndarray, t_ab: np.ndarray, z_lim: float, grupos_prep: list[list[tuple]], mxy: float,
) -> bool:
    """Confere se vertices e meios de arestas da parte abaixo com z > z_lim estao nos grupos."""
    if len(v_ab) == 0:
        return True
    mask_v = v_ab[:, 2] > z_lim
    if not np.any(mask_v):
        return True
    if not grupos_prep:
        return False
    pts_list = [v_ab[mask_v, :2]]
    if len(t_ab) > 0:
        edges = np.concatenate([t_ab[:, (0, 1)], t_ab[:, (1, 2)], t_ab[:, (2, 0)]], axis=0)
        both = mask_v[edges[:, 0]] & mask_v[edges[:, 1]]
        if np.any(both):
            e_uniq = np.unique(np.sort(edges[both], axis=1), axis=0)
            pts_list.append(0.5 * (v_ab[e_uniq[:, 0], :2] + v_ab[e_uniq[:, 1], :2]))
    tol_d = mxy + _EPS_DIST
    tol_d2 = tol_d * tol_d
    for px, py in np.unique(np.vstack(pts_list), axis=0).tolist():
        if not any(_ponto_no_grupo(px, py, preps, tol_d, tol_d2) for preps in grupos_prep):
            return False
    return True


def oclusores_da_peca(caixa_peca, outras, z, *, tol_z=1e-3, margem_xy=1e-3):
    """Retorna grupos de aneis fechados das pecas em `outras` que podem ocultar a peca em `z`.

    Retorna ``[]`` quando nada oculta e ``None`` quando nao e seguro decidir (enviar ao HLR).
    """
    try:
        xmin_p, ymin_p, xmax_p, ymax_p, zmin_p = (float(c) for c in caixa_peca)
        zf, tz, mxy = float(z), float(tol_z), float(margem_xy)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (xmin_p, ymin_p, xmax_p, ymax_p, zmin_p, zf, tz, mxy)):
        return None
    if xmin_p > xmax_p or ymin_p > ymax_p or tz < 0.0 or mxy < 0.0:
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
        if (
            float(xy_max[0]) + mxy < xmin_p or float(xy_min[0]) - mxy > xmax_p
            or float(xy_max[1]) + mxy < ymin_p or float(xy_min[1]) - mxy > ymax_p
        ):
            continue

        z_min, z_max = float(v[:, 2].min()), float(v[:, 2].max())
        if z_min > zf + _EPS_PLANO or z_max <= zmin_p + tz:
            continue
        if z_max < zf - _EPS_PLANO or np.any(np.abs(v[:, 2] - zf) <= _EPS_PLANO):
            return None

        v_ab, t_ab, segs = cortar_malha_no_plano(v, t, zf)
        fechados, abertos = aneis_de_segmentos(segs)
        if abertos:
            return None
        agrupados = _agrupar_aneis(fechados)
        if agrupados is None or not _degrau_coberto(v_ab, t_ab, zmin_p + tz, [p for _, p in agrupados], mxy):
            return None
        grupos.extend(rings for rings, _ in agrupados)

    return grupos
