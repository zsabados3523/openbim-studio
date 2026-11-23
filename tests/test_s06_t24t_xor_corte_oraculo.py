# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24t (ADR-010, P3): correcao D (XOR por multiplicidade em `corte_plano.py`).

Alvo (o implementador NAO edita este arquivo; somente producao `geometria/obim_geometria/corte_plano.py`):

CONTRATO (diag_t24r_quedas.md item D + revisao 1 T24t):
- Em `cortar_malha_no_plano(verts, tris, z)`, segmentos de corte que aparecem um numero PAR
  de vezes (mesmo segmento por coordenadas XY canonizadas, em qualquer ordem, inclusive
  arestas no plano `z` via `arestas_plano` com contadores `(n_abaixo, n_acima)`) sao
  descartados (XOR por multiplicidade); numero IMPAR mantem 1 copia preservando ordem e
  orientacao da primeira ocorrencia.
- Solido unico bem formado (todo segmento aparece 1 vez): retorna EXATAMENTE o mesmo
  resultado de hoje (`verts_abaixo`, `tris_abaixo`, `segmentos_secao`, mesma ordem, bit a bit).
- Pecas ja fechadas mantem a area liquida dos aneis; determinismo; entrada nao mutada;
  plano que nao cruza retorna vazio como hoje; segmento degenerado tratado como hoje.
- Sobreposicao sem coincidencia (ex.: dois cubos interpenetrando sem faces coincidentes):
  todos os segmentos tem multiplicidade 1, entao ficam intactos (nada e descartado nem
  inventado, sem intersecao 2D sintetica) e pecas que hoje fecham nao pioram.
