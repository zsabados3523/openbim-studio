# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24q (T3): grade de 2o nivel apenas nas celulas densas (Opcao A).

Contrato publico e de ambiente (testado por efeito, sem acoplar a nomes internos):
- Variavel de ambiente `OBIM_VISIB_SUBGRADE`:
  - `"0"`: desliga a grade de 2o nivel (caminho legado = referencia do oraculo).
  - ausente ou `"1"`: liga a grade de 2o nivel.
  - Deve ser lida POR CHAMADA (nao cacheada no import; testes usam `monkeypatch.setenv`).
- Equivalencia geometrica (com C1 / T24p ja aplicado):
  - Mesmas polilinhas normalizadas (segmentos orientados, ordenados, colineares unidos com
    tolerancia `1e-9 m`; contagem igual e pontas a `<= 1e-9 m`).
  - Igualdade bit a bit onde a uniao exata garante (threads 1/2/4/8, determinismo 3 rodadas,
    cenas pequenas sem celula densa e cenas densas passando `a, b, d` originais a `_filtrar_e_recortar`).
- Desempenho relativo e memoria:
  - Cena com peca densa grande (~100k tris em 60x70 m com 20 caixas): ligada <= 35% do tempo da
    desligada (mediana de 2 rodadas), teste sob ~60 s, memoria sob 2 GB (tracemalloc e RSS).
  - Cena sem peca densa: ligada <= 1,05x do tempo da desligada (nao pode piorar).
- Limite de memoria da subgrade (3 pecas densas e 2 clusters separados por 50 m), determinismo
  bit a bit em 3 rodadas, entradas nao mutadas (inclusive somente-leitura) e 5 mutantes em memoria.

Nao editar este arquivo durante a implementacao da T24q.
"""
from __future__ import annotations

import math
import os
import statistics
import sys
import time
import tracemalloc
from unittest import mock

import numpy as np
import pytest

import obim_geometria.visib_mapa as visib_mapa
import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_faixas import _passagem_faixas_orientadas
from obim_geometria.visib_mapa import (
    _compactar_H,
    _filtrar_e_recortar,
    _mapa_z_conservador,
    _varrer_cels_triangulos,
)
from obim_geometria.visibilidade import _cull_tris, linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas as _cenas_t22a
from test_s06_t24j_motor_mapa_z_oraculo import CENAS as _CENAS_T24J

_TOL = 1e-9
_LIMITE_MEM_BYTES = 2 * 1024**3  # 2 GB
_F_CAIXA = np.array(
    [
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6],
        [3, 0, 4], [3, 4, 7],
    ],
    dtype=np.int64,
)


# ---------------------------------------------------------------------------
# Medicao de memoria (tracemalloc + RSS real quando disponivel)
# ---------------------------------------------------------------------------

def _rss_bytes() -> int:
    """Retorna RSS/VmHWM atual do processo em bytes (Linux/Unix; 0 se indisponivel)."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except OSError:
            pass
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(ru) if sys.platform == "darwin" else int(ru) * 1024
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Normalizacao de polilinhas (ordenar, unir colineares, tol 1e-9 m) + bit a bit
# ---------------------------------------------------------------------------

