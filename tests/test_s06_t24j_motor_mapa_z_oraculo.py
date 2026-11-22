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


# ---------------------------------------------------------------------------
# Normalizacao canonica, hash SHA-256 e geradores de cenas sinteticas
# ---------------------------------------------------------------------------

def _canon_peca(pls: list[np.ndarray]) -> list[np.ndarray]:
    """Arredonda polilinhas a 1e-9 (eliminando -0.0) e ordena canonicamente."""
    if not pls:
        return []
    norm = [np.round(np.asarray(p, dtype=np.float64), 9) + 0.0 for p in pls]
    chaves = [
        (len(p), *p[0].tolist(), *p[-1].tolist(), *p.ravel().tolist())
        for p in norm
    ]
    ordem = sorted(range(len(norm)), key=chaves.__getitem__)
    return [norm[i] for i in ordem]


def _hash_resultado(res: list[list[np.ndarray]]) -> str:
    """SHA-256 deterministico do resultado normalizado (polilinhas arredondadas a 1e-9)."""
    h = hashlib.sha256()
    h.update(f"N:{len(res)}\n".encode())
    for i, pls in enumerate(res):
        c = _canon_peca(pls)
        h.update(f"P:{i}:{len(c)}\n".encode())
        for arr in c:
            h.update(f"L:{arr.shape[0]}:{arr.shape[1]}:".encode())
            h.update(np.ascontiguousarray(arr, dtype="<f8").tobytes())
    return h.hexdigest()


def _assert_equivalente(obtido, esperado, *, contexto: str = ""):
    assert _hash_resultado(obtido) == _hash_resultado(esperado), f"SHA-256 divergiu ({contexto})"
    assert len(obtido) == len(esperado), f"num pecas divergiu ({contexto})"
    for i, (pa, pb) in enumerate(zip(obtido, esperado)):
        ca, cb = _canon_peca(pa), _canon_peca(pb)
        assert [len(x) for x in ca] == [len(x) for x in cb], f"peca {i} contagem ({contexto})"
        if ca:
            dif = np.abs(np.concatenate(ca) - np.concatenate(cb)).max()
            assert dif <= _TOL_COORD, f"peca {i} diff={dif:.3e} ({contexto})"


def _comprimento_total(pls: list[np.ndarray]) -> float:
    return float(sum(np.hypot(*np.diff(p, axis=0).T).sum() for p in pls))


