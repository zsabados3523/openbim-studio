# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo complementar F0-S06-T24g (rodada 2): equivalencia com NaN/inf e encolher extremos.

Cobre as 2 divergencias da revisao anterior e variacoes relacionadas, comparando
`obim_geometria.recorte.recortar_fora_dos_aneis` com a referencia literal
`_referencia_recortar` do oraculo 1 (mesmo numero de polilinhas, mesmo shape e
`np.testing.assert_allclose(..., rtol=0.0, atol=1e-9, equal_nan=True)`):
1. Segmentos com `inf`/`-inf` que geram `aa == NaN` (nao descartados em `~(aa <= eps2)`).
2. `encolher=nan` quando ponto medio interno nao tem arestas candidatas (`cmask` vazio).
3. Variacoes: `NaN` em pontos de polilinha, `inf`/`-inf`/`NaN` em aneis, `encolher` `inf`/`-inf`/negativo
   e lote deterministico misto de finitos com `NaN`/`inf`.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from obim_geometria.recorte import recortar_fora_dos_aneis
from test_s06_t24g_recorte_vetorial_oraculo import _TOL, _rect, _referencia_recortar


def _assert_igual_ref_nan(res, ref, *, atol: float = _TOL, msg: str = "") -> None:
    assert isinstance(res, list), f"{msg}: saida deve ser list, veio {type(res)}"
    assert len(res) == len(ref), f"{msg}: qtd polilinhas {len(res)} != ref {len(ref)}"
    for idx, (r, e) in enumerate(zip(res, ref)):
        assert isinstance(r, np.ndarray), f"{msg} trecho {idx}: esperado ndarray, veio {type(r)}"
        assert r.ndim == 2 and r.shape[1] == 2, f"{msg} trecho {idx}: shape invalido {r.shape}"
        assert r.shape == e.shape, f"{msg} trecho {idx}: shape {r.shape} != ref {e.shape}"
        np.testing.assert_allclose(
            r,
            e,
            rtol=0.0,
            atol=atol,
            equal_nan=True,
            err_msg=f"{msg} trecho {idx}",
        )


def _comparar_com_ref(pols, aneis, *, encolher: float = 5e-4, msg: str = ""):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        err_ref = None
        err_res = None
        try:
            ref = _referencia_recortar(pols, aneis, encolher=encolher)
        except Exception as exc:
            err_ref = exc
            ref = None
        try:
            res = recortar_fora_dos_aneis(pols, aneis, encolher=encolher)
        except Exception as exc:
            err_res = exc
            res = None

    if err_ref is not None or err_res is not None:
        assert type(err_res) is type(err_ref), (
            f"{msg}: excecao divergente res={err_res!r} vs ref={err_ref!r}"
        )
        return None, None

    _assert_igual_ref_nan(res, ref, msg=msg)
    return res, ref


