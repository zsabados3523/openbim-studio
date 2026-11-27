# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de linhas visiveis por malha (vista de cima, z-buffer conservador + recorte analitico)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
import numbers
import os
import threading

import numpy as np

from obim_geometria.visib_base import (
    _arestas_candidatas,
    _cel_caixa,
    _expandir_celulas,
    _ler_quadro,
    _preparar_triangulos,
    _recortar_semi_espaco,
    _segmentos_corte_plano,
)
from obim_geometria.visib_faixas import _passagem_faixas_orientadas
from obim_geometria.visib_mapa import (
    _compactar_H,
    _filtrar_arestas_mapa_z,
    _mapa_z_conservador,
    _pares_celulas_e_recortar,
    _varrer_cels_triangulos,
)


def _cull_tris(
    kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom, n=512, kept_caixas=None
):
    """Mantem triangulos cuja caixa toca celula coberta pela caixa de alguma aresta (superconjunto)."""
    if len(kept) == 0 or len(ea_) == 0:
        return kept[:0]
    c = max(dx_dom, dy_dom, 1e-9) / n
    W = int(dx_dom / c) + 3
    H = int(dy_dom / c) + 3

    def ij(x, y):
        return (
            np.clip(np.floor((x - mn_x) / c).astype(np.int64), 0, W - 1),
            np.clip(np.floor((y - mn_y) / c).astype(np.int64), 0, H - 1),
        )

    if kept_caixas is not None:
        kx0, kx1, ky0, ky1 = kept_caixas
    else:
        kx0, kx1, ky0, ky1 = tx0[kept], tx1[kept], ty0[kept], ty1[kept]
    pad = max(3.0 * c, 1e-6)
    bx0 = float(min(ea_[:, 0].min(), eb_[:, 0].min())) - pad
    bx1 = float(max(ea_[:, 0].max(), eb_[:, 0].max())) + pad
    by0 = float(min(ea_[:, 1].min(), eb_[:, 1].min())) - pad
    by1 = float(max(ea_[:, 1].max(), eb_[:, 1].max())) + pad
    sel = np.nonzero((kx1 >= bx0) & (kx0 <= bx1) & (ky1 >= by0) & (ky0 <= by1))[0]
    if len(sel) == 0:
        return kept[:0]
    kept = kept[sel]
    ex0, ey0 = ij(np.minimum(ea_[:, 0], eb_[:, 0]), np.minimum(ea_[:, 1], eb_[:, 1]))
    ex1, ey1 = ij(np.maximum(ea_[:, 0], eb_[:, 0]), np.maximum(ea_[:, 1], eb_[:, 1]))
    ex0 = np.maximum(ex0 - 1, 0)
    ey0 = np.maximum(ey0 - 1, 0)
    ex1 = np.minimum(ex1 + 1, W - 1)
    ey1 = np.minimum(ey1 + 1, H - 1)
    gx0, gx1 = int(ex0.min()), int(ex1.max())
    gy0, gy1 = int(ey0.min()), int(ey1.max())
    qx0, qy0 = ij(kx0[sel], ky0[sel])
    qx1, qy1 = ij(kx1[sel], ky1[sel])
    ok_ov = (qx1 >= gx0) & (qx0 <= gx1) & (qy1 >= gy0) & (qy0 <= gy1)
    if not np.any(ok_ov):
        return kept[:0]
    kept = kept[ok_ov]
    Hl, Wl = gy1 - gy0 + 1, gx1 - gx0 + 1
    ex0_l, ex1_l = ex0 - gx0, ex1 - gx0
    ey0_l, ey1_l = ey0 - gy0, ey1 - gy0
    dif = np.zeros((Hl + 1, Wl + 1), np.int64)
    np.add.at(dif, (ey0_l, ex0_l), 1)
    np.add.at(dif, (ey0_l, ex1_l + 1), -1)
    np.add.at(dif, (ey1_l + 1, ex0_l), -1)
    np.add.at(dif, (ey1_l + 1, ex1_l + 1), 1)
    occ = (dif.cumsum(0).cumsum(1)[:Hl, :Wl] > 0).astype(np.int64)
    sat = np.zeros((Hl + 1, Wl + 1), np.int64)
    sat[1:, 1:] = occ.cumsum(0).cumsum(1)
    cx0 = np.maximum(qx0[ok_ov], gx0) - gx0
    cx1 = np.minimum(qx1[ok_ov], gx1) - gx0
    cy0 = np.maximum(qy0[ok_ov], gy0) - gy0
    cy1 = np.minimum(qy1[ok_ov], gy1) - gy0
    tot = sat[cy1 + 1, cx1 + 1] - sat[cy0, cx1 + 1] - sat[cy1 + 1, cx0] + sat[cy0, cx0]
    return kept[tot > 0]


