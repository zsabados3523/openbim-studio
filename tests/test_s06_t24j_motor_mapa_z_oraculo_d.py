# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 4 de test_s06_t24j_motor_mapa_z_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
import threading
import time
from unittest import mock
import numpy as np
import pytest
import obim_geometria.visib_faixas as visib_faixas
import obim_geometria.visib_mapa as visib_mapa
import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _aplicar_corte,
    _arestas_candidatas,
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_mapa import _compactar_H, _unir_intervalos, _varrer_cels_triangulos
from obim_geometria.visibilidade import (
    _cull_tris,
    _dedup_triangulos,
    _limpar_malha,
    _visibilidade_hibrida,
    linhas_visiveis_multi,
)
from test_s06_t24j_motor_mapa_z_oraculo import _linhas_visiveis_multi_ref  # noqa: F401
from test_s06_t24j_motor_mapa_z_oraculo_b import _assert_equivalente, _caixa, _cena_casa_compacta, _cena_tres_chaves_distintas, _comprimento_total, _hash_resultado, _instalar_spy_mapa_z  # noqa: F401



def test_mutante_03_respeita_tol_z():
    """Mutante 3: ignorar tol_z no filtro pre-dedup ou no mapa Z esconde aresta dentro da tolerancia."""
    tol = 1e-2
    teto = _caixa(0.0, 0.0, 0.9, 4.0, 4.0, 1.0)
    # Dentro da tolerancia (z=0.995 -> diferenca 0.005 < tol_z=0.01): topo visivel (perimetro 8 m)
    dentro_tol = _caixa(1.0, 1.0, 0.0, 3.0, 3.0, 1.0 - 5e-3)
    # Abaixo alem da tolerancia (z=0.98 -> diferenca 0.02 > tol_z=0.01): escondida (0 linhas)
    fora_tol = _caixa(1.0, 1.0, 0.0, 3.0, 3.0, 1.0 - 2e-2)

    for n_trab in (1, 8):
        r_vis = linhas_visiveis_multi([teto, dentro_tol], tol_z=tol, trabalhadores=n_trab)
        r_hid = linhas_visiveis_multi([teto, fora_tol], tol_z=tol, trabalhadores=n_trab)
        assert _comprimento_total(r_vis[1]) == pytest.approx(8.0, abs=1e-3)
        assert len(r_hid[1]) == 0
        _assert_equivalente(r_vis, _linhas_visiveis_multi_ref([teto, dentro_tol], tol_z=tol), contexto=f"tol_z_vis/n={n_trab}")
        _assert_equivalente(r_hid, _linhas_visiveis_multi_ref([teto, fora_tol], tol_z=tol), contexto=f"tol_z_hid/n={n_trab}")

    # Tambem diretamente em visib_mapa._filtrar_e_recortar
    P = np.array(
        [
            [0.0, 0.0, 1.0], [4.0, 0.0, 1.0], [0.0, 4.0, 1.0],  # triangulo em z=1.0
            [0.5, 0.5, 1.0 - 5e-3], [1.5, 0.5, 1.0 - 5e-3],  # aresta 5 mm abaixo
        ],
        dtype=np.float64,
    )
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, _ = _preparar_triangulos(P, np.array([[0, 1, 2]]))
    ea, eb = np.array([3], dtype=np.int64), np.array([4], dtype=np.int64)
    a, b = P[ea], P[eb]
    d = b - a
    ex0, ex1 = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    ey0, ey1 = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    ezmin = np.minimum(a[:, 2], b[:, 2])
    pe, pt = np.array([0, 0], dtype=np.int64), np.array([0, 0], dtype=np.int64)

    H_grande, H_pequena = [], []
    visib_mapa._filtrar_e_recortar(
        pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, len(A), 1e-2, -1e-6, H_grande,
    )
    visib_mapa._filtrar_e_recortar(
        pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, len(A), 1e-4, -1e-6, H_pequena,
    )
    assert len(_compactar_H(H_grande, limpar=True)[0]) == 0, "com tol_z=1e-2, diferenca de 5e-3 nao pode ocluir"
    assert len(_compactar_H(H_pequena, limpar=True)[0]) == 1, "com tol_z=1e-4, diferenca de 5e-3 deve ocluir"


def test_mutante_04_resultado_independente_do_numero_de_threads(monkeypatch):
    """Mutante 4: resultado variar com trabalhadores=1, 2, 4, 8 sob intercalacao concorrente."""
    pecas = _cena_casa_compacta() + _cena_tres_chaves_distintas()[6:10]
    ref = _linhas_visiveis_multi_ref(pecas)
    h_ref = _hash_resultado(ref)
    _instalar_spy_mapa_z(monkeypatch, atraso=0.01)

    resultados = {n: linhas_visiveis_multi(pecas, trabalhadores=n) for n in (1, 2, 4, 8)}
    for n, res in resultados.items():
        assert _hash_resultado(res) == h_ref, f"trabalhadores={n} divergiu da referencia"
        _assert_equivalente(res, resultados[1], contexto=f"mutante_04/n={n}")
        for i, (pa, pb) in enumerate(zip(res, resultados[1])):
            assert len(pa) == len(pb) and all(np.array_equal(x, y) for x, y in zip(pa, pb)), (
                f"trabalhadores={n} peca {i} nao bit a bit igual a n=1"
            )
