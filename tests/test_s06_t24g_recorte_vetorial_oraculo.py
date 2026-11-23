# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24g: aceleracao vetorial de `recortar_fora_dos_aneis` sem mudanca de resultado.

Modulo alvo (NAO editar este oraculo; editar apenas `geometria/obim_geometria/recorte.py`):
    `obim_geometria.recorte.recortar_fora_dos_aneis(polilinhas, aneis, encolher=5e-4)`

Contrato verificado:
1. Referencia congelada (`_referencia_recortar`): copia literal e autocontida da
   implementacao original de `recorte.py` (com `_REF_EPS` e `_ref_ponto_no_anel_arr`).
2. Equivalencia numerica e estrutural em centenas de casos com semente fixa:
   mesmo numero de polilinhas, mesmo numero de pontos por polilinha e
   `np.allclose(..., rtol=0.0, atol=1e-9)`.
3. Desempenho relativo no mesmo processo: mediana de 3 rodadas intercaladas com
   `time.perf_counter()` na cena sintetica grande (~30 aneis em 6 grupos,
   400 polilinhas x 60 pontos), exigindo tempo novo <= 40% da referencia.
4. Nao mutacao das entradas, independencia de memoria da saida, determinismo
   exato e pico de memoria < 300 MiB (`tracemalloc`) na cena grande.
