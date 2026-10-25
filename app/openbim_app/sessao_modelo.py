# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porta única do modelo (ADR-004 §5 e §5.1). Sem Qt, sem importar o `obimcore`.

`SessaoModelo` é a única dona do `ifcopenshell.file`: trava de leitura e escrita (vários leitores ou um escritor, com preferência do escritor),
reentrada proibida na hora, exceção solta a porta. O `obimcore` confere a trava por `_obimcore_entrar`/`_obimcore_sair` antes e depois da
geometria (o C++ nunca pega esta trava). Regra 3: o escritor parado esperando a geometria empresta a leitura (`emprestar_leitura`).
Ordem das travas (§5): esta sessão -> mutex da geometria -> `Motor::m_` -> `DadosCena::m_` -> `mc_`."""
import threading
import time
from contextlib import contextmanager

import ifcopenshell


class ModeloOcupado(RuntimeError):
    """Não conseguiu a porta dentro da espera."""


class ReentradaProibida(ModeloOcupado):
    """A thread já segura uma porta (ou o empréstimo) e pediu outra."""


class TravaNaoSegura(RuntimeError):
    """Acesso ao modelo sem a trava que o torna seguro."""


class Escrita:
    def __init__(self, sessao):
        self._s = sessao
        self._ativa = True

    @property
    def arquivo(self):
        s = self._s
        with s._cond:
            if not self._ativa or s._escritor != threading.get_ident() or s._emprestada:
                raise TravaNaoSegura("o arquivo só é do escritor dentro de escrever() e fora do empréstimo")
            return s._arquivo

    @contextmanager
    def emprestar_leitura(self):
        s, eu = self._s, threading.get_ident()
        with s._cond:
            if not self._ativa or s._escritor != eu:
                raise TravaNaoSegura("o empréstimo é só da thread do escritor")
            if s._emprestada:
                raise ReentradaProibida("empréstimo já aberto")
            s._emprestada = True
        try:
            yield
        finally:
            with s._cond:
                s._cond.wait_for(lambda: s._em_uso_cpp == 0)  # o escritor só volta com o C++ fora do modelo
                s._emprestada = False
                s._cond.notify_all()


class SessaoModelo:
    def __init__(self, arquivo):
        if not isinstance(arquivo, ifcopenshell.file):
            raise TypeError("esperado um ifcopenshell.file")
        self._arquivo = arquivo
        self._cond = threading.Condition()
        self._leitores = set()  # idents das threads dentro de ler()
        self._escritor = None
        self._esperando = 0
        self._emprestada = False
        self._em_uso_cpp = 0

    def estado(self):
        with self._cond:
            return {"leitores": len(self._leitores), "escritor": self._escritor, "esperando_escrever": self._esperando,
                    "emprestada": self._emprestada, "em_uso_cpp": self._em_uso_cpp}

    def _esperar(self, espera, livre):  # com self._cond; espera: None sem limite, 0 não espera
        if espera is not None and espera < 0:
            raise ValueError("espera negativa")
        eu = threading.get_ident()
        if eu in self._leitores or self._escritor == eu:
            raise ReentradaProibida("esta thread já segura o modelo")
        fim = None if espera is None else time.monotonic() + espera
        while not livre():
            resto = None if fim is None else fim - time.monotonic()
            if resto is not None and resto <= 0:
                raise ModeloOcupado("modelo ocupado")
            self._cond.wait(resto)
        return eu

    @contextmanager
    def ler(self, espera=None):
        with self._cond:
            eu = self._esperar(espera, lambda: self._escritor is None and self._esperando == 0)
            self._leitores.add(eu)
        try:
            yield self._arquivo
        finally:
            with self._cond:
                self._leitores.discard(eu)
                self._cond.notify_all()

    @contextmanager
    def escrever(self, espera=None):
        with self._cond:
            self._esperando += 1  # leitor novo não entra enquanto houver escritor esperando
            try:
                eu = self._esperar(espera, lambda: self._escritor is None and not self._leitores)
            finally:
                self._esperando -= 1
                self._cond.notify_all()
            self._escritor = eu
        esc = Escrita(self)
        try:
            yield esc
        finally:
            with self._cond:
                esc._ativa = False
                self._escritor = None
                self._cond.notify_all()

    def _obimcore_entrar(self):  # chamada pelo C++ com o bloqueio do interpretador, de qualquer thread
        eu = threading.get_ident()
        with self._cond:
            leitor = eu in self._leitores
            escritor_sem_emprestimo = self._escritor == eu and not self._emprestada
            outra_thread_no_emprestimo = self._emprestada and self._escritor != eu
            if not (leitor or escritor_sem_emprestimo or outra_thread_no_emprestimo):
                raise TravaNaoSegura("o modelo não está seguro para esta thread (sem ler(), escrever() ou empréstimo)")
            self._em_uso_cpp += 1
            return self._arquivo

    def _obimcore_sair(self):
        with self._cond:
            if self._em_uso_cpp == 0:
                raise RuntimeError("_obimcore_sair sem _obimcore_entrar")
            self._em_uso_cpp -= 1
            self._cond.notify_all()
