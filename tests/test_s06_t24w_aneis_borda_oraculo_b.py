# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24w_aneis_borda_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from collections import defaultdict
import math
import numpy as np
import pytest
from obim_geometria import aneis, oclusores
from test_s06_t24w_aneis_borda_oraculo import _CAIXA_M, _DIAM, _EXT_CONC, _EXT_L, _EXT_TRI, _assert_bit_a_bit, _cena_bib0_sintetica, _cena_bib1_sintetica, _checar_aneis_e_grupos, _rot, _segs_de  # noqa: F401



def test_independente_da_ordem_e_sentido_dos_segmentos():
    """25 permutacoes e inversoes de segmentos produzem saida bit a bit identica e valida."""
    pols1, areas1 = _cena_bib1_sintetica()
    rng = np.random.default_rng(7788)
    for pols, areas_desc, tam_gr in (
        (pols1, areas1, [1, 1, 1, 1, 1]),
        ([_EXT_CONC, [(3.0, 5.0), (5.0, 7.0), (6.0, 9.0)]], [70.0, 1.0], [1, 1]),
        ([_EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]], [50.0, -2.0], [2]),
        ([_DIAM, [(2.0 - 1e-11, 3.0), (3.0 - 1e-11, 2.0), (4.0, 4.0), (3.0, 5.0)]], [50.0, -3.0], [2]),
        ([_CAIXA_M, _EXT_TRI, [(3.0 + 1e-11, 3.0), (5.0 + 1e-11, 5.0), (6.0, 8.0)]], [144.0, -50.0, 2.0], [2, 1]),
    ):
        base = _segs_de(pols)
        _checar_aneis_e_grupos(base, areas_desc, tam_gr, atol_area=1e-5)
        ref = aneis.aneis_de_segmentos(base)
        for _ in range(25):
            m = base[rng.permutation(len(base))].copy()
            inv = rng.random(len(m)) < 0.5
            m[inv] = m[inv][:, [2, 3, 0, 1]]
            _assert_bit_a_bit(aneis.aneis_de_segmentos(m), ref)


# ---------- (4) MUTANTES (1 TESTE POR ERRO PLAUSIVEL) ----------
def test_mutante_01_usar_so_a_primeira_aresta():
    """Mutante 1: testar apenas a 1a aresta falha quando aresta 0 (ou 0 e 1) encosta na borda."""
    pols1, areas1 = _cena_bib1_sintetica()
    _checar_aneis_e_grupos(_segs_de(pols1), areas1, [1, 1, 1, 1, 1], atol_area=1e-5)
    _checar_aneis_e_grupos(_segs_de([_EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]]), [50.0, -2.0], [2])


def test_mutante_02_usar_ponto_sobre_vertice():
    """Mutante 2: usar vertice `r[0]` (ou qualquer vertice) falha quando vertices estao na borda."""
    insc_m11 = [(2.5 - 1e-11, 2.5), (7.5 + 1e-11, 2.5), (7.5 + 1e-11, 7.5), (2.5 - 1e-11, 7.5)]
    _checar_aneis_e_grupos(_segs_de([_DIAM, insc_m11]), [50.0, -25.0], [2])
    _checar_aneis_e_grupos(_segs_de([_EXT_L, [(4.0 - 1e-11, 6.0), (6.0, 5.0), (6.0, 7.0)]]), [64.0, 2.0], [1, 1])


def test_mutante_03_tolerancia_zero():
    """Mutante 3: usar `dist > 0.0` (tolerancia zero) falha em toques a ~1e-11 m."""
    _checar_aneis_e_grupos(_segs_de([_EXT_L, [(4.0 - 1e-11, 5.0), (7.0, 5.0), (7.0, 8.0), (4.0 - 1e-11, 8.0)]]), [64.0, 9.0], [1, 1])
    _checar_aneis_e_grupos(_segs_de([_DIAM, [(2.0 - 1e-11, 3.0), (3.0 - 1e-11, 2.0), (4.0, 4.0), (3.0, 5.0)]]), [50.0, -3.0], [2])


