# SPDX-License-Identifier: AGPL-3.0-or-later
"""F0-S04-T15b: lote longo em thread Python (forma 1) e lote fatiado na thread da janela (forma 2), LOTE_OPUS_9 §2.3. Mede M5 (quadros do núcleo) e M5b (mouse sintético).
Contrato em CONTRATO.md (seção T15) e no oráculo tests/test_s04_t15b_formas.py. Medir, não otimizar: nenhuma chamada da API é partida (só os blocos de `malhas`).
Importar este módulo não cria QApplication nem importa o obimcore. Uso: `python lote.py <saida.json> [--base 300] [--quantidade 1000] [--rodadas 3]`."""
import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import fluxo_a
import numpy as np

TIPO = {"cmd": "criar_tipo", "nome": "PAR15", "camadas_m": [0.02, 0.11, 0.02]}
FATIA_MS, PULSO_MS, MOUSE_MS, PARADO_MS = 8, 10, 20, 2000
BLOCO_MALHAS = 25  # GlobalIds por chamada de `obimcore.malhas` na forma 2 (a única chamada que se parte; as da API do IfcOpenShell nunca)
Y_MOUSE = -777.0  # marca dos eventos sintéticos (a posição x leva o índice k)


def lote_cmd(n):  # o `criar_paredes_lote` do passo 5b do roteiro R
    return {"cmd": "criar_paredes_lote", "quantidade": int(n), "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15}


def _caminhos():  # para `python lote.py` direto: pastas de que o fluxo A precisa (app, formato_malha, scripts); com o oráculo já estão no caminho
    raiz = Path(__file__).resolve().parents[3]
    for p in (raiz / "scripts", raiz / "prototypes", raiz / "app"):
        str(p) in sys.path or sys.path.insert(0, str(p))


def preparar(caminho_base, saida):  # uma QApplication por processo: preparar uma vez
    f = fluxo_a.FluxoA(caminho_base, janela=True, saida=saida)
    for c in ({"cmd": "abrir"}, TIPO, {"cmd": "enquadrar"}, {"cmd": "esperar", "ms": 500}, {"cmd": "animar_orbita", "graus_por_s": 30}):
        f.executar(c)
    return f


class _Fatiador:  # forma 2: cede ao Qt depois de cada operação se passaram >= FATIA_MS desde a última cessão
    def __init__(s, processar):
        s.processar, s.fatias, s.ini, s.maior = processar, [], time.perf_counter(), (0.0, "")

    def op(s, nome, fn, *a, **k):
        t = time.perf_counter()
        r = fn(*a, **k)
        t2 = time.perf_counter()
        (t2 - t) * 1000 > s.maior[0] and setattr(s, "maior", ((t2 - t) * 1000, nome))
        if (t2 - s.ini) * 1000 >= FATIA_MS:
            s.fechar(t2)
            s.processar()
            s.ini, s.maior = time.perf_counter(), (0.0, "")
        return r

    def fechar(s, t=None):  # fecha a fatia em andamento (da última cessão até `t`)
        s.fatias.append({"ms": ((t or time.perf_counter()) - s.ini) * 1000, "op_mais_longa": s.maior[1] or "(sem operação)"})


class _CenaFatiada:  # no lugar de `f.cena`: só `atualizar` é operação; o resto vai direto à Cena
    def __init__(s, cena, fat):
        s._cena, s._fat = cena, fat

    def atualizar(s, *a, **k):
        return s._fat.op("Cena.atualizar", s._cena.atualizar, *a, **k)

    def __getattr__(s, nome):
        return getattr(s._cena, nome)


def _forma_1(f, cmd):  # o comando numa threading.Thread; a thread da janela fica em QEventLoop.exec() até ela terminar
    from PySide6.QtCore import QEventLoop, QTimer
    est = {}

    def corre():
        est["thread"] = threading.get_ident()
        try:
            est["ret"] = f.executar_detalhado(cmd)
        except BaseException as e:
            est["erro"] = e
    th, loop, tm = threading.Thread(target=corre, name="lote-forma-1"), QEventLoop(), QTimer()
    tm.setInterval(10)
    tm.timeout.connect(lambda: th.is_alive() or loop.quit())
    tm.start()
    th.start()
    loop.exec()
    tm.stop()
    th.join()
    if "erro" in est:
        raise est["erro"]
    return est["ret"], est["thread"], None


def _forma_2(f, cmd):  # o comando na thread da janela, com embrulhos (só durante o comando) que cedem ao Qt entre as operações
    import obimcore
    from PySide6.QtCore import QCoreApplication
    fat, api0, malhas0, cena0 = _Fatiador(QCoreApplication.processEvents), fluxo_a.api, obimcore.malhas, f.cena

    def api(nome, *a, **k):
        return fat.op(nome, api0, nome, *a, **k)

    def malhas(ifc, guids):
        guids, mal = list(guids), {}
        for i in range(0, len(guids), BLOCO_MALHAS):
            mal.update(fat.op("obimcore.malhas", malhas0, ifc, guids[i:i + BLOCO_MALHAS]))
        return mal
    fluxo_a.api, obimcore.malhas, f.cena = api, malhas, _CenaFatiada(cena0, fat)
    try:
        ret = f.executar_detalhado(cmd)
    finally:
        fluxo_a.api, obimcore.malhas, f.cena = api0, malhas0, cena0
    fat.fechar()
    return ret, threading.get_ident(), fat.fatias


def medir(f, forma, quantidade=1000, cmd=None, mouse=True):  # uma rodada; não desfaz nada; mouse=False = controle (só o pulso, sem a thread que posta o mouse)
    import obimcore
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, QPointF, Qt, QTimer
    from PySide6.QtGui import QMouseEvent, QPointingDevice
    cmd, janela, agora = cmd or lote_cmd(quantidade), f.janela_principal, obimcore.agora
    janela.setMouseTracking(True)  # sem isso o Qt descarta o movimento sem botão antes do filtro
    thread_janela, dispositivo = threading.get_ident(), QPointingDevice.primaryPointingDevice()  # o dispositivo nasce na thread da janela
    # (a) parado
    loop = QEventLoop()
    QTimer.singleShot(PARADO_MS, loop.quit)
    p0 = agora()
    loop.exec()
    p1 = agora()
    parado = {"t0_ms": p0, "t1_ms": p1, "quadros": [float(t) for t, _ in f.cena.relogio() if p0 <= t <= p1]}
    # (b) t0 e sondas
    t0, pulsos, lista, est = agora(), [], [], {"t1": None}
    pulso = QTimer()
    pulso.setTimerType(Qt.PreciseTimer)
    pulso.setInterval(PULSO_MS)
    pulso.timeout.connect(lambda: pulsos.append(agora()))
    pulso.start()
    filtro = poster = None
    if mouse:
        class Filtro(QObject):  # na janela principal: anota o instante tratado e consome o evento sintético
            def eventFilter(s, obj, ev):
                if ev.type() == QEvent.MouseMove and obj is janela and ev.position().y() == Y_MOUSE:
                    lista[int(ev.position().x())][2] = agora()
                    return True
                return False
        filtro = Filtro()
        janela.installEventFilter(filtro)

        def posta():  # k = 0, 1, 2...: agendado em t0 + 20k; posta todos até passar de t1, mesmo atrasada
            k = 0
            while True:
                ag = t0 + k * MOUSE_MS
                while agora() < ag:
                    if est["t1"] is not None and ag > est["t1"]:
                        return
                    time.sleep(min(max((ag - agora()) / 1000, 0.0002), 0.005))
                if est["t1"] is not None and ag > est["t1"]:
                    return
                lista.append([ag, ag, None])
                ev = QMouseEvent(QEvent.MouseMove, QPointF(k, Y_MOUSE), QPointF(k, Y_MOUSE), Qt.NoButton, Qt.NoButton, Qt.NoModifier, dispositivo)
                lista[k][1] = agora()  # postado = logo antes de entrar na fila
                QCoreApplication.postEvent(janela, ev)
                k += 1
        poster = threading.Thread(target=posta, name="lote-mouse", daemon=True)
        poster.start()
    # (c) o comando
    (guids, det), thread_lote, fatias = (_forma_1 if forma == 1 else _forma_2)(f, cmd)
    # (d) t1: primeiro quadro com a sequência do comando (a mesma conta de FluxoA._quadro)
    t1 = f._quadro(det["sequencia"], det["t0_ms"], det["t_comando_ms"]) if det.get("sequencia") is not None else det["t_comando_ms"]
    est["t1"] = t1
    # (e) desliga as sondas e espera todo evento agendado até t1 ser tratado
    if poster is not None:
        poster.join(5)
        mouse_ev = [m for m in lista if m[0] <= t1]
        f._bombear(lambda: all(m[2] is not None for m in mouse_ev), 5000)
        janela.removeEventFilter(filtro)
    else:
        mouse_ev = []
    pulso.stop()
    r = {"forma": forma, "quantidade": quantidade, "parado": parado, "thread_janela": thread_janela, "thread_lote": thread_lote, "t0_ms": t0, "t1_ms": t1,
         "quadros": [float(t) for t, _ in f.cena.relogio() if t0 <= t <= t1], "pulsos": [float(t) for t in pulsos if t0 <= t <= t1],
         "mouse": [[float(a), float(b), None if c is None else float(c)] for a, b, c in mouse_ev], "criados": len(det["criados"])}
    if fatias is not None:
        r["fatias"] = fatias
    r["resumo"] = resumo(r)
    return r


def _maior(ts):  # maior diferença entre valores vizinhos (None com menos de 2)
    return float(np.diff(np.asarray(ts, float)).max()) if len(ts) > 1 else None


def resumo(r):  # função pura (sem Qt)
    t0, t1, q = r["t0_ms"], r["t1_ms"], r["quadros"]
    jan = [sum(1 for t in q if t0 + 1000 * k <= t < t0 + 1000 * (k + 1)) for k in range(int((t1 - t0) // 1000))]
    at = np.array([m[2] - m[0] for m in r["mouse"]], float)
    m5b = {"n": len(at), "mediana_ms": float(np.median(at)), "p95_ms": float(np.percentile(at, 95)), "max_ms": float(at.max())} if len(at) else None
    out = {"M5": {"janelas": jan, "maior_intervalo_ms": _maior([t0, *q, t1]), "maior_intervalo_parado_ms": _maior(r["parado"]["quadros"])}, "M5b": m5b, "pulso_maior_ms": _maior([t0, *r["pulsos"], t1])}
    if "fatias" in r:
        fm = max(r["fatias"], key=lambda x: x["ms"])
        out["fatias"] = {"n": len(r["fatias"]), "mediana_ms": float(np.median([x["ms"] for x in r["fatias"]])), "maior_ms": fm["ms"], "maior_op": fm["op_mais_longa"]}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="T15b: formas 1 e 2 do lote (M5, M5b); grava threads.json")
    ap.add_argument("saida")
    ap.add_argument("--base", type=int, default=300)
    ap.add_argument("--quantidade", type=int, default=1000)
    ap.add_argument("--rodadas", type=int, default=3)
    a = ap.parse_args(argv)
    _caminhos()
    import gerar_modelo_grande
    tmp = Path(tempfile.mkdtemp(prefix="lote_"))
    gerar_modelo_grande.gerar(str(tmp / "base.ifc"), paredes=a.base)
    f = preparar(str(tmp / "base.ifc"), tmp / "saida")
    dados = {"versao": 1, "plataforma": sys.platform, "rhi": f._rhi, "base": a.base, "quantidade": a.quantidade, "rodadas": a.rodadas, "formas": {"1": [], "2": []}, "controle": {"1": [], "2": []}}
    for forma in (1, 2):
        for _ in range(a.rodadas):
            for grupo, mouse in (("controle", False), ("formas", True)):
                r = medir(f, forma, a.quantidade, mouse=mouse)
                dados[grupo][str(forma)].append(r)
                f.executar({"cmd": "desfazer"})
                f.executar({"cmd": "esperar", "ms": 300})
                s = r["resumo"]
                print(f"forma {forma} {grupo}: quadros maior {s['M5']['maior_intervalo_ms']:.0f} ms, pulso maior {s['pulso_maior_ms']:.0f} ms, M5b {s['M5b'] and round(s['M5b']['mediana_ms'])} / {s['M5b'] and round(s['M5b']['max_ms'])} ms", flush=True)
    f.fechar()
    dados = json.loads(json.dumps(dados))
    Path(a.saida).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


if __name__ == "__main__":
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    main()
