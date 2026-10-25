# SPDX-License-Identifier: AGPL-3.0-or-later
"""Foto do arquivo IFC: tamanho, data de modificação e soma de verificação. O carregador tira a foto antes da carga
e entrega a cada processo filho; se o arquivo mudar no meio (OneDrive sincronizando, outro programa gravando), a carga para com
uma mensagem clara em vez de misturar duas versões do mesmo arquivo. Python puro, sem Qt e sem ifcopenshell."""
from __future__ import annotations

import hashlib
import os


def tirar(caminho, com_soma=True):
    """{"tamanho", "data_ns", "soma"} do arquivo, ou None se não der para ler (quem abre depois dá o erro de verdade).
    A soma (BLAKE2b de 16 bytes) lê o arquivo inteiro: só pedir quando vale o custo."""
    try:
        st = os.stat(caminho)
        soma = None
        if com_soma:
            h = hashlib.blake2b(digest_size=16)
            with open(caminho, "rb") as a:
                for bloco in iter(lambda: a.read(1 << 20), b""):
                    h.update(bloco)
            soma = h.hexdigest()
        return {"tamanho": st.st_size, "data_ns": st.st_mtime_ns, "soma": soma}
    except OSError:
        return None


def mudou(caminho, foto, com_soma=False):
    """Texto explicando o que mudou desde a foto, ou None se está igual (ou se não há foto). Sem soma é barato (só `stat`)."""
    if not foto:
        return None
    agora = tirar(caminho, com_soma=com_soma and foto.get("soma") is not None)
    if agora is None:
        return "o arquivo não pôde ser lido de novo durante a carga (sumiu, foi movido ou ficou bloqueado)"
    if agora["tamanho"] != foto["tamanho"]:
        return f"o arquivo mudou durante a carga (tamanho {foto['tamanho']} -> {agora['tamanho']} bytes)"
    if agora["data_ns"] != foto["data_ns"]:
        return "o arquivo mudou durante a carga (a data de modificação mudou)"
    if com_soma and foto.get("soma") is not None and agora["soma"] != foto["soma"]:
        return "o arquivo mudou durante a carga (o conteúdo mudou)"
    return None
