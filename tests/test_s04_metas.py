# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo das metas e da saída igual (S04-T12; LOTE_OPUS_9 §2.1 a §2.3 e §3; LOTE_OPUS_15 achado 1; LOTE_OPUS_18 itens 7 e 12). Apoio: s04_fluxo_aux.py (conta das metas do fluxo A) e s04_fluxo_b_aux.py.
GUARDA: pula enquanto `prototypes/s04/medir_s04.py` for o esqueleto (NotImplementedError); FALHA com OBIM_S04_T12_OBRIGATORIO=1. Os casos B reais (`OBIM_S04_SAIDA_B`) só falham com OBIM_S04_T14_OBRIGATORIO=1 (T14 ainda não existe).
Casos com A real rodam em `xvfb-run` (nunca na tela real) e reaproveitam o roteiro R do oráculo da T11 (mesma chave de cache: não rodam o roteiro duas vezes no CI). OBIM_S04_SAIDA_A aponta para uma pasta de A já medida (rodada oficial do PO).
CONTRATO DA FERRAMENTA (`python prototypes/s04/medir_s04.py`; o oráculo troca o caminho por OBIM_S04_MEDIR; o implementador não edita este arquivo):
 --a PASTA [--b PASTA] [--estrito] [--json ARQ]: cada PASTA tem `medicao.json` (o do fluxo) e o IFC do passo 7 (chave `arquivo_ifc`; relativo = a PASTA). `--estrito` = OBIM_S04_ESTRITO=1 no ambiente. Código de saída: 0 aprovado, 1 reprovado, 2 entrada inválida.
 --linhas --raiz DIR [--json ARQ]: linhas de DIR/obimcore, DIR/fluxo_a e DIR/fluxo_b. JSON: {"linhas": {"obimcore": n, "fluxo_a": n, "fluxo_b": n}}.
 JSON do --a/--b: {"estrito", "metas": {M2, M2b, M3, M4: {n, mediana_ms, p95_ms, max_ms, limite_ms, ok}, M5: {janelas, maior_intervalo_ms, maior_intervalo_parado_ms, ok}}, "erros": [texto "Mx: ..."],
  "m6": null sem --b ou {"razoes": {M2, M2b, M3, M4}, "folga_minima", "pesa"}, "saida_igual": null sem --b ou {"ok", "diferencas": [texto]}, "aprovado"}.
 Metas (§2.2, §2.3): SEMPRE dos tempos brutos de A (nunca do campo `metas` gravado). Passos: M2 = passo 3; M2b = 4b; M3 = 4a até t_painel_ms; M4 = 5b; M5 = 5b contra o passo 4c (parado); tempo = t_quadro_ms - t0_ms; percentil linear (numpy).
 Régua do CI virtual (sem --estrito): mediana < limite e nenhum valor >= 3 x limite (M2, M2b, M3); M4 < 20 s; M5: toda janela de 1 s com >= 20 quadros, maior intervalo < 100 ms e <= 3 x o do parado. Com --estrito: p95 < limite
 (200, 200, 50 ms), M4 < 20 s e maior intervalo < 200 ms. É a mesma régua de s04_fluxo_aux.veredito. `erros` lista cada violação; `ok` de cada meta = sem erro com o nome dela; aprovado = sem erros e (sem --b ou saída igual).
 M6 (informativo, nunca reprova): razoes = mediana de A / mediana de B em M2, M2b, M3 e M4 (um valor). folga_minima = menor entre 200/p95(M2), 200/p95(M2b), 50/p95(M3), 20000/max(M4), 200/maior_intervalo(M5);
 pesa = folga_minima < 2 (decisão do PO: só pesa se alguma meta absoluta ficar com menos de 2x de folga). As 3 rodadas alternadas do §2.2 ficam para a rodada oficial (a ferramenta lê um par A/B por vez).
 Entrada inválida (código 2): arquivo ausente, passos de B diferentes dos de A (ids ou número de repetições), `base.produtos` diferente (os dois têm de ter medido o mesmo modelo).
 Saída igual (§2.2): IFC inteiro, como gravado (GlobalIds e ids de linha podem diferir): mesmas contagens por classe (fora geometria de apoio e relações de material, que A compartilha e B não); para cada parede mesmo tipo, pavimento,
 espessuras de camada, nome, FireRating, triângulos, caixa e volume a 1e-6 (ifcopenshell.geom, em metros); os dois passam em `ifcopenshell.validate(express_rules=True)` (nível "error" em minúsculas). Parede de A sem par em B = diferença.
 `primeiro_quadro(relogio, seq)`: tempo do primeiro quadro com sequência >= seq, ou None (LOTE_OPUS_15: a sequência cai a 0 no reenvio da cena).
 `contar_linhas`: arquivos .py .cpp .h .hpp .cc, fora de pastas `build`, `__pycache__` e as que começam com ".". Python: sem docstrings, `ast.unparse` (some comentário e linha vazia; uma instrução por linha) e cada linha vale ceil(largura/100).
 C/C++: sem comentário (// e /* */, respeitando textos entre aspas), sem linha vazia, cada linha vale ceil(largura/100).
M2b informativo (LOTE_OPUS_15 achado 1): roteiro R com `corpus/modelo-grande-1m.ifc`; só imprime; pula se o arquivo não existir (também com OBRIGATORIO: ele é gerado à mão, ~60 s, e fica fora do git).
Fora do escopo do oráculo: M1 (T02/T04), nota do ADR-001 e compactar `lotes_` (núcleo)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import s04_fluxo_aux as aux
import s04_fluxo_b_aux as bx
from test_s04_viewport import caso as _caso

ESTE = Path(__file__).resolve()
MEDIR = Path(os.environ.get("OBIM_S04_MEDIR") or aux.RAIZ / "prototypes" / "s04" / "medir_s04.py")
OBRIG, OBRIG_B = os.environ.get("OBIM_S04_T12_OBRIGATORIO") == "1", os.environ.get("OBIM_S04_T14_OBRIGATORIO") == "1"
BASE = os.environ.get("OBIM_S04_BASE", "300")
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=aux.AQUI, **k)  # noqa: E731  (a mesma chave do oráculo da T11)

