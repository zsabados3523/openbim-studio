# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15i (parte c): caixas 2D de móveis no corte e na planta.
Ref: docs/state/cards/F0-S06/F0-S06-T15i-caixas2d-moveis.md.
"""
from __future__ import annotations

import pytest
from s06_t15i_aux import *  # noqa: F401,F403


@pytest.mark.parametrize("nome", list(_INVALIDAS))
@pytest.mark.parametrize("chave", ["int", "str"])
def test_planta_caixa_invalida_cai_no_fallback(monkeypatch, nome, chave):
    f, movel, pav = _modelo_planta_assimetrico()
    chamadas_cs = _espia_cs(monkeypatch)
    k = movel.id() if chave == "int" else str(movel.id())
    res = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.5, {k: _INVALIDAS[nome]}))
    assert res["ok"] is True
    assert movel.id() in chamadas_cs, f"caixa inválida '{nome}' deve cair no fallback create_shape"
    assert movel.id() in res["caixas"]
    pts, _ = _grupo_path(res["svg"], movel.GlobalId)  # desenhado a partir da geometria real
    _pts_aprox(pts, [(1.0, -7.0), (4.0, -7.0), (4.0, -2.0), (1.0, -2.0), (1.0, -7.0)])


@pytest.mark.parametrize("nome", list(_INVALIDAS))
@pytest.mark.parametrize("chave", ["int", "str"])
def test_corte_caixa_invalida_cai_no_fallback(monkeypatch, nome, chave):
    f, gid, movel = _modelo_corte_deslocado(1.2)
    chamadas_cs = _espia_cs(monkeypatch)
    k = movel.id() if chave == "int" else str(movel.id())
    res = desenho_geo._corte(f, _pedido_corte(gid, movel, {k: _INVALIDAS[nome]}), None, 0.0)
    assert res["ok"] is True
    assert movel.id() in chamadas_cs, f"caixa inválida '{nome}' deve cair no fallback create_shape"
    assert movel.id() in res["caixas"]
    pts, cls = _grupo_path(res["svg"], movel.GlobalId)
    ref = desenho_geo._corte(f, _pedido_corte(gid, movel, None), None, 0.0)
    pts_ref, cls_ref = _grupo_path(ref["svg"], movel.GlobalId)
    _pts_aprox(pts, pts_ref)
    assert cls == cls_ref == "cut"


def test_gate_caixas_coords_vazio_ou_nulo_e_fallback(monkeypatch):
    """caixas_coords ausente, None ou {} => fallback em corte e planta."""
    f, gid, movel = _modelo_corte_deslocado(1.2)
    chamadas_cs = _espia_cs(monkeypatch)
    for valor in (None, {}):
        chamadas_cs.clear()
        res = desenho_geo._corte(f, _pedido_corte(gid, movel, valor), None, 0.0)
        assert res["ok"] is True and movel.id() in chamadas_cs and movel.id() in res["caixas"]
    f2, movel2, pav = _modelo_planta_assimetrico()
    for valor in (None, {}):
        chamadas_cs.clear()
        ped = _pedido_planta(f2, movel2, pav, 0.5, valor)
        res = _rodar_planta(f2, ped)
        assert res["ok"] is True and movel2.id() in chamadas_cs and movel2.id() in res["caixas"]
