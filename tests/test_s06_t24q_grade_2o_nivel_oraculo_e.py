# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 5 de test_s06_t24q_grade_2o_nivel_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24q_grade_2o_nivel_oraculo import _assert_equivalente, _caixa, _canon_bit_a_bit  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo_b import _esfera_uv, _juntar_malhas, _rodar  # noqa: F401
from test_s06_t24q_grade_2o_nivel_oraculo_d import _cena_triangulo_ingreme  # noqa: F401



@pytest.mark.parametrize("grad", [120.0, 200.0, 500.0, 1000.0, 1e5])
@pytest.mark.parametrize("tol_z", [5e-5, 1e-4, 1e-3])
def test_triangulo_ingreme_api_publica(grad, tol_z, monkeypatch):
    """Via linhas_visiveis_multi (d_eps=-1e-6), subgrade ligada == desligada em triangulos ingremes."""
    pecas = _cena_triangulo_ingreme(grad, tol_z, eps=1e-6)
    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "0")
    ref = linhas_visiveis_multi(pecas, tol_z=tol_z, trabalhadores=1)
    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "1")
    obt = linhas_visiveis_multi(pecas, tol_z=tol_z, trabalhadores=1)
    _assert_equivalente(obt, ref, exigir_bit_a_bit=True, ctx=f"ingreme_pub/g={grad:g}/tz={tol_z:g}")


@pytest.mark.parametrize(
    "grad,d_eps,tol_z",
    [
        (120.0, -5e-4, 1e-4),
        (120.0, -5e-4, 1e-3),
        (1000.0, -5e-4, 1e-4),
        (1000.0, -5e-4, 1e-3),
    ],
)
def test_triangulo_ingreme_d_eps_alternativo(grad, d_eps, tol_z, monkeypatch):
    """Com d_eps=-5e-4 e tol_z variados, _visibilidade_hibrida ligada == desligada em triangulos ingremes."""
    pecas = _cena_triangulo_ingreme(grad, tol_z, eps=abs(d_eps))
    v_parts = [v for v, _ in pecas]
    V_all = np.vstack(v_parts)
    t_parts = []
    off = 0
    for v, t in pecas:
        t_parts.append(t + off)
        off += len(v)
    Tw_all = np.vstack(t_parts)
    a, b, ang, silh, _, ea, eb = _arestas_candidatas(V_all, pecas[0][1])
    m = ((ang >= 0.001) | silh) & (np.hypot(*(b - a)[:, :2].T) > 1e-4)
    prep = _preparar_triangulos(V_all, Tw_all)

    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "0")
    s_off = vis._visibilidade_hibrida(V_all, Tw_all, a[m], b[m], ea[m], eb[m], tol_z, d_eps, 1e-4, prep=prep)
    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "1")
    s_on = vis._visibilidade_hibrida(V_all, Tw_all, a[m], b[m], ea[m], eb[m], tol_z, d_eps, 1e-4, prep=prep)
    _assert_equivalente(
        [list(s_on)], [list(s_off)], exigir_bit_a_bit=True,
        ctx=f"ingreme_deps/g={grad:g}/deps={d_eps:g}/tz={tol_z:g}",
    )


# ---------------------------------------------------------------------------
# (7) Regressao de gatilho: casa realista sintetica + capturas reais (skipif)
# ---------------------------------------------------------------------------

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


def _cena_casa_realista_25x25() -> list[tuple[np.ndarray, np.ndarray]]:
    """Casa sintetica 25x25 m (g ~ 0.011 m): laje, paredes, esquadrias e 16 moveis moderados.

    Reproduz a estatistica de casas IFC reais (triangulos grandes + pecas tesseladas com
    ~5 a 60 tris/celula em partes espalhadas pelo dominio, sem peca ultra-densa de 100k tris).
    """
    pecas: list[tuple[np.ndarray, np.ndarray]] = []
    # Laje piso 25x25 m
    pecas.append(_caixa(0.0, 0.0, -0.15, 25.0, 25.0, 0.0))
    # Paredes externas e internas
    for p in (
        (0.0, 0.0, 0.0, 25.0, 0.2, 2.8),
        (0.0, 24.8, 0.0, 25.0, 25.0, 2.8),
        (0.0, 0.2, 0.0, 0.2, 24.8, 2.8),
        (24.8, 0.2, 0.0, 25.0, 24.8, 2.8),
        (0.2, 8.0, 0.0, 12.0, 8.15, 2.8),
        (12.0, 0.2, 0.0, 12.15, 16.0, 2.8),
        (12.15, 15.85, 0.0, 24.8, 16.0, 2.8),
        (6.0, 8.15, 0.0, 6.15, 24.8, 2.8),
        (18.0, 0.2, 0.0, 18.15, 15.85, 2.8),
    ):
        pecas.append(_caixa(*p))
    # Esquadrias (caixilhos compostos por barras finas)
    for k in range(10):
        x = 1.5 + (k % 5) * 4.4
        y = 0.05 if k < 5 else 24.85
        pecas.append(
            _juntar_malhas(
                _caixa(x, y, 0.9, x + 1.4, y + 0.1, 0.96),
                _caixa(x, y, 2.04, x + 1.4, y + 0.1, 2.1),
                _caixa(x, y, 0.96, x + 0.06, y + 0.1, 2.04),
                _caixa(x + 1.34, y, 0.96, x + 1.4, y + 0.1, 2.04),
                _caixa(x + 0.67, y, 0.96, x + 0.73, y + 0.1, 2.04),
            )
        )
    # 16 moveis/loucas moderadamente tesselados (~1.8k-3.5k tris, ~5-60 tris/celula)
    rng = np.random.default_rng(2026)
    for m in range(16):
        cx = 2.0 + (m % 4) * 5.8 + float(rng.uniform(-0.3, 0.3))
        cy = 2.2 + (m // 4) * 5.5 + float(rng.uniform(-0.3, 0.3))
        r = float(rng.uniform(0.38, 0.58))
        nlat = int(rng.choice([24, 28, 32]))
        nlon = int(rng.choice([24, 28, 32]))
        v1, t1 = _esfera_uv(cx, cy, 0.45, r, nlat, nlon, rot_x=0.35 + 0.1 * (m % 4))
        v1[:, 2] = 0.45 + 0.5 * (v1[:, 2] - 0.45)
        v2, t2 = _esfera_uv(cx + 0.25, cy - 0.15, 0.75, r * 0.75, nlat - 2, nlon - 2, rot_x=0.7)
        v2[:, 2] = 0.75 + 0.4 * (v2[:, 2] - 0.75)
        b1 = _caixa(cx - r, cy - r, 0.02, cx + r, cy + r, 0.06, rot_z=0.15 * m)
        pecas.append(_juntar_malhas((v1, t1), (v2, t2), b1))
    return pecas


def test_gatilho_casa_sintetica_realista_nao_piora(monkeypatch):
    """Cena sintetica de casa 25x25 m: ligada <= 1,05x desligada (mediana 3x, 1T) e SHA igual."""
    pecas = _cena_casa_realista_25x25()
    # Aquecimento + verificacao de equivalencia/SHA
    ref = _rodar(monkeypatch, pecas, subgrade="0", trabalhadores=1)
    obt = _rodar(monkeypatch, pecas, subgrade="1", trabalhadores=1)
    assert _sha_polilinhas(obt) == _sha_polilinhas(ref), "SHA difere na casa sintetica 25x25 m"

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
        f"regressao de gatilho na casa sintetica 25x25 m: ligada={med_on:.3f}s "
        f"desligada={med_off:.3f}s ({razao:.3f}x > 1.05x)"
    )


