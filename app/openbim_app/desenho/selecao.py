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


def _validar_filho(filho: Any) -> None:
    if filho is not None and not callable(getattr(filho, "executar", None)):
        raise TypeError(f"filho inválido: {filho!r} (esperado objeto com executar chamável ou None)")


def _validar_caixa(val: Any) -> list[float] | None:
    """Valida caixa envolvente [xmin, ymin, zmin, xmax, ymax, zmax] com 6 floats finitos."""
    if not isinstance(val, (list, tuple)) or len(val) != 6:
        return None
    try:
        floats = [float(x) for x in val]
    except (ValueError, TypeError):
        return None
    if not all(math.isfinite(x) for x in floats):
        return None
    if floats[0] > floats[3] or floats[1] > floats[4] or floats[2] > floats[5]:
        return None
    return floats


def _tem_unidade_ambigua(ifc: ifcopenshell.file, scale: float) -> bool:
    """Indica IfcProjectLibrary que pode divergir da escala de IfcProject no kernel C++."""
    libs = ifc.by_type("IfcProjectLibrary")
    return bool(libs) and (
        abs(scale - 1.0) > 1e-12
        or any(getattr(lib, "UnitsInContext", None) is not None for lib in libs)
    )


def _matriz_esperada_cache(elem: Any, scale: float) -> np.ndarray | None:
    """Matriz 4x4 esperada no cache (metros), ou None se placement for não-ortogonal/inválido."""
    pl = getattr(elem, "ObjectPlacement", None)
    if pl is None:
        return np.eye(4, dtype=np.float64)
    m = np.asarray(ifcopenshell.util.placement.get_local_placement(pl), dtype=np.float64).copy()
    if m.shape != (4, 4) or not np.all(np.isfinite(m)):
        return None
    r = m[:3, :3]
    if not np.allclose(r.T @ r, np.eye(3), rtol=0.0, atol=1e-9):
        return None
    m[:3, 3] *= scale
    return m


def _perto_borda_faixa(
    c: list[float],
    faixa: tuple[tuple[float, float, float], tuple[float, float, float]],
    tol: float = 1e-5,
) -> bool:
    """True se alguma face da caixa estiver a <= `tol` m da borda correspondente de `cruza`."""
    (xmin, ymin, zmin), (xmax, ymax, zmax) = faixa
    if (
        c[0] > xmax + tol or c[3] < xmin - tol
        or c[1] > ymax + tol or c[4] < ymin - tol
        or c[2] > zmax + tol or c[5] < zmin - tol
    ):
        return False
    return (
        abs(c[0] - xmax) <= tol or abs(c[3] - xmin) <= tol
        or abs(c[1] - ymax) <= tol or abs(c[4] - ymin) <= tol
        or abs(c[2] - zmax) <= tol or abs(c[5] - zmin) <= tol
    )


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
    assinatura_ifc: tuple[int, int] | list[int] | None = None,
    profundidade_corte: float | None = None,
    filho=None,
    pasta_cache_geometria: str | Path | None = None,
) -> Selecao:
    _validar_filho(filho)
    _validar_profundidade_corte(profundidade_corte)
    if pasta_cache_geometria is not None and not isinstance(pasta_cache_geometria, (str, Path)):
        raise TypeError(
            f"pasta_cache_geometria inválido: {pasta_cache_geometria!r} (esperado str, Path ou None)"
        )
    pasta_geo = str(pasta_cache_geometria) if pasta_cache_geometria is not None else ""
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
        def _rodar_auxiliar(pedido: dict) -> dict:
            preparado = auxiliar.preparar(
                ifc,
                pedido,
                caminho_ifc=caminho_ifc,
                assinatura=assinatura_ifc,
            )
            try:
                return auxiliar.executar(
                    preparado,
                    limite_s=limite_s,
                    cancelar=cancelar,
                    executor=executor,
                    filho=filho,
                )
            finally:
                preparado.fechar()

        restantes = faltantes
        if pasta_geo and caminho_ifc is not None and not _tem_unidade_ambigua(ifc, scale):
            elegiveis_cache: list[Any] = []
            matrizes_esp: dict[int, np.ndarray] = {}
            for e in faltantes:
                try:
                    mat_esp = _matriz_esperada_cache(e, scale)
                except Exception:
                    mat_esp = None
                if mat_esp is not None:
                    elegiveis_cache.append(e)
                    matrizes_esp[e.id()] = mat_esp
            if elegiveis_cache:
                resp_cache = _rodar_auxiliar({
                    "op": "caixas_cache",
                    "elementos": [[e.id(), e.GlobalId] for e in elegiveis_cache],
                    "vista": {"guid": gid_vista},
                    "pasta_cache_geometria": pasta_geo,
                    "threads": auxiliar.threads_padrao(),
                })
                cx_cache = resp_cache.get("caixas_envolventes") if isinstance(resp_cache, dict) else None
                mats_cache = resp_cache.get("matrizes") if isinstance(resp_cache, dict) else None
                if isinstance(cx_cache, dict):
                    for chave, caixa in cx_cache.items():
                        try:
                            id_step = int(chave)
                        except (TypeError, ValueError):
                            continue
                        mat_esp = matrizes_esp.get(id_step)
                        if mat_esp is None:
                            continue
                        caixa_ok = _validar_caixa(caixa)
                        if caixa_ok is None:
                            continue
                        if isinstance(mats_cache, dict):
                            mat_raw = mats_cache.get(str(id_step))
                            try:
                                mat_arr = np.asarray(mat_raw, dtype=np.float64).reshape((4, 4))
                                fresca = np.all(np.isfinite(mat_arr)) and np.allclose(
                                    mat_arr, mat_esp, rtol=0.0, atol=1e-9
                                )
                            except (TypeError, ValueError):
                                fresca = False
                            if not fresca:
                                continue
                        if _perto_borda_faixa(caixa_ok, faixa):
                            continue
                        guardadas[id_step] = caixa_ok
                        erros_por_id.pop(id_step, None)
                    restantes = [e for e in faltantes if e.id() not in guardadas]

        if restantes:
            resposta = _rodar_auxiliar({
                "op": "caixas",
                "elementos": [[e.id(), e.GlobalId] for e in restantes],
                "vista": {"guid": gid_vista},
                "threads": auxiliar.threads_padrao(),
            })

            for chave, caixa in resposta["caixas_envolventes"].items():
                guardadas[int(chave)] = [float(v) for v in caixa]
            for falha in resposta["falhas_geometria"]:
                guardadas[int(falha)] = None

            pedidos = [e.id() for e in restantes]
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
        floats = _validar_caixa(val[:6] if isinstance(val, (list, tuple)) and len(val) >= 6 else val)
        if floats is not None:
            caixas_dict[int(i)] = tuple(floats)

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
