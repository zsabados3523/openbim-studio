# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24t_xor_corte_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import numpy as np
import pytest
from obim_geometria import aneis, corte_plano, planta_cache, recorte
from openbim_app.desenho import estilo
from test_s06_t19j1_corte_plano_oraculo import anel_quadrado, octaedro, piramide
from test_s06_t24c_planta_cache_oraculo import _tubo_np
from test_s06_t24f_secao_tolerante_oraculo import _caixa_np, _montar_cena_numpy, _parse_svg, _transladar_malha  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _dist_pontos_a_segs, _eh_fechada, _polilinhas_mundo, _polilinhas_para_segs, _sha256  # noqa: F401
from test_s06_t24h_aneis_nao_agrupaveis_oraculo import _boas, _checar_imutavel, _congelar_snapshot
from test_s06_t24t_xor_corte_oraculo import _combinar_malhas  # noqa: F401
from test_s06_t24t_xor_corte_oraculo_b import _quad_tris  # noqa: F401



def test_defeito_1b_blocos_justapostos_subdivididos_no_plano_z():
    """Dois blocos soldados subdivididos em z=1.0: aresta interna em z=1.0 (mult=2) cancela -> 6 segs."""
    verts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 1, 0], [1, 1, 0], [2, 1, 0],
            [0, 0, 1], [1, 0, 1], [2, 0, 1], [0, 1, 1], [1, 1, 1], [2, 1, 1],
            [0, 0, 2], [1, 0, 2], [2, 0, 2], [0, 1, 2], [1, 1, 2], [2, 1, 2],
        ],
        dtype=np.float64,
    )
    tris: list[list[int]] = []
    # Bloco 1 [0,1]x[0,1]x[0,2] dividido em z=1
    tris += _quad_tris(0, 3, 4, 1) + _quad_tris(12, 13, 16, 15)
    tris += _quad_tris(0, 1, 7, 6) + _quad_tris(1, 4, 10, 7) + _quad_tris(4, 3, 9, 10) + _quad_tris(3, 0, 6, 9)
    tris += _quad_tris(6, 7, 13, 12) + _quad_tris(7, 10, 16, 13) + _quad_tris(10, 9, 15, 16) + _quad_tris(9, 6, 12, 15)
    # Bloco 2 [1,2]x[0,1]x[0,2] dividido em z=1
    tris += _quad_tris(1, 4, 5, 2) + _quad_tris(13, 14, 17, 16)
    tris += _quad_tris(1, 2, 8, 7) + _quad_tris(2, 5, 11, 8) + _quad_tris(5, 4, 10, 11) + _quad_tris(4, 1, 7, 10)
    tris += _quad_tris(7, 8, 14, 13) + _quad_tris(8, 11, 17, 14) + _quad_tris(11, 10, 16, 17) + _quad_tris(10, 7, 13, 16)
    t = np.asarray(tris, dtype=np.int32)

    _, _, segs = corte_plano.cortar_malha_no_plano(verts, t, 1.0)
    fe, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 6 and len(fe) == 1 and ab == [], f"segs={len(segs)} fe={len(fe)} ab={len(ab)}"
    assert abs(aneis._area(fe[0])) == pytest.approx(2.0, abs=1e-9)


def test_defeito_2a_malha_soldada_paredes_alturas_diferentes_padrao_bib0():
    """Malha 100% soldada (0 dup verts), 2 blocos de alturas 2 e 3:
    arestas verticais colineares (1,5) e (1,12) geram mesmo ponto XY com indices distintos e devem cancelar."""
    v = np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2],
            [2, 0, 0], [2, 1, 0], [2, 0, 3], [2, 1, 3],
            [1, 0, 3], [1, 1, 3],
        ],
        dtype=np.float64,
    )
    t = np.array(
        [
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [0, 7, 3], [0, 4, 7],
            [1, 9, 8], [1, 2, 9], [12, 10, 11], [12, 11, 13],
            [1, 8, 10], [1, 10, 12], [8, 9, 11], [8, 11, 10], [9, 2, 13], [9, 13, 11],
            [1, 6, 2], [1, 12, 6], [6, 12, 13],
        ],
        dtype=np.int32,
    )
    assert len(np.unique(v, axis=0)) == len(v)  # 100% soldada
    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.0)
    fe, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 12 and len(fe) == 1 and ab == [], f"segs={len(segs)} fe={len(fe)} ab={len(ab)}"
    assert abs(aneis._area(fe[0])) == pytest.approx(2.0, abs=1e-9)


def test_defeito_2b_blocos_justapostos_vertices_duplicados_nao_soldados():
    """Dois blocos justapostos com vertices duplicados nao soldados em x=1 devem cancelar face interna."""
    v, t = _combinar_malhas(
        _caixa_np(0.0, 0.0, 0.0, 1.0, 1.0, 2.0),
        _caixa_np(1.0, 0.0, 0.0, 2.0, 1.0, 2.0),
    )
    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.0)
    fe, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 12 and len(fe) == 1 and ab == [], f"segs={len(segs)} fe={len(fe)} ab={len(ab)}"
    assert abs(aneis._area(fe[0])) == pytest.approx(2.0, abs=1e-9)


def test_defeito_2c_sintetico_bib0_idx245_arestas_verticais_colineares():
    """Caso sintetico minimo (4 verts, 2 tris) derivado de bib_0 idx=245 (tris 44 e 308):
    base soldada em z=743.0 com arestas verticais de alturas distintas (750.64 e 754.14) e segmento de 4.87 mm."""
    dx, dy = 0.00052103863, -0.03099562
    for ox, oy in ((0.0, 0.0), (324566.5673745996, 7405486.645066726)):
        v = np.array(
            [
                [ox, oy, 743.0],
                [ox, oy, 750.6400000000001],
                [ox, oy, 754.14],
                [ox + dx, oy + dy, 750.6400000000001],
            ],
            dtype=np.float64,
        )
        t = np.array([[3, 0, 1], [3, 2, 0]], dtype=np.int32)
        assert len(np.unique(v, axis=0)) == 4
        _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 744.2)
        assert segs.shape == (0, 4), f"segmento 4.87mm nao cancelou (ox={ox}): segs={len(segs)}"
