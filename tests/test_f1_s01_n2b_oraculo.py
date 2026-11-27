# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-N2b: `obimvisib.filtrar_e_recortar` nativo e seletor em `visib_mapa`."""
from __future__ import annotations

import importlib, os, re, shutil, subprocess, sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from obim_geometria import visib_mapa, visib_nativo
from obim_geometria.visib_base import _preparar_triangulos
from obim_geometria.visibilidade import linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas

PASTA_NATIVO = Path(__file__).resolve().parent.parent / "native" / "obim_visib"
BUILD_SH = PASTA_NATIVO / "build.sh"
_POS_NAN = np.uint64(0x7FF8000000000000).view(np.float64)
_NEG_NAN = np.uint64(0xFFF8000000000000).view(np.float64)
_GUARD_MSVC = re.compile(
    r"#\s*(?:if\b[^\n]*_M_FP_PRECISE|ifndef\s+_M_FP_PRECISE\b)"
    r"(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b"
)


def _bits(a: np.ndarray) -> np.ndarray:
    assert a.dtype == np.float64
    return np.ascontiguousarray(a).view(np.uint64)


def _igual_bits(obt, esp) -> None:
    he_o, lo_o, hi_o = obt
    he_e, lo_e, hi_e = esp
    assert he_o.dtype == np.int64 and he_e.dtype == np.int64
    assert np.array_equal(he_o, he_e) and np.array_equal(_bits(lo_o), _bits(lo_e)) and np.array_equal(_bits(hi_o), _bits(hi_e))


def _cena(tris, arestas, *, ea=None, eb=None, tv=None, pe=None, pt=None, tol_z=1e-4, d_eps=0.0, **ov):
    p = np.asarray(tris, dtype=np.float64).reshape(-1, 3)
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv_p, _ = _preparar_triangulos(
        p, np.arange(len(p), dtype=np.int64).reshape(-1, 3)
    )
    assert len(A) == len(tris)
    a = np.asarray([e[0] for e in arestas], dtype=np.float64).reshape(-1, 3)
    b = np.asarray([e[1] for e in arestas], dtype=np.float64).reshape(-1, 3)
    nt, ne = len(A), len(a)
    campos = dict(
        pe=np.repeat(np.arange(ne, dtype=np.int64), nt) if pe is None else np.asarray(pe, dtype=np.int64),
        pt=np.tile(np.arange(nt, dtype=np.int64), ne) if pt is None else np.asarray(pt, dtype=np.int64),
        a=a, b=b, d=b - a,
        ea=np.full(ne, -1, dtype=np.int64) if ea is None else np.asarray(ea, dtype=np.int64),
        eb=np.full(ne, -2, dtype=np.int64) if eb is None else np.asarray(eb, dtype=np.int64),
        tv=tv_p if tv is None else np.asarray(tv, dtype=np.int64),
        A=A, gx=gx, gy=gy, nx_=nx_, ny_=ny_, cc_=cc_,
        tx0=tx0, tx1=tx1, ty0=ty0, ty1=ty1, tzmax=tzmax,
        ex0=np.minimum(a[:, 0], b[:, 0]), ex1=np.maximum(a[:, 0], b[:, 0]),
        ey0=np.minimum(a[:, 1], b[:, 1]), ey1=np.maximum(a[:, 1], b[:, 1]),
        ezmin=np.minimum(a[:, 2], b[:, 2]), nt_all=max(nt, 1), tol_z=float(tol_z), d_eps=float(d_eps),
    )
    campos.update(ov)
    return tuple(campos.values())


def _comparar(mod, args, *, vazio: bool | None = None):
    H_py: list = []
    visib_mapa._filtrar_e_recortar_py(*args, H_py)
    nat = mod.filtrar_e_recortar(*args)
    assert isinstance(nat, tuple) and len(nat) == 3
    assert nat[0].dtype == np.int64 and nat[1].dtype == np.float64 and nat[2].dtype == np.float64
    if not H_py:
        assert vazio is not False and len(nat[0]) == len(nat[1]) == len(nat[2]) == 0
    else:
        assert vazio is not True and len(H_py) == 1
        _igual_bits(nat, H_py[0])
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
    out = tmp_path_factory.mktemp("obimvisib_n2b")
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


def _tem_guarda_msvc(arq: Path, vistos: set[Path] | None = None) -> bool:
    vistos = set() if vistos is None else vistos
    if arq in vistos or not arq.is_file():
        return False
    vistos.add(arq)
    cod = _sem_com(arq.read_text(encoding="utf-8"))
    return bool(_GUARD_MSVC.search(cod)) or any(
        _tem_guarda_msvc((arq.parent / inc).resolve(), vistos) for inc in re.findall(r'#\s*include\s*"([^"]+)"', cod)
    )


