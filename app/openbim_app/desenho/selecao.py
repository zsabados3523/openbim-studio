# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seleção de elementos IFC para desenho de vistas 2D (ADR-006 §3 item 0)."""
from __future__ import annotations

import dataclasses
import os
from typing import Any, Iterable

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
from openbim_app import vistas_ifc


class SelecaoInvalida(ValueError):
    """Parâmetros de vista, pavimento ou categoria inválidos para seleção."""


@dataclasses.dataclass(frozen=True)
class Selecao:
    ids: tuple[int, ...]
    tipo: str
    pavimento: int | None
    faixa: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    ocultos_por_classe: dict[str, int]
    sem_geometria: int
    falhas_geometria: tuple[int, ...] = ()


def _validar_categorias(ifc: ifcopenshell.file, categorias: tuple[str, ...]) -> None:
    schema = ifcopenshell.schema_by_name(ifc.schema)
    for cat in categorias:
        try:
            decl = schema.declaration_by_name(cat)
        except RuntimeError:
            raise SelecaoInvalida(f"Categoria desconhecida no esquema {ifc.schema}: {cat}")
        if decl.as_entity() is None:
            raise SelecaoInvalida(f"Classe não é entidade: {cat}")


def _resolver_pavimento(
    ifc: ifcopenshell.file, anotacao: Any, pavimento: str | None
) -> Any | None:
    if pavimento is not None:
        try:
            cand = ifc.by_guid(pavimento)
        except RuntimeError:
            raise SelecaoInvalida(f"Pavimento inexistente: {pavimento}")
        if cand is None or not cand.is_a("IfcBuildingStorey"):
            raise SelecaoInvalida(f"Elemento não é IfcBuildingStorey: {pavimento}")
        return cand

    for rel in getattr(anotacao, "ContainedInStructure", ()) or ():
        struct = getattr(rel, "RelatingStructure", None)
        if struct is not None and struct.is_a("IfcBuildingStorey"):
            return struct
    return None


def _candidatos_planta(pav: Any) -> set[Any]:
    candidatos: set[Any] = set()

    espacos: list[Any] = []
    visitados_espacos: set[int] = {pav.id()}
    fila_espacial = [pav]
    while fila_espacial:
        pai = fila_espacial.pop()
        for rel in getattr(pai, "IsDecomposedBy", ()) or ():
            for obj in getattr(rel, "RelatedObjects", ()) or ():
                if obj.is_a("IfcSpace") and obj.id() not in visitados_espacos:
                    visitados_espacos.add(obj.id())
                    espacos.append(obj)
                    fila_espacial.append(obj)

    for estrutura in [pav, *espacos]:
        for rel in getattr(estrutura, "ContainsElements", ()) or ():
            for e in getattr(rel, "RelatedElements", ()) or ():
                if e.is_a("IfcElement") and not e.is_a("IfcSpace"):
                    candidatos.add(e)

    fila = list(candidatos)
    while fila:
        elem = fila.pop()
        for rel in getattr(elem, "IsDecomposedBy", ()) or ():
            for filho in getattr(rel, "RelatedObjects", ()) or ():
                if filho.is_a("IfcElement") and not filho.is_a("IfcSpace") and filho not in candidatos:
                    candidatos.add(filho)
                    fila.append(filho)
        for rel in getattr(elem, "HasOpenings", ()) or ():
            op = getattr(rel, "RelatedOpeningElement", None)
            if op is not None and op.is_a("IfcElement") and not op.is_a("IfcSpace"):
                if op not in candidatos:
                    candidatos.add(op)
                    fila.append(op)
                for frel in getattr(op, "HasFillings", ()) or ():
                    fill = getattr(frel, "RelatedBuildingElement", None)
                    if (
                        fill is not None
                        and fill.is_a("IfcElement")
                        and not fill.is_a("IfcSpace")
                        and fill not in candidatos
                    ):
                        candidatos.add(fill)
                        fila.append(fill)

    return candidatos


