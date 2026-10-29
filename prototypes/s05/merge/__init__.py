# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protótipo do merge de três vias por GlobalId (F0-S05-T11; ADR-002 §4.1 e §4.7). Sem Qt; `juntar` é o ponto de entrada."""
from .fusao import Resultado, juntar

__all__ = ["Resultado", "juntar"]
