# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F1-S01-N1: esqueleto do motor nativo de linhas visiveis (`obimvisib`)."""
from __future__ import annotations

import ast, importlib, os, re, shlex, shutil, subprocess, sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PASTA_NATIVO = RAIZ / "native" / "obim_visib"
CMAKE, BUILD_SH, PONTE_CPP = PASTA_NATIVO / "CMakeLists.txt", PASTA_NATIVO / "build.sh", PASTA_NATIVO / "ponte_visib.cpp"
VISIB_PY = RAIZ / "geometria" / "obim_geometria" / "visibilidade.py"
FLAGS_EXIGIDAS = ("-O2", "-ffp-contract=off", "/O2", "/fp:precise")
FLAGS_PROIBIDAS = (
    "-ffast-math",
    "-Ofast",
    "-march=native",
    "-funsafe-math-optimizations",
    "/fp:fast",
    "/fp:contract",
    "-ffp-contract=fast",
    "-ffp-contract=on",
)
RPATH_ESPERADO = "$ORIGIN/../../env/lib"


def _visib_nativo():
    return importlib.import_module("obim_geometria.visib_nativo")


def _sem_comentarios_cmake(texto: str) -> str:
    return re.sub(r"#.*", "", texto)


def _sem_comentarios_sh(texto: str) -> str:
    return "\n".join(ln for ln in texto.splitlines() if not ln.lstrip().startswith("#"))


def _sem_comentarios_cpp(texto: str) -> str:
    return re.sub(r"//.*", "", re.sub(r"/\*.*?\*/", "", texto, flags=re.S))


def _tem_token_flag(cod: str, flag: str, *, ignorar_caixa: bool = False) -> bool:
    pat = rf'(^|[\s"\'(;]){re.escape(flag)}($|[\s"\');])'
    return re.search(pat, cod, re.I if ignorar_caixa else 0) is not None


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, False), ("0", False), ("1", True), ("", False), ("true", False), (" 1", False)],
)
def test_seletor_ambiente(monkeypatch, valor, esperado):
    mod = _visib_nativo()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False) if valor is None else monkeypatch.setenv("OBIM_VISIB_NATIVO", valor)
    assert mod.visib_nativo_ligado() is esperado


def test_seletor_le_ambiente_a_cada_chamada(monkeypatch):
    mod = _visib_nativo()
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    assert mod.visib_nativo_ligado() is False
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    assert mod.visib_nativo_ligado() is True
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "0")
    assert mod.visib_nativo_ligado() is False


def test_carregar_indisponivel_retorna_none(monkeypatch):
    mod = _visib_nativo()
    monkeypatch.setitem(sys.modules, "obimvisib", None)
    assert mod.carregar() is None


def test_info_coerente_quando_indisponivel(monkeypatch):
    mod = _visib_nativo()
    monkeypatch.setitem(sys.modules, "obimvisib", None)
    monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
    assert mod.info() == {"ligado": False, "disponivel": False, "versao": None, "flags_fp": None}
    monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
    assert mod.info() == {"ligado": True, "disponivel": False, "versao": None, "flags_fp": None}


def test_cmake_flags_e_alvo():
    # Mutante: trocar -ffp-contract=off por -ffast-math (ou remover /fp:precise) deve reprovar.
    assert CMAKE.is_file() and PONTE_CPP.is_file(), f"ausente em {PASTA_NATIVO}"
    cod = _sem_comentarios_cmake(CMAKE.read_text(encoding="utf-8"))
    assert "nanobind_add_module" in cod and "_obimvisib" in cod
    for flag in FLAGS_EXIGIDAS:
        assert _tem_token_flag(cod, flag), f"flag exigida ausente: {flag}"
    for proibida in FLAGS_PROIBIDAS:
        assert not _tem_token_flag(cod, proibida, ignorar_caixa=True), f"flag proibida presente: {proibida}"


def test_ponte_cpp_guarda_fast_math():
    # Mutante: remover #ifdef __FAST_MATH__ / #error de ponte_visib.cpp deve reprovar.
    assert PONTE_CPP.is_file(), f"ausente: {PONTE_CPP}"
    cod = _sem_comentarios_cpp(PONTE_CPP.read_text(encoding="utf-8"))
    padrao = (
        r"#\s*(?:ifdef\s+__FAST_MATH__\b|if\s+defined(?:\s*\(\s*__FAST_MATH__\s*\)|\s+__FAST_MATH__\b))"
        r"(?:(?!#\s*(?:else|elif|endif)\b)[\s\S])*?#\s*error\b"
    )
    assert re.search(padrao, cod), "ponte_visib.cpp deve barrar __FAST_MATH__ com #error"


def test_cmake_sem_qt_nem_ifcopenshell():
    # Mutante: incluir find_package(Qt6 ...) ou IfcOpenShell no CMakeLists.txt deve reprovar.
    assert CMAKE.is_file(), f"ausente: {CMAKE}"
    cod = _sem_comentarios_cmake(CMAKE.read_text(encoding="utf-8"))
    assert not re.search(r"\bqt[56]?\b", cod, re.I), "CMakeLists.txt nao pode depender de Qt"
    assert "ifcopenshell" not in cod.lower(), "CMakeLists.txt nao pode depender de ifcopenshell"


def test_build_sh_estrito_e_pacote():
    # Mutante: remover "set -euo pipefail" (ou trocar por "set -e") ou importar ifcopenshell deve reprovar.
    assert BUILD_SH.is_file(), f"ausente: {BUILD_SH}"
    cod = _sem_comentarios_sh(BUILD_SH.read_text(encoding="utf-8"))
    assert re.search(r"^\s*set\s+-euo\s+pipefail(\s+#.*)?\s*$", cod, re.M)
    assert "obimvisib" in cod and "__init__.py" in cod
    assert "ifcopenshell" not in cod.lower()


