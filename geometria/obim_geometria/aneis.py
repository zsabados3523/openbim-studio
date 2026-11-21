# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construcao de aneis a partir de segmentos e recorte de polilinhas fora dos aneis."""
from collections import defaultdict
from dataclasses import dataclass
import math
import numpy as np

_EPS = 1e-12
_FP_EPS = float(np.finfo(float).eps)
_TOL_BORDA_MAX = 1e-8


def _area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]) + x[-1] * y[0] - x[0] * y[-1])


def _ponto_interior(r: np.ndarray, area_signed: float) -> tuple[float, float]:
    """Retorna ponto estritamente interior de um anel simples via orelha valida (Two-Ears)."""
    m = len(r)
    x0, y0 = float(r[0, 0]), float(r[0, 1])
    if m == 3:
        return (
            x0 + (float(r[1, 0]) - x0 + float(r[2, 0]) - x0) / 3.0,
            y0 + (float(r[1, 1]) - y0 + float(r[2, 1]) - y0) / 3.0,
        )

    pts = [(float(px) - x0, float(py) - y0) for px, py in r.tolist()]
    orient = 1.0 if area_signed >= 0.0 else -1.0
    best_abs_cross = -1.0
    best_pt: tuple[float, float] | None = None

    for curr in range(m):
        prev_idx = curr - 1 if curr > 0 else m - 1
        next_idx = curr + 1 if curr + 1 < m else 0
        ax, ay = pts[prev_idx]
        bx, by = pts[curr]
        cx, cy = pts[next_idx]
        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if cross * orient <= 0.0:
            continue

        minx = ax if ax < bx else bx
        if cx < minx:
            minx = cx
        maxx = ax if ax > bx else bx
        if cx > maxx:
            maxx = cx
        miny = ay if ay < by else by
        if cy < miny:
            miny = cy
        maxy = ay if ay > by else by
        if cy > maxy:
            maxy = cy

        e1x, e1y = bx - ax, by - ay
        e2x, e2y = cx - bx, cy - by
        e3x, e3y = ax - cx, ay - cy
        valida = True
        for k, (px, py) in enumerate(pts):
            if k == prev_idx or k == curr or k == next_idx:
                continue
            if minx <= px <= maxx and miny <= py <= maxy:
                if (
                    (e1x * (py - ay) - e1y * (px - ax)) * orient >= 0.0
                    and (e2x * (py - by) - e2y * (px - bx)) * orient >= 0.0
                    and (e3x * (py - cy) - e3y * (px - cx)) * orient >= 0.0
                ):
                    valida = False
                    break
        if valida:
            abs_cross = abs(cross)
            if m > 64:
                return x0 + (ax + bx + cx) / 3.0, y0 + (ay + by + cy) / 3.0
            if abs_cross > best_abs_cross:
                best_abs_cross = abs_cross
                best_pt = (x0 + (ax + bx + cx) / 3.0, y0 + (ay + by + cy) / 3.0)

    if best_pt is not None:
        return best_pt

    ys = sorted({py for _, py in pts})
    if len(ys) >= 2:
        k_best = max(range(len(ys) - 1), key=lambda k: ys[k + 1] - ys[k])
        y_mid = 0.5 * (ys[k_best] + ys[k_best + 1])
        xs: list[float] = []
        for idx in range(m):
            ux, uy = pts[idx]
            vx, vy = pts[(idx + 1) % m]
            if (uy > y_mid) != (vy > y_mid):
                xs.append(ux + (y_mid - uy) * (vx - ux) / (vy - uy))
        if len(xs) >= 2:
            xs.sort()
            t_best = max(range(0, len(xs) - 1, 2), key=lambda t: xs[t + 1] - xs[t])
            return x0 + 0.5 * (xs[t_best] + xs[t_best + 1]), y0 + y_mid

    return x0, y0


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
        perims = np.empty(n_rings, dtype=float)
        edges_xy = []
        for i, r in enumerate(fechados):
            rx, ry = r[:, 0], r[:, 1]
            bboxes[i] = (rx.min(), ry.min(), rx.max(), ry.max())
            rx_n = np.empty_like(rx)
            rx_n[:-1], rx_n[-1] = rx[1:], rx[0]
            ry_n = np.empty_like(ry)
            ry_n[:-1], ry_n[-1] = ry[1:], ry[0]
            perims[i] = float(np.hypot(rx_n - rx, ry_n - ry).sum())
            edges_xy.append((rx, ry, rx_n, ry_n))

        edge_diffs: list[tuple | None] = [None] * n_rings

        def _na_borda(px: float, py: float, j: int, tol_borda2: float) -> bool:
            diffs = edge_diffs[j]
            if diffs is None:
                x1, y1, x2, y2 = edges_xy[j]
                if len(x1) <= 32:
                    segs_py = []
                    for ax, ay, bx, by in zip(x1.tolist(), y1.tolist(), x2.tolist(), y2.tolist()):
                        dx = bx - ax
                        dy = by - ay
                        len2 = dx * dx + dy * dy
                        segs_py.append((ax, ay, dx, dy, 1.0 / len2 if len2 > 0.0 else 0.0))
                    diffs = (True, segs_py)
                else:
                    dx = x2 - x1
                    dy = y2 - y1
                    len2 = dx * dx + dy * dy
                    inv_len2 = np.zeros_like(len2)
                    mask = len2 > 0.0
                    inv_len2[mask] = 1.0 / len2[mask]
                    diffs = (False, (x1, y1, dx, dy, inv_len2))
                edge_diffs[j] = diffs
            if diffs[0]:
                for x1s, y1s, dxs, dys, invs in diffs[1]:
                    vx = px - x1s
                    vy = py - y1s
                    t = (vx * dxs + vy * dys) * invs
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    rx_d = vx - t * dxs
                    ry_d = vy - t * dys
                    if rx_d * rx_d + ry_d * ry_d <= tol_borda2:
                        return True
                return False
            x1, y1, dx, dy, inv_len2 = diffs[1]
            vx = px - x1
            vy = py - y1
            t = np.clip((vx * dx + vy * dy) * inv_len2, 0.0, 1.0)
            rx_d = vx - t * dx
            ry_d = vy - t * dy
            return bool(np.any(rx_d * rx_d + ry_d * ry_d <= tol_borda2))

        for i, r in enumerate(fechados):
            px0, py0 = 0.5 * (float(r[0, 0]) + float(r[1, 0])), 0.5 * (float(r[0, 1]) + float(r[1, 1]))
            perim_i = perims[i]
            thickness_i = 2.0 * abs_areas[i] / perim_i if perim_i > 0.0 else 0.0
            max_coord_i = max(
                abs(float(bboxes[i, 0])),
                abs(float(bboxes[i, 1])),
                abs(float(bboxes[i, 2])),
                abs(float(bboxes[i, 3])),
            )
            coord_eps_i = 4.0 * _FP_EPS * max_coord_i
            tol_borda_i = min(_TOL_BORDA_MAX, max(coord_eps_i, 0.05 * thickness_i))
            tol_borda2_i = tol_borda_i * tol_borda_i

            cand = np.flatnonzero(
                (abs_areas > abs_areas[i])
                & (bboxes[:, 0] <= bboxes[i, 0] + tol_borda_i)
                & (bboxes[:, 2] >= bboxes[i, 2] - tol_borda_i)
                & (bboxes[:, 1] <= bboxes[i, 1] + tol_borda_i)
                & (bboxes[:, 3] >= bboxes[i, 3] - tol_borda_i)
            )
            cont = 0
            if len(cand):
                toque = False
                for j in cand:
                    if _na_borda(px0, py0, j, tol_borda2_i):
                        toque = True
                        break
                if not toque:
                    for j in cand:
                        if _ponto_no_anel_arr(px0, py0, *edges_xy[j]):
                            cont += 1
                else:
                    x1_i, y1_i, x2_i, y2_i = edges_xy[i]
                    mids_x = 0.5 * (x1_i + x2_i)
                    mids_y = 0.5 * (y1_i + y2_i)
                    escolhido = None
                    for k in range(1, len(r)):
                        pxk, pyk = float(mids_x[k]), float(mids_y[k])
                        if not any(_na_borda(pxk, pyk, int(j), tol_borda2_i) for j in cand):
                            escolhido = (pxk, pyk)
                            break
                    if escolhido is not None:
                        px, py = escolhido
                        for j in cand:
                            if _ponto_no_anel_arr(px, py, *edges_xy[j]):
                                cont += 1
                    else:
                        m_edges = len(r)
                        pt_int: tuple[float, float] | None = None
                        for j in cand:
                            ji = int(j)
                            ex_j = edges_xy[ji]
                            testado = False
                            for k in range(m_edges):
                                pxk, pyk = float(mids_x[k]), float(mids_y[k])
                                if not _na_borda(pxk, pyk, ji, tol_borda2_i):
                                    if _ponto_no_anel_arr(pxk, pyk, *ex_j):
                                        cont += 1
                                    testado = True
                                    break
                            if not testado:
                                if pt_int is None:
                                    pt_int = _ponto_interior(r, areas[i])
                                if _ponto_no_anel_arr(pt_int[0], pt_int[1], *ex_j):
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
