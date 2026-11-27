# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers geometricos e de grade para visibilidade de malhas."""
from __future__ import annotations

import numpy as np

from obim_geometria import visib_nativo


def _rle_idx(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Retorna (indice_grupo, deslocamento_local) para contagens `n`."""
    grp = np.repeat(np.arange(len(n)), n)
    off = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
    return grp, off


def _fatias(n: np.ndarray, lim: int, chaves: np.ndarray | None = None):
    """Gera pares (inicio, fim) fatiando `n` para soma <= `lim` por bloco.

    Pre-condicao: se `chaves` for dado, deve estar em ordem nao-decrescente (senao o laco pode nao terminar).
    """
    ac = np.cumsum(n)
    i0 = 0
    while i0 < len(n):
        base = int(ac[i0 - 1]) if i0 else 0
        i1 = max(int(np.searchsorted(ac, base + lim, side="right")), i0 + 1)
        if chaves is not None and i1 < len(n) and chaves[i1] == chaves[i1 - 1]:
            fim_k = int(np.searchsorted(chaves, chaves[i1 - 1], side="right"))
            if int(ac[fim_k - 1]) - base <= 2 * lim:
                i1 = fim_k
        yield i0, i1
        i0 = i1


def _dedup_int64(ch: np.ndarray) -> np.ndarray:
    """Ordena in-place (muta `ch`; passe um temporario) e remove duplicatas de vetor 1D de inteiros."""
    if len(ch) <= 1:
        return ch
    ch.sort()
    m = np.empty(len(ch), dtype=bool)
    m[0] = True
    m[1:] = ch[1:] != ch[:-1]
    return ch[m]


def _expandir_celulas_py(ix0: np.ndarray, ix1: np.ndarray, iy0: np.ndarray, iy1: np.ndarray, nx: int):
    """Expande caixas de celulas em pares (indice_objeto, indice_celula) (versao Python)."""
    visib_nativo.registrar_chamada_py("expandir_celulas")
    w = ix1 - ix0 + 1
    obj, k = _rle_idx(w * (iy1 - iy0 + 1))
    return obj, (iy0[obj] + k // w[obj]) * nx + (ix0[obj] + k % w[obj])


def _expandir_celulas(ix0: np.ndarray, ix1: np.ndarray, iy0: np.ndarray, iy1: np.ndarray, nx: int):
    """Expande caixas de celulas em pares (indice_objeto, indice_celula)."""
    if visib_nativo.visib_nativo_ligado():
        i64 = [np.asarray(v, dtype=np.int64) for v in (ix0, ix1, iy0, iy1)]
        return visib_nativo.exigir("expandir_celulas")(*i64, int(nx))
    return _expandir_celulas_py(ix0, ix1, iy0, iy1, nx)


def _cel_caixa(x0, x1, y0, y1, mn_x: float, mn_y: float, g: float, W: int, H: int):
    """Converte caixas 2D do mundo em limites inteiros [0..W-1] x [0..H-1] da grade."""
    ix0 = np.clip(np.floor((x0 - mn_x) / g).astype(np.int64), 0, W - 1)
    ix1 = np.clip(np.floor((x1 - mn_x) / g).astype(np.int64), 0, W - 1)
    iy0 = np.clip(np.floor((y0 - mn_y) / g).astype(np.int64), 0, H - 1)
    iy1 = np.clip(np.floor((y1 - mn_y) / g).astype(np.int64), 0, H - 1)
    return ix0, ix1, iy0, iy1


def _subseg_cels_py(a, d, nsub, mn_x: float, mn_y: float, cg: float, Wc: int, Hc: int):
    """Divide arestas em subsegmentos e retorna parametros, pontas e caixas de celula (versao Python)."""
    visib_nativo.registrar_chamada_py("subseg_cels")
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


def _subseg_cels(a, d, nsub, mn_x: float, mn_y: float, cg: float, Wc: int, Hc: int):
    """Divide arestas em subsegmentos e retorna parametros, pontas e caixas de celula."""
    if visib_nativo.visib_nativo_ligado():
        return visib_nativo.exigir("subseg_cels")(
            np.asarray(a, dtype=np.float64), np.asarray(d, dtype=np.float64), np.asarray(nsub, dtype=np.int64),
            float(mn_x), float(mn_y), float(cg), int(Wc), int(Hc),
        )
    return _subseg_cels_py(a, d, nsub, mn_x, mn_y, cg, Wc, Hc)


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


def _ler_quadro(quadro) -> tuple[np.ndarray, np.ndarray]:
    """Extrai (origem (3,), matriz_eixos (3,3)) de um quadro ortonormal (u, v, w)."""
    origem = np.asarray(quadro.origem, dtype=np.float64).reshape(3)
    axes = np.vstack([
        np.asarray(quadro.u, dtype=np.float64).reshape(3),
        np.asarray(quadro.v, dtype=np.float64).reshape(3),
        np.asarray(quadro.w, dtype=np.float64).reshape(3),
    ])
    return origem, axes


def _cruzar_plano(T_c: np.ndarray, s_raw: np.ndarray, s_c: np.ndarray, nV: int):
    """Calcula intersecoes de arestas e rotaciona triangulos que cruzam s = 0."""
    e_a = T_c
    e_b = np.roll(T_c, -1, axis=1)
    is_cross = (s_c * np.roll(s_c, -1, axis=1)) < 0.0
    ca, cb = e_a[is_cross], e_b[is_cross]
    lo = np.minimum(ca, cb)
    hi = np.maximum(ca, cb)
    keys = lo.astype(np.int64) * nV + hi
    _, u_idx, inv = np.unique(keys, return_index=True, return_inverse=True)
    lo_u, hi_u = lo[u_idx], hi[u_idx]
    t_cut = -s_raw[lo_u] / (s_raw[hi_u] - s_raw[lo_u])
    cut_id = np.full((len(T_c), 3), -1, dtype=np.int64)
    cut_id[is_cross] = inv

    def _rot(mask: np.ndarray, shift: np.ndarray):
        Tm, sm, cm = T_c[mask], s_c[mask], cut_id[mask]
        cols = (np.arange(3)[None, :] + shift[:, None]) % 3
        rows = np.arange(len(Tm))[:, None]
        return Tm[rows, cols], sm[rows, cols], cm[rows, cols]

    n_neg = (s_c < 0.0).sum(axis=1)
    m1 = n_neg == 1
    m2 = n_neg == 2
    r1 = _rot(m1, np.argmax(s_c[m1] < 0.0, axis=1)) if np.any(m1) else None
    r2 = _rot(m2, (np.argmax(s_c[m2] > 0.0, axis=1) + 1) % 3) if np.any(m2) else None
    return lo_u, hi_u, t_cut, r1, r2


def _recortar_semi_espaco(
    V: np.ndarray, T: np.ndarray, s: np.ndarray, plane_w: float | None = None, eps: float = 1e-12
) -> tuple[np.ndarray, np.ndarray]:
    """Recorta malha (V, T) mantendo a regiao s <= 0."""
    if len(T) == 0 or len(V) == 0:
        return V, T
    s_snap = np.where(np.abs(s) <= eps, 0.0, s)
    st = s_snap[T]
    has_neg = (st < 0.0).any(axis=1)
    has_pos = (st > 0.0).any(axis=1)
    keep_mask = (~has_pos) & has_neg
    tris_out = [T[keep_mask]]

    all_zer = (~has_pos) & (~has_neg)
    if np.any(all_zer):
        Tz = T[all_zer]
        nV = len(V)

        def _arestas_tri(Tt: np.ndarray) -> np.ndarray:
            if len(Tt) == 0:
                return np.zeros(0, dtype=np.int64)
            ea = Tt
            eb = np.roll(Tt, -1, axis=1)
            lo = np.minimum(ea, eb).ravel()
            hi = np.maximum(ea, eb).ravel()
            return lo.astype(np.int64) * nV + hi

        pos_e = _arestas_tri(T[(~has_neg) & has_pos])
        neg_e = _arestas_tri(T[keep_mask])
        only_pos = np.setdiff1d(pos_e, neg_e)
        if len(only_pos):
            ez = _arestas_tri(Tz).reshape(-1, 3)
            Tz = Tz[~np.isin(ez, only_pos).any(axis=1)]
        if len(Tz):
            tris_out.append(Tz)

    V_out = V
    cross = has_neg & has_pos
    if np.any(cross):
        nV = len(V)
        lo_u, hi_u, t_cut, r1, r2 = _cruzar_plano(T[cross], s, st[cross], nV)
        V_cut = V[lo_u] + t_cut[:, None] * (V[hi_u] - V[lo_u])
        if plane_w is not None:
            V_cut[:, 2] = plane_w
        V_out = np.vstack([V, V_cut])
        if r1 is not None:
            T1, s1, c1 = r1
            p1 = np.where(s1[:, 1] == 0.0, T1[:, 1], nV + np.maximum(c1[:, 0], 0))
            p2 = np.where(s1[:, 2] == 0.0, T1[:, 2], nV + np.maximum(c1[:, 2], 0))
            tris_out.append(np.stack([T1[:, 0], p1, p2], axis=1))
        if r2 is not None:
            T2, _, c2 = r2
            tris_out.append(np.stack([T2[:, 0], T2[:, 1], nV + c2[:, 1]], axis=1))
            tris_out.append(np.stack([T2[:, 0], nV + c2[:, 1], nV + c2[:, 2]], axis=1))

    T_res = np.concatenate(tris_out, axis=0) if tris_out else np.zeros((0, 3), dtype=np.int64)
    if len(T_res) == 0:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int64)
    return V_out, T_res


def _segmentos_corte_plano(P: np.ndarray, Tw: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Extrai segmentos 2D (K, 2, 2) em (u, v) da intersecao da malha com w = 0."""
    if len(Tw) == 0 or len(P) == 0:
        return np.zeros((0, 2, 2), dtype=np.float64)
    w_raw = P[:, 2]
    w = np.where(np.abs(w_raw) <= eps, 0.0, w_raw)
    if not ((w > 0.0).any() and (w < 0.0).any()):
        return np.zeros((0, 2, 2), dtype=np.float64)

    nP = len(P)
    sw = w[Tw]
    has_neg = (sw < 0.0).any(axis=1)
    has_pos = (sw > 0.0).any(axis=1)
    segs_list: list[np.ndarray] = []

    cross = has_neg & has_pos
    if np.any(cross):
        lo_u, hi_u, t_cut, r1, r2 = _cruzar_plano(Tw[cross], w_raw, sw[cross], nP)
        pts_u = P[lo_u, :2] + t_cut[:, None] * (P[hi_u, :2] - P[lo_u, :2])
        if r1 is not None:
            T1, s1, c1 = r1
            pA = np.where((s1[:, 1] == 0.0)[:, None], P[T1[:, 1], :2], pts_u[np.maximum(c1[:, 0], 0)])
            pB = np.where((s1[:, 2] == 0.0)[:, None], P[T1[:, 2], :2], pts_u[np.maximum(c1[:, 2], 0)])
            segs_list.append(np.stack([pA, pB], axis=1))
        if r2 is not None:
            _, _, c2 = r2
            segs_list.append(np.stack([pts_u[c2[:, 1]], pts_u[c2[:, 2]]], axis=1))

    z_cnt = (sw == 0.0).sum(axis=1)
    seam_neg = (~has_pos) & has_neg & (z_cnt == 2)
    seam_pos = (~has_neg) & has_pos & (z_cnt == 2)
    if np.any(seam_neg) and np.any(seam_pos):
        def _chaves_costura(mask: np.ndarray) -> np.ndarray:
            Ts = Tw[mask]
            ss = sw[mask]
            idx_nz = np.argmax(ss != 0.0, axis=1)
            rows = np.arange(len(Ts))
            va = Ts[rows, (idx_nz + 1) % 3]
            vb = Ts[rows, (idx_nz + 2) % 3]
            lo = np.minimum(va, vb)
            hi = np.maximum(va, vb)
            return lo.astype(np.int64) * nP + hi

        kn, cn = np.unique(_chaves_costura(seam_neg), return_counts=True)
        kp, cp = np.unique(_chaves_costura(seam_pos), return_counts=True)
        comuns, i_n, i_p = np.intersect1d(kn, kp, return_indices=True)
        if len(comuns):
            mult = np.minimum(cn[i_n], cp[i_p])  # pecas encostadas repetem a costura: um segmento por par
            comuns = np.repeat(comuns, mult)
            lo_s = comuns // nP
            hi_s = comuns % nP
            segs_list.append(np.stack([P[lo_s, :2], P[hi_s, :2]], axis=1))

    if not segs_list:
        return np.zeros((0, 2, 2), dtype=np.float64)
    segs = np.concatenate(segs_list, axis=0)
    ok = np.hypot(*(segs[:, 1] - segs[:, 0]).T) > eps
    return segs[ok]
