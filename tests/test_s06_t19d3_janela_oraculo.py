# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19d3: janela da vista no motor lateral e no `_corte` (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19d3-janela-corte.md. Não editar nesta tarefa.
CONTRATO (`obim_geometria.visibilidade`, `obim_geometria.desenho._corte`):
1. `linhas_visiveis_vista(pecas, quadro, *, profundidade, janela=None, margem=0.1, angulo_graus=..., tol_z=..., min_len=...)`. `janela=None` = resultado idêntico ao de hoje.
2. `janela=(umin, umax, vmin, vmax)` em (u, v) do quadro, metros. Inválida (não é tupla/lista de 4 reais finitos, bool não vale, umin>=umax, vmin>=vmax) -> ValueError;
   `margem` real finito >= 0 (bool não vale) senão ValueError. Entrada não é alterada.
3. Equivalência: dentro da janela, as linhas com janela coincidem (5 mm, TOL da T19b1) com as sem janela, nos dois sentidos; nada passa de janela + margem (1e-6). A oclusão só ocorre ao longo de w.
4. Peça toda fora da janela + margem -> `[]` para ela; as demais seguem corretas e na ordem da entrada. 5. Oclusão correta com peça parcialmente dentro. 6. Vazio/degenerado nunca levanta.
7. `secao_plana(verts, tris, quadro, *, janela=None)`: com janela = interseção do resultado sem janela com o retângulo (SEM margem), furos preservados, fora -> [].
8. `desenho._corte` (motor_visivel): UMA chamada `visibilidade.linhas_visiveis_vista(..., janela=(-W/2, W/2, -H/2, H/2))`, `W = bloco.XLength * esc`, `H = bloco.YLength * esc`; `visibilidade.secao_plana(..., janela=<a mesma>)` uma vez por peça elegível.
9. Exceção no motor com janela -> queda inteira para o HLR, como na T19d2."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from test_s06_t19b1_visibilidade_oraculo import TOL, _amostra, _caixa, _dist, _segs
from test_s06_t19d1_motor_lateral_oraculo import AXIAL, _cubo_girado, _juntar, _mundo, _rot
from test_s06_t19d2_motor_no_corte_oraculo import ELEGIVEIS, _cena, _confere_linhas, _confere_tampas, _modulo, _par, _roda

import obim_geometria.desenho as D


def _V():
    return _modulo()


JAN = (0.0, 4.0, 0.0, 3.0)
PROF = 8.0


# ---------------------------------------------------------------- cenas (em coordenadas do quadro AXIAL)
def _cena_grande():
    return [_caixa(-2, 0.5, -3, 8, 2.5, -2)]  # ultrapassa a janela dos dois lados em u


def _cena_duas():
    return [_caixa(0.5, 0.5, -5, 3.5, 2.5, -4), _caixa(2, 1, -2, 5, 3.5, -1)]  # B tapa parte de A dentro da janela e sai por v e por u


def _cena_fora():
    return [_caixa(0.5, 0.5, -5, 3.5, 2.5, -4), _caixa(5, -5, -1, 40, 40, -0.5)]  # grande na frente, mas só fora da janela (u >= 5)


def _cena_inclinada():
    p, t = _cubo_girado((3.8, 1.5, -3.0), 30.0)
    return [(p @ _rot(0.0, 25.0).T, t), _caixa(0, 0, -6, 1, 1, -5)]


CENAS = {"grande": _cena_grande, "duas": _cena_duas, "fora": _cena_fora, "inclinada": _cena_inclinada}


def _quadro_girado():
    R = _rot(37.0, 20.0)
    return SimpleNamespace(origem=R @ AXIAL.origem, u=R @ AXIAL.u, v=R @ AXIAL.v, w=R @ AXIAL.w), R


def _prepara(nome, nao_axial):
    ms = CENAS[nome]()
    ax = [_mundo(AXIAL, m) for m in ms]
    if not nao_axial:
        return ax, AXIAL
    Q, R = _quadro_girado()
    return [(p @ R.T, t) for p, t in ax], Q


