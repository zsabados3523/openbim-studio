# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19h2 (leve): pre-aquecer o filho persistente. Nao editar nesta tarefa.

Contrato: ver cartao. (a) `servir` op "abrir"; (b) `FilhoPersistente.aquecer`; (c) `GerenteDesenho.aquecer`; (d) filho ligado por padrao.
IFC minimo gerado em tmp, sem cena pesada; o filho real so roda `servir` com `ifcopenshell.open` contado."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import ifcopenshell
import pytest
from test_s06_t19g4a_persistente_oraculo import FakeRx, FakeTx, _espiar

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def ifc(tmp_path):
    f = ifcopenshell.file(schema="IFC4")
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="P")
    p = tmp_path / "m.ifc"
    f.write(str(p))
    return str(p)


def _alvo_conta(tx, rx):
    """Filho de teste (spawn): `servir` real, abertura contada em OBIM_H2_LOG, `caixas` trivial."""
    import ifcopenshell as ios
    from obim_geometria import caixas, persistente

    orig = ios.open

    def aberto(*a, **k):
        with open(os.environ["OBIM_H2_LOG"], "a") as g:
            g.write("x\n")
        return orig(*a, **k)

    ios.open = aberto
    caixas.processar = lambda pedido, f=None: {"ok": True}
    persistente.servir(tx, rx)


# ------------------------------------------------------------------ (a) servir
def test_servir_op_abrir_abre_e_responde(ifc, monkeypatch):
    from obim_geometria import persistente

    abertos = _espiar(monkeypatch)
    rx = FakeRx([{"op": "abrir", "numero": 1, "arquivo": ifc}, {"op": "xyz", "numero": 2, "arquivo": ifc}])
    tx = FakeTx(abertos)
    persistente.servir(tx, rx)
    r1, r2 = (m["dados"] for m in tx.respostas)
    assert r1 == {"aberto": True}
    assert [a[0] for a in abertos] == [ifc]
    assert r2["ok"] is False and r2["erro"]["tipo"] == "OperacaoDesconhecida"


# ------------------------------------------------------------------ (b) FilhoPersistente.aquecer
def test_aquecer_abre_e_pedido_seguinte_nao_reabre(ifc, tmp_path, monkeypatch):
    from openbim_app.desenho.filho import FilhoPersistente

    log = tmp_path / "aberturas.log"
    monkeypatch.setenv("OBIM_H2_LOG", str(log))
    f = FilhoPersistente(ifc, alvo=_alvo_conta)
    try:
        f.aquecer()
        assert log.read_text().count("x") == 1 and f.pid is not None
        pid = f.pid
        r = f.executar({"op": "caixas", "protocolo": 1, "arquivo": ifc, "elementos": []})
        assert r["ok"] and f.pid == pid
        assert log.read_text().count("x") == 1  # reaproveitou o aberto
    finally:
        f.fechar()


def test_aquecer_respeita_a_trava(ifc):
    from openbim_app.desenho.filho import FilhoPersistente

    f = FilhoPersistente(ifc, alvo=_alvo_conta)
    def alvo():
        try:
            f.aquecer(limite_s=5)
        except Exception:  # fechado depois da espera: valido
            pass

    t = threading.Thread(target=alvo, daemon=True)
    with f._trava:  # pedido em voo: aquecer espera, nunca roda em paralelo
        t.start()
        t.join(0.4)
        assert t.is_alive() and f.pid is None
    f.fechar()  # fechar pega a trava depois; aquecer acaba sem travar o teste
    t.join(10)
    assert not t.is_alive()


# ------------------------------------------------------------------ (c)/(d) gerente
@pytest.fixture
def G(monkeypatch):
    pytest.importorskip("PySide6.QtCore")
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.instance() or QCoreApplication([])
    from openbim_app.desenho import filho as F
    from openbim_app.desenho import gerente

    gerente.F = F  # atalho para os testes
    return gerente


def _espia(mp, G, efeito=None):
    """Troca `FilhoPersistente.aquecer` por um espiao que bloqueia ate `solta` e depois levanta `efeito`."""
    e = type("E", (), {})()
    e.chamadas, e.threads, e.excecoes, e.efeito = [], [], [], efeito
    e.inicio, e.solta = threading.Event(), threading.Event()

    def aquecer(filho, *a, **k):
        e.chamadas.append(filho)
        e.threads.append(threading.current_thread())
        e.inicio.set()
        e.solta.wait(5)
        if e.efeito:
            raise e.efeito

    mp.setattr(G.F.FilhoPersistente, "aquecer", aquecer, raising=False)
    mp.setattr(threading, "excepthook", lambda a: e.excecoes.append(a.exc_value))
    return e


@pytest.mark.parametrize("caso", ["revisao_suja", "sem_arquivo", "desligado", "sem_revisao"])
def test_gerente_gate_fechado_nao_aquece(G, ifc, tmp_path, monkeypatch, caso):
    e = _espia(monkeypatch, G)
    g = G.GerenteDesenho(filho_persistente=caso != "desligado")
    arq = ifc if caso != "sem_arquivo" else str(tmp_path / "nao_existe.ifc")
    rev, salva = {"revisao_suja": (2, 1), "sem_revisao": (None, 1)}.get(caso, (1, 1))
    antes = threading.active_count()
    g.aquecer(arq, revisao=rev, revisao_salva=salva)
    e.inicio.wait(0.3)
    assert not e.chamadas and not g._filhos_doc and threading.active_count() == antes
    g.fechar()


@pytest.mark.parametrize("efeito", ["nada", "indisponivel", "cancelado"])
def test_gerente_gate_aberto_aquece_em_thread_e_engole_erro(G, ifc, monkeypatch, efeito):
    from openbim_app.desenho.auxiliar import DesenhoCancelado

    e = _espia(monkeypatch, G, {"nada": None, "indisponivel": G.F.FilhoIndisponivel("x"), "cancelado": DesenhoCancelado("c")}[efeito])
    g = G.GerenteDesenho(filho_persistente=True)
    g.aquecer(ifc, revisao=1, revisao_salva=1)
    assert e.inicio.wait(5) and e.threads[0] is not threading.main_thread() and e.threads[0].daemon
    assert g._filhos_doc.get(Path(ifc).resolve()) is e.chamadas[0]  # mesmo filho que o pedir usaria
    e.solta.set()
    e.threads[0].join(5)
    assert not e.excecoes
    g.fechar()


def test_gerente_invalidar_durante_aquecimento_sem_excecao(G, ifc, monkeypatch):
    e = _espia(monkeypatch, G, G.F.FilhoIndisponivel("fechado"))
    g = G.GerenteDesenho(filho_persistente=True)
    g.aquecer(ifc, revisao=1, revisao_salva=1)
    assert e.inicio.wait(5)
    g.invalidar()
    g.salvar()
    e.solta.set()
    e.threads[0].join(5)
    assert not e.excecoes and not e.threads[0].is_alive()
    g.fechar()


@pytest.mark.parametrize("kw,esperado", [({}, True), ({"filho_persistente": False}, False)])
def test_filho_persistente_ligado_por_padrao(G, ifc, kw, esperado):
    vistos, feito = [], threading.Event()

    def motor(tipo, ifc_, guid, opcoes, *, cancelar, progresso, **extra):
        vistos.append(extra.get("filho"))
        feito.set()
        return {"svg": ""}

    g = G.GerenteDesenho(motor=motor, **kw)
    g.pedir("corte", object(), "v1", caminho_ifc=ifc, revisao=1, revisao_salva=1)
    assert feito.wait(5)
    g.fechar()
    assert (vistos[0] is not None) is esperado
