# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do limite de tempo de parar() (critério 1 da correção): limite em
`Motor::parar()`. Não editar este arquivo; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do teste, , depois da
implementação (só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`). Contrato:
1. `estatisticas()["paradas_atrasadas"]` (int): quantas threads de desenho foram ABANDONADAS porque a espera de `parar()` estourou o limite. Conta uma vez
   por thread (outra `parar()`, `desligar()`, `aboutToQuit` ou `~Viewport` sobre a mesma thread já abandonada não somam). 0 em operação normal.
2. Limite de `parar()`: LIMITE_S = 5 s (fixo; o teste não lê constante do módulo). Com a thread presa, `parar()` volta entre LIMITE_S - 0,5 e LIMITE_S
   + FOLGA_S (1 s), contando a espera de `~Janela` (`desligar`) quando a janela é apagada. Chamada repetida com a thread ainda presa: volta em até
   LIMITE_S + FOLGA_S. Nunca congela; o `join` só acontece se a thread terminou (abandonada: `detach`). A PRÓPRIA thread guarda um `shared_ptr` do
   `Motor` (hoje ela captura `this` cru): `~Viewport` e `~Janela` soltarem os deles não o liberam; se o último dono for a thread, o `~Motor` roda nela
   e não pode fazer `join` de si mesma (caso `soltar`: Python solta a Cena com a thread presa).
3. GANCHO DE TESTE: `obimcore.Cena.travar_desenho_teste(ms: int)` (método da ponte, como `perder_contexto` e `definir_escala_teste`). `ms > 0`: na
   próxima parada, a thread de desenho, depois de sair do laço de quadros por pedido de parada (`Fim::Parar`) e ANTES de destruir os recursos da placa
   (a `Gpu`, ponto onde o WARP trava em `~QRhi`), dorme `ms` milissegundos sem olhar `parar_`. `ms == 0` (padrão): nada muda. `ms < 0`: ValueError.
   Ao acordar, a thread termina normalmente (`terminou_`, `viva()` falso). Se ela foi abandonada, a janela e a superfície de reserva podem já ter sumido:
   não tocar em nada delas (vazar a `Gpu` de propósito é aceitável: vazamento controlado, com o contador e um aviso em `info()`).
4. Depois que o gancho solta, nada acessa objeto destruído: o subprocesso termina com código 0 e uma viewport nova volta a desenhar. Sair do programa com
   a thread ainda presa (gancho de 60 s) também termina com código 0, sem esperar o gancho.
SANITIZADOR (critério 1, "20 voltas"): OBIM_S04_T07E_VOLTAS=20 repete os casos `travar` no mesmo subprocesso (padrão 1); rodar com o módulo
compilado com -fsanitize=address, LD_PRELOAD da libasan do ambiente e ASAN_OPTIONS=detect_leaks=0 (o vazamento proposital e os do Python/Qt fariam o
LeakSanitizer sair com código != 0); se não houver, registrar no relatório que não houve sanitizador. Só local, fora do CI.
GUARDA (pula, nunca afrouxa): sem o módulo obimcore ou sem tela virtual (xvfb-run no Linux; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1),
pula; com OBIM_S04_T07E_OBRIGATORIO=1 todo pulo vira falha. Casos em SUBPROCESSO, pelos auxiliares de `test_s04_viewport.py` (nunca na tela real)."""
import importlib.util
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from test_s04_viewport import RAIZ, caso as _caso, novo, retoma, rodar  # noqa: F401

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T07E_OBRIGATORIO") == "1"
LIMITE_S, FOLGA_S = 5.0, 1.0
TRAVA_MS = 7500  # maior que o limite (força o abandono) e acorda durante o subprocesso (mostra o que a thread faz ao acordar)
VOLTAS = int(os.environ.get("OBIM_S04_T07E_VOLTAS", "1"))
VIVAS = []  # caso `sair`: o processo termina com estas viewports vivas
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! parar(): {msg} (teste do limite de parar() NÃO FOI EXECUTADO) !!!\n")


@pytest.fixture(scope="module")
def tela():
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    import obimcore
    if not all(hasattr(getattr(obimcore, "Cena", None), m) for m in ("parar", "viva", "estatisticas", "viewport_ptr")):
        pular("obimcore.Cena sem parar/viva/estatisticas/viewport_ptr")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")


# ---------- testes ----------
def test_contador_existe_e_fica_em_zero_em_operacao_normal(tela):
    r = caso("normal")
    assert r["desenhou"], f"a viewport não chegou a desenhar: {r}"
    assert r["atrasadas"] == [0, 0, 0, 0], f"paradas_atrasadas deve ser 0 sem trava (parar, janela x2, contêiner): {r}"
    assert r["parar_s"] < LIMITE_S and not r["viva"], f"parar() normal não pode chegar ao limite: {r}"


@pytest.mark.parametrize("modo", ["parar", "janela", "soltar"])
def test_parar_volta_no_limite_com_a_thread_presa_e_conta_uma_vez(tela, modo):
    r = caso("travar", modo, limite=90 + 25 * VOLTAS)
    assert len(r["voltas"]) == VOLTAS, r
    for i, v in enumerate(r["voltas"]):
        assert v["desenhou"], f"volta {i}: a viewport não chegou a desenhar: {v}"
        assert LIMITE_S - 0.5 <= v["parar_s"] <= LIMITE_S + FOLGA_S, f"volta {i} ({modo}): a 1ª parada levou {v['parar_s']:.2f} s: {v}"
        assert v["n1"] == 1, f"volta {i} ({modo}): paradas_atrasadas depois do estouro = {v['n1']} (exige 1): {v}"
        assert v["parar2_s"] <= LIMITE_S + FOLGA_S, f"volta {i} ({modo}): a 2ª parada (thread ainda presa) levou {v['parar2_s']:.2f} s: {v}"
        if modo != "soltar":
            assert v["n2"] == 1 and v["n3"] == 1, f"volta {i} ({modo}): o abandono conta uma vez por thread: {v}"
            assert not v["viva"], f"volta {i} ({modo}): depois que o gancho soltou, a thread devia ter terminado: {v}"
    assert r["final_ok"] and r["final_atrasadas"] == 0, f"depois do abandono uma viewport nova não voltou a desenhar limpa: {r}"


def test_sair_com_a_thread_presa_nao_congela(tela):
    r = caso("sair", limite=60)  # caso(): código 0 e resultado; estourar 60 s (gancho de 60 s) = travou
    assert LIMITE_S - 0.5 <= r["parar_s"] <= LIMITE_S + FOLGA_S and r["n"] == 1, r


# ---------- casos (rodam no subprocesso) ----------
def c_normal(res):
    import shiboken6
    cs = []
    c, w, _ = novo(30)
    res["desenhou"] = yield from retoma(c, 5)
    t0 = time.perf_counter()
    c.parar()
    res["parar_s"], res["viva"] = time.perf_counter() - t0, c.viva()
    cs.append(c)
    w.close()
    for i in range(2):  # janela apagada com a thread rodando e sem parar() (os dois jeitos do caso `destruir` do test_s04_viewport)
        c, w, _ = novo(30)
        yield from retoma(c, 5)
        w.close()
        shiboken6.delete(w) if i else w.deleteLater()
        yield 300
        cs.append(c)
    c, w, cont = novo(30)  # só o contêiner some
    yield from retoma(c, 5)
    cont.setParent(None)
    shiboken6.delete(cont)
    yield 300
    cs.append(c)
    w.close()
    res["atrasadas"] = [x.estatisticas()["paradas_atrasadas"] for x in cs]


def c_travar(res, modo):
    import shiboken6
    res["voltas"] = []
    for _ in range(VOLTAS):
        c, w, _ = novo(30)
        v = {"desenhou": (yield from retoma(c, 5))}
        c.travar_desenho_teste(TRAVA_MS)
        t0 = time.perf_counter()
        if modo == "parar":
            c.parar()
        else:  # o caminho de desligar: ~Janela -> desligar() -> parar(), sem parar() antes
            w.close()
            shiboken6.delete(w)
        v["parar_s"] = time.perf_counter() - t0
        v["n1"] = c.estatisticas()["paradas_atrasadas"]
        t1 = time.perf_counter()
        if modo == "soltar":  # Python solta a Cena com a thread presa: ~Viewport espera e solta; o Motor só pode morrer quando a thread sair
            del c, w, _
        else:
            c.parar()  # o que `~Viewport` e `aboutToQuit` fariam com a thread ainda presa
            v["n2"] = c.estatisticas()["paradas_atrasadas"]
        v["parar2_s"] = time.perf_counter() - t1
        resta = TRAVA_MS / 1000 - (time.perf_counter() - t0)
        yield int(max(resta, 0) * 1000) + 2500  # o gancho solta; a thread acorda e termina
        if modo != "soltar":
            v["viva"], v["n3"] = c.viva(), c.estatisticas()["paradas_atrasadas"]
        if modo == "parar":
            w.close()
        res["voltas"].append(v)
        yield 200
    c, w, _ = novo(30)
    res["final_ok"] = yield from retoma(c, 10)
    res["final_atrasadas"] = c.estatisticas()["paradas_atrasadas"]
    c.parar()
    w.close()


def c_sair(res):
    c, w, cont = novo(30)
    yield from retoma(c, 5)
    c.travar_desenho_teste(60000)
    t0 = time.perf_counter()
    c.parar()
    res["parar_s"], res["n"] = time.perf_counter() - t0, c.estatisticas()["paradas_atrasadas"]
    VIVAS.append((c, w, cont))  # o programa sai com a thread ainda dormindo no gancho


if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "viewport"))
    nome, *resto = sys.argv[1:]
    import ifcopenshell  # noqa: F401  (mesma ordem do test_s04_viewport)
    import obimcore  # noqa: F401
    rodar(lambda r: globals()["c_" + nome](r, *resto))
