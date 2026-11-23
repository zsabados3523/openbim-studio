# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24h_aneis_nao_agrupaveis_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from obim_geometria import aneis, corte_plano, oclusores, planta_cache, recorte, visibilidade
from openbim_app.desenho import estilo
from test_s06_t24c_planta_cache_oraculo import _tubo_np
from test_s06_t24f_secao_tolerante_oraculo import _caixa_100_aberta_np, _caixa_np, _caixas_fundidas_em_t_np, _extrair_polilinhas_d, _malha_sem_segmentos_corte_np, _montar_cena_numpy, _parse_svg, _transladar_malha  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _dist_pontos_a_segs, _polilinhas_mundo, _polilinhas_para_segs, _pontos_de_segs, _sha256  # noqa: F401
from test_s06_t24h_aneis_nao_agrupaveis_oraculo import _boas, _malha_anel_area_quase_zero_np, _malha_furo_sem_pai_np, _malha_mista_nao_agrupavel_e_aberta_np, _verificar_linhas_peca_ruim  # noqa: F401



def test_mutante_03_contagem_secoes_parciais_errada():
    """Mutante 3: nao contar (0) ou contar em dobro (2) quando a peca tem fechado nao agrupavel + aberto."""
    boas3 = _boas(3)
    r1, mot1 = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas3, (13, "G_SO_FECH_RUIM", "IfcDoor", _malha_anel_area_quase_zero_np(12.0, 0.0))], altura_corte_m=1.2)
    )
    assert mot1 is None and r1 is not None and type(r1["secoes_parciais"]) is int and r1["secoes_parciais"] == 1
    malha_mista = _malha_mista_nao_agrupavel_e_aberta_np(12.0, 0.0)
    r2, mot2 = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas3, (13, "G_MISTA_RUIM", "IfcFurnishingElement", malha_mista)], altura_corte_m=1.2)
    )
    assert mot2 is None and r2 is not None and type(r2["secoes_parciais"]) is int and r2["secoes_parciais"] == 1
    _verificar_linhas_peca_ruim(_parse_svg(r2["svg"]), "G_MISTA_RUIM", malha_mista, 1.2)


def test_mutante_04_limite_25_ignorado():
    """Mutante 4: ignorar o limite de 25% para pecas nao agrupaveis ou aceitar peca com segmentos sem anel."""
    assert planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(2), (12, "G_R0", "IfcWindow", _malha_furo_sem_pai_np(10.0, 0.0)),
                             (13, "G_R1", "IfcWindow", _malha_furo_sem_pai_np(16.0, 0.0))], altura_corte_m=1.2)
    ) == (None, "secao_aberta")
    assert planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(1), (11, "G_R0", "IfcDoor", _malha_anel_area_quase_zero_np(4.0, 0.0)),
                             (12, "G_R1", "IfcDoor", _malha_anel_area_quase_zero_np(8.0, 0.0)),
                             (13, "G_R2", "IfcDoor", _malha_anel_area_quase_zero_np(12.0, 0.0))], altura_corte_m=1.2)
    ) == (None, "secao_aberta")
    assert planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(4), (99, "G_SEM_SEGS", "IfcWall", _caixa_np(24.0, 0.0, 0.0, 24.0 + 2e-7, 2e-7, 2.8))], altura_corte_m=1.2)
    ) == (None, "secao_aberta")
