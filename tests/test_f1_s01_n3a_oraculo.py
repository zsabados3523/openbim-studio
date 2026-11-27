# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-N3a: `obimvisib.subseg_cels`, `obimvisib.expandir_celulas` e seletor."""
from __future__ import annotations

import importlib, os, re, shutil, subprocess, sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from obim_geometria import visib_base, visib_mapa, visib_nativo
from obim_geometria.visibilidade import linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas

PASTA_NATIVO = Path(__file__).resolve().parent.parent / "native" / "obim_visib"
BUILD_SH = PASTA_NATIVO / "build.sh"
_I64_MIN, _I64_MAX = -(1 << 63), (1 << 63) - 1
_POS_NAN = np.uint64(0x7FF8000000000000).view(np.float64)
_NEG_NAN = np.uint64(0xFFF8000000000000).view(np.float64)
_GUARD_MSVC = re.compile(
    r"#\s*(?:if\b[^\n]*_M_FP_PRECISE|ifndef\s+_M_FP_PRECISE\b)(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b"
)
_GUARD_FMATH = re.compile(
    r"#\s*(?:ifdef\s+__FAST_MATH__\b|if\b[^\n]*__FAST_MATH__)(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b"
)


def _bits(a: np.ndarray) -> np.ndarray:
    assert a.dtype == np.float64
    return np.ascontiguousarray(a).view(np.uint64)


def _igual_subseg(obt, esp) -> None:
    assert isinstance(obt, tuple) and len(obt) == 9
    for i in (0, 5, 6, 7, 8):
        assert obt[i].dtype == np.int64 and esp[i].dtype == np.int64
        assert obt[i].shape == esp[i].shape and np.array_equal(obt[i], esp[i])
    for i in (1, 2):
        assert obt[i].shape == esp[i].shape and np.array_equal(_bits(obt[i]), _bits(esp[i]))
    for i in (3, 4):
        assert obt[i].ndim == 2 and obt[i].shape == esp[i].shape == (len(esp[0]), 3)
        assert np.array_equal(_bits(obt[i]), _bits(esp[i]))


def _igual_expandir(obt, esp) -> None:
    assert isinstance(obt, tuple) and len(obt) == 2
    for i in (0, 1):
        assert obt[i].dtype == np.int64 and esp[i].dtype == np.int64
        assert obt[i].shape == esp[i].shape and np.array_equal(obt[i], esp[i])


def _comparar_subseg(mod, a, d, nsub, mn_x: float, mn_y: float, cg: float, Wc: int, Hc: int):
    a64, d64, n64 = np.asarray(a, dtype=np.float64), np.asarray(d, dtype=np.float64), np.asarray(nsub, dtype=np.int64)
    nat = mod.subseg_cels(a64, d64, n64, mn_x, mn_y, cg, Wc, Hc)
    _igual_subseg(nat, visib_base._subseg_cels_py(a64, d64, n64, mn_x, mn_y, cg, Wc, Hc))
    return nat


def _comparar_expandir(mod, ix0, ix1, iy0, iy1, nx: int):
    args = tuple(np.asarray(v, dtype=np.int64) for v in (ix0, ix1, iy0, iy1))
    nat = mod.expandir_celulas(*args, nx)
    _igual_expandir(nat, visib_base._expandir_celulas_py(*args, nx))
    return nat


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
    out = tmp_path_factory.mktemp("obimvisib_n3a")
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


def _sem_com(txt: str) -> str:
    return re.sub(r"//.*", "", re.sub(r"/\*.*?\*/", "", txt, flags=re.S))


def _tem_guarda(arq: Path, padrao: re.Pattern[str], vistos: set[Path] | None = None) -> bool:
    vistos = set() if vistos is None else vistos
    if arq in vistos or not arq.is_file():
        return False
    vistos.add(arq)
    cod = _sem_com(arq.read_text(encoding="utf-8"))
    return bool(padrao.search(cod)) or any(
        _tem_guarda((arq.parent / inc).resolve(), padrao, vistos) for inc in re.findall(r'#\s*include\s*"([^"]+)"', cod)
    )


