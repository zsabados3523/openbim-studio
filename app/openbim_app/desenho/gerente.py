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

from openbim_app.desenho.auxiliar import DesenhoCancelado, ErroAuxiliar
from openbim_app.desenho.cache import arquivo_resolvido, assinatura_arquivo
from openbim_app.desenho.filho import FilhoIndisponivel, FilhoPersistente
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
    caminho_refino = opcoes.get("caminho_ifc")
    sig_inicio = assinatura_arquivo(caminho_refino) if (tipo == "planta" and caminho_refino is not None) else None
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
        faltantes = [int(x) for x in (getattr(r, "faltantes", ()) or ())]
        dados["faltantes"] = faltantes
        dados["incompleta"] = bool(getattr(r, "incompleta", False) or faltantes)
    if tipo == "planta" and dados["pesados"]:
        if previa is not None:
            previa(dados)
        from openbim_app.desenho import refino
        if (
            getattr(r, "divergente", False)
            or sig_inicio is None
            or assinatura_arquivo(caminho_refino) != sig_inicio
        ):
            caminho_refino = None
        dados = refino.refinar_pesados(
            ifc,
            r.pedido,
            dados,
            cache=cache,
            cancelar=cancelar,
            progresso=progresso,
            caminho_ifc=caminho_refino,
        )
    return dados


def _resolver_ifc_aberto(caminho_ifc, revisao, revisao_salva) -> Path | None:
    if not (caminho_ifc and revisao is not None and revisao == revisao_salva):
        return None
    return arquivo_resolvido(caminho_ifc)


class _Pedido:
    def __init__(self, chave, vista, filho=None, geracao=0):
        self.chave, self.vista = chave, vista
        self.filho = filho
        self.geracao = geracao
        self.cancelar = threading.Event()
        self.thread = None


class GerenteDesenho(QObject):
    """Gerencia pedidos de desenho em segundo plano."""
    progresso = Signal(str, str)
    pronto = Signal(str, object)
    falhou = Signal(str, str)
    previa = Signal(str, object)
    _evento = Signal(object, str, object)  # (pedido, tipo do evento, carga); interno

    def __init__(self, cache=None, *, motor=None, chave_estado=None, filho_persistente: bool = True, parent=None):
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
        self._cancelamentos_aquecer: set[threading.Event] = set()
        self._trava = threading.Lock()
        self._geracao = 0
        self._ativos: dict[str, _Pedido] = {}
        self._por_vista: dict[str, _Pedido] = {}
        self._sessoes: dict[int, tuple[object, SessaoSelecao, object]] = {}
        self._filhos_doc: dict[Path, FilhoPersistente] = {}
        self._evento.connect(self._tratar, Qt.ConnectionType.QueuedConnection)

    def _obter_filho_travado(self, caminho_resolvido: Path) -> tuple[FilhoPersistente, list[FilhoPersistente]]:
        filho = self._filhos_doc.get(caminho_resolvido)
        if filho is not None:
            return filho, []
        fechar_ociosos = []
        em_uso = {p.filho for p in list(self._ativos.values()) if p.filho is not None}
        for k, f_ant in list(self._filhos_doc.items()):
            if f_ant not in em_uso:
                self._filhos_doc.pop(k, None)
                fechar_ociosos.append(f_ant)
        filho = FilhoPersistente(caminho_resolvido)
        self._filhos_doc[caminho_resolvido] = filho
        return filho, fechar_ociosos

    def aquecer(self, caminho_ifc, *, revisao=None, revisao_salva=None) -> None:
        """Pré-aquece o filho persistente do documento salvo em segundo plano."""
        if not self._usar_filho:
            return
        caminho_resolvido = _resolver_ifc_aberto(caminho_ifc, revisao, revisao_salva)
        if caminho_resolvido is None:
            return
        cancelar = threading.Event()
        with self._trava:
            geracao = self._geracao
            filho, fechar_ociosos = self._obter_filho_travado(caminho_resolvido)
            t = threading.Thread(
                target=self._aquecer, args=(filho, geracao, cancelar), daemon=True
            )
            self._threads.add(t)
            self._cancelamentos_aquecer.add(cancelar)
        for f in fechar_ociosos:
            f.fechar()
        t.start()

    def _aquecer(self, filho: FilhoPersistente, geracao: int, cancelar: threading.Event) -> None:
        t = threading.current_thread()
        try:
            with self._trava:
                if geracao != self._geracao or cancelar.is_set():
                    return
            filho.aquecer(cancelar=cancelar)
        except (FilhoIndisponivel, ErroAuxiliar):
            pass
        finally:
            with self._trava:
                self._cancelamentos_aquecer.discard(cancelar)
                self._threads.discard(t)

    def pedir(self, tipo, ifc, vista_guid, *, caminho_ifc=None, revisao_salva=None, revisao=None, **opcoes) -> str:
        if tipo not in TIPOS:
            raise ValueError(f"tipo de desenho invalido: {tipo!r}")
        caminho_resolvido = _resolver_ifc_aberto(caminho_ifc, revisao, revisao_salva)
        if caminho_resolvido is not None:
            opcoes["caminho_ifc"] = caminho_resolvido
        filho = None
        fechar_ociosos = []
        with self._trava:
            geracao = self._geracao
            if self._usar_filho and caminho_resolvido is not None:
                filho, fechar_ociosos = self._obter_filho_travado(caminho_resolvido)
            filhos_atuais = list(self._filhos_doc.values())
        for f in fechar_ociosos:
            f.fechar()
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
        ped = _Pedido(chave, vista_guid, filho, geracao)
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
            self._geracao += 1
            for ev in self._cancelamentos_aquecer:
                ev.set()
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

    def salvar(self, caminho_ifc=None, *, revisao=None, revisao_salva=None) -> None:
        with self._trava:
            self._geracao += 1
            for ev in self._cancelamentos_aquecer:
                ev.set()
            filhos = list(self._filhos_doc.values())
        for f in filhos:
            f.salvar()
        if caminho_ifc is not None:
            self.aquecer(caminho_ifc, revisao=revisao, revisao_salva=revisao_salva)

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
            self._geracao += 1
            for ev in self._cancelamentos_aquecer:
                ev.set()
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
            with self._trava:
                mesma_geracao = ped.geracao == self._geracao
            if not mesma_geracao:
                opcoes = dict(opcoes)
                opcoes.pop("caminho_ifc", None)
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
            filho = getattr(ped, "filho", None) if mesma_geracao else None
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
