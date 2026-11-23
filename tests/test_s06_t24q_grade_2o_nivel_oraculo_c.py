# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24q_grade_2o_nivel_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24q_grade_2o_nivel_oraculo import _LIMITE_MEM_BYTES, _assert_bit_a_bit, _assert_equivalente, _caixa, _rss_bytes  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo_b import _cantos_dominio, _cena_aresta_longa_atravessando_densa, _cena_benchmark_sem_densa, _cena_dois_clusters_50m, _cena_peca_densa_80x80, _cena_triangulo_grande_atravessando_densa, _esfera_uv, _rodar  # noqa: F401



def test_desempenho_sem_peca_densa_nao_piora(monkeypatch):
    """Em cena sem peca densa, ligada leva <= 1,05x da desligada e devolve os mesmos bits."""
    pecas = _cena_benchmark_sem_densa()
    # Aquecimento
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx="bench_sem_densa")

    t_off: list[float] = []
    t_on: list[float] = []
    for _ in range(3):
        t0 = time.perf_counter()
        _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
        t_off.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
        t_on.append(time.perf_counter() - t0)

    med_off = statistics.median(t_off)
    med_on = statistics.median(t_on)
    razao = med_on / med_off if med_off > 0.0 else math.inf
    assert med_on <= 1.05 * med_off, (
        f"regressao em cena sem peca densa: ligada={med_on:.3f}s desligada={med_off:.3f}s "
        f"({razao:.3f}x > 1.05x)"
    )


# ---------------------------------------------------------------------------
# Testes (3): Contrato da variavel OBIM_VISIB_SUBGRADE (lida por chamada)
# ---------------------------------------------------------------------------

def test_contrato_env_lida_por_chamada(monkeypatch):
    """OBIM_VISIB_SUBGRADE='0' desliga; ausente ou '1' liga; alternancia por chamada funciona."""
    densa = _cena_peca_densa_80x80()
    pequena = _CENAS_T24J["casa_paredes_lajes_buracos"]()

    r_off_1 = _rodar(monkeypatch, densa, subgrade="0", trabalhadores=1)
    r_on_1 = _rodar(monkeypatch, densa, subgrade="1", trabalhadores=1)
    r_def = _rodar(monkeypatch, densa, subgrade=None, trabalhadores=1)
    r_off_2 = _rodar(monkeypatch, densa, subgrade="0", trabalhadores=1)

    _assert_equivalente(r_on_1, r_off_1, exigir_bit_a_bit=True, ctx="env_densa_1_vs_0")
    _assert_equivalente(r_def, r_on_1, exigir_bit_a_bit=True, ctx="env_densa_default_vs_1")
    _assert_equivalente(r_off_2, r_off_1, exigir_bit_a_bit=True, ctx="env_densa_0_repeat")

    p_off = _rodar(monkeypatch, pequena, subgrade="0", trabalhadores=1)
    p_def = _rodar(monkeypatch, pequena, subgrade=None, trabalhadores=1)
    _assert_equivalente(p_def, p_off, exigir_bit_a_bit=True, ctx="env_pequena_default_vs_0")


# ---------------------------------------------------------------------------
# Testes (4): Limite de memoria (3 pecas densas), determinismo 3x, imutabilidade
# ---------------------------------------------------------------------------