def pular(msg, obrig=None):
    (pytest.fail if (OBRIG if obrig is None else obrig) else pytest.skip)(f"\n!!! S04-T12: {msg} (oráculo das metas NÃO FOI EXECUTADO) !!!\n")

# ---------- construtor de medicao.json sintético: cada meta falha sozinha ----------
def med(fluxo="A", m2=20.0, m2b=20.0, m3=10.0, m4=3000.0, quadros=None, produtos=300, reps=20):
    v = lambda x: list(x) if isinstance(x, (list, tuple)) else [float(x)] * reps  # noqa: E731
    rep = lambda t, **k: {"t0_ms": 0.0, "t_comando_ms": 1.0, "t_quadro_ms": t, **k}  # noqa: E731
    quad = lambda fim: [[16.0 * i, i] for i in range(1, int(fim / 16) + 1)]  # noqa: E731
    ps = [("3", "criar_parede", [rep(t) for t in v(m2)]), ("4a", "editar_propriedades", [rep(1.0, t_painel_ms=t) for t in v(m3)]), ("4b", "mudar_comprimento", [rep(t) for t in v(m2b)]),
          ("4c", "esperar", [rep(3000.0, relogio=quad(3000.0))]), ("5b", "criar_paredes_lote", [rep(m4, relogio=quadros or quad(m4))])]
    return {"fluxo": fluxo, "versao": 1, "plataforma": "teste", "rhi": "gl", "base": {"arquivo": "base.ifc", "produtos": produtos}, "arquivo_ifc": None,
            "passos": [{"id": i, "cmd": c, "reps": r} for i, c, r in ps], "metas": None}

def gravar(pasta, m, ifc=None):  # pasta com medicao.json (e o IFC copiado para dentro, se houver)
    pasta.mkdir(parents=True, exist_ok=True)
    ifc and shutil.copy(ifc, pasta / "r.ifc")
    (pasta / "medicao.json").write_text(json.dumps(dict(m, arquivo_ifc="r.ifc" if ifc else None)), encoding="utf-8")
    return pasta

def rodar(*args, estrito=False, env=None):
    e = {k: v for k, v in os.environ.items() if k != "OBIM_S04_ESTRITO"} | dict(env or {})
    p = subprocess.run([sys.executable, str(MEDIR), *map(str, args), *(["--estrito"] if estrito else [])], env=e, capture_output=True, text=True, timeout=600)
    return p

