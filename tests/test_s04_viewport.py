# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da viewport C++ e do relógio (S04-T06; LOTE_OPUS_9 §2.3/§4; LOTE_OPUS_11/12). Cada caso gráfico roda em SUBPROCESSO sob
`xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1). GUARDA: pula enquanto `obimcore.Cena` ou seus métodos
não existirem (T07/T08); falha com OBIM_S04_OBRIGATORIO=1 **e** OBIM_S04_VIEWPORT_OBRIGATORIO=1. API ESPERADA (o Opus confere):
 obimcore.agora() -> ms (mesmo relógio de relogio(): steady_clock) · obimcore.Cena(gl: bool) (True OpenGL, False D3D11) · viewport_ptr()
 -> int (QWidget contêiner; shiboken6.wrapInstance) · iniciar()/parar()/viva() · adicionar_lote(LoteMalha) -> int (sequência crescente)
 · limpar() · relogio() -> [(tempo_ms, sequencia)] dos quadros APRESENTADOS (buffer >= 2000) · capturar() -> (larg, alt, RGBA8888 de cima
 para baixo) · camera() -> dict(alvo, distancia, azimute, elevacao) · definir_camera(...) (S03: Z para cima, graus, posição = alvo +
 distancia*(cos e cos a, cos e sin a, sin e)) · estatisticas() -> dict(lotes, triangulos, vertices, triangulos_na_placa, contextos) ·
 perder_contexto() (simula FrameOpDeviceLost). CONVENÇÕES: fundo (30,30,40) como na S03; faces CCW; azimute -90: +X à direita."""
import faulthandler
import importlib
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pytest

ESTE = Path(__file__).resolve()
RAIZ = ESTE.parent.parent
OBRIGATORIO = os.environ.get("OBIM_S04_OBRIGATORIO") == "1" and os.environ.get("OBIM_S04_VIEWPORT_OBRIGATORIO") == "1"
METODOS = ("viewport_ptr", "iniciar", "parar", "viva", "adicionar_lote", "limpar", "relogio", "capturar", "camera",
           "definir_camera", "estatisticas", "perder_contexto")
RODADAS, FUNDO = 5, (30, 30, 40)
CORES = ((240, 30, 30, 255), (30, 220, 30, 255), (30, 50, 240, 255))
CAM = dict(alvo=(0.0, 0.0, 0.0), distancia=20.0, azimute=-90.0, elevacao=20.0)
CAM2 = dict(alvo=(1.0, 0.0, 0.5), distancia=16.0, azimute=-70.0, elevacao=25.0)

VIVAS = []  # "sair": o processo termina com estas viewports vivas, sem parar()

pular = pytest.fail if OBRIGATORIO else pytest.skip

@pytest.fixture(scope="module")
def viewport():
    if importlib.util.find_spec("obimcore") is None:
        pular("\n!!! aguarda S04-T07/T08: módulo obimcore ausente (oráculo da viewport NÃO FOI EXECUTADO) !!!\n")
    import ifcopenshell, obimcore  # noqa: E401,F401
    faltam = [m for m in METODOS if not hasattr(getattr(obimcore, "Cena", None), m)] + ["agora"] * (not hasattr(obimcore, "agora"))
    faltam and pular(f"\n!!! aguarda S04-T07/T08: obimcore sem {faltam} (oráculo da viewport NÃO FOI EXECUTADO) !!!\n")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("\n!!! sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real !!!\n")

def caso(nome, *args, limite=400):
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")} | {"LC_ALL": "C"}
    win = sys.platform == "win32"
    env.update(QT_QPA_PLATFORM="windows", RHI="d3d11") if win else env.update(QT_QPA_PLATFORM="xcb", LIBGL_ALWAYS_SOFTWARE="1")
    pre = [] if win else ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24"]
    env["OBIM_LIMITE"] = str(limite)  # o subprocesso despeja a pilha das threads 20 s antes do tempo
    p = subprocess.run([*pre, sys.executable, str(ESTE), nome, *map(str, args)], env=env, capture_output=True, text=True, timeout=limite)
    linhas = [x for x in p.stdout.splitlines() if x.startswith("RESULTADO ")]
    assert p.returncode == 0 and linhas, f"o caso {nome} CAIU, travou ou não devolveu resultado (código {p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-2500:]}"
    r = json.loads(linhas[-1][10:])
    return r if "erro" not in r else pytest.fail(r["erro"])

def classificar(a):  # imagem HxWx4 -> {cor: (pixels, x médio)} para vermelho (v), verde (g), azul (a)
    r, g, b = (a[..., i].astype(int) for i in range(3))
    m = {k: (x >= 60) & (x > 1.8 * y) & (x > 1.8 * z) for k, (x, y, z) in zip("vga", ((r, g, b), (g, r, b), (b, r, g)))}
    return {k: [int(x.sum()), float(np.nonzero(x)[1].mean()) if x.any() else -1.0] for k, x in m.items()}

def veredito(fases):  # critério do LOTE_OPUS_11: {fase: [{"max": ms}, ...]} -> lista de erros
    mx = {k: [r["max"] for r in v] for k, v in fases.items()}
    erros, med = [f"fase {k}: {len(v)} rodadas (exige {RODADAS})" for k, v in mx.items() if len(v) != RODADAS], {k: statistics.median(v) for k, v in mx.items() if v}
    for k, v in mx.items():
        erros += [f"fase {k}: intervalo >= {200 if max(v) >= 200 else 100} ms ({max(v):.0f})"] * (max(v) >= 100)  # >= 200: reprova na hora
        erros += [f"fase {k}: mediana dos maiores {med[k]:.1f} ms >= 50"] * (med[k] >= 50)
        erros += [f"fase {k}: razão lote/parado {med[k] / med['A']:.1f} > 3"] * (k != "A" and med[k] > 3 * med["A"])
    return erros

def test_criterio_de_repeticao_do_oraculo():  # roda hoje, sem o módulo: a régua tem de aprovar o T05 e reprovar o F9
    f = lambda *m: {k: [{"max": x} for x in v] for k, v in zip("ABCD", m)}  # noqa: E731
    ok = [29.7, 30.1, 31.0, 29.9, 31.5]
    assert not veredito(f(ok, [31.9] * 5, [46.5, 31, 33, 32, 30], ok))
    assert all(veredito(f(ok, ok, c, ok)) for c in ([46.5, 31, 210, 32, 30], [120, 31, 33, 32, 30], [60] * 5, [30] * 4, [95] * 5))

def test_viewport_dentro_de_janela_pyside6_com_as_cores_esperadas(viewport):  # reaproveita S03-T03 (quadro não uniforme)
    r = caso("imagem")
    assert r["viva"] and r["na_janela"], r
    assert abs(r["tam"][0] - r["cont"][1]) <= 2 and abs(r["tam"][1] - r["cont"][0]) <= 2, f"imagem {r['tam']} != contêiner {r['cont']}"
    assert all(abs(c - f) <= 12 for px in r["cantos"] for c, f in zip(px, FUNDO)), f"fundo diferente de {FUNDO}: {r['cantos']}"
    assert all(r["cls"][k][0] >= 500 for k in "vga") and r["cores"] >= 3, f"cores esperadas ausentes: {r['cls']}"
    assert r["cls"]["v"][1] < r["cls"]["g"][1] < r["cls"]["a"][1], f"cubos fora de ordem na tela (X para a direita?): {r['cls']}"
    assert r["placa"] == 7200 and r["tri"] == 7200, r
    assert r["apos_limpar"] == [0, 0, 0] and r["tri_limpo"] == 0, r  # S03: limpar() solta tudo
    assert r["recolocado"], r

@pytest.mark.parametrize("ordem", ["PySide6.QtWidgets,PySide6.QtGui,obimcore", "obimcore,PySide6.QtWidgets,PySide6.QtGui"])
def test_r1e_um_qt_so_com_a_janela_aberta(viewport, ordem):  # Qt6Core, Gui, Widgets (e o que o GuiPrivate puxa) 1 vez cada
    r = caso("imagem", ordem)  # o mesmo caso da imagem, com a janela aberta e desenhando
    assert r["viva"]
    for fonte in ("modulo", "real"):  # nenhum núcleo duas vezes; as três bibliotecas Qt exatamente uma (T02 cobre as de geometria)
        assert all(len(v) <= 1 for v in (r[fonte] or {}).values()), f"duas cópias ({fonte}): {r[fonte]}"
    assert len(r["modulo"]["Qt6Core"]) == 1 and all(len(r["real"][k]) == 1 for k in ("Qt6Core", "Qt6Gui", "Qt6Widgets") if r["real"])

def test_relogio_crescente_e_casa_sequencia_com_quadro(viewport):
    r = caso("relogio")
    fr, marcas = r["quadros"], r["marcas"]
    ts, sq = [x[0] for x in fr], [x[1] for x in fr]
    assert len(fr) >= 40 and all(a < b for a, b in zip(ts, ts[1:])), "tempos dos quadros não crescem"
    assert all(a <= b for a, b in zip(sq, sq[1:])) and sq[-1] == marcas[-1][1], "sequência dos quadros não sobe até a última"
    assert all(a[1] < b[1] for a, b in zip(marcas, marcas[1:])), "sequência devolvida por adicionar_lote não cresce"
    for t, s in marcas:  # o quadro APRESENTADO que traz a mudança vem depois do pedido e logo (armadilha 6)
        q = next((x for x in fr if x[1] >= s), None)
        assert q and t < q[0] <= t + 500, f"sequência {s}: pedido em {t}, primeiro quadro com ela {q}"

def test_intervalo_maximo_com_o_bloqueio_preso(viewport):  # caso do T05, critério do lote 11, sensibilidade (c)
    r = caso("intervalo", limite=900)
    print("RODADAS", json.dumps({"fases": r["fases"], "hb": r["hb"]}))  # por rodada e fase: max, p99, lentos (>33 ms); hb = batimento da thread da janela
    for k in "CD":  # controle: o bloqueio ficou preso mesmo (a thread da janela parou >= 500 ms; só então a medida vale)
        assert min(r["hb"][k]) >= 500, f"controle falhou na fase {k}: a thread da janela só parou {r['hb'][k]} ms"
    assert not (erros := veredito(r["fases"])), f"{erros}\nrodadas: {r['fases']}"

def test_trocar_de_janela_setparent_esconder_e_redimensionar_sem_queda(viewport):  # armadilha 4 e achado 4(b): recriar a superfície
    r = caso("trocar")
    assert not r["falhas"] and r["viva"] and all(v[0] >= 500 for v in r["cls"].values()), r  # e a imagem final tem os 3 cubos

@pytest.mark.parametrize("modo", ["janela", "conteiner", "sair"])
def test_destruir_com_a_thread_rodando_sem_parar(viewport, modo):  # achado 3 e 4(a): vida da thread presa à da janela
    r = caso("destruir", modo)
    assert r["final_ok"], f"depois de {modo} uma viewport nova não voltou a desenhar: {r}"

def test_perda_de_contexto_volta_com_os_mesmos_triangulos_e_a_mesma_camera(viewport):  # lote 8 §2.3 item 5; S03 p17
    r = caso("contexto", limite=600)
    assert r["antes"]["triangulos_na_placa"] == r["antes"]["triangulos"] == 7200, r
    print("DIFS", json.dumps({"dif_imagem": [d["dif_imagem"] for d in r["depois"]], "dif_controle": r["dif_controle"], "dif_volta": r["dif_volta"]}))
    for i, d in enumerate(r["depois"]):
        assert d["contextos"] >= r["antes"]["contextos"] + i + 1, f"perda {i}: a QRhi não foi recriada ({d})"
        assert d["triangulos"] == d["triangulos_na_placa"] == 7200, f"perda {i}: voltou com {d} (eram 7200)"
        assert d["recuperou_s"] < 5.0, f"perda {i}: levou {d['recuperou_s']:.1f} s (a S03 esperava 5 s)"  # defeito 3 do lote 8
        assert np.allclose(d["camera"], r["camera0"], atol=1e-9), f"perda {i}: câmera {d['camera']} != {r['camera0']}"
        assert d["dif_imagem"] < 0.5, f"perda {i}: imagem difere do quadro de antes ({d['dif_imagem']:.2f} de 255)"
    # cubos pequenos na imagem: a diferença média /255 é baixa (2,1 medido), mas > 2x o limiar da repetida (0,5; medido 0,0)
    assert r["dif_controle"] > 1.0, "controle: trocar a câmera não muda a imagem (a captura não vê a câmera)"
    assert r["dif_volta"] < 0.5 and r["novo_lote"] == 7212, r  # lote novo depois da perda entra; câmera restaurada reproduz o quadro

def cubo(c, r, i):
    p, n, idx = [], [], []
    for eixo in range(3):
        for s in (-1, 1):
            nr, u, v = np.zeros(3), np.zeros(3), np.zeros(3)
            nr[eixo], u[(eixo + 1) % 3], v[(eixo + 2) % 3] = s, 1, 1
            b = i + len(p)
            p += [np.array(c, float) + r * (nr + a * u + k * v) for a, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            n += [nr] * 4
            idx += [b, b + 1, b + 2, b, b + 2, b + 3] if s > 0 else [b, b + 2, b + 1, b, b + 3, b + 2]
    return np.array(p), np.array(n), idx

def lote(n=600, cubos=None):  # 3 cubos coloridos à vista e n-3 cinza ATRÁS da câmera (fora do quadro): 12*n triângulos
    from viewport_qrhi.carregador import CINZA, DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    its = cubos or [((4 * i - 4, 0, 0), 1.0, CORES[i]) if i < 3 else (((i % 25) * 3 - 36, -100 - (i // 25) * 3, 0), 1.0, CINZA) for i in range(n)]
    v, o, ind = np.empty(24 * len(its), DTYPE_VERTICE), np.empty(len(its), DTYPE_OBJETO), []
    for j, (c, r, cor) in enumerate(its):
        p, nr, idx = cubo(c, r, 24 * j)
        v["pos"][24 * j:24 * j + 24], v["normal"][24 * j:24 * j + 24], v["cor"][24 * j:24 * j + 24] = p, nr, cor
        o[j] = (j, f"{j:022d}".encode(), 36 * j, 36, 24 * j, 24, p.min(0), p.max(0))
        ind += idx
    return LoteMalha(0, v, np.array(ind, np.uint32), o, np.zeros(3), len(its), len(its))
def um(i):
    return lote(cubos=[((i - 5.5, 0, -3), 0.4, CORES[i % 3])])

def novo(n=600, cam=CAM):
    import obimcore, shiboken6
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
    c = obimcore.Cena(os.environ.get("RHI", "d3d11" if sys.platform == "win32" else "gl") == "gl")
    w = QWidget()
    QVBoxLayout(w).addWidget(QLabel("Oráculo T06"))
    cont = shiboken6.wrapInstance(c.viewport_ptr(), QWidget)
    cont.setMinimumSize(320, 240)
    w.layout().addWidget(cont)
    w.resize(480, 400)
    c.definir_camera(**cam)
    if n:
        c.adicionar_lote(lote(n))
    c.iniciar()
    w.show()
    return c, w, cont
def captura(c):
    larg, alt, b = c.capturar()
    return np.frombuffer(bytes(b), np.uint8).reshape(alt, larg, 4)
def quadros(c, t0=0.0):
    return [(float(x[0]), int(x[1])) for x in c.relogio() if x[0] >= t0]
def esperar(cond, ms=8000):  # espera o quanto precisar sem travar a janela de teste
    t = time.perf_counter()
    while not cond() and (time.perf_counter() - t) * 1000 < ms:
        yield 50
    return cond()
def agora():  # importa o obimcore só na hora da chamada (a ordem de importação é do __main__)
    return __import__("obimcore").agora()
def retoma(c, n=5):
    t0 = agora()
    return (yield from esperar(lambda: c.viva() and len(quadros(c, t0)) >= n, 4000))
def segurar(s):  # chamada C que NÃO solta o bloqueio (PyDLL), como a de 0,75 s do T05
    import ctypes
    ctypes.PyDLL("kernel32").Sleep(int(s * 1000)) if sys.platform == "win32" else ctypes.PyDLL(None).usleep(int(s * 1e6))

def maps(res):  # R1-e: núcleos que o módulo vê e núcleos que o SO mapeou (Linux)
    import re
    import ifcopenshell.geom  # noqa: F401  (carrega geometry e OCCT)
    import obimcore
    rx = {"Qt6Core": "Qt6Core", "Qt6Gui": r"Qt6Gui(?!Private)", "Qt6Widgets": "Qt6Widgets", "parse": r"ifcopenshell\.parse",
          "geometry": r"ifcopenshell\.geometry(?!\.writer)", "TKernel": "TKernel"}
    agrupar = lambda cam: {k: sorted({os.path.realpath(x) for x in cam if re.search(r, os.path.basename(x))}) for k, r in rx.items()}  # noqa: E731
    res["modulo"] = agrupar(obimcore.bibliotecas_carregadas())
    res["real"] = agrupar({ln.split(None, 5)[5] for ln in Path("/proc/self/maps").read_text().splitlines() if len(ln.split(None, 5)) == 6}) \
        if sys.platform.startswith("linux") else None  # Windows: só a lista do módulo

def c_imagem(res, ordem=""):  # `ordem`: já importada pelo __main__ (R1-e nas duas ordens)
    c, w, cont = novo()
    res["viva"] = yield from esperar(lambda: c.viva() and len(quadros(c)) > 5 and c.estatisticas()["triangulos_na_placa"] == 7200)
    maps(res)
    a, st = captura(c), c.estatisticas()
    res.update(na_janela=cont.window() is w and cont.isVisible() and w.isVisible(), tam=list(a.shape), cont=[cont.width(), cont.height()],
               cls=classificar(a), cores=len({tuple(p) for p in a[::4, ::4].reshape(-1, 4)}), placa=st["triangulos_na_placa"], tri=st["triangulos"],
               cantos=[a[y, x, :3].tolist() for y in (2, -3) for x in (2, -3)])
    c.limpar()
    yield from esperar(lambda: c.estatisticas()["triangulos"] == 0)
    yield 500
    res.update(apos_limpar=[classificar(captura(c))[k][0] for k in "vga"], tri_limpo=c.estatisticas()["triangulos"])
    c.adicionar_lote(lote())
    res["recolocado"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 7200)
    c.parar()

def c_relogio(res):
    c, w, _ = novo(0)
    yield 1000
    res["marcas"] = []
    for i in range(12):
        res["marcas"].append([agora(), c.adicionar_lote(um(i))])
        yield 120
    yield 600
    res["quadros"] = quadros(c)
    c.parar()

def lote_api(dur):  # lote de ifcopenshell.api numa thread Python (como o T05)
    import ifcopenshell.api
    run = ifcopenshell.api.run
    f = run("project.create_file")
    run("root.create_entity", f, ifc_class="IfcProject")
    fim = time.perf_counter() + dur
    while time.perf_counter() < fim:
        w = run("root.create_entity", f, ifc_class="IfcWall", name="w")
        run("pset.edit_pset", f, pset=run("pset.add_pset", f, product=w, name="Pset_WallCommon"), properties={"FireRating": "R60"})
        run("attribute.edit_attributes", f, product=w, attributes={"Description": "x" * 20})

def c_intervalo(res):
    import threading
    from PySide6.QtCore import QTimer
    c, w, _ = novo(60)
    hb, tm = [], QTimer()  # batimento da thread da janela (controle de sensibilidade)
    tm.timeout.connect(lambda: hb.append(time.perf_counter() * 1000))
    tm.start(10)
    yield 2000
    res["fases"], res["hb"] = {k: [] for k in "ABCD"}, {"C": [], "D": []}

    def espera(alvo, *a):
        th = threading.Thread(target=alvo, args=a)
        th.start()
        while th.is_alive():
            yield 20
    for fase in "ABCD":
        for _ in range(RODADAS):
            t0, p0 = agora(), time.perf_counter() * 1000
            if fase == "A":
                yield 1500
            elif fase == "B":
                yield from espera(lote_api, 2.0)
            else:
                for _ in range(3):
                    if fase == "C":
                        yield from espera(segurar, 0.75)
                    else:
                        segurar(0.75)  # na thread principal: a janela PySide6 inteira para
                    yield 300
            t1, p1 = agora(), time.perf_counter() * 1000
            ts = [t for t, _ in quadros(c, t0) if t <= t1]
            g = sorted(b - a for a, b in zip(ts, ts[1:])) or [1e9]
            res["fases"][fase].append(dict(max=g[-1], p99=g[int(0.99 * (len(g) - 1))], lentos=sum(x > 33 for x in g), quadros=len(ts)))
            if fase in "CD":
                hh = [x for x in hb if p0 <= x <= p1]
                res["hb"][fase].append(max(b - a for a, b in zip(hh, hh[1:])) if len(hh) > 1 else 1e9)
    c.parar()

def c_trocar(res):
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    c, a, cont = novo(60)
    b = QWidget()
    QVBoxLayout(b)
    yield 1000
    res["falhas"] = []
    for i in range(10):  # trocar de janela pelo layout (setParent embutido)
        alvo, ori = (b, a) if i % 2 == 0 else (a, b)
        alvo.layout().addWidget(cont)
        ori.hide()
        alvo.show()
        if not (yield from retoma(c)):
            res["falhas"].append(f"layout {i}")
    for i in range(10):  # setParent explícito: solta (vira janela própria) e volta
        cont.setParent(None)
        cont.show()
        yield 150
        (a if i % 2 else b).layout().addWidget(cont)
        (a if i % 2 else b).show()
        if not (yield from retoma(c)):
            res["falhas"].append(f"setParent {i}")
    for i in range(20):  # redimensionar, esconder, minimizar e mostrar
        a.resize(400 + 10 * i, 360 + 5 * i)
        yield 60
        (a.showMinimized if i % 4 == 3 else a.hide)()
        yield 60
        (a.showNormal if i % 4 == 3 else a.show)()
        if not (yield from retoma(c)):
            res["falhas"].append(f"esconder {i}")
    res["img0"] = list(captura(c).shape)  # diagnóstico: captura imediata, antes de esperar
    yield 1500
    img = captura(c)
    res["viva"], res["cls"] = c.viva(), classificar(img)
    fundo = (np.abs(img[..., :3].astype(int) - (30, 30, 40)).sum(-1) > 30).any(0).nonzero()[0]  # diagnóstico: colunas com algo desenhado
    res["diag"] = dict(img=list(img.shape), janela=[a.width(), a.height()], cont=[cont.width(), cont.height()], dpr=cont.devicePixelRatioF(),
                       colunas=[int(fundo.min()), int(fundo.max())] if fundo.size else None)
    print("DIAG", json.dumps(res["diag"]), flush=True)
    try:
        from PIL import Image
        Image.fromarray(img).save(RAIZ / "out" / "s04_trocar.png")
    except Exception as e:  # noqa: BLE001
        print("sem PNG:", e, flush=True)
    c.parar()

def c_destruir(res, modo):
    import shiboken6
    for i in range(12):
        c, w, cont = novo(30)
        yield 200
        if modo == "janela":  # destrói a janela com a thread rodando e SEM parar()
            w.close()
            shiboken6.delete(w) if i % 2 else w.deleteLater()
        elif modo == "conteiner":  # só o contêiner some; a janela-pai fica. Pares: deleteLater() ainda no layout; ímpares: soltar e apagar
            if i % 2:
                cont.setParent(None)  # PySide6 puro: delete() de filho que ainda está no layout derruba o processo ao destruir a janela-pai
                shiboken6.delete(cont)
            else:
                cont.deleteLater()
            yield 200
            c.parar() if i % 2 else None
            w.close()
        else:  # "sair": nada é fechado; o processo termina com várias threads de desenho vivas
            VIVAS.append((c, w, cont))
        yield 250
    c, w, cont = novo(30)
    res["final_ok"] = yield from retoma(c, 10)
    VIVAS.append((c, w, cont)) if modo == "sair" else (c.parar(), w.close())

def c_contexto(res):  # `lote()` não fica em variável: o reenvio sai só da cópia compacta do C++
    c, w, _ = novo(0, CAM2)
    c.adicionar_lote(lote())
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 7200)
    yield 800
    res["camera0"], res["antes"], a0 = list(_cam(c)), c.estatisticas(), captura(c)
    dif = lambda: float(np.abs(captura(c).astype(int) - a0).mean())  # noqa: E731
    res["depois"] = []
    for _ in range(3):
        t0, n0 = time.perf_counter(), c.estatisticas()["contextos"]
        c.perder_contexto()
        yield from esperar(lambda: c.estatisticas()["contextos"] > n0 and c.estatisticas()["triangulos_na_placa"] == 7200, 12000)
        s, dt = c.estatisticas(), time.perf_counter() - t0
        yield 500
        res["depois"].append(dict(s, recuperou_s=dt, camera=list(_cam(c)), dif_imagem=dif()))
    for k, cam in (("dif_controle", CAM), ("dif_volta", CAM2)):
        c.definir_camera(**cam)
        yield 600
        res[k] = dif()
    c.adicionar_lote(um(0))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 7212)
    res["novo_lote"] = c.estatisticas()["triangulos"]
    c.parar()

def _cam(c):
    d = c.camera()
    return [*map(float, d["alvo"]), float(d["distancia"]), float(d["azimute"]), float(d["elevacao"])]

def rodar(corpo, limite=500):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", limite)) - 20, exit=True)  # diagnóstico: pilha de todas as threads
    app, res = QApplication(sys.argv[:1]), {}
    app.setQuitOnLastWindowClosed(False)
    fim = lambda r: (print("RESULTADO " + json.dumps(r, ensure_ascii=False), flush=True), app.exit(0))  # noqa: E731

    def passo(g):
        try:
            ms = next(g)
        except StopIteration:
            return fim(res)
        except BaseException:
            return fim({"erro": traceback.format_exc()})
        QTimer.singleShot(ms, lambda: passo(g))
    QTimer.singleShot(limite * 1000, lambda: fim({"erro": "tempo esgotado"}))
    QTimer.singleShot(0, lambda: passo(corpo(res)))
    sys.exit(app.exec())

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o oráculo importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in (resto[0] if nome == "imagem" and resto else "ifcopenshell,obimcore").split(",")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
