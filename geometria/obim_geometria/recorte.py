# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recorte de polilinhas fora da regiao dos aneis da secao (T19j2b)."""
from __future__ import annotations

from collections import namedtuple
import math

import numpy as np

from obim_geometria.aneis import _EPS, _ponto_no_anel_arr

_GrupoPrep = namedtuple("_GrupoPrep", "bbox rings cx cy ex_pt ey_pt ex ey el2 e_len nx ny emin_x emax_x emin_y emax_y vx vy")


def _sobrepoe(bb: tuple[float, float, float, float], x0: float, y0: float, x1: float, y1: float) -> bool:
    return bb[0] <= x1 and bb[2] >= x0 and bb[1] <= y1 and bb[3] >= y0


def _preparar_grupo(grupo) -> _GrupoPrep | None:
    rings_data = []
    for a in grupo:
        p = np.asarray(a, dtype=float)
        if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3:
            raise ValueError(f"Anel invalido: shape {p.shape}")
        if np.allclose(p[0], p[-1], atol=_EPS, rtol=0.0):
            p = p[:-1]
        d0 = (len(p) >= 3) and (np.max(np.abs(p - p[0]), axis=1) > _EPS)
        if not np.any(d0) or not np.any(d0 & (np.max(np.abs(p - p[np.argmax(d0)]), axis=1) > _EPS)):
            raise ValueError("Anel invalido: menos de 3 pontos distintos")
        rx1, ry1 = p[:, 0].copy(), p[:, 1].copy()
        rx2, ry2 = np.roll(rx1, -1), np.roll(ry1, -1)
        rings_data.append(((float(rx1.min()), float(ry1.min()), float(rx1.max()), float(ry1.max())), rx1, ry1, rx2, ry2))
    if not rings_data:
        return None

    vx = np.concatenate([r[1] for r in rings_data])
    vy = np.concatenate([r[2] for r in rings_data])
    ex_pt_all = np.concatenate([r[3] for r in rings_data])
    ey_pt_all = np.concatenate([r[4] for r in rings_data])
    ex_all, ey_all = ex_pt_all - vx, ey_pt_all - vy
    el2_all = ex_all * ex_all + ey_all * ey_all
    valid = el2_all > 0.0

    cx, cy = vx[valid], vy[valid]
    ex_pt, ey_pt = ex_pt_all[valid], ey_pt_all[valid]
    ex, ey, el2 = ex_all[valid], ey_all[valid], el2_all[valid]
    e_len = np.sqrt(el2)
    g_bbox = (float(vx.min()), float(vy.min()), float(vx.max()), float(vy.max()))
    return _GrupoPrep(
        g_bbox, rings_data, cx, cy, ex_pt, ey_pt, ex, ey, el2, e_len, -ey / e_len, ex / e_len,
        np.minimum(cx, ex_pt), np.maximum(cx, ex_pt), np.minimum(cy, ey_pt), np.maximum(cy, ey_pt), vx, vy,
    )


