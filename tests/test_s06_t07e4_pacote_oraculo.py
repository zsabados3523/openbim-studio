# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e4 (empacotamento do auxiliar de geometria). Especificação: `cards/F0-S06/F0-S06-T07e-especificacao.md` (§4 tabela T07e4, §6 R3).
Sem empacotar nada (a máquina já travou): confere os scripts de build por leitura de texto e simula a árvore do pacote copiando `geometria/obim_geometria` para um `app/` temporário.
CONTRATO [P] (escolha do oráculo; o Opus confirma): o pacote leva `app/obim_geometria/` (cópia de `geometria/obim_geometria`, ao lado de `app/openbim_app`; o AppRun e o
`OpenBIM-Studio.pyw` já põem `app/` no caminho) e `LGPL-COMO-TROCAR.md` na raiz; o filho `spawn` sob `-I` (e `pythonw -I` no Windows) acha `obim_geometria` e faz `caixas`.
Provas do pacote real (CI): `packaging/linux/test_appimage_auxiliar.sh` e `packaging/windows/test_instalador_auxiliar.sh` (usam `packaging/geometria_no_pacote.py`).
Os nomes `*_ponte.sh` já existentes são do módulo obimcore e não são tocados. Marcadores `@AINDA_NAO_T07E4` tirados depois do build da e4.
`OBIM_T07E4_RAIZ` (só para mutantes) aponta outra raiz de repositório para os arquivos lidos por texto."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RAIZ = Path(os.environ.get("OBIM_T07E4_RAIZ") or REPO)
GEO = REPO / "geometria" / "obim_geometria"
MODULOS = ("__init__.py", "processo.py", "caixas.py", "desenho.py")
BUILD_LINUX = RAIZ / "packaging/linux/build_appimage.sh"
BUILD_WIN = RAIZ / "packaging/windows/build_installer.sh"
PROVA_LINUX = RAIZ / "packaging/linux/test_appimage_auxiliar.sh"
PROVA_WIN = RAIZ / "packaging/windows/test_instalador_auxiliar.sh"
AUX = RAIZ / "packaging/geometria_no_pacote.py"


def _comandos(script):
    """Linhas de comando (sem comentário), com o índice da linha."""
    return [(i, ln) for i, ln in enumerate(script.read_text(encoding="utf-8").splitlines()) if ln.strip() and not ln.lstrip().startswith("#")]


def _cp_geometria(script, destino):
    """Índices das linhas que levam geometria/obim_geometria para `<destino>/app/obim_geometria/` (a pasta inteira vai para `<destino>/app/`, ou todos os módulos para `<destino>/app/obim_geometria/`)."""
    d = re.escape(destino)
    pasta = re.compile(r"^\s*cp\s+-\S+\s+\"?\$REPO/geometria/obim_geometria/?\"?\s+\"?" + d + r"/app/?\"?\s*($|;|&&)")
    ach = [i for i, ln in _comandos(script) if pasta.match(ln)]
    por_modulo = [(i, ln) for i, ln in _comandos(script) if re.match(r"\s*(cp|install)\b", ln) and d + "/app/obim_geometria/" in ln]
    if not ach and all(any(m in ln for _, ln in por_modulo) for m in MODULOS):
        ach = [i for i, _ in por_modulo]
    return ach


def _limpeza_pycache(script, destino):
    return [i for i, ln in _comandos(script) if "__pycache__" in ln and re.search(r"\bfind\b.*" + re.escape(destino) + r"/app", ln) and "rm -rf" in ln]


