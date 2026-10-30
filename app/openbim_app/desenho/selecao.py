# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seleção de elementos IFC para desenho de vistas 2D (ADR-006 §3 item 0)."""
from __future__ import annotations

import dataclasses
from typing import Any, Iterable

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.unit
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


def _validar_categorias(ifc: ifcopenshell.file, categorias: tuple[str, ...]) -> None:
    schema = ifcopenshell.schema_by_name(ifc.schema)
    for cat in categorias:
        try:
            decl = schema.declaration_by_name(cat)
            if decl.as_entity() is None:
                raise SelecaoInvalida(f"Classe não é entidade: {cat}")
        except Exception:
            raise SelecaoInvalida(f"Categoria desconhecida no esquema {ifc.schema}: {cat}")


def _resolver_pavimento(
    ifc: ifcopenshell.file, anotacao: Any, pavimento: str | None
) -> Any | None:
    if pavimento is not None:
        try:
            cand = ifc.by_guid(pavimento)
        except Exception:
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

    for rel in getattr(pav, "ContainsElements", ()) or ():
        for e in getattr(rel, "RelatedElements", ()) or ():
            if e.is_a("IfcElement"):
                candidatos.add(e)

    fila = list(candidatos)
    while fila:
        elem = fila.pop()
        for rel in getattr(elem, "IsDecomposedBy", ()) or ():
            for filho in getattr(rel, "RelatedObjects", ()) or ():
                if filho.is_a("IfcElement") and filho not in candidatos:
                    candidatos.add(filho)
                    fila.append(filho)

    novos = list(candidatos)
    while novos:
        elem = novos.pop()
        for rel in getattr(elem, "HasOpenings", ()) or ():
            op = getattr(rel, "RelatedOpeningElement", None)
            if op is not None and op.is_a("IfcElement") and op not in candidatos:
                candidatos.add(op)
                novos.append(op)
            if op is not None:
                for frel in getattr(op, "HasFillings", ()) or ():
                    fill = getattr(frel, "RelatedBuildingElement", None)
                    if fill is not None and fill.is_a("IfcElement") and fill not in candidatos:
                        candidatos.add(fill)
                        novos.append(fill)
        for rel in getattr(elem, "IsDecomposedBy", ()) or ():
            for filho in getattr(rel, "RelatedObjects", ()) or ():
                if filho.is_a("IfcElement") and filho not in candidatos:
                    candidatos.add(filho)
                    novos.append(filho)

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
        )

    # CORTE
    origem = info.get("origem")
    tamanho = info.get("tamanho")
    if origem is None or tamanho is None:
        raise SelecaoInvalida("Vista CORTE sem origem ou tamanho")

    scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    xmin = min(origem[0], origem[0] + tamanho[0]) * scale
    xmax = max(origem[0], origem[0] + tamanho[0]) * scale
    ymin = min(origem[1], origem[1] + tamanho[1]) * scale
    ymax = max(origem[1], origem[1] + tamanho[1]) * scale
    zmin = min(origem[2], origem[2] + tamanho[2]) * scale
    zmax = max(origem[2], origem[2] + tamanho[2]) * scale
    faixa = ((xmin, ymin, zmin), (xmax, ymax, zmax))

    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    sem_geometria = 0
    ocultos = {}
    ids = []
    for elem in ifc.by_type("IfcElement"):
        if not getattr(elem, "Representation", None):
            sem_geometria += 1
            continue
        try:
            shape = ifcopenshell.geom.create_shape(settings, elem)
        except Exception:
            continue
        v = shape.geometry.verts
        exmin, exmax = min(v[0::3]), max(v[0::3])
        eymin, eymax = min(v[1::3]), max(v[1::3])
        ezmin, ezmax = min(v[2::3]), max(v[2::3])

        if exmin <= xmax and exmax >= xmin and eymin <= ymax and eymax >= ymin and ezmin <= zmax and ezmax >= zmin:
            if any(elem.is_a(cat) for cat in cats):
                cls = elem.is_a()
                ocultos[cls] = ocultos.get(cls, 0) + 1
            else:
                ids.append(elem.id())

    return Selecao(
        ids=tuple(sorted(set(ids))),
        tipo="CORTE",
        pavimento=pav_ent.id() if pav_ent is not None else None,
        faixa=faixa,
        ocultos_por_classe=ocultos,
        sem_geometria=sem_geometria,
    )