def test_fontes_guarda_msvc_e_sem_fast_math():
    cpps = sorted(PASTA_NATIVO.glob("*.cpp"))
    assert cpps
    for cpp in cpps:
        assert _tem_guarda(cpp.resolve(), _GUARD_MSVC), f"falta guarda _M_FP_PRECISE em {cpp.name}"
        assert _tem_guarda(cpp.resolve(), _GUARD_FMATH), f"falta guarda __FAST_MATH__ em {cpp.name}"
    for arq in [*cpps, *sorted(PASTA_NATIVO.glob("*.h")), PASTA_NATIVO / "CMakeLists.txt"]:
        txt = arq.read_text(encoding="utf-8")
        cod = re.sub(r"#.*", "", txt) if arq.name == "CMakeLists.txt" else re.sub(r"^\s*#\s*error\b.*$", "", _sem_com(txt), flags=re.M)
        assert "-ffast-math" not in cod.lower() and "/fp:fast" not in cod.lower(), f"flag proibida em {arq.name}"


def test_seletor_contadores_e_import_error(monkeypatch):
    a, d = np.array([[0.1, 0.2, 0.3]]), np.array([[1.0, 0.5, -0.2]])
    nsub = np.array([2], dtype=np.int64)
    ix0, ix1, iy0, iy1 = (np.array([v], dtype=np.int64) for v in (1, 2, 0, 1))
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    assert visib_mapa._obter_chamadas_py()["subseg_cels"] == 0 and visib_mapa._obter_chamadas_py()["expandir_celulas"] == 0
    visib_base._subseg_cels(a, d, nsub, 0.0, 0.0, 1.0, 4, 4)
    visib_base._expandir_celulas(ix0, ix1, iy0, iy1, 4)
    cnt = visib_mapa._obter_chamadas_py()
    assert cnt["subseg_cels"] == 1 and cnt["expandir_celulas"] == 1
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    for mod_fake in (None, SimpleNamespace(versao=lambda: visib_nativo.VERSAO_ESPERADA, flags_fp=lambda: "")):
        monkeypatch.setitem(sys.modules, "obimvisib", mod_fake)
        visib_mapa._zerar_chamadas_py()
        with pytest.raises(ImportError, match=r".+"):
            visib_base._subseg_cels(a, d, nsub, 0.0, 0.0, 1.0, 4, 4)
        with pytest.raises(ImportError, match=r".+"):
            visib_base._expandir_celulas(ix0, ix1, iy0, iy1, 4)
        cnt = visib_mapa._obter_chamadas_py()
        assert cnt["subseg_cels"] == 0 and cnt["expandir_celulas"] == 0


def test_seletor_ligado_e_int32_convertido(obimvisib_mod, monkeypatch):
    a = np.array([[0.2, 0.4, 1.0], [1.5, -0.3, 2.0]], dtype=np.float64)
    d = np.array([[1.2, 0.8, -0.5], [-0.9, 1.7, 0.3]], dtype=np.float64)
    nsub = np.array([3, 5], dtype=np.int64)
    ix0, ix1 = np.array([0, 2], dtype=np.int64), np.array([2, 3], dtype=np.int64)
    iy0, iy1 = np.array([1, 0], dtype=np.int64), np.array([2, 2], dtype=np.int64)
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    esp_s = visib_base._subseg_cels_py(a, d, nsub, 0.0, -1.0, 0.5, 10, 10)
    esp_e = visib_base._expandir_celulas_py(ix0, ix1, iy0, iy1, 10)
    # Ponte direta usa .noconvert(); glue converte int32 e nao chama Python.
    with pytest.raises(TypeError):
        obimvisib_mod.subseg_cels(a, d, nsub.astype(np.int32), 0.0, -1.0, 0.5, 10, 10)
    with pytest.raises(TypeError):
        obimvisib_mod.expandir_celulas(ix0.astype(np.int32), ix1, iy0, iy1, 10)
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    _igual_subseg(visib_base._subseg_cels(a, d, nsub.astype(np.int32), 0.0, -1.0, 0.5, 10, 10), esp_s)
    _igual_expandir(visib_base._expandir_celulas(*(v.astype(np.int32) for v in (ix0, ix1, iy0, iy1)), 10), esp_e)
    cnt = visib_mapa._obter_chamadas_py()
    assert cnt["subseg_cels"] == 0 and cnt["expandir_celulas"] == 0