def test_achado1_segmento_com_inf_gera_aa_nan():
    """Achado 1: segmento com `inf - inf = NaN` nao pode ser descartado no filtro `aa <= eps2`."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]

    # Prova 1a da revisao anterior: (inf, 1.0) -> (inf, 1.0) gera dx=NaN, aa=NaN
    pol1 = [np.array([(2.0, 1.0), (np.inf, 1.0), (np.inf, 1.0)], dtype=float)]
    res1, ref1 = _comparar_com_ref(pol1, ret, encolher=5e-4, msg="achado1_inf_rep")
    assert len(res1) == 1 and res1[0].shape == (3, 2)
    assert len(ref1) == 1 and ref1[0].shape == (3, 2)

    # Prova 1b da revisao anterior: (inf, inf) -> (0.0, inf) gera dy=NaN, aa=NaN
    pol2 = [np.array([(5.0, -1.0), (np.inf, np.inf), (0.0, np.inf)], dtype=float)]
    res2, ref2 = _comparar_com_ref(pol2, ret, encolher=0.0, msg="achado1_inf_inf")
    assert len(res2) == 1 and res2[0].shape == (3, 2)
    assert len(ref2) == 1 and ref2[0].shape == (3, 2)

    # Variacoes com -inf, inf -> finito, -inf -> +inf e eixo Y
    variacoes = [
        ("neg_inf_rep", [np.array([(2.0, 1.0), (-np.inf, 1.0), (-np.inf, 1.0)], dtype=float)]),
        ("inf_para_fin", [np.array([(np.inf, 1.0), (2.0, 1.0), (-1.0, 1.0)], dtype=float)]),
        ("neginf_para_inf", [np.array([(-np.inf, 1.0), (np.inf, 1.0)], dtype=float)]),
        ("inf_em_y", [np.array([(2.0, -np.inf), (2.0, np.inf), (2.0, np.inf)], dtype=float)]),
    ]
    for nome, pols in variacoes:
        for enc in (0.0, 5e-4, 1e-2):
            _comparar_com_ref(pols, ret, encolher=enc, msg=f"{nome} enc={enc}")


def test_achado2_encolher_nan_com_cmask_vazio():
    """Achado 2: `encolher=nan` deve manter ponto interno como dentro quando `cmask` e vazio."""
    ret10 = _rect(0.0, 0.0, 10.0, 10.0)
    furo10 = _rect(3.0, 3.0, 7.0, 7.0, horario=True)
    ret_peq = _rect(0.0, 0.0, 4.0, 2.0)

    # Prova exata da revisao anterior: ponto medio (5, 5) longe das bordas (cmask vazio)
    lin = [np.array([(-1.0, 5.0), (11.0, 5.0)], dtype=float)]
    res, ref = _comparar_com_ref(lin, [ret10], encolher=float("nan"), msg="achado2_prova")
    assert len(res) == 2 and len(ref) == 2
    np.testing.assert_allclose(res[0], [(-1.0, 5.0), (0.0, 5.0)], rtol=0.0, atol=_TOL)
    np.testing.assert_allclose(res[1], [(10.0, 5.0), (11.0, 5.0)], rtol=0.0, atol=_TOL)

    # Variacoes com encolher=nan: furo, multiplos grupos, segmento 100% interno, zigue-zague
    cenarios = [
        ("furo", [ret10, furo10], lin),
        ("grupos", [[ret10], [ret_peq]], lin),
        ("interno_puro", [ret10], [np.array([(4.0, 5.0), (6.0, 5.0)], dtype=float)]),
        (
            "zigue_zague",
            [ret10, furo10],
            [np.array([(-1.0, 1.0), (5.0, 5.0), (11.0, 5.0), (5.0, 9.0), (-1.0, 9.0)], dtype=float)],
        ),
    ]
    for nome, aneis, pols in cenarios:
        _comparar_com_ref(pols, aneis, encolher=float("nan"), msg=f"achado2_{nome}")


@pytest.mark.parametrize("encolher", (0.0, 5e-4, 1e-2, float("nan")))
def test_variacoes_nan_em_pontos_de_polilinha(encolher: float):
    """NaN em pontos no inicio, meio, fim ou misturado com polilinhas finitas e com inf."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    pols = [
        np.array([(-1.0, 1.0), (5.0, 1.0)], dtype=float),
        np.array([(-1.0, 1.0), (np.nan, 1.0), (5.0, 1.0)], dtype=float),
        np.array([(np.nan, 1.0), (2.0, 1.0), (5.0, 1.0)], dtype=float),
        np.array([(-1.0, 1.0), (2.0, 1.0), (5.0, np.nan)], dtype=float),
        np.array([(np.nan, np.nan), (np.nan, np.nan)], dtype=float),
        np.array([(-1.0, 1.0), (2.0, np.nan), (5.0, 1.0)], dtype=float),
        np.array([(2.0, 1.0), (np.inf, 1.0), (np.inf, 1.0)], dtype=float),
    ]
    _comparar_com_ref(pols, ret, encolher=encolher, msg=f"nan_polilinha enc={encolher}")


