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


def _gerar_polilinha_aleatoria(
    rng: np.random.Generator,
    n_pts: int,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    step_range: tuple[float, float] = (0.3, 2.5),
) -> np.ndarray:
    x0 = float(rng.uniform(*xlim))
    y0 = float(rng.uniform(*ylim))
    if n_pts <= 1:
        return np.array([[x0, y0]], dtype=float)[:n_pts]
    if n_pts == 2:
        x1 = float(rng.uniform(*xlim))
        y1 = float(rng.uniform(*ylim))
        return np.array([[x0, y0], [x1, y1]], dtype=float)
    ang0 = float(rng.uniform(0.0, 2.0 * np.pi))
    steps = rng.uniform(step_range[0], step_range[1], size=n_pts - 1)
    dangs = rng.normal(0.0, 0.55, size=n_pts - 1)
    angs = ang0 + np.cumsum(dangs)
    xs = np.empty(n_pts, dtype=float)
    ys = np.empty(n_pts, dtype=float)
    xs[0], ys[0] = x0, y0
    xs[1:] = x0 + np.cumsum(steps * np.cos(angs))
    ys[1:] = y0 + np.cumsum(steps * np.sin(angs))
    return np.column_stack([xs, ys])


def _gerar_cena_grande(seed: int = 20260424) -> tuple[list[np.ndarray], list[list[np.ndarray]]]:
    """Cena sintetica grande: 30 aneis em 6 grupos, 400 polilinhas com 60 pontos cada."""
    rng = np.random.default_rng(seed)
    grupos: list[list[np.ndarray]] = []
    # 6 grupos em grade 3x2 com leve sobreposicao entre vizinhos; cada grupo tem 5 aneis = 30 aneis
    centros = [
        (10.0, 10.0), (26.0, 10.0), (42.0, 10.0),
        (10.0, 26.0), (26.0, 26.0), (42.0, 26.0),
    ]
    for g_idx, (gx, gy) in enumerate(centros):
        aneis_g: list[np.ndarray] = []
        # Anel externo poligonal (12 vertices)
        ang = np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False)
        raios = 8.4 + 0.7 * np.sin(3.0 * ang + g_idx)
        ext = np.column_stack([gx + raios * np.cos(ang), gy + raios * np.sin(ang)])
        aneis_g.append(ext)
        # 3 furos internos (retangulos e octogonos)
        desloc_furos = [(-3.2, -3.0), (3.2, -3.0), (0.0, 3.2)]
        for f_idx, (dx, dy) in enumerate(desloc_furos):
            if f_idx == 0:
                furo = _rect(gx + dx - 1.6, gy + dy - 1.4, gx + dx + 1.6, gy + dy + 1.4, horario=True)
            else:
                ang_f = np.linspace(0.0, 2.0 * np.pi, 8, endpoint=False)[::-1]
                rf = 1.5 + 0.15 * np.cos(2.0 * ang_f + f_idx)
                furo = np.column_stack([gx + dx + rf * np.cos(ang_f), gy + dy + rf * np.sin(ang_f)])
            aneis_g.append(furo)
        # 1 ilha dentro do primeiro furo (exerce par-impar de 3 niveis)
        ilha = _rect(gx - 3.2 - 0.6, gy - 3.0 - 0.5, gx - 3.2 + 0.6, gy - 3.0 + 0.5, horario=False)
        aneis_g.append(ilha)
        grupos.append(aneis_g)

    assert len(grupos) == 6
    assert sum(len(g) for g in grupos) == 30

    polilinhas: list[np.ndarray] = []
    for _ in range(400):
        polilinhas.append(_gerar_polilinha_aleatoria(rng, 60, (-5.0, 58.0), (-5.0, 42.0), (0.35, 1.6)))
    return polilinhas, grupos


# ==============================================================================
# (2) TESTES DE EQUIVALENCIA (CENTENAS DE CASOS COM SEMENTE FIXA)
# ==============================================================================


