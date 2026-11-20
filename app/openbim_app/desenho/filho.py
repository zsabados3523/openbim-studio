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
SAIDA_MEMORIA = 86
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
        self._construcao_params: dict | None = None
        self._construcao_ativa: bool = False
        self._sig_bloqueada_construir: tuple[int, int] | None = None
        self._atexit_fn = functools.partial(_encerrar_ao_sair, weakref.ref(self))
        atexit.register(self._atexit_fn)

    @property
    def construcao_ativa(self) -> bool:
        return self._construcao_ativa

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

    def _ocioso_vencido(self) -> bool:
        if self._fim_ultimo is None:
            return False
        return (self._relogio() - self._fim_ultimo) > self._ocioso_s

    def _ocioso(self) -> bool:
        return not self._construcao_ativa and self._ocioso_vencido()

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
        self._construcao_ativa = False
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

    def _tratar_morte(self, codigo: int) -> None:
        sig_morta = self._sig
        self._matar()
        if codigo == SAIDA_MEMORIA:
            self._sig_bloqueada_construir = sig_morta
            self._construcao_ativa = False
        else:
            self._quedas_seguidas += 1

    def _enviar_e_ler(
        self,
        pedido: dict,
        fim: float,
        cancelar: threading.Event | None,
        limite_s: float,
        aux,
        ao_fase=None,
    ) -> dict:
        self._numero += 1
        n = self._numero
        fase_atual = ""
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
                return msg.get("dados")

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
        if self._sig_bloqueada_construir is not None and self._sig != self._sig_bloqueada_construir:
            self._sig_bloqueada_construir = None
        if self._construcao_params is not None and (
            self._sig_bloqueada_construir is None or self._sig != self._sig_bloqueada_construir
        ):
            try:
                dados_c = self._enviar_e_ler(
                    {"op": "construir", "arquivo": self.arquivo, **self._construcao_params},
                    fim,
                    cancelar,
                    limite_s,
                    aux,
                )
            except aux.DesenhoCancelado:
                raise
            except Exception:
                self._construcao_ativa = False
            else:
                self._construcao_ativa = bool(
                    isinstance(dados_c, dict)
                    and dados_c.get("ok") is not False
                    and dados_c.get("aceito") is True
                    and int(dados_c.get("pendentes", 0)) > 0
                )

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
                    self._tratar_morte(self._codigo_saida())
                if self._proc is not None and (self._ocioso() or self._disco() != self._sig):
                    self._matar()
                if self._proc is None and self._quedas_seguidas >= 2:
                    raise FilhoIndisponivel("Filho persistente indisponível após quedas seguidas")

                try:
                    if self._proc is None:
                        self._subir(fim, cancelar, limite_s)
                    elif self._construcao_ativa and self._ocioso_vencido():
                        est = self._enviar_e_ler(
                            {"op": "estado_construcao", "arquivo": self.arquivo},
                            fim,
                            cancelar,
                            limite_s,
                            aux,
                        )
                        self._fim_ultimo = self._relogio()
                        if (
                            not isinstance(est, dict)
                            or est.get("ok") is False
                            or int(est.get("pendentes", 0)) == 0
                            or est.get("parado")
                        ):
                            self._construcao_ativa = False
                    dados = self._enviar_e_ler(
                        pedido, fim, cancelar, limite_s, aux, ao_fase=ao_fase
                    )
                except (aux.DesenhoCancelado, aux.AuxiliarEstourouTempo, aux.ProtocoloInvalido):
                    self._matar()
                    raise
                except aux.AuxiliarCaiu as e:
                    self._tratar_morte(e.codigo_saida)
                    continue

                self._quedas_seguidas = 0
                self._fim_ultimo = self._relogio()
                op = pedido.get("op")
                if op == "abrir" and isinstance(dados, dict) and dados.get("aberto") is True:
                    return dados
                if op in ("construir", "estado_construcao"):
                    res = self._tratar_resposta_construcao(op, dados, aux)
                    if op == "estado_construcao":
                        self._construcao_ativa = bool(
                            res.get("ativo", True)
                            and int(res.get("pendentes", 0)) > 0
                            and res.get("parado") is None
                        )
                    elif op == "construir":
                        self._construcao_ativa = bool(
                            res.get("aceito") is True
                            and int(res.get("pendentes", 0)) > 0
                            and res.get("parado") is None
                        )
                    return res
                return aux._tratar_resposta(dados)
        finally:
            self._trava.release()

    @staticmethod
    def _tratar_resposta_construcao(op: str, dados, aux) -> dict:
        if not isinstance(dados, dict):
            raise aux.ProtocoloInvalido(
                f"Resposta inválida do processo auxiliar: esperava dict, obteve {type(dados).__name__}"
            )
        if dados.get("ok") is False:
            erro = dados.get("erro") if isinstance(dados.get("erro"), dict) else {}
            raise aux.FalhaNoAuxiliar(
                erro.get("tipo", "RuntimeError"),
                erro.get("mensagem", ""),
                erro.get("rastro", ""),
            )
        if op == "construir" and ("aceito" not in dados or (dados.get("aceito") and "pendentes" not in dados)):
            raise aux.ProtocoloInvalido("Resposta de 'construir' sem 'aceito'/'pendentes'")
        return dados

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

    def construir(
        self,
        pasta_cache: str | Path,
        *,
        lote_max: int = 64,
        limite_mb: float = 6000.0,
        threads: int | None = None,
        cancelar: threading.Event | None = None,
        limite_s: float = LIMITE_PADRAO_S,
    ) -> dict:
        """Inicia ou atualiza a construção do cache de geometria em segundo plano no filho."""
        with self._trava:
            if self._sig_bloqueada_construir is not None:
                if self._disco() == self._sig_bloqueada_construir:
                    return {"aceito": False, "motivo": "memoria"}
                self._sig_bloqueada_construir = None
        params = {
            "pasta_cache": str(pasta_cache),
            "lote_max": int(lote_max),
            "limite_mb": float(limite_mb),
            "threads": threads,
        }
        dados = self.executar(
            {"op": "construir", "arquivo": self.arquivo, **params},
            cancelar=cancelar,
            limite_s=limite_s,
        )
        with self._trava:
            self._construcao_params = params
            self._construcao_ativa = bool(
                dados.get("aceito") and int(dados.get("pendentes", 0)) > 0 and dados.get("parado") is None
            )
        return dados

    def salvar(self) -> None:
        with self._trava:
            self._quedas_seguidas = 0
            self._matar()

    def invalidar(self) -> None:
        with self._trava:
            self._quedas_seguidas = 0
            self._matar()

    def podar(self) -> None:
        if not self._trava.acquire(blocking=False):
            return
        try:
            if self._proc is not None and self._ocioso():
                self._matar()
        finally:
            self._trava.release()

    def fechar(self) -> None:
        try:
            atexit.unregister(self._atexit_fn)
        except Exception:
            pass
        with self._trava:
            self._fechado = True
            self._matar()
