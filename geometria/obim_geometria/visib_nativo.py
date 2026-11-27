# SPDX-License-Identifier: AGPL-3.0-or-later
"""Carregamento e diagnostico do modulo nativo de visibilidade (`obimvisib`)."""
from __future__ import annotations

import importlib
import os
from types import ModuleType

ENV_LIGADO = "OBIM_VISIB_NATIVO"


def visib_nativo_ligado() -> bool:
    """Retorna True somente quando OBIM_VISIB_NATIVO == '1'."""
    return os.environ.get(ENV_LIGADO) == "1"


def carregar() -> ModuleType | None:
    """Importa `obimvisib` sob demanda ou retorna None se indisponivel."""
    try:
        return importlib.import_module("obimvisib")
    except (ImportError, OSError):
        return None


def info() -> dict[str, object]:
    """Retorna estado do seletor de ambiente e metadados do modulo nativo."""
    ligado = visib_nativo_ligado()
    mod = carregar()
    if mod is None:
        return {"ligado": ligado, "disponivel": False, "versao": None, "flags_fp": None}
    return {
        "ligado": ligado,
        "disponivel": True,
        "versao": mod.versao(),
        "flags_fp": mod.flags_fp(),
    }
