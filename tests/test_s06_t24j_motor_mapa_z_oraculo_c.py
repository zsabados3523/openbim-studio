# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24j_motor_mapa_z_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
import threading
import time
from unittest import mock
import numpy as np
import pytest
import obim_geometria.visib_faixas as visib_faixas
import obim_geometria.visib_mapa as visib_mapa
import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _aplicar_corte,
    _arestas_candidatas,
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_mapa import _compactar_H, _unir_intervalos, _varrer_cels_triangulos
from obim_geometria.visibilidade import (
    _cull_tris,
    _dedup_triangulos,
    _limpar_malha,
    _visibilidade_hibrida,
    linhas_visiveis_multi,
)
from test_s06_t24j_motor_mapa_z_oraculo import _MAPA_Z_REAL, _filtrar_e_recortar_ref, _linhas_visiveis_multi_ref, _preparar_cena, _visibilidade_hibrida_ref  # noqa: F401
from test_s06_t24j_motor_mapa_z_oraculo_b import CENAS, _assert_equivalente, _caixa, _cena_caixas_sobrepostas_e_escondidas, _cena_casa_compacta, _cena_tres_chaves_distintas, _comprimento_total, _executar_com_timeout, _hash_resultado, _instalar_spy_mapa_z, _quad_vertical, _threads_pool_vivas  # noqa: F401



def test_equivalencia_direta_filtrar_e_recortar_vs_copia_literal():
    """Compara visib_mapa._filtrar_e_recortar diretamente com a copia literal dedup-primeiro."""
    pecas = _cena_caixas_sobrepostas_e_escondidas()[:6]
    dados = _preparar_cena(pecas)
    assert dados is not None
    _, P, Tw_comb, ativos, prep = dados
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, _ = prep
    nt_all = len(A)
    tol_z = 1e-4
    d_eps = -1e-6

    rng = np.random.default_rng(24099)
    for _, (a, b, ea, eb) in ativos:
        d = b - a
        ex0 = np.minimum(a[:, 0], b[:, 0])
        ex1 = np.maximum(a[:, 0], b[:, 0])
        ey0 = np.minimum(a[:, 1], b[:, 1])
        ey1 = np.maximum(a[:, 1], b[:, 1])
        ezmin = np.minimum(a[:, 2], b[:, 2])

        # Gera pares com duplicatas abundantes + pares fora de Z e fora de XY
        pe_base = np.repeat(np.arange(len(a), dtype=np.int64), nt_all)
        pt_base = np.tile(np.arange(nt_all, dtype=np.int64), len(a))
        dup_idx = rng.integers(0, len(pe_base), size=min(len(pe_base), 300))
        pe = np.concatenate([pe_base, pe_base[dup_idx], pe_base[dup_idx]])
        pt = np.concatenate([pt_base, pt_base[dup_idx], pt_base[dup_idx]])

        H_ref, H_prod = [], []
        _filtrar_e_recortar_ref(
            pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
            tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_ref,
        )
        visib_mapa._filtrar_e_recortar(
            pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
            tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_prod,
        )
        e_ref, lo_ref, hi_ref = _compactar_H(H_ref, limpar=True)
        e_prod, lo_prod, hi_prod = _compactar_H(H_prod, limpar=True)
        assert np.array_equal(e_prod, e_ref)
        assert np.array_equal(lo_prod, lo_ref)
        assert np.array_equal(hi_prod, hi_ref)


# ---------------------------------------------------------------------------
# (2) Mapa Z calculado 1 vez por chave (8 threads)
# ---------------------------------------------------------------------------

def test_mapa_z_calculado_uma_vez_mesma_chave_8_threads(monkeypatch):
    """Com 8 threads e varias pecas de mesma chave, _mapa_z_conservador roda exatamente 1 vez."""
    pecas = _cena_casa_compacta()
    ref = _linhas_visiveis_multi_ref(pecas)
    chamadas = _instalar_spy_mapa_z(monkeypatch, atraso=0.05)

    obtido = _executar_com_timeout(lambda: linhas_visiveis_multi(pecas, trabalhadores=8), timeout=60.0)
    _assert_equivalente(obtido, ref, contexto="mapa_z_1_vez")
    assert len(set(chamadas)) == 1, f"esperava 1 chave distinta, viu {len(set(chamadas))}"
    assert len(chamadas) == 1, f"mapa Z calculado {len(chamadas)} vezes para 1 chave (esperado 1)"


