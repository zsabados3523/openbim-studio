# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19b, parte 2 (HLR do ifcopenshell): `linhas_visiveis` contra o HLR (`desenho.processar`, mesma malha num IFC mínimo),
tolerância 0,1 mm de papel em 1:50 (5 mm no mundo), cobertura >= 99% do comprimento NOS DOIS SENTIDOS. O HLR também traça as diagonais
coplanares da triangulação (ângulo 0), que o contrato descarta (limiar de ângulo); por isso o trecho do HLR que cai só sobre diagonal coplanar
é retirado da referência. A referência é validada contra o contorno analítico. Helpers e régua vêm da parte 1."""
from __future__ import annotations

import math
import pathlib
import re
import tempfile

import numpy as np
import pytest
import s06_t07_aux as X
import s06_t18a_aux as Z
from test_s06_t19b1_visibilidade_oraculo import PASSO, TOL, _amostra, _caixa, _cadeira, _cobertura, _dist, _junta, _lv, _segs

def _gira(m, graus_z=0.0, graus_x=0.0, graus_y=0.0):
    v = m[0] - m[0].mean(0)
    for ang, (i, j) in ((graus_x, (1, 2)), (graus_y, (2, 0)), (graus_z, (0, 1))):
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        v = v.copy()
        v[:, [i, j]] = np.stack([c * v[:, i] - s * v[:, j], s * v[:, i] + c * v[:, j]], 1)
    return v + m[0].mean(0), m[1]

def _prisma(n=24, r=0.5, h=1.0):
    p = [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    v = [(x, y, 0.0) for x, y in p] + [(x, y, h) for x, y in p]
    t = [(0, i + 1, i) for i in range(1, n - 1)] + [(n, n + i, n + i + 1) for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        t += [(i, j, n + j), (i, n + j, n + i)]
    return np.array(v, float), np.array(t)

def _placa_furo():
    """Placa 4x4x0,2 com furo quadrado 1x1 no centro (anel de 16 triângulos em cima e em baixo, paredes do furo)."""
    o, i = [(0, 0), (4, 0), (4, 4), (0, 4)], [(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5)]
    v = [(x, y, z) for z in (0.0, 0.2) for (x, y) in o + i]
    t = []
    for k in range(4):
        k1 = (k + 1) % 4
        ok, ok1, ik, ik1 = k, k1, 4 + k, 4 + k1
        t += [(8 + ok, 8 + ok1, 8 + ik1), (8 + ok, 8 + ik1, 8 + ik), (ok, ik1, ok1), (ok, ik, ik1)]  # topo, fundo
        t += [(ok, ok1, 8 + ok1), (ok, 8 + ok1, 8 + ok)]  # parede externa
        t += [(ik, 8 + ik1, ik1), (ik, 8 + ik, 8 + ik1)]  # parede do furo (normal para o furo)
    return np.array(v, float), np.array(t)

CASOS = {
    "cubo": _caixa(0, 0, 0, 1, 1, 1),
    "caixa45": _gira(_caixa(0, 0, 0, 2, 1, 1), graus_z=45),
    "caixa_inclinada": _gira(_caixa(0, 0, 0, 2, 1, 0.5), graus_z=30, graus_y=25),
    "prisma24": _prisma(24),
    "duas_caixas": _junta(_caixa(0, 0, 0, 2, 1, 1), _caixa(1.5, 0.4, 1.2, 3, 1.6, 2)),
    "cadeira": _cadeira(),
    "placa_furo": _placa_furo(),
}

def _volume(m):
    a, b, c = (m[0][m[1][:, k]] for k in range(3))
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)

def _coplanares(m):
    """Arestas (2D) entre 2 triângulos coplanares de mesma orientação: diagonais de triangulação, sem traço no contrato."""
    v, t = m
    n = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    n /= np.linalg.norm(n, axis=1)[:, None]
    viz = {}
    for f, tri in enumerate(t):
        for k in range(3):
            viz.setdefault(frozenset((int(tri[k]), int(tri[(k + 1) % 3]))), []).append(f)
    cop, resto = [], []
    for e, fs in viz.items():
        a, b = sorted(e)
        seg = (v[a, :2], v[b, :2])
        (cop if len(fs) == 2 and np.dot(n[fs[0]], n[fs[1]]) > 1 - 1e-12 else resto).append(seg)
    return np.array(cop).reshape(-1, 2, 2), np.array(resto).reshape(-1, 2, 2)

def _pseg(pw):
    """Pontos amostrados do HLR viram micro-segmentos (alvo de distância)."""
    p = pw[0]
    return np.stack([p, p + 1e-9], 1)

def _hlr(malha, tmp):
    from obim_geometria import desenho
    f, pavs = X.estrutura("IFC4", n_pav=1)
    el = X.caixa(f, "IfcBuildingElementProxy", "P", 0, 0, 0, 1, 1, 1)
    X.conter(f, pavs[0], el)
    Z.densificar(f, el, ([tuple(map(float, p)) for p in malha[0]], [tuple(map(int, q)) for q in malha[1]]))
    f.write(str(tmp / "m.ifc"))
    r = desenho.processar({"arquivo": str(tmp / "m.ifc"), "elementos": [[el.id(), el.GlobalId]], "threads": 1,
                           "vista": {"tipo": "PLANTA", "escala": 1.0, "altura_corte_m": 50.0, "pavimento": pavs[0].GlobalId}})
    assert r.get("ok"), r.get("erro")
    segs = []
    for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', r["svg"][r["svg"].find("</style>"):]):
        pts = [(float(a), -float(b)) for a, b in re.findall(r"(-?[\d.]+(?:e[-+]?\d+)?),(-?[\d.]+(?:e[-+]?\d+)?)", d)]
        segs += list(zip(pts, pts[1:]))
    return np.array(segs, float).reshape(-1, 2, 2)

def _referencia(malha):
    """HLR como (pontos, pesos) amostrados, sem o que só cai sobre diagonal coplanar da triangulação."""
    with tempfile.TemporaryDirectory() as d:
        ex = _hlr(malha, pathlib.Path(d))
    cop, resto = _coplanares(malha)
    p, w = _amostra(ex)
    ficar = ~((_dist(p, cop) <= TOL) & (_dist(p, resto) > TOL))
    return p[ficar], w[ficar]

# ---------------------------------------------------------------- testes
@pytest.mark.parametrize("nome", list(CASOS))
def test_malhas_do_oraculo_sao_fechadas_e_orientadas(nome):
    m = CASOS[nome]
    assert _volume(m) > 1e-3, "orientação invertida ou malha aberta"
    arestas = {}
    for tri in m[1].tolist():
        for k in range(3):
            e = (tri[k], tri[(k + 1) % 3])
            arestas[e] = arestas.get(e, 0) + 1
    assert all(c == 1 for c in arestas.values()), "aresta dirigida repetida"
    assert all(arestas.get((b, a), 0) == 1 for a, b in arestas), "aresta sem par oposto (malha não fechada)"

@pytest.mark.parametrize("nome", ["cubo", "caixa45", "prisma24"])
def test_referencia_hlr_confere_contorno_analitico(nome):
    """Valida a referência: o contorno visto de cima de um sólido convexo é o polígono da tampa superior (HLR e conta à mão devem coincidir)."""
    m = CASOS[nome]
    topo = m[0][m[0][:, 2] > m[0][:, 2].max() - 1e-9][:, :2]
    c = topo.mean(0)
    topo = topo[np.argsort(np.arctan2(topo[:, 1] - c[1], topo[:, 0] - c[0]))]
    analitico = np.stack([topo, np.roll(topo, -1, 0)], 1)
    ex = _referencia(m)
    assert _cobertura(ex, analitico) >= 0.99 and _cobertura(analitico, _pseg(ex)) >= 0.99

@pytest.mark.parametrize("nome", list(CASOS))
def test_linhas_visiveis_igual_hlr_nos_dois_sentidos(nome):
    lv = _lv()
    v, t = CASOS[nome]
    got = _segs(lv(v.copy(), t.copy()))
    ex = _referencia(CASOS[nome])
    assert len(got), "nenhuma linha"
    assert _cobertura(ex, got) >= 0.99, "HLR com trecho sem par no motor (linha faltando)"
    pg, wg = _amostra(got)
    assert float(wg[_dist(pg, _pseg(ex)) <= TOL].sum() / wg.sum()) >= 0.99, "motor com trecho sem par no HLR (linha sobrando)"
