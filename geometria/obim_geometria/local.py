# SPDX-License-Identifier: AGPL-3.0-or-later
"""Executor local no mesmo processo (somente para testes)."""
import traceback


def executar(pedido: dict) -> dict:
    try:
        if pedido.get("protocolo", 1) != 1:
            return {"ok": False, "erro": {"tipo": "ProtocoloInvalido", "mensagem": f"Protocolo inválido: {pedido.get('protocolo')}", "rastro": ""}}
        op = pedido.get("op")
        if op == "caixas":
            from obim_geometria import caixas
            return caixas.processar(pedido)
        return {"ok": False, "erro": {"tipo": "OperacaoDesconhecida", "mensagem": f"Operação desconhecida: {op}", "rastro": ""}}
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
