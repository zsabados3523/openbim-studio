# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ponto de entrada do processo auxiliar de geometria."""
import json
import os
import time
import traceback

PROTOCOLO = 1


def entrada(tx, pedido_json):
    """Executado no processo filho (spawn)."""
    tx.send_bytes(json.dumps({"tipo": "pronto", "pid": os.getpid(), "protocolo": PROTOCOLO}).encode("utf-8"))
    if os.environ.get("OBIM_TESTE_AUX_SEGV") == "1":
        import faulthandler
        faulthandler._sigsegv()

    try:
        pedido = json.loads(pedido_json) if isinstance(pedido_json, str) else pedido_json
        dormir = os.environ.get("OBIM_TESTE_AUX_DORMIR_S")
        if dormir:
            time.sleep(float(dormir))
        sair = os.environ.get("OBIM_TESTE_AUX_SAIR")
        if sair:
            os._exit(int(sair))
        levantar = os.environ.get("OBIM_TESTE_AUX_LEVANTAR")
        if levantar:
            raise RuntimeError(levantar)

        if pedido.get("protocolo", 1) != PROTOCOLO:
            resp = {"ok": False, "erro": {"tipo": "ProtocoloInvalido", "mensagem": f"Protocolo inválido: {pedido.get('protocolo')}", "rastro": ""}}
            tx.send_bytes(json.dumps({"tipo": "resposta", "dados": resp}).encode("utf-8"))
            return

        tx.send_bytes(json.dumps({"tipo": "fase", "fase": "aberto", "tempo": 0.0}).encode("utf-8"))
        op = pedido.get("op")
        if op == "caixas":
            from obim_geometria import caixas
            tx.send_bytes(json.dumps({"tipo": "fase", "fase": "geometria", "tempo": 0.0}).encode("utf-8"))
            resp = caixas.processar(pedido)
        else:
            resp = {"ok": False, "erro": {"tipo": "OperacaoDesconhecida", "mensagem": f"Operação desconhecida: {op}", "rastro": ""}}
        tx.send_bytes(json.dumps({"tipo": "resposta", "dados": resp}).encode("utf-8"))
    except Exception as e:
        resp = {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
        try:
            tx.send_bytes(json.dumps({"tipo": "resposta", "dados": resp}).encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            tx.close()
        except Exception:
            pass
