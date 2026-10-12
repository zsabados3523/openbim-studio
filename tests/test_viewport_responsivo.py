# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S03-T05 (Parte 0), R1 e R2: a janela continua responsiva durante a carga.

Transcrição de docs/state/reports/LOTE_OPUS_4.md §1.5. Congelado: não afrouxar número nem remover caso.
Emendas do lote Opus 5 §1.1 (P0b): todas as amostras de atraso (iniciar() dentro do laço), R2 demonstra o
fenômeno (atraso >= 0,5 x next()) e os números de R1/R2 aparecem sem -s (capsys.disabled + record_property).
R1a roda sem tela (parte A); R1b precisa de tela e dos métodos novos do Viewport (parte B).
R2 é a única falha esperada (xfail, não estrito). Testes lentos (M1M): OBIM_TESTES_LENTOS=1.
"""
import gc
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication

import ifcopenshell
import ifcopenshell.geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes"))

from test_viewport_carregador import (  # noqa: E402,F401  (modelos, M1M e fixtures compartilhados)
    CarregadorMalhas, LoteMalha, ResumoCarga, _m1m_ou_pular, m3000, mab, requer_a,
)
from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402

MAX_MS, P95_MS = 200.0, 33.0
requer_b = pytest.mark.skipif(
    not hasattr(CuboViewport, "adicionar_lote"), reason="aguarda S03-T05 parte B (Viewport.adicionar_lote)"
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _medir(caminho, consumir, **kw):
    """Sonda de 5 ms (preciso) na thread da interface, do iniciar() até o resumo e o carregador destruído.
    Um temporizador de 16 ms tira no máximo 1 lote por disparo. Devolve (atrasos em ms, resumo)."""
    atrasos, ultimo, estado = [], [0.0], {}
    loop = QEventLoop()

    def sonda():
        agora = time.perf_counter()
        atrasos.append((agora - ultimo[0]) * 1000.0 - 5.0)
        ultimo[0] = agora

    def consumidor():
        x = car.obter(timeout=0.0)
        if isinstance(x, LoteMalha):
            consumir(x)
        elif isinstance(x, ResumoCarga):
            estado["resumo"] = x
            loop.quit()

    t_sonda, t_cons = QTimer(), QTimer()
    t_sonda.setTimerType(Qt.PreciseTimer)
    t_sonda.setInterval(5)
    t_sonda.timeout.connect(sonda)
    t_cons.setInterval(16)
    t_cons.timeout.connect(consumidor)
    car = CarregadorMalhas(str(caminho), **kw)
    t_sonda.start()
    t_cons.start()
    # iniciar() roda já dentro do laço de eventos, com a sonda ligada: o custo dele entra na primeira amostra
    QTimer.singleShot(0, car.iniciar)
    ultimo[0] = time.perf_counter()
    loop.exec()
    t_cons.stop()
    car.aguardar(timeout=30.0)
    del car  # a destruição faz parte da janela de medição
    gc.collect()
    fim = time.perf_counter() + 0.1
    while time.perf_counter() < fim:  # deixa a sonda registrar qualquer parada da destruição
        QCoreApplication.processEvents()
    t_sonda.stop()
    return np.array(atrasos or [0.0]), estado["resumo"]  # todas as amostras, inclusive a primeira


def _publicar(capsys, record_property, chave, texto):
    """Mostra o número no terminal mesmo sem -s e o grava no relatório do pytest."""
    record_property(chave, texto)
    with capsys.disabled():
        print(f"\n[{chave}] {texto}")


def _conferir(atrasos, resumo, rotulo, capsys, record_property):
    p95 = float(np.percentile(atrasos, 95))
    texto = f"{rotulo}: atraso max={atrasos.max():.1f} ms, p95={p95:.1f} ms, amostras={len(atrasos)}"
    _publicar(capsys, record_property, rotulo, texto)
    assert resumo.estado == "concluido"
    assert atrasos.max() <= MAX_MS, f"atraso máximo {atrasos.max():.1f} ms > {MAX_MS} ms"
    assert p95 <= P95_MS, f"percentil 95 {p95:.1f} ms > {P95_MS} ms"


@requer_a
def test_r1a_janela_responsiva_m3000_sem_viewport(app, m3000, capsys, record_property):
    lista = []
    atrasos, resumo = _medir(m3000, lista.append, tamanho_bloco=4000)
    assert resumo.triangulos == 36000
    _conferir(atrasos, resumo, "R1a M3000", capsys, record_property)


@requer_a
def test_r1a_janela_responsiva_m1m_lento(app, capsys, record_property):
    caminho = _m1m_ou_pular()
    lista = []
    atrasos, resumo = _medir(caminho, lista.append, tamanho_bloco=4000)
    _conferir(atrasos, resumo, "R1a M1M", capsys, record_property)


def _viewport_visivel(app):
    w = CuboViewport(girar=False)
    w.resize(640, 480)
    quadros = []
    w.frameSubmitted.connect(lambda: quadros.append(1))
    w.show()
    t = QElapsedTimer()
    t.start()
    while not quadros and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    if w.rhi() is None or not quadros:
        w.close()
        pytest.skip("R1b precisa de tela (sem contexto gráfico; rode com QT_QPA_PLATFORM=xcb)")
    return w


@requer_a
@requer_b
@pytest.mark.parametrize("lento", [False, True], ids=["m3000", "m1m_lento"])
def test_r1b_janela_responsiva_com_viewport(app, m3000, lento, capsys, record_property):
    caminho = _m1m_ou_pular() if lento else m3000
    w = _viewport_visivel(app)
    atrasos, resumo = _medir(caminho, w.adicionar_lote, tamanho_bloco=4000)  # o tempo gasto em adicionar_lote conta
    w.enquadrar()
    w.close()
    _conferir(atrasos, resumo, "R1b " + ("M1M" if lento else "M3000"), capsys, record_property)


@pytest.fixture(scope="module")
def r2_medida(app, mab):
    if CarregadorMalhas is None:
        pytest.skip("aguarda S03-T05 parte A (CarregadorMalhas, LoteMalha, ResumoCarga)")
    f = ifcopenshell.open(str(mab))
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    s.set("weld-vertices", False)
    it, maior_next = ifcopenshell.geom.iterator(s, f, 1), 0.0
    if it.initialize():
        while True:
            t = time.perf_counter()
            continua = it.next()
            maior_next = max(maior_next, time.perf_counter() - t)
            if not continua:
                break
    del it
    atrasos, resumo = _medir(mab, lambda lote: None, tamanho_bloco=4000)
    return atrasos, resumo, maior_next


def _r2_texto(atrasos, maior_next):
    return f"atraso max={atrasos.max():.1f} ms; next() mais longo={maior_next * 1000:.1f} ms"


def test_r2_carga_termina_certa(r2_medida):
    atrasos, resumo, _ = r2_medida
    assert resumo.estado == "concluido" and resumo.produtos_com_malha == 21 and resumo.sem_malha == []


def test_r2_demonstra_o_fenomeno_do_gil(r2_medida, capsys, record_property):
    """Passa hoje: next() segura o GIL, então a janela para por quase o tempo do elemento lento.
    Se a S04 resolver o GIL, este teste FALHA e avisa (aí remover o xfail do teste de 200 ms)."""
    atrasos, _, maior_next = r2_medida
    _publicar(capsys, record_property, "R2", _r2_texto(atrasos, maior_next))
    assert atrasos.max() >= 0.5 * maior_next * 1000.0, (
        f"o fenômeno sumiu (GIL resolvido?): {_r2_texto(atrasos, maior_next)}; revisar o xfail de R2"
    )


@pytest.mark.xfail(strict=False, reason="R1 do lote Opus 4: next() segura o GIL")
def test_r2_atraso_maximo_com_elemento_lento(r2_medida):
    atrasos, _, maior_next = r2_medida
    assert atrasos.max() <= MAX_MS, f"atraso {atrasos.max():.1f} ms (next() mais longo {maior_next * 1000:.1f} ms)"
