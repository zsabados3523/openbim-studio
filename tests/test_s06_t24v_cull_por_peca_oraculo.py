# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24v (T3): cull por peca via caixa XY dilatada com copias contiguas cacheadas.

Contrato verificado pelo oraculo:
1. Igualdade bit a bit das polilinhas de `linhas_visiveis_multi` contra copia literal da
   implementacao atual (pre-T24v), em cenas especiais e fuzz de 200 seeds fixas.
2. Propriedade do conjunto mantido: para cada peca, o `kept` que segue ao motor contem
   todo triangulo que `_cull_tris` atual mantem E cuja caixa XY toca a caixa da peca
   dilatada com margem segura; nunca descarta triangulo que oclui aresta.
3. Capturas reais (`/tmp/t24e/dist/*.pkl` e `/tmp/t24e/u/an/bib_*.pkl`, skipif ausente):
   hash SHA-256 identico nas capturas menores (`bib_2`, `bib_4`, `c2x3_0`, `cas_9`) e ganho
   de tempo >= 15% na captura com muitas pecas (e tambem em cena sintetica equivalente).
4. Determinismo em 3 rodadas, `trabalhadores=1` e `4` iguais bit a bit, entrada nao mutada
   (inclusive arrays somente-leitura) e sem vazamento de cache entre chamadas.
5. Quatro mutantes plausiveis em memoria (caixa nao dilatada, caixa so em X, indice
   desalinhado em copia contigua, cache compartilhado errado entre pecas) detectados.

Nao editar este arquivo durante a implementacao da T24v.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc
import glob
import hashlib
import math
import os
import pickle
import statistics
import threading
import time
from unittest import mock

import numpy as np
import pytest

import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _arestas_candidatas,
    _cel_caixa,
    _dedup_int64,
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
    _subgrade_celulas_densas,
    _varrer_cels_triangulos,
)
from obim_geometria.visibilidade import (
    _dedup_triangulos,
    _limpar_malha,
    _resolver_trabalhadores_auto,
    _validar_trabalhadores,
    linhas_visiveis_multi,
)

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

_DIR_DIST = "/tmp/t24e/dist"
_DIR_BIB_MOB = "/tmp/t24e/u/an"
_MARGEM_PROPRIEDADE = 1e-6  # abs(d_eps): minimo seguro que toda caixa dilatada cobre


# ---------------------------------------------------------------------------
# Copia literal imutavel da implementacao atual (referencia pre-T24v)
# ---------------------------------------------------------------------------

def _cull_tris_ref(kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom, n=512):
    """Copia literal de `visibilidade._cull_tris` pre-T24v."""
    c = max(dx_dom, dy_dom, 1e-9) / n
    W = int(dx_dom / c) + 3
    H = int(dy_dom / c) + 3

    def ij(x, y):
        return (
            np.clip(np.floor((x - mn_x) / c).astype(np.int64), 0, W - 1),
            np.clip(np.floor((y - mn_y) / c).astype(np.int64), 0, H - 1),
        )

    ex0, ey0 = ij(np.minimum(ea_[:, 0], eb_[:, 0]), np.minimum(ea_[:, 1], eb_[:, 1]))
    ex1, ey1 = ij(np.maximum(ea_[:, 0], eb_[:, 0]), np.maximum(ea_[:, 1], eb_[:, 1]))
    ex0 = np.maximum(ex0 - 1, 0)
    ey0 = np.maximum(ey0 - 1, 0)
    ex1 = np.minimum(ex1 + 1, W - 1)
    ey1 = np.minimum(ey1 + 1, H - 1)
    dif = np.zeros((H + 1, W + 1), np.int64)
    np.add.at(dif, (ey0, ex0), 1)
    np.add.at(dif, (ey0, ex1 + 1), -1)
    np.add.at(dif, (ey1 + 1, ex0), -1)
    np.add.at(dif, (ey1 + 1, ex1 + 1), 1)
    occ = (dif.cumsum(0).cumsum(1)[:H, :W] > 0).astype(np.int64)
    sat = np.zeros((H + 1, W + 1), np.int64)
    sat[1:, 1:] = occ.cumsum(0).cumsum(1)
    qx0, qy0 = ij(tx0[kept], ty0[kept])
    qx1, qy1 = ij(tx1[kept], ty1[kept])
    tot = sat[qy1 + 1, qx1 + 1] - sat[qy0, qx1 + 1] - sat[qy1 + 1, qx0] + sat[qy0, qx0]
    return kept[tot > 0]


_REF_MEMO_MGR_LOCK = threading.Lock()
_REF_MEMO_CHAVE_LOCKS: dict[tuple[int, tuple], list] = {}


def _calc_mapa_z_ref(A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, mn_x, mn_y, mx_x, mx_y, g):
    """Copia literal de `_calc_mapa_z` pre-T24v."""
    z_full_, W_, H_ = _mapa_z_conservador(
        A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, mx_x, mx_y, g
    )
    tx0i, tx1i, ty0i, ty1i = _cel_caixa(tx0, tx1, ty0, ty1, mn_x, mn_y, g, W_, H_)
    idx_s = np.nonzero((tx1i - tx0i + 1) * (ty1i - ty0i + 1) <= 25)[0]
    tri_keep = np.ones(len(A), bool)
    zf_flat_ = z_full_.ravel()
    tri_keep[idx_s] = False
    for k0 in range(0, len(idx_s), 50_000):
        sl = idx_s[k0:k0 + 50_000]
        tobj, tcel = _expandir_celulas(tx0i[sl], tx1i[sl], ty0i[sl], ty1i[sl], W_)
        np.logical_or.at(tri_keep, sl[tobj], tzmax[sl[tobj]] >= zf_flat_[tcel] - 1e-9)
    return z_full_, zf_flat_, W_, H_, np.nonzero(tri_keep)[0]


def _visibilidade_hibrida_ref(
    P, Tw, a, b, ea, eb, tol_z: float, d_eps: float, min_len: float, prep=None, memo=None
) -> np.ndarray:
    """Copia literal de `visibilidade._visibilidade_hibrida` pre-T24v usando `_cull_tris_ref`."""
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

    if memo is None:
        entrada = _calc_mapa_z_ref(
            A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, mn_x, mn_y, mx_x, mx_y, g
        )
    else:
        entrada = memo.get(chave)
        if entrada is None:
            mk = (id(memo), chave)
            with _REF_MEMO_MGR_LOCK:
                slot = _REF_MEMO_CHAVE_LOCKS.get(mk)
                if slot is None:
                    slot = [threading.Lock(), 0]
                    _REF_MEMO_CHAVE_LOCKS[mk] = slot
                slot[1] += 1
            try:
                with slot[0]:
                    entrada = memo.get(chave)
                    if entrada is None:
                        entrada = memo.setdefault(
                            chave,
                            _calc_mapa_z_ref(
                                A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax,
                                mn_x, mn_y, mx_x, mx_y, g,
                            ),
                        )
            finally:
                with _REF_MEMO_MGR_LOCK:
                    slot[1] -= 1
                    if slot[1] == 0:
                        _REF_MEMO_CHAVE_LOCKS.pop(mk, None)
    z_full, zf_flat, W, H, kept_idx = entrada
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
            np.minimum(z_full[sy0, sx0], z_full[sy0, sx1]),
            np.minimum(z_full[sy1, sx0], z_full[sy1, sx1]),
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
        kept_idx = _cull_tris_ref(kept_idx, a[ek_idx], b[ek_idx], tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
    ex0 = np.minimum(a[:, 0], b[:, 0])
    ex1 = np.maximum(a[:, 0], b[:, 0])
    ey0 = np.minimum(a[:, 1], b[:, 1])
    ey1 = np.maximum(a[:, 1], b[:, 1])
    ezmin = np.minimum(a[:, 2], b[:, 2])
    ctx = (A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, ea, eb, ex0, ex1, ey0, ey1, ezmin)
    rem_t = _passagem_faixas_orientadas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z, d_eps, ctx, H_l)
    cg = g
    nt_all = len(A)
    usar_subgrade = os.environ.get("OBIM_VISIB_SUBGRADE") != "0"
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
                        sx0 = np.maximum(sx0, bx0)
                        sx1 = np.minimum(sx1, bx0 + Wl - 1)
                        sy0 = np.maximum(sy0, by0)
                        sy1 = np.minimum(sy1, by0 + Hl - 1)
                        okb = (sx1 >= sx0) & (sy1 >= sy0)
                        s_l, sa, sb = s_l[okb], sa[okb], sb[okb]
                        sobj, scel = _expandir_celulas(
                            sx0[okb] - bx0, sx1[okb] - bx0, sy0[okb] - by0, sy1[okb] - by0, Wl
                        )
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
                        if usar_subgrade and len(eobj):
                            denso_cel = cont >= 128
                            eh_denso = denso_cel[ecel]
                            if np.any(eh_denso) and int(ntri_par[eh_denso].sum()) >= 20_000_000:
                                eo_n, ec_n, nt_n = eobj[~eh_denso], ecel[~eh_denso], ntri_par[~eh_denso]
                                for p0, p1 in _fatias(nt_n, 200_000, chaves=eo_n):
                                    g3, kk = _rle_idx(nt_n[p0:p1])
                                    _filtrar_e_recortar(
                                        eo_n[p0:p1][g3], tri_por_cel[ini_cel[ec_n[p0:p1]][g3] + kk],
                                        a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                                        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                                        tol_z, d_eps, H_l,
                                    )
                                _subgrade_celulas_densas(
                                    eobj[eh_denso], ecel[eh_denso], cont, ini_cel, tri_por_cel,
                                    bx0, by0, Wl, mn_x, mn_y, cg,
                                    a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                                    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                                    tol_z, d_eps, H_l,
                                )
                                continue
                        for p0, p1 in _fatias(ntri_par, 200_000, chaves=eobj):
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


