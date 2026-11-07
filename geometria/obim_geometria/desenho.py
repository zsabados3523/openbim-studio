# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de desenho de planta (modo pavimento do motor SVG, sem criar entidade no arquivo)."""
import re
import time
import traceback

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.ifcopenshell_wrapper as W
import ifcopenshell.util.element
import ifcopenshell.util.placement
from obim_geometria import nucleos


_GRUPO = re.compile(r"<g\b[^>]*?(/?)>|</g>")


def _somente_pavimento(svg: str, guid: str) -> str:
    """Remove do texto os grupos `IfcBuildingStorey` que nao sao o pavimento `guid` (os de cima repetem a projecao)."""
    pilha, remover = [], []
    for m in _GRUPO.finditer(svg):
        tag = m.group(0)
        if tag.startswith("</"):
            if pilha:
                inicio, storey, gid = pilha.pop()
                if storey and gid != guid:
                    remover.append((inicio, m.end()))
            continue
        storey = 'class="IfcBuildingStorey"' in tag
        gid = None
        if storey:
            achado = re.search(r'ifc:guid="([^"]+)"', tag)
            gid = achado.group(1) if achado else None
        if m.group(1) == "/":
            if storey and gid != guid:
                remover.append((m.start(), m.end()))
            continue
        pilha.append((m.start(), storey, gid))
    fundidos = []
    for inicio, fim in sorted(remover):
        if fundidos and inicio <= fundidos[-1][1]:
            fundidos[-1][1] = max(fundidos[-1][1], fim)
        else:
            fundidos.append([inicio, fim])
    for inicio, fim in reversed(fundidos):
        svg = svg[:inicio] + svg[fim:]
    return svg


class ProtocoloInvalido(Exception):
    pass


def _pavimento(ifc: ifcopenshell.file, vista: dict) -> object:
    gid = vista.get("pavimento")
    if not gid:
        raise ProtocoloInvalido("Pedido de desenho sem pavimento na vista")
    try:
        pav = ifc.by_guid(gid)
    except RuntimeError:
        pav = None
    if pav is None or not pav.is_a("IfcBuildingStorey"):
        raise ProtocoloInvalido(f"Pavimento invalido no pedido: {gid}")
    return pav


def _corte(f: ifcopenshell.file, pedido: dict, fase, abrir_s: float) -> dict:
    vista = pedido["vista"]
    ann = f.by_guid(vista["guid"])
    for rel in getattr(ann, "IsDefinedBy", ()) or ():
        ps = getattr(rel, "RelatingPropertyDefinition", None)
        if ps is not None and ps.is_a("IfcPropertySet") and ps.Name == "EPset_Drawing":
            for pr in getattr(ps, "HasProperties", ()) or ():
                if pr.Name in ("Scale", "HumanScale"):
                    pr.NominalValue = f.create_entity(
                        "IfcLabel", "1/1000" if pr.Name == "Scale" else "1:1000"
                    )

    elementos = pedido.get("elementos", [])
    incl = [f.by_id(i) for i, _ in elementos if not f.by_id(i).is_a("IfcOpeningElement")] + [ann]
    selecionados = {i for i, _ in elementos}

    if fase is not None:
        fase("geometria")

    st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
    st.set("dimensionality", W.SURFACES_AND_SOLIDS)
    st.set("iterator-output", W.NATIVE)
    st.set("apply-default-materials", True)
    for k in ("svg-write-poly", "svg-xmlns", "svg-poly", "svg-project", "svg-without-storeys"):
        st.set(k, True)
    st.set("elevation-ref-guid", vista["guid"])

    m = ifcopenshell.util.placement.get_local_placement(ann.ObjectPlacement)
    esc = float(vista["escala"])
    st.set("model-offset", [-float(m[0, 3]) * esc, -float(m[1, 3]) * esc, -float(m[2, 3]) * esc])

    buf = ifcopenshell.geom.serializers.buffer()
    sr = ifcopenshell.geom.serializers.svg(buf, st)
    sr.setFile(f)

    if fase is not None:
        fase("motor")

    t0 = time.perf_counter()
    num_threads = nucleos.limitar_threads(pedido.get("threads"))
    it = ifcopenshell.geom.iterator(st, f, num_threads, include=incl)
    shapes = []
    if it.initialize():
        while True:
            shapes.append(it.get())
            if not it.next():
                break
    shapes.sort(key=lambda s: s.id)
    geo_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    for sh in shapes:
        sr.write(sh)
    write_s = time.perf_counter() - t1

    t2 = time.perf_counter()
    sr.finalize()
    finalize_s = time.perf_counter() - t2

    svg = buf.get_value()
    enviados = [sh.id for sh in shapes if sh.id in selecionados]
    enviados_set = set(enviados)
    falhas = [i for i, _ in elementos if i not in enviados_set and not f.by_id(i).is_a("IfcOpeningElement")]

    return {
        "ok": True,
        "svg": svg,
        "n_paths": len(re.findall(r"<path\b", svg)),
        "enviados": enviados,
        "caixas": [],
        "falhas_geometria": falhas,
        "tempos": {
            "abrir_s": float(abrir_s),
            "geo_s": float(geo_s),
            "write_s": float(write_s),
            "finalize_s": float(finalize_s),
        },
    }


