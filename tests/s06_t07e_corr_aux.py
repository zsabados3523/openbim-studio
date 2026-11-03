# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alvos de `spawn` do oráculo de correções da T07e1 (`test_s06_t07e_correcoes_oraculo.py`). Módulo leve (só biblioteca padrão): o filho o importa pelo nome. Não é de `app/`."""
import json
import time


def entrada_lixo(tx, pedido_json):  # mensagem que não é JSON
    tx.send_bytes(b"isto nao e json")
    time.sleep(1.5)


def entrada_dados_lista(tx, pedido_json):  # `dados` da resposta não é um dict
    tx.send_bytes(json.dumps({"tipo": "resposta", "dados": [1, 2]}).encode())
    time.sleep(1.5)


def entrada_muda(tx, pedido_json):  # fecha o canal e sai com código 0 (meio segundo depois) sem mandar resposta
    tx.close()
    time.sleep(0.5)
