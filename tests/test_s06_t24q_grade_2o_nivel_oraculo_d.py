# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 4 de test_s06_t24q_grade_2o_nivel_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import hashlib
import math
import os
import pickle
import statistics
import sys
import time
import tracemalloc
from unittest import mock
import numpy as np
import pytest
import obim_geometria.visib_mapa as visib_mapa
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
    _varrer_cels_triangulos,
)
from obim_geometria.visibilidade import _cull_tris, linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas as _cenas_t22a
from test_s06_t24j_motor_mapa_z_oraculo_b import CENAS as _CENAS_T24J  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo import _assert_equivalente, _caixa  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo_b import _calcular_g, _cantos_dominio, _cena_aresta_longa_atravessando_densa, _cena_peca_densa_80x80, _cena_triangulo_grande_atravessando_densa, _esfera_uv, _juntar_malhas, _rodar  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo_c import _subgrade_prototipo_bloco  # noqa: F401



def _rodar_prototipo_subgrade(pecas, *, modo_mutante: str | None = None):
    """Executa linhas_visiveis_multi substituindo apenas o laco `while` pelo prototipo da Opcao A."""
    cont_pares = [0]

    def _vis_proto(P, Tw, a, b, ea, eb, tol_z, d_eps, min_len, prep=None, memo=None):
        A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, area2 = (
            prep if prep is not None else _preparar_triangulos(P, Tw)
        )
        mn_x = float(min(a[:, 0].min(), b[:, 0].min(), tx0.min() if len(A) else math.inf))
        mn_y = float(min(a[:, 1].min(), b[:, 1].min(), ty0.min() if len(A) else math.inf))
        mx_x = float(max(a[:, 0].max(), b[:, 0].max(), tx1.max() if len(A) else -math.inf))
        mx_y = float(max(a[:, 1].max(), b[:, 1].max(), ty1.max() if len(A) else -math.inf))
        dx_dom = max(mx_x - mn_x, 0.0)
        dy_dom = max(mx_y - mn_y, 0.0)
        g = _calcular_g(dx_dom, dy_dom)
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
                starts, ends = hid.copy(), hid.copy()
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
        rem_t = _passagem_faixas_orientadas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z, d_eps, ctx, H_l)
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
                    iy_s, ix0_s, ix1_s = iy_s[ok_s], ix0_s[ok_s], ix1_s[ok_s]
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
                            tobj, tcel = tobj[ok_tc], tcel[ok_tc]
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
                            nz = cont[ecel] > 0
                            eobj, ecel = eobj[nz], ecel[nz]
                            if not len(eobj):
                                continue
                            _subgrade_prototipo_bloco(
                                ec, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                                tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                                tol_z, d_eps, H_l,
                                eobj, ecel, cont, ini_cel, tri_por_cel, bx0, by0, Wl, mn_x, mn_y, cg,
                                modo_mutante=modo_mutante, cont_pares=cont_pares,
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

    with mock.patch.object(vis, "_visibilidade_hibrida", _vis_proto):
        res = linhas_visiveis_multi(pecas, trabalhadores=1)
    return res, cont_pares[0]


def _cena_mutante_d_eps():
    """Cena cirurgica para detectar ausencia de folga `d_eps` em fronteiras de subcelula.

    A esfera densa fica ABAIXO (z in [0, 0.3]) para criar celulas densas (~40 tris/celula -> cg_sub = g/4)
    sem ocluir as barras acima (z = 1.0). Placas pequenas (z = 2.0) terminam a 2e-7 m antes de fronteiras
    exatas k*(g/16), enquanto barras quase verticais (z = 1.0) cruzam `xf` longe abaixo e passam em
    `x > xf` (subcelula adjacente) a ~4e-7 m (< d_eps = 1e-6 m) em toda a faixa de Y da placa.
    """
    g = _calcular_g(80.0, 80.0)
    # Esfera ~8k tris em raio 0.42 m (z em [0.0, 0.30]) -> celulas densas com ~35-55 tris/celula -> cg_sub = g/4
    v_esf, t_esf = _esfera_uv(40.0, 40.0, 0.15, 0.42, 64, 64, rot_x=0.5)
    v_esf[:, 2] = 0.15 + 0.35 * (v_esf[:, 2] - 0.15)  # achata em Z para ficar abaixo de z=0.35
    pecas = [(v_esf, t_esf), *_cantos_dominio(80.0, 80.0)]
    x_base = math.floor(40.0 / g) * g
    y_base = math.floor(40.0 / g) * g
    for k in range(1, 17):
        xf = x_base + k * (g / 16.0)
        yf = y_base + 0.004 * (k % 4)
        # Placa oclusora pequena (< g -> fora do mapa Z conservador), terminando em x = xf - 2e-7
        # Posicionada em y in [yf + 0.014, yf + 0.022], bem acima do cruzamento da barra em y = yf + 0.0028
        pecas.append(_caixa(xf - 0.004, yf + 0.014, 1.9, xf - 2e-7, yf + 0.022, 2.05))
        # Painel vertical fino (z in [0.9, 1.1], acima da esfera) indo de (xf - 5e-7, yf - 0.025)
        # ate (xf + 4e-7, yf + 0.025): ex0 <= tx1 passa o filtro AABB, e em y in [yf + 0.014, yf + 0.022]
        # todo subsegmento esta estritamente em x > xf (subcelula direita) a ~4-5.5e-7 m (< d_eps) da placa.
        v_bar = np.array(
            [
                [xf - 5e-7, yf - 0.025, 1.1],
                [xf + 4e-7, yf + 0.025, 1.1],
                [xf - 5e-7, yf - 0.025, 0.9],
                [xf + 4e-7, yf + 0.025, 0.9],
            ],
            dtype=np.float64,
        )
        t_bar = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        pecas.append((v_bar, t_bar))
    return pecas


def test_mutante_01_perder_triangulos_fronteira_subcelula(monkeypatch):
    """Mutante 1: off-by-one nas fronteiras de subcelula (ix1/iy1 - 1) perde triangulos densos."""
    pecas = _cena_peca_densa_80x80()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m01_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m01_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="perder_fronteira_subcelula")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m01_mutante")


