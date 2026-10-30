# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T04, parte da transação: `Sessao` = SessaoModelo + Lateral + Historico (S05) sobre um arquivo. Implementador não edita."""
import s05_conteudo_aux as R


class Sessao:  # o par SessaoModelo + Lateral + Historico (S05)
    def __init__(s, f):
        from openbim_app.lateral import Lateral
        from openbim_app.sessao_modelo import SessaoModelo
        from openbim_app.transacao import Historico
        s.f, s.lat, s.s = f, Lateral(), SessaoModelo(f)
        s.h = Historico(s.s, s.lat, limite_bytes=None)  # sem poda: o teste de 10.000 operações desfaz tudo

    def tx(s, fn):
        with s.s.escrever() as esc, s.h.transacao(esc) as t:
            fn(t)
        return t.resumo

    def desfazer(s):
        with s.s.escrever() as esc:
            return s.h.desfazer(esc)

    def refazer(s):
        with s.s.escrever() as esc:
            return s.h.refazer(esc)

    def foto(s):
        return R.foto(s.f, s.lat)

    def encerrar(s):
        s.h.encerrar()

