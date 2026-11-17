# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construcao de aneis a partir de segmentos e recorte de polilinhas fora dos aneis."""
from collections import defaultdict
from dataclasses import dataclass
import math
import numpy as np

_EPS = 1e-12


def _area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]) + x[-1] * y[0] - x[0] * y[-1])


def _ponto_no_anel_arr(
    px: float,
    py: float,
    x1: np.ndarray,
    y1: np.ndarray,
    x2: np.ndarray,
    y2: np.ndarray,
) -> bool:
    cond = (y1 > py) != (y2 > py)
    if not np.any(cond):
        return False
    y1c, y2c = y1[cond], y2[cond]
    x1c, x2c = x1[cond], x2[cond]
    return (int(np.count_nonzero(px < x1c + (py - y1c) * (x2c - x1c) / (y2c - y1c))) & 1) == 1


def _agrupar_nos(pts_all: np.ndarray, tol: float):
    """Agrupa extremidades por distancia < tol com grade 3x3 + union-find e representante min (x,y)."""
    id_map: dict[tuple[float, float], int] = {}
    pts_list: list[tuple[float, float]] = []
    pt_ids: list[int] = []
    for x, y in pts_all.tolist():
        key = (float(x), float(y))
        pid = id_map.get(key)
        if pid is None:
            pid = len(pts_list)
            id_map[key] = pid
            pts_list.append(key)
        pt_ids.append(pid)

    m = len(pts_list)
    if tol > 0.0 and m > 1:
        parent = list(range(m))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (px, py) in enumerate(pts_list):
            grid[(math.floor(px / tol), math.floor(py / tol))].append(i)

        tol2 = tol * tol
        for (cx, cy), ids_a in grid.items():
            na = len(ids_a)
            if na > 1:
                for p in range(na):
                    i = ids_a[p]
                    xi, yi = pts_list[i]
                    for q in range(p + 1, na):
                        j = ids_a[q]
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            xj, yj = pts_list[j]
                            dx, dy = xi - xj, yi - yj
                            if dx * dx + dy * dy < tol2:
                                parent[rj] = ri
            for nkey in ((cx + 1, cy - 1), (cx + 1, cy), (cx + 1, cy + 1), (cx, cy + 1)):
                ids_b = grid.get(nkey)
                if ids_b is None:
                    continue
                for i in ids_a:
                    xi, yi = pts_list[i]
                    for j in ids_b:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            xj, yj = pts_list[j]
                            dx, dy = xi - xj, yi - yj
                            if dx * dx + dy * dy < tol2:
                                parent[rj] = ri

        roots = [find(i) for i in range(m)]
        cluster_min: dict[int, tuple[float, float]] = {}
        for i, r in enumerate(roots):
            pt = pts_list[i]
            cur = cluster_min.get(r)
            if cur is None or pt < cur:
                cluster_min[r] = pt

        roots_ord = sorted(cluster_min, key=cluster_min.__getitem__)
        root_to_nid = {r: idx for idx, r in enumerate(roots_ord)}
        coords = [cluster_min[r] for r in roots_ord]
        mapped_ids = [root_to_nid[roots[pid]] for pid in pt_ids]
        return coords, mapped_ids

    ord_idx = sorted(range(m), key=pts_list.__getitem__)
    old_to_new = [0] * m
    for new_id, old_id in enumerate(ord_idx):
        old_to_new[old_id] = new_id
    coords = [pts_list[i] for i in ord_idx]
    mapped_ids = [old_to_new[pid] for pid in pt_ids]
    return coords, mapped_ids


