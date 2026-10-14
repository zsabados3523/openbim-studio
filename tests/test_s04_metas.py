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
 Entrada inválida (código 2; LOTE_OPUS_23 §B): a mensagem em stderr começa com "ENTRADA INVÁLIDA:", cita `passo <id>` quando o problema é de um passo e NUNCA é traceback nos casos abaixo (LOTE_OPUS_24 B). Casos:
 (i) tempo que não é número finito (NaN, infinito, texto, inteiro gigante como 10**400: `_num` trata OverflowError como "não é número"; vale para TODO campo numérico, inclusive os do relógio, `sequencia` e `base.produtos`); fora de ordem em qualquer repetição: `t0_ms <= t_comando_ms <= t_quadro_ms` (e `t_painel_ms >= t0_ms` no 4a); relógio (4c e 5b) com tempo não finito ou REPETIDO (dois quadros no mesmo instante: relógio duplicado esconde parada e infla a contagem por janela).
 A ferramenta ORDENA os tempos do relógio antes de medir os intervalos (relógio fora de ordem dá o mesmo resultado do ordenado).
 JANELA DO RELÓGIO (LOTE_OPUS_27 A2): todo quadro do `relogio` (4c e 5b) tem de estar em [t0_ms, t_quadro_ms] DA PRÓPRIA REPETIÇÃO (limites inclusivos, como o filtro de fluxo_a.py); qualquer entrada fora da janela (antes de t0 ou depois de t_quadro) é entrada inválida, código 2, citando `passo <id>`. A ferramenta REJEITA, não filtra: quadros de fora esconderiam parada (lote de 0,9 s com 9 quadros dentro e 9 logo depois) ou mascarariam o intervalo do parado (um quadro em -5000 ms),
 e `primeiro_quadro` não pode achar o lote antes de t0. O FLUXO B (T14), ao gravar `relogio`, deve filtrar igual ao A (`u["t0_ms"] <= t <= tq`); quem gerar o `medicao.json` de B é responsável por isso. (ii) número de repetições diferente do `n` de `fluxo_a/roteiro_r.json` em TODOS os passos medidos (3, 4a, 4b, 4c e 5b; LOTE_OPUS_27 A1): regra `len(reps) != n`, MENOS OU MAIS (201 e 500 também: repetições extras baratas puxariam a mediana e o p95), com `n` = 200 nos passos 3, 4a e 4b e PADRÃO 1 onde o roteiro não define `n` (4c e 5b: o fluxo A executa `int(p.get("n", 1))`); `_m5` só lê `reps[0]`, então uma 2ª repetição de 4c/5b nunca pode passar calada. Também `len(criados)` do 5b
 diferente da `quantidade` do roteiro (1000) ou ausente (o oráculo lê os dois valores do roteiro; mesma regra para B). (iii) passo sem `id`, sem `reps` ou com `reps` que não é lista; repetição sem os campos de tempo do passo; IFC do passo 7 ilegível (A ou B).
 (iv) 5b sem `sequencia`, com `sequencia` que não é inteiro >= 1 (0, negativa e 3,5 tornam o primeiro quadro trivial), com `criados` de GlobalIds repetidos (`len(set(criados))` tem de ser o lote), ou `primeiro_quadro(relogio, sequencia)` None ou maior que `t_quadro_ms` (o lote nunca apareceu num quadro). (v) régua estrita (--estrito ou OBIM_S04_ESTRITO=1) com `base.produtos` ausente ou < 3000: não é o modelo oficial.
 Também código 2: arquivo ausente, passos de B diferentes dos de A (ids ou número de repetições), `base.produtos` diferente (os dois têm de ter medido o mesmo modelo).
 Rede de segurança de `main` (erro de programação: KeyError, TypeError, IndexError, AttributeError fora do formato): código 2, primeira linha de stderr "ENTRADA INVÁLIDA: ..." e, DEPOIS dela, o `traceback.format_exc()` (o implementador precisa ver onde quebrou). `main(argv)` chama `avaliar(pasta_a, pasta_b, estrito)`.
 LIMITE CONHECIDO (LOTE_OPUS_24 B5): duração zero (`t_quadro_ms == t0_ms`) é aceita e passa nas metas; não há caso de oráculo para isso (exigir `t_quadro_ms > t0_ms` é opcional).
 Saída igual (§2.2): IFC inteiro, como gravado (comprimentos na unidade do próprio IFC, convertidos para metros: um IFC em mm e outro em m com as mesmas medidas são iguais) (GlobalIds e ids de linha podem diferir): mesmas contagens por classe (fora só a geometria de apoio; IfcMaterialLayerSetUsage e IfcRelAssociatesMaterial CONTAM: sem exceção desde a T11c, LOTE_OPUS_24 B item 6); para cada parede mesmo tipo, pavimento,
 espessuras de camada, nome, FireRating, triângulos, caixa e volume a 1e-6 (ifcopenshell.geom, em metros); os dois passam em `ifcopenshell.validate(express_rules=True)` (nível "error" em minúsculas). Parede de A sem par em B = diferença.
 `primeiro_quadro(relogio, seq)`: tempo do primeiro quadro com sequência >= seq, ou None (LOTE_OPUS_15: a sequência cai a 0 no reenvio da cena).
 `contar_linhas`: arquivos .py .cpp .h .hpp .cc, fora de pastas `build`, `__pycache__` e as que começam com ".". Python: sem docstrings, `ast.unparse` (some comentário e linha vazia; uma instrução por linha) e cada linha vale ceil(largura/100).
 C/C++: sem comentário (// e /* */, respeitando textos entre aspas), sem linha vazia, cada linha vale ceil(largura/100).
M2b informativo (LOTE_OPUS_15 achado 1): roteiro R com `corpus/modelo-grande-1m.ifc`; só imprime; pula se o arquivo não existir (também com OBRIGATORIO: ele é gerado à mão, ~60 s, e fica fora do git).
(A exceção de material saiu na T12, depois da T11c: A e B têm as mesmas contagens de IfcMaterialLayerSetUsage e IfcRelAssociatesMaterial; relação a menos ou uso compartilhado em B = saída diferente.)
Fora do escopo do oráculo: M1 (T02/T04), nota do ADR-001 e compactar `lotes_` (núcleo)."""
import copy
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
ROT = {p["id"]: p for p in json.loads(aux.ROTEIRO.read_text(encoding="utf-8"))["passos"]}
N, LOTE, OFICIAL = ROT["3"]["n"], ROT["5b"]["quantidade"], 3000  # repetições e tamanho do lote do roteiro R; paredes do modelo oficial (régua estrita)
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=aux.AQUI, **k)  # noqa: E731  (a mesma chave do oráculo da T11)

def pular(msg, obrig=None):
    (pytest.fail if (OBRIG if obrig is None else obrig) else pytest.skip)(f"\n!!! S04-T12: {msg} (oráculo das metas NÃO FOI EXECUTADO) !!!\n")

# ---------- construtor de medicao.json sintético: cada meta falha sozinha ----------
def med(fluxo="A", m2=20.0, m2b=20.0, m3=10.0, m4=3000.0, quadros=None, produtos=OFICIAL, reps=N, lote=LOTE, seq=3, parado=None):  # lote/seq None = campo ausente do 5b
    v = lambda x: list(x) if isinstance(x, (list, tuple)) else [float(x)] * reps  # noqa: E731
    rep = lambda t, **k: {"t0_ms": 0.0, "t_comando_ms": 1.0, "t_quadro_ms": t, **k}  # noqa: E731
    quad = lambda fim, passo=16.0: [[passo * i, i] for i in range(1, int(fim / passo) + 1)]  # noqa: E731
    r5 = rep(m4, relogio=quadros or quad(m4), **({} if lote is None else {"criados": [f"g{i}" for i in range(lote)]}), **({} if seq is None else {"sequencia": seq}))
    ps = [("3", "criar_parede", [rep(t) for t in v(m2)]), ("4a", "editar_propriedades", [rep(1.0, t_painel_ms=t) for t in v(m3)]), ("4b", "mudar_comprimento", [rep(t) for t in v(m2b)]),
          ("4c", "esperar", [rep(3000.0, relogio=parado or quad(3000.0))]), ("5b", "criar_paredes_lote", [r5])]
    return {"fluxo": fluxo, "versao": 1, "plataforma": "teste", "rhi": "gl", "base": {"arquivo": "base.ifc", "produtos": produtos}, "arquivo_ifc": None,
            "passos": [{"id": i, "cmd": c, "reps": r} for i, c, r in ps], "metas": None}

def passo(m, i):
    return next(p for p in m["passos"] if p["id"] == i)

def topo(base, alto, k=20):  # N valores: k altos (os 10% do topo) e o resto na base
    return [base] * (N - k) + [alto] * k

def buraco(g, passo_ms=16.0):  # quadros a cada passo_ms, com um único intervalo de g ms perto de 1 s (sequência crescente; o último quadro cai perto do fim)
    antes = [[passo_ms * i, i] for i in range(1, 60)]
    return antes + [[antes[-1][0] + g + passo_ms * k, 60 + k] for k in range(int((3000 - antes[-1][0] - g) / passo_ms) + 1)]

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
CASOS = [("bom", {}, True, True, None), ("m2 mediana alta", {"m2": 250.0}, False, False, "M2"), ("m2 10% dos valores em 210 (virtual passa, p95 reprova)", {"m2": topo(100.0, 210.0)}, True, False, "M2"),
         ("m2 um valor em 650 (teto reprova, p95 passa)", {"m2": topo(100.0, 650.0, 1)}, False, True, "M2"), ("m2b mediana alta", {"m2b": 300.0}, False, False, "M2b"),
         ("m3 mediana alta", {"m3": 60.0}, False, False, "M3"), ("m3 10% dos valores em 55", {"m3": topo(20.0, 55.0)}, True, False, "M3"), ("m4 lote lento", {"m4": 25000.0}, False, False, "M4"),
         ("m5 10 quadros por segundo", {"quadros": [[100.0 * i, i] for i in range(1, 31)]}, False, False, "M5"),
         ("m5 parada de 330 ms", {"quadros": [[16.0 * i, i] for i in range(1, 100)] + [[1900.0 + 16.0 * i, 100 + i] for i in range(68)]}, False, False, "M5")]
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
    m = med(m2=topo(100.0, 210.0))
    assert avaliar(tmp_path, m, nome="v")[0] == 0 and avaliar(tmp_path, m, nome="e", env={"OBIM_S04_ESTRITO": "1"})[0] == 1

def test_a_ferramenta_ignora_o_campo_metas_gravado_pelos_fluxos(ferramenta, tmp_path):  # um fluxo que se declara aprovado não vale nada: recalcular dos tempos brutos
    m = med(m2=250.0)
    m["metas"] = {"M2": {"passo": "3", "n": 20, "mediana_ms": 1.0, "p95_ms": 1.0, "max_ms": 1.0, "limite_ms": 200.0, "ok": True}}
    rc, js, _ = avaliar(tmp_path, m)
    assert rc == 1 and js["metas"]["M2"]["mediana_ms"] == pytest.approx(250.0) and not js["metas"]["M2"]["ok"]

# ---------- IFCs sintéticos: um IFC4 de verdade do fluxo A (tipo de 3 camadas, 4 paredes) e variações ----------
def para_mm(g):  # o mesmo modelo, gravado em milímetros: pontos, listas de pontos, alturas de extrusão e espessuras x 1000, unidades de comprimento/área/volume com prefixo MILLI
    for e in g.by_type("IfcCartesianPoint"):
        e.Coordinates = tuple(round(x * 1000, 6) for x in e.Coordinates)
    for e in g.by_type("IfcCartesianPointList2D") + g.by_type("IfcCartesianPointList3D"):
        e.CoordList = tuple(tuple(round(x * 1000, 6) for x in c) for c in e.CoordList)
    for e in g.by_type("IfcExtrudedAreaSolid"):
        e.Depth = round(e.Depth * 1000, 6)
    for e in g.by_type("IfcMaterialLayer"):
        e.LayerThickness = round(e.LayerThickness * 1000, 6)
    for u in g.by_type("IfcSIUnit"):
        if u.UnitType in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT"):
            u.Prefix = "MILLI"

def uso_compartilhado(g):  # B que compartilha UM IfcMaterialLayerSetUsage entre duas paredes (o que a T11c eliminou): a 2ª parede passa a apontar para o uso da 1ª; o uso e a relação antigos da 2ª somem
    ws = g.by_type("IfcWall")
    rels = [r for w in ws[:2] for r in w.HasAssociations if r.is_a("IfcRelAssociatesMaterial") and r.RelatingMaterial.is_a("IfcMaterialLayerSetUsage")]
    assert len(rels) == 2 and rels[0].RelatingMaterial != rels[1].RelatingMaterial, "a base do oráculo tem de ter 1 uso por parede"
    antigo = rels[1].RelatingMaterial
    rels[0].RelatedObjects = tuple(rels[0].RelatedObjects) + tuple(rels[1].RelatedObjects)
    g.remove(rels[1])
    g.remove(antigo)

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
          "mm": para_mm, "mm_camada": lambda g: (para_mm(g), setattr(g.by_type("IfcMaterialLayer")[1], "LayerThickness", 120.0)),  # 120 mm = o 0,12 m de "camada"
          "fogo": lambda g: setattr(next(p for p in g.by_type("IfcPropertySingleValue") if p.Name == "FireRating"), "NominalValue", g.createIfcLabel("R90")),
          "nome": lambda g: setattr(g.by_type("IfcWall")[0], "Name", "Outro nome"), "tipo": lambda g: setattr(g.by_type("IfcWallType")[0], "Name", "PAR20"),
          "pavimento": lambda g: setattr(g.by_type("IfcBuildingStorey")[0], "Name", "Pavimento 2"),
          "sem_rel_material": lambda g: ifcopenshell.api.run("material.unassign_material", g, products=[g.by_type("IfcWall")[-1]]),  # uma relação (e o uso dela) a menos
          "uso_compartilhado": uso_compartilhado,  # 1 uso e 1 relação a menos
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
    assert all(not bx.validar(ifcs[k]) for k in ("base", "guids", "sem_parede", "camada", "altura", "mm", "mm_camada", "fogo", "nome", "tipo", "pavimento", "sem_rel_material", "uso_compartilhado")), "os IFCs de controle têm de passar no validate"
    f, g = (bx.formas(__import__("ifcopenshell").open(str(ifcs[k]))) for k in ("base", "mm"))  # o IFC em mm tem a mesma geometria, em metros, que o IFC em m
    assert len(f) == len(g) == 4 and bx.igual([f[k] for k in sorted(f)], [g[k] for k in sorted(g)]) == [], "para_mm tem de preservar a geometria"
    assert bx.validar(ifcs["invalido"]) and bx.validar(ifcs["invalido_guids"]), "o IFC de controle inválido tem de reprovar no validate"

def test_uso_compartilhado_difere_so_nas_contagens_de_material_a_parede_e_igual(ifcs):  # isola a causa: sem este caso, a exceção de material (T11c) voltaria sem ninguém notar
    import ifcopenshell
    ca, cb = (assin(ifcs[k]) for k in ("base", "uso_compartilhado"))
    assert bx.igual(ca["paredes"], cb["paredes"]) == [], "cada parede tem de manter tipo, camadas, geometria e propriedades"
    dif = {c for c in ca["classes"].keys() | cb["classes"].keys() if ca["classes"].get(c) != cb["classes"].get(c)}
    assert dif == {"IfcMaterialLayerSetUsage", "IfcRelAssociatesMaterial"}, dif
    f = ifcopenshell.open(str(ifcs["uso_compartilhado"]))
    assert len(f.by_type("IfcMaterialLayerSetUsage")) == 3 and len(f.by_type("IfcRelAssociatesMaterial")) == 4  # 4 paredes: 3 usos, 3 relações de parede + 1 do tipo

@pytest.mark.parametrize("a,b,ok", [("base", "guids", True), ("base", "sem_parede", False), ("base", "camada", False), ("base", "altura", False), ("invalido", "invalido_guids", False),
                                    ("base", "mm", True), ("mm", "base", True), ("camada", "mm_camada", True), ("base", "mm_camada", False), ("base", "fogo", False), ("base", "nome", False), ("base", "tipo", False),
                                    ("base", "pavimento", False), ("base", "sem_rel_material", False), ("sem_rel_material", "base", False), ("base", "uso_compartilhado", False), ("uso_compartilhado", "base", False)],
                         ids=["globalids diferentes", "uma parede a menos", "espessura de camada", "altura da parede", "iguais mas inválidos", "A em m, B em mm", "A em mm, B em m", "0,12 m x 120 mm",
                              "camada 0,11 m x 120 mm", "FireRating diferente", "nome da parede diferente", "tipo com outro nome", "pavimento com outro nome",
                              "uma relação de material a menos em B", "uma relação de material a menos em A", "um uso compartilhado em B (so as contagens de material)", "um uso compartilhado em A"])
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

@pytest.mark.parametrize("b", [med("B", reps=N + 1), med("B", produtos=OFICIAL + 1)], ids=["repeticoes diferentes", "base diferente"])
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

# ---------- entrada inválida (LOTE_OPUS_23 §B itens 1, 2, 5, 7 e 9): código 2, mensagem clara, nunca traceback ----------
nan, inf = float("nan"), float("inf")
poe = lambda i, k, **c: lambda m: passo(m, i)["reps"][k].update(c)  # noqa: E731  (muda a repetição k do passo i)
INVALIDOS = [("NaN no M2", {}, poe("3", 7, t_quadro_ms=nan), "passo 3"), ("infinito no M2b", {}, poe("4b", 7, t_quadro_ms=inf), "passo 4b"), ("NaN no M3", {}, poe("4a", 7, t_painel_ms=nan), "passo 4a"),
             ("infinito negativo no M3", {}, poe("4a", 7, t_painel_ms=-inf), "passo 4a"), ("tempo em texto", {}, poe("3", 7, t_quadro_ms="abc"), "passo 3"),
             ("tempo negativo (t_quadro antes de t0)", {}, poe("3", 7, t0_ms=50.0, t_comando_ms=50.0, t_quadro_ms=20.0), "passo 3"), ("t_comando depois do t_quadro", {}, poe("4b", 3, t_comando_ms=500.0), "passo 4b"),
             ("t_comando antes de t0", {}, poe("3", 3, t0_ms=10.0, t_comando_ms=5.0, t_quadro_ms=30.0), "passo 3"), ("t_painel antes de t0", {}, poe("4a", 3, t0_ms=10.0, t_comando_ms=10.0, t_quadro_ms=10.0, t_painel_ms=5.0), "passo 4a"),
             ("NaN no relógio do lote", {}, lambda m: passo(m, "5b")["reps"][0]["relogio"].__setitem__(10, [nan, 11]), "passo 5b"),
             ("infinito no relógio do parado", {}, lambda m: passo(m, "4c")["reps"][0]["relogio"].__setitem__(10, [inf, 11]), "passo 4c"),
             ("repetição sem t_quadro_ms", {}, lambda m: passo(m, "3")["reps"][0].pop("t_quadro_ms"), "passo 3"), ("reps que não é lista", {}, lambda m: passo(m, "3").update(reps=5), "passo 3"),
             ("passo sem id", {}, lambda m: m["passos"].append({"cmd": "x", "reps": []}), None), ("passo sem reps", {}, lambda m: m["passos"].append({"id": "9", "cmd": "x"}), "passo 9"),
             ("1 repetição em vez de 200", {"reps": 1}, None, "passo 3"), ("199 repetições", {"reps": N - 1}, None, "passo 3"), ("lote de 10 paredes", {"lote": 10}, None, "passo 5b"),
             ("lote de 1001 paredes", {"lote": LOTE + 1}, None, "passo 5b"), ("lote sem a lista criados", {"lote": None}, None, "passo 5b"), ("5b sem sequencia", {"seq": None}, None, "passo 5b"),
             ("sequencia que nunca aparece nos quadros", {"seq": 10**6}, None, "passo 5b"),
             ("sequencia só vista depois do t_quadro (primeiro_quadro > t_quadro_ms)", {"m4": 1000.0, "quadros": [[16.0 * i, i] for i in range(1, 188)], "seq": 150}, None, "passo 5b")]

@pytest.mark.parametrize("c", INVALIDOS, ids=[c[0] for c in INVALIDOS])
def test_a_com_valor_invalido_ou_roteiro_incompleto_e_entrada_invalida_nunca_aprovacao_nem_traceback(ferramenta, tmp_path, c):
    nome, kw, mut, token = c
    m = med(**kw)
    mut and mut(m)
    rc, js, p = avaliar(tmp_path, m)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr and (token is None or token in p.stderr), (nome, rc, p.stdout[-300:], p.stderr[-600:])
    assert js is None or not js.get("aprovado"), "entrada inválida nunca aprova"

# ---------- LOTE_OPUS_24 B: 201 e 500 repetições, relógio duplicado, sequencia e criados, inteiro gigante ----------
GIG = 10**400  # json.dumps escreve os 401 dígitos; math.isfinite(GIG) levanta OverflowError
lento12 = [[1000.0 / 12 * i, i] for i in range(1, 37)]  # 12 quadros por segundo: honestamente reprova no M5 (so 12 por janela), mas duplicado pareceria 24
dobra = lambda i: lambda m: passo(m, i)["reps"][0].update(relogio=[list(x) for e in passo(m, i)["reps"][0]["relogio"] for x in (e, e)])  # noqa: E731  (cada tempo 2x)
repete = lambda i: lambda m: passo(m, i)["reps"][0]["relogio"].insert(11, list(passo(m, i)["reps"][0]["relogio"][10]))  # noqa: E731  (um único tempo repetido)
NOVOS = [("201 repetições no M2", {"reps": N + 1}, None, "passo 3"), ("201 repetições só no M3", {"m3": [10.0] * (N + 1)}, None, "passo 4a"),
         ("201 repetições só no M2b", {"m2b": [20.0] * (N + 1)}, None, "passo 4b"), ("500 repetições", {"reps": 500}, None, "passo 3"),
         ("200 a 250 ms mais 300 a 20 ms no M2 (puxam a mediana para baixo)", {"m2": [250.0] * N + [20.0] * 300}, None, "passo 3"),
         ("200 a 250 ms mais 300 a 20 ms no M2b", {"m2b": [250.0] * N + [20.0] * 300}, None, "passo 4b"),
         ("5b: cada quadro do relógio 2x (12 fps parece 24)", {"quadros": lento12}, dobra("5b"), "passo 5b"), ("5b: cada quadro do relógio 2x (relógio bom)", {}, dobra("5b"), "passo 5b"),
         ("5b: um tempo repetido no relógio", {}, repete("5b"), "passo 5b"), ("4c: cada quadro do relógio parado 2x", {}, dobra("4c"), "passo 4c"),
         ("4c: um tempo repetido no relógio parado", {}, repete("4c"), "passo 4c"), ("4c duplicado com o lote reprovando (entrada inválida vem antes do veredito)", {"quadros": lento12}, dobra("4c"), "passo 4c"),
         ("sequencia 0", {"seq": 0}, None, "passo 5b"), ("sequencia -1", {"seq": -1}, None, "passo 5b"), ("sequencia não inteira 3,5", {"seq": 3.5}, None, "passo 5b"),
         ("sequencia não inteira 0,5", {"seq": 0.5}, None, "passo 5b"), ("sequencia booleana", {"seq": True}, None, "passo 5b"),
         ("criados com 1 GlobalId repetido", {}, lambda m: passo(m, "5b")["reps"][0]["criados"].__setitem__(5, "g4"), "passo 5b"),
         ("criados todos iguais", {}, lambda m: passo(m, "5b")["reps"][0].update(criados=["g0"] * LOTE), "passo 5b"),
         ("10**400 em t_quadro_ms", {}, poe("3", 7, t_quadro_ms=GIG), "passo 3"), ("10**400 em t0_ms", {}, poe("3", 7, t0_ms=GIG), "passo 3"),
         ("10**400 em t_comando_ms", {}, poe("4b", 7, t_comando_ms=GIG), "passo 4b"), ("10**400 negativo em t0_ms", {}, poe("3", 7, t0_ms=-GIG), "passo 3"),
         ("10**400 em t_painel_ms", {}, poe("4a", 7, t_painel_ms=GIG), "passo 4a"), ("10**400 em t_quadro_ms do M2b", {}, poe("4b", 7, t_quadro_ms=GIG), "passo 4b"),
         ("10**400 no tempo do relógio do lote", {}, lambda m: passo(m, "5b")["reps"][0]["relogio"].__setitem__(10, [GIG, 11]), "passo 5b"),
         ("10**400 na sequência do relógio do lote", {}, lambda m: passo(m, "5b")["reps"][0]["relogio"].__setitem__(10, [176.0, GIG]), "passo 5b"),
         ("10**400 no relógio do parado", {}, lambda m: passo(m, "4c")["reps"][0]["relogio"].__setitem__(10, [GIG, 11]), "passo 4c"),
         ("10**400 em t_quadro_ms do 5b", {}, poe("5b", 0, t_quadro_ms=GIG), "passo 5b"), ("10**400 em sequencia", {"seq": GIG}, None, "passo 5b")]

@pytest.mark.parametrize("c", NOVOS, ids=[c[0] for c in NOVOS])
def test_lote_24_repeticoes_a_mais_relogio_duplicado_sequencia_criados_e_inteiro_gigante_sao_entrada_invalida(ferramenta, tmp_path, c):
    nome, kw, mut, token = c
    m = med(**kw)
    mut and mut(m)
    rc, js, p = avaliar(tmp_path, m)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr and token in p.stderr, (nome, rc, p.stdout[-300:], p.stderr[-600:])
    assert js is None or not js.get("aprovado"), "entrada inválida nunca aprova"

def test_controle_sem_duplicar_o_relogio_a_meta_que_falha_continua_codigo_1(ferramenta, tmp_path):  # a validação nova não pode virar rc 2 para um relógio honesto que reprova
    rc, js, p = avaliar(tmp_path, med(quadros=lento12))
    assert rc == 1 and js["aprovado"] is False and any(e.startswith("M5:") for e in js["erros"]), (rc, js and js["erros"], p.stderr[-400:])
    assert avaliar(tmp_path, med(parado=[[60.0 * i, i] for i in range(1, 51)]), nome="p")[0] == 0, "relógio parado distinto e mais lento (60 ms) continua válido"

# ---------- LOTE_OPUS_27 A1 e A2: `len(reps) != n` em todos os passos medidos; quadros do relógio fora de [t0_ms, t_quadro_ms] ----------
dois = lambda i, **c: lambda m: passo(m, i)["reps"].append(dict(copy.deepcopy(passo(m, i)["reps"][0]), **c))  # noqa: E731  (2ª repetição do passo i: cópia da 1ª, com ajustes)
lento10 = [[100.0 * i, i] for i in range(1, 31)]  # 10 quadros por segundo: o lote honesto reprova no M5 (rc 1)
r5_fora = lambda **c: lambda m: passo(m, "5b")["reps"][0].update(c)  # noqa: E731
dentro9, depois9 = [[90.0 * i, i] for i in range(1, 10)], [[905.0 + 10.0 * k, 10 + k] for k in range(9)]  # lote de 0,9 s: 9 quadros dentro (810 ms o último) e 9 logo depois do fim; maior intervalo 95 ms
buraco_parado = lambda extra: [list(x) for x in extra] + [[16.0 * i, i] for i in range(1, 188)]  # noqa: E731  (parado honesto de 16 ms mais quadros extras)
FORA = [  # (nome, parâmetros de A, mutação, estrita, token do passo no stderr)
    ("5b com 2 repetições (a 2ª a 10 quadros/s)", {}, dois("5b", relogio=lento10), False, "passo 5b"), ("5b com 2 repetições iguais, as duas boas", {}, dois("5b"), False, "passo 5b"),
    ("5b com 2 repetições na estrita", {}, dois("5b", relogio=lento10), True, "passo 5b"), ("4c com 2 repetições (a 1ª com buraco de 2,9 s)", {"parado": [[16.0 * i, i] for i in range(1, 30)] + [[2950.0 + 16.0 * i, 30 + i] for i in range(3)]}, dois("4c", relogio=[[16.0 * i, i] for i in range(1, 188)]), True, "passo 4c"),
    ("4c com 2 repetições na régua virtual", {}, dois("4c"), False, "passo 4c"),
    ("lote de 0,9 s: 9 quadros dentro e 9 logo depois do fim", {"m4": 900.0, "quadros": dentro9 + depois9}, None, False, "passo 5b"),
    ("lote de 0,9 s: 9 quadros dentro e 9 logo depois do fim (estrita)", {"m4": 900.0, "quadros": dentro9 + depois9}, None, True, "passo 5b"),
    ("lote com 1 quadro 5 ms depois do t_quadro_ms", {}, lambda m: passo(m, "5b")["reps"][0]["relogio"].append([3005.0, 190]), False, "passo 5b"),
    ("lote com 1 quadro 1 ms antes do t0_ms (t0 = 1000)", {}, r5_fora(t0_ms=1000.0, t_comando_ms=1001.0, t_quadro_ms=4000.0, relogio=[[999.0, 2]] + [[1000.0 + 16.0 * i, 2 + i] for i in range(1, 188)]), False, "passo 5b"),
    ("primeiro_quadro antes de t0 (a sequência pedida só aparece em quadro anterior ao t0)", {}, r5_fora(t0_ms=1000.0, t_comando_ms=1001.0, t_quadro_ms=4000.0, relogio=[[990.0, 3]] + [[1000.0 + 16.0 * i, 3 + i] for i in range(1, 188)]), False, "passo 5b"),
    ("primeiro_quadro antes de t0 (estrita)", {}, r5_fora(t0_ms=1000.0, t_comando_ms=1001.0, t_quadro_ms=4000.0, relogio=[[990.0, 3]] + [[1000.0 + 16.0 * i, 3 + i] for i in range(1, 188)]), True, "passo 5b"),
    ("estrita: 1 quadro em -5000 ms no parado + buraco de 150 ms no lote", {"quadros": buraco(150.0), "parado": buraco_parado([[-5000.0, 0]])}, None, True, "passo 4c"),
    ("virtual: 1 quadro em -5000 ms no parado + buraco de 150 ms no lote", {"quadros": buraco(150.0), "parado": buraco_parado([[-5000.0, 0]])}, None, False, "passo 4c"),
    ("estrita: 1 quadro em 8000 ms (depois do t_quadro) no parado + buraco de 150 ms no lote", {"quadros": buraco(150.0), "parado": buraco_parado([[8000.0, 300]])}, None, True, "passo 4c"),
    ("parado honesto com 1 quadro 1 ms antes do t0 (parado = [-1, ...])", {"parado": buraco_parado([[-1.0, 0]])}, None, False, "passo 4c")]

@pytest.mark.parametrize("c", FORA, ids=[c[0] for c in FORA])
def test_lote_27_reps_diferente_de_n_em_todos_os_passos_e_quadro_fora_da_janela_do_relogio_sao_entrada_invalida(ferramenta, tmp_path, c):
    nome, kw, mut, estrito, token = c
    m = med(**kw)
    mut and mut(m)
    rc, js, p = avaliar(tmp_path, m, estrito=estrito)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr and token in p.stderr, (nome, rc, js and js["erros"], p.stderr[-600:])
    assert js is None or not js.get("aprovado"), "entrada inválida nunca aprova"

CONTROLES = [  # relógios honestos que a validação nova NÃO pode transformar em rc 2: (nome, parâmetros, mutação, estrita, rc esperado)
    ("lote de 0,9 s só com os 9 quadros de dentro (honesto, reprova no M5)", {"m4": 900.0, "quadros": dentro9}, None, False, 1),
    ("lote de 0,9 s só com os 9 quadros de dentro (estrita)", {"m4": 900.0, "quadros": dentro9}, None, True, 1),
    ("estrita: o mesmo buraco de 150 ms com o parado honesto de 16 ms (reprova na regra do 3x)", {"quadros": buraco(150.0), "parado": buraco_parado([])}, None, True, 1),
    ("quadros exatamente em t0_ms e em t_quadro_ms (janela inclusiva)", {"quadros": [[0.0, 2]] + [[16.0 * i, 2 + i] for i in range(1, 188)] + [[3000.0, 190]], "parado": [[0.0, 0]] + buraco_parado([]) + [[3000.0, 300]]}, None, False, 0),
    ("lote com t0 = 1000 e todos os quadros dentro de [1000, 4000]", {}, r5_fora(t0_ms=1000.0, t_comando_ms=1001.0, t_quadro_ms=4000.0, relogio=[[1000.0 + 16.0 * i, 2 + i] for i in range(1, 188)] + [[4000.0, 300]]), False, 0)]

@pytest.mark.parametrize("c", CONTROLES, ids=[c[0] for c in CONTROLES])
def test_lote_27_controles_honestos_nao_viram_entrada_invalida(ferramenta, tmp_path, c):
    nome, kw, mut, estrito, rc_esp = c
    m = med(**kw)
    mut and mut(m)
    rc, js, p = avaliar(tmp_path, m, estrito=estrito)
    assert rc == rc_esp and js is not None and js["aprovado"] is (rc_esp == 0), (nome, rc, js and js["erros"], p.stderr[-600:])

def test_inteiro_gigante_em_base_produtos_da_estrita_e_entrada_invalida(ferramenta, tmp_path):
    rc, js, p = avaliar(tmp_path, med(produtos=GIG), estrito=True)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr, (rc, p.stderr[-600:])

def test_rede_de_seguranca_de_main_imprime_a_linha_e_depois_o_traceback(ferramenta, tmp_path, monkeypatch, capsys):  # erro de programação injetado em `avaliar` (nome fixado no contrato)
    sp = importlib.util.spec_from_file_location("medir_s04_rede", MEDIR)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    pasta = gravar(tmp_path / "a", med())
    def quebra(*a, **k):
        raise KeyError("erro_de_programacao_injetado")
    monkeypatch.setattr(mod, "avaliar", quebra)
    rc = mod.main(["--a", str(pasta), "--json", str(tmp_path / "x.json")])
    err = capsys.readouterr().err
    assert rc == 2 and err.startswith("ENTRADA INVÁLIDA:"), (rc, err[-600:])
    assert "Traceback (most recent call last)" in err and "erro_de_programacao_injetado" in err and err.index("ENTRADA INVÁLIDA:") < err.index("Traceback"), err[-800:]
    assert not (tmp_path / "x.json").exists(), "erro de programação nunca grava resultado"

def test_o_roteiro_r_ainda_diz_200_repeticoes_e_lote_de_1000():  # os números do contrato vêm de fluxo_a/roteiro_r.json
    assert (ROT["3"]["n"], ROT["4a"]["n"], ROT["4b"]["n"], ROT["5b"]["quantidade"]) == (200, 200, 200, 1000)
    assert (int(ROT["4c"].get("n", 1)), int(ROT["5b"].get("n", 1))) == (1, 1), "4c e 5b não definem `n`: padrão 1 (LOTE_OPUS_27 A1)"

def test_relogio_fora_de_ordem_da_o_mesmo_resultado_do_ordenado(ferramenta, tmp_path):  # a ferramenta ordena t antes do np.diff
    bom = avaliar(tmp_path, med(), nome="o")[1]
    for nome, mexe in (("ultimo na frente", lambda r: r.insert(0, r.pop())), ("invertido", lambda r: r.reverse())):
        m = med()
        mexe(passo(m, "5b")["reps"][0]["relogio"])
        mexe(passo(m, "4c")["reps"][0]["relogio"])
        rc, js, p = avaliar(tmp_path, m, nome=nome[:3])
        assert rc == 0 and js["metas"]["M5"] == bom["metas"]["M5"], (nome, js and js["erros"], p.stderr[-400:])

def test_sequencia_que_cai_a_zero_no_reenvio_da_cena_nao_atrapalha_primeiro_quadro(ferramenta, tmp_path):
    m = med(seq=60)
    r = passo(m, "5b")["reps"][0]["relogio"]
    for i in range(49, 53):
        r[i][1] = 0
    rc, js, p = avaliar(tmp_path, m)
    assert rc == 0 and js["aprovado"], (js and js["erros"], p.stderr[-400:])

def test_m5_so_a_regra_de_3x_o_intervalo_parado_reprova_na_estrita(ferramenta, tmp_path):  # o buraco é menor que 200 ms: só a comparação com o parado pega
    for g, passo_parado, rc_esp in ((150.0, 16.0, 1), (190.0, 60.0, 1), (170.0, 60.0, 0)):  # 3 x max(33,3; parado): 100; 180; 180
        tp = [[passo_parado * i, i] for i in range(1, int(3000 / passo_parado) + 1)]
        rc, js, p = avaliar(tmp_path, med(quadros=buraco(g), parado=tp), estrito=True)
        assert rc == rc_esp and (rc_esp == 0 or (len(js["erros"]) == 1 and js["erros"][0].startswith("M5:") and not js["metas"]["M5"]["ok"])), (g, passo_parado, js and js["erros"], p.stderr[-400:])
        assert js["metas"]["M5"]["maior_intervalo_ms"] == pytest.approx(g, abs=1e-6) and js["metas"]["M5"]["maior_intervalo_ms"] < 200.0

@pytest.mark.parametrize("como", ["flag", "variavel"])
@pytest.mark.parametrize("produtos", [None, 300, OFICIAL - 1])
def test_estrita_exige_o_modelo_oficial_de_3000_paredes(ferramenta, tmp_path, como, produtos):  # a régua do PO sobre a base errada não vale
    m = med(produtos=produtos)
    produtos is None and m["base"].pop("produtos")
    rc, js, p = avaliar(tmp_path, m, estrito=como == "flag", env={"OBIM_S04_ESTRITO": "1"} if como == "variavel" else None)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr and "3000" in p.stderr, (rc, p.stderr[-400:])

def test_estrita_com_3000_paredes_e_a_virtual_com_base_pequena_funcionam(ferramenta, tmp_path):
    assert avaliar(tmp_path, med(produtos=OFICIAL), estrito=True, nome="e")[0] == 0 and avaliar(tmp_path, med(produtos=300), nome="v")[0] == 0

def test_b_ou_a_com_passo_malformado_e_entrada_invalida_nao_traceback(ferramenta, tmp_path, ifcs):
    for nome, mut in (("sem id", lambda m: m["passos"].append({"cmd": "x", "reps": []})), ("sem reps", lambda m: m["passos"].append({"id": "9", "cmd": "x"})),
                      ("reps que não é lista", lambda m: passo(m, "3").update(reps=None)), ("NaN em B", poe("3", 7, t_quadro_ms=nan))):
        b = med("B")
        mut(b)
        rc, js, p = avaliar(tmp_path, med(), b, ifc_a=ifcs["base"], ifc_b=ifcs["guids"], nome=nome[:3])
        assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr, (nome, rc, p.stderr[-600:])

@pytest.mark.parametrize("lado", ["a", "b"])
@pytest.mark.parametrize("lixo", ["isto não é um IFC\n", "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('x'),'2;1');\n"], ids=["texto qualquer", "cabeçalho cortado"])
def test_ifc_ilegivel_e_entrada_invalida_nao_traceback(ferramenta, tmp_path, ifcs, lado, lixo):
    ruim = tmp_path / "lixo.ifc"
    ruim.write_text(lixo, encoding="utf-8")
    ia, ib = (ruim, ifcs["guids"]) if lado == "a" else (ifcs["base"], ruim)
    rc, js, p = avaliar(tmp_path, med(), med("B"), ifc_a=ia, ifc_b=ib)
    assert rc == 2 and p.stderr.startswith("ENTRADA INVÁLIDA:") and "Traceback" not in p.stderr, (rc, p.stderr[-600:])

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
    if aux.ESTRITO and int(BASE) < OFICIAL:
        pular(f"OBIM_S04_ESTRITO=1 exige a base oficial: OBIM_S04_BASE={BASE} < {OFICIAL} (a ferramenta devolve código 2)")
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
    return {"classes": dict(Counter(e.is_a() for e in f if e.is_a() not in bx.LIVRES)), "paredes": ps}

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