def _extrair_segmentos(pls: list[np.ndarray], tol: float = _TOL) -> np.ndarray:
    """Quebra polilinhas em segmentos 2D (K, 2, 2) orientados canonicamente."""
    partes: list[np.ndarray] = []
    for pl in pls:
        arr = np.asarray(pl, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < 2:
            continue
        segs = np.stack([arr[:-1], arr[1:]], axis=1)
        partes.append(segs)
    if not partes:
        return np.zeros((0, 2, 2), dtype=np.float64)
    segs = np.concatenate(partes, axis=0)
    d = segs[:, 1] - segs[:, 0]
    lens = np.hypot(d[:, 0], d[:, 1])
    segs = segs[lens > tol]
    if not len(segs):
        return np.zeros((0, 2, 2), dtype=np.float64)
    p0, p1 = segs[:, 0], segs[:, 1]
    trocar = (p0[:, 0] > p1[:, 0] + tol) | (
        (np.abs(p0[:, 0] - p1[:, 0]) <= tol) & (p0[:, 1] > p1[:, 1])
    )
    out = segs.copy()
    out[trocar, 0] = p1[trocar]
    out[trocar, 1] = p0[trocar]
    return out


def _fundir_grupo_direcao(
    segs: np.ndarray, ux: float, uy: float, orig: np.ndarray, tol: float
) -> list[np.ndarray]:
    """Dentro de segmentos quase paralelos a (ux, uy), agrupa colineares e une intervalos."""
    if len(segs) == 1:
        return [segs[0]]
    nx, ny = -uy, ux
    rel0 = segs[:, 0] - orig
    rel1 = segs[:, 1] - orig
    r0 = rel0[:, 0] * nx + rel0[:, 1] * ny
    r1 = rel1[:, 0] * nx + rel1[:, 1] * ny
    rmid = 0.5 * (r0 + r1)
    ord_r = np.argsort(rmid, kind="stable")
    segs = segs[ord_r]
    rel0 = rel0[ord_r]
    rel1 = rel1[ord_r]
    r0 = r0[ord_r]
    r1 = r1[ord_r]
    rmid = rmid[ord_r]

    fundidos: list[np.ndarray] = []
    n = len(segs)
    i = 0
    while i < n:
        j = i + 1
        # Coleta janela com rho proximo; depois valida distancia perpendicular real por par
        while j < n and (rmid[j] - rmid[j - 1]) <= 10.0 * tol:
            j += 1
        sub = segs[i:j]
        if len(sub) == 1:
            fundidos.append(sub[0])
            i = j
            continue
        # Sub-agrupamento exato por distancia perpendicular <= tol aos extremos da reta de referencia
        usados = [False] * len(sub)
        for a in range(len(sub)):
            if usados[a]:
                continue
            usados[a] = True
            s0 = sub[a]
            dv = s0[1] - s0[0]
            ln = math.hypot(float(dv[0]), float(dv[1]))
            u0x, u0y = float(dv[0]) / ln, float(dv[1]) / ln
            if u0x < -1e-9 or (abs(u0x) <= 1e-9 and u0y < 0.0):
                u0x, u0y = -u0x, -u0y
            n0x, n0y = -u0y, u0x
            base = s0[0]
            grupo = [s0]
            for b in range(a + 1, len(sub)):
                if usados[b]:
                    continue
                sb = sub[b]
                d0 = abs((sb[0, 0] - base[0]) * n0x + (sb[0, 1] - base[1]) * n0y)
                d1 = abs((sb[1, 0] - base[0]) * n0x + (sb[1, 1] - base[1]) * n0y)
                if d0 <= tol and d1 <= tol:
                    # Verifica tambem simetricamente com a reta de sb
                    dvb = sb[1] - sb[0]
                    lnb = math.hypot(float(dvb[0]), float(dvb[1]))
                    nbx, nby = -float(dvb[1]) / lnb, float(dvb[0]) / lnb
                    e0 = abs((s0[0, 0] - sb[0, 0]) * nbx + (s0[0, 1] - sb[0, 1]) * nby)
                    e1 = abs((s0[1, 0] - sb[0, 0]) * nbx + (s0[1, 1] - sb[0, 1]) * nby)
                    if e0 <= tol and e1 <= tol:
                        usados[b] = True
                        grupo.append(sb)
            if len(grupo) == 1:
                fundidos.append(grupo[0])
                continue
            # Projeta na direcao u0 preservando pontos originais dos extremos
            itens = []
            for gseg in grupo:
                t0 = float((gseg[0, 0] - base[0]) * u0x + (gseg[0, 1] - base[1]) * u0y)
                t1 = float((gseg[1, 0] - base[0]) * u0x + (gseg[1, 1] - base[1]) * u0y)
                if t0 <= t1:
                    itens.append((t0, t1, gseg[0], gseg[1]))
                else:
                    itens.append((t1, t0, gseg[1], gseg[0]))
            itens.sort(key=lambda x: x[0])
            c_lo, c_hi, p_lo, p_hi = itens[0]
            for t0, t1, q0, q1 in itens[1:]:
                if t0 <= c_hi + tol:
                    if t1 > c_hi:
                        c_hi, p_hi = t1, q1
                else:
                    fundidos.append(np.stack([p_lo, p_hi], axis=0))
                    c_lo, c_hi, p_lo, p_hi = t0, t1, q0, q1
            fundidos.append(np.stack([p_lo, p_hi], axis=0))
        i = j
    return fundidos


def _normalizar_polilinhas(pls: list[np.ndarray], tol: float = _TOL) -> np.ndarray:
    """Ordena segmentos e une colineares sobrepostos/adjacentes (tolerancia `tol`)."""
    segs = _extrair_segmentos(pls, tol=tol)
    if not len(segs):
        return segs
    orig = segs.reshape(-1, 2).min(axis=0)
    d = segs[:, 1] - segs[:, 0]
    ln = np.hypot(d[:, 0], d[:, 1])
    u = d / ln[:, None]
    flip = (u[:, 0] < -1e-9) | ((np.abs(u[:, 0]) <= 1e-9) & (u[:, 1] < 0.0))
    u[flip] = -u[flip]
    ang = np.arctan2(u[:, 1], u[:, 0])
    ang = np.where(ang < 0.0, ang + math.pi, ang)
    ang = np.where(ang >= math.pi - 1e-7, 0.0, ang)  # costura 0 ~ pi no mesmo extremo

    ord_a = np.argsort(ang, kind="stable")
    ang_s = ang[ord_a]
    segs_s = segs[ord_a]
    u_s = u[ord_a]

    tol_ang = 1e-6
    cortes = np.nonzero(np.diff(ang_s) > tol_ang)[0] + 1
    inicios = np.concatenate([[0], cortes])
    fins = np.concatenate([cortes, [len(ang_s)]])

    saida: list[np.ndarray] = []
    for i0, i1 in zip(inicios, fins):
        if i1 - i0 == 1:
            saida.append(segs_s[i0])
        else:
            u_med = u_s[i0]
            saida.extend(_fundir_grupo_direcao(segs_s[i0:i1], float(u_med[0]), float(u_med[1]), orig, tol))

    res = np.stack(saida, axis=0) if saida else np.zeros((0, 2, 2), dtype=np.float64)
    if not len(res):
        return res
    p0, p1 = res[:, 0], res[:, 1]
    trocar = (p0[:, 0] > p1[:, 0] + tol) | (
        (np.abs(p0[:, 0] - p1[:, 0]) <= tol) & (p0[:, 1] > p1[:, 1])
    )
    res[trocar, 0], res[trocar, 1] = p1[trocar].copy(), p0[trocar].copy()
    chaves = np.column_stack([res[:, 0, 0], res[:, 0, 1], res[:, 1, 0], res[:, 1, 1]])
    ord_f = np.lexsort((chaves[:, 3], chaves[:, 2], chaves[:, 1], chaves[:, 0]))
    return res[ord_f]


def _comparar_conjuntos_segs(sa: np.ndarray, sb: np.ndarray, tol: float, ctx: str) -> None:
    """Compara dois conjuntos ordenados de segmentos (N, 2, 2) dentro de `tol`."""
    assert len(sa) == len(sb), f"[{ctx}] contagem de segmentos normalizados difere: {len(sa)} != {len(sb)}"
    if not len(sa):
        return
    dif = np.abs(sa - sb).max(axis=(1, 2))
    ruins = np.nonzero(dif > tol)[0]
    if not len(ruins):
        return
    # Fallback para empates na ordenacao separados por <= tol: pareamento exato 1-para-1
    ra, rb = sa[ruins].reshape(-1, 4), sb[ruins].reshape(-1, 4)
    if len(ra) > 512:
        raise AssertionError(
            f"[{ctx}] {len(ra)} segmentos diferem alem de {tol:.1e} m (max={float(dif.max()):.3e} m)"
        )
    usados = np.zeros(len(rb), dtype=bool)
    for idx_a, va in enumerate(ra):
        dists = np.abs(rb - va).max(axis=1)
        dists[usados] = np.inf
        j = int(np.argmin(dists))
        if dists[j] > tol:
            raise AssertionError(
                f"[{ctx}] segmento sem par dentro de {tol:.1e} m (min_diff={float(dists[j]):.3e} m)"
            )
        usados[j] = True


def _canon_bit_a_bit(pls: list[np.ndarray]) -> list[np.ndarray]:
    """Ordena polilinhas deterministicamente preservando os bits exatos IEEE-754."""
    if not pls:
        return []
    arrs = [np.ascontiguousarray(p, dtype=np.float64) for p in pls]
    chaves = [(a.shape[0], *a.ravel().tolist()) for a in arrs]
    ordem = sorted(range(len(arrs)), key=chaves.__getitem__)
    return [arrs[i] for i in ordem]


def _assert_bit_a_bit(obt: list[list[np.ndarray]], ref: list[list[np.ndarray]], *, ctx: str = "") -> None:
    """Verifica igualdade bit a bit por peca (view uint64, na ordem canonica)."""
    assert len(obt) == len(ref), f"[{ctx}] num pecas difere: {len(obt)} != {len(ref)}"
    for i, (pa, pb) in enumerate(zip(obt, ref)):
        ca, cb = _canon_bit_a_bit(pa), _canon_bit_a_bit(pb)
        assert len(ca) == len(cb), f"[{ctx}] peca {i}: contagem polilinhas {len(ca)} != {len(cb)}"
        for j, (a, b) in enumerate(zip(ca, cb)):
            assert a.shape == b.shape, f"[{ctx}] peca {i} pl {j}: shape {a.shape} != {b.shape}"
            if not np.array_equal(a.view(np.uint64), b.view(np.uint64)):
                dif = float(np.abs(a - b).max()) if a.size else 0.0
                raise AssertionError(f"[{ctx}] peca {i} pl {j}: difere bit a bit (max={dif:.3e} m)")


def _assert_equivalente(
    obt: list[list[np.ndarray]],
    ref: list[list[np.ndarray]],
    *,
    tol: float = _TOL,
    exigir_bit_a_bit: bool = False,
    ctx: str = "",
) -> None:
    """Valida equivalencia normalizada (colineares unidos, tol 1e-9 m) e opcionalmente bit a bit."""
    assert len(obt) == len(ref), f"[{ctx}] num pecas difere: {len(obt)} != {len(ref)}"
    for i, (pa, pb) in enumerate(zip(obt, ref)):
        na = _normalizar_polilinhas(pa, tol=tol)
        nb = _normalizar_polilinhas(pb, tol=tol)
        _comparar_conjuntos_segs(na, nb, tol=tol, ctx=f"{ctx}/peca_{i}")
        la = float(np.hypot(*(na[:, 1] - na[:, 0]).T).sum()) if len(na) else 0.0
        lb = float(np.hypot(*(nb[:, 1] - nb[:, 0]).T).sum()) if len(nb) else 0.0
        assert abs(la - lb) <= max(tol * max(1, len(na)), 1e-7), (
            f"[{ctx}/peca_{i}] comprimento total difere: {la:.9f} != {lb:.9f}"
        )
    if exigir_bit_a_bit:
        _assert_bit_a_bit(obt, ref, ctx=ctx)


# ---------------------------------------------------------------------------
# Construtores de geometria sintetica
# ---------------------------------------------------------------------------

def _rz(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def _ry(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64)


def _caixa(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float,
    *, rot_z: float = 0.0, incl_y: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    cx, cy, cz = (x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    v = np.array(
        [[x, y, z] for z in (-0.5, 0.5) for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))],
        dtype=np.float64,
    ) * np.array([sx, sy, sz], dtype=np.float64)
    if rot_z or incl_y:
        v = v @ (_rz(rot_z) @ _ry(incl_y)).T
    return v + np.array([cx, cy, cz], dtype=np.float64), _F_CAIXA.copy()


def _esfera_uv(
    cx: float, cy: float, cz: float, r: float, nlat: int, nlon: int, *, rot_x: float = 0.65
) -> tuple[np.ndarray, np.ndarray]:
    """Esfera fechada com 2 * (nlat - 1) * nlon triangulos (nlat aneis internos + 2 polos)."""
    lats = np.linspace(-math.pi / 2.0, math.pi / 2.0, nlat + 1)[1:-1]
    lons = np.linspace(0.0, 2.0 * math.pi, nlon, endpoint=False)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    x = r * np.cos(la) * np.cos(lo)
    y = r * np.cos(la) * np.sin(lo)
    z = r * np.sin(la)
    v_mid = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    v = np.vstack([[[0.0, 0.0, -r]], v_mid, [[0.0, 0.0, r]]])
    if rot_x:
        c, s = math.cos(rot_x), math.sin(rot_x)
        v = v @ np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=np.float64).T
    v = v + np.array([cx, cy, cz], dtype=np.float64)
    nr = len(lats)
    j = np.arange(nlon, dtype=np.int64)
    j1 = (j + 1) % nlon
    tris = [np.column_stack([np.zeros(nlon, np.int64), 1 + j1, 1 + j])]
    for r_i in range(nr - 1):
        b0 = 1 + r_i * nlon
        b1 = 1 + (r_i + 1) * nlon
        tris.append(np.column_stack([b0 + j, b0 + j1, b1 + j1]))
        tris.append(np.column_stack([b0 + j, b1 + j1, b1 + j]))
    top = len(v) - 1
    b_top = 1 + (nr - 1) * nlon
    tris.append(np.column_stack([np.full(nlon, top, np.int64), b_top + j, b_top + j1]))
    return v, np.vstack(tris)


def _terreno(nx: int, ny: int, lado: float, amp: float, z0: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(nx + 1) * lado, np.arange(ny + 1) * lado)
    z = z0 + amp * np.sin(xs * 0.37) * np.cos(ys * 0.23)
    v = np.c_[xs.ravel(), ys.ravel(), z.ravel()]
    i = (np.arange(ny)[:, None] * (nx + 1) + np.arange(nx)[None, :]).ravel()
    t = np.stack([np.c_[i, i + 1, i + nx + 2], np.c_[i, i + nx + 2, i + nx + 1]], 1).reshape(-1, 3)
    return v, t.astype(np.int64)


def _juntar_malhas(*malhas: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    vs, ts, off = [], [], 0
    for v, t in malhas:
        vs.append(v)
        ts.append(t + off)
        off += len(v)
    return np.vstack(vs), np.vstack(ts)


def _cantos_dominio(lx: float, ly: float, z0: float = 0.0, z1: float = 1.0) -> list[tuple[np.ndarray, np.ndarray]]:
    return [
        _caixa(0.0, 0.0, z0, 0.8, 0.8, z1),
        _caixa(lx - 0.8, 0.0, z0, lx, 0.8, z1),
        _caixa(0.0, ly - 0.8, z0, 0.8, ly, z1),
        _caixa(lx - 0.8, ly - 0.8, z0, lx, ly, z1),
    ]


def _calcular_g(dx_dom: float, dy_dom: float) -> float:
    """Mesma formula de `g` de visibilidade.py (usada para construir casos em fronteiras de celula)."""
    g = max(0.002, math.sqrt(dx_dom * dy_dom / 5_500_000.0), (dx_dom + dy_dom) / 2_900_000.0)
    while (math.ceil(dx_dom / g) + 2) * (math.ceil(dy_dom / g) + 2) > 6_000_000:
        g *= 1.05
    return g


# ---------------------------------------------------------------------------
# (1) Cenas sinteticas obrigatorias do projeto
# ---------------------------------------------------------------------------

def _cena_peca_densa_80x80():
    """Peca densa (~20k tris em 0,7 m) em cena grande 80x80 m com caixas nos cantos."""
    return [
        _esfera_uv(40.0, 40.0, 1.0, 0.35, 100, 100),  # 19.800 tris
        _caixa(39.4, 39.6, 0.0, 40.6, 40.4, 0.8, rot_z=0.25),
        _caixa(39.8, 39.2, 1.1, 40.5, 40.8, 1.5, incl_y=0.15),
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_borda_e_fronteira_celula():
    """Peca densa encostada no canto (0,0) e na borda (80,80), + pares a <= 5e-7 m de fronteira de celula."""
    g = _calcular_g(80.0, 80.0)
    # Encosta esfera densa exatamente em x=0, y=0 (cx=r, cy=r)
    r = 0.30
    densa_canto = _esfera_uv(r, r, 1.0, r, 92, 92, rot_x=0.0)
    # Segunda esfera encostada na borda maxima (80, 80)
    densa_max = _esfera_uv(80.0 - r, 80.0 - r, 1.0, r, 90, 90, rot_x=0.4)
    # Pares oclusor/oclusado a <= 5e-7 m de fronteiras exatas k*g e k*g/4 perto da peca densa
    xf = round(10.0 / g) * g
    yf = round(10.0 / g) * g
    pecas = [
        densa_canto,
        densa_max,
        _caixa(0.0, 0.0, 0.0, 0.65, 0.65, 0.55),  # sob a esfera do canto (0,0)
        _caixa(79.35, 79.35, 0.0, 80.0, 80.0, 0.55),  # sob a esfera do canto (80,80)
        _caixa(xf - 0.15, yf - 0.15, 2.0, xf - 2e-7, yf + 0.15, 2.4),
        _caixa(xf + 2e-7, yf - 0.12, 0.0, xf + 0.15, yf + 0.12, 0.8),
        # Aresta levemente inclinada cruzando fronteira de celula a 3e-7 m do oclusor
        _caixa(xf - 0.08, yf - 0.08, 1.2, xf + 3e-7, yf + 0.08, 1.5, rot_z=0.002),
        *_cantos_dominio(80.0, 80.0),
    ]
    return pecas


def _cena_duas_pecas_densas_sobrepostas_z():
    """Duas pecas densas sobrepostas em Z diferentes (uma interpenetrada, outra acima)."""
    return [
        _esfera_uv(35.0, 42.0, 0.8, 0.35, 92, 92, rot_x=0.5),
        _esfera_uv(35.12, 42.08, 1.25, 0.35, 92, 92, rot_x=1.1),
        _esfera_uv(35.05, 42.02, 2.2, 0.22, 64, 64, rot_x=0.2),
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_triangulo_grande_atravessando_densa():
    """Triangulo grande (T_grd no mesmo cg + laje muito grande) atravessando peca densa."""
    # Tira estreita (dx=0.024 < g=0.034 -> fora do mapa Z conservador; dy=0.34 -> >400 subcelulas -> T_grd no mesmo cg!)
    tira_tgrd = _caixa(39.88, 39.83, 1.50, 39.904, 40.17, 1.62, incl_y=0.12)
    # Laje grande 6x6 m inclinada atravessando o lado direito da peca densa (vai para nivel mais grosso next_rem)
    laje_grande = _caixa(40.10, 37.0, 0.7, 46.10, 43.0, 1.3, incl_y=0.18, rot_z=0.12)
    return [
        _esfera_uv(40.0, 40.0, 1.0, 0.35, 92, 92, rot_x=0.6),
        tira_tgrd,
        laje_grande,
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_aresta_longa_atravessando_densa():
    """Aresta longa de parede (40 m) atravessando a peca densa de ponta a ponta."""
    return [
        _esfera_uv(40.0, 40.0, 1.5, 0.35, 92, 92, rot_x=0.55),
        _caixa(20.0, 39.94, 0.2, 60.0, 40.06, 0.9),  # parede 40 m visivel dos lados e ocluida no meio pela esfera
        _caixa(20.0, 40.14, 0.6, 60.0, 40.24, 1.4, incl_y=0.03),  # viga longa deslocada em Y cruzando a esfera
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_densa_escondida_atras_laje():
    """Peca densa totalmente escondida sob laje solida: resultado da peca 0 deve ser vazio."""
    return [
        _esfera_uv(40.0, 40.0, 0.8, 0.35, 92, 92, rot_x=0.6),
        _caixa(38.0, 38.0, 2.5, 42.0, 42.0, 2.8),  # laje cobrindo com folga
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_dois_clusters_50m():
    """Uma unica peca contendo 2 clusters densos separados por >50 m em X e Y."""
    c1 = _esfera_uv(10.0, 10.0, 1.0, 0.30, 74, 74, rot_x=0.5)  # ~10.8k tris
    c2 = _esfera_uv(60.0, 60.0, 1.0, 0.30, 74, 74, rot_x=0.9)  # ~10.8k tris
    peca_dupla = _juntar_malhas(c1, c2)
    return [
        peca_dupla,
        _caixa(9.5, 9.5, 0.0, 10.5, 10.5, 0.85, rot_z=0.2),
        _caixa(59.5, 59.5, 0.0, 60.5, 60.5, 0.85, rot_z=-0.3),
        *_cantos_dominio(80.0, 80.0),
    ]


def _cena_utm_densa():
    """Cena densa completa em coordenadas UTM georreferenciadas (500000, 7400000)."""
    off = np.array([500_000.0, 7_400_000.0, 750.0], dtype=np.float64)
    base = [
        _esfera_uv(40.0, 40.0, 1.2, 0.35, 90, 90, rot_x=0.6),
        _caixa(39.88, 39.88, 1.0, 40.12, 40.12, 1.35, incl_y=0.3),
        _caixa(20.0, 39.92, 0.2, 60.0, 40.08, 0.9),
        *_cantos_dominio(80.0, 80.0),
    ]
    return [(v + off, t.copy()) for v, t in base]


_CENAS_DENSAS = {
    "peca_densa_80x80": _cena_peca_densa_80x80,
    "borda_e_fronteira_celula": _cena_borda_e_fronteira_celula,
    "duas_pecas_densas_sobrepostas_z": _cena_duas_pecas_densas_sobrepostas_z,
    "triangulo_grande_atravessando_densa": _cena_triangulo_grande_atravessando_densa,
    "aresta_longa_atravessando_densa": _cena_aresta_longa_atravessando_densa,
    "densa_escondida_atras_laje": _cena_densa_escondida_atras_laje,
    "dois_clusters_50m": _cena_dois_clusters_50m,
    "utm_densa": _cena_utm_densa,
}

_CENAS_PEQUENAS_T22A = ["a00", "a05", "a17", "d0", "degenerada", "bordas", "tol_celula", "matar_m5_0", "georref"]
_CENAS_PEQUENAS_T24J = list(_CENAS_T24J.keys())


def _rodar(monkeypatch, pecas, *, subgrade: str | None, trabalhadores: int = 1):
    if subgrade is None:
        monkeypatch.delenv("OBIM_VISIB_SUBGRADE", raising=False)
    else:
        monkeypatch.setenv("OBIM_VISIB_SUBGRADE", subgrade)
    return linhas_visiveis_multi(pecas, trabalhadores=trabalhadores)


# ---------------------------------------------------------------------------
# Testes (1): Equivalencia ligado vs desligado e threads 1, 2, 4, 8
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", list(_CENAS_DENSAS.keys()))
def test_equivalencia_cenas_densas_sinteticas(nome, monkeypatch):
    pecas = _CENAS_DENSAS[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"densa/{nome}")
    if nome == "densa_escondida_atras_laje":
        assert ref[0] == [] and obt[0] == [], "peca densa escondida sob laje deve ter saida vazia"


@pytest.mark.parametrize("nome", _CENAS_PEQUENAS_T22A)
def test_equivalencia_cenas_pequenas_t22a(nome, monkeypatch):
    pecas = _cenas_t22a()[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"t22a/{nome}")


@pytest.mark.parametrize("nome", _CENAS_PEQUENAS_T24J)
def test_equivalencia_cenas_pequenas_t24j(nome, monkeypatch):
    pecas = _CENAS_T24J[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"t24j/{nome}")


@pytest.mark.parametrize(
    "nome",
    [
        "peca_densa_80x80",
        "duas_pecas_densas_sobrepostas_z",
        "triangulo_grande_atravessando_densa",
        "aresta_longa_atravessando_densa",
        "dois_clusters_50m",
        "utm_densa",
    ],
)
def test_threads_1_2_4_8_iguais_cenas_densas(nome, monkeypatch):
    pecas = _CENAS_DENSAS[nome]()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    base_1 = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(base_1, ref, exigir_bit_a_bit=True, ctx=f"threads/{nome}/t1_vs_ref")
    for n_trab in (2, 4, 8):
        obt_n = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=n_trab)
        _assert_equivalente(obt_n, base_1, exigir_bit_a_bit=True, ctx=f"threads/{nome}/t{n_trab}")


# ---------------------------------------------------------------------------
# Testes (2): Desempenho relativo (densa <= 35%, sem densa <= 1,05x) + memoria
# ---------------------------------------------------------------------------

def _cena_benchmark_densa_grande():
    """Esfera subdividida ~100k triangulos em cena 60x70 m com 20 caixas espalhadas."""
    esfera = _esfera_uv(30.0, 35.0, 1.0, 0.25, 224, 224, rot_x=0.65)  # 99.904 tris
    caixas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        _caixa(59.0, 69.0, 0.0, 60.0, 70.0, 1.0),
    ]
    for i in range(1, 19):
        x = 2.5 + (i * 3.1) % 54.0
        y = 2.5 + (i * 3.7) % 64.0
        caixas.append(_caixa(x, y, 0.0, x + 1.2, y + 1.0, 1.0 + 0.05 * i))
    return [esfera, *caixas]


def _cena_benchmark_sem_densa():
    """Cena media (~29k tris bem espalhados em 24x24 m, sem celulas densas) + 20 caixas."""
    terr = _terreno(120, 120, 0.2, 0.12, 0.0)
    caixas = [
        _caixa(
            1.0 + (i % 5) * 4.5, 1.0 + (i // 5) * 5.0, 0.1,
            2.5 + (i % 5) * 4.5, 2.2 + (i // 5) * 5.0, 1.5 + 0.1 * i,
        )
        for i in range(20)
    ]
    return [terr, *caixas]


def test_desempenho_peca_densa_grande_ate_35_porcento(monkeypatch):
    """Ligada leva <= 35% da desligada (mediana de 2 rodadas), < 60 s total, memoria < 2 GB."""
    pecas = _cena_benchmark_densa_grande()
    assert sum(len(t) for _, t in pecas) >= 95_000

    t_off: list[float] = []
    t_on: list[float] = []
    res_off = res_on = None

    tracemalloc.start()
    try:
        t_total0 = time.perf_counter()
        for r in range(2):
            t0 = time.perf_counter()
            res_off = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
            t_off.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            res_on = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
            t_on.append(time.perf_counter() - t0)
        t_total = time.perf_counter() - t_total0
        _, pico_tm = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    rss = _rss_bytes()
    assert res_off is not None and res_on is not None
    _assert_equivalente(res_on, res_off, exigir_bit_a_bit=True, ctx="bench_densa_100k")
    assert pico_tm < _LIMITE_MEM_BYTES, f"pico tracemalloc excedeu 2 GB: {pico_tm / 1e6:.1f} MB"
    assert rss < _LIMITE_MEM_BYTES, f"RSS excedeu 2 GB: {rss / 1e6:.1f} MB"
    assert t_total < 60.0, f"teste de benchmark excedeu 60 s ({t_total:.2f} s)"

    med_off = statistics.median(t_off)
    med_on = statistics.median(t_on)
    razao = med_on / med_off if med_off > 0.0 else math.inf
    assert med_on <= 0.35 * med_off, (
        f"2o nivel insuficiente na peca densa: ligada={med_on:.3f}s desligada={med_off:.3f}s "
        f"({razao * 100:.1f}% > 35.0%)"
    )


def test_desempenho_sem_peca_densa_nao_piora(monkeypatch):
    """Em cena sem peca densa, ligada leva <= 1,05x da desligada e devolve os mesmos bits."""
    pecas = _cena_benchmark_sem_densa()
    # Aquecimento
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx="bench_sem_densa")

    t_off: list[float] = []
    t_on: list[float] = []
    for _ in range(3):
        t0 = time.perf_counter()
        _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
        t_off.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
        t_on.append(time.perf_counter() - t0)

    med_off = statistics.median(t_off)
    med_on = statistics.median(t_on)
    razao = med_on / med_off if med_off > 0.0 else math.inf
    assert med_on <= 1.05 * med_off, (
        f"regressao em cena sem peca densa: ligada={med_on:.3f}s desligada={med_off:.3f}s "
        f"({razao:.3f}x > 1.05x)"
    )


# ---------------------------------------------------------------------------
# Testes (3): Contrato da variavel OBIM_VISIB_SUBGRADE (lida por chamada)
# ---------------------------------------------------------------------------

def test_contrato_env_lida_por_chamada(monkeypatch):
    """OBIM_VISIB_SUBGRADE='0' desliga; ausente ou '1' liga; alternancia por chamada funciona."""
    densa = _cena_peca_densa_80x80()
    pequena = _CENAS_T24J["casa_paredes_lajes_buracos"]()

    r_off_1 = _rodar(monkeypatch, densa, subgrade="0", trabalhadores=1)
    r_on_1 = _rodar(monkeypatch, densa, subgrade="1", trabalhadores=1)
    r_def = _rodar(monkeypatch, densa, subgrade=None, trabalhadores=1)
    r_off_2 = _rodar(monkeypatch, densa, subgrade="0", trabalhadores=1)

    _assert_equivalente(r_on_1, r_off_1, exigir_bit_a_bit=True, ctx="env_densa_1_vs_0")
    _assert_equivalente(r_def, r_on_1, exigir_bit_a_bit=True, ctx="env_densa_default_vs_1")
    _assert_equivalente(r_off_2, r_off_1, exigir_bit_a_bit=True, ctx="env_densa_0_repeat")

    p_off = _rodar(monkeypatch, pequena, subgrade="0", trabalhadores=1)
    p_def = _rodar(monkeypatch, pequena, subgrade=None, trabalhadores=1)
    _assert_equivalente(p_def, p_off, exigir_bit_a_bit=True, ctx="env_pequena_default_vs_0")


# ---------------------------------------------------------------------------
# Testes (4): Limite de memoria (3 pecas densas), determinismo 3x, imutabilidade
# ---------------------------------------------------------------------------

def test_memoria_subgrade_tres_pecas_densas(monkeypatch):
    """Cena com 3 pecas densas e cena com 2 clusters a 50 m ficam bem abaixo de 2 GB."""
    pecas_3 = [
        _esfera_uv(15.0, 20.0, 1.0, 0.32, 92, 92, rot_x=0.4),
        _esfera_uv(40.0, 40.0, 1.0, 0.32, 92, 92, rot_x=0.8),
        _esfera_uv(65.0, 60.0, 1.0, 0.32, 92, 92, rot_x=1.2),
        _caixa(14.5, 19.5, 0.0, 15.5, 20.5, 0.8),
        _caixa(39.5, 39.5, 0.0, 40.5, 40.5, 0.8),
        _caixa(64.5, 59.5, 0.0, 65.5, 60.5, 0.8),
        *_cantos_dominio(80.0, 80.0),
    ]
    ref_3 = _rodar(monkeypatch, pecas_3, subgrade="0", trabalhadores=1)
    ref_2c = _rodar(monkeypatch, _cena_dois_clusters_50m(), subgrade="0", trabalhadores=1)

    tracemalloc.start()
    try:
        obt_3 = _rodar(monkeypatch, pecas_3, subgrade="1", trabalhadores=1)
        obt_2c = _rodar(monkeypatch, _cena_dois_clusters_50m(), subgrade="1", trabalhadores=1)
        _, pico_tm = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    rss = _rss_bytes()
    _assert_equivalente(obt_3, ref_3, exigir_bit_a_bit=True, ctx="mem_3_densas")
    _assert_equivalente(obt_2c, ref_2c, exigir_bit_a_bit=True, ctx="mem_2_clusters_50m")
    assert pico_tm < 1024**3, f"pico tracemalloc da subgrade excedeu 1 GB: {pico_tm / 1e6:.1f} MB"
    assert rss < _LIMITE_MEM_BYTES, f"RSS excedeu 2 GB: {rss / 1e6:.1f} MB"


def test_determinismo_bit_a_bit_3_rodadas(monkeypatch):
    """3 rodadas consecutivas com subgrade ligada produzem exatamente os mesmos bits (1 e 4 threads)."""
    pecas = _cena_triangulo_grande_atravessando_densa()
    for n_trab in (1, 4):
        rodadas = [_rodar(monkeypatch, pecas, subgrade="1", trabalhadores=n_trab) for _ in range(3)]
        _assert_bit_a_bit(rodadas[1], rodadas[0], ctx=f"det_t{n_trab}_r1")
        _assert_bit_a_bit(rodadas[2], rodadas[0], ctx=f"det_t{n_trab}_r2")


def test_entradas_nao_mutadas_e_somente_leitura(monkeypatch):
    """Subgrade ligada nao altera arrays de entrada e aceita arrays somente-leitura."""
    pecas = _cena_aresta_longa_atravessando_densa()
    copias = [(v.copy(), t.copy()) for v, t in pecas]
    _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    for idx, ((v, t), (v0, t0)) in enumerate(zip(pecas, copias)):
        assert np.array_equal(v.view(np.uint64), v0.view(np.uint64)), f"verts peca {idx} mutados"
        assert np.array_equal(t, t0), f"tris peca {idx} mutados"

    ro_pecas = [(v.copy(), t.copy()) for v, t in copias]
    for v, t in ro_pecas:
        v.setflags(write=False)
        t.setflags(write=False)
    res_ro = _rodar(monkeypatch, ro_pecas, subgrade="1", trabalhadores=2)
    res_ref = _rodar(monkeypatch, copias, subgrade="0", trabalhadores=1)
    _assert_equivalente(res_ro, res_ref, exigir_bit_a_bit=True, ctx="somente_leitura")


# ---------------------------------------------------------------------------
# (5) Prototipo em memoria da Opcao A + 5 mutantes plausiveis
# ---------------------------------------------------------------------------

def _subgrade_prototipo_bloco(
    ec, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
    tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
    tol_z, d_eps, H_l,
    eobj, ecel, cont, ini_cel, tri_por_cel, bx0, by0, Wl, mn_x, mn_y, cg,
    *, modo_mutante: str | None, cont_pares: list[int],
):
    """Prototipo compacto em memoria da Opcao A sobre um lote de pares (eobj, ecel)."""
    lim_t = 24
    eps = abs(d_eps)

    def _emitir(pe, pt, a_loc=a, b_loc=b, d_loc=d):
        if len(pe):
            cont_pares[0] += len(pe)
            _filtrar_e_recortar(
                pe, pt, a_loc, b_loc, d_loc, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_l,
            )

    denso_cel = cont >= lim_t
    eh_denso = denso_cel[ecel]

    # Caminho normal (celulas nao densas; no mutante 'duplicar_pares', processa TODAS tambem no nivel grosso)
    mask_normal = np.ones(len(eobj), dtype=bool) if modo_mutante == "duplicar_pares" else ~eh_denso
    if np.any(mask_normal):
        eo_n, ec_n = eobj[mask_normal], ecel[mask_normal]
        nt_n = cont[ec_n]
        for p0, p1 in _fatias(nt_n, 200_000, chaves=eo_n):
            g3, kk = _rle_idx(nt_n[p0:p1])
            _emitir(eo_n[p0:p1][g3], tri_por_cel[ini_cel[ec_n[p0:p1]][g3] + kk])

    if not np.any(eh_denso):
        return

    # Celulas densas -> grade de 2o nivel
    eo_d, ec_d = eobj[eh_denso], ecel[eh_denso]
    cels_u = np.unique(ec_d)
    # Coleta triangulos unicos presentes nas celulas densas tocadas
    ts_parts = [tri_por_cel[ini_cel[c]:ini_cel[c] + cont[c]] for c in cels_u]
    t_densos = np.unique(np.concatenate(ts_parts))
    if not len(t_densos):
        return

    # Bbox do conjunto de celulas densas (em coordenadas do mundo)
    cy_d = by0 + (cels_u // Wl)
    cx_d = bx0 + (cels_u % Wl)
    sub_x0 = mn_x + float(cx_d.min()) * cg
    sub_x1 = mn_x + float(cx_d.max() + 1) * cg
    sub_y0 = mn_y + float(cy_d.min()) * cg
    sub_y1 = mn_y + float(cy_d.max() + 1) * cg
    dx_s = max(sub_x1 - sub_x0, cg)
    dy_s = max(sub_y1 - sub_y0, cg)
    area_d = float(len(cels_u)) * cg * cg
    cg_sub = max(1e-4, min(cg / 4.0, math.sqrt(area_d / max(len(t_densos) / 4.0, 1.0))))
    Ws = int(math.ceil(dx_s / cg_sub)) + 2
    Hs = int(math.ceil(dy_s / cg_sub)) + 2
    while Ws * Hs > 2_000_000:
        cg_sub *= 1.5
        Ws = int(math.ceil(dx_s / cg_sub)) + 2
        Hs = int(math.ceil(dy_s / cg_sub)) + 2

    folga = 0.0 if modo_mutante == "sem_folga_d_eps" else eps
    ix0, ix1, iy0, iy1 = _cel_caixa(
        tx0[t_densos] - folga, tx1[t_densos] + folga,
        ty0[t_densos] - folga, ty1[t_densos] + folga,
        sub_x0, sub_y0, cg_sub, Ws, Hs,
    )
    if modo_mutante == "perder_fronteira_subcelula":
        # Erro plausivel: perder triangulos na fronteira superior (ix1/iy1 subestimados em 1 celula)
        ix1 = np.maximum(ix0, ix1 - 1)
        iy1 = np.maximum(iy0, iy1 - 1)

    n_sub = (ix1 - ix0 + 1) * (iy1 - iy0 + 1)
    eh_grd = n_sub > 64
    t_grd = t_densos[eh_grd]
    t_fino_m = ~eh_grd

    # 1) T_grd fica no nivel cg (filtrado por celulas densas)
    if len(t_grd) and modo_mutante != "ignorar_T_grd":
        eo_u = np.unique(eo_d)
        # Pares (aresta densa, T_grd) com filtro rapido por bbox
        for g0 in range(0, len(t_grd), 256):
            tg = t_grd[g0:g0 + 256]
            pe_g = np.repeat(eo_u, len(tg))
            pt_g = np.tile(tg, len(eo_u))
            _emitir(pe_g, pt_g)

    # 2) T_fino vai para a subgrade cg_sub
    if not np.any(t_fino_m):
        return
    t_fino = t_densos[t_fino_m]
    tobj_s, tcel_s = _expandir_celulas(ix0[t_fino_m], ix1[t_fino_m], iy0[t_fino_m], iy1[t_fino_m], Ws)
    tobj_s = t_fino[tobj_s]
    ord_ts = np.argsort(tcel_s, kind="stable")
    tri_sub = tobj_s[ord_ts]
    cel_sub_ord = tcel_s[ord_ts]
    ncel_s = Ws * Hs
    cont_s = np.bincount(cel_sub_ord, minlength=ncel_s)
    ini_s = np.cumsum(cont_s) - cont_s
    sub_tzmax = np.full(ncel_s, -np.inf)
    np.maximum.at(sub_tzmax, cel_sub_ord, tzmax[tri_sub])

    eo_u = np.unique(eo_d)
    # Recorta cada aresta a bbox densa [sub_x0, sub_x1] x [sub_y0, sub_y1] (com folga) para gerar subsegmentos
    p0x, p0y = a[eo_u, 0], a[eo_u, 1]
    ddx, ddy = d[eo_u, 0], d[eo_u, 1]
    t_lo = np.zeros(len(eo_u), dtype=np.float64)
    t_hi = np.ones(len(eo_u), dtype=np.float64)
    pad_box = 0.0 if modo_mutante == "sem_folga_d_eps" else (eps + 1e-9)
    for comp_d, comp_p, lo_b, hi_b in (
        (ddx, p0x, sub_x0 - pad_box, sub_x1 + pad_box),
        (ddy, p0y, sub_y0 - pad_box, sub_y1 + pad_box),
    ):
        nz = np.abs(comp_d) > 1e-15
        fora = (~nz) & ((comp_p < lo_b) | (comp_p > hi_b))
        t_hi = np.where(fora, -1.0, t_hi)
        inv = np.where(nz, 1.0 / np.where(nz, comp_d, 1.0), 0.0)
        ta = (lo_b - comp_p) * inv
        tb = (hi_b - comp_p) * inv
        t_lo = np.where(nz, np.maximum(t_lo, np.minimum(ta, tb)), t_lo)
        t_hi = np.where(nz, np.minimum(t_hi, np.maximum(ta, tb)), t_hi)
    ok_clip = t_hi >= t_lo - 1e-12
    if not np.any(ok_clip):
        return
    eo_c = eo_u[ok_clip]
    t_lo = np.clip(t_lo[ok_clip], 0.0, 1.0)
    t_hi = np.clip(t_hi[ok_clip], 0.0, 1.0)
    a_clip = a[eo_c] + t_lo[:, None] * d[eo_c]
    d_clip = (t_hi - t_lo)[:, None] * d[eo_c]

    step_s = 0.999 * cg_sub
    span_s = np.maximum(np.abs(d_clip[:, 0]), np.abs(d_clip[:, 1]))
    nsub_s = np.maximum(1, np.ceil(span_s / step_s).astype(np.int64))

    # Mutante 4: clip errado da bbox densa (passa extremos recortados a_clip/d_clip em vez de a/b/d originais)
    a_pass, b_pass, d_pass = a, b, d
    if modo_mutante == "clip_bbox_errado":
        a_pass = a.copy()
        b_pass = b.copy()
        d_pass = d.copy()
        a_pass[eo_c] = a_clip
        b_pass[eo_c] = a_clip + d_clip
        d_pass[eo_c] = d_clip

    for e0, e1 in _fatias(nsub_s, 400_000):
        ec_s = eo_c[e0:e1]
        s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
            a_clip[e0:e1], d_clip[e0:e1], nsub_s[e0:e1], sub_x0, sub_y0, cg_sub, Ws, Hs
        )
        sobj, scel = _expandir_celulas(sx0, sx1, sy0, sy1, Ws)
        ok_sc = sub_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
        eo_s = ec_s[s_l[sobj[ok_sc]]]
        ecel_s = scel[ok_sc]
        if not len(eo_s):
            continue
        if modo_mutante != "duplicar_pares":
            ch_s = _dedup_int64(eo_s.astype(np.int64) * ncel_s + ecel_s)
            eo_s = ch_s // ncel_s
            ecel_s = ch_s % ncel_s
        nt_s = cont_s[ecel_s]
        nz = nt_s > 0
        eo_s, ecel_s, nt_s = eo_s[nz], ecel_s[nz], nt_s[nz]
        for p0, p1 in _fatias(nt_s, 200_000, chaves=eo_s):
            g3, kk = _rle_idx(nt_s[p0:p1])
            _emitir(
                eo_s[p0:p1][g3],
                tri_sub[ini_s[ecel_s[p0:p1]][g3] + kk],
                a_loc=a_pass, b_loc=b_pass, d_loc=d_pass,
            )


def _rodar_prototipo_subgrade(pecas, *, modo_mutante: str | None = None):
    """Executa linhas_visiveis_multi substituindo apenas o laco `while` pelo prototipo da Opcao A."""
    cont_pares = [0]

    def _vis_proto(P, Tw, a, b, ea, eb, tol_z, d_eps, min_len, prep=None, memo=None):
        A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, area2 = (
            prep if prep is not None else _preparar_triangulos(P, Tw)
        )
        mn_x = float(min(a[:, 0].min(), b[:, 0].min(), tx0.min() if len(A) else math.inf))
        mn_y = float(min(a[:, 1].min(), b[:, 1].min(), ty0.min() if len(A) else math.inf))
        mx_x = float(max(a[:, 0].max(), b[:, 0].max(), tx1.max() if len(A) else -math.inf))
        mx_y = float(max(a[:, 1].max(), b[:, 1].max(), ty1.max() if len(A) else -math.inf))
        dx_dom = max(mx_x - mn_x, 0.0)
        dy_dom = max(mx_y - mn_y, 0.0)
        g = _calcular_g(dx_dom, dy_dom)
        z_full, W, H = _mapa_z_conservador(
            A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, mx_x, mx_y, g
        )
        tx0i, tx1i, ty0i, ty1i = _cel_caixa(tx0, tx1, ty0, ty1, mn_x, mn_y, g, W, H)
        idx_s = np.nonzero((tx1i - tx0i + 1) * (ty1i - ty0i + 1) <= 25)[0]
        tri_keep = np.ones(len(A), bool)
        zf_flat = z_full.ravel()
        tri_keep[idx_s] = False
        for k0 in range(0, len(idx_s), 50_000):
            sl = idx_s[k0:k0 + 50_000]
            tobj, tcel = _expandir_celulas(tx0i[sl], tx1i[sl], ty0i[sl], ty1i[sl], W)
            np.logical_or.at(tri_keep, sl[tobj], tzmax[sl[tobj]] >= zf_flat[tcel] - 1e-9)
        kept_idx = np.nonzero(tri_keep)[0]
        d = b - a
        step_g = 0.999 * g
        nsub_g = np.maximum(1, np.ceil(np.maximum(np.abs(d[:, 0]), np.abs(d[:, 1])) / step_g).astype(np.int64))
        H_l = []
        ek_mask = np.zeros(len(a), bool)
        for e0, e1 in _fatias(nsub_g, 500_000):
            s_l, t0_s, t1_s, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
                a[e0:e1], d[e0:e1], nsub_g[e0:e1], mn_x, mn_y, g, W, H
            )
            s_id = s_l + e0
            z_min_4 = np.minimum(
                np.minimum(z_full[sy0, sx0], z_full[sy0, sx1]), np.minimum(z_full[sy1, sx0], z_full[sy1, sx1])
            )
            sub_keep = np.maximum(sa[:, 2], sb[:, 2]) >= z_min_4 - tol_z
            ek_mask[s_id[sub_keep]] = True
            hid = ~sub_keep
            if np.any(hid):
                starts, ends = hid.copy(), hid.copy()
                starts[1:] &= (~hid[:-1]) | (s_id[1:] != s_id[:-1])
                ends[:-1] &= (~hid[1:]) | (s_id[:-1] != s_id[1:])
                H_l.append((s_id[starts], t0_s[starts], t1_s[ends]))
        ek_idx = np.nonzero(ek_mask)[0]
        n_ref = len(kept_idx)
        if len(ek_idx) and len(kept_idx):
            kept_idx = _cull_tris(kept_idx, a[ek_idx], b[ek_idx], tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
        ex0 = np.minimum(a[:, 0], b[:, 0])
        ex1 = np.maximum(a[:, 0], b[:, 0])
        ey0 = np.minimum(a[:, 1], b[:, 1])
        ey1 = np.maximum(a[:, 1], b[:, 1])
        ezmin = np.minimum(a[:, 2], b[:, 2])
        ctx = (A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, ea, eb, ex0, ex1, ey0, ey1, ezmin)
        rem_t = _passagem_faixas_orientadas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z, d_eps, ctx, H_l)
        cg = g
        nt_all = len(A)
        while len(rem_t) and len(ek_idx):
            Wc = int(math.ceil(dx_dom / cg)) + 2
            Hc = int(math.ceil(dy_dom / cg)) + 2
            ncel = Wc * Hc
            lim_c = min(400, max(50, 3_000_000 // max(len(rem_t), n_ref)))
            if ncel <= lim_c:
                cand_m = np.ones(len(rem_t), bool)
            else:
                tx0c, tx1c, ty0c, ty1c = _cel_caixa(
                    tx0[rem_t], tx1[rem_t], ty0[rem_t], ty1[rem_t], mn_x, mn_y, cg, Wc, Hc
                )
                cand_m = (
                    (ty1c - ty0c + 1 <= lim_c) & (tx1c - tx0c + 1 <= lim_c)
                    & (area2[rem_t] <= lim_c * cg * cg)
                )
            cand = rem_t[cand_m]
            next_rem = [rem_t[~cand_m]]
            if len(cand):
                cov, loc_s, iy_s, ix0_s, ix1_s = _varrer_cels_triangulos(
                    cand, nx_, ny_, cc_, tx0, tx1, ty0, ty1, mn_x, mn_y, cg, Wc, Hc
                )
                keep_c = (cov <= lim_c) | (ncel <= lim_c)
                next_rem.append(cand[~keep_c])
                ok_s = keep_c[loc_s]
                if np.any(ok_s):
                    t_s = cand[loc_s[ok_s]]
                    iy_s, ix0_s, ix1_s = iy_s[ok_s], ix0_s[ok_s], ix1_s[ok_s]
                    w_s = ix1_s - ix0_s + 1
                    step_c = 0.999 * cg
                    span_e = np.maximum(np.abs(d[ek_idx, 0]), np.abs(d[ek_idx, 1]))
                    nsub_c = np.maximum(1, np.ceil(span_e / step_c).astype(np.int64))
                    for t0, t1 in _fatias(w_s, 2_000_000):
                        g_s, dx_s = _rle_idx(w_s[t0:t1])
                        tobj = t_s[t0:t1][g_s]
                        tcel = iy_s[t0:t1][g_s] * Wc + ix0_s[t0:t1][g_s] + dx_s
                        if cg == g:
                            ok_tc = tzmax[tobj] >= zf_flat[tcel] - 1e-9
                            tobj, tcel = tobj[ok_tc], tcel[ok_tc]
                        if not len(tobj):
                            continue
                        t_iy, t_ix = tcel // Wc, tcel % Wc
                        bx0, by0 = int(t_ix.min()), int(t_iy.min())
                        Wl = int(t_ix.max()) - bx0 + 1
                        Hl = int(t_iy.max()) - by0 + 1
                        ncel_l = Wl * Hl
                        tcel = (t_iy - by0) * Wl + (t_ix - bx0)
                        ord_t = np.argsort(tcel, kind="stable")
                        tri_por_cel = tobj[ord_t]
                        cel_ord = tcel[ord_t]
                        cont = np.bincount(cel_ord, minlength=ncel_l)
                        ini_cel = np.cumsum(cont) - cont
                        cell_tzmax = np.full(ncel_l, -np.inf)
                        np.maximum.at(cell_tzmax, cel_ord, tzmax[tri_por_cel])
                        for e0, e1 in _fatias(nsub_c, 400_000):
                            ec = ek_idx[e0:e1]
                            s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = _subseg_cels(
                                a[ec], d[ec], nsub_c[e0:e1], mn_x, mn_y, cg, Wc, Hc
                            )
                            sx0 = np.maximum(sx0, bx0); sx1 = np.minimum(sx1, bx0 + Wl - 1)
                            sy0 = np.maximum(sy0, by0); sy1 = np.minimum(sy1, by0 + Hl - 1)
                            okb = (sx1 >= sx0) & (sy1 >= sy0)
                            s_l, sa, sb = s_l[okb], sa[okb], sb[okb]
                            sobj, scel = _expandir_celulas(
                                sx0[okb] - bx0, sx1[okb] - bx0, sy0[okb] - by0, sy1[okb] - by0, Wl
                            )
                            ok_sc = cell_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
                            eobj = ec[s_l[sobj[ok_sc]]]
                            ecel = scel[ok_sc]
                            if not len(eobj):
                                continue
                            ch_ec = _dedup_int64(eobj.astype(np.int64) * ncel_l + ecel)
                            eobj = ch_ec // ncel_l
                            ecel = ch_ec % ncel_l
                            nz = cont[ecel] > 0
                            eobj, ecel = eobj[nz], ecel[nz]
                            if not len(eobj):
                                continue
                            _subgrade_prototipo_bloco(
                                ec, a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
                                tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all,
                                tol_z, d_eps, H_l,
                                eobj, ecel, cont, ini_cel, tri_por_cel, bx0, by0, Wl, mn_x, mn_y, cg,
                                modo_mutante=modo_mutante, cont_pares=cont_pares,
                            )
            rem_t = np.concatenate(next_rem)
            cg *= 4.0
        He, Hlo, Hhi = _compactar_H(H_l, limpar=True)
        sem = np.ones(len(a), bool)
        sem[He] = False
        idx_sem = np.nonzero(sem)[0]
        V_l = [(idx_sem, np.zeros(len(idx_sem)), np.ones(len(idx_sem)))]
        if len(He):
            novo = np.concatenate([[True], He[1:] != He[:-1]])
            ultimo = np.concatenate([He[1:] != He[:-1], [True]])
            ini_t = np.where(novo, 0.0, np.concatenate([[0.0], Hhi[:-1]]))
            fim_t = Hhi[ultimo]
            gap = Hlo - ini_t > 1e-9
            gl = fim_t < 1.0 - 1e-9
            V_l.append((He[gap], ini_t[gap], Hlo[gap]))
            V_l.append((He[ultimo][gl], fim_t[gl], np.ones(int(gl.sum()))))
        pe_, t0_, t1_ = (np.concatenate(x) for x in zip(*V_l))
        s0 = a[pe_, :2] + t0_[:, None] * d[pe_, :2]
        s1 = a[pe_, :2] + t1_[:, None] * d[pe_, :2]
        ok2 = np.hypot(*(s1 - s0).T) > min_len
        return np.stack([s0[ok2], s1[ok2]], axis=1)

    with mock.patch.object(vis, "_visibilidade_hibrida", _vis_proto):
        res = linhas_visiveis_multi(pecas, trabalhadores=1)
    return res, cont_pares[0]


def _cena_mutante_d_eps():
    """Cena cirurgica para detectar ausencia de folga `d_eps` em fronteiras de subcelula.

    A esfera densa fica ABAIXO (z in [0, 0.3]) para criar celulas densas (~40 tris/celula -> cg_sub = g/4)
    sem ocluir as barras acima (z = 1.0). Placas pequenas (z = 2.0) terminam a 2e-7 m antes de fronteiras
    exatas k*(g/16), enquanto barras quase verticais (z = 1.0) cruzam `xf` longe abaixo e passam em
    `x > xf` (subcelula adjacente) a ~4e-7 m (< d_eps = 1e-6 m) em toda a faixa de Y da placa.
    """
    g = _calcular_g(80.0, 80.0)
    # Esfera ~8k tris em raio 0.42 m (z em [0.0, 0.30]) -> celulas densas com ~35-55 tris/celula -> cg_sub = g/4
    v_esf, t_esf = _esfera_uv(40.0, 40.0, 0.15, 0.42, 64, 64, rot_x=0.5)
    v_esf[:, 2] = 0.15 + 0.35 * (v_esf[:, 2] - 0.15)  # achata em Z para ficar abaixo de z=0.35
    pecas = [(v_esf, t_esf), *_cantos_dominio(80.0, 80.0)]
    x_base = math.floor(40.0 / g) * g
    y_base = math.floor(40.0 / g) * g
    for k in range(1, 17):
        xf = x_base + k * (g / 16.0)
        yf = y_base + 0.004 * (k % 4)
        # Placa oclusora pequena (< g -> fora do mapa Z conservador), terminando em x = xf - 2e-7
        # Posicionada em y in [yf + 0.014, yf + 0.022], bem acima do cruzamento da barra em y = yf + 0.0028
        pecas.append(_caixa(xf - 0.004, yf + 0.014, 1.9, xf - 2e-7, yf + 0.022, 2.05))
        # Painel vertical fino (z in [0.9, 1.1], acima da esfera) indo de (xf - 5e-7, yf - 0.025)
        # ate (xf + 4e-7, yf + 0.025): ex0 <= tx1 passa o filtro AABB, e em y in [yf + 0.014, yf + 0.022]
        # todo subsegmento esta estritamente em x > xf (subcelula direita) a ~4-5.5e-7 m (< d_eps) da placa.
        v_bar = np.array(
            [
                [xf - 5e-7, yf - 0.025, 1.1],
                [xf + 4e-7, yf + 0.025, 1.1],
                [xf - 5e-7, yf - 0.025, 0.9],
                [xf + 4e-7, yf + 0.025, 0.9],
            ],
            dtype=np.float64,
        )
        t_bar = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        pecas.append((v_bar, t_bar))
    return pecas


def test_mutante_01_perder_triangulos_fronteira_subcelula(monkeypatch):
    """Mutante 1: off-by-one nas fronteiras de subcelula (ix1/iy1 - 1) perde triangulos densos."""
    pecas = _cena_peca_densa_80x80()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m01_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m01_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="perder_fronteira_subcelula")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m01_mutante")


def test_mutante_02_sem_folga_d_eps(monkeypatch):
    """Mutante 2: indexar subgrade sem folga `abs(d_eps)` perde oclusao a <= 5e-7 m de fronteira."""
    pecas = _cena_mutante_d_eps()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m02_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m02_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="sem_folga_d_eps")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m02_mutante")


def test_mutante_03_ignorar_T_grd_grande(monkeypatch):
    """Mutante 3: descartar triangulos `T_grd` (> 64 subcelulas) perde oclusao da placa atravessando a densa."""
    pecas = _cena_triangulo_grande_atravessando_densa()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m03_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m03_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="ignorar_T_grd")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m03_mutante")


def test_mutante_04_clip_errado_bbox_densa(monkeypatch):
    """Mutante 4: recortar aresta longa alterando `a, b, d` (t errado) corrompe os intervalos escondidos."""
    pecas = _cena_aresta_longa_atravessando_densa()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m04_real")

    limpo, _ = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m04_proto_limpo")

    mut, _ = _rodar_prototipo_subgrade(pecas, modo_mutante="clip_bbox_errado")
    with pytest.raises(AssertionError):
        _assert_equivalente(mut, ref, exigir_bit_a_bit=False, ctx="m04_mutante")


def test_mutante_05_duplicar_pares(monkeypatch):
    """Mutante 5: duplicar pares (processar celula densa nos dois niveis e sem dedup) preserva saida mas explode pares."""
    pecas = _cena_peca_densa_80x80()
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt_real = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    _assert_equivalente(obt_real, ref, exigir_bit_a_bit=True, ctx="m05_real")

    limpo, pares_limpo = _rodar_prototipo_subgrade(pecas, modo_mutante=None)
    _assert_equivalente(limpo, ref, exigir_bit_a_bit=True, ctx="m05_proto_limpo")

    mut, pares_mut = _rodar_prototipo_subgrade(pecas, modo_mutante="duplicar_pares")
    # Corretude: C1 + dedup de _filtrar_e_recortar tornam duplicacao idempotente na saida
    _assert_equivalente(mut, ref, exigir_bit_a_bit=True, ctx="m05_mutante_idempotencia")

    # Deteccao: o mutante que duplica pares ultrapassa com folga o orcamento de pares do prototipo limpo
    def _assert_sem_explosao_pares(n_pares: int, n_base: int) -> None:
        assert n_pares <= int(1.25 * n_base), f"duplicacao de pares detectada: {n_pares} > 1.25 * {n_base}"

    _assert_sem_explosao_pares(pares_limpo, pares_limpo)
    with pytest.raises(AssertionError):
        _assert_sem_explosao_pares(pares_mut, pares_limpo)