_DIR_CAPTURAS_T24E = "/tmp/t24e/dist"
_PKL_CASARAO_SUBSOLO = os.path.join(_DIR_CAPTURAS_T24E, "cas_4.pkl")


@pytest.mark.parametrize(
    "nome,caminho_pkl",
    [
        pytest.param(
            nome,
            os.path.join(_DIR_CAPTURAS_T24E, f"{nome}.pkl"),
            marks=pytest.mark.skipif(
                not os.path.exists(os.path.join(_DIR_CAPTURAS_T24E, f"{nome}.pkl")),
                reason=f"captura real ausente: {os.path.join(_DIR_CAPTURAS_T24E, f'{nome}.pkl')}",
            ),
            id=nome,
        )
        for nome in ("c2x4_0", "c2x4_1", "c2x3_0")
    ],
)
def test_gatilho_captura_real_casa_nao_piora(nome, caminho_pkl, monkeypatch):
    """Capturas reais de casa (/tmp/t24e/dist/*.pkl): ligada <= 1,05x desligada (mediana 3x, 1T) e SHA igual."""
    with open(caminho_pkl, "rb") as fh:
        pecas, _ = pickle.load(fh)

    # Aquecimento + SHA
    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "0")
    ref = linhas_visiveis_multi(pecas, angulo_graus=0.001, trabalhadores=1)
    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "1")
    obt = linhas_visiveis_multi(pecas, angulo_graus=0.001, trabalhadores=1)
    assert _sha_polilinhas(obt) == _sha_polilinhas(ref), f"SHA difere na captura real {nome}"

    t_off: list[float] = []
    t_on: list[float] = []
    for _ in range(3):
        monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "0")
        t0 = time.perf_counter()
        linhas_visiveis_multi(pecas, angulo_graus=0.001, trabalhadores=1)
        t_off.append(time.perf_counter() - t0)

        monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "1")
        t0 = time.perf_counter()
        linhas_visiveis_multi(pecas, angulo_graus=0.001, trabalhadores=1)
        t_on.append(time.perf_counter() - t0)

    med_off = statistics.median(t_off)
    med_on = statistics.median(t_on)
    razao = med_on / med_off if med_off > 0.0 else math.inf
    assert med_on <= 1.05 * med_off, (
        f"regressao de gatilho na captura real {nome}: ligada={med_on:.3f}s "
        f"desligada={med_off:.3f}s ({razao:.3f}x > 1.05x)"
    )


@pytest.mark.skipif(
    not os.path.exists(_PKL_CASARAO_SUBSOLO),
    reason=f"captura real ausente: {_PKL_CASARAO_SUBSOLO}",
)
def test_desempenho_real_casarao_subsolo_speedup(monkeypatch):
    """Captura real do casarao subsolo (cas_4.pkl): ligada >= 1,5x mais rapida que desligada e SHA igual."""
    with open(_PKL_CASARAO_SUBSOLO, "rb") as fh:
        pecas, _ = pickle.load(fh)

    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "0")
    t0 = time.perf_counter()
    ref = linhas_visiveis_multi(pecas, angulo_graus=0.001, trabalhadores=None)
    t_off = time.perf_counter() - t0

    monkeypatch.setenv("OBIM_VISIB_SUBGRADE", "1")
    t0 = time.perf_counter()
    obt = linhas_visiveis_multi(pecas, angulo_graus=0.001, trabalhadores=None)
    t_on = time.perf_counter() - t0

    assert _sha_polilinhas(obt) == _sha_polilinhas(ref), "SHA difere no casarao subsolo (cas_4)"
    speedup = t_off / t_on if t_on > 0.0 else math.inf
    assert speedup >= 1.5, (
        f"ganho insuficiente no casarao subsolo (cas_4): desligada={t_off:.2f}s "
        f"ligada={t_on:.2f}s (speedup={speedup:.2f}x < 1.50x)"
    )