def test_fontes_guarda_msvc_e_sem_fast_math():
    cpps = sorted(PASTA_NATIVO.glob("*.cpp"))
    assert cpps
    for cpp in cpps:
        assert _tem_guarda_msvc(cpp.resolve()), f"falta guarda _M_FP_PRECISE em {cpp.name} (ou header incluido)"
    for arq in [*cpps, *sorted(PASTA_NATIVO.glob("*.h")), PASTA_NATIVO / "CMakeLists.txt"]:
        txt = arq.read_text(encoding="utf-8")
        cod = re.sub(r"#.*", "", txt) if arq.name == "CMakeLists.txt" else re.sub(r"^\s*#\s*error\b.*$", "", _sem_com(txt), flags=re.M)
        assert "-ffast-math" not in cod.lower() and "/fp:fast" not in cod.lower(), f"flag proibida em {arq.name}"


def test_carregar_exige_versao_e_info_bate(obimvisib_mod, monkeypatch):
    ver = obimvisib_mod.versao()
    assert isinstance(ver, str) and ver and visib_nativo.carregar() is obimvisib_mod
    inf = visib_nativo.info()
    assert inf["disponivel"] is True and inf["versao"] == ver and inf["flags_fp"] == obimvisib_mod.flags_fp()
    monkeypatch.setitem(sys.modules, "obimvisib", SimpleNamespace(versao=lambda: f"{ver}-incompativel", flags_fp=lambda: ""))
    assert visib_nativo.carregar() is None and visib_nativo.info()["disponivel"] is False


def test_seletor_desligado_e_import_error(monkeypatch):
    args = _cena([[(0, 0, 5), (2, 0, 5), (0, 2, 5)]], [[(0.2, 0.2, 0), (1.0, 0.2, 0)]])
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 0
    H_l: list = []
    visib_mapa._filtrar_e_recortar(*args, H_l)
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 1 and len(H_l) == 1
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    monkeypatch.setitem(sys.modules, "obimvisib", None)
    visib_mapa._zerar_chamadas_py()
    with pytest.raises(ImportError, match=r".+"):
        visib_mapa._filtrar_e_recortar(*args, [])
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 0


def test_seletor_ligado_e_compactacao_hl(obimvisib_mod, monkeypatch):
    args = _cena([[(0, 0, 5), (2, 0, 5), (0, 2, 5)]], [[(0.0, 0.2, 0), (1.0, 0.2, 0)]])
    n_prev = 1_499_999
    prev = [(np.array([1], dtype=np.int64), np.array([0.0]), np.array([0.1])),
            (np.zeros(n_prev, dtype=np.int64), np.zeros(n_prev), np.full(n_prev, 0.2))]
    H_py, H_nat = list(prev), list(prev)
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    visib_mapa._filtrar_e_recortar(*args, H_py)
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 1 and len(H_py) == 1
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    visib_mapa._filtrar_e_recortar(*args, H_nat)
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 0 and len(H_nat) == 1
    _igual_bits(H_nat[0], H_py[0])


def test_vazio_filtro_zerado_par_unico_e_dedup(obimvisib_mod, monkeypatch):
    # Mutante: dedup removida (pe fora de ordem com pares repetidos quebra agrupamento por aresta).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    tri = [[(0, 0, 5), (2, 0, 5), (0, 2, 5)], [(0.5, 0, 6), (2.5, 0, 6), (0.5, 2, 6)]]
    ar = [[(0.1, 0.2, 0), (1.4, 0.2, 0)], [(0.2, 0.4, 0), (1.2, 0.4, 0)]]
    _comparar(obimvisib_mod, _cena(tri, ar, pe=[], pt=[]), vazio=True)
    _comparar(obimvisib_mod, _cena(tri[:1], [[(0.1, 0.2, 10), (1.4, 0.2, 10)]]), vazio=True)
    _comparar(obimvisib_mod, _cena(tri[:1], ar[:1]), vazio=False)
    _comparar(obimvisib_mod, _cena(tri, ar, pe=[1, 0, 1, 0, 0], pt=[0, 1, 0, 0, 1]), vazio=False)


