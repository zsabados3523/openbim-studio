# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cálculo de caixas envolventes (bbox) de produtos IFC em metros (mundo)."""
import math
import traceback
from itertools import chain

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
from obim_geometria import nucleos


class ArvoreCaixas:
    """Consulta de caixas envolventes por interseção fechada. A busca é linear: só o
    contrato de resultado importa (a poda espacial fica para a T07c)."""

    def __init__(self, caixas: dict):
        self._itens = []
        for chave, bruta in caixas.items():
            try:
                c = [float(v) for v in bruta]
            except (TypeError, ValueError) as e:
                raise ValueError(f"Caixa inválida para {chave!r}: {bruta!r}") from e
            if len(c) != 6 or not all(math.isfinite(v) for v in c):
                raise ValueError(f"Caixa inválida para {chave!r}: {bruta!r}")
            if c[0] > c[3] or c[1] > c[4] or c[2] > c[5]:
                raise ValueError(f"Caixa com mínimo maior que máximo para {chave!r}: {bruta!r}")
            self._itens.append((int(chave), c))

    def __len__(self) -> int:
        return len(self._itens)

    def cruzando(self, minimo, maximo) -> list[int]:
        lo, hi = [float(v) for v in minimo], [float(v) for v in maximo]
        if len(lo) != 3 or len(hi) != 3 or not all(math.isfinite(v) for v in lo + hi):
            raise ValueError(f"Consulta inválida: {minimo!r}, {maximo!r}")
        if lo[0] > hi[0] or lo[1] > hi[1] or lo[2] > hi[2]:
            raise ValueError(f"Consulta com mínimo maior que máximo: {minimo!r}, {maximo!r}")
        return sorted(
            chave
            for chave, c in self._itens
            if c[0] <= hi[0] and c[3] >= lo[0]
            and c[1] <= hi[1] and c[4] >= lo[1]
            and c[2] <= hi[2] and c[5] >= lo[2]
        )


def _caixa(shape) -> list[float] | None:
    verts = shape.geometry.verts if shape else None
    if not verts:
        return None
    xs, ys, zs = verts[0::3], verts[1::3], verts[2::3]
    return [float(min(xs)), float(min(ys)), float(min(zs)),
            float(max(xs)), float(max(ys)), float(max(zs))]


def _orto(M):
    """Ortogonaliza a coluna X contra Z e refaz Y, como o motor de geometria."""
    z, x = M[:3, 2], M[:3, 0]
    x = x - float(x @ z) * z
    norma = float(np.linalg.norm(x))
    if norma < 1e-12:
        raise ValueError("eixos de posicionamento degenerados")
    M = M.copy()
    M[:3, 0] = x / norma
    M[:3, 1] = np.cross(z, M[:3, 0])
    return M


def _matriz_placement(placement):
    """Placement mundial com eixos ortogonais, como o motor de geometria (o a2p não ortogonaliza o RefDirection)."""
    M = ifcopenshell.util.placement.get_local_placement(placement) if placement else np.eye(4)
    return _orto(M)


def _matriz_mapeada(item):
    """IfcMappedItem (MappingTarget.escala + MappingOrigin), com os eixos ortogonalizados como o motor."""
    alvo = item.MappingTarget
    if alvo is None or not alvo.is_a("IfcCartesianTransformationOperator3D") and not alvo.is_a(
            "IfcCartesianTransformationOperator3DnonUniform"):
        return None
    a1 = np.asarray(alvo.Axis1.DirectionRatios if alvo.Axis1 else (1.0, 0.0, 0.0), dtype=float)
    a2 = np.asarray(alvo.Axis2.DirectionRatios if alvo.Axis2 else (0.0, 1.0, 0.0), dtype=float)
    a3 = np.asarray(alvo.Axis3.DirectionRatios if getattr(alvo, "Axis3", None) else (0.0, 0.0, 1.0), dtype=float)
    norma = float(np.linalg.norm(a3))
    if norma < 1e-12:
        return None
    z = a3 / norma
    x = a1 - float(a1 @ z) * z
    norma = float(np.linalg.norm(x))
    if norma < 1e-12:
        return None
    x = x / norma
    y = np.cross(z, x)
    if float(y @ a2) < 0.0:
        y = -y
    s1 = float(alvo.Scale) if alvo.Scale is not None else 1.0
    if alvo.is_a("IfcCartesianTransformationOperator3DnonUniform"):
        s2 = float(alvo.Scale2) if alvo.Scale2 is not None else s1
        s3 = float(alvo.Scale3) if alvo.Scale3 is not None else s1
    else:
        s2 = s3 = s1
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2] = x * s1, y * s2, z * s3
    M[:3, 3] = np.asarray(alvo.LocalOrigin.Coordinates, dtype=float)
    origem = ifcopenshell.util.placement.get_axis2placement(item.MappingSource.MappingOrigin)
    return M @ _orto(origem)


