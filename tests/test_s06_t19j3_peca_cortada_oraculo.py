# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j3: `linhas_peca_cortada(verts, tris, z, aneis_oclusores=(), *, encolher=5e-4) -> list[ndarray (K,2)] | None`.
Contrato (cartão F0-S06-T19j3): None = "mande ao HLR" (vértice/face no plano, |dz| <= eps ~1e-9; seção aberta; malha ou z inválidos,
tris não inteiros); toda acima = []; caso geral = `linhas_visiveis(parte abaixo)` (já traz a borda da seção, nada duplicado),
recortada fora da PRÓPRIA seção (ponto mais alto) e fora de `aneis_oclusores` = lista de GRUPOS (um por parede, união).
Oráculo INDEPENDENTE por raios: cena = sólidos convexos (base em z0, topo em z1, troncos ou prismas) montados aqui; arestas
relevantes à mão (base, topo ou borda da seção em zc, laterais inclinadas); amostra a cada ~5 mm; raio +z contra faces
horizontais da parte abaixo, contra a seção própria (disco em zc, só para pontos abaixo dela) e contra os anéis das paredes
(união dos grupos, par-ímpar dentro de cada grupo). Visível => coberta (>= 99,9% a 1 mm); oculta => nenhuma linha a menos de
1 mm. Faixas de indiferença: borda de anel (visível se profundidade <= 0,3 mm, oculta se >= 2 mm) e borda de face (0,1 mm).
Nunca compara com o HLR e não exige contorno explícito da seção."""
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


def S(base, z0, z1, topo=None):
    """Sólido convexo: polígono da base em z0, do topo em z1 (prisma se topo omitido)."""
    return np.array(base, float), z0, np.array(base if topo is None else topo, float), z1


def malha(solidos):
    """Malha (soldada por sólido, faces para fora) de vários sólidos."""
    v, t = [], []
    for b, z0, tp, z1 in solidos:
        n, o = len(b), sum(len(x) for x in v)
        v += [np.c_[b, np.full(n, z0)], np.c_[tp, np.full(n, z1)]]
        tt = [(0, i + 1, i) for i in range(1, n - 1)] + [(n, n + i, n + i + 1) for i in range(1, n - 1)]
        for i in range(n):
            j = (i + 1) % n
            tt += [(i, j, n + j), (i, n + j, n + i)]
        t.append(np.array(tt, int) + o)
    return np.vstack(v), np.vstack(t)


# paredes (seção em zc), uma lista por parede = grupo; vão em x 1..2
PAREDE = [[np.array(rect(0, 0, 1, 0.2), float)], [np.array(rect(2, 0, 4, 0.2), float)]]
ZC = 1.5


# ---------- oráculo por raios ----------
def segs_de(pts):
    p = np.asarray(pts, float)
    return np.c_[p, np.roll(p, -1, axis=0)]


def dist_a_segs(P, S_):
    """Distância mínima de cada ponto de P (n,2) ao conjunto de segmentos S_ (m,4)."""
    if len(S_) == 0:
        return np.full(len(P), np.inf)
    a, d = S_[:, :2], S_[:, 2:] - S_[:, :2]
    l2 = np.maximum((d ** 2).sum(1), 1e-30)
    w = P[:, None, :] - a[None]
    u = np.clip((w * d[None]).sum(2) / l2, 0, 1)
    return np.sqrt(((w - u[..., None] * d[None]) ** 2).sum(2)).min(1)


def polilinhas_em_segs(linhas):
    return np.vstack([np.c_[l[:-1], l[1:]] for l in linhas if len(l) > 1] or [np.zeros((0, 4))])


def dist_convexo(P, poly):
    """Distância assinada (positiva dentro) ao polígono convexo anti-horário."""
    Sg = segs_de(poly)
    e = Sg[:, 2:] - Sg[:, :2]
    w = P[:, None, :] - Sg[None, :, :2]
    return ((e[None, :, 0] * w[..., 1] - e[None, :, 1] * w[..., 0]) / np.hypot(e[:, 0], e[:, 1])[None]).min(1)


def dentro_par_impar(P, aneis):
    n = np.zeros(len(P), int)
    for r in aneis:
        for x0, y0, x1, y1 in segs_de(r):
            c = (y0 > P[:, 1]) != (y1 > P[:, 1])
            xi = x0 + (P[:, 1] - y0) * (x1 - x0) / np.where(y1 == y0, 1, y1 - y0)
            n += c & (P[:, 0] < xi)
    return n % 2 == 1


def faixa(P, grupos):
    """União dos grupos (par-ímpar em cada um): (oculta exigida, visível aceitável); entre as duas, indiferente."""
    oculta, ok = np.zeros(len(P), bool), np.ones(len(P), bool)
    for g in grupos:
        dentro = dentro_par_impar(P, g)
        prof = dist_a_segs(P, np.vstack([segs_de(r) for r in g]))
        oculta |= dentro & (prof >= 2e-3)
        ok &= (~dentro) | (prof <= 3e-4)
    return oculta, ok


def derivados(solidos, zc):
    """(arestas 3D relevantes (m,6), faces horizontais [(poly,z)], seções próprias [[anel]])."""
    ar, blocos, secoes = [], [], []
    for b, z0, tp, z1 in solidos:
        if z0 >= zc:
            continue
        if z1 < zc:
            alto, zt = tp, z1
        else:
            alto, zt = b + (zc - z0) / (z1 - z0) * (tp - b), zc
            secoes.append([alto])
        blocos += [(b, z0)] + ([(tp, z1)] if z1 < zc else [])
        for i in range(len(b)):
            j = (i + 1) % len(b)
            ar += [(*b[i], z0, *b[j], z0), (*alto[i], zt, *alto[j], zt)]
            if np.hypot(*(alto[i] - b[i])) > 1e-6:
                ar.append((*b[i], z0, *alto[i], zt))
    return np.array(ar, float), blocos, secoes


def amostras(ar):
    pts = []
    for a in ar:
        n = max(1, int(np.ceil(np.linalg.norm(a[3:] - a[:3]) / PASSO)))
        u = ((np.arange(n) + 0.5) / n)[:, None]
        pts.append(a[:3] + u * (a[3:] - a[:3]))
    return np.vstack(pts)


def status(P, blocos, secoes, ocl, zc):
    """+1 visível exigido, -1 oculta exigida, 0 indiferente (por amostra)."""
    st = np.ones(len(P), int)
    for zb, poly in [(z, p) for p, z in blocos]:  # face horizontal acima do ponto
        d, acima = dist_convexo(P[:, :2], poly), zb > P[:, 2] + 1e-6
        st[acima & (d >= 1e-4)] = -1
        st[acima & (np.abs(d) < 1e-4) & (st > 0)] = 0
    for grupos, abaixo in ((secoes, P[:, 2] < zc - 1e-6), (ocl, np.ones(len(P), bool))):  # seção própria e paredes
        if len(grupos):
            oc, ok = faixa(P[:, :2], grupos)
            oc &= abaixo
            st[oc] = -1
            st[abaixo & ~oc & ~ok & (st > 0)] = 0
    return st


def confere(solidos, zc, ocl, linhas):
    assert isinstance(linhas, list) and all(l.ndim == 2 and l.shape[1] == 2 and len(l) >= 2 for l in linhas)
    ar, blocos, secoes = derivados(solidos, zc)
    P = amostras(ar)
    st = status(P, blocos, secoes, ocl, zc)
    Sg = polilinhas_em_segs(linhas)
    vis, ocu = P[st > 0, :2], P[st < 0, :2]
    if len(vis):
        cob = (dist_a_segs(vis, Sg) <= TOL_LIN).mean()
        assert cob >= 0.999, f"cobertura das visíveis {cob:.4f}"
    if len(ocu):  # oculta que nenhuma visível encobre perto: não pode haver linha a menos de 1 mm
        longe = ocu if not len(vis) else ocu[dist_a_segs(ocu, np.c_[vis, vis]) > 2 * TOL_LIN]
        assert (dist_a_segs(longe, Sg) > TOL_LIN).all(), "há linha emitida sobre trecho oculto"
    todos = np.vstack(linhas) if linhas else np.zeros((0, 2))  # nada fora das arestas relevantes
    assert (dist_a_segs(todos, ar[:, [0, 1, 3, 4]]) <= TOL_LIN).all(), "linha fora das arestas da peça"


def sem_duplicata(linhas):
    """Nenhum par de segmentos emitidos se sobrepõe colinearmente em mais de 1 mm."""
    Sg = polilinhas_em_segs(linhas)
    for i in range(len(Sg)):
        a, d = Sg[i, :2], Sg[i, 2:] - Sg[i, :2]
        L = np.hypot(*d)
        if L < 1e-9:
            continue
        u = d / L
        for j in range(i + 1, len(Sg)):
            q = Sg[j]
            h = [abs((q[k:k + 2] - a) @ np.array([-u[1], u[0]])) for k in (0, 2)]
            if max(h) > 1e-6:
                continue
            t = sorted([(q[0:2] - a) @ u, (q[2:4] - a) @ u])
            assert min(t[1], L) - max(t[0], 0.0) <= TOL_LIN, f"linhas repetidas {i} e {j}"


def roda(solidos, ocl=PAREDE, zc=ZC, **kw):
    v, t = malha(solidos)
    v0, t0 = v.copy(), t.copy()
    r = f()(v, t, zc, ocl, **kw)
    np.testing.assert_array_equal(v, v0)
    np.testing.assert_array_equal(t, t0)
    return r


def ok(solidos, ocl=PAREDE, zc=ZC):
    r = roda(solidos, ocl, zc)
    assert r is not None
    confere(solidos, zc, ocl, r)
    return r


# ---------- casos a mão ----------
def test_janela_embutida_5cm_zero_linhas_dentro_da_parede():
    r = ok([S(rect(0.95, 0.05, 2.05, 0.15), 0.9, 2.1)])
    for l in r:  # nada dentro da seção da parede (x < 0.998 ou x > 2.002)
        assert not ((l[:, 0] < 0.998) | (l[:, 0] > 2.002)).any()


def test_embutido_5mm():
    ok([S(rect(0.995, 0.05, 2.005, 0.15), 0.9, 2.1)])


def test_batente_faceando_a_parede_colinear_nao_some():
    r = ok([S(rect(1, 0, 2, 0.2), 0.9, 2.1)])  # x=1 e x=2 colineares com as bordas dos anéis
    Sg = polilinhas_em_segs(r)
    for x in (1.0, 2.0):  # as duas arestas verticais do batente aparecem inteiras
        P = np.c_[np.full(39, x), np.linspace(0.005, 0.195, 39)]
        assert (dist_a_segs(P, Sg) <= TOL_LIN).all()


def test_batente_a_0_2mm_dentro_da_parede_fica():
    ok([S(rect(1 - 2e-4, 0, 2 + 2e-4, 0.2), 0.9, 2.1)])  # profundidade 0,2 mm < encolher: exige visível


def test_folha_a_90_graus_toda_visivel():
    ok([S(rect(1.0, 0.2, 1.04, 1.0), 0.9, 2.1)])


def test_peitoril_saliente_aparece_fora_da_parede_e_some_sob_ela():
    r = ok([S(rect(0.9, -0.3, 2.1, 0.25), 0.8, 0.9)])  # toda abaixo do plano
    Sg = polilinhas_em_segs(r)
    assert dist_a_segs(np.array([[1.5, -0.3], [1.5, 0.25], [0.9, -0.1]]), Sg).max() <= TOL_LIN  # aparece
    assert dist_a_segs(np.array([[0.9, 0.1], [2.1, 0.1]]), Sg).min() > TOL_LIN  # sob a parede: some


def test_tronco_de_piramide_base_sai_da_secao_e_aparece():
    # base 2x2 em z=0, topo 1x1 em z=2, corte z=1: seção 1,5x1,5; a base (e as arestas inclinadas) fica fora dela
    r = ok([S(rect(-1, -1, 1, 1), 0, 2, rect(-.5, -.5, .5, .5))], ocl=(), zc=1.0)
    Sg = polilinhas_em_segs(r)
    P = np.array([[1, 0], [-1, 0.5], [0.2, -1], [0.9, 0.9], [0.8, 0.8]], float)  # base e lateral inclinada
    assert dist_a_segs(P, Sg).max() <= TOL_LIN


def test_T_invertido_secao_propria_oculta_a_haste_estreita():
    sol = [S(rect(0, 0, 1, 0.4), 1.0, 2.0), S(rect(0.3, 0.1, 0.7, 0.3), 0.5, 1.0)]  # larga em cima (cortada), estreita embaixo
    r = ok(sol, ocl=())
    Sg = polilinhas_em_segs(r)
    for x in (0.3, 0.7):
        assert (dist_a_segs(np.c_[np.full(9, x), np.linspace(0.12, 0.28, 9)], Sg) > TOL_LIN).all()


def test_soleira_mais_estreita_que_o_batente():
    r = ok([S(rect(1, 0, 2, 0.2), 0.9, 2.1), S(rect(1.05, 0.05, 1.95, 0.15), 0.4, 0.9)])
    Sg = polilinhas_em_segs(r)
    for x in (1.05, 1.95):
        assert (dist_a_segs(np.c_[np.full(9, x), np.linspace(0.07, 0.13, 9)], Sg) > TOL_LIN).all()


def test_sem_duplicata_no_tronco_cortado():
    # tronco (base != borda da seção): nenhuma linha repete outra. (Prisma vertical não serve: base e borda da seção coincidem na planta.)
    sem_duplicata(ok([S(rect(-1, -1, 1, 1), 0, 2, rect(-.5, -.5, .5, .5))], ocl=(), zc=1.0))


def test_paredes_sobrepostas_em_grupos_nao_deixam_linha_dentro():
    ocl = [[np.array(rect(0, 0, 2, 0.2), float)], [np.array(rect(1.9, 0, 2.1, 1.0), float)]]  # união; sobreposição x 1,9..2
    r = ok([S(rect(1.92, 0.05, 2.08, 0.15), 0.9, 2.1)], ocl=ocl)
    assert sum(np.hypot(*(l[1:] - l[:-1]).T).sum() for l in r) < TOL_LIN


def test_sem_oclusores_tudo_visivel():
    r = ok([S(rect(0.95, 0.05, 2.05, 0.15), 0.9, 2.1)], ocl=())
    Sg = polilinhas_em_segs(r)
    assert dist_a_segs(np.array([[0.96, 0.05], [0.96, 0.15], [2.05, 0.1]]), Sg).max() <= TOL_LIN


def test_toda_abaixo_sem_oclusores():
    ok([S(rect(0, 0, 1, 1), 0.2, 0.9)], ocl=())


def test_toda_acima_lista_vazia():
    assert roda([S(rect(0, 0, 1, 1), 2.0, 3.0)]) == []
    assert roda([S(rect(0.95, 0.05, 2.05, 0.15), 2.0, 3.0)], ocl=PAREDE) == []


def test_vertice_a_0_1mm_do_plano_nao_e_none():
    ok([S(rect(0, 0, 1, 1), 0.9, ZC + 1e-4)], ocl=())  # topo 0,1 mm acima: corta
    ok([S(rect(0, 0, 1, 1), 0.9, ZC - 1e-4)], ocl=())  # topo 0,1 mm abaixo: toda abaixo


def test_encolher_explicito_igual_ao_padrao():
    sol = [S(rect(0.995, 0.05, 2.005, 0.15), 0.9, 2.1)]
    a, b = roda(sol), roda(sol, encolher=5e-4)
    assert len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))


def test_deterministico():
    sol = [S(rect(0.9, -0.3, 2.1, 0.25), 0.8, 2.1)]
    a, b = roda(sol), roda(sol)
    assert len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))


# ---------- None = mande ao HLR ----------
def test_face_no_plano_e_none():
    assert roda([S(rect(0, 0, 1, 1), 1.5, 2.5)]) is None   # base no plano
    assert roda([S(rect(0, 0, 1, 1), 0.5, 1.5)]) is None   # topo no plano


def test_vertice_unico_no_plano_e_none():
    v = np.array([(0, 0, 0.2), (1, 0, 0.2), (0.5, 1, 0.2), (0.5, 0.4, ZC)], float)  # pirâmide, ápice exatamente no plano
    t = np.array([(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)], int)
    assert f()(v, t, ZC, PAREDE) is None


def test_secao_aberta_e_none():
    v, t = malha([S(rect(0, 0, 1, 1), 0.9, 2.1)])
    assert f()(v, t[:-2], ZC, ()) is None  # sem uma lateral: o corte não fecha


@pytest.mark.parametrize("v,t,z", [
    (np.zeros((4, 2)), np.array([(0, 1, 2)]), ZC),                                       # verts (n,2)
    (np.array([(0, 0, 0), (1, 0, 0), (0, 1, 3.0)]), np.array([(0, 1, 5)]), ZC),          # índice fora
    (np.array([(0, 0, 0), (1, np.nan, 0), (0, 1, 3.0)]), np.array([(0, 1, 2)]), ZC),     # NaN
    (np.array([(0, 0, 0), (1, 0, 0), (0, 1, 3.0)]), np.array([(0, 1, 2)]), float("nan")),
    (np.array([(0, 0, 0), (1, 0, 0), (0, 1, 3.0)]), np.array([(0, 1, 2)]), float("inf")),
])
def test_malha_ou_z_invalidos_sao_none(v, t, z):
    assert f()(v, t, z, ()) is None


def test_tris_float_e_none():
    v, t = malha([S(rect(0, 0, 1, 1), 0.9, 2.1)])  # malha válida, só o dtype dos índices muda
    assert f()(v, t.astype(float), ZC, ()) is None
    assert f()(v, t, ZC, ()) is not None
