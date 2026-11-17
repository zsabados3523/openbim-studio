# SPDX-License-Identifier: AGPL-3.0-or-later
"""Selecao de aneis oclusores a partir das demais pecas do pavimento."""
from __future__ import annotations

import math
import numpy as np

from obim_geometria.aneis import _area, _ponto_no_anel_arr, aneis_de_segmentos
from obim_geometria.corte_plano import cortar_malha_no_plano

_EPS_PLANO, _EPS_DIST = 1e-9, 1e-12


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
    if len(v) == 0 or int(t.min()) < 0 or int(t.max()) >= len(v):
        return False, None
    return True, (v, t)


def _agrupar_aneis(fechados: list[np.ndarray]) -> list[list[np.ndarray]] | None:
    """Agrupa aneis fechados: cada furo vai ao menor anel externo que o contem."""
    exts, furos = [], []
    for anel in fechados:
        area = _area(anel)
        if abs(area) <= _EPS_DIST:
            return None
        x1, y1 = anel[:, 0], anel[:, 1]
        bb = (float(x1.min()), float(y1.min()), float(x1.max()), float(y1.max()))
        if area > 0.0:
            exts.append((area, bb, x1, y1, np.roll(x1, -1), np.roll(y1, -1), [anel]))
        else:
            furos.append((-area, bb, anel))
    for abs_area, fbb, furo in furos:
        px, py = 0.5 * float(furo[0, 0] + furo[1, 0]), 0.5 * float(furo[0, 1] + furo[1, 1])
        cands = [
            c for c in exts
            if c[0] > abs_area
            and c[1][0] <= fbb[0] + _EPS_PLANO and c[1][2] >= fbb[2] - _EPS_PLANO
            and c[1][1] <= fbb[1] + _EPS_PLANO and c[1][3] >= fbb[3] - _EPS_PLANO
            and _ponto_no_anel_arr(px, py, c[2], c[3], c[4], c[5])
        ]
        if not cands:
            return None
        min(cands, key=lambda c: c[0])[6].append(furo)
    return [rings for *_, rings in exts]


def oclusores_da_peca(caixa_peca, outras, z, *, tol_z=1e-3, margem_xy=1e-3):
    """Retorna grupos de aneis fechados de `outras` que podem ocultar a peca em `z`, ou None."""
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
        (xmin, ymin), (xmax, ymax) = v[:, :2].min(axis=0), v[:, :2].max(axis=0)
        if xmax + mxy < xmin_p or xmin - mxy > xmax_p or ymax + mxy < ymin_p or ymin - mxy > ymax_p:
            continue
        z_min, z_max = float(v[:, 2].min()), float(v[:, 2].max())
        if z_min > zf + _EPS_PLANO or z_max <= zmin_p + tz:
            continue
        if z_max < zf - _EPS_PLANO or np.any(np.abs(v[:, 2] - zf) <= _EPS_PLANO):
            return None
        _, _, segs = cortar_malha_no_plano(v, t, zf)
        fechados, abertos = aneis_de_segmentos(segs)
        agrupados = None if abertos else _agrupar_aneis(fechados)
        if agrupados is None:
            return None
        grupos.extend(agrupados)
    return grupos
