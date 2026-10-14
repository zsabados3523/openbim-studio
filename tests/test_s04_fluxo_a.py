# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do fluxo A (S04-T11; LOTE_OPUS_9 §1.1, §1.4 regras 1-8, §2, §4 etapa 3; contrato em prototypes/s04/fluxo_a/CONTRATO.md).
GUARDA: pula enquanto `prototypes/s04/fluxo_a/fluxo_a.py` não existir; FALHA com OBIM_S04_T11_OBRIGATORIO=1, OBIM_S04_T11B_OBRIGATORIO=1 ou OBIM_S04_T11C_OBRIGATORIO=1 (todo skip vira falha; só o caso da localidade no Windows segue sendo pulado, não se aplica lá). Casos sem janela rodam no processo;
os gráficos rodam em SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1) e o roteiro R inteiro roda UMA vez.
Suposições do oráculo (o Opus confere): parede = prisma retangular = 12 triângulos; a base é `scripts/gerar_modelo_grande.py` com OBIM_S04_BASE paredes
(padrão 300; oficial 3000); régua do CI virtual = mediana < limite e nenhum valor acima de TETO x limite (M2, M2b, M3), M4 < 20 s, M5 pela régua do lote 11
(maior intervalo < 100 ms, >= 20 quadros por janela de 1 s, <= 3x o parado); OBIM_S04_ESTRITO=1 (máquina do PO) troca por p95 < limite.
Fora do escopo (T12): M1, M6, M7 e a comparação A x B. Sentinelas sem fluxo_a: roteiro, ifcopenshell sozinho e a conta das metas.

T11c (lote 22 item 5): `criar_paredes_lote` de N paredes cria N IfcMaterialLayerSetUsage e N IfcRelAssociatesMaterial (cada relação só da sua parede, +1 relação por tipo), como N `criar_parede`;
 o IFC segue válido (esquema + regras EXPRESS) e rollback, desfazer e refazer do lote seguem intactos (casos "t11c" abaixo; o fluxo B é conferido em test_s04_fluxo_b_paredes.py, sem exceção).

