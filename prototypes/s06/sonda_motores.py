# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda dos motores de desenho (F0-S06-T01).

Mede planta (corte a 1,2 m) e corte (plano vertical no meio da caixa do modelo) em tres variantes: a1 = serializador SVG padrao do ifcopenshell (HLRBRep_Algo), a2 = o mesmo com svg-poly
(HLRBRep_PolyAlgo) e d = secao + projecao proprias com shapely (sem remover partes ocultas).
"""
import argparse
import importlib.util
import math
import random
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.ops import polygonize

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.ifcopenshell_wrapper as W
import ifcopenshell.util.unit

RAIZ = Path(__file__).resolve().parents[2]
META_S = 10.0
ALTURA_PLANTA = 1.2
MOTORES = {"a1": "a1 padrao (HLRBRep_Algo)", "a2": "a2 svg-poly (HLRBRep_PolyAlgo)", "d": "d secao+projecao propria"}


def _api(nome, f, **kw):
    return ifcopenshell.api.run(nome, f, **kw)


def _base():
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = _api("root.create_entity", f, ifc_class="IfcProject", name="Sonda")
    _api("unit.assign_unit", f)
    ctx = _api("context.add_context", f, context_type="Model")
    corpo = _api("context.add_context", f, context_type="Model", context_identifier="Body",
                 target_view="MODEL_VIEW", parent=ctx)
    predio = _api("root.create_entity", f, ifc_class="IfcBuilding", name="Predio")
    piso = _api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    piso.Elevation = 0.0
    _api("aggregate.assign_object", f, products=[predio], relating_object=proj)
    _api("aggregate.assign_object", f, products=[piso], relating_object=predio)
    return f, corpo, piso


def _matriz(x, y, graus):
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return np.array([[c, -s, 0, x], [s, c, 0, y], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)


def _colocar(f, piso, produto, rep, matriz):
    _api("geometry.assign_representation", f, product=produto, representation=rep)
    _api("geometry.edit_object_placement", f, product=produto, matrix=matriz)
    _api("spatial.assign_container", f, products=[produto], relating_structure=piso)


def _gerar_casa(caminho):
    spec = importlib.util.spec_from_file_location("gerar_casa_simples", RAIZ / "scripts" / "gerar_casa_simples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main(str(caminho))
    f = ifcopenshell.open(str(caminho))
    for piso in f.by_type("IfcBuildingStorey"):
        piso.Elevation = 0.0
    f.write(str(caminho))


def _gerar_pavimento(caminho, semente):
    """Grade de 25 x 20 m (500 m2): perimetro, 4 paredes verticais e 3 horizontais, com portas em posicao sorteada."""
    rng = random.Random(semente)
    f, corpo, piso = _base()
    u = 1.0 / ifcopenshell.util.unit.calculate_unit_scale(f)  # portas: dimensoes em unidades do projeto
    ls = _api("material.add_material_set", f, name="Parede 15 cm", set_type="IfcMaterialLayerSet")
    for nome, cat, espessura in (("Alvenaria", "masonry", 0.13), ("Reboco", "render", 0.02)):
        camada = _api("material.add_layer", f, layer_set=ls, material=_api("material.add_material", f, name=nome, category=cat))
        camada.LayerThickness = espessura
    perimetro = [((0, 0), (25, 0)), ((25, 0), (25, 20)), ((25, 20), (0, 20)), ((0, 20), (0, 0))]
    internas = [((x, 0), (x, 20)) for x in (5, 10, 15, 20)] + [((0, y), (25, y)) for y in (5, 10, 15)]
    for k, ((x1, y1), (x2, y2)) in enumerate(perimetro + internas):
        L = math.hypot(x2 - x1, y2 - y1)
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        porta = k == 0 or k >= len(perimetro)
        c = L * rng.uniform(0.3, 0.7)
        trechos = [(c - 0.45, 0.0), (L, c + 0.45)] if porta else [(0.0, L)]
        for a, b in trechos:
            parede = _api("root.create_entity", f, ifc_class="IfcWall", name=f"Parede {k}")
            rep = _api("geometry.add_wall_representation", f, context=corpo, length=b - a, height=2.8, thickness=0.15)
            _colocar(f, piso, parede, rep, _matriz(x1 + ux * a, y1 + uy * a, ang))
            _api("material.assign_material", f, products=[parede], type="IfcMaterialLayerSet", material=ls)
        if porta:
            porta_el = _api("root.create_entity", f, ifc_class="IfcDoor", name=f"Porta {k}")
            rep = _api("geometry.add_door_representation", f, context=corpo, overall_height=2.1 * u, overall_width=0.9 * u)
            _colocar(f, piso, porta_el, rep, _matriz(x1 + ux * (c - 0.45), y1 + uy * (c - 0.45), ang))
    f.write(str(caminho))


def _caixa(f):
    mn, mx = np.full(3, np.inf), np.full(3, -np.inf)
    for el in ifcopenshell.geom.iterator(ifcopenshell.geom.settings(USE_WORLD_COORDS=True), f):
        v = np.asarray(el.geometry.verts, float).reshape(-1, 3)
        mn, mx = np.minimum(mn, v.min(0)), np.maximum(mx, v.max(0))
    return mn, mx


def _anotar_corte(f, mn, mx, y_corte):
    """Vista de corte no padrao Bonsai: IfcAnnotation DRAWING. Local: X = X do mundo, Z = +Y (normal), Y = -Z."""
    corpos = [c for c in f.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body"]
    corpo = corpos[0] if corpos else f.by_type("IfcGeometricRepresentationContext")[0]
    u = 1.0 / ifcopenshell.util.unit.calculate_unit_scale(f)  # iterador devolve metros; IFC usa unidades do projeto
    bloco = f.createIfcBlock(
        Position=f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((float(mn[0] * u), float(-mx[2] * u), 0.0))),
        XLength=float((mx[0] - mn[0]) * u), YLength=float((mx[2] - mn[2]) * u), ZLength=float((mx[1] - y_corte) * u),
    )
    plano = f.createIfcAxis2Placement3D(
        f.createIfcCartesianPoint((0.0, float(y_corte * u), 0.0)),
        f.createIfcDirection((0.0, 1.0, 0.0)), f.createIfcDirection((1.0, 0.0, 0.0)),
    )
    rep = f.createIfcShapeRepresentation(ContextOfItems=corpo, RepresentationIdentifier="Body",
                                         RepresentationType="CSG", Items=[f.createIfcCsgSolid(TreeRootExpression=bloco)])
    ann = f.createIfcAnnotation(
        GlobalId=ifcopenshell.guid.new(), Name="Corte sonda", ObjectType="DRAWING",
        ObjectPlacement=f.createIfcLocalPlacement(RelativePlacement=plano),
        Representation=f.createIfcProductDefinitionShape(Representations=[rep]),
    )
    pisos = f.by_type("IfcBuildingStorey")
    if pisos:
        _api("spatial.assign_container", f, products=[ann], relating_structure=pisos[0])
    return ann.GlobalId


def _svg_motor(f, poly, guid_corte=None):
    """Serializador SVG do ifcopenshell. Planta: corte a 1,2 m. Corte: IfcAnnotation DRAWING pelo GlobalId."""
    st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
    st.set("dimensionality", W.SURFACES_AND_SOLIDS)
    st.set("iterator-output", W.NATIVE)
    st.set("apply-default-materials", True)
    st.set("svg-write-poly", True)
    st.set("svg-xmlns", True)
    st.set("svg-poly", poly)
    st.set("door-arcs", True)
    if guid_corte:
        st.set("elevation-ref-guid", guid_corte)
        st.set("svg-without-storeys", True)
    else:
        st.set("section-height", ALTURA_PLANTA)
    buf = ifcopenshell.geom.serializers.buffer()
    sr = ifcopenshell.geom.serializers.svg(buf, st)
    sr.setFile(f)
    for el in ifcopenshell.geom.iterator(st, f):
        sr.write(el)
    sr.finalize()
    return buf.get_value()


def _secao(T, eixo, valor):
    """Segmentos 3D do corte de cada triangulo pelo plano eixo=valor (2 pontos por triangulo cruzado)."""
    d = T[:, :, eixo] - valor
    idx_l, pts_l = [], []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        m = np.nonzero((d[:, a] >= 0) != (d[:, b] >= 0))[0]
        t = d[m, a] / (d[m, a] - d[m, b])
        pts_l.append(T[m, a] + t[:, None] * (T[m, b] - T[m, a]))
        idx_l.append(m)
    idx, pts = np.concatenate(idx_l), np.concatenate(pts_l)
    ordem = np.argsort(idx, kind="stable")
    idx, pts = idx[ordem], pts[ordem]
    ok = np.bincount(idx, minlength=len(T))[idx] == 2
    return pts[ok].reshape(-1, 2, 3)


def _svg_d(f, eixo, valor, corte):
    """Secao com shapely + contorno da projecao das pecas do lado oposto. Sem remocao de partes ocultas."""
    st = ifcopenshell.geom.settings(USE_WORLD_COORDS=True)
    T = np.concatenate([
        np.asarray(el.geometry.verts, float).reshape(-1, 3)[np.asarray(el.geometry.faces, int).reshape(-1, 3)]
        for el in ifcopenshell.geom.iterator(st, f)
    ])
    eixos2d = [i for i in range(3) if i != eixo]
    seg = _secao(T, eixo, valor)
    poligonos = list(polygonize(shapely.union_all(shapely.linestrings(seg[:, :, eixos2d])))) if len(seg) else []
    lado = (T[:, :, eixo] >= valor).all(1) if corte else (T[:, :, eixo] <= valor).all(1)
    contorno = []
    if lado.any():
        proj = shapely.union_all(shapely.polygons(T[lado][:, :, eixos2d]))
        if not proj.is_empty:
            contorno = list(getattr(proj.boundary, "geoms", [proj.boundary]))

    def caminho(coords):
        return "M " + " L ".join(f"{x:.3f} {y:.3f}" for x, y in coords)

    partes = [f'<path d="{caminho(list(p.exterior.coords))} Z" fill="none" stroke="black"/>' for p in poligonos]
    partes += [f'<path d="{caminho(list(c.coords))}" fill="none" stroke="black"/>' for c in contorno]
    return '<svg xmlns="http://www.w3.org/2000/svg">\n' + "\n".join(partes) + "\n</svg>\n"


def _metricas(svg):
    linhas = len(re.findall(r"<(?:path|line|polyline)\b", svg))
    hachura = bool(re.search(r"<pattern\b|hatch", svg, re.IGNORECASE))
    arco = bool(re.search(r'\sd="[^"]*\bA[\s\d.,-]', svg))
    return linhas, hachura, arco


def _medir(fn, n):
    tempos, ultimo = [], None
    for _ in range(n):
        t0 = time.perf_counter()
        ultimo = fn()
        tempos.append(time.perf_counter() - t0)
    return statistics.mean(tempos), ultimo


def _avaliar(nome, caminho, n, saida):
    fp, fc = ifcopenshell.open(str(caminho)), ifcopenshell.open(str(caminho))
    mn, mx = _caixa(fp)
    y_corte = float((mn[1] + mx[1]) / 2)
    falhas_modelo, guid = [], None
    try:
        guid = _anotar_corte(fc, mn, mx, y_corte)
    except Exception as e:
        falhas_modelo.append(f"corte sem anotacao ({type(e).__name__}: {str(e)[:80]})")
    casos = {
        "a1": {"planta": lambda: _svg_motor(fp, False), "corte": lambda: _svg_motor(fc, False, guid)},
        "a2": {"planta": lambda: _svg_motor(fp, True), "corte": lambda: _svg_motor(fc, True, guid)},
        "d": {"planta": lambda: _svg_d(fp, 2, ALTURA_PLANTA, False), "corte": lambda: _svg_d(fp, 1, y_corte, True)},
    }
    linhas = []
    for chave, vistas in casos.items():
        r = {"modelo": nome, "motor": MOTORES[chave], "tempo": {}, "linhas": {}, "hach": [], "arco": [],
             "falhas": list(falhas_modelo)}
        for vista, fn in vistas.items():
            try:
                tempo, svg = _medir(fn, n)
                (saida / f"{nome}_{vista}_{chave}.svg").write_text(svg, encoding="utf-8")
                r["tempo"][vista] = tempo
                r["linhas"][vista], h, a = _metricas(svg)
                r["hach"].append(h)
                r["arco"].append(a)
            except Exception as e:
                r["falhas"].append(f"{vista}: {type(e).__name__}: {str(e)[:100]}")
        linhas.append(r)
    return linhas


def _tabela(linhas):
    cab = ["| Modelo | Motor | Planta (s) | Corte (s) | Linhas planta | Linhas corte | Hachura | Arco de porta | Meta 10 s | Falhas |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in linhas:
        t = r["tempo"]
        ok = "ok" if len(t) == 2 and max(t.values()) <= META_S and not r["falhas"] else "NAO"
        cab.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["modelo"], r["motor"],
            f"{t['planta']:.3f}" if "planta" in t else "-", f"{t['corte']:.3f}" if "corte" in t else "-",
            r["linhas"].get("planta", "-"), r["linhas"].get("corte", "-"),
            "sim" if any(r["hach"]) else "nao", "sim" if any(r["arco"]) else "nao",
            ok, "; ".join(r["falhas"]) or "-"))
    return "\n".join(cab)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", default="/tmp/s06-sonda", help="pasta dos SVG e IFC gerados (nao commitar)")
    ap.add_argument("--relatorio", default=None, help="arquivo .md com a tabela (padrao: nao grava)")
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--semente", type=int, default=1)
    ap.add_argument("--ifc", action="append", default=[], help="IFC publico extra a medir")
    args = ap.parse_args(argv)

    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    casa, pavimento = saida / "casa-simples.ifc", saida / "pavimento-500m2.ifc"
    _gerar_casa(casa)
    _gerar_pavimento(pavimento, args.semente)
    modelos = [("casa-simples", casa), ("pavimento-500m2", pavimento)] + [(Path(p).stem, Path(p)) for p in args.ifc]

    linhas = []
    for nome, caminho in modelos:
        try:
            linhas += _avaliar(nome, caminho, args.repeticoes, saida)
        except Exception as e:
            linhas.append({"modelo": nome, "motor": "-", "tempo": {}, "linhas": {}, "hach": [], "arco": [],
                           "falhas": [f"abrir/medir: {type(e).__name__}: {str(e)[:100]}"]})

    cabecalho = (f"ifcopenshell {ifcopenshell.version}, Python {sys.version.split()[0]}, "
                 f"media de {args.repeticoes} execucoes por vista, semente {args.semente}. Meta: {META_S:.0f} s por vista.")
    tabela = _tabela(linhas)
    print(cabecalho + "\n" + tabela)
    if args.relatorio:
        Path(args.relatorio).write_text("# F0-S06-T01: sonda dos motores de desenho\n\n" + cabecalho + "\n\n" + tabela + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
