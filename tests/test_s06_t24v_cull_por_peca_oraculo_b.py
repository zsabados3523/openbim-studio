# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24v_cull_por_peca_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc
import glob
import hashlib
import math
import os
import pickle
import statistics
import threading
import time
from unittest import mock
import numpy as np
import pytest
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
    _subgrade_celulas_densas,
    _varrer_cels_triangulos,
)
from obim_geometria.visibilidade import (
    _dedup_triangulos,
    _limpar_malha,
    _resolver_trabalhadores_auto,
    _validar_trabalhadores,
    linhas_visiveis_multi,
)
from test_s06_t24v_cull_por_peca_oraculo import _F_CAIXA, _MARGEM_PROPRIEDADE, _calc_mapa_z_ref, _cull_tris_ref, _visibilidade_hibrida_ref  # noqa: F401



def _linhas_visiveis_multi_ref(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
    trabalhadores: int | None = 1,
) -> list[list[np.ndarray]]:
    """Referencia fiel de `linhas_visiveis_multi` pre-T24v."""
    n_trab = _validar_trabalhadores(trabalhadores)
    pecas_l = list(pecas)
    if not pecas_l:
        return []
    limpas = [_limpar_malha(v, t) for v, t in pecas_l]
    v_parts, offsets, v_off = [], [], 0
    for item in limpas:
        offsets.append(None if item is None else (v_off, item[1]))
        if item is not None:
            v_parts.append(item[0])
            v_off += len(item[0])
    if not v_parts:
        return [[] for _ in pecas_l]
    V_all = v_parts[0] if len(v_parts) == 1 else np.vstack(v_parts)
    _, idx, inv = np.unique(
        np.round(V_all / 1e-6).astype(np.int64), axis=0, return_index=True, return_inverse=True
    )
    P, inv_flat = V_all[idx], inv.ravel()
    cands, tw_oks = [None] * len(pecas_l), []
    for i, off_t in enumerate(offsets):
        if off_t is None:
            continue
        Tw_i = _dedup_triangulos(inv_flat[off_t[1] + off_t[0]])
        if len(Tw_i) == 0:
            continue
        a, b, ang, silh, Tw_ok_i, ea, eb = _arestas_candidatas(P, Tw_i)
        if len(Tw_ok_i):
            tw_oks.append(Tw_ok_i)
        m = ((ang >= angulo_graus) | silh) & (np.hypot(*(b - a)[:, :2].T) > min_len)
        if np.any(m):
            cands[i] = (a[m], b[m], ea[m], eb[m])
    if not tw_oks:
        return [[] for _ in pecas_l]
    ativos = [(i, c) for i, c in enumerate(cands) if c is not None]
    if not ativos:
        return [[] for _ in pecas_l]
    Tw_comb = tw_oks[0] if len(tw_oks) == 1 else _dedup_triangulos(np.vstack(tw_oks))
    prep = _preparar_triangulos(P, Tw_comb)
    memo = {}
    if n_trab is None:
        n_trab = _resolver_trabalhadores_auto(len(ativos), len(Tw_comb))
    res: list[list[np.ndarray]] = [[] for _ in pecas_l]
    if n_trab == 1:
        for i, c in ativos:
            res[i] = list(_visibilidade_hibrida_ref(P, Tw_comb, *c, tol_z, -1e-6, min_len, prep=prep, memo=memo))
        return res
    with ThreadPoolExecutor(max_workers=n_trab) as pool:
        try:
            futs = [
                (i, pool.submit(_visibilidade_hibrida_ref, P, Tw_comb, *c, tol_z, -1e-6, min_len, prep=prep, memo=memo))
                for i, c in ativos
            ]
            for i, fut in futs:
                res[i] = list(fut.result())
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return res


# ---------------------------------------------------------------------------
# Comparadores bit a bit, SHA-256 e verificacao da propriedade de superconjunto
# ---------------------------------------------------------------------------

