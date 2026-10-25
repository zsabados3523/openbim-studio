# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conferências (i), (ii), (iii) e forma 3 (referência). Sondas que alimentam o ADR-004, não portão (a forma 3 deve reprovar).
Contrato em CONTRATO.md e nos testes tests/test_s04_t15c_conferencias.py. Medir, não otimizar. Importar não cria QApplication nem importa o obimcore.
Uso: `python conferencias.py <saida.json> [--base 300] [--quantidade 1000] [--rodadas 3]`."""
import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import fluxo_a
import lote
import numpy as np

SEG = 1.0  # duração de cada medida da conferência (i)
FORA = "(fora da API)"
GRANDE = 10000  # paredes do modelo das chamadas longas de (ii): abrir ~0,17 s, gravar ~0,5 s
ALVO_PRESO_S = 0.75  # a chamada C


def _fluxo(base, saida):  # fluxo sem janela, com o tipo PAR15 criado
    f = fluxo_a.FluxoA(base, janela=False, saida=saida)
    f.executar(lote.TIPO)
    return f


# ---------- (i) QEventLoop.exec() ocioso solta o bloqueio do interpretador? ----------
def _voltas(espera):  # voltas que uma thread Python dá enquanto a principal executa `espera()`
    parar, n = threading.Event(), [0]

    def conta():
        while not parar.is_set():
            n[0] += 1
    th = threading.Thread(target=conta, name="conferencia-i")
    th.start()
    try:
        espera()
    finally:
        parar.set()
        th.join()
    return n[0]


def conferencia_i():
    from PySide6.QtCore import QEventLoop, QTimer

    def em_join():
        dorme = threading.Thread(target=time.sleep, args=(SEG,))
        dorme.start()
        dorme.join()

    def em_exec():
        loop = QEventLoop()
        QTimer.singleShot(int(SEG * 1000), loop.quit)
        loop.exec()

    def ocupada():  # controle positivo: a principal trabalha em Python
        trabalho = threading.Thread(target=time.sleep, args=(SEG,))
        trabalho.start()
        k = 0
        while trabalho.is_alive():
            k += 1
    join, ex, oc = _voltas(em_join), _voltas(em_exec), _voltas(ocupada)
    r_exec, r_oc = ex / join, oc / join
    return {"join": int(join), "exec": int(ex), "ocupada": int(oc), "razao_exec": float(r_exec), "razao_ocupada": float(r_oc),
            "resposta": "sim" if r_exec >= 0.8 else "não" if r_exec <= 0.3 else "inconclusivo"}


# ---------- (ii) causa das paradas do F7 ----------
def _lote_com_vigia(f, quantidade):  # o lote com a API embrulhada e uma thread vigia; devolve (lote_ms, durações por função, amostras do vigia)
    api0, atual, duracoes, amostras, parar = fluxo_a.api, [FORA], [], [], threading.Event()

    def api(nome, *a, **k):
        atual[0], t = nome, time.perf_counter()
        try:
            return api0(nome, *a, **k)
        finally:
            duracoes.append((nome, (time.perf_counter() - t) * 1000))
            atual[0] = FORA

    def vigia():  # dorme 1 ms; o que passou de 1 ms é o quanto o bloqueio esteve fora de alcance, atribuído à função em curso ao acordar
        while not parar.is_set():
            t = time.perf_counter()
            time.sleep(0.001)
            amostras.append((atual[0], max(0.0, (time.perf_counter() - t) * 1000 - 1.0)))
    th = threading.Thread(target=vigia, name="conferencia-vigia")
    fluxo_a.api = api
    th.start()
    t = time.perf_counter()
    try:
        f.executar(lote.lote_cmd(quantidade))
    finally:
        lote_ms = (time.perf_counter() - t) * 1000
        fluxo_a.api = api0
        parar.set()
        th.join()
    return lote_ms, duracoes, amostras


def _por_funcao(duracoes, amostras):
    por = {n: {"n": 0, "duracao_max_ms": 0.0, "duracao_soma_ms": 0.0, "atraso_vigia_max_ms": 0.0} for n in {d[0] for d in duracoes} | {FORA}}
    for nome, d in duracoes:
        p = por[nome]
        p["n"] += 1
        p["duracao_soma_ms"] += d
        p["duracao_max_ms"] = max(p["duracao_max_ms"], d)
    for nome, a in amostras:
        por[nome]["atraso_vigia_max_ms"] = max(por[nome]["atraso_vigia_max_ms"], a)
    return por


def _taxa_principal(chamada):  # voltas/ms da principal durante `chamada()` (numa thread) ÷ voltas/ms antes, no MESMO laço; (ms da chamada, taxa)
    def laco(ev, limite_s):
        n, t = 0, time.perf_counter()
        while not ev.is_set() and time.perf_counter() - t < limite_s:
            n += 1
        return n / max((time.perf_counter() - t) * 1000, 1e-9)
    antes, fim, ms = laco(threading.Event(), 0.3), threading.Event(), []

    def trabalha():
        t = time.perf_counter()
        chamada()
        ms.append((time.perf_counter() - t) * 1000)
        fim.set()
    th = threading.Thread(target=trabalha, name="conferencia-chamada")
    th.start()
    durante = laco(fim, float("inf"))
    th.join()
    return ms[0], durante / antes


def conferencia_ii(base, quantidade, tmp):
    import ifcopenshell
    from openbim_app.localidade import garantir_numerico_c
    so = next(Path(ifcopenshell.__file__).parent.glob("_ifcopenshell_wrapper*"))
    blob = so.read_bytes()
    ii, original = {"importa_save_thread": b"PyEval_SaveThread" in blob, "importa_restore_thread": b"PyEval_RestoreThread" in blob, "intervalos": []}, sys.getswitchinterval()
    try:
        for intervalo in (0.005, 0.001):
            sys.setswitchinterval(intervalo)
            f = _fluxo(base, tmp / f"saida_ii_{intervalo}")
            lote_ms, duracoes, amostras = _lote_com_vigia(f, quantidade)
            f.executar({"cmd": "desfazer"})
            atrasos = [a for _, a in amostras] or [0.0]
            por = _por_funcao(duracoes, amostras)
            ii["intervalos"].append({"intervalo_s": intervalo, "lote_ms": float(lote_ms), "atraso_vigia_max_ms": float(max(atrasos)), "atraso_vigia_p95_ms": float(np.percentile(atrasos, 95)),
                                     "por_funcao": por})
    finally:
        sys.setswitchinterval(original)
    grande = tmp / "grande.ifc"
    import gerar_modelo_grande
    gerar_modelo_grande.gerar(str(grande), paredes=GRANDE)
    modelo = ifcopenshell.open(str(grande))
    garantir_numerico_c()
    chamadas = {"ifcopenshell.open": lambda: ifcopenshell.open(str(grande)), "file.write": lambda: modelo.write(str(tmp / "regravado.ifc"))}
    ii["solta_gil"] = {}
    for nome, chamada in chamadas.items():
        ms, taxa = _taxa_principal(chamada)
        ii["solta_gil"][nome] = {"ms": float(ms), "taxa_principal": float(taxa), "solta": bool(taxa >= 0.5)}
    return ii


# ---------- (iii) o desenho não passa pelo Python nem pela thread da janela ----------
def conferencia_iii(f):  # f = fluxo com janela e a órbita girando (lote.preparar); a thread da janela fica presa numa chamada C com o bloqueio preso
    import obimcore
    f.executar({"cmd": "esperar", "ms": 500})
    n = 1_000_000
    while True:  # calibra dobrando até a chamada durar >= 0,75 s
        t = time.perf_counter()
        sum(range(n))
        if time.perf_counter() - t >= ALVO_PRESO_S:
            break
        n *= 2
    t0 = obimcore.agora()
    sum(range(n))
    t1 = obimcore.agora()
    quadros = [float(t) for t, _ in f.cena.relogio() if t0 <= t <= t1]
    c = type(f._cont)
    return {"gil_preso_ms": float(t1 - t0), "quadros": len(quadros), "maior_intervalo_ms": lote._maior([t0, *quadros, t1]), "classe_conteiner": f"{c.__module__}.{c.__qualname__}",
            "conteiner_python": not c.__module__.startswith("PySide6.")}


# ---------- forma 3: a forma 1 com a viewport Python (referência; espera-se que reprove) ----------
def forma_3(base, quantidade, rodadas, tmp):
    import obimcore
    from PySide6.QtCore import QEventLoop, QTimer
    from viewport_qrhi.cubo_rhi import CuboViewport
    agora, quadros, pulsos = obimcore.agora, [], []
    w = CuboViewport(girar=True)  # cubo padrão
    w.resize(640, 480)
    w.frameSubmitted.connect(lambda: quadros.append(float(agora())))
    w.show()
    f, rs, loop = _fluxo(base, tmp / "saida_f3"), [], QEventLoop()
    QTimer.singleShot(10000, loop.quit)
    espera = QTimer()
    espera.setInterval(10)
    espera.timeout.connect(lambda: quadros and loop.quit())
    espera.start()
    loop.exec()
    espera.stop()
    if not quadros:
        raise RuntimeError("a viewport Python não apresentou o primeiro quadro em 10 s")
    pulso = QTimer()
    pulso.setInterval(lote.PULSO_MS)
    pulso.timeout.connect(lambda: pulsos.append(float(agora())))
    try:
        for _ in range(rodadas):
            loop = QEventLoop()  # (a) parado
            QTimer.singleShot(lote.PARADO_MS, loop.quit)
            p0 = float(agora())
            loop.exec()
            p1 = float(agora())
            parado = {"t0_ms": p0, "t1_ms": p1, "quadros": [t for t in quadros if p0 <= t <= p1]}
            pulsos.clear()  # (b) o lote numa thread Python, a janela em QEventLoop.exec()
            pulso.start()
            t0 = float(agora())
            (_, det), thread_lote, _ = lote._forma_1(f, lote.lote_cmd(quantidade))
            t1 = float(agora())
            pulso.stop()
            r = {"forma": 3, "quantidade": quantidade, "parado": parado, "thread_janela": threading.get_ident(), "thread_lote": thread_lote, "t0_ms": t0, "t1_ms": t1,
                 "quadros": [t for t in quadros if t0 <= t <= t1], "pulsos": [t for t in pulsos if t0 <= t <= t1], "criados": len(det["criados"])}
            r["resumo"] = {k: v for k, v in lote.resumo({**r, "mouse": []}).items() if k != "M5b"}
            rs.append(r)
            f.executar({"cmd": "desfazer"})  # fora da janela medida
    finally:
        pulso.stop()
        w.close()
    return rs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Conferências (i), (ii), (iii) e forma 3; grava conferencias.json")
    ap.add_argument("saida")
    ap.add_argument("--base", type=int, default=300)
    ap.add_argument("--quantidade", type=int, default=1000)
    ap.add_argument("--rodadas", type=int, default=3)
    a = ap.parse_args(argv)
    lote._caminhos()
    import gerar_modelo_grande
    tmp = Path(tempfile.mkdtemp(prefix="conferencias_"))
    gerar_modelo_grande.gerar(str(tmp / "base.ifc"), paredes=a.base)
    base = str(tmp / "base.ifc")
    f = lote.preparar(base, tmp / "saida")
    f._app.setQuitOnLastWindowClosed(False)  # a janela do núcleo fecha antes da forma 3; o programa segue
    dados = {"versao": 1, "plataforma": sys.platform, "base": a.base, "quantidade": a.quantidade, "rodadas": a.rodadas}
    dados["i"] = conferencia_i()
    dados["iii"] = conferencia_iii(f)
    f.fechar()
    dados["ii"] = conferencia_ii(base, a.quantidade, tmp)
    dados["forma3"] = forma_3(base, a.quantidade, a.rodadas, tmp)
    dados = json.loads(json.dumps(dados))
    Path(a.saida).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    i, iii, ii = dados["i"], dados["iii"], dados["ii"]
    print(f"(i) join {i['join']} exec {i['exec']} ocupada {i['ocupada']}: razão exec {i['razao_exec']:.2f}, ocupada {i['razao_ocupada']:.2f} -> {i['resposta']}", flush=True)
    for x in ii["intervalos"]:
        print(f"(ii) intervalo {x['intervalo_s']} s: lote {x['lote_ms']:.0f} ms, vigia max {x['atraso_vigia_max_ms']:.0f} ms, p95 {x['atraso_vigia_p95_ms']:.1f} ms", flush=True)
    print(f"(ii) solta o bloqueio: {ii['solta_gil']}; importa Save/Restore: {ii['importa_save_thread']}/{ii['importa_restore_thread']}", flush=True)
    print(f"(iii) preso {iii['gil_preso_ms']:.0f} ms, {iii['quadros']} quadros, maior intervalo {iii['maior_intervalo_ms']:.0f} ms, contêiner {iii['classe_conteiner']}", flush=True)
    for r in dados["forma3"]:
        s = r["resumo"]
        print(f"forma 3: parado {len(r['parado']['quadros'])} quadros, lote {r['t1_ms'] - r['t0_ms']:.0f} ms, maior intervalo {s['M5']['maior_intervalo_ms']:.0f} ms, pulso maior {s['pulso_maior_ms']:.0f} ms", flush=True)
    return dados


if __name__ == "__main__":
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    main()