def test_equivalencia_lote_aneis_retangulares_e_poligonais():
    """120 casos com aneis retangulares, poligonais, L, horarios/anti-horarios, abertos/fechados."""
    rng = np.random.default_rng(1001)
    for caso in range(120):
        encolher = _ENCOLHERES[caso % len(_ENCOLHERES)]
        formato_plano = (caso % 2 == 0)
        n_aneis = int(rng.integers(1, 5))
        aneis_lista = []
        for k in range(n_aneis):
            cx, cy = float(rng.uniform(0.0, 12.0)), float(rng.uniform(0.0, 12.0))
            horario = bool(rng.integers(0, 2))
            fechado = bool(rng.integers(0, 2))
            tipo = (caso + k) % 3
            if tipo == 0:
                w, h = float(rng.uniform(1.0, 4.5)), float(rng.uniform(1.0, 4.5))
                aneis_lista.append(_rect(cx, cy, cx + w, cy + h, horario=horario, fechado=fechado))
            elif tipo == 1:
                aneis_lista.append(_poligono_L(cx, cy, float(rng.uniform(1.5, 4.0)), float(rng.uniform(1.5, 4.0)), horario=horario, fechado=fechado))
            else:
                n_v = int(rng.integers(5, 13))
                aneis_lista.append(_poligono_estrelado(rng, cx, cy, 0.8, 3.0, n_v, horario=horario, fechado=fechado))

        aneis_in = aneis_lista if formato_plano else [[a] for a in aneis_lista]
        n_pols = int(rng.integers(2, 7))
        pols = [
            _gerar_polilinha_aleatoria(rng, int(rng.integers(2, 18)), (-2.0, 16.0), (-2.0, 16.0), (0.4, 3.0))
            for _ in range(n_pols)
        ]

        ref = _referencia_recortar(pols, aneis_in, encolher=encolher)
        res = recortar_fora_dos_aneis(pols, aneis_in, encolher=encolher)
        _assert_igual_ref(res, ref, msg=f"caso={caso} encolher={encolher} plano={formato_plano}")


def test_equivalencia_grupos_com_furos_e_ilhas():
    """60 casos com anel externo, multiplos furos e ilhas internas (par-impar multinivel)."""
    rng = np.random.default_rng(2002)
    for caso in range(60):
        encolher = _ENCOLHERES[caso % len(_ENCOLHERES)]
        n_grupos = int(rng.integers(1, 4))
        grupos = []
        for g in range(n_grupos):
            gx, gy = float(g * 12.0), float((g % 2) * 4.0)
            ext = _rect(gx, gy, gx + 10.0, gy + 10.0, horario=bool(rng.integers(0, 2)))
            furo1 = _rect(gx + 1.2, gy + 1.2, gx + 4.8, gy + 4.8, horario=bool(rng.integers(0, 2)))
            ilha1 = _rect(gx + 2.2, gy + 2.2, gx + 3.8, gy + 3.8, horario=bool(rng.integers(0, 2)))
            furo2 = _poligono_estrelado(rng, gx + 7.4, gy + 6.8, 0.9, 1.8, 7, horario=True)
            grupo = [ext, furo1, ilha1, furo2]
            grupos.append(grupo)

        aneis_in = grupos[0] if (n_grupos == 1 and caso % 2 == 0) else grupos
        pols = [
            _gerar_polilinha_aleatoria(rng, int(rng.integers(2, 22)), (-2.0, n_grupos * 12.0 + 2.0), (-2.0, 16.0))
            for _ in range(5)
        ]

        ref = _referencia_recortar(pols, aneis_in, encolher=encolher)
        res = recortar_fora_dos_aneis(pols, aneis_in, encolher=encolher)
        _assert_igual_ref(res, ref, msg=f"furos caso={caso} encolher={encolher}")


def test_equivalencia_grupos_sobrepostos_vs_plano():
    """60 casos de aneis sobrepostos: uniao entre grupos vs par-impar em formato plano."""
    rng = np.random.default_rng(3003)
    for caso in range(60):
        encolher = _ENCOLHERES[caso % len(_ENCOLHERES)]
        # 3 aneis com forte sobreposicao mutua
        a1 = _rect(0.0, 0.0, 5.0, 4.0)
        dx2, dy2 = float(rng.uniform(1.0, 3.5)), float(rng.uniform(-1.0, 2.0))
        a2 = _rect(dx2, dy2, dx2 + 5.0, dy2 + 4.0)
        a3 = _poligono_estrelado(rng, 3.5, 2.2, 1.2, 3.2, 6)
        furo_a1 = _rect(1.0, 1.0, 3.2, 3.0, horario=True)

        grupos = [[a1, furo_a1], [a2], [a3]]
        plano = [a1, furo_a1, a2, a3]
        pols = [
            _gerar_polilinha_aleatoria(rng, int(rng.integers(2, 16)), (-2.0, 10.0), (-2.0, 8.0))
            for _ in range(4)
        ]

        for nome, aneis_in in (("grupos", grupos), ("plano", plano)):
            ref = _referencia_recortar(pols, aneis_in, encolher=encolher)
            res = recortar_fora_dos_aneis(pols, aneis_in, encolher=encolher)
            _assert_igual_ref(res, ref, msg=f"sobreposto {nome} caso={caso} encolher={encolher}")