def test_bordas_caixa_eixo_y_limiar_1e5_e_tol_deps(obimvisib_mod, monkeypatch):
    # Mutantes: trocar >= por > no filtro; 1e-5 por 1e-6; eps sem abs; eixo y trocado.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    tri = [[(0, 0, 5), (2, 0, 5), (0, 2, 5)]]
    ar_b = [
        [(2.0, 0.1, 0), (2.0, 1.0, 0)], [(0.0, 0.1, 0), (0.0, 1.5, 0)],
        [(0.1, 2.0, 0), (1.0, 2.0, 0)], [(0.1, 0.0, 0), (1.5, 0.0, 0)],
        [(0.2, 0.2, 4.75), (1.0, 0.2, 4.75)],
        [(0.2, 0.2, float(np.nextafter(4.75, 0.0))), (1.0, 0.2, float(np.nextafter(4.75, 0.0)))],
    ]
    res = _comparar(obimvisib_mod, _cena(tri, ar_b, tol_z=0.25, d_eps=-0.25), vazio=False)
    assert set(res[0].tolist()) == {0, 1, 2, 3, 5}
    for tz, de in ((0.0, 0.0), (-0.25, -0.1), (2.0, 2.0), (10.0, -0.5)):
        _comparar(obimvisib_mod, _cena(tri, ar_b, tol_z=tz, d_eps=de))
    ar_l = [[(-1.0 + 5e-6, 0.2, 0), (5e-6, 0.2, 0)], [(-1.0 + 2e-5, 0.2, 0), (2e-5, 0.2, 0)]]
    assert _comparar(obimvisib_mod, _cena(tri, ar_l, tol_z=0.0, d_eps=0.0), vazio=False)[0].tolist() == [1]
    tri_y = [[(0, 10, 5), (2, 10, 5), (0, 12, 5)]]
    ar_y = [[(0.2, 10.2, 0), (1.0, 10.8, 0)], [(0.2, 0.2, 0), (1.0, 0.8, 0)], [(10.2, 10.2, 0), (11.0, 10.8, 0)]]
    assert _comparar(obimvisib_mod, _cena(tri_y, ar_y), vazio=False)[0].tolist() == [0]


def test_vertice_compartilhado_limites(obimvisib_mod, monkeypatch):
    # Mutante: pular so a_sh (esquecer b_sh) ou trocar >= por > em b_z >= z_b - tol_z.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    tri = [[(0, 0, 2), (2, 0, 2), (0, 2, 2)]]
    lim = 1.75
    z_ok, z_ab, z_ac = lim, float(np.nextafter(lim, 0.0)), float(np.nextafter(lim, 3.0))
    ar = [
        [(0, 0, 0), (0.8, 0.4, z_ok)], [(0, 0, 0), (0.8, 0.4, z_ac)], [(0, 0, 0), (0.8, 0.4, z_ab)],
        [(0.8, 0.4, z_ok), (0, 0, 0)], [(0.8, 0.4, z_ac), (0, 0, 0)], [(0.8, 0.4, z_ab), (0, 0, 0)],
        [(0, 0, z_ab), (2, 0, z_ok)], [(0, 0, z_ab), (2, 0, z_ab)],
    ]
    res = _comparar(obimvisib_mod, _cena(tri, ar, ea=[0, 0, 0, 9, 9, 9, 0, 0], eb=[8, 8, 8, 0, 0, 0, 1, 1], tv=[[0, 1, 2]], tol_z=0.25), vazio=False)
    assert res[0].tolist() == [2, 5, 7]


def test_vertical_xy_limiar_1e12_e_eq_fail_z(obimvisib_mod, monkeypatch):
    # Mutante: eq_fail invertido no corte Z (r==0 falha em Z, mas nao nos cortes XY).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    tri, e12 = [[(0, 0, 2), (2, 0, 2), (0, 2, 2)]], 1e-12
    e12p = float(np.nextafter(e12, 1.0))
    ar = [
        [(0.5, 0.5, 0), (0.5, 0.5, 1)],
        [(0.2, 0.2, 0), (0.2 + e12, 1.2, 0)], [(-0.1, 0.2, 0), (-0.1 + e12, 1.2, 0)],
        [(0.2, 0.2, 0), (0.2 + e12p, 1.2, 0)], [(0.2, 0.2, 0), (0.2 - e12p, 1.2, 0)],
        [(0.2, 0.2, 0), (1.2, 0.2 + e12, 0)], [(0.2, -0.1, 0), (1.2, -0.1 - e12, 0)],
        [(0.0, 0.1, 0), (0.0, 1.0, 0)],
        [(0.2, 0.2, 1.75), (1.0, 0.2, 1.75)], [(0.2, 0.2, 1.5), (1.0, 0.2, 1.5)],
    ]
    res = _comparar(obimvisib_mod, _cena(tri, ar, tol_z=0.25, d_eps=0.0), vazio=False)
    assert {0, 2, 6, 8}.isdisjoint(res[0].tolist()) and {7, 9}.issubset(res[0].tolist())


