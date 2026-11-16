# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construcao de aneis a partir de segmentos e recorte de polilinhas fora dos aneis."""
from collections import defaultdict
import math
import numpy as np

_EPS = 1e-12


def _area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _ponto_no_anel(px: float, py: float, poly: np.ndarray) -> bool:
    dentro, (x1, y1) = False, (float(poly[-1, 0]), float(poly[-1, 1]))
    for x2, y2 in poly:
        x2, y2 = float(x2), float(y2)
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
        x1, y1 = x2, y2
    return dentro


def aneis_de_segmentos(segs, tol: float = 1e-6):
    """Costura segmentos (k,4) em (fechados, abertos) com orientacao e inicio deterministicos."""
    arr = np.asarray(segs, dtype=float)
    if arr.size == 0:
        return [], []
    arr = arr.reshape(-1, 4)
    chave = (lambda p: (int(round(float(p[0]) / tol)), int(round(float(p[1]) / tol)))) if tol > 0 else (lambda p: (float(p[0]), float(p[1])))
    buckets, pares = defaultdict(list), []
    for row in arr:
        k1, k2 = chave(row[:2]), chave(row[2:])
        if k1 != k2:
            buckets[k1].append(row[:2])
            buckets[k2].append(row[2:])
            pares.append((k1, k2))
    if not pares:
        return [], []
    coords_raw = {k: (m[0].copy() if np.all((m := np.vstack(pts)) == m[0]) else np.mean(m, axis=0)) for k, pts in buckets.items()}
    chaves_ord = sorted(coords_raw, key=lambda k: (float(coords_raw[k][0]), float(coords_raw[k][1])))
    id_de = {k: i for i, k in enumerate(chaves_ord)}
    coords = [coords_raw[k] for k in chaves_ord]
    adj = [[] for _ in coords]
    for eid, (k1, k2) in enumerate(pares):
        u, v = id_de[k1], id_de[k2]
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
    areas = [_area(r) for r in fechados]
    orientados = []
    for i, r in enumerate(fechados):
        px, py = 0.5 * (r[0] + r[1])
        cont = sum(1 for j, r2 in enumerate(fechados) if j != i and abs(areas[j]) > abs(areas[i]) and _ponto_no_anel(float(px), float(py), r2))
        if (cont % 2 == 1 and areas[i] > 0.0) or (cont % 2 == 0 and areas[i] < 0.0):
            r = r[::-1].copy()
        idx = min(range(len(r)), key=lambda k: (float(r[k, 0]), float(r[k, 1])))
        orientados.append(np.roll(r, -idx, axis=0))
    orientados.sort(key=lambda r: (float(r[0, 0]), float(r[0, 1]), _area(r)))

    abertos = sorted(
        (pts[::-1].copy() if (float(pts[-1, 0]), float(pts[-1, 1])) < (float(pts[0, 0]), float(pts[0, 1])) else pts
         for pts in (np.array([coords[i] for i in cam], dtype=float) for cam in abertos_ids)),
        key=lambda p: (float(p[0, 0]), float(p[0, 1]), float(p[-1, 0]), float(p[-1, 1])),
    )
    return orientados, abertos