def _dentro(pts, j, e=0.0):
    return (pts[:, 0] >= j[0] - e) & (pts[:, 0] <= j[1] + e) & (pts[:, 1] >= j[2] - e) & (pts[:, 1] <= j[3] + e)


def _confere_peca(sem, com, j, margem):
    """`sem`/`com`: polilinhas de uma peça sem e com janela."""
    if com:
        todos = np.vstack(com)
        assert (todos[:, 0] >= j[0] - margem - 1e-6).all() and (todos[:, 0] <= j[1] + margem + 1e-6).all()
        assert (todos[:, 1] >= j[2] - margem - 1e-6).all() and (todos[:, 1] <= j[3] + margem + 1e-6).all(), "linha além da janela + margem"
    a = _segs(sem)
    b = _segs(com)
    pa = _amostra(a)[0] if len(a) else np.zeros((0, 2))
    pb = _amostra(b)[0] if len(b) else np.zeros((0, 2))
    ia, ib = pa[_dentro(pa, j)], pb[_dentro(pb, j)]
    if len(ia):
        assert len(b), "linhas dentro da janela sumiram"
        assert (_dist(ia, b) <= TOL).all(), "linha sem janela (dentro dela) faltando no resultado com janela"
    if len(ib):
        assert len(a), "linhas surgiram do nada"
        assert (_dist(ib, a) <= TOL).all(), "linha com janela (dentro dela) sobrando"


def _confere_cena(pecas, Q, j=JAN, margem=0.1):
    V = _V()
    sem = V.linhas_visiveis_vista(pecas, Q, profundidade=PROF)
    com = V.linhas_visiveis_vista(pecas, Q, profundidade=PROF, janela=j, margem=margem)
    assert len(com) == len(sem) == len(pecas)
    for s, c in zip(sem, com):
        _confere_peca(s, c, j, margem)
    return sem, com


# ---------------------------------------------------------------- 1: janela=None
@pytest.mark.parametrize("nome", list(CENAS))
def test_janela_none_identica_a_de_hoje(nome):
    V = _V()
    pecas, Q = _prepara(nome, False)
    a = V.linhas_visiveis_vista(pecas, Q, profundidade=PROF)
    b = V.linhas_visiveis_vista(pecas, Q, profundidade=PROF, janela=None)
    assert len(a) == len(b) and all(len(x) == len(y) and all(np.array_equal(p, q) for p, q in zip(x, y)) for x, y in zip(a, b))
    assert any(len(x) for x in a)


def test_assinatura_so_por_nome():
    import inspect

    V = _V()
    p = inspect.signature(V.linhas_visiveis_vista).parameters
    assert p["janela"].default is None and p["margem"].default == pytest.approx(0.1)
    assert p["janela"].kind == p["margem"].kind == inspect.Parameter.KEYWORD_ONLY
    assert inspect.signature(V.secao_plana).parameters["janela"].default is None
    assert inspect.signature(V.secao_plana).parameters["janela"].kind == inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------- 2: validação
INVALIDAS = [(0, 1, 0), (0, 1, 0, 1, 2), "abcd", 5, (0, 1, 0, True), (True, 2, 0, 1), (0, 0, 0, 1), (1, 0, 0, 1), (0, 1, 1, 1), (0, 1, 2, 1),
             (float("nan"), 1, 0, 1), (0, float("inf"), 0, 1), (0, 1, float("-inf"), 1), ("a", 1, 0, 1), (0, 1, 0, None), (0, 1, 0, [1])]


@pytest.mark.parametrize("janela", INVALIDAS)
def test_janela_invalida(janela):
    V = _V()
    mw = _mundo(AXIAL, _caixa(0, 0, -2, 2, 2, -1))
    with pytest.raises(ValueError):
        V.linhas_visiveis_vista([mw], AXIAL, profundidade=5.0, janela=janela)
    with pytest.raises(ValueError):
        V.secao_plana(*_mundo(AXIAL, _caixa(0, 0, -1, 2, 2, 1)), AXIAL, janela=janela)


