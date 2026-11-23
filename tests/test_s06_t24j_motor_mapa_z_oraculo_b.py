# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24j_motor_mapa_z_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
import threading
import time
from unittest import mock
import numpy as np
import pytest
import obim_geometria.visib_faixas as visib_faixas
import obim_geometria.visib_mapa as visib_mapa
import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _aplicar_corte,
    _arestas_candidatas,
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_mapa import _compactar_H, _unir_intervalos, _varrer_cels_triangulos
from obim_geometria.visibilidade import (
    _cull_tris,
    _dedup_triangulos,
    _limpar_malha,
    _visibilidade_hibrida,
    linhas_visiveis_multi,
)
from test_s06_t24j_motor_mapa_z_oraculo import _F_CAIXA, _MAPA_Z_REAL, _TOL_COORD, _linhas_visiveis_multi_ref  # noqa: F401



# ---------------------------------------------------------------------------
# Normalizacao canonica, hash SHA-256 e geradores de cenas sinteticas
# ---------------------------------------------------------------------------

def _canon_peca(pls: list[np.ndarray]) -> list[np.ndarray]:
    """Arredonda polilinhas a 1e-9 (eliminando -0.0) e ordena canonicamente."""
    if not pls:
        return []
    norm = [np.round(np.asarray(p, dtype=np.float64), 9) + 0.0 for p in pls]
    chaves = [
        (len(p), *p[0].tolist(), *p[-1].tolist(), *p.ravel().tolist())
        for p in norm
    ]
    ordem = sorted(range(len(norm)), key=chaves.__getitem__)
    return [norm[i] for i in ordem]


def _hash_resultado(res: list[list[np.ndarray]]) -> str:
    """SHA-256 deterministico do resultado normalizado (polilinhas arredondadas a 1e-9)."""
    h = hashlib.sha256()
    h.update(f"N:{len(res)}\n".encode())
    for i, pls in enumerate(res):
        c = _canon_peca(pls)
        h.update(f"P:{i}:{len(c)}\n".encode())
        for arr in c:
            h.update(f"L:{arr.shape[0]}:{arr.shape[1]}:".encode())
            h.update(np.ascontiguousarray(arr, dtype="<f8").tobytes())
    return h.hexdigest()


def _assert_equivalente(obtido, esperado, *, contexto: str = ""):
    assert _hash_resultado(obtido) == _hash_resultado(esperado), f"SHA-256 divergiu ({contexto})"
    assert len(obtido) == len(esperado), f"num pecas divergiu ({contexto})"
    for i, (pa, pb) in enumerate(zip(obtido, esperado)):
        ca, cb = _canon_peca(pa), _canon_peca(pb)
        assert [len(x) for x in ca] == [len(x) for x in cb], f"peca {i} contagem ({contexto})"
        if ca:
            dif = np.abs(np.concatenate(ca) - np.concatenate(cb)).max()
            assert dif <= _TOL_COORD, f"peca {i} diff={dif:.3e} ({contexto})"


def _comprimento_total(pls: list[np.ndarray]) -> float:
    return float(sum(np.hypot(*np.diff(p, axis=0).T).sum() for p in pls))


