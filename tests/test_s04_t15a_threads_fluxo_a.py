# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do fluxo A seguro com mais de uma thread.
1. `ultimo` e `_ult_guid` são escritos com a trava do modelo presa: num comando com trava, ANTES de soltá-la (o próximo escritor resolve "ultimo" certo);
   num comando livre (sem trava), só se a trava estiver livre, pegando-a sem esperar; ocupada: não publica e não espera.
2. `executar_roteiro` conta a base (produtos com geometria) com a trava presa pela própria thread.
3. `selecionar` chamado fora da thread da janela não chama nenhum método do contêiner Qt (`_cont`) e dá o mesmo ponto que na thread da janela.
4. `editar_propriedades` fora da thread da janela (com janela) NÃO devolve `t_painel_ms` (não há pintura medida); o texto novo chega ao painel pela fila do Qt.
   Na thread da janela e sem janela (`janela=False`), nada muda (`t_painel_ms` presente e >= `t_comando_ms`).
Como se confere (determinístico): uma trava espiã no lugar de `f.trava` anota o dono e o que estava publicado na hora de soltar; um espião no lugar de `_cont`
anota a thread de cada chamada. GUARDA: os casos sem janela rodam sempre (fluxo_a.py já existe); os de janela rodam em SUBPROCESSO sob `xvfb-run`
(nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1) e pulam sem obimcore; com OBIM_S04_T15_OBRIGATORIO=1 todo pulo vira falha."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import pytest
import s04_fluxo_aux as aux
from s04_fluxo_aux import FIRE, PAREDE, TIPO

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T15_OBRIGATORIO") == "1"


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! threads do fluxo A: {msg} (teste das threads do fluxo A NÃO FOI EXECUTADO) !!!\n")


class TravaEspia:  # fica no lugar de `f.trava`: um Lock de verdade (não reentrante) que sabe quem o segura e fotografa o publicado ao soltar
    def __init__(s, f):
        s.f, s.l, s.dono, s.solturas = f, threading.Lock(), None, []

    def acquire(s, blocking=True, timeout=-1):
        ok = s.l.acquire(blocking, timeout)
        if ok:
            s.dono = threading.get_ident()
        return ok

    def release(s):
        s.solturas.append({"ult_guid": getattr(s.f, "_ult_guid", None), "ultimo": json.loads(json.dumps(s.f.ultimo))})
        s.dono = None
        s.l.release()

    def locked(s):
        return s.l.locked()

    def minha(s):
        return s.l.locked() and s.dono == threading.get_ident()

    __enter__ = lambda s: s.acquire()  # noqa: E731
    __exit__ = lambda s, *a: s.release()  # noqa: E731


@pytest.fixture
def fa():
    if not (aux.PASTA / "fluxo_a.py").is_file():
        pular("tools/s04/fluxo_a/fluxo_a.py ausente")
    import fluxo_a
    return fluxo_a


@pytest.fixture
def f(fa, tmp_path):
    g = fa.FluxoA(None, janela=False, saida=tmp_path / "saida")
    g.trava = TravaEspia(g)
    return g


# ---------- sem janela: rodam sempre ----------
@pytest.mark.parametrize("passo", ["criar_parede", "editar_propriedades", "desfazer", "refazer", "criar_paredes_lote"])
def test_t15a_comando_com_trava_publica_ultimo_antes_de_soltar_a_trava(f, passo):
    f.executar(TIPO)
    a = f.executar(PAREDE)[0]
    cmd = {"criar_parede": PAREDE, "editar_propriedades": {"cmd": "editar_propriedades", "alvo": a, "nome": "X", "propriedades": {FIRE: "R30"}},
           "desfazer": {"cmd": "desfazer"}, "refazer": {"cmd": "refazer"}, "criar_paredes_lote": dict(PAREDE, cmd="criar_paredes_lote", quantidade=3)}[passo]
    if passo == "refazer":
        f.executar({"cmd": "desfazer"})
    n = len(f.trava.solturas)
    guids, det = f.executar_detalhado(cmd)
    assert guids, "o comando tem de devolver GlobalIds (senão o caso não prova nada)"
    s = f.trava.solturas[n:]
    assert len(s) == 1, f"{passo}: a trava foi solta {len(s)} vezes no comando (exige 1)"
    assert s[0]["ult_guid"] == guids[-1], f"{passo}: ao soltar a trava `_ult_guid` era {s[0]['ult_guid']!r}, não o do comando ({guids[-1]!r}): outro escritor resolveria 'ultimo' errado"
    assert {k: s[0]["ultimo"][k] for k in ("criados", "alterados", "apagados", "geometria")} == {k: det[k] for k in ("criados", "alterados", "apagados", "geometria")}, (
        f"{passo}: ao soltar a trava `ultimo` ainda era o do comando anterior: {s[0]['ultimo']}")