def test_mutante_04_ignorar_toque_e_contar_como_dentro():
    """Mutante 4: contar toque de borda como 'dentro' inverte anel externo adjacente e quebra `_agrupar_aneis`."""
    _checar_aneis_e_grupos(_segs_de([_EXT_CONC, [(3.0, 5.0), (5.0, 7.0), (6.0, 9.0)]]), [70.0, 1.0], [1, 1])
    pols0, areas0 = _cena_bib0_sintetica()
    _checar_aneis_e_grupos(_segs_de(pols0), areas0, [1, 1], atol_area=1e-6)


def test_mutante_05_ignorar_toque_e_contar_como_fora():
    """Mutante 5: contar toque de borda como 'fora' deixa furo com area > 0 e ilha com area < 0."""
    _checar_aneis_e_grupos(_segs_de([_EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]]), [50.0, -2.0], [2])
    _checar_aneis_e_grupos(_segs_de([_CAIXA_M, _EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]]), [144.0, -50.0, 2.0], [2, 1])


# ---------- (5) REVISAO 1: BBOX COM RUIDO, COLINEAR TOTAL E TOLERANCIA (7 TESTES) ----------
def _area_trans(pts: np.ndarray) -> float:
    x = pts[:, 0] - pts[0, 0]
    y = pts[:, 1] - pts[0, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]) + x[-1] * y[0] - x[0] * y[-1])


@pytest.mark.parametrize(
    ("offset", "eps"),
    [
        pytest.param((0.0, 0.0), -1e-11, id="origem_ruido_m1e11"),
        pytest.param((500_000.0, 7_500_000.0), -6e-11, id="utm_1ulp_x"),
        pytest.param((500_000.0, 7_500_000.0), -1e-9, id="utm_1ulp_y"),
    ],
)
def test_rev1_bbox_toque_com_ruido_sub_tol(offset: tuple[float, float], eps: float):
    """Furo encostando em aresta na extremidade da bbox com ruido sub-tol nao perde o pai."""
    ox, oy = offset
    ext = [(ox, oy), (ox + 10.0, oy), (ox + 10.0, oy + 10.0), (ox, oy + 10.0)]
    furo_x = [(ox + eps, oy + 2.0), (ox + 4.0, oy + 2.0), (ox + 4.0, oy + 8.0), (ox + eps, oy + 8.0)]
    cenas = [("x", furo_x)]
    if oy + eps != oy:
        furo_y = [(ox + 2.0, oy + eps), (ox + 8.0, oy + eps), (ox + 8.0, oy + 4.0), (ox + 2.0, oy + 4.0)]
        cenas.append(("y", furo_y))
    for eixo, furo in cenas:
        fe, ab = aneis.aneis_de_segmentos(_segs_de([ext, furo]))
        assert ab == [] and len(fe) == 2, f"eixo={eixo} fe={len(fe)} ab={len(ab)}"
        areas = sorted((_area_trans(r) for r in fe), key=lambda a: -abs(a))
        assert areas[0] > 0.0 and areas[1] < 0.0, f"furo virou externo ({eixo}): areas={areas}"


def test_rev1_colinear_total_furo_interno_angulos_e_formas():
    """Furo com todas as arestas colineares ao externo (sem vertices comuns): quadrado e triangulo em 36 angulos."""
    j_sq_ears = [
        (0.1, 0.0), (9.9, 0.0), (9.9, -0.1), (10.1, -0.1), (10.1, 0.1), (10.0, 0.1),
        (10.0, 9.9), (10.1, 9.9), (10.1, 10.1), (9.9, 10.1), (9.9, 10.0),
        (0.1, 10.0), (0.1, 10.1), (-0.1, 10.1), (-0.1, 9.9), (0.0, 9.9),
        (0.0, 0.1), (-0.1, 0.1), (-0.1, -0.1), (0.1, -0.1),
    ]
    i_sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    j_tri_ears = [
        (0.5, 0.0), (9.5, 0.0), (9.5, -0.5), (11.0, -0.5), (10.0, 1.0), (9.5, 0.5),
        (0.5, 9.5), (1.0, 10.0), (-0.5, 11.0), (-0.5, 9.5), (0.0, 9.5),
        (0.0, 0.5), (-0.5, 0.5), (-0.5, -0.5), (0.5, -0.5),
    ]
    i_tri = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]
    for nome, ext, furo in (("quadrado", j_sq_ears, i_sq), ("triangulo", j_tri_ears, i_tri)):
        for deg in range(0, 360, 10):
            th = math.radians(deg)
            fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(ext, th), _rot(furo, th)]))
            assert ab == [] and len(fe) == 2, f"{nome} deg={deg} fe={len(fe)} ab={len(ab)}"
            areas = sorted((_area_trans(r) for r in fe), key=lambda a: -abs(a))
            assert areas[0] > 0.0 and areas[1] < 0.0, f"{nome} deg={deg}: furo colinear virou externo: areas={areas}"