def selecionar(
    ifc: ifcopenshell.file,
    gid_vista: str,
    *,
    categorias_ocultas: Iterable[str] = (),
    pavimento: str | None = None,
) -> Selecao:
    cats = tuple(categorias_ocultas)
    _validar_categorias(ifc, cats)

    info = vistas_ifc.ler_vista(ifc, gid_vista)
    tipo = info.get("tipo")
    if tipo not in ("PLANTA", "CORTE"):
        raise SelecaoInvalida(f"Tipo de vista inválido ou ausente: {tipo}")

    anotacao = ifc.by_guid(gid_vista)
    pav_ent = _resolver_pavimento(ifc, anotacao, pavimento)

    if tipo == "PLANTA":
        if pav_ent is None:
            raise SelecaoInvalida("Vista PLANTA requer um IfcBuildingStorey válido")
        candidatos = _candidatos_planta(pav_ent)
        sem_geometria = 0
        ocultos: dict[str, int] = {}
        ids: list[int] = []

        for e in candidatos:
            if not getattr(e, "Representation", None):
                sem_geometria += 1
                continue
            if any(e.is_a(cat) for cat in cats):
                cls = e.is_a()
                ocultos[cls] = ocultos.get(cls, 0) + 1
            else:
                ids.append(e.id())

        return Selecao(
            ids=tuple(sorted(set(ids))),
            tipo="PLANTA",
            pavimento=pav_ent.id(),
            faixa=None,
            ocultos_por_classe=ocultos,
            sem_geometria=sem_geometria,
            falhas_geometria=(),
        )

    # CORTE
    origem = info.get("origem")
    tamanho = info.get("tamanho")
    if origem is None or tamanho is None:
        raise SelecaoInvalida("Vista CORTE sem origem ou tamanho")

    bloco = None
    if anotacao.Representation and anotacao.Representation.Representations:
        for rep in anotacao.Representation.Representations:
            for itm in getattr(rep, "Items", ()) or ():
                if itm.is_a("IfcCsgSolid"):
                    cand_bloco = getattr(itm, "TreeRootExpression", None)
                    if cand_bloco is not None and cand_bloco.is_a("IfcBlock"):
                        bloco = cand_bloco
                        break
                elif itm.is_a("IfcBlock"):
                    bloco = itm
                    break
            if bloco is not None:
                break

    if bloco is None or not bloco.is_a("IfcBlock") or anotacao.ObjectPlacement is None:
        raise SelecaoInvalida("Vista CORTE sem IfcBlock ou ObjectPlacement")

    M_placement = ifcopenshell.util.placement.get_local_placement(anotacao.ObjectPlacement)
    pos = getattr(bloco, "Position", None)
    M_block = (
        ifcopenshell.util.placement.get_axis2placement(pos)
        if pos is not None
        else np.eye(4)
    )
    M_total = M_placement @ M_block
    scale = float(ifcopenshell.util.unit.calculate_unit_scale(ifc))
    dx = float(bloco.XLength)
    dy = float(bloco.YLength)
    dz = float(bloco.ZLength)

    corners = []
    for x in (0.0, dx):
        for y in (0.0, dy):
            for z in (0.0, dz):
                p = M_total @ np.array([x, y, z, 1.0])
                corners.append(p[:3] * scale)

    xmin = float(min(p[0] for p in corners))
    xmax = float(max(p[0] for p in corners))
    ymin = float(min(p[1] for p in corners))
    ymax = float(max(p[1] for p in corners))
    zmin = float(min(p[2] for p in corners))
    zmax = float(max(p[2] for p in corners))
    faixa = ((xmin, ymin, zmin), (xmax, ymax, zmax))

    sem_geometria = 0
    ocultos = {}
    visiveis_com_rep: list[Any] = []

    for elem in ifc.by_type("IfcElement"):
        if not getattr(elem, "Representation", None):
            sem_geometria += 1
            continue
        if any(elem.is_a(cat) for cat in cats):
            cls = elem.is_a()
            ocultos[cls] = ocultos.get(cls, 0) + 1
        else:
            visiveis_com_rep.append(elem)

    ids = []
    processados: set[int] = set()

    if visiveis_com_rep:
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        num_threads = max(1, os.cpu_count() or 1)
        it = ifcopenshell.geom.iterator(
            settings,
            ifc,
            num_threads,
            include=visiveis_com_rep,
        )
        if it.initialize():
            while True:
                try:
                    shape = it.get()
                except Exception:
                    shape = None
                if shape is not None:
                    step_id = shape.id
                    v = shape.geometry.verts
                    if v:
                        processados.add(step_id)
                        exmin, exmax = min(v[0::3]), max(v[0::3])
                        eymin, eymax = min(v[1::3]), max(v[1::3])
                        ezmin, ezmax = min(v[2::3]), max(v[2::3])
                        if (
                            exmin <= xmax
                            and exmax >= xmin
                            and eymin <= ymax
                            and eymax >= ymin
                            and ezmin <= zmax
                            and ezmax >= zmin
                        ):
                            ids.append(step_id)
                try:
                    tem_mais = it.next()
                except Exception:
                    tem_mais = False
                if not tem_mais:
                    break

    candidatos_ids = {e.id() for e in visiveis_com_rep}
    falhas_geometria = tuple(sorted(candidatos_ids - processados))

    return Selecao(
        ids=tuple(sorted(set(ids))),
        tipo="CORTE",
        pavimento=pav_ent.id() if pav_ent is not None else None,
        faixa=faixa,
        ocultos_por_classe=ocultos,
        sem_geometria=sem_geometria,
        falhas_geometria=falhas_geometria,
    )
