# SPDX-License-Identifier: AGPL-3.0-or-later
"""Laço do processo auxiliar persistente de geometria com modelo IFC aberto."""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import time
import traceback

import ifcopenshell
from obim_geometria import caixas, desenho

PROTOCOLO = 1
SAIDA_MEMORIA = 86


def _erro_dict(tipo: str, mensagem: str, rastro: str = "") -> dict:
    return {"ok": False, "erro": {"tipo": tipo, "mensagem": mensagem, "rastro": rastro}}


def _estado_vazio(rss_mb: float) -> dict:
    return {
        "ativo": False,
        "pendentes": 0,
        "feitos": 0,
        "tesseladas": 0,
        "reaproveitadas": 0,
        "falhas": 0,
        "lotes": 0,
        "lote_max_s": 0.0,
        "rss_mb": rss_mb,
        "parado": None,
        "erro": None,
    }


def servir(tx, rx, *, construtor=None) -> None:
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
    cache = None
    construcao: dict | None = None

    def _abrir_mantido(caminho, pavimento=None):
        if f is not None and (caminho is None or str(caminho) == str(arq)):
            return f
        return orig_abrir(caminho, pavimento)

    def _rss_atual() -> float:
        return float(construtor.rss_mb()) if construtor is not None else 0.0

    def _garantir_aberto(arquivo: str) -> None:
        nonlocal f, arq, sig_aberta, construcao
        st = os.stat(arquivo)
        sig_atual = (int(st.st_size), int(st.st_mtime_ns))
        if f is None or arquivo != arq or sig_atual != sig_aberta:
            f = arq = sig_aberta = None
            construcao = None
            f = ifcopenshell.open(arquivo)
            arq, sig_aberta = arquivo, sig_atual

    def _estado_atual(arquivo: str) -> dict:
        if construcao is None or construcao["arquivo"] != arquivo:
            return _estado_vazio(_rss_atual())
        return {
            "ativo": True,
            "pendentes": len(construcao["fila"]),
            "feitos": construcao["feitos"],
            "tesseladas": construcao["tesseladas"],
            "reaproveitadas": construcao["reaproveitadas"],
            "falhas": construcao["falhas"],
            "lotes": construcao["lotes"],
            "lote_max_s": construcao["lote_max_s"],
            "rss_mb": _rss_atual(),
            "parado": construcao["parado"],
            "erro": construcao["erro"],
        }

    def _executar_lote() -> None:
        nonlocal construcao
        assert construcao is not None
        lote_max = construcao["lote_max"]
        ids = construcao["fila"][:lote_max]
        construcao["fila"] = construcao["fila"][lote_max:]
        t0 = time.monotonic()
        try:
            res = construtor.construir_lote(
                f,
                cache,
                ids,
                documento=construcao["documento"],
                assinatura=construcao["assinatura"],
                memo=construcao["memo"],
                threads=construcao["threads"],
            )
        except sqlite3.OperationalError as e:
            construcao["fila"] = ids + construcao["fila"]
            construcao["ocupado_seguidas"] += 1
            if construcao["ocupado_seguidas"] >= 3:
                construcao["parado"] = "banco_ocupado"
                construcao["erro"] = str(e)
            else:
                rx.poll(1.0)
            return
        except Exception as e:
            construcao["fila"] = ids + construcao["fila"]
            construcao["parado"] = "erro"
            construcao["erro"] = str(e)
            return

        dt = time.monotonic() - t0
        construcao["ocupado_seguidas"] = 0
        construcao["feitos"] += len(ids)
        construcao["tesseladas"] += int(res.get("tesseladas", 0))
        construcao["reaproveitadas"] += int(res.get("reaproveitadas", 0))
        construcao["falhas"] += int(res.get("falhas", 0))
        construcao["lotes"] += 1
        construcao["lote_max_s"] = max(construcao["lote_max_s"], float(res.get("segundos", dt)))
        if construtor.rss_mb() > construcao["limite_mb"]:
            if cache is not None:
                cache.fechar()
            os._exit(SAIDA_MEMORIA)

    while True:
        construcao_ativa = construcao is not None and bool(construcao["fila"]) and construcao["parado"] is None
        if construcao_ativa and not rx.poll(0):
            _executar_lote()
            continue

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
        if op not in ("desenho", "caixas", "abrir", "construir", "estado_construcao"):
            responder_erro(numero, "OperacaoDesconhecida", f"Operação desconhecida: {op}")
            continue

        arquivo = pedido.get("arquivo")
        if not isinstance(arquivo, str) or not arquivo:
            responder_erro(numero, "PedidoInvalido", "Pedido sem 'arquivo' válido")
            continue

        if op == "estado_construcao":
            responder(numero, _estado_atual(arquivo))
            continue

        if op == "construir":
            pasta_cache = pedido.get("pasta_cache")
            if not isinstance(pasta_cache, str) or not pasta_cache:
                responder_erro(numero, "PedidoInvalido", "Pedido sem 'pasta_cache' válido")
                continue
            if construtor is None:
                construtor = importlib.import_module("obim_geometria.construtor")
            try:
                _garantir_aberto(arquivo)
                if construcao is not None and construcao["arquivo"] == arquivo and construcao["sig"] == sig_aberta:
                    responder(numero, {"aceito": True, "pendentes": len(construcao["fila"])})
                    continue
                if cache is None:
                    try:
                        cache = construtor.abrir_banco(pasta_cache)
                    except ValueError:
                        responder(numero, {"aceito": False, "motivo": "banco_em_memoria"})
                        continue
                documento = construtor.documento_de(arquivo)
                assinatura = f"{sig_aberta[0]}:{sig_aberta[1]}"
                memo = cache.memo_ler(documento, assinatura)
                fila = list(construtor.fila_inicial(f))
                construcao = {
                    "arquivo": arquivo,
                    "sig": sig_aberta,
                    "documento": documento,
                    "assinatura": assinatura,
                    "memo": memo,
                    "fila": fila,
                    "lote_max": int(pedido.get("lote_max", 64)),
                    "limite_mb": float(pedido.get("limite_mb", 6000.0)),
                    "threads": pedido.get("threads"),
                    "feitos": 0,
                    "tesseladas": 0,
                    "reaproveitadas": 0,
                    "falhas": 0,
                    "lotes": 0,
                    "lote_max_s": 0.0,
                    "parado": None,
                    "erro": None,
                    "ocupado_seguidas": 0,
                }
                responder(numero, {"aceito": True, "pendentes": len(fila)})
            except Exception as e:
                responder_erro(numero, type(e).__name__, str(e), traceback.format_exc())
            continue

        def fase(nome: str, _n: int = numero) -> None:
            enviar({"tipo": "fase", "numero": _n, "fase": nome, "tempo": 0.0})

        try:
            erro_sig = desenho._conferir_assinatura(pedido)
            if erro_sig is not None:
                responder(numero, erro_sig)
                continue
            _garantir_aberto(arquivo)
            fase("aberto")
            if op == "abrir":
                dados = {"aberto": True}
            else:
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
        if op == "desenho" and construcao is not None and construcao["parado"] is None and construcao["fila"]:
            elementos = pedido.get("elementos") or []
            construcao["fila"] = construtor.priorizar(construcao["fila"], [eid for eid, _ in elementos])
