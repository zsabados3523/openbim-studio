# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 5 de test_s06_t24v_cull_por_peca_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24v_cull_por_peca_oraculo_b import _assert_bit_a_bit, _caixa, _executar_e_validar_propriedade, _linhas_visiveis_multi_ref  # noqa: F401
from test_s06_t24v_cull_por_peca_oraculo_d import _rodar_prototipo_cull  # noqa: F401



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
