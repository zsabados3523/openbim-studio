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
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")


def _fmt(v: float) -> str:
    return f"{round(v, 4) + 0.0:.4f}"


def _transladar_d(d: str, dx: float, dy: float) -> str:
    tokens = _TOK_RE.findall(d)
    out, i, n, cmd = [], 0, len(tokens), ""
    while i < n:
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            out.append(tok)
            i += 1
            continue
        if cmd in ("M", "L", "T", "C", "S", "Q") and i + 1 < n:
            out.append(f"{_fmt(float(tok) + dx)},{_fmt(float(tokens[i + 1]) - dy)}")
            i += 2
        elif cmd in ("A", "a") and i + 6 < n:
            rx, ry, rot, laf, sf = tokens[i : i + 5]
            out.extend([rx, ry, rot, laf, sf, f"{_fmt(float(tokens[i + 5]) + dx)},{_fmt(float(tokens[i + 6]) - dy)}"])
            i += 7
        elif cmd in ("H", "h"):
            out.append(_fmt(float(tok) + dx))
            i += 1
        elif cmd in ("V", "v"):
            out.append(_fmt(float(tok) - dy))
            i += 1
        else:
            out.append(tok)
            i += 1
    return " ".join(out)


def _clonar_path(tag_path: str, dx: float, dy: float) -> str:
    m = re.search(r'\bd\s*=\s*(["\'])(.*?)\1', tag_path)
    if not m:
        return tag_path
    novo_d = _transladar_d(m.group(2), dx, dy)
    return tag_path[: m.start(2)] + novo_d + tag_path[m.end(2) :]


def _obter_rep_id(el) -> int | None:
    try:
        rep_prod = getattr(el, "Representation", None)
        if rep_prod is None:
            return None
        reps = getattr(rep_prod, "Representations", None)
        if not reps:
            return None
        rep = reps[0]
        items = getattr(rep, "Items", ()) or ()
        for it in items:
            if it.is_a("IfcMappedItem"):
                return None
        return rep.id()
    except Exception:
        return None


