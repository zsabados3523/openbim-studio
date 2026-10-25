# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do roteiro R fora da thread da janela, sem `t_painel_ms`.
Desde a versão com threads, `editar_propriedades` com janela e fora da thread dela não traz `t_painel_ms` (não há pintura medida). Regra: sem o dado,
a meta M3 fica NÃO MEDIDA (ou falha explícita), nunca aprovada calada; nada de afrouxar.
1. `fluxo_a._metas(passos)`: M3 só é calculada quando TODAS as repetições do passo 4a têm `t_painel_ms` (nunca de um subconjunto).
   Faltando em qualquer uma: M3 = objeto explícito {"passo": "4a", "n": <repetições do 4a>, "limite_ms": 50, "medida": False, "ok": False,
   "motivo": <texto>}, SEM nenhum tempo (nenhuma chave terminada em `_ms` além de `limite_ms`). Nunca `None` (None = "não há passo 4a", como hoje).
   Com todas presentes, ou sem passo 4a: o resultado é IDÊNTICO ao de hoje (cópia congelada da conta em `metas_hoje`). M2, M2b, M4, M5 nunca mudam.
2. `executar_roteiro` rodado numa thread que não é a da janela (com janela) grava o `medicao.json` (hoje morre com KeyError antes de gravar), as
   repetições do 4a NÃO têm a chave `t_painel_ms` (nada de valor de enchimento: o juiz aceitaria `t_painel_ms = t_comando_ms` como M3 de ~1 ms) e
   `metas.M3` é o objeto do item 1. Controle: o mesmo roteiro na thread da janela tem `t_painel_ms` e metas iguais às de hoje.
3. Juiz (`prototypes/s04/medir_s04.py`, NÃO muda nesta tarefa): medicao sem `t_painel_ms` no 4a (todas ou uma repetição; em A ou em B; régua
   virtual ou estrita) é ENTRADA INVÁLIDA, código 2, citando `passo 4a` e `t_painel_ms`, nunca traceback, nunca aprovação (regra (iii) do
   cabeçalho de tests/test_s04_metas.py). Estes casos já passam hoje: são trava de regressão.
