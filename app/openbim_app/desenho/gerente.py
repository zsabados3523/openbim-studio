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
import math
import os
import threading
import time
import weakref
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot

from openbim_app.desenho.auxiliar import DesenhoCancelado, ErroAuxiliar
from openbim_app.desenho.cache import arquivo_resolvido, resolver_assinatura
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
    opcoes = dict(opcoes)
    sig_inicio = opcoes.pop("assinatura_ifc", None)
    caminho_refino = opcoes.get("caminho_ifc")
    if sig_inicio is None and caminho_refino is not None:
        caminho_refino, sig_inicio = resolver_assinatura(caminho_refino)
        if sig_inicio is not None:
            opcoes["caminho_ifc"] = caminho_refino
        else:
            opcoes.pop("caminho_ifc", None)
    if sig_inicio is not None:
        kw_sessao["assinatura_ifc"] = sig_inicio
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
        if getattr(r, "divergente", False) or sig_inicio is None:
            caminho_refino = None
            sig_refino = None
        else:
            sig_refino = sig_inicio
        dados = refino.refinar_pesados(
            ifc,
            r.pedido,
            dados,
            cache=cache,
            cancelar=cancelar,
            progresso=progresso,
            caminho_ifc=caminho_refino,
            assinatura_ifc=sig_refino,
        )
    return dados


def _resolver_ifc_aberto(caminho_ifc, revisao, revisao_salva) -> Path | None:
    if not (caminho_ifc and revisao is not None and revisao == revisao_salva):
        return None
    return arquivo_resolvido(caminho_ifc)


def _resolver_ifc_com_assinatura(caminho_ifc, revisao, revisao_salva) -> tuple[Path | None, tuple[int, int] | None]:
    if not (caminho_ifc and revisao is not None and revisao == revisao_salva):
        return None, None
    return resolver_assinatura(caminho_ifc)