def test_equivalencia_tangentes_vertices_e_colineares():
    """Casos cirurgicos e combinatorios de tangencia a vertices e colinearidade com arestas."""
    rng = np.random.default_rng(4004)
    ret = _rect(0.0, 0.0, 4.0, 2.0)
    quad = _rect(0.0, 0.0, 4.0, 4.0)
    forma_l = _poligono_L(0.0, 0.0, 4.0, 4.0)
    com_furo = [_rect(0.0, 0.0, 10.0, 10.0), _rect(3.0, 3.0, 7.0, 7.0, horario=True)]

    cenarios = [
        ("colinear_ext_inf", [ret], [np.array([(-1, 0), (5, 0)], float), np.array([(1, 0), (3, 0)], float)]),
        ("colinear_ext_dir", [ret], [np.array([(4, -1), (4, 3)], float), np.array([(4, 0), (4, 2)], float)]),
        ("colinear_ext_com_dobras", [ret], [np.array([(-1, 0), (0, 0), (2, 0), (4, 0), (4, 2), (5, 2)], float)]),
        ("colinear_aresta_furo", com_furo, [np.array([(1, 3), (9, 3)], float), np.array([(3, 1), (3, 9)], float)]),
        ("diagonal_pelos_vertices", [quad], [np.array([(-1, -1), (5, 5)], float), np.array([(-1, 5), (5, -1)], float)]),
        ("tangente_vertice_fora", [ret], [np.array([(-1, 1), (0, 0), (1, -1)], float), np.array([(3, 3), (4, 2), (5, 3)], float)]),
        ("tangente_vertice_meio_aresta", [ret], [np.array([(-1, 1), (0, 1), (-1, 2)], float), np.array([(-1, 1), (0, 1), (2, 1)], float)]),
        ("reentrante_L_raspa", [forma_l], [
            np.array([(1.0, 3.0), (2.0, 2.0), (3.0, 1.0)], float),
            np.array([(1.0, 2.0 - 3e-4), (3.0, 2.0 - 3e-4)], float),
            np.array([(2.0 - 2e-4 - 0.5, 2.0 - 2e-4 + 0.5), (2.0 - 2e-4 + 0.5, 2.0 - 2e-4 - 0.5)], float),
        ]),
    ]

    # Mais 30 cenarios gerados ligando pares de vertices / pontos medios de arestas de poligonos
    for k in range(30):
        poli_anel = _poligono_estrelado(rng, 2.0, 2.0, 1.0, 3.0, 8)
        v_idx = rng.integers(0, len(poli_anel), size=6)
        pols_k = []
        for i in range(0, 6, 2):
            p0 = poli_anel[v_idx[i]]
            p1 = poli_anel[(v_idx[i] + 1) % len(poli_anel)]
            v = p1 - p0
            # colinear estendida pela aresta
            pols_k.append(np.vstack([p0 - 0.5 * v, p0, p1, p1 + 0.5 * v]))
            # passando de um vertice a outro
            p2 = poli_anel[v_idx[i + 1]]
            if not np.allclose(p0, p2):
                d = p2 - p0
                pols_k.append(np.vstack([p0 - 0.3 * d, p2 + 0.3 * d]))
        cenarios.append((f"estrelado_col_vert_{k}", [poli_anel], pols_k))

    for nome, aneis_in, pols in cenarios:
        for encolher in _ENCOLHERES:
            ref = _referencia_recortar(pols, aneis_in, encolher=encolher)
            res = recortar_fora_dos_aneis(pols, aneis_in, encolher=encolher)
            _assert_igual_ref(res, ref, msg=f"{nome} encolher={encolher}")


