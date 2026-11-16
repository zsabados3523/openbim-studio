# SPDX-License-Identifier: AGPL-3.0-or-later
"""Corte exato de malha triangular por um plano horizontal z = constante."""

from __future__ import annotations

import numpy as np

_EPS = 1e-12


def cortar_malha_no_plano(verts, tris, z):
    """Corta malha triangular (verts, tris) pelo semi-espaco z <= `z`.

    Retorna (verts_abaixo, tris_abaixo, segmentos_secao) com shapes
    (n, 3) float, (m, 3) int e (k, 4) float.
    """
    v = np.asarray(verts, dtype=float)
    t = np.asarray(tris, dtype=int)
    zf = float(z)

    if len(v) == 0 or len(t) == 0:
        return (
            np.zeros((0, 3), dtype=float),
            np.zeros((0, 3), dtype=int),
            np.zeros((0, 4), dtype=float),
        )

    dz = v[:, 2] - zf
    if np.all(dz <= _EPS):
        return v.copy(), t.copy(), np.zeros((0, 4), dtype=float)
    if np.all(dz > _EPS):
        return (
            np.zeros((0, 3), dtype=float),
            np.zeros((0, 3), dtype=int),
            np.zeros((0, 4), dtype=float),
        )

    # -1 abaixo, 0 no plano, +1 acima
    classe = np.zeros(len(v), dtype=int)
    classe[dz < -_EPS] = -1
    classe[dz > _EPS] = 1

    novos_verts: list[np.ndarray] = []
    vert_aresta: dict[tuple[int, int], int] = {}
    n_orig = len(v)

    def ponto_aresta(ia: int, ib: int) -> int:
        chave = (ia, ib) if ia < ib else (ib, ia)
        idx = vert_aresta.get(chave)
        if idx is not None:
            return idx
        i0, i1 = chave
        p0, p1 = v[i0], v[i1]
        frac = (zf - p0[2]) / (p1[2] - p0[2])
        p = p0 + frac * (p1 - p0)
        p[2] = zf
        idx = n_orig + len(novos_verts)
        novos_verts.append(p)
        vert_aresta[chave] = idx
        return idx

    tris_out: list[tuple[int, int, int]] = []
    segs_vistos: set[tuple[int, int]] = set()
    segs_out: list[tuple[int, int]] = []

    def add_seg(ia: int, ib: int) -> None:
        if ia == ib:
            return
        chave = (ia, ib) if ia < ib else (ib, ia)
        if chave not in segs_vistos:
            segs_vistos.add(chave)
            segs_out.append((ia, ib))

    for tri in t:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        c0, c1, c2 = int(classe[i0]), int(classe[i1]), int(classe[i2])

        if c0 <= 0 and c1 <= 0 and c2 <= 0:
            tris_out.append((i0, i1, i2))
            continue

        if c0 >= 0 and c1 >= 0 and c2 >= 0:
            if (c0 == 0) + (c1 == 0) + (c2 == 0) == 2:
                on_ids = [idx for idx, c in ((i0, c0), (i1, c1), (i2, c2)) if c == 0]
                add_seg(on_ids[0], on_ids[1])
            continue

        n_ab = (c0 < 0) + (c1 < 0) + (c2 < 0)
        n_on = (c0 == 0) + (c1 == 0) + (c2 == 0)

        if n_on == 1:
            if c1 < 0:
                i0, i1, i2 = i1, i2, i0
                c0, c1, c2 = c1, c2, c0
            elif c2 < 0:
                i0, i1, i2 = i2, i0, i1
                c0, c1, c2 = c2, c0, c1
            if c1 == 0:
                p = ponto_aresta(i0, i2)
                tris_out.append((i0, i1, p))
                add_seg(i1, p)
            else:
                p = ponto_aresta(i0, i1)
                tris_out.append((i0, p, i2))
                add_seg(p, i2)
        elif n_ab == 1:
            if c1 < 0:
                i0, i1, i2 = i1, i2, i0
            elif c2 < 0:
                i0, i1, i2 = i2, i0, i1
            p0 = ponto_aresta(i0, i1)
            p1 = ponto_aresta(i0, i2)
            tris_out.append((i0, p0, p1))
            add_seg(p0, p1)
        else:
            if c1 > 0:
                i0, i1, i2 = i1, i2, i0
            elif c2 > 0:
                i0, i1, i2 = i2, i0, i1
            p0 = ponto_aresta(i0, i1)
            p1 = ponto_aresta(i0, i2)
            tris_out.append((p0, i1, i2))
            tris_out.append((p0, i2, p1))
            add_seg(p0, p1)

    todos_verts = np.vstack([v, np.asarray(novos_verts, dtype=float)]) if novos_verts else v

    if tris_out:
        tris_arr = np.asarray(tris_out, dtype=int)
        usados = np.unique(tris_arr)
        remap = np.empty(len(todos_verts), dtype=int)
        remap[usados] = np.arange(len(usados), dtype=int)
        verts_abaixo = todos_verts[usados].copy()
        tris_abaixo = remap[tris_arr]
    else:
        verts_abaixo = np.zeros((0, 3), dtype=float)
        tris_abaixo = np.zeros((0, 3), dtype=int)

    if segs_out:
        segs_idx = np.asarray(segs_out, dtype=int)
        segmentos_secao = np.hstack([todos_verts[segs_idx[:, 0], :2], todos_verts[segs_idx[:, 1], :2]])
    else:
        segmentos_secao = np.zeros((0, 4), dtype=float)

    return verts_abaixo, tris_abaixo, segmentos_secao
