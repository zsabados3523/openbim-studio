# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19d7: o mapa z conservador e o tri_keep rodam UMA vez por domínio igual dentro de `linhas_visiveis_multi`.
CONTRATO: `_visibilidade_hibrida(P, Tw, a, b, ea, eb, tol_z, d_eps, min_len, prep=None, memo=None)`; `memo` é dict opcional
(chave = domínio mn_x, mn_y, mx_x, mx_y e g). Mesmo domínio reaproveita `_mapa_z_conservador` e `tri_keep`/`kept_idx`; domínio diferente recalcula.
Resultado SEMPRE idêntico ao sem memo. `memo=None` mantém o comportamento antigo. Não editar nesta tarefa."""
from __future__ import annotations

import importlib

import numpy as np
import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from test_s06_t19b1_visibilidade_oraculo import _caixa


def _V():
    return importlib.import_module("obim_geometria.visibilidade")


def _cena(n_pecas, seed, tam=1.0, esp=6.0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_pecas):
        x, y = rng.uniform(0, esp, 2)
        z = rng.uniform(0, 3)
        sx, sy, sz = rng.uniform(0.5, 1.5, 3) * tam
        p, t = _caixa(x, y, z, x + sx, y + sy, z + sz)
        a = np.radians(rng.uniform(0, 40))
        R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        c = p.mean(axis=0)
        out.append(((p - c) @ R.T + c, t))
    return out


def _cena_pequena():
    return _cena(7, 1)


def _cena_grande():
    return _cena(30, 2, tam=0.4, esp=8.0)


def _espiao_mapa(monkeypatch):
    V = _V()
    orig = V._mapa_z_conservador
    n = {"c": 0}

    def esp(*a, **k):
        n["c"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(V, "_mapa_z_conservador", esp)
    return n


def _sem_memo(monkeypatch):
    V = _V()
    orig = V._visibilidade_hibrida

    def w(*a, memo=None, **k):
        return orig(*a, **k)

    monkeypatch.setattr(V, "_visibilidade_hibrida", w)


def _captura(monkeypatch, pecas):
    """Roda a multi e devolve os argumentos posicionais de cada chamada ao híbrido (sem memo)."""
    V = _V()
    orig = V._visibilidade_hibrida
    chamadas = []

    def w(*a, memo=None, **k):
        chamadas.append((a, k))
        return orig(*a, **k)

    monkeypatch.setattr(V, "_visibilidade_hibrida", w)
    V.linhas_visiveis_multi(pecas)
    monkeypatch.setattr(V, "_visibilidade_hibrida", orig)
    return chamadas


def _iguais(r1, r2):
    assert len(r1) == len(r2)
    for p1, p2 in zip(r1, r2):
        assert len(p1) == len(p2)
        for x, y in zip(p1, p2):
            assert x.shape == y.shape and np.array_equal(x, y)


# ---------------------------------------------------------------- (1) igualdade
@pytest.mark.parametrize("cena", [_cena_pequena, _cena_grande])
def test_1_igual_ao_sem_memo(monkeypatch, cena):
    V = _V()
    pecas = cena()
    got = V.linhas_visiveis_multi(pecas)
    assert sum(len(p) for p in got) > 0
    _sem_memo(monkeypatch)
    ref = V.linhas_visiveis_multi(pecas)
    _iguais(got, ref)


def test_1b_igual_chamando_hibrido_direto_sem_memo(monkeypatch):
    V = _V()
    pecas = _cena_pequena()
    cham = _captura(monkeypatch, pecas)
    ref = [list(V._visibilidade_hibrida(*a, **k)) for a, k in cham]
    got = [x for x in V.linhas_visiveis_multi(pecas) if x]
    assert len(got) == len(ref)
    _iguais(got, ref)


# ---------------------------------------------------------------- (2) contagem
def test_2_n_pecas_um_mapa(monkeypatch):
    V = _V()
    pecas = _cena_pequena()
    n_chamadas = len(_captura(monkeypatch, pecas))
    assert n_chamadas >= 3
    n = _espiao_mapa(monkeypatch)
    V.linhas_visiveis_multi(pecas)
    assert n["c"] == 1


def test_2b_memo_compartilhado_mesmo_dominio(monkeypatch):
    V = _V()
    cham = _captura(monkeypatch, _cena_pequena())
    n = _espiao_mapa(monkeypatch)
    memo = {}
    (a0, k0), (a1, k1) = cham[0], cham[1]
    r0 = V._visibilidade_hibrida(*a0, **k0, memo=memo)
    r1 = V._visibilidade_hibrida(*a1, **k1, memo=memo)
    assert n["c"] == 1
    _iguais([list(r0), list(r1)], [list(V._visibilidade_hibrida(*a0, **k0)), list(V._visibilidade_hibrida(*a1, **k1))])


def test_2c_dominio_diferente_recalcula(monkeypatch):
    V = _V()
    cham = _captura(monkeypatch, _cena_pequena())
    n = _espiao_mapa(monkeypatch)
    memo = {}
    a0, k0 = cham[0]
    V._visibilidade_hibrida(*a0, **k0, memo=memo)
    a1 = list(cham[1][0])
    a1[2] = a1[2] + np.array([50.0, 50.0, 0.0])  # arestas fora: domínio maior
    a1[3] = a1[3] + np.array([50.0, 50.0, 0.0])
    V._visibilidade_hibrida(*a1, **cham[1][1], memo=memo)
    assert n["c"] == 2


# ---------------------------------------------------------------- (3) memo=None: comportamento antigo
def test_3_sem_memo_um_mapa_por_chamada(monkeypatch):
    V = _V()
    cham = _captura(monkeypatch, _cena_pequena())
    n = _espiao_mapa(monkeypatch)
    for a, k in cham[:3]:
        V._visibilidade_hibrida(*a, **k)
    assert n["c"] == 3
    n["c"] = 0
    a, k = cham[0]
    V._visibilidade_hibrida(*a, **k, memo=None)
    assert n["c"] == 1


# ---------------------------------------------------------------- (4) API pública
def test_4_assinaturas_publicas():
    import inspect

    V = _V()
    assert list(inspect.signature(V.linhas_visiveis_multi).parameters) == ["pecas", "angulo_graus", "tol_z", "min_len", "trabalhadores"]
    ps = list(inspect.signature(V.linhas_visiveis_vista).parameters)
    assert ps[:2] == ["pecas", "quadro"] and "profundidade" in ps


@pytest.mark.parametrize("seed", [3, 4])
def test_4b_vista_igual_sem_memo(monkeypatch, seed):
    from types import SimpleNamespace

    V = _V()
    Q = SimpleNamespace(origem=np.zeros(3), u=np.array([1.0, 0, 0]), v=np.array([0, 0, 1.0]), w=np.array([0, -1.0, 0]))
    pecas = [(p + np.array([0, -1.0, 0]) * 0, t) for p, t in _cena(5, seed)]
    pecas = [(p * np.array([1, -1, 1]) , t[:, ::-1]) for p, t in pecas]  # y negativo: atrás do plano w=0 (w=-y)
    got = V.linhas_visiveis_vista(pecas, Q, profundidade=50.0)
    _sem_memo(monkeypatch)
    _iguais(got, V.linhas_visiveis_vista(pecas, Q, profundidade=50.0))
    assert len(got) == len(pecas)


# ---------------------------------------------------------------- (5) peças sem arestas candidatas
def test_5_peca_degenerada_no_meio(monkeypatch):
    V = _V()
    pecas = _cena_pequena()
    vazia = (np.zeros((0, 3)), np.zeros((0, 3), int))
    plana = (np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0.0]]), np.array([[0, 1, 2]]))  # colinear
    pecas = [pecas[0], vazia, plana, *pecas[1:]]
    n = _espiao_mapa(monkeypatch)
    got = V.linhas_visiveis_multi(pecas)
    assert n["c"] == 1
    assert len(got) == len(pecas) and got[1] == [] and got[2] == []
    _sem_memo(monkeypatch)
    _iguais(got, V.linhas_visiveis_multi(pecas))


# ---------------------------------------------------------------- (6) sem estado entre chamadas
def test_6_cenas_diferentes_nao_compartilham(monkeypatch):
    V = _V()
    c1, c2 = _cena(6, 10), _cena(6, 11, esp=9.0)
    a1 = V.linhas_visiveis_multi(c1)
    a2 = V.linhas_visiveis_multi(c2)
    n = _espiao_mapa(monkeypatch)
    V.linhas_visiveis_multi(c1)
    V.linhas_visiveis_multi(c2)
    assert n["c"] == 2  # um mapa por chamada pública: nada vaza de uma para a outra
    _sem_memo(monkeypatch)
    _iguais(a1, V.linhas_visiveis_multi(c1))
    _iguais(a2, V.linhas_visiveis_multi(c2))
