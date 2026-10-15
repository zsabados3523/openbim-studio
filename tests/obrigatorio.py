# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pulo que vira falha no CI (RG-03): quando a chave está ligada, o teste que não pôde rodar FALHA em vez de pular.

Chaves: OBIM_TELA_OBRIGATORIA (testes que precisam de tela/contexto gráfico) e OBIM_LOCALIDADE_OBRIGATORIA
(testes que precisam da localidade pt_BR). O CI liga a primeira no passo com tela virtual e a segunda no Linux.
"""
import os

import pytest


def pular(msg, chave):
    """Pula o teste, ou falha se `chave` estiver ligada (valor "1")."""
    (pytest.fail if os.environ.get(chave) == "1" else pytest.skip)(msg)


def pular_sem_tela(msg):
    pular(msg, "OBIM_TELA_OBRIGATORIA")
