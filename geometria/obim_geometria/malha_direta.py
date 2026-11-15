# SPDX-License-Identifier: AGPL-3.0-or-later
"""Leitura direta de malhas IFC (FaceSet) em coordenadas do mundo, sem o núcleo geométrico."""
from __future__ import annotations

import threading

import ifcopenshell.util.placement as _placement
import ifcopenshell.util.representation as _rep
import numpy as np
import shapely

_PROF_MAX = 32
_AUSENTE = object()
_CACHE_LOCK = threading.Lock()
_EM_CURSO: dict[tuple[int, int], threading.Event] = {}
_DT_CHAVE = np.dtype([("p", np.int64), ("x", np.float64), ("y", np.float64)])


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


def _cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.stack(
        (
            a[..., 1] * b[..., 2] - a[..., 2] * b[..., 1],
            a[..., 2] * b[..., 0] - a[..., 0] * b[..., 2],
            a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0],
        ),
        axis=-1,
    )


def _normais_newell_lote(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    q = p - p[:, :1, :]
    qa, qb = q[:, 1:-1, :], q[:, 2:, :]
    nx = (qa[..., 1] * qb[..., 2] - qa[..., 2] * qb[..., 1]).sum(axis=1)
    ny = (qa[..., 2] * qb[..., 0] - qa[..., 0] * qb[..., 2]).sum(axis=1)
    nz = (qa[..., 0] * qb[..., 1] - qa[..., 1] * qb[..., 0]).sum(axis=1)
    return np.column_stack((nx, ny, nz)), np.sqrt(nx * nx + ny * ny + nz * nz)


def _base_plano_lote(n_hat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ref = np.zeros_like(n_hat)
    use_x = np.abs(n_hat[:, 0]) < 0.9
    ref[use_x, 0] = 1.0
    ref[~use_x, 1] = 1.0
    u = _cross3(ref, n_hat)
    u /= np.sqrt((u * u).sum(axis=1))[:, None]
    return u, _cross3(n_hat, u)


def _triangulos_poligono_cdt(pts: np.ndarray, outer: list[int], inners: list[list[int]]) -> list[tuple[int, int, int]] | None:
    p_out = pts[outer]
    n_vec, norm = _normais_newell_lote(p_out[None, :, :])
    norm_n = float(norm[0])
    if norm_n <= 1e-15:
        return None
    u, v = _base_plano_lote(n_vec / norm_n)
    uv = np.column_stack((u[0], v[0]))

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


def _mapear_triangulos_lote(
    pts: np.ndarray,
    grupos_nc: list[tuple[np.ndarray, np.ndarray]],
    part_poly: np.ndarray,
    coords: np.ndarray,
    sucesso: np.ndarray,
) -> tuple[np.ndarray | None, np.ndarray]:
    in_p_l, in_xy_l, in_idx_l = [], [], []
    off = 0
    for idx_g, xy_g in grupos_nc:
        m_g, n_g = idx_g.shape
        in_p_l.append(np.repeat(np.arange(off, off + m_g, dtype=np.int64), n_g))
        in_xy_l.append(xy_g.reshape(-1, 2))
        in_idx_l.append(idx_g.ravel())
        off += m_g

    in_p = in_p_l[0] if len(in_p_l) == 1 else np.concatenate(in_p_l)
    in_xy = in_xy_l[0] if len(in_xy_l) == 1 else np.concatenate(in_xy_l)
    in_idx = in_idx_l[0] if len(in_idx_l) == 1 else np.concatenate(in_idx_l)

    keys = np.empty(len(in_p), dtype=_DT_CHAVE)
    keys["p"] = in_p
    keys["x"] = in_xy[:, 0] + 0.0
    keys["y"] = in_xy[:, 1] + 0.0
    order = np.argsort(keys, kind="stable")
    keys_s = keys[order]
    idx_s = in_idx[order]

    dup = keys_s[1:] == keys_s[:-1]
    if dup.any():
        d = np.flatnonzero(dup)
        a, b = idx_s[d], idx_s[d + 1]
        diff = a != b
        if diff.any():
            da = d[diff]
            pa, pb = pts[a[diff]], pts[b[diff]]
            bad = ~np.all(np.abs(pa - pb) <= 1e-12 + 1e-5 * np.abs(pb), axis=1)
            if bad.any():
                sucesso[keys_s["p"][da[bad]]] = False

    tri_xy = coords.reshape(len(part_poly), 4, 2)[:, :3, :].reshape(-1, 2)
    q_keys = np.empty(len(tri_xy), dtype=_DT_CHAVE)
    q_keys["p"] = np.repeat(part_poly, 3)
    q_keys["x"] = tri_xy[:, 0] + 0.0
    q_keys["y"] = tri_xy[:, 1] + 0.0

    pos = np.searchsorted(keys_s, q_keys)
    pos_clip = np.minimum(pos, len(keys_s) - 1)
    found = (pos < len(keys_s)) & (keys_s[pos_clip] == q_keys)
    if not found.all():
        sucesso[part_poly[np.flatnonzero(~found) // 3]] = False

    tri_ok = sucesso[part_poly]
    if not tri_ok.any():
        return None, sucesso
    if tri_ok.all():
        return idx_s[pos].reshape(-1, 3), sucesso
    return idx_s[pos[np.repeat(tri_ok, 3)]].reshape(-1, 3), sucesso


def _triangulos_cdt_lote(
    pts: np.ndarray,
    grupos_nc: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray | None, np.ndarray]:
    polys_l = [shapely.polygons(xy) for _, xy in grupos_nc]
    polys = polys_l[0] if len(polys_l) == 1 else np.concatenate(polys_l)
    areas = shapely.area(polys)
    sucesso = (~shapely.is_empty(polys)) & (areas > 1e-15) & shapely.is_valid(polys)
    ok_idx = np.flatnonzero(sucesso)
    if not len(ok_idx):
        return None, sucesso

    cdt = shapely.constrained_delaunay_triangles(polys[ok_idx])
    ok_cdt = (~shapely.is_empty(cdt)) & (
        np.abs(shapely.area(cdt) - areas[ok_idx]) <= 1e-5 * np.maximum(1.0, areas[ok_idx])
    )
    if not ok_cdt.all():
        sucesso[ok_idx[~ok_cdt]] = False
    parts, part_poly_sub = shapely.get_parts(cdt, return_index=True)
    if not len(parts):
        return None, np.zeros_like(sucesso)

    part_poly = ok_idx[part_poly_sub]
    coords, coord_part = shapely.get_coordinates(parts, return_index=True)
    v_per_part = np.bincount(coord_part, minlength=len(parts))
    bad_part = (~ok_cdt[part_poly_sub]) | (v_per_part != 4)
    if bad_part.any():
        sucesso[part_poly[bad_part]] = False
        keep = ~bad_part
        parts = parts[keep]
        part_poly = part_poly[keep]
        if not len(parts):
            return None, np.zeros_like(sucesso)
        coords, _ = shapely.get_coordinates(parts, return_index=True)

    sucesso &= np.bincount(part_poly, minlength=len(sucesso)) > 0
    return _mapear_triangulos_lote(pts, grupos_nc, part_poly, coords, sucesso)


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
    por_n: dict[int, list] = {}
    com_furos: list[tuple[list[int], list[list[int]]]] = []

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
            por_n.setdefault(len(outer), []).append(outer)
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
            com_furos.append((o0, furos0))

    blocos: list[np.ndarray] = []
    grupos_nc: list[tuple[np.ndarray, np.ndarray]] = []
    for n, lista in por_n.items():
        idx_n = np.asarray(lista, dtype=np.int64) - 1
        if idx_n.min() < 0 or idx_n.max() >= n_pts:
            return None
        if n == 3:
            blocos.append(idx_n)
            continue

        p = pts[idx_n]
        n_vec, norm = _normais_newell_lote(p)
        if not (norm > 1e-15).all():
            return None
        n_hat = n_vec / norm[:, None]

        arestas = np.empty_like(p)
        arestas[:, :-1, :] = p[:, 1:, :] - p[:, :-1, :]
        arestas[:, -1, :] = p[:, 0, :] - p[:, -1, :]
        prev_ar = np.empty_like(arestas)
        prev_ar[:, 1:, :] = arestas[:, :-1, :]
        prev_ar[:, 0, :] = arestas[:, -1, :]
        giros = (_cross3(prev_ar, arestas) * n_hat[:, None, :]).sum(axis=2)
        conv = (giros > 0).all(axis=1)

        if conv.any():
            t_idx = np.column_stack(
                (np.zeros(n - 2, dtype=np.int64), np.arange(1, n - 1), np.arange(2, n))
            )
            blocos.append(idx_n[conv][:, t_idx].reshape(-1, 3))
        if not conv.all():
            nc = ~conv
            p_nc = p[nc]
            u, v = _base_plano_lote(n_hat[nc])
            p_rel = p_nc - p_nc[:, :1, :]
            xy = np.stack(
                ((p_rel * u[:, None, :]).sum(axis=2), (p_rel * v[:, None, :]).sum(axis=2)),
                axis=-1,
            )
            grupos_nc.append((idx_n[nc], xy))

    if grupos_nc:
        tris_cdt, sucesso = _triangulos_cdt_lote(pts, grupos_nc)
        if tris_cdt is not None and len(tris_cdt):
            blocos.append(tris_cdt)
        if not sucesso.all():
            falhas_idx = np.flatnonzero(~sucesso)
            off, f_pos = 0, 0
            for idx_g, _ in grupos_nc:
                fim = off + len(idx_g)
                while f_pos < len(falhas_idx) and falhas_idx[f_pos] < fim:
                    com_furos.append((idx_g[falhas_idx[f_pos] - off].tolist(), []))
                    f_pos += 1
                off = fim

    if com_furos:
        extra: list[tuple[int, int, int]] = []
        for outer0, inners0 in com_furos:
            tri_f = _triangulos_poligono_cdt(pts, outer0, inners0)
            if tri_f is None:
                return None
            extra.extend(tri_f)
        if extra:
            blocos.append(np.asarray(extra, dtype=np.int64))

    if not blocos:
        return None
    tris = blocos[0] if len(blocos) == 1 else np.vstack(blocos)
    return pts, tris


def _extrair_fonte_local(item) -> tuple[np.ndarray, np.ndarray] | None:
    if item.is_a("IfcTriangulatedFaceSet"):
        return _extrair_faceset_triangulado(item)
    return _extrair_faceset_poligonal(item)


def _obter_fonte_local(item, cache: dict | None) -> tuple[np.ndarray, np.ndarray] | None:
    if cache is None:
        return _extrair_fonte_local(item)
    chave = int(item.id())
    chave_curso = (id(cache), chave)
    while True:
        with _CACHE_LOCK:
            val = cache.get(chave, _AUSENTE)
            if val is not _AUSENTE:
                return val
            ev_espera = _EM_CURSO.get(chave_curso)
            if ev_espera is None:
                ev_proprio = threading.Event()
                _EM_CURSO[chave_curso] = ev_proprio
                break
        ev_espera.wait()
    try:
        ext = _extrair_fonte_local(item)
        if ext is not None:
            pts, tris = ext
            pts = np.ascontiguousarray(pts, dtype=np.float64)
            tris = np.ascontiguousarray(tris, dtype=np.int64)
            pts.setflags(write=False)
            tris.setflags(write=False)
            ext = (pts, tris)
        with _CACHE_LOCK:
            existente = cache.get(chave, _AUSENTE)
            if existente is _AUSENTE:
                cache[chave] = ext
            else:
                ext = existente
    finally:
        with _CACHE_LOCK:
            _EM_CURSO.pop(chave_curso, None)
        ev_proprio.set()
    return ext


def _coletar_item(
    item,
    matriz: np.ndarray,
    escala: float,
    partes: list[tuple[np.ndarray, np.ndarray]],
    cache: dict | None = None,
    prof: int = 0,
) -> bool:
    if item is None or prof > _PROF_MAX:
        return False
    if item.is_a("IfcTriangulatedFaceSet") or item.is_a("IfcPolygonalFaceSet"):
        ext = _obter_fonte_local(item, cache)
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
            if not _coletar_item(sub, m_sub, escala, partes, cache, prof + 1):
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


def malha_mundo(el, escala: float = 1.0, cache: dict | None = None) -> tuple[np.ndarray, np.ndarray] | None:
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
                if not _coletar_item(item, m_place, esc, partes, cache):
                    return None
        if not partes:
            return None
        if len(partes) == 1:
            verts, tris = partes[0]
            if not tris.flags.writeable:
                tris = tris.copy()
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
