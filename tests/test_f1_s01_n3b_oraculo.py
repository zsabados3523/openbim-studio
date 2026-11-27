# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-N3b: `obimvisib.filtrar_arestas_mapa_z` e extracao do laco de celulas em `visib_mapa`."""
from __future__ import annotations

import ast, importlib, os, re, shutil, subprocess, sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from obim_geometria import visib_base, visib_mapa, visib_nativo, visibilidade
from test_s06_t22a_visibilidade_equivalencia_oraculo import todas

RAIZ = Path(__file__).resolve().parent.parent
PASTA_NATIVO = RAIZ / "native" / "obim_visib"
BUILD_SH, VISIB_PY = PASTA_NATIVO / "build.sh", RAIZ / "geometria" / "obim_geometria" / "visibilidade.py"
_POS_NAN = np.uint64(0x7FF8000000000000).view(np.float64)
_NEG_NAN = np.uint64(0xFFF8000000000000).view(np.float64)
_GUARD_MSVC = re.compile(r"#\s*(?:if\b[^\n]*_M_FP_PRECISE|ifndef\s+_M_FP_PRECISE\b)(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b")
_GUARD_FM = re.compile(r"#\s*(?:ifdef\s+__FAST_MATH__\b|if\s+defined(?:\s*\(\s*__FAST_MATH__\s*\)|\s+__FAST_MATH__\b))(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b")


def _bits(a: np.ndarray) -> np.ndarray:
    assert a.dtype == np.float64
    return np.ascontiguousarray(a).view(np.uint64)


def _juntar_hl(H_l: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not H_l:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)
    return H_l[0] if len(H_l) == 1 else tuple(np.concatenate(x) for x in zip(*H_l))


def _igual_4(obt, esp) -> None:
    ek_o, he_o, lo_o, hi_o = obt
    ek_e, he_e, lo_e, hi_e = esp
    assert ek_o.dtype == np.int64 and he_o.dtype == np.int64 and lo_o.dtype == np.float64 and hi_o.dtype == np.float64
    assert np.array_equal(ek_o, ek_e) and np.array_equal(he_o, he_e)
    assert np.array_equal(_bits(lo_o), _bits(lo_e)) and np.array_equal(_bits(hi_o), _bits(hi_e))


def _igual_visib(obt, esp) -> None:
    assert len(obt) == len(esp)
    for po, pe in zip(obt, esp):
        assert len(po) == len(pe)
        for so, se in zip(po, pe):
            assert so.shape == se.shape and np.array_equal(_bits(so), _bits(se))


def _comparar(mod, a, d, z_full, mn_x: float, mn_y: float, g: float, tol_z: float):
    H_py: list = []
    ek_py = visib_mapa._filtrar_arestas_mapa_z_py(a, d, z_full, mn_x, mn_y, g, tol_z, H_py)
    nat = mod.filtrar_arestas_mapa_z(a, d, z_full, mn_x, mn_y, g, tol_z)
    assert isinstance(nat, tuple) and len(nat) == 4
    _igual_4(nat, (ek_py, *_juntar_hl(H_py)))
    return nat, H_py


def _ref_pares_celulas(
    t_s, iy_s, ix0_s, ix1_s, ek_idx, zf_flat, filtrar_zf, mn_x, mn_y, cg, Wc, Hc,
    a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_, tx0, tx1, ty0, ty1, tzmax,
    ex0, ex1, ey0, ey1, ezmin, nt_all, tol_z, d_eps, usar_subgrade, H_l,
    *, lim_t_bloco: int = 2_000_000, lim_e_bloco: int = 400_000, lim_denso_pares: int = 20_000_000,
) -> None:
    """Referencia fiel do laco de celulas de `visibilidade.py:229-315` antes da N3b."""
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


@pytest.fixture(scope="module")
def obimvisib_mod(tmp_path_factory):
    bash = shutil.which("bash")
    if os.environ.get("OBIM_VISIB_BUILD") != "1" or not os.environ.get("CONDA_PREFIX") or shutil.which("cmake") is None or bash is None:
        pytest.skip("requer OBIM_VISIB_BUILD=1, CONDA_PREFIX, cmake e bash no PATH")
    assert BUILD_SH.is_file(), f"ausente: {BUILD_SH}"
    out = tmp_path_factory.mktemp("obimvisib_n3b")
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