def test_t15a_comando_livre_nao_espera_nem_publica_com_a_trava_ocupada(f):
    f.executar(TIPO)
    g = f.executar(PAREDE)[0]
    antes = json.loads(json.dumps(f.ultimo))
    presa, soltar = threading.Event(), threading.Event()

    def segura():
        f.trava.acquire()
        presa.set()
        soltar.wait(10)
        f.trava.release()
    t = threading.Thread(target=segura)
    t.start()
    assert presa.wait(5)
    try:
        t0 = time.perf_counter()
        r = f.executar({"cmd": "esperar", "ms": 0})
        dt = time.perf_counter() - t0
        agora = json.loads(json.dumps(f.ultimo))
    finally:
        soltar.set()
        t.join(10)
    assert r == [] and dt < 1.0, f"o comando livre esperou a trava ({dt:.2f} s): comando livre nunca espera"
    assert agora == antes and f._ult_guid == g, f"com a trava presa por outra thread o comando livre trocou `ultimo`: {agora}"
    f.executar({"cmd": "esperar", "ms": 0})  # trava livre: publica como antes (o `ultimo` de um comando livre tem listas vazias)
    assert not any(f.ultimo[k] for k in ("criados", "alterados", "apagados", "geometria")) and f._ult_guid == g


def test_t15a_contagem_da_base_com_a_trava_presa(f, tmp_path):
    f.executar(TIPO)
    [f.executar(PAREDE) for _ in range(3)]
    chamadas, orig = [], f.ifc.by_type
    f.ifc.by_type = lambda *a, **k: (chamadas.append((a[:1], f.trava.minha())), orig(*a, **k))[1]
    rot = tmp_path / "r.json"
    rot.write_text(json.dumps({"versao": 1, "passos": [{"id": "1", "cmd": "esperar", "ms": 0}]}), encoding="utf-8")
    med = f.executar_roteiro(rot)
    assert med["base"]["produtos"] == 3, med["base"]
    prod = [m for a, m in chamadas if a == ("IfcProduct",)]
    assert prod and all(prod), f"executar_roteiro leu o modelo (by_type) sem a trava presa pela própria thread: {chamadas}"
    assert not f.trava.locked(), "a trava ficou presa depois do roteiro"


# ---------- com janela: subprocesso sob xvfb-run ----------
class Espiao:  # fica no lugar de `f._cont`: anota a thread de toda chamada
    def __init__(s, real):
        s.real, s.chamadas = real, []

    def __getattr__(s, nome):
        a = getattr(s.real, nome)
        if not callable(a):
            return a

        def vigia(*args, **kw):
            s.chamadas.append((nome, threading.current_thread() is threading.main_thread()))
            return a(*args, **kw)
        return vigia


