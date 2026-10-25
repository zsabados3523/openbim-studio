# SPDX-License-Identifier: AGPL-3.0-or-later
"""Medição do carregador de malhas, com tela real. Uma configuração por execução (o pico de
memória é por processo). Uso: python medir.py arquivo.ifc [--threads N] [--bloco N] [--png saida.png]
Imprime uma linha JSON. Roda com QT_QPA_PLATFORM=xcb (ou o padrão do sistema), nunca offscreen."""
import argparse
import gc
import json
import locale
import multiprocessing
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from viewport_qrhi.carregador import CarregadorMalhas, LoteMalha, ResumoCarga  # noqa: E402
from viewport_qrhi.processo_malhas import pico_memoria_mb  # noqa: E402,F401  (sem Qt; aceita o id de um filho)


def esperar(cond, limite_s):
    from PySide6.QtCore import QCoreApplication  # Qt só dentro das funções: o filho (spawn) reimporta este módulo
    t = time.perf_counter()
    while not cond() and time.perf_counter() - t < limite_s:
        QCoreApplication.processEvents()
    return cond()


def _rss_mb(pid) -> float:
    """Memória residente atual (Linux, /proc). Fora do Linux devolve 0 (a soma amostrada é só informativa)."""
    try:
        with open(f"/proc/{pid}/status") as a:
            for linha in a:
                if linha.startswith("VmRSS:"):
                    return int(linha.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def _filhos_vivos() -> list:
    return [p for p in multiprocessing.active_children() if p.pid]


def medir_cancelamento(caminho, apos_s, biblioteca=None) -> dict:
    """Cancela a carga depois de `apos_s` e confere se sobrou processo filho (meta: nenhum)."""
    kw = {"biblioteca": biblioteca} if biblioteca else {}
    car = CarregadorMalhas(str(caminho), **kw)
    car.iniciar()
    time.sleep(apos_s)
    vivos_antes = len(_filhos_vivos())
    t = time.perf_counter()
    car.cancelar()
    car.aguardar(timeout=60.0)
    ate = t + 30.0
    while _filhos_vivos() and time.perf_counter() < ate:
        time.sleep(0.1)
    return {"cancelamento": True, "filhos_vivos_antes": vivos_antes, "filhos_sobrando": len(_filhos_vivos()),
            "cancelar_s": round(time.perf_counter() - t, 2)}


def medir(caminho, threads, bloco, png=None, janela=(1280, 720), biblioteca=None) -> dict:
    from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer
    from PySide6.QtGui import QRhiDriverInfo
    from PySide6.QtWidgets import QApplication

    from viewport_qrhi.cubo_rhi import CuboViewport
    app = QApplication.instance() or QApplication([])
    locale.setlocale(locale.LC_NUMERIC, "C")  # o Qt troca a localidade numérica e o IfcOpenShell grava vírgula decimal
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
    kw = {"biblioteca": biblioteca} if biblioteca else {}
    car = CarregadorMalhas(str(caminho), threads=threads, tamanho_bloco=bloco, **kw)
    soma_max = [0.0]

    def amostrar():  # número só informativo: pai + filhos vivos, a cada 0,25 s
        soma_max[0] = max(soma_max[0], _rss_mb(os.getpid()) + sum(_rss_mb(p.pid) for p in _filhos_vivos()))

    ta = QTimer()
    ta.setInterval(250)
    ta.timeout.connect(amostrar)
    ta.start()
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
    ta.stop()
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
    rhi = w.rhi()  # qual desenho rodou (lido antes de fechar a janela)
    di = rhi.driverInfo()
    desenho = {"info": f"{rhi.backendName()} {bytes(di.deviceName).decode(errors='replace')}",
               "software": di.deviceType == QRhiDriverInfo.DeviceType.CpuDevice}
    w.close()
    pico_pai = pico_memoria_mb()
    pico_filho = float(resumo.pico_filho_mb)
    filho_rusage = None
    if sys.platform != "win32":
        import resource  # conferência no Linux: maior pico entre filhos já finalizados
        filho_rusage = round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / (2**20 if sys.platform == "darwin" else 1024.0))  # bytes no macOS
    simp = list(resumo.simplificadas)
    return {
        "pico_pai_mb": round(pico_pai), "pico_filho_mb": round(pico_filho),
        "pico_somado_mb": round(pico_pai + pico_filho),  # META D5: pico do pai + maior pico entre os filhos
        "pico_filho_rusage_mb": filho_rusage, "soma_amostrada_max_mb": round(soma_max[0]),
        "simplificadas": {"quantidade": len(simp), "lista": [list(map(str, x)) for x in simp[:5]]},
        "pecas_com_malha": resumo.produtos_com_malha, "pecas_sem_malha": len(resumo.sem_malha),
        "biblioteca": biblioteca or "padrao", "filhos_sobrando": len(_filhos_vivos()),
        "nucleos": os.cpu_count(), "threads": resumo.threads, "bloco": bloco, "estado": resumo.estado,
        "triangulos": resumo.triangulos, "produtos": resumo.produtos_com_malha, "sem_malha": len(resumo.sem_malha),
        "lotes": est["lotes"], "abrir_s": round(t_abrir, 2),
        "primeiro_lote_visivel_s": round(marca_primeiro[0] - t0, 2) if marca_primeiro else None,
        "carga_s": round(resumo.tempos.get("total_s", 0.0), 2),
        "pico_memoria_mb": round(pico_memoria_mb()), "atraso_max_ms": round(float(atrasos.max()), 1),
        "atraso_p95_ms": round(float(np.percentile(atrasos, 95)), 1), "fps": round(fps, 1),
        "bytes_gpu_mb": round(est["bytes_gpu"] / 2**20),
        "reinicios": list(resumo.reinicios), "registro_reinicio": list(resumo.registro_reinicio), "desenho": desenho,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--bloco", type=int, default=1000)
    ap.add_argument("--png", default=None)
    ap.add_argument("--biblioteca", default=None, help="ex.: opencascade (padrão: híbrida)")
    ap.add_argument("--cancelar-apos", type=float, default=None, help="só mede o cancelamento (sem tela), em segundos")
    ap.add_argument("--janela", default="1280x720", help="LxA, ex.: 640x480")
    a = ap.parse_args()
    if a.cancelar_apos is not None:
        print(json.dumps(medir_cancelamento(a.arquivo, a.cancelar_apos, a.biblioteca)))
    else:
        print(json.dumps(medir(a.arquivo, a.threads, a.bloco, a.png, tuple(int(v) for v in a.janela.split('x')),
                               a.biblioteca)))