@pytest.mark.parametrize("margem", [-1.0, -1e-9, float("nan"), float("inf"), True, False, "a", None, [0.1]])
def test_margem_invalida(margem):
    V = _V()
    mw = _mundo(AXIAL, _caixa(0, 0, -2, 2, 2, -1))
    with pytest.raises(ValueError):
        V.linhas_visiveis_vista([mw], AXIAL, profundidade=5.0, janela=JAN, margem=margem)


@pytest.mark.parametrize("janela, margem", [((0, 4, 0, 3), 0), ([0, 4, 0, 3], 1), ((np.float64(0), np.float64(4), 0.0, 3.0), 0.25), ((-1e6, 1e6, -1e6, 1e6), 0.0)])
def test_janela_e_margem_validas(janela, margem):
    V = _V()
    mw = _mundo(AXIAL, _caixa(0.5, 0.5, -2, 2, 2, -1))
    r = V.linhas_visiveis_vista([mw], AXIAL, profundidade=5.0, janela=janela, margem=margem)
    assert len(r) == 1 and len(r[0])


def test_entrada_nao_e_alterada():
    V = _V()
    pecas, Q = _prepara("duas", True)
    copia = [(p.copy(), t.copy()) for p, t in pecas]
    jan = [0.0, 4.0, 0.0, 3.0]
    V.linhas_visiveis_vista(pecas, Q, profundidade=PROF, janela=jan)
    V.secao_plana(*pecas[0], Q, janela=jan)
    assert jan == [0.0, 4.0, 0.0, 3.0]
    assert all(np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1]) for a, b in zip(pecas, copia))


# ---------------------------------------------------------------- 3: equivalência
@pytest.mark.parametrize("nao_axial", [False, True])
@pytest.mark.parametrize("nome", list(CENAS))
def test_equivalencia_dentro_da_janela(nome, nao_axial):
    pecas, Q = _prepara(nome, nao_axial)
    sem, com = _confere_cena(pecas, Q)
    assert any(len(s) for s in sem), "cena vazia: o teste não discrimina"
    assert any(len(c) for c in com)


def test_equivalencia_cena_junta_nao_axial_e_margens():
    ms = _cena_duas() + _cena_inclinada() + [_caixa(6, 0, -1, 7, 2, -0.5)]
    Q, R = _quadro_girado()
    pecas = [(_mundo(AXIAL, m)[0] @ R.T, m[1]) for m in ms]
    for margem in (0.0, 0.1, 1.0):
        _confere_cena(pecas, Q, margem=margem)
    _confere_cena(pecas, Q, j=(1.0, 2.5, 0.8, 2.2), margem=0.0)  # janela pequena, no meio


def test_peca_grande_fora_nao_esconde_nada_e_some():
    V = _V()
    pecas, Q = _prepara("fora", False)
    sem, com = _confere_cena(pecas, Q)
    assert len(com[0]) and com[1] == [], "peça fora da janela + margem deve voltar []"
    assert _segs(sem[0]).shape == _segs(com[0]).shape or len(com[0]), "A mantém linhas"
    # sanidade: a peça grande de fato cobre o que está atrás dela fora da janela (sem janela, vê-se menos de A não: ela está em u>=5)
    assert len(sem[1])