def test_mapa_z_calculado_uma_vez_por_chave_distinta_8_threads(monkeypatch):
    """Com 3 chaves distintas e 8 threads, _mapa_z_conservador roda 1 vez por chave distinta (total 3)."""
    pecas = _cena_tres_chaves_distintas()
    ref = _linhas_visiveis_multi_ref(pecas)
    chamadas = _instalar_spy_mapa_z(monkeypatch, atraso=0.04)

    obtido = _executar_com_timeout(lambda: linhas_visiveis_multi(pecas, trabalhadores=8), timeout=60.0)
    _assert_equivalente(obtido, ref, contexto="mapa_z_3_chaves")
    assert len(set(chamadas)) == 3, f"esperava 3 chaves distintas, viu {len(set(chamadas))}"
    assert len(chamadas) == 3, f"mapa Z calculado {len(chamadas)} vezes para 3 chaves (esperado 3)"


# ---------------------------------------------------------------------------
# (3) Sem deadlock (timeout 60 s, excecoes dentro do calculo)
# ---------------------------------------------------------------------------

def test_sem_deadlock_normal_8_threads_timeout_60s(monkeypatch):
    pecas = _cena_casa_compacta()
    ref = _linhas_visiveis_multi_ref(pecas)
    _instalar_spy_mapa_z(monkeypatch, atraso=0.03)

    obtido = _executar_com_timeout(lambda: linhas_visiveis_multi(pecas, trabalhadores=8), timeout=60.0)
    _assert_equivalente(obtido, ref, contexto="sem_deadlock_normal")
    assert not _threads_pool_vivas()


def test_sem_deadlock_excecao_no_mapa_z_propaga_sem_travar(monkeypatch):
    """Excecao dentro de _mapa_z_conservador nao pode deixar outras threads penduradas."""
    pecas = _cena_casa_compacta()
    ref = _linhas_visiveis_multi_ref(pecas)

    def falhar_sempre(ordem, chave):
        raise RuntimeError("falha-simulada-mapa-z")

    _instalar_spy_mapa_z(monkeypatch, atraso=0.04, ao_chamar=falhar_sempre)
    with pytest.raises(RuntimeError, match="falha-simulada-mapa-z"):
        _executar_com_timeout(lambda: linhas_visiveis_multi(pecas, trabalhadores=8), timeout=60.0)
    assert not _threads_pool_vivas()

    # Depois da excecao, chamada limpa nao herda estado corrompido
    monkeypatch.setattr(vis, "_mapa_z_conservador", _MAPA_Z_REAL)
    monkeypatch.setattr(visib_mapa, "_mapa_z_conservador", _MAPA_Z_REAL)
    obtido = _executar_com_timeout(lambda: linhas_visiveis_multi(pecas, trabalhadores=8), timeout=60.0)
    _assert_equivalente(obtido, ref, contexto="pos_excecao_mapa_z")


