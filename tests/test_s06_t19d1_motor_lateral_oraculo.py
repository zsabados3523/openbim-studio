# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19d1: motor de visibilidade para vistas laterais (corte) em funções puras (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19d1-motor-lateral.md. Não editar nesta tarefa.
CONTRATO (`obim_geometria.visibilidade`, sem IFC, sem Qt):
1. `quadro` = `types.SimpleNamespace(origem=(3,), u=(3,), v=(3,), w=(3,))`, arrays numpy, eixos unitários ortonormais do MUNDO, `w = u x v` (destro). Mesma convenção do `_corte` do desenho: `m = get_local_placement(vista.ObjectPlacement)`,
   `origem = m[:3, 3]`, `u, v, w = m[:3, 0], m[:3, 1], m[:3, 2]`. Coordenada de um ponto P no quadro: `(u, v, w) = ((P - origem) . u, (P - origem) . v, (P - origem) . w)`. A câmera olha para -w: o plano de corte é w = 0,
   o desenhado fica em `-profundidade <= w <= 0`; w > 0 está atrás da câmera (descartado) e w < -profundidade além do alcance (descartado).
2. `linhas_visiveis_vista(pecas, quadro, *, profundidade) -> list[list[ndarray(K, 2)]]`: `pecas = [(verts (N,3) mundo, tris (M,3) int), ...]`; uma lista de polilinhas (u, v) por peça (mesmo tamanho da entrada), com oclusão mútua (como
   `linhas_visiveis_multi`). A malha é recortada na região `-profundidade <= w <= 0` (triângulos que cruzam o plano são cortados em w = 0). `profundidade` inválida (negativa, nan, não numérica) -> ValueError.
