# SPDX-License-Identifier: AGPL-3.0-or-later
"""Laço do processo auxiliar persistente de geometria com modelo IFC aberto."""
from __future__ import annotations

import json
import os
import traceback

import ifcopenshell
from obim_geometria import caixas, desenho

PROTOCOLO = 1


def _erro_dict(tipo: str, mensagem: str, rastro: str = "") -> dict:
    return {"ok": False, "erro": {"tipo": tipo, "mensagem": mensagem, "rastro": rastro}}


def servir(tx, rx) -> None:
    """Atende pedidos em sequência mantendo o último arquivo IFC aberto."""
    def enviar(obj: dict) -> None:
        tx.send_bytes(json.dumps(obj).encode("utf-8"))

    def responder(numero, dados: dict) -> None:
        enviar({"tipo": "resposta", "numero": numero, "dados": dados})

    def responder_erro(numero, tipo: str, mensagem: str, rastro: str = "") -> None:
        responder(numero, _erro_dict(tipo, mensagem, rastro))

    enviar({"tipo": "pronto", "pid": os.getpid(), "protocolo": PROTOCOLO})

    f = None
    arq = None
    sig_aberta: tuple[int, int] | None = None
    ultimo: int | None = None

    def _abrir_mantido(caminho, pavimento=None):
        if f is not None and (caminho is None or str(caminho) == str(arq)):
            return f
        return orig_abrir(caminho, pavimento)

    while True:
        try:
            bruto = rx.recv_bytes()
        except EOFError:
            return

        try:
            pedido = json.loads(bruto)
        except Exception as e:
            responder_erro(None, "PedidoInvalido", f"JSON inválido: {e}")
            continue

        if not isinstance(pedido, dict):
            responder_erro(None, "PedidoInvalido", "Pedido deve ser um objeto JSON")
            continue

        if pedido.get("op") == "encerrar":
            return

        numero = pedido.get("numero")
        if not isinstance(numero, int) or isinstance(numero, bool):
            responder_erro(None, "PedidoInvalido", "Pedido sem 'numero' inteiro válido")
            continue

        if ultimo is not None and numero <= ultimo:
            responder_erro(numero, "PedidoVelho", f"Pedido {numero} <= último aceito {ultimo}")
            continue
        ultimo = numero

        if pedido.get("protocolo", PROTOCOLO) != PROTOCOLO:
            responder_erro(numero, "ProtocoloInvalido", f"Protocolo inválido: {pedido.get('protocolo')}")
            continue

        op = pedido.get("op")
        if op not in ("desenho", "caixas"):
            responder_erro(numero, "OperacaoDesconhecida", f"Operação desconhecida: {op}")
            continue

        arquivo = pedido.get("arquivo")
        if not isinstance(arquivo, str) or not arquivo:
            responder_erro(numero, "PedidoInvalido", "Pedido sem 'arquivo' válido")
            continue

        def fase(nome: str, _n: int = numero) -> None:
            enviar({"tipo": "fase", "numero": _n, "fase": nome, "tempo": 0.0})

        try:
            erro_sig = desenho._conferir_assinatura(pedido)
            if erro_sig is not None:
                responder(numero, erro_sig)
                continue
            st = os.stat(arquivo)
            sig_atual = (int(st.st_size), int(st.st_mtime_ns))
            if f is None or arquivo != arq or sig_atual != sig_aberta:
                f = arq = sig_aberta = None
                f = ifcopenshell.open(arquivo)
                arq, sig_aberta = arquivo, sig_atual
            fase("aberto")
            with desenho._sem_rastro(f):
                if op == "caixas":
                    fase("geometria")
                    dados = caixas.processar(pedido, f=f)
                else:
                    orig_abrir = desenho._abrir_ifc
                    desenho._abrir_ifc = _abrir_mantido
                    try:
                        dados = desenho.processar(pedido, fase)
                    finally:
                        desenho._abrir_ifc = orig_abrir
        except Exception as e:
            responder_erro(numero, type(e).__name__, str(e), traceback.format_exc())
            continue

        responder(numero, dados)