def test_equivalencia_segmentos_minusculos_e_degenerados():
    """Segmentos <= _EPS, pouco acima de _EPS, polilinhas de 0/1/2/100 pts e vertices duplicados no anel."""
    rng = np.random.default_rng(5005)
    # Anel com vertice duplicado consecutivo (gera aresta nula filtrada no preparo)
    anel_dup = np.array([(0, 0), (4, 0), (4, 0), (4, 2), (0, 2), (0, 0)], dtype=float)
    furo_dup = np.array([(1, 0.5), (1, 1.5), (3, 1.5), (3, 1.5), (3, 0.5)], dtype=float)
    grupos = [[anel_dup, furo_dup]]

    comprimentos = [0.0, 0.25 * _REF_EPS, _REF_EPS, 2.0 * _REF_EPS, 1e-11, 1e-10, 1e-8, 1e-5, 1e-3]
    for caso in range(15):
        pols = [
            np.empty((0, 2), dtype=float),
            np.array([[1.0, 1.0]], dtype=float),
            np.array([[-1.0, 1.0], [-1.0, 1.0]], dtype=float),  # 2 pts coincidentes
            np.array([[-1.0, 1.0], [-1.0 + 0.5 * _REF_EPS, 1.0]], dtype=float),
            np.array([[-1.0, 1.0], [-1.0 + 1e-8, 1.0]], dtype=float),
        ]
        # Polilinha misturando segmentos normais e minusculos dentro/fora/borda
        pts_mix = [(-1.0, 1.0)]
        x_cur, y_cur = -1.0, 1.0
        for comp in comprimentos:
            x_cur += comp
            pts_mix.append((x_cur, y_cur))
            x_cur += float(rng.uniform(0.3, 0.8))
            y_cur += float(rng.uniform(-0.15, 0.15))
            pts_mix.append((x_cur, y_cur))
        pols.append(np.array(pts_mix, dtype=float))

        # Polilinha com 100 pontos alternando passos minusculos e medios
        pts100 = [(-0.5, float(rng.uniform(-0.2, 2.2)))]
        for j in range(99):
            px, py = pts100[-1]
            step = comprimentos[j % len(comprimentos)] if j % 3 == 0 else float(rng.uniform(0.05, 0.25))
            ang = float(rng.uniform(-0.4, 0.4))
            pts100.append((px + step * math.cos(ang), py + step * math.sin(ang)))
        pols.append(np.array(pts100, dtype=float))

        for encolher in _ENCOLHERES:
            ref = _referencia_recortar(pols, grupos, encolher=encolher)
            res = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
            _assert_igual_ref(res, ref, msg=f"minusculos caso={caso} encolher={encolher}")


@pytest.mark.parametrize("encolher", _ENCOLHERES)
def test_equivalencia_polilinhas_2_pontos_e_100_pontos(encolher: float):
    """Lote de 80 polilinhas de 2 pontos e 20 polilinhas de 100 pontos sobre cena com grupos e furos."""
    rng = np.random.default_rng(6006)
    grupos = [
        [_rect(0, 0, 8, 8), _rect(2, 2, 6, 6, horario=True)],
        [_rect(5, 3, 13, 11), _poligono_estrelado(rng, 9.5, 7.0, 1.0, 1.8, 7, horario=True)],
        [_poligono_L(-3, 5, 6, 6)],
    ]
    pols_2 = [_gerar_polilinha_aleatoria(rng, 2, (-5.0, 15.0), (-2.0, 13.0)) for _ in range(80)]
    pols_100 = [_gerar_polilinha_aleatoria(rng, 100, (-5.0, 15.0), (-2.0, 13.0), (0.2, 1.2)) for _ in range(20)]
    pols = pols_2 + pols_100

    ref = _referencia_recortar(pols, grupos, encolher=encolher)
    res = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
    _assert_igual_ref(res, ref, msg=f"2_e_100_pts encolher={encolher}")


def test_equivalencia_listas_vazias_formatos_e_validacao():
    """Listas vazias, grupos vazios, tuplas puras, arrays nao-float64, encolher padrao e ValueError."""
    ret_tup = [(0, 0), (4, 0), (4, 2), (0, 2)]
    lin_tup = [[(-1, 1), (5, 1)], [(-1, 5), (5, 5)]]
    lin_np = [np.array([(-1, 1), (5, 1)], dtype=np.float32), np.array([(-1, 5), (5, 5)], dtype=np.int64)]

    casos = [
        ("pols_vazias_com_aneis", [], [ret_tup]),
        ("pols_vazias_aneis_vazios", [], []),
        ("aneis_vazios", lin_np, []),
        ("grupos_vazios", lin_np, [[], []]),
        ("grupo_vazio_misturado", lin_np, [[], [ret_tup], []]),
        ("plano_tuplas", lin_tup, [ret_tup]),
        ("grupos_tuplas", lin_tup, [[ret_tup]]),
        ("pols_gerador_aneis_gerador", (p for p in lin_np), (g for g in [[ret_tup]])),
    ]
    for nome, pols_in, aneis_in in casos:
        # Materializa se for iterador para passar igual a ambos
        pols_list = list(pols_in)
        aneis_list = list(aneis_in)
        ref_def = _referencia_recortar(pols_list, aneis_list)
        res_def = recortar_fora_dos_aneis(pols_list, aneis_list)
        _assert_igual_ref(res_def, ref_def, msg=f"{nome} default")
        for encolher in _ENCOLHERES:
            ref = _referencia_recortar(pols_list, aneis_list, encolher=encolher)
            res = recortar_fora_dos_aneis(pols_list, aneis_list, encolher=encolher)
            _assert_igual_ref(res, ref, msg=f"{nome} encolher={encolher}")

    # Iteradores consumidos uma unica vez (sem materializar antes)
    res_iter = recortar_fora_dos_aneis(iter(lin_np), iter([[ret_tup]]), encolher=0.0)
    ref_iter = _referencia_recortar(lin_np, [[ret_tup]], encolher=0.0)
    _assert_igual_ref(res_iter, ref_iter, msg="iteradores")

    # Aneis invalidos devem levantar ValueError como a referencia
    invalidos = [
        [(0, 0), (1, 1)],
        [(0, 0), (0, 0), (1, 1)],
        [(0, 0, 0), (1, 1, 1), (2, 2, 2)],
        [(0, 0), (1, 0), (1, 0), (0, 0)],
    ]
    for anel_ruim in invalidos:
        with pytest.raises(ValueError):
            _referencia_recortar(lin_np, [anel_ruim], encolher=0.0)
        with pytest.raises(ValueError):
            recortar_fora_dos_aneis(lin_np, [anel_ruim], encolher=0.0)