def _tem_guarda(arq: Path, pat: re.Pattern[str], vistos: set[Path] | None = None) -> bool:
    vistos = set() if vistos is None else vistos
    if arq in vistos or not arq.is_file():
        return False
    vistos.add(arq)
    cod = _sem_com(arq.read_text(encoding="utf-8"))
    return bool(pat.search(cod)) or any(_tem_guarda((arq.parent / inc).resolve(), pat, vistos) for inc in re.findall(r'#\s*include\s*"([^"]+)"', cod))


def test_fontes_guardas_fp_e_contrato_imports():
    cpps = sorted(PASTA_NATIVO.glob("*.cpp"))
    assert cpps
    for cpp in cpps:
        assert _tem_guarda(cpp.resolve(), _GUARD_MSVC), f"falta guarda _M_FP_PRECISE em {cpp.name}"
        assert _tem_guarda(cpp.resolve(), _GUARD_FM), f"falta guarda __FAST_MATH__ em {cpp.name}"
    for arq in [*cpps, *sorted(PASTA_NATIVO.glob("*.h")), PASTA_NATIVO / "CMakeLists.txt"]:
        txt = arq.read_text(encoding="utf-8")
        cod = re.sub(r"#.*", "", txt) if arq.name == "CMakeLists.txt" else re.sub(r"^\s*#\s*error\b.*$", "", _sem_com(txt), flags=re.M)
        assert "-ffast-math" not in cod.lower() and "/fp:fast" not in cod.lower(), f"flag proibida em {arq.name}"
    arv, imp_mapa = ast.parse(VISIB_PY.read_text(encoding="utf-8")), set()
    for no in ast.walk(arv):
        if isinstance(no, ast.Import):
            nomes = [al.name for al in no.names]
        elif isinstance(no, ast.ImportFrom):
            mod = no.module or ""
            nomes = [mod, *(al.name for al in no.names)]
            if "visib_mapa" in mod:
                imp_mapa.update(al.name for al in no.names)
        else:
            continue
        for nome in nomes:
            assert "visib_nativo" not in nome and "obimvisib" not in nome, f"import proibido: {nome}"
    assert {"_filtrar_arestas_mapa_z", "_pares_celulas_e_recortar"} <= imp_mapa
    for nome in ("_filtrar_arestas_mapa_z_py", "_filtrar_arestas_mapa_z", "_pares_celulas_bloco_py", "_pares_celulas_e_recortar_py", "_pares_celulas_e_recortar"):
        assert callable(getattr(visib_mapa, nome, None)), f"ausente em visib_mapa: {nome}"


def test_seletor_contador_e_import_error(monkeypatch):
    a, d, z_hi, z_lo = np.array([[0.2, 0.2, 1.0]]), np.array([[0.5, 0.0, 0.0]]), np.full((2, 2), 5.0), np.full((2, 2), -5.0)
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    cont = visib_mapa._obter_chamadas_py()
    assert cont["filtrar_arestas_mapa_z"] == 0 and cont["pares_celulas"] == 0
    H_l, H_vis = [], []
    ek = visib_mapa._filtrar_arestas_mapa_z(a, d, z_hi, 0.0, 0.0, 1.0, 0.1, H_l)
    assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] == 1 and len(ek) == 0 and len(H_l) == 1
    ek_v = visib_mapa._filtrar_arestas_mapa_z(a, d, z_lo, 0.0, 0.0, 1.0, 0.1, H_vis)
    assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] == 2 and ek_v.tolist() == [0] and len(H_vis) == 0
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    for mod_fake in (None, SimpleNamespace(versao=lambda: visib_nativo.VERSAO_ESPERADA, flags_fp=lambda: "")):
        monkeypatch.setitem(sys.modules, "obimvisib", mod_fake)
        visib_mapa._zerar_chamadas_py()
        with pytest.raises(ImportError, match=r".+"):
            visib_mapa._filtrar_arestas_mapa_z(a, d, z_hi, 0.0, 0.0, 1.0, 0.1, [])
        assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] == 0