# ---------------------------------------------------------------- 4: fora some, ordem mantida
def test_peca_fora_da_janela_da_lista_vazia_e_mantem_a_ordem():
    V = _V()
    fora1 = _mundo(AXIAL, _caixa(10, 0, -3, 12, 2, -2))
    A = _mundo(AXIAL, _caixa(0.5, 0.5, -5, 3.5, 2.5, -4))
    fora2 = _mundo(AXIAL, _caixa(0, 10, -3, 2, 12, -2))
    B = _mundo(AXIAL, _caixa(2, 1, -2, 5, 3.5, -1))
    pecas = [fora1, A, fora2, B]
    sem = V.linhas_visiveis_vista(pecas, AXIAL, profundidade=PROF)
    com = V.linhas_visiveis_vista(pecas, AXIAL, profundidade=PROF, janela=JAN)
    assert len(com) == 4 and com[0] == [] and com[2] == [] and len(sem[0]) and len(sem[2])
    for i in (1, 3):
        assert len(com[i])
        _confere_peca(sem[i], com[i], JAN, 0.1)
    # peça só na faixa da margem fica; além dela, não
    na_margem = _mundo(AXIAL, _caixa(4.02, 0.5, -3, 4.08, 2.5, -2))
    alem = _mundo(AXIAL, _caixa(4.3, 0.5, -3, 4.5, 2.5, -2))
    r = V.linhas_visiveis_vista([na_margem, alem], AXIAL, profundidade=PROF, janela=JAN, margem=0.1)
    assert r[1] == []
    assert V.linhas_visiveis_vista([alem], AXIAL, profundidade=PROF, janela=JAN, margem=1.0)[0] != []


# ---------------------------------------------------------------- 5: oclusão com peça parcialmente dentro
@pytest.mark.parametrize("nao_axial", [False, True])
def test_oclusao_com_peca_parcialmente_dentro(nao_axial):
    V = _V()
    ms = [_caixa(-1, 1, -5, 7, 2, -4), _caixa(2, 0.5, -2, 6, 3, -1)]  # A atrás (arestas v=1 e v=2 cruzam a janela); B na frente, de u 2 a 6 (sai da janela em u = 4)
    pecas = [_mundo(AXIAL, m) for m in ms]
    Q = AXIAL
    if nao_axial:
        Q, R = _quadro_girado()
        pecas = [(p @ R.T, t) for p, t in pecas]
    sem, com = _confere_cena(pecas, Q)
    a = np.vstack(com[0]) if com[0] else np.zeros((0, 2))
    assert len(a), "A tem linhas visíveis em u < 2"
    dentro = a[_dentro(a, JAN)]
    assert len(dentro) and dentro[:, 0].max() <= 2.0 + TOL, "linhas de A atrás de B não podem aparecer"
    assert len(com[1]) and np.vstack(com[1])[:, 0].max() <= 4.1 + 1e-6


# ---------------------------------------------------------------- 6: vazio / degenerado
def test_vazio_e_degenerado_com_janela_nao_levanta():
    V = _V()
    vazia = (np.zeros((0, 3)), np.zeros((0, 3), int))
    sem_tri = (np.array([[0.0, 0, -1], [1, 0, -1], [0, 1, -1]]), np.zeros((0, 3), int))
    colinear = (np.array([[1.0, 0, -1], [2, 0, -1], [3, 0, -1]]), np.array([[0, 1, 2], [0, 0, 1]]))
    atravessa = (np.array([[1.0, 0, -1], [2, 0, 1], [3, 0, 0]]), np.array([[0, 1, 2]]))
    ok = _mundo(AXIAL, _caixa(0.5, 0.5, -2, 2, 2, -1))
    assert V.linhas_visiveis_vista([], AXIAL, profundidade=1.0, janela=JAN) == []
    assert V.linhas_visiveis_vista([vazia], AXIAL, profundidade=1.0, janela=JAN) == [[]]
    assert V.linhas_visiveis_vista([sem_tri], AXIAL, profundidade=1.0, janela=JAN) == [[]]
    r = V.linhas_visiveis_vista([vazia, _mundo(AXIAL, colinear), ok, _mundo(AXIAL, atravessa), sem_tri], AXIAL, profundidade=3.0, janela=JAN)
    assert len(r) == 5 and r[0] == [] and r[4] == [] and len(r[2])
    for m in (vazia, sem_tri, _mundo(AXIAL, colinear), _mundo(AXIAL, atravessa)):
        assert all(g.area <= 1e-12 for g in V.secao_plana(*m, AXIAL, janela=JAN))
    assert V.secao_plana(*vazia, AXIAL, janela=JAN) == []