def _cortes_no_segmento(
    ax: float, ay: float, bx: float, by: float,
    smin_x: float, smin_y: float, smax_x: float, smax_y: float,
    grupos_ativos: list[_GrupoPrep], encolher: float,
) -> list[float]:
    dx, dy = bx - ax, by - ay
    aa = dx * dx + dy * dy
    seg_len, ts, r2 = math.sqrt(aa), [0.0, 1.0], encolher * encolher

    for g in grupos_ativos:
        if len(g.cx) > 0:
            emask = (g.emin_x <= smax_x) & (g.emax_x >= smin_x) & (g.emin_y <= smax_y) & (g.emax_y >= smin_y)
            if np.any(emask):
                cx, cy, ex_pt, ey_pt = g.cx[emask], g.cy[emask], g.ex_pt[emask], g.ey_pt[emask]
                ex, ey, el2, e_len = g.ex[emask], g.ey[emask], g.el2[emask], g.e_len[emask]
                denom, acx, acy = dx * ey - dy * ex, cx - ax, cy - ay
                m_np = np.abs(denom) > (_EPS * seg_len * e_len)
                if np.any(m_np):
                    d_np = denom[m_np]
                    t = (acx[m_np] * ey[m_np] - acy[m_np] * ex[m_np]) / d_np
                    u = (acx[m_np] * dy - acy[m_np] * dx) / d_np
                    ts.extend(t[(-1e-11 <= u) & (u <= 1.0 + 1e-11) & (0.0 < t) & (t < 1.0)].tolist())

                m_col = (~m_np) & (np.abs(acx * dy - acy * dx) <= 1e-11 * seg_len)
                if np.any(m_col):
                    for px_e, py_e in ((cx[m_col], cy[m_col]), (ex_pt[m_col], ey_pt[m_col])):
                        tc = ((px_e - ax) * dx + (py_e - ay) * dy) / aa
                        ts.extend(tc[(0.0 < tc) & (tc < 1.0)].tolist())

                if encolher > 0.0:
                    nx, ny = g.nx[emask], g.ny[emask]
                    ds = dx * nx + dy * ny
                    m_ds = np.abs(ds) > (_EPS * seg_len)
                    if np.any(m_ds):
                        ds_m = ds[m_ds]
                        cx_m, cy_m, ex_m, ey_m, el2_m = cx[m_ds], cy[m_ds], ex[m_ds], ey[m_ds], el2[m_ds]
                        s0_m = (ax - cx_m) * nx[m_ds] + (ay - cy_m) * ny[m_ds]
                        for alvo in (encolher, -encolher):
                            t = (alvo - s0_m) / ds_m
                            ok_t = (0.0 < t) & (t < 1.0)
                            if np.any(ok_t):
                                tk = t[ok_t]
                                u = ((ax + tk * dx - cx_m[ok_t]) * ex_m[ok_t] + (ay + tk * dy - cy_m[ok_t]) * ey_m[ok_t]) / el2_m[ok_t]
                                ts.extend(tk[(-1e-11 <= u) & (u <= 1.0 + 1e-11)].tolist())

        if encolher > 0.0 and len(g.vx) > 0:
            vmask = (g.vx >= smin_x) & (g.vx <= smax_x) & (g.vy >= smin_y) & (g.vy <= smax_y)
            if np.any(vmask):
                wx, wy = ax - g.vx[vmask], ay - g.vy[vmask]
                bh = wx * dx + wy * dy
                disc = bh * bh - aa * (wx * wx + wy * wy - r2)
                m_v = disc >= 0.0
                if np.any(m_v):
                    sq, bh_v = np.sqrt(disc[m_v]), bh[m_v]
                    for t_cand in ((-bh_v - sq) / aa, (-bh_v + sq) / aa):
                        ts.extend(t_cand[(0.0 < t_cand) & (t_cand < 1.0)].tolist())

    ts.sort()
    tol_t, unicos = min(_EPS, _EPS / max(1.0, seg_len)), [0.0]
    for t in ts[1:-1]:
        if t - unicos[-1] > tol_t and 1.0 - t > tol_t:
            unicos.append(t)
    return unicos + [1.0]


def _dentro_grupo(px: float, py: float, g: _GrupoPrep, encolher: float) -> bool:
    if not _sobrepoe(g.bbox, px, py, px, py):
        return False
    paridade = 0
    for rb, rx1, ry1, rx2, ry2 in g.rings:
        if _sobrepoe(rb, px, py, px, py) and _ponto_no_anel_arr(px, py, rx1, ry1, rx2, ry2):
            paridade ^= 1
    if paridade == 0:
        return False
    if len(g.cx) == 0:
        return True

    pad_d = max(0.0, encolher) + _EPS
    cmask = (g.emin_x - pad_d <= px) & (px <= g.emax_x + pad_d) & (g.emin_y - pad_d <= py) & (py <= g.emax_y + pad_d)
    if not np.any(cmask):
        return True
    cx_c, cy_c, ex_c, ey_c = g.cx[cmask], g.cy[cmask], g.ex[cmask], g.ey[cmask]
    u = np.clip(((px - cx_c) * ex_c + (py - cy_c) * ey_c) / g.el2[cmask], 0.0, 1.0)
    dx_c, dy_c = px - (cx_c + u * ex_c), py - (cy_c + u * ey_c)
    d2 = float(np.min(dx_c * dx_c + dy_c * dy_c))
    return d2 > _EPS * _EPS if encolher <= 0.0 else math.sqrt(d2) >= encolher - _EPS