def avaliar(tmp, a, b=None, estrito=False, ifc_a=None, ifc_b=None, nome="s", env=None):  # (código, json|None, processo)
    pa = gravar(tmp / f"{nome}_a", a, ifc_a)
    args = ["--a", pa, "--json", tmp / f"{nome}.json"] + (["--b", gravar(tmp / f"{nome}_b", b, ifc_b)] if b else [])
    p = rodar(*args, estrito=estrito, env=env)
    return p.returncode, (json.loads((tmp / f"{nome}.json").read_text()) if (tmp / f"{nome}.json").is_file() else None), p

@pytest.fixture(scope="module")
def ferramenta(tmp_path_factory):  # o esqueleto levanta NotImplementedError: o oráculo espera pelo implementador
    if not MEDIR.is_file():
        pular(f"{MEDIR} ausente")
    rc, js, p = avaliar(tmp_path_factory.mktemp("sonda"), med())
    if "NotImplementedError" in p.stderr:
        pular("prototypes/s04/medir_s04.py ainda é o esqueleto")
    return MEDIR

# ---------- tabela de casos: (nome, parâmetros de A, passa na régua virtual, passa na estrita, erro esperado) ----------
CASOS = [("bom", {}, True, True, None), ("m2 mediana alta", {"m2": 250.0}, False, False, "M2"), ("m2 dois valores em 210 (virtual passa, p95 reprova)", {"m2": [100.0] * 18 + [210.0] * 2}, True, False, "M2"),
         ("m2 um valor em 650 (teto reprova, p95 passa)", {"m2": [100.0] * 19 + [650.0]}, False, True, "M2"), ("m2b mediana alta", {"m2b": 300.0}, False, False, "M2b"),
         ("m3 mediana alta", {"m3": 60.0}, False, False, "M3"), ("m3 dois valores em 55", {"m3": [20.0] * 18 + [55.0] * 2}, True, False, "M3"), ("m4 lote lento", {"m4": 25000.0}, False, False, "M4"),
         ("m5 10 quadros por segundo", {"quadros": [[100.0 * i, i] for i in range(1, 31)]}, False, False, "M5"),
         ("m5 parada de 330 ms", {"quadros": [[16.0 * i, i] for i in range(1, 100)] + [[1900.0 + 16.0 * i, 100 + i] for i in range(70)]}, False, False, "M5")]
IDS = [c[0] for c in CASOS]

def test_a_tabela_de_casos_confere_com_a_regua_do_fluxo_a(monkeypatch):  # sentinela que roda hoje: a tabela e a conta de s04_fluxo_aux concordam
    for nome, kw, virtual, estrito, erro in CASOS:
        for modo, esperado in ((False, virtual), (True, estrito)):
            monkeypatch.setattr(aux, "ESTRITO", modo)
            e = aux.veredito(aux.calcular(med(**kw)))
            assert (not e) == esperado and all(x.startswith(erro) for x in e), (nome, modo, e)

@pytest.mark.parametrize("modo", ["virtual", "estrito"])
@pytest.mark.parametrize("c", CASOS, ids=IDS)
def test_a_ferramenta_aprova_e_reprova_como_a_tabela(ferramenta, tmp_path, c, modo):
    nome, kw, virtual, estrito, erro = c
    ok, m = (estrito if modo == "estrito" else virtual), med(**kw)
    rc, js, p = avaliar(tmp_path, m, estrito=modo == "estrito")
    assert js is not None and rc == (0 if ok else 1) and js["aprovado"] is ok and js["estrito"] is (modo == "estrito"), (nome, rc, js, p.stderr[-800:])
    assert not ok or not js["erros"], js["erros"]
    assert ok or any(e.startswith(erro + ":") for e in js["erros"]), js["erros"]
    cal = aux.calcular(m)
    for k in ("M2", "M2b", "M3", "M4"):
        assert {a: js["metas"][k][a] for a in ("mediana_ms", "p95_ms", "max_ms")} == pytest.approx({a: cal[k][a] for a in ("mediana_ms", "p95_ms", "max_ms")}, abs=1e-6), k
        assert js["metas"][k]["n"] == cal[k]["n"] and js["metas"][k]["ok"] == (not any(e.startswith(k + ":") for e in js["erros"])), k
    assert js["metas"]["M5"]["maior_intervalo_ms"] == pytest.approx(cal["M5"]["maior_intervalo_ms"], abs=1e-6) and js["metas"]["M5"]["janelas"] == cal["M5"]["janelas"]
    assert js["metas"]["M5"]["ok"] == (not any(e.startswith("M5:") for e in js["erros"])) and js["m6"] is None and js["saida_igual"] is None