def test_sem_deadlock_excecao_transitoria_no_mapa_z(monkeypatch):
    """Falha apenas na 1a chamada de _mapa_z_conservador: threads propagam erro ou recalculam, nunca travam."""
    pecas = _cena_casa_compacta()

    def falhar_so_primeira(ordem, chave):
        if ordem == 1:
            raise RuntimeError("falha-transitoria-mapa-z")

    _instalar_spy_mapa_z(monkeypatch, atraso=0.04, ao_chamar=falhar_so_primeira)
    with pytest.raises(RuntimeError, match="falha-transitoria-mapa-z"):
        _executar_com_timeout(lambda: linhas_visiveis_multi(pecas, trabalhadores=8), timeout=60.0)
    assert not _threads_pool_vivas()

    # Tambem com _visibilidade_hibrida direto compartilhando um mesmo memo entre 8 threads
    dados = _preparar_cena(pecas)
    assert dados is not None
    _, P, Tw_comb, ativos, prep = dados
    refs = {
        i: _visibilidade_hibrida_ref(P, Tw_comb, *c, 1e-4, -1e-6, 1e-4, prep=prep, memo=None)
        for i, c in ativos[:8]
    }
    _instalar_spy_mapa_z(monkeypatch, atraso=0.04, ao_chamar=falhar_so_primeira)
    memo = {}

    def rodar_concorrente():
        saidas = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [
                (i, pool.submit(_visibilidade_hibrida, P, Tw_comb, *c, 1e-4, -1e-6, 1e-4, prep=prep, memo=memo))
                for i, c in ativos[:8]
            ]
            for i, fut in futs:
                try:
                    saidas.append((i, "ok", fut.result()))
                except RuntimeError as exc:
                    saidas.append((i, "err", str(exc)))
        return saidas

    saidas = _executar_com_timeout(rodar_concorrente, timeout=60.0)
    assert any(st == "err" and "falha-transitoria-mapa-z" in str(val) for _, st, val in saidas)
    for i, st, val in saidas:
        if st == "err":
            assert "falha-transitoria-mapa-z" in val
        else:
            assert _hash_resultado([list(val)]) == _hash_resultado([list(refs[i])])


# ---------------------------------------------------------------------------
# (4) Nao mutar entradas, determinismo 3 rodadas, memo reaproveitavel
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_trab", [1, 8])
def test_nao_muta_entradas(n_trab):
    pecas = _cena_casa_compacta()
    copias = [(v.copy(), t.copy()) for v, t in pecas]
    linhas_visiveis_multi(pecas, trabalhadores=n_trab)
    for (v, t), (v0, t0) in zip(pecas, copias):
        assert np.array_equal(v, v0) and v.dtype == v0.dtype
        assert np.array_equal(t, t0) and t.dtype == t0.dtype

    # Tambem com arrays somente-leitura
    ro = []
    for v, t in copias:
        vr, tr = v.copy(), t.copy()
        vr.setflags(write=False)
        tr.setflags(write=False)
        ro.append((vr, tr))
    res_ro = linhas_visiveis_multi(ro, trabalhadores=n_trab)
    assert _hash_resultado(res_ro) == _hash_resultado(_linhas_visiveis_multi_ref(pecas))


@pytest.mark.parametrize("nome_cena", ["perto_de_zero", "caixas_sobrepostas_e_escondidas", "utm_georref"])
@pytest.mark.parametrize("n_trab", [1, 8])
def test_determinismo_3_rodadas(nome_cena, n_trab):
    pecas = CENAS[nome_cena]()
    rodadas = [linhas_visiveis_multi(pecas, trabalhadores=n_trab) for _ in range(3)]
    h0 = _hash_resultado(rodadas[0])
    assert _hash_resultado(rodadas[1]) == h0
    assert _hash_resultado(rodadas[2]) == h0
    for r in rodadas[1:]:
        assert len(r) == len(rodadas[0])
        for pa, pb in zip(rodadas[0], r):
            assert len(pa) == len(pb)
            assert all(np.array_equal(x, y) for x, y in zip(pa, pb))


def test_memo_reaproveitavel_entre_chamadas_quando_passado(monkeypatch):
    """Passar o mesmo `memo` entre chamadas a `_visibilidade_hibrida` reaproveita o mapa Z sem recalcular."""
    pecas = _cena_casa_compacta()
    dados = _preparar_cena(pecas)
    assert dados is not None
    _, P, Tw_comb, ativos, prep = dados
    chamadas = _instalar_spy_mapa_z(monkeypatch)

    memo = {}
    resultados_memo = []
    for _, c in ativos[:5]:
        resultados_memo.append(
            _visibilidade_hibrida(P, Tw_comb, *c, 1e-4, -1e-6, 1e-4, prep=prep, memo=memo)
        )
    assert len(chamadas) == 1, f"esperava reaproveitar memo em 5 chamadas, mas calculou {len(chamadas)} vezes"

    # Nova chamada posterior usando o mesmo memo continua sem recalcular
    extra = _visibilidade_hibrida(P, Tw_comb, *ativos[5][1], 1e-4, -1e-6, 1e-4, prep=prep, memo=memo)
    assert len(chamadas) == 1

    # Resultados com memo sao identicos a chamadas sem memo
    for got, (_, c) in zip(resultados_memo + [extra], ativos[:6]):
        sem_memo = _visibilidade_hibrida(P, Tw_comb, *c, 1e-4, -1e-6, 1e-4, prep=prep, memo=None)
        assert _hash_resultado([list(got)]) == _hash_resultado([list(sem_memo)])


