# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seleção de elementos IFC para desenho de vistas 2D (ADR-006 §3 item 0)."""
from __future__ import annotations

import dataclasses
import math
import numbers
from pathlib import Path
from typing import Any, Iterable

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar


class SelecaoInvalida(ValueError):
    """Parâmetros de vista, pavimento ou categoria inválidos para seleção."""


def _validar_profundidade_corte(profundidade_corte: Any) -> None:
    if profundidade_corte is None:
        return
    if isinstance(profundidade_corte, bool) or not isinstance(profundidade_corte, (int, float, numbers.Real)):
        raise ValueError(f"profundidade_corte deve ser int ou float, recebido: {profundidade_corte!r}")
    if not math.isfinite(profundidade_corte) or profundidade_corte <= 0:
        raise ValueError(f"profundidade_corte deve ser positivo e finito, recebido: {profundidade_corte!r}")


CATEGORIAS_PADRAO_PLANTA_OCULTAS: tuple[str, ...] = (
    "IfcMember",
    "IfcPlate",
    "IfcMechanicalFastener",
    "IfcRailing",
)

CLASSES_VERTICAIS_CONTINUAS: tuple[str, ...] = (
    "IfcColumn",
    "IfcStair",
    "IfcStairFlight",
)

CLASSES_LOCAIS_XY: tuple[str, ...] = (
    "IfcWall", "IfcBeam", "IfcDoor", "IfcWindow", "IfcCovering", "IfcFlowSegment", "IfcFlowFitting"
)



@dataclasses.dataclass(frozen=True)
class Selecao:
    ids: tuple[int, ...]
    tipo: str
    pavimento: int | None
    faixa: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    ocultos_por_classe: dict[str, int]
    sem_geometria: int
    falhas_geometria: tuple[int, ...] = ()
    erros_geometria: tuple[str, ...] = ()
    caixas_envolventes: dict[int, tuple[float, float, float, float, float, float]] = dataclasses.field(default_factory=dict)


