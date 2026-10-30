# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T04: vista e prancha DENTRO do IFC (modelo híbrido; ADR-003 §3, §5, §8, §11 itens a a g; cartão T04).
Não editar este arquivo nem `tests/s06_t04_aux.py` na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit
próprio, depois da implementação (só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`). Oráculo = ADR-003 + ficha 2026-10-29 (formato do Bonsai, só nomes).
CONTRATO `app/openbim_app/vistas_ifc.py` (sem Qt; [P] = escolha do oráculo que o cartão não fixa, provisória até o PO/líder confirmar):
1. Funções recebem o `ifcopenshell.file` (`t.ifc` dentro de `Historico.transacao`; escrita fora da transação -> `EdicaoForaDeTransacao` do `transacao`;
   leitura aceita o arquivo cru). Esquemas: IFC2X3, IFC4 e IFC4X3. Em IFC2X3 o arquivo já tem um IfcOwnerHistory: reaproveitar o primeiro. [P] nomes.
2. `criar_vista(ifc, nome, tipo, escala="1:100", origem=(0,0,0), tamanho=(10.0,10.0,3.0)) -> GlobalId`; tipo "PLANTA" ou "CORTE" (outro: ValueError,
   arquivo intacto). Grava: IfcAnnotation(ObjectType "DRAWING"; em IFC4X3 PredefinedType USERDEFINED) com IfcCsgSolid>IfcBlock (X,Y,Z = tamanho) e
   ObjectPlacement em `origem` (RepresentationType livre desde que o validador aceite: em IFC2X3 "CSG" é recusado para IfcCsgSolid, "SolidModel" passa nas 3); pset EPset_Drawing SÓ com TargetView (PLAN_VIEW/SECTION_VIEW), Scale ("1/100") e HumanScale ("1:100"); IfcGroup
   (ObjectType "DRAWING", Name = nome) ligado à anotação e ao grupo pai "DRAWINGS" (ObjectType "DRAWINGS"); IfcDocumentInformation(Scope "DRAWING",
   Name = nome) + IfcDocumentReference(Location) + IfcRelAssociatesDocument anotação->referência. `Location`: relativo, barras "/", único por vista
   (nome repetido gera Location diferente).
3. `ler_vista(ifc, gid) -> dict(gid, nome, tipo, escala, location, origem, tamanho)`; `listar_vistas(ifc) -> lista desses dicts` (toda IfcAnnotation
   com ObjectType "DRAWING", feita por nós ou não; campo ausente = None); `apagar_vista(ifc, gid)` tira anotação, grupo, documento, referência, relações
   e as referências "DRAWING" dela nas pranchas. Inexistente: `VistaInexistente` (KeyError).
4. `criar_prancha(ifc, numero, titulo) -> numero`: IfcDocumentInformation(Scope "SHEET", Name = titulo, chave = Identification; DocumentId em IFC2X3)
   com 1 referência "LAYOUT" e 1 "TITLEBLOCK" (Location texto não vazio, [P]). Etiqueta da referência: Description em IFC4+; em IFC2X3 o prefixo de ItemReference ("LAYOUT", "TITLEBLOCK", "DRAWING/1"), nunca Name: o validador
   de IFC2X3 recusa referência com Name que pertence a um documento (regra "Name xor ReferenceToDocument"; ADR §3.2 precisa de correção).
   `colocar_vista(ifc, numero, gid)`: +1 referência "DRAWING", Location = a da vista, ordem ("1","2",...) em Identification (IFC4+) ou no sufixo de ItemReference
   (IFC2X3); a mesma vista duas vezes na mesma prancha: ValueError. `ler_prancha(ifc, numero) -> dict(numero, titulo, vistas=[GlobalId na ordem], ambigua)`;
   `listar_pranchas(ifc)` idem (toda Scope "SHEET"); `apagar_prancha(ifc, numero)` tira documento e referências (as vistas ficam).
5. Chave da prancha: exata (sem espaços nas pontas, não vazia; maiúscula conta; ponto, barra e espaço no meio valem). Repetida: `IdentificacaoRepetida`;
   fora da regra: `IdentificacaoInvalida` (as duas ValueError); arquivo intacto. Duas pranchas de mesmo número (outro programa): `ambigua` True nas duas,
   `ler_prancha`/`apagar_prancha` -> `PranchaAmbigua` (ValueError), `criar_prancha` -> IdentificacaoRepetida; o módulo nunca escolhe. `PranchaInexistente` (KeyError).
Régua: `s05_conteudo_aux.foto` (conteúdo, sem tolerância; inclui o lateral). GUARDA (pula, nunca afrouxa): sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 vira falha."""
import pytest
import s05_conteudo_aux as R
import s06_t04_aux as A
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="F0-S06-T04: openbim_app.vistas_ifc ainda não existe")


@pytest.fixture(params=A.ESQUEMAS)
def f(request):
    R.exigir()
    return A.novo_arquivo(request.param)


def ligados(f, a, b):  # existe alguma relação IFC que cita a e b?
    return any(r.is_a("IfcRelationship") and b in f.traverse(r, max_levels=1) for r in f.get_inverse(a))


# ---------- formato (ADR-003 §3) ----------
@AINDA_NAO
def test_vista_formato_no_ifc(f):
    import openbim_app.vistas_ifc as V
    gid = V.criar_vista(f, "Planta Térreo", "PLANTA", escala="1:50", origem=(1.0, 2.0, 1.2), tamanho=(12.0, 8.0, 3.0))
    v = A.vista_ifc(f, gid)
    a = v["ann"]
    assert a.GlobalId == gid and a.ObjectType == "DRAWING" and a.Name == "Planta Térreo"
    if f.schema.startswith("IFC4X3"):
        assert a.PredefinedType == "USERDEFINED"
    assert v["csg"].is_a("IfcCsgSolid") and v["bloco"].is_a("IfcBlock")
    assert (v["bloco"].XLength, v["bloco"].YLength, v["bloco"].ZLength) == (12.0, 8.0, 3.0)
    assert v["origem"] == pytest.approx((1.0, 2.0, 1.2))
    assert {k: x for k, x in v["pset"].items() if k != "id"} == {"TargetView": "PLAN_VIEW", "Scale": "1/50", "HumanScale": "1:50"}
    assert v["doc"].Scope == "DRAWING" and v["doc"].Name == "Planta Térreo"
    assert len(v["grupos"]) == 1 and ligados(f, a, v["grupos"][0])
    pais = [g for g in f.by_type("IfcGroup") if g.ObjectType == "DRAWINGS" and g.Name == "DRAWINGS"]
    assert len(pais) == 1 and ligados(f, v["grupos"][0], pais[0])
    c = V.criar_vista(f, "Corte AA", "CORTE")
    assert A.vista_ifc(f, c)["pset"]["TargetView"] == "SECTION_VIEW" and A.vista_ifc(f, c)["pset"]["HumanScale"] == "1:100"
    assert len([g for g in f.by_type("IfcGroup") if g.ObjectType == "DRAWINGS"]) == 1, "o grupo pai é um só"


@AINDA_NAO
def test_ler_e_listar_vistas(f):
    import openbim_app.vistas_ifc as V
    g1 = V.criar_vista(f, "Planta", "PLANTA", escala="1:50", origem=(1.0, 2.0, 1.2), tamanho=(12.0, 8.0, 3.0))
    g2 = V.criar_vista(f, "Corte", "CORTE")
    d = V.ler_vista(f, g1)
    assert (d["gid"], d["nome"], d["tipo"], d["escala"]) == (g1, "Planta", "PLANTA", "1:50")
    assert d["location"] == A.vista_ifc(f, g1)["location"] and tuple(d["tamanho"]) == (12.0, 8.0, 3.0) and tuple(d["origem"]) == pytest.approx((1.0, 2.0, 1.2))
    assert V.ler_vista(f, g2)["tipo"] == "CORTE"
    assert sorted(x["gid"] for x in V.listar_vistas(f)) == sorted([g1, g2])
    with pytest.raises(V.VistaInexistente):
        V.ler_vista(f, "naoexiste")


@AINDA_NAO
def test_location_relativo_e_unico(f):
    import openbim_app.vistas_ifc as V
    gs = [V.criar_vista(f, "Planta", "PLANTA") for _ in range(3)] + [V.criar_vista(f, "Planta/2 \\ x", "CORTE")]
    locs = [A.vista_ifc(f, g)["location"] for g in gs]
    assert len(set(locs)) == 4
    for loc in locs:
        assert isinstance(loc, str) and loc and "\\" not in loc and not loc.startswith("/") and ":" not in loc and ".." not in loc.split("/")
    assert [V.ler_vista(f, g)["nome"] for g in gs[:3]] == ["Planta"] * 3 and len({A.vista_ifc(f, g)["doc"].Name for g in gs[:3]}) == 1


@AINDA_NAO
def test_prancha_formato_no_ifc(f):
    import openbim_app.vistas_ifc as V
    g1, g2 = V.criar_vista(f, "P1", "PLANTA"), V.criar_vista(f, "C1", "CORTE")
    assert V.criar_prancha(f, "A-01", "Plantas e cortes") == "A-01"
    V.colocar_vista(f, "A-01", g2)
    V.colocar_vista(f, "A-01", g1)
    d, por = A.prancha_ifc(f, "A-01")
    assert d.Scope == "SHEET" and d.Name == "Plantas e cortes"
    assert {k: len(x) for k, x in por.items()} == {"LAYOUT": 1, "TITLEBLOCK": 1, "DRAWING": 2}
    assert all(isinstance(r.Location, str) and r.Location for k in ("LAYOUT", "TITLEBLOCK") for r in por[k])
    desenhos = sorted(por["DRAWING"], key=lambda r: int(A.ordem(r)))
    assert [str(A.ordem(r)) for r in desenhos] == ["1", "2"]
    assert [r.Location for r in desenhos] == [A.vista_ifc(f, g2)["location"], A.vista_ifc(f, g1)["location"]]
    assert all(A.doc_da_ref(r) == d for rs in por.values() for r in rs)
    assert V.ler_prancha(f, "A-01") == {"numero": "A-01", "titulo": "Plantas e cortes", "vistas": [g2, g1], "ambigua": False}
    with pytest.raises(ValueError):
        V.colocar_vista(f, "A-01", g1)
    with pytest.raises(V.VistaInexistente):
        V.colocar_vista(f, "A-01", "naoexiste")
    with pytest.raises(V.PranchaInexistente):
        V.ler_prancha(f, "Z-99")


@AINDA_NAO
def test_chave_da_prancha_unica_e_exata(f):
    import openbim_app.vistas_ifc as V
    V.criar_vista(f, "P", "PLANTA")
    V.criar_prancha(f, "A-01", "Uma")
    antes = R.foto(f)
    for ruim, exc in (("A-01", V.IdentificacaoRepetida), ("", V.IdentificacaoInvalida), ("   ", V.IdentificacaoInvalida),
                      (" A-01", V.IdentificacaoInvalida), ("A-02 ", V.IdentificacaoInvalida)):
        with pytest.raises(exc):
            V.criar_prancha(f, ruim, "Outra")
    assert issubclass(V.IdentificacaoRepetida, ValueError) and issubclass(V.IdentificacaoInvalida, ValueError)
    with pytest.raises(ValueError):
        V.criar_vista(f, "F", "FACHADA")
    assert R.diferencas(antes, R.foto(f)) == [], "recusa não deixa entidade solta"
    for n in ("a-01", "A 1.2/B", "1"):  # maiúscula conta; ponto, barra e espaço no meio valem
        assert V.criar_prancha(f, n, "x") == n and V.ler_prancha(f, n)["titulo"] == "x"
    assert sorted(p["numero"] for p in V.listar_pranchas(f)) == sorted(["A-01", "a-01", "A 1.2/B", "1"])


@AINDA_NAO
def test_apagar_vista_e_apagar_prancha_limpam_tudo(f):
    import openbim_app.vistas_ifc as V
    v0 = V.criar_vista(f, "V0", "PLANTA")
    V.criar_prancha(f, "P0", "zero")
    V.colocar_vista(f, "P0", v0)
    base = R.foto(f)
    v1 = V.criar_vista(f, "V1", "CORTE")
    V.colocar_vista(f, "P0", v1)
    V.criar_prancha(f, "P1", "um")
    V.colocar_vista(f, "P1", v1)
    V.colocar_vista(f, "P1", v0)
    V.apagar_vista(f, v1)
    assert V.ler_prancha(f, "P0")["vistas"] == [v0] and V.ler_prancha(f, "P1")["vistas"] == [v0]
    assert [x["gid"] for x in V.listar_vistas(f)] == [v0]
    V.apagar_prancha(f, "P1")
    assert R.diferencas(base, R.foto(f)) == [], "criar+apagar volta ao conteúdo de antes (nada órfão)"
    assert V.ler_vista(f, v0)["nome"] == "V0"
    V.apagar_prancha(f, "P0")
    assert [p["numero"] for p in V.listar_pranchas(f)] == [] and [x["gid"] for x in V.listar_vistas(f)] == [v0]
    with pytest.raises(V.VistaInexistente):
        V.apagar_vista(f, v1)
    with pytest.raises(V.PranchaInexistente):
        V.apagar_prancha(f, "P1")


@AINDA_NAO
def test_reabrir_mantem_globalid(f, tmp_path):
    import ifcopenshell
    import openbim_app.vistas_ifc as V
    g1, g2 = V.criar_vista(f, "P", "PLANTA", escala="1:75"), V.criar_vista(f, "C", "CORTE")
    V.criar_prancha(f, "A-01", "t")
    V.colocar_vista(f, "A-01", g2)
    V.colocar_vista(f, "A-01", g1)
    p = tmp_path / "Casa.ifc"
    f.write(str(p))
    g = ifcopenshell.open(str(p))
    assert g.schema == f.schema and A.vista_ifc(g, g1)["ann"].GlobalId == g1
    assert V.ler_vista(g, g1) == V.ler_vista(f, g1) and V.ler_vista(g, g2) == V.ler_vista(f, g2)
    assert V.ler_prancha(g, "A-01") == V.ler_prancha(f, "A-01") and V.ler_prancha(g, "A-01")["vistas"] == [g2, g1]


# ---------- IFC de outro programa e validador ----------
@AINDA_NAO
def test_ifc_de_outro_programa_sem_pset_nem_formato_nosso(f):
    import openbim_app.vistas_ifc as V
    ext = A.annotation(f, "Externa")
    A.annotation(f, "Legenda", tipo="TEXT")
    A.folha(f, "X-1", "Folha externa")
    assert not [p for p in f.by_type("IfcPropertySet") if p.Name == "OBIM_Projeto"]
    vs = V.listar_vistas(f)
    assert [x["gid"] for x in vs] == [ext.GlobalId] and vs[0]["nome"] == "Externa"
    assert vs[0]["tipo"] is None and vs[0]["escala"] is None and vs[0]["location"] is None
    assert V.ler_vista(f, ext.GlobalId)["nome"] == "Externa"
    assert V.ler_prancha(f, "X-1") == {"numero": "X-1", "titulo": "Folha externa", "vistas": [], "ambigua": False}
    antes = R.foto(f)
    n = V.criar_vista(f, "Nossa", "PLANTA")
    assert sorted(x["gid"] for x in V.listar_vistas(f)) == sorted([ext.GlobalId, n])
    V.apagar_vista(f, n)
    assert [x["gid"] for x in V.listar_vistas(f)] == [ext.GlobalId]
    assert f.by_guid(ext.GlobalId).Name == "Externa" and len(A.anotacoes_vista(f)) == 1


@AINDA_NAO
def test_pranchas_com_numero_repetido_sao_ambiguas(f):
    import openbim_app.vistas_ifc as V
    A.folha(f, "A-01", "um")
    A.folha(f, "A-01", "dois")
    ps = V.listar_pranchas(f)
    assert len(ps) == 2 and all(p["ambigua"] and p["numero"] == "A-01" for p in ps)
    antes = R.foto(f)
    for fn in (lambda: V.ler_prancha(f, "A-01"), lambda: V.apagar_prancha(f, "A-01")):
        with pytest.raises(V.PranchaAmbigua):
            fn()
    with pytest.raises(V.IdentificacaoRepetida):
        V.criar_prancha(f, "A-01", "tres")
    assert issubclass(V.PranchaAmbigua, ValueError) and R.diferencas(antes, R.foto(f)) == []


@AINDA_NAO
def test_arquivo_gravado_passa_no_validador(f):
    import ifcopenshell.validate as VAL
    import openbim_app.vistas_ifc as V
    for i in range(3):
        V.criar_vista(f, f"V{i}", "PLANTA" if i % 2 else "CORTE", escala="1:50")
    gs = [x["gid"] for x in V.listar_vistas(f)]
    V.criar_prancha(f, "A-01", "x")
    V.criar_prancha(f, "A-02", "y")
    for g in gs:
        V.colocar_vista(f, "A-01", g)
    V.colocar_vista(f, "A-02", gs[0])
    V.apagar_vista(f, gs[1])
    log = VAL.json_logger()
    VAL.validate(f, log, express_rules=True)
    assert log.statements == [], log.statements[:3]
