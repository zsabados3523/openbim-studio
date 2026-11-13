# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19a: `faixas.rodar_filho` chamado de várias threads dentro de um processo DAEMON.
O processo auxiliar do app é daemon; `rodar_filho` alterna `current_process().daemon` para poder dar spawn.
Corrida antiga: `antigo_daemon` lido fora do lock `_SPAWN`; uma thread restaurava True enquanto outra ia dar spawn
-> AssertionError "daemonic processes are not allowed to have children" em todas as faixas.
Aqui: 6 threads, pedido inválido barato (op desconhecida, sem abrir IFC); nenhuma resposta pode citar "daemonic"."""
from __future__ import annotations

import json
import multiprocessing
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

N_THREADS = 6
PEDIDO = {"protocolo": 1, "op": "t19a_inexistente"}


def alvo_daemon(tx):
    """Roda no processo daemon (módulo importável, não lambda)."""
    import importlib

    faixas = importlib.import_module("obim_geometria.faixas")
    barreira = threading.Barrier(N_THREADS)

    def uma(_):
        barreira.wait(timeout=60)
        return faixas.rodar_filho(dict(PEDIDO), limite_s=60)

    try:
        with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
            resp = list(ex.map(uma, range(N_THREADS)))
        tx.send_bytes(json.dumps({"respostas": resp, "daemon": multiprocessing.current_process().daemon}).encode("utf-8"))
    except Exception as e:  # noqa: BLE001
        tx.send_bytes(json.dumps({"falha": f"{type(e).__name__}: {e}"}).encode("utf-8"))
    finally:
        tx.close()


def test_rodar_filho_threads_em_processo_daemon_sem_erro_daemonic():
    ctx = multiprocessing.get_context("spawn")
    rx, tx = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=alvo_daemon, args=(tx,), daemon=True)
    proc.start()
    tx.close()
    try:
        assert rx.poll(90), "processo daemon não respondeu a tempo"
        dados = json.loads(rx.recv_bytes().decode("utf-8"))
    finally:
        proc.join(10)
        if proc.is_alive():
            proc.kill()
    assert "falha" not in dados, dados.get("falha")
    resps = dados["respostas"]
    assert len(resps) == N_THREADS
    assert dados["daemon"] is True, "flag daemon do processo não foi restaurada"
    for r in resps:
        assert isinstance(r, dict)
        assert "daemonic" not in json.dumps(r).lower(), r
        assert r.get("ok") is False, r
