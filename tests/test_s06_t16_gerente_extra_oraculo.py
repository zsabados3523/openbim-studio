# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo T16 extra: corridas entre cache hit, cancelar, encerrar e chave provisoria.

Contrato adicional: com chave_estado=None o gerente usa chave provisoria (unica por
pedido) e NUNCA consulta nem grava o cache; quem cuida do cache e o motor.
"""
import threading
import time

import pytest

from test_s06_t16_gerente_oraculo import (  # noqa: F401
    CacheFalso, MotorFalso, Ouvinte, app, chave_estado, girar, girar_um_pouco,
)
from openbim_app.desenho.auxiliar import DesenhoCancelado
from openbim_app.desenho.gerente import GerenteDesenho


def _g(cache, motor=None):
    motor = motor or MotorFalso()
    g = GerenteDesenho(cache, motor=motor, chave_estado=chave_estado)
    return g, motor, Ouvinte(g)


@pytest.fixture
def limpar():
    itens = []
    yield itens
    for g, motor in itens:
        for p in motor.portoes:
            p.set()
        g.encerrar()


def test_cache_hit_cancelar_antes_de_emitir_nao_emite(app, limpar):
    k = chave_estado("planta", None, "V1", {})
    g, motor, o = _g(CacheFalso({k: {"svg": "x", "n_paths": 1}}))
    limpar.append((g, motor))
    assert g.pedir("planta", None, "V1") == k
    g.cancelar(k)  # antes de o loop girar
    girar_um_pouco(300)
    assert o.prontos == [] and o.falhas == [] and motor.chamadas == []


def test_cache_hit_pedido_novo_antes_do_loop_so_o_novo_emite(app, limpar):
    ka = chave_estado("planta", None, "V1", {"a": 1})
    kb = chave_estado("planta", None, "V1", {"a": 2})
    g, motor, o = _g(CacheFalso({ka: {"svg": "A", "n_paths": 1}, kb: {"svg": "B", "n_paths": 1}}))
    limpar.append((g, motor))
    assert g.pedir("planta", None, "V1", a=1) == ka
    assert g.pedir("planta", None, "V1", a=2) == kb
    assert girar(lambda: o.prontos)
    girar_um_pouco(200)
    assert o.prontos == [(kb, {"svg": "B", "n_paths": 1})]
    assert motor.chamadas == []


def test_dois_pedidos_identicos_no_mesmo_tick_com_cache_um_pronto(app, limpar):
    k = chave_estado("corte", None, "V1", {})
    g, motor, o = _g(CacheFalso({k: {"svg": "x", "n_paths": 1}}))
    limpar.append((g, motor))
    assert g.pedir("corte", None, "V1") == g.pedir("corte", None, "V1")
    assert girar(lambda: o.prontos)
    girar_um_pouco(200)
    assert len(o.prontos) == 1 and motor.chamadas == []


def test_encerrar_apos_cancelar_espera_a_thread_terminar(app):
    terminou = threading.Event()
    solta = threading.Event()
    iniciou = threading.Event()

    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso):
        iniciou.set()
        cancelar.wait(3)
        solta.wait(3)  # limpeza lenta depois do cancelamento
        terminou.set()
        raise DesenhoCancelado("cancelado")

    g = GerenteDesenho(CacheFalso(), motor=motor, chave_estado=chave_estado)
    k = g.pedir("planta", None, "V1")
    assert iniciou.wait(3)
    g.cancelar(k)
    threading.Timer(0.15, solta.set).start()
    t0 = time.monotonic()
    g.encerrar()
    assert terminou.is_set()  # encerrar() so volta com a thread ja finalizada
    assert time.monotonic() - t0 >= 0.1


class CacheProibido:
    def obter(self, chave):
        raise AssertionError("gerente consultou o cache sem chave_estado")

    def guardar(self, chave, dados):
        raise AssertionError("gerente gravou o cache sem chave_estado")


def test_chave_provisoria_nunca_toca_o_cache_e_so_o_segundo_emite(app, limpar):
    motor = MotorFalso()
    g = GerenteDesenho(CacheProibido(), motor=motor)  # chave_estado=None
    o = Ouvinte(g)
    limpar.append((g, motor))
    k1 = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    k2 = g.pedir("planta", None, "V1")
    assert k1 != k2 and isinstance(k1, str) and isinstance(k2, str)
    assert motor.cancelamentos[0].is_set()
    motor.esperar_inicio()
    motor.portoes[0].set()
    girar_um_pouco(150)
    assert o.prontos == []
    motor.portoes[1].set()
    assert girar(lambda: o.prontos)
    girar_um_pouco(150)
    assert [c for c, _ in o.prontos] == [k2] and o.falhas == []
