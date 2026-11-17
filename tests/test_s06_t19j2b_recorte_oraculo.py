# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j2b: `recortar_fora_dos_aneis(polilinhas, aneis, encolher=5e-4) -> list[ndarray (n,2)]`.
Contrato (cartão F0-S06-T19j2): remove os trechos dentro da região (anéis encolhidos em `encolher`, par-ímpar; furo
cresce `encolher`), corta nas interseções exatas, mantém colinear com a borda; `aneis` = lista plana (um grupo) ou lista
de grupos (união dos grupos, par-ímpar só dentro de cada grupo); aceita anéis como listas de tuplas; sem mutar a entrada.
Suposições de formato: trechos de saída na ordem de percurso das polilinhas.
Todo valor esperado vem de conta à mão, nunca da função."""
import sys
import time
from pathlib import Path

import numpy as np
import pytest

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))
from obim_geometria.recorte import recortar_fora_dos_aneis  # noqa: E402

TOL = 1e-9
RET = [(0, 0), (4, 0), (4, 2), (0, 2)]          # área 8, anti-horário
RET10 = [(0, 0), (10, 0), (10, 10), (0, 10)]    # área 100
FURO = [(4, 4), (6, 4), (6, 6), (4, 6)]         # área 4 (dado anti-horário; esperado sai horário)
L = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]  # área 3



def _abre(p):
    p = np.asarray(p, float)
    return p[:-1] if len(p) > 1 and np.allclose(p[0], p[-1], atol=1e-12) else p


def area(p):
    """Área assinada (fórmula do cadarço)."""
    p = _abre(p)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def segs_de(pts, fecha=True):
    n = len(pts) if fecha else len(pts) - 1
    return [(*pts[i], *pts[(i + 1) % len(pts)]) for i in range(n)]


def trechos_iguais(res, esperado):
    assert len(res) == len(esperado), (len(res), esperado)
    for r, e in zip(res, esperado):
        np.testing.assert_allclose(np.asarray(r, float), np.asarray(e, float), atol=TOL, rtol=0)


def anel(pts):
    return np.array(pts, float)


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # anti-horário


def test_atravessa_retangulo_dois_trechos_pontos_exatos():
    lin = [np.array([(-1, 1), (5, 1)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)], encolher=0.0),
                   [[(-1, 1), (0, 1)], [(4, 1), (5, 1)]])


def test_encolher_5e4_move_os_cortes():
    lin = [np.array([(-1, 1), (5, 1)], float)]
    esperado = [[(-1, 1), (5e-4, 1)], [(4 - 5e-4, 1), (5, 1)]]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)], encolher=5e-4), esperado)
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)]), esperado)  # padrão = 5e-4


def test_toda_dentro_vazia():
    lin = [np.array([(1, 1), (3, 1)], float)]
    assert recortar_fora_dos_aneis(lin, [anel(RET)], encolher=0.0) == []


def test_toda_fora_igual():
    lin = [np.array([(-3, 5), (8, 5)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)]), [[(-3, 5), (8, 5)]])


def test_dentro_do_furo_mantida():
    lin = [np.array([(1, 5), (9, 5)], float)]
    aneis = [anel(RET10), anel(FURO[::-1])]  # furo horário
    trechos_iguais(recortar_fora_dos_aneis(lin, aneis, encolher=0.0), [[(4, 5), (6, 5)]])


def test_colinear_com_borda_mantida():
    lin = [np.array([(-1, 0), (5, 0)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)], encolher=5e-4), [[(-1, 0), (5, 0)]])


def test_vertice_exatamente_na_borda():
    toca = [np.array([(-1, 1), (0, 1), (-1, 2)], float)]  # só encosta no vértice (0,1)
    trechos_iguais(recortar_fora_dos_aneis(toca, [anel(RET)], encolher=5e-4),
                   [[(-1, 1), (0, 1), (-1, 2)]])
    entra = [np.array([(-1, 1), (0, 1), (2, 1)], float)]  # vértice na borda e segue para dentro
    trechos_iguais(recortar_fora_dos_aneis(entra, [anel(RET)], encolher=0.0), [[(-1, 1), (0, 1)]])


def test_polilinha_varios_vertices():
    lin = [np.array([(-1, 1), (2, 1), (2, 3), (6, 3)], float)]  # entra em (0,1), sai em (2,2)
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)], encolher=0.0),
                   [[(-1, 1), (0, 1)], [(2, 2), (2, 3), (6, 3)]])


def test_varias_polilinhas_em_ordem():
    lins = [np.array([(-1, 1), (5, 1)], float), np.array([(1, 1), (3, 1)], float),
            np.array([(-1, 5), (5, 5)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lins, [anel(RET)], encolher=0.0),
                   [[(-1, 1), (0, 1)], [(4, 1), (5, 1)], [(-1, 5), (5, 5)]])


def test_recorte_nao_muta_e_e_deterministico():
    lins = [np.array([(-1, 1), (2, 1), (2, 3), (6, 3)], float)]
    aneis = [anel(RET)]
    c_l, c_a = [x.copy() for x in lins], [x.copy() for x in aneis]
    r1 = recortar_fora_dos_aneis(lins, aneis)
    r2 = recortar_fora_dos_aneis(lins, aneis)
    for x, y in zip(lins + aneis, c_l + c_a):
        np.testing.assert_array_equal(x, y)
    assert len(r1) == len(r2)
    for x, y in zip(r1, r2):
        np.testing.assert_array_equal(x, y)


def test_linha_pelos_vertices_do_anel():
    lin = [np.array([(-1, -1), (5, 5)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(rect(0, 0, 4, 4))], encolher=0.0),
                   [[(-1, -1), (0, 0)], [(4, 4), (5, 5)]])


def test_encolher_cresce_o_furo():
    aneis = [anel(RET10), anel(FURO[::-1])]
    # a 2e-4 da borda do furo (no material): dentro da borda crescida, fica; corte em x = 4 - 5e-4
    trechos_iguais(recortar_fora_dos_aneis([np.array([(1, 5), (4 - 2e-4, 5)], float)], aneis, encolher=5e-4),
                   [[(4 - 5e-4, 5), (4 - 2e-4, 5)]])
    # a 1e-3 da borda: toda dentro da região, some
    assert recortar_fora_dos_aneis([np.array([(1, 5), (4 - 1e-3, 5)], float)], aneis, encolher=5e-4) == []


def test_encolher_vertice_reentrante_do_L():
    # reta x+y = 2-2a, perpendicular ao canto reentrante (1,1), a = 2e-4 (d = 2.8e-4 do vértice): passa raspando, mantém só o miolo
    for a, esperado in ((2e-4, [[(1 - 5e-4, 1 + 1e-4), (1 + 1e-4, 1 - 5e-4)]]), (6e-4, [])):
        lin = [np.array([(1 - a - 0.4, 1 - a + 0.4), (1 - a + 0.4, 1 - a - 0.4)], float)]
        trechos_iguais(recortar_fora_dos_aneis(lin, [anel(L)], encolher=5e-4), esperado)


def test_grupos_sobrepostos_uniao_nao_par_impar():
    A, B = anel(rect(0, 0, 5, 1)), anel(rect(4, 0, 5, 5))
    lin = [np.array([(4.9, -1), (4.9, 6)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [[A], [B]], encolher=0.0),
                   [[(4.9, -1), (4.9, 0)], [(4.9, 5), (4.9, 6)]])
    plano = recortar_fora_dos_aneis(lin, [A, B], encolher=0.0)  # par-ímpar plano: sobreposição conta como fora
    assert any(t[:, 1].min() < 0.5 < t[:, 1].max() for t in plano)


def test_recorte_saida_independe_da_entrada():
    lin = np.array([(-3, 5), (8, 5)], float)
    r = recortar_fora_dos_aneis([lin], [anel(RET)])
    r[0][:] = 99.0
    np.testing.assert_array_equal(lin, [(-3, 5), (8, 5)])
    r2 = recortar_fora_dos_aneis([lin], [anel(RET)])
    lin[:] = 0.0
    np.testing.assert_allclose(r2[0], [(-3, 5), (8, 5)], atol=TOL, rtol=0)


def test_desempenho_recorte():
    ang = 2 * np.pi * np.arange(5000) / 5000
    poli = np.c_[100 * np.cos(ang), 100 * np.sin(ang)]
    rng = np.random.default_rng(0)
    lins = [rng.uniform(200, 300, (5, 2)) for _ in range(200)]  # todas longe do poligono
    t = time.perf_counter()
    r = recortar_fora_dos_aneis(lins, [poli])
    assert time.perf_counter() - t < 2.0 and len(r) == 200
    np.testing.assert_allclose(r[0], lins[0], atol=TOL, rtol=0)


def test_ilha_dentro_de_furo_dentro_de_externo_recorte():
    pts = [rect(0, 0, 10, 10), rect(2, 2, 8, 8), rect(4, 4, 6, 6)]
    aneis = [anel(pts[0]), anel(pts[1][::-1]), anel(pts[2])]  # par-ímpar: dentro = borda externa menos furo mais ilha
    trechos_iguais(recortar_fora_dos_aneis([np.array([(-1, 5), (11, 5)], float)], aneis, encolher=0.0),
                   [[(-1, 5), (0, 5)], [(2, 5), (4, 5)], [(6, 5), (8, 5)], [(10, 5), (11, 5)]])


def test_L_arco_no_vertice_reentrante():
    # y = 1-3e-4: dentro da região só se dist ao quadrante x>1,y>1 > 5e-4: (1-x)^2 > 25e-8 - 9e-8 -> x < 1-4e-4
    lin = [np.array([(0.5, 1 - 3e-4), (1.5, 1 - 3e-4)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(L)], encolher=5e-4), [[(1 - 4e-4, 1 - 3e-4), (1.5, 1 - 3e-4)]])


def test_anel_externo_horario():
    lin = [np.array([(-1, 1), (5, 1)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(rect(0, 0, 4, 2)[::-1])], encolher=5e-4),
                   [[(-1, 1), (5e-4, 1)], [(4 - 5e-4, 1), (5, 1)]])


def test_polilinha_colinear_com_vertices_extras_atravessa():
    lin = [np.array([(-1, 1), (2, 1), (4, 1), (5, 1)], float)]
    trechos_iguais(recortar_fora_dos_aneis(lin, [anel(RET)], encolher=0.0), [[(-1, 1), (0, 1)], [(4, 1), (5, 1)]])


def test_aneis_como_listas_puras_de_tuplas():
    lin = [np.array([(-1, 1), (5, 1)], float)]
    esperado = [[(-1, 1), (0, 1)], [(4, 1), (5, 1)]]
    trechos_iguais(recortar_fora_dos_aneis(lin, [rect(0, 0, 4, 2)], 0.0), esperado)      # lista plana
    trechos_iguais(recortar_fora_dos_aneis(lin, [[rect(0, 0, 4, 2)]], 0.0), esperado)    # lista de grupos


@pytest.mark.parametrize("ruim", [[(0, 0), (1, 1)], [(0, 0, 0), (1, 1, 1), (2, 2, 2)], [(0, 0), (1,), (2, 2)]])
def test_anel_invalido_levanta_valueerror(ruim):
    with pytest.raises(ValueError):
        recortar_fora_dos_aneis([np.array([(-1, 1), (5, 1)], float)], [ruim], 0.0)