def test_mutante_02_sem_folga_d_eps(monkeypatch):
    """Mutante 2: indexar subgrade sem folga `abs(d_eps)` perde oclusao a <= 5e-7 m de fronteira."""
    pecas = _cena_mutante_d_eps()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m02_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m02_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="sem_folga_d_eps")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m02_mutante")


def test_mutante_03_ignorar_T_grd_grande(monkeypatch):
    """Mutante 3: descartar triangulos `T_grd` (> 64 subcelulas) perde oclusao da placa atravessando a densa."""
    pecas = _cena_triangulo_grande_atravessando_densa()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m03_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m03_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="ignorar_T_grd")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m03_mutante")


def test_mutante_04_clip_errado_bbox_densa(monkeypatch):
    """Mutante 4: recortar aresta longa alterando `a, b, d` (t errado) corrompe os intervalos escondidos."""
    pecas = _cena_aresta_longa_atravessando_densa()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m04_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m04_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="clip_bbox_errado")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m04_mutante")


def test_mutante_05_duplicar_pares(monkeypatch):
    """Mutante 5: duplicar pares (processar celula densa nos dois niveis e sem dedup) preserva saida mas explode pares."""
    pecas = _cena_peca_densa_80x80()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m05_real")

    limpo, pares_limpo = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m05_proto_limpo")

    mut, pares_mut = _rodar_prototipo_subgrade(pecas, modo_mutante="duplicar_pares")
    # Corretude: C1 + dedup de _filtrar_e_recortar tornam duplicacao idempotente na saida
    _assert_equivalente(mut, ref, exigir_bit_a_bit=True, ctx="m05_mutante_idempotencia")

    # Deteccao: o mutante que duplica pares ultrapassa com folga o orcamento de pares do prototipo limpo
    def _assert_sem_explosao_pares(n_pares: int, n_base: int) -> None:
        assert n_pares <= int(1.25 * n_base), f"duplicacao de pares detectada: {n_pares} > 1.25 * {n_base}"

    _assert_sem_explosao_pares(pares_limpo, pares_limpo)
    with pytest.raises(AssertionError):
        _assert_sem_explosao_pares(pares_mut, pares_limpo)


# ---------------------------------------------------------------------------
# (6) Regressao de corretude: triangulo ingreme (sub_tzmax vs plano em d_eps)
# ---------------------------------------------------------------------------

def _cena_triangulo_ingreme(
    grad: float, tol_z: float, *, eps: float = 1e-6
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Esfera densa + aresta inclinada na mesma peca + triangulo quase vertical (|gx| = grad).

    A esfera em z <= 0.30 dispara a subgrade com folga (~1k tris/celula, >10M pares).
    O triangulo ingreme tem topo em z_top=2.0 e gradiente gx=-grad; a 0.90*eps de tx0
    o plano extrapolado em d_eps atinge z_top + 0.90*grad*eps > z_top. A aresta passa
    nesse trecho acima de z_top - tol_z (derrubada por sub_tzmax=z_top sem z_dil) mas
    abaixo do plano extrapolado (recortada pelo motor sem subgrade).
    """
    v_esf, t_esf = _esfera_uv(40.0, 40.0, 0.15, 0.35, 90, 90, rot_x=0.5)
    v_esf[:, 2] = 0.15 + 0.35 * (v_esf[:, 2] - 0.15)  # z <= 0.30

    dx_t = 1e-3 if grad <= 2000.0 else 1e-4
    z_top = 2.0
    v_steep = np.array(
        [
            [40.0, 40.00, z_top],
            [40.0 + dx_t, 40.00, z_top - grad * dx_t],
            [40.0, 40.02, z_top],
            [40.0 + dx_t, 40.02, z_top - grad * dx_t],
        ],
        dtype=np.float64,
    )
    t_steep = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)

    marg = grad * eps
    v_edge = np.array(
        [
            [40.0 - 0.90 * eps, 39.999, z_top - tol_z + 0.55 * marg],
            [40.0 + 0.10 * eps, 40.079, z_top - tol_z - 0.50 * marg],
            [40.0 - 0.90 * eps, 39.999, z_top - 0.20],
            [40.0 + 0.10 * eps, 40.079, z_top - 0.20],
        ],
        dtype=np.float64,
    )
    t_edge = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)

    peca_densa_com_aresta = _juntar_malhas((v_esf, t_esf), (v_edge, t_edge))
    return [peca_densa_com_aresta, (v_steep, t_steep), *_cantos_dominio(80.0, 80.0)]
