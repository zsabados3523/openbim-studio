# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24q_grade_2o_nivel_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import hashlib
import math
import os
import pickle
import statistics
import sys
import time
import tracemalloc
from unittest import mock
import numpy as np
import pytest
import obim_geometria.visib_mapa as visib_mapa
import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _arestas_candidatas,
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_faixas import _passagem_faixas_orientadas
from obim_geometria.visib_mapa import (
    _compactar_H,
    _filtrar_e_recortar,
    _mapa_z_conservador,
    _varrer_cels_triangulos,
)
from obim_geometria.visibilidade import _cull_tris, linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas as _cenas_t22a
from test_s06_t24j_motor_mapa_z_oraculo_b import CENAS as _CENAS_T24J  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo import _LIMITE_MEM_BYTES, _assert_equivalente, _caixa, _rss_bytes  # noqa: F401



def _esfera_uv(
    cx: float, cy: float, cz: float, r: float, nlat: int, nlon: int, *, rot_x: float = 0.65
) -> tuple[np.ndarray, np.ndarray]:
    """Esfera fechada com 2 * (nlat - 1) * nlon triangulos (nlat aneis internos + 2 polos)."""
    lats = np.linspace(-math.pi / 2.0, math.pi / 2.0, nlat + 1)[1:-1]
    lons = np.linspace(0.0, 2.0 * math.pi, nlon, endpoint=False)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    x = r * np.cos(la) * np.cos(lo)
    y = r * np.cos(la) * np.sin(lo)
    z = r * np.sin(la)
    v_mid = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    v = np.vstack([[[0.0, 0.0, -r]], v_mid, [[0.0, 0.0, r]]])
    if rot_x:
        c, s = math.cos(rot_x), math.sin(rot_x)
        v = v @ np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=np.float64).T
    v = v + np.array([cx, cy, cz], dtype=np.float64)
    nr = len(lats)
    j = np.arange(nlon, dtype=np.int64)
    j1 = (j + 1) % nlon
    tris = [np.column_stack([np.zeros(nlon, np.int64), 1 + j1, 1 + j])]
    for r_i in range(nr - 1):
        b0 = 1 + r_i * nlon
        b1 = 1 + (r_i + 1) * nlon
        tris.append(np.column_stack([b0 + j, b0 + j1, b1 + j1]))
        tris.append(np.column_stack([b0 + j, b1 + j1, b1 + j]))
    top = len(v) - 1
    b_top = 1 + (nr - 1) * nlon
    tris.append(np.column_stack([np.full(nlon, top, np.int64), b_top + j, b_top + j1]))
    return v, np.vstack(tris)


def _terreno(nx: int, ny: int, lado: float, amp: float, z0: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(nx + 1) * lado, np.arange(ny + 1) * lado)
    z = z0 + amp * np.sin(xs * 0.37) * np.cos(ys * 0.23)
    v = np.c_[xs.ravel(), ys.ravel(), z.ravel()]
    i = (np.arange(ny)[:, None] * (nx + 1) + np.arange(nx)[None, :]).ravel()
    t = np.stack([np.c_[i, i + 1, i + nx + 2], np.c_[i, i + nx + 2, i + nx + 1]], 1).reshape(-1, 3)
    return v, t.astype(np.int64)