def _linhas_visiveis_multi_ref(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
    trabalhadores: int | None = 1,
) -> list[list[np.ndarray]]:
    """Referencia fiel de `linhas_visiveis_multi` pre-T24v."""
    n_trab = _validar_trabalhadores(trabalhadores)
    pecas_l = list(pecas)
    if not pecas_l:
        return []
    limpas = [_limpar_malha(v, t) for v, t in pecas_l]
    v_parts, offsets, v_off = [], [], 0
    for item in limpas:
        offsets.append(None if item is None else (v_off, item[1]))
        if item is not None:
            v_parts.append(item[0])
            v_off += len(item[0])
    if not v_parts:
        return [[] for _ in pecas_l]
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
    if not tw_oks:
        return [[] for _ in pecas_l]
    ativos = [(i, c) for i, c in enumerate(cands) if c is not None]
    if not ativos:
        return [[] for _ in pecas_l]
    Tw_comb = tw_oks[0] if len(tw_oks) == 1 else _dedup_triangulos(np.vstack(tw_oks))
    prep = _preparar_triangulos(P, Tw_comb)
    memo = {}
    if n_trab is None:
        n_trab = _resolver_trabalhadores_auto(len(ativos), len(Tw_comb))
    res: list[list[np.ndarray]] = [[] for _ in pecas_l]
    if n_trab == 1:
        for i, c in ativos:
            res[i] = list(_visibilidade_hibrida_ref(P, Tw_comb, *c, tol_z, -1e-6, min_len, prep=prep, memo=memo))
        return res
    with ThreadPoolExecutor(max_workers=n_trab) as pool:
        try:
            futs = [
                (i, pool.submit(_visibilidade_hibrida_ref, P, Tw_comb, *c, tol_z, -1e-6, min_len, prep=prep, memo=memo))
                for i, c in ativos
            ]
            for i, fut in futs:
                res[i] = list(fut.result())
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return res


# ---------------------------------------------------------------------------
# Comparadores bit a bit, SHA-256 e verificacao da propriedade de superconjunto
# ---------------------------------------------------------------------------

def _canon_bit_a_bit(pls: list[np.ndarray]) -> list[np.ndarray]:
    if not pls:
        return []
    arrs = [np.ascontiguousarray(p, dtype=np.float64) for p in pls]
    chaves = [(a.shape[0], *a.ravel().tolist()) for a in arrs]
    ordem = sorted(range(len(arrs)), key=chaves.__getitem__)
    return [arrs[i] for i in ordem]


def _assert_bit_a_bit(
    obt: list[list[np.ndarray]],
    ref: list[list[np.ndarray]],
    *,
    ordem_exata: bool = False,
    ctx: str = "",
) -> None:
    """Verifica igualdade bit a bit (view uint64) por peca."""
    assert len(obt) == len(ref), f"[{ctx}] num pecas difere: {len(obt)} != {len(ref)}"
    for i, (pa, pb) in enumerate(zip(obt, ref)):
        ca = [np.ascontiguousarray(p, dtype=np.float64) for p in pa] if ordem_exata else _canon_bit_a_bit(pa)
        cb = [np.ascontiguousarray(p, dtype=np.float64) for p in pb] if ordem_exata else _canon_bit_a_bit(pb)
        assert len(ca) == len(cb), f"[{ctx}] peca {i}: contagem polilinhas {len(ca)} != {len(cb)}"
        for j, (a, b) in enumerate(zip(ca, cb)):
            assert a.shape == b.shape, f"[{ctx}] peca {i} pl {j}: shape {a.shape} != {b.shape}"
            if not np.array_equal(a.view(np.uint64), b.view(np.uint64)):
                dif = float(np.abs(a - b).max()) if a.size else 0.0
                raise AssertionError(f"[{ctx}] peca {i} pl {j}: difere bit a bit (max={dif:.3e} m)")


def _sha_polilinhas(res: list[list[np.ndarray]]) -> str:
    """SHA-256 canonico dos bits IEEE-754 das polilinhas por peca."""
    h = hashlib.sha256()
    h.update(f"n={len(res)}\n".encode("ascii"))
    for i, pls in enumerate(res):
        can = _canon_bit_a_bit(pls)
        h.update(f"p={i}:{len(can)}\n".encode("ascii"))
        for arr in can:
            h.update(f"{arr.shape}\n".encode("ascii"))
            h.update(arr.view(np.uint64).tobytes())
    return h.hexdigest()


def _comprimento_total(pls: list[np.ndarray]) -> float:
    total = 0.0
    for pl in pls:
        arr = np.asarray(pl, dtype=np.float64)
        if len(arr) >= 2:
            d = np.diff(arr, axis=0)
            total += float(np.hypot(d[:, 0], d[:, 1]).sum())
    return total