def test_subseg_cels_vazios_zeros_m2_e_aleatorio(obimvisib_mod, monkeypatch):
    # Mutante M2: t1 = t0 + 1.0/dn diverge bit a bit de (k+1)/dn em n=5, 7, 10 (e cobre n=3).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    v0 = np.zeros((0, 3), dtype=np.float64)
    _comparar_subseg(obimvisib_mod, v0, v0, np.zeros(0, dtype=np.int64), 0.0, 0.0, 1.0, 5, 5)
    a3 = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0], [-1.0, 5.0, 2.0]])
    d3 = np.array([[1.0, 1.0, 1.0], [-0.5, 0.5, 0.0], [2.0, -3.0, 1.0]])
    _comparar_subseg(obimvisib_mod, a3, d3, [0, 0, 0], 0.0, 0.0, 1.0, 5, 5)
    a_m2 = np.array([
        [0.0, 0.0, 0.0], [-2.5, 4.1, 1.0], [0.1, 0.2, -0.3], [9.0, 9.0, 9.0],
        [3.3, -1.7, 0.5], [1.0, 1.0, 1.0], [-0.7, 2.9, 4.2], [5.0, 5.0, 5.0],
    ])
    d_m2 = np.array([
        [1.0, 1.0, 1.0], [6.7, -5.2, 0.9], [1.3, 2.7, -1.1], [0.0, 0.0, 0.0],
        [-4.9, 6.3, 2.2], [0.0, 0.0, 0.0], [5.1, -4.4, -3.3], [-1.0, -1.0, -1.0],
    ])
    _comparar_subseg(obimvisib_mod, a_m2, d_m2, [0, 3, 5, 0, 7, 1, 10, 0], -1.0, -1.0, 0.75, 8, 8)
    rng = np.random.default_rng(20260415)
    _comparar_subseg(
        obimvisib_mod, rng.uniform(-5.0, 12.0, (35, 3)), rng.uniform(-6.0, 6.0, (35, 3)),
        rng.integers(0, 12, 35, dtype=np.int64), -2.5, -3.1, 0.37, 29, 23,
    )
    # Indices 64-bit sem truncamento para int32 (Wc, Hc > 2^31).
    _comparar_subseg(obimvisib_mod, [[5e10 + 0.25, 6e10 + 0.75, 0.0]], [[1.0, -2.0, 0.5]], [2], 0.0, 0.0, 1.0, 10**11, 10**11)