def test_visibilidade_nao_importa_nativo():
    # Mutante: adicionar import de visib_nativo ou obimvisib em visibilidade.py deve reprovar.
    arvore = ast.parse(VISIB_PY.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes = [al.name for al in no.names]
        elif isinstance(no, ast.ImportFrom):
            nomes = [no.module or "", *(al.name for al in no.names)]
        else:
            continue
        for nome in nomes:
            assert "visib_nativo" not in nome and "obimvisib" not in nome, f"import proibido: {nome}"


def _verificar_flags_reais_linux(build_dir: Path) -> None:
    # Mutante: tirar -ffp-contract=off ou -O2 do target_compile_options deve reprovar.
    ninja = shutil.which("ninja")
    assert ninja, "ninja ausente no PATH"
    res = subprocess.run([ninja, "-C", str(build_dir), "-t", "commands"], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"ninja -t commands falhou ({res.returncode}):\n{res.stderr}"
    cmds = [
        toks
        for ln in res.stdout.splitlines()
        if "ponte_visib.cpp" in ln
        for toks in [shlex.split(ln)]
        if "-c" in toks and any(t.endswith("ponte_visib.cpp") for t in toks)
    ]
    assert cmds, "comando de compilacao de ponte_visib.cpp nao encontrado em ninja -t commands"
    for toks in cmds:
        assert "-ffp-contract=off" in toks, f"-ffp-contract=off ausente nas flags reais: {toks}"
        contratos = [t for t in toks if t.startswith("-ffp-contract=")]
        assert contratos[-1] == "-ffp-contract=off", f"ultima -ffp-contract= incorreta: {contratos}"
        otims = [t for t in toks if re.fullmatch(r"-O([0-3sfgz]|fast)?", t)]
        assert otims and otims[-1] == "-O2", f"ultima flag -O* nao e -O2: {otims}"
        toks_min = {t.lower() for t in toks}
        for proibida in FLAGS_PROIBIDAS:
            assert proibida.lower() not in toks_min, f"flag proibida nas flags reais: {proibida}"


def _verificar_rpath_linux(pkg_dir: Path) -> None:
    readelf = shutil.which("readelf")
    assert readelf, "readelf ausente no PATH"
    sos = sorted(pkg_dir.glob("_obimvisib*.so"))
    assert len(sos) == 1, f"esperava 1 .so em {pkg_dir}, achei {sos}"
    env = {**os.environ, "LC_ALL": "C"}
    res = subprocess.run([readelf, "-d", str(sos[0])], capture_output=True, text=True, env=env, timeout=30)
    assert res.returncode == 0, f"readelf -d falhou ({res.returncode}):\n{res.stderr}"
    linhas = [ln for ln in res.stdout.splitlines() if re.search(r"\((RPATH|RUNPATH)\)", ln)]
    assert len(linhas) == 1, f"esperava 1 entrada RPATH/RUNPATH, achei {linhas!r}"
    m = re.search(r"\((RPATH|RUNPATH)\).*\[([^\]]+)\]", linhas[0])
    assert m and m.group(1) == "RPATH" and m.group(2) == RPATH_ESPERADO, (
        f"esperava RPATH=[{RPATH_ESPERADO}], obtido: {linhas[0]!r}"
    )


def test_construcao_real_e_integracao(tmp_path, monkeypatch):
    if os.environ.get("OBIM_VISIB_BUILD") != "1":
        pytest.skip("defina OBIM_VISIB_BUILD=1; o CI roda no job obimcore")
    if not os.environ.get("CONDA_PREFIX"):
        pytest.skip("CONDA_PREFIX nao definido no ambiente")
    bash = shutil.which("bash")
    if shutil.which("cmake") is None or bash is None:
        pytest.skip("cmake ou bash ausente no PATH")
    assert BUILD_SH.is_file(), f"ausente: {BUILD_SH}"
    res = subprocess.run([bash, str(BUILD_SH), str(tmp_path)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, f"build.sh falhou ({res.returncode}):\n{res.stdout}\n{res.stderr}"
    assert (tmp_path / "obimvisib" / "__init__.py").is_file()
    if sys.platform.startswith("linux"):
        _verificar_flags_reais_linux(tmp_path / "build_obimvisib")
        _verificar_rpath_linux(tmp_path / "obimvisib")

    antes = {k: v for k, v in sys.modules.items() if k == "obimvisib" or k.startswith("obimvisib.")}
    for k in list(antes):
        sys.modules.pop(k, None)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    try:
        obimvisib = importlib.import_module("obimvisib")
        assert obimvisib.versao() == "1"
        assert obimvisib.somar(0.1, 0.2) == 0.1 + 0.2
        flags = obimvisib.flags_fp()
        assert isinstance(flags, str)
        esperada = "/fp:precise" if sys.platform == "win32" else "-ffp-contract=off"
        assert esperada in flags, f"esperava {esperada!r} em flags_fp()={flags!r}"
        vn = _visib_nativo()
        assert vn.carregar() is obimvisib
        monkeypatch.delenv("OBIM_VISIB_NATIVO", raising=False)
        assert vn.info() == {"ligado": False, "disponivel": True, "versao": "1", "flags_fp": flags}
        monkeypatch.setenv("OBIM_VISIB_NATIVO", "1")
        assert vn.info() == {"ligado": True, "disponivel": True, "versao": "1", "flags_fp": flags}
    finally:
        for k in [k for k in sys.modules if k == "obimvisib" or k.startswith("obimvisib.")]:
            sys.modules.pop(k, None)
        sys.modules.update(antes)
