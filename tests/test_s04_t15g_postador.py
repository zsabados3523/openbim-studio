# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da F0-S04-T15g: o postador de mouse de `lote.medir` não constrói evento fora da thread da janela (cartão F0-S04-T15g; diagnóstico T15f, lotes 43 e 44).
Os casos rodam o `lote.medir` de verdade num SUBPROCESSO com janela (Linux: `xvfb-run -a`; Windows: só no CI), com um `f` de ensaio (janela Qt
simples, comando que só espera, `obimcore.agora` de ensaio): não precisam do obimcore. Contrato (o implementador lê só isto):
1. Regra 1: todo `QMouseEvent` e o dispositivo nascem na thread da janela, DENTRO da chamada de `medir` e ANTES de t0 (cada rodada constrói os
   seus: de 3.001 a 90.001 eventos, ou seja, de 60 s a 30 min de lote a 20 ms). A thread `lote-mouse` só chama
   `QCoreApplication.postEvent(janela, ev)`: o k-ésimo objeto postado é UM dos construídos (identidade: nada de `clone()`, cópia ou reuso), com
   x == k. Espião: subclasses de `PySide6.QtGui.QMouseEvent`/`QPointingDevice` e `QCoreApplication.postEvent` trocados ANTES de `import lote`
   (use esses nomes na hora; não guarde cópias de antes).
2. Regra 2: acabaram os eventos = `RuntimeError` com "acabaram" na mensagem (nunca recicla, nunca para calado). Regra 3: depois de
   `poster.join(5)`, postador vivo = `RuntimeError` com "lote-mouse"; `f._bombear(...)` devolveu False = `RuntimeError` com "_bombear"
   (nunca `TypeError` em `resumo`).
3. Queda (critério 1b): a sonda `sonda_corrida.py` do lote 43 só cai com o postador rápido (medido: 6 de 6 a ~5.000 eventos/s, em 1 a 3 s;
   0 de 6 a 1 evento a cada 20 ms, em 25 s). Equivalente: o MESMO `medir` com o relógio de ensaio 100 vezes mais rápido (20 ms do relógio =
   0,2 ms reais), o ponteiro do X se mexendo a cada 1 ms sobre a janela, 15 s de rodadas de ~1.000 eventos. Trava com taxa medida, não prova:
   o determinístico é o espião (item 1).
4. Nenhuma régua, limite ou constante muda (M5, M5b, PARADO_MS, MOUSE_MS, PULSO_MS); fora de `medir` e do `__main__`, `lote.py` fica igual;
   o controle (`mouse=False`) não constrói nem posta evento de mouse e não cria a thread `lote-mouse`; o `__main__` liga `faulthandler.enable()`.
