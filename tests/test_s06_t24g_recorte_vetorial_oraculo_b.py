# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24g_recorte_vetorial_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24g_recorte_vetorial_oraculo import _ENCOLHERES, _REF_EPS, _assert_igual_ref, _poligono_L, _poligono_estrelado, _rect, _referencia_recortar, _transladar_aneis, _transladar_pols  # noqa: F401



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
