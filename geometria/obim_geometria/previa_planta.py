# SPDX-License-Identifier: AGPL-3.0-or-later
"""Previa provisoria da planta sem HLR (secao exata, silhueta/casco e caixas de falha)."""
from __future__ import annotations

from functools import reduce
from html import escape
import math
import os

import numpy as np
import shapely

from obim_geometria.aneis import aneis_de_segmentos
from obim_geometria.corte_plano import cortar_malha_no_plano
from obim_geometria.silhueta import silhueta_xy

_JITTER_Z = 1e-7
_AREA_MIN = 1e-12
_TOL_Z_OCLUSAO = 1e-3
_TOL_AREA_OCLUSAO = 1e-4
_PRIORIDADE_AUDITORIA = {"cortada": 0, "vista": 1, "falha": 2, "oculta": 3, "acima": 4}
_NS_SVG = "http://www.w3.org/2000/svg"
_NS_IFC = "http://www.ifcopenshell.org/ns"


def _fmt(valor: float) -> str:
    return f"{round(float(valor), 6) + 0.0:.6f}"


def _area_anel(pts) -> float:
    arr = np.asarray(pts, dtype=np.float64)
    if arr.ndim != 2 or len(arr) < 3 or arr.shape[1] < 2:
        return 0.0
    x, y = arr[:, 0], arr[:, 1]
    return 0.5 * abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))


def _validar_malha(verts, tris) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    if verts is None or tris is None:
        return None
    try:
        v = np.asarray(verts, dtype=np.float64)
        t_raw = np.asarray(tris)
    except (TypeError, ValueError):
        return None
    if v.ndim != 2 or v.shape[0] == 0 or v.shape[1] != 3:
        return None
    if t_raw.ndim != 2 or t_raw.shape[0] == 0 or t_raw.shape[1] != 3:
        return None
    if not np.issubdtype(t_raw.dtype, np.integer):
        return None
    t = t_raw.astype(np.int64, copy=False)
    if int(t.min()) < 0 or int(t.max()) >= len(v):
        return None
    usados = np.zeros(len(v), dtype=bool)
    usados[t] = True
    v_usados = v[usados]
    if len(v_usados) == 0 or not np.isfinite(v_usados).all():
        return None
    return v, t, v_usados


def _anel_caixa(caixa) -> list[list[tuple[float, float]]]:
    if caixa is None:
        return []
    try:
        vals = [float(x) for x in caixa]
    except (TypeError, ValueError):
        return []
    if len(vals) == 4:
        x0, y0, x1, y1 = vals
    elif len(vals) == 6:
        x0, y0, _, x1, y1, _ = vals
    else:
        return []
    if not all(math.isfinite(c) for c in (x0, y0, x1, y1)):
        return []
    if (x1 - x0) * (y1 - y0) <= _AREA_MIN or x1 <= x0 or y1 <= y0:
        return []
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


def _caixa_xy_malha(verts_usados: np.ndarray) -> list[list[tuple[float, float]]]:
    x0, y0 = float(verts_usados[:, 0].min()), float(verts_usados[:, 1].min())
    x1, y1 = float(verts_usados[:, 0].max()), float(verts_usados[:, 1].max())
    return _anel_caixa((x0, y0, x1, y1))


def _falha_aneis(item: dict, verts_usados: np.ndarray | None = None) -> list:
    aneis = _anel_caixa(item.get("caixa"))
    if aneis or verts_usados is None:
        return aneis
    return _caixa_xy_malha(verts_usados)


def _casco_convexo_xy(verts_usados: np.ndarray) -> list[list[tuple[float, float]]]:
    pts = verts_usados[:, :2]
    if len(pts) < 3:
        return []
    hull = shapely.convex_hull(shapely.linestrings(pts))
    if hull.is_empty or hull.geom_type != "Polygon" or hull.area <= _AREA_MIN:
        return []
    coords = list(hull.exterior.coords)[:-1]
    return [coords] if len(coords) >= 3 else []


