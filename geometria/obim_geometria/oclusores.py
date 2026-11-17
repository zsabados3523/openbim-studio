# SPDX-License-Identifier: AGPL-3.0-or-later
"""Selecao de aneis oclusores a partir das demais pecas do pavimento."""
from __future__ import annotations

import math

import numpy as np

from obim_geometria.aneis import aneis_de_segmentos
from obim_geometria.corte_plano import cortar_malha_no_plano

_EPS_PLANO = 1e-9


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

    grupos: list[list[np.ndarray]] = []
    for peca in outras:
        valida, malha = _validar_peca(peca)
        if not valida:
            return None
        if malha is None:
            continue
        v, t = malha

        xy_min = v[:, :2].min(axis=0)
        xy_max = v[:, :2].max(axis=0)
        if (
            float(xy_max[0]) + mxy < xmin_p
            or float(xy_min[0]) - mxy > xmax_p
            or float(xy_max[1]) + mxy < ymin_p
            or float(xy_min[1]) - mxy > ymax_p
        ):
            continue

        z_min = float(v[:, 2].min())
        z_max = float(v[:, 2].max())
        if z_min > zf + _EPS_PLANO or z_max <= zmin_p + tz:
            continue
        if z_max < zf - _EPS_PLANO or np.any(np.abs(v[:, 2] - zf) <= _EPS_PLANO):
            return None

        _, _, segs = cortar_malha_no_plano(v, t, zf)
        fechados, abertos = aneis_de_segmentos(segs)
        if abertos:
            return None
        if fechados:
            grupos.append(fechados)

    return grupos
