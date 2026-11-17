# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j4a: `oclusores_da_peca(caixa_peca, outras, z, *, tol_z=1e-3, margem_xy=1e-3) -> list[list[ndarray (n,2)]] | None`.
Contrato (cartão F0-S06-T19j4a): `caixa_peca = (xmin, ymin, xmax, ymax, zmin)`; `outras` = iterável de (verts, tris); resultado = um GRUPO
por peça oclusora (anéis fechados da seção dela no plano z), na ordem de `outras`; [] = nada oculta; None = mande ao HLR.
Por peça: malha vazia ignora, inválida => None; caixa XY (+margem) sem cruzar => ignora; zmin > z => ignora; zmax <= zmin_peca + tol_z => ignora;
inteira abaixo do plano e acima do zmin da peça => None; vértice no plano (1e-9) => None; seção aberta => None.
Oráculo analítico: prismas e tubos montados aqui; seção esperada = o polígono (área e vértices a mão), nunca da função."""
import sys
from pathlib import Path

import numpy as np
import pytest

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

TOL = 1e-9
Z = 1.5
CX = (0.95, 0.05, 2.05, 0.15, 0.9)  # caixa da janela: x 0.95..2.05, y 0.05..0.15, zmin 0.9


def f():  # importa dentro: falha com ModuleNotFoundError até existir a implementação
    from obim_geometria.oclusores import oclusores_da_peca
    return oclusores_da_peca


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # anti-horário


def prisma(poly, z0, z1):
    n = len(poly)
    v = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    t = [(0, i + 1, i) for i in range(1, n - 1)] + [(n, n + i, n + i + 1) for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        t += [(i, j, n + j), (i, n + j, n + i)]
    return np.array(v, float), np.array(t, int)


def tubo(ext, furo, z0, z1):
    """Prisma com furo (retângulos, mesma ordem de vértices): faces para fora; paredes do furo para dentro."""
    v = [(x, y, z) for z in (z0, z1) for x, y in ext + furo]
    ob, ib, ot, it = 0, 4, 8, 12
    t = []
    for i in range(4):
        j = (i + 1) % 4
        a, b, c, d = ob + i, ob + j, ib + j, ib + i
        t += [(a, c, b), (a, d, c), (a + 8, b + 8, c + 8), (a + 8, c + 8, d + 8)]  # fundo (para baixo) e topo (para cima)
        t += [(ob + i, ob + j, ot + j), (ob + i, ot + j, ot + i), (ib + j, ib + i, it + i), (ib + j, it + i, it + j)]
    return np.array(v, float), np.array(t, int)


def parede(x0, y0, x1, y1, z0=0.0, z1=3.0):
    return prisma(rect(x0, y0, x1, y1), z0, z1)


def area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def anel_igual(anel, pts, area_esperada):
    a = np.asarray(anel, float)
    if len(a) > 1 and np.allclose(a[0], a[-1]):
        a = a[:-1]
    d1, d2 = a - np.roll(a, 1, axis=0), np.roll(a, -1, axis=0) - a  # vértices colineares (arestas de triangulação) não contam
    a = a[np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) > 1e-12]
    assert len(a) == len(pts)
    np.testing.assert_allclose(a[np.lexsort((a[:, 1], a[:, 0]))], np.array(sorted(pts), float), atol=TOL, rtol=0)
    assert abs(area(a) - area_esperada) < TOL


def grupo_retangulo(g, x0, y0, x1, y1):
    assert len(g) == 1
    anel_igual(g[0], rect(x0, y0, x1, y1), (x1 - x0) * (y1 - y0))


# ---------- parede cortada, filtros ----------
def test_parede_cortada_cruzando_a_caixa_vira_um_grupo():
    r = f()(CX, [parede(0, 0, 1, 0.2)], Z)
    assert len(r) == 1
    grupo_retangulo(r[0], 0, 0, 1, 0.2)


def test_parede_longe_ignorada():
    assert f()(CX, [parede(10, 10, 11, 11)], Z) == []


def test_parede_acima_do_corte_ignorada():
    assert f()(CX, [parede(0, 0, 1, 0.2, 2.0, 3.0)], Z) == []


def test_peca_baixa_embaixo_da_janela_ignorada():
    assert f()(CX, [parede(1, 0, 2, 0.2, 0.2, 0.9)], Z) == []
    assert f()(CX, [parede(1, 0, 2, 0.2, 0.2, 0.9005)], Z) == []  # dentro de tol_z


def test_peca_baixa_que_passa_do_zmin_da_janela_e_none():
    assert f()(CX, [parede(1, 0, 2, 0.2, 0.2, 1.2)], Z) is None


def test_vertice_no_plano_e_none():
    assert f()(CX, [parede(0, 0, 1, 0.2, 0.0, Z)], Z) is None


def test_secao_aberta_e_none():
    v, t = parede(0, 0, 1, 0.2)
    assert f()(CX, [(v, t[:-2])], Z) is None


def test_duas_paredes_dois_grupos_na_ordem_de_outras():
    A, B = parede(0, 0, 1, 0.2), parede(2, 0, 4, 0.2)
    r = f()(CX, [A, B], Z)
    assert len(r) == 2
    grupo_retangulo(r[0], 0, 0, 1, 0.2)
    grupo_retangulo(r[1], 2, 0, 4, 0.2)
    r = f()(CX, [B, A], Z)  # ordem trocada na entrada, trocada na saída
    grupo_retangulo(r[0], 2, 0, 4, 0.2)
    grupo_retangulo(r[1], 0, 0, 1, 0.2)


def test_parede_com_furo_anel_e_furo_no_mesmo_grupo():
    caixa = (0.5, 0.2, 1.5, 0.8, 0.9)
    r = f()(caixa, [tubo(rect(0, 0, 3, 1), rect(1, 0.3, 2, 0.7), 0.0, 3.0)], Z)
    assert len(r) == 1 and len(r[0]) == 2
    a, b = sorted(r[0], key=area)
    anel_igual(a, rect(1, 0.3, 2, 0.7), -0.4)  # furo horário
    anel_igual(b, rect(0, 0, 3, 1), 3.0)       # externo anti-horário


def test_margem_xy_por_menos_cruza_por_mais_ignora():
    w = [parede(0, 0, 1, 0.2)]
    assert len(f()((1.0005, 0.05, 2.0, 0.15, 0.9), w, Z)) == 1   # folga 0,5 mm < margem 1 mm
    assert f()((1.002, 0.05, 2.0, 0.15, 0.9), w, Z) == []        # folga 2 mm > margem
    assert len(f()((1.002, 0.05, 2.0, 0.15, 0.9), w, Z, margem_xy=3e-3)) == 1


def test_entrada_vazia_e_malha_vazia():
    assert f()(CX, [], Z) == []
    assert f()(CX, iter(()), Z) == []
    assert f()(CX, [(np.zeros((0, 3)), np.zeros((0, 3), int))], Z) == []
    assert len(f()(CX, [(np.zeros((0, 3)), np.zeros((0, 3), int)), parede(0, 0, 1, 0.2)], Z)) == 1


@pytest.mark.parametrize("v,t", [
    (np.zeros((4, 2)), np.array([(0, 1, 2)])),
    (np.array([(0, 0, 0), (1, 0, 0), (0, 1, 3.0)]), np.array([(0, 1, 7)])),
    (np.array([(0, 0, 0), (1, np.nan, 0), (0, 1, 3.0)]), np.array([(0, 1, 2)])),
    (np.array([(0, 0, 0), (1, 0, 0), (0, 1, 3.0)]), np.array([(0, 1, 2)], float)),
])
def test_malha_invalida_e_none(v, t):
    assert f()(CX, [parede(0, 0, 1, 0.2), (v, t)], Z) is None


def test_aceita_iteravel_deterministico_e_nao_muta():
    pecas = [parede(0, 0, 1, 0.2), parede(2, 0, 4, 0.2)]
    c = [(v.copy(), t.copy()) for v, t in pecas]
    a = f()(CX, (p for p in pecas), Z)  # gerador
    b = f()(CX, pecas, Z)
    for (v, t), (v0, t0) in zip(pecas, c):
        np.testing.assert_array_equal(v, v0)
        np.testing.assert_array_equal(t, t0)
    assert len(a) == len(b) == 2
    for ga, gb in zip(a, b):
        assert len(ga) == len(gb) and all(np.array_equal(x, y) for x, y in zip(ga, gb))


# ---------- integração com linhas_peca_cortada (j3) ----------
def test_resultado_oculta_a_janela_embutida_na_parede():
    from obim_geometria.peca_cortada import linhas_peca_cortada
    v, t = prisma(rect(0.95, 0.05, 2.05, 0.15), 0.9, 2.1)  # embute 5 cm em cada parede
    ocl = f()(CX, [parede(0, 0, 1, 0.2), parede(2, 0, 4, 0.2)], Z)
    r = linhas_peca_cortada(v, t, Z, ocl)
    assert r
    for l in r:  # nada dentro da seção das paredes (x < 0.998 ou x > 2.002)
        assert not ((l[:, 0] < 0.998) | (l[:, 0] > 2.002)).any()
    todos = np.vstack(r)
    assert ((todos[:, 0] > 1.0 - 1e-6) & (todos[:, 0] < 2.0 + 1e-6)).any()  # o miolo do vão aparece


# ---------- rodada 2 (Opus): degrau, um grupo por anel externo, validação, lacunas ----------
CXP = (0.95, 0.05, 2.05, 0.15, 0.85)  # janela com peitoril z 0,85..0,90


def perfil(h, y0=0.0, y1=0.2):
    """Uma malha só: coluna x 0..0,5 até z 3 e degrau x 0,5..1,5 até z h (perfil em xz extrudado em y)."""
    p = [(0, 0), (.5, 0), (1.5, 0), (1.5, h), (.5, h), (.5, 3), (0, 3)]
    v = [(x, y, z) for y in (y0, y1) for x, z in p]
    cap = [(0, 1, 4), (0, 4, 5), (0, 5, 6), (1, 2, 3), (1, 3, 4)]
    t = [c for c in cap] + [tuple(7 + i for i in c[::-1]) for c in cap]
    for i in range(7):
        j = (i + 1) % 7
        t += [(i, j, 7 + j), (i, 7 + j, 7 + i)]
    return np.array(v, float), np.array(t, int)


def junta(*ms):
    o = np.cumsum([0] + [len(v) for v, _ in ms])
    return np.vstack([v for v, _ in ms]), np.vstack([t + k for (_, t), k in zip(ms, o)])


def test_degrau_acima_do_zmin_fora_da_secao_e_none():
    assert f()(CXP, [perfil(1.2)], Z) is None


def test_ressalto_abaixo_do_zmin_ignorado_e_parede_comum_continua():
    r = f()(CXP, [perfil(0.8)], Z)  # ressalto z 0,8 < 0,85: só a seção da coluna ocupa
    assert len(r) == 1
    grupo_retangulo(r[0], 0, 0, 0.5, 0.2)
    r = f()(CXP, [parede(0, 0, 1, 0.2)], Z)
    assert len(r) == 1
    grupo_retangulo(r[0], 0, 0, 1, 0.2)


def test_aresta_cujo_meio_cai_fora_de_anel_concavo_e_none():
    cunha = prisma([(1.9, 0.9), (0.9, 1.9), (1.0, 1.0)], 0.2, 1.2)  # vértices dentro do L, aresta (1,9;0,9)-(0,9;1,9) cruza o nicho
    corpo = junta(_prisma_L(), cunha)
    assert f()((0.5, 0.5, 1.5, 1.5, 0.85), [corpo], Z) is None


def _prisma_L():
    """Prisma z 0..3 com seção em L (côncava), triangulada à mão e soldada."""
    p = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    cap = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)]
    t = cap + [tuple(6 + i for i in c[::-1]) for c in cap]
    for i in range(6):
        j = (i + 1) % 6
        t += [(i, j, 6 + j), (i, 6 + j, 6 + i)]
    return np.array([(x, y, z) for z in (0.0, 3.0) for x, y in p], float), np.array(t, int)


def test_duas_caixas_sobrepostas_na_mesma_malha_dois_grupos():
    r = f()(CX, [junta(parede(0, 0, 1.5, 0.2), parede(1.2, 0.1, 2.5, 0.3))], Z)
    assert len(r) == 2
    a, b = sorted(r, key=lambda g: g[0][:, 0].min())
    grupo_retangulo(a, 0, 0, 1.5, 0.2)
    grupo_retangulo(b, 1.2, 0.1, 2.5, 0.3)


@pytest.mark.parametrize("caixa,kw", [
    ((2.0, 0.05, 1.0, 0.15, 0.9), {}),             # xmin > xmax
    ((0.95, 0.2, 2.05, 0.1, 0.9), {}),             # ymin > ymax
    (CX, {"tol_z": -1e-3}), (CX, {"margem_xy": -1e-3}),
    ((0.95, 0.05, float("inf"), 0.15, 0.9), {}), ((0.95, 0.05, 2.05, 0.15, float("nan")), {}),
])
def test_parametros_invalidos_sao_none(caixa, kw):
    assert f()(caixa, [parede(0, 0, 1, 0.2)], Z, **kw) is None


def test_z_nan_e_none():
    assert f()(CX, [parede(0, 0, 1, 0.2)], float("nan")) is None


def test_peca_longe_em_y_mas_cruzando_em_x_ignorada():
    assert f()(CX, [parede(0, 5, 1, 5.2)], Z) == []


def test_peca_toda_abaixo_com_zmax_2mm_acima_do_zmin_e_none():
    assert f()(CX, [parede(1, 0, 2, 0.2, 0.2, 0.902)], Z) is None


def test_vertice_a_1e10_do_plano_e_none_e_a_1e6_nao():
    assert f()(CX, [parede(0, 0, 1, 0.2, 0.0, Z + 1e-10)], Z) is None
    r = f()(CX, [parede(0, 0, 1, 0.2, 0.0, Z + 1e-6)], Z)
    assert r is not None and len(r) == 1