@pytest.mark.parametrize(
    "offset",
    [
        pytest.param((0.0, 0.0), id="origem_0_0"),
        pytest.param((1e-4, -1e-4), id="perto_de_zero"),
        pytest.param((-12.345, 67.89), id="local_neg_pos"),
        pytest.param((332_000.5, 7_395_000.25), id="utm_sp"),
        pytest.param((500_000.123456, 7_500_000.654321), id="utm_500k_7500k"),
        pytest.param((-500_000.25, -7_500_000.75), id="utm_negativo"),
    ],
)
def test_equivalencia_coordenadas_utm_e_perto_de_zero(offset: tuple[float, float]):
    """Equivalencia em coordenadas perto de zero e em coordenadas UTM reais."""
    ox, oy = offset
    rng = np.random.default_rng(7007)

    for caso in range(15):
        encolher = _ENCOLHERES[caso % len(_ENCOLHERES)]
        grupos_base = [
            [_rect(0.0, 0.0, 10.0, 8.0), _rect(2.5, 2.0, 6.5, 6.0, horario=True)],
            [_rect(7.0, 3.0, 14.0, 10.0)],
            [_poligono_estrelado(rng, 4.0, 11.0, 1.2, 2.8, 7)],
        ]
        pols_base = [
            np.array([(-1.0, 0.0), (11.0, 0.0)], dtype=float),  # colinear com borda
            np.array([(-1.0, 4.0), (15.0, 4.0)], dtype=float),  # cruza furo e sobreposicao
            _gerar_polilinha_aleatoria(rng, 12, (-2.0, 16.0), (-2.0, 14.0)),
            _gerar_polilinha_aleatoria(rng, 2, (-2.0, 16.0), (-2.0, 14.0)),
        ]
        plano = (caso % 2 == 0)
        aneis_base = [a for g in grupos_base for a in g] if plano else grupos_base
        pols = _transladar_pols(pols_base, ox, oy)
        aneis = _transladar_aneis(aneis_base, ox, oy, plano=plano)

        ref = _referencia_recortar(pols, aneis, encolher=encolher)
        res = recortar_fora_dos_aneis(pols, aneis, encolher=encolher)
        _assert_igual_ref(res, ref, msg=f"offset={offset} caso={caso} plano={plano} encolher={encolher}")


@pytest.mark.parametrize("encolher", (5e-4, 0.0))
def test_equivalencia_cena_grande(encolher: float):
    """Cena grande (30 aneis em 6 grupos, 400 polilinhas x 60 pts): saida igual a referencia."""
    pols, grupos = _gerar_cena_grande()
    ref = _referencia_recortar(pols, grupos, encolher=encolher)
    res = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
    assert len(ref) > 100
    _assert_igual_ref(res, ref, msg=f"cena_grande encolher={encolher}")


# ==============================================================================
# (3) TESTES ATOMICOS DE DESEMPENHO RELATIVO (MESMO PROCESSO)
# ==============================================================================


def _medir_relativo(pols, grupos, encolher: float, rodadas: int = 3) -> tuple[float, float, int, int]:
    """Mede mediana de `rodadas` intercaladas (mesmo processo, time.perf_counter)."""
    t_refs: list[float] = []
    t_novos: list[float] = []
    n_ref = 0
    n_novo = 0
    for r in range(rodadas):
        # Alterna a ordem em cada rodada para cancelar vies de aquecimento/cache/CI
        ordem = ("ref", "novo") if r % 2 == 0 else ("novo", "ref")
        for qual in ordem:
            gc.collect()
            t0 = time.perf_counter()
            if qual == "ref":
                out_r = _referencia_recortar(pols, grupos, encolher=encolher)
                t_refs.append(time.perf_counter() - t0)
                n_ref = len(out_r)
            else:
                out_n = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
                t_novos.append(time.perf_counter() - t0)
                n_novo = len(out_n)
    return statistics.median(t_refs), statistics.median(t_novos), n_ref, n_novo


