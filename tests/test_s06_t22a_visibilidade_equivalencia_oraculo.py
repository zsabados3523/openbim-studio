# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T22a (T3): a otimização do motor de linhas visíveis (corte espacial por peça + subgrade local) NÃO muda o resultado.
Dourado (tests/data/s06_t22a_dourado.npz) gravado com o motor ANTES da otimização (origin/main, 4b13ecc) em cenas de semente fixa.
Compara `linhas_visiveis_multi`: mesma contagem de polilinhas/pontos por peça e pontas a até 1e-9 m (ordem canônica).
Regerar o dourado só com o motor de referência: `python tests/test_s06_t22a_visibilidade_equivalencia_oraculo.py`. Não editar nesta tarefa."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from obim_geometria.visibilidade import linhas_visiveis_multi

DOURADO = Path(__file__).parent / "data" / "s06_t22a_dourado.npz"
TOL = 1e-9
F = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])


def _rz(th):
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def caixa(c, s, th=0.0, incl=0.0):
    v = np.array([[x, y, z] for z in (0, 1) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))], float) * s - np.array(s) / 2
    r = _rz(th)
    if incl:
        r = r @ np.array([[np.cos(incl), 0, np.sin(incl)], [0, 1, 0], [-np.sin(incl), 0, np.cos(incl)]])
    return v @ r.T + c, F.copy()


def tiras(x0, y0, comp, larg, n, th, z0, incl):
    """n tiras longas e finas (2 triângulos cada) numa superfície levemente inclinada: aciona o caminho de faixas."""
    q = np.array([[x0, y0 + i * larg] for i in range(n)])
    pts = np.concatenate([[[a, b], [a + comp, b], [a + comp, b + larg], [a, b + larg]] for a, b in q])
    v = np.c_[pts, z0 + incl * pts[:, 1]]
    k = np.arange(n)[:, None] * 4
    t = np.concatenate([k + [0, 1, 2], k + [0, 2, 3]]).reshape(2, n, 3).transpose(1, 0, 2).reshape(-1, 3)
    return v @ _rz(th).T, t


def cilindro(c, r, h, n):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    b = np.c_[c[0] + r * np.cos(a), c[1] + r * np.sin(a)]
    v = np.r_[np.c_[b, np.full(n, c[2])], np.c_[b, np.full(n, c[2] + h)], [[c[0], c[1], c[2]], [c[0], c[1], c[2] + h]]]
    i = np.arange(n)
    j = (i + 1) % n
    t = np.stack([np.c_[i, j, n + j], np.c_[i, n + j, n + i], np.c_[np.full(n, 2 * n), j, i], np.c_[np.full(n, 2 * n + 1), n + i, n + j]], 1)
    return v, t.reshape(-1, 3)


def terreno(nx, ny, lado, amp, z0=0.0):
    """Malha regular ondulada de 2*nx*ny triângulos."""
    xs, ys = np.meshgrid(np.arange(nx + 1) * lado, np.arange(ny + 1) * lado)
    z = z0 + amp * np.sin(xs * 0.37) * np.cos(ys * 0.23)
    v = np.c_[xs.ravel(), ys.ravel(), z.ravel()]
    i = (np.arange(ny)[:, None] * (nx + 1) + np.arange(nx)[None, :]).ravel()
    t = np.stack([np.c_[i, i + 1, i + nx + 2], np.c_[i, i + nx + 2, i + nx + 1]], 1).reshape(-1, 3)
    return v, t


def _aleatoria(sem):
    rng = np.random.default_rng(1000 + sem)
    lado = rng.uniform(2, 60)
    pecas = []
    for _ in range(int(rng.integers(3, 20))):
        c = rng.uniform(0, lado, 3) * [1, 1, 0.1]
        s = rng.uniform(0.01, lado / 3, 3)
        s[2] = rng.uniform(0.01, 3)
        th, inc, u = rng.uniform(0, np.pi), (rng.uniform(-0.5, 0.5) if rng.random() < 0.3 else 0.0), rng.random()
        if u < 0.2:
            th = round(th / (np.pi / 2)) * np.pi / 2  # alinhada/encostada
        if u > 0.85:
            pecas.append(cilindro(c, rng.uniform(0.05, 2), rng.uniform(0.1, 3), int(rng.integers(3, 80))))
        else:
            pecas.append(caixa(c, s, th, inc))
    return pecas


