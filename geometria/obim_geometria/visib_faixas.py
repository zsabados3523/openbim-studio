# SPDX-License-Identifier: AGPL-3.0-or-later
"""Passagem por faixas 1D orientadas para triangulos longos e estreitos."""
from __future__ import annotations

import math
import numpy as np

from obim_geometria.visib_base import _fatias, _rle_idx
from obim_geometria.visib_mapa import _filtrar_e_recortar


def _passagem_faixas_orientadas(P, tv, rem_t, ek_idx, a, b, d, g, tol_z, d_eps, ctx, H_l):
    """Trata triangulos longos e estreitos alinhados a direcoes dominantes por faixas 1D."""
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, ea, eb, ex0, ex1, ey0, ey1, ezmin = ctx
    nt_all = len(A)
    eps = abs(d_eps)
    for _ in range(3):
        if len(rem_t) < 200 or not len(ek_idx):
            break
        pts = P[tv[rem_t]]
        ev = np.roll(pts, -1, axis=1)[:, :, :2] - pts[:, :, :2]
        imax = (ev ** 2).sum(axis=2).argmax(axis=1)
        vec = ev[np.arange(len(rem_t)), imax]
        flip = (vec[:, 1] < 0) | ((vec[:, 1] == 0) & (vec[:, 0] < 0))
        vec[flip] = -vec[flip]
        ang = np.arctan2(vec[:, 1], vec[:, 0])
        bins = np.clip(np.floor(ang / (math.pi / 36.0)).astype(np.int64), 0, 35)
        cnt = np.bincount(bins, minlength=36)
        b_top = int(cnt.argmax())
        if cnt[b_top] < max(100, len(rem_t) // 8):
            break
        th = float(np.median(ang[bins == b_top]))
        cs = math.cos(th)
        sn = math.sin(th)
        pxr = cs * pts[:, :, 0] + sn * pts[:, :, 1]
        pyr = -sn * pts[:, :, 0] + cs * pts[:, :, 1]
        tx0r = pxr.min(1)
        tx1r = pxr.max(1)
        ty0r = pyr.min(1)
        ty1r = pyr.max(1)
        dyr = ty1r - ty0r
        cand_m = (tx1r - tx0r > 20.0 * g) & (dyr <= 0.1 * (tx1r - tx0r))
        if int(cand_m.sum()) < 100:
            break
        axr = cs * a[ek_idx, 0] + sn * a[ek_idx, 1]
        ayr = -sn * a[ek_idx, 0] + cs * a[ek_idx, 1]
        bxr = cs * b[ek_idx, 0] + sn * b[ek_idx, 1]
        byr = -sn * b[ek_idx, 0] + cs * b[ek_idx, 1]
        ex0r = np.minimum(axr, bxr)
        ex1r = np.maximum(axr, bxr)
        ey0r = np.minimum(ayr, byr)
        ey1r = np.maximum(ayr, byr)
        mn_yr = float(min(ty0r[cand_m].min(), ey0r.min()))
        mx_yr = float(max(ty1r[cand_m].max(), ey1r.max()))
        by = max(g, float(np.median(dyr[cand_m])) * 2.0, (mx_yr - mn_yr) / 4000.0)
        sel_m = cand_m & (dyr <= 8.0 * by)
        if int(sel_m.sum()) < 100:
            break
        ny_b = int(math.ceil((mx_yr - mn_yr) / by)) + 2
        e_iy0 = np.clip(np.floor((ey0r - mn_yr) / by).astype(np.int64), 0, ny_b - 1)
        e_iy1 = np.clip(np.floor((ey1r - mn_yr) / by).astype(np.int64), 0, ny_b - 1)
        e_cnt = e_iy1 - e_iy0 + 1
        if int(e_cnt.sum()) > 4_000_000:
            break
        cur_t = rem_t[sel_m]
        rem_t = rem_t[~sel_m]
        t_iy0 = np.clip(np.floor((ty0r[sel_m] - eps - mn_yr) / by).astype(np.int64), 0, ny_b - 1)
        t_iy1 = np.clip(np.floor((ty1r[sel_m] + eps - mn_yr) / by).astype(np.int64), 0, ny_b - 1)
        g_t, dt_b = _rle_idx(t_iy1 - t_iy0 + 1)
        tobj = cur_t[g_t]
        tbin = t_iy0[g_t] + dt_b
        ord_t = np.argsort(tbin, kind="stable")
        tri_por_b = tobj[ord_t]
        bin_ord = tbin[ord_t]
        cont_b = np.bincount(bin_ord, minlength=ny_b)
        ini_b = np.cumsum(cont_b) - cont_b
        b_tzmax = np.full(ny_b, -np.inf)
        np.maximum.at(b_tzmax, bin_ord, tzmax[tri_por_b])
        pos_t = np.full(nt_all, -1, dtype=np.int64)
        pos_t[cur_t] = np.nonzero(sel_m)[0]
        pos_e = np.full(len(a), -1, dtype=np.int64)
        pos_e[ek_idx] = np.arange(len(ek_idx))
        for e0, e1 in _fatias(e_cnt, 400_000):
            ge, de = _rle_idx(e_cnt[e0:e1])
            eobj = ek_idx[e0:e1][ge]
            ebin = e_iy0[e0:e1][ge] + de
            ok_eb = b_tzmax[ebin] > ezmin[eobj] + tol_z
            eobj = eobj[ok_eb]
            ebin = ebin[ok_eb]
            nt_p = cont_b[ebin]
            nz = nt_p > 0
            eobj = eobj[nz]
            ebin = ebin[nz]
            nt_p = nt_p[nz]
            for p0, p1 in _fatias(nt_p, 2_000_000):
                g3, kk = _rle_idx(nt_p[p0:p1])
                pe = eobj[p0:p1][g3]
                pt = tri_por_b[ini_b[ebin[p0:p1]][g3] + kk]
                ie = pos_e[pe]
                it = pos_t[pt]
                mxr = (tx1r[it] + eps >= ex0r[ie]) & (tx0r[it] - eps <= ex1r[ie])
                if np.any(mxr):
                    _filtrar_e_recortar(
                        pe[mxr], pt[mxr], a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_l,
                    )
    return rem_t