def _extrair_caminhos(svg: str, guid: str) -> list[str]:
    m = re.search(r'<g\b([^>]*\b(?:ifc:)?guid=[\"\']' + re.escape(guid) + r'[\"\'][^>]*)>(.*?)</g>', svg, re.DOTALL)
    if not m or m.group(1).rstrip().endswith("/"):
        return []
    return re.findall(r"<path\b[^>]*>", m.group(2))


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

    esc = float(vista["escala"])
    prof = vista.get("profundidade_corte")
    if prof is None:
        prof = pedido.get("profundidade_corte")
    if prof is not None:
        bloco = None
        if ann.Representation and ann.Representation.Representations:
            for rep in ann.Representation.Representations:
                for itm in getattr(rep, "Items", ()) or ():
                    if itm.is_a("IfcCsgSolid"):
                        cand_bloco = getattr(itm, "TreeRootExpression", None)
                        if cand_bloco is not None and cand_bloco.is_a("IfcBlock"):
                            bloco = cand_bloco
                            break
                    elif itm.is_a("IfcBlock"):
                        bloco = itm
                        break
                if bloco is not None:
                    break
        if bloco is not None:
            prof_val = float(prof) / esc
            bloco.ZLength = prof_val
            pos = getattr(bloco, "Position", None)
            loc_antigo = getattr(pos, "Location", None) if pos else None
            coords = getattr(loc_antigo, "Coordinates", None) if loc_antigo else None
            ox = float(coords[0]) if coords and len(coords) > 0 else 0.0
            oy = float(coords[1]) if coords and len(coords) > 1 else 0.0
            pt = f.create_entity("IfcCartesianPoint", Coordinates=(ox, oy, -prof_val))
            cam_rel = getattr(getattr(ann, "ObjectPlacement", None), "RelativePlacement", None)
            if pos is None or pos == cam_rel:
                bloco.Position = f.create_entity(
                    "IfcAxis2Placement3D",
                    Location=pt,
                    Axis=getattr(pos, "Axis", None) if pos else None,
                    RefDirection=getattr(pos, "RefDirection", None) if pos else None,
                )
            else:
                pos.Location = pt

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
    orig_cam = [float(m[0, 3]) * esc, float(m[1, 3]) * esc, float(m[2, 3]) * esc]
    st.set("model-offset", [-orig_cam[0], -orig_cam[1], -orig_cam[2]])

    u_axis, v_axis, w_axis = m[:3, 0], m[:3, 1], m[:3, 2]

    elementos = pedido.get("elementos", [])
    moveis_caixa2d = bool(pedido.get("moveis_caixa2d", True))
    incl, moveis_corte = [], []
    s_box = ifcopenshell.geom.settings()
    s_box.set(s_box.USE_WORLD_COORDS, True)
    for i, _ in elementos:
        el = f.by_id(i)
        if el is None or el.is_a("IfcOpeningElement"):
            continue
        is_movel = el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")
        if is_movel and moveis_caixa2d:
            cruza, us, vs = False, [], []
            try:
                shape = ifcopenshell.geom.create_shape(s_box, el)
                verts = shape.geometry.verts
                if verts and len(verts) >= 3:
                    ws = []
                    for k in range(0, len(verts), 3):
                        diff = [verts[k] - orig_cam[0], verts[k + 1] - orig_cam[1], verts[k + 2] - orig_cam[2]]
                        us.append(diff[0] * u_axis[0] + diff[1] * u_axis[1] + diff[2] * u_axis[2])
                        vs.append(diff[0] * v_axis[0] + diff[1] * v_axis[1] + diff[2] * v_axis[2])
                        ws.append(diff[0] * w_axis[0] + diff[1] * w_axis[1] + diff[2] * w_axis[2])
                    cruza = (min(ws) <= 0.0 <= max(ws))
            except Exception:
                pass
            if us and vs:
                moveis_corte.append((el, min(us), max(us), min(vs), max(vs), cruza))
        else:
            incl.append(el)
    incl.append(ann)
    selecionados = {i for i, _ in elementos}

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
    caixas_ids, caixas_svg = [], []
    if moveis_corte:
        m_m3 = re.search(
            r'ifc:matrix3="\[\[\s*[-+0-9.eE]+\s*,\s*[-+0-9.eE]+\s*,\s*([-+0-9.eE]+)\s*\]\s*,\s*\[\s*[-+0-9.eE]+\s*,\s*[-+0-9.eE]+\s*,\s*([-+0-9.eE]+)\s*\]',
            svg,
        )
        if m_m3:
            tx, ty = float(m_m3.group(1)), float(m_m3.group(2))
        else:
            m_vb = re.search(r'viewBox="[-+0-9.eE]+\s+[-+0-9.eE]+\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)"', svg)
            tx = float(m_vb.group(1)) / 2.0 if m_vb else 0.0
            ty = float(m_vb.group(2)) / 2.0 if m_vb else 0.0
        for el, min_u, max_u, min_v, max_v, cruza in moveis_corte:
            try:
                x0, x1 = min_u + tx, max_u + tx
                y0, y1 = ty - max_v, ty - min_v
                d = f"M {x0:.4f},{y0:.4f} L {x1:.4f},{y0:.4f} L {x1:.4f},{y1:.4f} L {x0:.4f},{y1:.4f} L {x0:.4f},{y0:.4f}"
                cls_p = "cut" if cruza else "boundary"
                caixas_svg.append(f'<g class="{el.is_a()}" ifc:guid="{el.GlobalId}"><path d="{d}" class="{cls_p}"/></g>')
                caixas_ids.append(el.id())
            except Exception:
                pass

        if caixas_svg:
            if "xmlns:ifc=" not in svg:
                svg = re.sub(r"(<svg\b[^>]*)", r'\1 xmlns:ifc="http://www.ifcopenshell.org/ns"', svg, count=1)
            if svg.rstrip().endswith("/>"):
                svg = svg.rstrip()[:-2] + "></svg>"
            bloco = "\n" + "\n".join(caixas_svg) + "\n"
            idx = svg.rfind("</svg>")
            svg = (svg[:idx] + bloco + svg[idx:]) if idx != -1 else (svg + bloco)

    enviados = [sh.id for sh in shapes if sh.id in selecionados]
    enviados.extend(caixas_ids)
    enviados_set = set(enviados)
    falhas = [i for i, _ in elementos if i not in enviados_set and not f.by_id(i).is_a("IfcOpeningElement")]

    return {
        "ok": True,
        "svg": svg,
        "n_paths": len(re.findall(r"<path\b", svg)),
        "enviados": enviados,
        "caixas": caixas_ids,
        "em_cache": [],
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

        cache_tipo = bool(pedido.get("cache_tipo", True))
        moveis_como_caixa = bool(pedido.get("moveis_como_caixa", True))

        selecionados = {id_step for id_step, _ in elementos}
        include_elems = []
        aberturas = set()
        moveis_elems = []
        primarias = {}
        replicas = []

        for id_step, _ in elementos:
            el = f.by_id(id_step)
            if el is None:
                continue
            if el.is_a("IfcOpeningElement"):
                aberturas.add(id_step)
            elif moveis_como_caixa and (el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")):
                moveis_elems.append(el)
            else:
                if cache_tipo:
                    rep_id = _obter_rep_id(el)
                    if rep_id is not None:
                        try:
                            m = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)
                            pure_z = (
                                abs(float(m[2, 2]) - 1.0) < 1e-4
                                and abs(float(m[0, 2])) < 1e-4
                                and abs(float(m[1, 2])) < 1e-4
                                and abs(float(m[2, 0])) < 1e-4
                                and abs(float(m[2, 1])) < 1e-4
                            )
                            if not pure_z:
                                include_elems.append(el)
                                continue
                            x_pos = float(m[0, 3]) * scale
                            y_pos = float(m[1, 3]) * scale
                            z_pos = float(m[2, 3]) * scale
                            rel_z = round(altura_corte_m - z_pos, 4) + 0.0
                            rot_2x2 = tuple(round(float(m[r, c]), 4) + 0.0 for r in (0, 1) for c in (0, 1))
                            chave = (rep_id, el.is_a(), rel_z, rot_2x2)
                            if chave not in primarias:
                                primarias[chave] = (el, x_pos, y_pos)
                                include_elems.append(el)
                            else:
                                prim_el, px, py = primarias[chave]
                                dx = x_pos - px
                                dy = y_pos - py
                                replicas.append((el, prim_el, dx, dy))
                            continue
                        except Exception:
                            pass
                include_elems.append(el)

        caixas_ids = []
        caixas_svg = []
        moveis_excluidos = set()
        if moveis_elems:
            s_box = ifcopenshell.geom.settings()
            s_box.set(s_box.USE_WORLD_COORDS, True)
            for el in moveis_elems:
                try:
                    shape = ifcopenshell.geom.create_shape(s_box, el)
                    verts = shape.geometry.verts
                    if not verts or len(verts) < 3:
                        continue
                    zs = verts[2::3]
                    zmin = float(min(zs))
                    if zmin > altura_corte_m:
                        moveis_excluidos.add(el.id())
                        continue
                    xs = verts[0::3]
                    ys = verts[1::3]
                    xmin, xmax = float(min(xs)), float(max(xs))
                    ymin, ymax = float(min(ys)), float(max(ys))
                    d = f"M {xmin:.4f},{-ymax:.4f} L {xmax:.4f},{-ymax:.4f} L {xmax:.4f},{-ymin:.4f} L {xmin:.4f},{-ymin:.4f} L {xmin:.4f},{-ymax:.4f}"
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

        if re.search(r"<svg\b[^>]*/>", svg):
            svg = re.sub(r"(<svg\b[^>]*?)/[ \t]*>", r"\1></svg>", svg, count=1)
        elif "</svg>" not in svg:
            if "<svg" in svg:
                svg = svg + "</svg>"
            else:
                svg = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ifc="http://www.ifcopenshell.org/ns"></svg>'

        shapes_ids = {sh.id for sh in shapes}
        em_cache_ids, replicas_sem_linhas, replicas_svg = [], [], []
        if replicas:
            caminhos_primarias = {}
            for rep_el, prim_el, dx, dy in replicas:
                if prim_el.id() not in shapes_ids:
                    continue
                prim_gid = prim_el.GlobalId
                if prim_gid not in caminhos_primarias:
                    caminhos_primarias[prim_gid] = _extrair_caminhos(svg, prim_gid)
                caminhos = caminhos_primarias[prim_gid]
                if caminhos:
                    novos_paths = [_clonar_path(p, dx, dy) for p in caminhos]
                    replicas_svg.append(f'<g class="{rep_el.is_a()}" ifc:guid="{rep_el.GlobalId}">{"".join(novos_paths)}</g>')
                    em_cache_ids.append(rep_el.id())
                else:
                    replicas_sem_linhas.append(rep_el.id())

        extra_svg = replicas_svg + caixas_svg
        if extra_svg:
            if "xmlns:ifc=" not in svg:
                svg = re.sub(r"(<svg\b[^>]*)", r'\1 xmlns:ifc="http://www.ifcopenshell.org/ns"', svg, count=1)
            bloco_extra = "\n" + "\n".join(extra_svg) + "\n"
            idx = svg.rfind("</svg>")
            if idx != -1:
                svg = svg[:idx] + bloco_extra + svg[idx:]
            else:
                svg = svg + bloco_extra

        enviados = [sh.id for sh in shapes if sh.id in selecionados]
        enviados.extend(caixas_ids)
        enviados.extend(em_cache_ids)
        enviados.extend(replicas_sem_linhas)
        enviados_set = set(enviados)
        falhas = [
            id_step for id_step, _ in elementos
            if id_step not in enviados_set and id_step not in aberturas and id_step not in moveis_excluidos
        ]
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
            "em_cache": em_cache_ids,
            "falhas_geometria": falhas,
            "tempos": tempos,
        }
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