def _ler_vmrss_mb(pid: int) -> float:
    with open(f"/proc/{pid}/status", "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            if linha.startswith("VmRSS:"):
                return float(linha.split()[1]) / 1024.0
    return 0.0


def _medir_rss_conjunto_mb() -> float:
    """Mede o RSS total (MB) do processo atual e seus descendentes."""
    raiz = os.getpid()
    if os.path.isdir(f"/proc/{raiz}"):
        vistos: set[int] = set()
        fila = [raiz]
        total = 0.0
        while fila:
            pid = fila.pop()
            if pid in vistos:
                continue
            vistos.add(pid)
            try:
                total += _ler_vmrss_mb(pid)
            except OSError:
                continue
            try:
                arqs = list(Path(f"/proc/{pid}/task").glob("*/children"))
            except OSError:
                arqs = []
            for arq in arqs:
                try:
                    txt = arq.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for tok in txt.split():
                    if tok.isdigit():
                        fila.append(int(tok))
        return total
    import psutil
    proc = psutil.Process(raiz)
    try:
        total = float(proc.memory_info().rss)
    except (psutil.Error, OSError):
        total = 0.0
    try:
        filhos = proc.children(recursive=True)
    except (psutil.Error, OSError):
        filhos = []
    for p in filhos:
        try:
            total += float(p.memory_info().rss)
        except (psutil.Error, OSError):
            continue
    return total / (1024.0 * 1024.0)


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

    def __init__(
        self,
        cache=None,
        *,
        motor=None,
        chave_estado=None,
        filho_persistente: bool = True,
        construir_cache: bool = False,
        limite_construcao: int | None = None,
        teto_memoria_mb: float = 6500.0,
        custo_trabalhador_mb: float = 2000.0,
        medir_rss_mb=None,
        intervalo_estado_s: float = 5.0,
        timeout_estado_s: float = 0.5,
        relogio=time.monotonic,
        parent=None,
    ):
        super().__init__(parent)
        if limite_construcao is not None:
            if isinstance(limite_construcao, bool):
                raise TypeError("limite_construcao nao pode ser bool")
            limite_construcao = max(1, int(limite_construcao))
        self._cache = cache
        self._padrao = chave_estado is None
        self._usar_filho = bool(filho_persistente)
        self._construir_cache = bool(construir_cache)
        self._limite_construcao = limite_construcao
        self._teto_memoria_mb = float(teto_memoria_mb)
        self._custo_trabalhador_mb = float(custo_trabalhador_mb)
        self._medir_rss_mb = medir_rss_mb
        self._intervalo_estado_s = max(0.0, float(intervalo_estado_s))
        self._timeout_estado_s = max(0.01, float(timeout_estado_s))
        self._relogio = relogio
        self._ultima_consulta_estado: float | None = None
        self._consultando_estado = False
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
        self._trava_vaga = threading.Lock()
        self._cond_vaga = threading.Condition(self._trava_vaga)
        self._fila_vagas: deque[_Pedido] = deque()
        self._vagas_em_uso = 0
        self._rss_reservado = 0.0
        self._geracao = 0
        self._ativos: dict[str, _Pedido] = {}
        self._por_vista: dict[str, _Pedido] = {}
        self._sessoes: dict[int, tuple[object, SessaoSelecao, object]] = {}
        self._filhos_doc: dict[Path, FilhoPersistente] = {}
        self._evento.connect(self._tratar, Qt.ConnectionType.QueuedConnection)

    def _construcao_ativa_agora(self) -> bool:
        with self._trava:
            return any(getattr(f, "construcao_ativa", False) for f in self._filhos_doc.values())

    def _consultar_estado_fundo(self, filhos: list, timeout_s: float) -> None:
        desativou = False
        try:
            for f in filhos:
                consultar = getattr(f, "consultar_estado_construcao", None)
                if callable(consultar):
                    try:
                        if consultar(timeout_s=timeout_s) is False:
                            desativou = True
                    except Exception:
                        pass
        finally:
            with self._trava:
                self._consultando_estado = False
            if desativou:
                with self._cond_vaga:
                    self._cond_vaga.notify_all()

    def _verificar_estado_construcao(self, *, sincrono: bool = False) -> None:
        agora = float(self._relogio())
        with self._trava:
            filhos = [f for f in self._filhos_doc.values() if getattr(f, "construcao_ativa", False)]
            if not filhos:
                self._ultima_consulta_estado = None
                return
            if self._ultima_consulta_estado is None:
                self._ultima_consulta_estado = agora
                return
            if (agora - self._ultima_consulta_estado) < self._intervalo_estado_s:
                return
            if self._consultando_estado and self._intervalo_estado_s <= 0.0:
                return
            self._ultima_consulta_estado = agora
            self._consultando_estado = True
            timeout_s = self._timeout_estado_s
        if sincrono:
            self._consultar_estado_fundo(filhos, timeout_s)
        else:
            threading.Thread(
                target=self._consultar_estado_fundo,
                args=(filhos, timeout_s),
                daemon=True,
            ).start()

    def _ler_rss_valido(self) -> float | None:
        try:
            medir = self._medir_rss_mb if self._medir_rss_mb is not None else _medir_rss_conjunto_mb
            rss = float(medir())
        except Exception:
            return None
        if not math.isfinite(rss) or rss < 0.0:
            return None
        return rss

    def _limite_com_rss(self, rss_medido: float | None, vagas: int, reservado: float) -> int:
        if rss_medido is None:
            return 1
        teto_n = self._limite_construcao if self._limite_construcao is not None else 2
        rss_efetivo = max(rss_medido, reservado)
        if self._custo_trabalhador_mb <= 0:
            adicionais = teto_n
        else:
            adicionais = int(max(0.0, self._teto_memoria_mb - rss_efetivo) // self._custo_trabalhador_mb)
        return max(1, min(teto_n, vagas + adicionais))

    def limite_trabalhadores(self) -> int | None:
        """Retorna o limite de trabalhadores durante construcao ativa, ou None."""
        if not self._construcao_ativa_agora():
            return None
        self._verificar_estado_construcao(sincrono=True)
        if not self._construcao_ativa_agora():
            return None
        rss_medido = self._ler_rss_valido()
        if not self._construcao_ativa_agora():
            return None
        with self._cond_vaga:
            vagas = self._vagas_em_uso
            reservado = self._rss_reservado
        return self._limite_com_rss(rss_medido, vagas, reservado)

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
            if self._construir_cache:
                with self._trava:
                    if geracao != self._geracao or cancelar.is_set():
                        return
                from openbim_app.desenho.cache import pasta_geometria
                filho.construir(str(pasta_geometria()), cancelar=cancelar)
                if getattr(filho, "construcao_ativa", False):
                    agora = float(self._relogio())
                    with self._trava:
                        self._ultima_consulta_estado = agora
        except (FilhoIndisponivel, ErroAuxiliar):
            pass
        finally:
            with self._trava:
                self._cancelamentos_aquecer.discard(cancelar)
                self._threads.discard(t)
            with self._cond_vaga:
                self._cond_vaga.notify_all()

    def pedir(self, tipo, ifc, vista_guid, *, caminho_ifc=None, revisao_salva=None, revisao=None, **opcoes) -> str:
        if tipo not in TIPOS:
            raise ValueError(f"tipo de desenho invalido: {tipo!r}")
        caminho_resolvido, sig = _resolver_ifc_com_assinatura(caminho_ifc, revisao, revisao_salva)
        if caminho_resolvido is not None and sig is not None:
            opcoes["caminho_ifc"] = caminho_resolvido
            opcoes["assinatura_ifc"] = sig
        else:
            opcoes.pop("caminho_ifc", None)
            opcoes.pop("assinatura_ifc", None)
        filho = None
        fechar_ociosos = []
        with self._trava:
            geracao = self._geracao
            if self._usar_filho and caminho_resolvido is not None:
                filho, fechar_ociosos = self._obter_filho_travado(caminho_resolvido)
            filhos_atuais = list(self._filhos_doc.values())
        for f in fechar_ociosos:
            f.fechar()
        if any(getattr(f, "construcao_ativa", False) for f in filhos_atuais):
            self._verificar_estado_construcao()
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
        with self._cond_vaga:
            self._cond_vaga.notify_all()

    def salvar(self, caminho_ifc=None, *, revisao=None, revisao_salva=None) -> None:
        with self._trava:
            self._geracao += 1
            for ev in self._cancelamentos_aquecer:
                ev.set()
            filhos = list(self._filhos_doc.values())
        for f in filhos:
            f.salvar()
        with self._cond_vaga:
            self._cond_vaga.notify_all()
        if caminho_ifc is not None:
            self.aquecer(caminho_ifc, revisao=revisao, revisao_salva=revisao_salva)

    def cancelar(self, chave) -> None:
        ped = self._ativos.pop(chave, None)
        if ped is None:
            return
        ped.cancelar.set()
        if self._por_vista.get(ped.vista) is ped:
            del self._por_vista[ped.vista]
        with self._cond_vaga:
            self._cond_vaga.notify_all()

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
        with self._cond_vaga:
            self._cond_vaga.notify_all()
        for t in vivas:
            t.join(timeout=10)
        for f in filhos:
            f.podar()
            f.fechar()

    encerrar = fechar

    def _adquirir_vaga(self, ped: _Pedido, opcoes: dict) -> tuple[int, float]:
        """Adquire vaga de trabalhador em fila FIFO durante construcao ativa; retorna (cota, reserva_mb)."""
        with self._cond_vaga:
            if ped.cancelar.is_set():
                raise DesenhoCancelado("cancelado na fila")
            self._fila_vagas.append(ped)
        try:
            while True:
                with self._cond_vaga:
                    while not ped.cancelar.is_set() and self._fila_vagas[0] is not ped:
                        self._cond_vaga.wait(timeout=0.1)
                    if ped.cancelar.is_set():
                        raise DesenhoCancelado("cancelado na fila")
                if not self._construcao_ativa_agora():
                    return 0, 0.0
                self._verificar_estado_construcao()
                rss_medido = self._ler_rss_valido()
                with self._cond_vaga:
                    if ped.cancelar.is_set():
                        raise DesenhoCancelado("cancelado na fila")
                    if self._fila_vagas[0] is not ped:
                        continue
                    limite = self._limite_com_rss(rss_medido, self._vagas_em_uso, self._rss_reservado)
                    if self._vagas_em_uso == 0 or self._vagas_em_uso < limite:
                        cota = 1
                        if "threads" in opcoes and opcoes["threads"] is not None:
                            cota = min(cota, max(1, int(opcoes["threads"])))
                        if rss_medido is None:
                            reserva_mb = max(
                                cota * max(0.0, self._custo_trabalhador_mb),
                                max(0.0, self._teto_memoria_mb),
                            )
                            rss_base = 0.0
                        else:
                            reserva_mb = cota * max(0.0, self._custo_trabalhador_mb)
                            rss_base = max(rss_medido, self._rss_reservado)
                        self._vagas_em_uso += cota
                        self._rss_reservado = max(self._rss_reservado, rss_base + reserva_mb)
                        opcoes["threads"] = cota
                        return cota, reserva_mb
                    self._cond_vaga.wait(timeout=0.1)
        finally:
            with self._cond_vaga:
                try:
                    self._fila_vagas.remove(ped)
                except ValueError:
                    pass
                self._cond_vaga.notify_all()

    def _rodar(self, ped, tipo, ifc, vista_guid, opcoes, sessao=None):
        # Thread de fundo: nada de Qt aqui alem de emitir o sinal interno (fila).
        cota = 0
        reserva_mb = 0.0
        try:
            cota, reserva_mb = self._adquirir_vaga(ped, opcoes)
            with self._trava:
                mesma_geracao = ped.geracao == self._geracao
            if not mesma_geracao:
                opcoes = dict(opcoes)
                opcoes.pop("caminho_ifc", None)
                opcoes.pop("assinatura_ifc", None)
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
            if cota:
                with self._cond_vaga:
                    self._vagas_em_uso = max(0, self._vagas_em_uso - cota)
                    if self._vagas_em_uso == 0:
                        self._rss_reservado = 0.0
                    else:
                        self._rss_reservado = max(0.0, self._rss_reservado - reserva_mb)
                    self._cond_vaga.notify_all()
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