def _dificil(k):
    rng = np.random.default_rng(2000 + k)
    th = rng.uniform(0, np.pi) if k % 2 else 0.0
    p = [tiras(0, 0, rng.uniform(15, 40), rng.uniform(0.01, 0.05), int(rng.integers(300, 700)), th, 0.0, rng.uniform(0, 0.05)),
         tiras(2, 1, rng.uniform(5, 20), 0.02, 400, th + 0.3, 1.0, 0.01)]
    p += [caixa(rng.uniform(0, 25, 3) * [1, 1, 0.1], rng.uniform(0.05, 6, 3), rng.uniform(0, np.pi)) for _ in range(int(rng.integers(5, 25)))]
    p.append(cilindro(np.r_[rng.uniform(0, 20, 2), 0], rng.uniform(0.1, 3), rng.uniform(0.5, 3), int(rng.integers(64, 1024))))
    p.append(caixa(np.array([500.0, 500, 0]), [1, 1, 1]))  # isolada a 500 m
    p.append(caixa(np.array([5.0, 5, -5]), [0.2, 0.2, 0.2]))  # escondida sob tudo
    p.append(caixa(np.array([5.0, 5, -5]), [0.2, 0.2, 0.2]))  # duplicata exata
    return p


def _degenerada():
    v, t = caixa(np.array([1.0, 1, 0]), [2, 2, 2])
    vd = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 0, 0.0]])
    return [(v, t), (np.zeros((0, 3)), np.zeros((0, 3), np.int64)), (vd, np.array([[0, 1, 2], [0, 0, 1], [1, 1, 1], [0, 1, 3]])),
            caixa(np.array([1.0, 1, 0]), [2, 2, 2]), caixa(np.array([30.0, 0, 0]), [1, 1, 1])]


def _grande():
    """> 100.000 triângulos: níveis de grade grossos."""
    p = [terreno(210, 250, 0.2, 0.15, -1.0)] + [caixa(np.array([4 + 9 * i, 6 + 5 * (i % 3), 0.5]), [3, 2, 2], 0.4 * i) for i in range(6)]
    p.append(cilindro(np.array([40.0, 25, 0]), 4, 5, 300))
    return p


def _georref():
    off = np.array([500000.0, 2500000.0, 700.0])
    return [(v + off, t) for v, t in _aleatoria(77)[:25] + [tiras(0, 0, 20, 0.03, 300, 0.4, 0.0, 0.02)]]


def _bordas():
    """Peças sob/sobre uma placa, encostadas na borda do domínio (±1e-7): o corte espacial não pode perder pares na borda."""
    p = [caixa(np.array([10.0, 10, 2]), [20, 20, 2], th) for th in (0.0,)]
    for i, (sx, sy) in enumerate([(1, 0), (-1, 0), (0, 1), (0, -1)] * 3):
        for k, dl in enumerate((0.0, 1e-7, -1e-7, 0.3)):
            t = 1.5 + 2.2 * (i + k * 3) % 16
            c = np.array([10 + sx * (10 - 0.75 + dl) + (1 - abs(sx)) * (t - 10), 10 + sy * (10 - 0.4 + dl) + (1 - abs(sy)) * (t - 10), 0.25 if i % 2 else 3.5])
            p.append(caixa(c, [1.5, 0.8, 0.5] if sx else [0.8, 1.5, 0.5], 0.0))
    return p


