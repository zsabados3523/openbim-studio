# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15g: pré-filtro XY seguro e móveis como caixa 2D no corte vertical.
Cartão: docs/state/cards/F0-S06/F0-S06-T15g-culling-xy-moveis-corte.md.

CONTRATO:
1. Em `app/openbim_app/desenho/selecao.py` (rota CORTE):
   - Classes locais: `CLASSES_LOCAIS_XY = ("IfcWall", "IfcBeam", "IfcDoor", "IfcWindow", "IfcCovering", "IfcFlowSegment", "IfcFlowFitting")`.
   - Se `e` pertence a `CLASSES_LOCAIS_XY` e tem `ObjectPlacement`:
     `M = ifcopenshell.util.placement.get_local_placement(e.ObjectPlacement)`
     `px = float(M[0, 3]) * scale`
     `py = float(M[1, 3]) * scale`
     Se `px < xmin - 5.0 or px > xmax + 5.0 or py < ymin - 5.0 or py > ymax + 5.0`:
     Pula antes de `op: caixas` (não vai para faltantes e não cruza a vista).
   - Classes com colocação em marco zero (`IfcSlab`, `IfcRoof`, `IfcBuildingElementProxy`)
     e classes verticais (`CLASSES_VERTICAIS_CONTINUAS`) NUNCA sofrem esse filtro XY.
   - Elementos sem `ObjectPlacement` continuam indo para `op: caixas`.
2. Em `app/openbim_app/desenho/corte.py`:
   - `gerar_corte(..., moveis_caixa2d: bool = True)` keyword-only com default `True`.
   - Dataclass `Corte`: campo `caixas: tuple[int, ...] = ()` (já existente).
   - Repassa `"moveis_caixa2d": bool(moveis_caixa2d)` no `pedido`.
3. Em `geometria/obim_geometria/desenho.py` na rota `_corte`:
   - Quando `pedido.get("moveis_caixa2d", True)` for True:
     Móveis (`IfcFurniture`) no corte não vão para `incl` do iterador 3D.
     Em vez disso, são gerados como retângulo 2D simplificado no SVG com
     `<g class="IfcFurniture" ifc:guid="..."><path .../></g>` e adicionados a
     `res["caixas"]` e `res["enviados"]`.
   - Quando `moveis_caixa2d=False`:
     Vão normalmente para o iterador 3D (comportamento original) e `res["caixas"] == []`.
