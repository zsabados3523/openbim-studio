# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T22c (T3): paralelizar por PEÇA o laço final de `linhas_visiveis_multi` com threads NÃO muda o resultado.
API esperada: `linhas_visiveis_multi(pecas, *, angulo_graus, tol_z, min_len, trabalhadores: int | None = None)`.
  1 = sequencial (sem pool); N>=2 = pool de N threads (max_workers == N); None = automático: variável OBIM_VISIB_THREADS
  (inteiro >= 1) se válida, senão min(4, os.cpu_count()) SÓ com >= 8 peças com candidatas e >= 20000 triângulos no total
  (se o resultado for 1, sem pool). Inválido (0, negativo, não inteiro, bool) = ValueError.
Decisão: valor inválido na VARIÁVEL DE AMBIENTE é ignorado (cai no automático), nunca levanta erro.
Contagem de pools: o teste troca `concurrent.futures.ThreadPoolExecutor` (e `visibilidade.ThreadPoolExecutor`, se importado por
nome) por uma subclasse que registra criação, max_workers e se foi fechada; o motor deve usar esse nome (ThreadPoolExecutor).
Dourado e cenas: reaproveitados do oráculo T22a (não editar). Equivalência por peça: mesma contagem de polilinhas/pontos,
pontas a 1e-9 m (ordem canônica); determinismo e N>=2 vs 1 também exigem igualdade bit a bit na ordem de saída."""
from __future__ import annotations

import concurrent.futures
import os
import threading

import numpy as np
import pytest

import obim_geometria.visibilidade as vis
from obim_geometria.visibilidade import linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import (TOL, _canon, _confere, _dificil, caixa, cilindro, gold,  # noqa: F401
                                                             terreno, todas)

CENAS = ["a00", "a05", "a17", "a33", "d0", "d1", "degenerada", "bordas", "tol_celula", "matar_m5_0", "georref", "grande"]
_cache: dict = {}


def _r1(nome):
    if nome not in _cache:
        _cache[nome] = linhas_visiveis_multi(todas()[nome](), trabalhadores=1)
    return _cache[nome]


def _iguais(a, b, exato=False):
    assert len(a) == len(b)
    for i, (x, y) in enumerate(zip(a, b)):
        if exato:
            assert len(x) == len(y) and all(np.array_equal(p, q) for p, q in zip(x, y)), f"peca {i}: nao bit a bit"
            continue
        x, y = _canon(x), _canon(y)
        assert [len(p) for p in x] == [len(p) for p in y], f"peca {i}: contagem/pontos"
        if x:
            assert np.abs(np.concatenate(x) - np.concatenate(y)).max() <= TOL, f"peca {i}: pontas"


class _Pool(concurrent.futures.ThreadPoolExecutor):
    criados: list = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        _Pool.criados.append(self)


@pytest.fixture
def pools(monkeypatch):
    _Pool.criados = []
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", _Pool)
    monkeypatch.setattr(vis, "ThreadPoolExecutor", _Pool, raising=False)
    monkeypatch.delenv("OBIM_VISIB_THREADS", raising=False)
    return _Pool.criados


def _stub(monkeypatch):
    """Troca o cálculo por peça por um stub barato: só o roteamento/contagem de pools é testado."""
    monkeypatch.setattr(vis, "_visibilidade_hibrida", lambda *a, **k: [np.zeros((2, 2))])


def _cena_auto(n_pecas, n_tri_terreno):
    """n_pecas peças (1 terreno + caixas) com candidatas; o terreno de ny linhas dá o total de triângulos."""
    return [terreno(n_tri_terreno // 200, 100, 0.2, 0.15, -1.0)] + [caixa(np.array([3.0 * i, 3.0, 0.5]), [1, 1, 1]) for i in range(n_pecas - 1)]


# (1) equivalência
@pytest.mark.parametrize("nome", CENAS)
def test_n1_igual_ao_dourado(nome, gold):  # noqa: F811
    _confere(nome, _r1(nome), gold)


@pytest.mark.parametrize("n,nome", [(n, c) for c in CENAS for n in (2, 4, 8) if c != "grande" or n == 4])  # grande: só N=4 (custo)
def test_n_threads_igual_a_sequencial(nome, n):
    r = linhas_visiveis_multi(todas()[nome](), trabalhadores=n)
    _iguais(r, _r1(nome))
    _iguais(r, _r1(nome), exato=True)


def test_mais_threads_que_pecas():
    pecas = todas()["a05"]()[:2]
    _iguais(linhas_visiveis_multi(pecas, trabalhadores=8), linhas_visiveis_multi(pecas, trabalhadores=1), exato=True)
    assert linhas_visiveis_multi([], trabalhadores=4) == []


# (2) determinismo e reentrância
@pytest.mark.parametrize("nome", ["a17", "d1"])
def test_determinismo_3_rodadas(nome):
    rs = [linhas_visiveis_multi(todas()[nome](), trabalhadores=4) for _ in range(3)]
    _iguais(rs[0], rs[1], exato=True)
    _iguais(rs[1], rs[2], exato=True)
    _iguais(rs[0], _r1(nome), exato=True)


def test_chamadas_concorrentes_do_chamador():
    nomes = ["a17", "d1", "bordas", "a05"]
    out, erros = {}, []

    def roda(i, nome, n):
        try:
            out[i] = linhas_visiveis_multi(todas()[nome](), trabalhadores=n)
        except BaseException as e:  # noqa: BLE001
            erros.append(e)

    ts = [threading.Thread(target=roda, args=(i, nm, n)) for i, (nm, n) in enumerate(zip(nomes * 2, [4, 1, 3, 2, 4, 4, 2, 3]))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not erros, erros
    for i, nm in enumerate(nomes * 2):
        _iguais(out[i], _r1(nm), exato=True)


# (3) automático
def test_auto_cena_pequena_nao_cria_pool(pools, monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    r = linhas_visiveis_multi(todas()["a05"]())  # poucas peças e poucos triângulos
    _iguais(r, _r1("a05"), exato=True)
    _stub(monkeypatch)
    for pecas in (_cena_auto(7, 21000), _cena_auto(12, 19000), _cena_auto(7, 19000)):  # <8 peças ou <20000 triângulos
        linhas_visiveis_multi(pecas)
    assert pools == []


def test_auto_cena_grande_cria_pool(pools, monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    linhas_visiveis_multi(_cena_auto(8, 21000))
    assert [p._max_workers for p in pools] == [4]
    pools.clear()
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    linhas_visiveis_multi(_cena_auto(10, 21000))
    assert [p._max_workers for p in pools] == [2]
    pools.clear()
    monkeypatch.setattr(os, "cpu_count", lambda: 1)  # 1 CPU: sem pool
    linhas_visiveis_multi(_cena_auto(10, 21000))
    assert pools == []


def test_env_forca_sequencial_e_n(pools, monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    monkeypatch.setenv("OBIM_VISIB_THREADS", "1")
    linhas_visiveis_multi(_cena_auto(10, 21000))
    assert pools == []
    monkeypatch.setenv("OBIM_VISIB_THREADS", "3")
    linhas_visiveis_multi(_cena_auto(10, 21000))
    assert [p._max_workers for p in pools] == [3]


def test_param_explicito_vence_env(pools, monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setenv("OBIM_VISIB_THREADS", "3")
    linhas_visiveis_multi(_cena_auto(10, 21000), trabalhadores=1)
    assert pools == []
    linhas_visiveis_multi(_cena_auto(10, 21000), trabalhadores=2)
    assert [p._max_workers for p in pools] == [2]


@pytest.mark.parametrize("valor", ["abc", "0", "-2", "", "1.5", " "])
def test_env_invalida_e_ignorada(valor, pools, monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    monkeypatch.setenv("OBIM_VISIB_THREADS", valor)
    linhas_visiveis_multi(_cena_auto(3, 2000))  # pequena: automático = sequencial, sem erro
    assert pools == []
    linhas_visiveis_multi(_cena_auto(10, 21000))  # grande: automático = 4
    assert [p._max_workers for p in pools] == [4]


# (4) validação
@pytest.mark.parametrize("n", [0, -1, -4, 1.5, 2.0, "4", True, False, [2]])
def test_trabalhadores_invalido(n):
    with pytest.raises(ValueError):
        linhas_visiveis_multi(todas()["a05"](), trabalhadores=n)
    with pytest.raises(ValueError):
        linhas_visiveis_multi([], trabalhadores=n)  # valida antes do atalho de entrada vazia


def test_trabalhadores_none_ou_inteiro_aceito():
    for n in (None, 1, 2, np.int64(3)):
        linhas_visiveis_multi(todas()["a05"]()[:3], trabalhadores=n)


# (5) exceção
@pytest.mark.parametrize("n,k", [(1, 3), (4, 1), (4, 3), (4, 7), (8, 2)])
def test_excecao_numa_peca_propaga_sem_threads_pendentes(n, k, pools, monkeypatch):
    real, cont, lock = vis._visibilidade_hibrida, [0], threading.Lock()

    def falha(*a, **kw):
        with lock:
            cont[0] += 1
            minha = cont[0]
        if minha == k:
            raise ArithmeticError("falha-na-peca")
        return real(*a, **kw)

    pecas = todas()["a17"]()
    monkeypatch.setattr(vis, "_visibilidade_hibrida", falha)
    with pytest.raises(ArithmeticError, match="falha-na-peca"):
        linhas_visiveis_multi(pecas, trabalhadores=n)
    assert all(p._shutdown for p in pools)  # pool fechado
    assert not [t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor") and t.is_alive()]
    monkeypatch.setattr(vis, "_visibilidade_hibrida", real)
    _iguais(linhas_visiveis_multi(pecas, trabalhadores=n), _r1("a17"), exato=True)  # sem estado sujo depois


def test_pool_fechado_no_caminho_normal(pools):
    linhas_visiveis_multi(todas()["a17"](), trabalhadores=4)
    assert len(pools) == 1 and pools[0]._max_workers == 4 and pools[0]._shutdown
    assert not [t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor") and t.is_alive()]


def test_n1_nao_cria_pool(pools):
    linhas_visiveis_multi(todas()["a17"](), trabalhadores=1)
    assert pools == []


# (6) o memo não vaza entre chamadas (nem com cenas diferentes em sequência) e peças repetidas não o corrompem
def test_cenas_diferentes_em_sequencia_sem_memo_residual():
    for nome in ("d0", "a05", "d0", "bordas", "a05"):
        _iguais(linhas_visiveis_multi(todas()[nome](), trabalhadores=4), _r1(nome), exato=True)


def test_pecas_duplicadas_e_escondidas_em_paralelo():
    p = _dificil(3)  # tem duplicata exata, peça isolada e peça escondida
    _iguais(linhas_visiveis_multi(p, trabalhadores=4), linhas_visiveis_multi(p, trabalhadores=1), exato=True)
    c = cilindro(np.array([0.0, 0, 0]), 1.0, 1.0, 16)
    _iguais(linhas_visiveis_multi([c] * 6, trabalhadores=3), linhas_visiveis_multi([c] * 6, trabalhadores=1), exato=True)


def _mesmo_dominio(h):
    """Mesma extensão (mesma chave de memo) com conteúdo diferente: o memo de uma chamada não pode vazar para a outra."""
    return [caixa(np.array([2.0, 2, 0]), [4, 4, 0.2]), caixa(np.array([2.0, 2, h]), [1.2, 1.2, 0.4]), caixa(np.array([2.0, 2, 0.5]), [0.4, 0.4, 0.5]),
            caixa(np.array([0.8, 3, 0.5]), [0.4, 0.4, 1.0])]


def test_memo_nao_vaza_entre_chamadas_de_mesmo_dominio():
    esperado = {6.0: [4, 4, 0, 4], 2.0: [4, 4, 0, 4]}  # polilinhas por peça (motor sequencial): a peça 2 fica sob o telhado nos dois casos
    for h in (6.0, 2.0, 6.0, 2.0):
        r = linhas_visiveis_multi(_mesmo_dominio(h), trabalhadores=4)
        assert [len(x) for x in r] == esperado[h], h
        _iguais(r, linhas_visiveis_multi(_mesmo_dominio(h), trabalhadores=1), exato=True)


@pytest.mark.parametrize("n", [2, 4])
def test_memo_compartilhado_entre_pecas(n, monkeypatch):
    real, cont, lock = vis._mapa_z_conservador, [0], threading.Lock()

    def conta(*a, **k):
        with lock:
            cont[0] += 1
        return real(*a, **k)

    monkeypatch.setattr(vis, "_mapa_z_conservador", conta)
    linhas_visiveis_multi(todas()["a17"](), trabalhadores=n)  # >> n peças, uma só chave: no máx. 1 cálculo por thread
    assert 1 <= cont[0] <= n