5. Mutantes cirurgicos com valores esperados a mao cobrindo defeitos plausiveis.
"""
from __future__ import annotations

from collections import namedtuple
import gc
import math
import statistics
import time
import tracemalloc

import numpy as np
import pytest

from obim_geometria.recorte import recortar_fora_dos_aneis


# ==============================================================================
# (1) COPIA LITERAL DA IMPLEMENTACAO ATUAL COMO REFERENCIA AUTOCONTIDA
#     (nao importa nada de obim_geometria.recorte nem de obim_geometria.aneis)
# ==============================================================================

_REF_EPS = 1e-12


def _ref_ponto_no_anel_arr(
    px: float,
    py: float,
    x1: np.ndarray,
    y1: np.ndarray,
    x2: np.ndarray,
    y2: np.ndarray,
) -> bool:
    cond = (y1 > py) != (y2 > py)
    if not np.any(cond):
        return False
    y1c, y2c = y1[cond], y2[cond]
    x1c, x2c = x1[cond], x2[cond]
    return (int(np.count_nonzero(px < x1c + (py - y1c) * (x2c - x1c) / (y2c - y1c))) & 1) == 1


_RefGrupoPrep = namedtuple(
    "_RefGrupoPrep",
    "bbox rings cx cy ex_pt ey_pt ex ey el2 e_len nx ny emin_x emax_x emin_y emax_y vx vy",
)


def _ref_sobrepoe(bb: tuple[float, float, float, float], x0: float, y0: float, x1: float, y1: float) -> bool:
    return bb[0] <= x1 and bb[2] >= x0 and bb[1] <= y1 and bb[3] >= y0


def _ref_preparar_grupo(grupo) -> _RefGrupoPrep | None:
    rings_data = []
    for a in grupo:
        p = np.asarray(a, dtype=float)
        if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3:
            raise ValueError(f"Anel invalido: shape {p.shape}")
        if np.allclose(p[0], p[-1], atol=_REF_EPS, rtol=0.0):
            p = p[:-1]
        d0 = (len(p) >= 3) and (np.max(np.abs(p - p[0]), axis=1) > _REF_EPS)
        if not np.any(d0) or not np.any(d0 & (np.max(np.abs(p - p[np.argmax(d0)]), axis=1) > _REF_EPS)):
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
    return _RefGrupoPrep(
        g_bbox, rings_data, cx, cy, ex_pt, ey_pt, ex, ey, el2, e_len, -ey / e_len, ex / e_len,
        np.minimum(cx, ex_pt), np.maximum(cx, ex_pt), np.minimum(cy, ey_pt), np.maximum(cy, ey_pt), vx, vy,
    )


def _ref_cortes_no_segmento(
    ax: float, ay: float, bx: float, by: float,
    smin_x: float, smin_y: float, smax_x: float, smax_y: float,
    grupos_ativos: list[_RefGrupoPrep], encolher: float,
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
                m_np = np.abs(denom) > (_REF_EPS * seg_len * e_len)
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
                    m_ds = np.abs(ds) > (_REF_EPS * seg_len)
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
    tol_t, unicos = min(_REF_EPS, _REF_EPS / max(1.0, seg_len)), [0.0]
    for t in ts[1:-1]:
        if t - unicos[-1] > tol_t and 1.0 - t > tol_t:
            unicos.append(t)
    return unicos + [1.0]


def _ref_dentro_grupo(px: float, py: float, g: _RefGrupoPrep, encolher: float) -> bool:
    if not _ref_sobrepoe(g.bbox, px, py, px, py):
        return False
    paridade = 0
    for rb, rx1, ry1, rx2, ry2 in g.rings:
        if _ref_sobrepoe(rb, px, py, px, py) and _ref_ponto_no_anel_arr(px, py, rx1, ry1, rx2, ry2):
            paridade ^= 1
    if paridade == 0:
        return False
    if len(g.cx) == 0:
        return True

    pad_d = max(0.0, encolher) + _REF_EPS
    cmask = (g.emin_x - pad_d <= px) & (px <= g.emax_x + pad_d) & (g.emin_y - pad_d <= py) & (py <= g.emax_y + pad_d)
    if not np.any(cmask):
        return True
    cx_c, cy_c, ex_c, ey_c = g.cx[cmask], g.cy[cmask], g.ex[cmask], g.ey[cmask]
    u = np.clip(((px - cx_c) * ex_c + (py - cy_c) * ey_c) / g.el2[cmask], 0.0, 1.0)
    dx_c, dy_c = px - (cx_c + u * ex_c), py - (cy_c + u * ey_c)
    d2 = float(np.min(dx_c * dx_c + dy_c * dy_c))
    return d2 > _REF_EPS * _REF_EPS if encolher <= 0.0 else math.sqrt(d2) >= encolher - _REF_EPS


def _ref_eh_lista_plana(aneis_list: list) -> bool:
    p0 = aneis_list[0] if aneis_list else None
    if isinstance(p0, np.ndarray):
        return p0.ndim == 2
    pt = p0[0] if isinstance(p0, (list, tuple)) and p0 else None
    return (isinstance(pt, (list, tuple, np.ndarray)) and getattr(pt, "ndim", 1) == 1 and len(pt) == 2
            and all(isinstance(v, (int, float, np.number)) and not isinstance(v, bool) for v in pt))


def _referencia_recortar(polilinhas, aneis, encolher: float = 5e-4):
    """Copia literal da implementacao original de `recortar_fora_dos_aneis`."""
    aneis_list = list(aneis)
    grupos_raw = [aneis_list] if _ref_eh_lista_plana(aneis_list) else aneis_list
    grupos = [gp for g in grupos_raw if (gp := _ref_preparar_grupo(g)) is not None]
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
        grupos_poli = [g for g in grupos if _ref_sobrepoe(g.bbox, pmin_x, pmin_y, pmax_x, pmax_y)]
        if not grupos_poli:
            saida.append(pts.copy())
            continue

        atual = None
        for i in range(len(pts) - 1):
            ax, ay, bx, by = float(pts[i, 0]), float(pts[i, 1]), float(pts[i + 1, 0]), float(pts[i + 1, 1])
            dx, dy = bx - ax, by - ay
            if dx * dx + dy * dy <= _REF_EPS * _REF_EPS:
                continue

            smin_x, smax_x = (ax - pad, bx + pad) if ax < bx else (bx - pad, ax + pad)
            smin_y, smax_y = (ay - pad, by + pad) if ay < by else (by - pad, ay + pad)
            grupos_seg = [g for g in grupos_poli if _ref_sobrepoe(g.bbox, smin_x, smin_y, smax_x, smax_y)]

            if not grupos_seg:
                interv = [(0.0, 1.0)]
            else:
                ts = _ref_cortes_no_segmento(ax, ay, bx, by, smin_x, smin_y, smax_x, smax_y, grupos_seg, encolher)
                interv = []
                for t0, t1 in zip(ts, ts[1:]):
                    mx, my = ax + 0.5 * (t0 + t1) * dx, ay + 0.5 * (t0 + t1) * dy
                    if not any(_ref_dentro_grupo(mx, my, g, encolher) for g in grupos_seg):
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


# ==============================================================================
# HELPERS DE COMPARACAO E GERACAO DE CENAS DETERMINISTICAS
# ==============================================================================

_TOL = 1e-9
_ENCOLHERES = (0.0, 5e-4, 1e-2)


def _assert_igual_ref(res, ref, *, atol: float = _TOL, msg: str = "") -> None:
    assert isinstance(res, list), f"{msg}: saida deve ser list, veio {type(res)}"
    assert len(res) == len(ref), f"{msg}: qtd polilinhas {len(res)} != ref {len(ref)}"
    for idx, (r, e) in enumerate(zip(res, ref)):
        assert isinstance(r, np.ndarray), f"{msg} trecho {idx}: esperado ndarray, veio {type(r)}"
        assert r.ndim == 2 and r.shape[1] == 2, f"{msg} trecho {idx}: shape invalido {r.shape}"
        assert r.shape == e.shape, f"{msg} trecho {idx}: qtd pontos {r.shape} != ref {e.shape}"
        assert np.allclose(r, e, rtol=0.0, atol=atol), (
            f"{msg} trecho {idx}: max_diff={float(np.max(np.abs(r - e))):.3e} > {atol}"
        )


def _assert_trechos_exatos(res, esperado, *, atol: float = _TOL, msg: str = "") -> None:
    esperado_arr = [np.asarray(e, dtype=float) for e in esperado]
    _assert_igual_ref(res, esperado_arr, atol=atol, msg=msg)


def _rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    horario: bool = False,
    fechado: bool = False,
) -> np.ndarray:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if horario:
        pts = list(reversed(pts))
    if fechado:
        pts.append(pts[0])
    return np.array(pts, dtype=float)


def _poligono_L(
    x0: float,
    y0: float,
    w: float,
    h: float,
    *,
    horario: bool = False,
    fechado: bool = False,
) -> np.ndarray:
    pts = [
        (x0, y0),
        (x0 + w, y0),
        (x0 + w, y0 + 0.5 * h),
        (x0 + 0.5 * w, y0 + 0.5 * h),
        (x0 + 0.5 * w, y0 + h),
        (x0, y0 + h),
    ]
    if horario:
        pts = list(reversed(pts))
    if fechado:
        pts.append(pts[0])
    return np.array(pts, dtype=float)


def _poligono_estrelado(
    rng: np.random.Generator,
    cx: float,
    cy: float,
    r_min: float,
    r_max: float,
    n_verts: int,
    *,
    horario: bool = False,
    fechado: bool = False,
) -> np.ndarray:
    ang = np.linspace(0.0, 2.0 * np.pi, n_verts, endpoint=False)
    ang = ang + rng.uniform(0.0, 2.0 * np.pi)
    raios = rng.uniform(r_min, r_max, size=n_verts)
    pts = np.column_stack([cx + raios * np.cos(ang), cy + raios * np.sin(ang)])
    if horario:
        pts = pts[::-1].copy()
    if fechado:
        pts = np.vstack([pts, pts[0:1]])
    return pts


def _transladar_pols(pols: list[np.ndarray], ox: float, oy: float) -> list[np.ndarray]:
    if ox == 0.0 and oy == 0.0:
        return [p.copy() for p in pols]
    off = np.array([ox, oy], dtype=float)
    return [p + off for p in pols]


def _transladar_aneis(aneis, ox: float, oy: float, *, plano: bool):
    if ox == 0.0 and oy == 0.0:
        if plano:
            return [np.asarray(a, dtype=float).copy() for a in aneis]
        return [[np.asarray(a, dtype=float).copy() for a in g] for g in aneis]
    off = np.array([ox, oy], dtype=float)
    if plano:
        return [np.asarray(a, dtype=float) + off for a in aneis]
    return [[np.asarray(a, dtype=float) + off for a in g] for g in aneis]
