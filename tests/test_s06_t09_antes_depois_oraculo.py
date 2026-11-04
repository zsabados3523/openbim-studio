# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T09: IFC antes/depois igual por conteúdo, exceto as entidades previstas, e válido (cartão T09; régua do T04 da S05).
Fluxo real: base gravada em disco, `Sessao` (SessaoModelo + Lateral + Historico), 2 vistas e 1 prancha numa transação, `gravar_par` (carimba o pset
OBIM_Projeto), reabrir o IFC gravado. Régua: `s05_conteudo_aux.foto/diferencas` (sem tolerância). CONTRATO:
1. Nada que existia muda (todo GlobalId e toda forma sem GlobalId da base seguem iguais), em IFC2X3, IFC4 e IFC4X3.
2. O que entra é EXATAMENTE as listas PREVISTAS abaixo (classe a classe, com contagem); qualquer classe a mais, a menos ou a mais de uma vez falha.
   Inclui o pset OBIM_Projeto (LadoId, Revisao 1) e nada mais no projeto.
3. O IFC gravado passa em `ifcopenshell.validate` (regras EXPRESS); regravar sem carimbo não muda nada; regravar com carimbo muda só Revisao.
Não editar na implementação. GUARDA (pula, nunca afrouxa): sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 vira falha."""
import ifcopenshell
import ifcopenshell.validate as VAL
import pytest
import s05_conteudo_aux as R
import s06_t04_aux as A
from collections import Counter
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)
from s06_t04_sessao_aux import Sessao

# ---- entidades previstas para 2 vistas + 1 prancha (+ carimbo), por classe e contagem ----
COM_GLOBALID = {  # vista: anotação, EPset_Drawing + sua relação, associação ao documento, grupo da vista + sua relação; 1 grupo pai + sua relação; carimbo
    "IfcAnnotation": 2, "IfcPropertySet": 3, "IfcRelDefinesByProperties": 3, "IfcRelAssociatesDocument": 2, "IfcGroup": 3, "IfcRelAssignsToGroup": 3}
SEM_GLOBALID = {  # sem GlobalId: posição, bloco, CSG, representação (por vista), documentos e referências (3 docs, 2+4 refs), 6+2 propriedades
    "IfcCartesianPoint": 4, "IfcAxis2Placement3D": 4, "IfcLocalPlacement": 2, "IfcBlock": 2, "IfcCsgSolid": 2, "IfcShapeRepresentation": 2,
    "IfcProductDefinitionShape": 2, "IfcPropertySingleValue": 8, "IfcDocumentInformation": 3, "IfcDocumentReference": 6}


def montar_base(esquema, destino):
    f = A.novo_arquivo(esquema)
    kw = {"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if A.e2x3(f) else {}
    g = ifcopenshell.guid.new
    andar = f.create_entity("IfcBuildingStorey", GlobalId=g(), Name="Térreo", CompositionType="ELEMENT", **kw)
    paredes = [f.create_entity("IfcWall", GlobalId=g(), Name=f"Parede {i}", **kw) for i in range(3)]
    f.create_entity("IfcRelAggregates", GlobalId=g(), RelatingObject=f.by_type("IfcProject")[0], RelatedObjects=[andar], **kw)
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=g(), RelatingStructure=andar, RelatedElements=paredes, **kw)
    ps = f.create_entity("IfcPropertySet", GlobalId=g(), Name="Pset_X", HasProperties=[
        f.create_entity("IfcPropertySingleValue", Name="K", NominalValue=f.create_entity("IfcLabel", "v"))], **kw)
    f.create_entity("IfcRelDefinesByProperties", GlobalId=g(), RelatedObjects=paredes[:2], RelatingPropertyDefinition=ps, **kw)
    A.annotation(f, "Legenda", tipo="TEXT")  # "de outro programa": não pode mudar
    A.folha(f, "X-1", "Folha externa")
    f.write(str(destino))
    return destino


def criar(s):
    import openbim_app.vistas_ifc as V

    def fn(t):
        g1 = V.criar_vista(t.ifc, "Planta Térreo", "PLANTA", escala="1:50", origem=(1.0, 2.0, 1.2), tamanho=(12.0, 8.0, 3.0))
        g2 = V.criar_vista(t.ifc, "Corte AA", "CORTE")
        V.criar_prancha(t.ifc, "A-01", "Plantas e cortes")
        V.colocar_vista(t.ifc, "A-01", g2)
        V.colocar_vista(t.ifc, "A-01", g1)
    s.tx(fn)


def gravar(s, destino, pasta, **kw):
    import openbim_app.gravacao_par as GP
    GP.gravar_par(sessao=s.s, historico=s.h, lateral=s.lat, destino=destino, pasta_projeto=pasta, lado_id="lado-t09", seq=1, **kw)


def novas(antes, depois):  # (por classe das com GlobalId, por classe das sem GlobalId, sumiram, mudaram)
    com = {g: v for g, v in depois["com"].items() if g not in antes["com"]}
    sem = depois["sem"] - antes["sem"]
    sumiu = [g for g in antes["com"] if g not in depois["com"]] + list((antes["sem"] - depois["sem"]).elements())
    mudou = [g for g, v in antes["com"].items() if g in depois["com"] and depois["com"][g] != v]
    por_classe = Counter()
    for (classe, _), n in sem.items():
        por_classe[classe] += n
    return Counter(v[0] for v in com.values()), por_classe, sumiu, mudou


@pytest.fixture(params=A.ESQUEMAS)
def caso(request, tmp_path):
    R.exigir()
    base = montar_base(request.param, tmp_path / "Base.ifc")
    destino, pasta = tmp_path / "Casa.ifc", tmp_path / "pasta"
    pasta.mkdir()
    antes = R.foto(ifcopenshell.open(str(base)))
    s = Sessao(ifcopenshell.open(str(base)))
    criar(s)
    gravar(s, destino, pasta)
    return request.param, antes, s, destino, pasta


def somar(*ds):
    t = Counter()
    for d in ds:
        t.update(d)
    return t


def test_so_as_entidades_previstas_entram_e_o_resto_fica_igual(caso):
    esquema, antes, _, destino, _ = caso
    com, sem, sumiu, mudou = novas(antes, R.foto(ifcopenshell.open(str(destino))))
    assert sumiu == [] and mudou == [], f"algo que existia sumiu ou mudou: {sumiu[:5]} {mudou[:5]}"
    assert dict(com) == COM_GLOBALID, dict(com)
    esperado = dict(SEM_GLOBALID, **({"IfcOwnerHistory": 2} if esquema == "IFC2X3" else {}))  # IFC2X3: o carimbo traz 1 histórico por entidade nova
    assert dict(sem) == esperado, dict(sem)


def test_carimbo_obim_projeto_e_so_ele(caso):
    import ifcopenshell.util.element as UE
    _, _, _, destino, _ = caso
    g = ifcopenshell.open(str(destino))
    projeto = g.by_type("IfcProject")[0]
    ps = [p for p in g.by_type("IfcPropertySet") if p.Name == "OBIM_Projeto"]
    assert len(ps) == 1 and sorted(p.Name for p in ps[0].HasProperties) == ["LadoId", "Revisao"]
    rels = [r for r in g.by_type("IfcRelDefinesByProperties") if projeto in r.RelatedObjects]
    assert len(rels) == 1 and rels[0].RelatingPropertyDefinition == ps[0] and list(rels[0].RelatedObjects) == [projeto]
    assert {k: {a: b for a, b in v.items() if a != "id"} for k, v in UE.get_psets(projeto).items()} == {"OBIM_Projeto": {"LadoId": "lado-t09", "Revisao": 1}}


def test_vistas_e_prancha_continuam_la_depois_de_reabrir(caso):
    import openbim_app.vistas_ifc as V
    _, _, _, destino, _ = caso
    g = ifcopenshell.open(str(destino))
    assert sorted(v["nome"] for v in V.listar_vistas(g)) == ["Corte AA", "Planta Térreo"]
    p = V.ler_prancha(g, "A-01")
    assert p["titulo"] == "Plantas e cortes" and [V.ler_vista(g, x)["nome"] for x in p["vistas"]] == ["Corte AA", "Planta Térreo"]
    assert V.ler_prancha(g, "X-1")["vistas"] == [] and len(V.listar_vistas(g)) == 2, "a folha e a anotação externas seguem como eram"


def test_ifc_gravado_passa_no_validador(caso):
    esquema, _, _, destino, _ = caso
    log = VAL.json_logger()
    VAL.validate(ifcopenshell.open(str(destino)), log, express_rules=True)
    assert log.statements == [], (esquema, log.statements[:3])


def test_gravar_reabrir_e_regravar_nao_muda_mais_nada(caso, tmp_path):
    _, _, _, destino, pasta = caso
    f1 = R.foto(ifcopenshell.open(str(destino)))
    s2 = Sessao(ifcopenshell.open(str(destino)))
    assert R.diferencas(f1, R.foto(s2.f)) == [], "reabrir não muda o conteúdo"
    gravar(s2, destino, pasta, carimbo=False)
    f2 = R.foto(ifcopenshell.open(str(destino)))
    assert R.diferencas(f1, f2) == [] and f1["sem"] == f2["sem"], "regravar sem carimbo não muda nada"
    s3 = Sessao(ifcopenshell.open(str(destino)))
    gravar(s3, destino, pasta)  # com carimbo: Revisao 1 -> 2 e só isso
    g3 = ifcopenshell.open(str(destino))
    import ifcopenshell.util.element as UE
    assert UE.get_psets(g3.by_type("IfcProject")[0])["OBIM_Projeto"]["Revisao"] == 2
    com, sem, sumiu, mudou = novas(f2, R.foto(g3))
    assert dict(com) == {} and dict(sem) == {"IfcPropertySingleValue": 1} and len(sumiu) == 1 and sumiu[0][0] == "IfcPropertySingleValue"
    assert mudou == [next(p.GlobalId for p in g3.by_type("IfcPropertySet") if p.Name == "OBIM_Projeto")], "só o pset do carimbo muda (Revisao)"


def test_desfazer_a_criacao_volta_ao_antes(tmp_path):
    R.exigir()
    base = montar_base("IFC4", tmp_path / "Base.ifc")
    s = Sessao(ifcopenshell.open(str(base)))
    antes = s.foto()
    criar(s)
    assert R.diferencas(antes, s.foto()) != []
    s.desfazer()
    assert R.diferencas(antes, s.foto()) == []