def aneis_de_segmentos(segs, tol: float = 1e-6):
    """Costura segmentos (k,4) em (fechados, abertos) com orientacao e inicio deterministicos."""
    arr = np.asarray(segs, dtype=float)
    if arr.size == 0:
        return [], []
    arr = arr.reshape(-1, 4)

    coords, mapped_ids = _agrupar_nos(arr.reshape(-1, 2), tol)
    pares = []
    for k in range(len(arr)):
        u, v = mapped_ids[2 * k], mapped_ids[2 * k + 1]
        if u != v:
            pares.append((u, v))
    if not pares:
        return [], []

    adj: list[list[tuple[int, int]]] = [[] for _ in coords]
    for eid, (u, v) in enumerate(pares):
        adj[u].append((v, eid))
        adj[v].append((u, eid))
    for lst in adj:
        lst.sort(key=lambda item: item[0])
    usada, deg = [False] * len(pares), [len(lst) for lst in adj]

    def caminhar(inicio: int):
        cam, atual = [inicio], inicio
        while (prox := next(((v, eid) for v, eid in adj[atual] if not usada[eid]), None)) is not None:
            v, eid = prox
            usada[eid], deg[atual], deg[v] = True, deg[atual] - 1, deg[v] - 1
            cam.append(v)
            atual = v
            if atual == inicio:
                break
        return cam

    fechados_ids, abertos_ids = [], []
    for cond in (lambda d: d == 1, lambda d: d % 2 == 1, lambda d: d > 0):
        for u in range(len(coords)):
            while cond(deg[u]):
                cam = caminhar(u)
                if cam[0] == cam[-1] and len(cam) >= 4:
                    fechados_ids.append(cam[:-1])
                elif len(cam) >= 2:
                    abertos_ids.append(cam)

    fechados = [np.array([coords[i] for i in cam], dtype=float) for cam in fechados_ids]
    orientados = []
    if fechados:
        n_rings = len(fechados)
        areas = np.array([_area(r) for r in fechados], dtype=float)
        abs_areas = np.abs(areas)
        bboxes = np.empty((n_rings, 4), dtype=float)
        edges_xy = []
        for i, r in enumerate(fechados):
            rx, ry = r[:, 0], r[:, 1]
            bboxes[i] = (rx.min(), ry.min(), rx.max(), ry.max())
            edges_xy.append((rx, ry, np.roll(rx, -1), np.roll(ry, -1)))

        for i, r in enumerate(fechados):
            px, py = 0.5 * (float(r[0, 0]) + float(r[1, 0])), 0.5 * (float(r[0, 1]) + float(r[1, 1]))
            cand = np.flatnonzero(
                (abs_areas > abs_areas[i])
                & (bboxes[:, 0] <= bboxes[i, 0] + _EPS)
                & (bboxes[:, 2] >= bboxes[i, 2] - _EPS)
                & (bboxes[:, 1] <= bboxes[i, 1] + _EPS)
                & (bboxes[:, 3] >= bboxes[i, 3] - _EPS)
            )
            cont = 0
            for j in cand:
                if _ponto_no_anel_arr(px, py, *edges_xy[j]):
                    cont += 1
            area_signed = areas[i]
            if (cont % 2 == 1 and area_signed > 0.0) or (cont % 2 == 0 and area_signed < 0.0):
                r = r[::-1].copy()
                area_signed = -area_signed
            idx = min(range(len(r)), key=lambda k: (float(r[k, 0]), float(r[k, 1])))
            orientados.append((np.roll(r, -idx, axis=0), area_signed))
        orientados.sort(key=lambda item: (float(item[0][0, 0]), float(item[0][0, 1]), item[1]))
        orientados_out = [item[0] for item in orientados]
    else:
        orientados_out = []

    abertos_raw = []
    for cam in abertos_ids:
        pts = np.array([coords[i] for i in cam], dtype=float)
        if (float(pts[-1, 0]), float(pts[-1, 1])) < (float(pts[0, 0]), float(pts[0, 1])):
            pts = pts[::-1].copy()
        abertos_raw.append(pts)
    abertos = sorted(
        abertos_raw,
        key=lambda p: (float(p[0, 0]), float(p[0, 1]), float(p[-1, 0]), float(p[-1, 1]), len(p)),
    )
    return orientados_out, abertos