def _canon_bit_a_bit(pls: list[np.ndarray]) -> list[np.ndarray]:
    if not pls:
        return []
    arrs = [np.ascontiguousarray(p, dtype=np.float64) for p in pls]
    chaves = [(a.shape[0], *a.ravel().tolist()) for a in arrs]
    ordem = sorted(range(len(arrs)), key=chaves.__getitem__)
    return [arrs[i] for i in ordem]


def _assert_bit_a_bit(
    obt: list[list[np.ndarray]],
    ref: list[list[np.ndarray]],
    *,
    ordem_exata: bool = False,
    ctx: str = "",
) -> None:
    """Verifica igualdade bit a bit (view uint64) por peca."""
    assert len(obt) == len(ref), f"[{ctx}] num pecas difere: {len(obt)} != {len(ref)}"
    for i, (pa, pb) in enumerate(zip(obt, ref)):
        ca = [np.ascontiguousarray(p, dtype=np.float64) for p in pa] if ordem_exata else _canon_bit_a_bit(pa)
        cb = [np.ascontiguousarray(p, dtype=np.float64) for p in pb] if ordem_exata else _canon_bit_a_bit(pb)
        assert len(ca) == len(cb), f"[{ctx}] peca {i}: contagem polilinhas {len(ca)} != {len(cb)}"
        for j, (a, b) in enumerate(zip(ca, cb)):
            assert a.shape == b.shape, f"[{ctx}] peca {i} pl {j}: shape {a.shape} != {b.shape}"
            if not np.array_equal(a.view(np.uint64), b.view(np.uint64)):
                dif = float(np.abs(a - b).max()) if a.size else 0.0
                raise AssertionError(f"[{ctx}] peca {i} pl {j}: difere bit a bit (max={dif:.3e} m)")


def _sha_polilinhas(res: list[list[np.ndarray]]) -> str:
    """SHA-256 canonico dos bits IEEE-754 das polilinhas por peca."""
    h = hashlib.sha256()
    h.update(f"n={len(res)}\n".encode("ascii"))
    for i, pls in enumerate(res):
        can = _canon_bit_a_bit(pls)
        h.update(f"p={i}:{len(can)}\n".encode("ascii"))
        for arr in can:
            h.update(f"{arr.shape}\n".encode("ascii"))
            h.update(arr.view(np.uint64).tobytes())
    return h.hexdigest()


def _comprimento_total(pls: list[np.ndarray]) -> float:
    total = 0.0
    for pl in pls:
        arr = np.asarray(pl, dtype=np.float64)
        if len(arr) >= 2:
            d = np.diff(arr, axis=0)
            total += float(np.hypot(d[:, 0], d[:, 1]).sum())
    return total


