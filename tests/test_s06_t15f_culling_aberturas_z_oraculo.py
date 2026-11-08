# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15f: poda de aberturas e pré-filtro vertical na seleção de corte.
Cartão: docs/state/cards/F0-S06/F0-S06-T15f-culling-aberturas-z.md.

CONTRATO:
1. Em `app/openbim_app/desenho/selecao.py` (rota CORTE):
   - Elementos `IfcOpeningElement` NÃO devem ser enviados na requisição `op: caixas`
     (desenho nunca os renderiza).
   - Pré-filtro vertical seguro por `ObjectPlacement`:
     Para cada elemento candidato a `op: caixas` (em `faltantes`):
     Se o elemento possui `ObjectPlacement` e sua classe NÃO pertence a
     `("IfcColumn", "IfcStair", "IfcStairFlight")`:
     Obter a coordenada Z mundial da colocação: `pz = float(M[2, 3]) * scale`.
     Se `pz < zmin - 4.0` ou `pz > zmax + 4.0` (onde `zmin, zmax` são os limites do corte):
     O elemento é podado antes de `op: caixas` e NÃO cruza a vista.
     Classes verticais contínuas (`IfcColumn`, `IfcStair`, `IfcStairFlight`) ou elementos
     sem colocação permanecem elegíveis para `op: caixas`.
   - Classes com colocação em marco zero do projeto (`IfcSlab`, `IfcRoof`, `IfcBuildingElementProxy`)
     NUNCA sofrem filtro em XY.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401 (fixture autouse e guarda)

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app import vistas_ifc
from openbim_app.desenho import selecao


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


def _criar_corte_z(
    f: Any,
    nome: str,
    zmin: float,
    zmax: float,
    xmin: float = -0.5,
    dx: float = 7.0,
    y0: float = 0.0,
    dy: float = 6.0,
    k: float = 1.0,
) -> str:
    """Cria vista CORTE voltada para +Y na cota Z [zmin, zmax] em metros."""
    altura = zmax - zmin
    tamanho = (dx * k, altura * k, dy * k)
    origem = (xmin * k, y0 * k, zmin * k)
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=origem, tamanho=tamanho)
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -dy * k))
    return gid


def _elemento_deslocado_xy(f: Any, cls: str, nome: str, z_plac: float, x_sol: float, y_sol: float, dx: float, dy: float, dz: float) -> Any:
    """Cria elemento com colocação no marco zero XY (0, 0, z_plac) mas sólido deslocado."""
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


