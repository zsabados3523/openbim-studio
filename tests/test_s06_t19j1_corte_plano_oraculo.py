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
    # z=0 passa pelos 4 vertices do equador: secao = quadrado de vertices (+-1,0),(0,+-1): perimetro 4*sqrt(2), 1 anel
    # (cada face tem uma aresta no plano; a aresta e compartilhada por duas faces e aparece uma vez)
    # parte abaixo: 4 faces de baixo, area 3D = 4 * (sqrt(3)/2) (triangulo equilatero de lado sqrt(2))
    v, t = octaedro()
    vb, tb, seg = cortar_malha_no_plano(v, t, 0.0)
    assert area_3d(vb, tb) == pytest.approx(4 * np.sqrt(3) / 2, abs=TOL)
    # secao nao gera duplicata; se emitir as arestas do equador, formam um unico anel fechado
    if len(seg):
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
