# SPDX-License-Identifier: AGPL-3.0-or-later
"""Previa provisoria da planta sem HLR (secao exata, silhueta/casco e caixas de falha)."""
from __future__ import annotations

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


def _validar_malha(verts, tris) -> tuple[np.ndarray, np.ndarray] | None:
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
    if not np.isfinite(v).all():
        return None
    return v, t


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


def _caixa_xy_malha(verts: np.ndarray) -> list[list[tuple[float, float]]]:
    x0, y0 = float(verts[:, 0].min()), float(verts[:, 1].min())
    x1, y1 = float(verts[:, 0].max()), float(verts[:, 1].max())
    return _anel_caixa((x0, y0, x1, y1))


def _casco_convexo_xy(verts: np.ndarray, tris: np.ndarray) -> list[list[tuple[float, float]]]:
    pts = verts[np.unique(tris), :2]
    if len(pts) < 3:
        return []
    hull = shapely.convex_hull(shapely.multipoints(pts))
    if hull.is_empty or hull.geom_type != "Polygon" or hull.area <= _AREA_MIN:
        return []
    coords = list(hull.exterior.coords)[:-1]
    return [coords] if len(coords) >= 3 else []


def _secao_cortada(verts: np.ndarray, tris: np.ndarray, zf: float, zmax: float) -> list:
    # Jitter para cima evita vertice exatamente no plano e corta pecas com zmin == z_corte.
    passo = min(_JITTER_Z, 0.5 * (zmax - zf))
    z_plano = zf + passo
    _, _, segs = cortar_malha_no_plano(verts, tris, z_plano)
    fechados, abertos = aneis_de_segmentos(segs)
    if abertos or not fechados:
        return []
    area_total = sum(_area_anel(anel) for anel in fechados)
    if area_total <= _AREA_MIN:
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


def _classificar_peca(
    item: dict,
    zf: float,
    moveis_como_caixa: bool,
    limiar_tris: int,
) -> tuple[str, str, list]:
    """Retorna (categoria_auditoria, papel_svg, aneis) para uma peca."""
    malha = _validar_malha(item.get("verts"), item.get("tris"))
    if malha is None:
        return "falha", "projection", _anel_caixa(item.get("caixa"))

    verts, tris = malha
    zmin = float(verts[:, 2].min())
    zmax = float(verts[:, 2].max())

    if zmin > zf:
        return "acima", "", []

    if zmin <= zf < zmax:
        aneis = _secao_cortada(verts, tris, zf, zmax)
        if _aneis_validos(aneis):
            return "cortada", "cut", aneis
        return "falha", "projection", _anel_caixa(item.get("caixa"))

    if bool(item.get("movel", False)) and moveis_como_caixa:
        aneis = _caixa_xy_malha(verts)
    elif len(tris) <= limiar_tris:
        aneis = silhueta_xy(verts, tris)
    else:
        aneis = _casco_convexo_xy(verts, tris)

    if _aneis_validos(aneis):
        return "vista", "projection", aneis
    return "falha", "projection", _anel_caixa(item.get("caixa"))


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

    if ao_fase is not None:
        ao_fase("previa")

    auditoria = {"cortada": set(), "vista": set(), "acima": set(), "falha": set()}
    grupos_svg: list[str] = []
    limites = [math.inf, math.inf, -math.inf, -math.inf]

    for item in pecas:
        guid = str(item["guid"])
        classe = str(item["classe"])
        categoria, papel, aneis = _classificar_peca(item, zf, moveis_como_caixa, limiar_tris)
        auditoria[categoria].add(guid)
        if categoria == "acima":
            continue
        grupo = _grupo_svg(classe, guid, papel, aneis, limites)
        if grupo is not None:
            grupos_svg.append(grupo)

    if math.isfinite(limites[0]):
        vx, vy = limites[0], limites[1]
        vw = max(limites[2] - limites[0], 1e-3)
        vh = max(limites[3] - limites[1], 1e-3)
        view_box = f"{_fmt(vx)} {_fmt(vy)} {_fmt(vw)} {_fmt(vh)}"
    else:
        view_box = "0 0 1 1"

    corpo = "\n".join(grupos_svg)
    svg = (
        f'<svg xmlns="{_NS_SVG}" xmlns:ifc="{_NS_IFC}" viewBox="{view_box}">'
        + (f"\n{corpo}\n" if corpo else "")
        + "</svg>"
    )

    if destino is not None:
        _escrever_atomico(destino, svg)

    return {"svg": svg, "auditoria": auditoria}
