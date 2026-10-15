# SPDX-License-Identifier: AGPL-3.0-or-later
"""Formato da geometria que Python e C++ trocam (F0-RG-04). Fonte única: o lado C++ (`obimcore/nucleo/cena.h` e `cena.cpp`)
repete estes números, e `tests/test_formato_malha.py` confere que os dois lados batem. Python puro, sem Qt e sem ifcopenshell.

Se mudar um número aqui, mude o C++ junto (o teste falha enquanto os dois divergirem)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Vértice: posição (3 x float32), normal (3 x float32), cor (4 x uint8) = 28 bytes, sem alinhamento extra.
DTYPE_VERTICE = np.dtype([("pos", "<f4", (3,)), ("normal", "<f4", (3,)), ("cor", "u1", (4,))])
# Linha da tabela de objetos: uma por peça do IFC.
DTYPE_OBJETO = np.dtype([
    ("id_step", "<i4"), ("guid", "S22"),
    ("primeiro_indice", "<u4"), ("n_indices", "<u4"), ("primeiro_vertice", "<u4"), ("n_vertices", "<u4"),
    ("caixa_min", "<f4", (3,)), ("caixa_max", "<f4", (3,)),
])
BYTES_VERTICE = DTYPE_VERTICE.itemsize  # 28
BYTES_OBJETO = DTYPE_OBJETO.itemsize  # 66


@dataclass(frozen=True)
class LoteMalha:
    """Um lote de malhas pronto para a tela: só numpy, sem Qt. `vertices` é DTYPE_VERTICE, `indices` uint32 (triângulos),
    `objetos` é DTYPE_OBJETO, `deslocamento` são 3 doubles (coordenadas do arquivo menos o centro da cena)."""
    indice_lote: int
    vertices: np.ndarray
    indices: np.ndarray
    objetos: np.ndarray
    deslocamento: np.ndarray
    produtos_feitos: int
    produtos_total: int
