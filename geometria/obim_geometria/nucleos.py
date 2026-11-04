# SPDX-License-Identifier: AGPL-3.0-or-later
"""Núcleos físicos e limite de threads da geometria (T07a2)."""
import os
import sys


class ThreadsInvalidas(ValueError):
    """Pedido de threads inválido (0, negativo, NaN/infinito, bool, float ou texto)."""


def _metade_dos_logicos() -> int:
    """Fallback conservador: metade dos núcleos lógicos, nunca o `cpu_count` cheio."""
    return max(1, (os.cpu_count() or 1) // 2)


def nucleos_fisicos() -> int:
    """Núcleos físicos da máquina. No Linux conta pares únicos (`physical id`, `core id`)
    de `/proc/cpuinfo`; fora do Linux ou sem dados confiáveis, cai para a metade dos lógicos."""
    if not sys.platform.startswith("linux"):
        return _metade_dos_logicos()
    try:
        pares = set()
        fisico = None
        with open("/proc/cpuinfo", encoding="ascii", errors="ignore") as arq:
            for linha in arq:
                chave, _, valor = linha.partition(":")
                chave = chave.strip()
                if chave == "physical id":
                    fisico = valor.strip()
                elif chave == "core id" and fisico is not None:
                    pares.add((fisico, valor.strip()))
        if pares:
            return max(1, len(pares))
    except OSError:
        pass
    return _metade_dos_logicos()


def limitar_threads(pedido=None, *, fisicos=None) -> int:
    """`None` = padrão (físicos, teto 8); inteiro >= 1 = `min(pedido, físicos, 8)`; resto = erro explícito."""
    if fisicos is None:
        fisicos = nucleos_fisicos()
    if pedido is None:
        return min(int(fisicos), 8)
    if isinstance(pedido, bool) or not isinstance(pedido, int):
        raise ThreadsInvalidas(f"Threads inválidas: {pedido!r} (esperado inteiro >= 1)")
    if pedido < 1:
        raise ThreadsInvalidas(f"Threads inválidas: {pedido!r} (esperado inteiro >= 1)")
    return min(pedido, int(fisicos), 8)
