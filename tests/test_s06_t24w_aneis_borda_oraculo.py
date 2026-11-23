# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24w: aninhamento de aneis robusto a toque de borda em `aneis.py`.

Alvo (implementador NAO edita este arquivo; somente producao `geometria/obim_geometria/aneis.py`):
- Em `aneis_de_segmentos` (bloco de orientacao/aninhamento ~linha 171), testar contencao com ponto
  fora da borda do candidato (ex.: primeiro ponto medio de aresta cuja distancia ao candidato
  exceda tolerancia, ou votacao por maioria dos pontos medios fora da borda), sem ambiguidade em
  toques a distancia 0 ou ~1e-11.
- Anel que apenas encosta na borda do externo e tratado conforme a maioria dos pontos nao-borda
  (externo area > 0, furo area < 0, ilha em furo area > 0), garantindo `oclusores._agrupar_aneis`
  nao retornar `None` e grupos corretos.
- Aneis sem toque: saida bit a bit igual a implementacao atual (`_ref_aneis_de_segmentos`).
- Determinismo, entrada nao mutada, independencia da ordem e sentido dos segmentos.
"""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np
import pytest

from obim_geometria import aneis, oclusores

_REF_EPS = 1e-12


# ---------- copia de referencia da implementacao ATUAL (bit a bit) ----------
def _ref_area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]) + x[-1] * y[0] - x[0] * y[-1])


def _ref_ponto_no_anel_arr(px: float, py: float, x1, y1, x2, y2) -> bool:
    cond = (y1 > py) != (y2 > py)
    if not np.any(cond):
        return False
    y1c, y2c, x1c, x2c = y1[cond], y2[cond], x1[cond], x2[cond]
    return (int(np.count_nonzero(px < x1c + (py - y1c) * (x2c - x1c) / (y2c - y1c))) & 1) == 1


def _ref_agrupar_nos(pts_all: np.ndarray, tol: float):
    id_map: dict[tuple[float, float], int] = {}
    pts_list: list[tuple[float, float]] = []
    pt_ids: list[int] = []
    for x, y in pts_all.tolist():
        key = (float(x), float(y))
        pid = id_map.setdefault(key, len(pts_list))
        if pid == len(pts_list):
            pts_list.append(key)
        pt_ids.append(pid)
    m = len(pts_list)
    if tol > 0.0 and m > 1:
        parent = list(range(m))
        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (px, py) in enumerate(pts_list):
            grid[(math.floor(px / tol), math.floor(py / tol))].append(i)
        tol2 = tol * tol
        for (cx, cy), ids_a in grid.items():
            for p, i in enumerate(ids_a):
                xi, yi = pts_list[i]
                for j in ids_a[p + 1:]:
                    ri, rj = find(i), find(j)
                    if ri != rj and (xi - pts_list[j][0]) ** 2 + (yi - pts_list[j][1]) ** 2 < tol2:
                        parent[rj] = ri
            for nkey in ((cx + 1, cy - 1), (cx + 1, cy), (cx + 1, cy + 1), (cx, cy + 1)):
                for i in ids_a:
                    xi, yi = pts_list[i]
                    for j in grid.get(nkey, ()):
                        ri, rj = find(i), find(j)
                        if ri != rj and (xi - pts_list[j][0]) ** 2 + (yi - pts_list[j][1]) ** 2 < tol2:
                            parent[rj] = ri
        roots = [find(i) for i in range(m)]
        cluster_min: dict[int, tuple[float, float]] = {}
        for i, r in enumerate(roots):
            if r not in cluster_min or pts_list[i] < cluster_min[r]:
                cluster_min[r] = pts_list[i]
        roots_ord = sorted(cluster_min, key=cluster_min.__getitem__)
        r2n = {r: idx for idx, r in enumerate(roots_ord)}
        return [cluster_min[r] for r in roots_ord], [r2n[roots[pid]] for pid in pt_ids]
    ord_idx = sorted(range(m), key=pts_list.__getitem__)
    old_to_new = [0] * m
    for new_id, old_id in enumerate(ord_idx):
        old_to_new[old_id] = new_id
    return [pts_list[i] for i in ord_idx], [old_to_new[pid] for pid in pt_ids]


def _ref_aneis_de_segmentos(segs, tol: float = 1e-6):
    arr = np.asarray(segs, dtype=float)
    if arr.size == 0:
        return [], []
    arr = arr.reshape(-1, 4)
    coords, mapped_ids = _ref_agrupar_nos(arr.reshape(-1, 2), tol)
    pares = [(mapped_ids[2 * k], mapped_ids[2 * k + 1]) for k in range(len(arr)) if mapped_ids[2 * k] != mapped_ids[2 * k + 1]]
    if not pares:
        return [], []
    adj: list[list[tuple[int, int]]] = [[] for _ in coords]
    for eid, (u, v) in enumerate(pares):
        adj[u].append((v, eid))
        adj[v].append((u, eid))
    for lst in adj:
        lst.sort(key=lambda item: item[0])
    usada, deg = [False] * len(pares), [len(lst) for lst in adj]
    def caminhar(inicio: int):
        cam, atual = [inicio], inicio
        while (prox := next(((v, eid) for v, eid in adj[atual] if not usada[eid]), None)) is not None:
            v, eid = prox
            usada[eid], deg[atual], deg[v] = True, deg[atual] - 1, deg[v] - 1
            cam.append(v); atual = v
            if atual == inicio:
                break
        return cam
    fechados_ids, abertos_ids = [], []
    for cond in (lambda d: d == 1, lambda d: d % 2 == 1, lambda d: d > 0):
        for u in range(len(coords)):
            while cond(deg[u]):
                cam = caminhar(u)
                if cam[0] == cam[-1] and len(cam) >= 4:
                    fechados_ids.append(cam[:-1])
                elif len(cam) >= 2:
                    abertos_ids.append(cam)
    fechados = [np.array([coords[i] for i in cam], dtype=float) for cam in fechados_ids]
    orientados_out = []
    if fechados:
        areas = np.array([_ref_area(r) for r in fechados], dtype=float)
        abs_areas = np.abs(areas)
        bboxes = np.array([(r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max()) for r in fechados], dtype=float)
        edges_xy = [(r[:, 0], r[:, 1], np.roll(r[:, 0], -1), np.roll(r[:, 1], -1)) for r in fechados]
        orientados = []
        for i, r in enumerate(fechados):
            px, py = 0.5 * (float(r[0, 0]) + float(r[1, 0])), 0.5 * (float(r[0, 1]) + float(r[1, 1]))
            cand = np.flatnonzero(
                (abs_areas > abs_areas[i]) & (bboxes[:, 0] <= bboxes[i, 0] + _REF_EPS) & (bboxes[:, 2] >= bboxes[i, 2] - _REF_EPS)
                & (bboxes[:, 1] <= bboxes[i, 1] + _REF_EPS) & (bboxes[:, 3] >= bboxes[i, 3] - _REF_EPS)
            )
            cont = sum(1 for j in cand if _ref_ponto_no_anel_arr(px, py, *edges_xy[j]))
            area_signed = areas[i]
            if (cont % 2 == 1 and area_signed > 0.0) or (cont % 2 == 0 and area_signed < 0.0):
                r, area_signed = r[::-1].copy(), -area_signed
            idx = min(range(len(r)), key=lambda k: (float(r[k, 0]), float(r[k, 1])))
            orientados.append((np.roll(r, -idx, axis=0), area_signed))
        orientados.sort(key=lambda item: (float(item[0][0, 0]), float(item[0][0, 1]), item[1]))
        orientados_out = [item[0] for item in orientados]
    abertos_raw = []
    for cam in abertos_ids:
        pts = np.array([coords[i] for i in cam], dtype=float)
        if (float(pts[-1, 0]), float(pts[-1, 1])) < (float(pts[0, 0]), float(pts[0, 1])):
            pts = pts[::-1].copy()
        abertos_raw.append(pts)
    return orientados_out, sorted(abertos_raw, key=lambda p: (float(p[0, 0]), float(p[0, 1]), float(p[-1, 0]), float(p[-1, 1]), len(p)))


# ---------- auxiliares geometricos e assercoes ----------
def _segs_de(poligonos, abertas=()):
    segs = [(*p[i], *p[(i + 1) % len(p)]) for p in poligonos for i in range(len(p))]
    segs.extend((*p[i], *p[i + 1]) for p in abertas for i in range(len(p) - 1))
    return np.asarray(segs, dtype=np.float64)


def _rot(pts, theta: float):
    c, s = math.cos(theta), math.sin(theta)
    return [(c * x - s * y, s * x + c * y) for x, y in pts]


def _transformar(poligonos, escala: float = 1.0, offset=(0.0, 0.0)):
    ox, oy = offset
    return [[(x * escala + ox, y * escala + oy) for x, y in p] for p in poligonos]


def _assert_bit_a_bit(obt, ref) -> None:
    fe_o, ab_o = obt
    fe_r, ab_r = ref
    assert len(fe_o) == len(fe_r) and len(ab_o) == len(ab_r)
    for a, b in zip(fe_o + ab_o, fe_r + ab_r):
        assert a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a.view(np.uint64), b.view(np.uint64))


def _checar_aneis_e_grupos(segs, areas_desc: list[float], tam_grupos: list[int], *, tol: float = 1e-6, atol_area: float = 1e-6):
    fe, ab = aneis.aneis_de_segmentos(segs, tol=tol)
    assert ab == [] and len(fe) == len(areas_desc), f"fe={len(fe)} ab={len(ab)}"
    areas_obt = sorted((_ref_area(r) for r in fe), key=lambda a: -abs(a))
    for obt, esp in zip(areas_obt, areas_desc):
        assert (obt > 0.0) == (esp > 0.0), f"sinal errado: obt={obt} esp={esp}"
        assert abs(obt - esp) <= max(atol_area, 1e-5 * abs(esp)), f"area: obt={obt} esp={esp}"
    grupos = oclusores._agrupar_aneis(fe)
    assert grupos is not None, f"_agrupar_aneis retornou None para areas={areas_obt}"
    assert sorted(len(rings) for rings, _ in grupos) == sorted(tam_grupos)
    assert sum(len(rings) for rings, _ in grupos) == len(fe)
    for rings, _ in grupos:
        assert _ref_area(rings[0]) > 0.0 and all(_ref_area(furo) < 0.0 for furo in rings[1:])
    return fe, grupos


# Geometrias canonicas com toque de borda
_EXT_CONC = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (8.0, 10.0), (2.0, 4.0), (0.0, 4.0)]  # area 70
_EXT_L = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0)]  # area 64
_EXT_TRI = [(0.0, 0.0), (10.0, 10.0), (0.0, 10.0)]  # area 50 (hipotenusa y=x)
_DIAM = [(0.0, 5.0), (5.0, 0.0), (10.0, 5.0), (5.0, 10.0)]  # area 50
_CAIXA_M = [(-1.0, -1.0), (11.0, -1.0), (11.0, 11.0), (-1.0, 11.0)]  # area 144


def _cena_bib1_sintetica():
    """Reducao sintetica de bib_1 idx=61 (Wall 1o Pav., 5 aneis, ~0.96 deg, 2 arestas na borda)."""
    th = 0.01681
    w0 = _rot([(0.0, 0.0), (0.123, 0.0), (0.123, 4.15), (0.0, 4.15)], th)
    c1 = _rot([(0.123 - 5e-12, 3.56), (0.154, 3.56), (0.154, 4.12), (0.123 - 5e-12, 4.12), (0.123 - 5e-12, 3.84)], th)
    c2 = _rot([(0.123 - 1e-11, 3.53), (0.154, 3.53), (0.154, 3.55), (0.123 - 1e-11, 3.55)], th)
    c3 = _rot([(0.123 - 5e-12, 0.05), (0.1385, 0.05), (0.1385, 3.44), (0.123 - 5e-12, 3.44)], th)
    c4 = _rot([(0.1385 - 5e-12, 0.06), (0.154, 0.06), (0.154, 3.43), (0.1385 - 5e-12, 3.43)], th)
    return [w0, c1, c2, c3, c4], [0.51045, 0.052545, 0.052235, 0.01736, 0.00062]


def _cena_bib0_sintetica():
    """Reducao sintetica de bib_0 idx=245 (Wall Terreo, camada 15.5mm x 15.5mm a ~3e-11)."""
    th = 0.01681
    w1 = _rot([(0.0, 0.0), (0.092, 0.0), (0.092, 4.58), (0.0, 4.58)], th)
    c3 = _rot([(0.092 - 3e-11, 4.447), (0.1075, 4.447), (0.1075, 4.4625), (0.092 - 3e-11, 4.4625), (0.092 - 3e-11, 4.455)], th)
    return [w1, c3], [0.42136, 0.00024025]


# ---------- (1) ACEITACAO (FALHA HOJE NO HEAD) ----------
@pytest.mark.parametrize(
    ("pols", "areas_desc", "tam_grupos"),
    [
        pytest.param([_EXT_CONC, [(3.0, 5.0), (5.0, 7.0), (6.0, 9.0)]], [70.0, 1.0], [1, 1], id="externo_inclinado_dist_0"),
        pytest.param([_EXT_CONC, [(3.0 + 1e-11, 5.0), (5.0 + 1e-11, 7.0), (6.0, 9.0)]], [70.0, 1.0], [1, 1], id="externo_inclinado_dist_1e11"),
        pytest.param([_EXT_L, [(4.0 - 1e-11, 5.0), (7.0, 5.0), (7.0, 8.0), (4.0 - 1e-11, 8.0)]], [64.0, 9.0], [1, 1], id="externo_vertical_dist_1e11"),
        pytest.param([_EXT_L, [(5.0, 4.0 - 1e-11), (6.0, 4.0 - 1e-11), (7.0, 7.0)]], [64.0, 1.5], [1, 1], id="externo_horizontal_dist_1e11"),
    ],
)
def test_aceitacao_externo_encosta_borda_dist_0_e_1e11(pols, areas_desc, tam_grupos):
    """Anel externo encostando por aresta (dist 0 e ~1e-11) mantem area > 0 e agrupa sem None."""
    _checar_aneis_e_grupos(_segs_de(pols), areas_desc, tam_grupos)


@pytest.mark.parametrize(
    ("pols", "areas_desc", "tam_grupos"),
    [
        pytest.param([_EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]], [50.0, -2.0], [2], id="furo_inclinado_dist_0"),
        pytest.param([_EXT_TRI, [(3.0 + 1e-11, 3.0), (5.0 + 1e-11, 5.0), (6.0, 8.0)]], [50.0, -2.0], [2], id="furo_inclinado_dist_1e11"),
        pytest.param([_DIAM, [(2.0 - 1e-11, 3.0), (3.0 - 1e-11, 2.0), (4.0, 4.0), (3.0, 5.0)]], [50.0, -3.0], [2], id="furo_diamante_ll_dist_1e11"),
        pytest.param([_EXT_TRI, [(3.0, 3.0), (4.0, 4.0), (5.0, 5.0), (6.0, 8.0)]], [50.0, -2.0], [2], id="furo_2_arestas_colineares_dist_0"),
    ],
)
def test_aceitacao_furo_encosta_borda_dist_0_e_1e11(pols, areas_desc, tam_grupos):
    """Furo interno encostando na borda do externo (dist 0 e ~1e-11) sai area < 0 e agrupa no pai."""
    _checar_aneis_e_grupos(_segs_de(pols), areas_desc, tam_grupos)


@pytest.mark.parametrize("eps", [pytest.param(0.0, id="dist_0"), pytest.param(1e-11, id="dist_1e11")])
def test_aceitacao_ilha_em_furo_encosta_borda(eps: float):
    """Ilha dentro de furo encostando na borda do furo sai area > 0 e gera 2 grupos ([ext, furo], [ilha])."""
    ilha = [(3.0 + eps, 3.0), (5.0 + eps, 5.0), (6.0, 8.0)]
    _checar_aneis_e_grupos(_segs_de([_CAIXA_M, _EXT_TRI, ilha]), [144.0, -50.0, 2.0], [2, 1])


@pytest.mark.parametrize("eps", [pytest.param(0.0, id="dist_0"), pytest.param(1e-11, id="dist_1e11")])
def test_aceitacao_toque_por_1_vertice_e_inscrito(eps: float):
    """Toque por 1 vertice (externo e furo) e furo inscrito com todos os vertices na borda."""
    _checar_aneis_e_grupos(_segs_de([_EXT_L, [(4.0 - eps, 6.0), (6.0, 5.0), (6.0, 7.0)]]), [64.0, 2.0], [1, 1])
    insc = [(2.5 - eps, 2.5), (7.5 + eps, 2.5), (7.5 + eps, 7.5), (2.5 - eps, 7.5)]
    _checar_aneis_e_grupos(_segs_de([_DIAM, insc]), [50.0, -25.0], [2])


@pytest.mark.parametrize(
    ("escala", "offset", "eps"),
    [
        pytest.param(1e-3, (0.0, 0.0), 0.0, id="mm_dist_0"),
        pytest.param(1e-3, (0.0, 0.0), 1e-11, id="mm_dist_1e11"),
        pytest.param(1.0, (0.0, 0.0), 1e-11, id="m_dist_1e11"),
        pytest.param(1e3, (0.0, 0.0), 0.0, id="km_dist_0"),
        pytest.param(1.0, (500_000.0, 7_500_000.0), 0.0, id="utm_dist_0"),
        pytest.param(1.0, (500_000.0, 7_500_000.0), 6e-11, id="utm_dist_1ulp"),
    ],
)
def test_aceitacao_escalas_mm_a_utm(escala: float, offset: tuple[float, float], eps: float):
    """Externo e furo com toque de borda funcionam de mm (1e-3) ate UTM (5e5, 7.5e6)."""
    f = escala * escala
    p_ext = _transformar([_EXT_CONC, [(3.0, 5.0), (5.0, 7.0), (6.0, 9.0)]], escala, offset)
    if eps:
        p_ext[1] = [(p_ext[1][0][0] + eps, p_ext[1][0][1]), (p_ext[1][1][0] + eps, p_ext[1][1][1]), p_ext[1][2]]
    _checar_aneis_e_grupos(_segs_de(p_ext), [70.0 * f, 1.0 * f], [1, 1], atol_area=max(1e-9, 1e-4 * f))
    p_furo = _transformar([_EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]], escala, offset)
    if eps:
        p_furo[1] = [(p_furo[1][0][0] + eps, p_furo[1][0][1]), (p_furo[1][1][0] + eps, p_furo[1][1][1]), p_furo[1][2]]
    _checar_aneis_e_grupos(_segs_de(p_furo), [50.0 * f, -2.0 * f], [2], atol_area=max(1e-9, 1e-4 * f))


def test_aceitacao_sintetico_bib1_idx61_e_bib0_idx245():
    """Reducoes sinteticas dos casos reais bib_1 idx=61 (5 aneis) e bib_0 idx=245: todos >0, sem None."""
    pols1, areas1 = _cena_bib1_sintetica()
    _checar_aneis_e_grupos(_segs_de(pols1), areas1, [1, 1, 1, 1, 1], atol_area=1e-5)
    pols0, areas0 = _cena_bib0_sintetica()
    _checar_aneis_e_grupos(_segs_de(pols0), areas0, [1, 1], atol_area=1e-6)


# ---------- (2) NAO-REGRESSAO BIT A BIT (PASSA HOJE) ----------
def test_nao_regressao_casos_canonicos_sem_toque_bit_a_bit():
    """Anel simples, furos, ilhas em furos, profundidade 4 e cadeias abertas: bit a bit igual ao atual."""
    r = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # noqa: E731
    for segs in (
        _segs_de([r(0, 0, 4, 2)]),
        _segs_de([_EXT_L]),
        _segs_de([r(0, 0, 10, 10), r(2, 2, 8, 8)]),
        _segs_de([r(0, 0, 20, 10), r(1, 1, 8, 9), r(11, 1, 19, 9)]),
        _segs_de([r(0, 0, 10, 10), r(1, 1, 9, 9), r(3, 3, 7, 7)]),
        _segs_de([r(0, 0, 12, 12), r(1, 1, 11, 11), r(2, 2, 10, 10), r(4, 4, 8, 8)]),
        _segs_de([r(0, 0, 10, 10), r(2, 2, 8, 8), r(15, 0, 20, 5)], abertas=[[(25, 0), (26, 1), (27, 0)]]),
    ):
        _assert_bit_a_bit(aneis.aneis_de_segmentos(segs), _ref_aneis_de_segmentos(segs))


def _pol_estrelado(rng: np.random.Generator, cx: float, cy: float, r_min: float, r_max: float, n: int):
    ang = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False) + float(rng.uniform(0.0, 2.0 * math.pi))
    return [(cx + float(ra * math.cos(a)), cy + float(ra * math.sin(a))) for ra, a in zip(rng.uniform(r_min, r_max, size=n), ang)]


def test_nao_regressao_fuzz_360_cenas_sem_toque_bit_a_bit():
    """Fuzz seed fixa (360 cenas >= 300) de aneis aninhados SEM toque: saida bit a bit igual ao atual."""
    rng = np.random.default_rng(20261121)
    for idx in range(360):
        tipo = idx % 5
        escala = (1e-2, 1.0, 10.0, 100.0)[idx % 4]
        offset = (500_000.0, 7_500_000.0) if (idx % 12 == 11) else (float(rng.uniform(-50, 50)), float(rng.uniform(-50, 50)))
        pols, abertas = [], []
        if tipo == 0:
            pols.append(_pol_estrelado(rng, 0.0, 0.0, 1.0, 4.0, int(rng.integers(3, 11))))
        elif tipo == 1:
            pols.append(_pol_estrelado(rng, 0.0, 0.0, 10.0, 12.0, int(rng.integers(6, 11))))
            pols.append(_pol_estrelado(rng, -3.5, 0.0, 0.8, 1.6, int(rng.integers(3, 8))))
            if idx % 2 == 0:
                pols.append(_pol_estrelado(rng, 3.5, 0.0, 0.8, 1.6, int(rng.integers(3, 8))))
        elif tipo == 2:
            for r0, r1, nmin in ((12.0, 14.0, 6), (6.0, 7.5, 6), (1.5, 3.0, 3)):
                pols.append(_pol_estrelado(rng, 0.0, 0.0, r0, r1, int(rng.integers(nmin, 10))))
        elif tipo == 3:
            for r0, r1, nmin in ((20.0, 22.0, 6), (12.5, 14.0, 6), (6.5, 8.0, 6), (1.5, 3.2, 3)):
                pols.append(_pol_estrelado(rng, 0.0, 0.0, r0, r1, int(rng.integers(nmin, 10))))
            pols.append(_pol_estrelado(rng, 45.0, 0.0, 2.0, 4.0, int(rng.integers(3, 7))))
        else:
            for gx in (0.0, 30.0):
                pols.append(_pol_estrelado(rng, gx, 0.0, 8.0, 9.5, int(rng.integers(6, 10))))
                pols.append(_pol_estrelado(rng, gx, 0.0, 2.0, 3.8, int(rng.integers(3, 8))))
            abertas.append([(50.0, 0.0), (52.0, 1.0), (54.0, -0.5)])
        segs = _segs_de(_transformar(pols, escala, offset), _transformar(abertas, escala, offset))
        segs = segs[rng.permutation(len(segs))].copy()
        inv = rng.random(len(segs)) < 0.5
        segs[inv] = segs[inv][:, [2, 3, 0, 1]]
        _assert_bit_a_bit(aneis.aneis_de_segmentos(segs), _ref_aneis_de_segmentos(segs))


# ---------- (3) DETERMINISMO, IMUTABILIDADE, ORDEM DOS SEGMENTOS ----------
def test_determinismo_3_rodadas_e_entrada_nao_mutada():
    """3 rodadas identicas bit a bit em cenas com toque; entrada read-only intacta e saida isolada."""
    pols1, _ = _cena_bib1_sintetica()
    for segs in (
        _segs_de(pols1),
        _segs_de([_EXT_CONC, [(3.0, 5.0), (5.0, 7.0), (6.0, 9.0)]]),
        _segs_de([_EXT_TRI, [(3.0, 3.0), (5.0, 5.0), (6.0, 8.0)]]),
    ):
        copia = segs.copy()
        segs.setflags(write=False)
        r1, r2, r3 = aneis.aneis_de_segmentos(segs), aneis.aneis_de_segmentos(segs), aneis.aneis_de_segmentos(segs)
        _assert_bit_a_bit(r1, r2)
        _assert_bit_a_bit(r1, r3)
        assert np.array_equal(segs, copia)
        if r1[0]:
            r1[0][0][:] = 999.0
            assert np.array_equal(segs, copia)
