# SPDX-License-Identifier: AGPL-3.0-or-later
"""Leitura direta de malhas IFC (FaceSet) em coordenadas do mundo, sem o núcleo geométrico."""
from __future__ import annotations

import ifcopenshell.util.placement as _placement
import ifcopenshell.util.representation as _rep
import numpy as np
import shapely

_PROF_MAX = 32


class _Vetor(np.ndarray):
    """Array 1-D compatível com verificações booleanas (`if geo.verts:`)."""

    def __new__(cls, dados, dtype):
        return np.ascontiguousarray(dados, dtype=dtype).ravel().view(cls)

    def __bool__(self) -> bool:
        return self.size > 0


class _GeometriaDireta:
    """Geometria compatível com `.geometry` do iterador ifcopenshell."""

    __slots__ = ("verts", "faces")

    def __init__(self, verts: _Vetor, faces: _Vetor) -> None:
        self.verts = verts
        self.faces = faces


class FormaDireta:
    """Forma compatível com o retorno de `ifcopenshell.geom.iterator.get()`."""

    __slots__ = ("id", "geometry")

    def __init__(self, id_step: int, verts, tris) -> None:
        self.id = int(id_step)
        self.geometry = _GeometriaDireta(_Vetor(verts, np.float64), _Vetor(tris, np.int64))


def _representacoes_corpo(el) -> list:
    if not el.is_a("IfcProduct") or getattr(el, "Representation", None) is None:
        return []
    todas = list(_rep.get_representations_iter(el))
    corpo = [r for r in todas if _rep.is_representation_of_context(r, "Model", "Body")]
    if corpo:
        return corpo
    return [
        r
        for r in todas
        if _rep.is_representation_of_context(r, "Model")
        and getattr(r, "RepresentationIdentifier", None) == "Body"
    ]


