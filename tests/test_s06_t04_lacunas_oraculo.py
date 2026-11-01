# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T04c: lacunas e bugs do parecer Opus (LOTE_OPUS_75, 2026-10-31, parte T04, bugs 1 a 7 e lacunas e.1 a e.6). CONTRATO: o do
cabeçalho de `test_s06_t04_vistas_ifc_oraculo.py` e `test_s06_t04_borda_oraculo.py` mais: (1) `apagar_vista` só apaga o documento da vista quando a
referência dela é a ÚNICA do documento; com outra referência (de outra anotação), tira só a referência da vista; (2) documento da vista ou da
prancha que é filho de `IfcDocumentInformationRelationship` (ou associado a objeto por `IfcRelAssociatesDocument`) sai sem deixar relação vazia
nem relação com `RelatingDocument` nulo; (3) grupo da vista é "nosso" pelo `ObjectType == "DRAWING"` e por a vista ser o ÚNICO membro de TODAS as
relações que o têm como `RelatingGroup` (o `Name` do grupo não conta: anotação renomeada não deixa grupo órfão); em IFC4+ outra relação de outro
programa no mesmo grupo o mantém vivo; (4) `criar_prancha`/`criar_vista` recusam título/nome que não seja texto não vazio (ValueError; arquivo intacto);
(5) `criar_vista` valida `origem` (3 números finitos) antes de escrever (ValueError; arquivo intacto); (6) o número da prancha nunca produz `Location`
com "..", "\\", ":" ou barra inicial: [P: a escolha é do implementador] recusa (IdentificacaoInvalida, arquivo intacto) OU grava `Location` limpo
sob "pranchas/" mantendo a chave exata; (7) o documento da vista tem Identification/DocumentId = Location; ordem da nova referência na prancha = maior
ordem + 1; entidades novas em IFC2X3 usam o PRIMEIRO IfcOwnerHistory; `ambigua` só é True com número repetido. Cada bug é validado com o
validador do ifcopenshell (`express_rules=True`) nos 3 esquemas, com "base 0 erros" antes. Os casos que ainda falham levam `@AINDA_NAO` (xfail estrito);
casos que o código atual já cumpre (só matam mutantes) NÃO levam a marca. Não editar; só o autor retira os `@AINDA_NAO`."""
import math

import ifcopenshell
import ifcopenshell.api
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
    return [str(s.get("message", s))[:160] for s in log.statements]


def base0(f):
    e = erros(f)
    assert e == [], f"a base já deveria validar: {e[:3]}"


def kw(f):
    return {"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}


def rel(f, cls, objs, **k):
    return f.create_entity(cls, GlobalId=ifcopenshell.guid.new(), RelatedObjects=objs, **kw(f), **k)


def documento(f, nome, scope):  # IfcDocumentInformation "de outro programa", sem referências
    d = f.create_entity("IfcDocumentInformation", Name=nome, Scope=scope,
                        **({"DocumentId": nome} if f.schema == "IFC2X3" else {"Identification": nome}))
    return d


def ref_em(f, doc, loc):  # nova IfcDocumentReference dentro de `doc`
    if f.schema == "IFC2X3":
        r = f.create_entity("IfcDocumentReference", Location=loc)
        doc.DocumentReferences = tuple(doc.DocumentReferences or ()) + (r,)
        return r
    return f.create_entity("IfcDocumentReference", Location=loc, ReferencedDocument=doc)


def doc_pai(f, filho):  # documento pai "DRAWINGS" ligado por IfcDocumentInformationRelationship (convenção do Bonsai)
    pai = documento(f, "DRAWINGS", "DRAWINGS")
    r = f.create_entity("IfcDocumentInformationRelationship", RelatingDocument=pai, RelatedDocuments=[filho])
    return pai, r


# ---------- bug 1: documento compartilhado ----------
def test_documento_com_segunda_referencia_nao_e_apagado(f):
    import openbim_app.vistas_ifc as V
    g = V.criar_vista(f, "V", "PLANTA")
    outra = A.annotation(f, "B")
    v = A.vista_ifc(f, g)
    doc, minha = v["doc"], v["ref"]
    r2 = ref_em(f, doc, "b.svg")
    rb = rel(f, "IfcRelAssociatesDocument", [outra], RelatingDocument=r2)
    base0(f)
    V.apagar_vista(f, g)
    assert erros(f) == []
    assert doc in f.by_type("IfcDocumentInformation") and r2 in f.by_type("IfcDocumentReference") and rb in f.by_type("IfcRelAssociatesDocument")
    assert minha not in f.by_type("IfcDocumentReference") and A.doc_da_ref(r2) == doc and rb.RelatingDocument == r2
    assert [x.Location for x in A.refs_de(doc)] == ["b.svg"]
    with pytest.raises(V.VistaInexistente):
        V.ler_vista(f, g)


def test_documento_so_da_vista_continua_sendo_apagado(f):  # a regra nova não pode deixar documento órfão no caso comum
    import openbim_app.vistas_ifc as V
    zero = R.foto(f)
    g = V.criar_vista(f, "V", "PLANTA")
    V.apagar_vista(f, g)
    assert R.diferencas(zero, R.foto(f)) == [] and not [d for d in f.by_type("IfcDocumentInformation") if d.Scope == "DRAWING"]
    assert erros(f) == []


# ---------- bug 2: documento filho de IfcDocumentInformationRelationship ----------
def test_documento_da_vista_filho_de_documento_pai(f):
    import openbim_app.vistas_ifc as V
    g = V.criar_vista(f, "V", "PLANTA")
    pai, r = doc_pai(f, A.vista_ifc(f, g)["doc"])
    base0(f)
    V.apagar_vista(f, g)
    assert erros(f) == []
    assert pai in f.by_type("IfcDocumentInformation") and not [x for x in f.by_type("IfcDocumentInformationRelationship") if not x.RelatedDocuments]
    assert not [d for d in f.by_type("IfcDocumentInformation") if d.Scope == "DRAWING"]


def test_prancha_filha_de_documento_pai_e_associada_ao_projeto(f):
    import openbim_app.vistas_ifc as V
    V.criar_prancha(f, "A-01", "x")
    doc = A.prancha_ifc(f, "A-01")[0]
    pai, r = doc_pai(f, doc)
    proj = f.by_type("IfcProject")[0]
    ra = rel(f, "IfcRelAssociatesDocument", [proj], RelatingDocument=doc)
    base0(f)
    V.apagar_prancha(f, "A-01")
    assert erros(f) == []
    assert proj in f.by_type("IfcProject") and pai in f.by_type("IfcDocumentInformation")
    assert not [x for x in f.by_type("IfcRelAssociatesDocument") if x.RelatingDocument is None]
    assert not [x for x in f.by_type("IfcDocumentInformationRelationship") if not x.RelatedDocuments]
    assert ra not in f.by_type("IfcRelAssociatesDocument") and V.listar_pranchas(f) == []


# ---------- bug 3: anotação renomeada ----------
def test_anotacao_renomeada_nao_deixa_grupo_orfao(f):
    import openbim_app.vistas_ifc as V
    zero = R.foto(f)
    g = V.criar_vista(f, "V", "PLANTA")
    f.by_guid(g).Name = "Renomeada"  # outro programa (ou um futuro "renomear" que esquece o grupo)
    base0(f)
    V.apagar_vista(f, g)
    assert erros(f) == [] and not f.by_type("IfcGroup") and not f.by_type("IfcRelAssignsToGroup")
    assert R.diferencas(zero, R.foto(f)) == []


def test_renomeada_com_outras_vistas_mantem_o_pai(f):
    import openbim_app.vistas_ifc as V
    g1, g2 = V.criar_vista(f, "A", "PLANTA"), V.criar_vista(f, "B", "CORTE")
    f.by_guid(g1).Name = "Outro nome"
    base0(f)
    V.apagar_vista(f, g1)
    assert erros(f) == []
    assert [x["gid"] for x in V.listar_vistas(f)] == [g2]
    assert sorted(x.Name for x in f.by_type("IfcGroup")) == ["B", "DRAWINGS"]


# ---------- bug 4 (e M10): grupo da vista com 2a relação de outro programa ----------
def _com_segunda_relacao(f):
    import openbim_app.vistas_ifc as V
    g = V.criar_vista(f, "V", "PLANTA")
    grupo = next(x for x in f.by_type("IfcGroup") if x.ObjectType == "DRAWING")
    ext = A.annotation(f, "Ext")
    r2 = rel(f, "IfcRelAssignsToGroup", [ext], RelatingGroup=grupo)
    return g, grupo, ext, r2


def test_grupo_com_segunda_relacao_de_outro_programa_sobrevive(f):
    if f.schema == "IFC2X3":
        pytest.skip("em IFC2X3 o inverso IsGroupedBy é 1:1: o cenário já é inválido antes de apagar")
    import openbim_app.vistas_ifc as V
    g, grupo, ext, r2 = _com_segunda_relacao(f)
    base0(f)
    V.apagar_vista(f, g)
    assert erros(f) == []
    assert grupo in f.by_type("IfcGroup") and r2 in f.by_type("IfcRelAssignsToGroup") and r2.RelatingGroup == grupo
    assert list(r2.RelatedObjects) == [ext] and ext in f.by_type("IfcAnnotation")


def test_grupo_com_outro_membro_na_mesma_relacao_sobrevive(f):
    import openbim_app.vistas_ifc as V
    g = V.criar_vista(f, "V", "PLANTA")
    grupo = next(x for x in f.by_type("IfcGroup") if x.ObjectType == "DRAWING")
    ext = A.annotation(f, "Ext")
    r = next(x for x in f.by_type("IfcRelAssignsToGroup") if x.RelatingGroup == grupo)
    r.RelatedObjects = tuple(r.RelatedObjects) + (ext,)
    base0(f)
    V.apagar_vista(f, g)
    assert erros(f) == [] and grupo in f.by_type("IfcGroup") and list(r.RelatedObjects) == [ext]


def test_grupo_alheio_com_so_a_vista_nao_e_apagado(f):  # grupo de outro tipo (ObjectType não DRAWING) nunca é nosso
    if f.schema == "IFC2X3":
        pytest.skip("em IFC2X3 grupo sem membros viola o inverso obrigatório; o cenário não tem versão válida")
    import openbim_app.vistas_ifc as V
    g = V.criar_vista(f, "V", "PLANTA")
    outro = f.create_entity("IfcGroup", GlobalId=ifcopenshell.guid.new(), Name="Meu grupo", ObjectType="OUTRO", **kw(f))
    rel(f, "IfcRelAssignsToGroup", [f.by_guid(g)], RelatingGroup=outro)
    base0(f)
    V.apagar_vista(f, g)
    assert erros(f) == [] and outro in f.by_type("IfcGroup")


# ---------- bug 5: Name None ----------
def test_titulo_e_nome_nao_textuais_sao_recusados(f):
    import openbim_app.vistas_ifc as V
    V.criar_vista(f, "P", "PLANTA")
    antes = R.foto(f)
    for ruim in (None, "", 5, 1.5):
        with pytest.raises(ValueError):
            V.criar_prancha(f, "A-01", ruim)
        with pytest.raises(ValueError):
            V.criar_vista(f, ruim, "PLANTA")
        assert R.diferencas(antes, R.foto(f)) == [], f"recusa de {ruim!r} deixou entidade solta"
    assert erros(f) == [] and V.listar_pranchas(f) == []
    assert V.criar_prancha(f, "A-01", "Titulo") == "A-01" and erros(f) == []  # e o caso normal segue valendo


# ---------- bug 6: origem ----------
def test_origem_invalida_e_recusada_antes_de_escrever(f):
    import openbim_app.vistas_ifc as V
    antes = R.foto(f)
    for ruim in ((1, 2), (1, 2, 3, 4), ("a", 2, 3), (None, 0, 0), (math.nan, 0, 0), (0, math.inf, 0), 7, None):
        with pytest.raises(ValueError):
            V.criar_vista(f, "V", "PLANTA", origem=ruim)
        assert R.diferencas(antes, R.foto(f)) == [], f"origem {ruim!r} deixou entidade solta"
    assert V.listar_vistas(f) == [] and erros(f) == []
    g = V.criar_vista(f, "V", "PLANTA", origem=(1, 2.5, -3))  # inteiros e negativos continuam valendo
    assert A.vista_ifc(f, g)["origem"] == pytest.approx((1.0, 2.5, -3.0)) and erros(f) == []


# ---------- bug 7: número da prancha no Location ----------
def test_numero_de_prancha_perigoso_nao_gera_location_perigoso(f):
    import openbim_app.vistas_ifc as V
    V.criar_vista(f, "P", "PLANTA")
    for numero in ("../../x", "..", "a/../b", "..\\x", "C:\\x", "/abs", "a\\b"):
        antes = R.foto(f)
        try:
            V.criar_prancha(f, numero, "t")
        except V.IdentificacaoInvalida:
            assert R.diferencas(antes, R.foto(f)) == [], f"{numero!r} recusado deixou entidade solta"
            continue
        _, por = A.prancha_ifc(f, numero)  # aceito: a chave é a exata e os Locations são limpos
        for r in por["LAYOUT"] + por["TITLEBLOCK"]:
            p = r.Location
            assert p.startswith("pranchas/") and ".." not in p.split("/") and "\\" not in p and ":" not in p and not p.startswith("/"), (numero, p)
        assert V.ler_prancha(f, numero)["numero"] == numero
    assert erros(f) == []


def test_numero_comum_continua_valendo_com_barra_e_ponto(f):  # a regra do bug 7 não pode matar os números do contrato
    import openbim_app.vistas_ifc as V
    for n in ("A-01", "A 1.2/B", "1", "a-01"):
        assert V.criar_prancha(f, n, "x") == n and V.ler_prancha(f, n)["numero"] == n
    assert erros(f) == []


# ---------- mutantes M1, M2, M4, M5, M6, M8: casos rápidos ----------
def test_ordem_nova_e_maior_ordem_mais_um(f):  # M1: len(refs)+1 repete a ordem depois de apagar a do meio
    import openbim_app.vistas_ifc as V
    gs = [V.criar_vista(f, f"V{i}", "PLANTA") for i in range(4)]
    V.criar_prancha(f, "A-01", "x")
    for x in gs[:3]:
        V.colocar_vista(f, "A-01", x)
    V.apagar_vista(f, gs[1])  # ordens que sobram: 1 e 3
    V.colocar_vista(f, "A-01", gs[3])
    _, por = A.prancha_ifc(f, "A-01")
    ordens = sorted(int(A.ordem(r)) for r in por["DRAWING"])
    assert ordens == [1, 3, 4], ordens
    assert V.ler_prancha(f, "A-01")["vistas"] == [gs[0], gs[2], gs[3]] and erros(f) == []


def test_cinco_vistas_de_mesmo_nome_tem_locations_distintos(f):  # M2: while -> if colide na 4a
    import openbim_app.vistas_ifc as V
    gs = [V.criar_vista(f, "Planta", "PLANTA") for _ in range(6)]
    locs = [A.vista_ifc(f, g)["location"] for g in gs]
    assert len(set(locs)) == 6, locs
    V.apagar_vista(f, gs[2])
    novo = V.criar_vista(f, "Planta", "PLANTA")  # depois de apagar, o novo também não colide com os vivos
    vivos = [A.vista_ifc(f, g)["location"] for g in gs[:2] + gs[3:] + [novo]]
    assert len(set(vivos)) == 6 and erros(f) == []


def test_apagar_vista_tira_a_referencia_de_todas_as_pranchas(f):  # M4: tira só da 1a prancha
    import openbim_app.vistas_ifc as V
    g, outra = V.criar_vista(f, "V", "PLANTA"), V.criar_vista(f, "W", "CORTE")
    for n in ("P1", "P2", "P3"):
        V.criar_prancha(f, n, n)
        V.colocar_vista(f, n, g)
        V.colocar_vista(f, n, outra)
    loc = A.vista_ifc(f, g)["location"]
    V.apagar_vista(f, g)
    for n in ("P1", "P2", "P3"):
        _, por = A.prancha_ifc(f, n)
        assert [r.Location for r in por["DRAWING"]] == [A.vista_ifc(f, outra)["location"]], n
        assert V.ler_prancha(f, n)["vistas"] == [outra]
    assert not [r for r in f.by_type("IfcDocumentReference") if r.Location == loc] and erros(f) == []


def test_pranchas_de_numeros_unicos_nao_sao_ambiguas(f):  # M5: ambigua = contagem > 0
    import openbim_app.vistas_ifc as V
    for n in ("A-01", "A-02", "B-01"):
        V.criar_prancha(f, n, n)
    lista = V.listar_pranchas(f)
    assert len(lista) == 3 and all(p["ambigua"] is False for p in lista)
    assert all(V.ler_prancha(f, p["numero"])["ambigua"] is False for p in lista)
    A.folha(f, "A-01", "de outro programa")  # repetição de verdade: só as duas A-01 ficam ambíguas
    assert {p["numero"]: p["ambigua"] for p in V.listar_pranchas(f)} == {"A-01": True, "A-02": False, "B-01": False}
    assert sum(1 for p in V.listar_pranchas(f) if p["numero"] == "A-01") == 2


def test_ifc2x3_com_dois_ownerhistory_usa_o_primeiro():  # M6: usa o último
    import openbim_app.vistas_ifc as V
    R.exigir()
    f = A.novo_arquivo("IFC2X3")
    oh1 = f.by_type("IfcOwnerHistory")[0]
    oh2 = f.create_entity("IfcOwnerHistory", OwningUser=oh1.OwningUser, OwningApplication=oh1.OwningApplication, ChangeAction="ADDED", CreationDate=1)
    assert f.by_type("IfcOwnerHistory")[0] == oh1 and oh2 in f.by_type("IfcOwnerHistory")
    antes = {e.id() for e in f}
    V.criar_vista(f, "V", "PLANTA")
    V.criar_vista(f, "W", "CORTE")
    novos = [e for e in f if e.id() not in antes and e.is_a("IfcRoot")]
    assert len(novos) >= 10
    assert all(e.OwnerHistory == oh1 for e in novos), [e.is_a() for e in novos if e.OwnerHistory != oh1]
    assert erros(f) == []


def test_documento_da_vista_tem_identificacao_igual_ao_location(f):  # M8: Identification = nome
    import openbim_app.vistas_ifc as V
    g1, g2 = V.criar_vista(f, "Planta Térreo", "PLANTA"), V.criar_vista(f, "Planta Térreo", "PLANTA")
    for g in (g1, g2):
        v = A.vista_ifc(f, g)
        assert A.numero_de(v["doc"]) == v["location"] == v["ref"].Location
    assert A.numero_de(A.vista_ifc(f, g1)["doc"]) != A.numero_de(A.vista_ifc(f, g2)["doc"])
    assert erros(f) == []
