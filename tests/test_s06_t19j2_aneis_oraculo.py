# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j2: `aneis_de_segmentos(segs, tol=1e-6) -> (fechados, abertos)` e
`recortar_fora_dos_aneis(polilinhas, aneis, encolher=5e-4) -> list[ndarray (n,2)]`.
Contrato (cartão F0-S06-T19j2): anéis (n,2) costurados dos segmentos (k,4); externos anti-horários (área > 0), furos
horários (área < 0); pontos dentro de `tol` são o mesmo nó; cadeia que não fecha vai em `abertos`; recorte remove
os trechos dentro da região (anéis encolhidos em `encolher`, par-ímpar), corta nas interseções exatas, mantém
colinear com a borda; sem mutar a entrada; determinístico.
Suposições de formato: anel pode repetir ou não o primeiro ponto no fim (o teste normaliza); ordem dos anéis livre
(o teste ordena pela área); trechos de saída na ordem de percurso das polilinhas.
Todo valor esperado vem de conta à mão, nunca da função."""
import sys
from pathlib import Path

import numpy as np

GEOMETRIA = Path(__file__).resolve().parent.parent / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))
from obim_geometria.aneis import aneis_de_segmentos, recortar_fora_dos_aneis  # noqa: E402

TOL = 1e-9


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


RET = [(0, 0), (4, 0), (4, 2), (0, 2)]          # área 8, anti-horário
RET10 = [(0, 0), (10, 0), (10, 10), (0, 10)]    # área 100
FURO = [(4, 4), (6, 4), (6, 6), (4, 6)]         # área 4 (dado anti-horário; esperado sai horário)
L = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]  # área 3


def trechos_iguais(res, esperado):
    assert len(res) == len(esperado), (len(res), esperado)
    for r, e in zip(res, esperado):
        np.testing.assert_allclose(np.asarray(r, float), np.asarray(e, float), atol=TOL, rtol=0)


# ---------- anéis ----------
def test_retangulo_area_e_orientacao():
    f, a = aneis_de_segmentos(np.array(segs_de(RET), float))
    assert len(f) == 1 and len(a) == 0
    assert len(_abre(f[0])) == 4
    assert abs(area(f[0]) - 8.0) < TOL


def test_L_area_e_orientacao():
    f, a = aneis_de_segmentos(np.array(segs_de(L), float))
    assert len(f) == 1 and len(a) == 0
    assert len(_abre(f[0])) == 6
    assert abs(area(f[0]) - 3.0) < TOL


def test_horario_na_entrada_sai_anti_horario():
    f, _ = aneis_de_segmentos(np.array(segs_de(RET[::-1]), float))
    assert abs(area(f[0]) - 8.0) < TOL


def test_furo_sai_horario_externo_anti_horario():
    f, a = aneis_de_segmentos(np.array(segs_de(RET10) + segs_de(FURO), float))
    assert len(f) == 2 and len(a) == 0
    areas = sorted(area(r) for r in f)
    assert abs(areas[0] - (-4.0)) < TOL and abs(areas[1] - 100.0) < TOL


def test_cadeia_aberta_vai_em_abertos():
    cadeia = [(0, 0), (1, 0), (1, 1), (2, 1)]
    f, a = aneis_de_segmentos(np.array(segs_de(cadeia, fecha=False), float))
    assert len(f) == 0 and len(a) == 1
    assert len(a[0]) == 4
    # extremos da cadeia são (0,0) e (2,1), em qualquer sentido
    ext = {tuple(np.round(a[0][0], 9)), tuple(np.round(a[0][-1], 9))}
    assert ext == {(0.0, 0.0), (2.0, 1.0)}


def test_fechado_e_aberto_juntos():
    segs = segs_de(RET) + segs_de([(10, 10), (11, 10), (11, 11)], fecha=False)
    f, a = aneis_de_segmentos(np.array(segs, float))
    assert len(f) == 1 and len(a) == 1
    assert abs(area(f[0]) - 8.0) < TOL


def test_fora_de_ordem_e_invertidos():
    s = np.array(segs_de(L), float)
    mist = s[[3, 0, 5, 2, 4, 1]].copy()
    mist[[0, 2, 4]] = mist[[0, 2, 4]][:, [2, 3, 0, 1]]  # inverte 3 segmentos
    f, a = aneis_de_segmentos(mist)
    assert len(f) == 1 and len(a) == 0
    assert abs(area(f[0]) - 3.0) < TOL and len(_abre(f[0])) == 6


def test_nos_coincidentes_dentro_de_tol():
    s = np.array(segs_de(RET), float)
    s[1, :2] += 5e-7   # cada ponta desloca menos que tol=1e-6
    s[2, :2] -= 5e-7
    f, a = aneis_de_segmentos(s, tol=1e-6)
    assert len(f) == 1 and len(a) == 0
    assert abs(area(f[0]) - 8.0) < 1e-5


def test_nos_fora_de_tol_nao_fecham():
    s = np.array(segs_de(RET), float)
    s[1, :2] += 1e-3
    f, a = aneis_de_segmentos(s, tol=1e-6)
    assert len(f) == 0 and len(a) == 1


def test_aneis_deterministico_e_ponto_inicial_independe_da_ordem():
    s = np.array(segs_de(RET10) + segs_de(FURO), float)
    f1, a1 = aneis_de_segmentos(s)
    f2, a2 = aneis_de_segmentos(s)
    emb = s[[7, 2, 5, 0, 6, 3, 1, 4]]
    f3, _ = aneis_de_segmentos(emb)
    k = lambda f: sorted(f, key=area)  # noqa: E731
    for x, y, z in zip(k(f1), k(f2), k(f3)):
        np.testing.assert_array_equal(x, y)
        np.testing.assert_allclose(x, z, atol=TOL, rtol=0)  # mesmo ponto inicial e sentido


def test_aneis_nao_muta_entrada():
    s = np.array(segs_de(L), float)
    c = s.copy()
    aneis_de_segmentos(s)
    np.testing.assert_array_equal(s, c)


# ---------- recorte ----------
def anel(pts):
    return np.array(pts, float)


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
