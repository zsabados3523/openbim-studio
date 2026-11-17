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


def recortar_fora_dos_aneis(polilinhas, aneis, encolher: float = 5e-4):
    """Remove trechos dentro da uniao dos grupos (par-impar dentro de cada grupo, encolhida)."""
    aneis_list = list(aneis)
    grupos_raw = [aneis_list] if _eh_lista_plana(aneis_list) else aneis_list
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
        grupos_poli = [g for g in grupos if _sobrepoe(g.bbox, pmin_x, pmin_y, pmax_x, pmax_y)]
        if not grupos_poli:
            saida.append(pts.copy())
            continue

        atual = None
        for i in range(len(pts) - 1):
            ax, ay, bx, by = float(pts[i, 0]), float(pts[i, 1]), float(pts[i + 1, 0]), float(pts[i + 1, 1])
            dx, dy = bx - ax, by - ay
            if dx * dx + dy * dy <= _EPS * _EPS:
                continue

            smin_x, smax_x = (ax - pad, bx + pad) if ax < bx else (bx - pad, ax + pad)
            smin_y, smax_y = (ay - pad, by + pad) if ay < by else (by - pad, ay + pad)
            grupos_seg = [g for g in grupos_poli if _sobrepoe(g.bbox, smin_x, smin_y, smax_x, smax_y)]

            if not grupos_seg:
                interv = [(0.0, 1.0)]
            else:
                ts = _cortes_no_segmento(ax, ay, bx, by, smin_x, smin_y, smax_x, smax_y, grupos_seg, encolher)
                interv = []
                for t0, t1 in zip(ts, ts[1:]):
                    mx, my = ax + 0.5 * (t0 + t1) * dx, ay + 0.5 * (t0 + t1) * dy
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
