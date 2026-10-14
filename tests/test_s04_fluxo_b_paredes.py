# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do fluxo B, parte 1: paredes em C++ (S04-T13; LOTE_OPUS_9 §1.1, §1.2, §2.2 "saída igual", §4 etapa 3; contrato em prototypes/s04/fluxo_b/CONTRATO.md; apoio em s04_fluxo_b_aux.py).
GUARDA: pula enquanto o módulo nanobind `fluxo_b_paredes` não puder ser importado (PYTHONPATH ou OBIM_S04_FLUXO_B_DIR); FALHA com OBIM_S04_T13_OBRIGATORIO=1. Rode sob xvfb-run.
A "saída igual" é conferida PASSO A PASSO: o mesmo roteiro curto vai ao fluxo A (Python, FluxoA sem janela) e à biblioteca C++, ambos gravam e reabrem o IFC depois de cada passo, e a
assinatura (classes, nomes, camadas, posição, representações, psets, triângulos/caixa/volume por create_shape, relações, desfazer/refazer) tem de ser igual a 1e-6 m. GlobalIds diferem.
Suposições do oráculo (o Opus confere): (1) classes de geometria de apoio (ponto, direção, eixo, lista de pontos, curva, perfil) NÃO são contadas, mas qualquer entidade sem referência
(órfã) reprova; as demais classes, inclusive relações, batem em número com A (1 relação de tipo e 1 de pavimento, compartilhadas), EXCETO uso de camadas e relação de material: o
fluxo A compartilha 1 de cada entre as paredes de um lote (desvio da T11, achado desta tarefa); B tem 1 uso por parede e 1 relação por parede e por tipo, conferido sozinho;
(2) o gancho `definir_falha(k)` conta TODA mutação do modelo (criar instância, alterar atributo, remover instância) feita pelo comando; (3) tipo e parede são achados pelo nome e pela posição.
Sentinelas sem o módulo: contrato, `validate` com regras EXPRESS, e o roteiro curto no próprio fluxo A (prova que o oráculo é satisfazível)."""
import functools
import gc
import importlib.util
import json
import locale
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element as E
import ifcopenshell.util.placement as P
import pytest
import s04_fluxo_b_aux as aux
from s04_fluxo_b_aux import CAMADAS, FIRE, PAR, FluxoAd, FluxoBd, alfabeto_ok, assinatura, igual, roteiro, validar

OBRIGATORIO = os.environ.get("OBIM_S04_T13_OBRIGATORIO") == "1"
if os.environ.get("OBIM_S04_FLUXO_B_DIR"):
    sys.path.insert(0, os.environ["OBIM_S04_FLUXO_B_DIR"])
TEM_MODULO = importlib.util.find_spec("fluxo_b_paredes") is not None
TIPO = dict(nome="PAR15", camadas_m=CAMADAS)

def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! aguarda S04-T13: {msg} (oráculo do fluxo B NÃO FOI EXECUTADO) !!!\n")

@pytest.fixture(scope="module")
def mod():
    if not TEM_MODULO:
        pular("módulo fluxo_b_paredes ausente (build.sh de prototypes/s04/fluxo_b/ e PYTHONPATH)")
    import ifcopenshell  # noqa: F401  (antes do módulo: registra os esquemas)
    import fluxo_b_paredes
    return fluxo_b_paredes

@pytest.fixture(scope="module")
def rodada(mod, tmp_path_factory):  # o roteiro inteiro, uma vez, nos dois fluxos
    pasta = tmp_path_factory.mktemp("fluxo_b")
    a, b = FluxoAd(pasta / "a"), FluxoBd(pasta / "b", mod)
    out, marcos = aux.percorrer(a, b, roteiro())
    return out, marcos

def novo(mod, n=3, **kw):  # modelo com o tipo PAR15 e n paredes
    b = mod.Paredes()
    b.criar_tipo(**TIPO)
    return b, [b.criar_parede(**PAR, **kw)[0] for _ in range(n)]

def estado(b, pasta, nome="e.ifc"):  # tudo o que um desfazer/rollback tem de devolver
    b.gravar(str(pasta / nome))
    return assinatura(pasta / nome), b.contar(None), b.pode_desfazer(), b.pode_refazer()

def esperado_curto(sig):  # o que o roteiro curto TEM de produzir, escrito sem olhar para A nem para B
    ps, d = sig["paredes"], []
    d += [f"{len(ps)} paredes (esperadas 20)"] * (len(ps) != 20)
    d += igual(sig["tipos"]["PAR15"]["camadas"], [(f"PAR15 camada {i}", t) for i, t in enumerate(CAMADAS, 1)], "camadas do tipo")
    for i in range(20):
        c, L = (i * 5.0, 0.0, 0.0), 5.0 if 5 <= i <= 9 else 4.0
        fogo = "R120" if i == 0 else "R60" if i < 5 else None
        e = dict(nome="Parede ção ✓-3" if i == 3 else f"Parede R-{i}" if i < 5 else "Parede", tipo="PAR15", pavimento="Pavimento 1", absoluta=True, altura=2.8, eixo=[[0.0, 0.0], [L, 0.0]],
                 psets={"Pset_WallCommon": {"FireRating": ("IfcPropertySingleValue", "IfcLabel", fogo)}} if fogo else {},
                 uso=["IfcMaterialLayerSetUsage", "PAR15", "AXIS2", "POSITIVE", 0.0, [(f"PAR15 camada {k}", t) for k, t in enumerate(CAMADAS, 1)]],
                 reps=[("Axis", "Curve2D", "Axis", 1), ("Body", "SweptSolid", "Body", ["IfcExtrudedAreaSolid"])],
                 forma=(12, [c[0], 0.0, 0.0], [c[0] + L, 0.15, 2.8], L * 0.15 * 2.8))
        d += igual(e, {k: ps[c][k] for k in e}, f"parede {i}") if c in ps else [f"parede {i} não está em {c}"]
    return d

def test_contrato_existe_e_cabe_em_80_linhas():
    linhas = aux.CONTRATO.read_text(encoding="utf-8").splitlines()
    assert 20 < len(linhas) <= 80 and all(x in "\n".join(linhas) for x in ("fluxo_b_paredes", "definir_falha", "desfazer", "OBIM_S04_T13_OBRIGATORIO"))

def test_validate_com_regras_express_reporta_erro_de_esquema_e_de_regra(tmp_path):  # sem isto "validação limpa" não prova nada (o módulo lark não está no ambiente)
    import ifcopenshell
    f = ifcopenshell.file(schema="IFC4")
    w = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new())
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(), RelatedElements=(w,))  # RelatingStructure obrigatório ausente
    f.create_entity("IfcMaterialLayer", Material=f.create_entity("IfcMaterial", Name="x"), LayerThickness=-1.0)  # regra WHERE: espessura >= 0
    f.write(str(tmp_path / "ruim.ifc"))
    erros = "\n".join(validar(tmp_path / "ruim.ifc"))
    assert "Attribute not optional" in erros and "(SELF >= 0.0)" in erros, erros

def test_sentinela_o_proprio_fluxo_a_cumpre_o_esperado_do_roteiro_curto(tmp_path):
    a = FluxoAd(tmp_path)
    for nome, kw in roteiro():
        if nome == "#curto":
            break
        a.rodar(nome, **kw)
    p = a.gravar()
    sig = assinatura(p)
    assert esperado_curto(sig) == [] and not sig["orfas"] and not validar(p) and not aux.guids_ruins(p) and sig["esquema"] == "IFC4"

def test_roteiro_curto_saida_igual_passo_a_passo(rodada):
    out, _ = rodada
    ate = next(i for i, (r, _) in enumerate(out) if r == "curto")
    ruins = [(r, d) for r, d in out[:ate + 1] if d]
    assert not ruins, f"{len(ruins)} passos diferentes de A; o primeiro: {ruins[0]}"
    assert len(out) > 40

def test_continuacao_desfazer_refazer_grade_e_lote_saida_igual(rodada):
    out, _ = rodada
    ate = next(i for i, (r, _) in enumerate(out) if r == "curto")
    ruins = [(r, d) for r, d in out[ate + 1:] if d]
    assert not ruins and len(out) > ate + 20, f"{len(ruins)} passos diferentes de A; o primeiro: {ruins[0] if ruins else None}"

def test_roteiro_curto_confere_com_os_valores_esperados(rodada):
    assert esperado_curto(rodada[1]["curto"]) == []

def test_desfazer_ate_o_fim_devolve_o_modelo_do_inicio(rodada):
    m = rodada[1]
    assert igual(m["desfazer_tudo"], m["inicio"], "ifc") == [] and not m["inicio"]["paredes"] and not m["desfazer_tudo"]["tipos"]

def test_ifc_gravado_e_ifc4_reabre_valida_e_tem_cabecalho(mod, tmp_path):
    import ifcopenshell
    b, _ = novo(mod)
    b.gravar(str(tmp_path / "x" / "y" / "p.ifc"))  # cria a pasta que faltar
    txt = (tmp_path / "x" / "y" / "p.ifc").read_text(encoding="utf-8")
    assert txt.startswith("ISO-10303-21;") and "FILE_SCHEMA(('IFC4'))" in txt and txt.rstrip().endswith("END-ISO-10303-21;")
    f = ifcopenshell.open(str(tmp_path / "x" / "y" / "p.ifc"))
    assert f.schema == "IFC4" and len(f.by_type("IfcWall")) == 3 and not validar(tmp_path / "x" / "y" / "p.ifc")

def test_gravar_nao_mexe_nas_pilhas_e_gravar_duas_vezes_da_o_mesmo(mod, tmp_path):
    b, ws = novo(mod)
    b.desfazer()
    e1 = estado(b, tmp_path, "1.ifc")
    assert estado(b, tmp_path, "2.ifc") == e1 and (e1[2], e1[3]) == (3, 1)

def test_globalids_sao_validos_unicos_novos_e_estaveis_no_refazer(mod, tmp_path):
    import ifcopenshell
    b, ws = novo(mod, 5)
    ws += b.criar_paredes_lote(**PAR, quantidade=30)
    b.gravar(str(tmp_path / "b.ifc"))
    f = ifcopenshell.open(str(tmp_path / "b.ifc"))
    assert not aux.guids_ruins(tmp_path / "b.ifc") and set(ws) <= set(aux.guids(f)) and len(set(ws)) == 35 and all(alfabeto_ok(g) for g in ws)
    b2, ws2 = novo(mod, 5)
    b2.gravar(str(tmp_path / "b2.ifc"))
    # dois B e um A não podem repetir nenhum GlobalId (o esqueleto também tem)
    a = FluxoAd(tmp_path / "a")
    a.rodar("criar_tipo", **TIPO)
    a.rodar("criar_parede", **PAR)
    pa = a.gravar()
    todos = [set(aux.guids(ifcopenshell.open(str(p)))) for p in (tmp_path / "b.ifc", tmp_path / "b2.ifc", pa)]
    assert not (todos[0] & todos[1]) and not (todos[0] & todos[2]) and not (todos[1] & todos[2])
    g1 = b.criar_parede(**PAR)[0]
    b.desfazer()
    assert b.refazer() == [g1]  # refazer devolve a MESMA parede
    b.desfazer()
    g2 = b.criar_parede(**PAR)[0]
    assert g2 != g1 and alfabeto_ok(g2)  # parede nova, GlobalId novo: nunca reaproveitado

def casos_invalidos(b, w, t):
    z = "0" * 22
    nan, inf = float("nan"), float("inf")
    return [lambda: b.criar_tipo("PAR15", [0.1]), lambda: b.criar_tipo("X", []), lambda: b.criar_tipo("X", [0.1, 0.0]), lambda: b.criar_tipo("X", [0.1, -0.02]), lambda: b.criar_tipo("X", [nan]),
            lambda: b.criar_tipo("X", [inf]), lambda: b.criar_tipo("", [0.1]), lambda: b.criar_parede(**dict(PAR, tipo="NAO")), lambda: b.criar_parede(**dict(PAR, comprimento=0.0)),
            lambda: b.criar_parede(**dict(PAR, altura=-2.8)), lambda: b.criar_parede(**dict(PAR, espessura=nan)), lambda: b.criar_parede(**dict(PAR, comprimento=inf)),
            lambda: b.criar_paredes_lote(**PAR, quantidade=0), lambda: b.criar_paredes_lote(**PAR, quantidade=-3), lambda: b.editar_propriedades(z, nome="x"),
            lambda: b.editar_propriedades(t, nome="x"), lambda: b.editar_propriedades(w, propriedades={"semponto": "v"}), lambda: b.editar_propriedades(w, propriedades={".Prop": "v"}),
            lambda: b.editar_propriedades(w, propriedades={"Pset.": "v"}), lambda: b.mudar_comprimento(z, 5.0), lambda: b.mudar_comprimento(t, 5.0), lambda: b.mudar_comprimento(w, 0.0),
            lambda: b.mudar_comprimento(w, -1.0), lambda: b.mudar_comprimento(w, nan)]

def test_entrada_invalida_levanta_valueerror_e_nao_muda_nada(mod, tmp_path):
    b = mod.Paredes()
    tipo = b.criar_tipo(**TIPO)[0]
    ws = [b.criar_parede(**PAR)[0] for _ in range(3)]
    b.editar_propriedades(ws[0], nome="N", propriedades={FIRE: "R30"})
    b.desfazer()  # pilha de refazer com 1 item
    antes = estado(b, tmp_path)
    for i, caso in enumerate(casos_invalidos(b, ws[0], tipo)):
        with pytest.raises(ValueError, match=r"\S"):
            caso()
        assert estado(b, tmp_path) == antes, f"caso inválido {i} mudou o modelo ou as pilhas"

def test_falha_no_meio_do_comando_desfaz_tudo_e_preserva_as_pilhas(mod, tmp_path):
    cmds = {"criar_tipo": (lambda b, ws: b.criar_tipo("Outro", [0.1, 0.05]), 3), "criar_parede": (lambda b, ws: b.criar_parede(**PAR), 3),
            "criar_paredes_lote": (lambda b, ws: b.criar_paredes_lote(**PAR, quantidade=5), 3),
            "editar_novo_pset": (lambda b, ws: b.editar_propriedades(ws[0], nome="Z", propriedades={FIRE: "R90", "Pset_Teste.Chave": "v"}), 3),
            "editar_pset_existente": (lambda b, ws: b.editar_propriedades(ws[1], propriedades={FIRE: "R30"}), 1), "editar_so_nome": (lambda b, ws: b.editar_propriedades(ws[0], nome="só o nome"), 1),
            "mudar_comprimento": (lambda b, ws: b.mudar_comprimento(ws[0], 7.5), 2)}  # (comando, menor número de mutações que ele faz; o gancho k <= isso TEM de disparar)
    for nome, (cmd, minimo) in cmds.items():
        for k in (1, 2, 3, 5, 9, 17, 40):
            b, ws = novo(mod)
            b.editar_propriedades(ws[1], propriedades={FIRE: "R60"})
            b.criar_parede(**PAR)
            b.desfazer()  # pilha de refazer com 1 item: a falha não pode limpá-la
            antes = estado(b, tmp_path, "antes.ifc")
            b.definir_falha(k)
            try:
                cmd(b, ws)
            except RuntimeError as e:
                assert "falha" in str(e).lower()
                assert estado(b, tmp_path, "depois.ifc") == antes, f"{nome} com falha na mutação {k} deixou estado parcial"
                assert len(b.refazer()) == 1 and b.contar("IfcWall") == 4, "depois da falha, desfazer e refazer seguem normais"
                b.criar_parede(**PAR)
                assert (20.0, 0.0, 0.0) in estado(b, tmp_path, "grade.ifc")[0]["paredes"], f"{nome}: a falha mexeu no contador da grade"
                continue
            assert k > minimo, f"{nome}: o gancho k={k} deveria disparar (o comando faz {minimo} mutações ou mais)"
            assert estado(b, tmp_path, "depois.ifc")[2] == antes[2] + 1 and b.pode_refazer() == 0, f"{nome} sem falha: 1 transação nova e refazer limpo"

def test_gancho_vale_so_para_o_proximo_comando_de_edicao(mod, tmp_path):
    b, ws = novo(mod)
    b.definir_falha(40)
    b.editar_propriedades(ws[0], nome="1 mutação, o gancho 40 não dispara e é descartado")
    b.criar_parede(**PAR)  # faria mais de 40 mutações: com o gancho ainda armado falharia
    b.definir_falha(1)
    b.desfazer()  # desfazer, refazer e gravar não consomem o gancho
    b.refazer()
    b.gravar(str(tmp_path / "g.ifc"))
    with pytest.raises(RuntimeError):
        b.criar_parede(**PAR)
    b.criar_parede(**PAR)  # e o gancho foi descartado pela falha
    b.definir_falha(0)
    b.criar_parede(**PAR)

def test_historico_sem_teto_de_64_desfazeres(mod, tmp_path):  # o padrão do ifcopenshell-python é 64 (medido); o roteiro R tem ~600 transações
    b, ws = novo(mod, 0)
    base = estado(b, tmp_path, "base.ifc")
    for _ in range(150):
        ws += b.criar_parede(**PAR)
    cheio = estado(b, tmp_path, "cheio.ifc")
    assert cheio[2] == 151
    for i in range(150):
        assert len(b.desfazer()) == 1, f"desfazer {i + 1}"
    assert estado(b, tmp_path, "volta.ifc")[:2] == base[:2] and b.pode_refazer() == 150
    assert [b.refazer()[0] for _ in range(150)] == ws
    assert estado(b, tmp_path, "refeito.ifc") == cheio

def test_lote_de_mil_paredes_em_uma_transacao_cobre_a_grade_e_desfaz(mod, tmp_path):
    b, _ = novo(mod, 0)
    base = estado(b, tmp_path, "base.ifc")
    t0 = time.perf_counter()
    r = b.criar_paredes_lote(**PAR, quantidade=1000)
    dt = time.perf_counter() - t0
    assert len(set(r)) == 1000 and b.pode_desfazer() == 2 and dt < 20, f"lote de 1000: {dt:.1f} s"
    cheio = estado(b, tmp_path, "cheio.ifc")
    assert set(cheio[0]["paredes"]) == {((g % 50) * 5.0, (g // 50) * 4.0, 0.0) for g in range(1000)}
    assert sorted(b.desfazer()) == sorted(r) and estado(b, tmp_path, "volta.ifc")[:2] == base[:2]
    assert b.refazer() == r and estado(b, tmp_path, "refeito.ifc") == cheio

def roteirinho(b):
    b.criar_tipo(**TIPO)
    w = [b.criar_parede(**PAR)[0] for _ in range(2)]
    b.editar_propriedades(w[0], nome="Muro", propriedades={FIRE: "R60"})
    b.mudar_comprimento(w[1], 5.55)

def test_gravar_com_localidade_pt_br_nao_poe_virgula_decimal(mod, tmp_path):  # armadilha 3 da etapa 3 (T26): o fluxo B não tem o garantir_numerico_c do Python
    nome = next((n for n in ("pt_BR.UTF-8", "pt_BR.utf8", "Portuguese_Brazil.1252", "pt_BR") if _tem(n)), None)
    nome or pytest.skip("\n!!! SEM LOCALIDADE pt_BR NESTA MÁQUINA: o caso da vírgula decimal NÃO FOI EXECUTADO !!!\n")
    b = mod.Paredes()
    roteirinho(b)
    b.gravar(str(tmp_path / "c.ifc"))
    try:
        locale.setlocale(locale.LC_NUMERIC, nome)
        assert locale.localeconv()["decimal_point"] == ","
        b2 = mod.Paredes()
        roteirinho(b2)  # criar, editar e gravar com a vírgula ligada no processo
        b2.gravar(str(tmp_path / "pt.ifc"))
        assert locale.localeconv()["decimal_point"] == ",", "a biblioteca tem de devolver a localidade do processo como estava"
    finally:
        locale.setlocale(locale.LC_NUMERIC, "C")
    assert igual(assinatura(tmp_path / "pt.ifc"), assinatura(tmp_path / "c.ifc"), "ifc") == [] and not validar(tmp_path / "pt.ifc")

def _tem(n):
    try:
        locale.setlocale(locale.LC_NUMERIC, n)
        return True
    except locale.Error:
        return False
    finally:
        locale.setlocale(locale.LC_NUMERIC, "C")

def test_instancias_sao_independentes_e_podem_ser_criadas_e_destruidas(mod, tmp_path):
    b1, w1 = novo(mod, 3)
    b2, w2 = novo(mod, 1)
    b2.gravar(str(tmp_path / "2.ifc"))
    assert list(assinatura(tmp_path / "2.ifc")["paredes"]) == [(0.0, 0.0, 0.0)] and not set(w1) & set(w2)  # a grade de cada modelo começa em 0
    b1.desfazer()
    assert b2.pode_desfazer() == 2 and b2.pode_refazer() == 0
    for _ in range(100):
        x, _ = novo(mod, 2)
        x.desfazer()
        del x
        gc.collect()

def test_contar_bate_com_o_arquivo_gravado_inclusive_subtipos(mod, tmp_path):
    import ifcopenshell
    b, ws = novo(mod, 4)
    b.editar_propriedades(ws[0], propriedades={FIRE: "R60"})
    b.desfazer()
    b.desfazer()
    b.gravar(str(tmp_path / "c.ifc"))
    f = ifcopenshell.open(str(tmp_path / "c.ifc"))
    for c in ("IfcWall", "IfcWallType", "IfcProduct", "IfcRoot", "IfcRelationship", "IfcPropertySet", "IfcMaterialLayer", "IfcRelAssociatesMaterial"):
        assert b.contar(c) == len(f.by_type(c)), c
    assert b.contar(None) == len(list(f)) and b.contar("IfcWall") == 3
    with pytest.raises(ValueError):
        b.contar("IfcNaoExiste")

# ======================= S04-T14a: abrir a base e as correções do lote 22 (CONTRATO.md, "Parte 2a") =======================
# Itens 1 a 4 (obrigatórios) de LOTE_OPUS_22 (os opcionais 5, 7, 8 ficam sem caso). Porta própria: OBIM_S04_T14A_OBRIGATORIO=1 (CI). Sem o módulo pula; módulo sem a API da Parte 2a FALHA.
# Localidade e trava rodam em PROCESSO À PARTE (s04_fluxo_b_t14a_aux.py): queda ou impasse viram falha limpa. "Saída igual" com a base: o fluxo A (FluxoA(base)), por multiconjunto
# de paredes (a base e a grade colidem em 0,0,0, então não se acha parede pela posição); o resto do contrato é conferido sem olhar para A (`conferir`; o próprio A é a sentinela).
OBRIG14 = os.environ.get("OBIM_S04_T14A_OBRIGATORIO") == "1"
FB = aux.RAIZ / "prototypes" / "s04" / "fluxo_b"
FILHO = aux.AQUI.parent / "s04_fluxo_b_t14a_aux.py"
def pular14(msg):
    (pytest.fail if OBRIG14 else pytest.skip)(f"\n!!! aguarda S04-T14a: {msg} (oráculo da biblioteca Paredes com base NÃO FOI EXECUTADO) !!!\n")
@pytest.fixture(scope="module")
def mod14():
    if not TEM_MODULO:
        pular14("módulo fluxo_b_paredes ausente (build.sh de prototypes/s04/fluxo_b/ e PYTHONPATH)")
    import fluxo_b_paredes
    falta = [f"Paredes.{n}" for n in ("abrir", "produtos_base", "copiar_atributo") if not hasattr(fluxo_b_paredes.Paredes, n)] + [n for n in ("ModeloOcupado",) if not hasattr(fluxo_b_paredes, n)]
    falta and pytest.fail(f"\n!!! S04-T14a: a ponte não tem {falta} (CONTRATO.md, Parte 2a) !!!\n")
    return fluxo_b_paredes

@functools.lru_cache(maxsize=None)
def assinar(caminho):  # classes + multiconjunto de paredes (forma por create_shape, medidas na unidade do arquivo) + unidades, contextos e entidades soltas; sem GlobalId
    f = ifcopenshell.open(str(caminho))
    fm, nome = aux.formas(f), lambda x: x.Name if x is not None else ""  # noqa: E731
    def parede(w):
        rs, us = {r.RepresentationIdentifier: r for r in w.Representation.Representations}, E.get_material(w, should_inherit=False)
        tri, lo, hi, vol = fm[w.id()]
        return [w.Name or "", nome(E.get_type(w)), nome(E.get_container(w)), (E.get_pset(w, "Pset_WallCommon") or {}).get("FireRating") or "", [c.LayerThickness for c in us.ForLayerSet.MaterialLayers] if us else [],
                tri, *lo, *hi, vol, *P.get_local_placement(w.ObjectPlacement)[:3, 3].tolist(), rs["Body"].Items[0].Depth, *(aux.pontos_eixo(rs["Axis"])[1] if "Axis" in rs else [])]
    ps = sorted((parede(w) for w in f.by_type("IfcWall")), key=lambda p: (*p[:4], tuple(round(x, 3) for x in p[6:12])))
    return {"classes": dict(Counter(e.is_a() for e in f if e.is_a() not in aux.LIVRES | aux.MATERIAL)), "paredes": ps,
            "orfas": sorted(e.is_a() for e in f if not e.is_a("IfcRoot") and not e.is_a("IfcRepresentationContext") and not f.get_inverse(e)),
            "unidades": sorted(str((u.UnitType, u.Prefix, u.Name)) for u in f.by_type("IfcSIUnit")),
            "contextos": sorted(str((c.ContextType, c.ContextIdentifier, getattr(c, "TargetView", None), (getattr(c, "ParentContext", None) or c).ContextType, getattr(c, "CoordinateSpaceDimension", None),
                                     getattr(c, "Precision", None))) for c in f.by_type("IfcGeometricRepresentationContext"))}

def fazer_base(pasta, prefixo="MILLI", nomes=("Zeta", "Alfa", "Meio")):  # IFC sintético (scripts/gerar_modelo_grande.py: 5 paredes, 3 pavimentos), com a unidade e os nomes de pavimento pedidos
    import gerar_modelo_grande
    p = Path(pasta) / f"base_{prefixo}.ifc"
    gerar_modelo_grande.gerar(str(p), paredes=5, por_andar=2)
    f = ifcopenshell.open(str(p))
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = prefixo
    for s, n in zip(f.by_type("IfcBuildingStorey"), nomes):  # a ordem dos nomes difere da ordem no arquivo: o pavimento certo é o de menor Name, não o primeiro do arquivo
        s.Name = n
    f.write(str(p))
    return p, dict(esc={None: 1.0, "CENTI": 0.01, "MILLI": 0.001}[prefixo], pav=min(nomes), guids=set(aux.guids(f)), erros=validar(p), sig=assinar(str(p)),
                   produtos=sum(1 for e in f.by_type("IfcProduct") if e.Representation),
                   paredes={w.GlobalId: (w.Name, E.get_container(w).Name, tuple(P.get_local_placement(w.ObjectPlacement)[:3, 3].round(6).tolist())) for w in f.by_type("IfcWall")})
def roda(f, n=60):  # mini roteiro (tipo, 1 parede, lote de n, edições, desfazer/refazer, desfazer tudo); grava em cada marco
    m = {"inicio": str(f.gravar())}
    ed = [("editar_propriedades", dict(alvo=3, nome="Muro", propriedades={FIRE: "R60"})), ("mudar_comprimento", dict(alvo=4, comprimento=5.0))]
    for marco, cmds in (("tipo", [("criar_tipo", TIPO)]), ("parede", [("criar_parede", PAR)]), ("lote", [("criar_paredes_lote", {**PAR, "quantidade": n})]), ("edicoes", ed), ("desfeito", [("desfazer", {})] * 2), ("refeito", [("refazer", {})] * 2)):
        [f.rodar(c, **kw) for c, kw in cmds]
        m[marco] = str(f.gravar())
    while f.pilhas()[0]:
        f.rodar("desfazer")
    m["fim"] = str(f.gravar())
    return m
def rodar_a(pasta, base, n=60):
    import fluxo_a
    a = FluxoAd(pasta)
    a.f = fluxo_a.FluxoA(str(base), janela=False, saida=pasta)
    return roda(a, n)
def rodar_b(pasta, mod, base, n=60):
    b = FluxoBd(pasta, mod)
    b.b.abrir(str(base))
    return roda(b, n)

def conferir(m, info, n=60):  # o que o contrato exige da base aberta, escrito sem olhar para A nem para B
    S, esc, d = {k: assinar(p) for k, p in m.items()}, info["esc"], []
    ctx = lambda k, c: sum(f"'{c}'" in x for x in S[k]["contextos"])  # noqa: E731
    d += igual(S["inicio"], info["sig"], "inicio (a base reaberta e regravada)")
    d += [f"{k}: {ctx(k, 'Axis')} contextos Axis (esperado {e}: criado dentro do 1o comando que o usa, removido pelo desfazer)" for k, e in (("inicio", 0), ("tipo", 0), ("parede", 1), ("lote", 1), ("fim", 0)) if ctx(k, "Axis") != e]
    d += [f"{k}: {ctx(k, 'Body')} contextos Body (esperado 1: reaproveita o da base)" for k in S if ctx(k, "Body") != 1]
    d += igual(S["fim"], S["inicio"], "fim (desfazer tudo)") + igual(S["desfeito"], S["lote"], "desfeito") + igual(S["refeito"], S["edicoes"], "refeito")
    d += [f"{k}: entidades soltas {S[k]['orfas']}" for k in S if S[k]["orfas"] != info["sig"]["orfas"]]
    f = ifcopenshell.open(m["lote"])
    novas = [w for w in f.by_type("IfcWall") if w.GlobalId not in info["guids"]]
    d += [f"{len(novas)} paredes novas (esperado {n + 1})"] * (len(novas) != n + 1) + ["a base perdeu GlobalIds"] * (not info["guids"] <= set(aux.guids(f)))
    d += igual(sorted(tuple(P.get_local_placement(w.ObjectPlacement)[:3, 3].round(3).tolist()) for w in novas),
               sorted((round((g % 50) * 5.0 / esc, 3), round((g // 50) * 4.0 / esc, 3), 0.0) for g in range(n + 1)), "grade (a base não conta; posição na unidade do projeto)")
    d += [f"parede nova no pavimento {E.get_container(w).Name!r} (esperado {info['pav']!r}, o de menor Name)" for w in novas if E.get_container(w).Name != info["pav"]]
    prof = {r.Items[0].Depth for w in novas for r in w.Representation.Representations if r.RepresentationIdentifier == "Body"}
    d += [f"profundidade {prof}: tem de ser EXATAMENTE {round(2.8 / esc, 6)} na unidade do projeto"] * (prof != {round(2.8 / esc, 6)})
    d += [f"parede da base {g} mudou" for g, v in info["paredes"].items() if (f.by_guid(g).Name, E.get_container(f.by_guid(g)).Name, tuple(P.get_local_placement(f.by_guid(g).ObjectPlacement)[:3, 3].round(6).tolist())) != v]
    d += [f"B: erro novo de validação: {e}" for e in validar(m["lote"]) if e not in info["erros"]]
    return d
def abrir14(mod, base):
    b = mod.Paredes()
    b.abrir(str(base))
    return b
@pytest.fixture(scope="module")
def base_mm(tmp_path_factory):
    return fazer_base(tmp_path_factory.mktemp("base"))
@pytest.fixture(scope="module")
def marcos_a(base_mm, tmp_path_factory):
    return rodar_a(tmp_path_factory.mktemp("a14"), base_mm[0])
@pytest.fixture(scope="module")
def marcos_b(mod14, base_mm, tmp_path_factory):
    return rodar_b(tmp_path_factory.mktemp("b14"), mod14, base_mm[0])

def test_t14a_contrato_e_ci_declaram_a_parte_2a():
    t = (FB / "CONTRATO.md").read_text(encoding="utf-8")
    assert len(t.splitlines()) <= 80 and all(x in t for x in ("Parte 2a", "abrir", "produtos_base", "copiar_atributo", "ModeloOcupado", "OBIM_S04_T14A_OBRIGATORIO", "gil_scoped_release", "uselocale", "Ifc4::get_schema", "logic_error"))

def test_t14a_ci_liga_a_variavel_no_passo_do_fluxo_b_dos_dois_jobs():  # falha com mensagem clara se o passo 'Fluxo B, paredes em C++' faltar no ci.yml (não é para o oráculo recriá-lo)
    ci = (aux.RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert len(re.findall(r"OBIM_S04_T14A_OBRIGATORIO=1[^\n]*\n[^\n]*test_s04_fluxo_b_paredes\.py", ci)) == 2, "OBIM_S04_T14A_OBRIGATORIO=1 tem de estar no passo do fluxo B dos dois jobs (linux e windows)"

def test_t14a_sentinela_o_fluxo_a_cumpre_o_esperado_da_base(base_mm, marcos_a):
    assert conferir(marcos_a, base_mm[1]) == []

def base_ler(pasta):  # IFC4 com PARES de instâncias da mesma classe, valores diferentes e não nulos em cada tipo de atributo: nome -> (destino, origem, atributo)
    f = ifcopenshell.file(schema="IFC4")
    c = f.create_entity
    pts = [c("IfcCartesianPoint", Coordinates=x) for x in ((1.0, 2.0, 3.0), (4.0, 5.0))]
    pol = [c("IfcPolyline", Points=[pts[0], pts[1]]), c("IfcPolyline", Points=[pts[1], pts[0], pts[1]])]
    cam = [c("IfcMaterialLayer", Material=c("IfcMaterial", Name="m"), LayerThickness=t, IsVentilated=v, Priority=p) for t, v, p in ((0.1, True, 3), (0.3, False, 7))]
    seg = [c("IfcCompositeCurveSegment", Transition=t, SameSense=s, ParentCurve=x) for t, s, x in (("CONTINUOUS", True, pol[0]), ("DISCONTINUOUS", False, pol[1]))]
    par = [c("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=n) for n in ("A", "B")]
    fac = [c("IfcIndexedPolygonalFace", CoordIndex=i) for i in ((1, 2, 3), (4, 5, 6, 7))]
    end = [c("IfcPostalAddress", AddressLines=x) for x in (["Rua A"], ["Rua B", "Casa 2"])]
    lst = [c("IfcCartesianPointList2D", CoordList=x) for x in (((0.0, 1.0), (2.0, 3.0)), ((4.0, 5.0),))]
    ct = c("IfcGeometricRepresentationContext", ContextType="Model")
    sub = [c("IfcGeometricRepresentationSubContext", ContextIdentifier=i, ContextType="Model", ParentContext=ct, TargetView="MODEL_VIEW") for i in "xy"]
    f.write(str(Path(pasta) / "ler.ifc"))
    caso = lambda x, a: (x[0].id(), x[1].id(), a)  # noqa: E731
    return Path(pasta) / "ler.ifc", {"STRING": caso(par, "Name"), "DOUBLE": caso(cam, "LayerThickness"), "INTEGER": caso(cam, "Priority"), "LOGICAL": caso(cam, "IsVentilated"), "BOOLEAN": caso(seg, "SameSense"),
                                     "ENUMERATION": caso(seg, "Transition"), "ENTITY": caso(seg, "ParentCurve"), "AGGREGATE_OF_INT": caso(fac, "CoordIndex"), "AGGREGATE_OF_DOUBLE": caso(pts, "Coordinates"),
                                     "AGGREGATE_OF_STRING": caso(end, "AddressLines"), "AGGREGATE_OF_ENTITY": caso(pol, "Points"), "AGGREGATE_OF_AGGREGATE_OF_DOUBLE": caso(lst, "CoordList")}, caso(sub, "WorldCoordinateSystem"), (par[0].id(), cam[0].id())
def valor(arquivo, i, a):  # valor do atributo no arquivo (entidade vira ("#", id))
    norm = lambda v: ("#", v.id()) if isinstance(v, ifcopenshell.entity_instance) else tuple(norm(x) for x in v) if isinstance(v, (tuple, list)) else v  # noqa: E731
    return norm(getattr(ifcopenshell.open(str(arquivo)).by_id(i), a))
def fonte(*nomes):  # sem comentários
    return "\n".join(re.sub(r"//[^\n]*|/\*.*?\*/", "", (FB / n).read_text(encoding="utf-8"), flags=re.S) for n in nomes)

FONTE = {
    "item 3: o esquema IFC4 referenciado em código (Ifc4::get_schema()) na biblioteca": lambda lib, cpp, ponte, cmake: "Ifc4::get_schema" in lib,
    "item 1: nada de setlocale na biblioteca (processo inteiro)": lambda lib, cpp, ponte, cmake: not re.search(r"\bsetlocale\s*\(", lib),
    "item 1: localidade por thread (uselocale no POSIX, _configthreadlocale no Windows)": lambda lib, cpp, ponte, cmake: re.search(r"\buselocale\b", lib) and "_configthreadlocale" in lib,
    "item 4: std::mutex, try_lock e a mensagem 'ocupado' na biblioteca": lambda lib, cpp, ponte, cmake: "std::mutex" in lib and re.search(r"try_lock|try_to_lock", lib) and "ocupado" in lib,
    "item 4: a ponte solta o GIL (gil_scoped_release) e expõe ModeloOcupado": lambda lib, cpp, ponte, cmake: "gil_scoped_release" in ponte and "ModeloOcupado" in ponte,
    "item 2: `ler` com std::logic_error e sem `default: return {}`": lambda lib, cpp, ponte, cmake: (m := re.search(r"\bler\s*\([^)]*\)\s*(?:const\s*)?\{(.*?)\n\}", cpp, re.S)) and "logic_error" in m.group(1)
                                                                                         and not re.search(r"default\s*:\s*return\s*(\{\s*\}|Valor\s*\(\s*\))\s*;", m.group(1)),
}

@pytest.mark.parametrize("regra", FONTE)
def test_fonte_da_biblioteca(regra):
    assert FONTE[regra](fonte("paredes.cpp", "paredes.h"), fonte("paredes.cpp"), fonte("ponte.cpp"), (FB / "CMakeLists.txt").read_text(encoding="utf-8")), regra

def test_abrir_base_mm_cumpre_o_contrato(base_mm, marcos_b):
    assert conferir(marcos_b, base_mm[1]) == []

def test_abrir_base_mm_saida_igual_a_do_fluxo_a_em_cada_marco(marcos_a, marcos_b):
    for k in marcos_a:
        assert igual(assinar(marcos_a[k]), assinar(marcos_b[k]), k) == [], k

@pytest.mark.parametrize("prefixo", [None, "CENTI"], ids=["metro", "centimetro"])
def test_abrir_unidade_qualquer_profundidade_exata_e_grade_na_unidade_do_projeto(mod14, tmp_path, prefixo):
    p, info = fazer_base(tmp_path, prefixo)
    mb = rodar_b(tmp_path / "b", mod14, p, 4)
    assert conferir(mb, info, 4) == []
    ma = rodar_a(tmp_path / "a", p, 4)
    assert all(igual(assinar(ma[k]), assinar(mb[k]), k) == [] for k in ma)

def test_abrir_invalido_levanta_valueerror_e_nao_toca_no_modelo(mod14, tmp_path):
    ifcopenshell.file(schema="IFC2X3").write(str(tmp_path / "x23.ifc"))
    ifcopenshell.file(schema="IFC4").write(str(tmp_path / "vazio.ifc"))
    (tmp_path / "texto.ifc").write_text("isto não é um IFC\n", encoding="utf-8")
    b, _ = novo(mod14, 2)
    antes = (b.contar(None), b.pode_desfazer(), b.pode_refazer(), b.produtos_base())
    for nome, caminho, texto in (("ausente", tmp_path / "nao_existe.ifc", ""), ("vazio", "", ""), ("pasta", tmp_path, ""), ("texto", tmp_path / "texto.ifc", ""), ("IFC2X3", tmp_path / "x23.ifc", "IFC4")):
        with pytest.raises(ValueError, match=texto or r"\S"):
            b.abrir(str(caminho))
        assert (b.contar(None), b.pode_desfazer(), b.pode_refazer(), b.produtos_base()) == antes, f"{nome}: abrir inválido mexeu no modelo anterior"
    b.abrir(str(tmp_path / "vazio.ifc"))  # IFC4 sem pavimento abre; só criar parede dá erro
    b.criar_tipo("T", [0.1])
    with pytest.raises(ValueError, match=r"\S"):
        b.criar_parede("T", 4.0, 2.8, 0.15)
    assert b.pode_desfazer() == 1

def test_abrir_zera_pilhas_ultimo_grade_e_gancho_e_conta_produtos_da_base(mod14, base_mm, tmp_path):
    p, info = base_mm
    b, _ = novo(mod14, 3)
    assert b.produtos_base() == 0
    b.desfazer()
    b.definir_falha(1)
    b.abrir(str(p))
    assert (b.pode_desfazer(), b.pode_refazer()) == (0, 0) and not any(b.ultimo().values()) and b.produtos_base() == info["produtos"] == 5 and b.contar("IfcWall") == 5
    b.criar_tipo(**TIPO)  # o gancho de antes foi descartado
    w = b.criar_parede(**PAR)[0]
    assert b.produtos_base() == 5  # edições não mudam a base
    b.gravar(str(tmp_path / "r.ifc"))
    assert P.get_local_placement(ifcopenshell.open(str(tmp_path / "r.ifc")).by_guid(w).ObjectPlacement)[:3, 3].tolist() == [0.0, 0.0, 0.0], "a grade recomeça em 0 (as paredes da base não contam)"

def test_reabrir_o_ifc_gravado_pelo_b_continua_sem_duplicar_contexto_nem_tipo(mod14, marcos_b, tmp_path):
    p = marcos_b["lote"]  # 61 paredes, tipo e contextos criados pelo B
    b = abrir14(mod14, p)
    with pytest.raises(ValueError, match=r"\S"):
        b.criar_tipo(**TIPO)
    b.criar_parede(**PAR)
    b.gravar(str(tmp_path / "r.ifc"))
    a, c = assinar(p), assinar(str(tmp_path / "r.ifc"))
    assert c["contextos"] == a["contextos"] and c["classes"]["IfcWall"] == a["classes"]["IfcWall"] + 1 and c["classes"]["IfcWallType"] == 1 and len(c["paredes"]) == len(a["paredes"]) + 1
    assert b.produtos_base() == sum(1 for e in ifcopenshell.open(p).by_type("IfcProduct") if e.Representation)

def test_falha_no_1o_comando_que_cria_contexto_nao_deixa_contexto_nem_estado_parcial(mod14, base_mm, tmp_path):
    def estado(b, nome):
        b.gravar(str(tmp_path / nome))
        s = assinar(str(tmp_path / nome))
        return s["classes"], s["contextos"], s["orfas"], len(s["paredes"]), b.contar(None), b.pode_desfazer(), b.pode_refazer()
    for k in (1, 2, 3, 6, 11, 20):
        b = abrir14(mod14, base_mm[0])
        b.criar_tipo(**TIPO)
        antes = estado(b, f"antes{k}.ifc")
        b.definir_falha(k)
        try:
            b.criar_parede(**PAR)
        except RuntimeError as e:
            assert "falha" in str(e).lower() and estado(b, f"depois{k}.ifc") == antes, f"k={k}: o modelo ficou diferente (contexto Axis fora da transação?)"
            b.criar_parede(**PAR)  # e o comando seguinte cria o contexto normalmente
            assert sum("'Axis'" in x for x in estado(b, f"refeito{k}.ifc")[1]) == 1
            continue
        assert k > 3, f"o gancho k={k} deveria disparar"

@pytest.mark.parametrize("nome", ["STRING", "DOUBLE", "INTEGER", "LOGICAL", "BOOLEAN", "ENUMERATION", "ENTITY", "AGGREGATE_OF_INT", "AGGREGATE_OF_DOUBLE", "AGGREGATE_OF_STRING", "AGGREGATE_OF_ENTITY",
                                  "AGGREGATE_OF_AGGREGATE_OF_DOUBLE"])
def test_item2_ler_cobre_o_tipo_no_desfazer_e_refazer(mod14, tmp_path, nome):  # o desfazer guarda o valor de antes com `ler`: `default: return {}` o apagaria em silêncio
    p, casos, _, _ = base_ler(tmp_path)
    d, o, a = casos[nome]
    antes, origem = valor(p, d, a), valor(p, o, a)
    assert antes not in (None, ()) and antes != origem, "a base do caso tem de ter valores diferentes e não nulos"
    b = abrir14(mod14, p)
    b.copiar_atributo(d, o, a)
    b.gravar(str(tmp_path / "1.ifc"))
    assert valor(tmp_path / "1.ifc", d, a) == origem, "copiar_atributo não copiou"
    b.desfazer()
    b.gravar(str(tmp_path / "2.ifc"))
    assert valor(tmp_path / "2.ifc", d, a) == antes, f"{nome}: o desfazer não devolveu o valor de antes"
    b.refazer()
    b.gravar(str(tmp_path / "3.ifc"))
    assert valor(tmp_path / "3.ifc", d, a) == origem, f"{nome}: o refazer não devolveu o valor novo"

def test_item2_ler_levanta_no_que_nao_suporta_e_copiar_atributo_valida_a_entrada(mod14, tmp_path):
    p, casos, (sd, so, sa), (w, camada) = base_ler(tmp_path)
    b = abrir14(mod14, p)
    with pytest.raises(RuntimeError, match="suportado"):  # atributo derivado (`*`): std::logic_error, nunca `{}` em silêncio
        b.copiar_atributo(sd, so, sa)
    for args in ((999999, casos["STRING"][1], "Name"), (casos["STRING"][0], casos["STRING"][1], "NaoExiste"), (w, camada, "Name")):  # número, atributo e classes
        with pytest.raises(ValueError, match=r"\S"):
            b.copiar_atributo(*args)
    assert (b.pode_desfazer(), b.pode_refazer()) == (0, 0)
def filho(*args):
    try:
        p = subprocess.run([sys.executable, str(FILHO), *map(str, args)], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        pytest.fail("o processo filho TRAVOU (impasse da trava ou da localidade?)")
    linhas = [x for x in p.stdout.splitlines() if x.startswith("RESULTADO ")]
    assert p.returncode == 0 and linhas, f"o processo filho CAIU (código {p.returncode}):\n{p.stdout[-600:]}\n{p.stderr[-1500:]}"
    return json.loads(linhas[-1][10:])

@pytest.mark.parametrize("t,n", [(2, 10), (4, 5)], ids=["2 threads", "4 threads"])
def test_item1_localidade_por_thread_gravacoes_simultaneas_com_virgula_no_processo(mod14, tmp_path, t, n):
    r = filho("localidade", t, n, tmp_path)
    if r["localidade"] is None:
        pytest.skip("\n!!! SEM LOCALIDADE pt_BR NESTA MÁQUINA: o caso da vírgula decimal NÃO FOI EXECUTADO !!!\n")
    s = r["sondas"]
    assert not r["erros"] and r["virgula_no_processo"] is True and s["total"] > 100, r
    assert s["dentro_de_gravacao"] >= 20, f"quase nenhuma sonda caiu DENTRO de uma gravação: a ponte tem de soltar o GIL em comandos e gravar (nb::gil_scoped_release); senão nada roda em paralelo e o caso não prova nada ({s})"
    assert s["dentro_com_virgula"] == s["dentro_de_gravacao"] and s["com_virgula"] == s["total"], f"outra thread viu a localidade mudar durante uma gravação (setlocale do processo?): {s}"
    assert r["decimal_depois"] == ",", "a localidade do processo tem de voltar como estava (pt_BR), não ficar em C"
    assert len(r["arquivos"]) == t * n
    corpo, eixo = lambda c: ((0.0, 0.0), (0.0, 0.15), (c, 0.15), (c, 0.0), (0.0, 0.0)), lambda c: ((0.0, 0.0), (c, 0.0))  # noqa: E731
    esperado = Counter({corpo(4.25): 1499, eixo(4.25): 1499, corpo(5.5): 1, eixo(5.5): 1})
    for a in r["arquivos"]:
        f = ifcopenshell.open(a)
        assert Counter(tuple(tuple(round(v, 6) for v in pt) for pt in x.CoordList) for x in f.by_type("IfcCartesianPointList2D")) == esperado, f"{a}: medidas corrompidas (vírgula decimal?)"

def test_item4_segundo_escritor_com_espera_zero_falha_ocupado_e_a_leitura_espera_o_lote(mod14):
    r = filho("corrida", 2, 15000)
    assert len(r["iteracoes"]) == 2
    for i, x in enumerate(r["iteracoes"]):
        assert x["ocupado"] >= 1, f"{i}: o 2o escritor nunca viu a trava ocupada: a ponte tem de soltar o GIL no lote e o modelo ter std::mutex ({x})"
        assert x["maior_tentativa_ms"] < 200, f"{i}: com espera=0 o 2o escritor tem de falhar NA HORA, não esperar o lote ({x})"
        assert x["lido_durante"] == x["esperado"] == x["paredes_final"], f"{i}: a leitura viu o lote pela metade ({x})"
        assert x["retorno"] == 15000 and x["pode_desfazer"] == 3 and x["total"] == x["total_ref"], f"{i}: o escritor barrado tocou no modelo ou o lote saiu diferente do lote sozinho ({x})"
