# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mapa Z conservador, varredura de celulas e recorte analitico de visibilidade."""
from __future__ import annotations

import math
import numpy as np

from obim_geometria.visib_base import (
    _aplicar_corte,
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _rle_idx,
    _subseg_cels,
    _varredura_x,
)


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
    n = len(He)
    if n == 0:
        return He[:0].copy(), np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    if n == 1:
        lo = np.asarray(Hlo, dtype=np.float64)
        return He.copy(), lo.copy(), np.maximum(lo, np.asarray(Hhi, dtype=np.float64))
    o = np.lexsort((Hlo, He))
    He = He[o]
    Hlo = np.asarray(Hlo[o], dtype=np.float64)
    Hhi = np.asarray(Hhi[o], dtype=np.float64)
    del o
    novo = np.empty(n, dtype=bool)
    novo[0] = True
    np.not_equal(He[1:], He[:-1], out=novo[1:])
    grp = np.cumsum(novo, dtype=np.int64)
    s = np.argsort(Hhi)
    Hhi_s = Hhi[s]
    rank = np.empty(n, dtype=np.int64)
    rank[s] = np.arange(n, dtype=np.int64)
    del s
    base = grp * n
    hic_rank = np.maximum.accumulate(base + rank) - base
    hic = Hhi_s[hic_rank]
    del Hhi_s, rank, base, hic_rank, grp
    ini = novo
    ini[1:] |= Hlo[1:] > hic[:-1] + 1e-9
    fim = np.empty(n, dtype=bool)
    fim[:-1] = ini[1:]
    fim[-1] = True
    Hlo_ini = Hlo[ini]
    return He[ini], Hlo_ini, np.maximum(Hlo_ini, hic[fim])


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
    """Filtra por Z e caixa XY, deduplica pares e executa o recorte analitico."""
    if not len(pe):
        return
    m = (
        (tzmax[pt] > ezmin[pe] + tol_z) & (tx1[pt] >= ex0[pe]) & (tx0[pt] <= ex1[pe])
        & (ty1[pt] >= ey0[pe]) & (ty0[pt] <= ey1[pe])
    )
    if not np.any(m):
        return
    pe = pe[m]
    pt = pt[m]
    ch = _dedup_int64(pe.astype(np.int64) * nt_all + pt)
    pe = ch // nt_all
    pt = ch % nt_all
    tv_p = tv[pt]
    a_sh = (ea[pe] == tv_p[:, 0]) | (ea[pe] == tv_p[:, 1]) | (ea[pe] == tv_p[:, 2])
    b_sh = (eb[pe] == tv_p[:, 0]) | (eb[pe] == tv_p[:, 1]) | (eb[pe] == tv_p[:, 2])
    if np.any(a_sh | b_sh):
        skip = np.zeros(len(pe), dtype=bool)
        if np.any(a_sh):
            pa, qa = pe[a_sh], pt[a_sh]
            z_b = A[qa, 2] + gx[qa] * (b[pa, 0] - A[qa, 0]) + gy[qa] * (b[pa, 1] - A[qa, 1])
            skip[a_sh] = b[pa, 2] >= z_b - tol_z
        if np.any(b_sh):
            pb, qb = pe[b_sh], pt[b_sh]
            z_a = A[qb, 2] + gx[qb] * (a[pb, 0] - A[qb, 0]) + gy[qb] * (a[pb, 1] - A[qb, 1])
            skip[b_sh] |= a[pb, 2] >= z_a - tol_z
        pe = pe[~skip]
        pt = pt[~skip]
    if not len(pe):
        return
    p0x = a[pe, 0]
    p0y = a[pe, 1]
    dx = d[pe, 0]
    dy = d[pe, 1]
    len2d = np.hypot(dx, dy)
    lo = np.zeros(len(pe))
    hi = np.ones(len(pe))
    eps = abs(d_eps)
    lo, hi = _aplicar_corte(dx, tx0[pt] - eps - p0x, lo, hi, -1.0)
    lo, hi = _aplicar_corte(-dx, p0x - tx1[pt] - eps, lo, hi, -1.0)
    lo, hi = _aplicar_corte(dy, ty0[pt] - eps - p0y, lo, hi, -1.0)
    lo, hi = _aplicar_corte(-dy, p0y - ty1[pt] - eps, lo, hi, -1.0)
    ok = (hi - lo) * len2d > 1e-5
    if not np.any(ok):
        return
    if not ok.all():
        pe, pt, p0x, p0y, dx, dy, len2d, lo, hi = (
            x[ok] for x in (pe, pt, p0x, p0y, dx, dy, len2d, lo, hi)
        )
    for ii in range(3):
        s_i = nx_[pt, ii] * dx + ny_[pt, ii] * dy
        r_i = d_eps - (nx_[pt, ii] * p0x + ny_[pt, ii] * p0y + cc_[pt, ii])
        lo, hi = _aplicar_corte(s_i, r_i, lo, hi, -1.0)
    ok = (hi - lo) * len2d > 1e-5
    if not np.any(ok):
        return
    if not ok.all():
        pe, pt, p0x, p0y, dx, dy, len2d, lo, hi = (
            x[ok] for x in (pe, pt, p0x, p0y, dx, dy, len2d, lo, hi)
        )
    G0 = A[pt, 2] + gx[pt] * (p0x - A[pt, 0]) + gy[pt] * (p0y - A[pt, 1]) - a[pe, 2] - tol_z
    lo, hi = _aplicar_corte(gx[pt] * dx + gy[pt] * dy - d[pe, 2], -G0, lo, hi, -1.0, eq_fail=True)
    v = (hi - lo) * len2d > 1e-5
    if np.any(v):
        H_l.append(_unir_intervalos(pe[v], lo[v], hi[v]))
        if len(H_l) > 1 and sum(len(x[0]) for x in H_l[1:]) >= max(1_500_000, len(H_l[0][0])):
            _compactar_H(H_l)