"""
from __future__ import annotations

import numpy as np
import pytest

from obim_geometria import aneis, corte_plano, planta_cache, recorte
from openbim_app.desenho import estilo
from test_s06_t19j1_corte_plano_oraculo import anel_quadrado, octaedro, piramide
from test_s06_t24c_planta_cache_oraculo import _tubo_np
from test_s06_t24f_secao_tolerante_oraculo import _caixa_np, _montar_cena_numpy, _parse_svg, _transladar_malha  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _dist_pontos_a_segs, _eh_fechada, _polilinhas_mundo, _polilinhas_para_segs, _sha256  # noqa: F401
from test_s06_t24h_aneis_nao_agrupaveis_oraculo import _boas, _checar_imutavel, _congelar_snapshot


# ---------- copia de referencia da implementacao ATUAL (pre-D) ----------
def _ref_cortar(verts, tris, z):
    """Logica atual de `cortar_malha_no_plano` embutida para comparacao bit a bit."""
    v = np.asarray(verts, dtype=float)
    t = np.asarray(tris, dtype=int)
    zf = float(z)
    eps = 1e-12 * max(1.0, abs(zf))

    if len(v) == 0 or len(t) == 0:
        return (
            np.zeros((0, 3), dtype=float),
            np.zeros((0, 3), dtype=int),
            np.zeros((0, 4), dtype=float),
        )

    dz = v[:, 2] - zf
    if np.all(dz <= eps):
        return v.copy(), t.copy(), np.zeros((0, 4), dtype=float)
    if np.all(dz > eps):
        return (
            np.zeros((0, 3), dtype=float),
            np.zeros((0, 3), dtype=int),
            np.zeros((0, 4), dtype=float),
        )

    classe = np.zeros(len(v), dtype=int)
    classe[dz < -eps] = -1
    classe[dz > eps] = 1
    classe = classe.tolist()
    vl = v.tolist()

    novos_verts: list[list[float]] = []
    vert_aresta: dict[tuple[int, int], int] = {}
    n_orig = len(v)

    def ponto_aresta(ia: int, ib: int) -> int:
        chave = (ia, ib) if ia < ib else (ib, ia)
        idx = vert_aresta.get(chave)
        if idx is not None:
            return idx
        i0, i1 = chave
        p0, p1 = vl[i0], vl[i1]
        frac = (zf - p0[2]) / (p1[2] - p0[2])
        p = [p0[0] + frac * (p1[0] - p0[0]), p0[1] + frac * (p1[1] - p0[1]), zf]
        idx = n_orig + len(novos_verts)
        novos_verts.append(p)
        vert_aresta[chave] = idx
        return idx

    tris_out: list[tuple[int, int, int]] = []
    segs_vistos: set[tuple[int, int]] = set()
    segs_out: list[tuple[int, int]] = []
    arestas_plano: dict[tuple[int, int], tuple[bool, bool]] = {}

    def add_seg(ia: int, ib: int) -> None:
        if ia == ib:
            return
        chave = (ia, ib) if ia < ib else (ib, ia)
        if chave not in segs_vistos:
            segs_vistos.add(chave)
            segs_out.append((ia, ib))

    def marca_aresta_plano(ia: int, ib: int, lado: int) -> None:
        if ia == ib:
            return
        chave = (ia, ib) if ia < ib else (ib, ia)
        abaixo, acima = arestas_plano.get(chave, (False, False))
        if lado < 0:
            abaixo = True
        else:
            acima = True
        arestas_plano[chave] = (abaixo, acima)

    for i0, i1, i2 in t.tolist():
        c0, c1, c2 = classe[i0], classe[i1], classe[i2]
        n_on = (c0 == 0) + (c1 == 0) + (c2 == 0)

        if n_on == 2:
            on_ids = [idx for idx, c in ((i0, c0), (i1, c1), (i2, c2)) if c == 0]
            marca_aresta_plano(on_ids[0], on_ids[1], c0 + c1 + c2)

        if c0 <= 0 and c1 <= 0 and c2 <= 0:
            tris_out.append((i0, i1, i2))
            continue
        if c0 >= 0 and c1 >= 0 and c2 >= 0:
            continue

        n_ab = (c0 < 0) + (c1 < 0) + (c2 < 0)
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

    for (ia, ib), (viu_abaixo, viu_acima) in arestas_plano.items():
        if viu_abaixo and viu_acima:
            add_seg(ia, ib)

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


# ---------- construtores sinteticos e metricas ----------
def _blocos_em_fila_soldados_np(
    xs: list[float] | tuple[float, ...], y0: float, y1: float, z0: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    """Blocos fechados justapostos em X com faces internas coincidentes soldadas (normais opostas, mesma diagonal)."""
    nx = len(xs)
    verts = []
    idx: dict[tuple[int, int, int], int] = {}
    for iz, z in enumerate((z0, z1)):
        for iy, y in enumerate((y0, y1)):
            for ix, x in enumerate(xs):
                idx[(ix, iy, iz)] = len(verts)
                verts.append([float(x), float(y), float(z)])
    tris = []
    for k in range(nx - 1):
        v0, v1, v2, v3 = idx[(k, 0, 0)], idx[(k + 1, 0, 0)], idx[(k + 1, 1, 0)], idx[(k, 1, 0)]
        v4, v5, v6, v7 = idx[(k, 0, 1)], idx[(k + 1, 0, 1)], idx[(k + 1, 1, 1)], idx[(k, 1, 1)]
        tris.extend(
            [
                [v0, v2, v1], [v0, v3, v2],  # base (-Z)
                [v4, v5, v6], [v4, v6, v7],  # topo (+Z)
                [v0, v1, v5], [v0, v5, v4],  # frente (-Y)
                [v1, v2, v6], [v1, v6, v5],  # direita (+X) -> diagonal v1-v6
                [v2, v3, v7], [v2, v7, v6],  # tras (+Y)
                [v0, v7, v3], [v0, v4, v7],  # esquerda (-X) -> mesma diagonal v0-v7 == v1_ant-v6_ant
            ]
        )
    return np.asarray(verts, dtype=np.float64), np.asarray(tris, dtype=np.int32)


def _combinar_malhas(*malhas: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    vs, ts, off = [], [], 0
    for v, t in malhas:
        vs.append(np.asarray(v, dtype=np.float64))
        ts.append(np.asarray(t, dtype=np.int32) + off)
        off += len(v)
    return np.vstack(vs), np.vstack(ts).astype(np.int32)


def _prisma_l_np(z0: float = 0.0, z1: float = 2.8) -> tuple[np.ndarray, np.ndarray]:
    """Prisma fechado bem formado em L (area=12.0)."""
    pts = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)]
    n = len(pts)
    verts = np.array([(x, y, z) for z in (z0, z1) for x, y in pts], dtype=np.float64)
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.extend([[i, j, j + n], [i, j + n, i + n]])
    for a, b, c in ((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)):
        tris.extend([[a, c, b], [a + n, b + n, c + n]])
    return verts, np.asarray(tris, dtype=np.int32)


def _caixa_com_face_mult_np(mult: int, *, inverter: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Caixa [0,2]x[0,1]x[0,2.8] cuja face +X (tris 6,7) e repetida `mult` vezes."""
    v, t = _caixa_np(0.0, 0.0, 0.0, 2.0, 1.0, 2.8)
    face_dir = t[6:8]
    extras = []
    for k in range(1, mult):
        extras.append(face_dir[:, ::-1] if (inverter and k % 2 == 1) else face_dir)
    if extras:
        t = np.vstack([t, *extras]).astype(np.int32)
    return v, t


