# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T07e0 (fronteira do processo auxiliar de desenho). Não é de `app/`; implementador não edita.
Modelo pequeno autossuficiente (não usa o auxiliar da T07a/T07b, que ainda não está no `main`): caixas extrudadas com colocação absoluta, cantos em
múltiplos de 1/64 m. `GEOMETRIA` entra no `sys.path` (o pacote `obim_geometria` mora em `geometria/`, fora de `app/`)."""
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
import s06_t04_aux as A

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))
GEO = (324550.0, 7405473.0)
# (esquema, deslocamento XY em metros, cota do térreo em metros, k = unidade: 1 metro, 1000 milímetro): georreferenciado, 2X3 em mm, cota negativa
MODELOS = [("IFC4", GEO, 0.0, 1.0), ("IFC2X3", (0.0, 0.0), 0.0, 1000.0), ("IFC4", (0.0, 0.0), -1.5, 1.0)]


def _pt(f, *c):
    return f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in c))


def _kw(f):
    return {"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}


def _el(f, cls, nome, **atrib):
    return f.create_entity(cls, GlobalId=ifcopenshell.guid.new(), Name=nome, **_kw(f), **atrib)


def caixa(f, cls, nome, x, y, z, dx, dy, dz, zero=False):
    """Elemento com geometria: caixa de canto mínimo (x, y, z) e lados dx, dy, dz (unidade do arquivo). `zero`: extrusão nula (geometria impossível)."""
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=dx, YDim=dy, Position=f.create_entity(
        "IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(dx / 2, dy / 2))))
    dire = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 0.0 if zero else 1.0))
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Position=f.create_entity("IfcAxis2Placement3D", Location=_pt(f, 0, 0, 0)),
                             Depth=dz, ExtrudedDirection=dire)
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=f.by_type("IfcGeometricRepresentationContext")[0],
                            RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    e = _el(f, cls, nome)
    e.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=_pt(f, x, y, z)))
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    return e


def _rel(f, cls, **atrib):
    return f.create_entity(cls, GlobalId=ifcopenshell.guid.new(), **atrib, **_kw(f))


def modelo(esq="IFC4", off=(0.0, 0.0), base=0.0, k=1.0):
    """Projeto > terreno > edifício > Pav0 (cota `base`) e Pav1 (+3 m). Pav0: parede P (5 x 0,25 x 3 em `off`), móvel M, peça `falha` (sem geometria possível);
    Pav1: parede Q. Vista PLANTA `vp` no Pav0 e vista CORTE `vc` (faixa que cobre P e M). Comprimentos do arquivo = metros x `k`. Devolve (f, d) com
    d = {nome: elemento} e d["vp"], d["vc"] = GlobalId das vistas."""
    import openbim_app.vistas_ifc as V
    f = A.novo_arquivo(esq)
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = "MILLI" if k == 1000.0 else None
    ox, oy = off
    site, edif = _el(f, "IfcSite", "Terreno"), _el(f, "IfcBuilding", "Edificio")
    pavs = []
    for i in range(2):
        p = _el(f, "IfcBuildingStorey", f"Pav{i}", Elevation=(base + 3.0 * i) * k)
        p.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity(
            "IfcAxis2Placement3D", Location=_pt(f, ox * k, oy * k, (base + 3.0 * i) * k)))
        pavs.append(p)
    for pai, filhos in ((f.by_type("IfcProject")[0], [site]), (site, [edif]), (edif, pavs)):
        _rel(f, "IfcRelAggregates", RelatingObject=pai, RelatedObjects=filhos)
    d = {"P": caixa(f, "IfcWall", "P", ox * k, oy * k, base * k, 5.0 * k, 0.25 * k, 3.0 * k),
         "M": caixa(f, "IfcBuildingElementProxy", "M", (ox + 1.0) * k, (oy + 2.0) * k, base * k, 0.5 * k, 0.5 * k, 1.5 * k),
         "falha": caixa(f, "IfcWall", "falha", (ox + 3.0) * k, oy * k, base * k, k, k, k, zero=True),
         "Q": caixa(f, "IfcWall", "Q", ox * k, oy * k, (base + 3.0) * k, 5.0 * k, 0.25 * k, 3.0 * k)}
    _rel(f, "IfcRelContainedInSpatialStructure", RelatingStructure=pavs[0], RelatedElements=[d["P"], d["M"], d["falha"]])
    _rel(f, "IfcRelContainedInSpatialStructure", RelatingStructure=pavs[1], RelatedElements=[d["Q"]])
    for nome, tipo, org, tam in (("vp", "PLANTA", (ox, oy, base), (10.0, 10.0, 3.0)), ("vc", "CORTE", (ox, oy - 1.0, base - 0.5), (10.0, 4.0, 4.0))):
        gid = V.criar_vista(f, nome, tipo, origem=[c * k for c in org], tamanho=[c * k for c in tam])
        d[nome] = gid
        if tipo == "PLANTA":
            _rel(f, "IfcRelContainedInSpatialStructure", RelatingStructure=pavs[0], RelatedElements=[f.by_guid(gid)])
    return f, d


def elementos(f, *nomes):
    """Lista `[[id, GlobalId], ...]` dos elementos de nome `nomes`, na ordem dada."""
    por = {e.Name: e for e in f.by_type("IfcProduct")}
    return [[por[n].id(), por[n].GlobalId] for n in nomes]


JANELA = """import json, sys
import ifcopenshell
assert "ifcopenshell.geom" not in sys.modules, "ifcopenshell.geom carregado antes de tudo"
arq, modo, gid = sys.argv[1:4]
f = ifcopenshell.open(arq)
if modo == "caixas":
    from openbim_app.desenho import auxiliar as X
    with X.preparar(f, {"op": "caixas", "elementos": [[w.id(), w.GlobalId] for w in f.by_type("IfcWall")]}) as p:
        ok = bool(X.executar(p)["caixas_envolventes"])
else:
    from openbim_app.desenho import planta
    ok = planta.gerar_planta(f, gid).n_paths > 0
ruins = [m for m in sys.modules if m.startswith(("ifcopenshell.geom", "obim_geometria.desenho", "obim_geometria.caixas", "obim_geometria.local"))]
print(json.dumps({"ok": ok, "ruins": sorted(ruins)}))
"""


def janela_limpa(f, modo, gid, pasta):
    """Roda `JANELA` num python NOVO (o processo da janela) sobre o modelo gravado em `pasta`; devolve {"ok", "ruins"}."""
    import json
    import os
    import subprocess
    arq = Path(pasta) / "janela.ifc"
    f.write(str(arq))
    r = subprocess.run([sys.executable, "-c", JANELA, str(arq), modo, gid or ""], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path), "LC_ALL": "C"})
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout.strip().splitlines()[-1])
