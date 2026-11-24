# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 4 de test_s06_t24v_cull_por_peca_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24v_cull_por_peca_oraculo import _DIR_BIB_MOB, _MARGEM_PROPRIEDADE  # noqa: F401
from test_s06_t24v_cull_por_peca_oraculo_b import _assert_bit_a_bit, _caixa, _cena_varias_pecas_espalhadas, _comprimento_total, _executar_e_validar_propriedade, _linhas_visiveis_multi_ref, _quad_vertical, _sha_polilinhas, _validar_conjunto_mantido  # noqa: F401
from test_s06_t24v_cull_por_peca_oraculo_c import _CENAS_ESPECIAIS, _carregar_captura, _cena_benchmark_cull_muitas_pecas  # noqa: F401



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
        with mock.patch("test_s06_t24v_cull_por_peca_oraculo._cull_tris_ref", _cull_proto):
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
