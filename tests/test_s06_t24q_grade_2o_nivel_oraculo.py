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

import hashlib
import math
import os
import pickle
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
    _arestas_candidatas,
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
from test_s06_t24j_motor_mapa_z_oraculo_b import CENAS as _CENAS_T24J  # noqa: F401

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