def test_memoria_subgrade_tres_pecas_densas(monkeypatch):
    """Cena com 3 pecas densas e cena com 2 clusters a 50 m ficam bem abaixo de 2 GB."""
    pecas_3 = [
        _esfera_uv(15.0, 20.0, 1.0, 0.32, 92, 92, rot_x=0.4),
        _esfera_uv(40.0, 40.0, 1.0, 0.32, 92, 92, rot_x=0.8),
        _esfera_uv(65.0, 60.0, 1.0, 0.32, 92, 92, rot_x=1.2),
        _caixa(14.5, 19.5, 0.0, 15.5, 20.5, 0.8),
        _caixa(39.5, 39.5, 0.0, 40.5, 40.5, 0.8),
        _caixa(64.5, 59.5, 0.0, 65.5, 60.5, 0.8),
        *_cantos_dominio(80.0, 80.0),
    ]
    ref_3 = _rodar(monkeypatch, pecas_3, subgrade="0", trabalhadores=1)
    ref_2c = _rodar(monkeypatch, _cena_dois_clusters_50m(), subgrade="0", trabalhadores=1)

    tracemalloc.start()
    try:
        obt_3 = _rodar(monkeypatch, pecas_3, subgrade="1", trabalhadores=1)
        obt_2c = _rodar(monkeypatch, _cena_dois_clusters_50m(), subgrade="1", trabalhadores=1)
        _, pico_tm = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    rss = _rss_bytes()
    _assert_equivalente(obt_3, ref_3, exigir_bit_a_bit=True, ctx="mem_3_densas")
    _assert_equivalente(obt_2c, ref_2c, exigir_bit_a_bit=True, ctx="mem_2_clusters_50m")
    assert pico_tm < 1024**3, f"pico tracemalloc da subgrade excedeu 1 GB: {pico_tm / 1e6:.1f} MB"
    assert rss < _LIMITE_MEM_BYTES, f"RSS excedeu 2 GB: {rss / 1e6:.1f} MB"


def test_determinismo_bit_a_bit_3_rodadas(monkeypatch):
    """3 rodadas consecutivas com subgrade ligada produzem exatamente os mesmos bits (1 e 4 threads)."""
    pecas = _cena_triangulo_grande_atravessando_densa()
    for n_trab in (1, 4):
        rodadas = [_rodar(monkeypatch, pecas, subgrade="1", trabalhadores=n_trab) for _ in range(3)]
        _assert_bit_a_bit(rodadas[1], rodadas[0], ctx=f"det_t{n_trab}_r1")
        _assert_bit_a_bit(rodadas[2], rodadas[0], ctx=f"det_t{n_trab}_r2")


def test_entradas_nao_mutadas_e_somente_leitura(monkeypatch):
    """Subgrade ligada nao altera arrays de entrada e aceita arrays somente-leitura."""
    pecas = _cena_aresta_longa_atravessando_densa()
    copias = [(v.copy(), t.copy()) for v, t in pecas]
    _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    for idx, ((v, t), (v0, t0)) in enumerate(zip(pecas, copias)):
        assert np.array_equal(v.view(np.uint64), v0.view(np.uint64)), f"verts peca {idx} mutados"
        assert np.array_equal(t, t0), f"tris peca {idx} mutados"

    ro_pecas = [(v.copy(), t.copy()) for v, t in copias]
    for v, t in ro_pecas:
        v.setflags(write=False)
        t.setflags(write=False)
    res_ro = _rodar(monkeypatch, ro_pecas, subgrade="1", trabalhadores=2)
    res_ref = _rodar(monkeypatch, copias, subgrade="0", trabalhadores=1)
    _assert_equivalente(res_ro, res_ref, exigir_bit_a_bit=True, ctx="somente_leitura")


# ---------------------------------------------------------------------------
# (5) Prototipo em memoria da Opcao A + 5 mutantes plausiveis
# ---------------------------------------------------------------------------