def test_subseg_cels_sinal_zero_nan_inf_e_m3(obimvisib_mod, monkeypatch):
    # Mutante M3 (min_f/max_f vs std::min/fmin com -0.0 e NaN) e spec 3.1/3.2.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    a_z = np.array([[-0.0, -0.0, -0.0], [0.0, -0.0, 0.0]])
    d_z = np.array([[-0.0, 0.0, -0.0], [-0.0, -0.0, 0.0]])
    res_z = _comparar_subseg(obimvisib_mod, a_z, d_z, [1, 2], 0.0, 0.0, 1.0, 5, 5)
    assert int(_bits(res_z[3])[0, 0]) == 0x8000000000000000
    # Spec 3.1: recorte_interno.h compartilhado preserva -0.0/+0.0 e -NaN/+NaN em max_f.
    he, lo = np.array([0, 0], dtype=np.int64), np.array([0.0, 0.0])
    for hhi in (np.array([-0.0, 0.0]), np.array([0.0, -0.0]), np.array([_POS_NAN, _NEG_NAN]), np.array([_NEG_NAN, _POS_NAN])):
        assert np.array_equal(_bits(obimvisib_mod.unir_intervalos(he, lo, hhi)[2]), _bits(visib_mapa._unir_intervalos_py(he, lo, hhi)[2]))
    # Spec 3.2: em +inf/1e300 Python estoura astype(int64) -> 0; C++ faz clamp sem UB -> dim-1.
    # Linha 3 gera sa=(NaN, NaN) e sb=(+inf, -inf) em k=0, matando std::fmin/fmax/std::min invertido.
    a_ext = np.array([[1e300, -1e300, 0.0], [np.inf, -np.inf, 0.0], [_NEG_NAN, 2.5, 0.0], [2.5, 2.5, 0.0]])
    d_ext = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, _POS_NAN, 0.0], [np.inf, -np.inf, 0.0]])
    s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = obimvisib_mod.subseg_cels(a_ext, d_ext, np.array([1, 1, 1, 2], dtype=np.int64), 0.0, 0.0, 1.0, 7, 5)
    assert s_l.tolist() == [0, 1, 2, 3, 3] and sx0.tolist() == [6, 6, 0, 0, 6] and sx1.tolist() == [6, 6, 0, 0, 6]
    assert sy0.tolist() == [0, 0, 0, 0, 0] and sy1.tolist() == [0, 0, 0, 0, 0]
    assert np.isnan(sa[2, 0]) and np.isnan(sa[3, 0]) and np.isposinf(sb[3, 0])


def test_expandir_celulas_casos_m4_e_64bit(obimvisib_mod, monkeypatch):
    # Mutante M4: ordem coluna-maior em vez de linha-maior.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    z = np.zeros(0, dtype=np.int64)
    _comparar_expandir(obimvisib_mod, z, z, z, z, 10)
    _comparar_expandir(obimvisib_mod, [3, 0], [2, 2], [0, 5], [2, 4], 10)
    obj, cel = _comparar_expandir(obimvisib_mod, [1], [3], [2], [3], 10)
    assert obj.tolist() == [0, 0, 0, 0, 0, 0] and cel.tolist() == [21, 22, 23, 31, 32, 33]
    _comparar_expandir(obimvisib_mod, [2, 1, 4, 0], [1, 3, 4, 2], [0, 2, 5, 3], [3, 3, 4, 3], 10)
    rng = np.random.default_rng(20260416)
    ix0, iy0 = rng.integers(0, 20, 30, dtype=np.int64), rng.integers(0, 20, 30, dtype=np.int64)
    _comparar_expandir(obimvisib_mod, ix0, ix0 + rng.integers(-1, 5, 30), iy0, iy0 + rng.integers(-1, 5, 30), 37)
    obj64, cel64 = _comparar_expandir(obimvisib_mod, [5], [6], [3], [4], 10**9)
    assert obj64.tolist() == [0, 0, 0, 0] and cel64.tolist() == [3_000_000_005, 3_000_000_006, 4_000_000_005, 4_000_000_006]


