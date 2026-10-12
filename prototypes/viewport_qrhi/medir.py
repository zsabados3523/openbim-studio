# SPDX-License-Identifier: AGPL-3.0-or-later
"""Medição da S03-T05 (LOTE_OPUS_4.md §1.6), com tela real. Uma configuração por execução (o pico de
memória é por processo). Uso: python medir.py arquivo.ifc [--threads N] [--bloco N] [--png saida.png]
Imprime uma linha JSON. Roda com QT_QPA_PLATFORM=xcb (ou o padrão do sistema), nunca offscreen."""
import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from viewport_qrhi.carregador import CarregadorMalhas, LoteMalha, ResumoCarga  # noqa: E402
from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402
from viewport_qrhi.processo_malhas import pico_memoria_mb  # noqa: E402,F401  (sem Qt; aceita o id de um filho)


def esperar(cond, limite_s):
    t = time.perf_counter()
    while not cond() and time.perf_counter() - t < limite_s:
        QCoreApplication.processEvents()
    return cond()


def medir(caminho, threads, bloco, png=None, janela=(1280, 720)) -> dict:
    app = QApplication.instance() or QApplication([])
    w = CuboViewport(girar=False)
    w.resize(*janela)
    quadros = []
    w.frameSubmitted.connect(lambda: quadros.append(time.perf_counter()))
    w.show()
    esperar(lambda: quadros, 10)
    if w.rhi() is None:
        raise SystemExit("sem contexto gráfico: rode com tela (QT_QPA_PLATFORM=xcb)")
    w.limpar()
    esperar(lambda: len(quadros) > 2, 2)

    atrasos, ultimo, estado, t_primeiro = [], [0.0], {}, [None]
    loop = QEventLoop()

    def sonda():
        agora = time.perf_counter()
        atrasos.append((agora - ultimo[0]) * 1000.0 - 5.0)
        ultimo[0] = agora

    def consumidor():
        x = car.obter(timeout=0.0)
        if isinstance(x, LoteMalha):
            w.adicionar_lote(x)  # no máximo 1 lote por disparo; o envio à placa é no desenho
            if t_primeiro[0] is None:
                t_primeiro[0] = len(quadros)  # primeiro quadro depois do primeiro lote
        elif isinstance(x, ResumoCarga):
            estado["resumo"] = x
            loop.quit()

    ts, tc = QTimer(), QTimer()
    ts.setTimerType(Qt.PreciseTimer)
    ts.setInterval(5)
    ts.timeout.connect(sonda)
    tc.setInterval(16)
    tc.timeout.connect(consumidor)
    car = CarregadorMalhas(str(caminho), threads=threads, tamanho_bloco=bloco)
    t0 = time.perf_counter()
    ultimo[0] = t0
    marca_primeiro = []
    w.frameSubmitted.connect(lambda: marca_primeiro.append(time.perf_counter())
                             if t_primeiro[0] is not None and not marca_primeiro and len(quadros) > t_primeiro[0] else None)
    ts.start()
    tc.start()
    QTimer.singleShot(0, car.iniciar)  # já dentro do laço de eventos, para a sonda ver o custo de iniciar()
    loop.exec()
    tc.stop()
    car.aguardar(timeout=30.0)
    resumo = estado["resumo"]
    del car
    gc.collect()
    w.enquadrar()
    # último lote enviado à placa e um quadro completo desenhado depois disso
    esperar(lambda: w.estatisticas()["pendentes"] == 0, 120)
    n = len(quadros)
    w.update()
    esperar(lambda: len(quadros) > n, 10)
    t_abrir = time.perf_counter() - t0
    ts.stop()
    atrasos = np.array(atrasos or [0.0])  # todas as amostras, inclusive a primeira (custo de iniciar())
    est = w.estatisticas()
    img = w.grab_image()
    if png:
        img.save(str(png))
    # FPS com o modelo todo: gira a câmera por 3 s, um quadro por vez
    n0, t1 = len(quadros), time.perf_counter()
    while time.perf_counter() - t1 < 3.0:
        w.camera.orbitar(2.0, 0.0)
        w.update()
        QCoreApplication.processEvents()
    fps = (len(quadros) - n0) / (time.perf_counter() - t1)
    w.close()
    return {
        "nucleos": os.cpu_count(), "threads": resumo.threads, "bloco": bloco, "estado": resumo.estado,
        "triangulos": resumo.triangulos, "produtos": resumo.produtos_com_malha, "sem_malha": len(resumo.sem_malha),
        "lotes": est["lotes"], "abrir_s": round(t_abrir, 2),
        "primeiro_lote_visivel_s": round(marca_primeiro[0] - t0, 2) if marca_primeiro else None,
        "carga_s": round(resumo.tempos.get("total_s", 0.0), 2),
        "pico_memoria_mb": round(pico_memoria_mb()), "atraso_max_ms": round(float(atrasos.max()), 1),
        "atraso_p95_ms": round(float(np.percentile(atrasos, 95)), 1), "fps": round(fps, 1),
        "bytes_gpu_mb": round(est["bytes_gpu"] / 2**20),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--bloco", type=int, default=4000)
    ap.add_argument("--png", default=None)
    ap.add_argument("--janela", default="1280x720", help="LxA, ex.: 640x480")
    a = ap.parse_args()
    print(json.dumps(medir(a.arquivo, a.threads, a.bloco, a.png, tuple(int(v) for v in a.janela.split('x')))))
