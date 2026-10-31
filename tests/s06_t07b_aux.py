# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T07b (planta SVG bruta). Não é de `app/`; implementador não edita. Modelos sintéticos pequenos (comprimentos em `k` vezes a unidade:
k=1 metro, k=1000 milímetro; o mundo é o mesmo), pavimentos em cota arbitrária, colocação absoluta ou relativa ao edifício, e leitores crus do SVG."""
import re
import xml.etree.ElementTree as ET

import s06_t04_aux as A
import s06_t07_aux as X

NUM = re.compile(r"(-?\d+\.?\d*(?:[eE][-+]?\d+)?),(-?\d+\.?\d*(?:[eE][-+]?\d+)?)")
# (esquema, deslocamento XY em metros, cota do térreo em metros, k, pavimentos com colocação relativa ao edifício)
MODELOS = [("IFC2X3", (0.0, 0.0), 0.0, 1.0, False), ("IFC4", X.GEO, 0.0, 1.0, False), ("IFC4", (0.0, 0.0), 12.5, 1.0, True),
           ("IFC2X3", X.GEO, -1.5, 1000.0, True), ("IFC4", (0.0, 0.0), 0.0, 1000.0, False)]


def modelo(esq, off=(0.0, 0.0), base=0.0, k=1.0, relativo=False, n_pav=2, esp=0.25, vaos=(("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0),), n_moveis=1):
    """`n_pav` pavimentos (3 m de pé direito). Pavimento s, z0 = base + 3 s: parede `P{s}` 5 x esp x 3 em (off, z0); laje `L{s}` 0,2 m ABAIXO de z0 (nunca desenhada: o motor só desenha o que cruza o plano de corte);
    `n_moveis` móveis `M{s}_{j}` (0,5 x 0,5 x 1,5, cruzam o corte de z0 + 1,2); caixas 0,3 x 0,3 no pavimento: `Xc` z 1,0 a 1,4 (cruza o corte), `Xa` z 1,45 a 1,9 (inteira
    ACIMA), `Xb` z 0,5 a 0,95 (inteira ABAIXO) e `Longe` (cruza, 150 m ao lado da parede); para cada vão (nome, classe, x, z, largura, altura) a abertura `O{nome}{s}` que fura a parede e o
    preenchimento `{nome}{s}` (NÃO contido no pavimento; a parede, a laje e os móveis são). Com `relativo`: o edifício fica em (off, base) e cada pavimento
    é relativo a ele (local z = 3 s, Elevation local); senão, absoluto (Elevation = base + 3 s). Devolve (arquivo, pavimentos, {nome: GlobalId})."""
    f = A.novo_arquivo(esq)
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = "MILLI" if k == 1000.0 else None
    ox, oy = off
    site, edif = X.elemento(f, "IfcSite", "Terreno"), X.elemento(f, "IfcBuilding", "Edificio")
    ped = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, ox * k, oy * k, base * k)))
    if relativo:
        edif.ObjectPlacement = ped
    pavs, g = [], {}
    for s in range(n_pav):
        z0 = base + 3.0 * s
        p = X.elemento(f, "IfcBuildingStorey", f"Pav{s}", Elevation=(3.0 * s if relativo else z0) * k)
        p.ObjectPlacement = (f.create_entity("IfcLocalPlacement", PlacementRelTo=ped, RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0, 0, 3.0 * s * k)))
                             if relativo else f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, ox * k, oy * k, z0 * k))))
        pavs.append(p)
    X.agregar(f, f.by_type("IfcProject")[0], site)
    X.agregar(f, site, edif)
    X.agregar(f, edif, *pavs)
    for s, p in enumerate(pavs):
        z0 = base + 3.0 * s

        def cx(cls, nome, x, y, z, dx, dy, dz):
            e = X.caixa(f, cls, nome + str(s), (ox + x) * k, (oy + y) * k, (z0 + z) * k, dx * k, dy * k, dz * k)
            g[nome + str(s)] = e.GlobalId
            return e
        par, laje = cx("IfcWall", "P", 0, 0, 0, 5.0, esp, 3.0), cx("IfcSlab", "L", 0, 0, -0.2, 5.0, 5.0, 0.2)
        movs = [cx(X.MOVEL[esq], f"M{j}_", 0.5 + 0.1 * j, 2.0, 0, 0.5, 0.5, 1.5) for j in range(n_moveis)]
        caixas = [cx("IfcBuildingElementProxy", n, x, 1.0, z, 0.3, 0.3, dz) for n, x, z, dz in
                  (("Xc", 1.0, 1.0, 0.4), ("Xa", 2.0, 1.45, 0.45), ("Xb", 3.0, 0.5, 0.45), ("Longe", 150.0, 1.0, 0.4))]
        X.conter(f, p, par, laje, *movs, *caixas)
        for nome, cls, x, z, w, h in vaos:
            o, d = cx("IfcOpeningElement", "O" + nome, x, 0, z, w, esp, h), cx(cls, nome, x, 0, z, w, esp, h)
            f.create_entity("IfcRelVoidsElement", GlobalId=A.ifcopenshell.guid.new(), RelatingBuildingElement=par, RelatedOpeningElement=o, **X.kw(f))
            f.create_entity("IfcRelFillsElement", GlobalId=A.ifcopenshell.guid.new(), RelatingOpeningElement=o, RelatedBuildingElement=d, **X.kw(f))
    return f, pavs, g


def planta(f, pav, nome="V"):
    return X.vista(f, "PLANTA", pav, nome=nome)


def grupo(svg, guid):
    """Texto do `<g ... ifc:guid="guid">...</g>` do elemento no SVG, ou None."""
    m = re.search(r'<g [^>]*ifc:guid="%s"[^>]*>(.*?)</g>' % re.escape(guid), svg, re.S)
    return m.group(1) if m else None


def subcaminhos(texto):
    """Lista de polilinhas [(x, y), ...] de todos os `<path d=...>` do texto (cada `M` abre uma)."""
    saida = []
    for d in re.findall(r'<path d="([^"]*)"', texto or ""):
        saida += [[(float(a), float(b)) for a, b in NUM.findall(t)] for t in d.split("M")[1:]]
    return saida


def caixa_de(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def svg_valido(svg):
    return ET.fromstring(svg).tag.endswith("svg")
