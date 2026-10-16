# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da F0-S04-T15c: forma 3 e conferências (i), (ii), (iii) do LOTE_OPUS_9 §2.3 (cartão F0-S04-T15c).
`conferencias.py <saida.json> --base N --quantidade N --rodadas N` grava `conferencias.json`:
(i) `QEventLoop.exec()` ocioso solta o bloqueio do interpretador? Uma thread Python conta voltas por 1 s com a principal em `join` (referência), em `exec`
    e OCUPADA em Python (controle positivo: tem de cair para <= 0,7 da referência, senão a medida não vale). Resposta "sim" se exec/join >= 0,8; "não" se <= 0,3.
(ii) causa das paradas do F7: no lote sem janela, uma thread vigia dorme 1 ms em laço e anota quanto passou do 1 ms, por função da API em curso, com
    `sys.setswitchinterval` 0,005 (padrão) e 0,001; o módulo do IfcOpenShell importa PyEval_SaveThread?; e quais chamadas longas (>= 100 ms) soltam o
    bloqueio (abrir e gravar um IFC grande): a principal roda o MESMO laço Python antes e durante a chamada; solta se a taxa durante for >= 0,5 da de antes.
(iii) nenhum método da janela de desenho em Python: com a thread da janela presa em C com o bloqueio preso (>= 700 ms), o maior intervalo entre quadros
    apresentados fica < 50 ms (critério da T05) e >= 20 quadros por segundo; o contêiner da viewport é a classe do PySide6 (sem subclasse Python); nenhum
    arquivo do fluxo instala filtro ou liga sinal no contêiner nem subclassifica janela ou componente Qt de desenho.