class SessaoSelecao:
    """Caixas (ou falhas) e erros de geometria já calculados POR elemento entre cortes;
    quem altera o modelo invalida os ids afetados."""

    def __init__(self) -> None:
        self._caixas: dict[int, list[float] | None] = {}
        self._erros: dict[int, list[str]] = {}

    def invalidar(self, ids=None) -> None:
        if ids is None:
            self._caixas.clear()
            self._erros.clear()
            return
        for i in ids:
            chave = int(i)
            self._caixas.pop(chave, None)
            self._erros.pop(chave, None)


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
    executor=None,
    limite_s: float = auxiliar.LIMITE_PADRAO_S,
    cancelar=None,
    sessao: SessaoSelecao | None = None,
    caminho_ifc: str | Path | None = None,
    profundidade_corte: float | None = None,
) -> Selecao:
    _validar_profundidade_corte(profundidade_corte)
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
            caixas_envolventes={},
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

    scale = float(ifcopenshell.util.unit.calculate_unit_scale(ifc))
    M_placement = ifcopenshell.util.placement.get_local_placement(anotacao.ObjectPlacement)
    pos = getattr(bloco, "Position", None)
    M_block = (
        ifcopenshell.util.placement.get_axis2placement(pos)
        if pos is not None
        else np.eye(4)
    )
    dx = float(bloco.XLength)
    dy = float(bloco.YLength)
    if profundidade_corte is not None:
        dz = float(profundidade_corte) / scale
        M_block = np.array(M_block, copy=True)
        M_block[2, 3] = -dz
    else:
        dz = float(bloco.ZLength)
    M_total = M_placement @ M_block

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

    guardadas = sessao._caixas if sessao is not None else {}
    erros_por_id = sessao._erros if sessao is not None else {}
    z_min_seguro, z_max_seguro = zmin - 4.0, zmax + 4.0
    x_min_seguro, x_max_seguro = xmin - 5.0, xmax + 5.0
    y_min_seguro, y_max_seguro = ymin - 5.0, ymax + 5.0

    faltantes: list[Any] = []
    for e in visiveis_com_rep:
        if e.id() in guardadas:
            continue
        if e.is_a("IfcOpeningElement"):
            continue
        if e.ObjectPlacement is not None and not any(e.is_a(c) for c in CLASSES_VERTICAIS_CONTINUAS):
            try:
                M = ifcopenshell.util.placement.get_local_placement(e.ObjectPlacement)
                pz = float(M[2, 3]) * scale
                if pz < z_min_seguro or pz > z_max_seguro:
                    continue
                if any(e.is_a(c) for c in CLASSES_LOCAIS_XY):
                    px, py = float(M[0, 3]) * scale, float(M[1, 3]) * scale
                    if px < x_min_seguro or px > x_max_seguro or py < y_min_seguro or py > y_max_seguro:
                        continue
            except Exception:
                pass
        faltantes.append(e)

    if faltantes:
        pedido = {
            "op": "caixas",
            "elementos": [[e.id(), e.GlobalId] for e in faltantes],
            "vista": {"guid": gid_vista},
            "threads": auxiliar.threads_padrao(),
        }
        preparado = auxiliar.preparar(ifc, pedido, caminho_ifc=caminho_ifc)
        try:
            resposta = auxiliar.executar(
                preparado,
                limite_s=limite_s,
                cancelar=cancelar,
                executor=executor,
            )
        finally:
            preparado.fechar()

        for chave, caixa in resposta["caixas_envolventes"].items():
            guardadas[int(chave)] = [float(v) for v in caixa]
        for falha in resposta["falhas_geometria"]:
            guardadas[int(falha)] = None

        pedidos = [e.id() for e in faltantes]
        for id_step in pedidos:  # recalculado: erros velhos desses ids não valem mais
            erros_por_id.pop(id_step, None)
        for erro in resposta.get("erros_iterator", ()):
            msg = f"{erro.get('tipo', 'RuntimeError')}: {erro.get('mensagem', '')}"
            for id_step in erro.get("ids") or pedidos:
                lista = erros_por_id.setdefault(int(id_step), [])
                if msg not in lista:
                    lista.append(msg)

    def cruza(id_step: int) -> bool:
        c = guardadas.get(id_step)
        return c is not None and (
            c[0] <= xmax and c[3] >= xmin
            and c[1] <= ymax and c[4] >= ymin
            and c[2] <= zmax and c[5] >= zmin
        )

    ids = [
        e.id()
        for e in visiveis_com_rep
        if not e.is_a("IfcOpeningElement") and cruza(e.id())
    ]
    falhas_geometria = tuple(sorted(
        e.id()
        for e in visiveis_com_rep
        if not e.is_a("IfcOpeningElement") and e.id() in guardadas and guardadas[e.id()] is None
    ))
    mensagens: list[str] = []
    for elem in visiveis_com_rep:  # só erro de elemento visível no corte, sem duplicar
        if elem.is_a("IfcOpeningElement"):
            continue
        for msg in erros_por_id.get(elem.id(), ()):
            if msg not in mensagens:
                mensagens.append(msg)
    erros_geometria = tuple(mensagens)

    caixas_dict: dict[int, tuple[float, float, float, float, float, float]] = {}
    for i in ids:
        val = guardadas.get(i)
        if isinstance(val, (list, tuple)) and len(val) >= 6:
            try:
                floats = tuple(float(x) for x in val[:6])
            except (ValueError, TypeError):
                continue
            if not all(math.isfinite(x) for x in floats):
                continue
            if floats[0] > floats[3] or floats[1] > floats[4] or floats[2] > floats[5]:
                continue
            caixas_dict[int(i)] = floats

    return Selecao(
        ids=tuple(sorted(set(ids))),
        tipo="CORTE",
        pavimento=pav_ent.id() if pav_ent is not None else None,
        faixa=faixa,
        ocultos_por_classe=ocultos,
        sem_geometria=sem_geometria,
        falhas_geometria=falhas_geometria,
        erros_geometria=erros_geometria,
        caixas_envolventes=caixas_dict,
    )