def _pacote_falso(tmp_path, com_geometria=True):
    """Árvore mínima como o build monta: AppRun, env/bin (o Python deste ambiente), app/obim_geometria, LGPL-COMO-TROCAR.md."""
    if sys.platform == "win32":
        pytest.skip("pacote falso com wrapper bash so existe no Linux; a prova real do Windows e o test_instalador_auxiliar.sh no job instalador-windows do CI")
    r = tmp_path / "pacote"
    (r / "app").mkdir(parents=True)
    (r / "env").mkdir()
    (r / "env" / "bin").mkdir()
    py = r / "env" / "bin" / "python"  # exe de verdade dentro do pacote (realpath nao sai dele): reexecuta o Python deste ambiente mantendo o argv[0]
    py.write_text(f'#!/bin/bash\nexec -a "$0" "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    (r / "AppRun").write_text("#!/bin/sh\n")
    (r / "LGPL-COMO-TROCAR.md").write_text("trocar as bibliotecas\n", encoding="utf-8")
    if com_geometria:
        shutil.copytree(GEO, r / "app" / "obim_geometria", ignore=shutil.ignore_patterns("__pycache__"))
    return r


def _roda(cmd, tmp_path, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    e.update({"QT_QPA_PLATFORM": "offscreen", "TMPDIR": str(tmp_path), **env})
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=e)


def test_geometria_tem_os_modulos_que_o_pacote_leva():
    for m in MODULOS:
        assert (GEO / m).is_file(), m


def test_filho_sob_i_acha_obim_geometria_do_pacote_e_faz_caixas(tmp_path):
    r = _pacote_falso(tmp_path)
    sujo = tmp_path / "sujo" / "obim_geometria"
    sujo.mkdir(parents=True)
    (sujo / "__init__.py").write_text("raise ImportError('de fora do pacote')\n")
    p = _roda([str(r / "env/bin/python"), "-I", str(AUX), str(r)], tmp_path, PYTHONPATH=str(tmp_path / "sujo"))
    assert p.returncode == 0, p.stdout + p.stderr
    assert '"erros": []' in p.stdout and "[10.0, 20.0, 0.0, 14.0, 20.25, 3.0]" in p.stdout


def test_pacote_sem_obim_geometria_reprova(tmp_path):
    r = _pacote_falso(tmp_path, com_geometria=False)
    p = _roda([str(r / "env/bin/python"), "-I", str(AUX), str(r)], tmp_path, PYTHONPATH=str(REPO / "geometria"))
    assert p.returncode == 1 and "obim_geometria" in p.stdout  # o PYTHONPATH do repositório não pode salvar o pacote


@pytest.mark.parametrize("modulo", MODULOS)
def test_pacote_sem_um_modulo_de_obim_geometria_reprova(modulo, tmp_path):
    r = _pacote_falso(tmp_path)
    (r / "app" / "obim_geometria" / modulo).unlink()
    p = _roda([str(r / "env/bin/python"), "-I", str(AUX), str(r)], tmp_path)
    assert p.returncode == 1 and modulo in p.stdout


def test_pacote_sem_lgpl_reprova(tmp_path):
    r = _pacote_falso(tmp_path)
    (r / "LGPL-COMO-TROCAR.md").unlink()
    p = _roda([str(r / "env/bin/python"), "-I", str(AUX), str(r)], tmp_path)
    assert p.returncode == 1 and "LGPL-COMO-TROCAR.md" in p.stdout


@pytest.mark.parametrize("script,env", [(PROVA_LINUX, {}), (PROVA_WIN, {"OBIM_TESTE_SIMULADO": "1"})])
def test_scripts_de_prova_aprovam_pacote_certo_e_reprovam_sem_geometria(script, env, tmp_path):
    ok = _pacote_falso(tmp_path / "ok")
    assert _roda(["bash", str(script), str(ok)], tmp_path, **env).returncode == 0
    mau = _pacote_falso(tmp_path / "mau", com_geometria=False)
    p = _roda(["bash", str(script), str(mau)], tmp_path, **env)
    assert p.returncode == 1 and "FALHA" in p.stdout and "obim_geometria" in p.stdout


@pytest.mark.parametrize("script,palavras", [(PROVA_LINUX, ("geometria_no_pacote.py", " -I ", "PYTHONPATH")),
                                             (PROVA_WIN, ("geometria_no_pacote.py", " -I ", "PYTHONPATH", "pythonw", "--pythonw", "--saida"))])
def test_scripts_de_prova_existem_validos_e_chamam_o_auxiliar(script, palavras):
    assert script.is_file() and os.access(script, os.X_OK)
    if sys.platform != "win32":  # no Windows `bash` pode ser o do WSL (sem distribuicao): a sintaxe e conferida no Linux
        assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    txt = script.read_text(encoding="utf-8")
    assert all(p in txt for p in palavras), [p for p in palavras if p not in txt]
    assert "LGPL-COMO-TROCAR.md" in txt and "obim_geometria" in txt


def test_lgpl_como_trocar_listado_nos_dois_pacotes():
    for build, d in ((BUILD_LINUX, "$APPDIR"), (BUILD_WIN, "$PKG")):
        txt = build.read_text(encoding="utf-8")
        assert re.search(r"cp .*LGPL-COMO-TROCAR\.md.*" + re.escape(d), txt), build
    for p in (RAIZ / "packaging/linux/LGPL-COMO-TROCAR.md", RAIZ / "packaging/windows/LGPL-COMO-TROCAR.md"):
        assert p.stat().st_size > 200, p


def test_atalhos_do_windows_usam_pythonw_em_modo_isolado():
    nsi = (RAIZ / "packaging/windows/openbim-studio.nsi").read_text(encoding="utf-8")
    atalhos = [a for a in re.findall(r"CreateShortcut .*", nsi) if "Uninstall.exe" not in a]  # o atalho do desinstalador não conta
    assert atalhos and all("pythonw.exe" in a and "-I " in a for a in atalhos)
    assert 'exec "$HERE/env/bin/python" -I ' in (RAIZ / "packaging/linux/AppRun").read_text(encoding="utf-8")


@pytest.mark.parametrize("build,d", [(BUILD_LINUX, "$APPDIR"), (BUILD_WIN, "$PKG")])
def test_build_copia_pasta_obim_geometria_para_app_e_limpa_pycache_depois(build, d):
    cps, limpezas = _cp_geometria(build, d), _limpeza_pycache(build, d)
    assert cps, f"{build.name} deve copiar geometria/obim_geometria para {d}/app/ (resulta em app/obim_geometria/; todos os módulos)"
    assert limpezas, f"{build.name} deve limpar __pycache__ de {d}/app (find ... rm -rf)"
    assert max(cps) < min(i for i in limpezas if i > max(cps)) if any(i > max(cps) for i in limpezas) else False, "a limpeza de __pycache__ tem de vir DEPOIS do cp"


def test_copia_parcial_ou_solta_nao_conta():
    # autoteste do detector: 1 módulo só, ou módulos soltos em app/, não valem
    from tempfile import NamedTemporaryFile
    for texto in ('cp "$REPO/geometria/obim_geometria/processo.py" "$APPDIR/app/obim_geometria/"\n',
                  'cp "$REPO/geometria/obim_geometria/__init__.py" "$REPO/geometria/obim_geometria/processo.py" "$REPO/geometria/obim_geometria/caixas.py" "$REPO/geometria/obim_geometria/desenho.py" "$APPDIR/app/"\n',
                  '# cp -a "$REPO/geometria/obim_geometria" "$APPDIR/app/"\n'):
        with NamedTemporaryFile("w", suffix=".sh", delete=False) as t:
            t.write(texto)
        assert _cp_geometria(Path(t.name), "$APPDIR") == [], texto
        os.unlink(t.name)


def _passos_ci(job):
    ci = (RAIZ / ".github/workflows/ci.yml").read_text(encoding="utf-8").splitlines()
    ini = next(i for i, ln in enumerate(ci) if ln == f"  {job}:")
    fim = next((i for i in range(ini + 1, len(ci)) if re.match(r"  [a-z][\w-]*:$", ci[i])), len(ci))
    return ini, [(i, ln) for i, ln in enumerate(ci[ini:fim], ini) if not ln.lstrip().startswith("#")]


def test_ci_chama_a_prova_do_instalador_entre_instalar_e_desinstalar():
    _, linhas = _passos_ci("instalador-windows")
    cham = [i for i, ln in linhas if re.search(r"bash packaging/windows/test_instalador_auxiliar\.sh \"\$DEST\"", ln)]
    inst = [i for i, ln in linhas if "OpenBIM-Studio-Setup.exe" in ln and "/S" in ln]
    desi = [i for i, ln in linhas if "Uninstall.exe" in ln and "/S" in ln]
    assert len(cham) == 1 and inst and desi and inst[0] < cham[0] < desi[0]


def test_ci_chama_a_prova_do_appimage_com_a_imagem_no_job_appimage():
    _, linhas = _passos_ci("appimage")
    assert any(re.search(r"bash packaging/linux/test_appimage_auxiliar\.sh \"\$IMG\"", ln) for _, ln in linhas)


def test_falha_da_prova_do_auxiliar_publica_o_log_do_auxiliar():
    # hoje fim() le sempre ponte-inst.log: o erro do auxiliar sairia com o log da prova do obimcore (que passou)
    _, linhas = _passos_ci("instalador-windows")
    txt = "\n".join(ln for _, ln in linhas)
    fim = re.search(r"fim\(\) \{.*?\n\s*\}", txt, re.S)
    assert fim, "funcao fim() nao achada"
    corpo = fim.group(0)
    assert "auxiliar-inst.log" in corpo or re.search(r"\$\{?LOG|\$1.*\.log|\$2", corpo), "fim() deve poder publicar o auxiliar-inst.log"
    assert re.search(r"fim \"prova do auxiliar[^\n]*auxiliar-inst\.log|auxiliar-inst\.log[^\n]*fim \"prova do auxiliar|LOG=.*auxiliar-inst\.log", txt), "a chamada de falha do auxiliar deve apontar o auxiliar-inst.log"


def test_ci_do_instalador_detecta_mudanca_em_geometria():
    _, linhas = _passos_ci("instalador-windows")
    m = [re.search(r"grep -qE '(\^\([^']*)'", ln) for _, ln in linhas]
    regex = next(x.group(1) for x in m if x)
    assert re.match(regex, "geometria/obim_geometria/processo.py") is not None or "geometria/" in regex


def test_script_windows_ensaio_exercita_pythonw_e_saida_e_mostra_resultado(tmp_path):
    p = _roda(["bash", str(PROVA_WIN), str(_pacote_falso(tmp_path))], tmp_path, OBIM_TESTE_SIMULADO="1")
    assert p.returncode == 0, p.stdout
    assert p.stdout.count("--- resultado:") == 2 and p.stdout.count('"erros": []') >= 2  # python -I e pythonw -I, ambos via --saida


@pytest.mark.parametrize("script,env", [(PROVA_LINUX, {}), (PROVA_WIN, {"OBIM_TESTE_SIMULADO": "1"})])
def test_scripts_nao_escondem_o_erro_do_python_do_pacote(script, env, tmp_path):
    r = _pacote_falso(tmp_path)
    (r / "app/obim_geometria/__init__.py").write_text("raise ImportError('quebrado de proposito')\n")
    p = _roda(["bash", str(script), str(r)], tmp_path, **env)
    assert p.returncode == 1 and "FALHA" in p.stdout and "quebrado de proposito" in p.stdout + p.stderr
    logico = script.read_text(encoding="utf-8").replace("\\\n", " ")  # junta as continuacoes de linha
    chamadas = [ln for ln in logico.splitlines() if ("geometria_no_pacote.py" in ln or '"$HP"' in ln) and " -I " in ln and "timeout" in ln]
    assert chamadas and not any("/dev/null" in c or "|| true" in c or "|| :" in c for c in chamadas), chamadas
