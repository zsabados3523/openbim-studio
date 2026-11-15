# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19d6: o corte pedido pelo gerente usa o motor novo por padrao.

CONTRATO: `gerente._motor_padrao(tipo="corte", ...)` chama `gerar_corte(..., motor_visivel=True)`;
a opcao explicita do chamador (`motor_visivel=False`) prevalece.
"""
from __future__ import annotations

import test_s06_t18c2b_motor_padrao_previa_oraculo as base
from test_s06_t18c2b_motor_padrao_previa_oraculo import Planta, chamar_padrao, falsos  # noqa: F401


def _vistos(monkeypatch, **opcoes):
    from openbim_app.desenho import corte as cmod
    vistos = []

    def gerar_corte(ifc, guid, **kw):
        vistos.append(kw)
        return Planta(base.PESADOS, svg="<svg>corte</svg>")

    monkeypatch.setattr(cmod, "gerar_corte", gerar_corte)
    chamar_padrao(tipo="corte", **opcoes)
    return vistos


def test_corte_liga_motor_visivel_por_padrao(falsos, monkeypatch):
    assert _vistos(monkeypatch)[0]["motor_visivel"] is True


def test_corte_opcao_do_chamador_prevalece(falsos, monkeypatch):
    assert _vistos(monkeypatch, opcoes={"motor_visivel": False})[0]["motor_visivel"] is False
