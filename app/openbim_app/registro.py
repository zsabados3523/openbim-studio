# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registro de erros (F0-RG-11): arquivo de texto na pasta do usuário, para o usuário poder mandar quando algo falhar.

Grava `openbim.log` (mensagens e erros não tratados, com a pilha) e `quedas.log` (queda do próprio Python/Qt,
pelo `faulthandler`). A pasta fica fora da instalação: `%LOCALAPPDATA%\\OpenBIM Studio\\logs` no Windows,
`~/.local/state/openbim-studio/logs` no Linux. A variável `OPENBIM_LOG_DIR` troca a pasta (testes)."""
import faulthandler
import logging
import os
import sys
import tempfile
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

NOME_LOG = "openbim.log"
NOME_QUEDAS = "quedas.log"
log = logging.getLogger("openbim")
_estado = {"pasta": None, "quedas": None, "handler": None, "antes": None, "dialogo": False, "em_dialogo": False}


def pasta_registros():
    """Pasta dos registros (não cria)."""
    forcada = os.environ.get("OPENBIM_LOG_DIR")
    if forcada:
        return Path(forcada)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "OpenBIM Studio" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "OpenBIM Studio"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "openbim-studio" / "logs"


def _abrir_pasta():
    """Cria a pasta dos registros; se não puder (disco somente leitura), usa a pasta temporária."""
    for pasta in (pasta_registros(), Path(tempfile.gettempdir()) / "OpenBIM Studio logs"):
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / NOME_LOG).touch()
            return pasta
        except OSError:
            continue
    return None


def _avisar(titulo, texto):
    """Diálogo de erro inesperado (só no app de verdade; os testes e o --selftest não abrem)."""
    if not _estado["dialogo"] or _estado["em_dialogo"] or os.environ.get("OPENBIM_SEM_DIALOGO"):
        return
    _estado["em_dialogo"] = True
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(None, titulo, texto)
    except Exception:  # noqa: BLE001 - o aviso nunca pode causar outro erro
        pass
    finally:
        _estado["em_dialogo"] = False


def _aviso_texto():
    return ("Ocorreu um erro inesperado. O programa tentou registrar o que houve.\n\n"
            f"Para pedir ajuda, mande os arquivos da pasta:\n{_estado['pasta']}\n"
            "(menu Ajuda > Abrir pasta de registros).")


def _gancho(tipo, valor, pilha):
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, pilha)
        return
    log.critical("Erro não tratado", exc_info=(tipo, valor, pilha))
    try:
        sys.__excepthook__(tipo, valor, pilha)  # com pythonw não há console; o erro já está no arquivo
    except Exception:  # noqa: BLE001
        pass
    _avisar("Erro inesperado", _aviso_texto())


def _gancho_thread(args):
    if args.exc_type is SystemExit:
        return
    nome = args.thread.name if args.thread else "?"
    log.critical("Erro não tratado na thread %s", nome, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def iniciar(dialogo=False):
    """Liga o registro: arquivo com rotação, ganchos de erro não tratado e `faulthandler`. Devolve a pasta (ou None).
    Chamar de novo não duplica nada. Nunca levanta: se não der para gravar, o programa abre do mesmo jeito."""
    _estado["dialogo"] = dialogo
    if _estado["pasta"] is not None:
        return _estado["pasta"]
    pasta = _abrir_pasta()
    if pasta is None:
        return None
    try:
        h = RotatingFileHandler(pasta / NOME_LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        quedas = open(pasta / NOME_QUEDAS, "a", encoding="utf-8")  # fica aberto até o fim: o faulthandler grava no descritor
        faulthandler.enable(file=quedas, all_threads=True)
        _estado["quedas"] = quedas
    except OSError:
        return None
    _estado.update(pasta=pasta, handler=h, antes=(sys.excepthook, threading.excepthook, faulthandler.is_enabled()))
    sys.excepthook = _gancho
    threading.excepthook = _gancho_thread
    log.info("Início: Python %s, %s, pasta de registros %s", sys.version.split()[0], sys.platform, pasta)
    return pasta


def parar():
    """Desfaz `iniciar` (testes): tira o arquivo e os ganchos e solta os arquivos abertos."""
    if _estado["pasta"] is None:
        return
    sys.excepthook, threading.excepthook, tinha_faulthandler = _estado["antes"]
    faulthandler.enable() if tinha_faulthandler else faulthandler.disable()
    log.removeHandler(_estado["handler"])
    _estado["handler"].close()
    _estado["quedas"].close()
    _estado.update(pasta=None, quedas=None, handler=None, antes=None, dialogo=False)


def instalar_qt():
    """Manda os avisos e erros do Qt para o mesmo arquivo (com pythonw eles se perderiam)."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    niveis = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO, QtMsgType.QtWarningMsg: logging.WARNING,
              QtMsgType.QtCriticalMsg: logging.ERROR, QtMsgType.QtFatalMsg: logging.CRITICAL}

    def gancho(tipo, _contexto, mensagem):
        log.log(niveis.get(tipo, logging.WARNING), "Qt: %s", mensagem)

    qInstallMessageHandler(gancho)
