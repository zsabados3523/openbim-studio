# SPDX-License-Identifier: AGPL-3.0-or-later
"""Malhas sintéticas e régua de área para o oráculo F0-S06-T18a (sem IFC). Não é de `app/`; o implementador não edita."""
from __future__ import annotations

import math

from shapely.geometry import Polygon


def area_aneis(aneis):
    """Área da união descrita pelos anéis (regra par-ímpar: anel dentro de N outros conta com sinal (-1)^N). Independe da orientação e da ordem."""
    polis = [Polygon(a) for a in aneis]
    total = 0.0
    for i, p in enumerate(polis):
        fundo = sum(1 for j, q in enumerate(polis) if j != i and q.contains(p))
        total += p.area * (-1) ** fundo
    return total


def bbox_aneis(aneis):
    xs = [x for a in aneis for x, _y in a]
    ys = [y for a in aneis for _x, y in a]
    return min(xs), min(ys), max(xs), max(ys)


def cubo(x=0.0, y=0.0, z=0.0, lado=1.0):
    v = [(x + dx * lado, y + dy * lado, z + dz * lado) for dz in (0, 1) for dy in (0, 1) for dx in (0, 1)]
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, [t for a, b, c, d in q for t in ((a, b, c), (a, c, d))]


def prisma(poligono, h=1.0):
    """Prisma reto sobre polígono 2D convexo ou em leque (fatias em triângulo a partir do vértice 0): tampa baixa, alta e laterais."""
    n = len(poligono)
    v = [(x, y, 0.0) for x, y in poligono] + [(x, y, h) for x, y in poligono]
    t = [(0, i, i + 1) for i in range(1, n - 1)] + [(n, n + i + 1, n + i) for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        t += [(i, j, n + j), (i, n + j, n + i)]
    return v, t


def juntar(*malhas):
    v, t = [], []
    for mv, mt in malhas:
        t += [tuple(i + len(v) for i in tri) for tri in mt]
        v += mv
    return v, t


def anel_de_blocos(h=1.0):
    """8 blocos 1x1 em volta de um furo 1x1 no centro (quadrado 3x3 com buraco): área 8."""
    return juntar(*[prisma([(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)], h) for i in range(3) for j in range(3) if (i, j) != (1, 1)])


def cilindro(r=0.3, n=24):
    return prisma([(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)], 1.5)