_MEMO_MGR_LOCK = threading.Lock()
_MEMO_CHAVE_LOCKS: dict[tuple[int, tuple], list] = {}


def _visibilidade_hibrida(
    P, Tw, a, b, ea, eb, tol_z: float, d_eps: float, min_len: float, prep=None, memo=None
) -> np.ndarray:
    """Combina z-buffer conservador em grade adaptativa com recorte analitico exato em blocos."""
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

    def _calc_mapa_z():
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
        kept_ = np.nonzero(tri_keep)[0]
        kept_caixas_ = (
            np.ascontiguousarray(tx0[kept_]),
            np.ascontiguousarray(tx1[kept_]),
            np.ascontiguousarray(ty0[kept_]),
            np.ascontiguousarray(ty1[kept_]),
        )
        return z_full_, zf_flat_, W_, H_, kept_, kept_caixas_

    if memo is None:
        entrada = _calc_mapa_z()
    else:
        entrada = memo.get(chave)
        if entrada is None:
            mk = (id(memo), chave)
            with _MEMO_MGR_LOCK:
                slot = _MEMO_CHAVE_LOCKS.get(mk)
                if slot is None:
                    slot = [threading.Lock(), 0]
                    _MEMO_CHAVE_LOCKS[mk] = slot
                slot[1] += 1
            try:
                with slot[0]:
                    entrada = memo.get(chave)
                    if entrada is None:
                        entrada = memo.setdefault(chave, _calc_mapa_z())
            finally:
                with _MEMO_MGR_LOCK:
                    slot[1] -= 1
                    if slot[1] == 0:
                        _MEMO_CHAVE_LOCKS.pop(mk, None)
    z_full, zf_flat, W, H, kept_idx, kept_caixas = entrada
    d = b - a
    H_l = []
    ek_idx = _filtrar_arestas_mapa_z(a, d, z_full, mn_x, mn_y, g, tol_z, H_l)
    n_ref = len(kept_idx)
    if len(ek_idx) and len(kept_idx):
        kept_idx = _cull_tris(
            kept_idx, a[ek_idx], b[ek_idx], tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom,
            kept_caixas=kept_caixas,
        )
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
                _pares_celulas_e_recortar(
                    cand[loc_s[ok_s]], iy_s[ok_s], ix0_s[ok_s], ix1_s[ok_s], ek_idx, zf_flat, cg == g,
                    mn_x, mn_y, cg, Wc, Hc,
                    a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin,
                    nt_all, tol_z, d_eps, usar_subgrade, H_l,
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


def _limpar_malha(verts: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Valida malha e remove vertices nao finitos e triangulos invalidos."""
    V = np.asarray(verts, dtype=np.float64)
    T_raw = np.asarray(tris)
    if V.ndim != 2 or V.shape[1] != 3:
        raise ValueError("verts deve ter formato (N, 3) de vertices")
    if T_raw.ndim != 2 or T_raw.shape[1] != 3 or not np.issubdtype(T_raw.dtype, np.integer):
        raise ValueError("tris deve ter formato (M, 3) de indices inteiros de triangulos")
    if len(T_raw) == 0:
        return None
    T = T_raw.astype(np.int64, copy=False)
    if len(V) == 0 or T.min() < 0 or T.max() >= len(V):
        raise ValueError("tris contem indice de vertice fora dos limites")
    fin_v = np.isfinite(V).all(axis=1)
    T = T[fin_v[T].all(axis=1)]
    if len(T) == 0:
        return None
    if not fin_v.all():
        V, T = V[fin_v], (np.cumsum(fin_v, dtype=np.int64) - 1)[T]
    if np.abs(V).max() > 1e12:
        raise ValueError("coordenadas de verts excedem o limite de 1e12")
    return V, T


def _dedup_triangulos(Tw: np.ndarray) -> np.ndarray:
    """Remove triangulos degenerados em indice e duplicatas preservando a ordem."""
    Tw = Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])]
    if len(Tw) == 0:
        return Tw
    _, u_idx = np.unique(np.sort(Tw, axis=1), axis=0, return_index=True)
    return Tw[np.sort(u_idx)]


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
    return linhas_visiveis_multi([(verts, tris)], angulo_graus=angulo_graus, tol_z=tol_z, min_len=min_len)[0]


def _validar_oclusores_extra(oclusores_extra: list[np.ndarray] | None) -> np.ndarray | None:
    """Valida `oclusores_extra` e concatena os nao-vazios em (M, 3, 3) float64, ou retorna None."""
    if oclusores_extra is None:
        return None
    if not isinstance(oclusores_extra, list):
        raise ValueError("oclusores_extra deve ser uma lista de ndarrays (n, 3, 3) ou None")
    partes: list[np.ndarray] = []
    for item in oclusores_extra:
        if not isinstance(item, np.ndarray) or item.ndim != 3 or item.shape[1:] != (3, 3):
            raise ValueError("cada item de oclusores_extra deve ser um ndarray de formato (n, 3, 3)")
        if (
            item.dtype == bool
            or not np.issubdtype(item.dtype, np.number)
            or np.issubdtype(item.dtype, np.complexfloating)
        ):
            raise ValueError("oclusores_extra deve conter apenas numeros reais")
        arr = np.asarray(item, dtype=np.float64)
        if arr.size and (not np.isfinite(arr).all() or np.abs(arr).max() > 1e12):
            raise ValueError("oclusores_extra deve conter apenas coordenadas finitas ate 1e12")
        if len(arr):
            partes.append(arr)
    if not partes:
        return None
    return partes[0] if len(partes) == 1 else np.concatenate(partes, axis=0)


def _caixa_xy_ativos(ativos: list[tuple[int, tuple]]) -> tuple[float, float, float, float]:
    """Calcula a AABB XY das arestas candidatas das pecas ativas."""
    x0 = min(float(min(c[0][:, 0].min(), c[1][:, 0].min())) for _, c in ativos)
    x1 = max(float(max(c[0][:, 0].max(), c[1][:, 0].max())) for _, c in ativos)
    y0 = min(float(min(c[0][:, 1].min(), c[1][:, 1].min())) for _, c in ativos)
    y1 = max(float(max(c[0][:, 1].max(), c[1][:, 1].max())) for _, c in ativos)
    return x0, y0, x1, y1


def _anexar_oclusores_extra(
    P: np.ndarray,
    Tw_comb: np.ndarray,
    extra_tris: np.ndarray,
    tol_z: float,
    d_eps: float,
    caixa_xy: tuple[float, float, float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Filtra triangulos extras validos perto da AABB XY das pecas e anexa sem solda nem dedup."""
    if caixa_xy is None:
        pts_xy = P[Tw_comb, :2]
        cx0, cy0 = pts_xy.min(axis=(0, 1))
        cx1, cy1 = pts_xy.max(axis=(0, 1))
    else:
        cx0, cy0, cx1, cy1 = caixa_xy
    # margem conservadora (nao e tolerancia de Z): o filtro ja e inclusivo
    folga = max(abs(d_eps), 1e-6) + 2.0 * max(float(tol_z), 1e-6)
    px0, py0, px1, py1 = cx0 - folga, cy0 - folga, cx1 + folga, cy1 + folga
    ex0 = extra_tris[:, :, 0].min(axis=1)
    ex1 = extra_tris[:, :, 0].max(axis=1)
    ey0 = extra_tris[:, :, 1].min(axis=1)
    ey1 = extra_tris[:, :, 1].max(axis=1)
    tris = extra_tris[(ex1 >= px0) & (ex0 <= px1) & (ey1 >= py0) & (ey0 <= py1)]
    if len(tris) == 0:
        return P, Tw_comb
    cr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    tris = tris[np.isfinite(cr).all(axis=1) & np.any(cr != 0.0, axis=1)]
    if len(tris) == 0:
        return P, Tw_comb
    V_ex = tris.reshape(-1, 3)
    Tw_ex = np.arange(len(V_ex), dtype=np.int64).reshape(-1, 3)
    return np.vstack([P, V_ex]), np.vstack([Tw_comb, Tw_ex + len(P)])


def _validar_trabalhadores(trabalhadores: int | None) -> int | None:
    """Valida o numero de trabalhadores: None ou inteiro >= 1 (rejeita bool e nao-inteiros)."""
    if trabalhadores is None:
        return None
    if isinstance(trabalhadores, bool) or not isinstance(trabalhadores, numbers.Integral):
        raise ValueError("trabalhadores deve ser inteiro >= 1 ou None")
    n = int(trabalhadores)
    if n < 1:
        raise ValueError("trabalhadores deve ser >= 1")
    return n


def _resolver_trabalhadores_auto(n_pecas_cand: int, n_tris: int) -> int:
    """Resolve numero de threads no modo automatico via env OBIM_VISIB_THREADS ou heuristica."""
    raw = os.environ.get("OBIM_VISIB_THREADS")
    if raw is not None:
        try:
            n_env = int(raw)
        except ValueError:
            n_env = 0
        if n_env >= 1:
            return n_env
    if n_pecas_cand >= 8 and n_tris >= 20_000:
        return min(4, os.cpu_count() or 1)
    return 1


def linhas_visiveis_multi(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
    trabalhadores: int | None = None,
    oclusores_extra: list[np.ndarray] | None = None,
) -> list[list[np.ndarray]]:
    """Calcula polilinhas visiveis de cada peca com oclusao mutua por todas as pecas."""
    n_trab = _validar_trabalhadores(trabalhadores)
    extra_tris = _validar_oclusores_extra(oclusores_extra)
    for nome, val in (("angulo_graus", angulo_graus), ("tol_z", tol_z), ("min_len", min_len)):
        fv = float(val)
        if not (math.isfinite(fv) and fv >= 0.0):
            raise ValueError(f"{nome} deve ser nao-negativo e finito")
    if float(min_len) < 1e-5:
        raise ValueError("min_len deve ser >= 1e-5")
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
    d_eps = -1e-6
    Tw_comb = tw_oks[0] if len(tw_oks) == 1 else _dedup_triangulos(np.vstack(tw_oks))
    if extra_tris is not None:
        P, Tw_comb = _anexar_oclusores_extra(
            P, Tw_comb, extra_tris, tol_z, d_eps, caixa_xy=_caixa_xy_ativos(ativos)
        )
    prep = _preparar_triangulos(P, Tw_comb)
    memo = {}
    if n_trab is None:
        n_trab = _resolver_trabalhadores_auto(len(ativos), len(Tw_comb))
    res: list[list[np.ndarray]] = [[] for _ in pecas_l]
    if n_trab == 1:
        for i, c in ativos:
            res[i] = list(_visibilidade_hibrida(P, Tw_comb, *c, tol_z, d_eps, min_len, prep=prep, memo=memo))
        return res
    with ThreadPoolExecutor(max_workers=n_trab) as pool:
        try:
            futs = [
                (i, pool.submit(_visibilidade_hibrida, P, Tw_comb, *c, tol_z, d_eps, min_len, prep=prep, memo=memo))
                for i, c in ativos
            ]
            for i, fut in futs:
                res[i] = list(fut.result())
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return res


def _extrair_poligonos(geom) -> list:
    """Extrai Polygon nao-degenerados de uma geometria Shapely."""
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom] if geom.area > 1e-12 else []
    if hasattr(geom, "geoms"):
        out = []
        for g in geom.geoms:
            out.extend(_extrair_poligonos(g))
        return out
    return []


def _validar_janela(janela) -> tuple[float, float, float, float] | None:
    """Valida janela (umin, umax, vmin, vmax) ou None."""
    if janela is None:
        return None
    if not isinstance(janela, (tuple, list)) or len(janela) != 4:
        raise ValueError("janela deve ser tupla/lista de 4 numeros")
    vals = []
    for x in janela:
        if isinstance(x, bool) or not isinstance(x, numbers.Real):
            raise ValueError("janela deve conter apenas numeros reais")
        fx = float(x)
        if not math.isfinite(fx):
            raise ValueError("janela deve conter apenas numeros finitos")
        vals.append(fx)
    umin, umax, vmin, vmax = vals
    if not (umin < umax and vmin < vmax):
        raise ValueError("janela deve ter umin < umax e vmin < vmax")
    return (umin, umax, vmin, vmax)


def _validar_margem(margem) -> float:
    """Valida margem numerica finita >= 0 (nao bool)."""
    if isinstance(margem, bool) or not isinstance(margem, numbers.Real):
        raise ValueError("margem deve ser numerica")
    m = float(margem)
    if not (math.isfinite(m) and m >= 0.0):
        raise ValueError("margem deve ser finita e nao-negativa")
    return m


def secao_plana(verts: np.ndarray, tris: np.ndarray, quadro, *, janela=None) -> list:
    """Calcula poligonos 2D (u, v) da intersecao da malha com o plano w = 0 do quadro."""
    jan = _validar_janela(janela)
    limpa = _limpar_malha(verts, tris)
    if limpa is None:
        return []
    V, T = limpa
    origem, axes = _ler_quadro(quadro)
    Vq = (V - origem) @ axes.T
    w = Vq[:, 2]
    if not ((w > 1e-12).any() and (w < -1e-12).any()):
        return []
    tol_w = max(1e-9, float(np.abs(Vq).max()) * 1e-15)
    _, idx, inv = np.unique(
        np.round(Vq / tol_w).astype(np.int64), axis=0, return_index=True, return_inverse=True
    )
    P = Vq[idx]
    Tw = inv.ravel()[T]
    Tw = Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])]
    # dedup por orientacao: triangulos opostos (parede interna entre pecas encostadas) ficam, os dois
    rot = np.argmin(Tw, axis=1)
    Tc = np.stack([Tw[np.arange(len(Tw)), (rot + k) % 3] for k in range(3)], axis=1)
    _, u_idx = np.unique(Tc, axis=0, return_index=True)
    Tw = Tw[np.sort(u_idx)]
    segs = _segmentos_corte_plano(P, Tw)
    if len(segs) == 0:
        return []
    import functools
    import shapely
    from shapely.ops import polygonize, unary_union

    nodada = unary_union(shapely.linestrings(segs))
    pols = [shapely.make_valid(p) for p in polygonize(nodada)]
    pols = [p for p in pols if not p.is_empty and p.area > 1e-12]
    if not pols:
        return []
    # polygonize devolve todas as faces do arranjo (o vao de um furo tambem e uma face):
    # regra par-impar por raio para +u contra os segmentos originais (arestas internas
    # de pecas encostadas cruzam duas vezes e se anulam).
    pts = np.array([[q.x, q.y] for q in (p.representative_point() for p in pols)])
    impar = np.zeros(len(pols), dtype=np.int64)
    for i in range(0, len(pols), 256):  # em blocos: nunca materializa faces x segmentos inteiro
        py, px = pts[i:i + 256, 1:2], pts[i:i + 256, 0:1]
        y1, y2 = segs[:, 0, 1][None, :], segs[:, 1, 1][None, :]
        x1, x2 = segs[:, 0, 0][None, :], segs[:, 1, 0][None, :]
        f, k = np.nonzero((y1 > py) != (y2 > py))
        dy = y2[0, k] - y1[0, k]
        xi = x1[0, k] + (py[f, 0] - y1[0, k]) * (x2[0, k] - x1[0, k]) / dy
        ok = px[f, 0] < xi
        impar[i:i + 256] = np.bincount(f[ok], minlength=len(py))
    impar = impar % 2 == 1
    solidas = [p for p, k in zip(pols, impar) if k]
    if not solidas:
        return []
    pols = _extrair_poligonos(shapely.make_valid(unary_union(solidas)))
    if jan is None or not pols:
        return pols
    from shapely.geometry import box

    caixa = box(jan[0], jan[2], jan[1], jan[3])
    rec = []
    for p in pols:
        rec.extend(_extrair_poligonos(p.intersection(caixa)))
    return rec


