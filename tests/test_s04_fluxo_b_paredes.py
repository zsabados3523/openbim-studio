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
import gc
import importlib.util
import locale
import os
import sys
import time

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

# ---------- sentinelas: rodam sem o módulo ----------
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

# ---------- saída igual ----------
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

# ---------- IFC gravado ----------
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

# ---------- erros e atomicidade ----------
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

# ---------- localidade, instâncias, contagem ----------
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
