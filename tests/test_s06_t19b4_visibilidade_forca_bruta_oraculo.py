# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19b, parte 4: FORÇA BRUTA. Cenas aleatórias de semente fixa (lascas, leques, triângulos minúsculos, lajes, soltos). Cada aresta
candidata é amostrada em 40 pontos; um ponto "seguramente visível" (nenhum triângulo, nem com folga, o cobre) tem de estar na saída de `linhas_visiveis`;
um "seguramente escondido" (dentro de um triângulo com folga e abaixo dele por mais de 3*tol_z) não pode estar (exceto cruzamento 2D com outra aresta).
Usa `visib_base._arestas_candidatas` só para listar as arestas candidatas. Só arestas com mais de 2 mm em planta entram (as quase verticais são ruído)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from obim_geometria.visib_base import _arestas_candidatas
from obim_geometria.visibilidade import linhas_visiveis

TOL = 1e-4

def _cena(seed):
    rng = np.random.default_rng(seed)
    S, vs = float(rng.choice([1.0, 20.0, 0.05])), []
    for _ in range(rng.integers(20, 120)):
        k, c, z = rng.integers(0, 5), rng.uniform(0, S, 2), rng.uniform(0, 1)
        if k == 0:  # lasca longa e fina, ângulo qualquer
            L, th, w = rng.uniform(0.2, 1.5) * S, rng.uniform(0, 2 * math.pi), 10 ** rng.uniform(-5, -2) * S
            u = np.array([math.cos(th), math.sin(th)])
            p, zs = [c, c + L * u + w * np.array([-u[1], u[0]]), c + L * u - w * np.array([-u[1], u[0]])], z + rng.uniform(-.3, .3, 3)
        elif k == 1:  # leque
            N, r, a0 = rng.integers(3, 40), rng.uniform(.02, .5) * S, rng.uniform(0, 6.3)
            for i in range(N):
                a1, a2 = a0 + i * 2 * math.pi / N, a0 + (i + 1) * 2 * math.pi / N
                vs.append(np.array([[c[0], c[1], z + .2], [c[0] + r * math.cos(a1), c[1] + r * math.sin(a1), z], [c[0] + r * math.cos(a2), c[1] + r * math.sin(a2), z]]))
            continue
        elif k == 2:  # minúsculo
            p, zs = [c, c + rng.uniform(-1, 1, 2) * 1e-3 * S, c + rng.uniform(-1, 1, 2) * 1e-3 * S], z + rng.uniform(-1e-3, 1e-3, 3)
        elif k == 3:  # laje grande
            p, zs = [c - rng.uniform(.1, .6) * S, c + [rng.uniform(.1, .6) * S, -rng.uniform(0, .3) * S], c + rng.uniform(.1, .6, 2) * S], np.full(3, z)
        else:
            p, zs = [c + rng.uniform(-.3, .3, 2) * S for _ in range(3)], z + rng.uniform(-.5, .5, 3)
        vs.append(np.column_stack([np.array(p), zs]))
    V = np.vstack(vs)
    return V, np.arange(len(V)).reshape(-1, 3)

def _limpa(V, T):
    _, idx, inv = np.unique(np.round(V / 1e-6).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    Tw = inv.ravel()[T]
    Tw = Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])]
    return V[idx], Tw[np.sort(np.unique(np.sort(Tw, axis=1), axis=0, return_index=True)[1])]

def _confere(seed, M=40):
    """(amostras seguramente visíveis ausentes da saída, amostras seguramente escondidas presentes na saída)."""
    V, T = _cena(seed)
    esc = max(1.0, float(np.ptp(V[:, :2])) / 20)
    S = np.array(linhas_visiveis(V, T, min_len=1e-5)).reshape(-1, 2, 2)
    P, Tw = _limpa(V, T)
    a, b, ang, silh = _arestas_candidatas(P, Tw)[:4]
    m = ((ang >= 0.001) | silh) & (np.hypot(*(b - a)[:, :2].T) > 2e-3)
    a, b = a[m], b[m]
    t = (np.arange(M) + 0.5) / M
    X = (a[:, None, :] + t[None, :, None] * (b - a)[:, None, :]).reshape(-1, 3)
    eid = np.repeat(np.arange(len(a)), M)
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    D = (B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1])
    ok = np.abs(D) > 1e-8 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
    A, B, C, D = A[ok], B[ok], C[ok], D[ok]

    def lado(p, q, r):  # distância assinada (positiva dentro) ao lado pq, com r dentro
        e = q - p
        s = np.sign(e[:, 0] * (r[:, 1] - p[:, 1]) - e[:, 1] * (r[:, 0] - p[:, 0]))
        return lambda Y: s * (e[:, 0] * (Y[:, None, 1] - p[:, 1]) - e[:, 1] * (Y[:, None, 0] - p[:, 0])) / np.hypot(e[:, 0], e[:, 1])
    f = [lado(A[:, :2], B[:, :2], C[:, :2]), lado(B[:, :2], C[:, :2], A[:, :2]), lado(C[:, :2], A[:, :2], B[:, :2])]
    gx = ((B[:, 2] - A[:, 2]) * (C[:, 1] - A[:, 1]) - (C[:, 2] - A[:, 2]) * (B[:, 1] - A[:, 1])) / D
    gy = ((B[:, 0] - A[:, 0]) * (C[:, 2] - A[:, 2]) - (C[:, 0] - A[:, 0]) * (B[:, 2] - A[:, 2])) / D
    hid, maybe = np.zeros(len(X), bool), np.zeros(len(X), bool)
    for k in range(0, len(X), 2000):
        Y = X[k:k + 2000]
        dmin = np.minimum(np.minimum(f[0](Y), f[1](Y)), f[2](Y))
        zp = A[:, 2] + gx * (Y[:, None, 0] - A[:, 0]) + gy * (Y[:, None, 1] - A[:, 1])
        hid[k:k + 2000] = ((dmin > 1e-4 * esc) & (zp > Y[:, None, 2] + 3 * TOL)).any(1)
        maybe[k:k + 2000] = ((dmin > -1e-4 * esc) & (zp > Y[:, None, 2] + 1e-6)).any(1)
    on = np.zeros(len(X), bool)
    for k in range(0, len(X), 1000):
        Y, p, q = X[k:k + 1000, None, :2], S[None, :, 0], S[None, :, 1]
        e = q - p
        u = np.clip(((Y - p) * e).sum(-1) / ((e ** 2).sum(-1) + 1e-300), 0, 1)
        on[k:k + 1000] = (np.hypot(*(Y - p - u[..., None] * e).transpose(2, 0, 1)) < 1e-7 * esc).any(1) if len(S) else False
    perdidos, extras = ~maybe & ~on, hid & on
    for i in np.nonzero(extras)[0]:  # cruzamento 2D com outra aresta: não conta
        p, e = a[:, :2], b[:, :2] - a[:, :2]
        u = np.clip(((X[i, :2] - p) * e).sum(1) / ((e ** 2).sum(1) + 1e-300), 0, 1)
        d = np.hypot(*(X[i, :2] - p - u[:, None] * e).T)
        d[eid[i]] = 9
        extras[i] = d.min() >= 2e-7 * esc
    return int(perdidos.sum()), int(extras.sum())

@pytest.mark.parametrize("seed", [*range(10, 21), 41, 99, 118])  # 41, 99 e 118 pegam o mapa conservador com só 2 cantos
def test_forca_bruta_nenhum_ponto_seguro_perdido_ou_indevido(seed):
    assert _confere(seed) == (0, 0)