def test_aberturas_nao_enviadas_para_caixas_em_corte():
    """Elementos IfcOpeningElement NUNCA devem ser enviados para cálculo de caixas envolventes em CORTE."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    parede = X.caixa(f, "IfcWall", "Parede", 0.0, -0.1, 0.0, 5.0, 0.2, 3.0)
    abertura = X.caixa(f, "IfcOpeningElement", "Abertura", 1.0, -0.1, 0.0, 1.0, 0.2, 2.0)
    porta = X.caixa(f, "IfcDoor", "Porta", 1.0, -0.1, 0.0, 1.0, 0.2, 2.0)
    X.conter(f, pav, parede, abertura, porta)

    f.create_entity(
        "IfcRelVoidsElement",
        GlobalId=X.ifcopenshell.guid.new(),
        RelatingBuildingElement=parede,
        RelatedOpeningElement=abertura,
    )
    f.create_entity(
        "IfcRelFillsElement",
        GlobalId=X.ifcopenshell.guid.new(),
        RelatingOpeningElement=abertura,
        RelatedBuildingElement=porta,
    )

    gid = _criar_corte_z(f, "Corte_Abertura", zmin=-0.5, zmax=3.5, y0=0.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    # Abertura não deve ser enviada para op: caixas nem constar na seleção
    assert abertura.id() not in espiao.ids_pedidos_caixas, (
        f"IfcOpeningElement (id {abertura.id()}) não deve ser enviado para op: caixas"
    )
    assert abertura.id() not in sel.ids, "IfcOpeningElement não deve constar em sel.ids"

    # Parede e porta devem ser enviadas e selecionadas
    assert parede.id() in espiao.ids_pedidos_caixas
    assert porta.id() in espiao.ids_pedidos_caixas
    assert parede.id() in sel.ids
    assert porta.id() in sel.ids


def test_pre_filtro_vertical_elimina_elementos_de_outros_andares():
    """Elementos com cota Z de colocação fora de [zmin - 4.0, zmax + 4.0] são podados antes de op: caixas.
    Com zmin=4.5 m no 1º Pavimento, a tolerância segura de 4.0 m delimita colocação em [0.5, 11.0] m:
    Térreo (pz=0.0 m < 0.5 m) e Cobertura (pz=12.0 m > 11.0 m) são podados; 1º Pav (pz=4.0 m) é mantido."""
    exigir()
    f, pavs = X.estrutura("IFC4", n_pav=2, base=0.0)
    pav_terreo = pavs[0]
    pav_superior = pavs[1]
    pav_superior.Elevation = 4.0
    pav_superior.ObjectPlacement.RelativePlacement.Location.Coordinates = (0.0, 0.0, 4.0)

    # Subsolo distante inferior (Z = -3.0 m)
    par_subsolo = X.caixa(f, "IfcWall", "ParedeSubsolo", 0.0, 0.5, -3.0, 3.0, 0.2, 2.8)
    # Elementos no Térreo (Z = 0.0 m)
    par_terreo = X.caixa(f, "IfcWall", "ParedeTerreo", 0.0, 0.5, 0.0, 3.0, 0.2, 2.8)
    mov_terreo = X.caixa(f, "IfcFurniture", "MovelTerreo", 1.0, 0.5, 0.0, 1.0, 0.5, 0.8)
    X.conter(f, pav_terreo, par_subsolo, par_terreo, mov_terreo)

    # Elementos no 1º Pavimento (Z = 4.0 m)
    par_1pav = X.caixa(f, "IfcWall", "Parede1Pav", 0.0, 0.5, 4.0, 3.0, 0.2, 2.8)
    mov_1pav = X.caixa(f, "IfcFurniture", "Movel1Pav", 1.0, 0.5, 4.0, 1.0, 0.5, 1.5)
    # Elemento distante superior (Cobertura em Z = 12.0 m)
    par_cobertura = X.caixa(f, "IfcWall", "ParedeCobertura", 0.0, 0.5, 12.0, 3.0, 0.2, 2.5)
    X.conter(f, pav_superior, par_1pav, mov_1pav, par_cobertura)

    # Corte no 1º Pavimento: Z de 4.5 a 7.0 m (faixa segura de colocação: [0.5, 11.0] m)
    gid = _criar_corte_z(f, "Corte_1Pav", zmin=4.5, zmax=7.0, y0=0.0, dy=3.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    # Subsolo (pz = -3.0), Térreo (pz = 0.0 < 0.5) e Cobertura (pz = 12.0 > 11.0) devem ser podados antes de caixas
    assert par_subsolo.id() not in espiao.ids_pedidos_caixas, "Subsolo não deve ir para op: caixas"
    assert par_terreo.id() not in espiao.ids_pedidos_caixas, "Parede do térreo não deve ir para op: caixas"
    assert mov_terreo.id() not in espiao.ids_pedidos_caixas, "Móvel do térreo não deve ir para op: caixas"
    assert par_cobertura.id() not in espiao.ids_pedidos_caixas, "Cobertura não deve ir para op: caixas"

    assert par_subsolo.id() not in sel.ids
    assert par_terreo.id() not in sel.ids
    assert mov_terreo.id() not in sel.ids
    assert par_cobertura.id() not in sel.ids

    # 1º Pavimento (pz = 4.0 dentro de [0.5, 11.0]) deve ir para op: caixas e ser selecionado
    assert par_1pav.id() in espiao.ids_pedidos_caixas
    assert mov_1pav.id() in espiao.ids_pedidos_caixas
    assert par_1pav.id() in sel.ids
    assert mov_1pav.id() in sel.ids


def test_pilares_verticais_isentos_de_culling_vertical():
    """Classes verticais contínuas (IfcColumn, IfcStair, IfcStairFlight) com colocação fora de [zmin-4, zmax+4]
    NÃO sofrem culling vertical e são enviadas para op: caixas."""
    exigir()
    f, pavs = X.estrutura("IFC4", n_pav=2, base=0.0)
    pav_terreo = pavs[0]
    pav_superior = pavs[1]
    pav_superior.Elevation = 4.0
    pav_superior.ObjectPlacement.RelativePlacement.Location.Coordinates = (0.0, 0.0, 4.0)

    # Pilar contínuo: colocação no térreo (Z = 0.0 m), mas altura 6.0 m cruzando o corte [4.5, 7.0]
    pilar = X.caixa(f, "IfcColumn", "PilarContinuo", 0.5, 0.5, 0.0, 0.4, 0.4, 6.0)
    # Escada contínua: colocação no térreo (Z = 0.0 m), altura 5.5 m cruzando o corte
    escada = X.caixa(f, "IfcStair", "EscadaContinua", 1.5, 0.5, 0.0, 1.0, 2.0, 5.5)
    # Lance de escada contínuo: colocação no térreo (Z = 0.0 m), altura 5.5 m cruzando o corte
    lance = X.caixa(f, "IfcStairFlight", "LanceContinuo", 3.0, 0.5, 0.0, 1.0, 2.0, 5.5)
    # Parede comum no térreo: colocação em Z = 0.0 m, altura 2.8 m (não cruza e deve ser podada)
    parede_baixa = X.caixa(f, "IfcWall", "ParedeBaixa", 4.5, 0.5, 0.0, 2.0, 0.2, 2.8)
    X.conter(f, pav_terreo, pilar, escada, lance, parede_baixa)

    # Corte no 1º Pavimento: Z de 4.5 a 7.0 m (zmin - 4.0 = 0.5 > 0.0)
    gid = _criar_corte_z(f, "Corte_Pilares", zmin=4.5, zmax=7.0, y0=0.0, dy=3.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    # Parede comum é podada
    assert parede_baixa.id() not in espiao.ids_pedidos_caixas
    assert parede_baixa.id() not in sel.ids

    # Pilar e escadas são isentos do pré-filtro vertical e vão para op: caixas
    assert pilar.id() in espiao.ids_pedidos_caixas, "IfcColumn deve ser enviado para op: caixas"
    assert escada.id() in espiao.ids_pedidos_caixas, "IfcStair deve ser enviado para op: caixas"
    assert lance.id() in espiao.ids_pedidos_caixas, "IfcStairFlight deve ser enviado para op: caixas"

    # Cruzam geometricamente a vista, logo constam em sel.ids
    assert pilar.id() in sel.ids
    assert escada.id() in sel.ids
    assert lance.id() in sel.ids


def test_lajes_com_marco_zero_selecionadas_corretamente():
    """Lajes (IfcSlab) e coberturas (IfcRoof) com colocação em marco zero XY do projeto (0, 0)
    NUNCA sofrem filtro em XY no placement: permanecem elegíveis para op: caixas e são selecionadas
    quando a geometria sólida cruza a vista, mesmo que o corte esteja deslocado em XY."""
    exigir()
    f, pavs = X.estrutura("IFC4", n_pav=2, base=0.0)
    pav_superior = pavs[1]
    pav_superior.Elevation = 4.0
    pav_superior.ObjectPlacement.RelativePlacement.Location.Coordinates = (0.0, 0.0, 4.0)

    # Laje com ObjectPlacement no marco zero XY (0.0, 0.0, 4.0), mas sólido deslocado para (10.0, 10.0)
    laje = _elemento_deslocado_xy(f, "IfcSlab", "LajeMarcoZero", 4.0, 10.0, 10.0, 6.0, 6.0, 0.2)
    # Cobertura (IfcRoof) também com ObjectPlacement em marco zero XY (0.0, 0.0, 4.0)
    telhado = _elemento_deslocado_xy(f, "IfcRoof", "CoberturaMarcoZero", 4.0, 10.0, 10.0, 6.0, 6.0, 0.5)
    X.conter(f, pav_superior, laje, telhado)

    # Corte centrado no sólido em (10, 10) e Z [3.8, 6.0], longe da colocação XY (0, 0)
    gid = _criar_corte_z(f, "Corte_Lajes", zmin=3.8, zmax=6.0, xmin=9.0, dx=8.0, y0=9.0, dy=8.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    assert laje.id() in espiao.ids_pedidos_caixas, "IfcSlab em marco zero XY deve ser enviada para op: caixas"
    assert telhado.id() in espiao.ids_pedidos_caixas, "IfcRoof em marco zero XY deve ser enviado para op: caixas"

    assert laje.id() in sel.ids
    assert telhado.id() in sel.ids


def test_elementos_sem_placement_nao_sao_podados():
    """Elementos com geometria válida mas sem ObjectPlacement não causam exceção e vão para op: caixas."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    parede = X.caixa(f, "IfcWall", "ParedeNormal", 0.0, 0.5, 0.0, 3.0, 0.2, 2.8)
    elem_sem_placement = X.caixa(f, "IfcBuildingElementProxy", "ProxySemPlacement", 1.0, 0.5, 0.0, 1.0, 1.0, 1.0)
    elem_sem_placement.ObjectPlacement = None
    X.conter(f, pav, parede, elem_sem_placement)

    gid = _criar_corte_z(f, "Corte_SemPlacement", zmin=-0.5, zmax=3.5, y0=0.0, dy=4.0)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    assert elem_sem_placement.id() in espiao.ids_pedidos_caixas, (
        "Elemento sem ObjectPlacement deve permanecer elegível para op: caixas"
    )
    assert elem_sem_placement.id() in sel.ids, "Elemento sem placement deve ser selecionado ao cruzar a vista"
    assert parede.id() in sel.ids


