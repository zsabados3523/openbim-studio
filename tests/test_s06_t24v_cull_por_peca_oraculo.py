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