def _pontos_faceset(item) -> np.ndarray | None:
    coords = getattr(item, "Coordinates", None)
    if coords is None or not coords.is_a("IfcCartesianPointList3D"):
        return None
    pts = np.asarray(coords.CoordList, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[0] == 0 or pts.shape[1] != 3 or not np.isfinite(pts).all():
        return None
    pn = getattr(item, "PnIndex", None)
    if pn:
        idx = np.asarray(pn, dtype=np.int64) - 1
        if idx.ndim != 1 or idx.size == 0 or idx.min() < 0 or idx.max() >= len(pts):
            return None
        pts = pts[idx]
    return pts


def _normal_newell(p3: np.ndarray) -> np.ndarray:
    q = p3 - p3[0]
    return np.cross(q, np.roll(q, -1, axis=0)).sum(axis=0)


def _triangulos_poligono_cdt(pts: np.ndarray, outer: list[int], inners: list[list[int]]) -> list[tuple[int, int, int]] | None:
    p_out = pts[outer]
    n = _normal_newell(p_out)
    norm_n = float(np.linalg.norm(n))
    if norm_n <= 1e-15:
        return None
    n_hat = n / norm_n
    ref = np.array([1.0, 0.0, 0.0]) if abs(n_hat[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(ref, n_hat)
    u /= np.linalg.norm(u)
    v = np.cross(n_hat, u)
    uv = np.column_stack((u, v))

    todos = list(outer)
    for furo in inners:
        todos.extend(furo)
    xy = (pts[todos] - p_out[0]) @ uv

    mapa: dict[tuple[float, float], int] = {}
    for idx, (x, y) in zip(todos, xy.tolist()):
        chave = (x, y)
        ant = mapa.get(chave)
        if ant is not None and ant != idx and not np.allclose(pts[ant], pts[idx], atol=1e-12):
            return None
        mapa[chave] = idx

    n_ext = len(outer)
    shell_2d = xy[:n_ext]
    holes_2d, pos = [], n_ext
    for furo in inners:
        holes_2d.append(xy[pos : pos + len(furo)])
        pos += len(furo)

    poly = shapely.Polygon(shell_2d, holes_2d)
    if poly.is_empty or poly.area <= 1e-15 or not poly.is_valid:
        return None
    cdt = shapely.constrained_delaunay_triangles(poly)
    if cdt.is_empty or len(cdt.geoms) == 0 or abs(cdt.area - poly.area) > 1e-5 * max(1.0, poly.area):
        return None

    saida: list[tuple[int, int, int]] = []
    for geom in cdt.geoms:
        cs = list(geom.exterior.coords)
        if len(cs) != 4:
            return None
        i0 = mapa.get((cs[0][0], cs[0][1]))
        i1 = mapa.get((cs[1][0], cs[1][1]))
        i2 = mapa.get((cs[2][0], cs[2][1]))
        if i0 is None or i1 is None or i2 is None:
            return None
        saida.append((i0, i1, i2))
    return saida


def _triangulos_poligonal_geral(pts: np.ndarray, outer: list[int], inners: list[list[int]]) -> list[tuple[int, int, int]] | None:
    if not inners:
        p_out = pts[outer]
        n = _normal_newell(p_out)
        norm_n = float(np.linalg.norm(n))
        if norm_n > 1e-15:
            n_hat = n / norm_n
            arestas = np.roll(p_out, -1, axis=0) - p_out
            giros = np.einsum("ij,j->i", np.cross(np.roll(arestas, 1, axis=0), arestas), n_hat)
            if np.all(giros > 0):
                i0 = outer[0]
                return [(i0, outer[k], outer[k + 1]) for k in range(1, len(outer) - 1)]
    return _triangulos_poligono_cdt(pts, outer, inners)


def _extrair_faceset_triangulado(item) -> tuple[np.ndarray, np.ndarray] | None:
    pts = _pontos_faceset(item)
    if pts is None:
        return None
    ci = getattr(item, "CoordIndex", None)
    if not ci:
        return None
    tris = np.asarray(ci, dtype=np.int64) - 1
    if tris.ndim != 2 or tris.shape[0] == 0 or tris.shape[1] != 3:
        return None
    if tris.min() < 0 or tris.max() >= len(pts):
        return None
    return pts, tris


def _extrair_faceset_poligonal(item) -> tuple[np.ndarray, np.ndarray] | None:
    pts = _pontos_faceset(item)
    if pts is None:
        return None
    faces = getattr(item, "Faces", None)
    if not faces:
        return None

    n_pts = len(pts)
    tris3, quads4 = [], []
    outros: list[tuple[list[int], list[list[int]]]] = []

    for fc in faces:
        n_attrs = len(fc)
        outer = fc[0]
        if n_attrs == 1:
            inners = None
        elif fc.is_a("IfcIndexedPolygonalFaceWithVoids"):
            inners = fc[1] or None
        else:
            return None

        if not outer or len(outer) < 3:
            return None
        if inners is None:
            k = len(outer)
            if k == 3:
                tris3.append(outer)
            elif k == 4:
                quads4.append(outer)
            else:
                o0 = [int(i) - 1 for i in outer]
                if min(o0) < 0 or max(o0) >= n_pts:
                    return None
                outros.append((o0, []))
        else:
            o0 = [int(i) - 1 for i in outer]
            if min(o0) < 0 or max(o0) >= n_pts:
                return None
            furos0 = []
            for furo in inners:
                if not furo or len(furo) < 3:
                    return None
                f0 = [int(i) - 1 for i in furo]
                if min(f0) < 0 or max(f0) >= n_pts:
                    return None
                furos0.append(f0)
            outros.append((o0, furos0))

    blocos: list[np.ndarray] = []
    if tris3:
        t3 = np.asarray(tris3, dtype=np.int64) - 1
        if t3.min() < 0 or t3.max() >= n_pts:
            return None
        blocos.append(t3)

    if quads4:
        q = np.asarray(quads4, dtype=np.int64) - 1
        if q.min() < 0 or q.max() >= n_pts:
            return None
        p = pts[q]
        e0, e1, e2, e3 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 1], p[:, 3] - p[:, 2], p[:, 0] - p[:, 3]
        c0, c1, c2, c3 = np.cross(e3, e0), np.cross(e0, e1), np.cross(e1, e2), np.cross(e2, e3)
        n = c0 + c1 + c2 + c3
        conv = (
            (np.einsum("ij,ij->i", n, n) > 1e-24)
            & (np.einsum("ij,ij->i", c0, n) > 0)
            & (np.einsum("ij,ij->i", c1, n) > 0)
            & (np.einsum("ij,ij->i", c2, n) > 0)
            & (np.einsum("ij,ij->i", c3, n) > 0)
        )
        if conv.any():
            qc = q[conv]
            blocos.append(qc[:, [0, 1, 2]])
            blocos.append(qc[:, [0, 2, 3]])
        if not conv.all():
            for row in q[~conv].tolist():
                outros.append((row, []))

    if outros:
        extra: list[tuple[int, int, int]] = []
        for outer0, inners0 in outros:
            tri_f = _triangulos_poligonal_geral(pts, outer0, inners0)
            if tri_f is None:
                return None
            extra.extend(tri_f)
        if extra:
            blocos.append(np.asarray(extra, dtype=np.int64))

    if not blocos:
        return None
    tris = blocos[0] if len(blocos) == 1 else np.vstack(blocos)
    return pts, tris


def _coletar_item(item, matriz: np.ndarray, escala: float, partes: list[tuple[np.ndarray, np.ndarray]], prof: int = 0) -> bool:
    if item is None or prof > _PROF_MAX:
        return False
    if item.is_a("IfcTriangulatedFaceSet"):
        ext = _extrair_faceset_triangulado(item)
    elif item.is_a("IfcPolygonalFaceSet"):
        ext = _extrair_faceset_poligonal(item)
    elif item.is_a("IfcMappedItem"):
        m_map = _placement.get_mappeditem_transformation(item)
        if m_map is None or m_map.shape != (4, 4) or not np.isfinite(m_map).all():
            return False
        src = getattr(item, "MappingSource", None)
        rep = getattr(src, "MappedRepresentation", None)
        itens = getattr(rep, "Items", None) if rep is not None else None
        if not itens:
            return False
        m_sub = matriz @ m_map
        for sub in itens:
            if not _coletar_item(sub, m_sub, escala, partes, prof + 1):
                return False
        return True
    else:
        return False

    if ext is None:
        return False
    pts, tris = ext
    verts_m = (pts @ matriz[:3, :3].T + matriz[:3, 3]) * escala
    partes.append((verts_m, tris))
    return True


def malha_mundo(el, escala: float = 1.0) -> tuple[np.ndarray, np.ndarray] | None:
    """Lê malha direta `(verts (n,3) float em metros, tris (m,3) int)` ou None se não suportada."""
    try:
        if el is None or el.is_a("IfcOpeningElement") or getattr(el, "HasOpenings", None):
            return None
        reps = _representacoes_corpo(el)
        if not reps:
            return None
        m_place = _placement.get_local_placement(getattr(el, "ObjectPlacement", None))
        if m_place is None or m_place.shape != (4, 4) or not np.isfinite(m_place).all():
            return None
        esc = float(escala)
        partes: list[tuple[np.ndarray, np.ndarray]] = []
        for rep in reps:
            itens = getattr(rep, "Items", None)
            if not itens:
                return None
            for item in itens:
                if not _coletar_item(item, m_place, esc, partes):
                    return None
        if not partes:
            return None
        if len(partes) == 1:
            verts, tris = partes[0]
        else:
            verts_all, tris_all, offset = [], [], 0
            for v_p, t_p in partes:
                verts_all.append(v_p)
                tris_all.append(t_p + offset)
                offset += len(v_p)
            verts = np.vstack(verts_all)
            tris = np.vstack(tris_all)
        if len(verts) == 0 or len(tris) == 0:
            return None
        return np.ascontiguousarray(verts, dtype=np.float64), np.ascontiguousarray(tris, dtype=np.int64)
    except Exception:
        return None