def processar(pedido: dict, fase=None) -> dict:
    try:
        t_a0 = time.perf_counter()
        f = ifcopenshell.open(pedido.get("arquivo"))
        abrir_s = time.perf_counter() - t_a0

        elementos = pedido.get("elementos", [])
        for id_step, guid in elementos:
            try:
                el = f.by_id(id_step)
            except Exception:
                el = None
            if el is None or getattr(el, "GlobalId", None) != guid:
                return {"ok": False, "erro": {"tipo": "ArquivoDivergente", "mensagem": f"ID {id_step} diverge do arquivo", "rastro": ""}}

        vista = pedido["vista"]
        if vista.get("tipo") == "CORTE":
            return _corte(f, pedido, fase, abrir_s)
        scale = float(vista["escala"])
        altura_corte_m = float(vista["altura_corte_m"])
        pav = _pavimento(f, vista)
        elevacao = float(getattr(pav, "Elevation", 0.0) or 0.0)
        section_height = altura_corte_m - elevacao * scale

        if fase is not None:
            fase("geometria")

        moveis_como_caixa = bool(pedido.get("moveis_como_caixa", True))

        selecionados = {id_step for id_step, _ in elementos}
        include_elems = []
        aberturas = set()
        moveis_elems = []
        for id_step, _ in elementos:
            el = f.by_id(id_step)
            if el is None:
                continue
            if el.is_a("IfcOpeningElement"):
                aberturas.add(id_step)
            elif moveis_como_caixa and (el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")):
                moveis_elems.append(el)
            else:
                include_elems.append(el)

        caixas_ids = []
        caixas_svg = []
        if moveis_elems:
            s_box = ifcopenshell.geom.settings()
            s_box.set(s_box.USE_WORLD_COORDS, True)
            for el in moveis_elems:
                try:
                    shape = ifcopenshell.geom.create_shape(s_box, el)
                    verts = shape.geometry.verts
                    if not verts:
                        continue
                    xs = verts[0::3]
                    ys = verts[1::3]
                    xmin, xmax = float(min(xs)), float(max(xs))
                    ymin, ymax = float(min(ys)), float(max(ys))
                    d = f"M {xmin:.6g},{-ymax:.6g} L {xmax:.6g},{-ymax:.6g} L {xmax:.6g},{-ymin:.6g} L {xmin:.6g},{-ymin:.6g} L {xmin:.6g},{-ymax:.6g}"
                    caixas_svg.append(f'<g class="{el.is_a()}" ifc:guid="{el.GlobalId}"><path d="{d}"/></g>')
                    caixas_ids.append(el.id())
                except Exception:
                    pass

        st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
        st.set("dimensionality", W.SURFACES_AND_SOLIDS)
        st.set("iterator-output", W.NATIVE)
        st.set("apply-default-materials", True)
        st.set("svg-write-poly", True)
        st.set("svg-xmlns", True)
        st.set("svg-poly", True)
        st.set("door-arcs", True)
        st.set("section-height-from-storeys", True)
        st.set("svg-project", True)
        st.set("section-height", float(section_height))

        buf = ifcopenshell.geom.serializers.buffer()
        sr = ifcopenshell.geom.serializers.svg(buf, st)
        sr.setFile(f)

        num_threads = nucleos.limitar_threads(pedido.get("threads"))

        if fase is not None:
            fase("motor")

        t_g0 = time.perf_counter()
        it = ifcopenshell.geom.iterator(st, f, num_threads, include=include_elems)
        shapes = []
        if it.initialize():
            while True:
                shapes.append(it.get())
                if not it.next():
                    break
        shapes.sort(key=lambda s: s.id)
        geo_s = time.perf_counter() - t_g0

        t_w0 = time.perf_counter()
        for sh in shapes:
            sr.write(sh)
        write_s = time.perf_counter() - t_w0

        t_f0 = time.perf_counter()
        sr.finalize()
        finalize_s = time.perf_counter() - t_f0

        svg = buf.get_value()
        svg = _somente_pavimento(svg, pav.GlobalId)

        if caixas_svg:
            bloco_caixas = "\n" + "\n".join(caixas_svg) + "\n"
            idx = svg.rfind("</svg>")
            if idx != -1:
                svg = svg[:idx] + bloco_caixas + svg[idx:]
            else:
                svg = svg + bloco_caixas

        enviados = [sh.id for sh in shapes if sh.id in selecionados]
        enviados.extend(caixas_ids)
        enviados_set = set(enviados)
        falhas = [id_step for id_step, _ in elementos if id_step not in enviados_set and id_step not in aberturas]
        n_paths = len(re.findall(r"<path\b", svg))
        tempos = {
            "abrir_s": float(abrir_s),
            "geo_s": float(geo_s),
            "write_s": float(write_s),
            "finalize_s": float(finalize_s),
        }
        return {
            "ok": True,
            "svg": svg,
            "n_paths": n_paths,
            "enviados": enviados,
            "caixas": caixas_ids,
            "falhas_geometria": falhas,
            "tempos": tempos,
        }
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
