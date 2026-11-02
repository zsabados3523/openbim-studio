# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T04, parte 3: bordas achadas na revisão (`docs/state/reports/F0-S06-T04-revisao.md` A1 a A7, C1 a C4). CONTRATO: o cabeçalho de
`test_s06_t04_vistas_ifc_oraculo.py` mais: (1) toda vista tem seu grupo ligado ao grupo pai "DRAWINGS", que tem UMA relação com N filhos; (2) apagar a
última vista tira também o grupo pai e a relação dele (arquivo volta ao conteúdo inicial e passa no validador); (3) `apagar_vista` só remove o que é da
vista (grupo ObjectType "DRAWING" de mesmo nome, relação/pset/referência/documento só dela); relação com outros `RelatedObjects` perde só a vista;
(4) referência "DRAWING" de ordem não numérica (de outro programa) não quebra leitura: vai depois das numéricas; as numéricas seguem a ordem do número,
não a ordem de criação no arquivo; (5) `colocar_vista` de vista sem documento (location None): ValueError, arquivo intacto; (6) `criar_vista` com
tamanho <= 0: ValueError antes de escrever; escala "1/50" vira "1:50" (ou ValueError); nome com ".." não vira ".." no Location; (7) `ler_vista`, `apagar_vista`
e `colocar_vista` com GlobalId que não é de IfcAnnotation DRAWING: VistaInexistente; (8) IFC2X3 sem IfcOwnerHistory: `criar_vista` recusa com ValueError
(arquivo intacto) OU grava sem aumentar os erros do validador [P: a escolha é do implementador]. Não editar; só o autor retira os `@AINDA_NAO`."""
import ifcopenshell
import ifcopenshell.validate as VAL
import pytest
import s05_conteudo_aux as R
import s06_t04_aux as A
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)



@pytest.fixture(params=A.ESQUEMAS)
def f(request):
    R.exigir()
    return A.novo_arquivo(request.param)


def erros(f):
    log = VAL.json_logger()
    VAL.validate(f, log, express_rules=True)
    return log.statements


def rel_pai(f):  # (pai, [relações IfcRelAssignsToGroup que o têm como RelatingGroup])
    pais = [g for g in f.by_type("IfcGroup") if g.ObjectType == "DRAWINGS"]
    assert len(pais) == 1
    return pais[0], [r for r in f.by_type("IfcRelAssignsToGroup") if r.RelatingGroup == pais[0]]


def ref_desenho(f, d, loc, ordem):  # referência "DRAWING" crua, como outro programa grava
    if f.schema == "IFC2X3":
        r = f.create_entity("IfcDocumentReference", Location=loc, ItemReference=f"DRAWING/{ordem}")
        d.DocumentReferences = tuple(d.DocumentReferences or ()) + (r,)
    else:
        r = f.create_entity("IfcDocumentReference", Location=loc, Description="DRAWING", Identification=ordem, ReferencedDocument=d)
    return r


def rel(f, cls, objs, **kw):
    ext = {"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}
    return f.create_entity(cls, GlobalId=ifcopenshell.guid.new(), RelatedObjects=objs, **ext, **kw)


def test_toda_vista_fica_ligada_ao_grupo_pai(f):  # C1
    import openbim_app.vistas_ifc as V
    gs = [V.criar_vista(f, f"V{i}", "PLANTA") for i in range(5)]
    pai, rels = rel_pai(f)
    assert len(rels) == 1 and len(rels[0].RelatedObjects) == 5
    for g in gs:
        a = f.by_guid(g)
        grupos = [r.RelatingGroup for r in f.by_type("IfcRelAssignsToGroup") if a in r.RelatedObjects]
        assert len(grupos) == 1 and grupos[0] in rels[0].RelatedObjects and grupos[0].Name == a.Name and grupos[0].ObjectType == "DRAWING"
    V.apagar_vista(f, gs[2])
    pai, rels = rel_pai(f)
    assert len(rels) == 1 and len(rels[0].RelatedObjects) == 4 and erros(f) == []


def test_apagar_todas_as_vistas_volta_ao_inicio(f):  # C2 (A1)
    import openbim_app.vistas_ifc as V
    zero = R.foto(f)
    g = V.criar_vista(f, "Unica", "CORTE")
    V.apagar_vista(f, g)
    assert R.diferencas(zero, R.foto(f)) == [] and erros(f) == []
    gs = [V.criar_vista(f, f"V{i}", "PLANTA") for i in range(3)]
    V.criar_prancha(f, "A-01", "x")
    for x in gs:
        V.colocar_vista(f, "A-01", x)
    V.apagar_prancha(f, "A-01")
    for x in gs:
        V.apagar_vista(f, x)
    assert R.diferencas(zero, R.foto(f)) == [] and erros(f) == [] and not [x for x in f.by_type("IfcGroup")]
    g2 = V.criar_vista(f, "De novo", "PLANTA")  # depois de esvaziar, criar de novo funciona e valida
    assert [x["gid"] for x in V.listar_vistas(f)] == [g2] and erros(f) == []


def test_apagar_nao_destroi_o_que_e_compartilhado(f):  # C3 (A2, A3)
    import openbim_app.vistas_ifc as V
    e1, e2 = A.annotation(f, "Ext1"), A.annotation(f, "Ext2")
    nossa = V.criar_vista(f, "Nossa", "PLANTA")
    n = f.by_guid(nossa)
    grupo = f.create_entity("IfcGroup", GlobalId=ifcopenshell.guid.new(), Name="Outro", **({"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}))
    rel(f, "IfcRelAssignsToGroup", [e1, e2, n], RelatingGroup=grupo)
    ref = f.create_entity("IfcDocumentReference", Location="ext/e.svg")
    doc = A.folha(f, "EXT", "doc externo")
    doc.Scope = "DRAWING"
    if f.schema == "IFC2X3":
        doc.DocumentReferences = (ref,)
    else:
        ref.ReferencedDocument = doc
    ra = rel(f, "IfcRelAssociatesDocument", [e1, n], RelatingDocument=ref)
    ps = f.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Outro", HasProperties=[
        f.create_entity("IfcPropertySingleValue", Name="K", NominalValue=f.create_entity("IfcLabel", "v"))], **({"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}))
    rel(f, "IfcRelDefinesByProperties", [e1, n], RelatingPropertyDefinition=ps)
    V.apagar_vista(f, nossa)
    assert grupo in f.by_type("IfcGroup") and {o.GlobalId for r in f.by_type("IfcRelAssignsToGroup") if r.RelatingGroup == grupo for o in r.RelatedObjects} == {e1.GlobalId, e2.GlobalId}
    assert ra in f.by_type("IfcRelAssociatesDocument") and ref in f.by_type("IfcDocumentReference") and doc in f.by_type("IfcDocumentInformation")
    assert V.ler_vista(f, e1.GlobalId)["location"] == "ext/e.svg" and A.UE.get_psets(e1)["Pset_Outro"]["K"] == "v"
    assert [o.GlobalId for o in ra.RelatedObjects] == [e1.GlobalId]
    with pytest.raises(V.VistaInexistente):
        V.ler_vista(f, nossa)
    assert not [g for g in f.by_type("IfcGroup") if g.Name == "Nossa"] and erros(f) == []


def test_referencia_de_ordem_nao_numerica_e_ordem_do_numero(f):  # C3 (A4), M26
    import openbim_app.vistas_ifc as V
    v1, v2, v3, v4 = (V.criar_vista(f, f"V{i}", "PLANTA") for i in range(4))
    loc = {g: V.ler_vista(f, g)["location"] for g in (v1, v2, v3, v4)}
    d = A.folha(f, "X-1", "externa")
    ref_desenho(f, d, loc[v3], "10")  # gravadas fora da ordem do número
    ref_desenho(f, d, loc[v4], "primeira")
    ref_desenho(f, d, loc[v1], "2")
    ref_desenho(f, d, loc[v2], "1")
    esperado = [v2, v1, v3, v4]  # numéricas pelo número (1, 2, 10), depois a não numérica
    assert V.ler_prancha(f, "X-1")["vistas"] == esperado
    assert [p["vistas"] for p in V.listar_pranchas(f)] == [esperado]
    V.criar_vista(f, "V5", "CORTE")  # e dá para continuar trabalhando na prancha
    novo = V.listar_vistas(f)[-1]["gid"]
    V.colocar_vista(f, "X-1", novo)
    assert sorted(V.ler_prancha(f, "X-1")["vistas"]) == sorted(esperado + [novo])


def test_vista_externa_sem_documento_nao_entra_na_prancha(f):  # C3 (A5)
    import openbim_app.vistas_ifc as V
    ext = A.annotation(f, "Sem doc")
    V.criar_prancha(f, "A-01", "x")
    antes = R.foto(f)
    with pytest.raises(ValueError):
        V.colocar_vista(f, "A-01", ext.GlobalId)
    assert R.diferencas(antes, R.foto(f)) == [] and V.ler_prancha(f, "A-01")["vistas"] == []


def test_tamanho_escala_e_nome_perigosos(f):  # C4 (A6, M28, M18)
    import openbim_app.vistas_ifc as V
    antes = R.foto(f)
    for t in ((0, 1, 1), (1, -1, 1), (1, 1, 0), (0.0, 0.0, 0.0)):
        with pytest.raises(ValueError):
            V.criar_vista(f, "X", "PLANTA", tamanho=t)
    assert R.diferencas(antes, R.foto(f)) == []
    try:
        g = V.criar_vista(f, "E", "PLANTA", escala="1/50")
    except ValueError:
        g = None
    if g:
        ps = A.vista_ifc(f, g)["pset"]
        assert V.ler_vista(f, g)["escala"] == "1:50" and ps["HumanScale"] == "1:50" and ps["Scale"] == "1/50"
    for nome in ("../../etc/passwd", "a/../b", "..", "..\\x", "C:\\x\\..\\y"):
        loc = A.vista_ifc(f, V.criar_vista(f, nome, "CORTE"))["location"]
        assert ".." not in loc.split("/") and "\\" not in loc and not loc.startswith("/") and ":" not in loc and loc
    assert erros(f) == []


def test_gid_que_nao_e_vista_e_recusado(f):  # C4 (M20)
    import openbim_app.vistas_ifc as V
    texto = A.annotation(f, "Legenda", tipo="TEXT")
    proj = f.by_type("IfcProject")[0]
    V.criar_prancha(f, "A-01", "x")
    antes = R.foto(f)
    for gid in (texto.GlobalId, proj.GlobalId, "naoexiste"):
        for fn in (lambda: V.ler_vista(f, gid), lambda: V.apagar_vista(f, gid), lambda: V.colocar_vista(f, "A-01", gid)):
            with pytest.raises(V.VistaInexistente):
                fn()
    assert R.diferencas(antes, R.foto(f)) == [] and texto in f.by_type("IfcAnnotation") and proj in f.by_type("IfcProject")


def test_ifc2x3_sem_ownerhistory_recusa_ou_nao_piora():  # C4 (A7)
    import openbim_app.vistas_ifc as V
    R.exigir()
    f = ifcopenshell.file(schema="IFC2X3")
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Sem dono")
    A.api("unit.assign_unit", f)
    A.api("context.add_context", f, context_type="Model")
    base, antes = len(erros(f)), R.foto(f)
    try:
        V.criar_vista(f, "V", "PLANTA")
    except ValueError as e:
        assert str(e) and R.diferencas(antes, R.foto(f)) == []
    else:
        assert len(erros(f)) <= base