"""
from __future__ import annotations

import copy
import dataclasses
import inspect
import re
import sys
from pathlib import Path
from typing import Any

import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401 (fixture autouse e guarda)

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app import vistas_ifc
from openbim_app.desenho import corte, estilo, selecao


class ExecutorEspiao:
    """Intermediário que armazena requisições do processo auxiliar para inspeção."""

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


def _criar_corte_xyz(
    f: Any,
    nome: str,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    k: float = 1.0,
) -> str:
    """Cria vista CORTE cobrindo o paralelepípedo [xmin, xmax] x [ymin, ymax] x [zmin, zmax]."""
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    tamanho = (dx * k, dz * k, dy * k)
    origem = (xmin * k, ymin * k, zmin * k)
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=origem, tamanho=tamanho)
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -dy * k))
    return gid


def _elemento_deslocado_xy(
    f: Any, cls: str, nome: str, z_plac: float, x_sol: float, y_sol: float, dx: float, dy: float, dz: float
) -> Any:
    """Cria elemento com colocação no marco zero XY (0, 0, z_plac) mas sólido em (x_sol, y_sol)."""
    eixo = f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, x_sol, y_sol, 0.0))
    pos2d = f.create_entity("IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(dx / 2, dy / 2)))
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=dx, YDim=dy, Position=pos2d)
    dir_z = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Position=eixo, Depth=dz, ExtrudedDirection=dir_z)
    ctx = f.by_type("IfcGeometricRepresentationContext")[0]
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=ctx, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    e = X.elemento(f, cls, nome)
    e.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0.0, 0.0, z_plac)))
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    return e


def _modelo_parede_movel(schema: str = "IFC4"):
    """Modelo com parede cortada e móvel (IfcFurniture) na vista de corte."""
    exigir()
    f, pavs = X.estrutura(schema)
    parede = X.caixa(f, "IfcWall", "Parede", 0.5, -0.1, 0.0, 4.0, 0.2, 2.8)
    movel = X.caixa(f, "IfcFurniture", "Movel", 1.0, -0.1, 0.0, 1.0, 0.6, 1.2)
    X.conter(f, pavs[0], parede, movel)
    gid = _criar_corte_xyz(f, f"Corte_Moveis_{schema}", xmin=-0.5, xmax=6.5, ymin=0.0, ymax=5.0, zmin=-0.5, zmax=3.5)
    return f, gid, parede, movel


def test_assinatura_gerar_corte_moveis_caixa2d():
    """Caso 1: Inspeciona corte.gerar_corte: parâmetro moveis_caixa2d keyword-only com default True e tipo bool.
    Valida selecao.CLASSES_LOCAIS_XY e o repasse booleano no dicionário pedido de desenho."""
    assert hasattr(selecao, "CLASSES_LOCAIS_XY"), "selecao.CLASSES_LOCAIS_XY deve existir"
    assert selecao.CLASSES_LOCAIS_XY == (
        "IfcWall",
        "IfcBeam",
        "IfcDoor",
        "IfcWindow",
        "IfcCovering",
        "IfcFlowSegment",
        "IfcFlowFitting",
    ), f"CLASSES_LOCAIS_XY incorreta: {getattr(selecao, 'CLASSES_LOCAIS_XY', None)}"

    sig = inspect.signature(corte.gerar_corte)
    assert "moveis_caixa2d" in sig.parameters, "corte.gerar_corte deve declarar moveis_caixa2d"
    param = sig.parameters["moveis_caixa2d"]
    assert param.default is True, f"moveis_caixa2d deve ter default True, obtido: {param.default!r}"
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, f"moveis_caixa2d deve ser keyword-only (*), obtido: {param.kind}"
    assert param.annotation in (bool, "bool"), f"moveis_caixa2d deve ter anotação bool, obtido: {param.annotation}"

    campos = {f.name: f for f in dataclasses.fields(corte.Corte)}
    assert "caixas" in campos, "Corte deve possuir o campo caixas"

    # Confere repasse estrito de booleano no pedido op: desenho enviado ao executor auxiliar
    f, gid, _parede, _movel = _modelo_parede_movel("IFC4")
    pedidos_desenho: list[dict[str, Any]] = []

    def espia_pedido(ped):
        if ped.get("op") == "desenho":
            pedidos_desenho.append(dict(ped))
        return local.executar(ped)

    corte.gerar_corte(f, gid, executor=espia_pedido)
    assert len(pedidos_desenho) == 1 and pedidos_desenho[0].get("moveis_caixa2d") is True
    assert type(pedidos_desenho[0]["moveis_caixa2d"]) is bool

    corte.gerar_corte(f, gid, moveis_caixa2d=False, executor=espia_pedido)
    assert len(pedidos_desenho) == 2 and pedidos_desenho[1].get("moveis_caixa2d") is False
    assert type(pedidos_desenho[1]["moveis_caixa2d"]) is bool

    corte.gerar_corte(f, gid, moveis_caixa2d=1, executor=espia_pedido)
    assert len(pedidos_desenho) == 3 and pedidos_desenho[2].get("moveis_caixa2d") is True
    assert type(pedidos_desenho[2]["moveis_caixa2d"]) is bool

    corte.gerar_corte(f, gid, moveis_caixa2d=0, executor=espia_pedido)
    assert len(pedidos_desenho) == 4 and pedidos_desenho[3].get("moveis_caixa2d") is False
    assert type(pedidos_desenho[3]["moveis_caixa2d"]) is bool


def test_pre_filtro_xy_corte_poda_paredes_e_vigas_distantes():
    """Caso 2: Modelo sintético com corte em X=0..10, Y=0..5, Z=0..3.
    Paredes e vigas distantes (além de xmax+5, xmin-5, ymax+5, ymin-5) são podadas antes de op: caixas.
    Paredes e vigas internas são enviadas para op: caixas e selecionadas."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    par1 = X.caixa(f, "IfcWall", "Parede1", 2.0, 1.0, 0.0, 2.0, 0.2, 2.5)
    par2_pos = X.caixa(f, "IfcWall", "Parede2Pos", 50.0, 1.0, 0.0, 2.0, 0.2, 2.5)
    par2_neg = X.caixa(f, "IfcWall", "Parede2Neg", -20.0, 1.0, 0.0, 2.0, 0.2, 2.5)

    viga1 = X.caixa(f, "IfcBeam", "Viga1", 2.0, 2.0, 2.0, 3.0, 0.3, 0.4)
    viga2_pos = X.caixa(f, "IfcBeam", "Viga2Pos", 2.0, 40.0, 2.0, 3.0, 0.3, 0.4)
    viga2_neg = X.caixa(f, "IfcBeam", "Viga2Neg", 2.0, -20.0, 2.0, 3.0, 0.3, 0.4)

    porta_longe = X.caixa(f, "IfcDoor", "PortaLonge", 60.0, 2.0, 0.0, 1.0, 0.2, 2.1)
    janela_longe = X.caixa(f, "IfcWindow", "JanelaLonge", 2.0, 60.0, 1.0, 1.0, 0.2, 1.2)

    podados = (par2_pos, par2_neg, viga2_pos, viga2_neg, porta_longe, janela_longe)
    mantidos = (par1, viga1)
    X.conter(f, pav, *mantidos, *podados)

    gid = _criar_corte_xyz(f, "Corte_Poda_XY", xmin=0.0, xmax=10.0, ymin=0.0, ymax=5.0, zmin=0.0, zmax=3.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    for el in podados:
        assert el.id() not in espiao.ids_pedidos_caixas, f"{el.Name} não deve ir a op: caixas"
        assert el.id() not in sel.ids, f"{el.Name} não deve constar em sel.ids"

    for el in mantidos:
        assert el.id() in espiao.ids_pedidos_caixas, f"{el.Name} deve ir a op: caixas"
        assert el.id() in sel.ids, f"{el.Name} deve constar em sel.ids"


def test_lajes_e_proxies_marco_zero_nao_sao_podados_por_xy():
    """Caso 3: Classes em marco zero (IfcSlab, IfcRoof, IfcBuildingElementProxy) e classes verticais contínuas
    (IfcColumn) com placement em (0, 0, 0) NUNCA sofrem poda XY: vão a op: caixas e são selecionadas.
    Elementos sem ObjectPlacement também não sofrem poda XY."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    laje = _elemento_deslocado_xy(f, "IfcSlab", "LajeMarcoZero", 0.0, 22.0, 21.0, 5.0, 3.0, 0.2)
    telhado = _elemento_deslocado_xy(f, "IfcRoof", "TelhadoMarcoZero", 0.0, 22.0, 21.0, 5.0, 3.0, 0.3)
    proxy = _elemento_deslocado_xy(f, "IfcBuildingElementProxy", "ProxyMarcoZero", 0.0, 22.0, 21.0, 1.0, 1.0, 1.0)
    coluna = _elemento_deslocado_xy(f, "IfcColumn", "ColunaMarcoZero", 0.0, 22.0, 21.0, 0.4, 0.4, 3.0)
    par_marco_zero = _elemento_deslocado_xy(f, "IfcWall", "ParedeMarcoZero", 0.0, 22.0, 21.0, 2.0, 0.2, 2.5)

    elem_sem_plac = _elemento_deslocado_xy(f, "IfcBuildingElementProxy", "SemPlacement", 0.0, 22.0, 21.0, 1.0, 1.0, 1.0)
    elem_sem_plac.ObjectPlacement = None

    isentos = (laje, telhado, proxy, coluna, elem_sem_plac)
    X.conter(f, pav, *isentos, par_marco_zero)

    gid = _criar_corte_xyz(f, "Corte_MarcoZero", xmin=20.0, xmax=30.0, ymin=20.0, ymax=25.0, zmin=0.0, zmax=3.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    for el in isentos:
        assert el.id() in espiao.ids_pedidos_caixas, f"{el.Name} deve ser enviado para op: caixas"
        assert el.id() in sel.ids, f"{el.Name} deve constar em sel.ids"

    assert par_marco_zero.id() not in espiao.ids_pedidos_caixas, "Parede local em marco zero distante deve ser podada"
    assert par_marco_zero.id() not in sel.ids


def test_moveis_caixa2d_no_corte_evitam_iterador_3d(monkeypatch):
    """Caso 4: Modelo com parede e móvel (IfcFurniture).
    Chama gerar_corte com moveis_caixa2d=True:
    - Móvel consta em c.caixas
    - Presente no SVG com <g class="IfcFurniture" ifc:guid="..."> contendo <path> com retângulo 2D válido
    - Iterador 3D NÃO recebe o móvel, mas recebe a parede."""
    import ifcopenshell.geom
    f, gid, parede, movel = _modelo_parede_movel("IFC4")

    includes_capturados: list[list[int]] = []
    real_iterator = ifcopenshell.geom.iterator

    def espia_iterator(*args, **kwargs):
        inc = kwargs.get("include") or (args[3] if len(args) > 3 else None)
        includes_capturados.append([e.id() for e in inc] if inc else [])
        return real_iterator(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "iterator", espia_iterator)

    c = corte.gerar_corte(f, gid, moveis_caixa2d=True, executor=local.executar)

    assert isinstance(c.caixas, tuple), f"c.caixas deve ser tupla, obtido {type(c.caixas)}"
    assert movel.id() in c.caixas, f"Móvel (id {movel.id()}) deve constar em c.caixas, obtido: {c.caixas}"
    assert parede.id() not in c.caixas, "Parede estrutural não deve estar em c.caixas"

    # Móvel não pode ter ido para o iterador 3D pesado
    assert len(includes_capturados) == 1, "Iterador 3D deve ser chamado exatamente uma vez"
    assert movel.id() not in includes_capturados[0], (
        f"Móvel (id {movel.id()}) NÃO deve ser enviado ao iterador 3D quando moveis_caixa2d=True"
    )
    assert parede.id() in includes_capturados[0], "Parede deve ser enviada ao iterador 3D"

    # Móvel emitido no SVG dentro de grupo IfcFurniture com polígono/retângulo fechado
    g_m = re.search(
        r'<g\b([^>]*\bifc:guid=[\"\']' + re.escape(movel.GlobalId) + r'[\"\'][^>]*)>(.*?)</g>',
        c.svg,
        re.DOTALL,
    )
    assert g_m is not None, f"Grupo para guid={movel.GlobalId!r} não encontrado no SVG gerado"
    abertura, conteudo = g_m.group(1), g_m.group(2)
    cls_m = re.search(r'\bclass=[\"\']([^\"]+)[\"\']', abertura)
    assert cls_m is not None and "IfcFurniture" in cls_m.group(1).split(), (
        f"Grupo do móvel deve conter class='IfcFurniture', obtido: {abertura}"
    )
    paths = re.findall(r"<path\b[^>]*>", conteudo)
    assert len(paths) >= 1, f"Grupo do móvel deve conter ao menos um <path>, obtido: {conteudo}"
    d_m = re.search(r'\bd=[\"\']([^\"\']+)[\"\']', paths[0])
    assert d_m is not None, f"Atributo d ausente no caminho do móvel: {paths[0]}"
    nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", d_m.group(1))]
    assert len(nums) >= 8, f"Caminho do móvel deve conter ao menos 4 vértices 2D, obtido: {nums}"
    assert c.n_paths == len(re.findall(r"<path\b", c.svg)), "n_paths deve refletir todos os caminhos do SVG"

    # Default moveis_caixa2d=True produz o mesmo comportamento sem o móvel no iterador 3D
    c_padrao = corte.gerar_corte(f, gid, executor=local.executar)
    assert movel.id() in c_padrao.caixas
    assert len(includes_capturados) == 2
    assert movel.id() not in includes_capturados[1]


def test_desativar_moveis_caixa2d_no_corte(monkeypatch):
    """Caso 5: Chama gerar_corte com moveis_caixa2d=False:
    - c.caixas == ()
    - Móvel foi gerado via iterador 3D."""
    import ifcopenshell.geom
    f, gid, parede, movel = _modelo_parede_movel("IFC4")

    includes_capturados: list[list[int]] = []
    real_iterator = ifcopenshell.geom.iterator

    def espia_iterator(*args, **kwargs):
        inc = kwargs.get("include") or (args[3] if len(args) > 3 else None)
        includes_capturados.append([e.id() for e in inc] if inc else [])
        return real_iterator(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "iterator", espia_iterator)

    c = corte.gerar_corte(f, gid, moveis_caixa2d=False, executor=local.executar)

    assert isinstance(c.caixas, tuple)
    assert c.caixas == (), f"c.caixas deve ser tupla vazia (), obtido: {c.caixas}"
    assert len(includes_capturados) == 1
    assert movel.id() in includes_capturados[0], (
        "Móvel deve ir para o iterador 3D normal quando moveis_caixa2d=False"
    )
    assert parede.id() in includes_capturados[0]
    assert movel.GlobalId in c.svg
    assert parede.GlobalId in c.svg


def test_compatibilidade_estilo_corte_caixa2d():
    """Caso 6: SVG gerado com móveis caixa 2D no corte é processado com sucesso por estilo.aplicar_estilo."""
    f, gid, parede, movel = _modelo_parede_movel("IFC4")
    c = corte.gerar_corte(f, gid, moveis_caixa2d=True, executor=local.executar)

    svg_50 = estilo.aplicar_estilo(c.svg, "1:50")
    assert isinstance(svg_50, str) and "<svg" in svg_50 and "</svg>" in svg_50
    assert B.svg_valido(svg_50), "SVG estilizado em 1:50 deve ser XML válido"
    assert 'viewBox="' in svg_50
    assert 'width="' in svg_50 and 'height="' in svg_50
    assert "<style" in svg_50
    assert movel.GlobalId in svg_50
    assert parede.GlobalId in svg_50

    svg_100 = estilo.aplicar_estilo(c.svg, "1:100")
    assert isinstance(svg_100, str) and B.svg_valido(svg_100), "SVG estilizado em 1:100 deve ser XML válido"
    assert movel.GlobalId in svg_100


def test_pre_filtro_xy_corte_respeita_unidade_milimetros():
    """Pré-filtro XY seguro em CORTE converte a coordenada mundial com scale em modelos em milímetros."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    X.em_milimetros(f)
    k = 1000.0
    pav = pavs[0]

    par1 = X.caixa(f, "IfcWall", "Par1MM", 2000.0, 1000.0, 0.0, 2000.0, 200.0, 2500.0)
    par2_pos = X.caixa(f, "IfcWall", "Par2PosMM", 50000.0, 1000.0, 0.0, 2000.0, 200.0, 2500.0)
    par2_neg = X.caixa(f, "IfcWall", "Par2NegMM", -20000.0, 1000.0, 0.0, 2000.0, 200.0, 2500.0)
    X.conter(f, pav, par1, par2_pos, par2_neg)

    gid = _criar_corte_xyz(f, "Corte_MM", xmin=0.0, xmax=10.0, ymin=0.0, ymax=5.0, zmin=0.0, zmax=3.0, k=k)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    assert par2_pos.id() not in espiao.ids_pedidos_caixas, "Parede a +50 m deve ser podada em mm"
    assert par2_neg.id() not in espiao.ids_pedidos_caixas, "Parede a -20 m deve ser podada em mm"
    assert par2_pos.id() not in sel.ids
    assert par2_neg.id() not in sel.ids
    assert par1.id() in espiao.ids_pedidos_caixas
    assert par1.id() in sel.ids
