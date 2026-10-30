# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T04 (vista e prancha dentro do IFC). Não é de `app/`; implementador não edita.
`novo_arquivo(esquema)` (IFC sem pset OBIM_Projeto), `annotation`/`folha` (entidades "de outro programa") e leitores crus das entidades IFC
(`vista_ifc`, `prancha_ifc`), usados pelos casos para conferir o formato do ADR-003 §3 SEM passar pelo módulo novo."""
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.util.element as UE
import ifcopenshell.util.placement as UP

ESQUEMAS = ("IFC2X3", "IFC4", "IFC4X3")
api = ifcopenshell.api.run


def novo_arquivo(esquema):
    """Projeto mínimo. Em IFC2X3 o arquivo já traz UM IfcOwnerHistory (obrigatório nessa versão); o módulo novo reaproveita o primeiro."""
    f = ifcopenshell.file(schema=esquema)
    kw = {}
    if esquema == "IFC2X3":
        pessoa = f.create_entity("IfcPerson", Id="u", FamilyName="Teste")
        org = f.create_entity("IfcOrganization", Name="Org")
        app_ = f.create_entity("IfcApplication", ApplicationDeveloper=org, Version="1", ApplicationFullName="Teste", ApplicationIdentifier="t")
        dono = f.create_entity("IfcOwnerHistory", OwningUser=f.create_entity("IfcPersonAndOrganization", ThePerson=pessoa, TheOrganization=org),
                               OwningApplication=app_, ChangeAction="ADDED", CreationDate=0)
        kw["OwnerHistory"] = dono
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Casa", **kw)
    api("unit.assign_unit", f)
    api("context.add_context", f, context_type="Model")
    return f


def annotation(f, nome, tipo="DRAWING"):  # IfcAnnotation "de outro programa" (sem nada do nosso formato)
    kw = {"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}
    return f.create_entity("IfcAnnotation", GlobalId=ifcopenshell.guid.new(), Name=nome, ObjectType=tipo, **kw)


def folha(f, numero, nome):  # IfcDocumentInformation SHEET "de outro programa", sem referências
    d = api("document.add_information", f)
    api("document.edit_information", f, information=d, attributes={("DocumentId" if f.schema == "IFC2X3" else "Identification"): numero,
                                                                 "Name": nome, "Scope": "SHEET"})
    return d


def e2x3(f):
    return f.schema == "IFC2X3"


# ---- leitores crus (formato do ADR-003 §3; só atributos que o ADR fixa) ----
def _refs_assoc(f, ann):  # IfcDocumentReference ligada à anotação por IfcRelAssociatesDocument
    return [r.RelatingDocument for r in f.by_type("IfcRelAssociatesDocument")
            if ann in r.RelatedObjects and r.RelatingDocument.is_a("IfcDocumentReference")]


def doc_da_ref(ref):
    return ref.ReferencedDocument if "ReferencedDocument" in ref.get_info() else ref.ReferenceToDocument[0]


def numero_de(d):
    return d.DocumentId if "DocumentId" in d.get_info() else d.Identification


def refs_de(d):  # referências do documento (2X3: lista no próprio; 4+: inverso)
    return list(d.DocumentReferences or ()) if "DocumentReferences" in d.get_info() else list(d.HasDocumentReferences or ())


def etiqueta(ref):  # "LAYOUT", "TITLEBLOCK", "DRAWING" (ADR-003 §3.2 ajustado: IFC4+ Description; IFC2X3 prefixo de ItemReference, [P], ver contrato)
    return (ref.ItemReference or "").split("/")[0] if "Description" not in ref.get_info() else ref.Description


def ordem(ref):  # IFC4+: Identification; IFC2X3: sufixo de ItemReference ("DRAWING/2")
    return (ref.ItemReference or "/").split("/")[-1] if "Description" not in ref.get_info() else ref.Identification


def anotacoes_vista(f):
    return [a for a in f.by_type("IfcAnnotation") if a.ObjectType == "DRAWING"]


def vista_ifc(f, gid):
    """Lê cru: dict com ann, nome, bloco (x,y,z), origem, pset, location, doc, grupo."""
    a = f.by_guid(gid)
    item = a.Representation.Representations[0].Items[0]
    refs = _refs_assoc(f, a)
    assert len(refs) == 1, "a vista tem uma (e só uma) IfcDocumentReference associada"
    pos = UP.get_local_placement(a.ObjectPlacement)
    return {"ann": a, "nome": a.Name, "csg": item, "bloco": item.TreeRootExpression if item.is_a("IfcCsgSolid") else None,
            "origem": tuple(float(x) for x in pos[:3, 3]), "pset": UE.get_psets(a).get("EPset_Drawing"),
            "ref": refs[0], "location": refs[0].Location, "doc": doc_da_ref(refs[0]),
            "grupos": [g for g in f.by_type("IfcGroup") if g.ObjectType == "DRAWING" and g.Name == a.Name]}


def pranchas_ifc(f):
    return [d for d in f.by_type("IfcDocumentInformation") if d.Scope == "SHEET"]


def prancha_ifc(f, numero):
    ds = [d for d in pranchas_ifc(f) if numero_de(d) == numero]
    assert len(ds) == 1
    d = ds[0]
    refs = refs_de(d)
    por = {}
    for r in refs:
        por.setdefault(etiqueta(r), []).append(r)
    return d, por