def _indices(flat, pn, total):
    """Índices 0-based únicos usados; `pn` (PnIndex) interpõe-se entre faces e CoordList."""
    try:
        if flat.size == 0:
            return None
        if pn:
            pn = np.asarray(pn, dtype=np.int64)
            if flat.min() < 1 or flat.max() > len(pn):
                return None
            flat = pn[flat - 1]
        if flat.size == 0 or flat.min() < 1 or flat.max() > total:
            return None
        return np.unique(flat) - 1
    except (TypeError, ValueError, IndexError):
        return None


def _pts_faceset(item, cache=None):
    """Pontos usados por IfcPolygonalFaceSet / IfcTriangulatedFaceSet (ou None). Cacheados por entidade."""
    chave = ("fs", item.id())
    if cache is not None and chave in cache:
        return cache[chave]
    try:
        P = np.asarray(item.Coordinates.CoordList, dtype=float)
        if P.ndim != 2 or P.shape[1] != 3 or not len(P):
            return None
        if item.is_a("IfcPolygonalFaceSet"):
            faces = item.Faces or []
            if not faces:
                return None
            listas = []
            for face in faces:
                listas.append(face.CoordIndex)
                if face.is_a("IfcIndexedPolygonalFaceWithVoids"):
                    listas.extend(face.InnerCoordIndices or [])
            flat = np.fromiter(chain.from_iterable(listas), dtype=np.int64)
        elif item.CoordIndex:
            flat = np.asarray(item.CoordIndex, dtype=np.int64).ravel()
        else:
            return None
        idx = _indices(flat, item.PnIndex, len(P))
    except (AttributeError, TypeError, ValueError, IndexError):
        return None
    pts = None if idx is None else P[idx]
    if cache is not None and pts is not None:
        cache[chave] = pts
    return pts


def _pts_cfs(conjuntos, chave=None, cache=None):
    """Pontos dos IfcPolyLoop das faces de uma lista de IfcConnectedFaceSet/IfcShell."""
    if cache is not None and chave in cache:
        return cache[chave]
    pontos = []
    try:
        for cfs in conjuntos or []:
            for face in cfs.CfsFaces or []:
                for limite in face.Bounds or []:
                    loop = limite.Bound
                    if not loop.is_a("IfcPolyLoop"):
                        return None
                    for p in loop.Polygon or []:
                        c = p.Coordinates
                        pontos.append((float(c[0]), float(c[1]), float(c[2])))
    except (AttributeError, TypeError, ValueError, IndexError):
        return None
    if not pontos:
        return None
    pts = np.asarray(pontos, dtype=float)
    if cache is not None:
        cache[chave] = pts
    return pts


def _pts_itens(itens, matriz, cache=None):
    """Pontos mundiais dos itens (face set direto ou via IfcMappedItem); None se algum não serve."""
    partes = []
    for item in itens:
        tipo = item.is_a()
        if tipo == "IfcMappedItem":
            tmap = _matriz_mapeada(item)
            if tmap is None:
                return None
            pts = _pts_itens(item.MappingSource.MappedRepresentation.Items, matriz @ tmap, cache)
        else:
            if tipo in ("IfcPolygonalFaceSet", "IfcTriangulatedFaceSet"):
                pts = _pts_faceset(item, cache)
            elif tipo == "IfcFaceBasedSurfaceModel":
                pts = _pts_cfs(item.FbsmFaces, ("cfs", item.id()), cache)
            elif tipo == "IfcShellBasedSurfaceModel":
                pts = _pts_cfs(item.SbsmBoundary, ("cfs", item.id()), cache)
            else:
                return None
            if pts is not None:
                pts = pts @ matriz[:3, :3].T + matriz[:3, 3]
        if pts is None or not len(pts):
            return None
        partes.append(pts)
    return np.vstack(partes) if partes else None


