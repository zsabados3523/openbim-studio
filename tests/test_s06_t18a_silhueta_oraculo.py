# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T18a (unitário de `obim_geometria/silhueta.py`): `silhueta_xy(verts, tris)` -> aneis [(x, y)] (exterior e furos; triângulo de área ~0 ou com NaN/inf descartado, nunca levanta);
`eh_pesada(n, limiar=LIMIAR_PADRAO=40000)` (n > limiar). Só malhas sintéticas, sem IFC."""
from __future__ import annotations

import math

import pytest
from s06_t18a_malha import anel_de_blocos, area_aneis, bbox_aneis, cilindro, cubo, juntar
from shapely.geometry import Point, Polygon

import obim_geometria.silhueta as S


def test_cubo_e_um_quadrado():
    r = S.silhueta_xy(*cubo(lado=2.0))
    assert len(r) == 1 and area_aneis(r) == pytest.approx(4.0) and bbox_aneis(r) == pytest.approx((0, 0, 2, 2))


def test_forma_em_L():
    v, t = juntar(cubo(0, 0), cubo(1, 0), cubo(0, 1))
    r = S.silhueta_xy(v, t)
    assert len(r) == 1 and area_aneis(r) == pytest.approx(3.0) and bbox_aneis(r) == pytest.approx((0, 0, 2, 2))
    assert not Polygon(r[0]).contains(Point(1.5, 1.5)) and Polygon(r[0]).contains(Point(0.5, 1.5))


def test_furo_preservado():
    r = S.silhueta_xy(*anel_de_blocos())
    assert len(r) == 2 and area_aneis(r) == pytest.approx(8.0)
    assert sorted(round(abs(Polygon(a).area), 6) for a in r) == [1.0, 9.0]


def test_sobreposicao_une_sem_somar_duas_vezes():
    r = S.silhueta_xy(*juntar(cubo(0, 0, lado=2.0), cubo(1, 1, 3.0, lado=2.0)))
    assert area_aneis(r) == pytest.approx(7.0)


def test_degenerados_descartados():
    v, t = cubo()
    v = v + [(9.0, 9.0, 0.0), (9.0, 9.0, 5.0), (3.0, 3.0, 0.0)]
    t = t + [(8, 9, 10), (8, 8, 9), (8, 10, 9)]  # vertical sobre um ponto; dois vértices iguais
    v = v + [(5.0, 5.0, 0.0), (6.0, 5.0, 0.0), (7.0, 5.0, 0.0)]
    t = t + [(11, 12, 13)]  # colinear
    r = S.silhueta_xy(v, t)
    assert len(r) == 1 and area_aneis(r) == pytest.approx(1.0) and bbox_aneis(r) == pytest.approx((0, 0, 1, 1))


def test_so_degenerados_ou_vazia():
    assert S.silhueta_xy([], []) == []
    assert S.silhueta_xy([(0, 0, 0), (0, 0, 1), (0, 0, 2)], [(0, 1, 2)]) == []


def test_cilindro_vira_poligono_da_base():
    r = S.silhueta_xy(*cilindro(0.3, 24))
    assert len(r) == 1 and bbox_aneis(r) == pytest.approx((-0.3, -0.3, 0.3, 0.3), abs=1e-6)
    assert area_aneis(r) == pytest.approx(0.5 * 24 * 0.3 ** 2 * math.sin(2 * math.pi / 24), rel=1e-6)


def test_eh_pesada_e_limiar_padrao():
    assert S.LIMIAR_PADRAO == 40000
    assert S.eh_pesada(40001) and not S.eh_pesada(39999) and not S.eh_pesada(0)
    assert S.eh_pesada(11, limiar=10) and not S.eh_pesada(5, limiar=10) and not S.eh_pesada(10, limiar=10)


def test_vertices_nao_finitos_sao_ignorados():
    nan, inf = float("nan"), float("inf")
    v, t = cubo()
    v = v + [(nan, 0, 0), (5, inf, 0), (6, 6, 0), (7, 6, 0)]
    t = t + [(8, 9, 10), (9, 10, 11), (8, 10, 11)]
    r = S.silhueta_xy(v, t)
    assert len(r) == 1 and area_aneis(r) == pytest.approx(1.0)
    assert S.silhueta_xy([(nan, nan, nan)] * 3, [(0, 1, 2)]) == []