Forma 3 (referência): a forma 1 com a viewport Python da S03 (`CuboViewport`, girando); quadros por `frameSubmitted`. Sem portão (espera-se que reprove);
o controle é ela desenhar parada (>= 20 quadros por segundo).
GUARDA: SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1); pula sem conferencias.py ou obimcore;
com OBIM_S04_T15_OBRIGATORIO=1 todo pulo vira falha."""
import importlib.util
import json
import os
import re
import shutil
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
FUNCOES = {"root.create_entity": QTD, "geometry.add_wall_representation": QTD, "geometry.edit_object_placement": QTD, "material.assign_material": QTD,
           "type.assign_type": 1, "spatial.assign_container": 1}


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-T15c: {msg} (oráculo das conferências NÃO FOI EXECUTADO) !!!\n")


def maior(ts):
    return float(np.diff(np.asarray(ts, float)).max()) if len(ts) > 1 else None


def c_conf(res, base, qtd, rodadas):
    import conferencias
    saida = Path(tempfile.mkdtemp()) / "conferencias.json"
    res["ret"] = conferencias.main([str(saida), "--base", str(base), "--quantidade", str(qtd), "--rodadas", str(rodadas)])
    res["arquivo"] = json.loads(saida.read_text(encoding="utf-8"))
    return res


@pytest.fixture(scope="module")
def conf():
    if not (aux.PASTA / "conferencias.py").is_file():
        pular("prototypes/s04/fluxo_a/conferencias.py ausente")
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    r = caso("conf", BASE, QTD, RODADAS, alvo=ESTE, limite=900)
    assert r["ret"] == r["arquivo"], "conferencias.main devolve o mesmo dicionário que grava"
    assert r["arquivo"]["versao"] == 1 and r["arquivo"]["base"] == BASE and r["arquivo"]["quantidade"] == QTD and r["arquivo"]["rodadas"] == RODADAS
    return r["arquivo"]


def test_t15c_i_exec_solta_o_bloqueio_com_controle_positivo(conf):
    i = conf["i"]
    assert all(isinstance(i[k], int) and i[k] > 0 for k in ("join", "exec", "ocupada")), i
    assert abs(i["razao_exec"] - i["exec"] / i["join"]) <= 1e-9 and abs(i["razao_ocupada"] - i["ocupada"] / i["join"]) <= 1e-9, i
    assert i["razao_ocupada"] <= 0.7, f"controle positivo falhou: com a principal ocupada em Python a outra thread não perdeu ritmo ({i}); a medida não distingue nada"
    esperado = "sim" if i["razao_exec"] >= 0.8 else "não" if i["razao_exec"] <= 0.3 else None
    assert esperado is not None, f"(i) inconclusivo (razão {i['razao_exec']:.2f} entre 0,3 e 0,8): repetir; se persistir, levar ao PO"
    assert i["resposta"] == esperado, i


def test_t15c_ii_modulo_importa_a_funcao_de_soltar_o_bloqueio(conf):
    import ifcopenshell
    so = next(Path(ifcopenshell.__file__).parent.glob("_ifcopenshell_wrapper*"))
    blob = so.read_bytes()
    assert conf["ii"]["importa_save_thread"] is (b"PyEval_SaveThread" in blob) and conf["ii"]["importa_restore_thread"] is (b"PyEval_RestoreThread" in blob)


def test_t15c_ii_tempo_de_bloqueio_por_funcao_nos_dois_intervalos(conf):
    iv = conf["ii"]["intervalos"]
    assert [x["intervalo_s"] for x in iv] == [0.005, 0.001], "intervalo de troca padrão (0,005 s) e menor (0,001 s), nessa ordem"
    for x in iv:
        pf = x["por_funcao"]
        for nome, n in FUNCOES.items():
            assert nome in pf and pf[nome]["n"] == n, f"intervalo {x['intervalo_s']}: {nome} com n={pf.get(nome, {}).get('n')} (esperado {n} no lote de {QTD})"
        assert x["lote_ms"] > 0 and 0 <= x["atraso_vigia_p95_ms"] <= x["atraso_vigia_max_ms"], x
        assert abs(max(v["atraso_vigia_max_ms"] for v in pf.values()) - x["atraso_vigia_max_ms"]) <= 1e-6, "o maior atraso geral tem de ser o de alguma função (ou de fora da API)"
        assert all(v["duracao_max_ms"] <= v["duracao_soma_ms"] + 1e-9 for v in pf.values() if v["n"])


def test_t15c_ii_quais_chamadas_longas_soltam_o_bloqueio(conf):
    s = conf["ii"]["solta_gil"]
    assert {"ifcopenshell.open", "file.write"} <= set(s), sorted(s)
    for nome, x in s.items():
        assert x["ms"] >= 100, f"{nome}: chamada de {x['ms']:.0f} ms (exige >= 100 ms para dizer algo)"
        assert x["solta"] is (x["taxa_principal"] >= 0.5), x


def test_t15c_iii_desenho_nao_passa_pelo_python_nem_pela_thread_da_janela(conf):
    x = conf["iii"]
    assert x["gil_preso_ms"] >= 700, f"a thread da janela tem de ficar presa >= 700 ms (T05: 0,75 s): {x}"
    assert x["maior_intervalo_ms"] < 50 and x["quadros"] >= 20 * x["gil_preso_ms"] / 1000, f"(iii) o desenho parou com o bloqueio preso na thread da janela: {x}"
    assert x["conteiner_python"] is False and x["classe_conteiner"].startswith("PySide6."), x


def test_t15c_iii_nenhum_arquivo_do_fluxo_mexe_na_janela_de_desenho():
    if not (aux.PASTA / "conferencias.py").is_file():
        pular("prototypes/s04/fluxo_a/conferencias.py ausente")
    for nome in ("fluxo_a.py", "lote.py", "conferencias.py"):
        for n, linha in enumerate((aux.PASTA / nome).read_text(encoding="utf-8").splitlines(), 1):
            assert not ("_cont" in linha and re.search(r"installEventFilter|\.connect\(|setMouseTracking|\.event\s*=", linha)), f"{nome}:{n}: mexe no contêiner da viewport: {linha.strip()}"
            assert not re.search(r"class\s+\w+\s*\((QWindow|QRhiWidget|QOpenGLWidget|QOpenGLWindow)\b", linha), f"{nome}:{n}: janela de desenho em Python: {linha.strip()}"


def test_t15c_forma_3_viewport_python_da_s03(conf):
    rs = conf["forma3"]
    assert len(rs) == RODADAS
    for r in rs:
        t0, t1, p = r["t0_ms"], r["t1_ms"], r["parado"]
        assert r["thread_lote"] != r["thread_janela"], "forma 3 = forma 1 (lote numa thread Python) com a viewport da S03"
        assert t0 < t1 and r["quadros"] == sorted(r["quadros"]) and all(t0 <= t <= t1 for t in r["quadros"]) and all(t0 <= t <= t1 for t in r["pulsos"])
        assert p["t1_ms"] <= t0 and len(p["quadros"]) >= 20 * (p["t1_ms"] - p["t0_ms"]) / 1000, f"controle: parada, a viewport da S03 tem de desenhar >= 20 quadros por segundo ({len(p['quadros'])})"
        jan = [sum(1 for t in r["quadros"] if t0 + 1000 * k <= t < t0 + 1000 * (k + 1)) for k in range(int((t1 - t0) // 1000))]
        esperado = {"M5": {"janelas": jan, "maior_intervalo_ms": maior([t0, *r["quadros"], t1]), "maior_intervalo_parado_ms": maior(p["quadros"])},
                    "pulso_maior_ms": maior([t0, *r["pulsos"], t1])}
        assert r["resumo"]["M5"]["janelas"] == jan
        for k in ("maior_intervalo_ms", "maior_intervalo_parado_ms"):
            assert abs(r["resumo"]["M5"][k] - esperado["M5"][k]) <= 1e-6, (k, r["resumo"])
        assert abs(r["resumo"]["pulso_maior_ms"] - esperado["pulso_maior_ms"]) <= 1e-6


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
