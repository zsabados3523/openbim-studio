# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do registro de erros e das mensagens de abertura (F0-RG-11)."""
import logging
import os
import runpy
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from openbim_app import registro
from openbim_app.main_window import MainWindow

RAIZ = Path(__file__).resolve().parent.parent
PYW = RAIZ / "packaging" / "windows" / "OpenBIM-Studio.pyw"


def _texto_log():
    for h in logging.getLogger("openbim").handlers:
        h.flush()
    return (registro.pasta_registros() / registro.NOME_LOG).read_text(encoding="utf-8")


def test_pasta_vem_da_variavel_e_sem_ela_fica_na_pasta_do_usuario(monkeypatch, tmp_path):
    assert registro.pasta_registros() == tmp_path / "logs-openbim"
    monkeypatch.delenv("OPENBIM_LOG_DIR")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "estado"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    pasta = registro.pasta_registros()
    esperado = {"win32": tmp_path / "local" / "OpenBIM Studio" / "logs", "linux": tmp_path / "estado" / "openbim-studio" / "logs"}
    if sys.platform in esperado:
        assert pasta == esperado[sys.platform]


def test_iniciar_cria_os_arquivos_e_nao_duplica():
    pasta = registro.iniciar()
    assert registro.iniciar() == pasta
    assert (pasta / registro.NOME_LOG).is_file() and (pasta / registro.NOME_QUEDAS).is_file()
    assert _texto_log().count("Início:") == 1


def test_erro_nao_tratado_vai_para_o_arquivo_com_a_pilha():
    registro.iniciar()
    try:
        raise ValueError("erro de teste 123")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    texto = _texto_log()
    assert "Erro não tratado" in texto and "ValueError: erro de teste 123" in texto and "Traceback" in texto


def test_erro_nao_tratado_em_thread_vai_para_o_arquivo():
    registro.iniciar()

    def falha():
        raise KeyError("na-thread")

    t = threading.Thread(target=falha, name="trabalhadora")
    t.start()
    t.join()
    assert "thread trabalhadora" in _texto_log() and "KeyError" in _texto_log()


def test_parar_devolve_os_ganchos():
    antes = (sys.excepthook, threading.excepthook)
    registro.iniciar()
    assert sys.excepthook is not antes[0]
    registro.parar()
    assert (sys.excepthook, threading.excepthook) == antes


def test_pasta_somente_leitura_nao_derruba_o_programa(monkeypatch, tmp_path):
    bloqueio = tmp_path / "arquivo"
    bloqueio.write_text("x")
    monkeypatch.setenv("OPENBIM_LOG_DIR", str(bloqueio / "dentro"))  # pai é arquivo: não dá para criar a pasta
    pasta = registro.iniciar()
    assert pasta is None or pasta != bloqueio / "dentro"  # caiu na pasta temporária (ou desligou), sem levantar


def test_menu_ajuda_abre_a_pasta_de_registros(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    abertos = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: abertos.append(url.toLocalFile()) or True)
    w = MainWindow()
    try:
        assert w.action_logs.text() == "Abrir pasta de registros"
        w.action_logs.trigger()
    finally:
        w.close()
    assert [Path(a) for a in abertos] == [tmp_path / "logs-openbim"] and (tmp_path / "logs-openbim").is_dir()


def _rodar_pyw(*args, **extra):
    env = {**os.environ, "PYTHONPATH": str(RAIZ / "app"), "QT_QPA_PLATFORM": "offscreen", "LC_ALL": "C", "OPENBIM_SEM_DIALOGO": "1", **extra}
    return subprocess.run([sys.executable, str(PYW), *args], env=env, capture_output=True, text=True, timeout=120)


def test_lancador_regra_da_pasta_igual_a_do_app():
    ns = runpy.run_path(str(PYW), run_name="teste")
    assert Path(ns["pasta_registros"]()) == registro.pasta_registros()


def test_lancador_selftest_ok_deixa_registro(tmp_path):
    pasta = tmp_path / "log-sub"
    r = _rodar_pyw("--selftest", OPENBIM_LOG_DIR=str(pasta))
    assert r.returncode == 0 and r.stdout.strip().endswith("OK"), r.stderr
    assert "selftest OK" in (pasta / registro.NOME_LOG).read_text(encoding="utf-8")


def test_lancador_falha_na_abertura_grava_abertura_log_e_sai_com_erro(tmp_path):
    pasta = tmp_path / "log-falha"
    r = _rodar_pyw("--selftest-falha", OPENBIM_LOG_DIR=str(pasta))
    assert r.returncode == 1
    texto = (pasta / "abertura.log").read_text(encoding="utf-8")
    assert "falha provocada por --selftest-falha" in texto and "Traceback" in texto
