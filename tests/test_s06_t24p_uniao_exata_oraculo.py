# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24p (T3, ADR-011 C1): uniao exata de intervalos por aresta sem offset.

Contrato de `obim_geometria.visib_mapa._unir_intervalos(He, Hlo, Hhi)` e `_compactar_H(H_l, limpar)`:
- Resultado BIT A BIT igual a `_ref_unir` (Python puro, floats IEEE-754, sem offset).
- Invariancia de lote: `unir(concat(A, B)) == unir(concat(unir(A), unir(B)))` bit a bit.
- Semantica de `lo > hi`, `NaN`, `+/-inf`, vazios e 1 elemento documentada em `_ref_unir`.
- Desempenho: mediana de 3 em 500 mil intervalos <= 1,3x da implementacao atual (`_atual_unir`).

Nao editar este arquivo durante a implementacao da T24p.
"""
from __future__ import annotations

import math
import statistics
import time

import numpy as np

from obim_geometria.visib_mapa import _compactar_H, _unir_intervalos

_TOL = 1e-9


# (1) Referencia exata em Python puro (sem numpy no laco)
def _max_f(a: float, b: float) -> float:
    """Maximo IEEE-754 propagando NaN (mesma semantica de np.maximum)."""
    return float("nan") if (math.isnan(a) or math.isnan(b)) else (a if a >= b else b)


def _ref_unir(He: np.ndarray, Hlo: np.ndarray, Hhi: np.ndarray):
    """Referencia exata em Python puro para `_unir_intervalos`.

    - Vazio (`len == 0`): arrays vazios preservando `He.dtype` e `float64`.
    - Ordena estavelmente por `(He, Hlo)` com `Hlo=NaN` no fim do grupo (igual `np.lexsort`).
    - Agrupa por `He`; novo bloco se `Hlo > hi_atual + 1e-9`, senao `hi_atual = _max_f(hi_atual, Hhi)`.
    - Fecha cada bloco com `(He, Hlo_ini, _max_f(Hlo_ini, hi_atual))`.
    - `lo > hi`: para qualquer `n >= 1` (inclusive `n == 1`), `hi_final = _max_f(Hlo_ini, hi_atual)`
      garante `hi_final >= Hlo_ini` (salvo NaN); durante a varredura `hi_atual` segue `Hhi` sem clamp.
    - `NaN` e `+/-inf`: estritamente isolados por `He` (nunca vazam entre arestas); na mesma aresta,
      `NaN` propaga em `_max_f` e funde (`lo > hi + 1e-9` e False); `+inf` absorve seguintes; `-inf`
      permite novo bloco ao ver finito/`+inf`.
    """
    n = len(He)
    he_dtype = He.dtype
    if n == 0:
        return np.empty(0, dtype=he_dtype), np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    itens = [(int(He[i]), float(Hlo[i]), float(Hhi[i])) for i in range(n)]
    itens.sort(key=lambda t: (t[0], math.isnan(t[1]), 0.0 if math.isnan(t[1]) else t[1]))
    out_e: list[int] = []
    out_lo: list[float] = []
    out_hi: list[float] = []
    e_cur, lo_ini, hi_cur = itens[0]
    for e, lo, hi in itens[1:]:
        if e != e_cur or lo > hi_cur + _TOL:
            out_e.append(e_cur)
            out_lo.append(lo_ini)
            out_hi.append(_max_f(lo_ini, hi_cur))
            e_cur, lo_ini, hi_cur = e, lo, hi
        else:
            hi_cur = _max_f(hi_cur, hi)
    out_e.append(e_cur)
    out_lo.append(lo_ini)
    out_hi.append(_max_f(lo_ini, hi_cur))
    return np.array(out_e, dtype=he_dtype), np.array(out_lo, dtype=np.float64), np.array(out_hi, dtype=np.float64)


def _atual_unir(He: np.ndarray, Hlo: np.ndarray, Hhi: np.ndarray):
    """Copia literal da implementacao pre-T24p de `_unir_intervalos` (uso exclusivo no benchmark)."""
    if len(He) <= 1:
        return He, Hlo, Hhi
    o = np.lexsort((Hlo, He))
    He, Hlo, Hhi = He[o], Hlo[o], Hhi[o]
    del o
    novo = np.concatenate([[True], He[1:] != He[:-1]])
    off = np.cumsum(novo) * 2.0
    hic = np.maximum.accumulate(Hhi + off)
    prev_hi = np.where(novo, -1.0, np.concatenate([[0.0], hic[:-1]]) - off)
    ini = novo | (Hlo > prev_hi + 1e-9)
    fim = np.concatenate([ini[1:], [True]])
    return He[ini], Hlo[ini], np.maximum(Hlo[ini], (hic - off)[fim])


def _assert_bit_a_bit(obt, ref, *, permitir_nan: bool = False, ctx: str = ""):
    """Verifica igualdade bit a bit (view uint64 em float64) e dtypes."""
    oe, olo, ohi = obt
    re, rlo, rhi = ref
    p = f"[{ctx}] " if ctx else ""
    assert oe.dtype == re.dtype, f"{p}dtype He: {oe.dtype} != {re.dtype}"
    assert olo.dtype == np.float64 and ohi.dtype == np.float64, f"{p}dtype float esperado float64"
    assert len(oe) == len(re), f"{p}contagem difere: obt={len(oe)} ref={len(re)}"
    assert np.array_equal(oe, re), f"{p}He difere"
    for nome, a, b in (("Hlo", olo, rlo), ("Hhi", ohi, rhi)):
        if not permitir_nan:
            assert np.array_equal(a.view(np.uint64), b.view(np.uint64)), (
                f"{p}{nome} difere bit a bit (max_abs={np.max(np.abs(a - b)) if len(a) else 0.0:.3e})"
            )
        else:
            ma, mb = np.isnan(a), np.isnan(b)
            assert np.array_equal(ma, mb), f"{p}{nome} posicoes NaN diferem"
            assert np.array_equal(a[~ma].view(np.uint64), b[~mb].view(np.uint64)), f"{p}{nome} nao-NaN difere"


def _concat(*partes):
    return tuple(np.concatenate(xs) for xs in zip(*partes))


def _gerar_caso(rng: np.random.Generator, n: int, n_arestas: int, dtype_e):
    he = rng.integers(0, n_arestas, size=n, dtype=dtype_e)
    lo = rng.random(n, dtype=np.float64)
    hi = np.minimum(1.0, lo + rng.random(n, dtype=np.float64) * 0.25)
    if n >= 6:
        lo[0], hi[0], lo[1], hi[1] = 0.0, 0.0, 1.0, 1.0
        he[2] = he[3] = he[4] = he[0]
        lo[2], hi[2] = 0.2, 0.35
        lo[3], hi[3] = hi[2] + _TOL, 0.5
        lo[4], hi[4] = np.nextafter(hi[3] + _TOL, 1.0), 0.8
        he[5], lo[5], hi[5] = he[2], lo[2], hi[2]  # duplicata exata
    perm = rng.permutation(n)
    return he[perm], lo[perm], hi[perm]


# (2) Equivalencia bit a bit contra a referencia
def test_arrays_vazios_e_um_elemento():
    for dtype_e in (np.int32, np.int64):
        vazio = (np.zeros(0, dtype=dtype_e), np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64))
        _assert_bit_a_bit(_unir_intervalos(*vazio), _ref_unir(*vazio), ctx=f"vazio/{dtype_e.__name__}")
        for lo_v, hi_v in ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.1, 0.3), (0.25, 0.25)):
            um = (np.array([7], dtype=dtype_e), np.array([lo_v]), np.array([hi_v]))
            _assert_bit_a_bit(_unir_intervalos(*um), _ref_unir(*um), ctx=f"um/{dtype_e.__name__}/{lo_v}/{hi_v}")


def test_casos_diadicos_bordas_dtypes_e_duplicatas():
    casos = [
        ("int32_embaralhado", np.array([30, 10, 30, 10, 10, 20], np.int32),
         np.array([0.5, 0.5, 0.0, 0.0, 0.0, 0.25]), np.array([1.0, 0.75, 0.5, 0.5, 0.5, 0.75])),
        ("int64_grandes", np.array([10**12 + 2, 10**12, 10**12, -5, -5], np.int64),
         np.array([0.0, 0.25, 0.0, 0.0, 0.5]), np.array([1.0, 0.5, 0.75, 0.5, 1.0])),
        ("iguais_e_extremos", np.array([0, 0, 0, 0], np.int64),
         np.array([1.0, 0.0, 0.5, 0.0]), np.array([1.0, 0.0, 0.5, 0.0])),
        ("fronteira_1e9_diadica", np.array([0, 0, 0], np.int64),
         np.array([0.0, 0.5 + _TOL, np.nextafter(0.75 + _TOL, 1.0)]), np.array([0.5, 0.75, 1.0])),
    ]
    for nome, he, lo, hi in casos:
        _assert_bit_a_bit(_unir_intervalos(he, lo, hi), _ref_unir(he, lo, hi), ctx=nome)


def test_equivalencia_bit_a_bit_milhares_de_casos():
    """2.000 casos aleatorios (semente fixa): poucos/muitos intervalos, bordas, duplicatas e dtypes."""
    rng = np.random.default_rng(20261121)
    for k in range(2000):
        dtype_e = np.int32 if (k % 3 == 0) else np.int64
        if k < 1200:
            n, n_arestas = int(rng.integers(2, 20)), int(rng.integers(1, 15))
        elif k < 1900:
            n, n_arestas = int(rng.integers(20, 120)), int(rng.integers(1, 35))
        else:
            n, n_arestas = int(rng.integers(120, 400)), int(rng.integers(1, 100))
        he, lo, hi = _gerar_caso(rng, n, n_arestas, dtype_e)
        _assert_bit_a_bit(_unir_intervalos(he, lo, hi), _ref_unir(he, lo, hi), ctx=f"caso_{k}")


def test_equivalencia_bit_a_bit_milhoes_de_grupos_offset_grande():
    """He com 2 milhoes de grupos distintos (off ~ 4e6) + 100k elementos contra _ref_unir completo."""
    rng = np.random.default_rng(20261122)
    m = 2_000_000
    pre = (np.arange(m, dtype=np.int64), np.zeros(m, dtype=np.float64), np.full(m, 0.5, dtype=np.float64))
    he_f, lo_f, hi_f = _gerar_caso(rng, 2000, 200, np.int64)
    fim = (he_f + m, lo_f, hi_f)
    obt = _unir_intervalos(*_concat(pre, fim))
    _assert_bit_a_bit(obt, _concat(pre, _ref_unir(*fim)), ctx="2M_grupos")

    he_m, lo_m, hi_m = _gerar_caso(rng, 100_000, 80_000, np.int64)
    _assert_bit_a_bit(_unir_intervalos(he_m, lo_m, hi_m), _ref_unir(he_m, lo_m, hi_m), ctx="100k_completo")


def test_lo_maior_que_hi_semantica_referencia():
    """Semantica para `lo > hi`: `hi_final = max(Hlo_ini, hi_atual)` para qualquer n >= 1."""
    casos = [
        ("len1_lo_gt_hi", np.array([5], np.int64), np.array([0.8]), np.array([0.2])),
        ("len2_separados", np.array([0, 0], np.int64), np.array([0.6, 0.4]), np.array([0.3, 0.1])),
        ("len2_mesmo_lo", np.array([0, 0], np.int64), np.array([0.5, 0.5]), np.array([0.1, 0.2])),
        ("aninhado_lo_gt_hi", np.array([0, 0, 0], np.int64), np.array([0.2, 0.5, 0.55]), np.array([0.8, 0.1, 0.6])),
        ("multi_arestas", np.array([2, 1, 1, 2], np.int32), np.array([0.7, 0.9, 0.3, 0.1]), np.array([0.2, 0.1, 0.4, 0.05])),
    ]
    for nome, he, lo, hi in casos:
        obt = _unir_intervalos(he, lo, hi)
        _assert_bit_a_bit(obt, _ref_unir(he, lo, hi), ctx=nome)
        assert np.all(obt[2] >= obt[1]), f"{nome}: hi_final menor que Hlo"


def test_nan_e_inf_semantica_referencia():
    """NaN e +/-inf seguem exatamente `_ref_unir` e nunca vazam entre arestas distintas."""
    casos = [
        ("nan_hhi_1grp", np.array([0, 0, 0], np.int64), np.array([0.1, 0.3, 0.8]), np.array([np.nan, 0.5, 0.9])),
        ("nan_hhi_isolado", np.array([0, 1, 1, 2], np.int64), np.array([0.1, 0.2, 0.3, 0.4]), np.array([np.nan, 0.35, 0.7, 0.6])),
        ("nan_hlo_isolado", np.array([0, 0, 1], np.int64), np.array([np.nan, 0.2, 0.1]), np.array([0.4, 0.5, 0.3])),
        ("nan_so_hlo", np.array([0, 0, 1], np.int64), np.array([np.nan, np.nan, 0.2]), np.array([0.3, 0.5, 0.8])),
        ("pos_inf_isolado", np.array([0, 0, 1, 1], np.int64), np.array([0.1, 0.9, 0.2, 0.6]), np.array([np.inf, 0.95, 0.3, 0.7])),
        ("neg_inf_isolado", np.array([0, 0, 1, 1], np.int64), np.array([-np.inf, 0.2, 0.1, 0.5]), np.array([-np.inf, 0.5, 0.3, 0.8])),
        ("inf_nan_misto", np.array([0, 0, 1, 1, 2, 2], np.int64),
         np.array([-np.inf, np.inf, 0.1, 0.2, 0.3, 0.9]), np.array([0.5, np.inf, np.nan, 0.4, 0.6, 1.0])),
    ]
    for nome, he, lo, hi in casos:
        _assert_bit_a_bit(_unir_intervalos(he, lo, hi), _ref_unir(he, lo, hi), permitir_nan=True, ctx=nome)


# (3) Invariancia de lote
def test_invariancia_lote_muitos_casos_aleatorios():
    """unir(concat(A, B)) == unir(concat(unir(A), unir(B))) bit a bit em 200 casos (2 e 3 lotes)."""
    rng = np.random.default_rng(20261123)
    for k in range(200):
        n = int(rng.integers(10, 250))
        he, lo, hi = _gerar_caso(rng, n, int(rng.integers(1, 60)), np.int64)
        c = int(rng.integers(1, n))
        direto = _unir_intervalos(he, lo, hi)
        em_2 = _unir_intervalos(*_concat(_unir_intervalos(he[:c], lo[:c], hi[:c]), _unir_intervalos(he[c:], lo[c:], hi[c:])))
        em_3 = _unir_intervalos(*_concat(*(_unir_intervalos(he[r::3], lo[r::3], hi[r::3]) for r in range(3))))
        _assert_bit_a_bit(direto, _ref_unir(he, lo, hi), ctx=f"inv_ref_{k}")
        _assert_bit_a_bit(em_2, direto, ctx=f"inv_2lotes_{k}")
        _assert_bit_a_bit(em_3, direto, ctx=f"inv_3lotes_{k}")


def test_invariancia_lote_offset_grande_ate_2e6_grupos():
    """A tem 2e6 grupos (off=4e6) e B tem pares perto da fronteira 1e-9: falha hoje em bits e contagem."""
    m = 2_000_000
    A = (np.arange(m, dtype=np.int64), np.zeros(m, dtype=np.float64), np.full(m, 0.5, dtype=np.float64))
    rng = np.random.default_rng(20261124)
    be, blo, bhi = [], [], []
    for j in range(400):
        e, base = m + j, float(rng.uniform(0.05, 0.85))
        be.extend([e, e, e])
        blo.extend([base - 0.02, base + 1.2e-9, base + 0.01 + 0.8e-9])
        bhi.extend([base, base + 0.01, base + 0.03])
    B = (np.array(be, dtype=np.int64), np.array(blo, dtype=np.float64), np.array(bhi, dtype=np.float64))
    AB = _concat(A, B)
    assert len(AB[0]) <= 3_000_000

    direto = _unir_intervalos(*AB)
    uA, uB = _unir_intervalos(*A), _unir_intervalos(*B)
    em_lotes = _unir_intervalos(*_concat(uA, uB))
    ref_B = _ref_unir(*B)
    _assert_bit_a_bit(uB, ref_B, ctx="uB_vs_ref")
    _assert_bit_a_bit((direto[0][m:], direto[1][m:], direto[2][m:]), ref_B, ctx="direto_cauda_vs_ref")
    _assert_bit_a_bit(direto, em_lotes, ctx="direto_vs_em_lotes_2e6")


# (4) _compactar_H(H_l, limpar)
def test_compactar_H_contrato_basico_e_limpar():
    H_vazio: list = []
    rv = _compactar_H(H_vazio, limpar=False)
    assert H_vazio == [] and [len(x) for x in rv] == [0, 0, 0]
    assert rv[0].dtype == np.int64 and rv[1].dtype == np.float64 and rv[2].dtype == np.float64

    lote = (np.array([1, 1, 0], np.int64), np.array([0.5, 0.0, 0.25]), np.array([0.75, 0.5, 0.75]))
    ref = _ref_unir(*lote)
    H1, H2 = [lote], [lote]
    r1, r2 = _compactar_H(H1, limpar=False), _compactar_H(H2, limpar=True)
    assert len(H1) == 1 and H2 == []
    _assert_bit_a_bit(r1, ref, ctx="limpar_false")
    _assert_bit_a_bit(H1[0], ref, ctx="H_mantido")
    _assert_bit_a_bit(r2, ref, ctx="limpar_true")


def test_compactar_H_igual_referencia_e_ordem_fatiamento():
    """Fatiamento de H_l em tamanhos/ordens diferentes (com/sem compactacao intermediaria) da mesmos bits."""
    rng = np.random.default_rng(20261125)
    for k in range(40):
        n = int(rng.integers(30, 400))
        he, lo, hi = _gerar_caso(rng, n, int(rng.integers(2, 80)), np.int64)
        ref = _ref_unir(he, lo, hi)

        c5 = np.linspace(0, n, 6, dtype=int)
        f5 = [(he[a:b], lo[a:b], hi[a:b]) for a, b in zip(c5[:-1], c5[1:]) if b > a]
        H_dir = list(f5)
        _assert_bit_a_bit(_compactar_H(H_dir, limpar=True), ref, ctx=f"H_dir_{k}")
        assert H_dir == []

        H_rev: list = []
        for idx, f in enumerate(reversed(f5)):
            H_rev.append(_unir_intervalos(*f))
            if idx == len(f5) // 2:
                _compactar_H(H_rev, limpar=False)
        _assert_bit_a_bit(_compactar_H(H_rev, limpar=True), ref, ctx=f"H_rev_{k}")

        c17 = np.linspace(0, n, 18, dtype=int)
        f17 = [(he[a:b], lo[a:b], hi[a:b]) for a, b in zip(c17[:-1], c17[1:]) if b > a]
        H_emb = [f17[i] for i in rng.permutation(len(f17))]
        _assert_bit_a_bit(_compactar_H(H_emb, limpar=False), ref, ctx=f"H_emb_{k}")
        assert len(H_emb) == 1


# (5) Desempenho relativo (500 mil intervalos, mediana de 3, mesmo processo)
def test_desempenho_relativo_500k_intervalos():
    """Nova implementacao <= 1,3x o tempo da atual em 500 mil intervalos (mediana de 3)."""
    rng = np.random.default_rng(20261126)
    n = 500_000
    he = rng.integers(0, 100_000, size=n, dtype=np.int64)
    lo = rng.random(n, dtype=np.float64)
    hi = np.minimum(1.0, lo + rng.random(n, dtype=np.float64) * 0.2)

    _atual_unir(he, lo, hi)
    _unir_intervalos(he, lo, hi)
    t_at, t_nv = [], []
    for _ in range(3):
        t0 = time.perf_counter()
        _atual_unir(he, lo, hi)
        t_at.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _unir_intervalos(he, lo, hi)
        t_nv.append(time.perf_counter() - t0)
    med_at, med_nv = statistics.median(t_at), statistics.median(t_nv)
    assert med_nv <= 1.3 * med_at, f"regressao 500k: novo={med_nv:.4f}s atual={med_at:.4f}s ({med_nv / med_at:.2f}x)"


# (6) Entradas nao mutadas e determinismo
def test_entradas_nao_mutadas_e_somente_leitura():
    rng = np.random.default_rng(20261127)
    for n in (0, 1, 50, 5000):
        he = rng.integers(0, max(1, n // 4), size=n, dtype=np.int64)
        lo = rng.random(n, dtype=np.float64)
        hi = np.minimum(1.0, lo + rng.random(n, dtype=np.float64) * 0.2)
        he0, lo0, hi0 = he.copy(), lo.copy(), hi.copy()
        _unir_intervalos(he, lo, hi)
        assert np.array_equal(he, he0)
        assert np.array_equal(lo.view(np.uint64), lo0.view(np.uint64))
        assert np.array_equal(hi.view(np.uint64), hi0.view(np.uint64))

        ro = tuple(a.copy() for a in (he0, lo0, hi0))
        for a in ro:
            a.setflags(write=False)
        _unir_intervalos(*ro)
        _compactar_H([ro], limpar=True)


def test_determinismo():
    rng = np.random.default_rng(20261128)
    he, lo, hi = _gerar_caso(rng, 2000, 300, np.int64)
    base = _unir_intervalos(he, lo, hi)
    for r in range(4):
        _assert_bit_a_bit(_unir_intervalos(he, lo, hi), base, ctx=f"det_unir_{r}")
    lotes = [(he[:700], lo[:700], hi[:700]), (he[700:], lo[700:], hi[700:])]
    base_c = _compactar_H(list(lotes), limpar=True)
    for r in range(4):
        _assert_bit_a_bit(_compactar_H(list(lotes), limpar=True), base_c, ctx=f"det_compactar_{r}")


# (7) Mutantes: um teste dedicado por erro plausivel
def test_mutante_01_maior_estrito_vs_maior_ou_igual():
    """Mata trocar `Hlo > prev_hi + 1e-9` por `>=`: distancia exata 1e-9 funde, +1 ULP separa."""
    he, hi_eq = np.array([0, 0], np.int64), np.array([0.5, 0.75])
    lo_eq = np.array([0.0, 0.5 + _TOL])
    _assert_bit_a_bit(_unir_intervalos(he, lo_eq, hi_eq), (np.array([0], np.int64), np.array([0.0]), np.array([0.75])), ctx="m01_eq")
    lo_gt = np.array([0.0, np.nextafter(0.5 + _TOL, 1.0)])
    _assert_bit_a_bit(_unir_intervalos(he, lo_gt, hi_eq), (he, lo_gt, hi_eq), ctx="m01_gt")


def test_mutante_02_tolerancia_errada():
    """Mata tolerancia diferente de 1e-9 (menor como 0/1e-10 ou maior como 2e-9/1e-8)."""
    he = np.array([0, 0], np.int64)
    for gap in (0.0, 5e-10, 9.99e-10):
        assert len(_unir_intervalos(he, np.array([0.0, 0.5 + gap]), np.array([0.5, 0.75]))[0]) == 1
    for gap in (1.01e-9, 5e-9, 1e-6):
        assert len(_unir_intervalos(he, np.array([0.0, 0.5 + gap]), np.array([0.5, 0.75]))[0]) == 2


def test_mutante_03_nao_perde_ultimo_bloco():
    """Mata erro off-by-one que descarta o ultimo bloco ou a ultima aresta."""
    he = np.array([0, 0, 1, 2, 2, 2], np.int64)
    lo = np.array([0.0, 0.5, 0.25, 0.0, 0.125, 0.75])
    hi = np.array([0.25, 0.75, 0.5, 0.25, 0.5, 1.0])
    esp = (np.array([0, 0, 1, 2, 2], np.int64), np.array([0.0, 0.5, 0.25, 0.0, 0.75]), np.array([0.25, 0.75, 0.5, 0.5, 1.0]))
    _assert_bit_a_bit(_unir_intervalos(he, lo, hi), esp, ctx="m03_ultimo")


def test_mutante_04_funde_intervalo_aninhado():
    """Mata comparar com Hhi[i-1] em vez do maximo acumulado do grupo."""
    he = np.array([0, 0, 0], np.int64)
    _assert_bit_a_bit(_unir_intervalos(he, np.array([0.0, 0.125, 0.5]), np.array([1.0, 0.25, 0.625])),
                      (np.array([0], np.int64), np.array([0.0]), np.array([1.0])), ctx="m04_aninhado")
    _assert_bit_a_bit(_unir_intervalos(he, np.array([0.0, 0.125, 0.5]), np.array([0.75, 0.25, 1.0])),
                      (np.array([0], np.int64), np.array([0.0]), np.array([1.0])), ctx="m04_extensao")


def test_mutante_05_nao_mistura_arestas_diferentes():
    """Mata esquecer fronteira `He[1:] != He[:-1]` e fundir arestas distintas."""
    he, lo, hi = np.array([0, 1, 2, 3], np.int64), np.array([0.0, 0.25, 0.5, 0.5]), np.array([1.0, 0.5, 0.75, 1.0])
    _assert_bit_a_bit(_unir_intervalos(he, lo, hi), (he, lo, hi), ctx="m05_arestas")


def test_mutante_06_hi_final_nunca_menor_que_hlo():
    """Mata omitir `max(Hlo_ini, hi_atual)` quando `lo > hi`."""
    he, lo, hi = np.array([0, 0, 1], np.int64), np.array([0.5, 0.75, 0.5]), np.array([0.25, 0.5, 0.25])
    _assert_bit_a_bit(_unir_intervalos(he, lo, hi), (he, lo, lo), ctx="m06_hi_ge_lo")