def _validar_conjunto_mantido(
    kept_prod: np.ndarray,
    kept_pre: np.ndarray,
    ea_: np.ndarray,
    eb_: np.ndarray,
    tx0: np.ndarray,
    tx1: np.ndarray,
    ty0: np.ndarray,
    ty1: np.ndarray,
    mn_x: float,
    mn_y: float,
    dx_dom: float,
    dy_dom: float,
    *,
    marg_caixa: float = _MARGEM_PROPRIEDADE,
    ctx: str = "",
) -> np.ndarray:
    """Valida que `kept_prod` e valido e contem todo tri de `_cull_tris_ref` na caixa dilatada."""
    kp = np.asarray(kept_prod)
    assert kp.ndim == 1, f"[{ctx}] kept_prod nao e 1D: shape={kp.shape}"
    assert np.issubdtype(kp.dtype, np.integer), f"[{ctx}] kept_prod nao e inteiro: {kp.dtype}"
    if len(kp):
        assert int(kp.min()) >= 0 and int(kp.max()) < len(tx0), (
            f"[{ctx}] indice fora do intervalo [0, {len(tx0)}): min={kp.min()} max={kp.max()}"
        )
        assert len(np.unique(kp)) == len(kp), f"[{ctx}] kept_prod contem duplicatas"

    ref_kept = _cull_tris_ref(kept_pre, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
    px0 = float(min(ea_[:, 0].min(), eb_[:, 0].min()))
    px1 = float(max(ea_[:, 0].max(), eb_[:, 0].max()))
    py0 = float(min(ea_[:, 1].min(), eb_[:, 1].min()))
    py1 = float(max(ea_[:, 1].max(), eb_[:, 1].max()))
    toca = (
        (tx1[ref_kept] >= px0 - marg_caixa)
        & (tx0[ref_kept] <= px1 + marg_caixa)
        & (ty1[ref_kept] >= py0 - marg_caixa)
        & (ty0[ref_kept] <= py1 + marg_caixa)
    )
    obrig = set(ref_kept[toca].tolist())
    obt = set(kp.tolist())
    faltando = obrig - obt
    assert not faltando, (
        f"[{ctx}] {len(faltando)} triangulo(s) obrigatorio(s) descartado(s) pelo cull "
        f"(ex.: {sorted(faltando)[:5]})"
    )
    return ref_kept


def _executar_e_validar_propriedade(
    pecas: list[tuple[np.ndarray, np.ndarray]],
    *,
    angulo_graus: float = 0.001,
    tol_z: float = 1e-4,
    min_len: float = 1e-4,
    marg_caixa: float = _MARGEM_PROPRIEDADE,
    ctx: str = "",
) -> tuple[list[list[np.ndarray]], list[dict]]:
    """Roda `linhas_visiveis_multi` observando `kept_idx` em `_passagem_faixas_orientadas`."""
    registros: list[dict] = []
    cache_pre: dict[tuple, np.ndarray] = {}
    real_faixas = vis._passagem_faixas_orientadas

    def spy_faixas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z_, d_eps, ctx_m, H_l):
        A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax = ctx_m[:11]
        mn_x = float(min(a[:, 0].min(), b[:, 0].min(), tx0.min() if len(A) else math.inf))
        mn_y = float(min(a[:, 1].min(), b[:, 1].min(), ty0.min() if len(A) else math.inf))
        mx_x = float(max(a[:, 0].max(), b[:, 0].max(), tx1.max() if len(A) else -math.inf))
        mx_y = float(max(a[:, 1].max(), b[:, 1].max(), ty1.max() if len(A) else -math.inf))
        dx_dom = max(mx_x - mn_x, 0.0)
        dy_dom = max(mx_y - mn_y, 0.0)
        chave = (mn_x, mn_y, mx_x, mx_y, g)
        kept_pre = cache_pre.get(chave)
        if kept_pre is None:
            _, _, _, _, kept_pre = _calc_mapa_z_ref(
                A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, mn_x, mn_y, mx_x, mx_y, g
            )
            cache_pre[chave] = kept_pre
        ref_kept = kept_pre[:0]
        if len(ek_idx) and len(kept_pre):
            ref_kept = _validar_conjunto_mantido(
                kept_idx, kept_pre, a[ek_idx], b[ek_idx], tx0, tx1, ty0, ty1,
                mn_x, mn_y, dx_dom, dy_dom, marg_caixa=marg_caixa,
                ctx=f"{ctx}/chamada_{len(registros)}",
            )
        registros.append(
            {
                "kept_prod": np.asarray(kept_idx).copy(),
                "kept_pre": kept_pre,
                "ref_kept": ref_kept,
                "n_ek": int(len(ek_idx)),
                "tx0": tx0, "tx1": tx1, "ty0": ty0, "ty1": ty1,
                "a_ek": a[ek_idx].copy(), "b_ek": b[ek_idx].copy(),
            }
        )
        return real_faixas(P, tv, kept_idx, ek_idx, a, b, d, g, tol_z_, d_eps, ctx_m, H_l)

    with mock.patch.object(vis, "_passagem_faixas_orientadas", spy_faixas):
        res = linhas_visiveis_multi(
            pecas, angulo_graus=angulo_graus, tol_z=tol_z, min_len=min_len, trabalhadores=1
        )
    return res, registros