def _tol_celula():
    """Oclusor e oclusado a menos de d_eps (1e-6) de distância, em lados opostos de fronteiras de célula (domínio 512 m)."""
    p = [caixa(np.array([0.5, 0.5, 0.5]), [1, 1, 1]), caixa(np.array([511.5, 511.5, 0.5]), [1, 1, 1])]
    j = 0
    for x0 in (10.0, 10.5, 32.0, 64.5, 128.0):
        for d in (-5e-7, 0.0, 5e-7, 2e-6):
            y = 20.0 + 12 * j
            j += 1
            for t in ((x0 + 1, y), (y, x0 + 1)):  # parede e baixa lado a lado em x e depois em y
                u = (x0 - 1 - d, y) if t[0] == x0 + 1 else (y, x0 - 1 - d)
                p += [caixa(np.array([*t, 2.5]), [2, 2, 5]), caixa(np.array([*u, 0.5]), [2, 2, 1])]
    return p


def _fita_na_borda():
    """Quatro fitas finas (menores que uma célula) nas bordas do domínio, com caixas baixas terminando sob elas."""
    W, H = 30.0, 20.0
    p = []
    for k, e in enumerate((0.001, 0.004, 0.02, 0.2)):
        z = 3 + 0.5 * k
        p += [caixa(np.array([W / 2, H - e / 2, z]), [W, e, 0.3]), caixa(np.array([W / 2, e / 2, z]), [W, e, 0.3]),
              caixa(np.array([e / 2, H / 2, z]), [e, H, 0.3]), caixa(np.array([W - e / 2, H / 2, z]), [e, H, 0.3])]
        x, y = 4 + 5 * k, 3 + 3 * k
        p += [caixa(np.array([x, H - 1, 0.5]), [1.5, 2, 1]), caixa(np.array([x, 1, 0.5]), [1.5, 2, 1]),
              caixa(np.array([1, y, 0.5]), [2, 1.5, 1]), caixa(np.array([W - 1, y, 0.5]), [2, 1.5, 1])]
    return p


def _caixa_xy(x0, x1, y0, y1, z0, z1):
    return caixa(np.array([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]), [x1 - x0, y1 - y0, z1 - z0])


def _gira(pecas, th):
    return [(v @ _rz(th).T, t) for v, t in pecas]