def _subgrade_prototipo_bloco(
    ec, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
    tol_z, d_eps, H_l,
    eobj, ecel, cont, ini_cel, tri_por_cel, bx0, by0, Wl, mn_x, mn_y, cg,
    *, modo_mutante: str | None, cont_pares: list[int],
):
    """Prototipo compacto em memoria da Opcao A sobre um lote de pares (eobj, ecel)."""
    lim_t = 24
    eps = abs(d_eps)

    def _emitir(pe, pt, a_loc=a, b_loc=b, d_loc=d):
        if len(pe):
            cont_pares[0] += len(pe)
            _filtrar_e_recortar(
                pe, pt, a_loc, b_loc, d_loc, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_l,
            )

    denso_cel = cont >= lim_t
    eh_denso = denso_cel[ecel]

    # Caminho normal (celulas nao densas; no mutante 'duplicar_pares', processa TODAS tambem no nivel grosso)
    mask_normal = np.ones(len(eobj), dtype=bool) if modo_mutante == "duplicar_pares" else ~eh_denso
    if np.any(mask_normal):
        eo_n, ec_n = eobj[mask_normal], ecel[mask_normal]
        nt_n = cont[ec_n]
        for p0, p1 in _fatias(nt_n, 200_000, chaves=eo_n):
            g3, kk = _rle_idx(nt_n[p0:p1])
            _emitir(eo_n[p0:p1][g3], tri_por_cel[ini_cel[ec_n[p0:p1]][g3] + kk])

    if not np.any(eh_denso):
        return

    # Celulas densas -> grade de 2o nivel
    eo_d, ec_d = eobj[eh_denso], ecel[eh_denso]
    cels_u = np.unique(ec_d)
    # Coleta triangulos unicos presentes nas celulas densas tocadas
    ts_parts = [tri_por_cel[ini_cel[c]:ini_cel[c] + cont[c]] for c in cels_u]
    t_densos = np.unique(np.concatenate(ts_parts))
    if not len(t_densos):
        return

    # Bbox do conjunto de celulas densas (em coordenadas do mundo)
    cy_d = by0 + (cels_u // Wl)
    cx_d = bx0 + (cels_u % Wl)
    sub_x0 = mn_x + float(cx_d.min()) * cg
    sub_x1 = mn_x + float(cx_d.max() + 1) * cg
    sub_y0 = mn_y + float(cy_d.min()) * cg
    sub_y1 = mn_y + float(cy_d.max() + 1) * cg
    dx_s = max(sub_x1 - sub_x0, cg)
    dy_s = max(sub_y1 - sub_y0, cg)
    area_d = float(len(cels_u)) * cg * cg
    cg_sub = max(1e-4, min(cg / 4.0, math.sqrt(area_d / max(len(t_densos) / 4.0, 1.0))))
    Ws = int(math.ceil(dx_s / cg_sub)) + 2
    Hs = int(math.ceil(dy_s / cg_sub)) + 2
    while Ws * Hs > 2_000_000:
        cg_sub *= 1.5
        Ws = int(math.ceil(dx_s / cg_sub)) + 2
        Hs = int(math.ceil(dy_s / cg_sub)) + 2

    folga = 0.0 if modo_mutante == "sem_folga_d_eps" else eps
    ix0, ix1, iy0, iy1 = _cel_caixa(
        tx0[t_densos] - folga, tx1[t_densos] + folga,
        ty0[t_densos] - folga, ty1[t_densos] + folga,
        sub_x0, sub_y0, cg_sub, Ws, Hs,
    )
    if modo_mutante == "perder_fronteira_subcelula":
        # Erro plausivel: perder triangulos na fronteira superior (ix1/iy1 subestimados em 1 celula)
        ix1 = np.maximum(ix0, ix1 - 1)
        iy1 = np.maximum(iy0, iy1 - 1)

    n_sub = (ix1 - ix0 + 1) * (iy1 - iy0 + 1)
    eh_grd = n_sub > 64
    t_grd = t_densos[eh_grd]
    t_fino_m = ~eh_grd

    # 1) T_grd fica no nivel cg (filtrado por celulas densas)
    if len(t_grd) and modo_mutante != "ignorar_T_grd":
        eo_u = np.unique(eo_d)
        # Pares (aresta densa, T_grd) com filtro rapido por bbox
        for g0 in range(0, len(t_grd), 256):
            tg = t_grd[g0:g0 + 256]
            pe_g = np.repeat(eo_u, len(tg))
            pt_g = np.tile(tg, len(eo_u))
            _emitir(pe_g, pt_g)

    # 2) T_fino vai para a subgrade cg_sub
    if not np.any(t_fino_m):
        return
    t_fino = t_densos[t_fino_m]
    tobj_s, tcel_s = _expandir_celulas(ix0[t_fino_m], ix1[t_fino_m], iy0[t_fino_m], iy1[t_fino_m], Ws)
    tobj_s = t_fino[tobj_s]
    ord_ts = np.argsort(tcel_s, kind="stable")
    tri_sub = tobj_s[ord_ts]
    cel_sub_ord = tcel_s[ord_ts]
    ncel_s = Ws * Hs
    cont_s = np.bincount(cel_sub_ord, minlength=ncel_s)
    ini_s = np.cumsum(cont_s) - cont_s
    sub_tzmax = np.full(ncel_s, -np.inf)
    np.maximum.at(sub_tzmax, cel_sub_ord, tzmax[tri_sub])

    eo_u = np.unique(eo_d)
    # Recorta cada aresta a bbox densa [sub_x0, sub_x1] x [sub_y0, sub_y1] (com folga) para gerar subsegmentos
    p0x, p0y = a[eo_u, 0], a[eo_u, 1]
    ddx, ddy = d[eo_u, 0], d[eo_u, 1]
    t_lo = np.zeros(len(eo_u), dtype=np.float64)
    t_hi = np.ones(len(eo_u), dtype=np.float64)
    pad_box = 0.0 if modo_mutante == "sem_folga_d_eps" else (eps + 1e-9)
    for comp_d, comp_p, lo_b, hi_b in (
        (ddx, p0x, sub_x0 - pad_box, sub_x1 + pad_box),
        (ddy, p0y, sub_y0 - pad_box, sub_y1 + pad_box),
    ):
        nz = np.abs(comp_d) > 1e-15
        fora = (~nz) & ((comp_p < lo_b) | (comp_p > hi_b))
        t_hi = np.where(fora, -1.0, t_hi)
        inv = np.where(nz, 1.0 / np.where(nz, comp_d, 1.0), 0.0)
        ta = (lo_b - comp_p) * inv
        tb = (hi_b - comp_p) * inv
        t_lo = np.where(nz, np.maximum(t_lo, np.minimum(ta, tb)), t_lo)
        t_hi = np.where(nz, np.minimum(t_hi, np.maximum(ta, tb)), t_hi)
    ok_clip = t_hi >= t_lo - 1e-12
    if not np.any(ok_clip):
        return
    eo_c = eo_u[ok_clip]
    t_lo = np.clip(t_lo[ok_clip], 0.0, 1.0)
    t_hi = np.clip(t_hi[ok_clip], 0.0, 1.0)
    a_clip = a[eo_c] + t_lo[:, None] * d[eo_c]
    d_clip = (t_hi - t_lo)[:, None] * d[eo_c]

    step_s = 0.999 * cg_sub
    span_s = np.maximum(np.abs(d_clip[:, 0]), np.abs(d_clip[:, 1]))
    nsub_s = np.maximum(1, np.ceil(span_s / step_s).astype(np.int64))

    # Mutante 4: clip errado da bbox densa (passa extremos recortados a_clip/d_clip em vez de a/b/d originais)
    a_pass, b_pass, d_pass = a, b, d
    if modo_mutante == "clip_bbox_errado":
        a_pass = a.copy()
        b_pass = b.copy()
        d_pass = d.copy()
        a_pass[eo_c] = a_clip
        b_pass[eo_c] = a_clip + d_clip
        d_pass[eo_c] = d_clip

    for e0, e1 in _fatias(nsub_s, 400_000):
        ec_s = eo_c[e0:e1]
        s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
            a_clip[e0:e1], d_clip[e0:e1], nsub_s[e0:e1], sub_x0, sub_y0, cg_sub, Ws, Hs
        )
        sobj, scel = _expandir_celulas(sx0, sx1, sy0, sy1, Ws)
        ok_sc = sub_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
        eo_s = ec_s[s_l[sobj[ok_sc]]]
        ecel_s = scel[ok_sc]
        if not len(eo_s):
            continue
        if modo_mutante != "duplicar_pares":
            ch_s = _dedup_int64(eo_s.astype(np.int64) * ncel_s + ecel_s)
            eo_s = ch_s // ncel_s
            ecel_s = ch_s % ncel_s
        nt_s = cont_s[ecel_s]
        nz = nt_s > 0
        eo_s, ecel_s, nt_s = eo_s[nz], ecel_s[nz], nt_s[nz]
        for p0, p1 in _fatias(nt_s, 200_000, chaves=eo_s):
            g3, kk = _rle_idx(nt_s[p0:p1])
            _emitir(
                eo_s[p0:p1][g3],
                tri_sub[ini_s[ecel_s[p0:p1]][g3] + kk],
                a_loc=a_pass, b_loc=b_pass, d_loc=d_pass,
            )