def test_seletor_ligado_hl_e_int32_wrapper(obimvisib_mod, monkeypatch):
    a_i, d_i = np.array([[0, 0, 1], [0, 0, 10]], dtype=np.int32), np.array([[2, 0, 0], [2, 0, 0]], dtype=np.int32)
    z_i = np.array([[5, 5, 0, 0], [5, 5, 0, 0]], dtype=np.int32)
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    H_py, H_nat, H_vazio = [], [], []
    ek_py = visib_mapa._filtrar_arestas_mapa_z_py(a_i, d_i, z_i, 0.0, 0.0, 1.0, 0.0, H_py)
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    ek_nat = visib_mapa._filtrar_arestas_mapa_z(a_i, d_i, z_i, 0.0, 0.0, 1.0, 0.0, H_nat)
    assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] == 0 and len(H_nat) == 1
    _igual_4((ek_nat, *H_nat[0]), (ek_py, *_juntar_hl(H_py)))
    ek_v = visib_mapa._filtrar_arestas_mapa_z(a_i[1:], d_i[1:], z_i, 0.0, 0.0, 1.0, 0.0, H_vazio)
    assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] == 0 and ek_v.tolist() == [0] and len(H_vazio) == 0


def test_vazio_visivel_escondida_alternados_e_m2(obimvisib_mod, monkeypatch):
    # Mutante M2: esquecer de fechar `in_hid` no fim da aresta (1.0).
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    nat_v, _ = _comparar(obimvisib_mod, np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((2, 4)), 0.0, 0.0, 1.0, 0.0)
    assert all(len(x) == 0 for x in nat_v)
    # 0: trechos alternados [0, 1/4] e [2/4, 3/4]; 1: toda visivel; 2: toda escondida [0, 1]; 3: [1/4, 1].
    z = np.array([[7.0, 4.5, 4.5, 1.0], [10.0, 10.0, 10.0, 10.0], [0.0, 10.0, 10.0, 10.0]])
    a = np.array([[0.0, 0.5, 6.0], [0.0, 1.5, 12.0], [0.0, 1.5, 1.0], [0.2, 2.5, 5.0]])
    d = np.array([[3.2, 0.0, -4.0], [3.2, 0.0, 0.0], [3.2, 0.0, 0.0], [3.2, 0.0, 0.0]])
    (ek, he, hlo, hhi), _ = _comparar(obimvisib_mod, a, d, z, 0.0, 0.0, 1.0, 0.0)
    assert ek.tolist() == [0, 1, 3] and he.tolist() == [0, 0, 2, 3]
    assert np.array_equal(hlo, [0.0, 0.5, 0.0, 0.25]) and np.array_equal(hhi, [0.25, 0.75, 1.0, 1.0])


def test_mutantes_m1_m3_m4_e_z_especial(obimvisib_mod, monkeypatch):
    # M1: >= vs > em max(sa2, sb2) >= z_min_4 - tol_z; M3: std::min engolindo NaN nos 4 cantos; M4: 0.999*g vs g.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    z1, lim, ab = np.full((2, 2), 5.0), 4.75, float(np.nextafter(4.75, 0.0))
    a1 = np.array([[0.2, 0.2, lim], [0.2, 0.2, ab], [0.2, 0.2, 0.0], [0.2, 0.2, lim]])
    d1 = np.array([[0.5, 0.0, 0.0], [0.5, 0.0, 0.0], [0.5, 0.0, lim], [0.5, 0.0, -lim]])
    (ek1, he1, _, _), _ = _comparar(obimvisib_mod, a1, d1, z1, 0.0, 0.0, 1.0, 0.25)
    assert ek1.tolist() == [0, 2, 3] and he1.tolist() == [1]
    for tz in (0.0, -0.25):
        _comparar(obimvisib_mod, a1, d1, z1, 0.0, 0.0, 1.0, tz)
    z4 = np.array([[10.0, -np.inf], [-np.inf, -np.inf]])
    a4, d4 = np.array([[0.2, 0.2, 0.0], [0.2, 0.2, 0.0]]), np.array([[0.9995, 0.0, 0.0], [0.0, 0.9995, 0.0]])
    (ek4, he4, lo4, hi4), _ = _comparar(obimvisib_mod, a4, d4, z4, 0.0, 0.0, 1.0, 0.0)
    assert ek4.tolist() == [0, 1] and he4.tolist() == [0, 1] and np.array_equal(lo4, [0.0, 0.0]) and np.array_equal(hi4, [0.5, 0.5])
    z3 = np.full((2, 12), 10.0)
    for r, c, v in ((0, 0, _POS_NAN), (0, 3, _NEG_NAN), (1, 4, _POS_NAN), (1, 7, _NEG_NAN), (1, 9, -np.inf)):
        z3[r, c] = v
    z3[:, 10:12] = np.inf
    a3 = np.array([[2 * k + 0.4, 0.4, -100.0 if k == 4 else 20.0] for k in range(6)])
    (ek3, he3, _, _), _ = _comparar(obimvisib_mod, a3, np.tile([0.8, 0.8, 0.0], (6, 1)), z3, 0.0, 0.0, 1.0, 0.0)
    assert ek3.tolist() == [4] and he3.tolist() == [0, 1, 2, 3, 5]


