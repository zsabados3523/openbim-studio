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
from test_s06_t24f_secao_tolerante_oraculo import (
    _caixa_np,
    _dist_pontos_a_segs,
    _eh_fechada,
    _montar_cena_numpy,
    _parse_svg,
    _polilinhas_mundo,
    _polilinhas_para_segs,
    _sha256,
    _transladar_malha,
)
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


# ---------- (1) ACEITACAO (FALHAM HOJE; PASSAM COM D) ----------
@pytest.mark.parametrize(
    ("xs", "y0", "y1", "z0", "z1", "z_corte"),
    [
        pytest.param((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0, 1.0, id="dois_cubos_unitarios"),
        pytest.param((0.0, 1.5, 4.0), 0.0, 0.4, 0.0, 2.8, 1.2, id="dois_blocos_parede"),
    ],
)
def test_aceitacao_dois_cubos_justapostos_fecha_em_um_anel_area_soma(xs, y0, y1, z0, z1, z_corte):
    """Dois cubos justapostos com face comum: hoje anel aberto; com D fecha em 1 anel de area=soma."""
    v, t = _blocos_em_fila_soldados_np(xs, y0, y1, z0, z1)
    v0, t0 = v.copy(), t.copy()
    v.setflags(write=False)
    t.setflags(write=False)
    _, _, segs_ref = _ref_cortar(v, t, z_corte)
    _, ab_ref = aneis.aneis_de_segmentos(segs_ref)
    assert len(ab_ref) >= 1 and len(segs_ref) == 14, "sanidade: hoje mantem face interna e abre anel"

    res = corte_plano.cortar_malha_no_plano(v, t, z_corte)
    for _ in range(2):
        _assert_igual_bit_a_bit(corte_plano.cortar_malha_no_plano(v, t, z_corte), res)
    assert np.array_equal(v, v0) and np.array_equal(t, t0)
    _, _, segs = res
    assert len(segs) == 12
    fechados, abertos = aneis.aneis_de_segmentos(segs)
    assert len(fechados) == 1 and abertos == []
    area_esp = (xs[-1] - xs[0]) * (y1 - y0)
    perim_esp = 2.0 * ((xs[-1] - xs[0]) + (y1 - y0))
    assert abs(aneis._area(fechados[0])) == pytest.approx(area_esp, abs=1e-9)
    assert _perimetro_anel(fechados[0]) == pytest.approx(perim_esp, abs=1e-9)


def test_aceitacao_tres_blocos_em_fila_fecha_em_um_anel_area_soma():
    """Tres blocos soldados em fila: 2 faces internas canceladas -> 1 anel fechado de area=soma."""
    xs, y0, y1 = (0.0, 1.0, 2.5, 4.0), 0.0, 0.5
    v, t = _blocos_em_fila_soldados_np(xs, y0, y1, 0.0, 2.8)
    _, _, segs_ref = _ref_cortar(v, t, 1.2)
    _, ab_ref = aneis.aneis_de_segmentos(segs_ref)
    assert len(ab_ref) >= 1 and len(segs_ref) == 20

    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.2)
    assert len(segs) == 16
    fechados, abertos = aneis.aneis_de_segmentos(segs)
    assert len(fechados) == 1 and abertos == []
    assert abs(aneis._area(fechados[0])) == pytest.approx(2.0, abs=1e-9)
    assert _perimetro_anel(fechados[0]) == pytest.approx(9.0, abs=1e-9)


