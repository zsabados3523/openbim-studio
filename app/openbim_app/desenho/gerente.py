# SPDX-License-Identifier: AGPL-3.0-or-later
"""Desenho em segundo plano: um pedido por vista, com cache e cancelamento (S06-T16).

Padrao de producao (chave_estado e motor nao injetados): a chave devolvida por pedir()
e provisoria (contador crescente), sem dedupe; todo pedir da mesma vista cancela o
anterior em voo. O cache de disco e lido e gravado so dentro de gerar_planta/gerar_corte
(thread de fundo, chave exata do pedido real); um hit real emite pronto rapido, do fundo.
Com chave_estado/motor injetados, o gerente consulta e grava o cache e deduplica por chave.
O chamador NAO deve alterar o ifc enquanto houver pedido em voo.
"""
from __future__ import annotations

import functools
import inspect
import itertools
import threading

from PySide6.QtCore import QObject, Qt, Signal, Slot

from openbim_app.desenho.auxiliar import DesenhoCancelado

TIPOS = ("planta", "corte")


def _motor_padrao(tipo, ifc, vista_guid, opcoes, *, cancelar, progresso, cache, previa=None):
    from openbim_app.desenho.corte import gerar_corte
    from openbim_app.desenho.planta import gerar_planta

    progresso("calculando")
    if tipo == "planta":
        opcoes = {"pesados": "silhueta", **opcoes}
    gerar = gerar_planta if tipo == "planta" else gerar_corte
    # cache exato (chave do pedido real, com elementos): leitura e gravacao aqui dentro
    r = gerar(ifc, vista_guid, cache=cache, cancelar=cancelar, **opcoes)
    dados = {
        "svg": r.svg,
        "n_paths": r.n_paths,
        "tempos": dict(r.tempos),
        "caixas": list(r.caixas),
        "em_cache": list(getattr(r, "em_cache", ())),
    }
    if tipo == "planta":
        dados["pesados"] = [dict(d) for d in (getattr(r, "pesados", ()) or ())]
    if tipo == "planta" and dados["pesados"]:
        if previa is not None:
            previa(dados)
        from openbim_app.desenho import refino
        dados = refino.refinar_pesados(
            ifc, r.pedido, dados, cache=cache, cancelar=cancelar, progresso=progresso)
    return dados


class _Pedido:
    def __init__(self, chave, vista):
        self.chave, self.vista = chave, vista
        self.cancelar = threading.Event()
        self.thread = None


class GerenteDesenho(QObject):
    progresso = Signal(str, str)
    pronto = Signal(str, object)
    falhou = Signal(str, str)
    previa = Signal(str, object)
    _evento = Signal(object, str, object)  # (pedido, tipo do evento, carga); interno

    def __init__(self, cache=None, *, motor=None, chave_estado=None, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._padrao = chave_estado is None
        if motor is None:
            from openbim_app.desenho.cache import CacheDesenho
            motor = functools.partial(
                _motor_padrao, cache=cache if cache is not None else CacheDesenho())
        self._motor = motor
        contador = itertools.count(1)
        self._chave_estado = chave_estado or (
            lambda tipo, ifc, guid, opcoes: f"{tipo}|{guid}|{next(contador)}")
        if self._padrao:
            self._cache = None  # cache fica no motor padrao
        self._threads: set = set()
        self._trava = threading.Lock()
        self._ativos: dict[str, _Pedido] = {}
        self._por_vista: dict[str, _Pedido] = {}
        self._evento.connect(self._tratar, Qt.ConnectionType.QueuedConnection)

    def pedir(self, tipo, ifc, vista_guid, **opcoes) -> str:
        if tipo not in TIPOS:
            raise ValueError(f"tipo de desenho invalido: {tipo!r}")
        chave = self._chave_estado(tipo, ifc, vista_guid, opcoes)
        if chave in self._ativos:
            return chave
        antigo = self._por_vista.get(vista_guid)
        if antigo is not None:
            self.cancelar(antigo.chave)  # estado novo da mesma vista
        ped = _Pedido(chave, vista_guid)
        if self._cache is not None:
            dados = self._cache.obter(chave)
            if dados is not None:
                self._ativos[chave] = self._por_vista[vista_guid] = ped
                self._evento.emit(ped, "pronto", dados)  # fila: nunca sincrono
                return chave
        self._ativos[chave] = self._por_vista[vista_guid] = ped
        ped.thread = threading.Thread(
            target=self._rodar, args=(ped, tipo, ifc, vista_guid, dict(opcoes)), daemon=True)
        with self._trava:
            self._threads.add(ped.thread)
        ped.thread.start()
        return chave

    def cancelar(self, chave) -> None:
        ped = self._ativos.pop(chave, None)
        if ped is None:
            return
        ped.cancelar.set()
        if self._por_vista.get(ped.vista) is ped:
            del self._por_vista[ped.vista]

    def encerrar(self) -> None:
        peds = list(self._ativos.values())
        for ped in peds:
            self.cancelar(ped.chave)
        with self._trava:
            vivas = list(self._threads)
        for t in vivas:
            t.join(timeout=10)

    def _rodar(self, ped, tipo, ifc, vista_guid, opcoes):
        # Thread de fundo: nada de Qt aqui alem de emitir o sinal interno (fila).
        try:
            extra = {}
            try:
                params = inspect.signature(self._motor).parameters.values()
            except (TypeError, ValueError):
                params = ()
            if "previa" in {p.name for p in params} or any(
                    p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
                extra["previa"] = lambda d: self._evento.emit(ped, "previa", d)
            dados = self._motor(
                tipo, ifc, vista_guid, opcoes, cancelar=ped.cancelar,
                progresso=lambda m: self._evento.emit(ped, "progresso", m), **extra)
            if ped.cancelar.is_set():
                return
            if self._cache is not None:
                self._cache.guardar(ped.chave, dados)
            self._evento.emit(ped, "pronto", dados)
        except DesenhoCancelado:
            pass
        except BaseException as e:  # falha vira sinal, nao derruba a thread
            if not ped.cancelar.is_set():
                self._evento.emit(ped, "falhou", str(e) or type(e).__name__)
        finally:
            with self._trava:
                self._threads.discard(ped.thread)

    @Slot(object, str, object)
    def _tratar(self, ped, tipo, carga):
        if self._ativos.get(ped.chave) is not ped or ped.cancelar.is_set():
            return  # cancelado ou estado velho: descarta
        if tipo == "previa":
            self.previa.emit(ped.chave, carga)
            return  # pedido segue vivo: o pronto ainda vem
        if tipo == "progresso":
            self.progresso.emit(ped.chave, carga)
            return
        self.cancelar(ped.chave)  # libera a vista (nao ha mais o que cancelar)
        if tipo == "pronto":
            self.pronto.emit(ped.chave, carga)
        else:
            self.falhou.emit(ped.chave, carga)