def _dist_seg2(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    ex, ey = bx - ax, by - ay
    l2 = ex * ex + ey * ey
    u = 0.0 if l2 <= 0.0 else max(0.0, min(1.0, ((px - ax) * ex + (py - ay) * ey) / l2))
    return (px - (ax + u * ex)) ** 2 + (py - (ay + u * ey)) ** 2


def _cortes_no_segmento(ax: float, ay: float, bx: float, by: float, arestas, vertices, encolher: float):
    dx, dy = bx - ax, by - ay
    aa = dx * dx + dy * dy
    seg_len, ts, r2 = math.sqrt(aa), [0.0, 1.0], encolher * encolher
    for cx, cy, ex_pt, ey_pt in arestas:
        ex, ey = ex_pt - cx, ey_pt - cy
        if (el2 := ex * ex + ey * ey) <= 0.0:
            continue
        denom, acx, acy, e_len = dx * ey - dy * ex, cx - ax, cy - ay, math.sqrt(el2)
        if abs(denom) > _EPS * seg_len * e_len:
            t, u = (acx * ey - acy * ex) / denom, (acx * dy - acy * dx) / denom
            if -1e-11 <= u <= 1.0 + 1e-11 and 0.0 < t < 1.0:
                ts.append(t)
        elif abs(acx * dy - acy * dx) <= 1e-11 * seg_len:
            for qx, qy in ((cx, cy), (ex_pt, ey_pt)):
                if 0.0 < (t := ((qx - ax) * dx + (qy - ay) * dy) / aa) < 1.0:
                    ts.append(t)
        if encolher > 0.0:
            nx, ny = -ey / e_len, ex / e_len
            s0, ds = (ax - cx) * nx + (ay - cy) * ny, dx * nx + dy * ny
            if abs(ds) > _EPS * seg_len:
                for alvo in (encolher, -encolher):
                    t = (alvo - s0) / ds
                    if 0.0 < t < 1.0 and -1e-11 <= ((ax + t * dx - cx) * ex + (ay + t * dy - cy) * ey) / el2 <= 1.0 + 1e-11:
                        ts.append(t)
    if encolher > 0.0:
        for vx, vy in vertices:
            wx, wy = ax - vx, ay - vy
            bh = wx * dx + wy * dy
            if (disc := bh * bh - aa * (wx * wx + wy * wy - r2)) >= 0.0:
                sq = math.sqrt(disc)
                ts.extend(t for t in ((-bh - sq) / aa, (-bh + sq) / aa) if 0.0 < t < 1.0)
    ts.sort()
    tol_t, unicos = min(_EPS, _EPS / max(1.0, seg_len)), [0.0]
    for t in ts[1:-1]:
        if t - unicos[-1] > tol_t and 1.0 - t > tol_t:
            unicos.append(t)
    return unicos + [1.0]


def recortar_fora_dos_aneis(polilinhas, aneis, encolher: float = 5e-4):
    """Remove trechos das polilinhas dentro da regiao par-impar encolhida dos aneis."""
    polys, arestas, vertices = [], [], []
    for a in aneis:
        p = np.asarray(a, dtype=float)
        p = p[:-1] if len(p) > 1 and np.allclose(p[0], p[-1], atol=_EPS, rtol=0.0) else p
        if len(p) < 3:
            continue
        polys.append(p)
        for i in range(len(p)):
            q1, q2 = p[i], p[(i + 1) % len(p)]
            arestas.append((float(q1[0]), float(q1[1]), float(q2[0]), float(q2[1])))
            vertices.append((float(q1[0]), float(q1[1])))

    def dentro(px: float, py: float) -> bool:
        if sum(1 for p in polys if _ponto_no_anel(px, py, p)) % 2 == 0:
            return False
        d2 = min(_dist_seg2(px, py, *e) for e in arestas)
        return d2 > _EPS * _EPS if encolher <= 0.0 else math.sqrt(d2) >= encolher - _EPS

    saida = []
    for poli in polilinhas:
        pts = np.asarray(poli, dtype=float)
        if len(pts) < 2:
            continue
        if not polys:
            saida.append(pts.copy())
            continue
        atual = None
        for i in range(len(pts) - 1):
            ax, ay, bx, by = float(pts[i, 0]), float(pts[i, 1]), float(pts[i + 1, 0]), float(pts[i + 1, 1])
            dx, dy = bx - ax, by - ay
            if dx * dx + dy * dy <= _EPS * _EPS:
                continue
            ts = _cortes_no_segmento(ax, ay, bx, by, arestas, vertices, encolher)
            interv = []
            for t0, t1 in zip(ts, ts[1:]):
                if not dentro(ax + 0.5 * (t0 + t1) * dx, ay + 0.5 * (t0 + t1) * dy):
                    if interv and interv[-1][1] == t0:
                        interv[-1] = (interv[-1][0], t1)
                    else:
                        interv.append((t0, t1))
            for t0, t1 in interv:
                p0 = pts[i].copy() if t0 == 0.0 else np.array([ax + t0 * dx, ay + t0 * dy])
                p1 = pts[i + 1].copy() if t1 == 1.0 else np.array([ax + t1 * dx, ay + t1 * dy])
                if atual is not None and t0 == 0.0:
                    atual.append(p1)
                else:
                    if atual is not None:
                        saida.append(np.vstack(atual))
                    atual = [p0, p1]
            if (not interv or interv[-1][1] != 1.0) and atual is not None:
                saida.append(np.vstack(atual))
                atual = None
        if atual is not None:
            saida.append(np.vstack(atual))
    return saida
