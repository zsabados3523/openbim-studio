# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da F0-S04-T15b: formas 1 e 2 do LOTE_OPUS_9 §2.3, M5 e M5b (cartão F0-S04-T15b; contrato em prototypes/s04/fluxo_a/CONTRATO.md, seção T15).
Forma 1: o lote (`criar_paredes_lote`) roda numa thread Python e a thread da janela fica em `QEventLoop.exec()`. Forma 2: o lote roda na thread da janela,
cedendo (`processEvents`) depois de cada operação quando passaram 8 ms desde a última cessão; operação = cada chamada de `fluxo_a.api`, cada bloco de até
25 GlobalIds de `obimcore.malhas` e `Cena.atualizar`. Nenhuma chamada da API é partida para melhorar o número.
M5 (relógio do núcleo): quadros apresentados entre t0 (início do lote) e t1 (1o quadro com a sequência do lote). M5b: eventos de mouse sintéticos agendados a cada
20 ms desde t0 (agendado_k = t0 + 20k), postos na fila da janela principal por uma thread auxiliar; atraso = tratado - AGENDADO (não o instante em que foi
postado: um postador sem o bloqueio do interpretador esconderia a espera). Mais o pulso de 10 ms da thread da janela (o mesmo número do fluxo B).
`lote.py <saida.json> --base N --quantidade N --rodadas N` grava `threads.json`; o oráculo recalcula tudo dos dados brutos e aplica a régua abaixo.
Controle (o postador do mouse é uma 3a thread Python e disputa o bloqueio: medido, ele quase triplica a surdez da janela na forma 1): `main` roda, por forma e
rodada, uma medida SÓ com o pulso (`medir(..., mouse=False)`, grupo "controle") e outra com pulso e mouse (grupo "formas"); a comparação entre formas e a
parada usam o controle; o M5b com mouse vai ao relatório ao lado, com o tamanho do efeito.
Régua (RG-09 + lote 11): por forma, em cada rodada toda janela de 1 s com >= 20 quadros; mediana dos maiores intervalos < 100 ms (OBIM_S04_ESTRITO=1: 200);
no máximo 1 rodada com intervalo > 200 ms; mediana <= 3x max(33,3 ms, mediana do parado). Forma 2 fatia de verdade: >= 20 fatias e mediana <= 20 ms.
Parada (PROPOSTA DO OPUS, aguarda o PO; o lote 9 §2.3 diz só "registrar"): se o maior intervalo do pulso no controle (mediana das rodadas) passar de
1.000 ms nas DUAS formas, o caso falha e o cartão manda levar ao PO (lote 9 §5.1: "janela surda por mais de 1 s" faria mudar de ideia).
GUARDA: os casos com janela rodam em SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1); pulam sem lote.py ou
obimcore; com OBIM_S04_T15_OBRIGATORIO=1 todo pulo vira falha. As sentinelas da régua rodam sempre."""
import importlib.util
import json
import os
import shutil
import statistics
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pytest
import s04_fluxo_aux as aux

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T15_OBRIGATORIO") == "1"
BASE, QTD, RODADAS = int(os.environ.get("OBIM_S04_BASE", "300")), 1000, 3
MOUSE_MS, LIM_M5 = 20.0, (200.0 if aux.ESTRITO else 100.0)
CHAVES = {"forma", "quantidade", "parado", "thread_janela", "thread_lote", "t0_ms", "t1_ms", "quadros", "pulsos", "mouse", "criados", "resumo"}


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-T15b: {msg} (oráculo das formas 1 e 2 NÃO FOI EXECUTADO) !!!\n")


# ---------- conta e régua (escritas sem olhar para lote.py) ----------
def maior(ts):
    return float(np.diff(np.asarray(ts, float)).max()) if len(ts) > 1 else None


def resumo(r):
    t0, t1, q = r["t0_ms"], r["t1_ms"], r["quadros"]
    jan = [sum(1 for t in q if t0 + 1000 * k <= t < t0 + 1000 * (k + 1)) for k in range(int((t1 - t0) // 1000))]
    at = np.array([m[2] - m[0] for m in r["mouse"]], float)
    m5b = {"n": len(at), "mediana_ms": float(np.median(at)), "p95_ms": float(np.percentile(at, 95)), "max_ms": float(at.max())} if len(at) else None
    out = {"M5": {"janelas": jan, "maior_intervalo_ms": maior([t0, *q, t1]), "maior_intervalo_parado_ms": maior(r["parado"]["quadros"])}, "M5b": m5b,
           "pulso_maior_ms": maior([t0, *r["pulsos"], t1])}
    if "fatias" in r:
        fm = max(r["fatias"], key=lambda x: x["ms"])
        out["fatias"] = {"n": len(r["fatias"]), "mediana_ms": float(np.median([x["ms"] for x in r["fatias"]])), "maior_ms": fm["ms"], "maior_op": fm["op_mais_longa"]}
    return out


def regua_m5(rodadas):  # rodadas = [resumo["M5"], ...] de uma forma -> lista de erros
    mx = [r["maior_intervalo_ms"] for r in rodadas]
    med, par = statistics.median(mx), statistics.median(r["maior_intervalo_parado_ms"] for r in rodadas)
    e = [f"rodada {i}: janela de 1 s com {min(r['janelas'])} quadros (< 20)" for i, r in enumerate(rodadas) if not r["janelas"] or min(r["janelas"]) < 20]
    e += [f"mediana dos maiores intervalos {med:.0f} ms >= {LIM_M5:.0f}"] * (med >= LIM_M5)
    e += [f"{sum(x > 200 for x in mx)} rodadas com intervalo > 200 ms (no máximo 1)"] * (sum(x > 200 for x in mx) >= 2)
    e += [f"mediana {med:.0f} ms > 3x o parado {par:.0f} ms"] * (med > 3 * max(33.3, par))
    return e


def igual(a, b, cam=""):  # comparação a 1e-6 de estruturas do JSON
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), f"{cam}: chaves {sorted(a)} != {sorted(b)}"
        [igual(a[k], b[k], f"{cam}.{k}") for k in a]
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), f"{cam}: {a} != {b}"
        [igual(x, y, f"{cam}[{i}]") for i, (x, y) in enumerate(zip(a, b))]
    elif isinstance(a, float) or isinstance(b, float):
        assert a is not None and b is not None and abs(a - b) <= 1e-6, f"{cam}: {a} != {b}"
    else:
        assert a == b, f"{cam}: {a!r} != {b!r}"


def test_sentinela_regua_m5_aprova_um_pico_e_reprova_dois():
    ok = {"janelas": [60, 61], "maior_intervalo_ms": 20.0, "maior_intervalo_parado_ms": 18.0}
    assert regua_m5([ok, ok, ok]) == []
    assert resumo({"t0_ms": 0.0, "t1_ms": 10.0, "quadros": [5.0], "pulsos": [], "parado": {"quadros": [0.0, 1.0]}, "mouse": []})["M5b"] is None
    assert regua_m5([ok, dict(ok, maior_intervalo_ms=250.0), ok]) == [], "um pico isolado passa (RG-09)"
    assert regua_m5([ok, dict(ok, maior_intervalo_ms=250.0), dict(ok, maior_intervalo_ms=210.0)]), "duas rodadas acima de 200 ms reprovam"
    assert regua_m5([dict(ok, janelas=[60, 12]), ok, ok]), "janela com menos de 20 quadros reprova"
    assert regua_m5([dict(ok, maior_intervalo_ms=120.0)] * 3), "mediana >= 100 ms reprova"


def test_sentinela_resumo_conta_as_pontas_e_o_agendado():
    r = {"t0_ms": 0.0, "t1_ms": 2500.0, "quadros": [100.0 + 20 * i for i in range(100)], "pulsos": [10.0 * i for i in range(1, 250)], "parado": {"quadros": [0.0, 16.0, 40.0]},
         "mouse": [[20.0 * k, 20.0 * k + 30, 20.0 * k + 35] for k in range(126)]}
    s = resumo(r)
    assert s["M5"]["maior_intervalo_ms"] == 420.0, "o intervalo do último quadro até t1 conta (pontas incluídas)"
    assert s["M5"]["janelas"] == [45, 50] and s["M5b"]["max_ms"] == 35.0 and s["pulso_maior_ms"] == 10.0


def test_t15b_resumo_de_lote_py_em_dados_sinteticos():  # `lote.resumo(r)` é função pura: a mesma conta do oráculo, com pontas que mandam no resultado
    if not (aux.PASTA / "lote.py").is_file():
        pular("prototypes/s04/fluxo_a/lote.py ausente")
    import lote
    r = {"t0_ms": 0.0, "t1_ms": 2500.0, "quadros": [300.0 + 20 * i for i in range(80)], "pulsos": [400.0 + 10 * i for i in range(100)], "parado": {"quadros": [0.0, 16.0, 40.0]},
         "mouse": [[20.0 * k, 20.0 * k + 3, 20.0 * k + (900 if k == 7 else 35)] for k in range(126)],
         "fatias": [{"ms": 8.5, "op_mais_longa": "root.create_entity"}] * 30 + [{"ms": 650.0, "op_mais_longa": "spatial.assign_container"}]}
    igual(resumo(r), lote.resumo(r), "lote.resumo")
    r2 = dict(r, mouse=[[m[0], m[1], m[1] + 35] for m in r["mouse"]])
    igual(resumo(r2), lote.resumo(r2), "lote.resumo (atraso conta do agendado, não do postado)")
    r3 = dict(r, mouse=[])
    igual(resumo(r3), lote.resumo(r3), "lote.resumo sem mouse (controle): M5b None")


# ---------- subprocesso (python este_arquivo.py <caso> ...) ----------
def c_lote(res, base, qtd, rodadas):
    import lote
    saida = Path(tempfile.mkdtemp()) / "threads.json"
    res["ret"] = lote.main([str(saida), "--base", str(base), "--quantidade", str(qtd), "--rodadas", str(rodadas)])
    res["arquivo"] = json.loads(saida.read_text(encoding="utf-8"))
    return res


def c_trava(res, base):  # durante o lote, um tratador na thread da janela tenta mudar o modelo sem esperar: ModeloOcupado, sem travar; comando livre passa
    import fluxo_a
    import gerar_modelo_grande
    import lote
    from PySide6.QtCore import QTimer
    tmp = Path(tempfile.mkdtemp())
    gerar_modelo_grande.gerar(str(tmp / "b.ifc"), paredes=int(base))
    f = lote.preparar(str(tmp / "b.ifc"), tmp / "s")
    for forma in (1, 2):
        cont = {"ocupado": 0, "outro": [], "livre": 0}

        def tenta():  # só tenta com a trava presa (durante o lote); se ela soltar bem na hora, o comando passa e é contado
            if not f.trava.locked():
                return
            try:
                f.executar(dict(aux.PAREDE), espera=0)
                cont["outro"].append("passou")
            except fluxo_a.ModeloOcupado:
                cont["ocupado"] += 1
            except Exception as e:
                cont["outro"].append(repr(e))
            f.executar({"cmd": "esperar", "ms": 0})
            cont["livre"] += 1
        tm = QTimer()
        tm.setInterval(5)
        tm.timeout.connect(tenta)
        paredes, hist = len(f.ifc.by_type("IfcWall")), len(f.historico)
        tm.start()
        r = lote.medir(f, forma, 300)
        tm.stop()
        res[str(forma)] = {**cont, "paredes": len(f.ifc.by_type("IfcWall")) - paredes, "hist": len(f.historico) - hist, "thread": r["thread_lote"] == r["thread_janela"]}
    f.fechar()
    return res


@pytest.fixture(scope="module")
def tela():
    if not (aux.PASTA / "lote.py").is_file():
        pular("prototypes/s04/fluxo_a/lote.py ausente")
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    return caso


@pytest.fixture(scope="module")
def med(tela):
    r = tela("lote", BASE, QTD, RODADAS, alvo=ESTE, limite=900)
    assert r["ret"] == r["arquivo"], "lote.main devolve o mesmo dicionário que grava"
    return r["arquivo"]


def rodadas(med, forma, grupo="formas"):
    return med[grupo][str(forma)]


GRUPOS = ("formas", "controle")


def test_t15b_estrutura_do_threads_json(med):
    assert med["versao"] == 1 and med["base"] == BASE and med["quantidade"] == QTD and med["rodadas"] == RODADAS and set(med["formas"]) == set(med["controle"]) == {"1", "2"}
    for forma, g in ((f, g) for f in (1, 2) for g in GRUPOS):
        rs = rodadas(med, forma, g)
        assert len(rs) == RODADAS
        for r in rs:
            assert (r["mouse"] == []) == (g == "controle"), f"{g}: o controle não tem mouse; as formas têm"

            assert CHAVES <= set(r) and r["forma"] == forma and r["quantidade"] == QTD and r["criados"] == QTD, sorted(r)
            assert ("fatias" in r) == (forma == 2), "só a forma 2 tem fatias"
            t0, t1 = r["t0_ms"], r["t1_ms"]
            assert t0 < t1 and r["quadros"] == sorted(r["quadros"]) and all(t0 <= t <= t1 for t in r["quadros"]) and len(r["quadros"]) > 0
            p = r["parado"]
            assert p["t1_ms"] <= t0 and p["t1_ms"] - p["t0_ms"] >= 1900 and all(p["t0_ms"] <= t <= p["t1_ms"] for t in p["quadros"]) and len(p["quadros"]) >= 20
            assert r["pulsos"] == sorted(r["pulsos"]) and all(t0 <= t <= t1 for t in r["pulsos"])


def test_t15b_forma_1_em_outra_thread_e_forma_2_na_da_janela(med):
    for g in GRUPOS:
        assert all(r["thread_lote"] != r["thread_janela"] for r in rodadas(med, 1, g)), "forma 1: o lote tem de rodar numa thread Python que não é a da janela"
        assert all(r["thread_lote"] == r["thread_janela"] for r in rodadas(med, 2, g)), "forma 2: o lote roda na thread da janela"


def test_t15b_mouse_agendado_a_cada_20_ms_e_todo_tratado(med):
    for forma in (1, 2):
        for r in rodadas(med, forma):
            m, t0, t1 = r["mouse"], r["t0_ms"], r["t1_ms"]
            assert len(m) == int((t1 - t0) // MOUSE_MS) + 1, f"forma {forma}: {len(m)} eventos para {t1 - t0:.0f} ms (todo evento agendado até t1, um a cada 20 ms)"
            for k, (ag, post, trat) in enumerate(m):
                assert abs(ag - (t0 + k * MOUSE_MS)) <= 1e-6, f"forma {forma}: evento {k} agendado em {ag}, não em t0 + 20k = {t0 + k * MOUSE_MS} (o atraso conta do AGENDADO)"
                assert trat is not None and post >= ag - 1e-6 and trat >= post, f"forma {forma}: evento {k} {m[k]}"


def test_t15b_resumo_igual_ao_recalculado(med):
    for forma, g in ((f, g) for f in (1, 2) for g in GRUPOS):
        for i, r in enumerate(rodadas(med, forma, g)):
            igual(resumo(r), r["resumo"], f"{g} forma {forma} rodada {i}")


def test_t15b_forma_2_fatia_de_verdade(med):
    for r in rodadas(med, 2) + rodadas(med, 2, "controle"):
        f = resumo(r)["fatias"]
        assert f["n"] >= 20 and f["mediana_ms"] <= 20.0, f"a forma 2 não fatiou: {f}"
        assert isinstance(f["maior_op"], str) and f["maior_op"], f"a maior fatia tem de dizer a operação que a causou: {f}"
        assert all(x["ms"] >= 0 for x in r["fatias"])
        assert len(r["pulsos"]) >= 0.25 * (r["t1_ms"] - r["t0_ms"]) / 10, f"forma 2: a janela quase não tratou eventos durante o lote ({len(r['pulsos'])} pulsos de 10 ms): cessão sem processEvents"


@pytest.mark.parametrize("forma", [1, 2])
def test_t15b_m5_na_forma(med, forma):
    e = regua_m5([resumo(r)["M5"] for r in rodadas(med, forma) + rodadas(med, forma, "controle")])
    assert not e, f"M5 reprovou na forma {forma}: {e}. M5 reprovada nas formas 1 e 2 = parar e levar ao PO (lote 9 §3)"


def test_t15b_janela_surda_mais_de_1_s_nas_duas_formas_para_e_vai_ao_po(med):  # PROPOSTA DO OPUS (aguarda o PO): mede no controle, sem o postador
    mx = {f: statistics.median(resumo(r)["pulso_maior_ms"] for r in rodadas(med, f, "controle")) for f in (1, 2)}
    assert min(mx.values()) <= 1000.0, f"a janela ficou surda por mais de 1 s nas duas formas (pulso, controle: {mx}): PARAR e levar ao PO (lote 9 §5.1)"


def test_t15b_tratador_que_muda_o_modelo_durante_o_lote_recebe_modelo_ocupado(tela):
    r = tela("trava", BASE, alvo=ESTE, limite=600)
    for forma in ("1", "2"):
        x = r[forma]
        passou = x["outro"].count("passou")
        assert len(x["outro"]) == passou <= 1 and x["ocupado"] >= 5, f"forma {forma}: comando que muda o modelo durante o lote tem de levar ModeloOcupado (espera=0), sem travar: {x}"
        assert x["livre"] >= x["ocupado"] and x["paredes"] == 300 + passou and x["hist"] == 1 + passou, f"forma {forma}: {x}"
    assert not r["1"]["thread"] and r["2"]["thread"]


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 900)) - 20, exit=True)
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + sys.argv[1]]({}, *sys.argv[2:])
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
