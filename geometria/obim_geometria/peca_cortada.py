# SPDX-License-Identifier: AGPL-3.0-or-later
"""Linhas visiveis de uma peca cortada por plano horizontal com oclusao por aneis."""
from __future__ import annotations

import math

import numpy as np

from obim_geometria.aneis import aneis_de_segmentos
from obim_geometria.corte_plano import cortar_malha_no_plano
from obim_geometria.recorte import recortar_fora_dos_aneis
from obim_geometria.visibilidade import linhas_visiveis


def _validar_entrada(verts, tris, z) -> tuple[np.ndarray, np.ndarray, float] | None:
    """Valida malha e cota z; retorna (verts_f64, tris_i64, z_f) ou None se invalida."""
    try:
        zf = float(z)
        v = np.asarray(verts, dtype=np.float64)
        t_raw = np.asarray(tris)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(zf):
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
    return v, t, zf


def linhas_peca_cortada(verts, tris, z, aneis_oclusores=(), *, encolher=5e-4):
    """Retorna polilinhas (K, 2) visiveis da peca cortada em `z` fora de `aneis_oclusores`, ou None."""
    validada = _validar_entrada(verts, tris, z)
    if validada is None:
        return None
    v, t, zf = validada

    dz = v[:, 2] - zf
    eps = max(1e-9, 1e-12 * max(1.0, abs(zf)))
    if np.any(np.abs(dz) <= eps):
        return None

    if np.all(dz > 0.0):
        return []
    if np.all(dz < 0.0):
        linhas = linhas_visiveis(v, t)
        return recortar_fora_dos_aneis(linhas, aneis_oclusores, encolher=encolher)

    verts_ab, tris_ab, segs = cortar_malha_no_plano(v, t, zf)
    fechados, abertos = aneis_de_segmentos(segs)
    if abertos:
        return None

    linhas = linhas_visiveis(verts_ab, tris_ab) if len(tris_ab) > 0 else []
    contornos = [np.vstack([r, r[:1]]) for r in fechados]
    return recortar_fora_dos_aneis(linhas + contornos, aneis_oclusores, encolher=encolher)