def _caixa_face_set(el, fator, cache=None):
    """Caixa mundial só de pontos, se o Body for exatamente um item de face set; senão None."""
    rep = getattr(el, "Representation", None)
    if rep is None:
        return None
    corpos = [r for r in (rep.Representations or []) if r.RepresentationIdentifier == "Body"]
    if len(corpos) != 1 or not corpos[0].Items:
        return None
    matriz = _matriz_placement(el.ObjectPlacement)
    pts = _pts_itens(corpos[0].Items, matriz, cache)
    if pts is None or not len(pts):
        return None
    pts = pts * fator
    minimo, maximo = pts.min(axis=0), pts.max(axis=0)
    return [float(v) for v in (*minimo, *maximo)]


def processar(pedido: dict) -> dict:
    try:
        threads = nucleos.limitar_threads(pedido.get("threads"))
        f = ifcopenshell.open(pedido.get("arquivo"))
        elementos = pedido.get("elementos", [])
        entidades = {}
        for id_step, guid in elementos:
            try:
                el = f.by_id(id_step)
            except Exception:
                el = None
            if el is None or getattr(el, "GlobalId", None) != guid:
                return {"ok": False, "erro": {"tipo": "ArquivoDivergente", "mensagem": f"ID {id_step} diverge do arquivo", "rastro": ""}}
            entidades[int(id_step)] = el

        if not elementos:
            return {"ok": True, "caixas_envolventes": {}, "falhas_geometria": [], "passagens_iterator": 0, "erros_iterator": []}

        s = ifcopenshell.geom.settings()
        s.set(s.USE_WORLD_COORDS, True)
        caixas: dict[str, list[float]] = {}
        visitados: set[int] = set()
        erros: list[dict] = []
        erros_multi: list[dict] = []
        passagens = 0

        def passagem(sub):
            nonlocal passagens
            passagens += 1
            it = ifcopenshell.geom.iterator(s, f, threads, include=[f.by_id(i) for i, _ in sub])
            if not it.initialize():
                return False, 0, None
            progresso, abortada, id_falha = 0, False, None

            def _falha(e):
                nonlocal id_falha, abortada
                if len(sub) == 1:
                    id_falha = int(sub[0][0])
                    erros.append({"tipo": type(e).__name__, "mensagem": str(e), "ids": [id_falha]})
                else:
                    erros_multi.append({"tipo": type(e).__name__, "mensagem": str(e)})
                abortada = True

            while True:
                try:
                    shape = it.get()
                except Exception as e:
                    _falha(e)
                    break
                if shape is not None:
                    visitados.add(int(shape.id))
                    progresso += 1
                    caixa = _caixa(shape)
                    if caixa is not None:
                        caixas[str(shape.id)] = caixa
                try:
                    if not it.next():
                        break
                except Exception as e:
                    _falha(e)
                    break
            return abortada, progresso, id_falha

        restantes = list(elementos)
        try:
            fator = ifcopenshell.util.unit.calculate_unit_scale(f, "LENGTHUNIT")
        except Exception:
            fator = None
        if fator is not None:
            pendentes = []
            cache: dict = {}
            for id_step, guid in restantes:
                caixa = None
                try:
                    caixa = _caixa_face_set(entidades.get(int(id_step)), fator, cache)
                except Exception:
                    caixa = None
                if caixa is None:
                    pendentes.append((id_step, guid))
                else:
                    caixas[str(id_step)] = caixa
                    visitados.add(int(id_step))
            restantes = pendentes
        while restantes:
            abortada, progresso, id_falha = passagem(restantes)
            if not abortada:
                break
            if id_falha is not None:
                visitados.add(id_falha)
            restantes = [e for e in restantes if int(e[0]) not in visitados]
            if not restantes:
                break
            if progresso or id_falha is not None:
                continue
            for elem in list(restantes):
                sub_abortada, _, sub_falha = passagem([elem])
                if sub_abortada:
                    visitados.add(sub_falha if sub_falha is not None else int(elem[0]))
                    break
            restantes = [e for e in restantes if int(e[0]) not in visitados]

        caixas = {str(i): caixas[str(i)] for i, _ in elementos if str(i) in caixas}
        falhas = [id_step for id_step, _ in elementos if str(id_step) not in caixas]
        if not erros:
            erros.extend(erros_multi)
        return {"ok": True, "caixas_envolventes": caixas, "falhas_geometria": falhas,
                "passagens_iterator": passagens, "erros_iterator": erros}
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
