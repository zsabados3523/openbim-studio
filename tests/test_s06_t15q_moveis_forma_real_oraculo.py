# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15q: móveis com a forma real por padrão (caixa 2D só se pedida).
Ref: docs/state/cards/F0-S06/F0-S06-T15q-moveis-forma-real.md. Móvel em L (6 vértices; a caixa teria 4 e cobriria a área toda).
"""
from __future__ import annotations

import inspect

import pytest
from s06_t15q_aux import *  # noqa: F401,F403
from s06_t15q_aux import canto_da_caixa_vazio, caixa_2d, modelo_l, vertices_svg


def _forma_real(svg, guid):
    pts = vertices_svg(svg)
    assert not caixa_2d(svg, guid), "móvel não deve vir como grupo de caixa 2D"
    assert len(pts) == 6, f"L tem 6 vértices distintos, obtido {len(pts)}: {sorted(pts)}"
    assert canto_da_caixa_vazio(pts), "o contorno real deixa um canto da caixa vazio"


def _como_caixa(svg, guid):
    pts = vertices_svg(svg)
    assert caixa_2d(svg, guid), "com a opção True o móvel vira grupo de caixa 2D"
    assert len(pts) == 4 and not canto_da_caixa_vazio(pts), f"caixa tem 4 cantos, obtido {sorted(pts)}"


def test_defaults_das_assinaturas_sao_false():
    """Caso 1a: gerar_planta(moveis_como_caixa) e gerar_corte(moveis_caixa2d) têm default False, bool, keyword-only."""
    for fn, nome in ((planta.gerar_planta, "moveis_como_caixa"), (corte.gerar_corte, "moveis_caixa2d")):
        par = inspect.signature(fn).parameters[nome]
        assert par.default is False and par.kind is inspect.Parameter.KEYWORD_ONLY, f"{nome}: {par}"


def test_pedido_default_ao_motor_leva_false():
    """Caso 1b: sem passar a opção, o pedido de desenho leva False (bool); com True, leva True."""
    f, gp, gc, _m = modelo_l("XY")
    e = ExecutorEspiao()
    planta.gerar_planta(f, gp, executor=e)
    corte.gerar_corte(f, gc, executor=e)
    pp, pc = e.pedidos_desenho
    assert pp["moveis_como_caixa"] is False and pc["moveis_caixa2d"] is False
    e2 = ExecutorEspiao()
    planta.gerar_planta(f, gp, moveis_como_caixa=True, executor=e2)
    corte.gerar_corte(f, gc, moveis_caixa2d=True, executor=e2)
    pp, pc = e2.pedidos_desenho
    assert pp["moveis_como_caixa"] is True and pc["moveis_caixa2d"] is True


@pytest.mark.parametrize("cls", ["IfcFurniture", "IfcSystemFurnitureElement"])
def test_planta_default_forma_real_e_opcao_true_caixa(cls):
    """Caso 2a: planta default segue o contorno do L; moveis_como_caixa=True vira caixa; False explícito igual ao default."""
    f, gp, _gc, m = modelo_l("XY", cls)
    padrao = planta.gerar_planta(f, gp, executor=local.executar).svg
    _forma_real(padrao, m.GlobalId)
    _como_caixa(planta.gerar_planta(f, gp, moveis_como_caixa=True, executor=local.executar).svg, m.GlobalId)
    assert vertices_svg(planta.gerar_planta(f, gp, moveis_como_caixa=False, executor=local.executar).svg) == vertices_svg(padrao)


def test_corte_default_forma_real_e_opcao_true_caixa():
    """Caso 2b: o mesmo no corte (L na elevação)."""
    f, _gp, gc, m = modelo_l("XZ")
    padrao = corte.gerar_corte(f, gc, executor=local.executar).svg
    _forma_real(padrao, m.GlobalId)
    _como_caixa(corte.gerar_corte(f, gc, moveis_caixa2d=True, executor=local.executar).svg, m.GlobalId)
    assert vertices_svg(corte.gerar_corte(f, gc, moveis_caixa2d=False, executor=local.executar).svg) == vertices_svg(padrao)


def test_pedido_ao_motor_sem_chave_desenha_forma_real():
    """Caso 3: pedido de desenho sem moveis_* (mesmo com caixas_coords) desenha o L real, na planta e no corte."""
    f, gp, gc, m = modelo_l("XY")
    pav = f.by_guid(gp)
    caixa = {m.id(): [1.0, 1.0, 0.0, 3.0, 3.0, 1.0]}
    ped_p = {"op": "desenho", "protocolo": 1, "elementos": [[m.id(), m.GlobalId]], "caixas_coords": caixa,
             "vista": {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId if pav.is_a("IfcBuildingStorey") else f.by_type("IfcBuildingStorey")[0].GlobalId}}
    with auxiliar.preparar(f, ped_p) as p:
        assert "moveis_como_caixa" not in p.pedido
        res = desenho_geo.processar(p.pedido)
    assert res["ok"] is True
    _forma_real(res["svg"], m.GlobalId)
    f2, _gp2, gc2, m2 = modelo_l("XZ")
    ped_c = {"op": "desenho", "protocolo": 1, "elementos": [[m2.id(), m2.GlobalId]], "caixas_coords": {m2.id(): [1.0, 1.0, 0.0, 3.0, 1.6, 2.0]},
             "vista": {"tipo": "CORTE", "guid": gc2, "escala": 1.0}}
    with auxiliar.preparar(f2, ped_c) as p:
        assert "moveis_caixa2d" not in p.pedido
        res = desenho_geo.processar(p.pedido)
    assert res["ok"] is True
    _forma_real(res["svg"], m2.GlobalId)


def test_selecao_por_caixas_continua_com_movel_em_forma_real():
    """Caso 4: seleção/culling por caixas segue valendo: o móvel entra em sel.caixas_envolventes com a caixa certa,
    a planta o inclui e o corte default desenha o L inteiro."""
    f, gp, gc, m = modelo_l("XZ")
    sel = selecao.selecionar(f, gc, executor=local.executar)
    assert m.id() in sel.ids and m.id() in sel.caixas_envolventes
    assert sel.caixas_envolventes[m.id()] == pytest.approx((1.0, 1.0, 0.0, 3.0, 1.6, 2.0), abs=1e-6)
    assert m.id() in selecao.selecionar(f, gp, executor=local.executar).ids
    _forma_real(corte.gerar_corte(f, gc, executor=local.executar).svg, m.GlobalId)
    # com a opção True a caixa 2D também sai (mesmas caixas, nenhum elemento some)
    assert corte.gerar_corte(f, gc, moveis_caixa2d=True, executor=local.executar).caixas != ()