def test_a_variavel_de_ambiente_liga_a_regua_estrita(ferramenta, tmp_path):  # a mesma mecânica do OBIM_S04_ESTRITO=1 da máquina do PO
    m = med(m2=[100.0] * 18 + [210.0] * 2)
    assert avaliar(tmp_path, m, nome="v")[0] == 0 and avaliar(tmp_path, m, nome="e", env={"OBIM_S04_ESTRITO": "1"})[0] == 1

def test_a_ferramenta_ignora_o_campo_metas_gravado_pelos_fluxos(ferramenta, tmp_path):  # um fluxo que se declara aprovado não vale nada: recalcular dos tempos brutos
    m = med(m2=250.0)
    m["metas"] = {"M2": {"passo": "3", "n": 20, "mediana_ms": 1.0, "p95_ms": 1.0, "max_ms": 1.0, "limite_ms": 200.0, "ok": True}}
    rc, js, _ = avaliar(tmp_path, m)
    assert rc == 1 and js["metas"]["M2"]["mediana_ms"] == pytest.approx(250.0) and not js["metas"]["M2"]["ok"]

# ---------- IFCs sintéticos: um IFC4 de verdade do fluxo A (tipo de 3 camadas, 4 paredes) e variações ----------
@pytest.fixture(scope="module")
def ifcs(tmp_path_factory):
    if not (aux.PASTA / "fluxo_a.py").is_file():
        pular("fluxo_a.py ausente")
    import fluxo_a
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.guid
    pasta = tmp_path_factory.mktemp("ifcs")
    f = fluxo_a.FluxoA(None, janela=False, saida=pasta)
    f.executar(aux.TIPO)
    [f.executar(aux.PAREDE) for _ in range(4)]
    f.executar({"cmd": "editar_propriedades", "alvo": "ultimo", "nome": "Muro X", "propriedades": {aux.FIRE: "R60"}})
    f.executar({"cmd": "gravar", "arquivo": "base.ifc"})
    ed = {"guids": lambda g: [setattr(e, "GlobalId", ifcopenshell.guid.new()) for e in g.by_type("IfcRoot")],
          "sem_parede": lambda g: ifcopenshell.api.run("root.remove_product", g, product=g.by_type("IfcWall")[-1]),
          "camada": lambda g: setattr(g.by_type("IfcMaterialLayer")[1], "LayerThickness", 0.12),
          "altura": lambda g: setattr(g.by_type("IfcExtrudedAreaSolid")[0], "Depth", 3.0),
          "invalido": lambda g: setattr(g.by_type("IfcMaterialLayer")[0], "LayerThickness", -0.02)}  # só o validate acusa (a geometria segue calculável)
    out = {"base": pasta / "base.ifc"}
    for nome, fn in ed.items():
        g = ifcopenshell.open(str(out["base"]))
        fn(g)
        out[nome] = pasta / f"{nome}.ifc"
        g.write(str(out[nome]))
    g = ifcopenshell.open(str(out["invalido"]))
    ed["guids"](g)
    out["invalido_guids"] = pasta / "invalido_guids.ifc"
    g.write(str(out["invalido_guids"]))
    return out

def test_ifcs_sinteticos_da_sentinela_sao_validos_ou_nao_como_o_oraculo_supoe(ifcs):
    assert all(not bx.validar(ifcs[k]) for k in ("base", "guids", "sem_parede", "camada", "altura")), "os IFCs de controle têm de passar no validate"
    assert bx.validar(ifcs["invalido"]) and bx.validar(ifcs["invalido_guids"]), "o IFC de controle inválido tem de reprovar no validate"

@pytest.mark.parametrize("a,b,ok", [("base", "guids", True), ("base", "sem_parede", False), ("base", "camada", False), ("base", "altura", False), ("invalido", "invalido_guids", False)],
                         ids=["globalids diferentes", "uma parede a menos", "espessura de camada", "altura da parede", "iguais mas inválidos"])
def test_saida_igual_aceita_globalids_diferentes_e_acusa_cada_diferenca(ferramenta, tmp_path, ifcs, a, b, ok):
    rc, js, p = avaliar(tmp_path, med(), med("B"), ifc_a=ifcs[a], ifc_b=ifcs[b])
    assert js is not None and js["saida_igual"]["ok"] is ok and (not ok) == bool(js["saida_igual"]["diferencas"]), (js, p.stderr[-800:])
    assert js["aprovado"] is ok and rc == (0 if ok else 1) and not js["erros"], "as metas de A estão boas: só a saída igual decide"