def test_mutantes_m6_t1_e_m10_fma(obimvisib_mod, monkeypatch):
    # M6: t1 = t0 + 1/dn vs (k+1)/dn (em binary64 nsub=3 coincide bit a bit; nsub=5 k=2 e nsub=6 k=4 divergem em 1 ulp).
    # M10: std::fma(t1, dz, az) vs az + t1*dz em sb2 (e sa2) exatamente na fronteira z_min_4 - tol_z.
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    z0, z1 = (2.0 / 5.0) + (1.0 / 5.0), 5.0 / 6.0
    z3 = float(np.nextafter(0.5 + (1.0 / 5.0) * 1.1, 1.0))
    z4 = float(np.ldexp(1.0, -53))
    assert z0 > 3.0 / 5.0 and (4.0 / 6.0) + (1.0 / 6.0) < z1
    z = np.array([[z0] * 7, [z1] * 7, [0.0] * 7, [z3] * 7, [z4] * 7], dtype=np.float64)
    a = np.array(
        [[0.0, 0.5, 0.0], [0.0, 1.5, 0.0], [0.0, 2.5, -1.0], [0.0, 3.5, 0.5], [0.0, 4.5, 2.0]],
        dtype=np.float64,
    )
    d = np.array(
        [[4.5, 0.0, 1.0], [5.5, 0.0, 1.0], [2.5, 0.0, 3.0], [4.5, 0.0, 1.1], [2.5, 0.0, -3.0]],
        dtype=np.float64,
    )
    (ek, he, hlo, hhi), _ = _comparar(obimvisib_mod, a, d, z, 0.0, 0.0, 1.0, 0.0)
    assert ek.tolist() == [0, 1, 2, 3, 4] and he.tolist() == [0, 1, 3, 4]
    assert np.array_equal(hlo, [0.0, 0.0, 0.0, 2.0 / 3.0]) and np.array_equal(hhi, [3.0 / 5.0, 4.0 / 6.0, 1.0 / 5.0, 1.0])


def test_fatia_500k_nao_contiguos_e_somente_leitura(obimvisib_mod, monkeypatch):
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    a_big = np.array([[0.2, 0.2, 1.0 if i in (0, 5) else 20.0] for i in range(6)])
    z_big = np.array([[10.0, -np.inf, 10.0, 10.0], [10.0, 10.0, 10.0, 10.0]])
    nat_big, H_py = _comparar(obimvisib_mod, a_big, np.tile([99_900.0, 0.0, 0.0], (6, 1)), z_big, 0.0, 0.0, 1.0, 0.0)
    assert len(H_py) == 2 and len(nat_big[1]) > 0
    rng = np.random.default_rng(20260417)
    a, d, z = rng.uniform(-1.0, 6.0, (50, 3)), rng.uniform(-2.5, 2.5, (50, 3)), rng.uniform(-1.0, 6.0, (10, 12))
    z[rng.random(z.shape) < 0.2] = -np.inf
    esp, _ = _comparar(obimvisib_mod, a, d, z, -0.5, -0.5, 0.75, 1e-3)

    def _nc(x: np.ndarray, inv: bool) -> np.ndarray:
        arr = np.asfortranarray((x[::-1, ::-1] if inv else x).repeat(2, axis=0).repeat(2, axis=1))
        arr = arr[::-2, ::-2] if inv else arr[::2, ::2]
        arr.setflags(write=False)
        return arr

    _igual_4(obimvisib_mod.filtrar_arestas_mapa_z(_nc(a, True), _nc(d, False), _nc(z, True), -0.5, -0.5, 0.75, 1e-3), esp)


