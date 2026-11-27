# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-N3c: `obimvisib.processar_celulas_e_recortar` e queda hibrida em `visib_mapa`.

Limites aceitos: sinal de zero e bits de NaN em empates de `hhi` (`np.argsort` instavel no Python).
"""
from __future__ import annotations

import ast, concurrent.futures, importlib, os, re, shutil, subprocess, sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from obim_geometria import visib_base, visib_mapa, visib_nativo, visibilidade
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas

RAIZ = Path(__file__).resolve().parent.parent
PASTA_NATIVO = RAIZ / "native" / "obim_visib"
BUILD_SH, VISIB_PY = PASTA_NATIVO / "build.sh", RAIZ / "geometria" / "obim_geometria" / "visibilidade.py"
_GUARD_MSVC = re.compile(r"#\s*(?:if\b[^\n]*_M_FP_PRECISE|ifndef\s+_M_FP_PRECISE\b)(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b")
_GUARD_FM = re.compile(r"#\s*(?:ifdef\s+__FAST_MATH__\b|if\s+defined(?:\s*\(\s*__FAST_MATH__\s*\)|\s+__FAST_MATH__\b))(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b")
_MALHA = ("a", "b", "d", "ea", "eb", "tv", "A", "gx", "gy", "nx_", "ny_", "cc_", "tx0", "tx1", "ty0", "ty1", "tzmax", "ex0", "ex1", "ey0", "ey1", "ezmin")
_NATIVOS = ("unir_intervalos", "filtrar_e_recortar", "expandir_celulas", "subseg_cels", "filtrar_arestas_mapa_z", "pares_celulas")


def _i64(*v) -> np.ndarray:
    return np.array(v, dtype=np.int64)


def _bits(a: np.ndarray) -> np.ndarray:
    assert a.dtype == np.float64
    return np.ascontiguousarray(a).view(np.uint64)


def _compactar_py(H_l: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not H_l:
        return np.zeros(0, np.int64), np.zeros(0, np.float64), np.zeros(0, np.float64)
    he, lo, hi = H_l[0] if len(H_l) == 1 else tuple(np.concatenate(x) for x in zip(*H_l))
    return visib_mapa._unir_intervalos_py(he, lo, hi)


def _igual_h(obt, esp) -> None:
    assert obt[0].dtype == np.int64 and obt[1].dtype == np.float64 and obt[2].dtype == np.float64
    assert np.array_equal(obt[0], esp[0]) and np.array_equal(_bits(obt[1]), _bits(esp[1])) and np.array_equal(_bits(obt[2]), _bits(esp[2]))


def _igual_visib(obt, esp) -> None:
    assert len(obt) == len(esp)
    for po, pe in zip(obt, esp):
        assert len(po) == len(pe)
        for so, se in zip(po, pe):
            assert so.shape == se.shape and np.array_equal(_bits(so), _bits(se))


def _ref_pares_celulas(
    t_s, iy_s, ix0_s, ix1_s, ek_idx, zf_flat, filtrar_zf, mn_x, mn_y, cg, Wc, Hc,
    a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax,
    ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, usar_subgrade, H_l,
    *, lim_t_bloco: int = 2_000_000, lim_e_bloco: int = 400_000, lim_denso_pares: int = 20_000_000,
) -> None:
    """Referencia fiel do laco de celulas original de `visibilidade.py:229-315`."""
    malha = (a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, H_l)
    w_s = ix1_s - ix0_s + 1
    nsub_c = np.maximum(1, np.ceil(np.maximum(np.abs(d[ek_idx, 0]), np.abs(d[ek_idx, 1])) / (0.999 * cg)).astype(np.int64))
    for t0, t1 in visib_base._fatias(w_s, lim_t_bloco):
        g_s, dx_s = visib_base._rle_idx(w_s[t0:t1])
        tobj, tcel = t_s[t0:t1][g_s], iy_s[t0:t1][g_s] * Wc + ix0_s[t0:t1][g_s] + dx_s
        if filtrar_zf:
            ok = tzmax[tobj] >= zf_flat[tcel] - 1e-9
            tobj, tcel = tobj[ok], tcel[ok]
        if not len(tobj):
            continue
        t_iy, t_ix = tcel // Wc, tcel % Wc
        bx0, by0 = int(t_ix.min()), int(t_iy.min())
        Wl, Hl = int(t_ix.max()) - bx0 + 1, int(t_iy.max()) - by0 + 1
        ncel_l, tcel = Wl * Hl, (t_iy - by0) * Wl + (t_ix - bx0)
        ord_t = np.argsort(tcel, kind="stable")
        tri_por_cel, cel_ord = tobj[ord_t], tcel[ord_t]
        cont = np.bincount(cel_ord, minlength=ncel_l)
        ini_cel, cell_tzmax = np.cumsum(cont) - cont, np.full(ncel_l, -np.inf)
        np.maximum.at(cell_tzmax, cel_ord, tzmax[tri_por_cel])
        for e0, e1 in visib_base._fatias(nsub_c, lim_e_bloco):
            ec = ek_idx[e0:e1]
            s_l, _, _, sa, sb, sx0, sx1, sy0, sy1 = visib_base._subseg_cels(a[ec], d[ec], nsub_c[e0:e1], mn_x, mn_y, cg, Wc, Hc)
            sx0, sx1, sy0, sy1 = np.maximum(sx0, bx0), np.minimum(sx1, bx0 + Wl - 1), np.maximum(sy0, by0), np.minimum(sy1, by0 + Hl - 1)
            okb = (sx1 >= sx0) & (sy1 >= sy0)
            s_l, sa, sb = s_l[okb], sa[okb], sb[okb]
            sobj, scel = visib_base._expandir_celulas(sx0[okb] - bx0, sx1[okb] - bx0, sy0[okb] - by0, sy1[okb] - by0, Wl)
            ok_sc = cell_tzmax[scel] > np.minimum(sa[:, 2], sb[:, 2])[sobj] + tol_z
            eobj, ecel = ec[s_l[sobj[ok_sc]]], scel[ok_sc]
            if not len(eobj):
                continue
            ch_ec = visib_base._dedup_int64(eobj.astype(np.int64) * ncel_l + ecel)
            eobj, ecel = ch_ec // ncel_l, ch_ec % ncel_l
            ntri_par = cont[ecel]
            nz = ntri_par > 0
            eobj, ecel, ntri_par = eobj[nz], ecel[nz], ntri_par[nz]
            if usar_subgrade and len(eobj):
                eh_d = (cont >= 128)[ecel]
                if np.any(eh_d) and int(ntri_par[eh_d].sum()) >= lim_denso_pares:
                    eo_n, ec_n, nt_n = eobj[~eh_d], ecel[~eh_d], ntri_par[~eh_d]
                    for p0, p1 in visib_base._fatias(nt_n, 200_000, chaves=eo_n):
                        g3, kk = visib_base._rle_idx(nt_n[p0:p1])
                        visib_mapa._filtrar_e_recortar(eo_n[p0:p1][g3], tri_por_cel[ini_cel[ec_n[p0:p1]][g3] + kk], *malha)
                    visib_mapa._subgrade_celulas_densas(eobj[eh_d], ecel[eh_d], cont, ini_cel, tri_por_cel, bx0, by0, Wl, mn_x, mn_y, cg, *malha)
                    continue
            for p0, p1 in visib_base._fatias(ntri_par, 200_000, chaves=eobj):
                g3, kk = visib_base._rle_idx(ntri_par[p0:p1])
                visib_mapa._filtrar_e_recortar(eobj[p0:p1][g3], tri_por_cel[ini_cel[ecel[p0:p1]][g3] + kk], *malha)


def _cena(
    tris, arestas, spans, *, Wc: int = 4, Hc: int = 2, mn_x: float = 0.0, mn_y: float = 0.0, cg: float = 1.0,
    ek_idx=None, zf_flat=None, filtrar_zf: bool = False, tol_z: float = 1e-4, d_eps: float = 0.0,
    usar_subgrade: bool = True, lim_t_bloco: int = 2_000_000, lim_e_bloco: int = 400_000, lim_denso_pares: int = 20_000_000,
) -> dict:
    p = np.asarray(tris, np.float64).reshape(-1, 3)
    A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax, tv, _ = visib_base._preparar_triangulos(p, np.arange(len(p), dtype=np.int64).reshape(-1, 3))
    assert len(A) == len(tris)
    a, b = np.asarray([e[0] for e in arestas], np.float64).reshape(-1, 3), np.asarray([e[1] for e in arestas], np.float64).reshape(-1, 3)
    nt, ne, sp = len(A), len(a), np.asarray(spans, np.int64).reshape(-1, 4)
    return dict(
        t_s=sp[:, 0].copy(), iy_s=sp[:, 1].copy(), ix0_s=sp[:, 2].copy(), ix1_s=sp[:, 3].copy(),
        ek_idx=np.arange(ne, dtype=np.int64) if ek_idx is None else np.asarray(ek_idx, np.int64),
        zf_flat=np.full(Wc * Hc, -np.inf) if zf_flat is None else np.asarray(zf_flat, np.float64),
        filtrar_zf=bool(filtrar_zf), mn_x=float(mn_x), mn_y=float(mn_y), cg=float(cg), Wc=int(Wc), Hc=int(Hc),
        a=a, b=b, d=b - a, ea=np.full(ne, -1, np.int64), eb=np.full(ne, -2, np.int64), tv=tv,
        A=A, gx=gx, gy=gy, nx_=nx_, ny_=ny_, cc_=cc_, tx0=tx0, tx1=tx1, ty0=ty0, ty1=ty1, tzmax=tzmax,
        ex0=np.minimum(a[:, 0], b[:, 0]), ex1=np.maximum(a[:, 0], b[:, 0]), ey0=np.minimum(a[:, 1], b[:, 1]),
        ey1=np.maximum(a[:, 1], b[:, 1]), ezmin=np.minimum(a[:, 2], b[:, 2]), nt_all=max(nt, 1), tol_z=float(tol_z),
        d_eps=float(d_eps), usar_subgrade=bool(usar_subgrade), lim_t_bloco=int(lim_t_bloco), lim_e_bloco=int(lim_e_bloco), lim_denso_pares=int(lim_denso_pares),
    )


def _chamar_nativo(mod, c: dict, *, com_lims: bool = True):
    """Helper unico da ponte `obimvisib.processar_celulas_e_recortar` (ordem exata da spec N3c)."""
    base = (c["t_s"], c["iy_s"], c["ix0_s"], c["ix1_s"], c["ek_idx"], c["zf_flat"], c["filtrar_zf"],
            c["mn_x"], c["mn_y"], c["cg"], c["Wc"], c["Hc"], *(c[k] for k in _MALHA), c["tol_z"], c["d_eps"], c["usar_subgrade"])
    return mod.processar_celulas_e_recortar(*base, *((c["lim_t_bloco"], c["lim_e_bloco"], c["lim_denso_pares"]) if com_lims else ()))


def _chamar_py(fn, c: dict, H_l: list) -> None:
    fn(c["t_s"], c["iy_s"], c["ix0_s"], c["ix1_s"], c["ek_idx"], c["zf_flat"], c["filtrar_zf"], c["mn_x"], c["mn_y"],
       c["cg"], c["Wc"], c["Hc"], *(c[k] for k in _MALHA), c["nt_all"], c["tol_z"], c["d_eps"], c["usar_subgrade"], H_l,
       lim_t_bloco=c["lim_t_bloco"], lim_e_bloco=c["lim_e_bloco"], lim_denso_pares=c["lim_denso_pares"])


def _comparar_sem_queda(mod, c: dict, *, com_lims: bool = True):
    H_ref: list = []
    _chamar_py(_ref_pares_celulas, c, H_ref)
    nat = _chamar_nativo(mod, c, com_lims=com_lims)
    assert isinstance(nat, tuple) and len(nat) == 5 and nat[3] == len(c["t_s"]) and nat[4] == len(c["t_s"])
    _igual_h(nat[:3], _compactar_py(H_ref))
    return nat


@pytest.fixture(scope="module")
def obimvisib_mod(tmp_path_factory):
    bash = shutil.which("bash")
    if os.environ.get("OBIM_VISIB_BUILD") != "1" or not os.environ.get("CONDA_PREFIX") or shutil.which("cmake") is None or bash is None:
        pytest.skip("requer OBIM_VISIB_BUILD=1, CONDA_PREFIX, cmake e bash no PATH")
    assert BUILD_SH.is_file(), f"ausente: {BUILD_SH}"
    out = tmp_path_factory.mktemp("obimvisib_n3c")
    res = subprocess.run([bash, str(BUILD_SH), str(out)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, f"build.sh falhou ({res.returncode}):\n{res.stdout}\n{res.stderr}"
    antes = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "obimvisib" or k.startswith("obimvisib.")}
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


def _tem_guarda(arq: Path, pat: re.Pattern[str], vistos: set[Path] | None = None) -> bool:
    vistos = set() if vistos is None else vistos
    if arq in vistos or not arq.is_file():
        return False
    vistos.add(arq)
    cod = _sem_com(arq.read_text(encoding="utf-8"))
    return bool(pat.search(cod)) or any(_tem_guarda((arq.parent / inc).resolve(), pat, vistos) for inc in re.findall(r'#\s*include\s*"([^"]+)"', cod))


def test_fontes_guardas_fp_contrato_e_contador():
    cpps = sorted(PASTA_NATIVO.glob("*.cpp"))
    assert cpps
    for cpp in cpps:
        assert _tem_guarda(cpp.resolve(), _GUARD_MSVC), f"falta guarda _M_FP_PRECISE em {cpp.name}"
        assert _tem_guarda(cpp.resolve(), _GUARD_FM), f"falta guarda __FAST_MATH__ em {cpp.name}"
    for arq in [*cpps, *sorted(PASTA_NATIVO.glob("*.h")), PASTA_NATIVO / "CMakeLists.txt"]:
        txt = arq.read_text(encoding="utf-8")
        cod = re.sub(r"#.*", "", txt) if arq.name == "CMakeLists.txt" else re.sub(r"^\s*#\s*error\b.*$", "", _sem_com(txt), flags=re.M)
        assert "-ffast-math" not in cod.lower() and "/fp:fast" not in cod.lower(), f"flag proibida em {arq.name}"
    for no in ast.walk(ast.parse(VISIB_PY.read_text(encoding="utf-8"))):
        nomes = [al.name for al in no.names] if isinstance(no, ast.Import) else ([no.module or "", *(al.name for al in no.names)] if isinstance(no, ast.ImportFrom) else [])
        assert all("visib_nativo" not in n and "obimvisib" not in n for n in nomes), f"import proibido: {nomes}"
    assert callable(getattr(visib_mapa, "_pares_celulas_e_recortar_nativo", None))
    assert "subgrade_celulas_densas" in visib_mapa._obter_chamadas_py()


def test_seletor_contador_import_error_e_int32(obimvisib_mod, monkeypatch):
    c = _cena([[(0, 0, 5), (2, 0, 5), (0, 2, 5)]], [[(0.1, 0.2, 0), (1.0, 0.2, 0)]], [(0, 0, 0, 1)])
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    H_py: list = []
    _chamar_py(visib_mapa._pares_celulas_e_recortar, c, H_py)
    assert visib_mapa._obter_chamadas_py()["pares_celulas"] == 1 and len(H_py) == 1
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    for fake in (None, SimpleNamespace(versao=lambda: visib_nativo.VERSAO_ESPERADA, flags_fp=lambda: "")):
        monkeypatch.setitem(sys.modules, "obimvisib", fake)
        visib_mapa._zerar_chamadas_py()
        with pytest.raises(ImportError, match=r".+"):
            _chamar_py(visib_mapa._pares_celulas_e_recortar, c, [])
        assert visib_mapa._obter_chamadas_py()["pares_celulas"] == 0
    monkeypatch.setitem(sys.modules, "obimvisib", obimvisib_mod)
    c32 = dict(c, **{k: c[k].astype(np.int32) for k in ("t_s", "iy_s", "ix0_s", "ix1_s", "ek_idx", "ea", "eb", "tv")})
    visib_mapa._zerar_chamadas_py()
    H_nat: list = []
    _chamar_py(visib_mapa._pares_celulas_e_recortar, c32, H_nat)
    assert visib_mapa._obter_chamadas_py()["pares_celulas"] == 0 and len(H_nat) == 1
    _igual_h(_compactar_py(H_nat), _compactar_py(H_py))


def test_bordas_zf_poda_m3_dedup_e_m4(obimvisib_mod, monkeypatch):
    # Bordas: tzmax == zf - 1e-9 vs nextafter; cell_tzmax > zmin_sub + tol_z (M3); dedup + finalizar_intervalos (M4).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    t0, a0 = [[(0, 0, 5), (2, 0, 5), (0, 2, 5)]], [[(0.1, 0.2, 0), (0.8, 0.2, 0)]]
    assert len(_comparar_sem_queda(obimvisib_mod, _cena(t0, a0, []), com_lims=False)[0]) == 0
    assert len(_comparar_sem_queda(obimvisib_mod, _cena(t0, a0, [(0, 0, 0, 0)], ek_idx=[]))[0]) == 0
    zf_v = 5.0
    lim_zf, ab_zf = zf_v - 1e-9, float(np.nextafter(zf_v - 1e-9, -np.inf))
    t_zf = [[(0, 0, lim_zf), (2, 0, lim_zf), (0, 2, lim_zf)], [(1, 0, ab_zf), (3, 0, ab_zf), (1, 2, ab_zf)]]
    a_zf, sp_zf = [[(0.1, 0.2, 0), (0.8, 0.2, 0)], [(1.1, 0.2, 0), (1.8, 0.2, 0)]], [(0, 0, 0, 0), (1, 0, 1, 1)]
    assert _comparar_sem_queda(obimvisib_mod, _cena(t_zf, a_zf, sp_zf, zf_flat=np.full(8, zf_v), filtrar_zf=True, tol_z=0.0))[0].tolist() == [0]
    assert _comparar_sem_queda(obimvisib_mod, _cena(t_zf, a_zf, sp_zf, zf_flat=np.zeros(0), filtrar_zf=False, tol_z=0.0))[0].tolist() == [0, 1]
    # M3: trocar > por >= em cell_tzmax > zmin_sub + tol_z deixa e=0 parear com t=0 e gerar [0.0, 0.5].
    lim_c, ac_c = 1.25, float(np.nextafter(1.25, 2.0))
    t_m3 = [[(0, 0, lim_c), (2.5, 0, lim_c), (0, 2.5, lim_c)], [(0, 1, ac_c), (2.5, 1, ac_c), (0, 3.5, ac_c)]]
    a_m3 = [[(0.0, 0.2, 0.0), (1.8, 0.2, 2.0)], [(0.0, 1.2, 0.0), (1.8, 1.2, 2.0)]]
    assert _comparar_sem_queda(obimvisib_mod, _cena(t_m3, a_m3, [(0, 0, 1, 1), (1, 1, 1, 1)], tol_z=0.25))[0].tolist() == [1]
    # Dedup de triangulo cobrindo 3 celulas + M4 (esquecer finalizar_intervalos entre 3 blocos: [1, 1, 0] -> [0, 1]).
    t_m4 = [[(0, 0, 5), (4, 0, 5), (0, 4, 5)], [(0.5, 0, 6), (4.5, 0, 6), (0.5, 4, 6)], [(0, 1, 5), (4, 1, 5), (0, 5, 5)]]
    a_m4 = [[(0.1, 1.2, 0), (1.5, 1.2, 0)], [(0.1, 0.2, 0), (2.2, 0.2, 0)]]
    assert _comparar_sem_queda(obimvisib_mod, _cena(t_m4, a_m4, [(0, 0, 0, 2), (1, 0, 1, 2), (2, 1, 0, 1)], lim_t_bloco=3))[0].tolist() == [0, 1]


def _denso(cx: int, cy: int = 0, n: int = 128) -> list:
    return [[(cx + 0.02 + 0.002 * k, cy + 0.02, 5.0 + 0.005 * k), (cx + 0.98, cy + 0.02, 5.0 + 0.005 * k), (cx + 0.02 + 0.002 * k, cy + 0.98, 5.0 + 0.005 * k)] for k in range(n)]


def test_ramo_denso_queda_hibrida_m1_m2_w0_e_sinal_zero(obimvisib_mod, monkeypatch):
    # 3 blocos: B0=[0,66) (cont=65 + w=0 na fronteira lim_t_bloco=130), B1=[66,196) (cont=130 denso), B2=[196,198).
    tris = [[(0, 0, 5), (2.5, 0, 5), (0, 2.5, 5)], [(0.4, 0, 6), (2.5, 0, 6), (0.4, 2.5, 6)]]
    tris.extend(_denso(4, 0, 130))
    tris.extend([[(7, 0, 5), (8.5, 0, 5), (7, 1.5, 5)], [(7.2, 0, 6), (8.6, 0, 6), (7.2, 1.5, 6)]])
    ars = [[(0.1, 0.2, 0), (1.8, 0.2, 0)], [(4.05, 0.15, 0), (4.9, 0.15, 0)], [(4.05, 0.35, 0), (4.9, 0.35, 0)], [(7.1, 0.2, 0), (7.9, 0.2, 0)]]
    spans = [(k % 2, 0, 0, 1) for k in range(65)] + [(0, 0, 1, 0)] + [(2 + k, 0, 4, 4) for k in range(130)] + [(132, 0, 7, 7), (133, 0, 7, 7)]
    c = _cena(tris, ars, spans, Wc=10, Hc=2, lim_t_bloco=130, lim_e_bloco=400_000, lim_denso_pares=200)
    # Direta C++: cai em B1=[66, 196) e He contem so B0=[0] (mata M1 rollback, bug w==0 e t_fim_py errado).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    H_b0: list = []
    _chamar_py(_ref_pares_celulas, dict(c, **{k: c[k][:66] for k in ("t_s", "iy_s", "ix0_s", "ix1_s")}), H_b0)
    he_q, lo_q, hi_q, ti, tf = _chamar_nativo(obimvisib_mod, c)
    assert (ti, tf) == (66, 196) and he_q.tolist() == [0]
    _igual_h((he_q, lo_q, hi_q), _compactar_py(H_b0))
    # Queda hibrida via glue: B0 C++, B1 subgrade Python (contador==1), B2 retoma C++; bit a bit == Python e ref.
    H_ref, H_py, H_nat = [], [], []
    _chamar_py(_ref_pares_celulas, c, H_ref)
    visib_mapa._zerar_chamadas_py()
    _chamar_py(visib_mapa._pares_celulas_e_recortar, c, H_py)
    assert visib_mapa._obter_chamadas_py()["pares_celulas"] == 1 and visib_mapa._obter_chamadas_py()["subgrade_celulas_densas"] == 1
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    _chamar_py(visib_mapa._pares_celulas_e_recortar, c, H_nat)
    cnt = visib_mapa._obter_chamadas_py()
    assert cnt["subgrade_celulas_densas"] == 1 and all(cnt[k] == 0 for k in _NATIVOS)
    res_nat = _compactar_py(H_nat)
    assert res_nat[0].tolist() == [0, 1, 2, 3]
    _igual_h(res_nat, _compactar_py(H_py))
    _igual_h(res_nat, _compactar_py(H_ref))
    # cont == 130 mas dense_pair_sum < 200 (mata M2), usar_subgrade=False e lim_e_bloco=1: 100% C++ (subgrade==0).
    for c_sem in (dict(c, ek_idx=_i64(0, 1, 3)), dict(c, usar_subgrade=False), dict(c, lim_e_bloco=1)):
        monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
        _comparar_sem_queda(obimvisib_mod, c_sem)
        monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
        visib_mapa._zerar_chamadas_py()
        _chamar_py(visib_mapa._pares_celulas_e_recortar, c_sem, [])
        assert visib_mapa._obter_chamadas_py()["subgrade_celulas_densas"] == 0 and visib_mapa._obter_chamadas_py()["pares_celulas"] == 0
    # Spec 3.8: celula densa (cont=130, t=0 com tx0=-0.0) + celula normal (t=130) abaixo do limiar preserva -0.0.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    t_s0 = [[(-1, -1, 5.0 + 0.001 * k), (3, -1, 5.0 + 0.001 * k), (-1, 3, 5.0 + 0.001 * k)] for k in range(131)]
    c_s0 = _cena(t_s0, [[(0.0, 0.2, 0.0), (1.5, 0.2, 0.0)]], [(k, 0, 0, 0) for k in range(130)] + [(130, 0, 1, 1)], Wc=3, Hc=1, lim_denso_pares=200)
    c_s0["tx0"] = np.zeros(131, dtype=np.float64)
    c_s0["tx0"][0] = -0.0
    assert int(_bits(_comparar_sem_queda(obimvisib_mod, c_s0)[1])[0]) == 0x8000000000000000


def test_quedas_fronteiras_m6_m7_m13_m15_e_duas_quedas_g3(obimvisib_mod, monkeypatch):
    # M15 (w=[lim,0,1] na fronteira lim_t_bloco=128) + M13 (cont==128 exato) + M7 (dense_pair_sum==lim_denso_pares==256).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    t_b = [[(0, 0, 5), (2, 0, 5), (0, 2, 5)], *_denso(0, 1, 128)]
    a_b = [[(0.1, 0.2, 0), (0.8, 0.2, 0)], [(0.05, 1.15, 0), (0.9, 1.15, 0)], [(0.05, 1.35, 0), (0.9, 1.35, 0)]]
    sp_b = [(0, 0, 0, 127), (0, 0, 1, 0)] + [(1 + k, 1, 0, 0) for k in range(128)]
    c_b = _cena(t_b, a_b, sp_b, Wc=130, Hc=2, lim_t_bloco=128, lim_denso_pares=256)
    he_b, lo_b, hi_b, ti_b, tf_b = _chamar_nativo(obimvisib_mod, c_b)
    assert (ti_b, tf_b) == (2, 130) and he_b.tolist() == [0]
    _comparar_sem_queda(obimvisib_mod, dict(c_b, lim_denso_pares=257))
    # M6: finalizar_intervalos no retorno da queda (B0 emite e1; B1 emite e0 e e1 sobreposto -> bruto [1,0,1], unido [0,1]).
    t_m6 = [[(0.0, 0.0, 5), (0.7, 0.0, 5), (0.0, 1.0, 5)], [(0.4, 0.0, 6), (1.2, 0.0, 6), (0.4, 1.0, 6)], [(2.0, 0.0, 5), (3.0, 0.0, 5), (2.0, 1.0, 5)], *_denso(0, 1, 128)]
    a_m6 = [[(2.1, 0.2, 0), (2.7, 0.2, 0)], [(0.1, 0.2, 0), (0.9, 0.2, 0)], [(0.05, 1.15, 0), (0.9, 1.15, 0)], [(0.05, 1.35, 0), (0.9, 1.35, 0)]]
    sp_m6 = [(0, 0, 0, 127), (1, 0, 0, 63), (2, 0, 2, 65)] + [(3 + k, 1, 0, 0) for k in range(128)]
    c_m6 = _cena(t_m6, a_m6, sp_m6, Wc=130, Hc=2, lim_t_bloco=128, lim_denso_pares=256)
    H_m6: list = []
    _chamar_py(_ref_pares_celulas, dict(c_m6, **{k: c_m6[k][:3] for k in ("t_s", "iy_s", "ix0_s", "ix1_s")}), H_m6)
    he_6, lo_6, hi_6, ti_6, tf_6 = _chamar_nativo(obimvisib_mod, c_m6)
    assert (ti_6, tf_6) == (3, 131) and he_6.tolist() == [0, 1]
    _igual_h((he_6, lo_6, hi_6), _compactar_py(H_m6))
    # G3: duas quedas no mesmo laco do cursor (B0 denso, B1 C++, B2 denso, B3 C++), bit a bit contra _ref_pares_celulas.
    t_g3 = [*_denso(0, 0, 128), [(2, 0, 5), (3.5, 0, 5), (2, 1.5, 5)], [(2.3, 0, 6), (3.8, 0, 6), (2.3, 1.5, 6)], *_denso(1, 1, 128), [(5, 1, 5), (6.5, 1, 5), (5, 2.5, 5)], [(5.3, 1, 6), (6.8, 1, 6), (5.3, 2.5, 6)]]
    a_g3 = [[(0.05, 0.15, 0), (0.9, 0.15, 0)], [(0.05, 0.35, 0), (0.9, 0.35, 0)], [(2.1, 0.2, 0), (2.9, 0.2, 0)], [(1.05, 1.15, 0), (1.9, 1.15, 0)], [(1.05, 1.35, 0), (1.9, 1.35, 0)], [(5.1, 1.2, 0), (5.9, 1.2, 0)]]
    sp_g3 = [(k, 0, 0, 0) for k in range(128)] + [(128, 0, 2, 65), (129, 0, 2, 65)] + [(130 + k, 1, 1, 1) for k in range(128)] + [(258, 1, 5, 5), (259, 1, 5, 5)]
    c_g3 = _cena(t_g3, a_g3, sp_g3, Wc=130, Hc=2, lim_t_bloco=128, lim_denso_pares=256)
    H_ref, H_nat = [], []
    _chamar_py(_ref_pares_celulas, c_g3, H_ref)
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    _chamar_py(visib_mapa._pares_celulas_e_recortar, c_g3, H_nat)
    cnt = visib_mapa._obter_chamadas_py()
    assert cnt["subgrade_celulas_densas"] == 2 and all(cnt[k] == 0 for k in _NATIVOS)
    res_g3 = _compactar_py(H_nat)
    assert res_g3[0].tolist() == [0, 1, 2, 3, 4, 5]
    _igual_h(res_g3, _compactar_py(H_ref))


def test_tzmax_nan_m17_e_kt1_inline_m18(obimvisib_mod, monkeypatch):
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    # M17: tzmax NaN propaga em cell_tzmax (max_f) quando filtrar_zf=False e e filtrado fora quando filtrar_zf=True.
    t_nan = [[(0, 0, 5), (2, 0, 5), (0, 2, 5)], [(0, 0, 4), (2, 0, 4), (0, 2, 4)]]
    c_nan = _cena(t_nan, [[(0.1, 0.2, 0), (0.8, 0.2, 0)]], [(0, 0, 0, 0), (1, 0, 0, 0)], zf_flat=np.zeros(8), filtrar_zf=False)
    c_nan["tzmax"][1] = np.nan
    assert _comparar_sem_queda(obimvisib_mod, c_nan)[0].tolist() == []
    assert _comparar_sem_queda(obimvisib_mod, dict(c_nan, filtrar_zf=True))[0].tolist() == [0]
    # M18: kt1=(k+1)/dn vs kt0+1/dn no laco inline (nsub=5, k=2: 3/5 < 2/5+1/5 por 1 ULP; em nsub=3 sao iguais em float64).
    dy = float(np.nextafter(5.0 / 3.0, -np.inf))
    c_m18 = _cena([[(0, 0, 5), (5, 0, 5), (0, 5, 5)]], [[(0.0, 0.0, 0.0), (4.5, dy, 0.0)]], [(0, 1, 1, 1)], Wc=6, Hc=3)
    assert _comparar_sem_queda(obimvisib_mod, c_m18)[0].tolist() == []


def test_validacoes_erros_e_limites_secao4(obimvisib_mod, monkeypatch):
    c = _cena([[(0, 0, 5), (2, 0, 5), (0, 2, 5)]], [[(0.1, 0.2, 0), (1.0, 0.2, 0)]], [(0, 0, 0, 1)], Wc=4, Hc=2)
    for ov in [
        dict(iy_s=np.zeros(2, np.int64)), dict(ix0_s=np.zeros(0, np.int64)), dict(Wc=0), dict(Hc=0), dict(Wc=1 << 32, Hc=1 << 32),
        *(dict(cg=v) for v in (0.0, -1.0, np.nan, np.inf, float(np.nextafter(0.0, 1.0)))),
        dict(mn_x=np.nan), dict(mn_y=np.inf), dict(lim_t_bloco=0), dict(lim_e_bloco=0),
        dict(ix0_s=_i64(2), ix1_s=_i64(0)), dict(a=np.zeros((1, 2))), dict(b=np.zeros((2, 3))),
        dict(tzmax=np.zeros(2)), dict(tv=np.zeros((1, 2), np.int64)),
        dict(d=np.array([[np.inf, 0.0, 0.0]])), dict(d=np.array([[2e8, 0.0, 0.0]])),
        dict(Wc=10_000, Hc=10_000, zf_flat=np.zeros(0), t_s=_i64(0, 0), iy_s=_i64(0, 9_999), ix0_s=_i64(0, 9_999), ix1_s=_i64(0, 9_999)),
    ]:
        with pytest.raises((ValueError, OverflowError)):
            _chamar_nativo(obimvisib_mod, dict(c, **ov))
    for ov in (dict(filtrar_zf=True, zf_flat=np.zeros(7)), dict(ix0_s=_i64(-(1 << 63)), ix1_s=_i64(-(1 << 63))), dict(ix0_s=_i64(0), ix1_s=_i64(-(1 << 63)))):
        with pytest.raises((ValueError, IndexError, OverflowError)):
            _chamar_nativo(obimvisib_mod, dict(c, **ov))
    for ov in [
        dict(ek_idx=_i64(-1)), dict(ek_idx=_i64(1)), dict(t_s=_i64(-1)), dict(t_s=_i64(1)),
        dict(iy_s=_i64(-1)), dict(iy_s=_i64(2)), dict(ix0_s=_i64(-1), ix1_s=_i64(0)), dict(ix0_s=_i64(0), ix1_s=_i64(4)),
    ]:
        with pytest.raises(IndexError):
            _chamar_nativo(obimvisib_mod, dict(c, **ov))
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    _comparar_sem_queda(obimvisib_mod, dict(c, lim_t_bloco=(1 << 63) - 1, lim_e_bloco=(1 << 63) - 1))


def test_nao_contiguos_somente_leitura_e_threads(obimvisib_mod, monkeypatch):
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    rng = np.random.default_rng(20260420)
    nt, ne, Wc, Hc = 24, 30, 8, 8
    bt = rng.uniform(0.2, 5.0, (nt, 3))
    tris = np.stack([bt, bt + rng.uniform([0.4, -0.2, -0.2], [1.6, 0.4, 0.2], (nt, 3)), bt + rng.uniform([-0.2, 0.4, -0.2], [0.4, 1.6, 0.2], (nt, 3))], axis=1)
    ars = np.stack([rng.uniform(0.0, 7.5, (ne, 3)), rng.uniform(0.0, 7.5, (ne, 3))], axis=1)
    spans = [(t, iy, max(0, int(tris[t, :, 0].min())), min(Wc - 1, int(tris[t, :, 0].max()))) for t in range(nt) for iy in range(max(0, int(tris[t, :, 1].min())), min(Hc, int(tris[t, :, 1].max()) + 1))]
    c = _cena(tris, ars, spans, Wc=Wc, Hc=Hc, zf_flat=rng.uniform(-2.0, 3.0, Wc * Hc), filtrar_zf=True, lim_t_bloco=25)
    esp = _comparar_sem_queda(obimvisib_mod, c)[:3]

    def _nc(x, inv: bool):
        if not isinstance(x, np.ndarray):
            return x
        arr = np.asfortranarray((x[::-1, ::-1] if inv else x).repeat(2, 0).repeat(2, 1)) if x.ndim == 2 else np.repeat(x[::-1] if inv else x, 2)
        arr = (arr[::-2, ::-2] if inv else arr[::2, ::2]) if x.ndim == 2 else (arr[::-2] if inv else arr[::2])
        arr.setflags(write=False)
        return arr

    c_nc = {k: _nc(v, k in ("t_s", "iy_s", "ix0_s", "ix1_s", "ek_idx", "a", "A")) for k, v in c.items()}
    nat_nc = _chamar_nativo(obimvisib_mod, c_nc)
    assert nat_nc[3] == len(c["t_s"]) and nat_nc[4] == len(c["t_s"])
    _igual_h(nat_nc[:3], esp)
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs_c = [ex.submit(_chamar_nativo, obimvisib_mod, c_nc) for _ in range(8)]
        futs_g = [ex.submit(lambda: (h := [], _chamar_py(visib_mapa._pares_celulas_e_recortar, c, h), h)[2]) for _ in range(8)]
        for f in futs_c:
            r = f.result()
            assert r[3] == len(c["t_s"]) and r[4] == len(c["t_s"])
            _igual_h(r[:3], esp)
        for f in futs_g:
            _igual_h(_compactar_py(f.result()), esp)


def test_pipeline_d1_equivalencia_e_contadores(obimvisib_mod, monkeypatch):
    pecas = todas()["d1"]()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    res_py = visibilidade.linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["pares_celulas"] > 0
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    res_nat = visibilidade.linhas_visiveis_multi(pecas, trabalhadores=1)
    cnt = visib_mapa._obter_chamadas_py()
    assert all(cnt[k] == 0 for k in _NATIVOS), f"contadores esperados zerados: {cnt}"
    _igual_visib(res_nat, res_py)