# ---------------------------------------------------------------------------
# (5) Mutantes: um teste por comportamento errado plausivel
# ---------------------------------------------------------------------------

def test_mutante_01_nao_usa_mapa_z_de_outra_chave():
    """Mutante 1: usar mapa Z de outra chave (ou vazar memo entre cenas de mesma caixa)."""
    # (a) Cena com multiplas chaves na mesma chamada: teto em [0,2]^2 + caixa escondida + paineis fora
    pecas_multi = [
        _caixa(0.0, 0.0, 4.0, 2.0, 2.0, 4.5),  # teto alto em [0, 2] x [0, 2]
        _caixa(0.4, 0.4, 0.0, 1.6, 1.6, 0.5),  # escondida sob o teto
        _quad_vertical(5.0, 0.5, 7.0, 0.5, 0.0, 1.0),  # fora da caixa do teto (chave distinta; topo+base = 4 m)
        _quad_vertical(-5.0, 1.0, -3.0, 1.0, 0.0, 1.0),  # fora no lado negativo (chave distinta; topo+base = 4 m)
    ]
    ref_multi = _linhas_visiveis_multi_ref(pecas_multi)
    obt_multi = linhas_visiveis_multi(pecas_multi, trabalhadores=8)
    _assert_equivalente(obt_multi, ref_multi, contexto="mutante_01_multi_chave")
    assert len(obt_multi[1]) == 0, "peca sob o teto deveria ficar escondida"
    assert _comprimento_total(obt_multi[2]) == pytest.approx(4.0, abs=1e-4)
    assert _comprimento_total(obt_multi[3]) == pytest.approx(4.0, abs=1e-4)

    # (b) Duas cenas sequenciais com EXATAMENTE a mesma caixa [0,2]x[0,2] (mesma chave), conteudo diferente
    cena_com_teto = [
        _caixa(0.0, 0.0, 4.0, 2.0, 2.0, 4.5),
        _caixa(0.4, 0.4, 0.0, 1.6, 1.6, 0.5),
    ]
    cena_sem_teto = [
        _caixa(0.0, 0.0, 0.0, 0.1, 0.1, 0.5),
        _caixa(1.9, 1.9, 0.0, 2.0, 2.0, 0.5),
        _caixa(0.4, 0.4, 0.0, 1.6, 1.6, 0.5),
    ]
    r1 = linhas_visiveis_multi(cena_com_teto, trabalhadores=8)
    r2 = linhas_visiveis_multi(cena_sem_teto, trabalhadores=8)
    assert len(r1[1]) == 0
    assert _comprimento_total(r2[2]) == pytest.approx(4.8, abs=1e-4)
    _assert_equivalente(r2, _linhas_visiveis_multi_ref(cena_sem_teto), contexto="mutante_01_sem_vazamento")

    # (c) Mesmo memo passado para chamadas com dominios diferentes em _visibilidade_hibrida
    dados = _preparar_cena(pecas_multi)
    assert dados is not None
    _, P, Tw_comb, ativos, prep = dados
    memo = {}
    for _, c in ativos:
        g_memo = _visibilidade_hibrida(P, Tw_comb, *c, 1e-4, -1e-6, 1e-4, prep=prep, memo=memo)
        g_ref = _visibilidade_hibrida(P, Tw_comb, *c, 1e-4, -1e-6, 1e-4, prep=prep, memo=None)
        assert _hash_resultado([list(g_memo)]) == _hash_resultado([list(g_ref)])