# ---------- M6 e entrada inválida ----------
def test_m6_e_so_acompanhamento_e_pesa_com_folga_menor_que_2(ferramenta, tmp_path, ifcs):
    rc, js, _ = avaliar(tmp_path, med(), med("B", m2=4.0, m2b=4.0, m3=2.0, m4=600.0), ifc_a=ifcs["base"], ifc_b=ifcs["guids"], nome="a")
    assert rc == 0 and js["m6"]["razoes"] == pytest.approx({"M2": 5.0, "M2b": 5.0, "M3": 5.0, "M4": 5.0}) and js["m6"]["folga_minima"] == pytest.approx(min(200 / 20, 50 / 10, 20000 / 3000, 200 / 16.0)) and not js["m6"]["pesa"]
    rc, js, _ = avaliar(tmp_path, med(m3=30.0), med("B", m3=5.0), ifc_a=ifcs["base"], ifc_b=ifcs["guids"], nome="b")  # 50/30 = 1,67 de folga: pesa, mas as metas absolutas passam
    assert rc == 0 and js["aprovado"] and js["m6"]["pesa"] and js["m6"]["folga_minima"] == pytest.approx(50 / 30) and js["m6"]["razoes"]["M3"] == pytest.approx(6.0)

@pytest.mark.parametrize("b", [med("B", reps=19), med("B", produtos=301)], ids=["repeticoes diferentes", "base diferente"])
def test_b_que_nao_mediu_o_mesmo_roteiro_e_o_mesmo_modelo_e_entrada_invalida(ferramenta, tmp_path, ifcs, b):
    assert avaliar(tmp_path, med(), b, ifc_a=ifcs["base"], ifc_b=ifcs["guids"])[0] == 2

def test_b_sem_um_passo_e_entrada_invalida(ferramenta, tmp_path, ifcs):
    b = med("B")
    b["passos"] = [p for p in b["passos"] if p["id"] != "5b"]
    assert avaliar(tmp_path, med(), b, ifc_a=ifcs["base"], ifc_b=ifcs["guids"])[0] == 2
    assert rodar("--a", tmp_path / "nao_existe", "--json", tmp_path / "x.json").returncode == 2

def test_primeiro_quadro_com_sequencia_maior_ou_igual_nao_supoe_sequencia_crescente(ferramenta):
    sp = importlib.util.spec_from_file_location("medir_s04_t12", MEDIR)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    r = [[16.0, 5], [32.0, 0], [48.0, 0], [64.0, 6], [80.0, 7]]  # a cena foi reenviada: a sequência cai a 0 e volta
    assert [mod.primeiro_quadro(r, s) for s in (1, 5, 6, 7, 8)] == [16.0, 16.0, 64.0, 80.0, None]
    r = [[16.0, 0], [32.0, 3], [48.0, 0], [64.0, 0], [80.0, 4]]
    assert [mod.primeiro_quadro(r, s) for s in (3, 4, 5)] == [32.0, 80.0, None] and mod.primeiro_quadro([], 1) is None

# ---------- M7: linhas por pasta, depois de formatar ----------
def test_m7_conta_linhas_por_pasta_sem_comentario_sem_vazias_e_depois_de_formatar(ferramenta, tmp_path):
    arq = {"obimcore/y.cpp": '// comentário\n/* bloco\n   de comentário */\nint a = 1;\n\nint b = 2; // fim\nconst char* u = "http://x";\nint main() {\n  return 0;\n}\n', "obimcore/y.h": "#pragma once\n",
           "obimcore/build/lixo.cpp": "int lixo;\n", "fluxo_a/x.py": f'"""doc"""\n# comentário\n\na = 1; b = 2\nif a: b = 3\nx = "{"y" * 250}"\n', "fluxo_a/README.md": "texto\ntexto\n",
           "fluxo_a/__pycache__/x.py": "z = 1\n", "fluxo_b/z.cpp": "int v[] = {" + "1, " * 80 + "};\n", "fluxo_b/CMakeLists.txt": "project(x)\n"}
    for k, t in arq.items():
        (tmp_path / "raiz" / k).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "raiz" / k).write_text(t, encoding="utf-8")
    p = rodar("--linhas", "--raiz", tmp_path / "raiz", "--json", tmp_path / "l.json")
    assert p.returncode == 0 and json.loads((tmp_path / "l.json").read_text())["linhas"] == {"obimcore": 7, "fluxo_a": 7, "fluxo_b": 3}, p.stderr[-800:]

