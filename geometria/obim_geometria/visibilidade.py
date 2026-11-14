# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de linhas visiveis por malha (vista de cima, z-buffer conservador + recorte analitico)."""
from __future__ import annotations

import math
import numpy as np

from obim_geometria.visib_base import (
    _arestas_candidatas,
    _cel_caixa,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_faixas import _passagem_faixas_orientadas
from obim_geometria.visib_mapa import (
    _compactar_H,
    _filtrar_e_recortar,
    _mapa_z_conservador,
    _varrer_cels_triangulos,
)


def _visibilidade_hibrida(P, Tw, a, b, ea, eb, tol_z: float, d_eps: float, min_len: float) -> np.ndarray:
    """Combina z-buffer conservador em grade adaptativa com recorte analitico exato em blocos."""
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, area2 = _preparar_triangulos(P, Tw)
    mn_x = float(min(a[:, 0].min(), b[:, 0].min(), tx0.min() if len(A) else math.inf))
    mn_y = float(min(a[:, 1].min(), b[:, 1].min(), ty0.min() if len(A) else math.inf))
    mx_x = float(max(a[:, 0].max(), b[:, 0].max(), tx1.max() if len(A) else -math.inf))
    mx_y = float(max(a[:, 1].max(), b[:, 1].max(), ty1.max() if len(A) else -math.inf))
    dx_dom = max(mx_x - mn_x, 0.0)
    dy_dom = max(mx_y - mn_y, 0.0)
    g = max(0.002, math.sqrt(dx_dom * dy_dom / 5_500_000.0), (dx_dom + dy_dom) / 2_900_000.0)
    while (math.ceil(dx_dom / g) + 2) * (math.ceil(dy_dom / g) + 2) > 6_000_000:
        g *= 1.05
    z_full, W, H = _mapa_z_conservador(
        A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, mx_x, mx_y, g
    )
    tx0i, tx1i, ty0i, ty1i = _cel_caixa(tx0, tx1, ty0, ty1, mn_x, mn_y, g, W, H)
    idx_s = np.nonzero((tx1i - tx0i + 1) * (ty1i - ty0i + 1) <= 25)[0]
    tri_keep = np.ones(len(A), bool)
    zf_flat = z_full.ravel()
    tri_keep[idx_s] = False
    for k0 in range(0, len(idx_s), 50_000):
        sl = idx_s[k0:k0 + 50_000]
        tobj, tcel = _expandir_celulas(tx0i[sl], tx1i[sl], ty0i[sl], ty1i[sl], W)
        np.logical_or.at(tri_keep, sl[tobj], tzmax[sl[tobj]] >= zf_flat[tcel] - 1e-9)
    kept_idx = np.nonzero(tri_keep)[0]
    d = b - a
    step_g = 0.999 * g
    nsub_g = np.maximum(1, np.ceil(np.maximum(np.abs(d[:, 0]), np.abs(d[:, 1])) / step_g).astype(np.int64))
    H_l = []
    ek_mask = np.zeros(len(a), bool)
    for e0, e1 in _fatias(nsub_g, 500_000):
        s_l, t0_s, t1_s, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
            a[e0:e1], d[e0:e1], nsub_g[e0:e1], mn_x, mn_y, g, W, H
        )
        s_id = s_l + e0
        z_min_4 = np.minimum(
            np.minimum(z_full[sy0, sx0], z_full[sy0, sx1]), np.minimum(z_full[sy1, sx0], z_full[sy1, sx1])
        )
        sub_keep = np.maximum(sa[:, 2], sb[:, 2]) >= z_min_4 - tol_z
        ek_mask[s_id[sub_keep]] = True
        hid = ~sub_keep
        if np.any(hid):
            starts = hid.copy()
            ends = hid.copy()
            starts[1:] &= (~hid[:-1]) | (s_id[1:] != s_id[:-1])
            ends[:-1] &= (~hid[1:]) | (s_id[:-1] != s_id[1:])
            H_l.append((s_id[starts], t0_s[starts], t1_s[ends]))
    ek_idx = np.nonzero(ek_mask)[0]
    ex0 = np.minimum(a[:, 0], b[:, 0])
    ex1 = np.maximum(a[:, 0], b[:, 0])
    ey0 = np.minimum(a[:, 1], b[:, 1])
    ey1 = np.maximum(a[:, 1], b[:, 1])
    ezmin = np.minimum(a[:, 2], b[:, 2])
    ctx = (A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, ea, eb, ex0, ex1, ey0, ey1, ezmin)
    rem_t = _passagem_faixas_orientadas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z, d_eps, ctx, H_l)
    cg = g
    nt_all = len(A)
    while len(rem_t) and len(ek_idx):
        Wc = int(math.ceil(dx_dom / cg)) + 2
        Hc = int(math.ceil(dy_dom / cg)) + 2
        ncel = Wc * Hc
        lim_c = min(400, max(50, 3_000_000 // len(rem_t)))
        if ncel <= lim_c:
            cand_m = np.ones(len(rem_t), bool)
        else:
            tx0c, tx1c, ty0c, ty1c = _cel_caixa(
                tx0[rem_t], tx1[rem_t], ty0[rem_t], ty1[rem_t], mn_x, mn_y, cg, Wc, Hc
            )
            cand_m = (
                (ty1c - ty0c + 1 <= lim_c) & (tx1c - tx0c + 1 <= lim_c)
                & (area2[rem_t] <= lim_c * cg * cg)
            )
        cand = rem_t[cand_m]
        next_rem = [rem_t[~cand_m]]
        if len(cand):
            cov, loc_s, iy_s, ix0_s, ix1_s = _varrer_cels_triangulos(
                cand, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, cg, Wc, Hc
            )
            keep_c = (cov <= lim_c) | (ncel <= lim_c)
            next_rem.append(cand[~keep_c])
            ok_s = keep_c[loc_s]
            if np.any(ok_s):
                t_s = cand[loc_s[ok_s]]
                iy_s = iy_s[ok_s]
                ix0_s = ix0_s[ok_s]
                ix1_s = ix1_s[ok_s]
                w_s = ix1_s - ix0_s + 1
                step_c = 0.999 * cg
                span_e = np.maximum(np.abs(d[ek_idx, 0]), np.abs(d[ek_idx, 1]))
                nsub_c = np.maximum(1, np.ceil(span_e / step_c).astype(np.int64))
                for t0, t1 in _fatias(w_s, 2_000_000):
                    g_s, dx_s = _rle_idx(w_s[t0:t1])
                    tobj = t_s[t0:t1][g_s]
                    tcel = iy_s[t0:t1][g_s] * Wc + ix0_s[t0:t1][g_s] + dx_s
                    if cg == g:
                        ok_tc = tzmax[tobj] >= zf_flat[tcel] - 1e-9
                        tobj = tobj[ok_tc]
                        tcel = tcel[ok_tc]
                    if not len(tobj):
                        continue
                    ord_t = np.argsort(tcel, kind="stable")
                    tri_por_cel = tobj[ord_t]
                    cel_ord = tcel[ord_t]
                    cont = np.bincount(cel_ord, minlength=ncel)
                    ini_cel = np.cumsum(cont) - cont
                    cell_tzmax = np.full(ncel, -np.inf)
                    np.maximum.at(cell_tzmax, cel_ord, tzmax[tri_por_cel])
                    for e0, e1 in _fatias(nsub_c, 400_000):
                        ec = ek_idx[e0:e1]
                        s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
                            a[ec], d[ec], nsub_c[e0:e1], mn_x, mn_y, cg, Wc, Hc
                        )
                        sobj, scel = _expandir_celulas(sx0, sx1, sy0, sy1, Wc)
                        ok_sc = cell_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
                        eobj = ec[s_l[sobj[ok_sc]]]
                        ecel = scel[ok_sc]
                        if not len(eobj):
                            continue
                        ch_ec = np.unique(eobj.astype(np.int64) * ncel + ecel)
                        eobj = ch_ec // ncel
                        ecel = ch_ec % ncel
                        ntri_par = cont[ecel]
                        nz = ntri_par > 0
                        eobj = eobj[nz]
                        ecel = ecel[nz]
                        ntri_par = ntri_par[nz]
                        # shortcut: pares por celula tem custo ~N^2 por ancora comum (vertice muito usado);
                        # limite pratico ~1000 arestas no mesmo vertice
                        # (cone 4096 lados = 17 s; max IFC real = 128).
                        for p0, p1 in _fatias(ntri_par, 2_000_000):
                            g3, kk = _rle_idx(ntri_par[p0:p1])
                            pe = eobj[p0:p1][g3]
                            pt = tri_por_cel[ini_cel[ecel[p0:p1]][g3] + kk]
                            _filtrar_e_recortar(
                                pe, pt, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                                tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                                tol_z, d_eps, H_l,
                            )
        rem_t = np.concatenate(next_rem)
        cg *= 4.0
    He, Hlo, Hhi = _compactar_H(H_l, limpar=True)
    sem = np.ones(len(a), bool)
    sem[He] = False
    idx_sem = np.nonzero(sem)[0]
    V_l = [(idx_sem, np.zeros(len(idx_sem)), np.ones(len(idx_sem)))]
    if len(He):
        novo = np.concatenate([[True], He[1:] != He[:-1]])
        ultimo = np.concatenate([He[1:] != He[:-1], [True]])
        ini_t = np.where(novo, 0.0, np.concatenate([[0.0], Hhi[:-1]]))
        fim_t = Hhi[ultimo]
        gap = Hlo - ini_t > 1e-9
        gl = fim_t < 1.0 - 1e-9
        V_l.append((He[gap], ini_t[gap], Hlo[gap]))
        V_l.append((He[ultimo][gl], fim_t[gl], np.ones(int(gl.sum()))))
    pe_, t0_, t1_ = (np.concatenate(x) for x in zip(*V_l))
    s0 = a[pe_, :2] + t0_[:, None] * d[pe_, :2]
    s1 = a[pe_, :2] + t1_[:, None] * d[pe_, :2]
    ok2 = np.hypot(*(s1 - s0).T) > min_len
    return np.stack([s0[ok2], s1[ok2]], axis=1)


def linhas_visiveis(
    verts: np.ndarray,
    tris: np.ndarray,
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
) -> list[np.ndarray]:
    """Retorna polilinhas 2D (K, 2) das arestas relevantes da malha.

    A vista e sempre de cima (+Z); quem chama gira a malha para outras
    vistas (corte e vistas laterais ficam na T19d).
    """
    for nome, val in (("angulo_graus", angulo_graus), ("tol_z", tol_z), ("min_len", min_len)):
        fv = float(val)
        if not (math.isfinite(fv) and fv >= 0.0):
            raise ValueError(f"{nome} deve ser nao-negativo e finito")
    if float(min_len) < 1e-5:
        raise ValueError("min_len deve ser >= 1e-5")
    V = np.asarray(verts, dtype=np.float64)
    T_raw = np.asarray(tris)
    if V.ndim != 2 or V.shape[1] != 3:
        raise ValueError("verts deve ter formato (N, 3) de vertices")
    if T_raw.ndim != 2 or T_raw.shape[1] != 3 or not np.issubdtype(T_raw.dtype, np.integer):
        raise ValueError("tris deve ter formato (M, 3) de indices inteiros de triangulos")
    if len(T_raw) == 0:
        return []
    T = T_raw.astype(np.int64, copy=False)
    if len(V) == 0 or T.min() < 0 or T.max() >= len(V):
        raise ValueError("tris contem indice de vertice fora dos limites")
    fin_v = np.isfinite(V).all(axis=1)
    T = T[fin_v[T].all(axis=1)]
    if len(T) == 0:
        return []
    if not fin_v.all():
        V = V[fin_v]
        T = (np.cumsum(fin_v, dtype=np.int64) - 1)[T]
    if np.abs(V).max() > 1e12:
        raise ValueError("coordenadas de verts excedem o limite de 1e12")
    _, idx, inv = np.unique(
        np.round(V / 1e-6).astype(np.int64), axis=0, return_index=True, return_inverse=True
    )
    P = V[idx]
    Tw = inv.ravel()[T]
    Tw = Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])]
    if len(Tw) == 0:
        return []
    _, u_idx = np.unique(np.sort(Tw, axis=1), axis=0, return_index=True)
    Tw = Tw[np.sort(u_idx)]
    a, b, ang, silh, Tw_ok, ea, eb = _arestas_candidatas(P, Tw)
    m = ((ang >= angulo_graus) | silh) & (np.hypot(*(b - a)[:, :2].T) > min_len)
    if not np.any(m):
        return []
    return list(_visibilidade_hibrida(P, Tw_ok, a[m], b[m], ea[m], eb[m], tol_z, -1e-6, min_len))