def test_pre_filtro_vertical_respeita_unidade_milimetros():
    """Pré-filtro vertical converte a coordenada mundial com scale em modelos em milímetros."""
    exigir()
    # Modelo em milímetros (k = 1000.0)
    f, pavs = X.estrutura("IFC4", n_pav=2, base=0.0)
    X.em_milimetros(f)
    k = 1000.0

    pav_terreo = pavs[0]
    pav_superior = pavs[1]
    pav_superior.Elevation = 4.0 * k
    pav_superior.ObjectPlacement.RelativePlacement.Location.Coordinates = (0.0, 0.0, 4.0 * k)

    # Parede no Térreo: Z = 0 mm
    par_terreo = X.caixa(f, "IfcWall", "ParedeTerreoMM", 0.0, 500.0, 0.0, 3000.0, 200.0, 2800.0)
    # Parede no 1º Pavimento: Z = 4000 mm (4.0 m)
    par_1pav = X.caixa(f, "IfcWall", "Parede1PavMM", 0.0, 500.0, 4000.0, 3000.0, 200.0, 2800.0)
    X.conter(f, pav_terreo, par_terreo)
    X.conter(f, pav_superior, par_1pav)

    # Corte no 1º Pavimento: 4.5 a 7.0 m
    gid = _criar_corte_z(f, "Corte_MM", zmin=4.5, zmax=7.0, y0=0.0, dy=3.0, k=k)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    # Parede do térreo (pz = 0.0 m < 0.5 m) deve ser podada antes de op: caixas
    assert par_terreo.id() not in espiao.ids_pedidos_caixas
    assert par_terreo.id() not in sel.ids

    # Parede do 1º pav (pz = 4.0 m dentro de [0.5, 11.0] m) deve ir para caixas e ser selecionada
    assert par_1pav.id() in espiao.ids_pedidos_caixas
    assert par_1pav.id() in sel.ids
