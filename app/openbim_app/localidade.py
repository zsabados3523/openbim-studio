# SPDX-License-Identifier: AGPL-3.0-or-later
"""Localidade numérica do processo (T26).

O construtor do Qt troca a localidade numérica do C (LC_NUMERIC) para a do ambiente; em pt_BR o
IfcOpenShell passa a gravar "2799,99" (IFC corrompido, que ainda reabre). Aqui a categoria numérica
volta a "C" logo depois de criar a aplicação, e pode ser garantida de novo antes de gravar.
Números mostrados ao usuário vêm do QLocale, nunca de funções do C.
"""
import locale

from PySide6.QtWidgets import QApplication


def fixar_numerico_c() -> None:
    """Põe só a categoria numérica em "C" (separador decimal é ponto)."""
    locale.setlocale(locale.LC_NUMERIC, "C")


def numerico_ok() -> bool:
    """Verdadeiro se o separador decimal do processo é ponto."""
    return locale.localeconv()["decimal_point"] == "."


def garantir_numerico_c() -> bool:
    """Se a localidade numérica foi desfeita, corrige e devolve verdadeiro (quem chamou deve avisar)."""
    if numerico_ok():
        return False
    fixar_numerico_c()
    return True


def criar_aplicacao(argv):
    """Único lugar do programa que cria a aplicação Qt; corrige a localidade numérica em seguida."""
    app = QApplication.instance() or QApplication(argv)
    fixar_numerico_c()
    return app
