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
    _ler_quadro,
    _preparar_triangulos,
    _recortar_semi_espaco,
    _rle_idx,
    _segmentos_corte_plano,
    _subseg_cels,
)
from obim_geometria.visib_faixas import _passagem_faixas_orientadas
from obim_geometria.visib_mapa import (
    _compactar_H,
    _filtrar_e_recortar,
    _mapa_z_conservador,
    _varrer_cels_triangulos,
)


def _visibilidade_hibrida(
    P, Tw, a, b, ea, eb, tol_z: float, d_eps: float, min_len: float, prep=None
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


def linhas_visiveis_multi(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
) -> list[list[np.ndarray]]:
    """Calcula polilinhas visiveis de cada peca com oclusao mutua por todas as pecas."""
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
    Tw_comb = tw_oks[0] if len(tw_oks) == 1 else _dedup_triangulos(np.vstack(tw_oks))
    prep = _preparar_triangulos(P, Tw_comb)
    return [
        [] if c is None else list(_visibilidade_hibrida(P, Tw_comb, *c, tol_z, -1e-6, min_len, prep=prep))
        for c in cands
    ]


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


def secao_plana(verts: np.ndarray, tris: np.ndarray, quadro) -> list:
    """Calcula poligonos 2D (u, v) da intersecao da malha com o plano w = 0 do quadro."""
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
    return _extrair_poligonos(shapely.make_valid(unary_union(solidas)))


def linhas_visiveis_vista(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    quadro,
    *,
    profundidade: float,
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
        recortadas.append((V2, T2) if len(T2) else vazia)
    return linhas_visiveis_multi(
        recortadas, angulo_graus=angulo_graus, tol_z=tol_z, min_len=min_len
    )