def test_m7_nas_pastas_reais_fluxo_a_depois_de_formatar_tem_mais_linhas_que_as_cruas(ferramenta, tmp_path):
    raiz = aux.RAIZ / "prototypes" / "s04"
    p = rodar("--linhas", "--raiz", raiz, "--json", tmp_path / "l.json")
    n = json.loads((tmp_path / "l.json").read_text())["linhas"]
    crua = sum(1 for f in (raiz / "fluxo_a").rglob("*.py") for x in f.read_text(encoding="utf-8").splitlines() if x.strip() and not x.strip().startswith("#"))
    assert p.returncode == 0 and all(n[k] > 0 for k in ("obimcore", "fluxo_a", "fluxo_b")) and n["fluxo_a"] > crua, (n, crua)
    print("LINHAS", json.dumps(n))

# ---------- A real (roteiro R inteiro, em tela virtual) ----------
@pytest.fixture(scope="module")
def saida_a(ferramenta):
    if os.environ.get("OBIM_S04_SAIDA_A"):
        return Path(os.environ["OBIM_S04_SAIDA_A"])
    if not (aux.PASTA / "fluxo_a.py").is_file() or importlib.util.find_spec("obimcore") is None:
        pular("fluxo_a.py ou obimcore ausente (A real)")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    return Path(caso("roteiro", BASE, limite=900)["arquivo_medicao"]).parent

def test_a_real_a_ferramenta_calcula_as_metas_dos_tempos_brutos_e_decide_como_a_regua(saida_a, tmp_path):
    m = json.loads((saida_a / "medicao.json").read_text())
    cal = aux.calcular(m)
    esperado = aux.veredito(cal)
    p = rodar("--a", saida_a, "--json", tmp_path / "r.json", estrito=aux.ESTRITO)
    js = json.loads((tmp_path / "r.json").read_text())
    assert p.returncode == (1 if esperado else 0) and js["aprovado"] is (not esperado), (js["erros"], esperado, p.stderr[-800:])
    assert {e.split(":")[0] for e in js["erros"]} == {e.split(":")[0] for e in esperado}
    for k in ("M2", "M2b", "M3", "M4"):
        assert {a: js["metas"][k][a] for a in ("mediana_ms", "p95_ms", "max_ms")} == pytest.approx({a: cal[k][a] for a in ("mediana_ms", "p95_ms", "max_ms")}, abs=1e-6), k
    print("METAS_A", json.dumps({k: js["metas"][k] for k in ("M2", "M2b", "M3", "M4", "M5")}), "ESTRITO" if aux.ESTRITO else "virtual")

def assin(caminho):  # assinatura do oráculo, sem GlobalId e sem achar parede pela posição (a base e a grade do roteiro colidem em 0,0,0): multiconjunto de paredes
    import ifcopenshell
    import ifcopenshell.util.element as E
    f = ifcopenshell.open(str(caminho))
    fm, nome = bx.formas(f), lambda x: (x.Name if x is not None else "")  # noqa: E731
    def parede(w):
        us, tri, lo, hi, vol = E.get_material(w, should_inherit=False), *fm[w.id()]
        return [w.Name or "", nome(E.get_type(w)), nome(E.get_container(w)), aux.fire(w) or "", [c.LayerThickness for c in us.ForLayerSet.MaterialLayers] if us else [], tri, *lo, *hi, vol]
    ps = sorted((parede(w) for w in f.by_type("IfcWall")), key=lambda p: (*p[:4], tuple(round(x, 3) for x in p[6:])))
    return {"classes": dict(Counter(e.is_a() for e in f if e.is_a() not in bx.LIVRES | bx.MATERIAL)), "paredes": ps}

