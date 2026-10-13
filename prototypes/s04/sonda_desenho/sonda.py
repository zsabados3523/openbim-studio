# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da thread de desenho (S04-T05): janela nativa desenhada por thread do C++, embutida numa janela PySide6.
Mede o MAIOR intervalo entre quadros apresentados (meta < 50 ms) parado, com o lote ifcopenshell.api numa thread Python,
com a chamada C de 0,75 s (em thread e na thread principal) e depois de 20 ciclos de redimensionar/esconder/mostrar e
20 aberturas e fechamentos. Nunca roda na tela real: use xvfb-run (Linux) ou o CI (Windows).
Uso: python sonda.py <pasta-do-modulo> <saida.json>   (RHI=gl|d3d11 escolhe o desenho; padrão: d3d11 no Windows, gl no resto)"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(sys.argv[1]))
os.environ.setdefault("QT_QUICK_BACKEND", "software")
import ifcopenshell  # noqa: E402
import ifcopenshell.api.attribute  # noqa: E402
import ifcopenshell.api.project  # noqa: E402
import ifcopenshell.api.pset  # noqa: E402
import ifcopenshell.api.root  # noqa: E402
import shiboken6  # noqa: E402
import _sonda_desenho as sd  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QWindow  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

META_MS = 50.0
GL = os.environ.get("RHI", "d3d11" if sys.platform == "win32" else "gl") == "gl"
app = QApplication(sys.argv[:1])
app.setQuitOnLastWindowClosed(False)
res = {"fases": {}, "ciclos": {}}
res["rhi"] = "gl" if GL else "d3d11"


def novo():
    """Cria o desenho e a janela PySide6 com o contêiner da janela nativa."""
    d = sd.Desenho(GL)
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("Sonda T05 (PySide6)"))
    cont = QWidget.createWindowContainer(shiboken6.wrapInstance(d.janela(), QWindow), w)
    cont.setMinimumSize(320, 240)
    lay.addWidget(cont)
    w.resize(480, 400)
    d.iniciar()
    return d, w, cont


def lote(duracao, feito):
    """Lote da API do IfcOpenShell numa thread Python (como o F7/F9)."""
    f = ifcopenshell.api.project.create_file()
    ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="p")
    n, fim = 0, time.perf_counter() + duracao
    while time.perf_counter() < fim:
        w = ifcopenshell.api.root.create_entity(f, ifc_class="IfcWall", name=f"w{n}")
        ps = ifcopenshell.api.pset.add_pset(f, product=w, name="Pset_WallCommon")
        ifcopenshell.api.pset.edit_pset(f, pset=ps, properties={"FireRating": "R60", "IsExternal": True})
        ifcopenshell.api.attribute.edit_attributes(f, product=w, attributes={"Description": "x" * 20})
        n += 1
    feito.append(n)


def medir(q, t0, t1):
    ts = [t for t in q if t0 <= t <= t1]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    return {"quadros": len(ts), "fps": round(len(ts) / max((t1 - t0) / 1000, 1e-9), 1),
            "maior_intervalo_ms": round(max(gaps), 1) if gaps else None,
            "mediana_ms": round(sorted(gaps)[len(gaps) // 2], 1) if gaps else None}


def fases():
    d, w, cont = novo()
    w.show()
    yield 2000  # aquecimento
    if not d.viva():
        res["erro"] = "thread de desenho nao subiu: " + d.info()
        return
    res["info"] = d.info()
    marcas = {}

    def fase(nome, t0, t1):
        marcas[nome] = (t0, t1)

    t0 = sd.agora()
    yield 2000
    fase("A_parado", t0, sd.agora())
    feito = []
    th = threading.Thread(target=lote, args=(4.0, feito))
    t0 = sd.agora()
    th.start()
    while th.is_alive():
        yield 20
    fase("B_lote_ifcopenshell_thread", t0, sd.agora())
    res["fases"]["B_operacoes_do_lote"] = feito[0]
    t0 = sd.agora()
    for _ in range(3):
        th = threading.Thread(target=sd.segurar_gil, args=(0.75,))
        th.start()
        while th.is_alive():
            yield 20
        yield 300
    fase("C_chamada_C_0.75s_em_thread", t0, sd.agora())
    t0 = sd.agora()
    for _ in range(3):
        sd.segurar_gil(0.75)  # na thread principal: a janela PySide6 inteira fica parada
        yield 300
    fase("D_chamada_C_0.75s_na_thread_principal", t0, sd.agora())
    q = d.quadros()
    for nome, (a, b) in marcas.items():
        res["fases"][nome] = medir(q, a, b)
    # 20 ciclos: redimensionar, esconder, mostrar; depois de cada mostrar a thread tem de voltar a desenhar
    falhas = 0
    for i in range(20):
        w.resize(400 + 10 * i, 360 + 5 * i)
        yield 60
        w.hide()
        yield 60
        n0 = len(d.quadros())
        w.show()
        yield 250
        if len(d.quadros()) <= n0 or not d.viva():
            falhas += 1
    res["ciclos"]["redimensionar_esconder_mostrar"] = {"ciclos": 20, "sem_retomar": falhas}
    d.parar()
    w.close()
    w.deleteLater()
    yield 100
    # 20 aberturas e fechamentos (cria, mostra, desenha, fecha) sem queda
    sem = 0
    for i in range(20):
        d2, w2, _ = novo()
        w2.show()
        yield 200
        if len(d2.quadros()) < 3:
            sem += 1
        w2.close()
        d2.parar()
        w2.deleteLater()
        del d2, w2
        yield 50
    res["ciclos"]["abrir_fechar"] = {"ciclos": 20, "sem_quadros": sem}
    del d, w, cont


def passo(gen):
    try:
        ms = next(gen)
    except StopIteration:
        return fim()
    QTimer.singleShot(ms, lambda: passo(gen))


def fim():
    bom = all(v["maior_intervalo_ms"] is not None and v["maior_intervalo_ms"] < META_MS
              for k, v in res["fases"].items() if isinstance(v, dict))
    c = res["ciclos"]
    bom = bom and "erro" not in res and c.get("redimensionar_esconder_mostrar", {}).get("sem_retomar", 1) == 0 \
        and c.get("abrir_fechar", {}).get("sem_quadros", 1) == 0
    res["meta_atingida"] = bool(bom)
    with open(sys.argv[2], "w", encoding="utf-8") as fo:
        json.dump(res, fo, indent=1, ensure_ascii=False)
    print("SONDA_DESENHO", json.dumps(res, ensure_ascii=False))
    app.exit(0 if bom else 1)


QTimer.singleShot(0, lambda: passo(fases()))
sys.exit(app.exec())