def _secao_cortada(
    verts: np.ndarray,
    tris: np.ndarray,
    zf: float,
    zmin: float,
    zmax: float,
) -> list:
    # Jitter para cima evita vertice exatamente no plano e corta pecas com zmin ~= z_corte.
    z_base = max(zf, zmin)
    passo = min(_JITTER_Z, 0.5 * (zmax - z_base))
    z_plano = z_base + passo
    dz_tris = (verts[:, 2] - z_plano)[tris]
    eps_cp = 1e-12 * max(1.0, abs(z_plano))
    cruzam = (dz_tris.min(axis=1) <= eps_cp) & (dz_tris.max(axis=1) >= -eps_cp)
    tris_corte = tris[cruzam]
    if len(tris_corte) == 0:
        return []
    _, _, segs = cortar_malha_no_plano(verts, tris_corte, z_plano)
    fechados, abertos = aneis_de_segmentos(segs)
    if abertos or not fechados:
        return []
    return fechados


def _aneis_validos(aneis: list) -> bool:
    return bool(aneis) and sum(_area_anel(a) for a in aneis) > _AREA_MIN


def _d_aneis(aneis: list, limites: list[float]) -> str:
    partes = []
    for anel in aneis:
        pts = [(float(p[0]), -float(p[1])) for p in anel]
        if len(pts) < 3:
            continue
        for x, y in pts:
            if x < limites[0]:
                limites[0] = x
            if y < limites[1]:
                limites[1] = y
            if x > limites[2]:
                limites[2] = x
            if y > limites[3]:
                limites[3] = y
        partes.append("M " + " L ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts) + " Z")
    return " ".join(partes)


def _grupo_svg(classe: str, guid: str, papel: str, aneis: list, limites: list[float]) -> str | None:
    d = _d_aneis(aneis, limites)
    if not d:
        return None
    cls_attr = escape(f"{classe} {papel}", quote=True)
    guid_attr = escape(guid, quote=True)
    return f'<g class="{cls_attr}" ifc:guid="{guid_attr}"><path d="{d}" fill-rule="evenodd"/></g>'


def _escrever_atomico(destino, svg: str) -> None:
    caminho = os.fspath(destino)
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    tmp = f"{caminho}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fp:
            fp.write(svg)
        os.replace(tmp, caminho)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def _so_poligonal(geom):
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom if geom.area > _AREA_MIN else None
    if hasattr(geom, "geoms"):
        partes = [
            g
            for g in geom.geoms
            if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty and g.area > _AREA_MIN
        ]
        if not partes:
            return None
        return partes[0] if len(partes) == 1 else shapely.union_all(partes)
    return None


def _pegada_de_aneis(aneis: list):
    """Constroi geometria Shapely da pegada via regra evenodd dos aneis."""
    if not aneis:
        return None
    if len(aneis) == 1:
        anel = aneis[0]
        if len(anel) < 3:
            return None
        p = shapely.Polygon(anel)
        if not p.is_valid:
            p = shapely.make_valid(p)
        return _so_poligonal(p)

    polis = []
    for anel in aneis:
        if len(anel) < 3:
            continue
        p = shapely.Polygon(anel)
        if not p.is_valid:
            p = shapely.make_valid(p)
        p = _so_poligonal(p)
        if p is not None:
            polis.append(p)
    if not polis:
        return None
    if len(polis) == 1:
        return polis[0]
    return _so_poligonal(reduce(shapely.symmetric_difference, polis))


def _classificar_peca(
    item: dict,
    zf: float,
    eps: float,
    moveis_como_caixa: bool,
    limiar_tris: int,
) -> tuple[str, str, list, float | None, bool]:
    """Retorna (categoria_auditoria, papel_svg, aneis, zmax, exata) para uma peca."""
    malha = _validar_malha(item.get("verts"), item.get("tris"))
    if malha is None:
        return "falha", "projection", _falha_aneis(item), None, False

    verts, tris, verts_usados = malha
    zmin = float(verts_usados[:, 2].min())
    zmax = float(verts_usados[:, 2].max())

    if zmin > zf + eps:
        return "acima", "", [], zmax, False

    if zmax > zf + eps:
        aneis = _secao_cortada(verts, tris, zf, zmin, zmax)
        if _aneis_validos(aneis):
            return "cortada", "cut", aneis, zmax, True
        return "falha", "projection", _falha_aneis(item, verts_usados), zmax, False

    if bool(item.get("movel", False)) and moveis_como_caixa:
        aneis = _caixa_xy_malha(verts_usados)
        exata = False
    elif len(tris) <= limiar_tris:
        aneis = silhueta_xy(verts, tris)
        exata = True
    else:
        aneis = _casco_convexo_xy(verts_usados)
        exata = False

    if _aneis_validos(aneis):
        return "vista", "projection", aneis, zmax, exata
    return "falha", "projection", _falha_aneis(item, verts_usados), zmax, False


def _aplicar_oclusao(classificados: list[dict]) -> None:
    """Marca como 'oculta' pecas 'vista' cobertas por oclusores exatos mais altos."""
    ocl_geoms = []
    ocl_zmax = []
    ocl_idx = []
    for idx, reg in enumerate(classificados):
        if reg["exata"] and reg["pegada"] is not None and reg["zmax"] is not None:
            ocl_geoms.append(reg["pegada"])
            ocl_zmax.append(reg["zmax"])
            ocl_idx.append(idx)

    if not ocl_geoms:
        return

    arvore = shapely.STRtree(ocl_geoms)
    for idx, reg in enumerate(classificados):
        if reg["categoria"] != "vista":
            continue
        pegada = reg["pegada"]
        zmax = reg["zmax"]
        if pegada is None or zmax is None:
            continue

        z_min_ocl = zmax + _TOL_Z_OCLUSAO
        candidatas = [
            ocl_geoms[k]
            for k in arvore.query(pegada, predicate="intersects")
            if ocl_idx[k] != idx and ocl_zmax[k] > z_min_ocl
        ]
        if not candidatas:
            continue

        uniao = candidatas[0] if len(candidatas) == 1 else shapely.union_all(candidatas)
        if pegada.difference(uniao).area <= _TOL_AREA_OCLUSAO:
            reg["categoria"] = "oculta"


def gerar_previa_planta(
    pecas,
    z_corte: float,
    destino=None,
    *,
    moveis_como_caixa: bool = False,
    ao_fase=None,
    limiar_tris: int = 2000,
) -> dict:
    """Gera previa SVG provisoria da planta (sem HLR) e auditoria por GUID."""
    zf = float(z_corte)
    if not math.isfinite(zf):
        raise ValueError(f"z_corte invalido: {z_corte!r}")
    eps = 1e-9 * max(1.0, abs(zf))

    if ao_fase is not None:
        ao_fase("previa")

    classificados: list[dict] = []
    for item in pecas:
        guid = str(item["guid"])
        classe = str(item["classe"])
        categoria, papel, aneis, zmax, exata = _classificar_peca(item, zf, eps, moveis_como_caixa, limiar_tris)
        pegada = _pegada_de_aneis(aneis) if (categoria == "vista" or exata) else None
        classificados.append(
            {
                "guid": guid,
                "classe": classe,
                "categoria": categoria,
                "papel": papel,
                "aneis": aneis,
                "zmax": zmax,
                "exata": exata,
                "pegada": pegada,
            }
        )

    _aplicar_oclusao(classificados)

    auditoria = {"cortada": set(), "vista": set(), "oculta": set(), "acima": set(), "falha": set()}
    cat_por_guid: dict[str, str] = {}
    grupos_svg: list[str] = []
    limites = [math.inf, math.inf, -math.inf, -math.inf]

    for reg in classificados:
        guid = reg["guid"]
        cat = reg["categoria"]
        ant = cat_por_guid.get(guid)
        if ant is None or _PRIORIDADE_AUDITORIA[cat] < _PRIORIDADE_AUDITORIA[ant]:
            cat_por_guid[guid] = cat
        if cat in ("acima", "oculta"):
            continue
        grupo = _grupo_svg(reg["classe"], guid, reg["papel"], reg["aneis"], limites)
        if grupo is not None:
            grupos_svg.append(grupo)

    for guid, cat in cat_por_guid.items():
        auditoria[cat].add(guid)

    if math.isfinite(limites[0]):
        vx, vy = limites[0], limites[1]
        vw = max(limites[2] - limites[0], 1e-3)
        vh = max(limites[3] - limites[1], 1e-3)
        view_box = f"{_fmt(vx)} {_fmt(vy)} {_fmt(vw)} {_fmt(vh)}"
    else:
        view_box = "0 0 1 1"

    corpo = "\n".join(grupos_svg)
    svg = (
        f'<svg xmlns="{_NS_SVG}" xmlns:ifc="{_NS_IFC}" data-obim-previa="1" viewBox="{view_box}">'
        + (f"\n{corpo}\n" if corpo else "")
        + "</svg>"
    )

    if destino is not None:
        _escrever_atomico(destino, svg)

    return {"svg": svg, "auditoria": auditoria}
