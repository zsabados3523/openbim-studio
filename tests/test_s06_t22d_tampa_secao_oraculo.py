# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo T22d: `oclusores_extra` (tampas de secao) em `linhas_visiveis_multi`.

Contrato: cada item de `oclusores_extra` e um ndarray (n,3,3) de triangulos em coordenadas do mundo, usado SO como oclusor
(nao gera linhas, nao entra na lista de retorno: 1 item por peca). None ou [] = comportamento identico ao atual, bit a bit.
Entrada invalida = ValueError. Oclusor coplanar (dentro de tol_z) ou abaixo da peca nao oculta. Ordem dos oclusores nao importa.
Cenas sinteticas exatas, valores calculados a mao (sem dourado do motor). Vista de cima (+Z)."""
from __future__ import annotations

import inspect
import itertools
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from obim_geometria.visibilidade import linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import caixa, todas

TOL = 1e-4  # o motor quantiza vertices em 1e-6: cortes analiticos saem com ~2e-6 de erro
TOLZ = 1e-3
TEM_TRAB = "trabalhadores" in inspect.signature(linhas_visiveis_multi).parameters


def viga():
    """Caixa x 0..4, y 0..1, z 0..1. Visivel de cima sem oclusor: o retangulo do topo (perimetro 10 m)."""
    return caixa(np.array([2.0, 0.5, 0.5]), [4.0, 1.0, 1.0])


def longe():
    """Caixa a 100 m da viga (sem sobreposicao em XY)."""
    return caixa(np.array([102.0, 0.5, 0.5]), [4.0, 1.0, 1.0])


def tampa(x0, x1, z, y0=-1.0, y1=2.0):
    """Retangulo horizontal em z, 2 triangulos, normal para cima."""
    p = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], float)
    return p[[[0, 1, 2], [0, 2, 3]]]


def run(pecas, oc=None, **kw):
    kw.setdefault("tol_z", TOLZ)
    return linhas_visiveis_multi(pecas, oclusores_extra=oc, **kw)


def comp(pls):
    return float(sum(np.hypot(*np.diff(p, axis=0).T).sum() for p in pls))


def pts(pls):
    return np.concatenate(pls) if pls else np.zeros((0, 2))


def canon(pls):
    ch = np.array([[len(p), *np.round(p[0], 5), *np.round(p[-1], 5)] for p in pls]) if pls else np.zeros((0, 5))
    return [pls[i] for i in np.lexsort(ch.T[::-1])] if pls else []


def iguais(a, b, tol=0.0):
    a, b = canon(a), canon(b)
    return len(a) == len(b) and all(x.shape == y.shape and (np.abs(x - y).max() <= tol if x.size else True) for x, y in zip(a, b))


def base(pecas):
    return linhas_visiveis_multi(pecas, tol_z=TOLZ)


def test_base_da_viga_e_o_perimetro_do_topo():
    assert comp(base([viga()])[0]) == pytest.approx(10.0, abs=TOL)


# (1) viga sob tampa de parede: linhas ocultas somem
def test_viga_sob_tampa_total_some_e_vizinha_intacta():
    pecas = [viga(), longe()]
    r = run(pecas, [tampa(-1, 5, 2.0)])
    assert len(r) == 2
    assert r[0] == [] or comp(r[0]) <= TOL
    assert iguais(r[1], base(pecas)[1])


def test_tampa_alta_e_baixa_empilhadas_tambem_ocultam():
    assert comp(run([viga()], [tampa(-1, 5, 1.5)])[0]) <= TOL
    assert comp(run([viga()], [tampa(-1, 5, 50.0)])[0]) <= TOL


# (2) tampa parcial: so o trecho coberto (x < 2) some; restam 2 (y=0) + 1 (x=4) + 2 (y=1) = 5 m
def test_tampa_parcial_remove_so_o_trecho_coberto():
    r = run([viga()], [tampa(-1, 2, 2.0)])[0]
    assert comp(r) == pytest.approx(5.0, abs=TOL)
    assert pts(r)[:, 0].min() >= 2.0 - TOL
    assert pts(r)[:, 0].max() == pytest.approx(4.0, abs=TOL)


def test_tampa_que_nao_toca_a_viga_em_xy_nao_muda_nada():
    assert iguais(run([viga()], [tampa(5.5, 9, 2.0)])[0], base([viga()])[0])
    assert iguais(run([viga()], [tampa(-1, 5, 2.0, 3.0, 6.0)])[0], base([viga()])[0])


# (3) borda exata / tol_z
@pytest.mark.parametrize("dz", [0.0, 0.4 * TOLZ, -0.4 * TOLZ])
def test_oclusor_coplanar_dentro_de_tol_z_nao_oculta(dz):
    assert iguais(run([viga()], [tampa(-1, 5, 1.0 + dz)])[0], base([viga()])[0])


def test_oclusor_acima_de_tol_z_oculta():
    assert comp(run([viga()], [tampa(-1, 5, 1.0 + 10 * TOLZ)])[0]) <= TOL


def test_tol_z_maior_faz_o_mesmo_oclusor_deixar_de_ocultar():
    tp = [tampa(-1, 5, 1.0 + 5e-3)]
    assert comp(run([viga()], tp, tol_z=1e-3)[0]) <= TOL  # 5e-3 > tol_z: oculta
    assert iguais(run([viga()], tp, tol_z=1e-2)[0], linhas_visiveis_multi([viga()], tol_z=1e-2)[0])  # 5e-3 < tol_z: nao oculta


@pytest.mark.parametrize("z", [-1.0, 0.5, -50.0])
def test_oclusor_abaixo_do_topo_da_peca_nao_oculta(z):
    assert iguais(run([viga()], [tampa(-1, 5, z)])[0], base([viga()])[0])


# (4) None e [] iguais ao atual, bit a bit
@pytest.mark.parametrize("nome", ["a05", "d2", "bordas"])
@pytest.mark.parametrize("oc", [None, []])
def test_sem_oclusores_extra_e_identico_bit_a_bit(nome, oc):
    pecas = todas()[nome]()
    r0 = linhas_visiveis_multi(pecas)
    r1 = linhas_visiveis_multi(pecas, oclusores_extra=oc)
    assert len(r0) == len(r1)
    for x, y in zip(r0, r1):
        assert len(x) == len(y) and all(p.dtype == q.dtype and np.array_equal(p, q) for p, q in zip(x, y))


# (5) entradas invalidas
NAN = np.array([[[0, 0, 2], [1, 0, 2], [np.nan, 1, 2]]], float)
INF = np.array([[[0, 0, 2], [1, 0, 2], [np.inf, 1, 2]]], float)
INV = {
    "nao_lista_ndarray": np.zeros((1, 3, 3)),
    "nao_lista_tupla": (tampa(-1, 5, 2.0),),
    "nao_lista_str": "abc",
    "item_nao_array": [[[0, 0, 2], [1, 0, 2], [1, 1, 2]]],
    "item_2d": [np.zeros((3, 3))],
    "item_n_por_3": [np.zeros((6, 3))],
    "item_n_4_3": [np.zeros((2, 4, 3))],
    "item_n_3_2": [np.zeros((2, 3, 2))],
    "item_4d": [np.zeros((1, 1, 3, 3))],
    "item_none": [None],
    "nan": [NAN],
    "inf": [INF],
    "valido_e_invalido": [tampa(-1, 5, 2.0), NAN],
    "invalido_e_valido": [np.zeros((2, 4, 3)), tampa(-1, 5, 2.0)],
}


@pytest.mark.parametrize("nome", list(INV))
def test_entrada_invalida_levanta_valueerror(nome):
    with pytest.raises(ValueError):
        run([viga()], INV[nome])


def test_oclusor_vazio_e_valido_e_sem_efeito():
    assert iguais(run([viga()], [np.zeros((0, 3, 3))])[0], base([viga()])[0])


# (6) a ordem dos oclusores nao muda o resultado
def _tres():
    return [tampa(-1, 1.5, 2.0), tampa(1.0, 3.0, 3.0), tampa(2.5, 5, 2.5)]


def test_ordem_dos_oclusores_nao_importa():
    ref = run([viga()], _tres())[0]
    for perm in itertools.permutations(_tres()):
        assert iguais(run([viga()], list(perm))[0], ref, 1e-9)


def test_ordem_dos_triangulos_dentro_do_oclusor_nao_importa():
    t = tampa(-1, 2, 2.0)
    r1 = run([viga()], [t])[0]
    r2 = run([viga()], [t[::-1].copy()])[0]
    assert iguais(r1, r2, 1e-9)


# (7) oclusor nao aparece na saida
def test_oclusor_nao_gera_linhas_nem_itens():
    cx = caixa(np.array([0.5, 0.5, 2.5]), [3.0, 1.0, 1.0])  # caixa com arestas nitidas sobre x -1..2, z 2..3
    r = run([viga(), longe()], [cx[0][cx[1]]])
    assert len(r) == 2
    p = pts(r[0])
    assert comp(r[0]) == pytest.approx(5.0, abs=TOL)  # so o resto da viga (x >= 2)
    assert p[:, 0].min() >= 2.0 - TOL and p[:, 0].max() <= 4.0 + TOL and p[:, 1].min() >= -TOL and p[:, 1].max() <= 1.0 + TOL


def test_so_oclusores_sem_pecas_visiveis_retorna_lista_por_peca():
    assert run([], [tampa(-1, 5, 2.0)]) == []
    r = run([longe()], [tampa(-1, 5, 2.0)])
    assert len(r) == 1 and iguais(r[0], base([longe()])[0])


# (8) varios oclusores sobrepostos
def test_oclusores_sobrepostos_cobrem_a_uniao():
    assert comp(run([viga()], _tres())[0]) <= TOL


def test_sem_o_terceiro_resta_o_trecho_x_maior_que_3():
    r = run([viga()], _tres()[:2])[0]
    assert comp(r) == pytest.approx(3.0, abs=TOL)  # 1 (y=0) + 1 (x=4) + 1 (y=1)
    assert pts(r)[:, 0].min() >= 3.0 - TOL


def test_sem_o_primeiro_resta_o_trecho_x_menor_que_1():
    r = run([viga()], _tres()[1:])[0]
    assert comp(r) == pytest.approx(3.0, abs=TOL)
    assert pts(r)[:, 0].max() <= 1.0 + TOL


def test_oclusor_duplicado_nao_muda_nada():
    assert iguais(run([viga()], [tampa(-1, 2, 2.0)] * 3)[0], run([viga()], [tampa(-1, 2, 2.0)])[0], 1e-9)


# (9) trabalhadores
@pytest.mark.parametrize("trab", [1, 2])
def test_funciona_com_trabalhadores(trab):
    kw = {}
    if trab == 2 and not TEM_TRAB:
        pytest.skip("parametro trabalhadores inexistente")
    if TEM_TRAB:
        kw["trabalhadores"] = trab
    ref = run([viga(), longe()], _tres()[:2])
    r = run([viga(), longe()], _tres()[:2], **kw)
    assert len(r) == 2 and iguais(r[0], ref[0], 1e-9) and iguais(r[1], ref[1], 1e-9)
    assert comp(r[0]) == pytest.approx(3.0, abs=TOL)


# MUTANTES para o lider rodar contra a implementacao (cada um deve fazer pelo menos 1 teste falhar):
#  M1 oclusores_extra ignorado (nunca entra em Tw_comb/prep).                      -> (1)(2)(8)
#  M2 oclusor tambem gera linhas de saida (arestas candidatas dele entram em cands).-> (7)
#  M3 oclusor vira peca extra no retorno (len(r) == pecas + oclusores).             -> (1)(7)
#  M4 ordem importa: so o primeiro (ou so o ultimo) oclusor e usado.                -> (6)(8)
#  M5 ignora tol_z para oclusores (oculta coplanar/ate z=1.0+0.4*tol).              -> (3)
#  M6 aceita NaN/inf sem erro (remove np.isfinite).                                 -> (5)
#  M7 aceita ndarray/tupla no lugar de list, ou nao valida shape (n,3,3).           -> (5)
#  M8 oclusor abaixo da peca oculta (compara z invertido / usa abs(dz)).            -> (3)
#  M9 ValueError so quando ha pecas visiveis (validacao tardia) ou nao valida item seguinte ao primeiro. -> (5) invalido_e_valido
#  M10 com None/[] altera caminho (ex.: np.vstack troca dtype/ordem; dedup diferente) -> (4) bit a bit
#  M11 oclusor tratado so como z-buffer (sem recorte analitico): trecho x<2 removido com erro de celula -> (2) tolerancia 1e-6
#  M12 oclusor com triangulos filtrados por _dedup_triangulos que apaga o vizinho (oclusor duplicado apaga a peca) -> (8) duplicado
#  M13 oclusor so oculta pecas de indice maior / so a primeira peca.                -> (1) (viga na posicao 0 e vizinha)
#  M14 oclusor so oculta com normal para cima (winding): nao coberto aqui.
