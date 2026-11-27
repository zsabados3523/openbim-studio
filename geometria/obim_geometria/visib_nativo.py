# SPDX-License-Identifier: AGPL-3.0-or-later
"""Carregamento e diagnostico do modulo nativo de visibilidade (`obimvisib`)."""
from __future__ import annotations

import importlib
import os
import threading
from types import ModuleType

ENV_LIGADO = "OBIM_VISIB_NATIVO"
VERSAO_ESPERADA = "1"
_CONTADOR_LOCK = threading.Lock()
_CHAMADAS_PY = {
    "unir_intervalos": 0,
    "filtrar_e_recortar": 0,
    "expandir_celulas": 0,
    "subseg_cels": 0,
    "filtrar_arestas_mapa_z": 0,
    "pares_celulas": 0,
    "subgrade_celulas_densas": 0,
}


def registrar_chamada_py(nome: str) -> None:
    """Incrementa contador de chamadas a versao Python de uma etapa."""
    with _CONTADOR_LOCK:
        _CHAMADAS_PY[nome] += 1


def obter_chamadas_py() -> dict[str, int]:
    """Retorna contagem de chamadas as versoes Python."""
    with _CONTADOR_LOCK:
        return dict(_CHAMADAS_PY)


def zerar_chamadas_py() -> None:
    """Zera contadores de chamadas as versoes Python."""
    with _CONTADOR_LOCK:
        for chave in _CHAMADAS_PY:
            _CHAMADAS_PY[chave] = 0


def visib_nativo_ligado() -> bool:
    """Retorna True somente quando OBIM_VISIB_NATIVO == '1'."""
    return os.environ.get(ENV_LIGADO) == "1"


def carregar() -> ModuleType | None:
    """Importa `obimvisib` sob demanda, valida a versao ou retorna None."""
    try:
        mod = importlib.import_module("obimvisib")
    except (ImportError, OSError):
        return None
    versao_fn = getattr(mod, "versao", None)
    if not callable(versao_fn):
        return None
    try:
        if versao_fn() != VERSAO_ESPERADA:
            return None
    except Exception:
        return None
    return mod


def exigir(nome: str):
    """Carrega `obimvisib` e retorna o simbolo `nome`, levantando ImportError se ausente."""
    mod = carregar()
    fn = getattr(mod, nome, None) if mod is not None else None
    if not callable(fn):
        raise ImportError(
            "Modulo nativo obimvisib indisponivel; compile com native/obim_visib/build.sh"
        )
    return fn


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
