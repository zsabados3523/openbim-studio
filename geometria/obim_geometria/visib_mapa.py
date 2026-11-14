# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mapa Z conservador, varredura de celulas e recorte analitico de visibilidade."""
from __future__ import annotations

import math
import numpy as np

from obim_geometria.visib_base import _aplicar_corte, _fatias, _rle_idx, _varredura_x


def _mapa_z_conservador(A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, mx_x, mx_y, res_c):
    """Constroi z_full em blocos: limite inferior garantido de Z em toda a extensao da celula."""
    Wc = int(math.ceil((mx_x - mn_x) / res_c)) + 2
    Hc = int(math.ceil((mx_y - mn_y) / res_c)) + 2
    zf = np.full((Hc, Wc), -np.inf, dtype=np.float64)
    ib = np.nonzero((tx1 - tx0 >= res_c) & (ty1 - ty0 >= res_c))[0]
    if not len(ib):
        return zf, Wc, Hc
    iy0b = np.maximum(0, np.ceil((ty0[ib] - mn_y) / res_c).astype(np.int64))
    iy1b = np.minimum(Hc - 1, np.floor((ty1[ib] - mn_y) / res_c).astype(np.int64) - 1)
    okb = iy1b >= iy0b
    ib = ib[okb]
    iy0b = iy0b[okb]
    iy1b = iy1b[okb]
    rows = iy1b - iy0b + 1
    for r0, r1 in _fatias(rows, 250_000):
        grp, dy = _rle_idx(rows[r0:r1])
        tri_r = ib[r0:r1][grp]
        iy_r = iy0b[r0:r1][grp] + dy
        Y_r = mn_y + (iy_r + 0.5) * res_c
        x_lo = np.full(len(tri_r), -np.inf)
        x_hi = np.full(len(tri_r), np.inf)
        # Margem de meio pixel + folga numerica cobre os 4 cantos da celula.
        fin, ix0_r, ix1_r, okr = _varredura_x(
            nx_, ny_, cc_, tri_r, Y_r, x_lo, x_hi, 0.5 * res_c + 1e-12, mn_x, res_c, Wc
        )
        tri_r = tri_r[fin][okr]
        iy_r = iy_r[fin][okr]
        Y_r = Y_r[fin][okr]
        ix0_r = ix0_r[okr]
        cols = ix1_r[okr] - ix0_r + 1
        for c0, c1 in _fatias(cols, 1_000_000):
            g2, dx = _rle_idx(cols[c0:c1])
            t_p = tri_r[c0:c1][g2]
            iy_p = iy_r[c0:c1][g2]
            Y_p = Y_r[c0:c1][g2]
            ix_p = ix0_r[c0:c1][g2] + dx
            X_p = mn_x + (ix_p + 0.5) * res_c
            z_c = (
                A[t_p, 2] + gx[t_p] * (X_p - A[t_p, 0]) + gy[t_p] * (Y_p - A[t_p, 1])
                - 0.5 * res_c * (np.abs(gx[t_p]) + np.abs(gy[t_p]))
            )
            np.maximum.at(zf, (iy_p, ix_p), z_c)
    return zf, Wc, Hc


def _varrer_cels_triangulos(cand, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, cg, Wc, Hc):
    """Varre faixas de linhas de `cand` retornando colunas cobertas (com 1 celula de folga)."""
    iy0 = np.maximum(0, np.floor((ty0[cand] - mn_y) / cg).astype(np.int64) - 1)
    iy1 = np.minimum(Hc - 1, np.floor((ty1[cand] - mn_y) / cg).astype(np.int64) + 1)
    rows = iy1 - iy0 + 1
    faixas = []
    cov = np.zeros(len(cand), dtype=np.int64)
    for r0, r1 in _fatias(rows, 250_000):
        grp, dy = _rle_idx(rows[r0:r1])
        loc_r = r0 + grp
        tri_r = cand[loc_r]
        iy_r = iy0[loc_r] + dy
        Y_r = mn_y + (iy_r + 0.5) * cg
        fin, ix0_r, ix1_r, okr = _varredura_x(
            nx_, ny_, cc_, tri_r, Y_r, tx0[tri_r] - 1.5 * cg, tx1[tri_r] + 1.5 * cg,
            -(1.5 * cg + 1e-12), mn_x, cg, Wc,
        )
        loc_r = loc_r[fin][okr]
        iy_r = iy_r[fin][okr]
        ix0_r = ix0_r[okr]
        ix1_r = ix1_r[okr]
        np.add.at(cov, loc_r, ix1_r - ix0_r + 1)
        faixas.append((loc_r, iy_r, ix0_r, ix1_r))
    if not faixas:
        z = np.zeros(0, dtype=np.int64)
        return cov, z, z, z, z
    loc_a, iy_a, ix0_a, ix1_a = (np.concatenate(x) for x in zip(*faixas))
    return cov, loc_a, iy_a, ix0_a, ix1_a