def _validar_conjunto_mantido(
    kept_prod: np.ndarray,
    kept_pre: np.ndarray,
    ea_: np.ndarray,
    eb_: np.ndarray,
    tx0: np.ndarray,
    tx1: np.ndarray,
    ty0: np.ndarray,
    ty1: np.ndarray,
    mn_x: float,
    mn_y: float,
    dx_dom: float,
    dy_dom: float,
    *,
    marg_caixa: float = _MARGEM_PROPRIEDADE,
    ctx: str = "",
) -> np.ndarray:
    """Valida que `kept_prod` e valido e contem todo tri de `_cull_tris_ref` na caixa dilatada."""
    kp = np.asarray(kept_prod)
    assert kp.ndim == 1, f"[{ctx}] kept_prod nao e 1D: shape={kp.shape}"
    assert np.issubdtype(kp.dtype, np.integer), f"[{ctx}] kept_prod nao e inteiro: {kp.dtype}"
    if len(kp):
        assert int(kp.min()) >= 0 and int(kp.max()) < len(tx0), (
            f"[{ctx}] indice fora do intervalo [0, {len(tx0)}): min={kp.min()} max={kp.max()}"
        )
        assert len(np.unique(kp)) == len(kp), f"[{ctx}] kept_prod contem duplicatas"

    ref_kept = _cull_tris_ref(kept_pre, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
    px0 = float(min(ea_[:, 0].min(), eb_[:, 0].min()))
    px1 = float(max(ea_[:, 0].max(), eb_[:, 0].max()))
    py0 = float(min(ea_[:, 1].min(), eb_[:, 1].min()))
    py1 = float(max(ea_[:, 1].max(), eb_[:, 1].max()))
    toca = (
        (tx1[ref_kept] >= px0 - marg_caixa)
        & (tx0[ref_kept] <= px1 + marg_caixa)
        & (ty1[ref_kept] >= py0 - marg_caixa)
        & (ty0[ref_kept] <= py1 + marg_caixa)
    )
    obrig = set(ref_kept[toca].tolist())
    obt = set(kp.tolist())
    faltando = obrig - obt
    assert not faltando, (
        f"[{ctx}] {len(faltando)} triangulo(s) obrigatorio(s) descartado(s) pelo cull "
        f"(ex.: {sorted(faltando)[:5]})"
    )
    return ref_kept


def _executar_e_validar_propriedade(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
    marg_caixa: float = _MARGEM_PROPRIEDADE,
    ctx: str = "",
) -> tuple[list[list[np.ndarray]], list[dict]]:
    """Roda `linhas_visiveis_multi` observando `kept_idx` em `_passagem_faixas_orientadas`."""
    registros: list[dict] = []
    cache_pre: dict[tuple, np.ndarray] = {}
    real_faixas = vis._passagem_faixas_orientadas

    def spy_faixas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z_, d_eps, ctx_m, H_l):
        A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax = ctx_m[:11]
        mn_x = float(min(a[:, 0].min(), b[:, 0].min(), tx0.min() if len(A) else math.inf))
        mn_y = float(min(a[:, 1].min(), b[:, 1].min(), ty0.min() if len(A) else math.inf))
        mx_x = float(max(a[:, 0].max(), b[:, 0].max(), tx1.max() if len(A) else -math.inf))
        mx_y = float(max(a[:, 1].max(), b[:, 1].max(), ty1.max() if len(A) else -math.inf))
        dx_dom = max(mx_x - mn_x, 0.0)
        dy_dom = max(mx_y - mn_y, 0.0)
        chave = (mn_x, mn_y, mx_x, mx_y, g)
        kept_pre = cache_pre.get(chave)
        if kept_pre is None:
            _, _, _, _, kept_pre = _calc_mapa_z_ref(
                A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, mn_x, mn_y, mx_x, mx_y, g
            )
            cache_pre[chave] = kept_pre
        ref_kept = kept_pre[:0]
        if len(ek_idx) and len(kept_pre):
            ref_kept = _validar_conjunto_mantido(
                kept_idx, kept_pre, a[ek_idx], b[ek_idx], tx0, tx1, ty0, ty1,
                mn_x, mn_y, dx_dom, dy_dom, marg_caixa=marg_caixa,
                ctx=f"{ctx}/chamada_{len(registros)}",
            )
        registros.append(
            {
                "kept_prod": np.asarray(kept_idx).copy(),
                "kept_pre": kept_pre,
                "ref_kept": ref_kept,
                "n_ek": int(len(ek_idx)),
                "tx0": tx0, "tx1": tx1, "ty0": ty0, "ty1": ty1,
                "a_ek": a[ek_idx].copy(), "b_ek": b[ek_idx].copy(),
            }
        )
        return real_faixas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z_, d_eps, ctx_m, H_l)

    with mock.patch.object(vis, "_passagem_faixas_orientadas", spy_faixas):
        res = linhas_visiveis_multi(
            pecas, angulo_graus=angulo_graus, tol_z=tol_z, min_len=min_len, trabalhadores=1
        )
    return res, registros


# ---------------------------------------------------------------------------
# Construtores geometricos e cenas sinteticas
# ---------------------------------------------------------------------------