def test_nao_contiguos_invertidos_so_leitura_m1(obimvisib_mod, monkeypatch):
    # Mutante M1: ignorar stride em View1D/View2D (Fortran, stride coluna != 1, stride negativo, ro).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    a = np.arange(18, dtype=np.float64).reshape(6, 3) * 0.35 - 1.2
    d = np.arange(18, dtype=np.float64).reshape(6, 3) * -0.21 + 0.7
    nsub = np.array([2, 0, 3, 1, 5, 2], dtype=np.int64)
    esp_s = _comparar_subseg(obimvisib_mod, a, d, nsub, -2.0, -2.0, 0.8, 12, 12)
    a_f, d_f, n_s = np.asfortranarray(np.repeat(a, 2, axis=0))[::2], np.asfortranarray(np.repeat(d, 2, axis=0))[::2], np.repeat(nsub, 2)[::2]
    for arr in (a_f, d_f, n_s):
        arr.setflags(write=False)
    assert not a_f.flags.c_contiguous and not a_f.flags.writeable
    _igual_subseg(obimvisib_mod.subseg_cels(a_f, d_f, n_s, -2.0, -2.0, 0.8, 12, 12), esp_s)

    def _s2_inv(m: np.ndarray) -> np.ndarray:
        buf = np.zeros((len(m) * 2, 6), dtype=np.float64)
        buf[1::2, ::2] = m[::-1]
        v = buf[::-2, ::2]
        v.setflags(write=False)
        assert np.array_equal(v, m)
        return v

    n_inv = np.repeat(nsub[::-1], 2)[::-2]
    n_inv.setflags(write=False)
    _igual_subseg(obimvisib_mod.subseg_cels(_s2_inv(a), _s2_inv(d), n_inv, -2.0, -2.0, 0.8, 12, 12), esp_s)
    ix0, ix1 = np.array([1, 4, 2, 0, 3], dtype=np.int64), np.array([3, 3, 2, 2, 5], dtype=np.int64)
    iy0, iy1 = np.array([0, 1, 4, 2, 1], dtype=np.int64), np.array([2, 3, 3, 3, 2], dtype=np.int64)
    esp_e = _comparar_expandir(obimvisib_mod, ix0, ix1, iy0, iy1, 12)
    inv_args = [np.repeat(arr[::-1], 2)[::-2] for arr in (ix0, ix1, iy0, iy1)]
    for v in inv_args:
        v.setflags(write=False)
    _igual_expandir(obimvisib_mod.expandir_celulas(*inv_args, 12), esp_e)


def test_subseg_cels_validacoes_e_overflow(obimvisib_mod):
    a1, n1 = np.zeros((1, 3)), np.array([1], dtype=np.int64)
    # Comprimentos, n1 != 3 (inclusive n0 == 0), nsub < 0 e parametros invalidos (spec 3.3 e 4).
    for a, d, ns in (
        (np.zeros((2, 3)), a1, n1), (a1, a1, np.array([1, 1], dtype=np.int64)),
        (np.zeros((1, 4)), a1, n1), (a1, np.zeros((1, 2)), n1),
        (np.zeros((0, 4)), np.zeros((0, 3)), np.zeros(0, dtype=np.int64)),
        (np.zeros((0, 3)), np.zeros((0, 2)), np.zeros(0, dtype=np.int64)),
        (a1, a1, np.array([-1], dtype=np.int64)),
    ):
        with pytest.raises(ValueError):
            obimvisib_mod.subseg_cels(a, d, ns, 0.0, 0.0, 1.0, 4, 4)
    for mn_x, mn_y, cg, Wc, Hc in (
        (0.0, 0.0, 0.0, 4, 4), (0.0, 0.0, -1.0, 4, 4), (0.0, 0.0, np.nan, 4, 4), (0.0, 0.0, np.inf, 4, 4),
        (np.nan, 0.0, 1.0, 4, 4), (0.0, -np.inf, 1.0, 4, 4), (0.0, 0.0, 1.0, 0, 4), (0.0, 0.0, 1.0, 4, -1),
    ):
        with pytest.raises(ValueError):
            obimvisib_mod.subseg_cels(a1, a1, n1, mn_x, mn_y, cg, Wc, Hc)
    a2 = np.zeros((2, 3))
    for ns in ([_I64_MAX, 1], [1 << 62, 0], [1 << 50, 0]):
        with pytest.raises((ValueError, OverflowError)):
            obimvisib_mod.subseg_cels(a2, a2, np.array(ns, dtype=np.int64), 0.0, 0.0, 1.0, 4, 4)
    # Mutante M8: total + n estoura int64 (n > MAX - total); match exige rejeicao no limite, nao na alocacao.
    with pytest.raises(ValueError, match="limite"):
        obimvisib_mod.subseg_cels(a2, a2, np.array([1, _I64_MAX], dtype=np.int64), 0.0, 0.0, 1.0, 4, 4)