def _rz(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _ry(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _caixa(x0, y0, z0, x1, y1, z1, *, rot_z: float = 0.0, incl_y: float = 0.0):
    cx, cy, cz = (x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    v = np.array(
        [[x, y, z] for z in (-0.5, 0.5) for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))],
        dtype=np.float64,
    ) * np.array([sx, sy, sz], dtype=np.float64)
    r = _rz(rot_z) @ _ry(incl_y)
    return v @ r.T + np.array([cx, cy, cz], dtype=np.float64), _F_CAIXA.copy()


def _placa_com_furo(x0, y0, x1, y1, fx0, fy0, fx1, fy1, z0, z1):
    """Laje fechada com furo retangular passante (anel no topo/fundo + paredes externas e do furo)."""
    ext = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    furo = [(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)]
    v = np.array([(x, y, z) for z in (z0, z1) for (x, y) in ext + furo], dtype=np.float64)
    t = []
    for k in range(4):
        k1 = (k + 1) % 4
        ok, ok1, ik, ik1 = k, k1, 4 + k, 4 + k1
        t += [(8 + ok, 8 + ok1, 8 + ik1), (8 + ok, 8 + ik1, 8 + ik)]
        t += [(ok, ik1, ok1), (ok, ik, ik1)]
        t += [(ok, ok1, 8 + ok1), (ok, 8 + ok1, 8 + ok)]
        t += [(ik, 8 + ik1, ik1), (ik, 8 + ik, 8 + ik1)]
    return v, np.array(t, dtype=np.int64)


def _parede_com_abertura_x(x0, x1, y0, y1, z0, z1, ax0, ax1, az0, az1):
    """Parede ao longo de X com vao retangular (4 blocos fechados como 1 peca)."""
    blocos = [
        _caixa(x0, y0, z0, ax0, y1, z1),
        _caixa(ax1, y0, z0, x1, y1, z1),
        _caixa(ax0, y0, az1, ax1, y1, z1),
    ]
    if az0 > z0 + 1e-6:
        blocos.append(_caixa(ax0, y0, z0, ax1, y1, az0))
    vs, ts, off = [], [], 0
    for vb, tb in blocos:
        vs.append(vb)
        ts.append(tb + off)
        off += len(vb)
    return np.vstack(vs), np.vstack(ts)


def _quad_vertical(x0, y0, x1, y1, z0, z1):
    """Painel puramente vertical (sem triangulos horizontais: fora da caixa de `prep`, muda `chave`)."""
    v = np.array([[x0, y0, z0], [x1, y1, z0], [x1, y1, z1], [x0, y0, z1]], dtype=np.float64)
    t = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return v, t


def _tiras(x0, y0, comp, larg, n, th, z0, incl):
    q = np.array([[x0, y0 + i * larg] for i in range(n)], dtype=np.float64)
    pts = np.concatenate([[[a, b], [a + comp, b], [a + comp, b + larg], [a, b + larg]] for a, b in q])
    v = np.c_[pts, z0 + incl * pts[:, 1]]
    k = np.arange(n, dtype=np.int64)[:, None] * 4
    t = np.concatenate([k + [0, 1, 2], k + [0, 2, 3]]).reshape(2, n, 3).transpose(1, 0, 2).reshape(-1, 3)
    return v @ _rz(th).T, t


def _cena_casa_paredes_lajes_buracos():
    """Cena residencial sintetica: piso, paredes com aberturas, laje com buracos, pecas escondidas e visiveis."""
    pecas = [
        _caixa(0.0, 0.0, -0.2, 12.0, 9.0, 0.0),  # piso
        _parede_com_abertura_x(0.0, 12.0, 0.0, 0.2, 0.0, 3.0, 2.0, 3.2, 0.0, 2.1),  # parede sul c/ porta
        _parede_com_abertura_x(0.0, 12.0, 8.8, 9.0, 0.0, 3.0, 5.0, 7.0, 1.0, 2.2),  # parede norte c/ janela
        _caixa(0.0, 0.2, 0.0, 0.2, 8.8, 3.0),  # parede oeste
        _caixa(11.8, 0.2, 0.0, 12.0, 8.8, 3.0),  # parede leste
        _caixa(5.8, 0.2, 0.0, 6.0, 6.5, 2.8),  # divisoria interna
        _caixa(0.2, 4.4, 0.0, 4.5, 4.6, 2.8),  # divisoria interna 2
        _placa_com_furo(0.0, 0.0, 6.5, 9.0, 1.5, 1.5, 4.0, 3.8, 3.0, 3.25),  # laje oeste com buraco de escada
        _placa_com_furo(6.5, 0.0, 12.0, 9.0, 8.0, 4.5, 10.2, 7.0, 3.0, 3.25),  # laje leste com claraboia
        _caixa(2.0, 2.0, 0.0, 3.4, 3.2, 0.8),  # mesa visivel pelo buraco oeste
        _caixa(8.5, 5.0, 0.0, 9.8, 6.4, 1.1),  # bancada visivel pelo buraco leste
        _caixa(0.8, 6.0, 0.0, 2.5, 7.5, 0.9),  # movel totalmente escondido sob laje oeste
        _caixa(7.0, 1.0, 0.0, 9.0, 2.6, 1.0),  # movel totalmente escondido sob laje leste
        _caixa(3.5, 2.8, 0.0, 5.2, 4.2, 1.2, rot_z=0.35),  # parcialmente sob a borda do buraco
        _caixa(7.5, 4.0, 0.0, 9.2, 5.5, 0.7, incl_y=0.2),  # inclinada cruzando a borda da claraboia
        _caixa(4.0, 5.5, 3.25, 8.0, 7.2, 4.1, rot_z=0.18),  # caixa sobre a laje (caixa d'agua)
        _caixa(1.0, 0.5, 3.25, 2.2, 1.4, 3.9),  # platibanda / volume no topo
        _caixa(10.5, 1.0, 3.25, 11.4, 2.5, 4.0),  # chamine no topo
    ]
    return pecas


def _cena_casa_compacta():
    """Versao compacta (2,4 x 1,8 m) da cena residencial com as mesmas 18 pecas, buracos e oclusoes."""
    return [(v * 0.2, t.copy()) for v, t in _cena_casa_paredes_lajes_buracos()]


def _cena_caixas_sobrepostas_e_escondidas():
    rng = np.random.default_rng(24001)
    pecas = [
        _caixa(0.0, 0.0, 2.5, 4.0, 4.0, 2.8),  # cobertura parcial
        _caixa(0.8, 0.8, 0.0, 1.6, 1.6, 1.0),  # totalmente escondida
        _caixa(0.8, 0.8, 0.0, 1.6, 1.6, 1.0),  # duplicata exata
        _caixa(2.0, 2.0, 0.0, 4.8, 2.8, 1.5),  # parcialmente escondida
        _caixa(2.0, 2.0, 1.0, 4.4, 2.6, 3.2, incl_y=0.25),  # sobreposta inclinada atravessando z=2.8
    ]
    for _ in range(12):
        cx, cy = rng.uniform(0.2, 4.6, 2)
        sx, sy, sz = rng.uniform(0.2, 1.2, 3)
        z0 = float(rng.uniform(0.0, 3.5))
        pecas.append(
            _caixa(cx - sx / 2, cy - sy / 2, z0, cx + sx / 2, cy + sy / 2, z0 + sz,
                   rot_z=float(rng.uniform(0.0, math.pi)),
                   incl_y=float(rng.uniform(-0.3, 0.3)) if rng.random() < 0.4 else 0.0)
        )
    return pecas


def _cena_lajes_buracos_e_faixas():
    pecas = [
        _placa_com_furo(0.0, 0.0, 6.0, 3.5, 1.2, 1.0, 3.4, 2.4, 2.0, 2.3),
        _tiras(0.3, 0.3, 5.2, 0.01, 240, 0.15, 2.6, 0.02),  # aciona passagem por faixas orientadas
    ]
    for i in range(10):
        x = 0.5 + 0.5 * i
        y = 0.5 + 0.5 * (i % 5)
        z0 = 0.0 if i % 2 == 0 else 2.8
        pecas.append(_caixa(x, y, z0, x + 0.45, y + 0.4, z0 + 0.9, rot_z=0.2 * i))
    return pecas


def _cena_utm_georref():
    off = np.array([500_000.0, 7_400_000.0, 750.0], dtype=np.float64)
    return [(v + off, t.copy()) for v, t in _cena_casa_compacta()]


def _cena_perto_de_zero():
    pecas = [
        _placa_com_furo(-0.5, -0.5, 0.5, 0.5, -0.2, -0.2, 0.2, 0.2, 0.2, 0.25),
        _caixa(-0.15, -0.15, -0.1, 0.15, 0.15, 0.1),  # visivel pelo furo em torno de (0,0)
        _caixa(-0.45, -0.45, -0.1, -0.25, -0.25, 0.1),  # escondida no quadrante negativo
        _caixa(0.25, 0.25, -0.1, 0.45, 0.45, 0.1),  # escondida no quadrante positivo
        _caixa(-0.3, -0.05, 0.0, 0.3, 0.05, 0.35, incl_y=0.15),  # cruza a origem e a laje
        _caixa(-0.4, 0.1, 0.25, 0.1, 0.35, 0.45, rot_z=0.4),
        _caixa(-1e-4, -0.4, 0.0, 1e-4 + 0.2, 0.4, 0.15),
        _caixa(-0.4, -1e-4, 0.26, 0.4, 1e-4 + 0.12, 0.36),
        _caixa(-0.22, -0.22, -0.05, -0.02, 0.18, 0.22),
        _caixa(0.05, -0.35, 0.0, 0.38, -0.08, 0.30, rot_z=-0.25),
    ]
    return pecas


def _cena_aleatoria_semente_fixa():
    rng = np.random.default_rng(24010)
    pecas = [
        _placa_com_furo(0.0, 0.0, 4.5, 4.0, 1.0, 1.0, 2.4, 2.4, 1.8, 2.0),
        _placa_com_furo(1.2, 0.6, 4.0, 3.4, 1.8, 1.3, 3.1, 2.7, 3.2, 3.4),
    ]
    for _ in range(16):
        cx, cy = rng.uniform(0.2, 4.3, 2)
        sx, sy, sz = rng.uniform(0.15, 0.9, 3)
        z0 = float(rng.uniform(-0.5, 4.0))
        pecas.append(
            _caixa(cx - sx / 2, cy - sy / 2, z0, cx + sx / 2, cy + sy / 2, z0 + sz,
                   rot_z=float(rng.uniform(0.0, math.pi)),
                   incl_y=float(rng.uniform(-0.35, 0.35)) if rng.random() < 0.35 else 0.0)
        )
    return pecas


def _cena_tres_chaves_distintas():
    """14 pecas gerando exatamente 3 chaves de mapa Z distintas em linhas_visiveis_multi."""
    pecas = [
        # Grupo A (6 caixas dentro de [0, 2] x [0, 2]) -> chave 1: [0, 2] x [0, 2]
        _caixa(0.0, 0.0, 2.0, 2.0, 2.0, 2.2),
        _caixa(0.2, 0.2, 0.0, 0.8, 0.8, 1.0),
        _caixa(1.0, 0.2, 0.0, 1.6, 0.8, 1.0),
        _caixa(0.2, 1.1, 0.0, 0.9, 1.7, 1.0),
        _caixa(1.1, 1.1, 2.2, 1.8, 1.8, 3.0),
        _caixa(0.2, 0.2, 2.2, 0.7, 0.7, 2.8),
        # Grupo B (4 paineis verticais em x=4, dentro de y=[0, 2]) -> chave 2: [0, 4] x [0, 2]
        _quad_vertical(4.0, 0.1, 4.0, 0.5, 0.0, 2.0),
        _quad_vertical(4.0, 0.6, 4.0, 1.0, 0.0, 2.0),
        _quad_vertical(4.0, 1.1, 4.0, 1.5, 0.0, 2.0),
        _quad_vertical(4.0, 1.6, 4.0, 1.9, 0.0, 2.0),
        # Grupo C (4 paineis verticais em x=6, dentro de y=[0, 2]) -> chave 3: [0, 6] x [0, 2]
        _quad_vertical(6.0, 0.1, 6.0, 0.5, 0.0, 2.0),
        _quad_vertical(6.0, 0.6, 6.0, 1.0, 0.0, 2.0),
        _quad_vertical(6.0, 1.1, 6.0, 1.5, 0.0, 2.0),
        _quad_vertical(6.0, 1.6, 6.0, 1.9, 0.0, 2.0),
    ]
    return pecas


CENAS = {
    "casa_paredes_lajes_buracos": _cena_casa_paredes_lajes_buracos,
    "caixas_sobrepostas_e_escondidas": _cena_caixas_sobrepostas_e_escondidas,
    "lajes_buracos_e_faixas": _cena_lajes_buracos_e_faixas,
    "utm_georref": _cena_utm_georref,
    "perto_de_zero": _cena_perto_de_zero,
    "aleatoria_semente_fixa": _cena_aleatoria_semente_fixa,
}


def _instalar_spy_mapa_z(monkeypatch, *, atraso: float = 0.0, ao_chamar=None):
    """Instala spy thread-safe em visibilidade._mapa_z_conservador (e visib_mapa)."""
    chamadas: list[tuple] = []
    lock = threading.Lock()

    def spy(*args, **kwargs):
        chave = tuple(args[-5:])
        with lock:
            chamadas.append(chave)
            ordem = len(chamadas)
        if atraso > 0.0:
            time.sleep(atraso)
        if ao_chamar is not None:
            ao_chamar(ordem, chave)
        return _MAPA_Z_REAL(*args, **kwargs)

    monkeypatch.setattr(vis, "_mapa_z_conservador", spy)
    monkeypatch.setattr(visib_mapa, "_mapa_z_conservador", spy)
    return chamadas


def _executar_com_timeout(fn, timeout: float = 60.0):
    """Executa `fn` em thread daemon com timeout para detectar deadlock sem travar pytest."""
    res: list = []
    erro: list[BaseException] = []

    def alvo():
        try:
            res.append(fn())
        except BaseException as exc:  # noqa: BLE001
            erro.append(exc)

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"deadlock detectado: execucao excedeu {timeout:.0f} s"
    if erro:
        raise erro[0]
    return res[0]


def _threads_pool_vivas() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor") and t.is_alive()]


# ---------------------------------------------------------------------------
# (1) Equivalencia: 1, 2 e 8 threads vs copia literal do motor atual
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome_cena", list(CENAS))
def test_equivalencia_1_2_8_threads_igual_referencia_literal(nome_cena):
    pecas = CENAS[nome_cena]()
    ref = _linhas_visiveis_multi_ref(pecas)
    h_ref = _hash_resultado(ref)

    for n_trab in (1, 2, 8):
        obtido = linhas_visiveis_multi(pecas, trabalhadores=n_trab)
        assert _hash_resultado(obtido) == h_ref, f"{nome_cena} trabalhadores={n_trab}"
        _assert_equivalente(obtido, ref, contexto=f"{nome_cena}/n={n_trab}")


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


def test_mutante_03_respeita_tol_z():
    """Mutante 3: ignorar tol_z no filtro pre-dedup ou no mapa Z esconde aresta dentro da tolerancia."""
    tol = 1e-2
    teto = _caixa(0.0, 0.0, 0.9, 4.0, 4.0, 1.0)
    # Dentro da tolerancia (z=0.995 -> diferenca 0.005 < tol_z=0.01): topo visivel (perimetro 8 m)
    dentro_tol = _caixa(1.0, 1.0, 0.0, 3.0, 3.0, 1.0 - 5e-3)
    # Abaixo alem da tolerancia (z=0.98 -> diferenca 0.02 > tol_z=0.01): escondida (0 linhas)
    fora_tol = _caixa(1.0, 1.0, 0.0, 3.0, 3.0, 1.0 - 2e-2)

    for n_trab in (1, 8):
        r_vis = linhas_visiveis_multi([teto, dentro_tol], tol_z=tol, trabalhadores=n_trab)
        r_hid = linhas_visiveis_multi([teto, fora_tol], tol_z=tol, trabalhadores=n_trab)
        assert _comprimento_total(r_vis[1]) == pytest.approx(8.0, abs=1e-3)
        assert len(r_hid[1]) == 0
        _assert_equivalente(r_vis, _linhas_visiveis_multi_ref([teto, dentro_tol], tol_z=tol), contexto=f"tol_z_vis/n={n_trab}")
        _assert_equivalente(r_hid, _linhas_visiveis_multi_ref([teto, fora_tol], tol_z=tol), contexto=f"tol_z_hid/n={n_trab}")

    # Tambem diretamente em visib_mapa._filtrar_e_recortar
    P = np.array(
        [
            [0.0, 0.0, 1.0], [4.0, 0.0, 1.0], [0.0, 4.0, 1.0],  # triangulo em z=1.0
            [0.5, 0.5, 1.0 - 5e-3], [1.5, 0.5, 1.0 - 5e-3],  # aresta 5 mm abaixo
        ],
        dtype=np.float64,
    )
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, _ = _preparar_triangulos(P, np.array([[0, 1, 2]]))
    ea, eb = np.array([3], dtype=np.int64), np.array([4], dtype=np.int64)
    a, b = P[ea], P[eb]
    d = b - a
    ex0, ex1 = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    ey0, ey1 = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    ezmin = np.minimum(a[:, 2], b[:, 2])
    pe, pt = np.array([0, 0], dtype=np.int64), np.array([0, 0], dtype=np.int64)

    H_grande, H_pequena = [], []
    visib_mapa._filtrar_e_recortar(
        pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, len(A), 1e-2, -1e-6, H_grande,
    )
    visib_mapa._filtrar_e_recortar(
        pe.copy(), pt.copy(), a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, len(A), 1e-4, -1e-6, H_pequena,
    )
    assert len(_compactar_H(H_grande, limpar=True)[0]) == 0, "com tol_z=1e-2, diferenca de 5e-3 nao pode ocluir"
    assert len(_compactar_H(H_pequena, limpar=True)[0]) == 1, "com tol_z=1e-4, diferenca de 5e-3 deve ocluir"


def test_mutante_04_resultado_independente_do_numero_de_threads(monkeypatch):
    """Mutante 4: resultado variar com trabalhadores=1, 2, 4, 8 sob intercalacao concorrente."""
    pecas = _cena_casa_compacta() + _cena_tres_chaves_distintas()[6:10]
    ref = _linhas_visiveis_multi_ref(pecas)
    h_ref = _hash_resultado(ref)
    _instalar_spy_mapa_z(monkeypatch, atraso=0.01)

    resultados = {n: linhas_visiveis_multi(pecas, trabalhadores=n) for n in (1, 2, 4, 8)}
    for n, res in resultados.items():
        assert _hash_resultado(res) == h_ref, f"trabalhadores={n} divergiu da referencia"
        _assert_equivalente(res, resultados[1], contexto=f"mutante_04/n={n}")
        for i, (pa, pb) in enumerate(zip(res, resultados[1])):
            assert len(pa) == len(pb) and all(np.array_equal(x, y) for x, y in zip(pa, pb)), (
                f"trabalhadores={n} peca {i} nao bit a bit igual a n=1"
            )