def linhas_visiveis_vista(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    quadro,
    *,
    profundidade: float,
    janela=None,
    margem: float = 0.1,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
) -> list[list[np.ndarray]]:
    """Calcula polilinhas visiveis em (u, v) no quadro dentro de -profundidade <= w <= 0."""
    if isinstance(profundidade, bool):
        raise ValueError("profundidade invalida")
    try:
        prof = float(profundidade)
    except (TypeError, ValueError) as exc:
        raise ValueError("profundidade deve ser numerica") from exc
    if not (math.isfinite(prof) and prof >= 0.0):
        raise ValueError("profundidade deve ser finita e nao-negativa")
    jan = _validar_janela(janela)
    marg = _validar_margem(margem)

    pecas_l = list(pecas)
    if not pecas_l:
        return []
    origem, axes = _ler_quadro(quadro)
    vazia = (np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int64))
    recortadas: list[tuple[np.ndarray, np.ndarray]] = []
    for v, t in pecas_l:
        limpa = _limpar_malha(v, t)
        if limpa is None:
            recortadas.append(vazia)
            continue
        V, T = limpa
        Vq = (V - origem) @ axes.T
        V1, T1 = _recortar_semi_espaco(Vq, T, Vq[:, 2], plane_w=0.0)
        if len(T1) == 0:
            recortadas.append(vazia)
            continue
        V2, T2 = _recortar_semi_espaco(V1, T1, -prof - V1[:, 2], plane_w=-prof)
        if jan is not None and len(T2) > 0:
            umin, umax, vmin, vmax = jan
            pad = max(marg, 7e-7)
            for eixo, lim, eh_max in (
                (0, umax + pad, True),
                (0, umin - pad, False),
                (1, vmax + pad, True),
                (1, vmin - pad, False),
            ):
                if len(T2) == 0:
                    break
                s = (V2[:, eixo] - lim) if eh_max else (lim - V2[:, eixo])
                V2, T2 = _recortar_semi_espaco(V2, T2, s)
        recortadas.append((V2, T2) if len(T2) else vazia)
    return linhas_visiveis_multi(
        recortadas, angulo_graus=angulo_graus, tol_z=tol_z, min_len=min_len
    )