def c_janela(res):
    import fluxo_a
    from PySide6.QtWidgets import QApplication, QLabel
    f = fluxo_a.FluxoA(None, janela=True, saida=Path(tempfile.mkdtemp()))
    f.executar(TIPO)
    a = f.executar(PAREDE)[0]
    pontos, real_sel = [], f.cena.selecionar

    class Cena:  # só anota o ponto pedido à Cena
        def __getattr__(s, nome):
            return getattr(f._real_cena, nome)

        def selecionar(s, x, y):
            pontos.append((x, y, threading.current_thread() is threading.main_thread()))
            return real_sel(x, y)
    f._real_cena = f.cena
    f.cena = Cena()
    esp = f._cont = Espiao(f._cont)
    centro = {"cmd": "selecionar", "x": "centro", "y": "centro"}
    f.executar(centro)
    out = {}
    n = len(esp.chamadas)
    t = threading.Thread(target=lambda: out.setdefault("sel", f.executar(centro)))
    t.start()
    while t.is_alive():
        QApplication.processEvents()
        time.sleep(0.001)
    res["sel_outra"] = out.get("sel")
    res["cont_fora"] = [c for c in esp.chamadas[n:] if not c[1]]
    res["pontos"] = pontos
    f.cena = f._real_cena
    _, dp = f.executar_detalhado({"cmd": "editar_propriedades", "alvo": a, "nome": "Muro principal", "propriedades": {FIRE: "R30"}})
    res["det_principal"] = dp
    t = threading.Thread(target=lambda: out.setdefault("det", f.executar_detalhado({"cmd": "editar_propriedades", "alvo": a, "nome": "Muro da outra thread", "propriedades": {FIRE: "R90"}})[1]))
    t.start()
    t.join(30)
    rot = f.janela_principal.findChild(QLabel)
    fim = time.perf_counter() + 5
    while "Muro da outra thread" not in rot.text() and time.perf_counter() < fim:
        QApplication.processEvents()
        time.sleep(0.005)
    res["det_outra"], res["rotulo"] = out.get("det"), rot.text()
    f.fechar()
    return res


@pytest.fixture(scope="module")
def janela():
    if not (aux.PASTA / "fluxo_a.py").is_file():
        pular("tools/s04/fluxo_a/fluxo_a.py ausente")
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    return caso("janela", alvo=ESTE, limite=300)


def test_t15a_selecionar_fora_da_thread_da_janela_nao_toca_no_conteiner_qt(janela):
    assert janela["cont_fora"] == [], f"selecionar numa thread que não é a da janela chamou métodos do contêiner Qt: {janela['cont_fora']}"
    p = janela["pontos"]
    assert len(p) == 2 and p[0][2] and not p[1][2], f"esperado 1 selecionar na thread da janela e 1 fora: {p}"
    assert p[0][:2] == p[1][:2] and p[0][0] > 0 and p[0][1] > 0, f"o centro fora da thread da janela {p[1][:2]} difere do centro na thread da janela {p[0][:2]}"
    assert isinstance(janela["sel_outra"], list)


def test_t15a_t_painel_so_na_thread_da_janela(janela):
    dp, do = janela["det_principal"], janela["det_outra"]
    assert "t_painel_ms" in dp and dp["t_painel_ms"] >= dp["t_comando_ms"], f"na thread da janela o t_painel_ms continua: {dp}"
    assert do is not None and "t_painel_ms" not in do, f"fora da thread da janela não há pintura medida: o detalhe não pode trazer t_painel_ms ({do})"
    assert "Muro da outra thread" in janela["rotulo"], f"o texto novo não chegou ao painel pela fila do Qt: {janela['rotulo']!r}"


def test_t15a_sem_janela_t_painel_continua_em_outra_thread(f):
    f.executar(TIPO)
    a = f.executar(PAREDE)[0]
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("d", f.executar_detalhado({"cmd": "editar_propriedades", "alvo": a, "nome": "N", "propriedades": {FIRE: "R30"}})[1]))
    t.start()
    t.join(30)
    assert out["d"]["t_comando_ms"] <= out["d"]["t_painel_ms"], out


if __name__ == "__main__":  # python este_arquivo.py janela  (sob xvfb-run)
    sys.path[:0] = [str(aux.PASTA), str(aux.RAIZ / "app"), str(aux.RAIZ / "viewport")]
    import faulthandler
    faulthandler.dump_traceback_later(max(int(os.environ.get("OBIM_LIMITE", "300")) - 20, 30), exit=True)
    r = {}
    try:
        globals()["c_" + sys.argv[1]](r)
    except Exception:
        r["erro"] = traceback.format_exc()
    print("RESULTADO " + json.dumps(r, default=str))
    sys.stdout.flush()
    os._exit(0)