def test_desempenho_relativo_cena_grande_encolher_padrao():
    """Versao nova deve levar no maximo 40% do tempo da referencia (encolher=5e-4)."""
    pols, grupos = _gerar_cena_grande()
    med_ref, med_novo, n_ref, n_novo = _medir_relativo(pols, grupos, encolher=5e-4, rodadas=3)
    assert n_novo == n_ref, f"qtd trechos divergente no benchmark: {n_novo} != {n_ref}"
    razao = med_novo / med_ref
    assert med_novo <= 0.40 * med_ref, (
        f"lento demais (encolher=5e-4): novo={med_novo:.4f}s vs ref={med_ref:.4f}s "
        f"({100.0 * razao:.1f}% > 40.0%)"
    )


def test_desempenho_relativo_cena_grande_encolher_zero():
    """Versao nova deve levar no maximo 40% do tempo da referencia (encolher=0.0)."""
    pols, grupos = _gerar_cena_grande()
    med_ref, med_novo, n_ref, n_novo = _medir_relativo(pols, grupos, encolher=0.0, rodadas=3)
    assert n_novo == n_ref, f"qtd trechos divergente no benchmark: {n_novo} != {n_ref}"
    razao = med_novo / med_ref
    assert med_novo <= 0.40 * med_ref, (
        f"lento demais (encolher=0.0): novo={med_novo:.4f}s vs ref={med_ref:.4f}s "
        f"({100.0 * razao:.1f}% > 40.0%)"
    )


# ==============================================================================
# (4) NAO MUTAR ENTRADAS, DETERMINISMO E USO DE MEMORIA LIMITADO
# ==============================================================================


def test_nao_muta_entradas_nem_compartilha_memoria():
    """Nao muta polilinhas nem aneis (plano e grupos), e saida nao compartilha buffer."""
    pols = [
        np.array([(-2.0, 5.0), (8.0, 5.0)], dtype=float),              # toda fora
        np.array([(-1.0, 1.0), (2.0, 1.0), (2.0, 3.0), (6.0, 3.0)], dtype=float),  # cortada
        np.array([(1.0, 1.0), (3.0, 1.0)], dtype=float),               # toda dentro
    ]
    grupos = [[_rect(0.0, 0.0, 4.0, 2.0)], [_rect(3.0, 0.0, 5.0, 4.0)]]
    plano = [_rect(0.0, 0.0, 4.0, 2.0)]

    pols_snap = [p.copy() for p in pols]
    grupos_snap = [[a.copy() for a in g] for g in grupos]
    plano_snap = [a.copy() for a in plano]

    res_g = recortar_fora_dos_aneis(pols, grupos, encolher=5e-4)
    res_p = recortar_fora_dos_aneis(pols, plano, encolher=0.0)

    for orig, snap in zip(pols, pols_snap):
        np.testing.assert_array_equal(orig, snap)
    for g_orig, g_snap in zip(grupos, grupos_snap):
        assert len(g_orig) == len(g_snap)
        for a_orig, a_snap in zip(g_orig, g_snap):
            np.testing.assert_array_equal(a_orig, a_snap)
    for a_orig, a_snap in zip(plano, plano_snap):
        np.testing.assert_array_equal(a_orig, a_snap)

    # Mutar a saida nao pode afetar a entrada
    for arr in res_g + res_p:
        arr[:] = -999.0
    for orig, snap in zip(pols, pols_snap):
        np.testing.assert_array_equal(orig, snap)

    # Mutar a entrada apos a chamada nao pode afetar a saida
    pol_mut = np.array([(-3.0, 8.0), (7.0, 8.0)], dtype=float)
    res_mut = recortar_fora_dos_aneis([pol_mut], plano, encolher=5e-4)
    pol_mut[:] = 0.0
    np.testing.assert_allclose(res_mut[0], [(-3.0, 8.0), (7.0, 8.0)], rtol=0.0, atol=_TOL)


def test_determinismo_chamadas_repetidas():
    """Chamadas repetidas produzem saida identica bit a bit."""
    rng = np.random.default_rng(8008)
    grupos = [
        [_rect(0.0, 0.0, 10.0, 10.0), _rect(2.5, 2.5, 7.5, 7.5, horario=True)],
        [_poligono_estrelado(rng, 8.0, 6.0, 1.5, 4.0, 9)],
    ]
    pols = [_gerar_polilinha_aleatoria(rng, 25, (-2.0, 14.0), (-2.0, 12.0)) for _ in range(30)]

    for encolher in (5e-4, 0.0):
        r1 = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
        r2 = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
        r3 = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
        assert len(r1) == len(r2) == len(r3) > 0
        for a, b, c in zip(r1, r2, r3):
            np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(a, c)


