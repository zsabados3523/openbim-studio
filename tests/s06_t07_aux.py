# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T07a (seleção por pavimento e faixa). Não é de `app/`; implementador não edita.
Modelos pequenos sintéticos, sem arquivo grande: caixas extrudadas com colocação ABSOLUTA (sem PlacementRelTo), cantos em múltiplos de 1/64 m
(sem ruído de ponto flutuante nas bordas), deslocáveis para longe da origem (modelo georreferenciado) e com cota de base arbitrária."""
import ifcopenshell.guid
import s06_t04_aux as A

ESQUEMAS = ("IFC2X3", "IFC4")
MOVEL = {"IFC2X3": "IfcFurnishingElement", "IFC4": "IfcFurniture"}  # classe concreta do móvel por esquema
GEO = (324550.0, 7405473.0)  # X/Y do modelo de 303 MB da T01h
# (esquema, deslocamento XY, cota do térreo): cobre 2X3 e 4, perto e longe da origem, pavimento em cota 0, positiva e negativa
MODELOS = [("IFC2X3", (0.0, 0.0), 0.0), ("IFC4", GEO, 0.0), ("IFC4", (0.0, 0.0), 12.5), ("IFC2X3", GEO, -1.5)]


def kw(f):
    return {"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}


def _pt(f, *c):
    return f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in c))


def elemento(f, cls, nome, **atrib):
    return f.create_entity(cls, GlobalId=ifcopenshell.guid.new(), Name=nome, **kw(f), **atrib)


def caixa(f, cls, nome, x, y, z, dx, dy, dz, **atrib):
    """Elemento com geometria: caixa com o canto mínimo em (x, y, z) do mundo e lados dx, dy, dz."""
    eixo = f.create_entity("IfcAxis2Placement3D", Location=_pt(f, 0, 0, 0))
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=dx, YDim=dy, Position=f.create_entity(
        "IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(dx / 2, dy / 2))))
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Position=eixo, Depth=dz,
                             ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=f.by_type("IfcGeometricRepresentationContext")[0],
                            RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    e = elemento(f, cls, nome, **atrib)
    e.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity(
        "IfcAxis2Placement3D", Location=_pt(f, x, y, z)))
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    return e


def conter(f, pav, *elementos):
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(), RelatingStructure=pav,
                    RelatedElements=list(elementos), **kw(f))


def agregar(f, pai, *filhos):
    f.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=pai, RelatedObjects=list(filhos), **kw(f))


def estrutura(esq, off=(0.0, 0.0), base=0.0, n_pav=2):
    """Projeto > terreno > edifício > `n_pav` pavimentos (Elevation = base + 3 i, colocação no mundo). Devolve (arquivo, [pavimentos])."""
    f = A.novo_arquivo(esq)
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = None  # o arquivo-base vem em milímetros; aqui o metro, para os números do caso serem metros
    site, edif = elemento(f, "IfcSite", "Terreno"), elemento(f, "IfcBuilding", "Edificio")
    pavs = []
    for i in range(n_pav):
        p = elemento(f, "IfcBuildingStorey", f"Pav{i}", Elevation=base + 3.0 * i)
        p.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity(
            "IfcAxis2Placement3D", Location=_pt(f, off[0], off[1], base + 3.0 * i)))
        pavs.append(p)
    agregar(f, f.by_type("IfcProject")[0], site)
    agregar(f, site, edif)
    agregar(f, edif, *pavs)
    return f, pavs


def conteudo(f, pav, s, off, z0):
    """Conteúdo do pavimento `s`: parede P, laje L, móvel M, janela W (contidos); abertura O na parede e porta D que a preenche (D NÃO é contida);
    conjunto A > (peça C1, subconjunto B > peça C2) (só A é contido; peças por IfcRelAggregates); X = parede sem geometria. Nomes terminam em `s`."""
    ox, oy = off
    p = caixa(f, "IfcWall", f"P{s}", ox, oy, z0, 5.0, 0.25, 3.0)
    lj = caixa(f, "IfcSlab", f"L{s}", ox, oy, z0 + 2.75, 5.0, 5.0, 0.25)
    m = caixa(f, MOVEL[f.schema], f"M{s}", ox + 1.0, oy + 2.0, z0, 1.0, 0.5, 0.5)
    w = caixa(f, "IfcWindow", f"W{s}", ox + 3.0, oy, z0 + 1.0, 1.0, 0.25, 1.0)
    o = caixa(f, "IfcOpeningElement", f"O{s}", ox + 1.0, oy, z0, 1.0, 0.25, 2.0)
    d = caixa(f, "IfcDoor", f"D{s}", ox + 1.0, oy, z0, 1.0, 0.25, 2.0)
    x = elemento(f, "IfcWall", f"X{s}")
    a, b = elemento(f, "IfcElementAssembly", f"A{s}"), elemento(f, "IfcElementAssembly", f"B{s}")
    c1 = caixa(f, "IfcMember", f"C1{s}", ox + 4.0, oy + 4.0, z0, 0.25, 0.25, 2.0)
    c2 = caixa(f, "IfcMember", f"C2{s}", ox + 4.5, oy + 4.0, z0, 0.25, 0.25, 2.0)
    conter(f, pav, p, lj, m, w, x, a)
    f.create_entity("IfcRelVoidsElement", GlobalId=ifcopenshell.guid.new(), RelatingBuildingElement=p, RelatedOpeningElement=o, **kw(f))
    f.create_entity("IfcRelFillsElement", GlobalId=ifcopenshell.guid.new(), RelatingOpeningElement=o, RelatedBuildingElement=d, **kw(f))
    agregar(f, a, c1, b)
    agregar(f, b, c2)
    return {f"{n}{s}" for n in ("P", "L", "M", "W", "O", "D", "C1", "C2")}  # nomes com geometria


def casa(esq, off=(0.0, 0.0), base=0.0):
    """2 pavimentos com `conteudo`. Devolve (arquivo, pavimentos, [nomes esperados por pavimento]); sem geometria por pavimento: X, A, B (3)."""
    f, pavs = estrutura(esq, off, base)
    return f, pavs, [conteudo(f, p, i, off, base + 3.0 * i) for i, p in enumerate(pavs)]


def faixa(esq, off=(0.0, 0.0), base=0.0):
    """Corte: volume X [ox, ox+10], Y [oy+2, oy+3], Z [base, base+6]. Elementos 1 m em X, cantos exatos. Devolve (f, pavs, dentro, fora)."""
    f, pavs = estrutura(esq, off, base)
    ox, oy = off
    z = (base + 0.5, base + 3.5)
    casos = [  # nome, pavimento, y, dy, x, z
        ("in", 0, 2.25, 0.25, 1.0, z[0]), ("lo", 1, 1.5, 1.0, 1.0, z[1]), ("hi", 0, 2.5, 1.0, 1.0, z[0]), ("amplo", 1, 1.0, 3.0, 1.0, z[1]),
        ("toque_hi", 0, 3.0, 0.5, 1.0, z[0]), ("toque_lo", 1, 1.5, 0.5, 1.0, z[1]),
        ("fora_lo", 0, 1.0, 0.984375, 1.0, z[0]), ("fora_hi", 1, 3.015625, 0.5, 1.0, z[1]), ("fora_x", 0, 2.25, 0.25, 20.0, z[0]),
        ("fora_z", 1, 2.25, 0.25, 1.0, base + 7.0)]
    for nome, i, y, dy, x, zz in casos:
        conter(f, pavs[i], caixa(f, "IfcBuildingElementProxy", nome, ox + x, oy + y, zz, 1.0, dy, 0.5))
    conter(f, pavs[0], caixa(f, MOVEL[esq], "movel_in", ox + 1.0, oy + 2.25, z[0], 1.0, 0.25, 0.5))
    nomes = [c[0] for c in casos]
    return f, pavs, {n for n in nomes if not n.startswith("fora")} | {"movel_in"}, {n for n in nomes if n.startswith("fora")}


def vista(f, tipo, pav=None, origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 3.0), nome="V"):
    import openbim_app.vistas_ifc as V
    gid = V.criar_vista(f, nome, tipo, origem=origem, tamanho=tamanho)
    if pav is not None:
        conter(f, pav, f.by_guid(gid))
    return gid


def nomes(f, sel):
    return {f.by_id(i).Name for i in sel.ids}


def em_milimetros(f):
    """Troca a unidade de comprimento do arquivo para milímetro SEM mexer nos números: o modelo inteiro (elementos e volume da vista) encolhe 1000 vezes
    no mundo; o conjunto selecionado tem de ser o mesmo, e `Selecao.faixa` sai em metros (valor do arquivo x 0,001)."""
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = "MILLI"