def test_mutante_02_filtro_antes_do_dedup_nao_perde_par():
    """Mutante 2: filtrar errado antes de _dedup_int64 (perder par inclinado, tangente na borda XY ou duplicado)."""
    # (a) Teste direto em visib_mapa._filtrar_e_recortar com casos de fronteira:
    # Triangulo T0 (z=2.0): cobre [1, 3] x [1, 3]
    # Triangulo T1 (z=0.1): baixo, nao pode ocluir arestas em z=1.0
    # Triangulo T2 (z=2.0): fora em X ([10, 12] x [1, 3])
    # Arestas:
    #   E0: horizontal em y=1.0 (borda exata ty0 == ey0 == ey1!), x de 0.0 a 4.0, z=1.0 -> parcialmente coberta em [1, 3]
    #   E1: vertical em x=3.0 (borda exata tx1 == ex0 == ex1!), y de 0.0 a 4.0, z=1.0 -> parcialmente coberta em [1, 3]
    #   E2: inclinada em Z de z=0.5 (abaixo de T0) ate z=3.5 (acima de T0): ezmin < tzmax < ezmax!
    P = np.array(
        [
            [1.0, 1.0, 2.0], [3.0, 1.0, 2.0], [3.0, 3.0, 2.0], [1.0, 3.0, 2.0],  # 0..3: T0 (2 tris)
            [1.0, 1.0, 0.1], [3.0, 1.0, 0.1], [3.0, 3.0, 0.1],  # 4..6: T1 baixo
            [10.0, 1.0, 2.0], [12.0, 1.0, 2.0], [12.0, 3.0, 2.0],  # 7..9: T2 fora XY
            [0.0, 1.0, 1.0], [4.0, 1.0, 1.0],  # 10..11: E0 na borda y=1.0
            [3.0, 0.0, 1.0], [3.0, 4.0, 1.0],  # 12..13: E1 na borda x=3.0
            [1.5, 2.0, 0.5], [2.5, 2.0, 3.5],  # 14..15: E2 inclinada (ezmin=0.5 < 2.0 < ezmax=3.5)
        ],
        dtype=np.float64,
    )
    Tw = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.int64)
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, _ = _preparar_triangulos(P, Tw)
    ea = np.array([10, 12, 14], dtype=np.int64)
    eb = np.array([11, 13, 15], dtype=np.int64)
    a, b = P[ea], P[eb]
    d = b - a
    ex0, ex1 = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    ey0, ey1 = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    ezmin = np.minimum(a[:, 2], b[:, 2])
    nt_all = len(A)

    # Mistura pares validos repetidos com pares invalidos (em Z e em XY)
    pe = np.array([0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 2], dtype=np.int64)
    pt = np.array([0, 2, 3, 0, 0, 1, 0, 0, 1, 2, 1, 0], dtype=np.int64)

    H_ref, H_prod = [], []
    _filtrar_e_recortar_ref(
        pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, 1e-4, -1e-6, H_ref,
    )
    visib_mapa._filtrar_e_recortar(
        pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, 1e-4, -1e-6, H_prod,
    )
    er, lor, hir = _compactar_H(H_ref, limpar=True)
    ep, lop, hip = _compactar_H(H_prod, limpar=True)
    assert len(er) == 3, "todos os 3 casos (borda Y, borda X e aresta inclinada) devem ser ocluidos"
    assert np.array_equal(ep, er) and np.array_equal(lop, lor) and np.array_equal(hip, hir)

    # (b) Fim-a-fim: barra inclinada passando sob cobertura (ezmin < tzmax < ezmax) + caixa tocando borda
    pecas = [
        _caixa(1.0, 1.0, 1.9, 3.0, 3.0, 2.0),  # cobertura em z=2.0
        _caixa(0.0, 1.8, 0.5, 4.0, 2.2, 2.5, incl_y=-0.4),  # barra inclinada cruzando z=2.0
        _caixa(0.0, 0.0, 0.0, 4.0, 1.0, 1.0),  # toca exatamente y=1.0 da cobertura
    ]
    ref = _linhas_visiveis_multi_ref(pecas)
    for n_trab in (1, 8):
        obt = linhas_visiveis_multi(pecas, trabalhadores=n_trab)
        _assert_equivalente(obt, ref, contexto=f"mutante_02_e2e/n={n_trab}")