def test_a_real_sentinela_a_contra_ele_mesmo_com_globalids_novos_tem_saida_igual(saida_a, tmp_path, ferramenta):
    import ifcopenshell
    import ifcopenshell.guid
    m = json.loads((saida_a / "medicao.json").read_text())
    ifc = Path(m["arquivo_ifc"])
    g = ifcopenshell.open(str(ifc))
    [setattr(e, "GlobalId", ifcopenshell.guid.new()) for e in g.by_type("IfcRoot")]
    g.write(str(tmp_path / "r.ifc"))
    (tmp_path / "medicao.json").write_text(json.dumps(dict(m, fluxo="B", arquivo_ifc="r.ifc")), encoding="utf-8")
    assert bx.igual(assin(ifc), assin(tmp_path / "r.ifc")) == [] and not bx.validar(ifc)
    p = rodar("--a", saida_a, "--b", tmp_path, "--json", tmp_path / "s.json", estrito=aux.ESTRITO)
    js = json.loads((tmp_path / "s.json").read_text())
    assert js["saida_igual"] == {"ok": True, "diferencas": []} and all(r == pytest.approx(1.0) for r in js["m6"]["razoes"].values()), (js["saida_igual"], p.stderr[-800:])

# ---------- B real (T14): só quando a pasta existir ----------
def test_b_real_metas_e_saida_igual_contra_a(saida_a, tmp_path):
    b = os.environ.get("OBIM_S04_SAIDA_B")
    if not b or not (Path(b) / "medicao.json").is_file():
        pular("aguarda S04-T14: sem OBIM_S04_SAIDA_B (pasta com o medicao.json e o IFC do passo 7 do fluxo B, medidos com o MESMO modelo de base)", OBRIG_B)
    mb = json.loads((Path(b) / "medicao.json").read_text())
    ma = json.loads((saida_a / "medicao.json").read_text())
    assert mb["fluxo"] == "B" and mb["base"]["produtos"] == ma["base"]["produtos"] and [(p["id"], len(p["reps"])) for p in mb["passos"]] == [(p["id"], len(p["reps"])) for p in ma["passos"]]
    ia, ib = Path(ma["arquivo_ifc"]), Path(mb["arquivo_ifc"]) if Path(mb["arquivo_ifc"]).is_absolute() else Path(b) / mb["arquivo_ifc"]
    assert bx.igual(assin(ia), assin(ib)) == [] and not bx.validar(ia) and not bx.validar(ib), "saída diferente entre A e B (o IFC de B tem de conter o modelo de base)"
    p = rodar("--a", saida_a, "--b", b, "--json", tmp_path / "ab.json", estrito=aux.ESTRITO)
    js = json.loads((tmp_path / "ab.json").read_text())
    assert p.returncode == 0 and js["aprovado"] and js["saida_igual"]["ok"], (js, p.stderr[-800:])
    print("M6", json.dumps(js["m6"]))

# ---------- M2b informativo, modelo de 1 milhão ----------
def test_m2b_com_o_modelo_de_1_milhao_so_informa():
    ifc = Path(os.environ.get("OBIM_S04_M2B_IFC") or aux.RAIZ / "corpus" / "modelo-grande-1m.ifc")
    if not ifc.is_file():
        pytest.skip(f"informativo: {ifc} não existe (gere com scripts/gerar_modelo_grande.py --paredes 83334; ~60 s; fica fora do git)")
    if importlib.util.find_spec("obimcore") is None or (not shutil.which("xvfb-run") and sys.platform != "win32"):
        pytest.skip("informativo: sem obimcore ou sem tela virtual")
    c = _caso("roteiro_ifc", ifc, alvo=ESTE, limite=3600)
    m = json.loads(Path(c["arquivo_medicao"]).read_text())
    cal = aux.calcular(m)
    assert cal["M2b"]["n"] == 200 and all(np.isfinite(cal["M2b"][k]) for k in ("mediana_ms", "p95_ms", "max_ms")) and m["base"]["produtos"] > 80000
    print("M2b_1M (informativo, limite 200 ms; LOTE_OPUS_15 achado 1: trocar uma peça reenvia a cena)", json.dumps(cal["M2b"]), "M3", json.dumps(cal["M3"]), "M2", json.dumps(cal["M2"]))

if __name__ == "__main__":  # caso gráfico do M2b: o roteiro R sobre um IFC dado (processo próprio, sob xvfb-run)
    import faulthandler
    import tempfile
    import traceback
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 600)) - 20, exit=True)
    nome, *resto = sys.argv[1:]
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        import fluxo_a
        f = fluxo_a.FluxoA(resto[0], janela=True, saida=Path(tempfile.mkdtemp()))
        saida = {"arquivo_medicao": f.executar_roteiro(aux.ROTEIRO)["arquivo_medicao"]}
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
