# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19o: `visibilidade.linhas_visiveis_multi(pecas)` (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19o-motor-multipeca.md. Não editar nesta tarefa.
CONTRATO: `pecas = [(verts (N,3), tris (M,3) int), ...]`; devolve lista (mesmo tamanho) de listas de polilinhas (K,2). Arestas candidatas só da própria peça; oclusão por todas as peças. Uma peça = idêntico a `linhas_visiveis`. Peça sem triângulos -> []. Lista vazia -> []."""
from __future__ import annotations

import numpy as np

from obim_geometria import visibilidade as V


def _caixa(x0, y0, z0, x1, y1, z1):
    v = np.array([[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], float)
    q = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    t = np.array([[a, b, c] for a, b, c, d in q] + [[a, c, d] for a, b, c, d in q], dtype=np.int64)
    return v, t


def _comp(pls):
    return float(sum(np.hypot(*np.diff(p, axis=0).T).sum() for p in pls))


def _igual(a, b):
    assert len(a) == len(b)
    ka = sorted(map(lambda p: np.round(p, 6).tobytes(), a))
    kb = sorted(map(lambda p: np.round(p, 6).tobytes(), b))
    assert ka == kb


def test_uma_peca_e_identica_a_linhas_visiveis():
    v, t = _caixa(0, 0, 0, 1, 1, 1)
    r = V.linhas_visiveis_multi([(v, t)])
    assert len(r) == 1
    _igual(r[0], V.linhas_visiveis(v, t))


def test_pecas_disjuntas_nao_mudam_umas_as_outras():
    a, b = _caixa(0, 0, 0, 1, 1, 1), _caixa(5, 0, 0, 6, 1, 2)
    r = V.linhas_visiveis_multi([a, b])
    _igual(r[0], V.linhas_visiveis(*a))
    _igual(r[1], V.linhas_visiveis(*b))


def test_peca_totalmente_sob_outra_some_e_a_de_cima_fica_inteira():
    baixa, alta = _caixa(1, 1, 0, 2, 2, 0.5), _caixa(0, 0, 1, 3, 3, 2)
    r = V.linhas_visiveis_multi([baixa, alta])
    assert r[0] == [] or _comp(r[0]) < 1e-6
    _igual(r[1], V.linhas_visiveis(*alta))


def test_oclusao_parcial_corta_so_a_parte_coberta():
    a, b = _caixa(0, 0, 0, 2, 2, 0.5), _caixa(1, -1, 1, 3, 3, 2)  # b cobre a faixa x in [1,2] de a
    r = V.linhas_visiveis_multi([a, b])
    sozinha = _comp(V.linhas_visiveis(*a))
    juntas = _comp(r[0])
    assert 0.0 < juntas < sozinha
    for p in r[0]:
        dentro = (p[:, 0] > 1.001) & (p[:, 0] < 2.999) & (p[:, 1] > -0.999) & (p[:, 1] < 2.999)
        assert not dentro.any(), "linha de a ficou sob b"
    _igual(r[1], V.linhas_visiveis(*b))


def test_ordem_das_pecas_nao_muda_o_resultado_de_cada_uma():
    a, b = _caixa(0, 0, 0, 2, 2, 0.5), _caixa(1, -1, 1, 3, 3, 2)
    r1, r2 = V.linhas_visiveis_multi([a, b]), V.linhas_visiveis_multi([b, a])
    _igual(r1[0], r2[1])
    _igual(r1[1], r2[0])


def test_casos_de_borda():
    assert V.linhas_visiveis_multi([]) == []
    v, t = _caixa(0, 0, 0, 1, 1, 1)
    r = V.linhas_visiveis_multi([(v, np.zeros((0, 3), np.int64)), (v, t)])
    assert r[0] == [] and len(r) == 2
    _igual(r[1], V.linhas_visiveis(v, t))