3. `secao_plana(verts, tris, quadro) -> list[shapely.geometry.Polygon]`: interseção da malha com w = 0, em (u, v) (as tampas do corte). Malha vazia, degenerada ou do lado errado -> [].
4. Malha vazia ou degenerada nunca levanta. Entrada não é alterada.
REFERÊNCIA: o HLR do IfcOpenShell (`desenho.processar`, vista CORTE): grupo `projection` = linhas, grupos com `ifc:guid` fora da projeção = regiões do corte. SVG: u = x - largura/2, v = altura/2 - y."""
from __future__ import annotations

import copy
import pathlib
from functools import reduce
from types import SimpleNamespace

import numpy as np
import pytest
import s06_t07_aux as X
import s06_t18a_aux as Z
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from test_s06_t19b1_visibilidade_oraculo import TOL, _amostra, _caixa, _cobertura, _dist, _junta, _segs
from test_s06_t19b2_visibilidade_hlr_oraculo import _coplanares


def _V():
    import importlib

    return importlib.import_module("obim_geometria.visibilidade")


# ---------------------------------------------------------------- quadros e malhas no quadro
def _unit(a):
    a = np.asarray(a, float)
    return a / np.linalg.norm(a)


def _quadro(origem=(0.0, 0.0, 0.0), u=(1.0, 0.0, 0.0), v=(0.0, 0.0, 1.0)):
    u, v = _unit(u), _unit(v)
    return SimpleNamespace(origem=np.array(origem, float), u=u, v=v, w=np.cross(u, v))


AXIAL = _quadro()  # u = X, v = Z, w = -Y: a câmera olha para +Y (a vista CORTE com Axis (0,-1,0) e RefDirection (1,0,0))


def _mundo(Q, m):
    """Malha dada em (u, v, w) do quadro `Q` -> malha do mundo (a transformação é destra: o sentido dos triângulos se mantém)."""
    p, t = m
    return Q.origem + p[:, 0:1] * Q.u + p[:, 1:2] * Q.v + p[:, 2:3] * Q.w, t


def _no_quadro(Q, m):
    p, t = m
    d = p - Q.origem
    return np.stack([d @ Q.u, d @ Q.v, d @ Q.w], axis=1), t


def _comp(pls):
    return float(sum(np.hypot(*np.diff(p, axis=0).T).sum() for p in pls))


def _retangulo(u0, v0, u1, v1):
    return np.array([[(u0, v0), (u1, v0)], [(u1, v0), (u1, v1)], [(u1, v1), (u0, v1)], [(u0, v1), (u0, v0)]], float)


def _igual(got, esp, tol=1e-6):
    """`got` (polilinhas) e `esp` (segmentos (n,2,2)) cobrem o mesmo traço, nos dois sentidos, (traço repetido sobre o mesmo segmento não conta)."""
    s = _segs(got)
    assert len(s), "sem linha nenhuma"
    assert _cobertura(s, esp, tol) >= 1 - 1e-9, "linha sobrando"
    assert _cobertura(esp, s, tol) >= 1 - 1e-9, "linha faltando"


def _orienta(p, t):
    """Vira para fora os triângulos de um sólido convexo (teste do centróide)."""
    c = p.mean(axis=0)
    n = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    dentro = ((p[t[:, 0]] - c) * n).sum(axis=1) < 0
    t = t.copy()
    t[dentro] = t[dentro][:, ::-1]
    return p, t


def _cunha(u0, u1, vw):
    """Prisma de seção triangular `vw` (3 pontos (v, w)) extrudado em u de u0 a u1, em coordenadas do quadro."""
    p = np.array([(u, v, w) for u in (u0, u1) for v, w in vw], float)
    t = np.array([[0, 1, 2], [3, 5, 4], [0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4], [2, 0, 3], [2, 3, 5]])
    return _orienta(p, t)


def _cubo_girado(centro, graus):
    """Cubo de lado 1 girado `graus` em torno do eixo v, em coordenadas do quadro (o plano w = 0 o corta de viés)."""
    p, t = _caixa(-0.5, -0.5, -0.5, 0.5, 0.5, 0.5)
    a = np.radians(graus)
    R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return p @ R.T + np.asarray(centro, float), t


def _rot(graus_z, graus_u):
    z, x = np.radians(graus_z), np.radians(graus_u)
    Rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    return Rz @ Rx


# ---------------------------------------------------------------- casos sintéticos (a) a (h)
def test_a_cubo_inteiro_atras_do_plano_sem_tampa():
    V = _V()
    m = _caixa(1, 0, -3, 3, 2, -1)  # no quadro: u 1..3, v 0..2, w -3..-1
    mw = _mundo(AXIAL, m)
    v0, t0 = mw[0].copy(), mw[1].copy()
    r = V.linhas_visiveis_vista([mw], AXIAL, profundidade=10.0)
    assert len(r) == 1 and all(isinstance(p, np.ndarray) and p.ndim == 2 and p.shape[1] == 2 and np.isfinite(p).all() for p in r[0])
    _igual(r[0], _retangulo(1, 0, 3, 2))  # 12 arestas: as 4 do contorno (frente e fundo coincidem), as 4 que fogem para o fundo não têm comprimento
    assert V.secao_plana(*mw, AXIAL) == []  # não toca o plano: sem tampa
    assert np.array_equal(mw[0], v0) and np.array_equal(mw[1], t0)
    r2 = V.linhas_visiveis_vista([mw], AXIAL, profundidade=10.0)
    assert len(r2[0]) == len(r[0]) and all(np.array_equal(a, b) for a, b in zip(r[0], r2[0]))  # determinístico


def test_a2_cubo_inclinado_atras_do_plano_bate_com_o_motor_de_topo():
    """Sem recorte nenhum (tudo em -profundidade <= w <= 0), a vista é o motor de topo da malha levada ao quadro."""
    V = _V()
    p, t = _cubo_girado((2.0, 2.0, -3.0), 30.0)
    p = p @ _rot(0.0, 25.0).T + np.array([0, 0, 0])  # inclina também para a câmera
    assert p[:, 2].max() < 0 and p[:, 2].min() > -6
    mw = _mundo(AXIAL, (p, t))
    got = V.linhas_visiveis_vista([mw], AXIAL, profundidade=6.0)[0]
    ref = V.linhas_visiveis_multi([(p, t)])[0]
    _igual(got, _segs(ref))


def test_b_cubo_cruzado_pelo_plano():
    V = _V()
    m = _caixa(0, 0, -1, 2, 3, 1)  # u 0..2, v 0..3, w -1..1: o plano o corta ao meio
    mw = _mundo(AXIAL, m)
    s = V.secao_plana(*mw, AXIAL)
    assert len(s) == 1 and s[0].geom_type == "Polygon" and abs(s[0].area - 6.0) <= 1e-9
    assert s[0].symmetric_difference(__import__("shapely.geometry", fromlist=["box"]).box(0, 0, 2, 3)).area <= 1e-9
    r = V.linhas_visiveis_vista([mw], AXIAL, profundidade=5.0)[0]
    _igual(r, _retangulo(0, 0, 2, 3))


def test_b2_corte_de_vies_area_exata_e_nada_alem_do_plano():
    V = _V()
    graus = 30.0
    m = _cubo_girado((2.0, 2.0, 0.0), graus)  # o plano w = 0 passa pelo centro: seção = retângulo 1 x 1/cos
    mw = _mundo(AXIAL, m)
    s = V.secao_plana(*mw, AXIAL)
    assert len(s) == 1 and abs(s[0].area - 1.0 / np.cos(np.radians(graus))) <= 1e-9
    r = V.linhas_visiveis_vista([mw], AXIAL, profundidade=5.0)[0]
    assert len(r)
    # caixa (u, v) do que fica em w <= 0: vértices com w <= 0 e os pontos onde as 12 arestas cruzam w = 0
    p, t = m
    ar = [(i, j) for i in range(8) for j in range(i + 1, 8) if np.count_nonzero(np.abs(p[i] - p[j]) > 1e-9) >= 1 and abs(np.linalg.norm(p[i] - p[j]) - 1.0) < 1e-9]
    assert len(ar) == 12
    pts = [p[i, :2] for i in range(8) if p[i, 2] <= 1e-12]
    for i, j in ar:
        if p[i, 2] * p[j, 2] < 0:
            k = p[i, 2] / (p[i, 2] - p[j, 2])
            pts.append((p[i] + k * (p[j] - p[i]))[:2])
    pts = np.array(pts)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    todos = np.vstack(r)
    assert (todos.min(axis=0) >= lo - 1e-6).all() and (todos.max(axis=0) <= hi + 1e-6).all(), "linha de geometria com w > 0"
    assert (p[:, :2].max(axis=0) > hi + 1e-3).any() or (p[:, :2].min(axis=0) < lo - 1e-3).any(), "o caso não discrimina: o cubo inteiro caberia na mesma caixa"


def test_c_oclusao_mutua_a_de_tras_perde_linhas():
    V = _V()
    A = _mundo(AXIAL, _caixa(0, 0, -5, 4, 2, -4))  # atrás
    B = _mundo(AXIAL, _caixa(2, 1, -2, 6, 3, -1))  # na frente, cobre u 2..6, v 1..3
    r = V.linhas_visiveis_vista([A, B], AXIAL, profundidade=10.0)
    assert len(r) == 2
    esp_a = np.array([[(0, 0), (0, 2)], [(0, 0), (4, 0)], [(4, 0), (4, 1)], [(0, 2), (2, 2)]], float)  # contorno de A menos o que B cobre
    _igual(r[0], esp_a)
    _igual(r[1], _retangulo(2, 1, 6, 3))
    so_a = V.linhas_visiveis_vista([A], AXIAL, profundidade=10.0)[0]
    assert _comp(so_a) > _comp(r[0]) + 1.0  # sozinha, A tem 8 de contorno; com B na frente sobram 9 - 3
    inv = V.linhas_visiveis_vista([B, A], AXIAL, profundidade=10.0)  # a ordem da lista não muda o resultado de cada peça
    _igual(inv[1], esp_a)
    _igual(inv[0], _retangulo(2, 1, 6, 3))


def test_d_profundidade_descarta_o_que_passa_do_alcance():
    V = _V()
    perto = _mundo(AXIAL, _caixa(0, 0, -1, 2, 2, -0.5))
    longe = _mundo(AXIAL, _caixa(0, 0, -5, 2, 2, -4))
    r = V.linhas_visiveis_vista([perto, longe], AXIAL, profundidade=2.0)
    _igual(r[0], _retangulo(0, 0, 2, 2))
    assert r[1] == [] or _comp(r[1]) < 1e-9, "peça além da profundidade desenhada"
    # peça que atravessa o limite: o que passa de -profundidade some (a cunha vai a v = 2 em w = -3; em w = -2, v = 1)
    cunha = _mundo(AXIAL, _cunha(0, 4, [(0, -1), (2, -3), (0, -5)]))
    cheia = np.vstack(V.linhas_visiveis_vista([cunha], AXIAL, profundidade=10.0)[0])
    assert abs(cheia[:, 1].max() - 2.0) <= 1e-6 and abs(cheia[:, 1].min()) <= 1e-6
    cortada = np.vstack(V.linhas_visiveis_vista([cunha], AXIAL, profundidade=2.0)[0])
    assert cortada[:, 1].max() <= 1.0 + 1e-6, "geometria além de -profundidade"
    assert cortada[:, 0].min() >= -1e-6 and cortada[:, 0].max() <= 4 + 1e-6 and cortada[:, 1].max() > 0.9


def test_e_vista_nao_axial_igual_ao_axial_com_a_malha_girada_ao_contrario():
    V = _V()
    base = [_caixa(0, 0, -5, 4, 2, -4), _caixa(2, 1, -2, 6, 3, -1), _caixa(7, 0, -1, 8, 2, 1), _cubo_girado((10.0, 1.0, -3.0), 20.0)]
    ax = [_mundo(AXIAL, m) for m in base]
    r_ax = V.linhas_visiveis_vista(ax, AXIAL, profundidade=8.0)
    R = _rot(37.0, 20.0)
    Q = SimpleNamespace(origem=R @ AXIAL.origem, u=R @ AXIAL.u, v=R @ AXIAL.v, w=R @ AXIAL.w)
    assert np.allclose(np.cross(Q.u, Q.v), Q.w) and np.allclose([Q.u @ Q.v, Q.u @ Q.w, Q.v @ Q.w], 0.0)
    gir = [(p @ R.T, t) for p, t in ax]
    r_g = V.linhas_visiveis_vista(gir, Q, profundidade=8.0)
    assert len(r_g) == len(r_ax) == 4 and all(len(a) for a in r_ax)
    for a, b in zip(r_ax, r_g):
        _igual(b, _segs(a), tol=1e-6)
    s0, s1 = V.secao_plana(*ax[2], AXIAL), V.secao_plana(*gir[2], Q)
    assert len(s0) == len(s1) == 1 and abs(s0[0].area - 2.0) <= 1e-9 and abs(s1[0].area - 2.0) <= 1e-6
    assert s0[0].symmetric_difference(s1[0]).area <= 1e-6
    obl = _mundo(AXIAL, _cubo_girado((10.0, 1.0, 0.0), 30.0))
    s2, s3 = V.secao_plana(*obl, AXIAL), V.secao_plana(obl[0] @ R.T, obl[1], Q)
    assert len(s2) == len(s3) == 1 and s2[0].symmetric_difference(s3[0]).area <= 1e-6


def test_e2_origem_deslocada():
    """A origem do quadro entra na conta: o mesmo traço com a origem em (10, 20, 30) e a cena movida junto."""
    V = _V()
    Q = _quadro(origem=(10.0, 20.0, 30.0))
    base = [_caixa(0, 0, -5, 4, 2, -4), _caixa(2, 1, -2, 6, 3, -1)]
    r0 = V.linhas_visiveis_vista([_mundo(AXIAL, m) for m in base], AXIAL, profundidade=10.0)
    r1 = V.linhas_visiveis_vista([_mundo(Q, m) for m in base], Q, profundidade=10.0)
    for a, b in zip(r0, r1):
        _igual(b, _segs(a))


def test_f_peca_do_lado_errado_some():
    V = _V()
    atras = _mundo(AXIAL, _caixa(0, 0, 1, 2, 2, 3))  # w > 0: atrás da câmera
    assert V.linhas_visiveis_vista([atras], AXIAL, profundidade=10.0) == [[]]
    assert V.secao_plana(*atras, AXIAL) == []
    ok = _mundo(AXIAL, _caixa(5, 0, -2, 7, 2, -1))
    r = V.linhas_visiveis_vista([atras, ok], AXIAL, profundidade=10.0)
    assert r[0] == [] and len(r) == 2
    _igual(r[1], _retangulo(5, 0, 7, 2))


def test_g_malha_vazia_ou_degenerada_nao_levanta():
    V = _V()
    vazia = (np.zeros((0, 3)), np.zeros((0, 3), int))
    assert V.linhas_visiveis_vista([], AXIAL, profundidade=1.0) == []
    assert V.linhas_visiveis_vista([vazia], AXIAL, profundidade=1.0) == [[]]
    sem_tri = (np.array([[0.0, 0, -1], [1, 0, -1], [0, 1, -1]]), np.zeros((0, 3), int))
    assert V.linhas_visiveis_vista([sem_tri], AXIAL, profundidade=1.0) == [[]]
    assert V.secao_plana(*vazia, AXIAL) == [] and V.secao_plana(*sem_tri, AXIAL) == []
    ok = _mundo(AXIAL, _caixa(0, 0, -2, 2, 2, -1))
    colinear = (np.array([[10.0, 0, -1], [11, 0, -1], [12, 0, -1]]), np.array([[0, 1, 2], [0, 0, 1]]))  # colinear, índice repetido
    atravessa = (np.array([[20.0, 0, -1], [21, 0, 1], [22, 0, 0]]), np.array([[0, 1, 2]]))  # colinear em (u, w) e cruzando o plano
    r = V.linhas_visiveis_vista([vazia, _mundo(AXIAL, colinear), ok, _mundo(AXIAL, atravessa)], AXIAL, profundidade=3.0)
    assert len(r) == 4 and r[0] == []
    assert all(p[:, 0].max() < 5 for p in r[1]) or not r[1]
    _igual(r[2], _retangulo(0, 0, 2, 2))
    for s in (V.secao_plana(*_mundo(AXIAL, colinear), AXIAL), V.secao_plana(*_mundo(AXIAL, atravessa), AXIAL)):
        assert all(g.area <= 1e-12 for g in s)


@pytest.mark.parametrize("prof", [-1.0, -1e-9, float("nan"), float("-inf"), "abc", ""])
def test_h_profundidade_invalida(prof):
    V = _V()
    mw = _mundo(AXIAL, _caixa(0, 0, -2, 2, 2, -1))
    with pytest.raises(ValueError):
        V.linhas_visiveis_vista([mw], AXIAL, profundidade=prof)
    with pytest.raises(ValueError):
        V.linhas_visiveis_vista([], AXIAL, profundidade=prof)  # validada antes de olhar a lista


def test_profundidade_so_por_nome():
    V = _V()
    mw = _mundo(AXIAL, _caixa(0, 0, -2, 2, 2, -1))
    with pytest.raises(TypeError):
        V.linhas_visiveis_vista([mw], AXIAL, 5.0)


# ---------------------------------------------------------------- contra a referência real (HLR do IfcOpenShell)
def _mesa(x0, x1, y0, y1, yf, yb, ly=0.1):
    """Tampo (esp. 5 cm, z 0,7..0,75) e 4 pernas (5 cm de lado em x, `ly` em y, z 0..0,7): as da frente em y `yf`, as de trás em `yb`. Uma malha só."""
    pernas = [_caixa(x, y, 0, x + 0.05, y + ly, 0.7) for x in (x0, x1 - 0.05) for y in (yf, yb)]
    return _junta(_caixa(x0, y0, 0.7, x1, y1, 0.75), *pernas)


def _cena_corte(tmp_path):
    """Corte para +Y a partir de y = 0: peças em coordenadas do mundo (metros). Bloco da vista: x -2..8, z -1..3, profundidade y 0..6."""
    exigir()
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.placement as placement
    from openbim_app import vistas_ifc

    nomes_malhas = [
        ("K1", _caixa(0, -0.5, 0, 1, 0.5, 1)),  # cruza o plano
        ("MesaA", _mesa(2.0, 3.2, -0.1, 0.9, -0.05, 0.75)),  # tampo e as pernas da frente cruzam o plano
        ("MesaB", _mesa(5.0, 6.2, 2.0, 3.2, 2.05, 3.0)),  # inteira atrás do plano
        ("Oclusor", _caixa(5.5, 1.0, 0.2, 6.5, 1.5, 0.6)),  # na frente da MesaB: esconde parte dela
        ("AtrasDaCamera", _caixa(4.0, -2.0, 1.0, 4.5, -1.0, 1.8)),  # y < 0: nada
        ("AlemDoAlcance", _caixa(0.0, 7.0, 1.2, 1.0, 8.0, 1.8)),  # y > 6: nada
    ]
    f, pavs = X.estrutura("IFC4", n_pav=1)
    els = []
    for nome, m in nomes_malhas:
        e = X.caixa(f, "IfcBuildingElementProxy", nome, 0, 0, 0, 1, 1, 1)
        X.conter(f, pavs[0], e)
        Z.densificar(f, e, ([tuple(map(float, p)) for p in m[0]], [tuple(map(int, q)) for q in m[1]]))
        els.append(e)
    x0, x1, y0, y1, z0, z1 = -2.0, 8.0, 0.0, 6.0, -1.0, 3.0
    gid = vistas_ifc.criar_vista(f, "C", "CORTE", escala="1:50", origem=(x0, y0, z0), tamanho=(x1 - x0, z1 - z0, y1 - y0))
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -(y1 - y0)))
    arq = str(pathlib.Path(tmp_path) / "corte.ifc")
    f.write(arq)
    ped = {"protocolo": 1, "op": "desenho", "arquivo": arq, "elementos": [[e.id(), e.GlobalId] for e in els], "threads": 1,
           "vista": {"tipo": "CORTE", "guid": gid, "escala": 1.0}}
    m = placement.get_local_placement(f.by_guid(gid).ObjectPlacement)
    Q = SimpleNamespace(origem=np.array(m[:3, 3], float), u=np.array(m[:3, 0], float), v=np.array(m[:3, 1], float), w=np.array(m[:3, 2], float))
    st = ifcopenshell.geom.settings()
    st.set(st.USE_WORLD_COORDS, True)
    malhas = []
    for e in els:  # a malha como o motor de verdade a entrega (mundo), não a que o teste escreveu
        sh = ifcopenshell.geom.create_shape(st, e)
        malhas.append((np.array(sh.geometry.verts, float).reshape(-1, 3), np.array(sh.geometry.faces, np.int64).reshape(-1, 3)))
    return ped, Q, malhas, y1 - y0, [n for n, _m in nomes_malhas]


def _svg_hlr(svg):
    """(polilinhas da projeção, polígonos do corte por caminho) em (u, v) relativos à origem da vista."""
    import re

    import shapely.geometry as sg

    vb = re.search(r'viewBox="0 0 ([-+0-9.eE]+) ([-+0-9.eE]+)"', svg)
    W, H = float(vb.group(1)), float(vb.group(2))
    corpo = svg[svg.find("</style>"):]
    pj = re.search(r'<g class="projection">(.*?)</g>', corpo, re.S)
    proj = pj.group(1) if pj else ""
    resto = corpo.replace(proj, "") if proj else corpo

    def subs(txt):
        for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', txt):
            yield [np.array([(float(a) - W / 2, H / 2 - float(b)) for a, b in re.findall(r"(-?[\d.]+(?:e[-+]?\d+)?),(-?[\d.]+(?:e[-+]?\d+)?)", s)]) for s in d.split("M")[1:]]

    linhas = [p for ss in subs(proj) for p in ss if len(p) >= 2]
    cortes = []
    for ss in subs(resto):
        pols = [sg.Polygon(p) for p in ss if len(p) >= 3]
        if pols:
            import shapely

            cortes.append(reduce(lambda a, b: a.symmetric_difference(b), [shapely.make_valid(p) for p in pols]))  # fill-rule evenodd
    return linhas, cortes


def test_referencia_hlr_linhas_e_tampas(tmp_path):
    import shapely

    V = _V()
    ped, Q, malhas, prof, nomes = _cena_corte(tmp_path)
    r = __import__("obim_geometria.desenho", fromlist=["processar"]).processar(copy.deepcopy(ped))
    assert r["ok"], r.get("erro")
    ref_linhas, ref_cortes = _svg_hlr(r["svg"])
    assert len(ref_linhas) and len(ref_cortes), "o HLR de referência não devolveu linhas e corte"
    a = _segs(ref_linhas)

    lin = V.linhas_visiveis_vista(malhas, Q, profundidade=prof)
    assert len(lin) == len(malhas)
    assert lin[nomes.index("AtrasDaCamera")] == [] and lin[nomes.index("AlemDoAlcance")] == []
    assert all(len(lin[nomes.index(n)]) for n in ("K1", "MesaA", "MesaB", "Oclusor"))
    b = _segs([p for pls in lin for p in pls])

    # o HLR desenha as diagonais coplanares da triangulação (sem traço no contrato do motor, T19b2): o trecho que só cai sobre elas não conta
    cop, resto = [], []
    for m in malhas:
        c, rs = _coplanares(_no_quadro(Q, m))
        cop.append(c)
        resto.append(rs)
    cop, resto = np.concatenate(cop), np.concatenate(resto)
    p, w = _amostra(a)
    ficar = ~((_dist(p, cop) <= TOL) & (_dist(p, resto) > TOL))
    cob = float(w[ficar & (_dist(p, b) <= TOL)].sum() / w[ficar].sum())
    assert cob >= 0.99, f"linha do HLR faltando no motor ({cob:.4f})"
    assert _cobertura(b, a) >= 0.99, f"linha sobrando no motor ({_cobertura(b, a):.4f})"

    # tampas: o HLR escreve o corte por elemento; a união das seções do motor tem a mesma área (1%) e o mesmo desenho
    secoes = [g for m in malhas for g in V.secao_plana(*m, Q)]
    assert secoes and all(g.geom_type == "Polygon" for g in secoes)
    meu, dele = shapely.unary_union(secoes), shapely.unary_union(ref_cortes)
    assert dele.area > 0 and abs(meu.area - dele.area) <= 0.01 * dele.area, f"área do corte {meu.area} x HLR {dele.area}"
    assert meu.symmetric_difference(dele).area <= 0.01 * dele.area
    assert abs(meu.area - 1.13) <= 1e-9  # K1 (1 x 1) + tampo 1,2 x 0,05 + 2 pernas da frente 0,05 x 0,7 (0,06 + 0,07)
    for nome in ("MesaB", "Oclusor", "AtrasDaCamera", "AlemDoAlcance"):
        assert V.secao_plana(*malhas[nomes.index(nome)], Q) == [], f"{nome} não cruza o plano"


def test_secao_com_furo_mantem_o_vazio():
    """Parede com abertura / tubo oco: a tampa tem furo (revisão Argon, 15/11). Moldura 4x4 com vão 2x2, feita de 4 caixas numa malha."""
    V = _V()
    partes = [_caixa(0, 0, -1, 4, 1, 1), _caixa(0, 3, -1, 4, 4, 1), _caixa(0, 1, -1, 1, 3, 1), _caixa(3, 1, -1, 4, 3, 1)]
    p = np.concatenate([x[0] for x in partes])
    t = np.concatenate([x[1] + sum(len(y[0]) for y in partes[:i]) for i, x in enumerate(partes)])
    s = V.secao_plana(*_mundo(AXIAL, (p, t)), AXIAL)
    assert abs(sum(g.area for g in s) - 12.0) <= 1e-9, "o vão 2x2 não pode ser tampado"
    assert sum(len(g.interiors) for g in s) == 1
    ilha = _caixa(1.5, 1.5, -1, 2.5, 2.5, 1)  # ilha dentro do vão (outra peça solta na mesma malha): conta de novo
    p2 = np.concatenate([p, ilha[0]])
    t2 = np.concatenate([t, ilha[1] + len(p)])
    s2 = V.secao_plana(*_mundo(AXIAL, (p2, t2)), AXIAL)
    assert abs(sum(g.area for g in s2) - 13.0) <= 1e-9


def _juntar(partes):
    p = np.concatenate([x[0] for x in partes])
    t = np.concatenate([x[1] + sum(len(y[0]) for y in partes[:i]) for i, x in enumerate(partes)])
    return p, t


def test_pecas_encostadas_na_mesma_malha_somam_as_areas():
    """Revisão Argon (15/11): a parede interna compartilhada tem 2 triângulos opostos; nenhum pode ser colapsado."""
    V = _V()
    m = _juntar([_caixa(0, 0, -1, 1, 1, 1), _caixa(1, 0, -1, 2, 1, 1)])
    s = V.secao_plana(*_mundo(AXIAL, m), AXIAL)
    assert abs(sum(g.area for g in s) - 2.0) <= 1e-9
    # vértices exatamente em w = 0 (costura): cada caixa partida em duas metades
    m2 = _juntar([_caixa(0, 0, -1, 1, 1, 0), _caixa(0, 0, 0, 1, 1, 1), _caixa(1, 0, -1, 2, 1, 0), _caixa(1, 0, 0, 2, 1, 1)])
    s2 = V.secao_plana(*_mundo(AXIAL, m2), AXIAL)
    assert abs(sum(g.area for g in s2) - 2.0) <= 1e-9


def test_secao_grande_nao_estoura_memoria():
    """5000 caixas lado a lado: a conta par-impar não pode materializar faces x segmentos densos (< 600 MB de pico)."""
    import tracemalloc
    V = _V()
    m = _juntar([_caixa(2 * k, 0, -1, 2 * k + 1, 1, 1) for k in range(3000)])
    tracemalloc.start()
    s = V.secao_plana(*_mundo(AXIAL, m), AXIAL)
    pico = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert len(s) == 3000 and abs(sum(g.area for g in s) - 3000.0) <= 1e-6
    assert pico < 600e6
