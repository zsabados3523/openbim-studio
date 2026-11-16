# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gerenciamento do processo auxiliar persistente de geometria e desenho."""
from __future__ import annotations

import atexit
import functools
import json
import logging
import multiprocessing
import os
import threading
import time
import weakref
from importlib import import_module
from pathlib import Path

LIMITE_PADRAO_S = 180
_logger = logging.getLogger(__name__)


class FilhoIndisponivel(RuntimeError):
    pass


def _auxiliar():
    return import_module("openbim_app.desenho.auxiliar")


def _entrar_persistente(tx, rx) -> None:
    """Ponto de entrada padrão do filho persistente (carrega geometria só no filho)."""
    pacote = import_module("obim_geometria.processo").__package__
    import_module(".persistente", pacote).servir(tx, rx)


def _fechar_canais(*canais) -> None:
    for c in canais:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass


def _encerrar_ao_sair(ref: weakref.ref[FilhoPersistente]) -> None:
    inst = ref()
    if inst is not None:
        inst._matar_emergencia()


class FilhoPersistente:
    """Mantém um processo filho vivo com o IFC aberto entre pedidos de um documento."""

    def __init__(
        self,
        arquivo: str | Path,
        *,
        ocioso_s: float = 600.0,
        relogio=time.monotonic,
        alvo=None,
    ) -> None:
        self.arquivo = str(arquivo)
        self._ocioso_s = float(ocioso_s)
        self._relogio = relogio
        self._alvo = alvo
        self._ctx = multiprocessing.get_context("spawn")
        self._trava = threading.Lock()
        self._proc = None
        self._rx = None
        self._tx = None
        self._sig: tuple[int, int] | None = None
        self._fim_ultimo: float | None = None
        self._numero = 0
        self._quedas_seguidas = 0
        self._fechado = False
        self._atexit_fn = functools.partial(_encerrar_ao_sair, weakref.ref(self))
        atexit.register(self._atexit_fn)

    @property
    def pid(self) -> int | None:
        p = self._proc
        if p is None:
            return None
        try:
            return p.pid if p.is_alive() else None
        except Exception:
            return None

    def _disco(self) -> tuple[int, int] | None:
        try:
            st = os.stat(self.arquivo)
            return (int(st.st_size), int(st.st_mtime_ns))
        except OSError:
            return None

    def _ocioso(self) -> bool:
        if self._fim_ultimo is None:
            return False
        return (self._relogio() - self._fim_ultimo) > self._ocioso_s

    def _codigo_saida(self) -> int:
        p = self._proc
        if p is None:
            return 1
        try:
            if p.exitcode is None:
                p.join(timeout=0.5)
            code = p.exitcode
        except Exception:
            code = None
        return 0 if code == 0 else (code or 1)

    def _matar(self) -> None:
        p, rx, tx = self._proc, self._rx, self._tx
        self._proc = self._rx = self._tx = None
        self._sig = None
        self._fim_ultimo = None
        _fechar_canais(rx, tx)
        if p is not None:
            _auxiliar()._matar_filho(p)

    def _matar_emergencia(self) -> None:
        p, rx, tx = self._proc, self._rx, self._tx
        self._proc = self._rx = self._tx = None
        _fechar_canais(rx, tx)
        if p is not None:
            try:
                if p.is_alive():
                    p.kill()
                p.join(timeout=2.0)
            except Exception:
                pass

    def _ler(self, fim: float, cancelar: threading.Event | None, limite_s: float, fase_atual: str = "") -> dict:
        aux = _auxiliar()
        while True:
            if cancelar is not None and cancelar.is_set():
                raise aux.DesenhoCancelado("Operação cancelada")
            restante = fim - time.monotonic()
            if restante <= 0:
                raise aux.AuxiliarEstourouTempo(limite_s, fase_atual)
            if self._rx.poll(min(0.05, restante)):
                try:
                    bruto = self._rx.recv_bytes()
                except (EOFError, OSError):
                    raise aux.AuxiliarCaiu(self._codigo_saida(), fase_atual) from None
                return self._decodificar(bruto, aux)
            if not self._proc.is_alive():
                if self._rx.poll(0.01):
                    try:
                        bruto = self._rx.recv_bytes()
                    except (EOFError, OSError):
                        pass
                    else:
                        return self._decodificar(bruto, aux)
                raise aux.AuxiliarCaiu(self._codigo_saida(), fase_atual)

    @staticmethod
    def _decodificar(bruto: bytes, aux) -> dict:
        try:
            msg = json.loads(bruto.decode("utf-8"))
        except Exception as e:
            raise aux.ProtocoloInvalido(f"Mensagem do processo auxiliar não é JSON: {e}") from e
        if not isinstance(msg, dict):
            raise aux.ProtocoloInvalido(f"Mensagem do processo auxiliar não é um dicionário: {type(msg).__name__}")
        return msg

    def _subir(self, fim: float, cancelar: threading.Event | None, limite_s: float) -> None:
        aux = _auxiliar()
        rx, tx_c = self._ctx.Pipe(duplex=False)
        rx_c, tx = self._ctx.Pipe(duplex=False)
        alvo = self._alvo if self._alvo is not None else _entrar_persistente
        p = self._ctx.Process(target=alvo, args=(tx_c, rx_c), daemon=True)
        try:
            p.start()
        except BaseException:
            _fechar_canais(rx, tx_c, rx_c, tx)
            raise
        _fechar_canais(tx_c, rx_c)
        self._proc, self._rx, self._tx = p, rx, tx
        self._sig = self._disco()
        self._fim_ultimo = None
        msg = self._ler(fim, cancelar, limite_s)
        if msg.get("tipo") != "pronto":
            raise aux.ProtocoloInvalido(f"Esperava 'pronto' do filho persistente, recebeu {msg.get('tipo')!r}")

    def _adquirir_trava(self, cancelar: threading.Event | None, aux) -> None:
        if cancelar is not None and cancelar.is_set():
            raise aux.DesenhoCancelado("Operação cancelada antes de iniciar")
        while not self._trava.acquire(timeout=0.05):
            if cancelar is not None and cancelar.is_set():
                raise aux.DesenhoCancelado("Operação cancelada na fila de espera")

    def executar(
        self,
        pedido: dict,
        *,
        cancelar: threading.Event | None = None,
        limite_s: float = LIMITE_PADRAO_S,
        ao_fase=None,
    ) -> dict:
        aux = _auxiliar()
        self._adquirir_trava(cancelar, aux)
        try:
            if cancelar is not None and cancelar.is_set():
                raise aux.DesenhoCancelado("Operação cancelada antes de iniciar")
            fim = time.monotonic() + limite_s
            while True:
                if self._fechado:
                    raise FilhoIndisponivel("Filho persistente fechado")
                if self._proc is not None and not self._proc.is_alive():
                    self._matar()
                    self._quedas_seguidas += 1
                if self._proc is not None and (self._ocioso() or self._disco() != self._sig):
                    self._matar()
                if self._proc is None and self._quedas_seguidas >= 2:
                    raise FilhoIndisponivel("Filho persistente indisponível após quedas seguidas")

                fase_atual = ""
                try:
                    if self._proc is None:
                        self._subir(fim, cancelar, limite_s)
                    self._numero += 1
                    n = self._numero
                    try:
                        self._tx.send_bytes(json.dumps({**pedido, "numero": n}).encode("utf-8"))
                    except (BrokenPipeError, EOFError, OSError):
                        raise aux.AuxiliarCaiu(self._codigo_saida(), fase_atual) from None
                    while True:
                        msg = self._ler(fim, cancelar, limite_s, fase_atual)
                        if msg.get("numero") != n:
                            continue
                        tipo = msg.get("tipo")
                        if tipo == "fase":
                            fase_atual = msg.get("fase", fase_atual)
                            if ao_fase is not None:
                                ao_fase(fase_atual)
                        elif tipo == "resposta":
                            dados = msg.get("dados")
                            break
                except (aux.DesenhoCancelado, aux.AuxiliarEstourouTempo, aux.ProtocoloInvalido):
                    self._matar()
                    raise
                except aux.AuxiliarCaiu:
                    self._matar()
                    self._quedas_seguidas += 1
                    continue

                self._quedas_seguidas = 0
                self._fim_ultimo = self._relogio()
                if pedido.get("op") == "abrir" and isinstance(dados, dict) and dados.get("aberto") is True:
                    return dados
                return aux._tratar_resposta(dados)
        finally:
            self._trava.release()

    def aquecer(
        self,
        cancelar: threading.Event | None = None,
        limite_s: float = LIMITE_PADRAO_S,
    ) -> dict:
        """Pré-aquece o processo filho abrindo o IFC sem executar desenho."""
        return self.executar(
            {"op": "abrir", "protocolo": 1, "arquivo": self.arquivo},
            cancelar=cancelar,
            limite_s=limite_s,
        )

    def salvar(self) -> None:
        with self._trava:
            self._quedas_seguidas = 0
            self._matar()

    def invalidar(self) -> None:
        with self._trava:
            self._quedas_seguidas = 0
            self._matar()

    def podar(self) -> None:
        with self._trava:
            if self._proc is not None and self._ocioso():
                self._matar()

    def fechar(self) -> None:
        try:
            atexit.unregister(self._atexit_fn)
        except Exception:
            pass
        with self._trava:
            self._fechado = True
            self._matar()
