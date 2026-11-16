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
import weakref
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot

from openbim_app.desenho.auxiliar import DesenhoCancelado
from openbim_app.desenho.filho import FilhoPersistente
from openbim_app.desenho.selecao import SessaoSelecao

TIPOS = ("planta", "corte")


def _motor_padrao(tipo, ifc, vista_guid, opcoes, *, cancelar, progresso, cache, previa=None, sessao_selecao=None, filho=None):
    from openbim_app.desenho.corte import gerar_corte
    from openbim_app.desenho.planta import gerar_planta

    progresso("calculando")
    if tipo == "planta":
        opcoes = {"pesados": "silhueta", "componentes": True, "motor_visivel": True, **opcoes}
        if previa is not None:
            def _cb_previa(svg):
                try:
                    previa({
                        "svg": svg,
                        "n_paths": svg.count("<path"),
                        "tempos": {},
                        "caixas": [],
                        "em_cache": [],
                        "pesados": [],
                        "parcial": True,
                    })
                except Exception:
                    pass

            opcoes["previa"] = _cb_previa
    if tipo == "corte":
        opcoes = {"motor_visivel": True, **opcoes}
    gerar = gerar_planta if tipo == "planta" else gerar_corte
    # cache exato (chave do pedido real, com elementos): leitura e gravacao aqui dentro
    kw_sessao = {"sessao_selecao": sessao_selecao} if sessao_selecao is not None else {}
    if filho is not None:
        kw_sessao["filho"] = filho
    r = gerar(ifc, vista_guid, cache=cache, cancelar=cancelar, **kw_sessao, **opcoes)
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
    def __init__(self, chave, vista, filho=None):
        self.chave, self.vista = chave, vista
        self.filho = filho
        self.cancelar = threading.Event()
        self.thread = None


