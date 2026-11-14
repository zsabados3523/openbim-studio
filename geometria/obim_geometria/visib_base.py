# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers geometricos e de grade para visibilidade de malhas."""
from __future__ import annotations

import numpy as np


def _rle_idx(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Retorna (indice_grupo, deslocamento_local) para contagens `n`."""
    grp = np.repeat(np.arange(len(n)), n)
    off = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
    return grp, off


def _fatias(n: np.ndarray, lim: int):
    """Gera pares (inicio, fim) fatiando `n` para soma <= `lim` por bloco."""
    ac = np.cumsum(n)
    i0 = 0
    while i0 < len(n):
        base = int(ac[i0 - 1]) if i0 else 0
        i1 = max(int(np.searchsorted(ac, base + lim, side="right")), i0 + 1)
        yield i0, i1
        i0 = i1


def _expandir_celulas(ix0: np.ndarray, ix1: np.ndarray, iy0: np.ndarray, iy1: np.ndarray, nx: int):
    """Expande caixas de celulas em pares (indice_objeto, indice_celula)."""
    w = ix1 - ix0 + 1
    obj, k = _rle_idx(w * (iy1 - iy0 + 1))
    return obj, (iy0[obj] + k // w[obj]) * nx + (ix0[obj] + k % w[obj])


def _cel_caixa(x0, x1, y0, y1, mn_x: float, mn_y: float, g: float, W: int, H: int):
    """Converte caixas 2D do mundo em limites inteiros [0..W-1] x [0..H-1] da grade."""
    ix0 = np.clip(np.floor((x0 - mn_x) / g).astype(np.int64), 0, W - 1)
    ix1 = np.clip(np.floor((x1 - mn_x) / g).astype(np.int64), 0, W - 1)
    iy0 = np.clip(np.floor((y0 - mn_y) / g).astype(np.int64), 0, H - 1)
    iy1 = np.clip(np.floor((y1 - mn_y) / g).astype(np.int64), 0, H - 1)
    return ix0, ix1, iy0, iy1


def _subseg_cels(a, d, nsub, mn_x: float, mn_y: float, cg: float, Wc: int, Hc: int):
    """Divide arestas em subsegmentos e retorna parametros, pontas e caixas de celula."""
    s_l, k = _rle_idx(nsub)
    n_rep = np.repeat(nsub, nsub)
    t0_s = k / n_rep
    t1_s = (k + 1) / n_rep
    sa = a[s_l] + t0_s[:, None] * d[s_l]
    sb = a[s_l] + t1_s[:, None] * d[s_l]
    sx0, sx1, sy0, sy1 = _cel_caixa(
        np.minimum(sa[:, 0], sb[:, 0]), np.maximum(sa[:, 0], sb[:, 0]),
        np.minimum(sa[:, 1], sb[:, 1]), np.maximum(sa[:, 1], sb[:, 1]), mn_x, mn_y, cg, Wc, Hc,
    )
    return s_l, t0_s, t1_s, sa, sb, sx0, sx1, sy0, sy1


def _aplicar_corte(s, r, lo, hi, fail_val: float, eq_fail: bool = False):
    """Atualiza intervalo [lo, hi] pelo corte linear com `s` e `r`."""
    pos = s > 1e-12
    neg = s < -1e-12
    zer = ~(pos | neg)
    tt = np.where(zer, 0.0, r / np.where(zer, 1.0, s))
    lo = np.where(pos, np.maximum(lo, tt), lo)
    hi = np.where(neg, np.minimum(hi, tt), hi)
    return lo, np.where(zer & (r >= 0 if eq_fail else r > 0), fail_val, hi)


def _varredura_x(nx_, ny_, cc_, tri_r, Y_r, x_lo, x_hi, folga: float, mn_x: float, res: float, W: int):
    """Calcula intervalos [ix0, ix1] de colunas numa faixa de linhas para triangulos `tri_r`."""
    for k in range(3):
        nxk = nx_[tri_r, k]
        nyk = ny_[tri_r, k]
        rhs = folga * (np.abs(nxk) + np.abs(nyk)) - nyk * Y_r - cc_[tri_r, k]
        x_lo, x_hi = _aplicar_corte(nxk, rhs, x_lo, x_hi, -np.inf)
    fin = np.isfinite(x_lo) & np.isfinite(x_hi) & (x_hi >= x_lo)
    ix0 = np.maximum(0, np.ceil((x_lo[fin] - mn_x) / res - 0.5).astype(np.int64))
    ix1 = np.minimum(W - 1, np.floor((x_hi[fin] - mn_x) / res - 0.5).astype(np.int64))
    return fin, ix0, ix1, ix1 >= ix0


def _arestas_candidatas(P: np.ndarray, Tw: np.ndarray):
    """Extrai arestas unicas com angulo diedro, silhueta e indices de vertices."""
    n = np.cross(P[Tw[:, 1]] - P[Tw[:, 0]], P[Tw[:, 2]] - P[Tw[:, 0]])
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-14
    Tw = Tw[ok]
    n = n[ok] / ln[ok][:, None]
    nt = len(Tw)
    if not nt:
        v0 = np.zeros((0, 3), dtype=np.float64)
        i0 = np.zeros(0, dtype=np.int64)
        return v0, v0, np.zeros(0), np.zeros(0, bool), Tw, i0, i0
    e = np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]])
    fid = np.tile(np.arange(nt), 3)
    lo = e.min(1)
    hi = e.max(1)
    chave = lo.astype(np.int64) * (len(P) + 1) + hi
    ordem = np.argsort(chave, kind="stable")
    chave_o = chave[ordem]
    fid_o = fid[ordem]
    idx = np.nonzero(np.concatenate([[True], chave_o[1:] != chave_o[:-1]]))[0]
    cont = np.diff(np.concatenate([idx, [len(chave_o)]]))
    m1 = (cont == 1) | (cont > 2)
    m2 = np.nonzero(cont == 2)[0]
    f1 = fid_o[idx[m2]]
    f2 = fid_o[idx[m2] + 1]
    ang = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", n[f1], n[f2]), -1.0, 1.0)))
    sel = np.concatenate([idx[m1], idx[m2]])
    ang_all = np.concatenate([np.full(int(m1.sum()), 180.0), ang])
    silh = np.concatenate([np.zeros(int(m1.sum()), bool), n[f1, 2] * n[f2, 2] < 0])
    ea = lo[ordem][sel]
    eb = hi[ordem][sel]
    return P[ea], P[eb], ang_all, silh, Tw, ea, eb


def _preparar_triangulos(P: np.ndarray, Tw: np.ndarray):
    """Orienta triangulos nao-verticais CCW em planta e pre-calcula planos e caixas."""
    A = P[Tw[:, 0]].copy()
    B = P[Tw[:, 1]].copy()
    C = P[Tw[:, 2]].copy()
    D = (B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1])
    ln3 = np.linalg.norm(np.cross(B - A, C - A), axis=1)
    # Limiar relativo ao tamanho: |sin(inclinacao)| > 1e-8 evita quase-verticais em qualquer escala.
    ok = (ln3 > 1e-14) & (np.abs(D) > 1e-8 * ln3)
    A = A[ok]
    B = B[ok]
    C = C[ok]
    D = D[ok]
    tv = Tw[ok]
    neg = D < 0
    B2 = np.where(neg[:, None], C, B)
    C2 = np.where(neg[:, None], B, C)
    D = np.abs(D)
    gx = ((B2[:, 2] - A[:, 2]) * (C2[:, 1] - A[:, 1]) - (C2[:, 2] - A[:, 2]) * (B2[:, 1] - A[:, 1])) / D
    gy = ((B2[:, 0] - A[:, 0]) * (C2[:, 2] - A[:, 2]) - (C2[:, 0] - A[:, 0]) * (B2[:, 2] - A[:, 2])) / D
    V3 = np.stack([A, B2, C2], axis=1)
    Q3 = np.roll(V3, -1, axis=1)
    dx = Q3[:, :, 0] - V3[:, :, 0]
    dy = Q3[:, :, 1] - V3[:, :, 1]
    h = np.hypot(dx, dy)
    ln = np.where(h < 1e-12, 1.0, h)
    nx_ = -dy / ln
    ny_ = dx / ln
    cc_ = (dy * V3[:, :, 0] - dx * V3[:, :, 1]) / ln
    return (
        A, gx, gy, nx_, ny_, cc_, V3[:, :, 0].min(1), V3[:, :, 0].max(1),
        V3[:, :, 1].min(1), V3[:, :, 1].max(1), V3[:, :, 2].max(1), tv, 0.5 * D,
    )
