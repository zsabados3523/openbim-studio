# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j1: `cortar_malha_no_plano(verts, tris, z) -> (verts_abaixo, tris_abaixo, segmentos_secao)`.
Contrato (cartão F0-S06-T19j1): parte z <= `z` com triângulos cortados exatamente (sem deslocar vértices, z de interseção = `z`), sem tampa;
`segmentos_secao` (x0,y0,x1,y1) sem duplicar aresta compartilhada, aneis fechados em sólido fechado; toda abaixo = malha igual e seção vazia;
toda acima = abaixo vazia; triângulo coplanar conta como abaixo e não gera segmento; determinismo; só numpy.
Todo valor esperado vem de conta à mão (área, perímetro, volume), nunca da função. Sólidos construídos com faces para fora (anti-horário)."""
import sys
from pathlib import Path

import numpy as np
import pytest

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))
from obim_geometria.corte_plano import cortar_malha_no_plano  # noqa: E402

TOL = 1e-9


# ---------- sólidos ----------
def caixa(x0, y0, z0, x1, y1, z1):
    v = np.array([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                  (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], float)
    t = np.array([(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
                  (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)], int)
    return v, t


def prisma_regular(n, r, z0, z1):
    """Prisma de n lados (raio r) centrado na origem; tampas em leque a partir do centro."""
    ang = 2 * np.pi * np.arange(n) / n
    base = [(r * np.cos(a), r * np.sin(a)) for a in ang]
    v = [(x, y, z0) for x, y in base] + [(x, y, z1) for x, y in base] + [(0, 0, z0), (0, 0, z1)]
    cb, ct = 2 * n, 2 * n + 1
    t = []
    for i in range(n):
        j = (i + 1) % n
        t += [(cb, j, i), (ct, n + i, n + j), (i, j, n + j), (i, n + j, n + i)]
    return np.array(v, float), np.array(t, int)


def anel_quadrado(ext, inte, z0, z1):
    """Caixa quadrada [0,ext]^2 com furo passante centrado de lado `inte`, altura z0..z1."""
    a = (ext - inte) / 2
    o = [(0, 0), (ext, 0), (ext, ext), (0, ext)]
    n = [(a, a), (a + inte, a), (a + inte, a + inte), (a, a + inte)]
    v = [(x, y, z0) for x, y in o] + [(x, y, z0) for x, y in n] + [(x, y, z1) for x, y in o] + [(x, y, z1) for x, y in n]
    ob, ib, ot, it = 0, 4, 8, 12
    t = []
    for i in range(4):
        j = (i + 1) % 4
        t += [(ot + i, ot + j, it + j), (ot + i, it + j, it + i)]  # topo +z
        t += [(ob + i, ib + i, ib + j), (ob + i, ib + j, ob + j)]  # base -z
        t += [(ob + i, ob + j, ot + j), (ob + i, ot + j, ot + i)]  # parede externa
        t += [(ib + j, ib + i, it + i), (ib + j, it + i, it + j)]  # parede do furo (normal para o furo)
    return np.array(v, float), np.array(t, int)


def piramide():
    """Base 2x2 em z=0, ápice (1,1,2)."""
    v = np.array([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (1, 1, 2)], float)
    t = np.array([(0, 2, 1), (0, 3, 2), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)], int)
    return v, t


def octaedro():
    v = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)], float)
    t = np.array([(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)], int)
    return v, t


# ---------- medidas independentes ----------
def area_proj_soma(v, t):
    """Soma de |área XY| de cada triângulo."""
    if len(t) == 0:
        return 0.0
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.sum(0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))))


def area_3d(v, t):
    if len(t) == 0:
        return 0.0
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.sum(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)))


def volume_com_tampa(v, t, z, area_tampa):
    """Volume pelo teorema da divergência com F=(0,0,z): malha aberta em z mais tampa plana em z (normal +z, área dada)."""
    if len(t) == 0:
        return 0.0
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    axy = 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    zm = (a[:, 2] + b[:, 2] + c[:, 2]) / 3
    return float(np.sum(axy * zm) + z * area_tampa)


def coords_tris(v, t):
    return sorted(tuple(sorted(tuple(np.round(v[i], 9)) for i in tri)) for tri in t)


def chave(p):
    return (round(float(p[0]), 9) + 0.0, round(float(p[1]), 9) + 0.0)


def analisa_aneis(seg):
    """(n_componentes, todos_grau_2, comprimento_total, duplicados)."""
    pai = {}

    def f(x):
        pai.setdefault(x, x)
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    grau, vistos, dup, comp = {}, set(), 0, 0.0
    for x0, y0, x1, y1 in seg:
        p, q = chave((x0, y0)), chave((x1, y1))
        if frozenset((p, q)) in vistos:
            dup += 1
        vistos.add(frozenset((p, q)))
        grau[p] = grau.get(p, 0) + 1
        grau[q] = grau.get(q, 0) + 1
        pai[f(p)] = f(q)
        comp += float(np.hypot(x1 - x0, y1 - y0))
    n = len({f(k) for k in grau})
    return n, all(g == 2 for g in grau.values()), comp, dup


def confere_forma(vb, tb, seg):
    assert vb.ndim == 2 and vb.shape[1] == 3
    assert tb.ndim == 2 and tb.shape[1] == 3
    assert seg.ndim == 2 and seg.shape[1] == 4
    if len(tb):
        assert tb.min() >= 0 and tb.max() < len(vb)


def confere_sem_deslocar(v, vb, z):
    """Todo vértice de saída é original ou está exatamente em z (interseção); nenhum acima de z."""
    assert np.all(vb[:, 2] <= z + TOL)
    orig = {tuple(p) for p in v}
    for p in vb:
        assert tuple(p) in orig or abs(p[2] - z) <= TOL


# ---------- caixa ----------
@pytest.mark.parametrize("z", [0.5, 1.0, 2.5])
def test_caixa_corte_no_meio(z):
    # caixa 3 x 2 x 4: secao 3x2 = 6, perimetro 10, volume abaixo = 6*z
    v, t = caixa(0, 0, 0, 3, 2, 4)
    vb, tb, seg = cortar_malha_no_plano(v, t, z)
    confere_forma(vb, tb, seg)
    confere_sem_deslocar(v, vb, z)
    assert vb[:, 2].max() == pytest.approx(z, abs=TOL)
    assert vb[:, 2].min() == pytest.approx(0.0, abs=TOL)
    n, grau2, comp, dup = analisa_aneis(seg)
    assert (n, grau2, dup) == (1, True, 0)
    assert comp == pytest.approx(10.0, abs=TOL)
    assert volume_com_tampa(vb, tb, z, 6.0) == pytest.approx(6.0 * z, abs=TOL)
    # parte aberta: so a base projeta (as paredes sao verticais); original projeta base + topo
    assert area_proj_soma(vb, tb) == pytest.approx(6.0, abs=TOL)
    assert area_proj_soma(vb, tb) <= area_proj_soma(v, t) + TOL
    assert area_proj_soma(v, t) == pytest.approx(12.0, abs=TOL)
    # area 3D da parte aberta: base 6 + paredes (perimetro 10 x z)
    assert area_3d(vb, tb) == pytest.approx(6.0 + 10.0 * z, abs=TOL)
    # todos os segmentos ficam no contorno do retangulo [0,3]x[0,2]
    x0, y0, x1, y1 = seg.T
    for xs, ys in ((x0, y0), (x1, y1)):
        assert np.all(xs >= -TOL) and np.all(xs <= 3 + TOL) and np.all(ys >= -TOL) and np.all(ys <= 2 + TOL)
        no_contorno = (np.abs(xs) < TOL) | (np.abs(xs - 3) < TOL) | (np.abs(ys) < TOL) | (np.abs(ys - 2) < TOL)
        assert np.all(no_contorno)


def test_caixa_coordenadas_deslocadas_e_negativas():
    # mesma conta fora da origem: caixa [-1,2]x[5,7]x[-3,1], corte z=-1 -> altura abaixo 2, secao 6, perimetro 10
    v, t = caixa(-1, 5, -3, 2, 7, 1)
    vb, tb, seg = cortar_malha_no_plano(v, t, -1.0)
    n, grau2, comp, dup = analisa_aneis(seg)
    assert (n, grau2, dup) == (1, True, 0)
    assert comp == pytest.approx(10.0, abs=TOL)
    assert volume_com_tampa(vb, tb, -1.0, 6.0) == pytest.approx(12.0, abs=TOL)
    assert seg[:, [0, 2]].min() == pytest.approx(-1.0, abs=TOL) and seg[:, [0, 2]].max() == pytest.approx(2.0, abs=TOL)
    assert seg[:, [1, 3]].min() == pytest.approx(5.0, abs=TOL) and seg[:, [1, 3]].max() == pytest.approx(7.0, abs=TOL)


# ---------- prisma regular (cilindro facetado) ----------
def test_cilindro_octogonal():
    # octogono r=1: area = 8 * 1/2 * sin(45 graus) = 2*sqrt(2); perimetro = 8 * 2*sin(22,5 graus) = 16*sin(pi/8)
    area = 2 * np.sqrt(2)
    perim = 16 * np.sin(np.pi / 8)
    v, t = prisma_regular(8, 1.0, 0.0, 3.0)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_forma(vb, tb, seg)
    confere_sem_deslocar(v, vb, 1.0)
    n, grau2, comp, dup = analisa_aneis(seg)
    assert (n, grau2, dup) == (1, True, 0)
    assert comp == pytest.approx(perim, abs=TOL)
    assert volume_com_tampa(vb, tb, 1.0, area) == pytest.approx(area * 1.0, abs=TOL)
    assert area_proj_soma(vb, tb) == pytest.approx(area, abs=TOL)


# ---------- caixa com furo: duas aneis ----------
def test_caixa_com_furo_dois_aneis():
    # 4x4 com furo 2x2, altura 2, corte z=1: secao = 16-4 = 12; perimetros 16 (externo) + 8 (furo) = 24; volume abaixo = 12
    v, t = anel_quadrado(4.0, 2.0, 0.0, 2.0)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_forma(vb, tb, seg)
    confere_sem_deslocar(v, vb, 1.0)
    n, grau2, comp, dup = analisa_aneis(seg)
    assert n == 2 and grau2 and dup == 0
    assert comp == pytest.approx(24.0, abs=TOL)
    assert volume_com_tampa(vb, tb, 1.0, 12.0) == pytest.approx(12.0, abs=TOL)
    assert area_proj_soma(vb, tb) == pytest.approx(12.0, abs=TOL)
    # nenhum segmento dentro da parede maciça: cada ponto esta no quadrado externo ou no quadrado do furo
    for x0, y0, x1, y1 in seg:
        for x, y in ((x0, y0), (x1, y1)):
            externo = min(abs(x), abs(x - 4), abs(y), abs(y - 4)) < TOL
            furo = (1 - TOL <= x <= 3 + TOL and 1 - TOL <= y <= 3 + TOL
                    and min(abs(x - 1), abs(x - 3), abs(y - 1), abs(y - 3)) < TOL)
            assert externo or furo


# ---------- paredes inclinadas ----------
def test_piramide_corte_no_meio():
    # base 2x2, altura 2, corte z=1: secao quadrada de lado 1 (perimetro 4, area 1)
    # volume abaixo = tronco: h/3*(A1+A2+sqrt(A1*A2)) = 1/3*(4+1+2) = 7/3
    # projecao: base 4 + paredes abaixo de z=1 (4 - 1 = 3) = 7; original: 4 + 4 = 8
    v, t = piramide()
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_forma(vb, tb, seg)
    confere_sem_deslocar(v, vb, 1.0)
    n, grau2, comp, dup = analisa_aneis(seg)
    assert (n, grau2, dup) == (1, True, 0)
    assert comp == pytest.approx(4.0, abs=TOL)
    assert volume_com_tampa(vb, tb, 1.0, 1.0) == pytest.approx(7.0 / 3.0, abs=TOL)
    assert area_proj_soma(vb, tb) == pytest.approx(7.0, abs=TOL)
    assert area_proj_soma(v, t) == pytest.approx(8.0, abs=TOL)
    cantos = {(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)}
    pontos = {chave(p) for s in seg for p in ((s[0], s[1]), (s[2], s[3]))}
    assert pontos == cantos


# ---------- plano exatamente em face / vertice ----------
def test_plano_na_face_de_cima_malha_toda_abaixo():
    # z=2 = topo da caixa: tampa coplanar conta como abaixo; malha igual; secao vazia
    v, t = caixa(0, 0, 0, 3, 2, 2)
    vb, tb, seg = cortar_malha_no_plano(v, t, 2.0)
    assert coords_tris(vb, tb) == coords_tris(v, t)
    assert seg.shape == (0, 4)


def test_plano_na_face_de_baixo():
    # z=0 = base: a base (coplanar) fica; paredes e topo estao acima. Area 3D que resta = base 3x2 = 6; nenhum vertice acima de 0
    v, t = caixa(0, 0, 0, 3, 2, 2)
    vb, tb, seg = cortar_malha_no_plano(v, t, 0.0)
    confere_forma(vb, tb, seg)
    assert np.all(vb[:, 2] <= TOL)
    assert area_3d(vb, tb) == pytest.approx(6.0, abs=TOL)
    assert area_proj_soma(vb, tb) == pytest.approx(6.0, abs=TOL)
    assert seg.shape == (0, 4)  # face coplanar nao gera segmento; arestas das paredes nao tem triangulo abaixo estrito


def test_plano_no_vertice_de_cima_nao_gera_secao():
    # octaedro de raio 1; z=1 toca so o apice: tudo esta abaixo (<=), secao vazia (ponto nao e segmento)
    v, t = octaedro()
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert coords_tris(vb, tb) == coords_tris(v, t)
    assert seg.shape == (0, 4)


def test_plano_no_vertice_de_baixo_nao_sobra_area():
    # z=-1 toca so o apice de baixo: nenhuma area abaixo, secao vazia
    v, t = octaedro()
    vb, tb, seg = cortar_malha_no_plano(v, t, -1.0)
    assert area_3d(vb, tb) == pytest.approx(0.0, abs=TOL)
    assert seg.shape == (0, 4)


def test_octaedro_no_equador():
    # z=0 passa pelos 4 vertices do equador. Cada aresta do equador e compartilhada por uma face com vertice estritamente
    # abaixo e outra estritamente acima: 4 segmentos, 1 anel fechado, perimetro 4*sqrt(2), sem duplicata.
    # parte abaixo: 4 faces de baixo, area 3D = 4 * (sqrt(3)/2) (triangulo equilatero de lado sqrt(2))
    v, t = octaedro()
    vb, tb, seg = cortar_malha_no_plano(v, t, 0.0)
    assert area_3d(vb, tb) == pytest.approx(4 * np.sqrt(3) / 2, abs=TOL)
    assert len(seg) == 4
    n, grau2, comp, dup = analisa_aneis(seg)
    assert (n, grau2, dup) == (1, True, 0)
    assert comp == pytest.approx(4 * np.sqrt(2), abs=TOL)


# ---------- toda abaixo / toda acima / vazia / coplanar ----------
def test_malha_toda_abaixo():
    v, t = caixa(0, 0, 0, 3, 2, 2)
    vb, tb, seg = cortar_malha_no_plano(v, t, 10.0)
    assert coords_tris(vb, tb) == coords_tris(v, t)
    assert seg.shape == (0, 4)


def test_malha_toda_acima():
    v, t = caixa(0, 0, 5, 3, 2, 7)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert len(tb) == 0
    assert seg.shape == (0, 4)


def test_malha_vazia():
    v, t = np.zeros((0, 3)), np.zeros((0, 3), int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert len(tb) == 0
    assert vb.shape == (0, 3) and tb.shape == (0, 3) and seg.shape == (0, 4)


def test_triangulo_coplanar_conta_como_abaixo_sem_segmento():
    v = np.array([(0, 0, 1), (2, 0, 1), (0, 2, 1)], float)
    t = np.array([(0, 1, 2)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert area_3d(vb, tb) == pytest.approx(2.0, abs=TOL)
    assert len(tb) == 1
    assert seg.shape == (0, 4)


def test_triangulo_isolado_cruzado_exatamente():
    # triangulo (0,0,0),(2,0,0),(0,0,2)? plano z=1 corta as arestas ao meio: segmento (1,0)-(0,0), comprimento 1
    # parte abaixo = trapezio: area 3D = 2 - 0,5 = 1,5 (triangulo de catetos 2 menos o de catetos 1)
    v = np.array([(0, 0, 0), (2, 0, 0), (0, 0, 2)], float)
    t = np.array([(0, 1, 2)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_sem_deslocar(v, vb, 1.0)
    assert area_3d(vb, tb) == pytest.approx(1.5, abs=TOL)
    assert len(seg) == 1
    p, q = chave(seg[0][:2]), chave(seg[0][2:])
    assert {p, q} == {(1.0, 0.0), (0.0, 0.0)}


# ---------- determinismo e entrada preservada ----------
def test_determinismo_e_entrada_intacta():
    v, t = anel_quadrado(4.0, 2.0, 0.0, 2.0)
    v0, t0 = v.copy(), t.copy()
    r1 = cortar_malha_no_plano(v, t, 1.0)
    r2 = cortar_malha_no_plano(v, t, 1.0)
    for a, b in zip(r1, r2):
        assert np.array_equal(a, b)
    assert np.array_equal(v, v0) and np.array_equal(t, t0)
    # nova copia da entrada: mesma saida
    r3 = cortar_malha_no_plano(v.copy(), t.copy(), 1.0)
    for a, b in zip(r1, r3):
        assert np.array_equal(a, b)


# ---------- reforco (revisao Argon) ----------
def normais_unitarias(v, t):
    if len(t) == 0:
        return np.zeros((0, 3))
    n = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    m = np.linalg.norm(n, axis=1)
    return n[m > 1e-12] / m[m > 1e-12, None]


def confere_orientacao(v, t, vb, tb):
    """Cada triangulo (nao degenerado) da saida tem a normal 3D da de algum triangulo original: produto escalar > 0 (na verdade ~1)."""
    orig = normais_unitarias(v, t)
    for n in normais_unitarias(vb, tb):
        assert np.max(orig @ n) > 1 - 1e-9


def tri_unico(a, b, c, rot):
    v = np.array([a, b, c], float)
    return v, np.roll(np.array([0, 1, 2]), -rot)[None, :]


@pytest.mark.parametrize("rot", [0, 1, 2])
def test_um_vertice_no_plano_dois_em_lados_opostos(rot):
    # a=(0,0,1) no plano, b=(2,0,0) abaixo, c=(0,2,2) acima; z=1. Plano corta bc em (1,1,1): segmento (0,0)-(1,1).
    # parte abaixo = triangulo a,b,(1,1,1): cross((2,0,-1),(1,1,0)) = (1,-1,2), area = sqrt(6)/2
    v, t = tri_unico((0, 0, 1), (2, 0, 0), (0, 2, 2), rot)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_forma(vb, tb, seg)
    assert area_3d(vb, tb) == pytest.approx(np.sqrt(6) / 2, abs=TOL)
    assert len(seg) == 1
    assert {chave(seg[0][:2]), chave(seg[0][2:])} == {(0.0, 0.0), (1.0, 1.0)}
    confere_orientacao(v, t, vb, tb)


@pytest.mark.parametrize("rot", [0, 1, 2])
def test_um_vertice_abaixo_dois_acima(rot):
    # a=(0,0,0) abaixo; b=(2,0,2), c=(0,2,2) acima; z=1: cortes em (1,0,1) e (0,1,1). Abaixo = 1/4 do original (area 2*sqrt(3)) = sqrt(3)/2
    v, t = tri_unico((0, 0, 0), (2, 0, 2), (0, 2, 2), rot)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_forma(vb, tb, seg)
    assert area_3d(vb, tb) == pytest.approx(np.sqrt(3) / 2, abs=TOL)
    assert len(seg) == 1
    assert {chave(seg[0][:2]), chave(seg[0][2:])} == {(1.0, 0.0), (0.0, 1.0)}
    assert np.hypot(*(seg[0][:2] - seg[0][2:])) == pytest.approx(np.sqrt(2), abs=TOL)
    confere_orientacao(v, t, vb, tb)


@pytest.mark.parametrize("rot", [0, 1, 2])
def test_dois_vertices_abaixo_um_acima(rot):
    # a=(0,0,0), b=(2,0,0) abaixo; c=(0,2,2) acima; z=1: cortes em (0,1,1) e (1,1,1). Original: area 2*sqrt(2); topo cortado = 1/4 => abaixo = 3*sqrt(2)/2
    v, t = tri_unico((0, 0, 0), (2, 0, 0), (0, 2, 2), rot)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    confere_forma(vb, tb, seg)
    assert area_3d(vb, tb) == pytest.approx(3 * np.sqrt(2) / 2, abs=TOL)
    assert len(seg) == 1
    assert {chave(seg[0][:2]), chave(seg[0][2:])} == {(0.0, 1.0), (1.0, 1.0)}
    confere_orientacao(v, t, vb, tb)


@pytest.mark.parametrize("z", [0.5, 1.0, 3.5])
def test_orientacao_preservada_em_solidos(z):
    for v, t in (caixa(0, 0, 0, 3, 2, 4), anel_quadrado(4.0, 2.0, 0.0, 4.0), piramide(), prisma_regular(8, 1.0, 0.0, 4.0)):
        vb, tb, _ = cortar_malha_no_plano(v, t, z)
        confere_orientacao(v, t, vb, tb)


def test_dedupe_aresta_compartilhada_parede_de_dois_triangulos():
    # parede vertical 2x2 em y=0 com diagonal (0,2) compartilhada; z=1 corta a diagonal, uma lateral de cada triangulo: 3 vertices novos
    # (diagonal em (1,0,1), (2,0,1) e (0,0,1)), nao 4; 2 segmentos; verts_abaixo = 2 originais + 3 novos
    v = np.array([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)], float)
    t = np.array([(0, 1, 2), (0, 2, 3)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert int(np.sum(np.abs(vb[:, 2] - 1.0) <= TOL)) == 3
    assert len(vb) == 5
    assert len(seg) == 2
    assert analisa_aneis(seg)[3] == 0
    assert area_3d(vb, tb) == pytest.approx(2.0, abs=TOL)  # metade de baixo da parede 2x2 = 2x1
    confere_orientacao(v, t, vb, tb)


def test_dedupe_caixa_oito_vertices_novos_oito_segmentos():
    # caixa fechada: 4 arestas verticais + 4 diagonais das paredes cruzam o plano -> 8 vertices novos e 8 segmentos
    v, t = caixa(0, 0, 0, 3, 2, 4)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert int(np.sum(np.abs(vb[:, 2] - 1.0) <= TOL)) == 8
    assert len(seg) == 8


def test_quilha_aresta_so_por_cima_secao_vazia():
    # prisma triangular fechado em z de 0 a 2 tocando z=0 so por uma aresta: nada abaixo, secao vazia (aresta no plano sem triangulo abaixo estrito)
    v = np.array([(0, 0, 0), (0, 2, 0), (-1, 0, 2), (1, 0, 2), (-1, 2, 2), (1, 2, 2)], float)
    t = np.array([(0, 3, 2), (1, 4, 5), (2, 3, 5), (2, 5, 4), (0, 1, 5), (0, 5, 3), (1, 0, 2), (1, 2, 4)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 0.0)
    assert area_3d(vb, tb) == pytest.approx(0.0, abs=TOL)
    assert seg.shape == (0, 4)


def test_quilha_aresta_so_por_baixo_secao_vazia():
    # o mesmo prisma de ponta cabeca (aresta em z=0, corpo abaixo): z=0 so toca por baixo: tudo abaixo, secao vazia
    v = np.array([(0, 0, 0), (0, 2, 0), (-1, 0, -2), (1, 0, -2), (-1, 2, -2), (1, 2, -2)], float)
    t = np.array([(0, 2, 3), (1, 5, 4), (2, 5, 3), (2, 4, 5), (0, 5, 1), (0, 3, 5), (1, 2, 0), (1, 4, 2)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 0.0)
    assert coords_tris(vb, tb) == coords_tris(v, t)
    assert seg.shape == (0, 4)


def test_ruido_de_acumulo_em_1e3_nao_quebra_topo_coplanar():
    # topo somado de 0,01 em 0,01 (150 passos) em ~1e3 m erra ~1e-12 do alvo 1001,5; um vertice do topo com ruido de sinal oposto
    z_topo = 1000.0
    for _ in range(150):
        z_topo += 0.01
    zc = 1001.5
    v, t = caixa(1000.0, 2000.0, 1000.0, 1003.0, 2002.0, z_topo)
    v[6, 2] = zc + (zc - z_topo)
    vb, tb, seg = cortar_malha_no_plano(v, t, zc)
    assert seg.shape == (0, 4)
    assert len(tb) == 12  # nenhum vertice estritamente acima: tudo abaixo


def test_ruido_de_alguns_ulp_em_1e3():
    u = np.spacing(1000.0)
    v, t = caixa(1000.0, 2000.0, 999.0, 1003.0, 2002.0, 1000.0)
    v[4:, 2] = 1000.0 + u * np.array([-2, 0, 1, 3])
    vb, tb, seg = cortar_malha_no_plano(v, t, 1000.0)
    assert seg.shape == (0, 4)
    assert len(tb) == 12


def test_solido_so_tocando_por_cima_ou_por_baixo_secao_vazia():
    # caixa [2,4] tocando z=2 pela base (por cima do plano) e caixa [0,2] tocando z=2 pelo topo (por baixo do plano)
    for z0, z1 in ((2.0, 4.0), (0.0, 2.0)):
        v, t = caixa(0, 0, z0, 3, 2, z1)
        _, _, seg = cortar_malha_no_plano(v, t, 2.0)
        assert seg.shape == (0, 4)


# ---------- mutantes (revisao Opus) ----------
def junta(*malhas):
    vs, ts, off = [], [], 0
    for v, t in malhas:
        vs.append(v)
        ts.append(t + off)
        off += len(v)
    return np.vstack(vs), np.vstack(ts)


@pytest.mark.parametrize("primeira", [(0, 0, 0, 1, 1, 2), (0, 0, 2, 1, 1, 4)])
def test_duas_caixas_so_a_que_cruza_gera_secao(primeira):
    # 1a caixa so toca z=2 (pelo topo, ou pela base): sem segmento. 2a [5,6]^2 x [0,4] cruza: secao 1x1,
    # perimetro 4, 1 anel; 4 arestas verticais + 4 diagonais das paredes = 8 segmentos
    v, t = junta(caixa(*primeira), caixa(5, 5, 0, 6, 6, 4))
    vb, tb, seg = cortar_malha_no_plano(v, t, 2.0)
    confere_forma(vb, tb, seg)
    assert len(seg) == 8
    n, grau2, comp, dup = analisa_aneis(seg)
    assert (n, grau2, dup) == (1, True, 0)
    assert comp == pytest.approx(4.0, abs=TOL)
    assert seg.min() >= 5.0 - TOL and seg.max() <= 6.0 + TOL


def test_triangulo_abaixo_no_plano_acima_sem_rotacao():
    # a=(2,0,0) abaixo, b=(0,0,1) no plano, c=(0,2,2) acima; z=1: plano corta ac em (1,1,1); segmento (0,0)-(1,1)
    # abaixo = triangulo a,b,(1,1,1): cross((-2,0,1),(-1,1,1)) = (-1,1,-2), area = sqrt(6)/2; normal original (-2,2,-4)
    v = np.array([(2, 0, 0), (0, 0, 1), (0, 2, 2)], float)
    t = np.array([(0, 1, 2)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert area_3d(vb, tb) == pytest.approx(np.sqrt(6) / 2, abs=TOL)
    assert len(seg) == 1
    assert {chave(seg[0][:2]), chave(seg[0][2:])} == {(0.0, 0.0), (1.0, 1.0)}
    confere_orientacao(v, t, vb, tb)
    assert np.dot(normais_unitarias(vb, tb)[0], normais_unitarias(v, t)[0]) > 0


def test_z_novo_exatamente_igual_ao_plano():
    # aresta de z=-1,88 a z=4,49 cortada em 0,82: vertices novos com z == 0,82 exato (sem aproximacao)
    v = np.array([(0, 0, -1.88), (1, 0, 4.49), (0, 1, 4.49)], float)
    t = np.array([(0, 1, 2)], int)
    vb, tb, seg = cortar_malha_no_plano(v, t, 0.82)
    zs = vb[:, 2]
    assert sorted(set(zs.tolist())) == [-1.88, 0.82]
    assert int(np.sum(zs == 0.82)) == 2


def test_topo_1e_10_acima_do_plano_em_z_1_nao_e_engolido():
    # caixa unitaria de altura 1+1e-10, z=1: topo estritamente acima; secao 1x1 nao vazia: 8 segmentos, perimetro 4
    v, t = caixa(0, 0, 0, 1, 1, 1 + 1e-10)
    vb, tb, seg = cortar_malha_no_plano(v, t, 1.0)
    assert len(seg) == 8
    # pontos novos ficam a ~1e-10 dos cantos: chaves de 9 casas nao fecham o anel, entao mede-se so o comprimento (tolerancia 1e-8)
    assert float(np.sum(np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]))) == pytest.approx(4.0, abs=1e-8)