def test_uso_memoria_limitado_cena_grande():
    """Pico de memoria alocada na cena grande deve ficar abaixo de 300 MiB."""
    pols, grupos = _gerar_cena_grande()
    limite_bytes = 300 * 1024 * 1024
    gc.collect()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        res = recortar_fora_dos_aneis(pols, grupos, encolher=5e-4)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(res) > 100
    assert pico < limite_bytes, f"pico de memoria {pico / (1024 * 1024):.1f} MiB >= 300.0 MiB"


# ==============================================================================
# (5) MUTANTES: UM TESTE POR COMPORTAMENTO ERRADO PLAUSIVEL
# ==============================================================================


def test_mutante_perder_trecho_na_fronteira():
    """Mutante: descartar trecho colinear com a borda ou apenas tocando a fronteira."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    for encolher in (0.0, 5e-4):
        # Colinear atravessando a borda inferior inteira
        res1 = recortar_fora_dos_aneis([np.array([(-1.0, 0.0), (5.0, 0.0)])], ret, encolher=encolher)
        _assert_trechos_exatos(res1, [[(-1.0, 0.0), (5.0, 0.0)]], msg=f"borda_estendida e={encolher}")

        # Inteiramente contida sobre a aresta da fronteira
        res2 = recortar_fora_dos_aneis([np.array([(1.0, 0.0), (3.0, 0.0)])], ret, encolher=encolher)
        _assert_trechos_exatos(res2, [[(1.0, 0.0), (3.0, 0.0)]], msg=f"borda_interna e={encolher}")

        # Apenas encosta no ponto (0, 1) da fronteira e volta para fora
        res3 = recortar_fora_dos_aneis([np.array([(-1.0, 1.0), (0.0, 1.0), (-1.0, 2.0)])], ret, encolher=encolher)
        _assert_trechos_exatos(res3, [[(-1.0, 1.0), (0.0, 1.0), (-1.0, 2.0)]], msg=f"toca_borda e={encolher}")


def test_mutante_juntar_trechos_que_nao_deveriam():
    """Mutante: fundir trechos separados por corte em uma unica polilinha."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]

    # 1) Unico segmento atravessando o retangulo: devem sair 2 trechos separados
    res1 = recortar_fora_dos_aneis([np.array([(-1.0, 1.0), (5.0, 1.0)])], ret, encolher=0.0)
    _assert_trechos_exatos(res1, [[(-1.0, 1.0), (0.0, 1.0)], [(4.0, 1.0), (5.0, 1.0)]], msg="corte_simples")

    # 2) Polilinha de 4 pontos com segmento intermediario todo removido
    res2 = recortar_fora_dos_aneis(
        [np.array([(-1.0, 1.0), (0.0, 1.0), (4.0, 1.0), (5.0, 1.0)])], ret, encolher=0.0
    )
    _assert_trechos_exatos(res2, [[(-1.0, 1.0), (0.0, 1.0)], [(4.0, 1.0), (5.0, 1.0)]], msg="meio_removido")

    # 3) Dois retangulos separados por fenda estreita de 1 cm: 3 trechos distintos
    dois_rets = [[_rect(0.0, 0.0, 2.0, 2.0)], [_rect(2.01, 0.0, 4.0, 2.0)]]
    res3 = recortar_fora_dos_aneis([np.array([(-1.0, 1.0), (5.0, 1.0)])], dois_rets, encolher=0.0)
    _assert_trechos_exatos(
        res3,
        [[(-1.0, 1.0), (0.0, 1.0)], [(2.0, 1.0), (2.01, 1.0)], [(4.0, 1.0), (5.0, 1.0)]],
        msg="fenda_estreita",
    )