GUARDA: os casos sem janela rodam sempre; os de janela rodam em SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com
OBIM_S04_TELA_VIRTUAL=1) e pulam sem obimcore; com OBIM_S04_T15_OBRIGATORIO=1 todo pulo vira falha."""
import copy
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

import numpy as np
import pytest
import s04_fluxo_aux as aux
from s04_fluxo_aux import FIRE

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T15_OBRIGATORIO") == "1"
TEMPOS = ("mediana_ms", "p95_ms", "max_ms")


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! painel ausente: {msg} (teste do painel ausente NÃO FOI EXECUTADO) !!!\n")


def metas_hoje(passos, com_m3=True):  # cópia CONGELADA de fluxo_a._metas; com_m3=False omite só a conta do M3
    por = {p["id"]: p["reps"] for p in passos}
    meta = lambda pid, f, lim: (lambda v: {"passo": pid, "n": len(v), "mediana_ms": float(np.median(v)), "p95_ms": float(np.percentile(v, 95)), "max_ms": float(v.max()), "limite_ms": lim,  # noqa: E731
                                           "ok": bool(np.percentile(v, 95) < lim)} if len(v) else None)(np.array([f(r) for r in por.get(pid, [])], float))
    m = {"M2": meta("3", lambda r: r["ms_total"], 200), "M2b": meta("4b", lambda r: r["ms_total"], 200), "M4": meta("5b", lambda r: r["ms_total"], 20000), "M5": None, "M1": None, "M6": None}
    if com_m3:
        m["M3"] = meta("4a", lambda r: r["t_painel_ms"] - r["t0_ms"], 50)
    if por.get("5b") and por.get("4c"):
        lote, parado = por["5b"][0], por["4c"][0]
        t, tp, ini, fim = (np.array([x[0] for x in lote["relogio"]], float), np.array([x[0] for x in parado["relogio"]], float), lote["t0_ms"], lote["t_quadro_ms"])
        jan = [int(((t >= ini + 1000 * k) & (t < ini + 1000 * (k + 1))).sum()) for k in range(int((fim - ini) // 1000))]
        maior, par = float(np.diff(np.r_[ini, t, fim]).max()), float(np.diff(tp).max()) if len(tp) > 1 else 0.0
        m["M5"] = {"passo": "5b", "n": len(t), "limite_ms": 200, "quadros_por_janela_min": min(jan) if jan else None, "janelas": jan, "maior_intervalo_ms": maior, "maior_intervalo_parado_ms": par,
                   "ok": bool(all(n >= 20 for n in jan) and (jan or len(t) >= 20 * (fim - ini) / 1000) and maior < 200 and maior <= 3 * max(33.3, par))}
    return m


def conferir_nao_medida(m3, n):  # o objeto explícito do item 1
    assert isinstance(m3, dict), f"M3 sem t_painel_ms tem de ser o objeto explícito 'não medida', não {m3!r} (None = sem passo 4a)"
    assert m3.get("medida") is False and m3.get("ok") is False and m3.get("passo") == "4a" and m3.get("n") == n and m3.get("limite_ms") == 50, m3
    assert isinstance(m3.get("motivo"), str) and m3["motivo"].strip(), f"falta o motivo em texto: {m3}"
    assert {k for k in m3 if k.endswith("_ms")} == {"limite_ms"}, f"M3 não medida não pode trazer tempo nenhum: {m3}"
    json.dumps(m3, allow_nan=False)  # nada de NaN nem tipo numpy


def sem_painel(passos):  # tira o t_painel_ms de todas as repetições do 4a
    for p in passos:
        for r in p["reps"] if p["id"] == "4a" else []:
            r.pop("t_painel_ms", None)
    return passos


# ---------- 1. `_metas`, função pura (roda sempre) ----------
def passos_sint():  # 5 repetições em 3, 4a e 4b; 4c e 5b com relógio de 16 ms; tempos variados (mediana, p95 e máximo distintos)
    rep = lambda t0, ms, **k: {"t0_ms": t0, "t_comando_ms": t0 + 1.0, "t_quadro_ms": t0 + ms, "ms_total": ms, **k}  # noqa: E731
    quad = lambda ini, fim: [[ini + 16.0 * i, i] for i in range(1, int((fim - ini) / 16.0))]  # noqa: E731
    return [{"id": "3", "cmd": "criar_parede", "reps": [rep(100.0 * k, 20.0 + 7 * k) for k in range(5)]},
            {"id": "4a", "cmd": "editar_propriedades", "reps": [rep(1000.0 + 100 * k, 1.0, t_painel_ms=1000.0 + 100 * k + 9.0 + 3 * k * k) for k in range(5)]},
            {"id": "4b", "cmd": "mudar_comprimento", "reps": [rep(2000.0 + 100 * k, 30.0 + 11 * k) for k in range(5)]},
            {"id": "4c", "cmd": "esperar", "reps": [rep(3000.0, 3000.0, relogio=quad(3000.0, 6000.0))]},
            {"id": "5b", "cmd": "criar_paredes_lote", "reps": [rep(7000.0, 2500.0, relogio=quad(7000.0, 9500.0))]}]


@pytest.fixture
def fa():
    if not (aux.PASTA / "fluxo_a.py").is_file():
        pular("prototypes/s04/fluxo_a/fluxo_a.py ausente")
    import fluxo_a
    return fluxo_a


def test_t15e_metas_com_t_painel_em_todas_identicas_as_de_hoje(fa):  # trava de regressão (passa hoje)
    ps = passos_sint()
    assert fa._metas(copy.deepcopy(ps)) == metas_hoje(ps)


def test_t15e_metas_sem_passo_4a_continuam_com_m3_none(fa):  # trava de regressão (passa hoje): None = "não há passo 4a"
    ps = [p for p in passos_sint() if p["id"] != "4a"]
    assert fa._metas(copy.deepcopy(ps)) == metas_hoje(ps) and fa._metas(ps)["M3"] is None


@pytest.mark.parametrize("quais", ["todas", "so_a_terceira", "so_a_primeira"])
def test_t15e_metas_sem_t_painel_m3_nao_medida_e_o_resto_igual(fa, quais):
    ps = passos_sint()
    reps = next(p for p in ps if p["id"] == "4a")["reps"]
    for k in {"todas": range(5), "so_a_terceira": [2], "so_a_primeira": [0]}[quais]:
        reps[k].pop("t_painel_ms")
    try:
        m = fa._metas(copy.deepcopy(ps))
    except KeyError as e:
        pytest.fail(f"_metas levantou KeyError {e!r} sem t_painel_ms: o roteiro morreria antes de gravar o medicao.json")
    conferir_nao_medida(m.get("M3", "AUSENTE"), 5)
    assert {k: v for k, v in m.items() if k != "M3"} == metas_hoje(ps, com_m3=False), "sem t_painel_ms, só o M3 muda"


# ---------- 3. juiz: entrada inválida, código 2 (passa hoje; medir_s04.py não muda) ----------
@pytest.fixture(scope="module")
def juiz():
    import test_s04_metas as tm
    if not tm.MEDIR.is_file():
        pular(f"{tm.MEDIR} ausente")
    return tm


def tira(m, quais):
    reps = next(p for p in m["passos"] if p["id"] == "4a")["reps"]
    for r in (reps if quais == "todas" else [reps[7]]):
        r.pop("t_painel_ms")
    return m


@pytest.mark.parametrize("lado,quais,estrito", [("a", "todas", False), ("a", "uma", False), ("a", "todas", True), ("b", "todas", False), ("b", "uma", False)],
                         ids=["A sem em todas", "A sem em uma", "A sem em todas, estrita", "B sem em todas", "B sem em uma"])
def test_t15e_juiz_sem_t_painel_e_entrada_invalida_nunca_aprova(juiz, tmp_path, lado, quais, estrito):
    a = juiz.med() if lado == "b" else tira(juiz.med(), quais)
    b = tira(juiz.med("B"), quais) if lado == "b" else None
    rc, js, p = juiz.avaliar(tmp_path, a, b, estrito=estrito)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr, (rc, p.stdout[-300:], p.stderr[-600:])
    assert "passo 4a" in p.stderr and "t_painel_ms" in p.stderr, p.stderr[-600:]
    assert js is None or not js.get("aprovado"), "sem t_painel_ms o juiz nunca aprova"


def test_t15e_juiz_controle_com_t_painel_aprova(juiz, tmp_path):  # os casos acima não são vazios: a mesma medicao com o dado passa
    rc, js, p = juiz.avaliar(tmp_path, juiz.med(), estrito=True)
    assert rc == 0 and js["aprovado"] and js["metas"]["M3"]["ok"], (rc, p.stderr[-400:])


# ---------- 2. roteiro real com janela: subprocesso sob xvfb-run ----------
def roteiro(pasta, tipo):  # o roteiro R em miniatura (3 repetições; lote de 20)
    par = {"tipo": tipo, "comprimento": 4.0, "altura": 2.8, "espessura": 0.15}
    ps = [{"id": "2", "cmd": "criar_tipo", "nome": tipo, "camadas_m": [0.02, 0.11, 0.02]}, {"id": "3", "cmd": "criar_parede", "n": 3, **par}, {"id": "3b", "cmd": "enquadrar"},
          {"id": "4a", "cmd": "editar_propriedades", "n": 3, "alvo": {"passo": "3"}, "nome": "Parede R-{r}", "propriedades": {FIRE: "R60"}},
          {"id": "4b", "cmd": "mudar_comprimento", "n": 3, "alvo": {"passo": "3"}, "comprimento": 5.0}, {"id": "4c", "cmd": "esperar", "ms": 300},
          {"id": "5b", "cmd": "criar_paredes_lote", "quantidade": 20, **par}]
    arq = Path(pasta) / f"roteiro_{tipo}.json"
    arq.write_text(json.dumps({"versao": 1, "passos": ps}), encoding="utf-8")
    return arq


def c_roteiro(res):
    import fluxo_a
    from PySide6.QtWidgets import QApplication
    saida = Path(tempfile.mkdtemp())
    f = fluxo_a.FluxoA(None, janela=True, saida=saida)
    arq = saida / "medicao.json"
    f.executar_roteiro(roteiro(saida, "PJAN"))  # controle: na thread da janela
    res["janela"] = json.loads(arq.read_text(encoding="utf-8"))
    arq.unlink()
    out = {}

    def roda():
        try:
            out["ret"] = json.loads(json.dumps(f.executar_roteiro(roteiro(saida, "POUT"))))
        except BaseException:
            out["erro"] = traceback.format_exc()
    t = threading.Thread(target=roda)
    t.start()
    fim = time.perf_counter() + 120
    while t.is_alive() and time.perf_counter() < fim:
        QApplication.processEvents()
        time.sleep(0.001)
    res["outra_viva"], res["outra_erro"], res["outra_ret"] = t.is_alive(), out.get("erro"), out.get("ret")
    res["outra"] = json.loads(arq.read_text(encoding="utf-8")) if arq.is_file() else None
    t.is_alive() or f.fechar()
    return res


@pytest.fixture(scope="module")
def real():
    if not (aux.PASTA / "fluxo_a.py").is_file():
        pular("prototypes/s04/fluxo_a/fluxo_a.py ausente")
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    return caso("roteiro", alvo=ESTE, limite=300)


def reps_4a(med):
    return next(p for p in med["passos"] if p["id"] == "4a")["reps"]


def test_t15e_roteiro_na_thread_da_janela_continua_igual(real):  # controle
    med = real["janela"]
    assert len(reps_4a(med)) == 3 and all(r["t_painel_ms"] >= r["t_comando_ms"] for r in reps_4a(med)), reps_4a(med)
    assert med["metas"] == metas_hoje(med["passos"]) and med["metas"]["M3"]["n"] == 3, med["metas"]


def test_t15e_roteiro_fora_da_thread_da_janela_grava_medicao_sem_t_painel_e_m3_nao_medida(real):
    assert not real["outra_viva"] and real["outra_erro"] is None, f"executar_roteiro fora da thread da janela caiu ou travou:\n{real['outra_erro']}"
    med = real["outra"]
    assert med is not None, "o medicao.json não foi gravado"
    assert real["outra_ret"] == med, "o dict devolvido difere do medicao.json gravado"
    painel = [(p["id"], r["r"]) for p in med["passos"] for r in p["reps"] if "t_painel_ms" in r]
    assert painel == [], f"fora da thread da janela não há pintura medida: nenhuma repetição pode trazer t_painel_ms (nem valor de enchimento): {painel}"
    assert len(reps_4a(med)) == 3
    conferir_nao_medida(med["metas"]["M3"], 3)
    assert {k: v for k, v in med["metas"].items() if k != "M3"} == metas_hoje(med["passos"], com_m3=False), "fora da thread da janela, só o M3 muda"


if __name__ == "__main__":  # python este_arquivo.py roteiro  (sob xvfb-run)
    sys.path[:0] = [str(aux.PASTA), str(aux.RAIZ / "app"), str(aux.RAIZ / "prototypes")]
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
