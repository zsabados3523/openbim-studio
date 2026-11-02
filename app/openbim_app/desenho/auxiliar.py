# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cliente do processo auxiliar de geometria e desenho."""
import json
import logging
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
_logger = logging.getLogger(__name__)


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
                return
            except OSError as e:
                if tentativa < 2:
                    time.sleep(0.2)
                else:
                    _logger.warning("Falha ao apagar pasta temporária %s: %s", self.pasta, e)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fechar()


def _limpar_pastas_antigas():
    try:
        limite = time.time() - 86400
        temp_dir = Path(tempfile.gettempdir())
        for p in temp_dir.glob("obim-desenho-*"):
            try:
                if p.is_dir() and p.stat().st_mtime < limite:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
    except Exception:
        pass


def preparar(ifc, pedido: dict) -> Preparado:
    _limpar_pastas_antigas()
    p = dict(pedido)
    p.setdefault("protocolo", PROTOCOLO)
    p.setdefault("threads", min(8, os.cpu_count() or 1))
    pasta = Path(tempfile.mkdtemp(prefix="obim-desenho-", dir=tempfile.gettempdir()))
    arquivo = (pasta / "modelo.ifc").resolve()
    try:
        ifc.write(str(arquivo))
    except BaseException:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    p["arquivo"] = str(arquivo)
    return Preparado(p, pasta)


def _tratar_resposta(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ProtocoloInvalido(f"Resposta inválida do processo auxiliar: esperava dict, obteve {type(raw).__name__}")
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
        proc.join(timeout=5.0)
        if proc.is_alive():
            _logger.warning("Processo auxiliar (PID %s) não encerrou após kill e join(5)", getattr(proc, "pid", None))
    else:
        proc.join(timeout=5.0)


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
    proc = None
    t_inicio, fase_atual, resposta_raw = time.monotonic(), "", None
    saiu_sem_resposta = False

    try:
        proc = ctx.Process(target=entrada, args=(tx, json.dumps(preparado.pedido)), daemon=True)
        proc.start()
        tx.close()

        while True:
            if cancelar is not None and cancelar.is_set():
                raise DesenhoCancelado("Operação cancelada")
            decorrido = time.monotonic() - t_inicio
            if decorrido > limite_s:
                raise AuxiliarEstourouTempo(limite_s, fase_atual)
            espera = min(0.05, max(0.001, limite_s - decorrido))
            if rx.poll(espera):
                try:
                    raw_bytes = rx.recv_bytes()
                except (EOFError, OSError):
                    saiu_sem_resposta = True
                    break
                try:
                    msg = json.loads(raw_bytes.decode("utf-8"))
                except Exception as e:
                    raise ProtocoloInvalido(f"Mensagem do processo auxiliar não é JSON: {e}")
                if not isinstance(msg, dict):
                    raise ProtocoloInvalido(f"Mensagem do processo auxiliar não é um dicionário: {type(msg).__name__}")
                tipo = msg.get("tipo")
                if tipo == "fase":
                    fase_atual = msg.get("fase", fase_atual)
                elif tipo == "resposta":
                    resposta_raw = msg.get("dados")
                    break
            elif not proc.is_alive():
                saiu_sem_resposta = True
                while rx.poll(0.01):
                    try:
                        raw_bytes = rx.recv_bytes()
                    except (EOFError, OSError):
                        break
                    try:
                        msg = json.loads(raw_bytes.decode("utf-8"))
                    except Exception as e:
                        raise ProtocoloInvalido(f"Mensagem do processo auxiliar não é JSON: {e}")
                    if not isinstance(msg, dict):
                        raise ProtocoloInvalido(f"Mensagem do processo auxiliar não é um dicionário: {type(msg).__name__}")
                    if msg.get("tipo") == "resposta":
                        resposta_raw = msg.get("dados")
                        saiu_sem_resposta = False
                        break
                    elif msg.get("tipo") == "fase":
                        fase_atual = msg.get("fase", fase_atual)
                break

        if saiu_sem_resposta:
            proc.join(timeout=5.0)
    finally:
        for c in (rx, tx):
            try:
                c.close()
            except Exception:
                pass
        if proc is not None:
            _matar_filho(proc)

    if resposta_raw is not None:
        return _tratar_resposta(resposta_raw)
    codigo = proc.exitcode
    raise AuxiliarCaiu(0 if codigo == 0 else (codigo or 1), fase_atual)