def test_aceitacao_planta_cache_justapostos_zera_parciais_e_ganha_tampa(monkeypatch):
    """Em `desenhar_planta_cache`, parede justaposta deixa de contar em `secoes_parciais` e ganha tampa."""
    grupos_passados: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis
    monkeypatch.setattr(
        recorte,
        "recortar_fora_dos_aneis",
        lambda pols, grupos, *a, **k: (grupos_passados.append(list(grupos)), real_recorte(pols, grupos, *a, **k))[1],
    )
    parede_2 = _blocos_em_fila_soldados_np((0.0, 2.0, 4.0), 0.0, 0.4, 0.0, 2.8)
    pecas = [
        (10, "G_JUSTA", "IfcWall", parede_2),
        *_boas(3, id0=11, x0=6.0),
        (20, "G_BARRA_1", "IfcSlab", _caixa_np(0.9, -0.5, 0.0, 1.1, 1.0, 0.2)),
        (21, "G_BARRA_2", "IfcSlab", _caixa_np(2.9, -0.5, 0.0, 3.1, 1.0, 0.2)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0
    assert len(grupos_passados) == 1 and len(grupos_passados[0]) == 4

    parsed = _parse_svg(resp["svg"])
    pls_j = _polilinhas_mundo(parsed.cut_by_guid["G_JUSTA"])
    assert len(pls_j) == 1 and _eh_fechada(pls_j[0])
    assert abs(aneis._area(pls_j[0][:-1])) == pytest.approx(1.6, abs=1e-4)

    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    # Ambos os blocos tampam as barras de piso sob a parede (y=0.2), mantendo fora (y=-0.3, y=0.8) visivel
    assert float(_dist_pontos_a_segs(np.array([[0.9, 0.2], [1.1, 0.2], [2.9, 0.2], [3.1, 0.2]]), segs_proj).min()) > 0.05
    assert float(_dist_pontos_a_segs(np.array([[0.9, -0.3], [1.1, 0.8], [2.9, -0.3], [3.1, 0.8]]), segs_proj).max()) <= 1e-3
    estilo.aplicar_estilo(resp["svg"], "1:50")

    # 2 boas + 2 paredes de 3 blocos em fila (antes 50% > 25% -> caia secao_aberta; com D passa com 0 parciais)
    pecas_4 = [
        *_boas(2, id0=10, x0=0.0),
        (12, "G_FILA_1", "IfcWall", _blocos_em_fila_soldados_np((10.0, 11.0, 12.5, 14.0), 0.0, 0.4, 0.0, 2.8)),
        (13, "G_FILA_2", "IfcWall", _blocos_em_fila_soldados_np((16.0, 17.0, 18.5, 20.0), 0.0, 0.4, 0.0, 2.8)),
    ]
    r4, mot4 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas_4, altura_corte_m=1.2))
    assert mot4 is None and r4 is not None and r4["secoes_parciais"] == 0


# ---------- (2) NAO-REGRESSAO (PASSAM HOJE E PASSAM COM D) ----------
def test_nao_regressao_solidos_canonicos_bordas_e_degenerado_bit_a_bit():
    """Cubo, L, anel com furo, piramide, octaedro, nao-cruzamento e degenerado: identico bit a bit a `_ref_cortar`."""
    ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    furo = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    tri_deg_v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0]], dtype=np.float64)
    tri_deg_t = np.array([[0, 0, 1], [0, 1, 1]], dtype=np.int32)
    casos = [
        ("cubo_meio", *_caixa_np(0.0, 0.0, 0.0, 3.0, 2.0, 4.0), 1.5, True),
        ("prisma_l", *_prisma_l_np(0.0, 2.8), 1.2, True),
        ("anel_furo_tubo", *_tubo_np(ext, furo, 0.0, 2.8), 1.2, True),
        ("anel_quadrado", *anel_quadrado(4.0, 2.0, 0.0, 2.0), 1.0, True),
        ("piramide", *piramide(), 1.0, True),
        ("octaedro_equador", *octaedro(), 0.0, True),
        ("plano_acima", *_caixa_np(0.0, 0.0, 0.0, 2.0, 2.0, 2.0), 5.0, False),
        ("plano_abaixo", *_caixa_np(0.0, 0.0, 3.0, 2.0, 2.0, 5.0), 1.0, False),
        ("vazio", np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32), 1.0, False),
        ("degenerado_idx_igual", tri_deg_v, tri_deg_t, 1.0, False),
    ]
    for nome, v, t, z, checar_area in casos:
        v0, t0 = v.copy(), t.copy()
        v.setflags(write=False)
        t.setflags(write=False)
        ref = _ref_cortar(v, t, z)
        obt = corte_plano.cortar_malha_no_plano(v, t, z)
        _assert_igual_bit_a_bit(obt, ref)
        assert np.array_equal(v, v0) and np.array_equal(t, t0), nome
        if checar_area:
            f_ref, ab_ref = aneis.aneis_de_segmentos(ref[2])
            f_obt, ab_obt = aneis.aneis_de_segmentos(obt[2])
            assert ab_ref == [] and ab_obt == [] and len(f_obt) == len(f_ref), nome
            assert sum(aneis._area(a) for a in f_obt) == pytest.approx(sum(aneis._area(a) for a in f_ref), abs=1e-12)


