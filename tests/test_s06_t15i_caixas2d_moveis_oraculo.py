# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15i: reaproveitamento de caixas 2D de móveis no corte e planta.
Ref: docs/state/cards/F0-S06/F0-S06-T15i-caixas2d-moveis.md.
"""
from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
import re
import sys
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.unit
import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.desenho as desenho_geo
import obim_geometria.local as local
from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, corte, planta, selecao


class ExecutorEspiao:
    """Grava pedidos enviados ao executor auxiliar."""

    def __init__(self, delegate=local.executar):
        self.delegate = delegate
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, pedido: dict[str, Any]) -> dict[str, Any]:
        self.chamadas.append(copy.deepcopy(pedido))
        return self.delegate(pedido)

    @property
    def pedidos_desenho(self) -> list[dict[str, Any]]:
        return [p for p in self.chamadas if p.get("op") == "desenho"]


def _espia_cs(monkeypatch) -> list[int]:
    chamadas: list[int] = []
    real = ifcopenshell.geom.create_shape

    def espia(*args, **kwargs):
        el = args[1] if len(args) > 1 else kwargs.get("element")
        if el is not None:
            chamadas.append(el.id())
        return real(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "create_shape", espia)
    return chamadas


def _dimensoes_svg(svg: str, guid: str) -> tuple[float, float]:
    m = re.search(rf'<g\b[^>]*\b(?:ifc:)?guid=["\']{re.escape(guid)}["\'][^>]*>(.*?)</g>', svg, re.DOTALL)
    assert m is not None, f"Grupo guid={guid} ausente no SVG"
    d_m = re.search(r'\bd=["\']([^"\']+)["\']', m.group(1))
    assert d_m is not None, f"d ausente no grupo guid={guid}"
    nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", d_m.group(1))]
    xs, ys = nums[0::2], nums[1::2]
    return max(xs) - min(xs), max(ys) - min(ys)


def _criar_corte_xyz(f: Any, nome: str, xmin: float, xmax: float, ymin: float, ymax: float, zmin: float, zmax: float, k: float = 1.0) -> str:
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=(xmin * k, ymin * k, zmin * k), tamanho=(dx * k, dz * k, dy * k))
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -dy * k))
    return gid


def _modelo_parede_movel(schema: str = "IFC4", k: float = 1.0):
    exigir()
    f, pavs = X.estrutura(schema)
    if k != 1.0:
        X.em_milimetros(f)
    parede = X.caixa(f, "IfcWall", "Parede", 0.5 * k, 1.0 * k, 0.0 * k, 2.0 * k, 0.2 * k, 2.8 * k)
    movel = X.caixa(f, "IfcFurniture", "Movel", 1.0 * k, 1.0 * k, 0.0 * k, 1.0 * k, 0.6 * k, 1.2 * k)
    X.conter(f, pavs[0], parede, movel)
    gid_corte = _criar_corte_xyz(f, f"Corte_{schema}_{int(k)}", 0.0, 6.0, 0.0, 4.0, 0.0, 3.5, k=k)
    gid_planta = X.vista(f, "PLANTA", pavs[0], nome=f"Planta_{schema}_{int(k)}")
    return f, gid_corte, gid_planta, parede, movel, pavs[0]


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


# ---------------------------------------------------------------------------
# Reforço do oráculo (revisão crítica): posição absoluta, equivalência com o
# fallback, validação de caixas inválidas e chaves int/str.
# ---------------------------------------------------------------------------

def _grupo_path(svg: str, guid: str) -> tuple[list[tuple[float, float]], str]:
    """Pontos (x, y) absolutos do <path> do grupo guid e sua classe CSS."""
    m = re.search(rf'<g\b[^>]*\b(?:ifc:)?guid=["\']{re.escape(guid)}["\'][^>]*>(.*?)</g>', svg, re.DOTALL)
    assert m is not None, f"Grupo guid={guid} ausente no SVG"
    tag = re.search(r"<path\b[^>]*>", m.group(1))
    assert tag is not None, f"<path> ausente no grupo guid={guid}"
    d_m = re.search(r'\bd=["\']([^"\']+)["\']', tag.group(0))
    assert d_m is not None
    nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", d_m.group(1))]
    assert len(nums) == 10, f"Esperados 5 pontos (retângulo fechado), obtido {nums}"
    c_m = re.search(r'\bclass=["\']([^"\']*)["\']', tag.group(0))
    return list(zip(nums[0::2], nums[1::2])), (c_m.group(1) if c_m else "")


def _pts_aprox(a, b, tol=2e-3):
    assert len(a) == len(b)
    for (x0, y0), (x1, y1) in zip(a, b):
        assert x0 == pytest.approx(x1, abs=tol) and y0 == pytest.approx(y1, abs=tol), f"{a} != {b}"


def _pedido_planta(f, movel, pav, alt, caixas):
    return {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "PLANTA", "altura_corte_m": alt, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId},
        "moveis_como_caixa": True,
        "caixas_coords": caixas,
    }


def _rodar_planta(f, pedido):
    with auxiliar.preparar(f, pedido) as p:
        return desenho_geo.processar(p.pedido)


def _modelo_planta_assimetrico():
    """Móvel real em [1,2,0 , 4,7,1] (XYZ todos distintos, não cúbico) fora da origem."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    movel = X.caixa(f, "IfcFurniture", "MovelA", 1.0, 2.0, 0.0, 3.0, 5.0, 1.0)
    X.conter(f, pavs[0], movel)
    return f, movel, pavs[0]