def test_rev1_colinear_total_externo_em_cavidade_angulos():
    """Anel externo em cavidade de C-shape (todas as arestas colineares, fora de j) mantem area > 0 em 36 angulos."""
    j_c = [
        (0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (2.1, 2.0), (2.1, 1.9), (1.9, 1.9), (1.9, 2.1), (2.0, 2.1),
        (2.0, 7.9), (1.9, 7.9), (1.9, 8.1), (2.1, 8.1), (2.1, 8.0),
        (7.9, 8.0), (7.9, 8.1), (8.1, 8.1), (8.1, 7.9), (8.0, 7.9),
        (8.0, 2.1), (8.1, 2.1), (8.1, 1.9), (7.9, 1.9), (7.9, 2.0),
        (3.05, 2.0), (3.05, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0),
    ]
    i_cav = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)]
    for deg in range(0, 360, 10):
        th = math.radians(deg)
        fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(j_c, th), _rot(i_cav, th)]))
        assert ab == [] and len(fe) == 2, f"deg={deg} fe={len(fe)} ab={len(ab)}"
        areas = sorted((_area_trans(r) for r in fe), key=lambda a: -abs(a))
        assert areas[0] > 0.0 and areas[1] > 0.0, f"deg={deg}: externo em cavidade virou furo: areas={areas}"


def test_rev1_tol_borda_anel_pequeno_1e6m():
    """Tolerancia de borda escala com o anel em cena pequena (1e-6 m, tol=1e-9) em varios angulos."""
    s = 1e-6
    ext = [(0.0, 0.0), (s, 0.0), (s, s), (0.0, s)]
    furo = [(s, 0.1 * s), (s, 0.5 * s), (s, 0.9 * s), (s - 1.5e-8, 0.5 * s)]
    for deg in (0, 15, 30, 45, 90, 135, 210, 300):
        th = math.radians(deg)
        fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(ext, th), _rot(furo, th)]), tol=1e-9)
        assert ab == [] and len(fe) == 2, f"deg={deg} fe={len(fe)} ab={len(ab)}"
        areas = sorted((_area_trans(r) for r in fe), key=lambda a: -abs(a))
        assert areas[0] > 0.0 and areas[1] < 0.0, f"deg={deg}: furo pequeno 1e-6m virou externo: areas={areas}"


def test_rev1_tol_borda_anel_fino_em_metros():
    """Furo fino em metros (espessura 1.5e-8 m, tol=1e-6) nao e engolido por tol_borda fixa em varios angulos."""
    ext = [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    furo = [(0.2, 0.2), (0.4, 0.4), (0.6, 0.6), (0.8, 0.8), (0.5, 0.5 + 1.5e-8)]
    for deg in (0, 30, 60, 90, 135, 210):
        th = math.radians(deg)
        fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(ext, th), _rot(furo, th)]))
        assert ab == [] and len(fe) == 2, f"deg={deg} fe={len(fe)} ab={len(ab)}"
        areas = sorted((_area_trans(r) for r in fe), key=lambda a: -abs(a))
        assert areas[0] > 0.0 and areas[1] < 0.0, f"deg={deg}: furo fino (tol=1e-6) virou externo: areas={areas}"


