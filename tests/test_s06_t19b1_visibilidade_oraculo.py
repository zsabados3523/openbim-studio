# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19b, parte 1 (sem HLR): `obim_geometria.visibilidade.linhas_visiveis(verts, tris, *, angulo_graus=0.001, tol_z=1e-4, min_len=1e-4)`.
Vista de cima (olho em +z). Saída: lista de polilinhas (K,2) em x,y do mundo, só as partes VISÍVEIS das arestas da malha.
Aqui: formato, malha vazia, triângulo degenerado, determinismo/entrada intacta e oclusão por cálculo analítico (posição do corte conhecida à mão).
Tolerância 0,1 mm de papel em 1:50 = 5 mm no mundo. Os helpers daqui também servem à parte 2 (HLR)."""
from __future__ import annotations

import importlib

import numpy as np
import pytest

TOL = 0.1 * 50 / 1000.0  # 0,1 mm de papel em 1:50 = 5 mm no mundo
PASSO = TOL / 5.0

def _lv():
    try:
        return importlib.import_module("obim_geometria.visibilidade").linhas_visiveis
    except ImportError as e:
        pytest.fail(f"módulo obim_geometria.visibilidade inexistente (a implementar na T19b): {e}")

def _caixa(x0, y0, z0, x1, y1, z1):
    v = [(x, y, z) for z in (z0, z1) for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    t = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return np.array(v, float), np.array(t)

def _junta(*ms):
    v, t, n = [], [], 0
    for mv, mt in ms:
        v.append(mv)
        t.append(mt + n)
        n += len(mv)
    return np.vstack(v), np.vstack(t)

def _cadeira():
    return _junta(_caixa(0, 0, 0.45, 0.5, 0.5, 0.5), _caixa(0, 0, 0.5, 0.5, 0.05, 0.9),
                  *[_caixa(x, y, 0, x + 0.05, y + 0.05, 0.45) for x in (0, 0.45) for y in (0, 0.45)])

def _segs(polis):
    return np.array([(p[i], p[i + 1]) for p in polis for i in range(len(p) - 1)], float).reshape(-1, 2, 2)

def _amostra(seg, passo=PASSO):
    d = seg[:, 1] - seg[:, 0]
    L = np.hypot(d[:, 0], d[:, 1])
    n = np.maximum(1, np.ceil(L / passo).astype(int))
    s = np.repeat(np.arange(len(seg)), n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    return seg[s, 0] + ((k + 0.5) / n[s])[:, None] * d[s], (L / n)[s]

def _dist(pts, alvo):
    import shapely
    if len(alvo) == 0:
        return np.full(len(pts), np.inf)
    arv = shapely.STRtree(shapely.linestrings(alvo))
    idx, dd = arv.query_nearest(shapely.points(pts), return_distance=True, all_matches=False)
    out = np.full(len(pts), np.inf)
    out[idx[0]] = dd
    return out

def _cobertura(a, b, tol=TOL):
    """Fração do comprimento de `a` (segmentos ou (pontos, pesos)) que fica a até `tol` de `b` (segmentos)."""
    p, w = a if isinstance(a, tuple) else _amostra(a)
    return 1.0 if len(p) == 0 else float(w[_dist(p, b) <= tol].sum() / w.sum())

def test_formato_da_saida():
    out = _lv()(*_cadeira())
    assert isinstance(out, list) and out
    for p in out:
        assert isinstance(p, np.ndarray) and p.ndim == 2 and p.shape[1] == 2 and len(p) >= 2 and np.isfinite(p).all()

def test_malha_vazia():
    lv = _lv()
    assert lv(np.zeros((0, 3)), np.zeros((0, 3), int)) == []
    assert lv(np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]), np.zeros((0, 3), int)) == []

def test_triangulo_degenerado_e_ignorado():
    lv = _lv()
    v, t = _caixa(0, 0, 0, 1, 1, 1)
    base = _segs(lv(v.copy(), t.copy()))
    v2 = np.vstack([v, [[10, 10, 0], [11, 10, 0], [12, 10, 0]]])  # colinear (área zero), longe
    t2 = np.vstack([t, [[8, 9, 10], [0, 0, 1], [8, 9, 10]]])  # colinear, índice repetido e duplicado
    got = _segs(lv(v2, t2))
    assert _cobertura(base, got) >= 0.99 and _cobertura(got, base) >= 0.99
    assert got[:, :, 0].max() < 5, "o degenerado produziu linha"

def test_deterministico_e_entrada_intacta():
    lv = _lv()
    v, t = _cadeira()
    v0, t0 = v.copy(), t.copy()
    a, b = lv(v, t), lv(v, t)
    assert np.array_equal(v, v0) and np.array_equal(t, t0) and v.dtype == v0.dtype and t.dtype == t0.dtype
    assert len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))

def test_triangulo_escondido_atras_de_outro_nao_gera_linha():
    grande = np.array([[0, 0, 1.0], [4, 0, 1], [0, 4, 1]])
    pequeno = np.array([[0.5, 0.5, 0.0], [0.5, 1.5, 0], [1.5, 0.5, 0]])  # abaixo e dentro da projeção do grande
    v, t = np.vstack([grande, pequeno]), np.array([[0, 1, 2], [3, 4, 5]])
    got = _segs(_lv()(v, t))
    ref = np.array([[(0, 0), (4, 0)], [(4, 0), (0, 4)], [(0, 4), (0, 0)]], float)
    assert _cobertura(got, ref, 1e-6) >= 0.999 and _cobertura(ref, got, 1e-6) >= 0.999

def test_aresta_parcialmente_coberta_e_cortada_no_ponto_certo():
    """A = [0,2]x[0,1]x[0,1] (baixa); B = [1,3]x[0.5,1.5]x[0,2] (alta, atravessa A). Visível de A: aresta y=1 só para x<=1; aresta x=2 só para y<=0.5."""
    v, t = _junta(_caixa(0, 0, 0, 2, 1, 1), _caixa(1, 0.5, 0, 3, 1.5, 2))
    segs = _segs(_lv()(v, t))

    def trecho(eixo, valor, faixa):
        s = segs[(np.abs(segs[:, :, eixo] - valor) < 1e-6).all(1)]
        s = s[(s[:, :, 1 - eixo] >= faixa[0] - 1e-6).all(1) & (s[:, :, 1 - eixo] <= faixa[1] + 1e-6).all(1)]
        return s[:, :, 1 - eixo]
    ya = trecho(1, 1.0, (0, 2))
    assert len(ya) and ya.min() == pytest.approx(0.0, abs=1e-3) and ya.max() == pytest.approx(1.0, abs=1e-3)
    assert np.abs(ya[:, 1] - ya[:, 0]).sum() == pytest.approx(1.0, abs=2e-3)
    xa = trecho(0, 2.0, (0, 1))
    assert len(xa) and xa.min() == pytest.approx(0.0, abs=1e-3) and xa.max() == pytest.approx(0.5, abs=1e-3)
    assert np.abs(xa[:, 1] - xa[:, 0]).sum() == pytest.approx(0.5, abs=2e-3)