T11b (lote 18; o implementador precisa saber, ver também CONTRATO.md):
 - NOVO retorno de comando: `FluxoA.executar_detalhado(cmd, espera=None) -> (guids, detalhe)`; `detalhe` é um dict NOVO a cada chamada (criados, alterados, apagados,
   geometria, sequencia, t0_ms, t_comando_ms e, só em editar_propriedades, t_painel_ms), nunca o objeto compartilhado. `executar` continua devolvendo só a lista de GlobalIds
   (= o primeiro item) e `ultimo` continua existindo (cópia do último detalhe), mas `executar_roteiro` não pode depender dele: usa o detalhe devolvido.
 - falha DEPOIS do `end_transaction` (em `_lote`/`obimcore.malhas` ou em `Cena.atualizar`): `ifc.undo()` + tirar o registro do histórico, a grade (`_g`) não anda, a trava solta e a exceção sobe;
   falha no meio da transação (antes do commit): `discard_transaction()`. O oráculo força a falha em `fluxo_a.api` e `ifcopenshell.api.run` (o módulo continua com `api = ifcopenshell.api.run`
   e chama as funções por ele), em `obimcore.malhas` (chamado como atributo do módulo na hora) e em `self.cena.atualizar`.
 - desfazer/refazer: o registro só sai da pilha depois de `ifc.undo()/redo()` dar certo; se `Cena.atualizar` (ou a malha) falhar depois, volta o undo/redo e o registro à pilha
   (modelo e cena em sincronia). A malha re-enviada é só a afetada: `geometria` do registro (o que o comando original mandou) mais o que o desfazer/refazer fez APARECER
   (desfazer de apagar, refazer de criar); editar_propriedades nunca manda malha (`atualizar(None, [])`).
 - a tabela do núcleo (`Cena.objetos(seq)["id_step"]`) recebe 0, não o id STEP; `mudar_comprimento` em IFC2X3 levanta ValueError; a profundidade da extrusão depois de `mudar_comprimento`
   é EXATA em mm (== 2800.0, sem o ruído 2799.9999999999995; tolerância de 1e-9 deixaria passar o defeito)."""
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
OBRIGATORIO = "1" in (os.environ.get("OBIM_S04_T11_OBRIGATORIO"), os.environ.get("OBIM_S04_T11B_OBRIGATORIO"), os.environ.get("OBIM_S04_T11C_OBRIGATORIO"))
BASE = os.environ.get("OBIM_S04_BASE", "300")
MUTA = {"criar_tipo", "criar_parede", "criar_paredes_lote", "editar_propriedades", "mudar_comprimento", "mover", "apagar", "desfazer", "refazer"}
GEO = {"criar_parede", "criar_paredes_lote", "mudar_comprimento", "mover"}  # comandos cuja `geometria` é tudo o que mudou
CMDS = MUTA | {"abrir", "selecionar", "orbitar", "camera_mover", "aproximar", "enquadrar", "camera", "animar_orbita", "parar_animacao", "esperar", "gravar"}

def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-T11/T11b/T11c: {msg} (oráculo do fluxo A NÃO FOI EXECUTADO) !!!\n")

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

# ---------- T11c: uma camada de material por parede, também no lote ----------
LOTE = dict(PAREDE, cmd="criar_paredes_lote")

def test_t11c_lote_de_n_paredes_tem_n_usos_e_n_relacoes_de_material(novo):
    f = novo()
    f.executar(TIPO)
    for n in (1, 2, 7, 120):
        f.executar(dict(LOTE, quantidade=n))
    aux.confere_uma_camada_por_parede(f.ifc, 1 + 2 + 7 + 120)
    assert aux.materiais(f.ifc)["IfcMaterialLayerSetUsage"] == 130 and len(f.historico) == 5  # criar_tipo + 4 lotes: cada lote continua 1 transação

def test_t11c_lote_e_n_criar_parede_dao_o_mesmo_modelo_em_classes_e_material(novo):
    a, b = novo(), novo()
    for f in (a, b):
        f.executar(TIPO)
    a.executar(dict(LOTE, quantidade=9))
    for _ in range(9):
        b.executar(PAREDE)
    assert estado(a.ifc)[0] == estado(b.ifc)[0] and aux.materiais(a.ifc) == aux.materiais(b.ifc)  # (os GlobalIds diferem; a contagem por classe e a forma de cada parede, não)
    assert sorted(map(str, estado(a.ifc)[1].values())) == sorted(map(str, estado(b.ifc)[1].values()))
    aux.confere_uma_camada_por_parede(a.ifc, 9)
    aux.confere_uma_camada_por_parede(b.ifc, 9)

def test_t11c_dois_tipos_cada_parede_com_o_uso_do_seu_tipo(novo):
    f = novo()
    f.executar(TIPO)
    f.executar(dict(TIPO, nome="PAR20", camadas_m=[0.02, 0.16, 0.02]))
    f.executar(dict(LOTE, quantidade=4))
    f.executar(dict(LOTE, quantidade=3, tipo="PAR20", espessura=0.20))
    aux.confere_uma_camada_por_parede(f.ifc, 7, tipos=2)
    import ifcopenshell.util.element as E
    assert sorted(E.get_material(w, should_inherit=False).ForLayerSet.LayerSetName for w in f.ifc.by_type("IfcWall")) == ["PAR15"] * 4 + ["PAR20"] * 3

def test_t11c_ifc_do_lote_e_valido_grava_e_reabre_com_um_uso_por_parede(novo, tmp_path):
    import ifcopenshell
    f = novo()
    f.executar(TIPO)
    f.executar(dict(LOTE, quantidade=30))
    f.executar({"cmd": "gravar", "arquivo": "lote.ifc"})
    g = ifcopenshell.open(str(tmp_path / "saida" / "lote.ifc"))
    assert aux.erros_ifc(f.ifc) == [] and aux.erros_ifc(g) == []
    aux.confere_uma_camada_por_parede(g, 30)
    assert not [e for e in g if not e.is_a("IfcRoot") and not e.is_a("IfcRepresentationContext") and not g.get_inverse(e)], "sobra de entidade solta"

def test_t11c_desfazer_e_refazer_do_lote_levam_e_trazem_os_n_usos_e_as_n_relacoes(novo):
    f = novo()
    f.executar(TIPO)
    f.executar(PAREDE)  # uma parede antes do lote: o desfazer do lote não pode mexer no uso dela
    e0, m0 = estado(f.ifc), aux.materiais(f.ifc)
    lote = f.executar(dict(LOTE, quantidade=25))
    e1 = estado(f.ifc)
    aux.confere_uma_camada_por_parede(f.ifc, 26)
    assert sorted(f.executar({"cmd": "desfazer"})) == sorted(lote) and estado(f.ifc) == e0 and aux.materiais(f.ifc) == m0
    aux.confere_uma_camada_por_parede(f.ifc, 1)
    assert sorted(f.executar({"cmd": "refazer"})) == sorted(lote) and estado(f.ifc) == e1
    aux.confere_uma_camada_por_parede(f.ifc, 26)
    f.executar({"cmd": "desfazer"})
    f.executar({"cmd": "desfazer"})  # agora desfaz a parede avulsa: o tipo fica sozinho (0 usos, só a relação do tipo)
    assert aux.materiais(f.ifc)["IfcMaterialLayerSetUsage"] == 0 and aux.materiais(f.ifc)["IfcRelAssociatesMaterial"] == 1
    f.executar({"cmd": "refazer"})
    f.executar({"cmd": "refazer"})
    assert estado(f.ifc) == e1
    aux.confere_uma_camada_por_parede(f.ifc, 26)

def test_t11c_apagar_uma_parede_do_lote_leva_so_o_uso_e_a_relacao_dela_e_o_desfazer_traz_de_volta(novo):
    f = novo()
    f.executar(TIPO)
    lote = f.executar(dict(LOTE, quantidade=6))
    e1 = estado(f.ifc)
    f.executar({"cmd": "apagar", "alvo": lote[2]})
    aux.confere_uma_camada_por_parede(f.ifc, 5)  # o resto do lote mantém o seu uso e a sua relação
    f.executar({"cmd": "desfazer"})
    assert estado(f.ifc) == e1
    aux.confere_uma_camada_por_parede(f.ifc, 6)

def test_t11c_lote_que_falha_no_meio_deixa_zero_usos_novos_e_o_desfazer_seguinte_e_o_do_comando_anterior(novo, fa, monkeypatch):
    import ifcopenshell.api as A
    real = A.run

    def com_falha(prefixos, n):  # falha na n-ésima chamada de qualquer função da API que comece com um dos prefixos (cobre uma implementação com 1 chamada ou 1 por parede)
        cont = {"n": 0}

        def api(nome, *a, **k):
            cont["n"] += nome.startswith(prefixos)
            if nome.startswith(prefixos) and cont["n"] == n:
                raise RuntimeError(f"falha injetada em {nome}")
            return real(nome, *a, **k)
        return api
    for prefixos, n in ((("type.", "material."), 1), (("spatial.",), 1), (("geometry.edit_object_placement",), 4), (("geometry.add_wall_representation",), 5)):
        f = novo()
        f.executar(TIPO)
        f.executar(PAREDE)
        anterior = f.executar(PAREDE)
        e0, m0, ids0, h0 = estado(f.ifc), aux.materiais(f.ifc), ids_modelo(f.ifc), len(f.historico)
        with monkeypatch.context() as m:
            m.setattr(A, "run", com_falha(prefixos, n))
            m.setattr(fa, "api", com_falha(prefixos, n))
            with pytest.raises(RuntimeError, match="falha injetada"):
                f.executar(dict(LOTE, quantidade=8))
        assert estado(f.ifc) == e0 and aux.materiais(f.ifc) == m0 and ids_modelo(f.ifc) == ids0 and len(f.historico) == h0 and not f.trava.locked(), prefixos
        aux.confere_uma_camada_por_parede(f.ifc, 2)
        assert f.executar({"cmd": "desfazer"}) == anterior, f"{prefixos}: o desfazer depois da falha tem de desfazer o comando anterior, não o lote"
        f.executar({"cmd": "refazer"})
        lote = f.executar(dict(LOTE, quantidade=8))  # e o lote refeito depois da falha sai certo (grade: a falha não andou)
        aux.confere_uma_camada_por_parede(f.ifc, 10)
        assert forma(f.ifc.by_guid(lote[0]))[2] == [2 * 5.0, 0.0, 0.0], prefixos

def test_t11c_tipo_sem_conjunto_de_camadas(novo):  # lote Opus 24 A1: tipo sem material, ou com IfcMaterial simples, não tem conjunto de camadas a usar; no main funciona (a parede só não ganha uso), então o lote também tem de funcionar
    import ifcopenshell.api as A
    for nome, simples in (("SEM", False), ("SIMPLES", True)):
        f = novo()
        t = A.run("root.create_entity", f.ifc, ifc_class="IfcWallType", name=nome)  # tipo montado direto no IFC, antes de qualquer comando
        if simples:
            A.run("material.assign_material", f.ifc, products=[t], material=A.run("material.add_material", f.ifc, name=nome))  # IfcMaterial simples, de nome igual ao do tipo
        antes = aux.materiais(f.ifc)
        assert antes["IfcMaterialLayerSet"] == 0 and antes["IfcMaterialLayerSetUsage"] == 0 and antes["IfcMaterial"] == int(simples)
        criados = f.executar(dict(LOTE, tipo=nome, quantidade=6))
        criados += f.executar(dict(PAREDE, tipo=nome))  # criar_parede usa o mesmo caminho
        assert len(set(criados)) == 7 and len(f.ifc.by_type("IfcWall")) == 7, nome
        assert aux.materiais(f.ifc) == antes, f"{nome}: o lote não pode criar conjunto, uso, camada, material ou relação de material novos: {antes} -> {aux.materiais(f.ifc)}"
        assert aux.erros_ifc(f.ifc) == [], nome
        assert all(w.IsTypedBy and w.IsTypedBy[0].RelatingType == t for w in f.ifc.by_type("IfcWall")), f"{nome}: cada parede continua ligada ao tipo"

def test_t11c_custo_do_lote_nao_cresce_com_as_paredes_que_o_tipo_ja_tem(novo):  # sentinela de escala (lote 23 A3): vale com OBIM_S04_T11C_OBRIGATORIO=1 (o `fa` falha em vez de pular)
    # O mesmo lote de 300 paredes, com 0 e com ~2000 paredes do tipo já no modelo: o tempo não pode mais que dobrar.
    # Não prescreve número nem forma de chamada da API (o lote 23 mediu 5,7x num código quadrático e 1,1x na alternativa linear).
    def tempo_do_lote(f):
        t0 = time.perf_counter()
        f.executar(dict(LOTE, quantidade=300))
        return time.perf_counter() - t0

    vazio = []
    for _ in range(3):  # 3 modelos novos, o melhor tempo (o mínimo tira o ruído da máquina)
        f = novo()
        f.executar(TIPO)
        vazio.append(tempo_do_lote(f))
    f = novo()
    f.executar(TIPO)
    for _ in range(8):  # 8 x 250 = 2000 paredes do tipo, em lotes menores para a preparação não pesar
        f.executar(dict(LOTE, quantidade=250))
    assert len(f.ifc.by_type("IfcWall")) == 2000
    cheio = [tempo_do_lote(f) for _ in range(2)]  # o modelo vai de 2000 a 2600 paredes: o mínimo é o lote que ainda vê ~2000
    razao = min(cheio) / min(vazio)
    assert razao < 2.0, f"lote de 300 paredes: {min(vazio):.2f} s com 0 paredes do tipo, {min(cheio):.2f} s com ~2000 ({razao:.1f}x; o limite é 2x): o custo por parede cresce com as paredes que o tipo já tem"

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
    nome or pular("SEM LOCALIDADE pt_BR NESTA MÁQUINA: o caso 'gravar com vírgula'")
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

# ---------- T11b: casos sem janela ----------
def test_conferencia_de_validade_do_ifc_do_oraculo_pega_ifc_invalido(novo, tmp_path):
    import ifcopenshell
    import ifcopenshell.validate as V
    f = novo()
    f.executar(TIPO)
    f.executar(PAREDE)
    f.executar({"cmd": "gravar", "arquivo": "ok.ifc"})
    arq = str(tmp_path / "saida" / "ok.ifc")
    assert aux.erros_ifc(ifcopenshell.open(arq)) == []
    ruim = ifcopenshell.open(arq)  # descartável: espessura de camada negativa (regra EXPRESS) e GlobalId com tamanho errado (esquema)
    ruim.by_type("IfcMaterialLayer")[0].LayerThickness = -0.5
    ruim.by_type("IfcWall")[0].GlobalId = "abc"
    assert len(aux.erros_ifc(ruim)) >= 2, "o oráculo tem de ver os dois defeitos (esquema e regra EXPRESS)"
    antigo = V.json_logger()  # o filtro de antes (nível em maiúsculas, sem regras EXPRESS) não via nenhum: é o que o lote 18 achou
    V.validate(ruim, antigo)
    assert not [x for x in antigo.statements if x.get("level") == "ERROR"] and not [x for x in antigo.statements if x.get("level") == "error" and "SELF" in x.get("message", "")]

def test_falha_no_meio_de_um_comando_deixa_o_modelo_igual_e_o_historico_intacto(novo, fa, monkeypatch):
    import ifcopenshell.api as A
    real = A.run

    def com_falha(onde, n=1):
        cont = {"n": 0}

        def api(nome, *a, **k):
            cont["n"] += nome == onde
            if nome == onde and cont["n"] == n:
                raise RuntimeError(f"falha injetada em {nome}")
            return real(nome, *a, **k)
        return api
    for nome, onde, n in (("mudar_comprimento", "geometry.add_axis_representation", 1), ("criar_paredes_lote", "geometry.edit_object_placement", 3), ("criar_parede", "spatial.assign_container", 1),
                          ("criar_tipo", "material.assign_material", 1), ("editar_propriedades", "pset.edit_pset", 1), ("mover", "geometry.edit_object_placement", 1), ("apagar", "root.remove_product", 1)):
        f = novo()
        f.executar(TIPO)
        a = f.executar(PAREDE)[0]
        e_ant = estado(f.ifc)
        outra = f.executar(PAREDE)  # a transação anterior: um ifc.undo() no lugar de discard_transaction() desfaria ESTA
        cmd = {"mudar_comprimento": {"cmd": nome, "alvo": a, "comprimento": 6.0}, "criar_paredes_lote": dict(PAREDE, cmd=nome, quantidade=5), "criar_parede": PAREDE, "criar_tipo": dict(TIPO, nome="OUTRO"),
               "editar_propriedades": {"cmd": nome, "alvo": a, "nome": "Meio", "propriedades": {FIRE: "R90"}}, "mover": {"cmd": nome, "alvo": a, "dx": 1.0, "dy": 0.0, "dz": 0.0}, "apagar": {"cmd": nome, "alvo": a}}[nome]
        e0, ids0, h0 = estado(f.ifc), ids_modelo(f.ifc), len(f.historico)
        with monkeypatch.context() as m:
            m.setattr(A, "run", com_falha(onde, n))
            m.setattr(fa, "api", com_falha(onde, n))
            with pytest.raises(RuntimeError, match="falha injetada"):
                f.executar(cmd)
        assert estado(f.ifc) == e0 and ids_modelo(f.ifc) == ids0 and len(f.historico) == h0 and not f.trava.locked(), nome
        assert f.executar({"cmd": "desfazer"}) == outra and estado(f.ifc) == e_ant, f"{nome}: o desfazer depois da falha tem de desfazer o comando anterior"
        assert f.executar({"cmd": "refazer"}) == outra and estado(f.ifc) == e0
        if nome in ("criar_parede", "criar_paredes_lote"):  # a grade não anda por comando que falhou: a próxima parede vai para o lugar 2
            w = f.ifc.by_guid(f.executar(PAREDE)[0])
            assert forma(w)[2] == [2 * 5.0, 0.0, 0.0], nome

def test_desfazer_e_refazer_que_falham_no_ifc_nao_perdem_o_registro(novo, monkeypatch):
    f = novo()
    f.executar(TIPO)
    e0, a = estado(f.ifc), f.executar(PAREDE)
    e1, h = estado(f.ifc), len(f.historico)

    def boom(*args, **kw):
        raise RuntimeError("falha injetada no ifc")
    with monkeypatch.context() as m:
        m.setattr(f.ifc, "undo", boom)
        with pytest.raises(RuntimeError, match="falha injetada"):
            f.executar({"cmd": "desfazer"})
    assert len(f.historico) == h and estado(f.ifc) == e1 and not f.trava.locked(), "o registro só sai da pilha depois de o undo() dar certo"
    assert f.executar({"cmd": "refazer"}) == [], "nada foi desfeito: a pilha de refazer está vazia"
    assert f.executar({"cmd": "desfazer"}) == a and estado(f.ifc) == e0
    with monkeypatch.context() as m:
        m.setattr(f.ifc, "redo", boom)
        with pytest.raises(RuntimeError, match="falha injetada"):
            f.executar({"cmd": "refazer"})
    assert estado(f.ifc) == e0 and not f.trava.locked() and len(f.historico) == h - 1, "o registro só passa para a pilha de refazer depois de o redo() dar certo"
    assert f.executar({"cmd": "refazer"}) == a and estado(f.ifc) == e1 and len(f.historico) == h

def test_desfazer_e_refazer_devolvem_no_detalhe_so_a_malha_afetada(novo):
    f = novo()
    f.executar(TIPO)
    a, b = f.executar(PAREDE)[0], f.executar(PAREDE)[0]
    vazio = dict(g=[], c=[], a=[], al=[])  # g = geometria (malha re-enviada), c = criados, a = apagados, al = alterados (do registro)
    casos = [("criar_tipo", dict(TIPO, nome="OUTRO"), None), ("criar_parede", PAREDE, None), ("criar_paredes_lote", dict(PAREDE, cmd="criar_paredes_lote", quantidade=3), None),
             ("editar_propriedades", {"cmd": "editar_propriedades", "alvo": a, "nome": "X", "propriedades": {FIRE: "R30"}}, (dict(vazio, al=[a]),) * 2),  # propriedade não é malha: nada vai à cena
             ("mudar_comprimento", {"cmd": "mudar_comprimento", "alvo": a, "comprimento": 6.0}, (dict(vazio, g=[a], al=[a]),) * 2),
             ("mover", {"cmd": "mover", "alvo": b, "dx": 1.0, "dy": 0.0, "dz": 0.0}, (dict(vazio, g=[b], al=[b]),) * 2),
             ("apagar", {"cmd": "apagar", "alvo": b}, (dict(vazio, g=[b], c=[b]), dict(vazio, a=[b])))]  # desfazer de apagar: a parede APARECE, então vai à cena
    for nome, cmd, esperado in casos:
        guids, d = f.executar_detalhado(cmd)
        assert bool(d["geometria"]) == (nome in GEO), nome
        if esperado is None:  # criação: desfazer faz sumir (nada vai à cena); refazer faz aparecer (a malha vai, se é parede)
            esperado = dict(vazio, a=guids), dict(vazio, c=guids, g=guids if nome != "criar_tipo" else [])
        for qual, esp in zip(("desfazer", "refazer"), esperado):
            r, dd = f.executar_detalhado({"cmd": qual})
            assert sorted(r) == sorted(guids), (nome, qual)
            assert {k: sorted(dd[n]) for k, n in (("g", "geometria"), ("c", "criados"), ("a", "apagados"), ("al", "alterados"))} == {k: sorted(v) for k, v in esp.items()}, (nome, qual, dd)

def test_mudar_comprimento_em_ifc2x3_levanta_valueerror_e_nao_mexe_no_modelo(novo, tmp_path, monkeypatch):
    import ifcopenshell.api as A
    import ifcopenshell.api.owner.settings as OS
    f = A.run("project.create_file", version="IFC2X3")
    org = f.create_entity("IfcOrganization", Name="o")
    usuario = f.create_entity("IfcPersonAndOrganization", ThePerson=f.create_entity("IfcPerson", Id="x", FamilyName="t"), TheOrganization=org)
    app = f.create_entity("IfcApplication", ApplicationDeveloper=org, Version="1", ApplicationFullName="t", ApplicationIdentifier="t")
    monkeypatch.setattr(OS, "get_user", lambda ifc: usuario)  # a API do IFC2X3 exige histórico de propriedade
    monkeypatch.setattr(OS, "get_application", lambda ifc: app)
    api = A.run
    api("root.create_entity", f, ifc_class="IfcProject", name="P")
    api("unit.assign_unit", f)
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=api("context.add_context", f, context_type="Model"))
    pav, w = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pav"), api("root.create_entity", f, ifc_class="IfcWall", name="W")
    api("geometry.assign_representation", f, product=w, representation=api("geometry.add_wall_representation", f, context=corpo, length=4.0, height=2.8, thickness=0.15))
    api("geometry.edit_object_placement", f, product=w, matrix=np.eye(4))
    api("spatial.assign_container", f, products=[w], relating_structure=pav)
    f.write(str(tmp_path / "v23.ifc"))
    x = novo(str(tmp_path / "v23.ifc"))
    assert x.ifc.schema == "IFC2X3"
    e0, ids0 = estado(x.ifc), ids_modelo(x.ifc)
    with pytest.raises(ValueError):
        x.executar({"cmd": "mudar_comprimento", "alvo": w.GlobalId, "comprimento": 5.0})
    assert estado(x.ifc) == e0 and ids_modelo(x.ifc) == ids0 and not x.historico and not x.trava.locked()

def test_base_em_mm_grade_no_lugar_e_profundidade_sem_ruido_depois_de_mudar_o_comprimento(novo, tmp_path):
    import gerar_modelo_grande
    import ifcopenshell.util.unit as U
    gerar_modelo_grande.gerar(str(tmp_path / "mm.ifc"), paredes=4)
    f = novo(str(tmp_path / "mm.ifc"))
    assert U.calculate_unit_scale(f.ifc) == 0.001, "a base do oráculo tem de ser em milímetros"
    f.executar(TIPO)
    gs = [f.executar(PAREDE)[0] for _ in range(52)]
    for g in (0, 1, 49, 50, 51):  # a grade é em metros, qualquer que seja a unidade do projeto
        assert forma(f.ifc.by_guid(gs[g])) == (12, [4.0, 0.15, 2.8], [g % 50 * 5.0, g // 50 * 4.0, 0.0]), g

    def solido(w):
        return next(r for r in w.Representation.Representations if r.RepresentationIdentifier == "Body").Items[0]
    alvos = [(gs[0], 5.0), (gs[0], 3.3), (gs[0], 7.25), (gs[0], 4.0), (f.ifc.by_type("IfcWall")[0].GlobalId, 5.5)]  # a última: parede da base, não criada pelo fluxo
    for g, comp in alvos:
        f.executar({"cmd": "mudar_comprimento", "alvo": g, "comprimento": comp})
        w = f.ifc.by_guid(g)
        sol = solido(w)
        assert sol.Depth == 2800.0, f"profundidade {sol.Depth!r} (mm) depois de mudar para {comp} m: tem de ser 2800.0 exato (sem o ruído de ponto flutuante de 2799.9999999999995)"
        pts = {v for p in sol.SweptArea.OuterCurve.Points.CoordList for v in p}
        assert all(min(abs(v - alvo) for alvo in (0.0, 150.0, comp * 1000.0)) <= 1e-9 for v in pts), (comp, sorted(pts))
        assert forma(w)[1] == [comp, 0.15, 2.8]

def test_executar_detalhado_devolve_o_detalhe_do_proprio_comando_mesmo_com_duas_threads(novo):
    f = novo()
    f.executar(TIPO)
    alvo = f.executar(PAREDE)[0]
    guids, d = f.executar_detalhado(PAREDE)
    assert isinstance(guids, list) and d["criados"] == guids and d["geometria"] == guids and not d["alterados"] and not d["apagados"] and "t_painel_ms" not in d and d["t0_ms"] <= d["t_comando_ms"]
    assert d == f.ultimo, "numa thread só, `ultimo` é uma cópia do detalhe devolvido"
    erros, todos = [], []

    def criador():
        for _ in range(50):
            r, d = f.executar_detalhado(PAREDE)
            todos.append(d)
            (d["criados"] == r and len(r) == 1 and d["geometria"] == r and not d["alterados"] and not d["apagados"] and "t_painel_ms" not in d) or erros.append(("criar", r, d))

    def editor():
        for i in range(50):
            r, d = f.executar_detalhado({"cmd": "editar_propriedades", "alvo": alvo, "nome": f"N{i}", "propriedades": {FIRE: "R30"}})
            todos.append(d)
            (r == [alvo] and d["alterados"] == [alvo] and not d["criados"] and not d["apagados"] and not d["geometria"] and d["t_comando_ms"] <= d["t_painel_ms"]) or erros.append(("editar", r, d))
    antes = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)  # troca de thread o tempo todo: se o detalhe fosse um estado compartilhado, a corrida apareceria
    try:
        ts = [threading.Thread(target=fn) for fn in (criador, editor)]
        [t.start() for t in ts]
        [t.join(120) for t in ts]
    finally:
        sys.setswitchinterval(antes)
    assert not erros, erros[:3]
    assert len({id(d) for d in todos}) == len(todos) == 100, "cada chamada devolve um dict novo"

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
    if sys.platform == "win32":
        pytest.skip("\n!!! Windows: sem pt_BR.UTF-8 no xvfb; o caso da localidade com a aplicação NÃO FOI EXECUTADO (o do gravar roda em test_gravar_corrige...) !!!\n")
    if sem_locale("pt_BR.UTF-8"):
        pular("SEM pt_BR.UTF-8: o caso da localidade com a aplicação")
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "LC_ALL")} | {"QT_QPA_PLATFORM": "xcb", "LIBGL_ALWAYS_SOFTWARE": "1", "LANG": "pt_BR.UTF-8", "LC_NUMERIC": "pt_BR.UTF-8"}
    p = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", sys.executable, str(aux.AQUI), "locale"], env=env, capture_output=True, text=True, timeout=300)
    linhas = [x for x in p.stdout.splitlines() if x.startswith("RESULTADO ")]
    assert p.returncode == 0 and linhas, p.stdout[-1500:] + p.stderr[-1500:]
    res = json.loads(linhas[-1][10:])
    assert "erro" not in res, res["erro"]
    assert res["controle_virgula"], "controle: o Qt deveria ter posto vírgula no processo (sem isso o caso não prova nada)"
    assert res["depois"] == "." and res["lc"] == "C" and res["apos_gravar"] == "." and res["dims"] == [4.0, 0.15, 2.8], res

# ---------- T11b: casos gráficos ----------
def test_roteiro_r_tempos_batem_com_o_relogio_do_nucleo_visto_por_fora(rot):  # lote 18 achado 2: o oráculo não confia só nos tempos que o fluxo anota
    med, ch = rot["med"], rot["chamadas"]
    vistos = {float(t): int(s) for t, s in rot["quadros_vistos"]}
    assert len(vistos) > 100, "o espião de Cena.relogio() quase não viu quadros"
    for (i, cmd, x), c in zip(reps(med), ch):
        tc, tq = x["t_comando_ms"], x["t_quadro_ms"]
        assert c["ini"] <= x["t0_ms"] <= tc <= c["fim"], f"{i} {cmd}: t0 {x['t0_ms']} e comando {tc} têm de cair dentro da chamada [{c['ini']}, {c['fim']}] (obimcore.agora tomado por fora)"
        if "t_painel_ms" in x:
            assert tc <= x["t_painel_ms"] <= c["fim"], (i, cmd)
        if x["sequencia"] is not None and (cmd == "abrir" or x["geometria"] or x["apagados"]):  # a cena mudou: o quadro com a mudança tem de existir em Cena.relogio()
            assert tq >= tc
            assert [t for t, s in vistos.items() if s >= x["sequencia"] and x["t0_ms"] <= t <= tq], f"{i} {cmd}: nenhum quadro com sequência >= {x['sequencia']} até {tq}"
            assert tq == tc or vistos.get(tq, -1) >= x["sequencia"], f"{i} {cmd}: t_quadro_ms {tq} não é uma entrada real de relogio() com sequência >= {x['sequencia']}"
        else:
            assert tq == tc, f"{i} {cmd}: sem quadro a esperar, t_quadro_ms = t_comando_ms"

def tem_nome(texto, nome):  # a linha do nome inteira (o nome "R-1" não vale como "R-12")
    return any(linha.endswith(nome) for linha in texto.splitlines())

def test_roteiro_r_m3_o_rotulo_mostra_o_texto_novo_e_foi_pintado_antes_de_t_painel(rot):
    assert rot["rotulo_achado"], "a janela principal tem de ter o painel como QLabel"
    eds = [(x, c) for (i, cmd, x), c in zip(reps(rot["med"]), rot["chamadas"]) if cmd == "editar_propriedades"]
    assert len(eds) == 200
    for x, c in eds:
        nome, alvo = c["args"]["nome"], x["guids"][0]
        assert tem_nome(c["rotulo"], nome) and alvo in c["rotulo"] and "R60" in c["rotulo"] and "IfcWall" in c["rotulo"], (nome, c["rotulo"])
        novos = [t for t, tx in c["pinturas"] if tem_nome(tx, nome) and "R60" in tx]
        assert novos, f"{nome}: nenhum evento de pintura do QLabel mostrou o texto novo"
        assert c["ini"] <= novos[0] <= x["t_painel_ms"], f"{nome}: o rótulo só foi pintado em {novos[0]}, depois de t_painel_ms {x['t_painel_ms']}"

def test_roteiro_r_a_camera_girou_durante_o_passo_5b(rot):
    az = {i: c["azimute"] for (i, cmd, x), c in zip(reps(rot["med"]), rot["chamadas"]) if i in ("5b", "5c")}
    giro = abs((az["5c"] - az["5b"] + 180) % 360 - 180)
    assert giro > 0.5, f"a câmera deveria girar a 30 graus/s durante o lote (azimute {az['5b']} -> {az['5c']})"

@pytest.fixture(scope="module")
def fino(tela):
    return caso("fino", limite=600)

def secao(fino, nome):
    r = fino[nome]
    assert not (isinstance(r, dict) and "erro" in r), r["erro"]
    return r

def test_tabela_do_nucleo_recebe_id_step_zero(fino):
    t = [x for x in secao(fino, "tabela") if "ids" in x]  # (o núcleo tira de um lote antigo o objeto que um lote novo substituiu: a tabela pode ter só parte do que foi enviado)
    assert {x["m"] for x in t} == {"adicionar_lote", "atualizar"} and sum(len(x["ids"]) for x in t) >= 12 and sum(1 for x in t if x["ids"]) >= 3, t
    for x in t:
        assert not any(x["ids"]) and set(x["guids"]) <= set(x["esperado"]), f"o id STEP não pode ir à tabela do núcleo: {x}"

def test_desfazer_e_refazer_de_propriedade_nao_reenviam_a_cena(fino):
    p = secao(fino, "propriedade")
    for k in ("editar", "des_editar", "ref_editar"):
        assert p[k]["dfatias"] == 0 and p[k]["tri"][0] == p[k]["tri"][1] == p[k]["tri"][2], (k, p[k])
        assert len(p[k]["log"]) == 1 and not p[k]["log"][0]["guids"] and not p[k]["log"][0]["remover"], f"{k}: propriedade não é malha, a cena não recebe lote ({p[k]['log']})"
    for k in ("des_mudar", "ref_mudar"):  # só a parede que mudou; o núcleo ainda reenvia tudo (T12), mas não mais do que no comando original
        assert [l["guids"] for l in p[k]["log"]] == [[p["alvo_mudar"]]] and not p[k]["log"][0]["remover"], (k, p[k]["log"])
        assert p[k]["dfatias"] <= p["mudar"]["dfatias"], (k, p[k]["dfatias"], p["mudar"]["dfatias"])

def test_falha_depois_do_commit_volta_a_transacao_e_modelo_e_cena_ficam_em_sincronia(fino):
    r = secao(fino, "falhas")
    assert len(r) == 10, sorted(r)
    for caso_, v in r.items():
        assert all(v.values()), (caso_, {k: x for k, x in v.items() if not x})

def test_desfazer_e_refazer_com_falha_na_cena_voltam_o_modelo_e_o_registro(fino):  # mesmo princípio: modelo e cena em sincronia (ver o topo do arquivo)
    r = secao(fino, "falhas_desfazer")
    assert sorted(r) == ["atualizar", "malhas"]
    for onde, v in r.items():
        assert v["voltou"], onde
        for qual in ("desfazer", "refazer"):
            assert all(v[qual].values()), (onde, qual, {k: x for k, x in v[qual].items() if not x})
