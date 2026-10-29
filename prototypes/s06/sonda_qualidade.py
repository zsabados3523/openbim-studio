# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda de qualidade dos motores de desenho (F0-S06-T01b): contorno, hachura, arco de porta, tempo.
Reusa sonda_motores.py sem altera-lo. Saidas em /tmp/s06-sonda-q (nao commitar).
Uso: python sonda_qualidade.py [--parte sintetico|po-arcos|po-tempo|todas] [--repeticoes 3]
"""
import os
import argparse
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.ifcopenshell_wrapper as W

SAIDA = Path("/tmp/s06-sonda-q")
PO = Path(os.environ.get("OBIM_IFC_REFERENCIA", "referencia.ifc"))  # IFC do PO: fora do repositorio, caminho pela variavel
ALTURA_PLANTA = 1.2
RE_GRUPO = re.compile(r'<g id="product-[^"]*"[^>]*ifc:guid="([^"]+)"[^>]*>(.*?)</g>', re.S)
# padroes de hachura (45 graus, 135 graus, horizontal), um por material, ciclico
PADROES = ['<line x1="0" y1="0" x2="0.1" y2="0.1"/>', '<line x1="0" y1="0.1" x2="0.1" y2="0"/>',
           '<line x1="0" y1="0.05" x2="0.1" y2="0.05"/>']


def _carregar_sonda():
    spec = importlib.util.spec_from_file_location("sonda_motores", Path(__file__).with_name("sonda_motores.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _api(nome, f, **kw):
    return ifcopenshell.api.run(nome, f, **kw)


def _base(metros):
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = _api("root.create_entity", f, ifc_class="IfcProject", name="Teste")
    if metros:
        _api("unit.assign_unit", f, length={"is_metric": True, "raw": "METRE"})
    else:
        _api("unit.assign_unit", f)  # padrao da API: milimetros
    ctx = _api("context.add_context", f, context_type="Model")
    corpo = _api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    pred = _api("root.create_entity", f, ifc_class="IfcBuilding", name="Predio")
    piso = _api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    piso.Elevation = 0.0
    _api("aggregate.assign_object", f, products=[pred], relating_object=proj)
    _api("aggregate.assign_object", f, products=[piso], relating_object=pred)
    return f, corpo, piso


def _parede(f, corpo, piso, nome, x):
    w = _api("root.create_entity", f, ifc_class="IfcWall", name=nome)
    rep = _api("geometry.add_wall_representation", f, context=corpo, length=4.0, height=2.8, thickness=0.15)  # metros SI
    _api("geometry.assign_representation", f, product=w, representation=rep)
    m = np.eye(4)
    m[0, 3] = x
    _api("geometry.edit_object_placement", f, product=w, matrix=m)
    _api("spatial.assign_container", f, products=[w], relating_structure=piso)
    return w


def _porta(f, corpo, piso, tipada, sc, certa):
    """certa: dimensoes em unidades do projeto (metros / sc). Falso: passa 0,9 m cru (erro de unidade)."""
    larg, alt = (0.9 / sc, 2.1 / sc) if certa else (0.9, 2.1)
    kw = dict(context=corpo, overall_height=alt, overall_width=larg, operation_type="SINGLE_SWING_LEFT", unit_scale=sc)
    d = _api("root.create_entity", f, ifc_class="IfcDoor", name="Porta")
    if tipada:
        t = _api("root.create_entity", f, ifc_class="IfcDoorType", name="Tipo porta")
        t.PredefinedType = "DOOR"
        t.OperationType = "SINGLE_SWING_LEFT"
        _api("geometry.assign_representation", f, product=t, representation=_api("geometry.add_door_representation", f, **kw))
        _api("type.assign_type", f, related_objects=[d], relating_type=t)
    else:
        _api("geometry.assign_representation", f, product=d, representation=_api("geometry.add_door_representation", f, **kw))
    m = np.eye(4)
    m[0, 3], m[1, 3] = 1.0, 2.0  # na frente da parede A
    _api("geometry.edit_object_placement", f, product=d, matrix=m)
    _api("spatial.assign_container", f, products=[d], relating_structure=piso)


def _sintetico(metros, tipada, certa=True):
    f, corpo, piso = _base(metros)
    sc = 1.0 if metros else 0.001  # metros por unidade do projeto
    a = _parede(f, corpo, piso, "Parede A", 0.0)
    b = _parede(f, corpo, piso, "Parede B", 5.0)
    c = _parede(f, corpo, piso, "Parede C", 10.0)
    _api("material.assign_material", f, products=[a], type="IfcMaterial",
         material=_api("material.add_material", f, name="Material A", category="masonry"))
    _api("material.assign_material", f, products=[b], type="IfcMaterial",
         material=_api("material.add_material", f, name="Material B", category="render"))
    ls = _api("material.add_material_set", f, name="Parede C", set_type="IfcMaterialLayerSet")
    for nome, cat, esp in (("Alvenaria C", "masonry", 0.13), ("Reboco C", "render", 0.02)):
        camada = _api("material.add_layer", f, layer_set=ls, material=_api("material.add_material", f, name=nome, category=cat))
        camada.LayerThickness = esp
    _api("material.assign_material", f, products=[c], type="IfcMaterialLayerSet", material=ls)
    _porta(f, corpo, piso, tipada, sc, certa)
    return f


def _svg(f, arcos):
    st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
    for k, v in {"dimensionality": W.SURFACES_AND_SOLIDS, "iterator-output": W.NATIVE, "section-height": ALTURA_PLANTA,
                 "svg-write-poly": True, "svg-xmlns": True, "door-arcs": arcos}.items():
        st.set(k, v)
    buf = ifcopenshell.geom.serializers.buffer()
    sr = ifcopenshell.geom.serializers.svg(buf, st)
    sr.setFile(f)
    for el in ifcopenshell.geom.iterator(st, f):
        sr.write(el)
    sr.finalize()
    return buf.get_value()


def _tamanho_porta(f):
    st = ifcopenshell.geom.settings(USE_WORLD_COORDS=True)
    for el in ifcopenshell.geom.iterator(st, f):
        if el.type == "IfcDoor":
            v = np.asarray(el.geometry.verts, float).reshape(-1, 3)
            return [round(float(x), 3) for x in (v.max(0) - v.min(0))]
    return None


def _material(el):
    m = ifcopenshell.util.element.get_material(el)
    if m is not None and m.is_a("IfcMaterialLayerSetUsage"):
        m = m.ForLayerSet
    if m is not None and m.is_a("IfcMaterialLayerSet"):
        m = m.MaterialLayers[0].Material if m.MaterialLayers else None
    return m.Name if m is not None and m.is_a("IfcMaterial") else None


def _hachurar(f, svg):
    """Hachura por material: cada grupo de produto (ifc:guid) recebe o padrao do material do IFC."""
    mapa, cont = {}, {}

    def troca(m):
        try:
            nome = _material(f.by_guid(m.group(1)))
        except Exception:
            nome = None
        if nome is None:
            return m.group(0)
        i = mapa.setdefault(nome, len(mapa) % len(PADROES))
        cont[nome] = cont.get(nome, 0) + 1
        return m.group(0).replace("<path ", f'<path fill="url(#h{i})" ')

    novo = RE_GRUPO.sub(troca, svg)
    defs = "".join(f'<pattern id="h{i}" width="0.1" height="0.1" patternUnits="userSpaceOnUse" stroke="#000" stroke-width="0.01">{p}</pattern>'
                   for i, p in enumerate(PADROES))
    return novo.replace("<defs>", "<defs>" + defs, 1), mapa, cont


def _fechados(svg):
    """Subcaminhos de produto que terminam onde comecam (contorno fechado, sem Z)."""
    ok = tot = 0
    for g in RE_GRUPO.finditer(svg):
        for d in re.findall(r'<path d="([^"]+)"', g.group(0)):
            for sub in d.split("M")[1:]:
                pts = [tuple(map(float, p.split(","))) for p in sub.replace("L", " ").split() if "," in p]
                if len(pts) >= 3:
                    tot += 1
                    ok += abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6
    return ok, tot


def _estilos_com_arco(f):
    return [s for s in f.by_type("IfcDoorStyle") if any(
        e.is_a("IfcTrimmedCurve") for m in (s.RepresentationMaps or []) if m.MappedRepresentation.RepresentationIdentifier == "FootPrint"
        for i in m.MappedRepresentation.Items for e in (i.Elements or []))]


def _parte_sintetico():
    print("\n## Porta: unidade e tipo (sintetico)")
    print("| Projeto | Tipo | Dimensao certa | Caixa da porta (m) | Saida igual com/sem door-arcs | Caminhos extras com door-arcs |")
    print("|---|---|---|---|---|---|")
    for metros in (False, True):
        for tipada in (False, True):
            for certa in (True, False):
                f = _sintetico(metros, tipada, certa)
                on, off = _svg(f, True), _svg(f, False)
                print(f"| {'m' if metros else 'mm'} | {'IfcDoorType' if tipada else 'sem tipo'} | {certa} | "
                      f"{_tamanho_porta(f)} | {on == off} | {on.count('<path') - off.count('<path')} |")
    f = _sintetico(False, True, True)  # mesmo modelo para SVG e para a consulta de material (GUIDs mudam a cada modelo)
    svg = _svg(f, False)
    novo, mapa, cont = _hachurar(f, svg)
    (SAIDA / "hachura_sintetico.svg").write_text(novo, encoding="utf-8")
    ET.fromstring(novo)  # XML valido
    print("\n## Contorno e hachura (sintetico, planta)")
    print(f"contorno fechado por subcaminho (ok/total): {_fechados(svg)}")
    print(f"materiais hachurados: {cont}; padrao por material: {mapa}")


def _parte_po_arcos():
    f = ifcopenshell.open(str(PO))
    on, off = _svg(f, True), _svg(f, False)
    (SAIDA / "po_planta_door_arcs_on.svg").write_text(on, encoding="utf-8")
    print("\n## casa-2pav (planta), door-arcs ligado e desligado")
    print(f"schema: {f.schema}; bytes com/sem door-arcs: {len(on)} / {len(off)}; saida igual: {on == off}")
    print(f"portas (IfcDoor): {len(f.by_type('IfcDoor'))}; grupos IfcDoor na planta: {on.count('class=\"IfcDoor\"')}")
    print(f"IfcDoor tem atributo OperationType: {any(hasattr(d, 'OperationType') for d in f.by_type('IfcDoor'))}")
    estilos = f.by_type("IfcDoorStyle")
    print(f"estilos de porta: {len(estilos)}; OperationType: {sorted({s.OperationType for s in estilos})}; "
          f"com arco no FootPrint: {len(_estilos_com_arco(f))}")
    alvo = _estilos_com_arco(f)
    for s in alvo:
        s.OperationType = "SINGLE_SWING_LEFT"  # em memoria, nada gravado
    teste = _svg(f, True)
    print(f"teste em memoria, {len(alvo)} estilos com SINGLE_SWING_LEFT: caminhos extras com door-arcs: "
          f"{teste.count('<path') - on.count('<path')}")
    novo, mapa, cont = _hachurar(f, on)
    ET.fromstring(novo)
    print(f"contorno fechado (ok/total): {_fechados(on)}; materiais hachurados: {len(mapa)}; elementos: {sum(cont.values())}")


def _parte_po_tempo(n):
    sm = _carregar_sonda()
    f, fc = ifcopenshell.open(str(PO)), ifcopenshell.open(str(PO))
    mn, mx = sm._caixa(f)
    guid = sm._anotar_corte(fc, mn, mx, float((mn[1] + mx[1]) / 2))
    t_pl, _ = sm._medir(lambda: sm._svg_motor(f, False), n)
    t_co, _ = sm._medir(lambda: sm._svg_motor(fc, False, guid), n)
    print(f"\n## Tempo casa-2pav, motor a1, media de {n} execucoes")
    print(f"planta: {t_pl:.3f} s; corte: {t_co:.3f} s; meta 10 s: {'sim' if max(t_pl, t_co) <= 10 else 'nao'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parte", choices=["sintetico", "po-arcos", "po-tempo", "todas"], default="todas")
    ap.add_argument("--repeticoes", type=int, default=3)
    args = ap.parse_args(argv)
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"ifcopenshell {ifcopenshell.version}")
    if args.parte in ("sintetico", "todas"):
        _parte_sintetico()
    if args.parte in ("po-arcos", "todas"):
        _parte_po_arcos()
    if args.parte in ("po-tempo", "todas"):
        _parte_po_tempo(args.repeticoes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