def test_expandir_celulas_validacoes_e_overflow(obimvisib_mod):
    z1, z2 = np.array([0], dtype=np.int64), np.array([0, 0], dtype=np.int64)
    for args in ((z2, z1, z1, z1), (z1, z2, z1, z1), (z1, z1, z2, z1), (z1, z1, z1, z2)):
        with pytest.raises(ValueError):
            obimvisib_mod.expandir_celulas(*args, 4)
    # Spec 3.4: qualquer w < 0 ou h < 0 levanta ValueError (inclui w<0&h<0 e w==0&h<0).
    for ix0, ix1, iy0, iy1 in (
        ([5], [3], [0], [0]), ([0], [0], [5], [3]), ([5], [3], [5], [3]),
        ([2], [1], [5], [3]), ([5], [3], [2], [1]), ([_I64_MAX], [_I64_MIN], [0], [0]),
    ):
        with pytest.raises(ValueError):
            obimvisib_mod.expandir_celulas(*(np.array(v, dtype=np.int64) for v in (ix0, ix1, iy0, iy1)), 4)
    # Spec 4: overflow em (x1-x0+1), w*h, total, limite gigante e y*nx+x.
    for ix0, ix1, iy0, iy1, nx in (
        ([_I64_MIN], [_I64_MAX], [0], [0], 1), ([0], [_I64_MAX], [0], [0], 1),
        ([0], [(1 << 32) - 1], [0], [(1 << 32) - 1], 1), ([0, 0], [(1 << 62) - 1, (1 << 62) - 1], [0, 0], [0, 0], 1),
        ([0], [1 << 50], [0], [0], 1), ([0], [0], [1 << 40], [1 << 40], 1 << 40),
        ([10], [10], [1], [1], _I64_MAX), ([-10], [-10], [-1], [-1], _I64_MAX),
    ):
        with pytest.raises((ValueError, OverflowError)):
            obimvisib_mod.expandir_celulas(*(np.array(v, dtype=np.int64) for v in (ix0, ix1, iy0, iy1)), nx)
    # Mutantes M5 (canto x1,y0), M6 (y<0 * nx>0) e M7 (y>0 * nx<0) em check_cel_coord.
    for ix0, ix1, iy0, iy1, nx in (
        ([_I64_MAX - 1], [_I64_MAX], [1], [1], 1),
        ([0], [0], [-2], [-2], _I64_MAX),
        ([0], [0], [3], [3], -(1 << 62)),
    ):
        with pytest.raises(ValueError, match="indice de celula"):
            obimvisib_mod.expandir_celulas(*(np.array(v, dtype=np.int64) for v in (ix0, ix1, iy0, iy1)), nx)
    # Mutante M9: total + prod estoura int64 (prod > MAX - total); match evita falso verde via length_error.
    with pytest.raises(ValueError, match="limite"):
        obimvisib_mod.expandir_celulas(
            np.array([0, 0], dtype=np.int64), np.array([0, _I64_MAX - 1], dtype=np.int64),
            np.array([0, 0], dtype=np.int64), np.array([0, 0], dtype=np.int64), 1,
        )


def test_pipeline_d1_equivalencia_bit_a_bit(obimvisib_mod, monkeypatch):
    pecas = todas()["d1"]()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    res_py = linhas_visiveis_multi(pecas, trabalhadores=1)
    cnt_py = visib_mapa._obter_chamadas_py()
    assert cnt_py["subseg_cels"] > 0 and cnt_py["expandir_celulas"] > 0
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    res_nat = linhas_visiveis_multi(pecas, trabalhadores=1)
    cnt_nat = visib_mapa._obter_chamadas_py()
    assert cnt_nat["subseg_cels"] == 0 and cnt_nat["expandir_celulas"] == 0 and len(res_nat) == len(res_py)
    for pls_nat, pls_py in zip(res_nat, res_py):
        assert len(pls_nat) == len(pls_py)
        for seg_nat, seg_py in zip(pls_nat, pls_py):
            assert seg_nat.shape == seg_py.shape and np.array_equal(_bits(seg_nat), _bits(seg_py))
