# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15i (parte a): caixas 2D de móveis no corte e na planta.
Ref: docs/state/cards/F0-S06/F0-S06-T15i-caixas2d-moveis.md.
"""
from __future__ import annotations

import pytest
from s06_t15i_aux import *  # noqa: F401,F403


def test_selecao_popula_caixas_envolventes():
    """Caso 1: Seleção em corte popula sel.caixas_envolventes com tuplas de 6 floats (parede e móvel)."""
    campos = {f.name: f for f in dataclasses.fields(selecao.Selecao)}
    assert "caixas_envolventes" in campos, "Selecao deve declarar campo caixas_envolventes"
    campo_cx = campos["caixas_envolventes"]
    assert campo_cx.default_factory is dict or campo_cx.default == {}, "caixas_envolventes deve ter default dict"

    f, gid_corte, gid_planta, parede, movel, _pav = _modelo_parede_movel("IFC4")

    # CORTE: executa op: caixas e popula caixas_envolventes para todos os elementos selecionados
    sel_corte = selecao.selecionar(f, gid_corte, executor=local.executar)
    assert isinstance(sel_corte.caixas_envolventes, dict) and len(sel_corte.caixas_envolventes) > 0
    assert parede.id() in sel_corte.caixas_envolventes and movel.id() in sel_corte.caixas_envolventes
    for eid in (parede.id(), movel.id()):
        cx = sel_corte.caixas_envolventes[eid]
        assert isinstance(cx, tuple) and len(cx) == 6 and all(isinstance(v, float) for v in cx)
        assert cx[0] <= cx[3] and cx[1] <= cx[4] and cx[2] <= cx[5]

    # PLANTA: Selecao mantém caixas_envolventes como dict
    sel_planta = selecao.selecionar(f, gid_planta)
    assert isinstance(sel_planta.caixas_envolventes, dict)


def test_corte_e_planta_repassam_caixas_coords_no_pedido(monkeypatch):
    """Caso 2: gerar_corte e gerar_planta repassam pedido['caixas_coords'] ao processo auxiliar."""
    f, gid_corte, gid_planta, parede, movel, _pav = _modelo_parede_movel("IFC4")

    # CORTE: repassa caixas_coords com as coordenadas das caixas calculadas na seleção
    espiao_corte = ExecutorEspiao()
    corte.gerar_corte(f, gid_corte, executor=espiao_corte)
    assert len(espiao_corte.pedidos_desenho) == 1
    ped_corte = espiao_corte.pedidos_desenho[0]
    assert "caixas_coords" in ped_corte, "pedido de corte deve conter caixas_coords"
    cx_corte = ped_corte["caixas_coords"]
    assert isinstance(cx_corte, dict) and movel.id() in cx_corte and parede.id() in cx_corte
    for eid in (movel.id(), parede.id()):
        coords = cx_corte[eid]
        assert isinstance(coords, list) and len(coords) == 6 and all(isinstance(v, float) for v in coords)
        assert coords[0] <= coords[3] and coords[1] <= coords[4] and coords[2] <= coords[5]

    # PLANTA: repassa caixas_coords no pedido
    espiao_planta = ExecutorEspiao()
    planta.gerar_planta(f, gid_planta, executor=espiao_planta)
    assert len(espiao_planta.pedidos_desenho) == 1
    ped_planta = espiao_planta.pedidos_desenho[0]
    assert "caixas_coords" in ped_planta, "pedido de planta deve conter caixas_coords"
    assert isinstance(ped_planta["caixas_coords"], dict)

    # PLANTA com caixas_envolventes populadas: repassa exatamente as coordenadas
    sel_real = selecao.selecionar
    def _sel_com_caixas(*args, **kwargs):
        s = sel_real(*args, **kwargs)
        if hasattr(s, "caixas_envolventes"):
            cx_mock = dict(s.caixas_envolventes)
            cx_mock[movel.id()] = (1.0, 1.0, 0.0, 2.0, 2.0, 1.0)
            return dataclasses.replace(s, caixas_envolventes=cx_mock)
        return s

    monkeypatch.setattr(selecao, "selecionar", _sel_com_caixas)
    espiao_planta_cx = ExecutorEspiao()
    planta.gerar_planta(f, gid_planta, executor=espiao_planta_cx)
    ped_planta_cx = espiao_planta_cx.pedidos_desenho[0]
    assert ped_planta_cx["caixas_coords"].get(movel.id()) == [1.0, 1.0, 0.0, 2.0, 2.0, 1.0]


def test_corte_moveis_2d_usa_caixas_coords_sem_chamar_create_shape(monkeypatch):
    """Caso 3: _corte usa caixas_coords e NÃO chama create_shape para o móvel."""
    f, gid_corte, _gid_planta, _parede, movel, _pav = _modelo_parede_movel("IFC4")
    chamadas_cs = _espia_cs(monkeypatch)

    pedido = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "CORTE", "guid": gid_corte, "escala": 1.0},
        "moveis_caixa2d": True,
        "caixas_coords": {movel.id(): [1.0, 1.0, 0.0, 2.0, 2.0, 1.0]},
    }
    res = desenho_geo._corte(f, pedido, None, 0.0)

    assert res["ok"] is True
    assert movel.id() not in chamadas_cs, f"create_shape NÃO deve ser chamado para o móvel; chamadas: {chamadas_cs}"
    assert movel.id() in res["caixas"], f"Móvel deve constar em res['caixas']: {res.get('caixas')}"

    m_grp = re.search(rf'<g\b[^>]*\b(?:ifc:)?guid=["\']{re.escape(movel.GlobalId)}["\'][^>]*>(.*?)</g>', res["svg"], re.DOTALL)
    assert m_grp is not None, f"Grupo do móvel ausente no SVG: {res['svg']}"
    assert "IfcFurniture" in m_grp.group(0)
    assert re.search(r'<path\b[^>]*(?:\bd=["\'][^"\']+["\'][^>]*\bclass=["\'](boundary|cut)["\']|\bclass=["\'](boundary|cut)["\'][^>]*\bd=["\'][^"\']+["\'])', m_grp.group(1)) is not None

    # Aceita chave como str (formato JSON de IPC)
    chamadas_cs.clear()
    pedido_str = dict(pedido, caixas_coords={str(movel.id()): [1.0, 1.0, 0.0, 2.0, 2.0, 1.0]})
    res_str = desenho_geo._corte(f, pedido_str, None, 0.0)
    assert res_str["ok"] is True
    assert movel.id() not in chamadas_cs
    assert movel.id() in res_str["caixas"]


def test_planta_moveis_2d_usa_caixas_coords_sem_chamar_create_shape(monkeypatch):
    """Caso 4: desenho.processar (PLANTA) usa caixas_coords e NÃO chama create_shape para o móvel."""
    f, _gid_corte, _gid_planta, _parede, movel, pav = _modelo_parede_movel("IFC4")
    chamadas_cs = _espia_cs(monkeypatch)

    pedido = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId},
        "moveis_como_caixa": True,
        "caixas_coords": {movel.id(): [1.0, 1.0, 0.0, 2.0, 2.0, 1.0]},
    }
    with auxiliar.preparar(f, pedido) as p:
        res = desenho_geo.processar(p.pedido)

    assert res["ok"] is True
    assert movel.id() not in chamadas_cs, f"create_shape NÃO deve ser chamado para móvel na planta; chamadas: {chamadas_cs}"
    assert movel.id() in res["caixas"]

    m_grp = re.search(rf'<g\b[^>]*\b(?:ifc:)?guid=["\']{re.escape(movel.GlobalId)}["\'][^>]*>(.*?)</g>', res["svg"], re.DOTALL)
    assert m_grp is not None, f"Grupo do móvel ausente no SVG: {res['svg']}"
    assert "IfcFurniture" in m_grp.group(0)
    assert re.search(r'<path\b[^>]*\bd=["\'][^"\']+["\']', m_grp.group(1)) is not None
    largura, altura = _dimensoes_svg(res["svg"], movel.GlobalId)
    assert largura == pytest.approx(1.0, abs=0.01)
    assert altura == pytest.approx(1.0, abs=0.01)

    # Aceita chave como str (formato JSON de IPC)
    chamadas_cs.clear()
    pedido_str = dict(pedido, caixas_coords={str(movel.id()): [1.0, 1.0, 0.0, 2.0, 2.0, 1.0]})
    with auxiliar.preparar(f, pedido_str) as p2:
        res_str = desenho_geo.processar(p2.pedido)
    assert res_str["ok"] is True
    assert movel.id() not in chamadas_cs
    assert movel.id() in res_str["caixas"]


def test_planta_moveis_2d_caixas_coords_acima_da_corte_excluido(monkeypatch):
    """Caso 4b (borda): Móvel com zmin > altura_corte_m em caixas_coords é excluído da planta sem create_shape."""
    f, _gid_corte, _gid_planta, _parede, movel, pav = _modelo_parede_movel("IFC4")
    chamadas_cs = _espia_cs(monkeypatch)

    pedido = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId},
        "moveis_como_caixa": True,
        "caixas_coords": {movel.id(): [1.0, 1.0, 2.0, 2.0, 2.0, 3.0]},  # zmin=2.0 > altura_corte=1.2
    }
    with auxiliar.preparar(f, pedido) as p:
        res = desenho_geo.processar(p.pedido)

    assert res["ok"] is True
    assert movel.id() not in chamadas_cs
    assert movel.id() not in res["caixas"], "Móvel acima do corte não deve entrar em res['caixas']"
    assert movel.GlobalId not in res["svg"], "Móvel acima do corte não deve ser desenhado no SVG"


def test_fallback_chama_create_shape_quando_caixas_coords_ausente(monkeypatch):
    """Caso 5: Sem caixas_coords no pedido ou id ausente, corte e planta fazem fallback chamando create_shape."""
    f, gid_corte, _gid_planta, _parede, movel, pav = _modelo_parede_movel("IFC4")
    chamadas_cs = _espia_cs(monkeypatch)

    # Fallback em CORTE quando caixas_coords ausente
    pedido_corte = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "CORTE", "guid": gid_corte, "escala": 1.0},
        "moveis_caixa2d": True,
    }
    res_corte = desenho_geo._corte(f, pedido_corte, None, 0.0)
    assert res_corte["ok"] is True
    assert movel.id() in chamadas_cs, "Fallback deve chamar create_shape no corte quando caixas_coords ausente"
    assert movel.id() in res_corte["caixas"] and movel.GlobalId in res_corte["svg"]

    # Fallback em CORTE quando id não consta em caixas_coords
    chamadas_cs.clear()
    pedido_corte_incompleto = dict(pedido_corte, caixas_coords={999999: [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]})
    res_corte_inc = desenho_geo._corte(f, pedido_corte_incompleto, None, 0.0)
    assert res_corte_inc["ok"] is True
    assert movel.id() in chamadas_cs, "Fallback deve chamar create_shape no corte quando id ausente de caixas_coords"

    # Fallback em PLANTA quando caixas_coords ausente
    chamadas_cs.clear()
    pedido_planta = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId},
        "moveis_como_caixa": True,
    }
    with auxiliar.preparar(f, pedido_planta) as p:
        res_planta = desenho_geo.processar(p.pedido)
    assert res_planta["ok"] is True
    assert movel.id() in chamadas_cs, "Fallback deve chamar create_shape na planta quando caixas_coords ausente"
    assert movel.id() in res_planta["caixas"] and movel.GlobalId in res_planta["svg"]


def test_corte_moveis_2d_caixas_coords_em_milimetros(monkeypatch):
    """Caso 6: Modelo em milímetros (unit_scale=0.001) projeta móvel 2D com cotas corretas em metros."""
    f, gid_corte, _gid_planta, _parede, movel, _pav = _modelo_parede_movel("IFC4", k=1000.0)
    assert ifcopenshell.util.unit.calculate_unit_scale(f) == pytest.approx(0.001)
    chamadas_cs = _espia_cs(monkeypatch)

    # Caixa em metros do móvel (1000, 1000, 0) com dim (1000, 600, 1200) mm
    # -> x: [1.0, 2.0], y: [1.0, 1.6], z: [0.0, 1.2]
    pedido = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "CORTE", "guid": gid_corte, "escala": 0.001},
        "moveis_caixa2d": True,
        "caixas_coords": {movel.id(): [1.0, 1.0, 0.0, 2.0, 1.6, 1.2]},
    }
    res = desenho_geo._corte(f, pedido, None, 0.0)
    assert res["ok"] is True
    assert movel.id() not in chamadas_cs
    assert movel.id() in res["caixas"]

    largura, altura = _dimensoes_svg(res["svg"], movel.GlobalId)
    assert largura == pytest.approx(1.0, abs=0.02)
    assert altura == pytest.approx(1.2, abs=0.02)

    # Verifica também via gerar_corte completo com executor
    chamadas_cs.clear()
    c = corte.gerar_corte(f, gid_corte, executor=local.executar)
    assert movel.id() not in chamadas_cs
    assert movel.id() in c.caixas
    largura_c, altura_c = _dimensoes_svg(c.svg, movel.GlobalId)
    assert largura_c == pytest.approx(1.0, abs=0.02)
    assert altura_c == pytest.approx(1.2, abs=0.02)
