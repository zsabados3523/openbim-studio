# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j3: `linhas_peca_cortada(verts, tris, z, aneis_oclusores=(), *, encolher=5e-4) -> list[ndarray (K,2)] | None`.
Contrato (cartão F0-S06-T19j3): None = "mande ao HLR" (vértice/face no plano; seção aberta; malha inválida); malha toda acima = [];
caso geral = linhas da parte abaixo do plano + contorno da seção, recortadas fora dos anéis oclusores (seção das paredes, no plano).
Oráculo INDEPENDENTE por raios: a cena é um prisma convexo (polígono, z0..z1) construído aqui, com anéis relevantes à mão
(base em z0 e topo em min(z1, zc)); amostra a cada ~5 mm; raio +z contra faces horizontais da parte abaixo (disco convexo com
margem) e contra o prisma dos anéis oclusores (par-ímpar, queda para baixo do plano zc). Visível => coberta (>= 99,9%);
oculta => nenhuma linha a menos de 1 mm. Faixas de indiferença: perto da borda do anel (visível se profundidade <= 0,3 mm,
oculta se >= 2 mm; entre as duas não se exige nada) e perto de borda de face (margem 0,1 mm). Nunca compara com o HLR."""
import sys
from pathlib import Path

import numpy as np
import pytest

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

PASSO, TOL_LIN = 0.005, 1e-3


def f():  # importa dentro: falha com ImportError até existir a implementação
    from obim_geometria.peca_cortada import linhas_peca_cortada
    return linhas_peca_cortada


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # anti-horário


def prisma(poly, z0, z1):
    """Malha soldada, faces para fora (poly convexo anti-horário)."""
    n = len(poly)
    v = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    t = [(0, i + 1, i) for i in range(1, n - 1)] + [(n, n + i, n + i + 1) for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        t += [(i, j, n + j), (i, n + j, n + i)]
    return np.array(v, float), np.array(t, int)


# parede com vão em x 1..2 (dois anéis separados, espessura y 0..0.2), seção no plano zc
PAREDE = [np.array(rect(0, 0, 1, 0.2), float), np.array(rect(2, 0, 4, 0.2), float)]
ZC = 1.5


# ---------- oráculo por raios ----------
def segs_de(pts):
    p = np.asarray(pts, float)
    return np.c_[p, np.roll(p, -1, axis=0)]


def dist_a_segs(P, S):
    """Distância mínima de cada ponto de P (n,2) ao conjunto de segmentos S (m,4)."""
    if len(S) == 0:
        return np.full(len(P), np.inf)
    a, d = S[:, :2], S[:, 2:] - S[:, :2]
    l2 = np.maximum((d ** 2).sum(1), 1e-30)
    w = P[:, None, :] - a[None]
    u = np.clip((w * d[None]).sum(2) / l2, 0, 1)
    return np.sqrt(((w - u[..., None] * d[None]) ** 2).sum(2)).min(1)


def polilinhas_em_segs(linhas):
    return np.vstack([np.c_[l[:-1], l[1:]] for l in linhas if len(l) > 1] or [np.zeros((0, 4))])


def amostras(poly, z):
    pts = []
    for s in segs_de(poly):
        n = max(1, int(np.ceil(np.hypot(s[2] - s[0], s[3] - s[1]) / PASSO)))
        u = (np.arange(n) + 0.5) / n
        pts.append(np.c_[s[0] + u * (s[2] - s[0]), s[1] + u * (s[3] - s[1]), np.full(n, z)])
    return np.vstack(pts)


def dist_convexo(P, poly):
    """Distância assinada (positiva dentro) ao polígono convexo anti-horário."""
    S = segs_de(poly)
    e = S[:, 2:] - S[:, :2]
    w = P[:, None, :] - S[None, :, :2]
    return ((e[None, :, 0] * w[..., 1] - e[None, :, 1] * w[..., 0]) / np.hypot(e[:, 0], e[:, 1])[None]).min(1)


def dentro_par_impar(P, aneis):
    n = np.zeros(len(P), int)
    for r in aneis:
        for x0, y0, x1, y1 in segs_de(r):
            c = (y0 > P[:, 1]) != (y1 > P[:, 1])
            xi = x0 + (P[:, 1] - y0) * (x1 - x0) / np.where(y1 == y0, 1, y1 - y0)
            n += c & (P[:, 0] < xi)
    return n % 2 == 1


def status(cena, P):
    """+1 visível exigido, -1 oculta exigida, 0 indiferente (por amostra)."""
    poly, z0, z1, zc, ocl = cena
    st = np.ones(len(P), int)
    blocos = [(z0, poly)] + ([(z1, poly)] if z1 < zc else [])
    for zb, pol in blocos:  # face horizontal acima do ponto bloqueia; faixa de 0,1 mm da borda = indiferente
        d, acima = dist_convexo(P[:, :2], pol), zb > P[:, 2] + 1e-6
        st[acima & (d >= 1e-4)] = -1
        st[acima & (np.abs(d) < 1e-4) & (st > 0)] = 0
    if len(ocl):
        dentro = dentro_par_impar(P[:, :2], ocl)
        prof = dist_a_segs(P[:, :2], np.vstack([segs_de(r) for r in ocl]))
        oculta, ok = dentro & (prof >= 2e-3), (~dentro) | (prof <= 3e-4)
        st[oculta] = -1
        st[~oculta & ~ok & (st > 0)] = 0
    return st


def confere(cena, linhas):
    poly, z0, z1, zc, ocl = cena
    assert isinstance(linhas, list) and all(l.ndim == 2 and l.shape[1] == 2 and len(l) >= 2 for l in linhas)
    P = np.vstack([amostras(poly, z0), amostras(poly, min(z1, zc))])
    st = status(cena, P)
    S = polilinhas_em_segs(linhas)
    vis, ocu = P[st > 0, :2], P[st < 0, :2]
    if len(vis):
        cob = (dist_a_segs(vis, S) <= TOL_LIN).mean()
        assert cob >= 0.999, f"cobertura das visíveis {cob:.4f}"
    if len(ocu):  # oculta que nenhuma visível encobre perto: não pode haver linha a menos de 1 mm
        longe = ocu if not len(vis) else ocu[dist_a_segs(ocu, np.c_[vis, vis]) > 2 * TOL_LIN]
        assert (dist_a_segs(longe, S) > TOL_LIN).all(), "há linha emitida sobre trecho oculto"
    todos = np.vstack(linhas) if linhas else np.zeros((0, 2))  # nada fora das arestas relevantes
    assert (dist_a_segs(todos, np.vstack([segs_de(poly)])) <= TOL_LIN).all(), "linha fora das arestas da peça"


def roda(poly, z0, z1, ocl=PAREDE, zc=ZC, **kw):
    v, t = prisma(poly, z0, z1)
    v0, t0 = v.copy(), t.copy()
    r = f()(v, t, zc, ocl, **kw)
    np.testing.assert_array_equal(v, v0)
    np.testing.assert_array_equal(t, t0)
    return r, (poly, z0, z1, zc, list(ocl))


# ---------- casos a mão ----------
def test_janela_embutida_5cm_zero_linhas_dentro_da_parede():
    r, cena = roda(rect(0.95, 0.05, 2.05, 0.15), 0.9, 2.1)
    confere(cena, r)
    for l in r:  # nada dentro da seção da parede (x < 0.998 ou x > 2.002)
        assert not ((l[:, 0] < 0.998) | (l[:, 0] > 2.002)).any()


def test_embutido_5mm():
    r, cena = roda(rect(0.995, 0.05, 2.005, 0.15), 0.9, 2.1)
    confere(cena, r)


def test_batente_faceando_a_parede_colinear_nao_some():
    r, cena = roda(rect(1, 0, 2, 0.2), 0.9, 2.1)  # x=1 e x=2 colineares com as bordas dos anéis
    confere(cena, r)
    S = polilinhas_em_segs(r)
    for x in (1.0, 2.0):  # as duas arestas verticais do batente aparecem inteiras
        P = np.c_[np.full(39, x), np.linspace(0.005, 0.195, 39)]
        assert (dist_a_segs(P, S) <= TOL_LIN).all()


def test_batente_a_0_2mm_dentro_da_parede_fica():
    r, cena = roda(rect(1 - 2e-4, 0, 2 + 2e-4, 0.2), 0.9, 2.1)
    confere(cena, r)  # profundidade 0,2 mm < encolher: exige visível


def test_folha_a_90_graus_toda_visivel():
    r, cena = roda(rect(1.0, 0.2, 1.04, 1.0), 0.9, 2.1)
    confere(cena, r)


def test_peitoril_saliente_aparece_fora_da_parede_e_some_sob_ela():
    r, cena = roda(rect(0.9, -0.3, 2.1, 0.25), 0.8, 0.9)  # toda abaixo do plano
    confere(cena, r)
    S = polilinhas_em_segs(r)
    assert dist_a_segs(np.array([[1.5, -0.3], [1.5, 0.25], [0.9, -0.1]]), S).max() <= TOL_LIN  # aparece
    assert dist_a_segs(np.array([[0.9, 0.1], [2.1, 0.1]]), S).min() > TOL_LIN  # sob a parede: some


def test_sem_oclusores_tudo_visivel():
    r, cena = roda(rect(0.95, 0.05, 2.05, 0.15), 0.9, 2.1, ocl=())
    confere(cena, r)
    S = polilinhas_em_segs(r)
    assert dist_a_segs(np.array([[0.96, 0.05], [0.96, 0.15], [2.05, 0.1]]), S).max() <= TOL_LIN


def test_toda_abaixo_sem_oclusores():
    r, cena = roda(rect(0, 0, 1, 1), 0.2, 0.9, ocl=())
    confere(cena, r)


def test_toda_acima_lista_vazia():
    r, _ = roda(rect(0, 0, 1, 1), 2.0, 3.0)
    assert r == []
    r, _ = roda(rect(0.95, 0.05, 2.05, 0.15), 2.0, 3.0, ocl=PAREDE)
    assert r == []


def test_encolher_explicito_igual_ao_padrao():
    a, _ = roda(rect(0.995, 0.05, 2.005, 0.15), 0.9, 2.1)
    b, _ = roda(rect(0.995, 0.05, 2.005, 0.15), 0.9, 2.1, encolher=5e-4)
    assert len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))


def test_deterministico():
    a, _ = roda(rect(0.9, -0.3, 2.1, 0.25), 0.8, 2.1)
    b, _ = roda(rect(0.9, -0.3, 2.1, 0.25), 0.8, 2.1)
    assert len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))


# ---------- None = mande ao HLR ----------
def test_face_no_plano_e_none():
    assert roda(rect(0, 0, 1, 1), 1.5, 2.5)[0] is None   # base no plano
    assert roda(rect(0, 0, 1, 1), 0.5, 1.5)[0] is None   # topo no plano


def test_vertice_unico_no_plano_e_none():
    v = np.array([(0, 0, 0.2), (1, 0, 0.2), (0.5, 1, 0.2), (0.5, 0.4, ZC)], float)  # pirâmide, ápice exatamente no plano
    t = np.array([(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)], int)
    assert f()(v, t, ZC, PAREDE) is None


def test_secao_aberta_e_none():
    v, t = prisma(rect(0, 0, 1, 1), 0.9, 2.1)
    assert f()(v, t[:-2], ZC, ()) is None  # sem uma lateral: o corte não fecha


@pytest.mark.parametrize("v,t", [
    (np.zeros((4, 2)), np.array([(0, 1, 2)])),                                   # verts (n,2)
    (np.array([(0, 0, 0), (1, 0, 0), (0, 1, 3.0)]), np.array([(0, 1, 5)])),      # índice fora
    (np.array([(0, 0, 0), (1, np.nan, 0), (0, 1, 3.0)]), np.array([(0, 1, 2)])), # NaN
])
def test_malha_invalida_e_none(v, t):
    assert f()(v, t, ZC, ()) is None