# ---------- (6) REVISAO 2: _PONTO_INTERIOR M > 64 COM VERTICES COLINEARES (9 TESTES) ----------
def _subdiv(pts, per_edge: int):
    out = []
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        for k in range(per_edge):
            t = k / per_edge
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def _subdiv_m(pts, m: int):
    n = len(pts)
    base, rem = divmod(m, n)
    out = []
    for i in range(n):
        k_edge = base + (1 if i < rem else 0)
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        for k in range(k_edge):
            t = k / k_edge
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def _dist_borda(px: float, py: float, r: np.ndarray) -> float:
    x1, y1 = r[:, 0], r[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    dx, dy = x2 - x1, y2 - y1
    len2 = dx * dx + dy * dy
    t = np.clip(((px - x1) * dx + (py - y1) * dy) / np.where(len2 > 0.0, len2, 1.0), 0.0, 1.0)
    return float(np.sqrt(np.min((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2)))


def _enclosing_colinear_j(poly_ccw, cut: float = 0.005, ear: float = 0.02):
    """Externo simples que envolve `poly_ccw` colinearmente em todas as arestas sem vertices comuns."""
    n = len(poly_ccw)
    out = []
    for i in range(n):
        ax, ay = poly_ccw[(i - 1) % n]
        bx, by = poly_ccw[i]
        cx, cy = poly_ccw[(i + 1) % n]
        p1 = (ax + (1.0 - cut) * (bx - ax), ay + (1.0 - cut) * (by - ay))
        p2 = (bx + cut * (cx - bx), by + cut * (cy - by))
        lab = math.hypot(bx - ax, by - ay)
        lbc = math.hypot(cx - bx, cy - by)
        nab = ((by - ay) / lab, -(bx - ax) / lab)
        nbc = ((cy - by) / lbc, -(cx - bx) / lbc)
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if cross < 0.0:
            bix, biy = nab[0] + nbc[0], nab[1] + nbc[1]
            bl = math.hypot(bix, biy)
            qm = (bx + 0.03 * bix / bl, by + 0.03 * biy / bl)
            out.extend([p1, qm, p2])
        else:
            q1 = (p1[0] + ear * nab[0], p1[1] + ear * nab[1])
            q2 = (bx + ear * (nab[0] + nbc[0]), by + ear * (nab[1] + nbc[1]))
            q3 = (p2[0] + ear * nbc[0], p2[1] + ear * nbc[1])
            out.extend([p1, q1, q2, q3, p2])
    return out


def test_rev2_defeito1a_ponto_interior_m_gt_64_retorna_ponto_fora_do_anel():
    """`_ponto_interior` com m=80 (>64) e vertices colineares nao retorna ponto fora do proprio anel."""
    sq80 = _subdiv([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], 20)
    sq80 = sq80[5:] + sq80[:5]  # inicio no meio de aresta reta
    r = np.array(_rot(sq80, math.radians(11.0)), dtype=float)
    px, py = aneis._ponto_interior(r, _area_trans(r))
    x1, y1 = r[:, 0], r[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    assert aneis._ponto_no_anel_arr(px, py, x1, y1, x2, y2), (
        f"_ponto_interior retornou ponto fora do proprio anel (m={len(r)}): {(px, py)}"
    )


def test_rev2_defeito1b_aneis_de_segmentos_furo_colinear_m_gt_64():
    """Furo concavo colinear total (dart m=68 > 64) sai area < 0 em varios angulos no fluxo completo."""
    dart = [(0.0, 5.0), (10.0, 0.0), (0.4, 5.0), (10.0, 10.0)]
    dart_68 = _subdiv(dart, 17)  # m=68 > 64
    j_dart = _enclosing_colinear_j(dart)
    for deg in (0, 5, 30, 355):
        th = math.radians(deg)
        fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(j_dart, th), _rot(dart_68, th)]))
        assert ab == [] and len(fe) == 2
        areas = sorted((_area_trans(r) for r in fe), key=lambda v: -abs(v))
        assert areas[0] > 0.0 and areas[1] < 0.0, (
            f"deg={deg}: furo colinear m=68 virou externo: areas={areas}"
        )