@pytest.mark.parametrize("chave", ["int", "str"])
def test_planta_posicao_absoluta_assimetrica_e_equivale_ao_fallback(monkeypatch, chave):
    """Posição absoluta do retângulo 2D: X nunca troca com Y, ordem [xmin,ymin,zmin,xmax,ymax,zmax]."""
    f, movel, pav = _modelo_planta_assimetrico()
    caixa = [1.0, 2.0, 0.0, 4.0, 7.0, 1.0]
    k = movel.id() if chave == "int" else str(movel.id())
    chamadas_cs = _espia_cs(monkeypatch)

    res = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.5, {k: caixa}))
    assert res["ok"] is True and movel.id() not in chamadas_cs
    pts, _cls = _grupo_path(res["svg"], movel.GlobalId)
    # y do SVG = -y do mundo: x em [1,4], y em [-7,-2]; sequência exata dos cantos
    esperado = [(1.0, -7.0), (4.0, -7.0), (4.0, -2.0), (1.0, -2.0), (1.0, -7.0)]
    _pts_aprox(pts, esperado, tol=1e-3)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert (min(xs), max(xs)) == pytest.approx((1.0, 4.0), abs=1e-3)
    assert (min(ys), max(ys)) == pytest.approx((-7.0, -2.0), abs=1e-3)

    # Equivalência com o caminho antigo (create_shape sobre o mesmo elemento/geometria)
    chamadas_cs.clear()
    res_fb = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.5, {}))
    assert res_fb["ok"] is True and movel.id() in chamadas_cs
    pts_fb, _ = _grupo_path(res_fb["svg"], movel.GlobalId)
    _pts_aprox(pts, pts_fb)


@pytest.mark.parametrize("alt, incluido", [
    (0.5, True),    # zmin(0) <= alt < zmax(1)
    (0.0, True),    # alt == zmin: ainda incluído (excluir só se zmin > alt)
    (1.2, True),    # alt > zmax: caixa abaixo do corte continua desenhada (igual ao fallback)
    (-0.5, False),  # zmin > alt: excluído
])
def test_planta_faixa_z_usa_zmin_e_nao_zmax(monkeypatch, alt, incluido):
    f, movel, pav = _modelo_planta_assimetrico()
    caixa = [1.0, 2.0, 0.0, 4.0, 7.0, 1.0]
    chamadas_cs = _espia_cs(monkeypatch)
    res = _rodar_planta(f, _pedido_planta(f, movel, pav, alt, {movel.id(): caixa}))
    assert res["ok"] is True and movel.id() not in chamadas_cs
    if incluido:
        assert movel.id() in res["caixas"] and movel.GlobalId in res["svg"]
    else:
        assert movel.id() not in res["caixas"] and movel.GlobalId not in res["svg"]
    # o fallback decide igual (mesma geometria)
    res_fb = _rodar_planta(f, _pedido_planta(f, movel, pav, alt, {}))
    assert (movel.id() in res_fb["caixas"]) is incluido