def _eh_lista_plana(aneis_list: list) -> bool:
    p0 = aneis_list[0] if aneis_list else None
    if isinstance(p0, np.ndarray):
        return p0.ndim == 2
    pt = p0[0] if isinstance(p0, (list, tuple)) and p0 else None
    return (isinstance(pt, (list, tuple, np.ndarray)) and getattr(pt, "ndim", 1) == 1 and len(pt) == 2
            and all(isinstance(v, (int, float, np.number)) and not isinstance(v, bool) for v in pt))


_BLOCO_SEG = 2048
_MAX_ELEMS_BLOCO = 262_144


def _cortes_bloco(
    ax: np.ndarray,
    ay: np.ndarray,
    dx: np.ndarray,
    dy: np.ndarray,
    aa: np.ndarray,
    seg_len: np.ndarray,
    smin_x: np.ndarray,
    smin_y: np.ndarray,
    smax_x: np.ndarray,
    smax_y: np.ndarray,
    grupos: list[_GrupoPrep],
    encolher: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calcula todos os cortes (seg_idx, t) e flag de grupo ativo para um bloco de segmentos."""
    n_seg = len(ax)
    tem_grupo = np.zeros(n_seg, dtype=bool)
    seg_parts: list[np.ndarray] = []
    t_parts: list[np.ndarray] = []
    r2 = encolher * encolher

    for g in grupos:
        gmin_x, gmin_y, gmax_x, gmax_y = g.bbox
        gmask = (gmin_x <= smax_x) & (gmax_x >= smin_x) & (gmin_y <= smax_y) & (gmax_y >= smin_y)
        if not np.any(gmask):
            continue
        tem_grupo |= gmask
        g_idx = np.flatnonzero(gmask)
        n_g = len(g_idx)

        n_edges = len(g.cx)
        if n_edges > 0:
            step_e = max(1, _MAX_ELEMS_BLOCO // max(1, n_edges))
            for ini in range(0, n_g, step_e):
                sub_idx = g_idx[ini:ini + step_e]
                emask = (
                    (g.emin_x[None, :] <= smax_x[sub_idx, None])
                    & (g.emax_x[None, :] >= smin_x[sub_idx, None])
                    & (g.emin_y[None, :] <= smax_y[sub_idx, None])
                    & (g.emax_y[None, :] >= smin_y[sub_idx, None])
                )
                si_loc, ei = np.nonzero(emask)
                if len(si_loc) == 0:
                    continue
                si = sub_idx[si_loc]
                ax_p, ay_p = ax[si], ay[si]
                dx_p, dy_p = dx[si], dy[si]
                sl_p = seg_len[si]
                cx_p, cy_p = g.cx[ei], g.cy[ei]
                ex_p, ey_p = g.ex[ei], g.ey[ei]
                el_p = g.e_len[ei]

                denom = dx_p * ey_p - dy_p * ex_p
                acx = cx_p - ax_p
                acy = cy_p - ay_p
                m_np = np.abs(denom) > (_EPS * sl_p * el_p)
                if np.any(m_np):
                    d_np = denom[m_np]
                    t = (acx[m_np] * ey_p[m_np] - acy[m_np] * ex_p[m_np]) / d_np
                    u = (acx[m_np] * dy_p[m_np] - acy[m_np] * dx_p[m_np]) / d_np
                    ok = (-1e-11 <= u) & (u <= 1.0 + 1e-11) & (0.0 < t) & (t < 1.0)
                    if np.any(ok):
                        seg_parts.append(si[m_np][ok])
                        t_parts.append(t[ok])

                m_col = (~m_np) & (np.abs(acx * dy_p - acy * dx_p) <= 1e-11 * sl_p)
                if np.any(m_col):
                    si_c = si[m_col]
                    ax_c, ay_c = ax_p[m_col], ay_p[m_col]
                    dx_c, dy_c = dx_p[m_col], dy_p[m_col]
                    aa_c = aa[si_c]
                    for px_e, py_e in ((cx_p[m_col], cy_p[m_col]), (g.ex_pt[ei][m_col], g.ey_pt[ei][m_col])):
                        tc = ((px_e - ax_c) * dx_c + (py_e - ay_c) * dy_c) / aa_c
                        ok_c = (0.0 < tc) & (tc < 1.0)
                        if np.any(ok_c):
                            seg_parts.append(si_c[ok_c])
                            t_parts.append(tc[ok_c])

                if encolher > 0.0:
                    nx_p, ny_p = g.nx[ei], g.ny[ei]
                    ds = dx_p * nx_p + dy_p * ny_p
                    m_ds = np.abs(ds) > (_EPS * sl_p)
                    if np.any(m_ds):
                        si_d = si[m_ds]
                        ds_m = ds[m_ds]
                        ax_m, ay_m = ax_p[m_ds], ay_p[m_ds]
                        dx_m, dy_m = dx_p[m_ds], dy_p[m_ds]
                        cx_m, cy_m = cx_p[m_ds], cy_p[m_ds]
                        ex_m, ey_m = ex_p[m_ds], ey_p[m_ds]
                        el2_m = g.el2[ei][m_ds]
                        s0_m = (ax_m - cx_m) * nx_p[m_ds] + (ay_m - cy_m) * ny_p[m_ds]
                        for alvo in (encolher, -encolher):
                            t = (alvo - s0_m) / ds_m
                            ok_t = (0.0 < t) & (t < 1.0)
                            if np.any(ok_t):
                                tk = t[ok_t]
                                u = (
                                    (ax_m[ok_t] + tk * dx_m[ok_t] - cx_m[ok_t]) * ex_m[ok_t]
                                    + (ay_m[ok_t] + tk * dy_m[ok_t] - cy_m[ok_t]) * ey_m[ok_t]
                                ) / el2_m[ok_t]
                                ok_u = (-1e-11 <= u) & (u <= 1.0 + 1e-11)
                                if np.any(ok_u):
                                    seg_parts.append(si_d[ok_t][ok_u])
                                    t_parts.append(tk[ok_u])

        n_verts = len(g.vx)
        if encolher > 0.0 and n_verts > 0:
            step_v = max(1, _MAX_ELEMS_BLOCO // max(1, n_verts))
            for ini in range(0, n_g, step_v):
                sub_idx = g_idx[ini:ini + step_v]
                vmask = (
                    (g.vx[None, :] >= smin_x[sub_idx, None])
                    & (g.vx[None, :] <= smax_x[sub_idx, None])
                    & (g.vy[None, :] >= smin_y[sub_idx, None])
                    & (g.vy[None, :] <= smax_y[sub_idx, None])
                )
                svi_loc, vi = np.nonzero(vmask)
                if len(svi_loc) == 0:
                    continue
                svi = sub_idx[svi_loc]
                wx = ax[svi] - g.vx[vi]
                wy = ay[svi] - g.vy[vi]
                dx_v, dy_v, aa_v = dx[svi], dy[svi], aa[svi]
                bh = wx * dx_v + wy * dy_v
                disc = bh * bh - aa_v * (wx * wx + wy * wy - r2)
                m_v = disc >= 0.0
                if np.any(m_v):
                    svi_m = svi[m_v]
                    sq = np.sqrt(disc[m_v])
                    bh_v = bh[m_v]
                    aa_m = aa_v[m_v]
                    for t_cand in ((-bh_v - sq) / aa_m, (-bh_v + sq) / aa_m):
                        ok_tc = (0.0 < t_cand) & (t_cand < 1.0)
                        if np.any(ok_tc):
                            seg_parts.append(svi_m[ok_tc])
                            t_parts.append(t_cand[ok_tc])

    if not seg_parts:
        return tem_grupo, np.empty(0, dtype=np.intp), np.empty(0, dtype=float)
    seg_all = np.concatenate(seg_parts)
    t_all = np.concatenate(t_parts)
    ord_idx = np.lexsort((t_all, seg_all))
    return tem_grupo, seg_all[ord_idx], t_all[ord_idx]


def _dentro_grupos_vetorizado(
    mx: np.ndarray,
    my: np.ndarray,
    grupos: list[_GrupoPrep],
    encolher: float,
) -> np.ndarray:
    """Testa vetorizadamente se cada ponto medio (mx, my) esta dentro de algum grupo."""
    n_pts = len(mx)
    dentro = np.zeros(n_pts, dtype=bool)
    if n_pts == 0:
        return dentro
    pad_d = max(0.0, encolher) + _EPS
    eps2 = _EPS * _EPS

    for g in grupos:
        cand_mask = (~dentro) & (g.bbox[0] <= mx) & (mx <= g.bbox[2]) & (g.bbox[1] <= my) & (my <= g.bbox[3])
        if not np.any(cand_mask):
            continue
        idx_g = np.flatnonzero(cand_mask)
        px = mx[idx_g]
        py = my[idx_g]
        n_g = len(idx_g)
        paridade = np.zeros(n_g, dtype=np.int8)

        for rb, rx1, ry1, rx2, ry2 in g.rings:
            in_rb = (rb[0] <= px) & (px <= rb[2]) & (rb[1] <= py) & (py <= rb[3])
            if not np.any(in_rb):
                continue
            rb_idx = np.flatnonzero(in_rb)
            px_r = px[rb_idx]
            py_r = py[rb_idx]
            n_r = len(rb_idx)
            n_re = len(rx1)
            step_r = max(1, _MAX_ELEMS_BLOCO // max(1, n_re))
            for ini in range(0, n_r, step_r):
                px_s = px_r[ini:ini + step_r]
                py_s = py_r[ini:ini + step_r]
                cond = (ry1[None, :] > py_s[:, None]) != (ry2[None, :] > py_s[:, None])
                pi, ei = np.nonzero(cond)
                if len(pi) == 0:
                    continue
                y1c, y2c = ry1[ei], ry2[ei]
                x1c, x2c = rx1[ei], rx2[ei]
                cruzou = px_s[pi] < x1c + (py_s[pi] - y1c) * (x2c - x1c) / (y2c - y1c)
                if np.any(cruzou):
                    cont = np.bincount(pi[cruzou], minlength=len(px_s))
                    paridade[rb_idx[ini:ini + step_r]] ^= (cont & 1).astype(np.int8)

        idx_par = idx_g[paridade == 1]
        if len(idx_par) == 0:
            continue
        if len(g.cx) == 0:
            dentro[idx_par] = True
            continue

        px_p = mx[idx_par]
        py_p = my[idx_par]
        n_p = len(idx_par)
        d2_min = np.full(n_p, np.inf, dtype=float)
        n_ce = len(g.cx)
        step_c = max(1, _MAX_ELEMS_BLOCO // max(1, n_ce))
        for ini in range(0, n_p, step_c):
            px_s = px_p[ini:ini + step_c]
            py_s = py_p[ini:ini + step_c]
            cmask = (
                (g.emin_x[None, :] - pad_d <= px_s[:, None])
                & (px_s[:, None] <= g.emax_x[None, :] + pad_d)
                & (g.emin_y[None, :] - pad_d <= py_s[:, None])
                & (py_s[:, None] <= g.emax_y[None, :] + pad_d)
            )
            pi_c, ei_c = np.nonzero(cmask)
            if len(pi_c) == 0:
                continue
            cx_c, cy_c = g.cx[ei_c], g.cy[ei_c]
            ex_c, ey_c = g.ex[ei_c], g.ey[ei_c]
            u = np.clip(((px_s[pi_c] - cx_c) * ex_c + (py_s[pi_c] - cy_c) * ey_c) / g.el2[ei_c], 0.0, 1.0)
            dx_c = px_s[pi_c] - (cx_c + u * ex_c)
            dy_c = py_s[pi_c] - (cy_c + u * ey_c)
            d2_sub = d2_min[ini:ini + step_c]
            np.minimum.at(d2_sub, pi_c, dx_c * dx_c + dy_c * dy_c)

        if encolher <= 0.0:
            ok_dist = d2_min > eps2
        else:
            ok_dist = np.sqrt(d2_min) >= (encolher - _EPS)
        dentro[idx_par[ok_dist]] = True

    return dentro


def recortar_fora_dos_aneis(polilinhas, aneis, encolher: float = 5e-4):
    """Remove trechos dentro da uniao dos grupos (par-impar dentro de cada grupo, encolhida)."""
    aneis_list = list(aneis)
    grupos_raw = [aneis_list] if _eh_lista_plana(aneis_list) else aneis_list
    grupos = [gp for g in grupos_raw if (gp := _preparar_grupo(g)) is not None]
    pad = max(0.0, encolher) + 1e-5
    eps2 = _EPS * _EPS

    pols_pts: list[np.ndarray] = []
    segs_info: list[tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    ativos_idx: list[int] = []

    for poli in polilinhas:
        pts = np.asarray(poli, dtype=float)
        if len(pts) < 2:
            continue
        p_idx = len(pols_pts)
        pols_pts.append(pts)
        if not grupos:
            continue
        pmin_x, pmin_y = float(pts[:, 0].min()) - pad, float(pts[:, 1].min()) - pad
        pmax_x, pmax_y = float(pts[:, 0].max()) + pad, float(pts[:, 1].max()) + pad
        if not any(_sobrepoe(g.bbox, pmin_x, pmin_y, pmax_x, pmax_y) for g in grupos):
            continue

        d = pts[1:] - pts[:-1]
        aa_all = d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]
        valid_i = np.flatnonzero(aa_all > eps2)
        if len(valid_i) > 0:
            ativos_idx.append(p_idx)
            segs_info.append((p_idx, valid_i, d[valid_i, 0], d[valid_i, 1], aa_all[valid_i]))

    if not grupos:
        return [pts.copy() for pts in pols_pts]

    intervs_por_poli: dict[int, list[list[tuple[float, float]]]] = {}
    if segs_info:
        all_ax = np.concatenate([pols_pts[pi][vi, 0] for pi, vi, _, _, _ in segs_info])
        all_ay = np.concatenate([pols_pts[pi][vi, 1] for pi, vi, _, _, _ in segs_info])
        all_dx = np.concatenate([dx for _, _, dx, _, _ in segs_info])
        all_dy = np.concatenate([dy for _, _, _, dy, _ in segs_info])
        all_aa = np.concatenate([aa for _, _, _, _, aa in segs_info])
        all_bx = all_ax + all_dx
        all_by = all_ay + all_dy
        all_sl = np.sqrt(all_aa)
        all_smin_x = np.minimum(all_ax, all_bx) - pad
        all_smax_x = np.maximum(all_ax, all_bx) + pad
        all_smin_y = np.minimum(all_ay, all_by) - pad
        all_smax_y = np.maximum(all_ay, all_by) + pad

        n_tot = len(all_ax)
        intervs_seg: list[list[tuple[float, float]]] = [[(0.0, 1.0)] for _ in range(n_tot)]

        for b_ini in range(0, n_tot, _BLOCO_SEG):
            b_fim = min(n_tot, b_ini + _BLOCO_SEG)
            ax_b = all_ax[b_ini:b_fim]
            ay_b = all_ay[b_ini:b_fim]
            dx_b = all_dx[b_ini:b_fim]
            dy_b = all_dy[b_ini:b_fim]
            sl_b = all_sl[b_ini:b_fim]

            tem_g, seg_s, t_s = _cortes_bloco(
                ax_b, ay_b, dx_b, dy_b, all_aa[b_ini:b_fim], sl_b,
                all_smin_x[b_ini:b_fim], all_smin_y[b_ini:b_fim],
                all_smax_x[b_ini:b_fim], all_smax_y[b_ini:b_fim],
                grupos, encolher,
            )
            if not np.any(tem_g):
                continue

            sub_seg_list: list[int] = []
            sub_t0_list: list[float] = []
            sub_t1_list: list[float] = []

            if len(seg_s) > 0:
                cortes_unicos, cortes_pos = np.unique(seg_s, return_index=True)
                cortes_fim = np.empty(len(cortes_unicos), dtype=np.intp)
                cortes_fim[:-1] = cortes_pos[1:]
                cortes_fim[-1] = len(seg_s)
                mapa_cortes = dict(zip(cortes_unicos.tolist(), zip(cortes_pos.tolist(), cortes_fim.tolist())))
            else:
                mapa_cortes = {}

            for s_loc in np.flatnonzero(tem_g).tolist():
                rng_c = mapa_cortes.get(s_loc)
                if rng_c is None:
                    sub_seg_list.append(s_loc)
                    sub_t0_list.append(0.0)
                    sub_t1_list.append(1.0)
                else:
                    tol_t = min(_EPS, _EPS / max(1.0, float(sl_b[s_loc])))
                    unicos = [0.0]
                    for t_val in t_s[rng_c[0]:rng_c[1]].tolist():
                        if t_val - unicos[-1] > tol_t and 1.0 - t_val > tol_t:
                            unicos.append(t_val)
                    unicos.append(1.0)
                    for k in range(len(unicos) - 1):
                        sub_seg_list.append(s_loc)
                        sub_t0_list.append(unicos[k])
                        sub_t1_list.append(unicos[k + 1])
                intervs_seg[b_ini + s_loc] = []

            sub_seg = np.asarray(sub_seg_list, dtype=np.intp)
            sub_t0 = np.asarray(sub_t0_list, dtype=float)
            sub_t1 = np.asarray(sub_t1_list, dtype=float)
            tm = 0.5 * (sub_t0 + sub_t1)
            mx = ax_b[sub_seg] + tm * dx_b[sub_seg]
            my = ay_b[sub_seg] + tm * dy_b[sub_seg]

            dentro = _dentro_grupos_vetorizado(mx, my, grupos, encolher)
            for idx_k in np.flatnonzero(~dentro).tolist():
                s_glob = b_ini + int(sub_seg[idx_k])
                t0_k, t1_k = float(sub_t0[idx_k]), float(sub_t1[idx_k])
                iv = intervs_seg[s_glob]
                if iv and iv[-1][1] == t0_k:
                    iv[-1] = (iv[-1][0], t1_k)
                else:
                    iv.append((t0_k, t1_k))

        offset = 0
        for pi, vi, _, _, _ in segs_info:
            n_v = len(vi)
            intervs_por_poli[pi] = (vi, intervs_seg[offset:offset + n_v])
            offset += n_v

    saida: list[np.ndarray] = []
    for p_idx, pts in enumerate(pols_pts):
        info_p = intervs_por_poli.get(p_idx)
        if info_p is None:
            pmin_x, pmin_y = float(pts[:, 0].min()) - pad, float(pts[:, 1].min()) - pad
            pmax_x, pmax_y = float(pts[:, 0].max()) + pad, float(pts[:, 1].max()) + pad
            if not any(_sobrepoe(g.bbox, pmin_x, pmin_y, pmax_x, pmax_y) for g in grupos):
                saida.append(pts.copy())
            continue

        vi, ivs = info_p
        atual = None
        for idx_s, i in enumerate(vi.tolist()):
            interv = ivs[idx_s]
            ax, ay = float(pts[i, 0]), float(pts[i, 1])
            dx, dy = float(pts[i + 1, 0]) - ax, float(pts[i + 1, 1]) - ay
            for t0, t1 in interv:
                p0 = pts[i].copy() if t0 == 0.0 else np.array([ax + t0 * dx, ay + t0 * dy])
                p1 = pts[i + 1].copy() if t1 == 1.0 else np.array([ax + t1 * dx, ay + t1 * dy])
                if atual is not None and t0 == 0.0:
                    atual.append(p1)
                else:
                    if atual is not None:
                        saida.append(np.vstack(atual))
                    atual = [p0, p1]
            if (not interv or interv[-1][1] != 1.0) and atual is not None:
                saida.append(np.vstack(atual))
                atual = None
        if atual is not None:
            saida.append(np.vstack(atual))
    return saida
