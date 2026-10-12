# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da T26 (lote Opus 6, §3.3): o IFC não pode sair com vírgula decimal depois de criar o QApplication.

Cada caso roda em SUBPROCESSO sem LC_ALL (o conftest.py põe LC_ALL=C no pytest e isso esconderia o defeito).
Casos que dependem de app/openbim_app/localidade.py pulam até o módulo existir (S03-T26).
Sem localidade pt_BR na máquina, tudo pula COM MENSAGEM EM DESTAQUE; nunca passa em silêncio.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "app"
AUX = Path(__file__).resolve().parent / "localidade_aux.py"
TEM_MODULO = (APP / "openbim_app" / "localidade.py").exists()
AGUARDA = pytest.mark.skipif(not TEM_MODULO, reason="aguarda S03-T26: localidade.py")
WIN = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")


def ambiente(pt_br=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith("LC_") and k not in ("LANG", "LANGUAGE")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(APP)
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    if pt_br and not WIN:
        env["LANG"] = "pt_BR.UTF-8"
        env["LC_NUMERIC"] = "pt_BR.UTF-8"
    return env


def rodar(*args, env=None, check=True):
    p = subprocess.run([sys.executable, *map(str, args)], env=env or ambiente(), capture_output=True,
                       text=True, timeout=120)
    if check:
        assert p.returncode == 0, f"subprocesso falhou ({p.returncode}):\n{p.stdout}\n{p.stderr}"
    return p


def caso(nome, pt_br=True):
    p = rodar(AUX, nome, env=ambiente(pt_br))
    return json.loads(p.stdout.strip().splitlines()[-1])


def destaque(msg):
    return "\n!!! " + msg + " !!!\n"


@pytest.fixture(scope="module")
def virgula_disponivel():
    nome = caso("provar_locale")["nome"]
    if not nome:
        pytest.skip(destaque("SEM LOCALIDADE pt_BR NESTA MAQUINA: oraculo da T26 NAO FOI EXECUTADO "
                             "(Linux: locale-gen pt_BR.UTF-8)"))
    return nome


@pytest.fixture(scope="module")
def canario_windows_ok(virgula_disponivel):
    """No Windows, L2 a L5 só provam algo se o IfcOpenShell enxerga a vírgula forçada (L1w)."""
    if WIN and "2799,9" not in caso("l1w")["texto"]:
        pytest.skip(destaque("CANARIO L1w NAO REPRODUZ NO WINDOWS: L2 a L5 pulados (passariam sem provar nada)"))


@pytest.fixture(scope="module")
def referencia(virgula_disponivel):
    env = ambiente(pt_br=False)
    env["LC_ALL"] = "C"  # só no processo de referência
    p = rodar(AUX, "ref", env=env)
    return json.loads(p.stdout.strip().splitlines()[-1])


def conferir_gravacao(r, ref):
    assert r["linhas"] == ref["linhas"], f"IFC difere de um processo em C:\n{r['linhas']}\n{ref['linhas']}"
    assert r["linhas_to_string"] == ref["linhas_to_string"]
    assert [tuple(p) for p in r["pontos"]] == [(2799.9999999999995, 0.5, 1e-7), (-0.001, 0.0, 0.0)]  # exatos, 3 coord.


@pytest.mark.skipif(WIN, reason="L1 é o canário do Linux (no Windows vale L1w)")
def test_l1_canario_qapplication_sem_correcao(virgula_disponivel):
    r = caso("l1")
    assert r["antes"] == ".", "pré-condição: o Python começa com ponto decimal"
    assert r["depois"] == ",", ("O CANARIO PAROU DE REPRODUZIR: o QApplication não troca mais a localidade; "
                                "revise o teste e a especificação da T26")
    assert "2799,9" in r["texto"], "o IfcOpenShell deveria gravar vírgula sem a correção (canário)"


def test_l1w_canario_forcando_virgula_a_mao(virgula_disponivel):
    r = caso("l1w")
    assert r["ponto"] == ",", f"localidade com vírgula não pôde ser forçada: {r}"
    assert "2799,9" in r["texto"], "o IfcOpenShell não enxerga a localidade forçada"


@AGUARDA
def test_l2_gravacao_identica_a_processo_em_c(canario_windows_ok, referencia):
    r = caso("l2")
    assert r["numerico_ok"] and r["ponto"] == "."
    conferir_gravacao(r, referencia)


@AGUARDA
def test_l3_interface_continua_brasileira(canario_windows_ok):
    r = caso("l3")
    assert r["numerico_ok"]
    if LINUX:  # no Linux o Qt segue o ambiente (pt_BR): valores exatos; datas e textos não mudam
        assert r["fmt"] == "1.234,50"
        assert r["nome_qt"] == "pt_BR"
        assert "pt_BR" in r["time"] and "pt_BR" in r["ctype"], r
    else:  # Windows e macOS: o Qt segue o idioma do sistema; a correção não pode mudar o que a interface mostra
        ref = caso("l3ref")
        assert (r["fmt"], r["nome_qt"]) == (ref["fmt"], ref["nome_qt"]), (r, ref)


@AGUARDA
def test_l4_outra_biblioteca_desfaz_a_correcao(canario_windows_ok, referencia):
    r = caso("l4")
    assert r["desfeito"] == ",", "pré-condição: a localidade com vírgula deveria ter voltado"
    assert r["garantiu"] is True
    assert r["depois_ok"] is True
    conferir_gravacao(r, referencia)


@AGUARDA
def test_l5_gravacao_em_thread_secundaria(canario_windows_ok, referencia):
    conferir_gravacao(caso("l5"), referencia)


@AGUARDA
def test_l6_selftest_em_pt_br(virgula_disponivel):
    p = rodar("-m", "openbim_app", "--selftest", env=ambiente())
    assert p.stdout.strip().splitlines()[-1] == "OK", p.stdout + p.stderr


@AGUARDA
def test_l6_qapplication_so_em_localidade_py():
    achados = {f.name for f in (APP / "openbim_app").rglob("*.py") if "QApplication(" in f.read_text(encoding="utf-8")}
    assert achados == {"localidade.py"}, f"QApplication( deve aparecer só em localidade.py; achado em {sorted(achados)}"