class GerenteDesenho(QObject):
    progresso = Signal(str, str)
    pronto = Signal(str, object)
    falhou = Signal(str, str)
    previa = Signal(str, object)
    _evento = Signal(object, str, object)  # (pedido, tipo do evento, carga); interno

    def __init__(self, cache=None, *, motor=None, chave_estado=None, filho_persistente: bool = False, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._padrao = chave_estado is None
        self._usar_filho = bool(filho_persistente)
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
        self._sessoes: dict[int, tuple[object, SessaoSelecao, object]] = {}
        self._filhos_doc: dict[Path, FilhoPersistente] = {}
        self._evento.connect(self._tratar, Qt.ConnectionType.QueuedConnection)

    def pedir(self, tipo, ifc, vista_guid, *, caminho_ifc=None, revisao_salva=None, revisao=None, **opcoes) -> str:
        if tipo not in TIPOS:
            raise ValueError(f"tipo de desenho invalido: {tipo!r}")
        aberto = False
        caminho_resolvido = None
        if caminho_ifc and revisao is not None and revisao == revisao_salva:
            try:
                caminho_resolvido = Path(caminho_ifc).resolve()
                aberto = caminho_resolvido.is_file()
            except OSError:
                aberto = False
            if aberto:
                opcoes["caminho_ifc"] = caminho_ifc
        filho = None
        with self._trava:
            if self._usar_filho and aberto:
                filho = self._filhos_doc.get(caminho_resolvido)
                if filho is None:
                    filho = FilhoPersistente(caminho_resolvido)
                    self._filhos_doc[caminho_resolvido] = filho
            filhos_atuais = list(self._filhos_doc.values())
        chave = self._chave_estado(tipo, ifc, vista_guid, opcoes)
        sessao = self._obter_sessao(ifc, revisao) if revisao is not None else self._limpar_mortas()
        if chave in self._ativos:
            for f in filhos_atuais:
                f.podar()
            return chave
        antigo = self._por_vista.get(vista_guid)
        if antigo is not None:
            self.cancelar(antigo.chave)  # estado novo da mesma vista
        for f in filhos_atuais:
            f.podar()
        ped = _Pedido(chave, vista_guid, filho)
        if self._cache is not None:
            dados = self._cache.obter(chave)
            if dados is not None:
                self._ativos[chave] = self._por_vista[vista_guid] = ped
                self._evento.emit(ped, "pronto", dados)  # fila: nunca sincrono
                return chave
        self._ativos[chave] = self._por_vista[vista_guid] = ped
        ped.thread = threading.Thread(
            target=self._rodar, args=(ped, tipo, ifc, vista_guid, dict(opcoes), sessao), daemon=True)
        with self._trava:
            self._threads.add(ped.thread)
        ped.thread.start()
        return chave

    def _limpar_mortas_travado(self) -> None:
        for k, (_, _, ref) in list(self._sessoes.items()):
            if ref() is None:
                self._sessoes.pop(k, None)

    def _limpar_mortas(self) -> None:
        with self._trava:
            self._limpar_mortas_travado()

    def _criar_ref(self, ifc, chave_ifc: int):
        ref_gerente = weakref.ref(self)

        def _ao_morrer(ref_morta):
            g = ref_gerente()
            if g is not None:
                atual = g._sessoes.get(chave_ifc)
                if atual is not None and atual[2] is ref_morta:
                    g._sessoes.pop(chave_ifc, None)

        try:
            return weakref.ref(ifc, _ao_morrer)
        except TypeError:
            return lambda o=ifc: o

    def _obter_sessao(self, ifc, revisao) -> SessaoSelecao:
        with self._trava:
            self._limpar_mortas_travado()
            chave_ifc = id(ifc)
            atual = self._sessoes.get(chave_ifc)
            if atual is not None and atual[2]() is ifc and atual[0] == revisao:
                return atual[1]
            sessao = SessaoSelecao()
            ref = atual[2] if atual is not None and atual[2]() is ifc else self._criar_ref(ifc, chave_ifc)
            self._sessoes[chave_ifc] = (revisao, sessao, ref)
            return sessao

    @staticmethod
    def _copiar_sessao_sem(sessao: SessaoSelecao, excluir) -> SessaoSelecao:
        nova = SessaoSelecao()
        nova._caixas = sessao._caixas.copy()
        nova._erros = sessao._erros.copy()
        nova.invalidar(excluir)
        return nova

    def invalidar(self, ifc=None, ids=None) -> None:
        excluir = None if ids is None else tuple(int(i) for i in ids)
        with self._trava:
            self._limpar_mortas_travado()
            filhos = list(self._filhos_doc.values())
            if ifc is None:
                if excluir is None:
                    self._sessoes.clear()
                else:
                    for chave_ifc, (rev, sessao, ref) in list(self._sessoes.items()):
                        vivo = ref()
                        if vivo is None:
                            self._sessoes.pop(chave_ifc, None)
                            continue
                        self._sessoes[chave_ifc] = (rev, self._copiar_sessao_sem(sessao, excluir), ref)
                        del vivo
            else:
                chave_ifc = id(ifc)
                atual = self._sessoes.get(chave_ifc)
                if atual is not None and atual[2]() is ifc:
                    if excluir is None:
                        self._sessoes.pop(chave_ifc, None)
                    else:
                        self._sessoes[chave_ifc] = (atual[0], self._copiar_sessao_sem(atual[1], excluir), atual[2])
        for f in filhos:
            f.invalidar()

    def salvar(self) -> None:
        with self._trava:
            filhos = list(self._filhos_doc.values())
        for f in filhos:
            f.salvar()

    def cancelar(self, chave) -> None:
        ped = self._ativos.pop(chave, None)
        if ped is None:
            return
        ped.cancelar.set()
        if self._por_vista.get(ped.vista) is ped:
            del self._por_vista[ped.vista]

    def fechar(self) -> None:
        peds = list(self._ativos.values())
        for ped in peds:
            self.cancelar(ped.chave)
        with self._trava:
            self._sessoes.clear()
            vivas = list(self._threads)
            filhos = list(self._filhos_doc.values())
            self._filhos_doc.clear()
        for t in vivas:
            t.join(timeout=10)
        for f in filhos:
            f.podar()
            f.fechar()

    encerrar = fechar

    def _rodar(self, ped, tipo, ifc, vista_guid, opcoes, sessao=None):
        # Thread de fundo: nada de Qt aqui alem de emitir o sinal interno (fila).
        try:
            extra = {}
            try:
                params = inspect.signature(self._motor).parameters.values()
            except (TypeError, ValueError):
                params = ()
            nomes = {p.name for p in params}
            tem_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
            if "previa" in nomes or tem_kw:
                extra["previa"] = lambda d: self._evento.emit(ped, "previa", d)
            if sessao is not None and ("sessao_selecao" in nomes or tem_kw):
                extra["sessao_selecao"] = sessao
            filho = getattr(ped, "filho", None)
            if filho is not None and ("filho" in nomes or tem_kw):
                extra["filho"] = filho
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