@pytest.mark.parametrize("m", [65, 80, 200, 500], ids=["m65", "m80", "m200", "m500"])
def test_rev2_furo_quadrado_subdividido_colinear_m_gt_64(m: int):
    """Furo quadrado subdividido (m=65, 80, 200, 500 colineares) em varios angulos: `_ponto_interior` e fluxo completo."""
    sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    sq_m = _subdiv_m(sq, m)
    sq_shift = sq_m[3:] + sq_m[:3]
    j_sq = _enclosing_colinear_j(sq)
    for deg in (0, 5, 11, 25, 35, 45, 73, 135, 210, 300):
        th = math.radians(deg)
        r = np.array(_rot(sq_shift, th), dtype=float)
        px, py = aneis._ponto_interior(r, _area_trans(r))
        x1, y1 = r[:, 0], r[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        assert aneis._ponto_no_anel_arr(px, py, x1, y1, x2, y2), (
            f"m={m} deg={deg}: _ponto_interior fora do quadrado: {(px, py)}"
        )
        assert _dist_borda(px, py, r) > 1e-6, (
            f"m={m} deg={deg}: _ponto_interior sobre a borda (dist={_dist_borda(px, py, r):.3e})"
        )
        fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(j_sq, th), _rot(sq_m, th)]))
        assert ab == [] and len(fe) == 2, f"m={m} deg={deg}: fe={len(fe)} ab={len(ab)}"
        areas = sorted((_area_trans(rg) for rg in fe), key=lambda v: -abs(v))
        assert areas[0] > 0.0 and areas[1] < 0.0, f"m={m} deg={deg}: furo quadrado virou externo: areas={areas}"


@pytest.mark.parametrize(
    ("poly", "m", "angulos"),
    [
        pytest.param(
            [(0.0, 5.0), (10.0, 0.0), (10.0, 2.0), (0.5, 5.0), (10.0, 8.0), (10.0, 10.0)],
            72,
            (0, 10, 30, 50, 135, 210, 350),
            id="chevron_m72",
        ),
        pytest.param(
            [(0.0, 5.0), (10.0, 0.0), (0.4, 5.0), (10.0, 10.0)],
            80,
            (0, 15, 30, 45, 135, 300, 355),
            id="dart_m80",
        ),
        pytest.param(
            [(0.0, 5.0), (10.0, 0.0), (10.0, 2.0), (0.5, 5.0), (10.0, 8.0), (10.0, 10.0)],
            120,
            (0, 10, 30, 90, 210, 350),
            id="chevron_m120",
        ),
    ],
)
def test_rev2_anel_concavo_m_gt_64_colinear(poly, m: int, angulos: tuple[int, ...]):
    """Anel concavo m>64 com arestas colineares: fluxo completo `aneis_de_segmentos` e `_ponto_interior`."""
    ring_m = _subdiv_m(poly, m)
    ring_shift = ring_m[3:] + ring_m[:3]
    j_ext = _enclosing_colinear_j(poly)
    for deg in angulos:
        th = math.radians(deg)
        fe, ab = aneis.aneis_de_segmentos(_segs_de([_rot(j_ext, th), _rot(ring_m, th)]))
        assert ab == [] and len(fe) == 2, f"m={m} deg={deg}: fe={len(fe)} ab={len(ab)}"
        areas = sorted((_area_trans(rg) for rg in fe), key=lambda v: -abs(v))
        assert areas[0] > 0.0 and areas[1] < 0.0, (
            f"m={m} deg={deg}: furo concavo colinear virou externo: areas={areas}"
        )
        r = np.array(_rot(ring_shift, th), dtype=float)
        px, py = aneis._ponto_interior(r, _area_trans(r))
        x1, y1 = r[:, 0], r[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        assert aneis._ponto_no_anel_arr(px, py, x1, y1, x2, y2), (
            f"m={m} deg={deg}: _ponto_interior fora do concavo: {(px, py)}"
        )
        assert _dist_borda(px, py, r) > 1e-6, (
            f"m={m} deg={deg}: _ponto_interior na borda do concavo (dist={_dist_borda(px, py, r):.3e})"
        )