def test_planta_zmin_zmax_invertidos_na_ordem_dos_campos(monkeypatch):
    """zmin/zmax distintos de x/y: caixa alta com zmin=0.3 > alt=0.2 é excluída; com alt=0.4 é incluída."""
    f, movel, pav = _modelo_planta_assimetrico()
    caixa = [1.0, 2.0, 0.3, 4.0, 7.0, 9.0]
    r1 = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.2, {movel.id(): caixa}))
    assert movel.id() not in r1["caixas"]
    r2 = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.4, {movel.id(): caixa}))
    assert movel.id() in r2["caixas"]
    pts, _ = _grupo_path(r2["svg"], movel.GlobalId)
    _pts_aprox(pts, [(1.0, -7.0), (4.0, -7.0), (4.0, -2.0), (1.0, -2.0), (1.0, -7.0)], tol=1e-3)


def _modelo_corte_deslocado(ycam: float):
    """Móvel real [1.5,0.7,0.2 , 3.5,2.0,1.1] (não cúbico); câmera deslocada da origem em (0.4, ycam, 0.3)."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    movel = X.caixa(f, "IfcFurniture", "MovelC", 1.5, 0.7, 0.2, 2.0, 1.3, 0.9)
    X.conter(f, pavs[0], movel)
    gid = _criar_corte_xyz(f, f"CorteDesl_{ycam}", 0.4, 6.4, ycam, ycam + 4.0, 0.3, 3.8)
    return f, gid, movel


_CAIXA_C = [1.5, 0.7, 0.2, 3.5, 2.0, 1.1]


def _pedido_corte(gid, movel, caixas):
    ped = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "CORTE", "guid": gid, "escala": 1.0},
        "moveis_caixa2d": True,
    }
    if caixas is not None:
        ped["caixas_coords"] = caixas
    return ped


@pytest.mark.parametrize("ycam, classe", [(1.2, "cut"), (3.0, "boundary"), (-1.0, "boundary")])
@pytest.mark.parametrize("chave", ["int", "str"])
def test_corte_coordenadas_absolutas_equivalem_ao_fallback(monkeypatch, ycam, classe, chave):
    """Câmera fora da origem + caixa não cúbica: <path> idêntico ao do create_shape; 'cruza' correto."""
    f, gid, movel = _modelo_corte_deslocado(ycam)
    k = movel.id() if chave == "int" else str(movel.id())
    chamadas_cs = _espia_cs(monkeypatch)

    res = desenho_geo._corte(f, _pedido_corte(gid, movel, {k: _CAIXA_C}), None, 0.0)
    assert res["ok"] is True and movel.id() not in chamadas_cs
    pts, cls = _grupo_path(res["svg"], movel.GlobalId)

    chamadas_cs.clear()
    res_fb = desenho_geo._corte(f, _pedido_corte(gid, movel, None), None, 0.0)
    assert movel.id() in chamadas_cs
    pts_fb, cls_fb = _grupo_path(res_fb["svg"], movel.GlobalId)

    _pts_aprox(pts, pts_fb)
    assert cls == cls_fb == classe
    if classe == "boundary":
        assert "cut" not in cls
    # dimensões: largura = dx (2.0), altura = dz (0.9)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert max(xs) - min(xs) == pytest.approx(2.0, abs=2e-3)
    assert max(ys) - min(ys) == pytest.approx(0.9, abs=2e-3)


def test_corte_posicao_acompanha_origem_da_camera():
    """Deslocar a câmera 0.5 m em X desloca o retângulo -0.5 no SVG (orig_cam_m não pode ser zerada/invertida)."""
    f1, gid1, m1 = _modelo_corte_deslocado(1.2)
    r1 = desenho_geo._corte(f1, _pedido_corte(gid1, m1, {m1.id(): _CAIXA_C}), None, 0.0)
    p1, _ = _grupo_path(r1["svg"], m1.GlobalId)

    # mesma caixa, caixa deslocada +0.5 m em X (mesmo plano de câmera) => retângulo desloca +0.5
    caixa_dx = [_CAIXA_C[0] + 0.5, _CAIXA_C[1], _CAIXA_C[2], _CAIXA_C[3] + 0.5, _CAIXA_C[4], _CAIXA_C[5]]
    r2 = desenho_geo._corte(f1, _pedido_corte(gid1, m1, {m1.id(): caixa_dx}), None, 0.0)
    p2, _ = _grupo_path(r2["svg"], m1.GlobalId)
    assert min(p[0] for p in p2) - min(p[0] for p in p1) == pytest.approx(0.5, abs=2e-3)
    assert min(p[1] for p in p2) == pytest.approx(min(p[1] for p in p1), abs=2e-3)

    # deslocar +0.4 m em Z move o retângulo no eixo vertical do SVG em módulo 0.4
    caixa_dz = [_CAIXA_C[0], _CAIXA_C[1], _CAIXA_C[2] + 0.4, _CAIXA_C[3], _CAIXA_C[4], _CAIXA_C[5] + 0.4]
    r3 = desenho_geo._corte(f1, _pedido_corte(gid1, m1, {m1.id(): caixa_dz}), None, 0.0)
    p3, _ = _grupo_path(r3["svg"], m1.GlobalId)
    assert abs(min(p[1] for p in p3) - min(p[1] for p in p1)) == pytest.approx(0.4, abs=2e-3)
    assert min(p[0] for p in p3) == pytest.approx(min(p[0] for p in p1), abs=2e-3)


def test_corte_caixa_que_nao_cruza_plano_nao_gera_cut():
    """Caixa inteiramente de um lado do plano de corte: classe boundary, nunca cut."""
    f, gid, movel = _modelo_corte_deslocado(1.2)
    # plano em y=1.2; caixa falsa totalmente em y>1.2 (e outra em y<1.2)
    for caixa in ([1.5, 1.5, 0.2, 3.5, 2.0, 1.1], [1.5, 0.1, 0.2, 3.5, 1.0, 1.1]):
        res = desenho_geo._corte(f, _pedido_corte(gid, movel, {movel.id(): caixa}), None, 0.0)
        _pts, cls = _grupo_path(res["svg"], movel.GlobalId)
        assert cls == "boundary" and "cut" not in cls
    # e a que atravessa o plano é cut
    res = desenho_geo._corte(f, _pedido_corte(gid, movel, {movel.id(): [1.5, 0.7, 0.2, 3.5, 2.0, 1.1]}), None, 0.0)
    assert _grupo_path(res["svg"], movel.GlobalId)[1] == "cut"


_NAN, _INF = float("nan"), float("inf")
_INVALIDAS = {
    "nan": [_NAN, 1.0, 0.0, 2.0, 2.0, 1.0],
    "nan_no_fim": [1.0, 1.0, 0.0, 2.0, 2.0, _NAN],
    "inf": [1.0, 1.0, 0.0, _INF, 2.0, 1.0],
    "menos_inf": [-_INF, 1.0, 0.0, 2.0, 2.0, 1.0],
    "curta5": [1.0, 1.0, 0.0, 2.0, 2.0],
    "vazia": [],
    "none": None,
    "string": "1,1,0,2,2,1",
    "strings_nao_numericas": ["a", "b", "c", "d", "e", "f"],
    "numero": 5.0,
    "invertida_x": [2.0, 1.0, 0.0, 1.0, 2.0, 1.0],
    "invertida_y": [1.0, 2.0, 0.0, 2.0, 1.0, 1.0],
    "invertida_z": [1.0, 1.0, 1.0, 2.0, 2.0, 0.0],
}


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
