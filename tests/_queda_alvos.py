# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alvos de nível de módulo para o processo filho (o spawn só importa funções de módulo): usados em test_viewport_queda_registro."""
import os
import signal


def sair_zero(tx, params):  # termina "bem" sem mandar `fim`
    os._exit(0)


def morrer_por_sinal(tx, params):  # morte por sinal: -15 no Linux, 15 no Windows (TerminateProcess)
    os.kill(os.getpid(), signal.SIGTERM)