def _rz(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def _ry(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64)


def _caixa(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float,
    *, rot_z: float = 0.0, incl_y: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    cx, cy, cz = (x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    v = np.array(
        [[x, y, z] for z in (-0.5, 0.5) for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))],
        dtype=np.float64,
    ) * np.array([sx, sy, sz], dtype=np.float64)
    if rot_z or incl_y:
        v = v @ (_rz(rot_z) @ _ry(incl_y)).T
    return v + np.array([cx, cy, cz], dtype=np.float64), _F_CAIXA.copy()


def _quad_vertical(
    x0: float, y0: float, x1: float, y1: float, z0: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    v = np.array([[x0, y0, z0], [x1, y1, z0], [x1, y1, z1], [x0, y0, z1]], dtype=np.float64)
    t = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return v, t


def _triangulo_unico(p0, p1, p2) -> tuple[np.ndarray, np.ndarray]:
    return np.array([p0, p1, p2], dtype=np.float64), np.array([[0, 1, 2]], dtype=np.int64)


def _peca_uma_aresta(x0: float, y0: float, z_top: float, z_bot: float = 0.0, comp: float = 1.8e-4):
    """Triangulo vertical com exatamente 1 aresta candidata (`len2d > min_len=1e-4`).

    Pela desigualdade triangular, com o 3o vertice no ponto medio em XY (`comp/2 = 9e-5 < 1e-4`),
    apenas a aresta superior `(0, 1)` passa no filtro `len2d > min_len`.
    """
    v = np.array(
        [
            [x0, y0, z_top],
            [x0 + comp, y0, z_top],
            [x0 + 0.5 * comp, y0, z_bot],
        ],
        dtype=np.float64,
    )
    t = np.array([[0, 1, 2]], dtype=np.int64)
    return v, t


def _terreno_plano(nx: int, ny: int, lado: float, z0: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(nx + 1) * lado, np.arange(ny + 1) * lado)
    z = np.full_like(xs, z0, dtype=np.float64)
    v = np.c_[xs.ravel(), ys.ravel(), z.ravel()]
    i = (np.arange(ny)[:, None] * (nx + 1) + np.arange(nx)[None, :]).ravel()
    t = np.stack([np.c_[i, i + 1, i + nx + 2], np.c_[i, i + nx + 2, i + nx + 1]], 1).reshape(-1, 3)
    return v, t.astype(np.int64)


def _cena_varias_pecas_espalhadas():
    rng = np.random.default_rng(240101)
    pecas = []
    for k in range(28):
        x = float((k % 7) * 18.0 + rng.uniform(0.0, 2.5))
        y = float((k // 7) * 28.0 + rng.uniform(0.0, 2.5))
        w = float(rng.uniform(0.4, 2.0))
        h = float(rng.uniform(0.4, 2.0))
        z0 = float(rng.uniform(0.0, 2.0))
        pecas.append(_caixa(x, y, z0, x + w, y + h, z0 + 0.8, rot_z=float(rng.uniform(0, math.pi))))
        if k % 3 == 0:
            pecas.append(_caixa(x + 0.1, y + 0.1, z0 + 1.2, x + w * 0.7, y + h * 0.7, z0 + 1.5))
    return pecas


def _cena_triangulos_ingremes():
    pecas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 0.5),
        _caixa(50.0, 50.0, 0.0, 51.0, 51.0, 0.5),
    ]
    for k, grad in enumerate((150.0, 500.0, 2000.0, 1e4)):
        x0 = 8.0 + 10.0 * k
        y0 = 10.0 + 6.0 * k
        dx = 1e-3 if grad <= 2000.0 else 1e-4
        v_st = np.array(
            [
                [x0, y0, 3.0],
                [x0 + dx, y0, 3.0 - grad * dx],
                [x0, y0 + 0.4, 3.0],
                [x0 + dx, y0 + 0.4, 3.0 - grad * dx],
            ],
            dtype=np.float64,
        )
        t_st = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        pecas.append((v_st, t_st))
        pecas.append(_caixa(x0 - 0.1, y0 + 0.05, 0.5, x0 + 0.2, y0 + 0.35, 1.2, incl_y=0.2))
        pecas.append(_quad_vertical(x0 - 0.05, y0 + 0.2, x0 + 0.05, y0 + 0.2, 0.0, 2.95))
    return pecas


def _cena_pecas_sobrepostas():
    pecas = [
        _caixa(0.0, 0.0, 0.0, 20.0, 20.0, 0.2),
        _caixa(4.0, 4.0, 3.0, 12.0, 12.0, 3.3),
        _caixa(5.0, 5.0, 0.5, 11.0, 11.0, 1.2),  # escondida
        _caixa(5.0, 5.0, 0.5, 11.0, 11.0, 1.2),  # duplicata exata
        _caixa(10.0, 6.0, 1.0, 16.0, 10.0, 4.0, incl_y=0.35),  # corta teto
        _caixa(2.0, 8.0, 2.0, 8.0, 14.0, 2.8, rot_z=0.5),
        _caixa(4.5, 4.5, 4.0, 7.5, 7.5, 4.5, rot_z=0.2),
        _caixa(14.0, 14.0, 0.5, 18.0, 18.0, 2.0),
    ]
    return pecas


def _cena_peca_toca_borda_dominio():
    W, H = 40.0, 30.0
    pecas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        _caixa(W - 1.0, H - 1.0, 0.0, W, H, 1.0),
        # Toca exatamente as 4 bordas do dominio
        _caixa(0.0, 12.0, 0.2, 1.2, 16.0, 0.8),
        _caixa(0.0, 13.0, 1.5, 0.6, 15.0, 2.0),  # oclusor na borda x=0
        _caixa(W - 1.2, 10.0, 0.2, W, 14.0, 0.8),
        _caixa(W - 0.5, 11.0, 1.5, W, 13.0, 2.0),  # oclusor na borda x=W
        _caixa(15.0, 0.0, 0.2, 19.0, 1.2, 0.8),
        _caixa(16.0, 0.0, 1.5, 18.0, 0.5, 2.0),  # oclusor na borda y=0
        _caixa(18.0, H - 1.2, 0.2, 22.0, H, 0.8),
        _caixa(19.0, H - 0.5, 1.5, 21.0, H, 2.0),  # oclusor na borda y=H
        # Toca a borda a +-1e-7 m
        _caixa(1e-7, 20.0, 0.2, 0.8, 22.0, 0.9),
        _caixa(0.0, 20.2, 1.5, 1e-7 + 0.4, 21.8, 2.0),
    ]
    return pecas


def _cena_peca_uma_aresta():
    """Inclui pecas com exatamente 1 aresta ativa (`len(ek_idx) == 1`): uma visivel e uma ocluida."""
    pecas = [
        _caixa(0.0, 0.0, 0.0, 20.0, 20.0, 0.2),
        _peca_uma_aresta(5.0, 5.0, z_top=2.0, z_bot=0.5),
        _peca_uma_aresta(12.0, 12.0, z_top=2.0, z_bot=0.5),
        # Oclusor cobrindo a 2a peca de 1 aresta (sem tocar a 1a)
        _caixa(11.5, 11.5, 2.8, 12.5, 12.5, 3.0),
        # Peca longe para alargar o dominio
        _caixa(70.0, 70.0, 0.0, 72.0, 72.0, 1.0),
    ]
    return pecas


def _cena_triangulo_enorme_cobre_varias_pecas():
    """Triangulo gigante (100x100 m) cujos 3 vertices ficam longe de varias pecas espalhadas."""
    tri_gigante = _triangulo_unico([0.0, 0.0, 2.5], [100.0, 0.0, 2.5], [50.0, 100.0, 2.5])
    tri_gigante_inclinado = _triangulo_unico([0.0, 0.0, 0.5], [100.0, 0.0, 3.5], [50.0, 100.0, 1.8])
    pecas = [tri_gigante, tri_gigante_inclinado]
    for cx, cy, z in (
        (20.0, 15.0, 0.2),
        (50.0, 25.0, 1.0),
        (50.0, 50.0, 3.2),  # acima dos dois triangulos gigantes
        (75.0, 15.0, 1.2),
        (45.0, 70.0, 0.8),
        (5.0, 90.0, 0.5),  # fora dos triangulos gigantes
    ):
        pecas.append(_caixa(cx - 1.0, cy - 1.0, z, cx + 1.0, cy + 1.0, z + 0.6, rot_z=0.3))
    return pecas


def _cena_utm():
    off = np.array([500_000.0, 7_400_000.0, 720.0], dtype=np.float64)
    base = _cena_varias_pecas_espalhadas()[:14] + _cena_peca_toca_borda_dominio()[:6]
    return [(v + off, t.copy()) for v, t in base]


_CENAS_ESPECIAIS = {
    "varias_pecas_espalhadas": _cena_varias_pecas_espalhadas,
    "triangulos_ingremes": _cena_triangulos_ingremes,
    "pecas_sobrepostas": _cena_pecas_sobrepostas,
    "peca_toca_borda_dominio": _cena_peca_toca_borda_dominio,
    "peca_uma_aresta": _cena_peca_uma_aresta,
    "triangulo_enorme_cobre_varias_pecas": _cena_triangulo_enorme_cobre_varias_pecas,
    "coordenadas_utm": _cena_utm,
}


def _gerar_cena_fuzz(seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Gera cena sintetica variada com semente fixa cobrindo todos os padroes geometricos."""
    rng = np.random.default_rng(240_000 + seed)
    lado = float(rng.choice([3.0, 12.0, 40.0, 120.0]))
    usar_utm = (seed % 7 == 0)
    off = (
        np.array([500_000.0, 7_400_000.0, 700.0], dtype=np.float64)
        if usar_utm
        else np.zeros(3, dtype=np.float64)
    )
    pecas: list[tuple[np.ndarray, np.ndarray]] = []
    n_pecas = int(rng.integers(4, 13))

    # Espalhadas e sobrepostas
    for k in range(n_pecas):
        x0 = float(rng.uniform(0.0, lado * 0.85))
        y0 = float(rng.uniform(0.0, lado * 0.85))
        dx = float(rng.uniform(0.05, max(0.15, lado * 0.18)))
        dy = float(rng.uniform(0.05, max(0.15, lado * 0.18)))
        z0 = float(rng.uniform(-1.0, 3.0))
        dz = float(rng.uniform(0.05, 1.5))
        modo = int(rng.integers(0, 6))
        if modo == 0:
            # Peca tocando exatamente a borda do dominio
            borda = k % 4
            if borda == 0:
                x0 = 0.0
            elif borda == 1:
                x0 = lado - dx
            elif borda == 2:
                y0 = 0.0
            else:
                y0 = lado - dy
            v, t = _caixa(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz)
        elif modo == 1:
            # Triangulo ingreme
            dxs = float(rng.uniform(1e-4, 2e-3))
            v = np.array(
                [
                    [x0, y0, z0 + dz],
                    [x0 + dxs, y0, z0],
                    [x0, y0 + dy, z0 + dz],
                    [x0 + dxs, y0 + dy, z0],
                ],
                dtype=np.float64,
            )
            t = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        elif modo == 2:
            # Quad vertical (poucas arestas, sobreposto a outras pecas)
            v, t = _quad_vertical(x0, y0, x0 + dx, y0 + dy * 0.5, z0, z0 + dz)
        elif modo == 3:
            # Triangulo enorme cobrindo varias pecas
            zt = float(rng.uniform(0.5, 4.0))
            v, t = _triangulo_unico(
                [0.0, 0.0, zt],
                [lado, 0.0, zt + float(rng.uniform(-0.3, 0.3))],
                [lado * 0.5, lado, zt + float(rng.uniform(-0.3, 0.3))],
            )
        else:
            rot = float(rng.uniform(0.0, math.pi)) if rng.random() < 0.7 else 0.0
            incl = float(rng.uniform(-0.45, 0.45)) if rng.random() < 0.35 else 0.0
            v, t = _caixa(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz, rot_z=rot, incl_y=incl)
        pecas.append((v + off, t))

    # Garante sobreposicao direta em parte das seeds
    if seed % 3 == 0:
        bx, by = lado * 0.4, lado * 0.4
        pecas.append((_caixa(bx, by, 0.0, bx + 1.0, by + 1.0, 0.6)[0] + off, _F_CAIXA.copy()))
        pecas.append((_caixa(bx + 0.1, by + 0.1, 1.2, bx + 0.9, by + 0.9, 1.5)[0] + off, _F_CAIXA.copy()))
    return pecas


# ---------------------------------------------------------------------------
# (1) Igualdade bit a bit + propriedade do conjunto mantido
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", list(_CENAS_ESPECIAIS.keys()))
def test_igualdade_cenas_especiais_bit_a_bit_e_propriedade(nome):
    """Cenas especiais: saida bit a bit identica a referencia e propriedade do cull preservada."""
    pecas = _CENAS_ESPECIAIS[nome]()
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, regs = _executar_e_validar_propriedade(pecas, ctx=f"especial/{nome}")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx=f"especial/{nome}")
    assert len(regs) > 0
    if nome == "peca_uma_aresta":
        assert any(r["n_ek"] == 1 for r in regs), "cena peca_uma_aresta deve exercitar len(ek_idx)==1"


@pytest.mark.parametrize("bloco", range(20), ids=[f"seeds_{b * 10:03d}_{b * 10 + 9:03d}" for b in range(20)])
def test_igualdade_fuzz_200_seeds_bit_a_bit_e_propriedade(bloco):
    """Fuzz com 200 seeds fixas (20 blocos x 10): bit a bit igual a referencia e propriedade do cull."""
    for seed in range(bloco * 10, bloco * 10 + 10):
        pecas = _gerar_cena_fuzz(seed)
        ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
        obt, _ = _executar_e_validar_propriedade(pecas, ctx=f"fuzz_{seed}")
        _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx=f"fuzz_{seed}")


def test_cull_tris_direto_propriedade_superconjunto():
    """Chamada direta a `vis._cull_tris` preserva superconjunto sobre `kept` esparso, borda, 1 aresta e UTM."""
    rng = np.random.default_rng(240_999)
    for off_x, off_y in ((0.0, 0.0), (500_000.0, 7_400_000.0)):
        n_tris = 400
        x0 = off_x + rng.uniform(0.0, 100.0, n_tris)
        y0 = off_y + rng.uniform(0.0, 100.0, n_tris)
        tx0 = x0
        tx1 = x0 + rng.uniform(0.01, 2.0, n_tris)
        ty0 = y0
        ty1 = y0 + rng.uniform(0.01, 2.0, n_tris)
        # Inclui triangulo gigante e triangulo exatamente na borda
        tx0[0], tx1[0], ty0[0], ty1[0] = off_x, off_x + 100.0, off_y, off_y + 100.0
        tx0[1], tx1[1], ty0[1], ty1[1] = off_x + 49.0, off_x + 50.0, off_y + 49.0, off_y + 51.0
        # kept esparso (nao-contiguo: pula indices baixos e alterna)
        kept = np.array([0, 1, *range(5, n_tris, 2)], dtype=np.int64)
        # 1 unica aresta tocando exatamente x = off_x + 50.0
        ea_ = np.array([[off_x + 50.0, off_y + 49.5, 1.0]], dtype=np.float64)
        eb_ = np.array([[off_x + 50.0, off_y + 50.5, 1.0]], dtype=np.float64)
        mn_x, mn_y = float(tx0.min()), float(ty0.min())
        dx_dom, dy_dom = float(tx1.max() - mn_x), float(ty1.max() - mn_y)

        kept_prod = vis._cull_tris(kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
        _validar_conjunto_mantido(
            kept_prod, kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom,
            ctx=f"direto_off_{off_x:g}",
        )
        assert 0 in set(kept_prod.tolist()), "triangulo gigante descartado"
        assert 1 in set(kept_prod.tolist()), "triangulo tocando borda exata descartado"


# ---------------------------------------------------------------------------
# (2) Propriedade do cull: nunca descarta triangulo que oclui aresta
# ---------------------------------------------------------------------------

def test_propriedade_oclusor_peca_distante_nao_some():
    """Oclusor que cobre somente a aresta de uma peca distante (195, 195) nao pode sumir."""
    pecas = [
        # Massa de pecas perto da origem para dominar a cena
        *[_caixa(float(i), float(j), 0.0, float(i) + 0.6, float(j) + 0.6, 0.8) for i in range(6) for j in range(6)],
        # Peca distante em (195, 195): barra de comprimento 2.0 m em z=1.0
        _quad_vertical(195.0, 195.0, 197.0, 195.0, 0.0, 1.0),
        # Oclusor pequeno que cobre SOMENTE o trecho [195.5, 196.5] da barra distante
        _caixa(195.5, 194.8, 2.0, 196.5, 195.2, 2.3),
    ]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, regs = _executar_e_validar_propriedade(pecas, ctx="oclusor_distante")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx="oclusor_distante")

    idx_barra = len(pecas) - 2
    # Barra tem topo+base (4.0 m), mas metade [195.5, 196.5] esta ocluida -> sobram 2.0 m (topo+base nas pontas)
    assert _comprimento_total(obt[idx_barra]) == pytest.approx(2.0, abs=1e-3), (
        f"oclusor da peca distante sumiu: comp={_comprimento_total(obt[idx_barra]):.4f} m"
    )
    # Verifica diretamente que o registro da barra distante manteve triangulos em x in [195.5, 196.5]
    reg_barra = regs[idx_barra]
    kp = reg_barra["kept_prod"]
    tx0, tx1, ty0, ty1 = reg_barra["tx0"], reg_barra["tx1"], reg_barra["ty0"], reg_barra["ty1"]
    toca_ocl = (tx0[kp] <= 196.5) & (tx1[kp] >= 195.5) & (ty0[kp] <= 195.2) & (ty1[kp] >= 194.8)
    assert int(toca_ocl.sum()) >= 2, "triangulos do oclusor distante nao permaneceram em kept_prod"


@pytest.mark.parametrize("lado", ["-x", "+x", "-y", "+y"])
def test_propriedade_oclusor_tangente_quatro_lados_nao_some(lado):
    """Oclusor tangente na borda exata da aresta (nos 4 lados) nunca e descartado e oclui a aresta."""
    # Peca ancora longe para ampliar o dominio (c ~ 0.16 m)
    ancora = _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    ancora2 = _caixa(80.0, 80.0, 0.0, 81.0, 81.0, 1.0)
    if lado == "-x":
        ocl = _caixa(39.0, 40.0, 2.0, 40.0, 42.0, 2.2)  # tx1 == 40.0 == px0
        bar = _quad_vertical(40.0, 40.2, 40.0, 41.8, 0.0, 1.0)
    elif lado == "+x":
        ocl = _caixa(40.0, 40.0, 2.0, 41.0, 42.0, 2.2)  # tx0 == 40.0 == px1
        bar = _quad_vertical(40.0, 40.2, 40.0, 41.8, 0.0, 1.0)
    elif lado == "-y":
        ocl = _caixa(40.0, 39.0, 2.0, 42.0, 40.0, 2.2)  # ty1 == 40.0 == py0
        bar = _quad_vertical(40.2, 40.0, 41.8, 40.0, 0.0, 1.0)
    else:
        ocl = _caixa(40.0, 40.0, 2.0, 42.0, 41.0, 2.2)  # ty0 == 40.0 == py1
        bar = _quad_vertical(40.2, 40.0, 41.8, 40.0, 0.0, 1.0)
    pecas = [ancora, ancora2, ocl, bar]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, _ = _executar_e_validar_propriedade(pecas, ctx=f"tangente_{lado}")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx=f"tangente_{lado}")
    assert len(obt[3]) == 0, f"barra tangente no lado {lado} deveria estar totalmente ocluida"


def test_propriedade_triangulo_gigante_vertices_longe_nao_some():
    """Triangulo gigante com todos os vertices > 50 m longe da peca continua ocluindo a peca."""
    tri = _triangulo_unico([0.0, 0.0, 3.0], [160.0, 0.0, 3.0], [80.0, 160.0, 3.0])
    alvo = _caixa(79.5, 59.5, 0.0, 80.5, 60.5, 1.0)
    pecas = [tri, alvo]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, _ = _executar_e_validar_propriedade(pecas, ctx="gigante_vertices_longe")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx="gigante_vertices_longe")
    assert len(obt[1]) == 0, "peca totalmente sob triangulo gigante deveria ficar escondida"


# ---------------------------------------------------------------------------
# (3) Capturas reais (skipif ausente) e ganho de tempo >= 15%
# ---------------------------------------------------------------------------

def _carregar_captura(caminho_pkl: str) -> tuple[list[tuple[np.ndarray, np.ndarray]], float]:
    with open(caminho_pkl, "rb") as fh:
        pecas, meta = pickle.load(fh)
    ang = float(meta.get("angulo_graus", 0.001)) if isinstance(meta, dict) else 0.001
    return pecas, ang


@pytest.mark.parametrize(
    "nome,caminho_pkl",
    [
        pytest.param(
            nome,
            os.path.join(_DIR_DIST, f"{nome}.pkl"),
            marks=pytest.mark.skipif(
                not os.path.exists(os.path.join(_DIR_DIST, f"{nome}.pkl")),
                reason=f"captura real ausente: {os.path.join(_DIR_DIST, f'{nome}.pkl')}",
            ),
            id=nome,
        )
        for nome in ("bib_2", "bib_4", "c2x3_0", "cas_9")
    ],
)
def test_captura_real_hash_polilinhas_igual(nome, caminho_pkl):
    """Capturas reais menores (/tmp/t24e/dist/*.pkl): hash SHA-256 e bits identicos a referencia."""
    pecas, ang = _carregar_captura(caminho_pkl)
    ref = _linhas_visiveis_multi_ref(pecas, angulo_graus=ang, trabalhadores=None)
    obt = linhas_visiveis_multi(pecas, angulo_graus=ang, trabalhadores=None)
    assert _sha_polilinhas(obt) == _sha_polilinhas(ref), f"SHA-256 difere na captura real {nome}"
    _assert_bit_a_bit(obt, ref, ctx=f"captura_{nome}")


def _cena_benchmark_cull_muitas_pecas() -> list[tuple[np.ndarray, np.ndarray]]:
    """Terreno plano de 80k tris (so contorno) + 500 caixas pequenas espalhadas em 80x80 m."""
    terr = _terreno_plano(200, 200, 0.4, z0=0.0)  # 80.000 triangulos
    rng = np.random.default_rng(240_777)
    caixas = []
    for _ in range(500):
        x = float(rng.uniform(1.0, 78.0))
        y = float(rng.uniform(1.0, 78.0))
        caixas.append(_caixa(x, y, 0.25, x + 0.4, y + 0.4, 0.85))
    return [terr, *caixas]


def test_ganho_tempo_sintetico_muitas_pecas_pelo_menos_15_porcento():
    """Cena sintetica com muitas pecas espalhadas: ganho >= 15% sobre referencia e bits identicos."""
    pecas = _cena_benchmark_cull_muitas_pecas()
    # Aquecimento + igualdade bit a bit
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt = linhas_visiveis_multi(pecas, trabalhadores=1)
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx="bench_syn_cull")
    del ref, obt
    gc.collect()

    t_ref: list[float] = []
    t_prod: list[float] = []
    for k in range(3):
        if k % 2 == 0:
            t0 = time.perf_counter()
            _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
            t_ref.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            linhas_visiveis_multi(pecas, trabalhadores=1)
            t_prod.append(time.perf_counter() - t0)
        else:
            t0 = time.perf_counter()
            linhas_visiveis_multi(pecas, trabalhadores=1)
            t_prod.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
            t_ref.append(time.perf_counter() - t0)

    med_ref = statistics.median(t_ref)
    med_prod = statistics.median(t_prod)
    ganho = 1.0 - (med_prod / med_ref if med_ref > 0.0 else 1.0)
    assert med_prod <= 0.85 * med_ref, (
        f"ganho insuficiente na cena sintetica: prod={med_prod:.3f}s ref={med_ref:.3f}s "
        f"(ganho={ganho * 100:.1f}% < 15.0%)"
    )


def _selecionar_captura_bib_mobiliario() -> str | None:
    for nome in ("bib_1.pkl", "bib_3.pkl", "bib_0.pkl"):
        cand = os.path.join(_DIR_BIB_MOB, nome)
        if os.path.exists(cand):
            return cand
    outros = sorted(glob.glob(os.path.join(_DIR_BIB_MOB, "bib_*.pkl")))
    return outros[0] if outros else None


_PKL_BIB_MOB = _selecionar_captura_bib_mobiliario()


@pytest.mark.skipif(
    _PKL_BIB_MOB is None,
    reason=f"captura bib com mobiliario ausente em {_DIR_BIB_MOB}/bib_*.pkl",
)
def test_ganho_tempo_captura_real_bib_mobiliario_pelo_menos_15_porcento():
    """Captura real bib com mobiliario: hash identico e ganho de tempo >= 15% sobre referencia."""
    assert _PKL_BIB_MOB is not None
    pecas, ang = _carregar_captura(_PKL_BIB_MOB)

    gc.collect()
    t0 = time.perf_counter()
    ref = _linhas_visiveis_multi_ref(pecas, angulo_graus=ang, trabalhadores=None)
    t_ref = time.perf_counter() - t0
    sha_ref = _sha_polilinhas(ref)
    del ref
    gc.collect()

    t0 = time.perf_counter()
    obt = linhas_visiveis_multi(pecas, angulo_graus=ang, trabalhadores=None)
    t_prod = time.perf_counter() - t0
    sha_prod = _sha_polilinhas(obt)
    del obt

    assert sha_prod == sha_ref, (
        f"SHA-256 difere em {os.path.basename(_PKL_BIB_MOB)}"
    )
    ganho = 1.0 - (t_prod / t_ref if t_ref > 0.0 else 1.0)
    assert t_prod <= 0.85 * t_ref, (
        f"ganho insuficiente em {os.path.basename(_PKL_BIB_MOB)}: "
        f"prod={t_prod:.2f}s ref={t_ref:.2f}s (ganho={ganho * 100:.1f}% < 15.0%)"
    )


# ---------------------------------------------------------------------------
# (4) Determinismo 3 rodadas, threads 1 e 4, entrada nao mutada, sem vazamento
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "nome",
    ["varias_pecas_espalhadas", "triangulos_ingremes", "pecas_sobrepostas", "peca_toca_borda_dominio", "coordenadas_utm"],
)
def test_determinismo_3_rodadas_e_threads_1_e_4(nome):
    """3 rodadas consecutivas e trabalhadores=1 vs 4 produzem resultados bit a bit identicos."""
    pecas = _CENAS_ESPECIAIS[nome]()
    r1 = [linhas_visiveis_multi(pecas, trabalhadores=1) for _ in range(3)]
    r4 = [linhas_visiveis_multi(pecas, trabalhadores=4) for _ in range(3)]
    for k in (1, 2):
        _assert_bit_a_bit(r1[k], r1[0], ordem_exata=True, ctx=f"det_t1/{nome}/r{k}")
        _assert_bit_a_bit(r4[k], r4[0], ordem_exata=True, ctx=f"det_t4/{nome}/r{k}")
    _assert_bit_a_bit(r4[0], r1[0], ordem_exata=True, ctx=f"t4_vs_t1/{nome}")


@pytest.mark.parametrize("n_trab", [1, 4])
def test_entradas_nao_mutadas_e_somente_leitura(n_trab):
    """`linhas_visiveis_multi` nao muta arrays de entrada e aceita arrays somente-leitura."""
    pecas = _cena_varias_pecas_espalhadas()
    copias = [(v.copy(), t.copy()) for v, t in pecas]
    res = linhas_visiveis_multi(pecas, trabalhadores=n_trab)
    for idx, ((v, t), (v0, t0)) in enumerate(zip(pecas, copias)):
        assert np.array_equal(v.view(np.uint64), v0.view(np.uint64)), f"verts peca {idx} mutados"
        assert np.array_equal(t, t0), f"tris peca {idx} mutados"

    ro = []
    for v, t in copias:
        vr, tr = v.copy(), t.copy()
        vr.setflags(write=False)
        tr.setflags(write=False)
        ro.append((vr, tr))
    res_ro = linhas_visiveis_multi(ro, trabalhadores=n_trab)
    _assert_bit_a_bit(res_ro, res, ordem_exata=True, ctx=f"somente_leitura_t{n_trab}")


def test_cull_tris_nao_muta_entradas_somente_leitura():
    """`_cull_tris` aceita arrays somente-leitura sem mutar nenhum argumento."""
    kept = np.array([0, 2, 4, 6], dtype=np.int64)
    ea_ = np.array([[1.0, 1.0, 0.5], [2.0, 2.0, 0.5]], dtype=np.float64)
    eb_ = np.array([[2.0, 1.0, 0.5], [2.0, 3.0, 0.5]], dtype=np.float64)
    tx0 = np.linspace(0.0, 10.0, 8, dtype=np.float64)
    tx1 = tx0 + 1.0
    ty0 = np.linspace(0.0, 10.0, 8, dtype=np.float64)
    ty1 = ty0 + 1.0
    orig = [arr.copy() for arr in (kept, ea_, eb_, tx0, tx1, ty0, ty1)]
    for arr in (kept, ea_, eb_, tx0, tx1, ty0, ty1):
        arr.setflags(write=False)
    out = vis._cull_tris(kept, ea_, eb_, tx0, tx1, ty0, ty1, 0.0, 0.0, 11.0, 11.0)
    assert len(out) > 0
    for arr, arr0 in zip((kept, ea_, eb_, tx0, tx1, ty0, ty1), orig):
        assert np.array_equal(arr, arr0)


def test_sem_vazamento_cache_entre_chamadas_mesmo_dominio():
    """Duas cenas distintas com exatamente o mesmo dominio [0,10]^2 nao vazam cache."""
    cena_com_teto = [
        _caixa(0.0, 0.0, 0.0, 10.0, 10.0, 0.2),
        _caixa(2.0, 2.0, 3.0, 8.0, 8.0, 3.2),  # teto
        _caixa(4.0, 4.0, 0.5, 6.0, 6.0, 1.0),  # escondida
    ]
    cena_sem_teto = [
        _caixa(0.0, 0.0, 0.0, 10.0, 10.0, 0.2),
        _caixa(0.2, 0.2, 3.0, 0.8, 0.8, 3.2),  # longe da caixa central
        _caixa(4.0, 4.0, 0.5, 6.0, 6.0, 1.0),  # visivel
    ]
    ref_com = _linhas_visiveis_multi_ref(cena_com_teto, trabalhadores=1)
    ref_sem = _linhas_visiveis_multi_ref(cena_sem_teto, trabalhadores=1)
    for n_trab in (1, 4):
        for _ in range(2):
            r_com = linhas_visiveis_multi(cena_com_teto, trabalhadores=n_trab)
            r_sem = linhas_visiveis_multi(cena_sem_teto, trabalhadores=n_trab)
            _assert_bit_a_bit(r_com, ref_com, ordem_exata=True, ctx=f"cache_com_t{n_trab}")
            _assert_bit_a_bit(r_sem, ref_sem, ordem_exata=True, ctx=f"cache_sem_t{n_trab}")
            assert len(r_com[2]) == 0
            assert _comprimento_total(r_sem[2]) == pytest.approx(8.0, abs=1e-3)


# ---------------------------------------------------------------------------
# (5) Prototipo limpo em memoria + 4 mutantes plausiveis
# ---------------------------------------------------------------------------

def _rodar_prototipo_cull(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    modo_mutante: str | None = None,
) -> tuple[list[list[np.ndarray]], list[dict]]:
    """Executa o motor trocando `_cull_tris` por um prototipo limpo (ou mutante) da T24v."""
    cache_contiguo: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    cache_errado_peca: dict[int, np.ndarray] = {}
    stats: list[dict] = []

    def _cull_proto(kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom, n=512):
        c = max(dx_dom, dy_dom, 1e-9) / n
        W = int(dx_dom / c) + 3
        H = int(dy_dom / c) + 3

        key = (id(kept), id(tx0))
        box = cache_contiguo.get(key)
        if box is None:
            box = (
                np.ascontiguousarray(tx0[kept]),
                np.ascontiguousarray(tx1[kept]),
                np.ascontiguousarray(ty0[kept]),
                np.ascontiguousarray(ty1[kept]),
            )
            cache_contiguo[key] = box
        kx0, kx1, ky0, ky1 = box

        ex0_v = np.minimum(ea_[:, 0], eb_[:, 0])
        ex1_v = np.maximum(ea_[:, 0], eb_[:, 0])
        ey0_v = np.minimum(ea_[:, 1], eb_[:, 1])
        ey1_v = np.maximum(ea_[:, 1], eb_[:, 1])
        px0, px1 = float(ex0_v.min()), float(ex1_v.max())
        py0, py1 = float(ey0_v.min()), float(ey1_v.max())
        marg = 3.0 * c

        if modo_mutante == "caixa_nao_dilatada_sem_margem":
            m = (kx1 >= px0) & (kx0 <= px1) & (ky1 >= py0) & (ky0 <= py1)
        elif modo_mutante == "caixa_nao_dilatada_estrita":
            m = (kx1 > px0) & (kx0 < px1) & (ky1 > py0) & (ky0 < py1)
        elif modo_mutante == "caixa_so_em_x_esquece_y":
            m = (kx1 >= px0 - marg) & (kx0 <= px1 + marg)
        elif modo_mutante == "caixa_so_em_x_usa_x_em_y":
            m = (kx1 >= px0 - marg) & (kx0 <= px1 + marg) & (ky1 >= px0 - marg) & (ky0 <= px1 + marg)
        else:
            m = (kx1 >= px0 - marg) & (kx0 <= px1 + marg) & (ky1 >= py0 - marg) & (ky0 <= py1 + marg)

        if modo_mutante == "cache_compartilhado_pecas":
            if id(kept) in cache_errado_peca:
                res_cached = cache_errado_peca[id(kept)]
                stats.append({"n_pre": len(kept), "n_box": len(res_cached), "out": res_cached.copy()})
                return res_cached

        if not np.any(m):
            out_vazio = kept[:0]
            stats.append({"n_pre": len(kept), "n_box": 0, "out": out_vazio.copy()})
            if modo_mutante == "cache_compartilhado_pecas":
                cache_errado_peca[id(kept)] = out_vazio
            return out_vazio

        if modo_mutante == "indice_desalinhado":
            # Bug plausivel: usa posicoes locais no array contiguo como indices globais em `tx0`
            pos_loc = np.nonzero(m)[0]
            sub_kept = pos_loc
            sx0, sx1, sy0, sy1 = kx0[pos_loc], kx1[pos_loc], ky0[pos_loc], ky1[pos_loc]
        else:
            sub_kept = kept[m]
            sx0, sx1, sy0, sy1 = kx0[m], kx1[m], ky0[m], ky1[m]

        def ij(x, y):
            return (
                np.clip(np.floor((x - mn_x) / c).astype(np.int64), 0, W - 1),
                np.clip(np.floor((y - mn_y) / c).astype(np.int64), 0, H - 1),
            )

        ex0, ey0 = ij(ex0_v, ey0_v)
        ex1, ey1 = ij(ex1_v, ey1_v)
        ex0 = np.maximum(ex0 - 1, 0)
        ey0 = np.maximum(ey0 - 1, 0)
        ex1 = np.minimum(ex1 + 1, W - 1)
        ey1 = np.minimum(ey1 + 1, H - 1)
        dif = np.zeros((H + 1, W + 1), np.int64)
        np.add.at(dif, (ey0, ex0), 1)
        np.add.at(dif, (ey0, ex1 + 1), -1)
        np.add.at(dif, (ey1 + 1, ex0), -1)
        np.add.at(dif, (ey1 + 1, ex1 + 1), 1)
        occ = (dif.cumsum(0).cumsum(1)[:H, :W] > 0).astype(np.int64)
        sat = np.zeros((H + 1, W + 1), np.int64)
        sat[1:, 1:] = occ.cumsum(0).cumsum(1)
        qx0, qy0 = ij(sx0, sy0)
        qx1, qy1 = ij(sx1, sy1)
        tot = sat[qy1 + 1, qx1 + 1] - sat[qy0, qx1 + 1] - sat[qy1 + 1, qx0] + sat[qy0, qx0]
        out = sub_kept[tot > 0]
        stats.append({"n_pre": len(kept), "n_box": len(sub_kept), "out": out.copy()})
        if modo_mutante == "cache_compartilhado_pecas":
            cache_errado_peca[id(kept)] = out
        return out

    # Envolve `_visibilidade_hibrida_ref` trocando `_cull_tris_ref` por `_cull_proto`
    with mock.patch.object(vis, "_cull_tris", _cull_proto):
        # Usa `_visibilidade_hibrida_ref` com `_cull_tris_ref` -> `_cull_proto` para independencia total
        with mock.patch(f"{__name__}._cull_tris_ref", _cull_proto):
            res = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    return res, stats


def test_mutante_01_caixa_nao_dilatada():
    """Mutante 1: caixa sem dilatacao perde triangulo de borda (exata ou a <= 5e-7 m)."""
    pecas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        _caixa(80.0, 80.0, 0.0, 81.0, 81.0, 1.0),
        # Placa terminando exatamente em x=40.0 (tx1 == px0 da barra)
        _caixa(39.0, 40.0, 2.0, 40.0, 42.0, 2.2),
        # Placa terminando a 5e-7 m antes de x=40.0 (dentro da margem segura 1e-6)
        _caixa(39.0, 40.5, 2.5, 40.0 - 5e-7, 41.5, 2.7),
        # Barra vertical exatamente em x=40.0
        _quad_vertical(40.0, 40.2, 40.0, 41.8, 0.0, 1.0),
    ]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt_real, regs_real = _executar_e_validar_propriedade(pecas, ctx="m01_real")
    _assert_bit_a_bit(obt_real, ref, ordem_exata=True, ctx="m01_real")

    limpo, stats_limpo = _rodar_prototipo_cull(pecas, modo_mutante=None)
    _assert_bit_a_bit(limpo, ref, ordem_exata=True, ctx="m01_limpo")

    # (a) Sem dilatacao (marg=0, >=): perde triangulo a 5e-7 m -> morto pela propriedade de superconjunto
    _, stats_sem_marg = _rodar_prototipo_cull(pecas, modo_mutante="caixa_nao_dilatada_sem_margem")
    reg_bar = regs_real[4]
    with pytest.raises(AssertionError):
        _validar_conjunto_mantido(
            stats_sem_marg[4]["out"], reg_bar["kept_pre"], reg_bar["a_ek"], reg_bar["b_ek"],
            reg_bar["tx0"], reg_bar["tx1"], reg_bar["ty0"], reg_bar["ty1"],
            0.0, 0.0, 81.0, 81.0, marg_caixa=_MARGEM_PROPRIEDADE, ctx="m01_sem_margem",
        )

    # (b) Sem dilatacao estrita (>): perde triangulo de borda exata tx1==px0 -> morto na saida bit a bit
    mut_estrito, _ = _rodar_prototipo_cull(pecas, modo_mutante="caixa_nao_dilatada_estrita")
    with pytest.raises(AssertionError):
        _assert_bit_a_bit(mut_estrito, ref, ctx="m01_estrito")


def test_mutante_02_caixa_so_em_x():
    """Mutante 2: filtrar caixa so em X (esquece Y ou usa X em Y) e detectado."""
    pecas = []
    for k in range(20):
        y0 = 8.0 * k
        pecas.append(_caixa(0.0, y0, 0.0, 1.0, y0 + 1.0, 0.8))
        pecas.append(_caixa(0.2, y0 + 0.2, 1.5, 0.8, y0 + 0.8, 1.8))  # oclusor local em y0

    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt_real, _ = _executar_e_validar_propriedade(pecas, ctx="m02_real")
    _assert_bit_a_bit(obt_real, ref, ordem_exata=True, ctx="m02_real")

    limpo, stats_limpo = _rodar_prototipo_cull(pecas, modo_mutante=None)
    _assert_bit_a_bit(limpo, ref, ordem_exata=True, ctx="m02_limpo")

    def _assert_filtra_em_y(stats_list: list[dict]) -> None:
        fracs = [s["n_box"] / max(1, s["n_pre"]) for s in stats_list]
        med = statistics.median(fracs)
        assert med <= 0.25, f"filtro nao restringiu em Y: mediana n_box/n_pre = {med:.3f}"

    _assert_filtra_em_y(stats_limpo)

    # (a) Esquece Y: nao filtra ao longo de Y (mantem ~100% dos tris)
    _, stats_so_x = _rodar_prototipo_cull(pecas, modo_mutante="caixa_so_em_x_esquece_y")
    with pytest.raises(AssertionError):
        _assert_filtra_em_y(stats_so_x)

    # (b) Copy-paste (usa px0/px1 no eixo Y): perde oclusores de pecas com Y longe de X
    mut_xy, _ = _rodar_prototipo_cull(pecas, modo_mutante="caixa_so_em_x_usa_x_em_y")
    with pytest.raises(AssertionError):
        _assert_bit_a_bit(mut_xy, ref, ctx="m02_usa_x_em_y")


def test_mutante_03_cull_sobre_indice_errado_copia_desalinhada():
    """Mutante 3: usar posicao local na copia contigua como indice global falha quando mapa Z poda tris."""
    pecas = [
        # Varias pecas pequenas (<=25 celulas g) escondidas sob laje grande -> podadas pelo mapa Z!
        *[_caixa(2.0 + 0.2 * k, 2.0, 0.0, 2.03 + 0.2 * k, 2.03, 0.2) for k in range(10)],
        # Laje grande acima delas em z=3.0 (entra no mapa Z e poda as 10 pecas pequenas de kept)
        _caixa(0.0, 0.0, 2.8, 12.0, 6.0, 3.0),
        # Peca alvo longe em (30, 30) e seu oclusor local (indices altos, desalinhados de 0..len(kept)-1)
        _caixa(30.0, 30.0, 0.0, 32.0, 32.0, 1.0),
        _caixa(30.2, 30.2, 2.0, 31.8, 31.8, 2.4),
    ]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt_real, regs_real = _executar_e_validar_propriedade(pecas, ctx="m03_real")
    _assert_bit_a_bit(obt_real, ref, ordem_exata=True, ctx="m03_real")
    # Garante que o mapa Z realmente podou triangulos (logo kept != arange)
    assert len(regs_real[0]["kept_pre"]) < len(regs_real[0]["tx0"])

    limpo, _ = _rodar_prototipo_cull(pecas, modo_mutante=None)
    _assert_bit_a_bit(limpo, ref, ordem_exata=True, ctx="m03_limpo")

    mut_desal, _ = _rodar_prototipo_cull(pecas, modo_mutante="indice_desalinhado")
    with pytest.raises(AssertionError):
        _assert_bit_a_bit(mut_desal, ref, ctx="m03_desalinhado")


def test_mutante_04_cache_compartilhado_entre_pecas_errado():
    """Mutante 4: compartilhar `kept` filtrado entre pecas diferentes perde oclusores das pecas seguintes."""
    pecas = [
        _caixa(1.0, 1.0, 0.0, 3.0, 3.0, 1.0),
        _caixa(1.2, 1.2, 2.0, 2.8, 2.8, 2.3),
        _caixa(30.0, 30.0, 0.0, 32.0, 32.0, 1.0),
        _caixa(30.2, 30.2, 2.0, 31.8, 31.8, 2.3),
        _caixa(60.0, 60.0, 0.0, 62.0, 62.0, 1.0),
        _caixa(60.2, 60.2, 2.0, 61.8, 61.8, 2.3),
    ]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt_real, _ = _executar_e_validar_propriedade(pecas, ctx="m04_real")
    _assert_bit_a_bit(obt_real, ref, ordem_exata=True, ctx="m04_real")

    limpo, _ = _rodar_prototipo_cull(pecas, modo_mutante=None)
    _assert_bit_a_bit(limpo, ref, ordem_exata=True, ctx="m04_limpo")

    mut_cache, _ = _rodar_prototipo_cull(pecas, modo_mutante="cache_compartilhado_pecas")
    with pytest.raises(AssertionError):
        _assert_bit_a_bit(mut_cache, ref, ctx="m04_cache_compartilhado")