@pytest.mark.parametrize("encolher", (0.0, 5e-4, float("nan"), float("inf"), -1.0))
def test_variacoes_inf_e_nan_em_aneis(encolher: float):
    """Aneis contendo +inf, -inf ou NaN produzem resultado ou excecao identicos a referencia."""
    pols = [
        np.array([(-5.0, 1.0), (5.0, 1.0)], dtype=float),
        np.array([(2.0, -1.0), (2.0, 3.0)], dtype=float),
        np.array([(1.0, 1.0), (np.inf, 1.0)], dtype=float),
    ]
    aneis_casos = [
        ("inf_pos_x", [np.array([(0.0, 0.0), (np.inf, 0.0), (np.inf, 2.0), (0.0, 2.0)], dtype=float)]),
        ("inf_neg_x", [np.array([(-np.inf, 0.0), (4.0, 0.0), (4.0, 2.0), (-np.inf, 2.0)], dtype=float)]),
        ("inf_um_vertice", [np.array([(0.0, 0.0), (4.0, 0.0), (np.inf, 2.0), (0.0, 2.0)], dtype=float)]),
        (
            "todos_inf",
            [np.array([(-np.inf, -np.inf), (np.inf, -np.inf), (np.inf, np.inf), (-np.inf, np.inf)], dtype=float)],
        ),
        ("nan_vertice", [np.array([(0.0, 0.0), (4.0, 0.0), (np.nan, 2.0), (0.0, 2.0)], dtype=float)]),
    ]
    for nome, aneis in aneis_casos:
        _comparar_com_ref(pols, aneis, encolher=encolher, msg=f"anel_{nome} enc={encolher}")


@pytest.mark.parametrize("encolher", (float("inf"), float("-inf"), -1e-4, -0.5, -10.0))
def test_variacoes_encolher_inf_e_negativo(encolher: float):
    """`encolher` infinito (+inf/-inf) e negativo em retangulo, furo e grupos sobrepostos."""
    ret10 = _rect(0.0, 0.0, 10.0, 10.0)
    furo10 = _rect(3.0, 3.0, 7.0, 7.0, horario=True)
    ret_sobre = _rect(6.0, 2.0, 12.0, 8.0)

    pols = [
        np.array([(-1.0, 5.0), (13.0, 5.0)], dtype=float),
        np.array([(-1.0, 0.0), (11.0, 0.0)], dtype=float),
        np.array([(4.0, 5.0), (6.0, 5.0)], dtype=float),
        np.array([(2.0, 1.0), (np.inf, 1.0), (np.inf, 1.0)], dtype=float),
    ]
    for nome, aneis in (
        ("retangulo", [ret10]),
        ("com_furo", [ret10, furo10]),
        ("grupos_sobrepostos", [[ret10, furo10], [ret_sobre]]),
    ):
        _comparar_com_ref(pols, aneis, encolher=encolher, msg=f"encolher_{nome} enc={encolher}")


def test_lote_misto_nan_inf_semente_fixa():
    """Lote deterministico (300 casos) combinando finitos, NaN, +inf, -inf e encolheres extremos."""
    rng = np.random.default_rng(20261121)
    encolheres = (0.0, 5e-4, 1e-2, -0.5, float("nan"), float("inf"), float("-inf"))
    vals = np.array([np.nan, np.inf, -np.inf, -2.0, 0.0, 1.0, 2.0, 5.0, 10.0], dtype=float)

    for caso in range(300):
        enc = encolheres[caso % len(encolheres)]
        n_g = int(rng.integers(1, 3))
        grupos = []
        for _ in range(n_g):
            g = []
            for _ in range(int(rng.integers(1, 3))):
                x0, y0 = float(rng.uniform(-2.0, 4.0)), float(rng.uniform(-2.0, 4.0))
                anel = _rect(x0, y0, x0 + float(rng.uniform(1.0, 8.0)), y0 + float(rng.uniform(1.0, 8.0)))
                if rng.random() < 0.25:
                    ri = int(rng.integers(0, len(anel)))
                    ci = int(rng.integers(0, 2))
                    anel[ri, ci] = float(rng.choice([np.inf, -np.inf, np.nan]))
                g.append(anel)
            grupos.append(g)
        aneis_in = grupos[0] if (n_g == 1 and caso % 2 == 0) else grupos

        pols = []
        for _ in range(int(rng.integers(1, 4))):
            n_pts = int(rng.integers(2, 7))
            p = rng.uniform(-3.0, 12.0, size=(n_pts, 2))
            if rng.random() < 0.75:
                for _ in range(int(rng.integers(1, n_pts + 1))):
                    p[int(rng.integers(0, n_pts)), int(rng.integers(0, 2))] = float(rng.choice(vals))
            pols.append(p)

        _comparar_com_ref(pols, aneis_in, encolher=enc, msg=f"lote_misto caso={caso} enc={enc}")
