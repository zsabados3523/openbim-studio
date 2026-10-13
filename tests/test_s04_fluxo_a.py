# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do fluxo A (S04-T11; LOTE_OPUS_9 §1.1, §1.4 regras 1-8, §2, §4 etapa 3; contrato em prototypes/s04/fluxo_a/CONTRATO.md).
GUARDA: pula enquanto `prototypes/s04/fluxo_a/fluxo_a.py` não existir; FALHA com OBIM_S04_T11_OBRIGATORIO=1. Casos sem janela rodam no processo;
os gráficos rodam em SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1) e o roteiro R inteiro roda UMA vez.
Suposições do oráculo (o Opus confere): parede = prisma retangular = 12 triângulos; a base é `scripts/gerar_modelo_grande.py` com OBIM_S04_BASE paredes
(padrão 300; oficial 3000); régua do CI virtual = mediana < limite e nenhum valor acima de TETO x limite (M2, M2b, M3), M4 < 20 s, M5 pela régua do lote 11
(maior intervalo < 100 ms, >= 20 quadros por janela de 1 s, <= 3x o parado); OBIM_S04_ESTRITO=1 (máquina do PO) troca por p95 < limite.
Fora do escopo (T12): M1, M6, M7 e a comparação A x B. Sentinelas sem fluxo_a: roteiro, ifcopenshell sozinho e a conta das metas."""
import json
import locale
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import s04_fluxo_aux as aux
from s04_fluxo_aux import FIRE, PAREDE, PASTA, ROTEIRO, TIPO, calcular, estado, fire, forma, ids_modelo, sintetico, veredito
from test_s04_viewport import caso as _caso  # xvfb-run, LC_ALL=C, resultado em JSON

caso = lambda nome, *a, **k: _caso(nome, *a, alvo=aux.AQUI, **k)  # noqa: E731
OBRIGATORIO = os.environ.get("OBIM_S04_T11_OBRIGATORIO") == "1"
BASE = os.environ.get("OBIM_S04_BASE", "300")
MUTA = {"criar_tipo", "criar_parede", "criar_paredes_lote", "editar_propriedades", "mudar_comprimento", "mover", "apagar", "desfazer", "refazer"}
GEO = {"criar_parede", "criar_paredes_lote", "mudar_comprimento", "mover"}  # comandos cuja `geometria` é tudo o que mudou
CMDS = MUTA | {"abrir", "selecionar", "orbitar", "camera_mover", "aproximar", "enquadrar", "camera", "animar_orbita", "parar_animacao", "esperar", "gravar"}

def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! aguarda S04-T11: {msg} (oráculo do fluxo A NÃO FOI EXECUTADO) !!!\n")

@pytest.fixture(scope="module")
def fa():
    if not (PASTA / "fluxo_a.py").is_file():
        pular("prototypes/s04/fluxo_a/fluxo_a.py ausente")
    import fluxo_a
    return fluxo_a

@pytest.fixture
def novo(fa, tmp_path):
    def abrir(base=None):
        return fa.FluxoA(base, janela=False, saida=tmp_path / "saida")
    return abrir

# ---------- sentinelas: rodam hoje, sem fluxo_a ----------
def test_roteiro_r_tem_os_7_passos_do_lote_9():
    r = json.loads(ROTEIRO.read_text())
    ps = {p["id"]: p for p in r["passos"]}
    assert r["versao"] == 1 and len({p["id"] for p in r["passos"]}) == len(r["passos"]) and {p["cmd"] for p in r["passos"]} <= CMDS
    assert [ps[i]["cmd"] for i in ("1", "2", "3", "4a", "4b", "5b", "6a", "6b", "7")] == ["abrir", "criar_tipo", "criar_parede", "editar_propriedades",
                                                                                        "mudar_comprimento", "criar_paredes_lote", "desfazer", "refazer", "gravar"]
    assert (ps["3"]["n"], ps["4a"]["n"], ps["4b"]["n"], ps["5b"]["quantidade"]) == (200, 200, 200, 1000) and ps["2"]["camadas_m"] == [0.02, 0.11, 0.02]
    assert ps["4b"]["comprimento"] == 5.0 and ps["3"]["comprimento"] == 4.0 and (ps["3"]["altura"], ps["3"]["espessura"]) == (2.8, 0.15)
    ordem = [p["id"] for p in r["passos"]]
    assert ordem.index("4c") < ordem.index("5a") < ordem.index("5b") < ordem.index("5c") < ordem.index("6a") < ordem.index("6b") < ordem.index("7")

def test_ifcopenshell_sozinho_desfaz_e_refaz_como_o_oraculo_supoe():  # a base de todos os casos de desfazer; o padrão de 64 desfazeres é medido
    import ifcopenshell.api as A
    api = A.run
    f = api("project.create_file")
    assert f.history_size == 64
    f.set_history_size(100000)
    api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f)
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=api("context.add_context", f, context_type="Model"))
    f.begin_transaction()
    w = api("root.create_entity", f, ifc_class="IfcWall", name="a")
    api("geometry.assign_representation", f, product=w, representation=api("geometry.add_wall_representation", f, context=corpo, length=4.0, height=2.8, thickness=0.15))
    api("geometry.edit_object_placement", f, product=w, matrix=np.eye(4))
    f.end_transaction()
    g, e0 = w.GlobalId, estado(f)
    f.begin_transaction()
    antiga = w.Representation.Representations[0]
    api("geometry.unassign_representation", f, product=w, representation=antiga)
    api("geometry.remove_representation", f, representation=antiga)
    api("geometry.assign_representation", f, product=w, representation=api("geometry.add_wall_representation", f, context=corpo, length=5.0, height=2.8, thickness=0.15))
    f.end_transaction()
    e1 = estado(f)
    assert e1 != e0 and forma(f.by_guid(g))[1][0] == 5.0
    f.undo()
    assert estado(f) == e0
    f.redo()
    assert estado(f) == e1
    f.begin_transaction()
    api("root.remove_product", f, product=f.by_guid(g))
    f.end_transaction()
    assert g not in ids_modelo(f)
    f.undo()
    assert estado(f) == e1
    for i in range(700):  # o roteiro R tem ~600 transações
        f.begin_transaction()
        api("root.create_entity", f, ifc_class="IfcWall")
        f.end_transaction()
    for i in range(700):
        f.undo()
    assert len(f.by_type("IfcWall")) == 1

def test_conta_das_metas_aprova_o_bom_e_reprova_o_ruim():
    assert not veredito(calcular(sintetico()))
    ruim = [sintetico(t_ms=700), sintetico(painel=500), sintetico(quadros=[[100.0 * i, i] for i in range(1, 31)]), sintetico(quadros=[[16.0 * i, i] for i in range(1, 100)] + [[1750.0 + 16.0 * i, 100 + i] for i in range(80)])]
    assert all(veredito(calcular(m)) for m in ruim)
    assert calcular(sintetico())["M5"]["maior_intervalo_ms"] == pytest.approx(16.0, abs=1e-9)

# ---------- casos sem janela (processo do pytest, só ifcopenshell) ----------
def test_cada_comando_devolve_os_globalids_certos(novo):
    import ifcopenshell.util.element as E
    f = novo()
    def diff(cmd):  # (criados, apagados, devolvido), vistos de fora pelo ifcopenshell
        a = ids_modelo(f.ifc)
        r = f.executar(cmd)
        b = ids_modelo(f.ifc)
        return b - a, a - b, r
    novos, sumiu, r = diff(TIPO)
    assert len(r) == 1 and set(r) == novos and not sumiu and len(r[0]) == 22
    tipo = f.ifc.by_guid(r[0])
    assert tipo.is_a("IfcWallType") and [c.LayerThickness for c in E.get_material(tipo).MaterialLayers] == [0.02, 0.11, 0.02]
    guias = []
    for g in range(52):  # a grade vira de linha na 51a parede
        novos, sumiu, r = diff(PAREDE)
        assert len(r) == 1 and set(r) == novos and not sumiu and f.ultimo["criados"] == r and not f.ultimo["apagados"], r
        guias += r
    assert len(set(guias)) == 52 and len(f.historico) == 53
    for g in (0, 1, 49, 50, 51):
        w = f.ifc.by_guid(guias[g])
        assert w.is_a("IfcWall") and E.get_type(w) == tipo and E.get_container(w).is_a("IfcBuildingStorey")
        assert E.get_material(w, should_inherit=False).is_a("IfcMaterialLayerSetUsage")
        assert {x.RepresentationIdentifier for x in w.Representation.Representations} == {"Body", "Axis"}
        assert forma(w) == (12, [4.0, 0.15, 2.8], [g % 50 * 5.0, g // 50 * 4.0, 0.0])
    a = guias[0]
    novos, sumiu, r = diff({"cmd": "editar_propriedades", "alvo": a, "nome": "Muro A", "propriedades": {FIRE: "R90"}})
    assert r == [a] and not novos and not sumiu and f.ifc.by_guid(a).Name == "Muro A" and fire(f.ifc.by_guid(a)) == "R90" and f.selecionado == a
    assert f.ultimo["alterados"] == [a] and not f.ultimo["geometria"] and "Muro A" in f.painel_texto() and "R90" in f.painel_texto()
    novos, sumiu, r = diff({"cmd": "mudar_comprimento", "alvo": a, "comprimento": 5.0})
    assert r == [a] and not novos and not sumiu and forma(f.ifc.by_guid(a)) == (12, [5.0, 0.15, 2.8], [0.0, 0.0, 0.0]) and f.ultimo["geometria"] == [a]
    novos, sumiu, r = diff({"cmd": "mover", "alvo": a, "dx": 1.5, "dy": -2.0, "dz": 0.25})
    assert r == [a] and forma(f.ifc.by_guid(a)) == (12, [5.0, 0.15, 2.8], [1.5, -2.0, 0.25])
    novos, sumiu, r = diff({"cmd": "apagar", "alvo": a})
    assert r == [a] and sumiu == {a} and not novos and f.ultimo["apagados"] == [a] and not f.ultimo["criados"]
    novos, sumiu, r = diff({"cmd": "criar_paredes_lote", "quantidade": 25, "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15})
    assert len(r) == 25 and set(r) == novos and len(set(r) | set(guias)) == 77 and len(f.historico) == 58
    for cmd in ({"cmd": "mover", "alvo": "0" * 22, "dx": 1, "dy": 0, "dz": 0}, {"cmd": "inexistente"}, dict(PAREDE, tipo="NAOEXISTE")):  # erro: ValueError, nada muda
        e0, h0 = estado(f.ifc)[0], len(f.historico)
        with pytest.raises(ValueError):
            f.executar(cmd)
        assert estado(f.ifc)[0] == e0 and len(f.historico) == h0 and not f.trava.locked()

def test_desfazer_e_refazer_devolvem_o_ifc_ao_estado_anterior(novo):
    f = novo()
    assert f.executar({"cmd": "desfazer"}) == [] and f.executar({"cmd": "refazer"}) == []
    seq, estados, guias = [{"cmd": "criar_tipo", "nome": "PAR15", "camadas_m": [0.02, 0.11, 0.02]}], [estado(f.ifc)], []
    seq += [PAREDE, PAREDE]
    for c in seq:
        guias.append(f.executar(c))
        estados.append(estado(f.ifc))
    a, b = guias[1][0], guias[2][0]
    mais = [{"cmd": "editar_propriedades", "alvo": a, "nome": "X", "propriedades": {FIRE: "R30"}}, {"cmd": "mudar_comprimento", "alvo": a, "comprimento": 6.0},
            {"cmd": "mover", "alvo": b, "dx": 3.0, "dy": 0.0, "dz": 0.0}, {"cmd": "apagar", "alvo": a}]
    for c in mais:
        guias.append(f.executar(c))
        estados.append(estado(f.ifc))
    assert len(f.historico) == len(estados) - 1
    for i in range(len(estados) - 1, 0, -1):  # desfaz um a um: devolve os GlobalIds do comando e o IFC do passo anterior
        assert f.executar({"cmd": "desfazer"}) == guias[i - 1] and estado(f.ifc) == estados[i - 1], f"desfazer do passo {i}"
    assert not f.historico and f.executar({"cmd": "desfazer"}) == []
    for i in range(1, len(estados)):
        assert f.executar({"cmd": "refazer"}) == guias[i - 1] and estado(f.ifc) == estados[i], f"refazer do passo {i}"
    f.executar({"cmd": "desfazer"})
    f.executar(PAREDE)  # comando novo apaga a pilha de refazer
    assert f.executar({"cmd": "refazer"}) == []

def test_lote_de_paredes_e_uma_transacao_so(novo):
    f = novo()
    f.executar(TIPO)
    e0, h0 = estado(f.ifc), len(f.historico)
    r = f.executar({"cmd": "criar_paredes_lote", "quantidade": 120, "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15})
    e1 = estado(f.ifc)
    assert len(set(r)) == 120 and len(f.historico) == h0 + 1 and len(f.ifc.by_type("IfcWall")) == 120
    assert sorted(f.executar({"cmd": "desfazer"})) == sorted(r) and estado(f.ifc) == e0 and not f.ifc.by_type("IfcWall")
    assert sorted(f.executar({"cmd": "refazer"})) == sorted(r) and estado(f.ifc) == e1

def test_trava_do_modelo_um_escritor_por_vez(novo, fa):
    f = novo()
    f.executar(TIPO)
    e0, h0 = estado(f.ifc), len(f.historico)
    with f.trava:  # outro escritor está no meio de um comando
        for espera in (0, 0.05):
            with pytest.raises(fa.ModeloOcupado):
                f.executar(PAREDE, espera=espera)
        assert estado(f.ifc) == e0 and len(f.historico) == h0
    saida = []
    f.trava.acquire()
    t = threading.Thread(target=lambda: saida.append(f.executar(PAREDE)))
    t.start()
    time.sleep(0.3)
    assert t.is_alive() and not saida and estado(f.ifc) == e0, "sem espera=0 o segundo escritor deve esperar a trava"
    f.trava.release()
    t.join(20)
    assert not t.is_alive() and len(saida[0]) == 1 and len(f.ifc.by_type("IfcWall")) == 1 and not f.trava.locked()
    ts = [threading.Thread(target=lambda: [f.executar(PAREDE) for _ in range(40)]) for _ in range(2)]  # corrida real: nada se perde nem se duplica
    [x.start() for x in ts]
    [x.join(120) for x in ts]
    gs = [w.GlobalId for w in f.ifc.by_type("IfcWall")]
    assert len(gs) == 81 == len(set(gs)) and len(f.historico) == h0 + 81 and not f.trava.locked()
    for _ in range(81):  # mais que os 64 desfazeres do padrão do ifcopenshell
        f.executar({"cmd": "desfazer"})
    assert estado(f.ifc) == e0

def test_leitura_durante_a_escrita_nao_espera_e_mostra_o_valor_anterior(novo):
    f = novo()
    f.executar(TIPO)
    g = f.executar(PAREDE)[0]
    f.executar({"cmd": "editar_propriedades", "alvo": g, "nome": "Antes", "propriedades": {FIRE: "R60"}})
    assert f.ler_propriedade(g, "Name") == "Antes" and f.ler_propriedade(g, FIRE) == "R60"
    with f.trava:  # um escritor está no meio da transação (o nome já mudou no modelo)
        f.ifc.by_guid(g).Name = "Durante"
        t0 = time.perf_counter()
        v = f.ler_propriedade(g, "Name")
        assert time.perf_counter() - t0 < 0.05 and v == "Antes", "o painel não pode esperar nem tocar no modelo durante a escrita"
    assert f.ler_propriedade(g, "Name") == "Durante"

def test_gravar_corrige_a_localidade_e_o_ifc_reabre_igual(novo, tmp_path):
    import ifcopenshell
    f = novo()
    f.executar(TIPO)
    g = f.executar(PAREDE)[0]
    f.executar({"cmd": "editar_propriedades", "alvo": g, "nome": "Muro", "propriedades": {FIRE: "R60"}})
    nome = next((n for n in ("pt_BR.UTF-8", "Portuguese_Brazil.1252", "pt_BR") if not sem_locale(n)), None)
    nome or pytest.skip("\n!!! SEM LOCALIDADE pt_BR NESTA MÁQUINA: o caso 'gravar com vírgula' NÃO FOI EXECUTADO !!!\n")
    try:
        locale.setlocale(locale.LC_NUMERIC, nome)
        assert locale.localeconv()["decimal_point"] == ","
        f.executar({"cmd": "gravar", "arquivo": "loc.ifc"})
        assert locale.localeconv()["decimal_point"] == ".", "gravar tem de chamar garantir_numerico_c() antes de escrever"
    finally:
        locale.setlocale(locale.LC_NUMERIC, "C")
    g2 = ifcopenshell.open(str(tmp_path / "saida" / "loc.ifc"))
    assert estado(g2) == estado(f.ifc) and forma(g2.by_guid(g))[1] == [4.0, 0.15, 2.8]

def sem_locale(n):  # verdadeiro se a máquina não tem a localidade
    try:
        locale.setlocale(locale.LC_NUMERIC, n)
        return False
    except locale.Error:
        return True
    finally:
        locale.setlocale(locale.LC_NUMERIC, "C")

def test_mini_roteiro_sem_janela_resolve_alvos_repeticoes_e_grava_medicao(novo, tmp_path):
    import ifcopenshell
    mini = {"versao": 1, "passos": [dict(TIPO, id="t"), dict(PAREDE, id="p", n=3), {"id": "e", "cmd": "editar_propriedades", "n": 3, "alvo": {"passo": "p"}, "nome": "Muro {r}", "propriedades": {FIRE: "R60"}},
                                    {"id": "m", "cmd": "mudar_comprimento", "n": 3, "alvo": {"passo": "p"}, "comprimento": 5.0}, {"id": "x", "cmd": "apagar", "alvo": {"passo": "p", "k": 1}},
                                    {"id": "d", "cmd": "desfazer"}, {"id": "r", "cmd": "refazer"}, {"id": "w", "cmd": "gravar", "arquivo": "mini.ifc"}]}
    (tmp_path / "mini.json").write_text(json.dumps(mini))
    f = novo()
    med = f.executar_roteiro(tmp_path / "mini.json")
    por = {p["id"]: p for p in med["passos"]}
    gs = [x["guids"][0] for x in por["p"]["reps"]]
    assert len(set(gs)) == 3 and [x["guids"] for x in por["e"]["reps"]] == [[g] for g in gs] == [x["guids"] for x in por["m"]["reps"]]
    assert por["x"]["reps"][0]["apagados"] == [gs[1]] and por["d"]["reps"][0]["criados"] == [gs[1]] and por["d"]["reps"][0]["guids"] == [gs[1]]
    assert por["r"]["reps"][0]["apagados"] == [gs[1]] and por["w"]["reps"][0]["guids"] == []
    g2 = ifcopenshell.open(med["arquivo_ifc"])
    assert {w.Name for w in g2.by_type("IfcWall")} == {"Muro 0", "Muro 2"}, "o passo x apagou a parede 1 (desfazer e refazer a apagaram de novo)"
    arq = json.loads(Path(med["arquivo_medicao"]).read_text())
    assert arq["fluxo"] == "A" and Path(med["arquivo_medicao"]).name == "medicao.json" and [p["id"] for p in arq["passos"]] == [p["id"] for p in mini["passos"]]
    assert all(r["t0_ms"] <= r["t_comando_ms"] <= r["t_quadro_ms"] for p in arq["passos"] for r in p["reps"])

# ---------- casos gráficos (subprocesso sob xvfb-run) ----------
@pytest.fixture(scope="module")
def tela(fa):
    import importlib.util
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")

@pytest.fixture(scope="module")
def rot(tela):  # o roteiro R inteiro, uma vez só
    return caso("roteiro", BASE, limite=900)

def reps(med):
    return [(p["id"], p["cmd"], x) for p in med["passos"] for x in p["reps"]]

def test_roteiro_r_cada_passo_devolve_os_globalids_que_o_ifc_mostra(rot):
    med, ch = rot["med"], rot["chamadas"]
    rs, por = reps(med), {p["id"]: p for p in med["passos"]}
    assert [c["cmd"] for c in ch] == [x[1] for x in rs] and len(rs) == sum(p.get("n", 1) for p in json.loads(ROTEIRO.read_text())["passos"]) == 611
    tamanho = {"criar_parede": 1, "criar_tipo": 1, "criar_paredes_lote": 1000, "editar_propriedades": 1, "mudar_comprimento": 1, "apagar": 1}
    for (i, cmd, x), c in zip(rs, ch):
        assert x["guids"] == c["r"] and sorted(x["criados"]) == c["criados"] and sorted(x["apagados"]) == c["apagados"], f"{i} {cmd}: o fluxo diz uma coisa e o ifcopenshell outra"
        if cmd in MUTA:
            assert set(x["guids"]) == set(x["criados"]) | set(x["alterados"]) | set(x["apagados"]) and len(set(x["guids"])) == len(x["guids"]), (i, cmd)
        if cmd in tamanho:
            assert len(x["guids"]) == tamanho[cmd], (i, cmd)
        elif cmd not in ("abrir", "selecionar", "desfazer", "refazer", "mover"):
            assert x["guids"] == [], (i, cmd)
    g3 = [x["guids"][0] for x in por["3"]["reps"]]
    assert len(set(g3)) == 200 and [x["guids"] for x in por["4a"]["reps"]] == [x["guids"] for x in por["4b"]["reps"]] == [[g] for g in g3]
    assert sorted(por["6a"]["reps"][0]["apagados"]) == sorted(por["5b"]["reps"][0]["guids"]) == sorted(por["6b"]["reps"][0]["criados"]) and not set(g3) & set(por["5b"]["reps"][0]["guids"])
    assert set(por["1"]["reps"][0]["guids"]) == set(rot["base_guids"]) and set(por["3c"]["reps"][0]["guids"]) <= set(rot["base_guids"]) | set(g3) and len(por["3c"]["reps"][0]["guids"]) <= 1

def test_roteiro_r_atualiza_a_cena_depois_de_cada_transacao_desfazer_e_refazer_com_a_trava_presa(rot):
    med, ch = rot["med"], rot["chamadas"]
    seqs = [k["seq"] for c in ch for k in c["chamadas"]]
    assert seqs == rot["sequencias"] and all(a < b for a, b in zip(seqs, seqs[1:])), "as sequências devolvidas pela Cena têm de crescer sempre (não as de relogio())"
    for (i, cmd, x), c in zip(reps(med), ch):
        ks = c["chamadas"]
        if cmd in MUTA:
            assert len(ks) == 1 and ks[0]["m"] == "atualizar" and ks[0]["seq"] == x["sequencia"], f"{i} {cmd}: exatamente 1 Cena.atualizar por transação, desfazer e refazer"
            k = ks[0]
            assert k["trava"], f"{i} {cmd}: Cena.atualizar rodou sem a trava do modelo presa (regra 7)"
            assert sorted(k["remover"]) == c["apagados"], (i, cmd)  # estado resultante: some da cena o que deixou de existir
            if cmd in ("desfazer", "refazer"):
                assert set(k["guids"]) == set(x["guids"]) - set(c["apagados"]) and sorted(k["guids"]) == sorted(x["geometria"]), (i, cmd)
            else:
                assert sorted(k["guids"]) == sorted(x["geometria"]) and bool(x["geometria"]) == (cmd in GEO), (i, cmd)
        elif cmd == "abrir":
            assert ks and x["sequencia"] == ks[-1]["seq"]
        else:
            assert not ks and x["sequencia"] is None, (i, cmd)
    por = {p["id"]: p for p in med["passos"]}
    assert por["5b"]["reps"][0]["sequencia"] < por["6a"]["reps"][0]["sequencia"] < por["6b"]["reps"][0]["sequencia"]
    assert all(len(x["relogio"]) > 5 for i, cmd, x in reps(med) if cmd in ("esperar", "criar_paredes_lote"))

def test_roteiro_r_a_cena_tem_os_triangulos_do_ifc(rot):
    por = {p["id"]: p["reps"] for p in rot["med"]["passos"]}
    nb = len(rot["base_guids"])
    esperado = {"1": nb, "3": nb + 200, "4a": nb + 200, "4b": nb + 200, "5b": nb + 1200, "6a": nb + 200, "6b": nb + 1200}
    assert {i: por[i][-1]["triangulos_cena"] for i in esperado} == {i: 12 * n for i, n in esperado.items()}
    assert por["6b"][-1]["triangulos_cena"] == rot["tri_ref"], "a cena difere da conta independente pelo ifcopenshell no fim do roteiro"

def test_roteiro_r_o_ifc_gravado_reabre_igual_e_sem_virgula_decimal(rot):
    s = rot["salvo"]
    assert s["mesmos_guids"] and s["paredes"] == len(rot["base_guids"]) + 1200 and s["tipos"] == 1 and not s["erros"], s
    assert s["nomes"] == [f"Parede R-{k}" for k in range(200)] and s["fire"] == ["R60"] and s["dims_200"] == [[5.0, 0.15, 2.8]] and s["dims_lote"] == [[4.0, 0.15, 2.8]]
    assert rot["ponto_decimal"] == "." and rot["lc_numeric"] == "C"

def test_roteiro_r_grava_medicao_json_com_os_campos_e_as_metas_do_lote_9(rot):
    med, c = rot["med"], calcular(rot["med"])
    assert json.loads(Path(rot["arquivo_medicao"]).read_text()) == med and Path(rot["arquivo_medicao"]).name == "medicao.json"
    assert med["fluxo"] == "A" and med["versao"] == 1 and {"plataforma", "rhi", "base"} <= med.keys() and med["base"]["produtos"] == len(rot["base_guids"])
    for i, cmd, x in reps(med):
        assert {"r", "guids", "criados", "alterados", "apagados", "geometria", "sequencia", "t0_ms", "t_comando_ms", "t_quadro_ms", "ms_total", "triangulos_cena"} <= x.keys(), (i, cmd)
        assert x["t0_ms"] <= x["t_comando_ms"] <= x["t_quadro_ms"] and x["ms_total"] == pytest.approx(x["t_quadro_ms"] - x["t0_ms"], abs=1e-6), (i, cmd)
        assert ("t_painel_ms" in x) == (cmd == "editar_propriedades") and x.get("t_painel_ms", x["t0_ms"]) >= x["t0_ms"], (i, cmd)
    m = med["metas"]
    assert m["M1"] is None and m["M6"] is None and {"M2", "M2b", "M3", "M4", "M5"} <= m.keys()
    for k, lim in (("M2", 200), ("M2b", 200), ("M3", 50), ("M4", 20000)):  # as metas gravadas são as dos tempos brutos (percentil linear, 1e-6 ms)
        assert {a: m[k][a] for a in ("mediana_ms", "p95_ms", "max_ms")} == pytest.approx({a: c[k][a] for a in ("mediana_ms", "p95_ms", "max_ms")}, abs=1e-6), k
        assert m[k]["n"] == c[k]["n"] and m[k]["limite_ms"] == lim, k
    for a in ("maior_intervalo_ms", "maior_intervalo_parado_ms"):
        assert m["M5"][a] == pytest.approx(c["M5"][a], abs=1e-6), a
    print("METAS", json.dumps(c))

def test_roteiro_r_metas_dentro_da_regua_do_ci_virtual(rot):  # a régua do CI não é o número oficial: esse é o do PO (OBIM_S04_ESTRITO=1)
    assert not (e := veredito(calcular(rot["med"]))), e

def test_desfazer_e_refazer_devolvem_cena_imagem_e_selecao_ao_estado_anterior(tela):
    c = caso("cena", limite=600)
    assert c["janela"] and c["viva"], c
    for op, v in c["ops"].items():
        assert v["tri"][2] == v["tri"][0] and v["tri"][3] == v["tri"][1] and v["ids"] == [True, True, op in ("criar_parede", "apagar")], (op, v)
        assert (v["tri"][0] != v["tri"][1]) == (op in ("criar_parede", "apagar")), (op, v)
        assert v["muda"] > 150 and v["desfaz"] <= 25 and v["refaz"] <= 25, f"{op}: pixels que mudaram {v['muda']}, depois de desfazer {v['desfaz']}, depois de refazer {v['refaz']}"
    assert c["sel"] == {"centro": c["g1"], "canto": None, "apos_apagar": None, "apos_desfazer": c["g1"]}, c["sel"]

def test_localidade_numerica_c_depois_de_criar_a_aplicacao(tela):
    if sys.platform == "win32" or sem_locale("pt_BR.UTF-8"):
        pytest.skip("\n!!! SEM pt_BR.UTF-8 (ou Windows): o caso da localidade com a aplicação NÃO FOI EXECUTADO (o do gravar roda em test_gravar_corrige...) !!!\n")
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "LC_ALL")} | {"QT_QPA_PLATFORM": "xcb", "LIBGL_ALWAYS_SOFTWARE": "1", "LANG": "pt_BR.UTF-8", "LC_NUMERIC": "pt_BR.UTF-8"}
    p = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", sys.executable, str(aux.AQUI), "locale"], env=env, capture_output=True, text=True, timeout=300)
    linhas = [x for x in p.stdout.splitlines() if x.startswith("RESULTADO ")]
    assert p.returncode == 0 and linhas, p.stdout[-1500:] + p.stderr[-1500:]
    res = json.loads(linhas[-1][10:])
    assert "erro" not in res, res["erro"]
    assert res["controle_virgula"], "controle: o Qt deveria ter posto vírgula no processo (sem isso o caso não prova nada)"
    assert res["depois"] == "." and res["lc"] == "C" and res["apos_gravar"] == "." and res["dims"] == [4.0, 0.15, 2.8], res
