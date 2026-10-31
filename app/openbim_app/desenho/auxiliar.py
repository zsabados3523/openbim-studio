# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cliente do processo auxiliar de geometria e desenho."""
import json
import multiprocessing
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from obim_geometria.processo import PROTOCOLO, entrada

LIMITE_PADRAO_S = 180
_TRAVA_FILHO = threading.Lock()


class ErroAuxiliar(RuntimeError): pass
class DesenhoCancelado(ErroAuxiliar): pass
class ArquivoDivergente(ErroAuxiliar): pass
class ProtocoloInvalido(ErroAuxiliar): pass


class AuxiliarCaiu(ErroAuxiliar):
    def __init__(self, codigo_saida: int, fase: str = ""):
        super().__init__(f"Processo auxiliar caiu (código {codigo_saida}, fase '{fase}')")
        self.codigo_saida, self.fase = codigo_saida, fase


class AuxiliarEstourouTempo(ErroAuxiliar):
    def __init__(self, limite_s: float, fase: str = ""):
        super().__init__(f"Processo auxiliar estourou o tempo de {limite_s} s (fase '{fase}')")
        self.limite_s, self.fase = limite_s, fase


class FalhaNoAuxiliar(ErroAuxiliar):
    def __init__(self, tipo: str, mensagem: str, rastro: str):
        super().__init__(f"{tipo}: {mensagem}")
        self.tipo, self.mensagem, self.rastro = tipo, mensagem, rastro


class Preparado:
    def __init__(self, pedido: dict, pasta: Path):
        self.pedido, self.pasta = pedido, Path(pasta)

    def fechar(self):
        if not self.pasta.exists():
            return
        for tentativa in range(3):
            try:
                shutil.rmtree(self.pasta)
                break
            except OSError:
                if tentativa < 2:
                    time.sleep(0.2)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fechar()


def preparar(ifc, pedido: dict) -> Preparado:
    p = dict(pedido)
    p.setdefault("protocolo", PROTOCOLO)
    p.setdefault("threads", min(8, os.cpu_count() or 1))
    pasta = Path(tempfile.mkdtemp(prefix="obim-desenho-", dir=tempfile.gettempdir()))
    arquivo = (pasta / "modelo.ifc").resolve()
    ifc.write(str(arquivo))
    p["arquivo"] = str(arquivo)
    return Preparado(p, pasta)


def _tratar_resposta(raw: dict) -> dict:
    if raw.get("ok"):
        return raw
    erro = raw.get("erro", {})
    tipo, msg, rastro = erro.get("tipo", "RuntimeError"), erro.get("mensagem", ""), erro.get("rastro", "")
    if tipo == "ArquivoDivergente":
        raise ArquivoDivergente(msg)
    if tipo == "ProtocoloInvalido":
        raise ProtocoloInvalido(msg)
    raise FalhaNoAuxiliar(tipo, msg, rastro)


def _matar_filho(proc):
    if proc.is_alive():
        try:
            proc.kill()
        except OSError:
            pass
        proc.join(timeout=2.0)
    else:
        proc.join(timeout=0.5)


def executar(preparado: Preparado, *, limite_s: float = LIMITE_PADRAO_S, cancelar: threading.Event | None = None, executor=None) -> dict:
    if preparado.pedido.get("protocolo") != PROTOCOLO:
        raise ProtocoloInvalido(f"Protocolo inválido: {preparado.pedido.get('protocolo')}")
    if executor is not None:
        if cancelar is not None and cancelar.is_set():
            raise DesenhoCancelado("Operação cancelada antes de iniciar")
        return _tratar_resposta(executor(preparado.pedido))

    while not _TRAVA_FILHO.acquire(timeout=0.05):
        if cancelar is not None and cancelar.is_set():
            raise DesenhoCancelado("Operação cancelada na fila de espera")
    try:
        if cancelar is not None and cancelar.is_set():
            raise DesenhoCancelado("Operação cancelada antes de iniciar")
        return _executar_filho(preparado, limite_s, cancelar)
    finally:
        _TRAVA_FILHO.release()


def _executar_filho(preparado: Preparado, limite_s: float, cancelar: threading.Event | None) -> dict:
    ctx = multiprocessing.get_context("spawn")
    rx, tx = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=entrada, args=(tx, json.dumps(preparado.pedido)))
    t_inicio, fase_atual, resposta_raw = time.monotonic(), "", None
    proc.start()
    tx.close()

    try:
        while True:
            if cancelar is not None and cancelar.is_set():
                _matar_filho(proc)
                raise DesenhoCancelado("Operação cancelada")
            decorrido = time.monotonic() - t_inicio
            if decorrido > limite_s:
                _matar_filho(proc)
                raise AuxiliarEstourouTempo(limite_s, fase_atual)
            espera = min(0.05, max(0.001, limite_s - decorrido))
            if rx.poll(espera):
                try:
                    raw_bytes = rx.recv_bytes()
                except (EOFError, OSError):
                    break
                try:
                    msg = json.loads(raw_bytes.decode("utf-8"))
                except Exception:
                    continue
                tipo = msg.get("tipo")
                if tipo == "fase":
                    fase_atual = msg.get("fase", fase_atual)
                elif tipo == "resposta":
                    resposta_raw = msg.get("dados")
                    break
            elif not proc.is_alive():
                while rx.poll(0.01):
                    try:
                        raw_bytes = rx.recv_bytes()
                        msg = json.loads(raw_bytes.decode("utf-8"))
                        if msg.get("tipo") == "resposta":
                            resposta_raw = msg.get("dados")
                            break
                        elif msg.get("tipo") == "fase":
                            fase_atual = msg.get("fase", fase_atual)
                    except Exception:
                        break
                break
    finally:
        try:
            rx.close()
        except Exception:
            pass
        _matar_filho(proc)

    if resposta_raw is not None:
        return _tratar_resposta(resposta_raw)
    codigo = proc.exitcode
    raise AuxiliarCaiu(1 if codigo is None or codigo == 0 else codigo, fase_atual)