GUARDA: com OBIM_S04_T15_OBRIGATORIO=1 todo pulo vira falha."""
import hashlib
import inspect
import math
import os
import shutil
import sys
import threading
import time
import traceback
import types
from pathlib import Path

import pytest
import s04_fluxo_aux as aux

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T15_OBRIGATORIO") == "1"
REG = {"ev": [], "disp": [], "post": [], "segurar": False}


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-T15g: {msg} (oráculo do postador NÃO FOI EXECUTADO) !!!\n")


# ---------- ambiente de ensaio (só no subprocesso) ----------
def _ambiente(vel=1.0, espiao=True):  # relógio de ensaio `vel` vezes mais rápido; espiões ANTES de `import lote`
    b = time.perf_counter()

    def agora():
        return 1000.0 * (b + (time.perf_counter() - b) * vel)
    sys.modules["obimcore"] = types.SimpleNamespace(agora=agora, malhas=lambda ifc, guids: {})
    import PySide6.QtCore as C
    import PySide6.QtGui as G
    from PySide6.QtWidgets import QApplication, QMainWindow
    if espiao:
        Ev, Disp, post0 = G.QMouseEvent, G.QPointingDevice, C.QCoreApplication.postEvent

        class EspEv(Ev):
            def __init__(s, *a, **k):
                REG["ev"].append((threading.get_ident(), agora(), s))  # referência forte: id() não se repete
                super().__init__(*a, **k)

        class EspDisp(Disp):
            def __init__(s, *a, **k):
                REG["disp"].append(threading.get_ident())
                super().__init__(*a, **k)

            @staticmethod
            def primaryPointingDevice(*a):
                REG["disp"].append(threading.get_ident())
                return Disp.primaryPointingDevice(*a)

        def post(obj, ev, *a):
            try:  # lido ANTES de postar (depois o Qt é o dono); objeto já apagado pelo Qt = reuso: conta como mouse repetido
                mm, x = ev.type() == C.QEvent.MouseMove, ev.position().x()
            except (RuntimeError, AttributeError):
                mm, x = isinstance(ev, EspEv), None
            if mm:
                REG["post"].append((threading.current_thread().name, threading.get_ident(), id(ev), x))
                if REG["segurar"] and threading.current_thread() is not threading.main_thread():  # 1o post do postador preso 15 s
                    REG["segurar"] = False
                    time.sleep(15.0)
            return post0(obj, ev, *a)
        G.QMouseEvent, G.QPointingDevice, C.QCoreApplication.postEvent = EspEv, EspDisp, staticmethod(post)
    app, jan = QApplication.instance() or QApplication(sys.argv[:1]), QMainWindow()
    jan.resize(640, 480)
    jan.move(0, 0)
    jan.show()
    for _ in range(30):
        app.processEvents()
        time.sleep(0.01)
    import fluxo_a
    import lote
    fluxo_a.api = lambda nome, *a, **k: time.sleep(0.001)  # o "comando" só espera (na forma 2, embrulhado pelo fatiador)
    return app, jan, lote, agora


class _F:  # o `f` de ensaio: só o que `medir` usa do FluxoA
    def __init__(s, app, jan, agora, dur, bombear_ok=True):
        s._app, s.janela_principal, s.agora, s.dur, s.ok, s.vivas = app, jan, agora, dur, bombear_ok, set()
        s.cena = types.SimpleNamespace(relogio=lambda: [])

    def executar_detalhado(s, cmd):
        import fluxo_a
        t = time.perf_counter()
        while time.perf_counter() - t < s.dur:
            fluxo_a.api("esperar")
            s.vivas |= {th.name for th in threading.enumerate()}
        return [], {"sequencia": None, "t0_ms": s.agora(), "t_comando_ms": s.agora(), "criados": []}

    def _bombear(s, cond=None, ms=0):  # como FluxoA._bombear (thread da janela); bombear_ok=False: tempo esgotado
        fim = time.perf_counter() + ms / 1000
        while s.ok:
            s._app.processEvents()
            if cond is None or cond():
                return True
            if time.perf_counter() >= fim:
                return False
            time.sleep(0.0005)
        return False


def _medir(lote, f, forma, mouse=True, t0=None):  # uma chamada de medir e o que o espião viu nela; t0=inf: medir que deve falhar
    ini, jan, r = (len(REG["ev"]), len(REG["post"])), threading.get_ident(), {"mouse": []}
    try:
        r = lote.medir(f, forma, 10, cmd={"cmd": "ensaio"}, mouse=mouse)
        exc = None
    except Exception as e:
        if t0 is None:
            raise
        exc = [type(e).__name__, str(e)]
    t0, evs, posts = r.get("t0_ms", t0), REG["ev"][ini[0]:], REG["post"][ini[1]:]
    ok = {id(e) for th, t, e in evs if th == jan and t < t0}
    return r, {"n_ev": len(evs), "ev_fora_da_janela": sum(th != jan for th, _, _ in evs), "ev_depois_t0": sum(t >= t0 for _, t, _ in evs), "excecao": exc,
               "disp_fora_da_janela": sum(th != jan for th in REG["disp"]), "n_post": len(posts), "post_threads": sorted({p[0] for p in posts}),
               "post_na_janela": sum(p[1] == jan for p in posts), "post_sem_registro": sum(p[2] not in ok for p in posts), "n_mouse": len(r["mouse"]),
               "post_repetido": len(posts) - len({p[2] for p in posts}), "fora_de_ordem": sum(p[3] != k for k, p in enumerate(posts)), "vivas": sorted(f.vivas)}


def c_espiao(res, dur="1.0", mouse="1"):  # regra 1 no ritmo real (relógio de ensaio = de verdade), formas 1 e 2; mouse=0: controle
    app, jan, lote, agora = _ambiente()
    return {str(fm): _medir(lote, _F(app, jan, agora, float(dur)), fm, mouse == "1")[1] for fm in (1, 2)}


def c_falha(res, caso):  # medir que tem de falhar com RuntimeError clara
    app, jan, lote, agora = _ambiente(vel=1e5 if caso == "falta" else 1.0)  # falta: 0,5 s reais = 50.000 s de relógio (~2,5 milhões de eventos)
    REG["segurar"] = caso == "vivo"
    t = time.perf_counter()
    res = _medir(lote, _F(app, jan, agora, 0.3 if caso == "vivo" else 0.5, bombear_ok=caso != "bombear"), 1, t0=math.inf)[1]
    return dict(res, s=time.perf_counter() - t)


def c_queda(res, segundos):  # item 3 do contrato: SEM espião (a subclasse muda o caminho do destrutor), ponteiro se mexendo
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtGui import QCursor
    app, jan, lote, agora = _ambiente(vel=100.0, espiao=False)
    lote.PARADO_MS = 50  # só neste subprocesso: a fase parada não mede nada aqui
    c, i, tm = jan.mapToGlobal(jan.rect().center()), [0], QTimer()

    def mexe():
        i[0] += 1
        QCursor.setPos(QPoint(int(c.x() + 200 * math.cos(i[0] * 0.3)), int(c.y() + 150 * math.sin(i[0] * 0.3))))
    tm.setInterval(1)
    tm.timeout.connect(mexe)
    tm.start()
    fim, res["rodadas"], res["eventos"] = time.perf_counter() + float(segundos), 0, 0
    while time.perf_counter() < fim:
        r = lote.medir(_F(app, jan, agora, 0.2), 1, 10, cmd={"cmd": "ensaio"})  # 0,2 s x 100 = 20 s de relógio: ~1.000 eventos
        res["rodadas"], res["eventos"] = res["rodadas"] + 1, res["eventos"] + len(r["mouse"])
    return dict(res, ponteiro=i[0])


# ---------- testes ----------
@pytest.fixture(scope="module")
def tela():
    if not (aux.PASTA / "lote.py").is_file():
        pular("prototypes/s04/fluxo_a/lote.py ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    return lambda nome, *a, limite=120: caso(nome, *a, alvo=ESTE, limite=limite)


def test_t15g_regra_1_todo_evento_nasce_na_thread_da_janela_antes_de_t0(tela):
    for forma, e in tela("espiao").items():
        assert e["n_mouse"] >= 40 and e["n_mouse"] <= e["n_post"] <= e["n_mouse"] + 1, f"forma {forma}: {e}"
        assert e["ev_fora_da_janela"] == 0 and e["ev_depois_t0"] == 0, f"forma {forma}: QMouseEvent construído fora da thread da janela ou depois de t0: {e}"
        assert e["disp_fora_da_janela"] == 0, f"forma {forma}: dispositivo tomado fora da thread da janela: {e}"
        assert 3001 <= e["n_ev"] <= 90001, f"forma {forma}: pré-alocação de {e['n_ev']} eventos (contrato: de 3.001 a 90.001 por rodada)"
        assert e["post_threads"] == ["lote-mouse"] and e["post_na_janela"] == 0, f"forma {forma}: só a thread lote-mouse posta o mouse: {e}"
        assert e["post_sem_registro"] == e["post_repetido"] == e["fora_de_ordem"] == 0, f"forma {forma}: postado = o k-ésimo pré-construído, sem cópia nem reuso: {e}"


def test_t15g_controle_sem_postador(tela):
    for forma, e in tela("espiao", 0.5, 0).items():
        assert e["n_mouse"] == e["n_ev"] == e["n_post"] == 0 and "lote-mouse" not in e["vivas"], f"forma {forma}: o controle (mouse=False) não tem postador: {e}"


def test_t15g_regra_2_eventos_acabaram_falha_clara(tela):
    r = tela("falha", "falta", limite=40)
    assert r["excecao"] and r["excecao"][0] == "RuntimeError" and "acabaram" in r["excecao"][1], f"faltaram eventos e medir não falhou com mensagem clara: {r}"
    assert r["post_repetido"] == r["post_sem_registro"] == 0 and r["n_post"] <= r["n_ev"] <= 90001, f"reciclou ou postou evento não pré-alocado: {r}"


def test_t15g_regra_3_postador_vivo_depois_do_join_falha_clara(tela):
    r = tela("falha", "vivo")
    assert r["excecao"] and r["excecao"][0] == "RuntimeError" and "lote-mouse" in r["excecao"][1] and r["s"] < 12, f"postador vivo depois de join(5) não foi acusado: {r}"


def test_t15g_regra_3_bombear_sem_sucesso_falha_clara(tela):
    r = tela("falha", "bombear")
    assert r["excecao"] and r["excecao"][0] == "RuntimeError" and "_bombear" in r["excecao"][1], f"_bombear devolveu False e medir não falhou com mensagem clara: {r}"


def test_t15g_queda_postador_rapido_com_ponteiro_se_mexendo(tela):  # cair = "o caso queda CAIU" (código 134/139 no Linux)
    r = tela("queda", 15)
    assert r["rodadas"] >= 5 and r["eventos"] >= 8000 and r["ponteiro"] >= 1000, f"o ensaio de queda não exercitou o postador: {r}"


CONST = {"FATIA_MS": 8, "PULSO_MS": 10, "MOUSE_MS": 20, "PARADO_MS": 2000, "BLOCO_MALHAS": 25, "Y_MOUSE": -777.0}
INTACTAS = {  # nome -> sha256 (16 primeiros) do código-fonte, linhas sem espaço à direita (main de 2026-10-16, commit 128af53)
            "lote_cmd": "d5bb3138e24a7d04", "_caminhos": "64f71a63eeeb8595", "preparar": "539e2f9d37df2760", "_Fatiador": "0ddc417fe50fb112",
            "_CenaFatiada": "b4174a96f4de1130", "_forma_1": "f755f6e78f911dc8", "_forma_2": "6b98d53c60b27427", "_maior": "e0460bb707cd66ad",
            "resumo": "01448951e43bafbe", "main": "767c40caa9d53267"}
MEDIR = ("QTimer.singleShot(PARADO_MS, loop.quit)", "pulso.setInterval(PULSO_MS)", 'name="lote-mouse"', "poster.join(5)", "ag = t0 + k * MOUSE_MS",
         "if ev.type() == QEvent.MouseMove and obj is janela and ev.position().y() == Y_MOUSE:", "lista[int(ev.position().x())][2] = agora()",
         'det["t_comando_ms"]) if det.get("sequencia") is not None else det["t_comando_ms"]', "f._bombear(lambda: all(m[2] is not None for m in mouse_ev), 5000)")


def test_t15g_reguas_constantes_e_resto_de_lote_py_intactos():
    if not (aux.PASTA / "lote.py").is_file():
        pular("prototypes/s04/fluxo_a/lote.py ausente")
    import lote
    h = {k: hashlib.sha256("\n".join(x.rstrip() for x in inspect.getsource(getattr(lote, k)).splitlines()).encode()).hexdigest()[:16] for k in INTACTAS}
    assert {k: getattr(lote, k) for k in CONST} == CONST and h == INTACTAS, "nenhuma constante muda; fora de medir e do __main__, lote.py não muda"
    assert [x for x in MEDIR if x not in inspect.getsource(lote.medir)] == [], "em medir só mudam o bloco do postador e o fim da rodada"
    assert "faulthandler.enable()" in (aux.PASTA / "lote.py").read_text(encoding="utf-8").split('if __name__ == "__main__":')[-1], "regra 4: faulthandler.enable() no __main__"


if __name__ == "__main__":
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 120)) - 10, exit=True)
    try:
        saida = globals()["c_" + sys.argv[1]]({}, *sys.argv[2:])
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + __import__("json").dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
