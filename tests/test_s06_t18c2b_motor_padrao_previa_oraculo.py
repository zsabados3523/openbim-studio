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
    (Parte 2b: motor padrao e ponta a ponta; a parte 2a testa o gerente com motor injetado.)"""
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



# ---------- _motor_padrao ----------

class Planta:
    def __init__(self, pesados=(), svg="<svg>sil</svg>"):
        self.svg, self.n_paths = svg, 3
        self.tempos = {"x": 0.1}
        self.caixas = [(0, 0, 1, 1)]
        self.em_cache = ["a"]
        self.pesados = tuple(pesados)
        self.pedido = {"op": "desenho"}


PESADOS = [{"guid": "G1", "id": 11, "faces": 5000}]


@pytest.fixture
def falsos(monkeypatch):
    from openbim_app.desenho import planta as pmod
    from openbim_app.desenho import refino as rmod
    est = SimpleNamespace(gerar=[], refino=[], planta=Planta(PESADOS), cancela=False)

    def gerar_planta(ifc, guid, **kw):
        est.gerar.append((ifc, guid, kw))
        return est.planta

    def refinar(ifc, pedido, dados, **kw):
        est.refino.append((ifc, pedido, dados, kw))
        if est.cancela:
            raise DesenhoCancelado("cancelado")
        return {**dados, "svg": "<svg>exato</svg>", "refinadas": ["G1"], "falhas_refino": []}

    monkeypatch.setattr(pmod, "gerar_planta", gerar_planta)
    monkeypatch.setattr(rmod, "refinar_pesados", refinar)
    return est


def chamar_padrao(tipo="planta", opcoes=None, previas=None, cache="CACHE"):
    ev = threading.Event()
    prog = []
    previas = [] if previas is None else previas
    r = gmod._motor_padrao(tipo, "IFC", "V1", dict(opcoes or {}), cancelar=ev,
                           progresso=prog.append, cache=cache, previa=previas.append)
    return r, previas, ev, prog


def test_padrao_planta_com_pesados_faz_previa_e_refino(falsos):
    r, previas, ev, prog = chamar_padrao()
    ifc, guid, kw = falsos.gerar[0]
    assert ifc == "IFC" and guid == "V1" and kw["pesados"] == "silhueta"
    assert len(previas) == 1
    p = previas[0]
    for chave in ("svg", "n_paths", "tempos", "caixas", "em_cache", "pesados"):
        assert chave in p
    assert p["svg"] == "<svg>sil</svg>" and p["pesados"] == PESADOS
    assert all(isinstance(d, dict) for d in p["pesados"])
    assert len(falsos.refino) == 1
    ifc2, pedido, dados, kw2 = falsos.refino[0]
    assert ifc2 == "IFC" and pedido == {"op": "desenho"} and dados["svg"] == "<svg>sil</svg>"
    assert kw2["cache"] == "CACHE" and kw2["cancelar"] is ev and callable(kw2["progresso"])
    assert r["svg"] == "<svg>exato</svg>" and r["refinadas"] == ["G1"] and r["falhas_refino"] == []


def test_padrao_opcao_pesados_do_chamador_prevalece(falsos):
    chamar_padrao(opcoes={"pesados": None, "ocultar": True})
    kw = falsos.gerar[0][2]
    assert kw["pesados"] is None and kw["ocultar"] is True


def test_padrao_sem_pesados_nao_chama_previa_nem_refino(falsos):
    falsos.planta = Planta(())
    r, previas, _, _ = chamar_padrao()
    assert previas == [] and falsos.refino == []
    assert r["svg"] == "<svg>sil</svg>" and r["pesados"] == []
    for chave in ("n_paths", "tempos", "caixas", "em_cache"):
        assert chave in r


def test_padrao_corte_nao_passa_pesados_nem_previa(falsos, monkeypatch):
    from openbim_app.desenho import corte as cmod
    vistos = []

    def gerar_corte(ifc, guid, **kw):
        vistos.append(kw)
        return Planta(PESADOS, svg="<svg>corte</svg>")

    monkeypatch.setattr(cmod, "gerar_corte", gerar_corte)
    r, previas, _, _ = chamar_padrao(tipo="corte")
    assert "pesados" not in vistos[0]
    assert previas == [] and falsos.refino == [] and falsos.gerar == []
    assert r["svg"] == "<svg>corte</svg>"


def test_padrao_cancelado_no_refino_propaga(falsos):
    falsos.cancela = True
    previas = []
    with pytest.raises(DesenhoCancelado):
        chamar_padrao(previas=previas)
    assert len(previas) == 1  # previa saiu antes; o pedido cancelado a descarta no gerente


# ---------- ponta a ponta (motor padrao + gerente padrao) ----------

def test_ponta_a_ponta_previa_silhueta_e_pronto_exato(app, falsos):
    g = GerenteDesenho(CacheFalso())
    o = Ouvinte(g)
    try:
        k = g.pedir("planta", "IFC", "V1")
        assert girar(lambda: o.prontos, 5000)
        girar_um_pouco()
        assert [e[0] for e in o.eventos] == ["previa", "pronto"]
        assert o.prevs[0][0] == k and o.prontos[0][0] == k
        assert o.prevs[0][1]["svg"] == "<svg>sil</svg>"
        assert o.prontos[0][1]["svg"] == "<svg>exato</svg>"
        assert o.falhas == []
        assert o.thread_previa[0] is threading.main_thread()
    finally:
        g.encerrar()


def test_ponta_a_ponta_cancelado_no_refino_nao_emite_pronto_nem_falhou(app, falsos):
    falsos.cancela = True
    g = GerenteDesenho(CacheFalso())
    o = Ouvinte(g)
    try:
        g.pedir("planta", "IFC", "V1")
        girar_um_pouco(500)
        assert o.prontos == [] and o.falhas == []
    finally:
        g.encerrar()
