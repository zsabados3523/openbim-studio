# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agrupamento de elementos por componentes conexos da pegada 2D real (XY)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re

import ifcopenshell
import ifcopenshell.geom
import numpy as np
from obim_geometria import nucleos, silhueta
from shapely import STRtree

FOLGA = 0.002


def pegada_xy(verts, tris):
    """União 2D (Polygon | MultiPolygon | None) dos triângulos projetados em XY, sem folga."""
    return silhueta.uniao_triangulos_xy(verts, tris, threads=1)


def agrupar(pegadas, folga: float = FOLGA) -> list[list[int]]:
    """Componentes conexos de `pegadas` (distância <= `folga`); saída determinística por menor índice."""
    n = len(pegadas)
    if n == 0:
        return []
    pai = list(range(n))

    def achar(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def unir(a: int, b: int) -> None:
        ra, rb = achar(a), achar(b)
        if ra != rb:
            if ra < rb:
                pai[rb] = ra
            else:
                pai[ra] = rb

    validos = [(i, g) for i, g in enumerate(pegadas) if g is not None and not g.is_empty]
    if len(validos) >= 2:
        geoms = [g for _, g in validos]
        pares = STRtree(geoms).query(geoms, predicate="dwithin", distance=float(folga))
        for a, b in zip(pares[0].tolist(), pares[1].tolist()):
            if a < b:
                unir(validos[a][0], validos[b][0])

    grupos: dict[int, list[int]] = {}
    for i in range(n):
        grupos.setdefault(achar(i), []).append(i)
    return sorted(grupos.values(), key=lambda g: g[0])


def _pegada_da_forma(sh):
    """Calcula a pegada 2D de uma forma já triangulada."""
    try:
        geo = sh.geometry
        if geo.verts and geo.faces:
            return pegada_xy(
                np.asarray(geo.verts, dtype=float).reshape(-1, 3),
                np.asarray(geo.faces, dtype=int).reshape(-1, 3),
            )
    except Exception:
        pass
    return None


def _aberturas_step(arquivo, ids: list[int]) -> set[int]:
    """IDs de `IfcOpeningElement` no STEP sem chamar `ifcopenshell.open`."""
    alvo, achados = set(ids), set()
    pat = re.compile(r"^\s*#(\d+)\s*=\s*IFCOPENING(?:ELEMENT|STANDARDCASE)\s*\(", re.I)
    try:
        with open(arquivo, "r", encoding="utf-8", errors="ignore") as fp:
            for linha in fp:
                if (m := pat.match(linha)) and (eid := int(m.group(1))) in alvo:
                    achados.add(eid)
                    if len(achados) == len(alvo):
                        break
    except Exception:
        pass
    return achados


def dividir_elementos(
    arquivo, elementos, folga: float = FOLGA, threads: int | None = None, formas: dict | None = None, f=None
) -> list[list]:
    """Agrupa `elementos` (`[id_step, guid]`) pela pegada XY no mundo, mantendo a ordem original."""
    elems = [list(e) for e in elementos]
    if not elems:
        return []
    if len(elems) == 1:
        return [elems]
    formas_uso = dict(formas) if isinstance(formas, dict) else {}
    faltam_ids = list(dict.fromkeys(
        id_step for id_step, _guid in elems if formas_uso.get(id_step) is None
    ))
    if faltam_ids and f is None:
        aberturas = _aberturas_step(arquivo, faltam_ids)
        if aberturas:
            faltam_ids = [i for i in faltam_ids if i not in aberturas]
    if faltam_ids:
        if f is None:
            f = ifcopenshell.open(arquivo)
        cfg = ifcopenshell.geom.settings()
        cfg.set(cfg.USE_WORLD_COORDS, True)
        incl = []
        for id_step in faltam_ids:
            try:
                el = f.by_id(id_step)
                if el is not None and not el.is_a("IfcOpeningElement"):
                    incl.append(el)
            except Exception:
                pass
        try:
            if incl:
                it = ifcopenshell.geom.iterator(cfg, f, nucleos.limitar_threads(threads), include=incl)
                if it.initialize():
                    while True:
                        try:
                            sh = it.get()
                            geo = sh.geometry
                            if geo.verts and geo.faces:
                                formas_uso[sh.id] = sh
                        except Exception:
                            pass
                        if not it.next():
                            break
        except Exception:
            pass
    pares = [
        (id_step, formas_uso[id_step])
        for id_step in dict.fromkeys(i for i, _guid in elems)
        if formas_uso.get(id_step) is not None
    ]
    peg_por_id = {}
    if pares:
        with ThreadPoolExecutor(max_workers=nucleos.limitar_threads(threads)) as ex:
            for (id_step, _sh), peg in zip(pares, ex.map(_pegada_da_forma, (sh for _, sh in pares))):
                if peg is not None:
                    peg_por_id[id_step] = peg
    pegadas = [peg_por_id.get(id_step) for id_step, _guid in elems]
    return [[elems[i] for i in g] for g in agrupar(pegadas, folga=folga)]