def _subgrade_celulas_densas(
    eobj_d, ecel_d, cont, ini_cel, tri_por_cel, bx0: int, by0: int, Wl: int,
    mn_x: float, mn_y: float, cg: float,
    a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all: int,
    tol_z: float, d_eps: float, H_l: list,
):
    """Subdivide apenas celulas densas em grade de 2o nivel preservando a, b, d originais."""
    cels_u = np.unique(ecel_d)
    ts_parts = [tri_por_cel[ini_cel[c]:ini_cel[c] + cont[c]] for c in cels_u]
    t_densos = np.unique(np.concatenate(ts_parts))
    if not len(t_densos):
        return

    cy_d = by0 + (cels_u // Wl)
    cx_d = bx0 + (cels_u % Wl)
    sub_x0 = mn_x + float(cx_d.min()) * cg
    sub_x1 = mn_x + float(cx_d.max() + 1) * cg
    sub_y0 = mn_y + float(cy_d.min()) * cg
    sub_y1 = mn_y + float(cy_d.max() + 1) * cg
    dx_s = max(sub_x1 - sub_x0, cg)
    dy_s = max(sub_y1 - sub_y0, cg)
    area_d = float(len(cels_u)) * cg * cg
    cg_sub = max(1e-4, min(cg / 4.0, math.sqrt(area_d / max(len(t_densos) / 4.0, 1.0))))
    Ws = int(math.ceil(dx_s / cg_sub)) + 2
    Hs = int(math.ceil(dy_s / cg_sub)) + 2
    while Ws * Hs > 2_000_000:
        cg_sub *= 1.5
        Ws = int(math.ceil(dx_s / cg_sub)) + 2
        Hs = int(math.ceil(dy_s / cg_sub)) + 2

    eps = abs(d_eps)
    ix0, ix1, iy0, iy1 = _cel_caixa(
        tx0[t_densos] - eps, tx1[t_densos] + eps,
        ty0[t_densos] - eps, ty1[t_densos] + eps,
        sub_x0, sub_y0, cg_sub, Ws, Hs,
    )
    n_sub = (ix1 - ix0 + 1) * (iy1 - iy0 + 1)
    eh_grd = n_sub > 64
    t_grd = t_densos[eh_grd]
    t_fino_m = ~eh_grd

    eo_u = np.unique(eobj_d)
    if len(t_grd):
        eo_g = eo_u
        if len(t_grd) * len(eo_g) > 200_000:
            mg = (
                (ex1[eo_g] >= tx0[t_grd].min()) & (ex0[eo_g] <= tx1[t_grd].max())
                & (ey1[eo_g] >= ty0[t_grd].min()) & (ey0[eo_g] <= ty1[t_grd].max())
                & (ezmin[eo_g] < tzmax[t_grd].max() - tol_z)
            )
            eo_g = eo_g[mg]
        if len(eo_g):
            step_g = max(1, 200_000 // len(eo_g))
            for g0 in range(0, len(t_grd), step_g):
                tg = t_grd[g0:g0 + step_g]
                _filtrar_e_recortar(
                    np.repeat(eo_g, len(tg)), np.tile(tg, len(eo_g)),
                    a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                    tol_z, d_eps, H_l,
                )

    if not np.any(t_fino_m):
        return
    t_fino = t_densos[t_fino_m]
    tobj_s, tcel_s = _expandir_celulas(ix0[t_fino_m], ix1[t_fino_m], iy0[t_fino_m], iy1[t_fino_m], Ws)
    tobj_s = t_fino[tobj_s]
    ord_ts = np.argsort(tcel_s, kind="stable")
    tri_sub = tobj_s[ord_ts]
    cel_sub_ord = tcel_s[ord_ts]
    ncel_s = Ws * Hs
    cont_s = np.bincount(cel_sub_ord, minlength=ncel_s)
    ini_s = np.cumsum(cont_s) - cont_s
    sub_tzmax = np.full(ncel_s, -np.inf)
    np.maximum.at(sub_tzmax, cel_sub_ord, tzmax[tri_sub])

    p0x, p0y = a[eo_u, 0], a[eo_u, 1]
    ddx, ddy = d[eo_u, 0], d[eo_u, 1]
    t_lo = np.zeros(len(eo_u), dtype=np.float64)
    t_hi = np.ones(len(eo_u), dtype=np.float64)
    pad_box = eps + 1e-9
    for comp_d, comp_p, lo_b, hi_b in (
        (ddx, p0x, sub_x0 - pad_box, sub_x1 + pad_box),
        (ddy, p0y, sub_y0 - pad_box, sub_y1 + pad_box),
    ):
        nz = np.abs(comp_d) > 1e-15
        fora = (~nz) & ((comp_p < lo_b) | (comp_p > hi_b))
        t_hi = np.where(fora, -1.0, t_hi)
        inv = np.where(nz, 1.0 / np.where(nz, comp_d, 1.0), 0.0)
        ta = (lo_b - comp_p) * inv
        tb = (hi_b - comp_p) * inv
        t_lo = np.where(nz, np.maximum(t_lo, np.minimum(ta, tb)), t_lo)
        t_hi = np.where(nz, np.minimum(t_hi, np.maximum(ta, tb)), t_hi)
    ok_clip = t_hi >= t_lo - 1e-12
    if not np.any(ok_clip):
        return
    eo_c = eo_u[ok_clip]
    t_lo = np.clip(t_lo[ok_clip], 0.0, 1.0)
    t_hi = np.clip(t_hi[ok_clip], 0.0, 1.0)
    a_clip = a[eo_c] + t_lo[:, None] * d[eo_c]
    d_clip = (t_hi - t_lo)[:, None] * d[eo_c]

    step_s = 0.999 * cg_sub
    span_s = np.maximum(np.abs(d_clip[:, 0]), np.abs(d_clip[:, 1]))
    nsub_s = np.maximum(1, np.ceil(span_s / step_s).astype(np.int64))
    for e0, e1 in _fatias(nsub_s, 400_000):
        ec_s = eo_c[e0:e1]
        s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
            a_clip[e0:e1], d_clip[e0:e1], nsub_s[e0:e1], sub_x0, sub_y0, cg_sub, Ws, Hs
        )
        sobj, scel = _expandir_celulas(sx0, sx1, sy0, sy1, Ws)
        ok_sc = sub_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
        eo_s = ec_s[s_l[sobj[ok_sc]]]
        ecel_s = scel[ok_sc]
        if not len(eo_s):
            continue
        ch_s = _dedup_int64(eo_s.astype(np.int64) * ncel_s + ecel_s)
        eo_s = ch_s // ncel_s
        ecel_s = ch_s % ncel_s
        nt_s = cont_s[ecel_s]
        nz = nt_s > 0
        eo_s, ecel_s, nt_s = eo_s[nz], ecel_s[nz], nt_s[nz]
        for p0, p1 in _fatias(nt_s, 200_000, chaves=eo_s):
            g3, kk = _rle_idx(nt_s[p0:p1])
            _filtrar_e_recortar(
                eo_s[p0:p1][g3], tri_sub[ini_s[ecel_s[p0:p1]][g3] + kk],
                a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                tol_z, d_eps, H_l,
            )