def test_validacoes_erros_e_limites_fp(obimvisib_mod, monkeypatch):
    a, d, z = np.array([[0.5, 0.5, 1.0]]), np.array([[0.1, 0.1, 0.0]]), np.array([[0.0, 0.0], [0.0, 10.0]])
    for args in [
        (np.zeros((2, 3)), d, z, 0.0, 0.0, 1.0, 0.0), (np.zeros((0, 4)), np.zeros((0, 4)), z, 0.0, 0.0, 1.0, 0.0),
        (np.zeros((1, 2)), np.zeros((1, 2)), z, 0.0, 0.0, 1.0, 0.0), (np.zeros((1, 4)), np.zeros((1, 3)), z, 0.0, 0.0, 1.0, 0.0),
        (a, d, np.zeros((0, 2)), 0.0, 0.0, 1.0, 0.0), (a, d, np.zeros((2, 0)), 0.0, 0.0, 1.0, 0.0),
        *((a, d, z, 0.0, 0.0, g_b, 0.0) for g_b in (0.0, -1.0, np.nan, np.inf, -np.inf)),
        *((a, d, z, mx, 0.0, 1.0, 0.0) for mx in (np.nan, np.inf, -np.inf)),
        *((a, d, z, 0.0, my, 1.0, 0.0) for my in (np.nan, np.inf, -np.inf)),
    ]:
        with pytest.raises(ValueError):
            obimvisib_mod.filtrar_arestas_mapa_z(*args)
    for d_b, g_v in ((np.array([[1.0, 0.0, 0.0]]), float(np.nextafter(0.0, 1.0))), (np.array([[np.inf, 0.0, 0.0]]), 1.0),
                     (np.array([[-np.inf, 0.0, 0.0]]), 1.0), (np.array([[2e8, 0.0, 0.0]]), 1.0)):
        with pytest.raises((ValueError, OverflowError)):
            obimvisib_mod.filtrar_arestas_mapa_z(a, d_b, z, 0.0, 0.0, g_v, 0.0)
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    _comparar(obimvisib_mod, a, np.zeros((1, 3)), z, 0.0, 0.0, 1.0, 0.0)
    # Spec 3.5: d com NaN -> nsub=1, cel_clamp(NaN)=0 sem UB; Spec 3.2 (divergencia documentada do Python): +inf/1e300 -> dim-1.
    ek_n, he_n, _, _ = obimvisib_mod.filtrar_arestas_mapa_z(a, np.array([[np.nan, 0.0, 0.0]]), z, 0.0, 0.0, 1.0, 0.0)
    assert ek_n.tolist() == [0] and len(he_n) == 0
    a_ext = np.array([[np.inf, np.inf, 1.0], [1e300, 1e300, 1.0], [-np.inf, -np.inf, 1.0], [np.nan, np.nan, 1.0]])
    ek_e, he_e, lo_e, hi_e = obimvisib_mod.filtrar_arestas_mapa_z(a_ext, np.zeros((4, 3)), z, 0.0, 0.0, 1.0, 0.0)
    assert ek_e.tolist() == [2, 3] and he_e.tolist() == [0, 1] and np.array_equal(lo_e, [0.0, 0.0]) and np.array_equal(hi_e, [1.0, 1.0])


def test_extracao_pares_celulas_d1_referencia(monkeypatch):
    pecas = todas()["d1"]()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    res_py = visibilidade.linhas_visiveis_multi(pecas, trabalhadores=1)
    cont = visib_mapa._obter_chamadas_py()
    assert cont["filtrar_arestas_mapa_z"] > 0 and cont["pares_celulas"] > 0
    assert len(res_py) == len(pecas) and sum(len(p) for p in res_py) > 0
    for pls in res_py:
        for seg in pls:
            assert seg.shape == (2, 2) and seg.dtype == np.float64 and np.isfinite(seg).all() and float(np.hypot(*(seg[1] - seg[0]))) > 1e-4
    monkeypatch.setattr(visib_mapa, "_pares_celulas_e_recortar", _ref_pares_celulas)
    if hasattr(visibilidade, "_pares_celulas_e_recortar"):
        monkeypatch.setattr(visibilidade, "_pares_celulas_e_recortar", _ref_pares_celulas)
    _igual_visib(res_py, visibilidade.linhas_visiveis_multi(pecas, trabalhadores=1))


def test_pipeline_d1_equivalencia_bit_a_bit(obimvisib_mod, monkeypatch):
    pecas = todas()["d1"]()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    visib_mapa._zerar_chamadas_py()
    res_py = visibilidade.linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] > 0
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    visib_mapa._zerar_chamadas_py()
    res_nat = visibilidade.linhas_visiveis_multi(pecas, trabalhadores=1)
    assert visib_mapa._obter_chamadas_py()["filtrar_arestas_mapa_z"] == 0
    _igual_visib(res_nat, res_py)