def _permutar_malha(v: np.ndarray, t: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    pv = rng.permutation(len(v))
    inv = np.empty_like(pv)
    inv[pv] = np.arange(len(v))
    pt = rng.permutation(len(t))
    return v[pv].copy(), inv[t[pt]].astype(t.dtype)


def _rotacao_3d(rng: np.random.Generator) -> np.ndarray:
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


def _malha_aleatoria_bem_formada(rng: np.random.Generator, idx: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Gera malha aleatoria de solido fechado manifold bem formado e uma cota de corte z."""
    tipo = idx % 4
    if tipo == 0:  # prisma estrelado/convexo rotacionado
        n = int(rng.integers(3, 13))
        ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False) + rng.uniform(0.0, 0.2)
        raios = rng.uniform(0.3, 2.5, size=n)
        pts = np.column_stack([raios * np.cos(ang), raios * np.sin(ang)])
        z0, z1 = float(rng.uniform(-2.0, 0.0)), float(rng.uniform(0.5, 4.0))
        v = np.vstack(
            [
                np.column_stack([pts, np.full(n, z0)]),
                np.column_stack([pts, np.full(n, z1)]),
                np.array([[0.0, 0.0, z0], [0.0, 0.0, z1]]),
            ]
        )
        cb, ct = 2 * n, 2 * n + 1
        tris = []
        for i in range(n):
            j = (i + 1) % n
            tris.extend([(cb, j, i), (ct, n + i, n + j), (i, j, n + j), (i, n + j, n + i)])
        t = np.asarray(tris, dtype=np.int32)
    elif tipo == 1:  # prisma subdividido em camadas Z (ocasionalmente com vertices no plano)
        n = int(rng.integers(3, 9))
        ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        raios = rng.uniform(0.4, 2.0, size=n)
        pts = np.column_stack([raios * np.cos(ang), raios * np.sin(ang)])
        zs = np.sort(rng.uniform(-1.0, 4.0, size=int(rng.integers(3, 5))))
        if zs[-1] - zs[0] < 0.5:
            zs = np.linspace(0.0, 3.0, len(zs))
        v_parts = [np.column_stack([pts, np.full(n, zc)]) for zc in zs]
        v_parts.append(np.array([[0.0, 0.0, zs[0]], [0.0, 0.0, zs[-1]]]))
        v = np.vstack(v_parts)
        nc = len(zs)
        cb, ct = nc * n, nc * n + 1
        tris = []
        for i in range(n):
            j = (i + 1) % n
            tris.extend([(cb, j, i), (ct, (nc - 1) * n + i, (nc - 1) * n + j)])
        for k in range(nc - 1):
            b, top = k * n, (k + 1) * n
            for i in range(n):
                j = (i + 1) % n
                tris.extend([(b + i, b + j, top + j), (b + i, top + j, top + i)])
        t = np.asarray(tris, dtype=np.int32)
    elif tipo == 2:  # prisma com furo (anel poligonal)
        n = int(rng.integers(4, 9))
        ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        r_ext = rng.uniform(1.5, 3.0, size=n)
        r_int = r_ext * rng.uniform(0.25, 0.65)
        ext = np.column_stack([r_ext * np.cos(ang), r_ext * np.sin(ang)])
        furo = np.column_stack([r_int * np.cos(ang), r_int * np.sin(ang)])
        z0, z1 = 0.0, float(rng.uniform(1.5, 3.5))
        v = np.vstack(
            [
                np.column_stack([ext, np.full(n, z0)]),
                np.column_stack([furo, np.full(n, z0)]),
                np.column_stack([ext, np.full(n, z1)]),
                np.column_stack([furo, np.full(n, z1)]),
            ]
        )
        ob, ib, ot, it = 0, n, 2 * n, 3 * n
        tris = []
        for i in range(n):
            j = (i + 1) % n
            tris.extend(
                [
                    (ot + i, ot + j, it + j), (ot + i, it + j, it + i),
                    (ob + i, ib + i, ib + j), (ob + i, ib + j, ob + j),
                    (ob + i, ob + j, ot + j), (ob + i, ot + j, ot + i),
                    (ib + j, ib + i, it + i), (ib + j, it + i, it + j),
                ]
            )
        t = np.asarray(tris, dtype=np.int32)
    else:  # dipiramide / octaedro perturbado
        n = int(rng.integers(4, 11))
        ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        r = rng.uniform(0.5, 2.2, size=n)
        zeq = rng.uniform(-0.3, 0.3, size=n)
        v = np.vstack(
            [
                np.column_stack([r * np.cos(ang), r * np.sin(ang), zeq]),
                np.array([[0.0, 0.0, float(rng.uniform(1.0, 2.5))], [0.0, 0.0, float(rng.uniform(-2.5, -1.0))]]),
            ]
        )
        top_i, bot_i = n, n + 1
        tris = []
        for i in range(n):
            j = (i + 1) % n
            tris.extend([(i, j, top_i), (j, i, bot_i)])
        t = np.asarray(tris, dtype=np.int32)

    if tipo != 1 or (idx % 8 != 1):
        v = v @ _rotacao_3d(rng).T
    v = v + rng.uniform(-50.0, 50.0, size=(1, 3))
    v, t = _permutar_malha(v, t, rng)

    zmin, zmax = float(v[:, 2].min()), float(v[:, 2].max())
    modo_z = idx % 10
    if modo_z == 0:
        z = zmin - 1.0  # tudo acima
    elif modo_z == 1:
        z = zmax + 1.0  # tudo abaixo
    elif modo_z == 2:
        z = float(v[int(rng.integers(0, len(v))), 2])  # vertice exatamente no plano
    else:
        z = float(rng.uniform(zmin + 0.05 * (zmax - zmin), zmax - 0.05 * (zmax - zmin)))
    return v, t, z


def _assert_igual_bit_a_bit(obtido, esperado) -> None:
    for a, b in zip(obtido, esperado):
        assert a.shape == b.shape and a.dtype == b.dtype
        assert np.array_equal(a, b)


def _perimetro_anel(anel: np.ndarray) -> float:
    nxt = np.roll(anel, -1, axis=0)
    return float(np.sum(np.hypot(nxt[:, 0] - anel[:, 0], nxt[:, 1] - anel[:, 1])))
