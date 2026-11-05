# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T07c (corte vertical SVG bruto). Não é de `app/`; implementador não edita. Modelo sintético pequeno (comprimentos em `k` vezes a unidade: k=1 metro,
k=1000 milímetro; o mundo é o mesmo), esquema, deslocamento XY, cota de base e a vista CORTE já voltada para +Y ou -Y, mais leitores crus do SVG."""
import re

import s06_t04_aux as A
import s06_t07_aux as X
import s06_t07b_aux as B

DX, DY, DZ = 7.0, 4.5, 6.0  # volume da vista (m): largura, altura e profundidade (a profundidade segue a direção de visão)
XMIN, ZMIN = -0.5, -0.5  # o volume começa 0,5 m antes da parede (x) e 0,5 m abaixo da cota de base (z): nenhum elemento do caso toca a borda
GEO = X.GEO
# (esquema, deslocamento XY em metros, cota de base em metros, k)
MODELOS = [("IFC2X3", (0.0, 0.0), 0.0, 1.0), ("IFC4", GEO, 0.0, 1.0), ("IFC4", (0.0, 0.0), 12.5, 1.0), ("IFC2X3", GEO, -1.5, 1000.0),
           ("IFC4", (0.0, 0.0), 0.0, 1000.0), ("IFC4X3", GEO, 1450.0, 1.0)]
PORTA = ("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0)  # nome, classe, x, z, largura, altura (m, relativos à origem do modelo)


def modelo(esq, off=(0.0, 0.0), base=0.0, k=1.0, vaos=(), esp=0.25, extras=True):
    """Origem O = (off, base). Plano do corte: y = O.y (a parede o atravessa: y de -esp/2 a +esp/2). Tudo em metros relativos a O (x, y, z); a unidade do arquivo é 1/k m.
    Parede `P` 5 x esp x 3 em x 0..5, z 0..3; laje `L` x 0..5, y -2..3, z -0,2..0 (cruza o plano); para cada vão (nome, classe, x, z, largura, altura) a abertura `O{nome}` que fura a parede e o
    preenchimento `{nome}`. Com `extras`: móvel `M` ATRÁS do plano (x 5,1..5,4, y 2..2,5, z 0..1,5); `Fundo` além da profundidade (x 5,5..5,8, y 7..7,5); `Atras` do lado de quem olha
    (x 5,1..5,4, y -3..-2,5); `Longe` a 150 m. Devolve (arquivo, {nome: GlobalId})."""
    f = A.novo_arquivo(esq)
    for u in f.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT":
            u.Prefix = "MILLI" if k == 1000.0 else None
    site, edif = X.elemento(f, "IfcSite", "Terreno"), X.elemento(f, "IfcBuilding", "Edificio")
    pav = X.elemento(f, "IfcBuildingStorey", "Pav0", Elevation=base * k)
    pav.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, off[0] * k, off[1] * k, base * k)))
    X.agregar(f, f.by_type("IfcProject")[0], site)
    X.agregar(f, site, edif)
    X.agregar(f, edif, pav)
    g = {}

    def cx(cls, nome, x, y, z, dx, dy, dz):
        e = X.caixa(f, cls, nome, (off[0] + x) * k, (off[1] + y) * k, (base + z) * k, dx * k, dy * k, dz * k)
        g[nome] = e.GlobalId
        return e
    par, laje = cx("IfcWall", "P", 0, -esp / 2, 0, 5.0, esp, 3.0), cx("IfcSlab", "L", 0, -2.0, -0.2, 5.0, 5.0, 0.2)
    movs = []
    if extras:
        movs = [cx(X.MOVEL[esq], "M", 5.1, 2.0, 0, 0.3, 0.5, 1.5), cx("IfcBuildingElementProxy", "Fundo", 5.5, 7.0, 0, 0.3, 0.5, 1.0),
                cx("IfcBuildingElementProxy", "Atras", 5.1, -3.0, 0, 0.3, 0.5, 1.0), cx("IfcBuildingElementProxy", "Longe", 150.0, -0.1, 0, 0.3, 0.2, 1.0)]
    X.conter(f, pav, par, laje, *movs)
    for nome, cls, x, z, w, h in vaos:
        o, d = cx("IfcOpeningElement", "O" + nome, x, -esp / 2, z, w, esp, h), cx(cls, nome, x, -esp / 2, z, w, esp, h)
        f.create_entity("IfcRelVoidsElement", GlobalId=A.ifcopenshell.guid.new(), RelatingBuildingElement=par, RelatedOpeningElement=o, **X.kw(f))
        f.create_entity("IfcRelFillsElement", GlobalId=A.ifcopenshell.guid.new(), RelatingOpeningElement=o, RelatedBuildingElement=d, **X.kw(f))
    return f, g


def corte(f, off=(0.0, 0.0), base=0.0, k=1.0, olhar="+Y", escala="1:100", nome="C", tamanho=(DX, DY, DZ), origem=None):
    """Vista CORTE voltada para +Y (eixo local X = X do mundo, local Y = Z do mundo, câmera em O) ou para -Y (câmera 7 m adiante em X, X local = -X do mundo). O volume (`IfcBlock`)
    vai de 0 a `tamanho` em X e Y locais e de -profundidade a 0 em Z local (a direção de visão é o -Z local, como o motor lê). Devolve o GlobalId."""
    import openbim_app.vistas_ifc as V
    ox, oy = off
    o = origem or ((ox + XMIN + (DX if olhar == "-Y" else 0.0)) * k, oy * k, (base + ZMIN) * k)
    gid = V.criar_vista(f, nome, "CORTE", escala=escala, origem=o, tamanho=tuple(t * k for t in tamanho))
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    d = (0.0, -1.0, 0.0) if olhar == "+Y" else (0.0, 1.0, 0.0)
    r = (1.0, 0.0, 0.0) if olhar == "+Y" else (-1.0, 0.0, 0.0)
    eixo.Axis, eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=d), f.create_entity("IfcDirection", DirectionRatios=r)
    X.deslocar_bloco(f, gid, (0.0, 0.0, -tamanho[2] * k))
    return gid


def projecao(svg):
    m = re.search(r'<g class="projection">(.*?)</g>', svg, re.S)
    return m.group(1) if m else ""


def area(pts):
    """Área (módulo da fórmula do cadarço) da polilinha fechada."""
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2.0


def local(p, olhar="+Y"):
    """Ponto do SVG -> (x, z) em metros relativos à origem O do modelo (x do mundo, z do mundo). O motor devolve x = X local + largura/2 e y = altura/2 - Y local (y cresce para baixo);
    com `olhar` -Y o X local é o -X do mundo."""
    xl, zl = p[0] - DX / 2.0, DY / 2.0 - p[1]
    return round((XMIN + xl) if olhar == "+Y" else (XMIN + DX - xl), 3), round(zl + ZMIN, 3)