# ---------------------------------------------------------------- 7: secao_plana com janela
def _moldura_malha():
    return _juntar([_caixa(0, 0, -1, 4, 1, 1), _caixa(0, 3, -1, 4, 4, 1), _caixa(0, 1, -1, 1, 3, 1), _caixa(3, 1, -1, 4, 3, 1)])  # 4x4 com vão 2x2


def _secoes_casos():
    return {
        "caixa": _caixa(-2, -1, -1, 6, 5, 1),
        "moldura": _moldura_malha(),
        "girado": _cubo_girado((3.0, 2.0, 0.0), 30.0),
        "pequena_dentro": _caixa(1, 1, -1, 2, 2, 1),
        "fora": _caixa(10, 10, -1, 12, 12, 1),
    }


@pytest.mark.parametrize("nao_axial", [False, True])
@pytest.mark.parametrize("janela", [(0.0, 4.0, 0.0, 3.0), (0.5, 3.5, 0.5, 3.5), (-1.0, 5.0, -1.0, 5.0), (1.2, 2.7, -3.0, 2.2)])
def test_secao_com_janela_e_a_intersecao_com_o_retangulo(janela, nao_axial):
    import shapely
    import shapely.geometry as sg

    V = _V()
    Q = AXIAL
    R = np.eye(3)
    if nao_axial:
        Q, R = _quadro_girado()
    box = sg.box(janela[0], janela[2], janela[1], janela[3])
    for nome, m in _secoes_casos().items():
        p, t = _mundo(AXIAL, m)
        p = p @ R.T
        sem = V.secao_plana(p, t, Q)
        com = V.secao_plana(p, t, Q, janela=janela)
        esp = shapely.unary_union(sem).intersection(box) if sem else sg.Polygon()
        assert all(g.geom_type == "Polygon" for g in com)
        if esp.area == 0:
            assert sum(g.area for g in com) <= 1e-9, nome
            continue
        got = shapely.unary_union(com)
        assert abs(got.area - esp.area) <= 1e-6 * max(esp.area, 1.0), f"{nome}: área {got.area} x {esp.area}"
        assert got.symmetric_difference(esp).area <= 1e-6 * max(esp.area, 1.0), nome
        assert sum(len(g.interiors) for g in com) == sum(len(g.interiors) for g in shapely.get_parts(esp)), f"{nome}: furos"


def test_secao_janela_none_igual_e_furo_preservado_e_fora_vazio():
    import shapely

    V = _V()
    p, t = _mundo(AXIAL, _moldura_malha())
    a, b = V.secao_plana(p, t, AXIAL), V.secao_plana(p, t, AXIAL, janela=None)
    assert len(a) == len(b) and all(x.equals(y) for x, y in zip(a, b))
    com = V.secao_plana(p, t, AXIAL, janela=(0.5, 3.5, 0.5, 3.5))  # o vão 1..3 fica dentro da janela
    assert sum(len(g.interiors) for g in com) == 1 and abs(shapely.unary_union(com).area - (9.0 - 4.0)) <= 1e-9
    assert V.secao_plana(p, t, AXIAL, janela=(10.0, 11.0, 10.0, 11.0)) == []
    assert V.secao_plana(*_mundo(AXIAL, _caixa(0, 0, -3, 2, 2, -1)), AXIAL, janela=JAN) == []  # não cruza o plano


# ---------------------------------------------------------------- 8: _corte passa a janela (espiões/stubs sempre via atributos do módulo)
def _bloco(c):
    import ifcopenshell

    f = ifcopenshell.open(c.ped["arquivo"])
    b = f.by_type("IfcBlock")
    assert b, "vista sem IfcBlock"
    return float(b[0].XLength), float(b[0].YLength)


def _troca(monkeypatch, lin, sec):
    V = _V()
    for nome, fn in (("linhas_visiveis_vista", lin), ("secao_plana", sec)):
        monkeypatch.setattr(V, nome, fn)
        if hasattr(D, nome):
            monkeypatch.setattr(D, nome, fn)


