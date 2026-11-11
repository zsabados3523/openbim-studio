# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo T18c-2: GerenteDesenho com previa (silhueta rapida) e refino exato em segundo plano.

CONTRATO (app/openbim_app/desenho/gerente.py):
 1. Novo sinal previa(str chave, object dados).
 2. O motor injetado pode aceitar o kwarg `previa` (callable(dados), chamavel da thread de fundo).
    O gerente so passa `previa=` se a assinatura do motor aceitar (param `previa` ou **kw);
    motores do T16 (sem previa) seguem funcionando.
 3. previa(d) no motor => sinal previa(chave, d) na thread principal, ANTES do pronto do mesmo pedido;
    nao libera a vista, nao cancela, nao vai ao cache; o pronto final vai ao cache.
 4. Pedido cancelado (cancelar ou novo pedido da mesma vista): previa emitida depois e descartada.
 5. Motor que nao chama previa => so pronto.
 6. _motor_padrao(tipo, ifc, guid, opcoes, *, cancelar, progresso, cache, previa=None):
    planta => gerar_planta(..., pesados='silhueta') (opcoes do chamador prevalecem); devolve dict de
    hoje + 'pesados'; se pesados nao vazio: previa(dados_rapidos) e depois
    refino.refinar_pesados(ifc, r.pedido, dados_rapidos, cache=, cancelar=, progresso=) -> dict refinado.
    Sem pesados: nem previa nem refino. Corte: sem pesados e sem previa. DesenhoCancelado propaga."""
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app.desenho.auxiliar import DesenhoCancelado  # noqa: E402
from openbim_app.desenho import gerente as gmod  # noqa: E402
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


class MotorPrevia:
    """Aceita `previa`. Roteiro por chamada: emite previas, espera o portao, devolve o final.
    `antes` = lista de dados a enviar por previa antes de esperar; `depois` = idem apos o portao."""

    def __init__(self, antes=({"svg": "<svg>sil</svg>"},), depois=()):
        self.antes, self.depois = list(antes), list(depois)
        self.chamadas, self.portoes, self.cancelamentos = [], [], []
        self.iniciou = threading.Semaphore(0)
        self.kwargs = []
        self.threads_previa = []

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, previa=None):
        portao = threading.Event()
        self.portoes.append(portao)
        self.chamadas.append((tipo, guid, dict(opcoes)))
        self.cancelamentos.append(cancelar)
        for d in self.antes:
            previa(d)
        self.iniciou.release()
        fim = time.monotonic() + 4
        while not portao.is_set():
            if time.monotonic() > fim:
                raise TimeoutError("teste esqueceu de liberar o motor")
            time.sleep(0.005)
        for d in self.depois:
            previa(d)
        return {"svg": f"<svg>exato{guid}</svg>", "n_paths": 7}

    def esperar_inicio(self, n=1):
        for _ in range(n):
            assert self.iniciou.acquire(timeout=3)


class MotorSemPrevia:
    """Motor antigo (T16): se o gerente passar `previa=`, levanta TypeError."""

    def __init__(self):
        self.chamadas = 0

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso):
        self.chamadas += 1
        return {"svg": "<svg>velho</svg>", "n_paths": 1}


class MotorKw:
    def __init__(self):
        self.recebido = None

    def __call__(self, tipo, ifc, guid, opcoes, **kw):
        self.recebido = kw
        if "previa" in kw:
            kw["previa"]({"svg": "<svg>kw</svg>"})
        return {"svg": "<svg>fim</svg>", "n_paths": 1}


def girar(cond, ms=3000):
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
        self.eventos = []  # ordem global: ("previa"|"pronto"|"falhou", chave, dados)
        self.prevs, self.prontos, self.falhas = [], [], []
        self.thread_previa = []
        g.previa.connect(self._previa)
        g.pronto.connect(self._pronto)
        g.falhou.connect(lambda c, m: (self.falhas.append((c, m)), self.eventos.append(("falhou", c, m))))

    def _previa(self, c, d):
        self.thread_previa.append(threading.current_thread())
        self.prevs.append((c, d))
        self.eventos.append(("previa", c, d))

    def _pronto(self, c, d):
        self.prontos.append((c, d))
        self.eventos.append(("pronto", c, d))


@pytest.fixture
def montar(app):
    criados = []

    def f(cache=None, motor=None, **kw):
        motor = motor or MotorPrevia()
        g = GerenteDesenho(cache if cache is not None else CacheFalso(), motor=motor,
                           chave_estado=chave_estado, **kw)
        criados.append((g, motor))
        return g, motor, Ouvinte(g)

    yield f
    for g, motor in criados:
        for p in getattr(motor, "portoes", []):
            p.set()
        g.encerrar()


# ---------- sinal e ordem ----------

def test_previa_chega_na_thread_principal_antes_do_pronto(montar):
    g, motor, o = montar()
    k = g.pedir("planta", None, "V1")
    assert girar(lambda: o.prevs)
    assert o.prevs == [(k, {"svg": "<svg>sil</svg>"})]
    assert o.thread_previa[0] is threading.main_thread()
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    assert [e[0] for e in o.eventos] == ["previa", "pronto"]
    assert o.prontos[0] == (k, {"svg": "<svg>exatoV1</svg>", "n_paths": 7})


def test_previa_nao_libera_a_vista_nem_cancela(montar):
    g, motor, o = montar()
    k1 = g.pedir("planta", None, "V1")
    assert girar(lambda: o.prevs)
    k2 = g.pedir("planta", None, "V1")  # mesmo estado: continua o mesmo pedido ativo
    assert k1 == k2
    girar_um_pouco(100)
    assert len(motor.chamadas) == 1
    assert not motor.cancelamentos[0].is_set()
    assert o.prontos == [] and o.falhas == []  # pronto ainda nao chegou
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    girar_um_pouco()
    assert len(o.prontos) == 1 and len(motor.chamadas) == 1


def test_varias_previas_chegam_em_ordem(montar):
    m = MotorPrevia(antes=[{"svg": "a"}, {"svg": "b"}], depois=[])
    g, motor, o = montar(motor=m)
    g.pedir("planta", None, "V1")
    assert girar(lambda: len(o.prevs) == 2)
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    assert [d["svg"] for _, d in o.prevs] == ["a", "b"]
    assert [e[0] for e in o.eventos] == ["previa", "previa", "pronto"]


def test_previa_nao_vai_ao_cache_e_o_pronto_vai(montar):
    cache = CacheFalso()
    g, motor, o = montar(cache=cache)
    k = g.pedir("planta", None, "V1")
    assert girar(lambda: o.prevs)
    assert cache.guardados == [] and cache.dados == {}
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    assert cache.guardados == [k]
    assert cache.dados[k]["n_paths"] == 7  # o exato, nao a silhueta


def test_motor_que_nao_chama_previa_so_emite_pronto(montar):
    m = MotorPrevia(antes=[])
    g, motor, o = montar(motor=m)
    k = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    motor.portoes[0].set()
    assert girar(lambda: o.prontos)
    girar_um_pouco()
    assert o.prevs == [] and [e[0] for e in o.eventos] == ["pronto"]
    assert o.prontos[0][0] == k


# ---------- compatibilidade de assinatura ----------

def test_motor_antigo_sem_previa_funciona_sem_kwarg(montar):
    m = MotorSemPrevia()
    g, _, o = montar(motor=m)
    g.pedir("corte", None, "V1")
    assert girar(lambda: o.prontos)
    assert o.falhas == [] and o.prevs == [] and m.chamadas == 1


def test_motor_com_kwargs_recebe_previa(montar):
    m = MotorKw()
    g, _, o = montar(motor=m)
    g.pedir("planta", None, "V1")
    assert girar(lambda: o.prontos)
    assert callable(m.recebido.get("previa"))
    assert "cancelar" in m.recebido and "progresso" in m.recebido
    assert o.prevs and o.prevs[0][1] == {"svg": "<svg>kw</svg>"}


# ---------- cancelamento ----------

def test_previa_depois_de_cancelar_e_descartada(montar):
    m = MotorPrevia(antes=[], depois=[{"svg": "velha"}])
    g, motor, o = montar(motor=m)
    k = g.pedir("planta", None, "V1")
    motor.esperar_inicio()
    g.cancelar(k)
    motor.portoes[0].set()  # motor termina "com resultado" e ainda chama previa
    girar_um_pouco(300)
    assert o.prevs == [] and o.prontos == [] and o.falhas == []


def test_previa_do_pedido_velho_nao_aparece_apos_novo_pedido_da_vista(montar):
    m = MotorPrevia(antes=[], depois=[{"svg": "velha"}])
    g, motor, o = montar(motor=m)
    k1 = g.pedir("planta", None, "V1", ocultar=False)
    motor.esperar_inicio()
    k2 = g.pedir("planta", None, "V1", ocultar=True)
    assert k1 != k2
    motor.esperar_inicio()
    motor.portoes[0].set()  # velho chama previa depois de substituido
    girar_um_pouco(300)
    assert o.prevs == [] and o.prontos == []
    motor.portoes[1].set()  # novo emite previa e pronto normalmente
    assert girar(lambda: o.prontos)
    assert [c for c, _ in o.prontos] == [k2]
    assert all(c == k2 for c, _ in o.prevs)
    assert not any(c == k1 for c, _ in o.prevs)


def test_previa_nao_cancela_vistas_diferentes(montar):
    g, motor, o = montar()
    ka = g.pedir("planta", None, "A")
    kb = g.pedir("planta", None, "B")
    assert girar(lambda: len(o.prevs) == 2)
    assert {c for c, _ in o.prevs} == {ka, kb}
    assert not any(c.is_set() for c in motor.cancelamentos)
