# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j4a2: regra do degrau de `oclusores_da_peca(caixa_peca, outras, z, *, tol_z=1e-3, margem_xy=1e-3)`.
Contrato (cartão F0-S06-T19j4a, rodada 2): para peça que cruza o plano, a parte abaixo do plano que fica acima de
zmin_peca + tol_z (degrau, bancada, ressalto, viga/rampa inclinada) tem de caber, em vértices e pontos médios de arestas, na
união dos anéis externos da peça (com seus furos), com tolerância `margem_xy`; qualquer ponto fora (ou dentro de furo) => None;
degrau abaixo do zmin da janela é ignorado. Casos a mão (coordenadas conhecidas), nada vem da função."""
import sys
import time
from pathlib import Path

import numpy as np
import pytest

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

Z = 1.5
CXP = (0.95, 0.05, 2.05, 0.15, 0.85)  # janela com peitoril z 0,85..0,90


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
    v = [(x, y, z) for z in (z0, z1) for x, y in ext + furo]
    t = []
    for i in range(4):
        j = (i + 1) % 4
        a, b, c, d = i, j, 4 + j, 4 + i
        t += [(a, c, b), (a, d, c), (a + 8, b + 8, c + 8), (a + 8, c + 8, d + 8)]
        t += [(i, j, 8 + j), (i, 8 + j, 8 + i), (4 + j, 4 + i, 12 + i), (4 + j, 12 + i, 12 + j)]
    return np.array(v, float), np.array(t, int)


def parede(x0, y0, x1, y1, z0=0.0, z1=3.0):
    return prisma(rect(x0, y0, x1, y1), z0, z1)


def junta(*ms):
    o = np.cumsum([0] + [len(v) for v, _ in ms])
    return np.vstack([v for v, _ in ms]), np.vstack([t + k for (_, t), k in zip(ms, o)])


def extrude(p, y0, y1, cap=None):
    """Perfil (x, z) extrudado em y: malha fechada; `cap` = triângulos do perfil (leque se omitido)."""
    n = len(p)
    cap = cap or [(0, i, i + 1) for i in range(1, n - 1)]
    v = [(x, y, z) for y in (y0, y1) for x, z in p]
    t = list(cap) + [tuple(n + i for i in c[::-1]) for c in cap]
    for i in range(n):
        j = (i + 1) % n
        t += [(i, j, n + j), (i, n + j, n + i)]
    return np.array(v, float), np.array(t, int)


def perfil(h, y0=0.0, y1=0.2):
    """Coluna x 0..0,5 até z 3 e degrau x 0,5..1,5 até z h, numa malha só."""
    p = [(0, 0), (.5, 0), (1.5, 0), (1.5, h), (.5, h), (.5, 3), (0, 3)]
    return extrude(p, y0, y1, [(0, 1, 4), (0, 4, 5), (0, 5, 6), (1, 2, 3), (1, 3, 4)])


def prisma_L():
    """Prisma z 0..3 com seção em L (côncava; nicho x 1..2, y 1..2), triangulada à mão."""
    p = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    cap = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)]
    t = cap + [tuple(6 + i for i in c[::-1]) for c in cap]
    for i in range(6):
        j = (i + 1) % 6
        t += [(i, j, 6 + j), (i, 6 + j, 6 + i)]
    return np.array([(x, y, z) for z in (0.0, 3.0) for x, y in p], float), np.array(t, int)


# ---------- degrau ----------
def test_degrau_acima_do_zmin_fora_da_secao_e_none():
    assert f()(CXP, [perfil(1.2)], Z) is None


def test_ressalto_abaixo_do_zmin_ignorado_e_parede_comum_continua():
    r = f()(CXP, [perfil(0.8)], Z)  # ressalto z 0,8 < 0,85: só a seção da coluna conta
    assert r is not None and len(r) == 1 and len(r[0]) == 1
    r = f()(CXP, [parede(0, 0, 1, 0.2)], Z)
    assert r is not None and len(r) == 1


def test_aresta_cujo_meio_cai_fora_de_anel_concavo_e_none():
    cunha = prisma([(1.9, 0.9), (0.9, 1.9), (1.0, 1.0)], 0.85, 1.2)  # vértices dentro do L; só o MEIO da aresta do topo cai no nicho
    assert f()((0.5, 0.5, 1.5, 1.5, 0.85), [junta(prisma_L(), cunha)], Z) is None


def test_viga_inclinada_acima_do_zmin_fora_da_secao_e_none():
    # perfil (x,z): (0;3) (0,4;3) (2;0) (1,6;0), y -0,4..0,3: seção em z=1,5 é x 0,8..1,2; em z=0,85 a viga está em x 1,147..1,547
    viga = extrude([(0, 3), (0.4, 3), (2, 0), (1.6, 0)], -0.4, 0.3)
    assert f()((0.9, -0.3, 2.1, 0.25, 0.85), [viga], Z) is None
    # zmin 1,4985: só 0,5 mm de viga acima de zmin+tol (z >= 1,4995), em x 0,8003..1,2003: cabe na margem de 1 mm
    assert f()((0.9, -0.3, 2.1, 0.25, 1.4985), [viga], Z) is not None


def test_tubo_com_bloco_dentro_do_furo_acima_do_zmin_e_none():
    caixa = (0.5, 0.5, 1.5, 1.5, 0.85)
    t = tubo(rect(0, 0, 2, 2), rect(.5, .5, 1.5, 1.5), 0.0, 3.0)
    assert f()(caixa, [junta(t, prisma(rect(.8, .8, 1.2, 1.2), 0.2, 1.2))], Z) is None  # topo 1,2 > zmin: dentro do furo
    r = f()(caixa, [junta(t, prisma(rect(.8, .8, 1.2, 1.2), 0.2, 0.8))], Z)         # topo 0,8 < zmin: ignorado
    assert r is not None and len(r) == 1 and len(r[0]) == 2


@pytest.mark.parametrize("folga,esperado_none", [(5e-4, False), (2e-3, True), (3e-3, True), (5e-3, True)])
def test_tolerancia_2_a_5_mm_fora_da_secao(folga, esperado_none):
    calco = prisma(rect(1 + folga, 0.05, 1 + folga + 1e-4, 0.15), 0.2, 1.2)  # lasca fina a `folga` da parede x 0..1
    r = f()(CXP, [junta(parede(0, 0, 1, 0.2), calco)], Z)
    assert (r is None) == esperado_none
    if not esperado_none:
        assert len(r) == 1


def _cilindro(n):
    a = 2 * np.pi * np.arange(n) / n
    return prisma((np.c_[0.5 * np.cos(a) + 1.5, 0.5 * np.sin(a) + 0.1]).tolist(), 0.0, 3.0)  # 2n vértices, raio 0,5 em torno de (1,5; 0,1)


def _melhor_de_3(malha):
    ts, r = [], None
    for _ in range(3):
        t0 = time.perf_counter()
        r = f()(CXP, [malha], Z)
        ts.append(time.perf_counter() - t0)
    assert r is None or (len(r) == 1 and len(r[0]) == 1)  # o teto de pontos pode mandar ao HLR (None); se decidir, tem de acertar
    return min(ts)


def test_desempenho_cilindro_nao_e_quadratico():
    # 10 mil e 40 mil vértices: linear dá razão ~4, quadrático ~16 (relógio de runner varia: razão + teto largo, não limite justo)
    t10, t40 = _melhor_de_3(_cilindro(5000)), _melhor_de_3(_cilindro(20000))
    assert t40 / max(t10, 1e-3) < 8.0, f"t10={t10:.3f}s t40={t40:.3f}s"
    assert t40 < 5.0


@pytest.mark.parametrize("xmax,esperado_none", [(0.9, False), (1.0005, False), (1.0015, True)])
def test_so_conta_ponto_da_fatia_dentro_da_caixa_da_peca_mais_margem(xmax, esperado_none):
    # lasca a 2 mm da parede (x 1,002..1,0021): fora da seção, mas só importa se estiver a <= 1 mm (margem_xy) da caixa da janela
    lasca = prisma(rect(1.002, 0.05, 1.0021, 0.15), 0.2, 1.2)
    r = f()((0.5, 0.05, xmax, 0.15, 0.85), [junta(parede(0, 0, 1, 0.2), lasca)], Z)  # distância caixa-lasca: 102 mm, 1,5 mm, 0,5 mm
    assert (r is None) == esperado_none
    if not esperado_none:
        assert len(r) == 1 and len(r[0]) == 1


def test_degrau_longe_da_caixa_da_peca_nao_oculta():
    # janela só sobre a coluna (x 0,1..0,4); o degrau (x 0,5..1,5, z 1,2) fica 10 cm fora da caixa: parede/degrau fora da janela não oculta
    r = f()((0.1, 0.05, 0.4, 0.15, 0.85), [perfil(1.2)], Z)
    assert r is not None and len(r) == 1 and len(r[0]) == 1


def laje_inclinada():
    """Laje fechada x,y -5..5, topo z = 1,55 - 0,3 x, espessura 0,1 (12 triângulos): cruza o plano z=1,5 numa faixa |x| < 0,1667."""
    v, t = prisma(rect(-5, -5, 5, 5), 0.0, 1.0)
    v[:, 2] = 1.45 - 0.3 * v[:, 0] + 0.1 * (np.arange(8) >= 4)
    return v, t


@pytest.mark.parametrize("caixa", [(0.6, 2.0, 1.4, 2.2, 0.85), (0.6, -0.1, 1.4, 0.1, 0.85)])
def test_laje_inclinada_grande_cujos_vertices_ficam_fora_da_caixa_e_none(caixa):
    # triângulos enormes cruzam a caixa da janela sem ter vértice dentro dela; abaixo do plano, acima do zmin e fora da seção => HLR
    assert f()(caixa, [laje_inclinada()], Z) is None


@pytest.mark.parametrize("y0,esperado_none", [(3.0, False), (0.1515, False), (0.1505, True)])
def test_limite_em_y_da_caixa_decide(y0, esperado_none):
    # calço fora da seção (x 1,002..1,5, 2 mm da parede) que cruza a caixa em x; só a distância em y (102 mm, 1,5 mm, 0,5 mm) decide
    calco = prisma(rect(1.002, y0, 1.5, y0 + 0.05), 0.2, 1.2)
    r = f()((0.5, 0.05, 1.2, 0.15, 0.85), [junta(parede(0, 0, 1, 0.2), calco)], Z)
    assert (r is None) == esperado_none
    if not esperado_none:
        assert len(r) == 1 and len(r[0]) == 1