def test_nao_regressao_fuzz_360_solidos_bem_formados_bit_a_bit():
    """Fuzz seed fixa (360 malhas aleatorias de solido bem formado): saida bit a bit igual a `_ref_cortar`."""
    rng = np.random.default_rng(20260424)
    n_cruzou = 0
    for idx in range(360):
        v, t, z = _malha_aleatoria_bem_formada(rng, idx)
        v0, t0 = v.copy(), t.copy()
        v.setflags(write=False)
        t.setflags(write=False)
        ref = _ref_cortar(v, t, z)
        obt = corte_plano.cortar_malha_no_plano(v, t, z)
        _assert_igual_bit_a_bit(obt, ref)
        assert np.array_equal(v, v0) and np.array_equal(t, t0)
        if len(ref[2]) > 0:
            n_cruzou += 1
    assert n_cruzou >= 250


# ---------- (3) SOBREPOSICAO SEM COINCIDENCIA (PASSA HOJE E PASSA COM D) ----------
@pytest.mark.parametrize(
    ("caixa_a", "caixa_b"),
    [
        pytest.param((0.0, 0.0, 0.0, 2.0, 1.0, 2.8), (1.0, 0.2, 0.0, 3.0, 1.2, 2.8), id="deslocados"),
        pytest.param((0.0, 0.0, 0.0, 2.0, 1.0, 2.8), (0.5, -0.5, 0.0, 1.5, 1.5, 2.8), id="em_cruz"),
    ],
)
def test_sobreposicao_sem_coincidencia_mantem_segmentos_e_nao_piora_fechadas(caixa_a, caixa_b):
    """Dois cubos com volumes interpenetrando SEM faces coincidentes:

    Comportamento esperado de D: nenhum segmento coincide (multiplicidade 1 para todos), logo
    todos os segmentos ficam exatamente como hoje e nenhuma intersecao 2D e inventada.
    Pecas que hoje fecham em 2 aneis fechados continuam fechando sem piorar (secoes_parciais=0).
    """
    v, t = _combinar_malhas(_caixa_np(*caixa_a), _caixa_np(*caixa_b))
    ref = _ref_cortar(v, t, 1.2)
    obt = corte_plano.cortar_malha_no_plano(v, t, 1.2)
    _assert_igual_bit_a_bit(obt, ref)
    assert len(obt[2]) == 16

    fech, ab = aneis.aneis_de_segmentos(obt[2])
    assert len(fech) == 2 and ab == []
    assert sum(abs(aneis._area(a)) for a in fech) == pytest.approx(4.0, abs=1e-9)

    resp, mot = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([(10, "G_SOBRE", "IfcWall", (v, t))], altura_corte_m=1.2)
    )
    assert mot is None and resp is not None and resp["secoes_parciais"] == 0


