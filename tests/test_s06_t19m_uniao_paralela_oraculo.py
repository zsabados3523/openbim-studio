# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19m: união 2D dos triângulos vetorizada e em partes paralelas (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19m-uniao-paralela.md. Não editar nesta tarefa.
Medido (casarão, 2 peças pesadas de ~400 mil triângulos): `silhueta_xy` leva 46 s (laço Python criando 1 polígono por triângulo + `unary_union` serial); o pai da planta fica 63 s, quase todo nisso.
CONTRATO:
1. `silhueta.uniao_triangulos_xy(verts, tris, threads=None)` -> geometria shapely (Polygon/MultiPolygon) ou None se nada sobra: união dos triângulos projetados em XY. Descarta triângulo com índice fora de [0, len(verts)),
   coordenada não finita ou área <= 1e-12 (mesmo critério de `componentes.pegada_xy`). VETORIZADA (um só `shapely.polygons` sobre o array) e a união é feita em partes (triângulos ordenados pelo centroide em x, ~2 x `threads`
   partes) em `ThreadPoolExecutor(max_workers=nucleos.limitar_threads(threads))`, depois a união das partes. Resultado igual à união ingênua (diferença simétrica de área <= 1e-9 x área) e igual para threads=1 e 4.
2. `silhueta.silhueta_xy(verts, tris, threads=None)` devolve os mesmos anéis de antes (exterior e furos) usando a função acima; vazio -> [].
3. `componentes.pegada_xy(verts, tris)` mantém a assinatura e o resultado e usa a mesma função com threads=1 (quem a chama já está em threads)."""
from __future__ import annotations

import numpy as np
import pytest
import shapely
from shapely import polygons, unary_union

import obim_geometria.componentes as C
import obim_geometria.silhueta as S


def _sopa(n, seed=0, lado=10.0):
    rng = np.random.default_rng(seed)
    v = rng.uniform(0, lado, size=(n * 3, 3))
    t = np.arange(n * 3).reshape(n, 3)
    return v, t


def _ingenua(v, t):
    tri = v[:, :2][t]
    area = 0.5 * np.abs((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1]) - (tri[:, 1, 1] - tri[:, 0, 1]) * (tri[:, 2, 0] - tri[:, 0, 0]))
    tri = tri[area > 1e-12]
    return unary_union(list(polygons(tri)))


def _igual(a, b, tol=1e-9):
    return a.symmetric_difference(b).area <= tol * max(1.0, b.area)


@pytest.mark.parametrize("threads", [1, 4])
def test_uniao_igual_a_ingenua(threads):
    v, t = _sopa(3000, seed=1)
    got = S.uniao_triangulos_xy(v, t, threads=threads)
    assert _igual(got, _ingenua(v, t))


def test_threads_1_e_4_iguais():
    v, t = _sopa(2000, seed=2)
    assert _igual(S.uniao_triangulos_xy(v, t, threads=1), S.uniao_triangulos_xy(v, t, threads=4))


def test_descarta_invalidos_e_vazio():
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [np.nan, 0, 0], [2, 2, 0], [2, 2, 0], [2, 2, 0]], float)
    t = np.array([[0, 1, 2], [0, 1, 99], [0, 1, 3], [4, 5, 6], [-1, 1, 2]])
    got = S.uniao_triangulos_xy(v, t, threads=1)
    assert got is not None and abs(got.area - 0.5) < 1e-12
    assert S.uniao_triangulos_xy(v, np.array([[3, 4, 5]]), threads=1) is None
    assert S.uniao_triangulos_xy(np.zeros((0, 3)), np.zeros((0, 3), int), threads=1) is None


def test_vetorizada_sem_laco_por_triangulo(monkeypatch):
    chamadas = []
    orig = shapely.polygons
    monkeypatch.setattr(S, "polygons", lambda *a, **k: chamadas.append(1) or orig(*a, **k), raising=False)
    monkeypatch.setattr(shapely, "polygons", lambda *a, **k: chamadas.append(1) or orig(*a, **k))
    v, t = _sopa(5000, seed=3)
    S.uniao_triangulos_xy(v, t, threads=2)
    assert 0 < len(chamadas) <= 4, f"polygons chamado {len(chamadas)} vezes (esperado vetorizado)"


def test_silhueta_xy_aneis_iguais_aos_de_antes():
    v, t = _sopa(800, seed=4)
    aneis = S.silhueta_xy([tuple(x) for x in v], [tuple(x) for x in t])
    ref = S._aneis(_ingenua(v, t))
    areas = lambda rs: sorted(round(shapely.Polygon(r).area, 9) for r in rs)
    assert len(aneis) == len(ref) > 0 and areas(aneis) == areas(ref)
    assert S.silhueta_xy([], []) == []


def test_pegada_xy_inalterada():
    v, t = _sopa(1500, seed=5)
    assert _igual(C.pegada_xy(v, t), _ingenua(v, t))
    assert C.pegada_xy(np.zeros((0, 3)), np.zeros((0, 3), int)) is None