# ---------------------------------------------------------------------------
# Construtores geometricos e cenas sinteticas
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


def _quad_vertical(
    x0: float, y0: float, x1: float, y1: float, z0: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    v = np.array([[x0, y0, z0], [x1, y1, z0], [x1, y1, z1], [x0, y0, z1]], dtype=np.float64)
    t = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return v, t


def _triangulo_unico(p0, p1, p2) -> tuple[np.ndarray, np.ndarray]:
    return np.array([p0, p1, p2], dtype=np.float64), np.array([[0, 1, 2]], dtype=np.int64)


def _peca_uma_aresta(x0: float, y0: float, z_top: float, z_bot: float = 0.0, comp: float = 1.8e-4):
    """Triangulo vertical com exatamente 1 aresta candidata (`len2d > min_len=1e-4`).

    Pela desigualdade triangular, com o 3o vertice no ponto medio em XY (`comp/2 = 9e-5 < 1e-4`),
    apenas a aresta superior `(0, 1)` passa no filtro `len2d > min_len`.
    """
    v = np.array(
        [
            [x0, y0, z_top],
            [x0 + comp, y0, z_top],
            [x0 + 0.5 * comp, y0, z_bot],
        ],
        dtype=np.float64,
    )
    t = np.array([[0, 1, 2]], dtype=np.int64)
    return v, t


def _terreno_plano(nx: int, ny: int, lado: float, z0: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(nx + 1) * lado, np.arange(ny + 1) * lado)
    z = np.full_like(xs, z0, dtype=np.float64)
    v = np.c_[xs.ravel(), ys.ravel(), z.ravel()]
    i = (np.arange(ny)[:, None] * (nx + 1) + np.arange(nx)[None, :]).ravel()
    t = np.stack([np.c_[i, i + 1, i + nx + 2], np.c_[i, i + nx + 2, i + nx + 1]], 1).reshape(-1, 3)
    return v, t.astype(np.int64)


def _cena_varias_pecas_espalhadas():
    rng = np.random.default_rng(240101)
    pecas = []
    for k in range(28):
        x = float((k % 7) * 18.0 + rng.uniform(0.0, 2.5))
        y = float((k // 7) * 28.0 + rng.uniform(0.0, 2.5))
        w = float(rng.uniform(0.4, 2.0))
        h = float(rng.uniform(0.4, 2.0))
        z0 = float(rng.uniform(0.0, 2.0))
        pecas.append(_caixa(x, y, z0, x + w, y + h, z0 + 0.8, rot_z=float(rng.uniform(0, math.pi))))
        if k % 3 == 0:
            pecas.append(_caixa(x + 0.1, y + 0.1, z0 + 1.2, x + w * 0.7, y + h * 0.7, z0 + 1.5))
    return pecas


def _cena_triangulos_ingremes():
    pecas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 0.5),
        _caixa(50.0, 50.0, 0.0, 51.0, 51.0, 0.5),
    ]
    for k, grad in enumerate((150.0, 500.0, 2000.0, 1e4)):
        x0 = 8.0 + 10.0 * k
        y0 = 10.0 + 6.0 * k
        dx = 1e-3 if grad <= 2000.0 else 1e-4
        v_st = np.array(
            [
                [x0, y0, 3.0],
                [x0 + dx, y0, 3.0 - grad * dx],
                [x0, y0 + 0.4, 3.0],
                [x0 + dx, y0 + 0.4, 3.0 - grad * dx],
            ],
            dtype=np.float64,
        )
        t_st = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        pecas.append((v_st, t_st))
        pecas.append(_caixa(x0 - 0.1, y0 + 0.05, 0.5, x0 + 0.2, y0 + 0.35, 1.2, incl_y=0.2))
        pecas.append(_quad_vertical(x0 - 0.05, y0 + 0.2, x0 + 0.05, y0 + 0.2, 0.0, 2.95))
    return pecas