def _rz(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _ry(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _caixa(x0, y0, z0, x1, y1, z1, *, rot_z: float = 0.0, incl_y: float = 0.0):
    cx, cy, cz = (x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    v = np.array(
        [[x, y, z] for z in (-0.5, 0.5) for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))],
        dtype=np.float64,
    ) * np.array([sx, sy, sz], dtype=np.float64)
    r = _rz(rot_z) @ _ry(incl_y)
    return v @ r.T + np.array([cx, cy, cz], dtype=np.float64), _F_CAIXA.copy()


def _placa_com_furo(x0, y0, x1, y1, fx0, fy0, fx1, fy1, z0, z1):
    """Laje fechada com furo retangular passante (anel no topo/fundo + paredes externas e do furo)."""
    ext = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    furo = [(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)]
    v = np.array([(x, y, z) for z in (z0, z1) for (x, y) in ext + furo], dtype=np.float64)
    t = []
    for k in range(4):
        k1 = (k + 1) % 4
        ok, ok1, ik, ik1 = k, k1, 4 + k, 4 + k1
        t += [(8 + ok, 8 + ok1, 8 + ik1), (8 + ok, 8 + ik1, 8 + ik)]
        t += [(ok, ik1, ok1), (ok, ik, ik1)]
        t += [(ok, ok1, 8 + ok1), (ok, 8 + ok1, 8 + ok)]
        t += [(ik, 8 + ik1, ik1), (ik, 8 + ik, 8 + ik1)]
    return v, np.array(t, dtype=np.int64)


def _parede_com_abertura_x(x0, x1, y0, y1, z0, z1, ax0, ax1, az0, az1):
    """Parede ao longo de X com vao retangular (4 blocos fechados como 1 peca)."""
    blocos = [
        _caixa(x0, y0, z0, ax0, y1, z1),
        _caixa(ax1, y0, z0, x1, y1, z1),
        _caixa(ax0, y0, az1, ax1, y1, z1),
    ]
    if az0 > z0 + 1e-6:
        blocos.append(_caixa(ax0, y0, z0, ax1, y1, az0))
    vs, ts, off = [], [], 0
    for vb, tb in blocos:
        vs.append(vb)
        ts.append(tb + off)
        off += len(vb)
    return np.vstack(vs), np.vstack(ts)


def _quad_vertical(x0, y0, x1, y1, z0, z1):
    """Painel puramente vertical (sem triangulos horizontais: fora da caixa de `prep`, muda `chave`)."""
    v = np.array([[x0, y0, z0], [x1, y1, z0], [x1, y1, z1], [x0, y0, z1]], dtype=np.float64)
    t = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return v, t


def _tiras(x0, y0, comp, larg, n, th, z0, incl):
    q = np.array([[x0, y0 + i * larg] for i in range(n)], dtype=np.float64)
    pts = np.concatenate([[[a, b], [a + comp, b], [a + comp, b + larg], [a, b + larg]] for a, b in q])
    v = np.c_[pts, z0 + incl * pts[:, 1]]
    k = np.arange(n, dtype=np.int64)[:, None] * 4
    t = np.concatenate([k + [0, 1, 2], k + [0, 2, 3]]).reshape(2, n, 3).transpose(1, 0, 2).reshape(-1, 3)
    return v @ _rz(th).T, t


def _cena_casa_paredes_lajes_buracos():
    """Cena residencial sintetica: piso, paredes com aberturas, laje com buracos, pecas escondidas e visiveis."""
    pecas = [
        _caixa(0.0, 0.0, -0.2, 12.0, 9.0, 0.0),  # piso
        _parede_com_abertura_x(0.0, 12.0, 0.0, 0.2, 0.0, 3.0, 2.0, 3.2, 0.0, 2.1),  # parede sul c/ porta
        _parede_com_abertura_x(0.0, 12.0, 8.8, 9.0, 0.0, 3.0, 5.0, 7.0, 1.0, 2.2),  # parede norte c/ janela
        _caixa(0.0, 0.2, 0.0, 0.2, 8.8, 3.0),  # parede oeste
        _caixa(11.8, 0.2, 0.0, 12.0, 8.8, 3.0),  # parede leste
        _caixa(5.8, 0.2, 0.0, 6.0, 6.5, 2.8),  # divisoria interna
        _caixa(0.2, 4.4, 0.0, 4.5, 4.6, 2.8),  # divisoria interna 2
        _placa_com_furo(0.0, 0.0, 6.5, 9.0, 1.5, 1.5, 4.0, 3.8, 3.0, 3.25),  # laje oeste com buraco de escada
        _placa_com_furo(6.5, 0.0, 12.0, 9.0, 8.0, 4.5, 10.2, 7.0, 3.0, 3.25),  # laje leste com claraboia
        _caixa(2.0, 2.0, 0.0, 3.4, 3.2, 0.8),  # mesa visivel pelo buraco oeste
        _caixa(8.5, 5.0, 0.0, 9.8, 6.4, 1.1),  # bancada visivel pelo buraco leste
        _caixa(0.8, 6.0, 0.0, 2.5, 7.5, 0.9),  # movel totalmente escondido sob laje oeste
        _caixa(7.0, 1.0, 0.0, 9.0, 2.6, 1.0),  # movel totalmente escondido sob laje leste
        _caixa(3.5, 2.8, 0.0, 5.2, 4.2, 1.2, rot_z=0.35),  # parcialmente sob a borda do buraco
        _caixa(7.5, 4.0, 0.0, 9.2, 5.5, 0.7, incl_y=0.2),  # inclinada cruzando a borda da claraboia
        _caixa(4.0, 5.5, 3.25, 8.0, 7.2, 4.1, rot_z=0.18),  # caixa sobre a laje (caixa d'agua)
        _caixa(1.0, 0.5, 3.25, 2.2, 1.4, 3.9),  # platibanda / volume no topo
        _caixa(10.5, 1.0, 3.25, 11.4, 2.5, 4.0),  # chamine no topo
    ]
    return pecas


def _cena_casa_compacta():
    """Versao compacta (2,4 x 1,8 m) da cena residencial com as mesmas 18 pecas, buracos e oclusoes."""
    return [(v * 0.2, t.copy()) for v, t in _cena_casa_paredes_lajes_buracos()]


def _cena_caixas_sobrepostas_e_escondidas():
    rng = np.random.default_rng(24001)
    pecas = [
        _caixa(0.0, 0.0, 2.5, 4.0, 4.0, 2.8),  # cobertura parcial
        _caixa(0.8, 0.8, 0.0, 1.6, 1.6, 1.0),  # totalmente escondida
        _caixa(0.8, 0.8, 0.0, 1.6, 1.6, 1.0),  # duplicata exata
        _caixa(2.0, 2.0, 0.0, 4.8, 2.8, 1.5),  # parcialmente escondida
        _caixa(2.0, 2.0, 1.0, 4.4, 2.6, 3.2, incl_y=0.25),  # sobreposta inclinada atravessando z=2.8
    ]
    for _ in range(12):
        cx, cy = rng.uniform(0.2, 4.6, 2)
        sx, sy, sz = rng.uniform(0.2, 1.2, 3)
        z0 = float(rng.uniform(0.0, 3.5))
        pecas.append(
            _caixa(cx - sx / 2, cy - sy / 2, z0, cx + sx / 2, cy + sy / 2, z0 + sz,
                   rot_z=float(rng.uniform(0.0, math.pi)),
                   incl_y=float(rng.uniform(-0.3, 0.3)) if rng.random() < 0.4 else 0.0)
        )
    return pecas


def _cena_lajes_buracos_e_faixas():
    pecas = [
        _placa_com_furo(0.0, 0.0, 6.0, 3.5, 1.2, 1.0, 3.4, 2.4, 2.0, 2.3),
        _tiras(0.3, 0.3, 5.2, 0.01, 240, 0.15, 2.6, 0.02),  # aciona passagem por faixas orientadas
    ]
    for i in range(10):
        x = 0.5 + 0.5 * i
        y = 0.5 + 0.5 * (i % 5)
        z0 = 0.0 if i % 2 == 0 else 2.8
        pecas.append(_caixa(x, y, z0, x + 0.45, y + 0.4, z0 + 0.9, rot_z=0.2 * i))
    return pecas


def _cena_utm_georref():
    off = np.array([500_000.0, 7_400_000.0, 750.0], dtype=np.float64)
    return [(v + off, t.copy()) for v, t in _cena_casa_compacta()]


def _cena_perto_de_zero():
    pecas = [
        _placa_com_furo(-0.5, -0.5, 0.5, 0.5, -0.2, -0.2, 0.2, 0.2, 0.2, 0.25),
        _caixa(-0.15, -0.15, -0.1, 0.15, 0.15, 0.1),  # visivel pelo furo em torno de (0,0)
        _caixa(-0.45, -0.45, -0.1, -0.25, -0.25, 0.1),  # escondida no quadrante negativo
        _caixa(0.25, 0.25, -0.1, 0.45, 0.45, 0.1),  # escondida no quadrante positivo
        _caixa(-0.3, -0.05, 0.0, 0.3, 0.05, 0.35, incl_y=0.15),  # cruza a origem e a laje
        _caixa(-0.4, 0.1, 0.25, 0.1, 0.35, 0.45, rot_z=0.4),
        _caixa(-1e-4, -0.4, 0.0, 1e-4 + 0.2, 0.4, 0.15),
        _caixa(-0.4, -1e-4, 0.26, 0.4, 1e-4 + 0.12, 0.36),
        _caixa(-0.22, -0.22, -0.05, -0.02, 0.18, 0.22),
        _caixa(0.05, -0.35, 0.0, 0.38, -0.08, 0.30, rot_z=-0.25),
    ]
    return pecas


def _cena_aleatoria_semente_fixa():
    rng = np.random.default_rng(24010)
    pecas = [
        _placa_com_furo(0.0, 0.0, 4.5, 4.0, 1.0, 1.0, 2.4, 2.4, 1.8, 2.0),
        _placa_com_furo(1.2, 0.6, 4.0, 3.4, 1.8, 1.3, 3.1, 2.7, 3.2, 3.4),
    ]
    for _ in range(16):
        cx, cy = rng.uniform(0.2, 4.3, 2)
        sx, sy, sz = rng.uniform(0.15, 0.9, 3)
        z0 = float(rng.uniform(-0.5, 4.0))
        pecas.append(
            _caixa(cx - sx / 2, cy - sy / 2, z0, cx + sx / 2, cy + sy / 2, z0 + sz,
                   rot_z=float(rng.uniform(0.0, math.pi)),
                   incl_y=float(rng.uniform(-0.35, 0.35)) if rng.random() < 0.35 else 0.0)
        )
    return pecas


def _cena_tres_chaves_distintas():
    """14 pecas gerando exatamente 3 chaves de mapa Z distintas em linhas_visiveis_multi."""
    pecas = [
        # Grupo A (6 caixas dentro de [0, 2] x [0, 2]) -> chave 1: [0, 2] x [0, 2]
        _caixa(0.0, 0.0, 2.0, 2.0, 2.0, 2.2),
        _caixa(0.2, 0.2, 0.0, 0.8, 0.8, 1.0),
        _caixa(1.0, 0.2, 0.0, 1.6, 0.8, 1.0),
        _caixa(0.2, 1.1, 0.0, 0.9, 1.7, 1.0),
        _caixa(1.1, 1.1, 2.2, 1.8, 1.8, 3.0),
        _caixa(0.2, 0.2, 2.2, 0.7, 0.7, 2.8),
        # Grupo B (4 paineis verticais em x=4, dentro de y=[0, 2]) -> chave 2: [0, 4] x [0, 2]
        _quad_vertical(4.0, 0.1, 4.0, 0.5, 0.0, 2.0),
        _quad_vertical(4.0, 0.6, 4.0, 1.0, 0.0, 2.0),
        _quad_vertical(4.0, 1.1, 4.0, 1.5, 0.0, 2.0),
        _quad_vertical(4.0, 1.6, 4.0, 1.9, 0.0, 2.0),
        # Grupo C (4 paineis verticais em x=6, dentro de y=[0, 2]) -> chave 3: [0, 6] x [0, 2]
        _quad_vertical(6.0, 0.1, 6.0, 0.5, 0.0, 2.0),
        _quad_vertical(6.0, 0.6, 6.0, 1.0, 0.0, 2.0),
        _quad_vertical(6.0, 1.1, 6.0, 1.5, 0.0, 2.0),
        _quad_vertical(6.0, 1.6, 6.0, 1.9, 0.0, 2.0),
    ]
    return pecas


CENAS = {
    "casa_paredes_lajes_buracos": _cena_casa_paredes_lajes_buracos,
    "caixas_sobrepostas_e_escondidas": _cena_caixas_sobrepostas_e_escondidas,
    "lajes_buracos_e_faixas": _cena_lajes_buracos_e_faixas,
    "utm_georref": _cena_utm_georref,
    "perto_de_zero": _cena_perto_de_zero,
    "aleatoria_semente_fixa": _cena_aleatoria_semente_fixa,
}


def _instalar_spy_mapa_z(monkeypatch, *, atraso: float = 0.0, ao_chamar=None):
    """Instala spy thread-safe em visibilidade._mapa_z_conservador (e visib_mapa)."""
    chamadas: list[tuple] = []
    lock = threading.Lock()

    def spy(*args, **kwargs):
        chave = tuple(args[-5:])
        with lock:
            chamadas.append(chave)
            ordem = len(chamadas)
        if atraso > 0.0:
            time.sleep(atraso)
        if ao_chamar is not None:
            ao_chamar(ordem, chave)
        return _MAPA_Z_REAL(*args, **kwargs)

    monkeypatch.setattr(vis, "_mapa_z_conservador", spy)
    monkeypatch.setattr(visib_mapa, "_mapa_z_conservador", spy)
    return chamadas


def _executar_com_timeout(fn, timeout: float = 60.0):
    """Executa `fn` em thread daemon com timeout para detectar deadlock sem travar pytest."""
    res: list = []
    erro: list[BaseException] = []

    def alvo():
        try:
            res.append(fn())
        except BaseException as exc:  # noqa: BLE001
            erro.append(exc)

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"deadlock detectado: execucao excedeu {timeout:.0f} s"
    if erro:
        raise erro[0]
    return res[0]


def _threads_pool_vivas() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor") and t.is_alive()]


# ---------------------------------------------------------------------------
# (1) Equivalencia: 1, 2 e 8 threads vs copia literal do motor atual
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome_cena", list(CENAS))
def test_equivalencia_1_2_8_threads_igual_referencia_literal(nome_cena):
    pecas = CENAS[nome_cena]()
    ref = _linhas_visiveis_multi_ref(pecas)
    h_ref = _hash_resultado(ref)

    for n_trab in (1, 2, 8):
        obtido = linhas_visiveis_multi(pecas, trabalhadores=n_trab)
        assert _hash_resultado(obtido) == h_ref, f"{nome_cena} trabalhadores={n_trab}"
        _assert_equivalente(obtido, ref, contexto=f"{nome_cena}/n={n_trab}")