# ---------- (4) ORDEM INVERTIDA E MULTIPLICIDADES 2, 3, 4 ----------
def test_ordem_invertida_e_multiplicidades_2_3_4():
    """Segmentos com ordem invertida contam como o mesmo; mult 2 e 4 descartam; mult 3 mantem 1."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [0.0, 2.0, 2.0]], dtype=np.float64)
    # 1) Ordem invertida (mult=2) -> descartado
    _, _, segs_inv2 = corte_plano.cortar_malha_no_plano(v, np.array([[0, 1, 2], [0, 2, 1]], dtype=np.int32), 1.0)
    assert segs_inv2.shape == (0, 4)

    # 2) Multiplicidade 3 (com inversoes) -> mantem 1
    _, _, segs_3 = corte_plano.cortar_malha_no_plano(
        v, np.array([[0, 1, 2], [0, 2, 1], [0, 1, 2]], dtype=np.int32), 1.0
    )
    assert segs_3.shape == (1, 4)
    pts_3 = {(round(float(segs_3[0, 0]), 9), round(float(segs_3[0, 1]), 9)),
             (round(float(segs_3[0, 2]), 9), round(float(segs_3[0, 3]), 9))}
    assert pts_3 == {(1.0, 0.0), (0.0, 1.0)}

    # 3) Multiplicidade 4 (mesma ordem e alternada) -> descartado
    for tris_4 in (
        np.array([[0, 1, 2], [0, 1, 2], [0, 1, 2], [0, 1, 2]], dtype=np.int32),
        np.array([[0, 1, 2], [0, 2, 1], [0, 1, 2], [0, 2, 1]], dtype=np.int32),
    ):
        _, _, segs_4 = corte_plano.cortar_malha_no_plano(v, tris_4, 1.0)
        assert segs_4.shape == (0, 4)

    # 4) Em solido: face +X com mult=3 fecha (area=2.0); face +X com mult=4 some (6 segs, aberto)
    v3, t3 = _caixa_com_face_mult_np(3, inverter=True)
    _, _, s_c3 = corte_plano.cortar_malha_no_plano(v3, t3, 1.2)
    f3, a3 = aneis.aneis_de_segmentos(s_c3)
    assert len(s_c3) == 8 and len(f3) == 1 and a3 == [] and abs(aneis._area(f3[0])) == pytest.approx(2.0, abs=1e-9)

    v4, t4 = _caixa_com_face_mult_np(4, inverter=True)
    _, _, s_c4 = corte_plano.cortar_malha_no_plano(v4, t4, 1.2)
    f4, a4 = aneis.aneis_de_segmentos(s_c4)
    assert len(s_c4) == 6 and f4 == [] and len(a4) == 1


# ---------- (5) MUTANTES (1 TESTE POR ERRO PLAUSIVEL) ----------
def test_mutante_01_descartar_todo_duplicado_inclusive_impar():
    """Mutante 1: usar `count == 1` em vez de `count % 2 == 1` descartaria face externa de mult=3."""
    v, t = _blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0)
    # Duplica 2x a face externa esquerda (-X do 1o cubo, indices 10 e 11 de `t`) -> mult=3 nessa face, mult=2 na interna
    face_ext = t[10:12]
    t_m = np.vstack([t, face_ext[:, ::-1], face_ext]).astype(np.int32)
    _, _, segs = corte_plano.cortar_malha_no_plano(v, t_m, 1.0)
    fech, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 12 and len(fech) == 1 and ab == []
    assert abs(aneis._area(fech[0])) == pytest.approx(2.0, abs=1e-9)


def test_mutante_02_ignorar_ordem_invertida():
    """Mutante 2: contar chave orientada `(ia, ib)` em vez de nao-orientada deixa pares invertidos vivos."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [0.0, 2.0, 2.0]], dtype=np.float64)
    _, _, s_a = _ref_cortar(v, np.array([[0, 1, 2]], dtype=np.int32), 1.0)
    _, _, s_b = _ref_cortar(v, np.array([[0, 2, 1]], dtype=np.int32), 1.0)
    assert np.array_equal(s_a[0, :2], s_b[0, 2:]) and np.array_equal(s_a[0, 2:], s_b[0, :2])

    _, _, segs_par = corte_plano.cortar_malha_no_plano(v, np.array([[0, 1, 2], [0, 2, 1]], dtype=np.int32), 1.0)
    assert len(segs_par) == 0

    v2, t2 = _blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0)
    _, _, segs_cubos = corte_plano.cortar_malha_no_plano(v2, t2, 1.0)
    fech, ab = aneis.aneis_de_segmentos(segs_cubos)
    assert len(segs_cubos) == 12 and len(fech) == 1 and ab == []


