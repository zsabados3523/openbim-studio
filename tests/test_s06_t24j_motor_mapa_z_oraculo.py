# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24j (T3): otimizacoes do motor de visibilidade sem mudar o resultado.

Alvo 1: mapa Z conservador calculado 1 vez por chave (trava ou pre-calculo antes do pool em
`linhas_visiveis_multi`), sem corrida entre threads e sem deadlock.
Alvo 2: em `visib_mapa._filtrar_e_recortar`, filtrar por Z e caixa XY antes de `_dedup_int64`
preservando exatamente o mesmo conjunto final de pares e a mesma saida.

Nao editar este arquivo durante a implementacao da T24j.
"""
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

_MAPA_Z_REAL = visib_mapa._mapa_z_conservador
_TOL_COORD = 1e-9
_F_CAIXA = np.array(
    [
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6],
        [3, 0, 4], [3, 4, 7],
    ],
    dtype=np.int64,
)


# ---------------------------------------------------------------------------
# Copia literal da implementacao atual (referencia imutavel do oraculo)
# ---------------------------------------------------------------------------

def _filtrar_e_recortar_ref(
    pe, pt, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_l,
):
    """Copia literal de visib_mapa._filtrar_e_recortar antes da T24j (dedup-primeiro)."""
    if not len(pe):
        return
    ch = _dedup_int64(pe.astype(np.int64) * nt_all + pt)
    pe = ch // nt_all
    pt = ch % nt_all
    m = (
        (tzmax[pt] > ezmin[pe] + tol_z) & (tx1[pt] >= ex0[pe]) & (tx0[pt] <= ex1[pe])
        & (ty1[pt] >= ey0[pe]) & (ty0[pt] <= ey1[pe])
    )
    if not np.any(m):
        return
    pe = pe[m]
    pt = pt[m]
    tv_p = tv[pt]
    a_sh = (ea[pe] == tv_p[:, 0]) | (ea[pe] == tv_p[:, 1]) | (ea[pe] == tv_p[:, 2])
    b_sh = (eb[pe] == tv_p[:, 0]) | (eb[pe] == tv_p[:, 1]) | (eb[pe] == tv_p[:, 2])
    if np.any(a_sh | b_sh):
        skip = np.zeros(len(pe), dtype=bool)
        if np.any(a_sh):
            pa, qa = pe[a_sh], pt[a_sh]
            z_b = A[qa, 2] + gx[qa] * (b[pa, 0] - A[qa, 0]) + gy[qa] * (b[pa, 1] - A[qa, 1])
            skip[a_sh] = b[pa, 2] >= z_b - tol_z
        if np.any(b_sh):
            pb, qb = pe[b_sh], pt[b_sh]
            z_a = A[qb, 2] + gx[qb] * (a[pb, 0] - A[qb, 0]) + gy[qb] * (a[pb, 1] - A[qb, 1])
            skip[b_sh] |= a[pb, 2] >= z_a - tol_z
        pe = pe[~skip]
        pt = pt[~skip]
    if not len(pe):
        return
    p0x = a[pe, 0]
    p0y = a[pe, 1]
    dx = d[pe, 0]
    dy = d[pe, 1]
    len2d = np.hypot(dx, dy)
    lo = np.zeros(len(pe))
    hi = np.ones(len(pe))
    eps = abs(d_eps)
    lo, hi = _aplicar_corte(dx, tx0[pt] - eps - p0x, lo, hi, -1.0)
    lo, hi = _aplicar_corte(-dx, p0x - tx1[pt] - eps, lo, hi, -1.0)
    lo, hi = _aplicar_corte(dy, ty0[pt] - eps - p0y, lo, hi, -1.0)
    lo, hi = _aplicar_corte(-dy, p0y - ty1[pt] - eps, lo, hi, -1.0)
    ok = (hi - lo) * len2d > 1e-5
    if not np.any(ok):
        return
    if not ok.all():
        pe, pt, p0x, p0y, dx, dy, len2d, lo, hi = (
            x[ok] for x in (pe, pt, p0x, p0y, dx, dy, len2d, lo, hi)
        )
    for ii in range(3):
        s_i = nx_[pt, ii] * dx + ny_[pt, ii] * dy
        r_i = d_eps - (nx_[pt, ii] * p0x + ny_[pt, ii] * p0y + cc_[pt, ii])
        lo, hi = _aplicar_corte(s_i, r_i, lo, hi, -1.0)
    ok = (hi - lo) * len2d > 1e-5
    if not np.any(ok):
        return
    if not ok.all():
        pe, pt, p0x, p0y, dx, dy, len2d, lo, hi = (
            x[ok] for x in (pe, pt, p0x, p0y, dx, dy, len2d, lo, hi)
        )
    G0 = A[pt, 2] + gx[pt] * (p0x - A[pt, 0]) + gy[pt] * (p0y - A[pt, 1]) - a[pe, 2] - tol_z
    lo, hi = _aplicar_corte(gx[pt] * dx + gy[pt] * dy - d[pe, 2], -G0, lo, hi, -1.0, eq_fail=True)
    v = (hi - lo) * len2d > 1e-5
    if np.any(v):
        H_l.append(_unir_intervalos(pe[v], lo[v], hi[v]))
        if len(H_l) > 1 and sum(len(x[0]) for x in H_l[1:]) >= max(1_500_000, len(H_l[0][0])):
            _compactar_H(H_l)


def _visibilidade_hibrida_ref(
    P, Tw, a, b, ea, eb, tol_z: float, d_eps: float, min_len: float, prep=None, memo=None
) -> np.ndarray:
    """Copia literal de visibilidade._visibilidade_hibrida antes da T24j (trecho do memo + filtro antigo)."""
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, area2 = (
        prep if prep is not None else _preparar_triangulos(P, Tw)
    )
    mn_x = float(min(a[:, 0].min(), b[:, 0].min(), tx0.min() if len(A) else math.inf))
    mn_y = float(min(a[:, 1].min(), b[:, 1].min(), ty0.min() if len(A) else math.inf))
    mx_x = float(max(a[:, 0].max(), b[:, 0].max(), tx1.max() if len(A) else -math.inf))
    mx_y = float(max(a[:, 1].max(), b[:, 1].max(), ty1.max() if len(A) else -math.inf))
    dx_dom = max(mx_x - mn_x, 0.0)
    dy_dom = max(mx_y - mn_y, 0.0)
    g = max(0.002, math.sqrt(dx_dom * dy_dom / 5_500_000.0), (dx_dom + dy_dom) / 2_900_000.0)
    while (math.ceil(dx_dom / g) + 2) * (math.ceil(dy_dom / g) + 2) > 6_000_000:
        g *= 1.05
    chave = (mn_x, mn_y, mx_x, mx_y, g)
    entrada = memo.get(chave) if memo is not None else None
    if entrada is not None:
        z_full, zf_flat, W, H, kept_idx = entrada
    else:
        z_full, W, H = _MAPA_Z_REAL(
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
        if memo is not None:
            z_full, zf_flat, W, H, kept_idx = memo.setdefault(
                chave, (z_full, zf_flat, W, H, kept_idx)
            )
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
    n_ref = len(kept_idx)
    if len(ek_idx) and len(kept_idx):
        kept_idx = _cull_tris(kept_idx, a[ek_idx], b[ek_idx], tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
    ex0 = np.minimum(a[:, 0], b[:, 0])
    ex1 = np.maximum(a[:, 0], b[:, 0])
    ey0 = np.minimum(a[:, 1], b[:, 1])
    ey1 = np.maximum(a[:, 1], b[:, 1])
    ezmin = np.minimum(a[:, 2], b[:, 2])
    ctx = (A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, ea, eb, ex0, ex1, ey0, ey1, ezmin)
    with mock.patch.object(visib_faixas, "_filtrar_e_recortar", _filtrar_e_recortar_ref):
        rem_t = visib_faixas._passagem_faixas_orientadas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z, d_eps, ctx, H_l)
    cg = g
    nt_all = len(A)
    while len(rem_t) and len(ek_idx):
        Wc = int(math.ceil(dx_dom / cg)) + 2
        Hc = int(math.ceil(dy_dom / cg)) + 2
        ncel = Wc * Hc
        lim_c = min(400, max(50, 3_000_000 // max(len(rem_t), n_ref)))
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
                    t_iy, t_ix = tcel // Wc, tcel % Wc
                    bx0, by0 = int(t_ix.min()), int(t_iy.min())
                    Wl = int(t_ix.max()) - bx0 + 1
                    Hl = int(t_iy.max()) - by0 + 1
                    ncel_l = Wl * Hl
                    tcel = (t_iy - by0) * Wl + (t_ix - bx0)
                    ord_t = np.argsort(tcel, kind="stable")
                    tri_por_cel = tobj[ord_t]
                    cel_ord = tcel[ord_t]
                    cont = np.bincount(cel_ord, minlength=ncel_l)
                    ini_cel = np.cumsum(cont) - cont
                    cell_tzmax = np.full(ncel_l, -np.inf)
                    np.maximum.at(cell_tzmax, cel_ord, tzmax[tri_por_cel])
                    for e0, e1 in _fatias(nsub_c, 400_000):
                        ec = ek_idx[e0:e1]
                        s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
                            a[ec], d[ec], nsub_c[e0:e1], mn_x, mn_y, cg, Wc, Hc
                        )
                        sx0 = np.maximum(sx0, bx0); sx1 = np.minimum(sx1, bx0 + Wl - 1)
                        sy0 = np.maximum(sy0, by0); sy1 = np.minimum(sy1, by0 + Hl - 1)
                        okb = (sx1 >= sx0) & (sy1 >= sy0)
                        s_l, sa, sb = s_l[okb], sa[okb], sb[okb]
                        sobj, scel = _expandir_celulas(sx0[okb] - bx0, sx1[okb] - bx0, sy0[okb] - by0, sy1[okb] - by0, Wl)
                        ok_sc = cell_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
                        eobj = ec[s_l[sobj[ok_sc]]]
                        ecel = scel[ok_sc]
                        if not len(eobj):
                            continue
                        ch_ec = _dedup_int64(eobj.astype(np.int64) * ncel_l + ecel)
                        eobj = ch_ec // ncel_l
                        ecel = ch_ec % ncel_l
                        ntri_par = cont[ecel]
                        nz = ntri_par > 0
                        eobj = eobj[nz]
                        ecel = ecel[nz]
                        ntri_par = ntri_par[nz]
                        for p0, p1 in _fatias(ntri_par, 200_000, chaves=eobj):
                            g3, kk = _rle_idx(ntri_par[p0:p1])
                            pe = eobj[p0:p1][g3]
                            pt = tri_por_cel[ini_cel[ecel[p0:p1]][g3] + kk]
                            _filtrar_e_recortar_ref(
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


def _preparar_cena(pecas, *, angulo_graus: float = 0.001, min_len: float = 1e-4):
    """Pre-processamento identico a linhas_visiveis_multi para testes diretos e referencia."""
    pecas_l = list(pecas)
    limpas = [_limpar_malha(v, t) for v, t in pecas_l]
    v_parts, offsets, v_off = [], [], 0
    for item in limpas:
        offsets.append(None if item is None else (v_off, item[1]))
        if item is not None:
            v_parts.append(item[0])
            v_off += len(item[0])
    if not v_parts:
        return None
    V_all = v_parts[0] if len(v_parts) == 1 else np.vstack(v_parts)
    _, idx, inv = np.unique(
        np.round(V_all / 1e-6).astype(np.int64), axis=0, return_index=True, return_inverse=True
    )
    P, inv_flat = V_all[idx], inv.ravel()
    cands, tw_oks = [None] * len(pecas_l), []
    for i, off_t in enumerate(offsets):
        if off_t is None:
            continue
        Tw_i = _dedup_triangulos(inv_flat[off_t[1] + off_t[0]])
        if len(Tw_i) == 0:
            continue
        a, b, ang, silh, Tw_ok_i, ea, eb = _arestas_candidatas(P, Tw_i)
        if len(Tw_ok_i):
            tw_oks.append(Tw_ok_i)
        m = ((ang >= angulo_graus) | silh) & (np.hypot(*(b - a)[:, :2].T) > min_len)
        if np.any(m):
            cands[i] = (a[m], b[m], ea[m], eb[m])
    ativos = [(i, c) for i, c in enumerate(cands) if c is not None]
    if not tw_oks or not ativos:
        return None
    Tw_comb = tw_oks[0] if len(tw_oks) == 1 else _dedup_triangulos(np.vstack(tw_oks))
    prep = _preparar_triangulos(P, Tw_comb)
    return len(pecas_l), P, Tw_comb, ativos, prep


def _linhas_visiveis_multi_ref(
    pecas, *, angulo_graus: float = 0.001, tol_z: float = 1e-4, min_len: float = 1e-4
) -> list[list[np.ndarray]]:
    """Referencia sequencial usando a copia literal do motor pre-T24j."""
    pecas_l = list(pecas)
    if not pecas_l:
        return []
    dados = _preparar_cena(pecas_l, angulo_graus=angulo_graus, min_len=min_len)
    if dados is None:
        return [[] for _ in pecas_l]
    n_pecas, P, Tw_comb, ativos, prep = dados
    memo = {}
    res: list[list[np.ndarray]] = [[] for _ in range(n_pecas)]
    for i, c in ativos:
        res[i] = list(_visibilidade_hibrida_ref(P, Tw_comb, *c, tol_z, -1e-6, min_len, prep=prep, memo=memo))
    return res
