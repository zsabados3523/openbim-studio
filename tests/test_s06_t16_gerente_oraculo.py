# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo T16: GerenteDesenho (desenho em segundo plano, um pedido por vista).

Interface esperada (app/openbim_app/desenho/gerente.py):
  GerenteDesenho(cache=None, *, motor=None, chave_estado=None, parent=None)
    cache.obter(chave)->dict|None ; cache.guardar(chave, dict)
    chave_estado(tipo, ifc, vista_guid, opcoes: dict) -> str  (identifica o ESTADO)
    motor(tipo, ifc, vista_guid, opcoes, *, cancelar: threading.Event,
          progresso: Callable[[str], None]) -> dict   (roda FORA da thread principal;
          levanta DesenhoCancelado se cancelar for acionado)
  sinais: progresso(str, str), pronto(str, object), falhou(str, str)
  pedir(tipo, ifc, vista_guid, **opcoes) -> str (chave; imediato)
  cancelar(chave) -> None ; encerrar() -> None (cancela tudo e espera as threads)
  A chave devolvida e a de chave_estado: mesma vista+mesmo estado = mesma chave.
"""
import json
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app.desenho.auxiliar import DesenhoCancelado  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


class CacheFalso:
    def __init__(self, dados=None):
        self.dados = dict(dados or {})
        self.guardados = []

    def obter(self, chave):
        return self.dados.get(chave)

    def guardar(self, chave, dados):
        self.dados[chave] = dados
        self.guardados.append(chave)
        return True


def chave_estado(tipo, ifc, guid, opcoes):
    return f"{tipo}|{guid}|{json.dumps(opcoes, sort_keys=True)}"


class MotorFalso:
    """Cada chamada espera o seu Event `portao` (ou o cancelamento)."""

    def __init__(self, erro=None):
        self.chamadas = []
        self.threads = []
        self.cancelamentos = []
        self.portoes = []
        self.erro = erro
        self.iniciou = threading.Semaphore(0)

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso):
        portao = threading.Event()
        self.portoes.append(portao)
        self.chamadas.append((tipo, guid, dict(opcoes)))
        self.threads.append(threading.current_thread())
        self.cancelamentos.append(cancelar)
        self.iniciou.release()
        progresso("meio")
        fim = time.monotonic() + 4
        while not portao.is_set():
            if cancelar.is_set():
                break
            if time.monotonic() > fim:
                raise TimeoutError("teste esqueceu de liberar o motor")
            time.sleep(0.005)
        if self.erro:
            raise self.erro
        if cancelar.is_set() and not portao.is_set():
            raise DesenhoCancelado("cancelado")
        return {"svg": f"<svg>{guid}{sorted(opcoes.items())}</svg>", "n_paths": 1}

    def esperar_inicio(self, n=1):
        for _ in range(n):
            assert self.iniciou.acquire(timeout=3)


def girar(cond, ms=3000):
    """Roda o loop de eventos ate cond() ou estourar ms."""
    loop = QEventLoop()
    t = QTimer()
    t.setInterval(5)
    fim = time.monotonic() + ms / 1000
    def tic():
        if cond() or time.monotonic() > fim:
            loop.quit()
    t.timeout.connect(tic)
    t.start()
    loop.exec()
    t.stop()
    return cond()


def girar_um_pouco(ms=150):
    girar(lambda: False, ms)


class Ouvinte:
    def __init__(self, g):
        self.prontos, self.falhas, self.progressos = [], [], []
        g.pronto.connect(lambda c, r: self.prontos.append((c, r)))
        g.falhou.connect(lambda c, m: self.falhas.append((c, m)))
        g.progresso.connect(lambda c, m: self.progressos.append((c, m)))


@pytest.fixture
def montar(app):
    criados = []

    def f(cache=None, motor=None):
        motor = motor or MotorFalso()
        g = GerenteDesenho(cache or CacheFalso(), motor=motor, chave_estado=chave_estado)
        criados.append((g, motor))
        return g, motor, Ouvinte(g)

    yield f
    for g, motor in criados:
        for p in motor.portoes:
            p.set()
        g.encerrar()


def test_cache_hit_nao_chama_motor_e_emite_assincrono(montar):
    chave = chave_estado("planta", None, "V1", {})
    g, motor, o = montar(cache=CacheFalso({chave: {"svg": "<svg/>", "n_paths": 3}}))
    k = g.pedir("planta", None, "V1")
    assert k == chave
    assert o.prontos == []  # nunca emite de forma sincrona
    assert girar(lambda: o.prontos)
    assert o.prontos == [(chave, {"svg": "<svg/>", "n_paths": 3})]
    girar_um_pouco()
    assert motor.chamadas == [] and len(o.prontos) == 1 and o.falhas == []


def test_dois_pedidos_identicos_uma_chamada_um_pronto(montar):
    g, motor, o = montar()
    k1 = g.pedir("corte", None, "V1", profundidade=2.0)
    motor.esperar_inicio()
    k2 = g.pedir("corte", None, "V1", profundidade=2.0)
    assert k1 == k2
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    girar_um_pouco()
    assert len(motor.chamadas) == 1 and len(o.prontos) == 1
    assert o.prontos[0][0] == k1


def test_resultado_vai_para_o_cache_e_segundo_pedido_nao_usa_motor(montar):
    cache = CacheFalso()
    g, motor, o = montar(cache=cache)
    k = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    assert cache.guardados == [k]
    g.pedir("planta", None, "V1")
    assert girar(lambda: len(o.prontos) == 2)
    assert len(motor.chamadas) == 1


def test_pedido_novo_da_mesma_vista_cancela_antigo(montar):
    g, motor, o = montar()
    k1 = g.pedir("planta", None, "V1", ocultar=False)
    motor.esperar_inicio()
    k2 = g.pedir("planta", None, "V1", ocultar=True)
    assert k1 != k2
    assert motor.cancelamentos[0].is_set()  # antigo recebeu o sinal de cancelar
    motor.esperar_inicio()
    motor.portoes[0].set()  # antigo termina "com resultado": nao pode ser emitido
    girar_um_pouco()
    assert o.prontos == []
    motor.portoes[1].set()
    assert girar(lambda: o.prontos)
    girar_um_pouco()
    assert [c for c, _ in o.prontos] == [k2] and o.falhas == []


def test_vistas_diferentes_nao_se_cancelam(montar):
    g, motor, o = montar()
    ka = g.pedir("planta", None, "A")
    kb = g.pedir("planta", None, "B")
    motor.esperar_inicio(2)
    assert not any(c.is_set() for c in motor.cancelamentos)
    for p in motor.portoes:
        p.set()
    assert girar(lambda: len(o.prontos) == 2)
    assert {c for c, _ in o.prontos} == {ka, kb}


def test_cancelar_nao_emite_nada_e_libera(montar):
    g, motor, o = montar()
    k = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    g.cancelar(k)
    assert motor.cancelamentos[0].is_set()
    girar_um_pouco(300)
    assert o.prontos == [] and o.falhas == []  # nem pronto nem falhou
    g.pedir("planta", None, "V1")  # liberado: refaz o calculo
    motor.esperar_inicio()
    assert len(motor.chamadas) == 2
    motor.portoes[1].set()
    assert girar(lambda: o.prontos)


def test_cancelar_chave_desconhecida_e_inofensivo(montar):
    g, _, o = montar()
    g.cancelar("nao-existe")
    girar_um_pouco()
    assert o.prontos == [] and o.falhas == []


def test_falha_do_motor_vira_falhou_e_libera(montar):
    g, motor, o = montar(motor=MotorFalso(erro=RuntimeError("explodiu")))
    k = g.pedir("corte", None, "V1")
    motor.esperar_inicio()
    motor.portoes[0].set()
    assert girar(lambda: o.falhas)
    assert o.falhas[0][0] == k and "explodiu" in o.falhas[0][1]
    assert o.prontos == []
    g.pedir("corte", None, "V1")  # falha nao deixa a vista presa
    motor.esperar_inicio()
    assert len(motor.chamadas) == 2


def test_pedir_volta_rapido_com_motor_lento_e_motor_fora_da_thread_principal(montar):
    g, motor, o = montar()
    t0 = time.perf_counter()
    g.pedir("planta", None, "V1")
    assert time.perf_counter() - t0 < 0.05
    motor.esperar_inicio()
    assert motor.threads[0] is not threading.main_thread()
    girar_um_pouco(50)  # loop segue vivo enquanto o motor segura
    assert o.prontos == []


def test_resultado_so_chega_apos_o_fim_do_calculo(montar):
    g, motor, o = montar()
    k = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    girar_um_pouco(200)
    assert o.prontos == []
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    assert o.prontos[0][0] == k and o.prontos[0][1]["n_paths"] == 1


def test_progresso_do_motor_chega_como_sinal_com_a_chave(montar):
    g, motor, o = montar()
    k = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    assert girar(lambda: o.progressos)
    assert o.progressos[0] == (k, "meio")
    motor.portoes[0].set()
    girar(lambda: o.prontos)


def test_tipo_invalido_levanta_valueerror(montar):
    g, _, _ = montar()
    with pytest.raises(ValueError):
        g.pedir("elevacao", None, "V1")