def test_mutante_03_manter_os_dois_de_multiplicidade_2():
    """Mutante 3: manter os dois (ou um) segmentos de multiplicidade 2 (mesma orientacao ou oposta)."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [0.0, 2.0, 2.0]], dtype=np.float64)
    _, _, segs_dup = corte_plano.cortar_malha_no_plano(v, np.array([[0, 1, 2], [0, 1, 2]], dtype=np.int32), 1.0)
    assert len(segs_dup) == 0

    v2, t2 = _blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0)
    _, _, segs = corte_plano.cortar_malha_no_plano(v2, t2, 1.0)
    assert len(segs) == 12
    # Nenhum segmento da face interna x=1.0 pode restar
    eh_interno = (np.abs(segs[:, 0] - 1.0) < 1e-9) & (np.abs(segs[:, 2] - 1.0) < 1e-9)
    assert not np.any(eh_interno)


def test_mutante_04_mexer_em_solido_unico():
    """Mutante 4: alterar ordem, direcao `(ia, ib)` ou parte abaixo num solido unico bem formado."""
    ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    furo = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    for v, t, z in (
        (*_caixa_np(0.0, 0.0, 0.0, 3.0, 2.0, 4.0), 1.2),
        (*_prisma_l_np(0.0, 2.8), 1.2),
        (*_tubo_np(ext, furo, 0.0, 2.8), 1.2),
        (*octaedro(), 0.0),
    ):
        _assert_igual_bit_a_bit(corte_plano.cortar_malha_no_plano(v, t, z), _ref_cortar(v, t, z))


def test_mutante_05_perder_ordem_estavel():
    """Mutante 5: usar `set`, `sorted(chaves)` ou trocar `(ia, ib)` por `(min, max)` quebra ordem estavel."""
    rng = np.random.default_rng(1337)
    v, t = _permutar_malha(*_blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0), rng)
    _, _, segs_ref = _ref_cortar(v, t, 1.0)
    mask_int = (np.abs(segs_ref[:, 0] - 1.0) < 1e-9) & (np.abs(segs_ref[:, 2] - 1.0) < 1e-9)
    assert int(np.sum(mask_int)) == 2
    segs_esp = segs_ref[~mask_int]

    _, _, segs_obt = corte_plano.cortar_malha_no_plano(v, t, 1.0)
    assert segs_obt.shape == segs_esp.shape and np.array_equal(segs_obt, segs_esp)

    # Tambem checa solido unico embaralhado contra `_ref_cortar`
    vc, tc = _permutar_malha(*_caixa_np(0.0, 0.0, 0.0, 3.0, 2.0, 4.0), rng)
    _assert_igual_bit_a_bit(corte_plano.cortar_malha_no_plano(vc, tc, 1.2), _ref_cortar(vc, tc, 1.2))


# ---------- (6) INTEGRACAO DESENHO: SHA 3 RODADAS E MALHAS_MUNDO INTACTO ----------
@pytest.mark.parametrize(
    "offset",
    [pytest.param((0.0, 0.0), id="origem"), pytest.param((500_000.25, 7_500_000.75), id="utm")],
)
def test_integracao_desenho_sha256_3_rodadas_e_malhas_mundo_nao_mutado(offset):
    """Cena com paredes justapostas + boas + furo: SHA identico 3 rodadas, reversa, threads=4; `malhas_mundo` intacto."""
    ox, oy = offset
    ext = [(16.0, 0.0), (18.0, 0.0), (18.0, 2.0), (16.0, 2.0)]
    furo = [(16.5, 0.5), (17.5, 0.5), (17.5, 1.5), (16.5, 1.5)]
    base = [
        (10, "G_JUSTA_2", "IfcWall", _blocos_em_fila_soldados_np((0.0, 1.5, 3.0), 0.0, 0.4, 0.0, 2.8)),
        (11, "G_JUSTA_3", "IfcWall", _blocos_em_fila_soldados_np((5.0, 6.0, 7.5, 9.0), 0.0, 0.4, 0.0, 2.8)),
        *_boas(2, id0=12, x0=11.0, passo=2.5),
        (14, "G_FURO", "IfcWall", _tubo_np(ext, furo, 0.0, 2.8)),
        (15, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 19.0, 2.5, 0.0)),
    ]
    pecas = [(i, g, c, _transladar_malha(m, ox, oy)) for i, g, c, m in base]
    f, ped, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2, threads=1)
    snap = _congelar_snapshot(malhas, ped)
    shas = []
    for _ in range(3):
        r, mot = planta_cache.desenhar_planta_cache(f, ped, malhas, ev)
        assert mot is None and r is not None and r["ok"] is True and r["secoes_parciais"] == 0
        shas.append(_sha256(r["svg"]))
    assert shas[0] == shas[1] == shas[2]
    _checar_imutavel(malhas, ped, *snap)

    r_rev, mot_rev = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(list(reversed(pecas)), altura_corte_m=1.2, threads=1))
    assert mot_rev is None and _sha256(r_rev["svg"]) == shas[0]
    r_t4, mot_t4 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2, threads=4))
    assert mot_t4 is None and _sha256(r_t4["svg"]) == shas[0]


# ---------- (7) DEFEITOS REV1: ARESTAS_PLANO COM CONTADORES E CHAVE XOR POR COORDENADAS ----------
def _quad_tris(a: int, b: int, c: int, d: int) -> list[list[int]]:
    return [[a, b, c], [a, c, d]]


def test_defeito_1a_face_dupla_com_aresta_no_plano_deve_cancelar():
    """Face vertical dupla (mult=2) com aresta horizontal em z=1.0: 0 segs; mult=3: 1 seg."""
    v = np.array(
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 1.0], [0.0, 0.0, 2.0], [0.0, 1.0, 2.0]],
        dtype=np.float64,
    )
    t_par = np.array([[2, 3, 0], [2, 4, 3], [3, 2, 0], [3, 4, 2]], dtype=np.int32)
    _, _, s_fora = corte_plano.cortar_malha_no_plano(v, t_par, 0.5)
    assert len(s_fora) == 0  # sanidade fora do plano
    _, _, s_no = corte_plano.cortar_malha_no_plano(v, t_par, 1.0)
    assert len(s_no) == 0, f"arestas_plano ignorou multiplicidade par: retornou {len(s_no)} seg(s)"

    # Multiplicidade impar (3) em aresta no plano z=1.0 deve manter 1 segmento
    t_impar = np.array([[2, 3, 0], [2, 4, 3], [3, 2, 0], [3, 4, 2], [2, 3, 0], [2, 4, 3]], dtype=np.int32)
    _, _, s_imp = corte_plano.cortar_malha_no_plano(v, t_impar, 1.0)
    assert len(s_imp) == 1


def test_defeito_1b_blocos_justapostos_subdivididos_no_plano_z():
    """Dois blocos soldados subdivididos em z=1.0: aresta interna em z=1.0 (mult=2) cancela -> 6 segs."""
    verts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 1, 0], [1, 1, 0], [2, 1, 0],
            [0, 0, 1], [1, 0, 1], [2, 0, 1], [0, 1, 1], [1, 1, 1], [2, 1, 1],
            [0, 0, 2], [1, 0, 2], [2, 0, 2], [0, 1, 2], [1, 1, 2], [2, 1, 2],
        ],
        dtype=np.float64,
    )
    tris: list[list[int]] = []
    # Bloco 1 [0,1]x[0,1]x[0,2] dividido em z=1
    tris += _quad_tris(0, 3, 4, 1) + _quad_tris(12, 13, 16, 15)
    tris += _quad_tris(0, 1, 7, 6) + _quad_tris(1, 4, 10, 7) + _quad_tris(4, 3, 9, 10) + _quad_tris(3, 0, 6, 9)
    tris += _quad_tris(6, 7, 13, 12) + _quad_tris(7, 10, 16, 13) + _quad_tris(10, 9, 15, 16) + _quad_tris(9, 6, 12, 15)
    # Bloco 2 [1,2]x[0,1]x[0,2] dividido em z=1
    tris += _quad_tris(1, 4, 5, 2) + _quad_tris(13, 14, 17, 16)
    tris += _quad_tris(1, 2, 8, 7) + _quad_tris(2, 5, 11, 8) + _quad_tris(5, 4, 10, 11) + _quad_tris(4, 1, 7, 10)
    tris += _quad_tris(7, 8, 14, 13) + _quad_tris(8, 11, 17, 14) + _quad_tris(11, 10, 16, 17) + _quad_tris(10, 7, 13, 16)
    t = np.asarray(tris, dtype=np.int32)

    _, _, segs = corte_plano.cortar_malha_no_plano(verts, t, 1.0)
    fe, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 6 and len(fe) == 1 and ab == [], f"segs={len(segs)} fe={len(fe)} ab={len(ab)}"
    assert abs(aneis._area(fe[0])) == pytest.approx(2.0, abs=1e-9)


def test_defeito_2a_malha_soldada_paredes_alturas_diferentes_padrao_bib0():
    """Malha 100% soldada (0 dup verts), 2 blocos de alturas 2 e 3:
    arestas verticais colineares (1,5) e (1,12) geram mesmo ponto XY com indices distintos e devem cancelar."""
    v = np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2],
            [2, 0, 0], [2, 1, 0], [2, 0, 3], [2, 1, 3],
            [1, 0, 3], [1, 1, 3],
        ],
        dtype=np.float64,
    )
    t = np.array(
        [
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [0, 7, 3], [0, 4, 7],
            [1, 9, 8], [1, 2, 9], [12, 10, 11], [12, 11, 13],
            [1, 8, 10], [1, 10, 12], [8, 9, 11], [8, 11, 10], [9, 2, 13], [9, 13, 11],
            [1, 6, 2], [1, 12, 6], [6, 12, 13],
        ],
        dtype=np.int32,
    )
    assert len(np.unique(v, axis=0)) == len(v)  # 100% soldada
    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.0)
    fe, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 12 and len(fe) == 1 and ab == [], f"segs={len(segs)} fe={len(fe)} ab={len(ab)}"
    assert abs(aneis._area(fe[0])) == pytest.approx(2.0, abs=1e-9)


def test_defeito_2b_blocos_justapostos_vertices_duplicados_nao_soldados():
    """Dois blocos justapostos com vertices duplicados nao soldados em x=1 devem cancelar face interna."""
    v, t = _combinar_malhas(
        _caixa_np(0.0, 0.0, 0.0, 1.0, 1.0, 2.0),
        _caixa_np(1.0, 0.0, 0.0, 2.0, 1.0, 2.0),
    )
    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.0)
    fe, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 12 and len(fe) == 1 and ab == [], f"segs={len(segs)} fe={len(fe)} ab={len(ab)}"
    assert abs(aneis._area(fe[0])) == pytest.approx(2.0, abs=1e-9)


def test_defeito_2c_sintetico_bib0_idx245_arestas_verticais_colineares():
    """Caso sintetico minimo (4 verts, 2 tris) derivado de bib_0 idx=245 (tris 44 e 308):
    base soldada em z=743.0 com arestas verticais de alturas distintas (750.64 e 754.14) e segmento de 4.87 mm."""
    dx, dy = 0.00052103863, -0.03099562
    for ox, oy in ((0.0, 0.0), (324566.5673745996, 7405486.645066726)):
        v = np.array(
            [
                [ox, oy, 743.0],
                [ox, oy, 750.6400000000001],
                [ox, oy, 754.14],
                [ox + dx, oy + dy, 750.6400000000001],
            ],
            dtype=np.float64,
        )
        t = np.array([[3, 0, 1], [3, 2, 0]], dtype=np.int32)
        assert len(np.unique(v, axis=0)) == 4
        _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 744.2)
        assert segs.shape == (0, 4), f"segmento 4.87mm nao cancelou (ox={ox}): segs={len(segs)}"
