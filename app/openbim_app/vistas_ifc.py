# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vista e prancha dentro do IFC (ADR-003 §3, §5 e §8). Sem Qt, sem o `obimcore`.

Vista = `IfcAnnotation` (ObjectType "DRAWING") com volume CSG, pset `EPset_Drawing`, grupo e documento com uma
`IfcDocumentReference`; prancha = `IfcDocumentInformation` (Scope "SHEET") com referências LAYOUT, TITLEBLOCK e
DRAWING. Escrita só dentro de `Historico.transacao` (o `transacao` recusa fora); leitura aceita o arquivo cru.
IFC2X3 reaproveita o primeiro `IfcOwnerHistory` e usa `DocumentId`/`ItemReference`; IFC4/4X3 usam
`Identification`/`Description`. Funções não decidem esquema por conta própria: leem o do arquivo."""
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.util.element as UE
import ifcopenshell.util.placement as UP


class VistaInexistente(KeyError):
    """Não existe `IfcAnnotation` "DRAWING" com esse GlobalId."""


class PranchaInexistente(KeyError):
    """Não existe documento "SHEET" com esse número."""


class IdentificacaoRepetida(ValueError):
    """Já existe prancha com esse número (ou duas, o que também é repetição)."""


class IdentificacaoInvalida(ValueError):
    """Número de prancha vazio ou com espaço nas pontas."""


class PranchaAmbigua(ValueError):
    """Duas ou mais pranchas com o mesmo número; o módulo não escolhe."""


_TIPO = {"PLANTA": "PLAN_VIEW", "CORTE": "SECTION_VIEW"}
_VIEW = {v: k for k, v in _TIPO.items()}


def _e2x3(ifc):
    return ifc.schema == "IFC2X3"


def _kw(ifc):  # IFC2X3 exige OwnerHistory nos IfcRoot; reaproveita o primeiro
    if not _e2x3(ifc):
        return {}
    oh = ifc.by_type("IfcOwnerHistory")
    if not oh:
        raise ValueError("IFC2X3 sem IfcOwnerHistory: não dá para gravar vista ou prancha")
    return {"OwnerHistory": oh[0]}


def _pranchas(ifc):
    return [d for d in ifc.by_type("IfcDocumentInformation") if d.Scope == "SHEET"]


def _numero(ifc, d):
    return d.DocumentId if _e2x3(ifc) else d.Identification


def _refs(ifc, d):
    return list(d.DocumentReferences or ()) if _e2x3(ifc) else list(d.HasDocumentReferences or ())


def _doc_da_ref(ifc, r):
    if _e2x3(ifc):
        return r.ReferenceToDocument[0] if r.ReferenceToDocument else None
    return r.ReferencedDocument


def _etiqueta(r):
    return (r.ItemReference or "").split("/")[0] if not hasattr(r, "Description") else r.Description


def _ordem(r):
    return (r.ItemReference or "/").split("/")[-1] if not hasattr(r, "Description") else r.Identification


def _ordem_num(r):  # número da ordem, ou None quando outro programa gravou texto
    o = _ordem(r)
    return int(o) if o is not None and str(o).isdigit() else None


def _chave_ordem(r):  # numéricas pelo número, depois as não numéricas (na ordem do arquivo)
    n = _ordem_num(r)
    return (0, n) if n is not None else (1, 0)


def _contexto(ifc):
    ctx = [c for c in ifc.by_type("IfcGeometricRepresentationContext") if c.ContextType == "Model"]
    if not ctx:
        ctx = [ifcopenshell.api.run("context.add_context", ifc, context_type="Model")]
    return ctx[0]


def _caminho(nome):
    partes = []
    for p in str(nome).replace("\\", "/").replace(":", "").split("/"):
        p = p.strip()
        if p and p not in (".", ".."):
            partes.append(p)
    return "/".join(partes or ["vista"]) + ".svg"


def _location_livre(ifc, nome):
    usados = {r.Location for r in ifc.by_type("IfcDocumentReference") if r.Location}
    base = _caminho(nome)
    if base not in usados:
        return base
    raiz = base[:-4]
    n = 2
    while f"{raiz}-{n}.svg" in usados:
        n += 1
    return f"{raiz}-{n}.svg"


def _vista_dict(ifc, a):
    ps = UE.get_psets(a).get("EPset_Drawing") or {}
    rel = next((r for r in a.HasAssociations if r.is_a("IfcRelAssociatesDocument")), None)
    ref = rel.RelatingDocument if rel is not None and rel.RelatingDocument.is_a("IfcDocumentReference") else None
    origem = tamanho = None
    if a.ObjectPlacement is not None:
        origem = tuple(float(x) for x in UP.get_local_placement(a.ObjectPlacement)[:3, 3])
    bloco = None
    if a.Representation and a.Representation.Representations:
        itens = a.Representation.Representations[0].Items
        if itens and itens[0].is_a("IfcCsgSolid"):
            bloco = itens[0].TreeRootExpression
    if bloco is not None and bloco.is_a("IfcBlock"):
        tamanho = (bloco.XLength, bloco.YLength, bloco.ZLength)
    escala = ps.get("HumanScale") or ((ps.get("Scale") or "").replace("/", ":") or None)
    return {"gid": a.GlobalId, "nome": a.Name, "tipo": _VIEW.get(ps.get("TargetView")), "escala": escala,
            "location": ref.Location if ref is not None else None, "origem": origem, "tamanho": tamanho}


def _anotacao(ifc, gid):
    try:
        a = ifc.by_guid(gid)
    except RuntimeError:
        a = None
    if a is None or not a.is_a("IfcAnnotation") or a.ObjectType != "DRAWING":
        raise VistaInexistente(gid)
    return a


def criar_vista(ifc, nome, tipo, escala="1:100", origem=(0, 0, 0), tamanho=(10.0, 10.0, 3.0)):
    if tipo not in _TIPO:
        raise ValueError(f"tipo de vista inválido: {tipo!r}")
    try:
        medidas = tuple(float(x) for x in tamanho)
    except (TypeError, ValueError):
        raise ValueError(f"tamanho inválido: {tamanho!r}") from None
    if len(medidas) != 3 or any(x <= 0 for x in medidas):
        raise ValueError(f"tamanho inválido: {tamanho!r}")
    escala = str(escala).replace("/", ":")
    location, kw = _location_livre(ifc, nome), _kw(ifc)
    gid = ifcopenshell.guid.new()
    a = ifc.create_entity("IfcAnnotation", GlobalId=gid, Name=nome, ObjectType="DRAWING", **kw)
    if ifc.schema.startswith("IFC4X3"):
        a.PredefinedType = "USERDEFINED"
    eixo = ifc.create_entity("IfcAxis2Placement3D", Location=ifc.create_entity(
        "IfcCartesianPoint", Coordinates=tuple(float(x) for x in origem)))
    a.ObjectPlacement = ifc.create_entity("IfcLocalPlacement", RelativePlacement=eixo)
    bloco = ifc.create_entity("IfcBlock", Position=ifc.create_entity(
        "IfcAxis2Placement3D", Location=ifc.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
        XLength=medidas[0], YLength=medidas[1], ZLength=medidas[2])
    forma = ifc.create_entity("IfcShapeRepresentation", ContextOfItems=_contexto(ifc), RepresentationIdentifier="Body",
                              RepresentationType="SolidModel", Items=[ifc.create_entity("IfcCsgSolid", TreeRootExpression=bloco)])
    a.Representation = ifc.create_entity("IfcProductDefinitionShape", Representations=[forma])
    props = [ifc.create_entity("IfcPropertySingleValue", Name=k, NominalValue=ifc.create_entity("IfcLabel", v))
             for k, v in (("TargetView", _TIPO[tipo]), ("Scale", escala.replace(":", "/")), ("HumanScale", escala))]
    ps = ifc.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="EPset_Drawing",
                           HasProperties=props, **kw)
    ifc.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(),
                      RelatedObjects=[a], RelatingPropertyDefinition=ps, **kw)
    doc = ifc.create_entity("IfcDocumentInformation", Name=nome, Scope="DRAWING",
                            **({"DocumentId": location} if _e2x3(ifc) else {"Identification": location}))
    if _e2x3(ifc):
        ref = ifc.create_entity("IfcDocumentReference", Location=location)
        doc.DocumentReferences = [ref]
    else:
        ref = ifc.create_entity("IfcDocumentReference", Location=location, ReferencedDocument=doc)
    ifc.create_entity("IfcRelAssociatesDocument", GlobalId=ifcopenshell.guid.new(),
                      RelatedObjects=[a], RelatingDocument=ref, **kw)
    grupo = ifc.create_entity("IfcGroup", GlobalId=ifcopenshell.guid.new(), Name=nome, ObjectType="DRAWING", **kw)
    ifc.create_entity("IfcRelAssignsToGroup", GlobalId=ifcopenshell.guid.new(),
                      RelatedObjects=[a], RelatingGroup=grupo, **kw)
    pai = next((g for g in ifc.by_type("IfcGroup") if g.ObjectType == "DRAWINGS" and g.Name == "DRAWINGS"), None)
    if pai is None:
        pai = ifc.create_entity("IfcGroup", GlobalId=ifcopenshell.guid.new(), Name="DRAWINGS", ObjectType="DRAWINGS", **kw)
        ifc.create_entity("IfcRelAssignsToGroup", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[grupo], RelatingGroup=pai, **kw)
    else:
        rel = next((r for r in pai.IsGroupedBy if r.is_a("IfcRelAssignsToGroup")), None)
        if rel is None:
            ifc.create_entity("IfcRelAssignsToGroup", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[grupo], RelatingGroup=pai, **kw)
        else:
            rel.RelatedObjects = tuple(rel.RelatedObjects) + (grupo,)
    return gid


def ler_vista(ifc, gid):
    return _vista_dict(ifc, _anotacao(ifc, gid))


def listar_vistas(ifc):
    return [_vista_dict(ifc, a) for a in ifc.by_type("IfcAnnotation") if a.ObjectType == "DRAWING"]


def _mapa_locais(ifc):
    mapa = {}
    for rel in ifc.by_type("IfcRelAssociatesDocument"):
        ref = rel.RelatingDocument
        if not ref.is_a("IfcDocumentReference") or not ref.Location:
            continue
        for o in rel.RelatedObjects:
            if o.is_a("IfcAnnotation") and o.ObjectType == "DRAWING":
                mapa[ref.Location] = o.GlobalId
    return mapa


def _vistas_da(ifc, d, mapa):
    refs = [r for r in _refs(ifc, d) if _etiqueta(r) == "DRAWING"]
    refs.sort(key=_chave_ordem)
    return [mapa[r.Location] for r in refs if r.Location in mapa]


def _prancha_dict(ifc, d, ambigua, mapa):
    return {"numero": _numero(ifc, d), "titulo": d.Name, "vistas": _vistas_da(ifc, d, mapa), "ambigua": ambigua}


def _uma_prancha(ifc, numero):
    ds = [d for d in _pranchas(ifc) if _numero(ifc, d) == numero]
    if not ds:
        raise PranchaInexistente(numero)
    if len(ds) > 1:
        raise PranchaAmbigua(numero)
    return ds[0]


def listar_pranchas(ifc):
    mapa, contagem = _mapa_locais(ifc), {}
    for d in _pranchas(ifc):
        contagem[_numero(ifc, d)] = contagem.get(_numero(ifc, d), 0) + 1
    return [_prancha_dict(ifc, d, contagem[_numero(ifc, d)] > 1, mapa) for d in _pranchas(ifc)]


def _nova_ref(ifc, d, etiqueta, location, ordem=None):
    if _e2x3(ifc):
        item = etiqueta if ordem is None else f"{etiqueta}/{ordem}"
        return ifc.create_entity("IfcDocumentReference", Location=location, ItemReference=item)
    kw = {"Identification": ordem} if ordem is not None else {}
    return ifc.create_entity("IfcDocumentReference", Location=location, Description=etiqueta,
                             ReferencedDocument=d, **kw)


def criar_prancha(ifc, numero, titulo):
    if not isinstance(numero, str) or not numero or numero != numero.strip():
        raise IdentificacaoInvalida(numero)
    if any(_numero(ifc, d) == numero for d in _pranchas(ifc)):
        raise IdentificacaoRepetida(numero)
    kw = _kw(ifc)
    doc = ifc.create_entity("IfcDocumentInformation", Name=titulo, Scope="SHEET",
                            **({"DocumentId": numero} if _e2x3(ifc) else {"Identification": numero}))
    refs = [_nova_ref(ifc, doc, "LAYOUT", f"pranchas/{numero}/layout.svg"),
            _nova_ref(ifc, doc, "TITLEBLOCK", f"pranchas/{numero}/titleblock.svg")]
    if _e2x3(ifc):
        doc.DocumentReferences = refs
    return numero


def colocar_vista(ifc, numero, gid):
    d, v = _uma_prancha(ifc, numero), ler_vista(ifc, gid)
    if not v["location"]:
        raise ValueError("vista sem documento (Location); não dá para colocar na prancha")
    refs = [r for r in _refs(ifc, d) if _etiqueta(r) == "DRAWING"]
    if any(r.Location == v["location"] for r in refs):
        raise ValueError("a vista já está nesta prancha")
    ordem = max((n for n in (_ordem_num(r) for r in refs) if n is not None), default=0) + 1
    ref = _nova_ref(ifc, d, "DRAWING", v["location"], str(ordem))
    if _e2x3(ifc):
        d.DocumentReferences = tuple(d.DocumentReferences) + (ref,)
    return numero


def ler_prancha(ifc, numero):
    return _prancha_dict(ifc, _uma_prancha(ifc, numero), False, _mapa_locais(ifc))


def apagar_prancha(ifc, numero):
    d = _uma_prancha(ifc, numero)
    for r in _refs(ifc, d):
        ifc.remove(r)
    ifc.remove(d)


def _tirar(ifc, rel, obj):  # relação compartilhada perde só o objeto; vazia, sai
    resto = tuple(o for o in rel.RelatedObjects if o != obj)
    if resto:
        rel.RelatedObjects = resto
    else:
        ifc.remove(rel)


def _purgar_grupo(ifc, rel):  # grupo da vista + relação com o pai; pai vazio sai junto
    grupo = rel.RelatingGroup
    ifc.remove(rel)
    for pr in [r for r in ifc.get_inverse(grupo) if r.is_a("IfcRelAssignsToGroup")]:
        resto = tuple(o for o in pr.RelatedObjects if o != grupo)
        if resto:
            pr.RelatedObjects = resto
            continue
        pai = pr.RelatingGroup
        ifc.remove(pr)
        if pai is not None and not any(r.is_a("IfcRelAssignsToGroup") for r in ifc.get_inverse(pai)):
            ifc.remove(pai)
    ifc.remove(grupo)


def apagar_vista(ifc, gid):
    a = _anotacao(ifc, gid)
    location = _vista_dict(ifc, a)["location"]
    if location:
        for d in _pranchas(ifc):
            for r in _refs(ifc, d):
                if _etiqueta(r) == "DRAWING" and r.Location == location:
                    ifc.remove(r)
    for rel in list(ifc.get_inverse(a)):
        if rel.is_a("IfcRelAssignsToGroup"):
            grupo = rel.RelatingGroup
            nossa = grupo.ObjectType == "DRAWING" and grupo.Name == a.Name and len(rel.RelatedObjects) == 1
            _purgar_grupo(ifc, rel) if nossa else _tirar(ifc, rel, a)
        elif rel.is_a("IfcRelDefinesByProperties"):
            if len(rel.RelatedObjects) > 1:
                _tirar(ifc, rel, a)
            else:
                ps = rel.RelatingPropertyDefinition
                ifc.remove(rel)
                if ps is not None:
                    UE.remove_deep2(ifc, ps)
        elif rel.is_a("IfcRelAssociatesDocument"):
            if len(rel.RelatedObjects) > 1:
                _tirar(ifc, rel, a)
            else:
                ref = rel.RelatingDocument
                ifc.remove(rel)
                if ref.is_a("IfcDocumentReference"):
                    doc = _doc_da_ref(ifc, ref)
                    ifc.remove(ref)
                    if doc is not None:
                        ifc.remove(doc)
    UE.remove_deep2(ifc, a)