def _matar_m5(var=0):
    """Oclusor estreito (dx < g, > 25 células) cuja linha de folga de cima é podada por uma placa alta em z_full; aresta baixa
    na última linha da subgrade local. Cobre o clamp de borda da subgrade (sx0/sx1/sy0/sy1) quando girada em 90 graus."""
    x = [(0.0015, 0.0025), (0.0005, 0.0015), (0.0011, 0.0019)][var % 3]
    p = [_caixa_xy(*x, 0, 0.2018, 0, 5), _caixa_xy(-1, 2, 0.2019, 1.5, 9.5, 10), _caixa_xy(-0.5, 0.5, 0.1, 0.2010, 0, 0.5)]
    return _gira(p, (var // 3) * np.pi / 2)


def _roteamento_faixas_lim_c():
    """Mais de 200 triângulos longos/finos alinhados (rota de faixas) misturados com triângulos pequenos e grandes (lim_c)."""
    p = [tiras(0, 0, 30, 0.02, 150, 0.0, 0.0, 0.01), tiras(1, 0.5, 25, 0.015, 120, 0.0, 0.4, 0.0), terreno(14, 12, 0.4, 0.2, 0.3)]
    p += [caixa(np.array([3.0 + 2.1 * i, 1.0 + 0.7 * (i % 4), 0.3]), [0.05 + 0.1 * (i % 3), 1.0, 0.6], 0.1 * i) for i in range(8)]
    return p


def _cull_45_graus():
    """Fitas e caixas nas bordas do domínio, giradas 45 graus: caixas de aresta e de triângulo diagonais no corte."""
    return _gira(_fita_na_borda(), np.pi / 4)


def todas():
    c = {f"a{k:02d}": (lambda k=k: _aleatoria(k)) for k in range(40)}
    c.update({f"d{k}": (lambda k=k: _dificil(k)) for k in range(6)})
    c.update(degenerada=_degenerada, bordas=_bordas, fita_na_borda=_fita_na_borda,
             roteamento_faixas_lim_c=_roteamento_faixas_lim_c, cull_45_graus=_cull_45_graus, tol_celula=_tol_celula, grande=_grande, georref=_georref)
    c.update({f"matar_m5_{k}": (lambda k=k: _matar_m5(k)) for k in range(12)})  # 3 posições x 4 giros de 90 graus (subgrade nos 4 lados)
    return c


def _canon(pls):
    """Ordem canônica das polilinhas de uma peça: (nº pontos, 1º ponto, último ponto) arredondados."""
    if not pls:
        return []
    ch = np.array([[len(p), *np.round(p[0], 5), *np.round(p[-1], 5)] for p in pls])
    return [pls[i] for i in np.lexsort(ch.T[::-1])]


def _empacotar(res):
    d = {}
    for i, pls in enumerate(res):
        pls = _canon(pls)
        d[f"{i}_n"] = np.array([len(p) for p in pls], np.int32)
        d[f"{i}_p"] = np.concatenate(pls) if pls else np.zeros((0, 2))
    return d


def _confere(nome, res, gold):
    n_pecas = len([k for k in gold if k.startswith(nome + "/") and k.endswith("_n")])
    assert len(res) == n_pecas, nome
    for i, pls in enumerate(res):
        pls = _canon(pls)
        gn, gp = gold[f"{nome}/{i}_n"], gold[f"{nome}/{i}_p"]
        assert len(pls) == len(gn), f"{nome} peca {i}: contagem de polilinhas"
        assert [len(p) for p in pls] == gn.tolist(), f"{nome} peca {i}: pontos por polilinha"
        if len(gn):
            dif = np.abs(np.concatenate(pls) - gp).max()
            assert dif <= TOL, f"{nome} peca {i}: pontas diferem {dif:.3e} m"


@pytest.fixture(scope="module")
def gold():
    with np.load(DOURADO) as z:
        return {k: z[k] for k in z.files}


@pytest.mark.parametrize("nome", list(todas()))
def test_equivale_ao_dourado(nome, gold):
    _confere(nome, linhas_visiveis_multi(todas()[nome]()), gold)


@pytest.mark.parametrize("nome", ["a03", "a17", "d1", "degenerada"])
def test_invariante_a_ordem_das_pecas_e_deterministico(nome):
    pecas = todas()[nome]()
    r0 = linhas_visiveis_multi(pecas)
    n = len(pecas)
    ordem = [(i * 7 + 3) % n for i in range(n)] if np.gcd(7, n) == 1 else list(range(n))[::-1]
    rp = linhas_visiveis_multi([pecas[j] for j in ordem])
    for pos, j in enumerate(ordem):  # peça j vista com as demais como oclusores, em outra ordem
        a, b = _canon(rp[pos]), _canon(r0[j])
        assert len(a) == len(b) and all(len(x) == len(y) and np.abs(x - y).max() <= TOL for x, y in zip(a, b)), (nome, j)
    for _ in range(2):  # determinismo: 3 rodadas iguais
        r1 = linhas_visiveis_multi(pecas)
        assert all(len(x) == len(y) and all(np.array_equal(p, q) for p, q in zip(_canon(x), _canon(y))) for x, y in zip(r0, r1))


def test_a_cena_grande_tem_mais_de_100_mil_triangulos():
    assert sum(len(t) for _, t in _grande()) > 100_000  # garante que os níveis de grade grossos são exercitados


if __name__ == "__main__":  # regera o dourado (só com o motor de referência)
    out = {}
    for nome, f in todas().items():
        out.update({f"{nome}/{k}": v for k, v in _empacotar(linhas_visiveis_multi(f())).items()})
    np.savez_compressed(DOURADO, **out)
    print(DOURADO, DOURADO.stat().st_size)