def test_mutante_inverter_par_impar():
    """Mutante: inverter par-impar dentro de um grupo ou confundir uniao entre grupos com par-impar."""
    # Externo + furo: so o furo permanece
    ext_furo = [_rect(0.0, 0.0, 10.0, 10.0), _rect(3.0, 3.0, 7.0, 7.0, horario=True)]
    res_furo = recortar_fora_dos_aneis([np.array([(1.0, 5.0), (9.0, 5.0)])], ext_furo, encolher=0.0)
    _assert_trechos_exatos(res_furo, [[(3.0, 5.0), (7.0, 5.0)]], msg="furo_mantido")

    # Externo + furo + ilha: 3 niveis de paridade
    tres_niveis = [
        _rect(0.0, 0.0, 10.0, 10.0),
        _rect(2.0, 2.0, 8.0, 8.0, horario=True),
        _rect(4.0, 4.0, 6.0, 6.0),
    ]
    res_3 = recortar_fora_dos_aneis([np.array([(-1.0, 5.0), (11.0, 5.0)])], tres_niveis, encolher=0.0)
    _assert_trechos_exatos(
        res_3,
        [[(-1.0, 5.0), (0.0, 5.0)], [(2.0, 5.0), (4.0, 5.0)], [(6.0, 5.0), (8.0, 5.0)], [(10.0, 5.0), (11.0, 5.0)]],
        msg="ilha_no_furo",
    )

    # Sobreposicao: plano (par-impar mantem miolo) vs grupos (uniao remove miolo)
    a = _rect(0.0, 0.0, 5.0, 2.0)
    b = _rect(3.0, 0.0, 8.0, 2.0)
    lin = [np.array([(-1.0, 1.0), (9.0, 1.0)])]
    res_plano = recortar_fora_dos_aneis(lin, [a, b], encolher=0.0)
    _assert_trechos_exatos(
        res_plano,
        [[(-1.0, 1.0), (0.0, 1.0)], [(3.0, 1.0), (5.0, 1.0)], [(8.0, 1.0), (9.0, 1.0)]],
        msg="sobreposicao_plano_par_impar",
    )
    res_grupos = recortar_fora_dos_aneis(lin, [[a], [b]], encolher=0.0)
    _assert_trechos_exatos(
        res_grupos,
        [[(-1.0, 1.0), (0.0, 1.0)], [(8.0, 1.0), (9.0, 1.0)]],
        msg="sobreposicao_grupos_uniao",
    )


def test_mutante_ignorar_encolher():
    """Mutante: ignorar `encolher` em aresta externa, furo ou arco de vertice reentrante."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    lin = [np.array([(-1.0, 1.0), (5.0, 1.0)])]

    # Aresta externa recuada em encolher=1e-2 e padrao 5e-4
    _assert_trechos_exatos(
        recortar_fora_dos_aneis(lin, ret, encolher=1e-2),
        [[(-1.0, 1.0), (0.01, 1.0)], [(3.99, 1.0), (5.0, 1.0)]],
        msg="encolher_1e2",
    )
    _assert_trechos_exatos(
        recortar_fora_dos_aneis(lin, ret),
        [[(-1.0, 1.0), (5e-4, 1.0)], [(4.0 - 5e-4, 1.0), (5.0, 1.0)]],
        msg="encolher_padrao",
    )

    # Furo cresce `encolher` para dentro do material
    ext_furo = [_rect(0.0, 0.0, 10.0, 10.0), _rect(4.0, 4.0, 6.0, 6.0, horario=True)]
    _assert_trechos_exatos(
        recortar_fora_dos_aneis([np.array([(1.0, 5.0), (9.0, 5.0)])], ext_furo, encolher=1e-2),
        [[(3.99, 5.0), (6.01, 5.0)]],
        msg="furo_cresce_encolher",
    )

    # Vertice reentrante do L (1, 1): corte no arco de raio 5e-4 em y = 1 - 3e-4 -> x = 1 - 4e-4
    forma_l = [np.array([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)], dtype=float)]
    _assert_trechos_exatos(
        recortar_fora_dos_aneis([np.array([(0.5, 1.0 - 3e-4), (1.5, 1.0 - 3e-4)])], forma_l, encolher=5e-4),
        [[(1.0 - 4e-4, 1.0 - 3e-4), (1.5, 1.0 - 3e-4)]],
        msg="arco_vertice_reentrante",
    )


def test_mutante_descartar_polilinha_de_2_pontos():
    """Mutante: descartar polilinhas de exatamente 2 pontos por off-by-one."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    pols = [
        np.array([(-2.0, 5.0), (6.0, 5.0)], dtype=float),              # 2 pts toda fora
        np.array([(-1.0, 1.0), (2.0, 1.0)], dtype=float),              # 2 pts metade fora
        np.array([(-1.0, 1.5), (5.0, 1.5)], dtype=float),              # 2 pts atravessa -> 2 trechos de 2 pts
        np.array([(10.0, 10.0), (10.0 + 1e-8, 10.0)], dtype=float),    # 2 pts curta (> _EPS) fora
    ]
    res = recortar_fora_dos_aneis(pols, ret, encolher=0.0)
    _assert_trechos_exatos(
        res,
        [
            [(-2.0, 5.0), (6.0, 5.0)],
            [(-1.0, 1.0), (0.0, 1.0)],
            [(-1.0, 1.5), (0.0, 1.5)],
            [(4.0, 1.5), (5.0, 1.5)],
            [(10.0, 10.0), (10.0 + 1e-8, 10.0)],
        ],
        msg="polilinhas_2_pontos",
    )