def _stubs(monkeypatch):
    lin, sec = [], []

    def stub_lin(pecas, quadro, **kw):
        lin.append((len(pecas), kw))
        return [[] for _ in pecas]

    def stub_sec(verts, tris, quadro, **kw):
        sec.append(kw)
        return []

    _troca(monkeypatch, stub_lin, stub_sec)
    return lin, sec


@pytest.mark.parametrize("esc", [1.0, 0.001])
def test_corte_passa_a_janela_do_bloco_em_metros(monkeypatch, tmp_path, esc):
    c = _cena(tmp_path)
    c.ped["vista"] = {**c.ped["vista"], "escala": esc}
    xl, yl = _bloco(c)
    W, H = xl * esc, yl * esc
    assert (W, H) == pytest.approx((10.0 * esc, 4.0 * esc))
    lin, sec = _stubs(monkeypatch)
    r = _roda(c, motor_visivel=True)
    assert r["ok"], r.get("erro")
    assert len(lin) == 1, "uma chamada de linhas_visiveis_vista"
    n, kw = lin[0]
    assert n == len(ELEGIVEIS) and "janela" in kw
    esperada = (-W / 2, W / 2, -H / 2, H / 2)
    assert tuple(kw["janela"]) == pytest.approx(esperada)
    assert len(sec) == n, "uma secao_plana por peça elegível"
    assert all("janela" in k and tuple(k["janela"]) == pytest.approx(esperada) for k in sec)


def test_corte_escala_milimetros_xlength_10000():
    """Aritmética do contrato: bloco em milímetros (XLength = 10000) com esc = 0,001 dá janela de 10 m."""
    esc, xl, yl = 0.001, 10000.0, 4000.0
    assert (-xl * esc / 2, xl * esc / 2, -yl * esc / 2, yl * esc / 2) == pytest.approx((-5.0, 5.0, -2.0, 2.0))


def test_corte_com_motor_real_e_janela_bate_com_o_hlr(tmp_path):
    c = _cena(tmp_path)
    ref, r = _par(c)
    assert r["motor_pecas"], "o motor não desenhou nada (caiu para o HLR?)"
    _confere_linhas(ref, r, [c.malhas[n] for n in ELEGIVEIS], c.Q)
    _confere_tampas(ref, r)


def test_janela_reduz_o_trabalho_chamadas_reais_recebem_a_janela(monkeypatch, tmp_path):
    c = _cena(tmp_path)
    V = _V()
    real_l, real_s = V.linhas_visiveis_vista, V.secao_plana
    vistos = []

    def lin(*a, **k):
        vistos.append(k.get("janela"))
        return real_l(*a, **k)

    def sec(*a, **k):
        vistos.append(k.get("janela"))
        return real_s(*a, **k)

    _troca(monkeypatch, lin, sec)
    r = _roda(c, motor_visivel=True)
    assert r["ok"] and r["motor_pecas"] and len(vistos) >= 1 + 3 and all(v is not None for v in vistos)
    assert len({tuple(v) for v in vistos}) == 1


# ---------------------------------------------------------------- 9: queda para o HLR com janela
@pytest.mark.parametrize("nome, na_chamada", [("linhas_visiveis_vista", 1), ("secao_plana", 1), ("secao_plana", 2)])
def test_excecao_com_janela_cai_inteiro_para_o_hlr(monkeypatch, tmp_path, nome, na_chamada):
    c = _cena(tmp_path)
    ref = _roda(c)
    V = _V()
    real = getattr(V, nome)
    chamadas = []

    def espiao(*a, **k):
        chamadas.append(k)
        if len(chamadas) >= na_chamada:
            raise RuntimeError("falha injetada")
        return real(*a, **k)

    monkeypatch.setattr(V, nome, espiao)
    if hasattr(D, nome):
        monkeypatch.setattr(D, nome, espiao)
    r = _roda(c, motor_visivel=True)
    assert len(chamadas) >= na_chamada and "janela" in chamadas[0], "o motor deve ser chamado com janela="
    assert r["ok"] and r["motor_pecas"] == [] and r["svg"] == ref["svg"]
    assert isinstance(r["tempos"].get("motor_s"), float)
