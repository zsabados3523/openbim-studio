# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15h: profundidade de corte configurável (far clip / culling de profundidade).
Ref: docs/state/cards/F0-S06/F0-S06-T15h-profundidade-corte.md."""
from __future__ import annotations

import copy
import inspect
from pathlib import Path
import sys
from typing import Any

import ifcopenshell.util.unit
import pytest
import s06_t04_aux as A
import s06_t07_aux as X
import s06_t07b_aux as B
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.desenho as desenho_geo
import obim_geometria.local as local
from openbim_app import vistas_ifc
from openbim_app.desenho import corte, selecao


class ExecutorEspiao:
    def __init__(self, delegate=local.executar):
        self.delegate = delegate
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, pedido: dict[str, Any]) -> dict[str, Any]:
        self.chamadas.append(copy.deepcopy(pedido))
        return self.delegate(pedido)

    @property
    def pedidos_caixas(self) -> list[dict[str, Any]]:
        return [p for p in self.chamadas if p.get("op") == "caixas"]

    @property
    def ids_pedidos_caixas(self) -> set[int]:
        return {item[0] for p in self.pedidos_caixas for item in p.get("elementos", [])}

    @property
    def pedidos_desenho(self) -> list[dict[str, Any]]:
        return [p for p in self.chamadas if p.get("op") == "desenho"]


def _criar_corte_xyz(f: Any, nome: str, xmin: float, xmax: float, ymin: float, ymax: float, zmin: float, zmax: float, k: float = 1.0) -> str:
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=(xmin * k, ymin * k, zmin * k), tamanho=(dx * k, dz * k, dy * k))
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -dy * k))
    return gid


def _modelo_sintetico_corte(esquema: str = "IFC4", k: float = 1.0, prof_original: float = 20.0):
    exigir()
    f = A.novo_arquivo(esquema)
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = "MILLI" if k == 1000.0 else None
    site, edif = X.elemento(f, "IfcSite", "Terreno"), X.elemento(f, "IfcBuilding", "Edificio")
    pav = X.elemento(f, "IfcBuildingStorey", "Pav0", Elevation=0.0)
    pav.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0.0, 0.0, 0.0)))
    X.agregar(f, f.by_type("IfcProject")[0], site)
    X.agregar(f, site, edif)
    X.agregar(f, edif, pav)
    p1 = X.caixa(f, "IfcWall", "Parede1", 0.0 * k, -0.1 * k, 0.0 * k, 2.0 * k, 0.2 * k, 2.8 * k)
    p2 = X.caixa(f, "IfcWall", "Parede2", 3.0 * k, 2.0 * k, 0.0 * k, 2.0 * k, 0.2 * k, 2.8 * k)
    p3 = X.caixa(f, "IfcWall", "Parede3", 6.0 * k, 10.0 * k, 0.0 * k, 2.0 * k, 0.2 * k, 2.8 * k)
    X.conter(f, pav, p1, p2, p3)
    gid = _criar_corte_xyz(f, f"Corte_FarClip_{esquema}", -0.5, 9.0, 0.0, prof_original, -0.5, 3.5, k=k)
    return f, gid, p1, p2, p3


def _tem_projecao_em_x(svg: str, x_min: float, x_max: float) -> bool:
    proj = C.projecao(svg)
    pts = [pt for sp in B.subcaminhos(proj) for pt in sp]
    return any(x_min <= p[0] <= x_max for p in pts)


def test_assinatura_gerar_corte_profundidade_corte():
    """Caso 1: Inspeciona assinatura de gerar_corte e selecao.selecionar e repasse no pedido."""
    sig_corte = inspect.signature(corte.gerar_corte)
    assert "profundidade_corte" in sig_corte.parameters
    param_corte = sig_corte.parameters["profundidade_corte"]
    assert param_corte.default is None
    assert param_corte.kind == inspect.Parameter.KEYWORD_ONLY

    sig_sel = inspect.signature(selecao.selecionar)
    assert "profundidade_corte" in sig_sel.parameters
    param_sel = sig_sel.parameters["profundidade_corte"]
    assert param_sel.default is None
    assert param_sel.kind == inspect.Parameter.KEYWORD_ONLY

    f, gid, _p1, _p2, _p3 = _modelo_sintetico_corte("IFC4")
    espiao_float = ExecutorEspiao()
    corte.gerar_corte(f, gid, profundidade_corte=3.0, executor=espiao_float)
    assert len(espiao_float.pedidos_desenho) == 1
    ped_vista = espiao_float.pedidos_desenho[0]["vista"]
    assert "profundidade_corte" in ped_vista
    assert ped_vista["profundidade_corte"] == pytest.approx(3.0)
    assert isinstance(ped_vista["profundidade_corte"], float)

    espiao_int = ExecutorEspiao()
    corte.gerar_corte(f, gid, profundidade_corte=5, executor=espiao_int)
    assert len(espiao_int.pedidos_desenho) == 1
    ped_vista_int = espiao_int.pedidos_desenho[0]["vista"]
    assert ped_vista_int["profundidade_corte"] == pytest.approx(5.0)
    assert isinstance(ped_vista_int["profundidade_corte"], float)

    espiao_none = ExecutorEspiao()
    corte.gerar_corte(f, gid, profundidade_corte=None, executor=espiao_none)
    assert len(espiao_none.pedidos_desenho) == 1
    ped_vista_none = espiao_none.pedidos_desenho[0]["vista"]
    assert ped_vista_none.get("profundidade_corte") is None

    sel_direta = selecao.selecionar(f, gid, profundidade_corte=3.0, executor=espiao_float)
    assert sel_direta.faixa is not None
    assert sel_direta.faixa[0][1] == pytest.approx(0.0, abs=0.1)
    assert sel_direta.faixa[1][1] == pytest.approx(3.0, abs=0.1)


def test_profundidade_corte_poda_elementos_alem_do_far_clip():
    """Caso 2: profundidade_corte=3.0 poda Parede 3 (Y=10) antes de op: caixas e a exclui do SVG."""
    f, gid, p1, p2, p3 = _modelo_sintetico_corte("IFC4", prof_original=20.0)
    bloco = f.by_guid(gid).Representation.Representations[0].Items[0].TreeRootExpression
    z_len_antes = float(bloco.ZLength)

    espiao = ExecutorEspiao()
    c = corte.gerar_corte(f, gid, profundidade_corte=3.0, executor=espiao)
    assert p1.id() in c.selecao.ids
    assert p2.id() in c.selecao.ids
    assert p3.id() not in c.selecao.ids
    assert p1.id() in espiao.ids_pedidos_caixas
    assert p2.id() in espiao.ids_pedidos_caixas
    assert p3.id() not in espiao.ids_pedidos_caixas

    assert p1.GlobalId in c.svg
    assert _tem_projecao_em_x(c.svg, 8.0, 11.0)
    assert p3.GlobalId not in c.svg
    assert not _tem_projecao_em_x(c.svg, 11.0, 14.0)

    assert c.selecao.faixa is not None
    ymin, ymax = c.selecao.faixa[0][1], c.selecao.faixa[1][1]
    assert ymin == pytest.approx(0.0, abs=0.1)
    assert ymax == pytest.approx(3.0, abs=0.1)
    assert ymax - ymin == pytest.approx(3.0, abs=0.1)
    assert float(bloco.ZLength) == pytest.approx(z_len_antes)


def test_profundidade_corte_none_preserva_profundidade_original():
    """Caso 3: profundidade_corte=None mantém profundidade original de 20 m e inclui Parede 3."""
    f, gid, p1, p2, p3 = _modelo_sintetico_corte("IFC4", prof_original=20.0)
    c_clip = corte.gerar_corte(f, gid, profundidade_corte=3.0, executor=local.executar)
    assert p3.id() not in c_clip.selecao.ids

    espiao = ExecutorEspiao()
    c = corte.gerar_corte(f, gid, profundidade_corte=None, executor=espiao)
    assert p1.id() in c.selecao.ids
    assert p2.id() in c.selecao.ids
    assert p3.id() in c.selecao.ids
    assert p3.id() in espiao.ids_pedidos_caixas
    assert p1.GlobalId in c.svg
    assert _tem_projecao_em_x(c.svg, 8.0, 11.0)
    assert _tem_projecao_em_x(c.svg, 11.0, 14.0)

    assert c.selecao.faixa is not None
    ymin, ymax = c.selecao.faixa[0][1], c.selecao.faixa[1][1]
    assert ymin == pytest.approx(0.0, abs=0.1)
    assert ymax == pytest.approx(20.0, abs=0.1)
    assert ymax - ymin == pytest.approx(20.0, abs=0.1)


@pytest.mark.parametrize(
    "invalido",
    [-1.0, 0, 0.0, -0.5, "invalido", float("nan"), float("inf"), -float("inf"), True, False],
)
def test_profundidade_corte_invalida_levanta_excecao(invalido):
    """Caso 4: Valores não positivos ou inválidos levantam ValueError imediatamente sem chamar executor."""
    f, gid, _p1, _p2, _p3 = _modelo_sintetico_corte("IFC4")
    espiao_corte = ExecutorEspiao()
    with pytest.raises(ValueError):
        corte.gerar_corte(f, gid, profundidade_corte=invalido, executor=espiao_corte)
    assert len(espiao_corte.chamadas) == 0

    espiao_sel = ExecutorEspiao()
    with pytest.raises(ValueError):
        selecao.selecionar(f, gid, profundidade_corte=invalido, executor=espiao_sel)
    assert len(espiao_sel.chamadas) == 0


def test_profundidade_corte_unidade_milimetros():
    """Caso 5: Modelo em milímetros (k=1000, scale=0.001) converte profundidade_corte em metros."""
    f, gid, p1, p2, p3 = _modelo_sintetico_corte("IFC4", k=1000.0, prof_original=20.0)
    assert ifcopenshell.util.unit.calculate_unit_scale(f) == pytest.approx(0.001)
    bloco = f.by_guid(gid).Representation.Representations[0].Items[0].TreeRootExpression
    z_len_orig = float(bloco.ZLength)

    espiao = ExecutorEspiao()
    c = corte.gerar_corte(f, gid, profundidade_corte=2.5, executor=espiao)
    assert c.unidade_escala == pytest.approx(0.001)
    assert p1.id() in c.selecao.ids
    assert p2.id() in c.selecao.ids
    assert p3.id() not in c.selecao.ids
    assert p1.id() in espiao.ids_pedidos_caixas
    assert p2.id() in espiao.ids_pedidos_caixas
    assert p3.id() not in espiao.ids_pedidos_caixas

    assert p1.GlobalId in c.svg
    assert _tem_projecao_em_x(c.svg, 8.0, 11.0)
    assert p3.GlobalId not in c.svg
    assert not _tem_projecao_em_x(c.svg, 11.0, 14.0)

    assert c.selecao.faixa is not None
    ymin, ymax = c.selecao.faixa[0][1], c.selecao.faixa[1][1]
    assert ymin == pytest.approx(0.0, abs=0.05)
    assert ymax == pytest.approx(2.5, abs=0.05)
    assert ymax - ymin == pytest.approx(2.5, abs=0.05)
    assert float(bloco.ZLength) == pytest.approx(z_len_orig)

    c_padrao = corte.gerar_corte(f, gid, profundidade_corte=None, executor=local.executar)
    assert p3.id() in c_padrao.selecao.ids
    assert _tem_projecao_em_x(c_padrao.svg, 11.0, 14.0)
    ymin_p, ymax_p = c_padrao.selecao.faixa[0][1], c_padrao.selecao.faixa[1][1]
    assert ymin_p == pytest.approx(0.0, abs=0.05)
    assert ymax_p == pytest.approx(20.0, abs=0.05)
    assert ymax_p - ymin_p == pytest.approx(20.0, abs=0.05)


def test_profundidade_corte_preserva_placement_camera_e_offset_lateral():
    """Caso 6: Bloco com offset lateral (ox != 0, oy != 0) e IfcCartesianPoint compartilhado
    com a câmera não corrompe o ObjectPlacement da câmera e preserva o alinhamento lateral no corte."""
    f, gid, p1, p2, p3 = _modelo_sintetico_corte("IFC4", prof_original=20.0)
    ann = f.by_guid(gid)
    cam_loc = ann.ObjectPlacement.RelativePlacement
    bloco = ann.Representation.Representations[0].Items[0].TreeRootExpression
    ox, oy = 1.5, 0.5
    pt_comp = f.create_entity("IfcCartesianPoint", Coordinates=(ox, oy, 0.0))
    cam_loc.Location = pt_comp
    bloco.Position.Location = pt_comp
    assert ann.ObjectPlacement.RelativePlacement.Location.id() == bloco.Position.Location.id()

    c = corte.gerar_corte(f, gid, profundidade_corte=3.0, executor=local.executar)
    assert c.svg
    assert ann.ObjectPlacement.RelativePlacement.Location.Coordinates == (ox, oy, 0.0)
    assert p2.id() in c.selecao.ids
    assert p3.id() not in c.selecao.ids
    assert _tem_projecao_em_x(c.svg, 6.0, 8.5)
    assert not _tem_projecao_em_x(c.svg, 10.0, 15.0)

    f_proc = ifcopenshell.file.from_string(f.to_string())
    ann_proc = f_proc.by_guid(gid)
    bloco_proc = ann_proc.Representation.Representations[0].Items[0].TreeRootExpression
    assert ann_proc.ObjectPlacement.RelativePlacement.Location.id() == bloco_proc.Position.Location.id()
    res = desenho_geo._corte(
        f_proc,
        {"vista": {"guid": gid, "escala": 100.0, "profundidade_corte": 3.0}, "elementos": [[p1.id(), p1.GlobalId]]},
        None,
        0.0,
    )
    assert res["ok"]
    assert ann_proc.ObjectPlacement.RelativePlacement.Location.Coordinates == (ox, oy, 0.0)
    assert bloco_proc.Position.Location.id() != ann_proc.ObjectPlacement.RelativePlacement.Location.id()
    assert bloco_proc.Position.Location.Coordinates == (ox, oy, -3.0 / 100.0)

    # Caso com Axis2Placement3D inteiro compartilhado entre câmera e bloco
    f_axis = ifcopenshell.file.from_string(f.to_string())
    ann_axis = f_axis.by_guid(gid)
    bloco_axis = ann_axis.Representation.Representations[0].Items[0].TreeRootExpression
    bloco_axis.Position = ann_axis.ObjectPlacement.RelativePlacement
    assert ann_axis.ObjectPlacement.RelativePlacement.id() == bloco_axis.Position.id()
    res_axis = desenho_geo._corte(
        f_axis,
        {"vista": {"guid": gid, "escala": 100.0, "profundidade_corte": 3.0}, "elementos": [[p1.id(), p1.GlobalId]]},
        None,
        0.0,
    )
    assert res_axis["ok"]
    assert ann_axis.ObjectPlacement.RelativePlacement.Location.Coordinates == (ox, oy, 0.0)
    assert bloco_axis.Position.id() != ann_axis.ObjectPlacement.RelativePlacement.id()
    assert bloco_axis.Position.Location.Coordinates == (ox, oy, -3.0 / 100.0)