def _unir_intervalos(He: np.ndarray, Hlo: np.ndarray, Hhi: np.ndarray):
    """Ordena e une intervalos [lo, hi] sobrepostos por aresta."""
    if len(He) <= 1:
        return He, Hlo, Hhi
    o = np.lexsort((Hlo, He))
    He = He[o]
    Hlo = Hlo[o]
    Hhi = Hhi[o]
    del o
    novo = np.concatenate([[True], He[1:] != He[:-1]])
    off = np.cumsum(novo) * 2.0
    hic = np.maximum.accumulate(Hhi + off)
    prev_hi = np.where(novo, -1.0, np.concatenate([[0.0], hic[:-1]]) - off)
    ini = novo | (Hlo > prev_hi + 1e-9)
    fim = np.concatenate([ini[1:], [True]])
    return He[ini], Hlo[ini], np.maximum(Hlo[ini], (hic - off)[fim])


def _compactar_H(H_l: list, limpar: bool = False):
    """Concatena e compacta intervalos escondidos acumulados em `H_l`."""
    if not H_l:
        z_i = np.zeros(0, dtype=np.int64)
        z_f = np.zeros(0, dtype=np.float64)
        return z_i, z_f, z_f
    if len(H_l) == 1:
        He, Hlo, Hhi = H_l[0]
    else:
        He, Hlo, Hhi = (np.concatenate(x) for x in zip(*H_l))
    H_l.clear()
    res = _unir_intervalos(He, Hlo, Hhi)
    if not limpar:
        H_l.append(res)
    return res


def _filtrar_e_recortar(
    pe, pt, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_l,
):
    """Aplica filtros de caixa/leque, deduplica pares e executa o recorte analitico."""
    m = (
        (tzmax[pt] > ezmin[pe] + tol_z) & (tx1[pt] >= ex0[pe]) & (tx0[pt] <= ex1[pe])
        & (ty1[pt] >= ey0[pe]) & (ty0[pt] <= ey1[pe])
    )
    if not np.any(m):
        return
    pe = pe[m]
    pt = pt[m]
    tv_p = tv[pt]
    a_sh = (ea[pe] == tv_p[:, 0]) | (ea[pe] == tv_p[:, 1]) | (ea[pe] == tv_p[:, 2])
    b_sh = (eb[pe] == tv_p[:, 0]) | (eb[pe] == tv_p[:, 1]) | (eb[pe] == tv_p[:, 2])
    if np.any(a_sh | b_sh):
        z_a = A[pt, 2] + gx[pt] * (a[pe, 0] - A[pt, 0]) + gy[pt] * (a[pe, 1] - A[pt, 1])
        z_b = A[pt, 2] + gx[pt] * (b[pe, 0] - A[pt, 0]) + gy[pt] * (b[pe, 1] - A[pt, 1])
        skip = (a_sh & (b[pe, 2] >= z_b - tol_z)) | (b_sh & (a[pe, 2] >= z_a - tol_z))
        pe = pe[~skip]
        pt = pt[~skip]
    if not len(pe):
        return
    ch = np.unique(pe.astype(np.int64) * nt_all + pt)
    pe = ch // nt_all
    pt = ch % nt_all
    p0x = a[pe, 0]
    p0y = a[pe, 1]
    dx = d[pe, 0]
    dy = d[pe, 1]
    lo = np.zeros(len(pe))
    hi = np.ones(len(pe))
    eps = abs(d_eps)
    lo, hi = _aplicar_corte(dx, tx0[pt] - eps - p0x, lo, hi, -1.0)
    lo, hi = _aplicar_corte(-dx, p0x - tx1[pt] - eps, lo, hi, -1.0)
    lo, hi = _aplicar_corte(dy, ty0[pt] - eps - p0y, lo, hi, -1.0)
    lo, hi = _aplicar_corte(-dy, p0y - ty1[pt] - eps, lo, hi, -1.0)
    for ii in range(3):
        s_i = nx_[pt, ii] * dx + ny_[pt, ii] * dy
        r_i = d_eps - (nx_[pt, ii] * p0x + ny_[pt, ii] * p0y + cc_[pt, ii])
        lo, hi = _aplicar_corte(s_i, r_i, lo, hi, -1.0)
    G0 = A[pt, 2] + gx[pt] * (p0x - A[pt, 0]) + gy[pt] * (p0y - A[pt, 1]) - a[pe, 2] - tol_z
    lo, hi = _aplicar_corte(gx[pt] * dx + gy[pt] * dy - d[pe, 2], -G0, lo, hi, -1.0, eq_fail=True)
    v = (hi - lo) * np.hypot(dx, dy) > 1e-5
    if np.any(v):
        H_l.append(_unir_intervalos(pe[v], lo[v], hi[v]))
        if len(H_l) > 1 and sum(len(x[0]) for x in H_l[1:]) >= max(1_500_000, len(H_l[0][0])):
            _compactar_H(H_l)
