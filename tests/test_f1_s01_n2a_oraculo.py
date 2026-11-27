# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-N2a: `obimvisib.unir_intervalos` nativo e seletor em `visib_mapa`."""
from __future__ import annotations

import importlib, os, shutil, subprocess, sys
from pathlib import Path

import numpy as np
import pytest

from obim_geometria import visib_mapa
from obim_geometria.visibilidade import linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas

BUILD_SH = Path(__file__).resolve().parent.parent / "native" / "obim_visib" / "build.sh"


def _bits(a: np.ndarray) -> np.ndarray:
    assert a.dtype == np.float64
    return np.ascontiguousarray(a).view(np.uint64)


def _igual_bits(obt, esp, *, checar_dtype_he: bool = True) -> None:
    he_o, lo_o, hi_o = obt
    he_e, lo_e, hi_e = esp
    if checar_dtype_he:
        assert he_o.dtype == he_e.dtype, f"dtype he: {he_o.dtype} != {he_e.dtype}"
    assert np.array_equal(he_o, he_e)
    assert np.array_equal(_bits(lo_o), _bits(lo_e))
    assert np.array_equal(_bits(hi_o), _bits(hi_e))


@pytest.fixture(scope="module")
def obimvisib_mod(tmp_path_factory):
    if os.environ.get("OBIM_VISIB_BUILD") != "1":
        pytest.skip("defina OBIM_VISIB_BUILD=1; o CI roda no job obimcore")
    if not os.environ.get("CONDA_PREFIX"):
        pytest.skip("CONDA_PREFIX nao definido no ambiente")
    bash = shutil.which("bash")
    if shutil.which("cmake") is None or bash is None:
        pytest.skip("cmake ou bash ausente no PATH")
    assert BUILD_SH.is_file(), f"ausente: {BUILD_SH}"
    out = tmp_path_factory.mktemp("obimvisib_n2a")
    res = subprocess.run([bash, str(BUILD_SH), str(out)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, f"build.sh falhou ({res.returncode}):\n{res.stdout}\n{res.stderr}"
    antes = {k: v for k, v in sys.modules.items() if k == "obimvisib" or k.startswith("obimvisib.")}
    for k in list(antes):
        sys.modules.pop(k, None)
    sys.path.insert(0, str(out))
    importlib.invalidate_caches()
    try:
        yield importlib.import_module("obimvisib")
    finally:
        if str(out) in sys.path:
            sys.path.remove(str(out))
        for k in [k for k in sys.modules if k == "obimvisib" or k.startswith("obimvisib.")]:
            sys.modules.pop(k, None)
        sys.modules.update(antes)


def test_seletor_desligado_conta_chamadas_python(monkeypatch):
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 0
    he, lo, hi = np.array([2, 1, 2], dtype=np.int64), np.array([0.4, 0.1, 0.0]), np.array([0.8, 0.3, 0.5])
    r1 = visib_mapa._unir_intervalos(he, lo, hi)
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 1
    r2 = visib_mapa._unir_intervalos(he, lo, hi)
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 2
    _igual_bits(r1, r2)
    _igual_bits(r1, visib_mapa._unir_intervalos_py(he, lo, hi))
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 3


def test_seletor_ligado_sem_modulo_levanta_import_error(monkeypatch):
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    monkeypatch.setitem(sys.modules, "obimvisib", None)
    visib_mapa._zerar_chamadas_py()
    with pytest.raises(ImportError, match=r".+"):
        visib_mapa._unir_intervalos(np.array([0, 0], dtype=np.int64), np.array([0.0, 0.5]), np.array([0.6, 1.0]))
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 0


@pytest.mark.parametrize("dtype_he", [np.int32, np.int64])
def test_vazio_unitario_e_zeros_assinados(obimvisib_mod, dtype_he):
    # Mutante: esquecer max(lo, hi) quando lo > hi no caso n==1 ou normalizar -0.0 para 0.0.
    casos = [
        ([], [], []), ([7], [0.2], [0.8]), ([7], [0.5], [0.5]), ([7], [0.9], [0.1]),
        ([0], [-0.0], [0.5]), ([0], [0.0], [0.5]), ([0], [-0.0], [-0.0]),
        ([0], [-0.0], [-1.0]), ([0], [0.0], [-1.0]), ([0], [-2.0], [-0.0]),
    ]
    for he_l, lo_l, hi_l in casos:
        he, lo, hi = np.array(he_l, dtype=dtype_he), np.array(lo_l, dtype=np.float64), np.array(hi_l, dtype=np.float64)
        _igual_bits(obimvisib_mod.unir_intervalos(he, lo, hi), visib_mapa._unir_intervalos_py(he, lo, hi))


@pytest.mark.parametrize("dtype_he", [np.int32, np.int64])
def test_fronteira_1e9_duplicados_negativos_e_estabilidade(obimvisib_mod, dtype_he):
    # Mutantes: (1) trocar + 1e-9 por - 1e-9; (2) usar < no lugar de <= na fusao;
    # (3) ordenar so por aresta (ignorar lo); (4) usar hi[i-1] em vez de max_hi acumulado.
    lim1 = 1.0 + 1e-9
    he = np.array([1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7, 8, 8, 8, -3, -3, -3, 9, 9, 10, 10], dtype=dtype_he)
    lo = np.array([
        0.0, 1e-9, 0.0, np.nextafter(1e-9, 0.0), 0.0, np.nextafter(1e-9, 1.0),
        0.0, lim1, 0.0, np.nextafter(lim1, 2.0), 0.5, 0.0, 0.0, 1.0, 5.0 + 1e-9,
        0.2, 0.2, 0.2, -5.0, -5.0 + 1e-9, -10.0, -0.0, 0.0, 0.0, -0.0,
    ], dtype=np.float64)
    hi = np.array([
        0.0, 0.4, 0.0, 0.4, 0.0, 0.4, 1.0, 2.0, 1.0, 2.0, 0.9, 0.6, 5.0, 2.0, 6.0,
        0.2, 0.7, 0.4, -5.0, -4.0, -9.0, 0.2, 0.6, 0.2, 0.6,
    ], dtype=np.float64)
    obt = obimvisib_mod.unir_intervalos(he, lo, hi)
    _igual_bits(obt, visib_mapa._unir_intervalos_py(he, lo, hi))
    for aresta, qtd in ((1, 1), (2, 1), (3, 2), (4, 1), (5, 2), (6, 1), (7, 1), (-3, 2)):
        assert int(np.count_nonzero(obt[0] == aresta)) == qtd
    assert int(_bits(obt[1][obt[0] == 9])[0]) == 0x8000000000000000
    assert int(_bits(obt[1][obt[0] == 10])[0]) == 0x0


@pytest.mark.parametrize("dtype_he", [np.int32, np.int64])
def test_aleatorios_ordenados_inversos_e_n_grande(obimvisib_mod, dtype_he):
    rng = np.random.default_rng(20260401)
    for n, n_ar in ((300, 15), (4_000, 80)):
        he = rng.integers(-5, n_ar, size=n, dtype=dtype_he)
        lo = rng.uniform(-10.0, 10.0, size=n)
        hi = lo + rng.uniform(-0.2, 1.5, size=n)
        lo[::17] = hi[::17]
        ord_idx = np.lexsort((lo, he))
        for idx in (np.arange(n), ord_idx, ord_idx[::-1]):
            _igual_bits(obimvisib_mod.unir_intervalos(he[idx], lo[idx], hi[idx]), visib_mapa._unir_intervalos_py(he[idx], lo[idx], hi[idx]))
    if dtype_he is np.int64:
        he_g = rng.integers(0, 5_000, size=200_000, dtype=np.int64)
        lo_g = rng.uniform(-100.0, 100.0, size=200_000)
        hi_g = lo_g + rng.uniform(0.0, 2.0, size=200_000)
        _igual_bits(obimvisib_mod.unir_intervalos(he_g, lo_g, hi_g), visib_mapa._unir_intervalos_py(he_g, lo_g, hi_g))


@pytest.mark.parametrize("dtype_he", [np.int32, np.int64])
def test_fatias_nao_contiguas_e_somente_leitura(obimvisib_mod, dtype_he):
    # Mutante: ignorar stride(0) ou exigir buffer contiguo/gravavel.
    rng = np.random.default_rng(77)
    he, lo = rng.integers(0, 12, size=180, dtype=dtype_he), rng.uniform(-3.0, 3.0, size=180)
    hi = lo + rng.uniform(-0.1, 0.8, size=180)
    for arr in (he, lo, hi):
        arr.setflags(write=False)
    for f in (slice(None), slice(None, None, 2), slice(None, None, -3)):
        _igual_bits(obimvisib_mod.unir_intervalos(he[f], lo[f], hi[f]), visib_mapa._unir_intervalos_py(he[f], lo[f], hi[f]))


def test_conversao_outros_dtypes_e_seletor_ligado(obimvisib_mod, monkeypatch):
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    casos = ((np.int32, np.float64), (np.int64, np.float64), (np.int16, np.float64), (np.uint8, np.float64), (np.int16, np.float32))
    for dt_he, dt_f in casos:
        he = np.array([4, 1, 4, 2, 1], dtype=dt_he)
        lo, hi = np.array([0.5, 0.2, 0.0, 0.1, 0.0], dtype=dt_f), np.array([0.9, 0.6, 0.5, 0.3, 0.25], dtype=dt_f)
        visib_mapa._zerar_chamadas_py()
        obt = visib_mapa._unir_intervalos(he, lo, hi)
        assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 0
        preserva = dt_he in (np.int32, np.int64)
        assert obt[0].dtype == (dt_he if preserva else np.int64)
        _igual_bits(obt, visib_mapa._unir_intervalos_py(he, lo, hi), checar_dtype_he=preserva)


def test_determinismo_e_invariancia_a_permutacao(obimvisib_mod):
    rng, n = np.random.default_rng(999), 600
    he = np.repeat(np.arange(30, dtype=np.int64), n // 30)
    lo = np.tile(np.linspace(-2.0, 5.0, n // 30, endpoint=False), 30) + rng.uniform(0.0, 1e-4, size=n)
    hi = lo + rng.uniform(0.0, 0.5, size=n)
    base = obimvisib_mod.unir_intervalos(he, lo, hi)
    for _ in range(2):
        _igual_bits(obimvisib_mod.unir_intervalos(he, lo, hi), base)
    for _ in range(3):
        perm = rng.permutation(n)
        _igual_bits(obimvisib_mod.unir_intervalos(he[perm], lo[perm], hi[perm]), base)


def test_pipeline_d1_equivalencia_bit_a_bit(obimvisib_mod, monkeypatch):
    pecas = todas()["d1"]()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    res_py = linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] > 0

    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    res_nat = linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["unir_intervalos"] == 0

    assert len(res_nat) == len(res_py)
    for pls_nat, pls_py in zip(res_nat, res_py):
        assert len(pls_nat) == len(pls_py)
        for seg_nat, seg_py in zip(pls_nat, pls_py):
            assert seg_nat.shape == seg_py.shape
            assert np.array_equal(_bits(seg_nat), _bits(seg_py))
