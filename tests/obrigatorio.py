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


# OBIM_CI=1 (RG-12) liga de uma vez as chaves de obrigatório da S04, uma por etapa. Fica de fora OBIM_S04_T14_OBRIGATORIO
# (casos B reais de test_s04_metas.py: a T14 ainda não existe). As chaves de tela e de localidade têm passo próprio no CI.
CHAVES_S04 = (
    "OBIM_S04_OBRIGATORIO", "OBIM_S04_VIEWPORT_OBRIGATORIO", "OBIM_S04_T07B_OBRIGATORIO", "OBIM_S04_T08_OBRIGATORIO",
    "OBIM_S04_T09_OBRIGATORIO", "OBIM_S04_T10_OBRIGATORIO", "OBIM_S04_T10B_OBRIGATORIO", "OBIM_S04_T10C_OBRIGATORIO",
    "OBIM_S04_T11_OBRIGATORIO", "OBIM_S04_T11B_OBRIGATORIO", "OBIM_S04_T11C_OBRIGATORIO", "OBIM_S04_T12_OBRIGATORIO",
    "OBIM_S04_T13_OBRIGATORIO", "OBIM_S04_T14A_OBRIGATORIO", "OBIM_S04_T16_OBRIGATORIO",
)


def ligar_ci():
    """Com OBIM_CI=1, cada chave de CHAVES_S04 que não foi definida passa a valer 1 (uma chave definida à mão vence)."""
    if os.environ.get("OBIM_CI") == "1":
        for chave in CHAVES_S04:
            os.environ.setdefault(chave, "1")
