# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recorte de polilinhas fora da regiao dos aneis da secao (T19j2b)."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from obim_geometria.aneis import _EPS, _ponto_no_anel_arr


@dataclass
class _GrupoPrep:
    bbox: tuple[float, float, float, float]
    rings: list[tuple[tuple[float, float, float, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]]
    cx: np.ndarray
    cy: np.ndarray
    ex_pt: np.ndarray
    ey_pt: np.ndarray
    ex: np.ndarray
    ey: np.ndarray
    el2: np.ndarray
    e_len: np.ndarray
    nx: np.ndarray
    ny: np.ndarray
    emin_x: np.ndarray
    emax_x: np.ndarray
    emin_y: np.ndarray
    emax_y: np.ndarray
    vx: np.ndarray
    vy: np.ndarray


def _preparar_grupo(grupo) -> _GrupoPrep | None:
    rings_data = []
    xs1, ys1, xs2, ys2, vxs, vys = [], [], [], [], [], []
    for a in grupo:
        p = np.asarray(a, dtype=float)
        if p.ndim != 2 or len(p) < 3:
            continue
        if np.allclose(p[0], p[-1], atol=_EPS, rtol=0.0):
            p = p[:-1]
        if len(p) < 3:
            continue
        rx1 = p[:, 0].copy()
        ry1 = p[:, 1].copy()
        rx2 = np.roll(rx1, -1)
        ry2 = np.roll(ry1, -1)
        r_bbox = (float(rx1.min()), float(ry1.min()), float(rx1.max()), float(ry1.max()))
        rings_data.append((r_bbox, rx1, ry1, rx2, ry2))
        xs1.append(rx1)
        ys1.append(ry1)
        xs2.append(rx2)
        ys2.append(ry2)
        vxs.append(rx1)
        vys.append(ry1)

    if not rings_data:
        return None

    cx_all = np.concatenate(xs1)
    cy_all = np.concatenate(ys1)
    ex_pt_all = np.concatenate(xs2)
    ey_pt_all = np.concatenate(ys2)
    ex_all = ex_pt_all - cx_all
    ey_all = ey_pt_all - cy_all
    el2_all = ex_all * ex_all + ey_all * ey_all
    valid = el2_all > 0.0

    cx = cx_all[valid]
    cy = cy_all[valid]
    ex_pt = ex_pt_all[valid]
    ey_pt = ey_pt_all[valid]
    ex = ex_all[valid]
    ey = ey_all[valid]
    el2 = el2_all[valid]
    e_len = np.sqrt(el2)
    nx = -ey / e_len
    ny = ex / e_len
    emin_x = np.minimum(cx, ex_pt)
    emax_x = np.maximum(cx, ex_pt)
    emin_y = np.minimum(cy, ey_pt)
    emax_y = np.maximum(cy, ey_pt)

    vx = np.concatenate(vxs)
    vy = np.concatenate(vys)
    g_bbox = (
        min(rb[0] for rb, *_ in rings_data),
        min(rb[1] for rb, *_ in rings_data),
        max(rb[2] for rb, *_ in rings_data),
        max(rb[3] for rb, *_ in rings_data),
    )
    return _GrupoPrep(
        bbox=g_bbox,
        rings=rings_data,
        cx=cx,
        cy=cy,
        ex_pt=ex_pt,
        ey_pt=ey_pt,
        ex=ex,
        ey=ey,
        el2=el2,
        e_len=e_len,
        nx=nx,
        ny=ny,
        emin_x=emin_x,
        emax_x=emax_x,
        emin_y=emin_y,
        emax_y=emax_y,
        vx=vx,
        vy=vy,
    )


def _cortes_no_segmento(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    smin_x: float,
    smin_y: float,
    smax_x: float,
    smax_y: float,
    grupos_ativos: list[_GrupoPrep],
    encolher: float,
) -> list[float]:
    dx, dy = bx - ax, by - ay
    aa = dx * dx + dy * dy
    seg_len, ts, r2 = math.sqrt(aa), [0.0, 1.0], encolher * encolher

    for g in grupos_ativos:
        if len(g.cx) > 0:
            emask = (
                (g.emin_x <= smax_x)
                & (g.emax_x >= smin_x)
                & (g.emin_y <= smax_y)
                & (g.emax_y >= smin_y)
            )
            if np.any(emask):
                cx = g.cx[emask]
                cy = g.cy[emask]
                ex_pt = g.ex_pt[emask]
                ey_pt = g.ey_pt[emask]
                ex = g.ex[emask]
                ey = g.ey[emask]
                el2 = g.el2[emask]
                e_len = g.e_len[emask]

                denom = dx * ey - dy * ex
                acx = cx - ax
                acy = cy - ay
                m_np = np.abs(denom) > (_EPS * seg_len * e_len)
                if np.any(m_np):
                    d_np = denom[m_np]
                    t = (acx[m_np] * ey[m_np] - acy[m_np] * ex[m_np]) / d_np
                    u = (acx[m_np] * dy - acy[m_np] * dx) / d_np
                    ok = (-1e-11 <= u) & (u <= 1.0 + 1e-11) & (0.0 < t) & (t < 1.0)
                    if np.any(ok):
                        ts.extend(t[ok].tolist())

                m_col = (~m_np) & (np.abs(acx * dy - acy * dx) <= 1e-11 * seg_len)
                if np.any(m_col):
                    t1 = ((cx[m_col] - ax) * dx + (cy[m_col] - ay) * dy) / aa
                    t2 = ((ex_pt[m_col] - ax) * dx + (ey_pt[m_col] - ay) * dy) / aa
                    ok1 = (0.0 < t1) & (t1 < 1.0)
                    ok2 = (0.0 < t2) & (t2 < 1.0)
                    if np.any(ok1):
                        ts.extend(t1[ok1].tolist())
                    if np.any(ok2):
                        ts.extend(t2[ok2].tolist())

                if encolher > 0.0:
                    nx = g.nx[emask]
                    ny = g.ny[emask]
                    s0 = (ax - cx) * nx + (ay - cy) * ny
                    ds = dx * nx + dy * ny
                    m_ds = np.abs(ds) > (_EPS * seg_len)
                    if np.any(m_ds):
                        ds_m = ds[m_ds]
                        s0_m = s0[m_ds]
                        cx_m, cy_m = cx[m_ds], cy[m_ds]
                        ex_m, ey_m, el2_m = ex[m_ds], ey[m_ds], el2[m_ds]
                        for alvo in (encolher, -encolher):
                            t = (alvo - s0_m) / ds_m
                            ok_t = (0.0 < t) & (t < 1.0)
                            if np.any(ok_t):
                                tk = t[ok_t]
                                u = (
                                    (ax + tk * dx - cx_m[ok_t]) * ex_m[ok_t]
                                    + (ay + tk * dy - cy_m[ok_t]) * ey_m[ok_t]
                                ) / el2_m[ok_t]
                                ok_u = (-1e-11 <= u) & (u <= 1.0 + 1e-11)
                                if np.any(ok_u):
                                    ts.extend(tk[ok_u].tolist())

        if encolher > 0.0 and len(g.vx) > 0:
            vmask = (g.vx >= smin_x) & (g.vx <= smax_x) & (g.vy >= smin_y) & (g.vy <= smax_y)
            if np.any(vmask):
                wx = ax - g.vx[vmask]
                wy = ay - g.vy[vmask]
                bh = wx * dx + wy * dy
                disc = bh * bh - aa * (wx * wx + wy * wy - r2)
                m_v = disc >= 0.0
                if np.any(m_v):
                    sq = np.sqrt(disc[m_v])
                    bh_v = bh[m_v]
                    for t_cand in ((-bh_v - sq) / aa, (-bh_v + sq) / aa):
                        ok_v = (0.0 < t_cand) & (t_cand < 1.0)
                        if np.any(ok_v):
                            ts.extend(t_cand[ok_v].tolist())

    ts.sort()
    tol_t, unicos = min(_EPS, _EPS / max(1.0, seg_len)), [0.0]
    for t in ts[1:-1]:
        if t - unicos[-1] > tol_t and 1.0 - t > tol_t:
            unicos.append(t)
    return unicos + [1.0]


def _dentro_grupo(px: float, py: float, g: _GrupoPrep, encolher: float) -> bool:
    gb = g.bbox
    if px < gb[0] or px > gb[2] or py < gb[1] or py > gb[3]:
        return False

    paridade = 0
    for rb, rx1, ry1, rx2, ry2 in g.rings:
        if rb[0] <= px <= rb[2] and rb[1] <= py <= rb[3]:
            if _ponto_no_anel_arr(px, py, rx1, ry1, rx2, ry2):
                paridade ^= 1
    if paridade == 0:
        return False

    if len(g.cx) == 0:
        return True
    pad_d = max(0.0, encolher) + _EPS
    cmask = (
        (g.emin_x - pad_d <= px)
        & (px <= g.emax_x + pad_d)
        & (g.emin_y - pad_d <= py)
        & (py <= g.emax_y + pad_d)
    )
    if not np.any(cmask):
        return True
    cx_c, cy_c = g.cx[cmask], g.cy[cmask]
    ex_c, ey_c = g.ex[cmask], g.ey[cmask]
    u = np.clip(((px - cx_c) * ex_c + (py - cy_c) * ey_c) / g.el2[cmask], 0.0, 1.0)
    dx_c = px - (cx_c + u * ex_c)
    dy_c = py - (cy_c + u * ey_c)
    d2 = float(np.min(dx_c * dx_c + dy_c * dy_c))
    return d2 > _EPS * _EPS if encolher <= 0.0 else math.sqrt(d2) >= encolher - _EPS


def recortar_fora_dos_aneis(polilinhas, aneis, encolher: float = 5e-4):
    """Remove trechos dentro da uniao dos grupos (par-impar dentro de cada grupo, encolhida)."""
    aneis_list = list(aneis)
    if not aneis_list:
        grupos_raw = []
    elif isinstance(aneis_list[0], np.ndarray) and aneis_list[0].ndim == 2:
        grupos_raw = [aneis_list]
    else:
        grupos_raw = aneis_list

    grupos = [gp for g in grupos_raw if (gp := _preparar_grupo(g)) is not None]
    pad = max(0.0, encolher) + 1e-5

    saida = []
    for poli in polilinhas:
        pts = np.asarray(poli, dtype=float)
        if len(pts) < 2:
            continue
        if not grupos:
            saida.append(pts.copy())
            continue

        pmin_x, pmin_y = float(pts[:, 0].min()) - pad, float(pts[:, 1].min()) - pad
        pmax_x, pmax_y = float(pts[:, 0].max()) + pad, float(pts[:, 1].max()) + pad
        grupos_poli = [
            g for g in grupos
            if g.bbox[0] <= pmax_x and g.bbox[2] >= pmin_x and g.bbox[1] <= pmax_y and g.bbox[3] >= pmin_y
        ]
        if not grupos_poli:
            saida.append(pts.copy())
            continue

        atual = None
        for i in range(len(pts) - 1):
            ax, ay, bx, by = float(pts[i, 0]), float(pts[i, 1]), float(pts[i + 1, 0]), float(pts[i + 1, 1])
            dx, dy = bx - ax, by - ay
            if dx * dx + dy * dy <= _EPS * _EPS:
                continue

            smin_x = (ax if ax < bx else bx) - pad
            smax_x = (bx if ax < bx else ax) + pad
            smin_y = (ay if ay < by else by) - pad
            smax_y = (by if ay < by else ay) + pad
            grupos_seg = [
                g for g in grupos_poli
                if g.bbox[0] <= smax_x and g.bbox[2] >= smin_x and g.bbox[1] <= smax_y and g.bbox[3] >= smin_y
            ]

            if not grupos_seg:
                interv = [(0.0, 1.0)]
            else:
                ts = _cortes_no_segmento(ax, ay, bx, by, smin_x, smin_y, smax_x, smax_y, grupos_seg, encolher)
                interv = []
                for t0, t1 in zip(ts, ts[1:]):
                    mx = ax + 0.5 * (t0 + t1) * dx
                    my = ay + 0.5 * (t0 + t1) * dy
                    if not any(_dentro_grupo(mx, my, g, encolher) for g in grupos_seg):
                        if interv and interv[-1][1] == t0:
                            interv[-1] = (interv[-1][0], t1)
                        else:
                            interv.append((t0, t1))

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