def test_aleatorio_com_dedup_dtypes_e_nao_contiguos(obimvisib_mod, monkeypatch):
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    rng = np.random.default_rng(20260410)
    nt, ne = 18, 25
    bt = rng.uniform(-2.0, 2.0, size=(nt, 3))
    tris = np.stack([bt, bt + rng.uniform([0.3, -0.2, -0.3], [1.5, 0.4, 0.3], size=(nt, 3)),
                     bt + rng.uniform([-0.2, 0.3, -0.3], [0.4, 1.5, 0.3], size=(nt, 3))], axis=1)
    ar = np.stack([rng.uniform(-2.5, 3.0, size=(ne, 3)), rng.uniform(-2.5, 3.0, size=(ne, 3))], axis=1)
    pe_r, pt_r = rng.integers(0, ne, size=300, dtype=np.int64), rng.integers(0, nt, size=300, dtype=np.int64)
    args = _cena(tris, ar, pe=pe_r, pt=pt_r, tol_z=1e-3, d_eps=-1e-4)
    esp = _comparar(obimvisib_mod, args, vazio=False)

    def _nc(x, inv=False):
        if not isinstance(x, np.ndarray):
            return x
        arr = np.asfortranarray(np.repeat(x, 2, axis=0))[::2] if x.ndim == 2 else (np.repeat(x, 2)[::-2] if inv else np.repeat(x, 2)[::2])
        arr.setflags(write=False)
        return arr

    _igual_bits(obimvisib_mod.filtrar_e_recortar(*(_nc(x, i < 2) for i, x in enumerate(args))), esp)
    H_nat: list = []
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    visib_mapa._filtrar_e_recortar(pe_r.astype(np.int32), pt_r.astype(np.int32), *args[2:], H_nat)
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 0 and len(H_nat) == 1
    _igual_bits(H_nat[0], esp)


def test_nan_inf_e_caso_m12(obimvisib_mod, monkeypatch):
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    tri = [[(0, 0, 5), (2, 0, 5), (0, 2, 5)], [(0, 0, 6), (2, 0, 6), (0, 2, 6)], [(0, 0, 7), (2, 0, 7), (0, 2, 7)]]
    ar = [[(0.2, 0.2, 0), (1.2, 0.2, 0)], [(0.2, 0.4, 0), (1.2, 0.4, 0)], [(0.2, 0.6, 0), (1.2, 0.6, 0)]]
    args = list(_cena(tri, ar))
    for idx, pos, val in ((9, 1, np.nan), (14, 2, -np.inf), (15, 2, np.inf), (18, 2, np.inf), (23, 1, -np.inf), (2, (2, 2), np.nan)):
        args[idx] = args[idx].copy()
        args[idx][pos] = val
    _comparar(obimvisib_mod, tuple(args), vazio=False)

    # Caso M12: em n grande com empates +0/-0 ou NaNs distintos em hhi, o np.argsort instavel do Python
    # pode variar os bits (limitacao aceita); em n=2 ambos fundem em [0], [0.0], [NaN] preservando bits.
    he, lo = np.array([0, 0], dtype=np.int64), np.array([0.0, 0.5], dtype=np.float64)
    for hhi in (np.array([_POS_NAN, _NEG_NAN]), np.array([_NEG_NAN, _POS_NAN])):
        obt, esp = obimvisib_mod.unir_intervalos(he, lo, hhi), visib_mapa._unir_intervalos_py(he, lo, hhi)
        assert np.array_equal(obt[0], [0]) and int(_bits(obt[1])[0]) == 0 and np.isnan(obt[2][0])
        _igual_bits(obt, esp)


def test_pipeline_d1_equivalencia_bit_a_bit(obimvisib_mod, monkeypatch):
    pecas = todas()["d1"]()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    res_py = linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] > 0
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    res_nat = linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["filtrar_e_recortar"] == 0 and len(res_nat) == len(res_py)
    for pls_nat, pls_py in zip(res_nat, res_py):
        assert len(pls_nat) == len(pls_py)
        for seg_nat, seg_py in zip(pls_nat, pls_py):
            assert seg_nat.shape == seg_py.shape and np.array_equal(_bits(seg_nat), _bits(seg_py))