def _juntar_malhas(*malhas: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    vs, ts, off = [], [], 0
    for v, t in malhas:
        vs.append(v)
        ts.append(t + off)
        off += len(v)
    return np.vstack(vs), np.vstack(ts)


def _cantos_dominio(lx: float, ly: float, z0: float = 0.0, z1: float = 1.0) -> list[tuple[np.ndarray, np.ndarray]]:
    return [
        _caixa(0.0, 0.0, z0, 0.8, 0.8, z1),
        _caixa(lx - 0.8, 0.0, z0, lx, 0.8, z1),
        _caixa(0.0, ly - 0.8, z0, 0.8, ly, z1),
        _caixa(lx - 0.8, ly - 0.8, z0, lx, ly, z1),
    ]


def _calcular_g(dx_dom: float, dy_dom: float) -> float:
    """Mesma formula de `g` de visibilidade.py (usada para construir casos em fronteiras de celula)."""
    g = max(0.002, math.sqrt(dx_dom * dy_dom / 5_500_000.0), (dx_dom + dy_dom) / 2_900_000.0)
    while (math.ceil(dx_dom / g) + 2) * (math.ceil(dy_dom / g) + 2) > 6_000_000:
        g *= 1.05
    return g


# ---------------------------------------------------------------------------
# (1) Cenas sinteticas obrigatorias do projeto
# ---------------------------------------------------------------------------

def _cena_peca_densa_80x80():
    """Peca densa (~20k tris em 0,7 m) em cena grande 80x80 m com caixas nos cantos."""
    return [
        _esfera_uv(40.0, 40.0, 1.0, 0.35, 100, 100),  # 19.800 tris
        _caixa(39.4, 39.6, 0.0, 40.6, 40.4, 0.8, rot_z=0.25),
        _caixa(39.8, 39.2, 1.1, 40.5, 40.8, 1.5, incl_y=0.15),
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_borda_e_fronteira_celula():
    """Peca densa encostada no canto (0,0) e na borda (80,80), + pares a <= 5e-7 m de fronteira de celula."""
    g = _calcular_g(80.0, 80.0)
    # Encosta esfera densa exatamente em x=0, y=0 (cx=r, cy=r)
    r = 0.30
    densa_canto = _esfera_uv(r, r, 1.0, r, 92, 92, rot_x=0.0)
    # Segunda esfera encostada na borda maxima (80, 80)
    densa_max = _esfera_uv(80.0 - r, 80.0 - r, 1.0, r, 90, 90, rot_x=0.4)
    # Pares oclusor/oclusado a <= 5e-7 m de fronteiras exatas k*g e k*g/4 perto da peca densa
    xf = round(10.0 / g) * g
    yf = round(10.0 / g) * g
    pecas = [
        densa_canto,
        densa_max,
        _caixa(0.0, 0.0, 0.0, 0.65, 0.65, 0.55),  # sob a esfera do canto (0,0)
        _caixa(79.35, 79.35, 0.0, 80.0, 80.0, 0.55),  # sob a esfera do canto (80,80)
        _caixa(xf - 0.15, yf - 0.15, 2.0, xf - 2e-7, yf + 0.15, 2.4),
        _caixa(xf + 2e-7, yf - 0.12, 0.0, xf + 0.15, yf + 0.12, 0.8),
        # Aresta levemente inclinada cruzando fronteira de celula a 3e-7 m do oclusor
        _caixa(xf - 0.08, yf - 0.08, 1.2, xf + 3e-7, yf + 0.08, 1.5, rot_z=0.002),
        *_cantos_dominio(80.0, 80.0),
    ]
    return pecas


def _cena_duas_pecas_densas_sobrepostas_z():
    """Duas pecas densas sobrepostas em Z diferentes (uma interpenetrada, outra acima)."""
    return [
        _esfera_uv(35.0, 42.0, 0.8, 0.35, 92, 92, rot_x=0.5),
        _esfera_uv(35.12, 42.08, 1.25, 0.35, 92, 92, rot_x=1.1),
        _esfera_uv(35.05, 42.02, 2.2, 0.22, 64, 64, rot_x=0.2),
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_triangulo_grande_atravessando_densa():
    """Triangulo grande (T_grd no mesmo cg + laje muito grande) atravessando peca densa."""
    # Tira estreita (dx=0.024 < g=0.034 -> fora do mapa Z conservador; dy=0.34 -> >400 subcelulas -> T_grd no mesmo cg!)
    tira_tgrd = _caixa(39.88, 39.83, 1.50, 39.904, 40.17, 1.62, incl_y=0.12)
    # Laje grande 6x6 m inclinada atravessando o lado direito da peca densa (vai para nivel mais grosso next_rem)
    laje_grande = _caixa(40.10, 37.0, 0.7, 46.10, 43.0, 1.3, incl_y=0.18, rot_z=0.12)
    return [
        _esfera_uv(40.0, 40.0, 1.0, 0.35, 92, 92, rot_x=0.6),
        tira_tgrd,
        laje_grande,
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_aresta_longa_atravessando_densa():
    """Aresta longa de parede (40 m) atravessando a peca densa de ponta a ponta."""
    return [
        _esfera_uv(40.0, 40.0, 1.5, 0.35, 92, 92, rot_x=0.55),
        _caixa(20.0, 39.94, 0.2, 60.0, 40.06, 0.9),  # parede 40 m visivel dos lados e ocluida no meio pela esfera
        _caixa(20.0, 40.14, 0.6, 60.0, 40.24, 1.4, incl_y=0.03),  # viga longa deslocada em Y cruzando a esfera
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_densa_escondida_atras_laje():
    """Peca densa totalmente escondida sob laje solida: resultado da peca 0 deve ser vazio."""
    return [
        _esfera_uv(40.0, 40.0, 0.8, 0.35, 92, 92, rot_x=0.6),
        _caixa(38.0, 38.0, 2.5, 42.0, 42.0, 2.8),  # laje cobrindo com folga
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_dois_clusters_50m():
    """Uma unica peca contendo 2 clusters densos separados por >50 m em X e Y."""
    c1 = _esfera_uv(10.0, 10.0, 1.0, 0.30, 74, 74, rot_x=0.5)  # ~10.8k tris
    c2 = _esfera_uv(60.0, 60.0, 1.0, 0.30, 74, 74, rot_x=0.9)  # ~10.8k tris
    peca_dupla = _juntar_malhas(c1, c2)
    return [
        peca_dupla,
        _caixa(9.5, 9.5, 0.0, 10.5, 10.5, 0.85, rot_z=0.2),
        _caixa(59.5, 59.5, 0.0, 60.5, 60.5, 0.85, rot_z=-0.3),
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_utm_densa():
    """Cena densa completa em coordenadas UTM georreferenciadas (500000, 7400000)."""
    off = np.array([500_000.0, 7_400_000.0, 750.0], dtype=np.float64)
    base = [
        _esfera_uv(40.0, 40.0, 1.2, 0.35, 90, 90, rot_x=0.6),
        _caixa(39.88, 39.88, 1.0, 40.12, 40.12, 1.35, incl_y=0.3),
        _caixa(20.0, 39.92, 0.2, 60.0, 40.08, 0.9),
        *_cantos_dominio(80.0, 80.0),
    ]
    return [(v + off, t.copy()) for v, t in base]


_CENAS_DENSAS = {
    "peca_densa_80x80": _cena_peca_densa_80x80,
    "borda_e_fronteira_celula": _cena_borda_e_fronteira_celula,
    "duas_pecas_densas_sobrepostas_z": _cena_duas_pecas_densas_sobrepostas_z,
    "triangulo_grande_atravessando_densa": _cena_triangulo_grande_atravessando_densa,
    "aresta_longa_atravessando_densa": _cena_aresta_longa_atravessando_densa,
    "densa_escondida_atras_laje": _cena_densa_escondida_atras_laje,
    "dois_clusters_50m": _cena_dois_clusters_50m,
    "utm_densa": _cena_utm_densa,
}

_CENAS_PEQUENAS_T22A = ["a00", "a05", "a17", "d0", "degenerada", "bordas", "tol_celula", "matar_m5_0", "georref"]
_CENAS_PEQUENAS_T24J = list(_CENAS_T24J.keys())


def _rodar(monkeypatch, pecas, *, subgrade: str | None, trabalhadores: int = 1):
    if subgrade is None:
        monkeypatch.delenv("OBIM_VISIB_SUBGRADE", raising=False)
    else:
        monkeypatch.setenv("OBIM_VISIB_SUBGRADE", subgrade)
    return linhas_visiveis_multi(pecas, trabalhadores=trabalhadores)


# ---------------------------------------------------------------------------
# Testes (1): Equivalencia ligado vs desligado e threads 1, 2, 4, 8
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", list(_CENAS_DENSAS.keys()))
def test_equivalencia_cenas_densas_sinteticas(nome, monkeypatch):
    pecas = _CENAS_DENSAS[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"densa/{nome}")
    if nome == "densa_escondida_atras_laje":
        assert ref[0] == [] and obt[0] == [], "peca densa escondida sob laje deve ter saida vazia"


@pytest.mark.parametrize("nome", _CENAS_PEQUENAS_T22A)
def test_equivalencia_cenas_pequenas_t22a(nome, monkeypatch):
    pecas = _cenas_t22a()[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"t22a/{nome}")


@pytest.mark.parametrize("nome", _CENAS_PEQUENAS_T24J)
def test_equivalencia_cenas_pequenas_t24j(nome, monkeypatch):
    pecas = _CENAS_T24J[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"t24j/{nome}")


@pytest.mark.parametrize(
    "nome",
    [
        "peca_densa_80x80",
        "duas_pecas_densas_sobrepostas_z",
        "triangulo_grande_atravessando_densa",
        "aresta_longa_atravessando_densa",
        "dois_clusters_50m",
        "utm_densa",
    ],
)
def test_threads_1_2_4_8_iguais_cenas_densas(nome, monkeypatch):
    pecas = _CENAS_DENSAS[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    base_1 = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(base_1, ref, exigir_bit_a_bit=True, ctx=f"threads/{nome}/t1_vs_ref")
    for n_trab in (2, 4, 8):
        obt_n = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=n_trab)
        _assert_equivalente(obt_n, base_1, exigir_bit_a_bit=True, ctx=f"threads/{nome}/t{n_trab}")


# ---------------------------------------------------------------------------
# Testes (2): Desempenho relativo (densa <= 35%, sem densa <= 1,05x) + memoria
# ---------------------------------------------------------------------------

def _cena_benchmark_densa_grande():
    """Esfera subdividida ~100k triangulos em cena 60x70 m com 20 caixas espalhadas."""
    esfera = _esfera_uv(30.0, 35.0, 1.0, 0.25, 224, 224, rot_x=0.65)  # 99.904 tris
    caixas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        _caixa(59.0, 69.0, 0.0, 60.0, 70.0, 1.0),
    ]
    for i in range(1, 19):
        x = 2.5 + (i * 3.1) % 54.0
        y = 2.5 + (i * 3.7) % 64.0
        caixas.append(_caixa(x, y, 0.0, x + 1.2, y + 1.0, 1.0 + 0.05 * i))
    return [esfera, *caixas]


def _cena_benchmark_sem_densa():
    """Cena media (~29k tris bem espalhados em 24x24 m, sem celulas densas) + 20 caixas."""
    terr = _terreno(120, 120, 0.2, 0.12, 0.0)
    caixas = [
        _caixa(
            1.0 + (i % 5) * 4.5, 1.0 + (i // 5) * 5.0, 0.1,
            2.5 + (i % 5) * 4.5, 2.2 + (i // 5) * 5.0, 1.5 + 0.1 * i,
        )
        for i in range(20)
    ]
    return [terr, *caixas]


def test_desempenho_peca_densa_grande_ate_35_porcento(monkeypatch):
    """Ligada leva <= 35% da desligada (mediana de 2 rodadas), < 60 s total, memoria < 2 GB."""
    pecas = _cena_benchmark_densa_grande()
    assert sum(len(t) for _, t in pecas) >= 95_000

    t_off: list[float] = []
    t_on: list[float] = []
    res_off = res_on = None

    tracemalloc.start()
    try:
        t_total0 = time.perf_counter()
        for r in range(2):
            t0 = time.perf_counter()
            res_off = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
            t_off.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            res_on = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
            t_on.append(time.perf_counter() - t0)
        t_total = time.perf_counter() - t_total0
        _, pico_tm = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    rss = _rss_bytes()
    assert res_off is not None and res_on is not None
    _assert_equivalente(res_on, res_off, exigir_bit_a_bit=True, ctx="bench_densa_100k")
    assert pico_tm < _LIMITE_MEM_BYTES, f"pico tracemalloc excedeu 2 GB: {pico_tm / 1e6:.1f} MB"
    assert rss < _LIMITE_MEM_BYTES, f"RSS excedeu 2 GB: {rss / 1e6:.1f} MB"
    assert t_total < 60.0, f"teste de benchmark excedeu 60 s ({t_total:.2f} s)"

    med_off = statistics.median(t_off)
    med_on = statistics.median(t_on)
    razao = med_on / med_off if med_off > 0.0 else math.inf
    assert med_on <= 0.35 * med_off, (
        f"2o nivel insuficiente na peca densa: ligada={med_on:.3f}s desligada={med_off:.3f}s "
        f"({razao * 100:.1f}% > 35.0%)"
    )
