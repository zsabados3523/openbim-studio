# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de desenho de planta (modo pavimento do motor SVG, sem criar entidade no arquivo)."""
import contextlib
import functools
import inspect
import math
import os
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.ifcopenshell_wrapper as W
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
import shapely
from obim_geometria import (
    aneis,
    cache_geometria,
    cache_leitura,
    construtor,
    corte_plano,
    faixas,
    nucleos,
    oclusores,
    peca_cortada,
    peca_visivel,
    planta_cache,
    silhueta,
    visibilidade,
)


def caixa_valida(c) -> list[float] | None:
    if not isinstance(c, (list, tuple)) or len(c) < 6:
        return None
    try:
        floats = [float(x) for x in c[:6]]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in floats):
        return None
    if floats[0] > floats[3] or floats[1] > floats[4] or floats[2] > floats[5]:
        return None
    return floats


_GRUPO = re.compile(r"<g\b[^>]*?(/?)>|</g>")
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")


def _fmt(v: float) -> str:
    return f"{round(v, 4) + 0.0:.4f}"


def _d_silhueta(aneis) -> str:
    partes = []
    for anel in aneis:
        pts = [(float(x), -float(y)) for x, y in anel]
        if len(pts) < 3:
            continue
        partes.append("M " + " L ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts) + " Z")
    return " ".join(partes)


def _limiar_pesado(pedido: dict) -> int:
    try:
        return int(pedido.get("limiar_pesado", silhueta.LIMIAR_PADRAO))
    except (TypeError, ValueError):
        return silhueta.LIMIAR_PADRAO


def _candidata_silhueta(el, moveis_como_caixa: bool) -> bool:
    if el.is_a("IfcDoor") or el.is_a("IfcWindow"):
        return False
    try:
        if getattr(el, "HasOpenings", None):
            return False
    except Exception:
        pass
    if moveis_como_caixa and (el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")):
        return False
    return True


def _grupo_silhueta(el, aneis) -> str | None:
    d = _d_silhueta(aneis)
    if not d:
        return None
    return f'<g class="{el.is_a()}" ifc:guid="{el.GlobalId}" data-silhueta="1"><path d="{d}" fill-rule="evenodd"/></g>'


class _FormaId:
    """Envolve forma do iterador expondo `.id()` compatível com `entity_instance`."""

    def __init__(self, id_step: int, forma):
        self._id = id_step
        self._forma = forma

    def id(self) -> int:
        return self._id

    def __getattr__(self, nome):
        return getattr(self._forma, nome)


def _pesadas_para_svg(
    f: ifcopenshell.file, pedido: dict, elementos, altura_corte_m: float, formas: dict | None = None
):
    """Silhuetas do pedido inteiro (usado pelo pai das faixas): svg, info, ids desenhados, ids fora do corte."""
    pesados_svg, pesados_info, ids, excluidos = [], [], set(), set()
    if pedido.get("pesados") != "silhueta":
        return pesados_svg, pesados_info, ids, excluidos
    limiar = _limiar_pesado(pedido)
    moveis_como_caixa = bool(pedido.get("moveis_como_caixa", False))
    candidatos = []
    for id_step, _ in elementos:
        el = f.by_id(id_step)
        if el is None or el.is_a("IfcOpeningElement"):
            continue
        if not _candidata_silhueta(el, moveis_como_caixa):
            continue
        candidatos.append((id_step, el))
    if isinstance(formas, dict):
        faltantes, vistos = [], set()
        for id_step, el in candidatos:
            if id_step not in formas and id_step not in vistos:
                faltantes.append(el)
                vistos.add(id_step)
        if faltantes:
            formas.update(silhueta.formas_do_mundo(f, faltantes, threads=pedido.get("threads")))
    for id_step, el in candidatos:
        forma = formas.get(id_step) if isinstance(formas, dict) else None
        alvo = _FormaId(el.id(), forma) if hasattr(forma, "geometry") else el
        n_faces, aneis, zmin = silhueta.faces_e_silhueta(alvo, limiar, z_corte=altura_corte_m)
        if not silhueta.eh_pesada(n_faces, limiar):
            continue
        if aneis is None or (zmin is not None and zmin > altura_corte_m):
            excluidos.add(id_step)
            continue
        grupo = _grupo_silhueta(el, aneis)
        if grupo is None:
            continue
        pesados_svg.append(grupo)
        pesados_info.append({"guid": el.GlobalId, "id": el.id(), "faces": int(n_faces)})
        ids.add(id_step)
    return pesados_svg, pesados_info, ids, excluidos


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


def _isolar_pavimento(f: ifcopenshell.file, pav) -> None:
    """Tira da copia em memoria (do filho) os outros pavimentos: o serializador repete a projecao em cada um (custo ~ n de pavimentos)."""
    for s in list(f.by_type("IfcBuildingStorey")):
        if s.id() != pav.id():
            f.remove(s)


def _fmt6(v: float) -> str:
    return f"{round(float(v), 6) + 0.0:.6f}"


def _anel_d(coords, tx: float, ty: float) -> str | None:
    pts = [(float(c[0]) + tx, ty - float(c[1])) for c in coords]
    if len(pts) < 3:
        return None
    if pts[-1] != pts[0]:
        pts.append(pts[0])
    cmds = [f"M {_fmt6(pts[0][0])},{_fmt6(pts[0][1])}"]
    cmds.extend(f"L {_fmt6(x)},{_fmt6(y)}" for x, y in pts[1:])
    return " ".join(cmds)


def _injetar_motor_corte(svg: str, els: list, pols_linhas: list, pols_tampas: list) -> str:
    """Injeta linhas de projeção e tampas do motor lateral no SVG do corte."""
    tx, ty = _tx_ty(svg)
    proj_paths = []
    for polilinhas in pols_linhas:
        for poli in polilinhas:
            pts = np.asarray(poli, dtype=np.float64)
            if pts.ndim != 2 or pts.shape[0] < 2 or pts.shape[1] < 2:
                continue
            cmds = [f"M {_fmt6(pts[0, 0] + tx)},{_fmt6(ty - pts[0, 1])}"]
            cmds.extend(f"L {_fmt6(p[0] + tx)},{_fmt6(ty - p[1])}" for p in pts[1:])
            proj_paths.append(f'<path d="{" ".join(cmds)}"/>')

    tampas_svg = []
    for el, polys in zip(els, pols_tampas):
        if not polys:
            continue
        subpaths = []
        for poly in polys:
            if poly.is_empty or poly.area <= 1e-12:
                continue
            d_ext = _anel_d(poly.exterior.coords, tx, ty)
            if not d_ext:
                continue
            subpaths.append(d_ext)
            for interior in poly.interiors:
                d_int = _anel_d(interior.coords, tx, ty)
                if d_int:
                    subpaths.append(d_int)
        if subpaths:
            tampas_svg.append(
                f'<g class="{el.is_a()}" ifc:guid="{el.GlobalId}"><path d="{" ".join(subpaths)}" fill-rule="evenodd"/></g>'
            )

    if "xmlns:ifc=" not in svg:
        svg = re.sub(r"(<svg\b[^>]*)", r'\1 xmlns:ifc="http://www.ifcopenshell.org/ns"', svg, count=1)
    if svg.rstrip().endswith("/>"):
        svg = svg.rstrip()[:-2] + "></svg>"
    proj_match = _PROJ_RE.search(svg)
    if proj_match is not None:
        if proj_paths:
            svg = svg[: proj_match.end(1)] + "\n" + "\n".join(proj_paths) + "\n" + svg[proj_match.end(1) :]
    else:
        proj_self = re.search(r'<g\b[^>]*\bclass=["\']projection["\'][^>]*/>', svg)
        bloco_proj = '<g class="projection">\n' + "\n".join(proj_paths) + ("\n" if proj_paths else "") + "</g>"
        if proj_self is not None:
            svg = svg[: proj_self.start()] + bloco_proj + svg[proj_self.end() :]
        else:
            tampas_svg.append(bloco_proj)
    if tampas_svg:
        bloco = "\n" + "\n".join(tampas_svg) + "\n"
        idx = svg.rfind("</svg>")
        svg = (svg[:idx] + bloco + svg[idx:]) if idx != -1 else (svg + bloco)
    return svg


def _kw_ifc(f: ifcopenshell.file) -> dict:
    if f.schema != "IFC2X3":
        return {}
    oh = f.by_type("IfcOwnerHistory")
    if not oh:
        raise ValueError("IFC2X3 sem IfcOwnerHistory: não dá para gravar vista")
    return {"OwnerHistory": oh[0]}


def _bloco_de(ann):
    rep_prod = getattr(ann, "Representation", None)
    for rep in getattr(rep_prod, "Representations", ()) or ():
        for itm in getattr(rep, "Items", ()) or ():
            if itm.is_a("IfcCsgSolid"):
                cand = getattr(itm, "TreeRootExpression", None)
                if cand is not None and cand.is_a("IfcBlock"):
                    return cand
            elif itm.is_a("IfcBlock"):
                return itm
    return None


def _garantir_anotacao(f: ifcopenshell.file, vista: dict) -> None:
    """Garante IfcAnnotation da vista no modelo em memória com matriz e bloco do pedido."""
    gid = vista["guid"]
    try:
        ann = f.by_guid(gid)
    except Exception:
        ann = None
    if "matriz" not in vista or "bloco" not in vista:
        if ann is not None:
            return
        raise RuntimeError(f"Instance with GlobalId '{gid}' not found")

    if ann is None:
        kw = _kw_ifc(f)
        nome = vista.get("nome") or "CORTE"
        ann = f.create_entity("IfcAnnotation", GlobalId=gid, Name=nome, ObjectType="DRAWING", **kw)
        if f.schema.startswith("IFC4X3"):
            ann.PredefinedType = "USERDEFINED"
        props = [
            f.create_entity("IfcPropertySingleValue", Name=k, NominalValue=f.create_entity("IfcLabel", v))
            for k, v in (("TargetView", "SECTION_VIEW"), ("Scale", "1/100"), ("HumanScale", "1:100"))
        ]
        ps = f.create_entity(
            "IfcPropertySet",
            GlobalId=ifcopenshell.guid.new(),
            Name="EPset_Drawing",
            HasProperties=props,
            **kw,
        )
        f.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=[ann],
            RelatingPropertyDefinition=ps,
            **kw,
        )

    elif vista.get("nome"):
        ann.Name = str(vista["nome"])

    m = np.array(vista["matriz"], dtype=float)
    pt = f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(x) for x in m[:3, 3]))
    eixo = f.create_entity(
        "IfcAxis2Placement3D",
        Location=pt,
        Axis=f.create_entity("IfcDirection", DirectionRatios=tuple(float(x) for x in m[:3, 2])),
        RefDirection=f.create_entity("IfcDirection", DirectionRatios=tuple(float(x) for x in m[:3, 0])),
    )
    ann.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=eixo)

    bl = vista["bloco"]
    loc = tuple(float(x) for x in bl["Location"])
    bloco = _bloco_de(ann)
    if bloco is None:
        ctx = [c for c in f.by_type("IfcGeometricRepresentationContext") if c.ContextType == "Model"]
        if not ctx:
            ctx = [ifcopenshell.api.run("context.add_context", f, context_type="Model")]
        pos_b = f.create_entity(
            "IfcAxis2Placement3D",
            Location=f.create_entity("IfcCartesianPoint", Coordinates=loc),
        )
        bloco = f.create_entity(
            "IfcBlock",
            Position=pos_b,
            XLength=float(bl["XLength"]),
            YLength=float(bl["YLength"]),
            ZLength=float(bl["ZLength"]),
        )
        forma = f.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=ctx[0],
            RepresentationIdentifier="Body",
            RepresentationType="SolidModel",
            Items=[f.create_entity("IfcCsgSolid", TreeRootExpression=bloco)],
        )
        ann.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    else:
        bloco.XLength = float(bl["XLength"])
        bloco.YLength = float(bl["YLength"])
        bloco.ZLength = float(bl["ZLength"])
        cam_rel = getattr(getattr(ann, "ObjectPlacement", None), "RelativePlacement", None)
        pos_b = getattr(bloco, "Position", None)
        pt_b = f.create_entity("IfcCartesianPoint", Coordinates=loc)
        if pos_b is None or pos_b == cam_rel:
            bloco.Position = f.create_entity("IfcAxis2Placement3D", Location=pt_b)
        else:
            pos_b.Location = pt_b
            pos_b.Axis = None
            pos_b.RefDirection = None


def _corte(f: ifcopenshell.file, pedido: dict, fase, abrir_s: float) -> dict:
    vista = pedido["vista"]
    _garantir_anotacao(f, vista)
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
    bloco = _bloco_de(ann)
    if prof is not None and bloco is not None:
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

    orig_cam_m = orig_cam
    elementos = pedido.get("elementos", [])
    moveis_caixa2d = bool(pedido.get("moveis_caixa2d", False))
    caixas_coords = pedido.get("caixas_coords") or {}
    incl, moveis_corte = [], []
    s_box = ifcopenshell.geom.settings()
    s_box.set(s_box.USE_WORLD_COORDS, True)
    for i, _ in elementos:
        el = f.by_id(i)
        if el is None or el.is_a("IfcOpeningElement"):
            continue
        is_movel = el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")
        if is_movel and moveis_caixa2d:
            c = caixa_valida(caixas_coords.get(el.id()) if el.id() in caixas_coords else caixas_coords.get(str(el.id())))
            if c is not None:
                corners = [[x, y, z] for x in (c[0], c[3]) for y in (c[1], c[4]) for z in (c[2], c[5])]
                us, vs, ws = [], [], []
                for x, y, z in corners:
                    diff = [x - orig_cam_m[0], y - orig_cam_m[1], z - orig_cam_m[2]]
                    us.append(diff[0] * u_axis[0] + diff[1] * u_axis[1] + diff[2] * u_axis[2])
                    vs.append(diff[0] * v_axis[0] + diff[1] * v_axis[1] + diff[2] * v_axis[2])
                    ws.append(diff[0] * w_axis[0] + diff[1] * w_axis[1] + diff[2] * w_axis[2])
                cruza = (min(ws) <= 0.0 <= max(ws))
                moveis_corte.append((el, min(us), max(us), min(vs), max(vs), cruza))
            else:
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
    selecionados = {i for i, _ in elementos}
    num_threads = nucleos.limitar_threads(pedido.get("threads"))

    motor_visivel = bool(pedido.get("motor_visivel"))
    elegiveis, pols_linhas, pols_tampas, motor_ids = [], [], [], []
    motor_geo_s, motor_s = 0.0, 0.0

    buf = ifcopenshell.geom.serializers.buffer()
    sr = ifcopenshell.geom.serializers.svg(buf, st)
    sr.setFile(f)

    def _janela_bloco():
        if (
            bloco is None
            or getattr(bloco, "XLength", None) is None
            or getattr(bloco, "YLength", None) is None
        ):
            raise ValueError("vista sem dimensoes de janela")
        largura = float(bloco.XLength) * esc
        altura = float(bloco.YLength) * esc
        if not (math.isfinite(largura) and math.isfinite(altura) and largura > 0.0 and altura > 0.0):
            raise ValueError("vista sem dimensoes de janela")
        return (-largura / 2.0, largura / 2.0, -altura / 2.0, altura / 2.0)

    def _na_janela(el, janela):
        if not caixas_coords:
            return True
        c = caixa_valida(caixas_coords.get(el.id()) if el.id() in caixas_coords else caixas_coords.get(str(el.id())))
        if c is None:
            return True
        us, vs = [], []
        for x in (c[0], c[3]):
            for y in (c[1], c[4]):
                for z in (c[2], c[5]):
                    dx, dy, dz = x - orig_cam_m[0], y - orig_cam_m[1], z - orig_cam_m[2]
                    us.append(dx * u_axis[0] + dy * u_axis[1] + dz * u_axis[2])
                    vs.append(dx * v_axis[0] + dy * v_axis[1] + dz * v_axis[2])
        return not (
            max(us) < janela[0] - 0.1
            or min(us) > janela[1] + 0.1
            or max(vs) < janela[2] - 0.1
            or min(vs) > janela[3] + 0.1
        )

    janela, incl_podada, geo_ok = None, None, False
    if motor_visivel and incl:
        try:
            janela = _janela_bloco()
            incl_podada = [el for el in incl if _na_janela(el, janela)]
            cands = [
                el for el in incl_podada
                if not el.is_a("IfcDoor") and not el.is_a("IfcWindow")
                and not getattr(el, "HasOpenings", None) and getattr(el, "Representation", None) is not None
            ]
            if cands:
                t_mg0 = time.perf_counter()
                try:
                    formas = silhueta.formas_do_mundo(f, cands, threads=num_threads)
                    for el in cands:
                        dados = _malha_caixa(formas.get(el.id()))
                        if dados is not None:
                            elegiveis.append((el, dados[0], dados[1]))
                finally:
                    motor_geo_s = time.perf_counter() - t_mg0
            geo_ok = True
        except Exception:
            elegiveis, geo_ok = [], False

    if fase is not None:
        fase("motor")

    if motor_visivel and elegiveis:
        t_m0 = time.perf_counter()
        try:
            if prof is not None:
                prof_motor = float(prof)
            elif bloco is not None and getattr(bloco, "ZLength", None) is not None:
                prof_motor = float(bloco.ZLength) * esc
            else:
                raise ValueError("vista sem profundidade de corte")
            quadro = SimpleNamespace(
                origem=np.asarray(m[:3, 3], dtype=np.float64) * esc,
                u=np.asarray(m[:3, 0], dtype=np.float64),
                v=np.asarray(m[:3, 1], dtype=np.float64),
                w=np.asarray(m[:3, 2], dtype=np.float64),
            )
            pols_linhas = visibilidade.linhas_visiveis_vista(
                [(v, t) for _el, v, t in elegiveis], quadro, profundidade=prof_motor, janela=janela
            )
            pols_tampas = [visibilidade.secao_plana(v, t, quadro, janela=janela) for _el, v, t in elegiveis]
            motor_ids = [el.id() for el, _v, _t in elegiveis]
            motor_set = set(motor_ids)
            incl = [el for el in incl_podada if el.id() not in motor_set]
        except Exception:
            pols_linhas, pols_tampas, motor_ids = [], [], []
        motor_s = time.perf_counter() - t_m0
    elif motor_visivel and geo_ok:
        incl = incl_podada

    incl.append(ann)

    t0 = time.perf_counter()
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

    if motor_ids:
        svg = _injetar_motor_corte(svg, [el for el, _v, _t in elegiveis], pols_linhas, pols_tampas)

    enviados = [sh.id for sh in shapes if sh.id in selecionados]
    enviados.extend(caixas_ids)
    enviados.extend(motor_ids)
    enviados_set = set(enviados)
    falhas = [i for i, _ in elementos if i not in enviados_set and not f.by_id(i).is_a("IfcOpeningElement")]

    tempos = {
        "abrir_s": float(abrir_s),
        "geo_s": float(geo_s + motor_geo_s),
        "write_s": float(write_s),
        "finalize_s": float(finalize_s),
    }
    if motor_visivel:
        tempos["motor_s"] = float(motor_s)
    resp = {
        "ok": True,
        "svg": svg,
        "n_paths": len(re.findall(r"<path\b", svg)),
        "enviados": enviados,
        "caixas": caixas_ids,
        "em_cache": [],
        "falhas_geometria": falhas,
        "tempos": tempos,
    }
    if motor_visivel:
        resp["motor_pecas"] = motor_ids
    return resp


_PROJ_RE = re.compile(r'<g\b[^>]*\bclass=["\']projection["\'][^>]*>(.*?)</g>', re.S)
_PATH_RE = re.compile(r"<path\b[^>]*>", re.S)
_D_ATTR = re.compile(r'\bd\s*=\s*(["\'])(.*?)\1', re.S)
_PRODUTO_RE = re.compile(r'<g\b[^>]*\bid=["\']product-[^"\']*["\'][^>]*>.*?</g>\s*', re.S)
_GUID_ATTR = re.compile(r'\bifc:guid\s*=\s*["\']([^"\']*)["\']')


def _tx_ty(svg: str) -> tuple[float, float]:
    """Deslocamento do SVG: meia largura/altura do viewBox (não ler matrix3: locale)."""
    raiz = re.search(r"<svg\b[^>]*>", svg, re.S | re.I)
    vb = re.search(r'\bviewBox\s*=\s*["\']([^"\']*)["\']', raiz.group(0), re.I) if raiz else None
    if vb is None:
        return 0.0, 0.0
    nums = re.findall(r'[-+]?(?:\d*[.,]\d+|\d+)(?:[eE][-+]?\d+)?', vb.group(1))
    try:
        vals = [float(t.replace(",", ".")) for t in nums[:4]]
    except ValueError:
        return 0.0, 0.0
    if len(vals) < 4:
        return 0.0, 0.0
    return vals[2] / 2.0, vals[3] / 2.0


def _polilinhas_d(d: str) -> list[list[tuple[float, float]]]:
    toks = _TOK_RE.findall(d)
    runs, atual, cmd, i = [], None, "", 0
    while i < len(toks):
        tok = toks[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            continue
        if cmd in ("M", "L") and i + 1 < len(toks):
            try:
                p = (float(tok), float(toks[i + 1]))
            except ValueError:
                i += 1
                continue
            if cmd == "M" or atual is None:
                if atual:
                    runs.append(atual)
                atual = [p]
            else:
                atual.append(p)
            i += 2
        else:
            i += 1
    if atual:
        runs.append(atual)
    return runs


def _recortar_segmento(p, q, xa, xb):
    x0, y0 = p
    x1, y1 = q
    dx = x1 - x0
    t0, t1 = 0.0, 1.0
    if dx == 0.0:
        if (xa is not None and x0 < xa) or (xb is not None and x0 > xb):
            return None
    else:
        if xa is not None:
            t = (xa - x0) / dx
            if dx > 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
        if xb is not None:
            t = (xb - x0) / dx
            if dx > 0:
                t1 = min(t1, t)
            else:
                t0 = max(t0, t)
    if t0 > t1:
        return None
    a = (x0 + t0 * dx, y0 + t0 * (y1 - y0))
    b = (x0 + t1 * dx, y0 + t1 * (y1 - y0))
    if xb is not None and a[0] == xb and b[0] == xb:
        return None
    return a, b


def _recortar_d(d: str, xa: float | None, xb: float | None, fmt=lambda v: f"{v:.9g}") -> list[str]:
    saida = []
    for pts in _polilinhas_d(d):
        runs = []
        atual = []
        for p, q in zip(pts, pts[1:]):
            c = _recortar_segmento(p, q, xa, xb)
            if c is None:
                if atual:
                    runs.append(atual)
                    atual = []
                continue
            a, b = c
            if atual and abs(atual[-1][0] - a[0]) <= 1e-9 and abs(atual[-1][1] - a[1]) <= 1e-9:
                atual.append(b)
            else:
                if atual:
                    runs.append(atual)
                atual = [a, b]
        if atual:
            runs.append(atual)
        for run in runs:
            if len(run) >= 2:
                saida.append("M" + " L".join(f"{fmt(x)},{fmt(y)}" for x, y in run))
    return saida


def _filtrar_grupos(svg: str, guids: set[str]) -> str:
    def manter(m):
        achado = _GUID_ATTR.search(m.group(0))
        return m.group(0) if achado is not None and achado.group(1) in guids else ""

    return _PRODUTO_RE.sub(manter, svg)


def _recortar_svg_faixa(svg: str, faixa: dict, donos_guids: set[str]) -> str:
    tx, _ty = _tx_ty(svg)
    u0, u1 = faixa.get("u0"), faixa.get("u1")
    xa = None if u0 is None else float(u0) + tx
    xb = None if u1 is None else float(u1) + tx
    m = _PROJ_RE.search(svg)
    if m is not None and (xa is not None or xb is not None):
        novos = []
        for tag in _PATH_RE.findall(m.group(1)):
            dm = _D_ATTR.search(tag)
            if dm is None:
                continue
            novos.extend(f'<path d="{d}"/>' for d in _recortar_d(dm.group(2), xa, xb))
        svg = svg[: m.start(1)] + "\n" + "\n".join(novos) + "\n" + svg[m.end(1) :]
    return _filtrar_grupos(svg, donos_guids)


def _itens_das_faixas(f: ifcopenshell.file, pedido: dict):
    vista = pedido["vista"]
    _garantir_anotacao(f, vista)
    ann = f.by_guid(vista["guid"])
    esc = float(vista["escala"])
    m = ifcopenshell.util.placement.get_local_placement(ann.ObjectPlacement)
    orig = [float(m[0, 3]) * esc, float(m[1, 3]) * esc, float(m[2, 3]) * esc]
    u_axis = m[:3, 0]
    coords = pedido.get("caixas_coords") or {}
    moveis_caixa2d = bool(pedido.get("moveis_caixa2d", False))
    itens, primeira = [], set()
    for i, guid in pedido.get("elementos", []):
        c = caixa_valida(coords.get(i) if i in coords else coords.get(str(i)))
        el = f.by_id(i)
        if c is None or el is None:
            return None
        us = []
        for x in (c[0], c[3]):
            for y in (c[1], c[4]):
                for z in (c[2], c[5]):
                    diff = (x - orig[0], y - orig[1], z - orig[2])
                    us.append(diff[0] * float(u_axis[0]) + diff[1] * float(u_axis[1]) + diff[2] * float(u_axis[2]))
        itens.append((i, guid, min(us), max(us)))
        if moveis_caixa2d and (el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")):
            primeira.add(i)
    return itens, primeira


def _corte_em_faixas(f: ifcopenshell.file, pedido: dict, fase, abrir_s: float) -> dict:
    n = faixas._validar_n(pedido.get("faixas"))

    def normal() -> dict:
        return _corte(f, pedido, fase, abrir_s)

    if n == 1 or not pedido.get("elementos"):
        return normal()
    dados = _itens_das_faixas(f, pedido)
    if dados is None:
        return normal()
    itens, primeira = dados
    if not itens:
        return normal()
    limites = faixas.limites(itens, n, so_primeira=primeira)
    if len(limites) <= 1:
        return normal()
    divisao = faixas.dividir(itens, n, so_primeira=primeira)
    total_threads = nucleos.limitar_threads(pedido.get("threads"))
    simultaneos = max(1, min(len(limites), total_threads))
    threads_filho = max(1, total_threads // simultaneos)

    pedidos = []
    for k, (a, b) in enumerate(limites):
        donos = []
        for i, _guid, u0, u1 in itens:
            if i in primeira:
                if k == 0:
                    donos.append(i)
                continue
            centro = (u0 + u1) / 2.0
            if (a is None or centro >= a) and (b is None or centro < b):
                donos.append(i)
        q = dict(pedido)
        q.pop("faixas", None)
        q["elementos"] = [list(e) for e in divisao[k]]
        q["faixa"] = {"u0": a, "u1": b, "donos": donos}
        q["threads"] = threads_filho
        pedidos.append(q)

    try:
        with ThreadPoolExecutor(max_workers=simultaneos) as ex:
            futuros = [ex.submit(faixas.rodar_filho, q) for q in pedidos]
            resultados = [fut.result() for fut in futuros]
        for r in resultados:
            if isinstance(r, dict) and not r.get("ok") and (r.get("erro") or {}).get("tipo") == "Divergente":
                return r
        if any(not isinstance(r, dict) or not r.get("ok") or not r.get("svg") for r in resultados):
            return normal()
        svg = faixas.unir([r["svg"] for r in resultados])
    except Exception:
        return normal()

    enviados, caixas = [], []
    for r in resultados:
        enviados.extend(r.get("enviados") or ())
        caixas.extend(r.get("caixas") or ())
    enviados = list(dict.fromkeys(enviados))
    caixas = list(dict.fromkeys(caixas))
    enviados_set = set(enviados)
    falhas = [
        i for i, _ in pedido.get("elementos", [])
        if i not in enviados_set and not f.by_id(i).is_a("IfcOpeningElement")
    ]
    tempos = {
        "abrir_s": float(abrir_s),
        "geo_s": float(sum(float((r.get("tempos") or {}).get("geo_s", 0.0)) for r in resultados)),
        "write_s": float(sum(float((r.get("tempos") or {}).get("write_s", 0.0)) for r in resultados)),
        "finalize_s": float(sum(float((r.get("tempos") or {}).get("finalize_s", 0.0)) for r in resultados)),
    }
    return {
        "ok": True,
        "svg": svg,
        "n_paths": len(re.findall(r"<path\b", svg)),
        "enviados": enviados,
        "caixas": caixas,
        "em_cache": [],
        "falhas_geometria": falhas,
        "tempos": tempos,
    }


_ARQ_LOTE: dict[tuple[str, str | None, bool], object] | None = None
_LOTE_TLS = threading.local()


def _abrir_ifc(caminho, pavimento: str | None = None, lazy: bool = False):
    """Abre o IFC, reaproveitando por `(caminho, pavimento, lazy)` durante `processar_lote`."""
    cache = getattr(_LOTE_TLS, "cache", None)
    if cache is None:
        cache = _ARQ_LOTE
    if cache is not None and caminho is not None:
        chave = (str(caminho), pavimento, bool(lazy))
        if chave not in cache:
            cache[chave] = ifcopenshell.open(caminho, lazy=True) if lazy else ifcopenshell.open(caminho)
        return cache[chave]
    return ifcopenshell.open(caminho, lazy=True) if lazy else ifcopenshell.open(caminho)


def _malha_caixa(sh):
    geo = getattr(sh, "geometry", None) if sh is not None else None
    vs, fs = (getattr(geo, "verts", None), getattr(geo, "faces", None)) if geo is not None else (None, None)
    if vs is None or fs is None or len(vs) < 9 or len(fs) < 3:
        return None
    verts, tris = np.asarray(vs, dtype=np.float64).reshape(-1, 3), np.asarray(fs, dtype=np.int64).reshape(-1, 3)
    if not len(verts) or not len(tris) or not np.isfinite(verts).all():
        return None
    mn, mx = verts.min(axis=0), verts.max(axis=0)
    return verts, tris, (float(mn[0]), float(mn[1]), float(mx[0]), float(mx[1])), float(mn[2]), float(mx[2])


def _cruza_xy(a: tuple[float, float, float, float], b: tuple[float, float, float, float], margem: float = 0.001) -> bool:
    """Retorna True se as caixas XY `a` e `b` se cruzam com folga `margem`."""
    return a[2] + margem >= b[0] and a[0] - margem <= b[2] and a[3] + margem >= b[1] and a[1] - margem <= b[3]


def _extrair_aneis_geom(geom) -> list[np.ndarray]:
    """Extrai aneis exteriores e interiores de poligonos (ou colecoes) com area util."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        if geom.area <= 1e-12:
            return []
        rings = [np.asarray(geom.exterior.coords, dtype=np.float64)[:, :2]]
        rings.extend(np.asarray(it.coords, dtype=np.float64)[:, :2] for it in geom.interiors)
        return rings
    sub = getattr(geom, "geoms", None)
    if sub is not None:
        out = []
        for g in sub:
            out.extend(_extrair_aneis_geom(g))
        return out
    return []


def _aneis_secao_visiveis(fechados: list[np.ndarray], grupos: list[list[np.ndarray]]) -> list[np.ndarray]:
    """Remove dos aneis fechados da secao apenas trechos cobertos pelos oclusores."""
    if not fechados or not grupos:
        return fechados
    sec_polys = [shapely.make_valid(shapely.Polygon(a)) for a in fechados if len(a) >= 3]
    if not sec_polys:
        return []
    sec_geom = sec_polys[0] if len(sec_polys) == 1 else functools.reduce(shapely.symmetric_difference, sec_polys)
    if sec_geom.is_empty or sec_geom.area <= 1e-12:
        return []
    ocl_polys = [shapely.make_valid(shapely.Polygon(g[0], g[1:])) for g in grupos if g and len(g[0]) >= 3]
    if not ocl_polys:
        return fechados
    ocl_geom = ocl_polys[0] if len(ocl_polys) == 1 else shapely.union_all(ocl_polys)
    inter = shapely.intersection(sec_geom, ocl_geom)
    if inter.is_empty or float(inter.area) <= 1e-9:
        return fechados
    return _extrair_aneis_geom(shapely.difference(sec_geom, ocl_geom))


def _janela_pelo_motor(
    el, verts: np.ndarray, tris: np.ndarray, box_xy: tuple[float, float, float, float], z0: float,
    malhas_hlr: list, pm_boxes: list, altura_corte_m: float,
    diag: dict | None = None,
) -> str | None:
    """Calcula grupo SVG da abertura pelo motor de peca cortada + oclusores, ou None para HLR."""
    try:
        if any(_cruza_xy(pm, box_xy) for pm in pm_boxes):
            return None
        outras = [(ov, ot) for oid, ov, ot, obox in malhas_hlr if oid != el.id() and _cruza_xy(obox, box_xy)]
        caixa_peca = (box_xy[0], box_xy[1], box_xy[2], box_xy[3], z0)
        grupos = oclusores.oclusores_da_peca(caixa_peca, outras, altura_corte_m)
        if grupos is None:
            return None
        pols = peca_cortada.linhas_peca_cortada(verts, tris, altura_corte_m, grupos)
        if pols is None:
            return None
        _va, _ta, segs = corte_plano.cortar_malha_no_plano(verts, tris, altura_corte_m)
        fechados, abertos = aneis.aneis_de_segmentos(segs)
        if abertos:
            return None
        pols_validas = []
        for pl in pols:
            pts = np.asarray(pl, dtype=np.float64)
            if pts.ndim == 2 and pts.shape[0] >= 2 and pts.shape[1] >= 2:
                d = np.diff(pts[:, :2], axis=0)
                if float(np.hypot(d[:, 0], d[:, 1]).sum()) > 1e-9:
                    pols_validas.append(pts)
        grupo, _ = peca_visivel._grupo_svg(el, pols_validas)
        aneis_visiveis = _aneis_secao_visiveis(fechados, grupos)
        subcaminhos = [d for a in aneis_visiveis if (d := _anel_d(a, 0.0, 0.0))]
        if subcaminhos:
            grupo = grupo[:-4] + f'<path d="{" ".join(subcaminhos)}"/></g>'
        return grupo
    except Exception:
        if diag is not None:
            diag["erro"] = diag.get("erro", 0) + 1
        return None


def _motor_planta(
    f, hlr_cands: list, pesadas: dict, moveis_elems: list, caixas_coords: dict,
    altura_corte_m: float, num_threads: int, motor_janelas: bool = False,
    diag_janelas: dict | None = None,
) -> tuple[list[str], list[int], set[int], float, float]:
    """Seleciona peças elegíveis e gera grupos SVG pelo motor de visibilidade."""
    t_g0 = time.perf_counter()
    moveis_caixas = {
        el.id(): c for el in moveis_elems
        if (c := caixa_valida(caixas_coords.get(el.id()) if el.id() in caixas_coords else caixas_coords.get(str(el.id())))) is not None
    }
    para_formas = [
        el for el in hlr_cands + [e for e in moveis_elems if e.id() not in moveis_caixas]
        if getattr(el, "Representation", None) is not None
    ]
    formas = silhueta.formas_do_mundo(f, para_formas, threads=num_threads) if para_formas else {}
    geo_s = time.perf_counter() - t_g0

    candidatas, janelas_cands, malhas_hlr, excluidas, inel_boxes = [], [], [], set(), []
    for el in hlr_cands:
        if (dados := _malha_caixa(formas.get(el.id()))) is None:
            continue
        verts, tris, box_xy, z0, z1 = dados
        if z0 > altura_corte_m:
            excluidas.add(el.id())
            continue
        if motor_janelas:
            malhas_hlr.append((el.id(), verts, tris, box_xy))
        eh_abertura_el = el.is_a("IfcDoor") or el.is_a("IfcWindow")
        if not eh_abertura_el and not getattr(el, "HasOpenings", None) and z1 <= altura_corte_m:
            candidatas.append((el, verts, tris, box_xy))
        else:
            inel_boxes.append(box_xy)
            if motor_janelas and eh_abertura_el and z0 <= altura_corte_m < z1:
                janelas_cands.append((el, verts, tris, box_xy, z0))
    if not candidatas and not janelas_cands:
        if diag_janelas is not None:
            diag_janelas.update({"aceitas": 0, "hlr": 0, "erro": 0})
        return [], [], excluidas, geo_s, 0.0

    pm_boxes = []
    for _el, _nf, aneis in pesadas.values():
        if aneis and (pts := [pt for anel in aneis for pt in anel]):
            arr = np.asarray(pts, dtype=np.float64)
            pm_boxes.append((float(arr[:, 0].min()), float(arr[:, 1].min()), float(arr[:, 0].max()), float(arr[:, 1].max())))
    for el in moveis_elems:
        c = moveis_caixas.get(el.id())
        if c is not None and min(c[2], c[5]) <= altura_corte_m:
            pm_boxes.append((min(c[0], c[3]), min(c[1], c[4]), max(c[0], c[3]), max(c[1], c[4])))
        elif c is None and (dados := _malha_caixa(formas.get(el.id()))) is not None and dados[3] <= altura_corte_m:
            pm_boxes.append(dados[2])
    inel_boxes.extend(pm_boxes)

    if inel_boxes:
        ib = np.asarray(inel_boxes, dtype=np.float64)
        elegiveis = [
            it for it in candidatas if not np.any(
                (ib[:, 2] + 0.001 >= it[3][0]) & (ib[:, 0] - 0.001 <= it[3][2])
                & (ib[:, 3] + 0.001 >= it[3][1]) & (ib[:, 1] - 0.001 <= it[3][3]))
        ]
    else:
        elegiveis = candidatas
    if not elegiveis and not janelas_cands:
        if diag_janelas is not None:
            diag_janelas.update({"aceitas": 0, "hlr": 0, "erro": 0})
        return [], [], excluidas, geo_s, 0.0

    grupos_svg, ids_motor = [], []
    t_m0 = time.perf_counter()
    if elegiveis:
        pols = visibilidade.linhas_visiveis_multi([(v, t) for _el, v, t, _box in elegiveis])
        grupos_svg.extend(peca_visivel._grupo_svg(el, pl)[0] for (el, _v, _t, _box), pl in zip(elegiveis, pols))
        ids_motor.extend(el.id() for el, *_ in elegiveis)
    aceitas, hlr_j, erro_diag = 0, 0, {"erro": 0}
    for el, verts, tris, box_xy, z0 in janelas_cands:
        grupo = _janela_pelo_motor(
            el, verts, tris, box_xy, z0, malhas_hlr, pm_boxes, altura_corte_m, diag=erro_diag,
        )
        if grupo is None:
            hlr_j += 1
            continue
        grupos_svg.append(grupo)
        ids_motor.append(el.id())
        aceitas += 1
    motor_s = time.perf_counter() - t_m0
    if diag_janelas is not None:
        diag_janelas.update({"aceitas": aceitas, "hlr": hlr_j, "erro": erro_diag["erro"]})
    return grupos_svg, ids_motor, excluidas, geo_s, motor_s


def _erro_divergencia(pedido: dict, msg: str) -> dict:
    tipo = "Divergente" if pedido.get("assinatura") is not None else "ArquivoDivergente"
    return {"ok": False, "erro": {"tipo": tipo, "mensagem": msg, "rastro": ""}}


def _conferir_assinatura(pedido: dict) -> dict | None:
    assinatura = pedido.get("assinatura")
    if assinatura is None:
        return None
    try:
        st = os.stat(pedido.get("arquivo"))
        atual = [int(st.st_size), int(st.st_mtime_ns)]
    except (OSError, TypeError):
        atual = None
    esperado = list(assinatura) if isinstance(assinatura, (list, tuple)) else None
    if atual is None or esperado != atual:
        return {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "Arquivo IFC salvo não confere com o modelo", "rastro": ""}}
    return None


def _conferir_elementos(pedido: dict, f) -> dict | None:
    for id_step, guid in pedido.get("elementos", []):
        try:
            el = f.by_id(id_step)
        except Exception:
            el = None
        if el is None or getattr(el, "GlobalId", None) != guid:
            return _erro_divergencia(pedido, f"ID {id_step} diverge do arquivo")
    return None


def _processar_base(pedido: dict, fase=None, f=None, abrir_s: float | None = None) -> dict:
    try:
        if f is None:
            erro = _conferir_assinatura(pedido)
            if erro is not None:
                return erro
            t_a0 = time.perf_counter()
            vista = pedido.get("vista")
            pav_guid = vista.get("pavimento") if isinstance(vista, dict) else None
            f = _abrir_ifc(pedido.get("arquivo"), pav_guid)
            abrir_s = time.perf_counter() - t_a0
            erro = _conferir_elementos(pedido, f)
            if erro is not None:
                return erro
        elif abrir_s is None:
            abrir_s = 0.0

        elementos = pedido.get("elementos", [])
        vista = pedido["vista"]
        if vista.get("tipo") == "CORTE":
            faixa = pedido.get("faixa")
            if faixa is not None:
                try:
                    r = _corte(f, pedido, fase, abrir_s)
                    if r.get("ok") and r.get("svg"):
                        donos_guids = {f.by_id(i).GlobalId for i in faixa.get("donos") or ()}
                        r["svg"] = _recortar_svg_faixa(r["svg"], faixa, donos_guids)
                        r["n_paths"] = len(re.findall(r"<path\b", r["svg"]))
                    return r
                except Exception as e:
                    return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": f"faixa: {e}", "rastro": traceback.format_exc()}}
            if "faixas" in pedido and not (type(pedido.get("faixas")) is int and pedido.get("faixas") == 1):
                return _corte_em_faixas(f, pedido, fase, abrir_s)
            return _corte(f, pedido, fase, abrir_s)
        scale = float(vista["escala"])
        altura_corte_m = float(vista["altura_corte_m"])
        pav = _pavimento(f, vista)
        _isolar_pavimento(f, pav)
        elevacao = float(getattr(pav, "Elevation", 0.0) or 0.0)
        section_height = altura_corte_m - elevacao * scale

        if fase is not None:
            fase("geometria")

        cache_tipo = bool(pedido.get("cache_tipo", True))
        moveis_como_caixa = bool(pedido.get("moveis_como_caixa", False))
        usar_silhueta = pedido.get("pesados") == "silhueta"
        limiar_pesado = _limiar_pesado(pedido)

        selecionados = {id_step for id_step, _ in elementos}
        include_elems = []
        aberturas = set()
        moveis_elems = []
        primarias = {}
        replicas = []
        pesadas = {}
        pesadas_excluidas = set()
        hlr_cands = []
        caixas_coords = pedido.get("caixas_coords") or {}
        num_threads = nucleos.limitar_threads(pedido.get("threads"))

        for id_step, _ in elementos:
            el = f.by_id(id_step)
            if el is None:
                continue
            if el.is_a("IfcOpeningElement"):
                aberturas.add(id_step)
                continue
            if usar_silhueta and _candidata_silhueta(el, moveis_como_caixa):
                n_faces, aneis, zmin = silhueta.faces_e_silhueta(el, limiar_pesado, z_corte=altura_corte_m)
                if silhueta.eh_pesada(n_faces, limiar_pesado):
                    if aneis is None or (zmin is not None and zmin > altura_corte_m):
                        pesadas_excluidas.add(id_step)
                        continue
                    if aneis:
                        pesadas[id_step] = (el, n_faces, aneis)
                        continue
            if moveis_como_caixa and (el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")):
                moveis_elems.append(el)
            else:
                hlr_cands.append(el)

        motor_visivel = bool(pedido.get("motor_visivel"))
        motor_janelas = motor_visivel and bool(pedido.get("motor_janelas"))
        motor_svg, motor_ids, motor_excluidas, motor_geo_s, motor_s = [], [], set(), 0.0, 0.0
        janelas_diag = {"aceitas": 0, "hlr": 0, "erro": 0} if motor_janelas else None
        if motor_visivel and hlr_cands:
            try:
                motor_svg, motor_ids, motor_excluidas, motor_geo_s, motor_s = _motor_planta(
                    f, hlr_cands, pesadas, moveis_elems, caixas_coords, altura_corte_m, num_threads,
                    motor_janelas=motor_janelas, diag_janelas=janelas_diag,
                )
                fora_hlr = set(motor_ids) | motor_excluidas
                if fora_hlr:
                    hlr_cands = [el for el in hlr_cands if el.id() not in fora_hlr]
            except Exception:
                motor_svg, motor_ids, motor_excluidas, motor_geo_s, motor_s = [], [], set(), 0.0, 0.0
                if motor_janelas:
                    janelas_diag = {"aceitas": 0, "hlr": 0, "erro": 0}

        for el in hlr_cands:
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
                c = caixa_valida(caixas_coords.get(el.id()) if el.id() in caixas_coords else caixas_coords.get(str(el.id())))
                if c is not None:
                    zmin = min(c[2], c[5])
                    if zmin > altura_corte_m:
                        moveis_excluidos.add(el.id())
                        continue
                    xmin, xmax = min(c[0], c[3]), max(c[0], c[3])
                    ymin, ymax = min(c[1], c[4]), max(c[1], c[4])
                    d = f"M {xmin:.4f},{-ymax:.4f} L {xmax:.4f},{-ymax:.4f} L {xmax:.4f},{-ymin:.4f} L {xmin:.4f},{-ymin:.4f} L {xmin:.4f},{-ymax:.4f}"
                    caixas_svg.append(f'<g class="{el.is_a()}" ifc:guid="{el.GlobalId}"><path d="{d}"/></g>')
                    caixas_ids.append(el.id())
                else:
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
        svg = _normalizar_svg_vazio(svg)

        pesados_svg, pesados_info = [], []
        for el, n_faces, aneis in pesadas.values():
            grupo = _grupo_silhueta(el, aneis)
            if grupo is None:
                continue
            pesados_svg.append(grupo)
            pesados_info.append({"guid": el.GlobalId, "id": el.id(), "faces": int(n_faces)})

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

        extra_svg = pesados_svg + replicas_svg + caixas_svg + motor_svg
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
        enviados.extend(info["id"] for info in pesados_info)
        enviados.extend(motor_ids)
        enviados_set = set(enviados)
        falhas = [
            id_step for id_step, _ in elementos
            if id_step not in enviados_set and id_step not in aberturas and id_step not in moveis_excluidos
            and id_step not in pesadas_excluidas and id_step not in motor_excluidas
        ]
        n_paths = len(re.findall(r"<path\b", svg))
        tempos = {
            "abrir_s": float(abrir_s),
            "geo_s": float(geo_s + motor_geo_s),
            "write_s": float(write_s),
            "finalize_s": float(finalize_s),
        }
        if motor_visivel:
            tempos["motor_s"] = float(motor_s)
        resp = {
            "ok": True,
            "svg": svg,
            "n_paths": n_paths,
            "enviados": enviados,
            "caixas": caixas_ids,
            "em_cache": em_cache_ids,
            "pesados": pesados_info,
            "falhas_geometria": falhas,
            "tempos": tempos,
        }
        if motor_visivel:
            resp["motor_pecas"] = motor_ids
            if janelas_diag is not None:
                resp["motor_janelas_diag"] = janelas_diag
        return resp
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}


_GRUPO_ELEM = re.compile(r'<g\b(?![^>]*IfcBuildingStorey)[^>]*\bifc:guid\s*=\s*["\']([^"\']*)["\'][^>]*?(?:/>|>.*?</g>)\s*', re.S)


def _planta_recortada(pedido: dict, fase, f=None, abrir_s: float | None = None) -> dict:
    """Filho de planta em faixas: caminho normal e depois recorte da projeção na faixa e filtro dos donos."""
    faixa = pedido["faixa"]
    base = {k: v for k, v in pedido.items() if k not in ("faixa", "pesados", "limiar_pesado")}
    r = _processar_base(base, fase, f=f, abrir_s=abrir_s)
    if not (r.get("ok") and r.get("svg")):
        return r
    try:
        donos = set(faixa.get("donos") or ())
        guids = {guid for i, guid in pedido.get("elementos", []) if i in donos}
        svg = r["svg"]
        u0, u1 = faixa.get("u0"), faixa.get("u1")
        m = _PROJ_RE.search(svg)
        if m is not None and (u0 is not None or u1 is not None):
            novos = []
            for tag in _PATH_RE.findall(m.group(1)):
                dm = _D_ATTR.search(tag)
                if dm is not None:
                    novos.extend(f'<path d="{d}"/>' for d in _recortar_d(dm.group(2), u0, u1, repr))
            svg = svg[: m.start(1)] + "\n" + "\n".join(novos) + "\n" + svg[m.end(1):]
        r["svg"] = _GRUPO_ELEM.sub(lambda g: g.group(0) if g.group(1) in guids else "", svg)
        r["n_paths"] = len(re.findall(r"<path\b", r["svg"]))
        return r
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": f"faixa: {e}", "rastro": traceback.format_exc()}}


def _itens_planta(pedido: dict, total_threads: int):
    """(id, guid, u0, u1) pelas caixas do pedido, completadas por `caixas.processar`; None se faltar alguma."""
    from obim_geometria import caixas as cx

    elementos = pedido.get("elementos", [])
    coords = {}
    for i, _g in elementos:
        c = caixa_valida((pedido.get("caixas_coords") or {}).get(i) or (pedido.get("caixas_coords") or {}).get(str(i)))
        if c is not None:
            coords[i] = c
    falta = [e for e in elementos if e[0] not in coords]
    if falta:
        r = cx.processar({"arquivo": pedido.get("arquivo"), "elementos": falta, "threads": total_threads})
        if not r.get("ok"):
            return None
        for i, _g in falta:
            c = caixa_valida((r.get("caixas_envolventes") or {}).get(str(i)) or (r.get("caixas_envolventes") or {}).get(i))
            if c is not None:
                coords[i] = c
    if any(i not in coords for i, _g in elementos):
        return None
    return [(i, g, min(coords[i][0], coords[i][3]), max(coords[i][0], coords[i][3])) for i, g in elementos]


PESO_MOVEL = 300.0
MIN_ITENS_PESO = 200  # modelo pequeno é rápido de qualquer jeito: divisão por contagem


def _pesos_planta(pedido: dict, itens) -> dict | None:
    """Móvel desenhado em linhas custa ordens de grandeza mais que parede: pesa mais no equilíbrio das faixas."""
    if pedido.get("moveis_como_caixa") or len(itens) < MIN_ITENS_PESO:
        return None
    try:
        f = ifcopenshell.open(pedido.get("arquivo"))
        pesos = {i: PESO_MOVEL for i, _g, _a, _b in itens
                 if (e := f.by_id(i)).is_a("IfcFurnishingElement") or e.is_a("IfcSystemFurnitureElement")}
    except Exception:
        return None
    return pesos or None


def _eh_timeout_resp(resp) -> bool:
    return isinstance(resp, dict) and not resp.get("ok") and "tempo" in str((resp.get("erro") or {}).get("tipo", "")).lower()


def _aplicar_tempos_relogio(
    tempos: dict, *, pesados_s: float = 0.0, formas_s: float = 0.0, agrupar_s: float = 0.0,
    max_lote_s: float = 0.0, refaz_faixas_s: float = 0.0, n_timeouts: int = 0,
    n_grupos: int = 0, maior_grupo: int = 0, megagrupo_direto: bool | None = None,
) -> dict:
    tempos.update({
        "pesados_s": float(pesados_s), "formas_s": float(formas_s), "agrupar_s": float(agrupar_s),
        "max_lote_s": float(max_lote_s), "refaz_faixas_s": float(refaz_faixas_s),
        "n_timeouts": int(n_timeouts), "n_grupos": int(n_grupos), "maior_grupo": int(maior_grupo),
    })
    if megagrupo_direto is not None:
        tempos["megagrupo_direto"] = bool(megagrupo_direto)
    return tempos


def _planta_em_faixas(pedido: dict, fase, n: int, f=None, abrir_s: float | None = None, sem_normal: bool = False) -> dict:
    base = {k: v for k, v in pedido.items() if k != "faixas"}
    pesados_s = 0.0
    formas_s = 0.0
    agrupar_s = 0.0
    max_lote_s = 0.0
    n_timeouts = 0
    pedidos = []
    stats_faixas = None

    def normal() -> dict:
        if sem_normal:
            r = {"ok": False, "erro": {"tipo": "FaixasFalhou", "mensagem": "refazer em faixas falhou", "rastro": ""},
                 "n_timeouts": int(n_timeouts)}
            if stats_faixas:
                r.update(stats_faixas)
            return r
        r = _processar_base(base, fase, f=f, abrir_s=abrir_s)
        if r.get("ok") and isinstance(r.get("tempos"), dict):
            elems = pedido.get("elementos") or ()
            _aplicar_tempos_relogio(r["tempos"], pesados_s=pesados_s, formas_s=formas_s, agrupar_s=agrupar_s, max_lote_s=max_lote_s,
                                    n_timeouts=n_timeouts, n_grupos=1 if elems else 0, maior_grupo=len(elems))
            if stats_faixas:
                r["tempos"].update(stats_faixas)
        return r

    try:
        if not pedido.get("elementos"):
            return normal()
        total_threads = nucleos.limitar_threads(pedido.get("threads"))
        t_fm0 = time.perf_counter()
        itens = _itens_planta(pedido, total_threads)
        formas_s = time.perf_counter() - t_fm0
        if not itens:
            return normal()

        pesados_svg, pesados_info, pesadas_ids, pesadas_excluidas = [], [], set(), set()
        if pedido.get("pesados") == "silhueta":
            t_p0 = time.perf_counter()
            if f is None:
                f = _abrir_ifc(pedido.get("arquivo"))
            altura_corte_m = float((pedido.get("vista") or {}).get("altura_corte_m", float("inf")))
            pesados_svg, pesados_info, pesadas_ids, pesadas_excluidas = _pesadas_para_svg(f, pedido, pedido.get("elementos", []), altura_corte_m)
            pesados_s = time.perf_counter() - t_p0
        fora = pesadas_ids | pesadas_excluidas
        itens = [it for it in itens if it[0] not in fora]
        if not itens:
            return normal()

        t_ag0 = time.perf_counter()
        pesos = _pesos_planta(pedido, itens)
        lims = faixas.limites(itens, n, pesos=pesos)
        if len(lims) <= 1:
            agrupar_s = time.perf_counter() - t_ag0
            return normal()
        divisao = faixas.dividir(itens, n, pesos=pesos)
        agrupar_s = time.perf_counter() - t_ag0
        simultaneos = max(1, min(len(lims), total_threads))
        threads_filho = max(1, total_threads // simultaneos)
        donos_de = []
        for k, (a, b) in enumerate(lims):
            donos = [i for i, _g, u0, u1 in itens if (a is None or (u0 + u1) / 2.0 >= a) and (b is None or (u0 + u1) / 2.0 < b)]
            q = dict(base)
            q.pop("pesados", None)
            q.pop("limiar_pesado", None)
            q["elementos"] = [list(e) for e in divisao[k]]
            q["faixa"] = {"u0": a, "u1": b, "donos": donos}
            q["threads"] = threads_filho
            pedidos.append(q)
            donos_de.append(set(donos))

        def _exec_faixa(q):
            t0 = time.perf_counter()
            r = faixas.rodar_filho(q)
            return r, time.perf_counter() - t0

        t_bl0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=simultaneos) as ex:
            futuros = [ex.submit(_exec_faixa, q) for q in pedidos]
            pares = [fut.result() for fut in futuros]
        resultados = [p[0] for p in pares]
        max_lote_s = max((p[1] for p in pares), default=0.0)
        n_timeouts = sum(1 for r in resultados if _eh_timeout_resp(r))
        stats_faixas = {
            "n_faixas": len(pedidos),
            "faixas_s": [float(p[1]) for p in pares],
            "faixas_abrir_s": [float(((r.get("tempos") or {}).get("abrir_s", 0.0) or 0.0)) if isinstance(r, dict) else 0.0 for r in resultados],
            "faixas_total_s": float(time.perf_counter() - t_bl0),
        }
        for r in resultados:
            if isinstance(r, dict) and not r.get("ok") and (r.get("erro") or {}).get("tipo") == "Divergente":
                return r
        if any(not isinstance(r, dict) or not r.get("ok") or not r.get("svg") for r in resultados):
            return normal()
        svg = faixas.unir_planta([r["svg"] for r in resultados])
        if pesados_svg:
            if "xmlns:ifc=" not in svg:
                svg = re.sub(r"(<svg\b[^>]*)", r'\1 xmlns:ifc="http://www.ifcopenshell.org/ns"', svg, count=1)
            bloco = "\n" + "\n".join(pesados_svg) + "\n"
            idx = svg.rfind("</svg>")
            svg = (svg[:idx] + bloco + svg[idx:]) if idx != -1 else (svg + bloco)
    except Exception:
        return normal()

    def junta(chave):
        return list(dict.fromkeys(x for r in resultados for x in (r.get(chave) or ())))

    enviados = junta("enviados")
    enviados.extend(info["id"] for info in pesados_info)
    enviados = list(dict.fromkeys(enviados))
    falhas = sorted({i for r, d in zip(resultados, donos_de) for i in (r.get("falhas_geometria") or ()) if i in d})
    tempos = {"abrir_s": 0.0, **{k: float(sum(float((r.get("tempos") or {}).get(k, 0.0)) for r in resultados)) for k in ("geo_s", "write_s", "finalize_s")}}
    _aplicar_tempos_relogio(
        tempos, pesados_s=pesados_s, formas_s=formas_s, agrupar_s=agrupar_s, max_lote_s=max_lote_s,
        n_timeouts=n_timeouts, n_grupos=len(pedidos), maior_grupo=max((len(p["elementos"]) for p in pedidos), default=0),
    )
    if stats_faixas:
        tempos.update(stats_faixas)
    return {"ok": True, "svg": svg, "n_paths": len(re.findall(r"<path\b", svg)), "enviados": enviados, "caixas": junta("caixas"),
            "em_cache": junta("em_cache"), "pesados": pesados_info, "falhas_geometria": falhas, "tempos": tempos}


def _injetar_silhuetas(svg: str, pesados_svg: list[str]) -> str:
    """Anexa os grupos de silhueta antes de `</svg>`, garantindo `xmlns:ifc`."""
    if not pesados_svg:
        return svg
    if "xmlns:ifc=" not in svg:
        svg = re.sub(r"(<svg\b[^>]*)", r'\1 xmlns:ifc="http://www.ifcopenshell.org/ns"', svg, count=1)
    bloco = "\n" + "\n".join(pesados_svg) + "\n"
    idx = svg.rfind("</svg>")
    return (svg[:idx] + bloco + svg[idx:]) if idx != -1 else (svg + bloco)


def _eh_abertura(f, id_step: int) -> bool:
    try:
        el = f.by_id(id_step)
        return el is not None and el.is_a("IfcOpeningElement")
    except Exception:
        return False


def _peso_grupo(grupo, formas: dict) -> int:
    total = 0
    for id_step, _ in grupo:
        sh = formas.get(id_step)
        geo = getattr(sh, "geometry", None)
        faces = getattr(geo, "faces", None) if geo is not None else None
        total += (len(faces) // 3) if faces else 1
    return total


def _repartir_lotes(grupos, formas: dict, n_lotes: int) -> list[list[int]]:
    """Repartição gulosa (LPT): ordena por peso decrescente e aloca no lote de menor soma."""
    pesos = [_peso_grupo(g, formas) for g in grupos]
    lotes: list[list[int]] = [[] for _ in range(n_lotes)]
    somas = [0] * n_lotes
    for idx_g in sorted(range(len(grupos)), key=lambda i: -pesos[i]):
        k = min(range(n_lotes), key=lambda j: somas[j])
        lotes[k].append(idx_g)
        somas[k] += pesos[idx_g]
    return lotes


def _normalizar_svg_vazio(svg: str) -> str:
    """Garante tag `<svg>...</svg>` aberta e fechada para inserção de grupos."""
    if re.search(r"<svg\b[^>]*/>", svg):
        return re.sub(r"(<svg\b[^>]*?)/[ \t]*>", r"\1></svg>", svg, count=1)
    if "</svg>" not in svg:
        if "<svg" in svg:
            return svg + "</svg>"
        return '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ifc="http://www.ifcopenshell.org/ns"></svg>'
    return svg


LIMIAR_MEGAGRUPO_FRACAO = 0.5
LIMIAR_MEGAGRUPO_PECAS = 200


def _planta_por_componentes(pedido: dict, fase, f=None, abrir_s: float | None = None) -> dict:
    from obim_geometria import componentes

    base = {k: v for k, v in pedido.items() if k not in ("componentes", "previa_arquivo")}
    elementos = pedido.get("elementos") or []
    formas = {}
    pesados_svg, pesados_info, pesadas_ids, pesadas_excluidas = [], [], set(), set()
    pesadas_prontas = False
    restantes = list(elementos)
    grupos = []
    pesados_s = 0.0
    formas_s = 0.0
    agrupar_s = 0.0
    max_lote_s = 0.0
    refaz_faixas_s = 0.0
    n_timeouts = 0
    faixas_execs = []

    def fallback() -> dict:
        if not pesadas_prontas:
            r = _processar_base(base, fase, f=f, abrir_s=abrir_s)
            if r.get("ok"):
                n_g = 1 if elementos else 0
                r["grupos"] = n_g
                r["grupos_ids"] = [[i for i, _ in elementos]] if elementos else []
                if isinstance(r.get("tempos"), dict):
                    _aplicar_tempos_relogio(r["tempos"], pesados_s=pesados_s, formas_s=formas_s, agrupar_s=agrupar_s, max_lote_s=max_lote_s,
                                            refaz_faixas_s=refaz_faixas_s, n_timeouts=n_timeouts, n_grupos=n_g, maior_grupo=len(elementos),
                                            megagrupo_direto=False)
            return r
        q_rest = {k: v for k, v in base.items() if k not in ("pesados", "limiar_pesado")}
        q_rest["elementos"] = [list(e) for e in restantes]
        r = _processar_base(q_rest, fase, f=f, abrir_s=abrir_s)
        if not r.get("ok"):
            return r
        if pesados_svg:
            r["svg"] = _injetar_silhuetas(r["svg"], pesados_svg)
            r["n_paths"] = len(re.findall(r"<path\b", r["svg"]))
        env = list(r.get("enviados") or ())
        env.extend(info["id"] for info in pesados_info)
        r["enviados"] = list(dict.fromkeys(env))
        r["pesados"] = list(pesados_info)
        n_g = 1 if restantes else 0
        r["grupos"] = n_g
        r["grupos_ids"] = [[i for i, _ in restantes]] if restantes else []
        if isinstance(r.get("tempos"), dict):
            _aplicar_tempos_relogio(r["tempos"], pesados_s=pesados_s, formas_s=formas_s, agrupar_s=agrupar_s, max_lote_s=max_lote_s,
                                    refaz_faixas_s=refaz_faixas_s, n_timeouts=n_timeouts, n_grupos=n_g,
                                    maior_grupo=max((len(g) for g in grupos), default=len(restantes)),
                                    megagrupo_direto=False)
        return r

    try:
        if not elementos:
            return fallback()

        if f is None:
            f = _abrir_ifc(pedido.get("arquivo"))

        t_fm0 = time.perf_counter()
        incl, vistos = [], set()
        for id_step, _ in elementos:
            if id_step in formas or id_step in vistos:
                continue
            vistos.add(id_step)
            try:
                el = f.by_id(id_step)
            except Exception:
                el = None
            if el is not None and not el.is_a("IfcOpeningElement"):
                incl.append(el)
        if incl:
            formas.update(silhueta.formas_do_mundo(f, incl, threads=pedido.get("threads")))
        formas_s = time.perf_counter() - t_fm0

        if pedido.get("previa_arquivo"):
            try:
                from obim_geometria import previa_planta
                pecas_previa = []
                for id_step, guid in elementos:
                    try:
                        el = f.by_id(id_step) if f is not None else None
                    except Exception:
                        el = None
                    malha = _malha_caixa(formas.get(id_step))
                    pecas_previa.append({
                        "guid": guid,
                        "classe": el.is_a() if el is not None else "",
                        "verts": malha[0] if malha is not None else None,
                        "tris": malha[1] if malha is not None else None,
                        "movel": bool(el is not None and (
                            el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement"))),
                    })
                previa_planta.gerar_previa_planta(
                    pecas_previa,
                    float((pedido.get("vista") or {}).get("altura_corte_m")),
                    pedido.get("previa_arquivo"),
                    moveis_como_caixa=bool(pedido.get("moveis_como_caixa")),
                    ao_fase=fase,
                )
            except Exception:
                pass

        if pedido.get("pesados") == "silhueta":
            t_p0 = time.perf_counter()
            altura_corte_m = float((pedido.get("vista") or {}).get("altura_corte_m", float("inf")))
            pesados_svg, pesados_info, pesadas_ids, pesadas_excluidas = _pesadas_para_svg(
                f, pedido, elementos, altura_corte_m, formas=formas
            )
            pesados_s = time.perf_counter() - t_p0
        pesadas_prontas = True

        restantes = [e for e in elementos if e[0] not in (pesadas_ids | pesadas_excluidas)]
        if not restantes:
            return fallback()

        t_ag0 = time.perf_counter()
        grupos = componentes.dividir_elementos(
            pedido.get("arquivo"), restantes, threads=pedido.get("threads"), formas=formas, f=f
        )
        agrupar_s = time.perf_counter() - t_ag0
        if len(grupos) <= 1:
            return fallback()

        total_threads = nucleos.limitar_threads(pedido.get("threads"))
        limiar_fracao = LIMIAR_MEGAGRUPO_FRACAO
        limiar_pecas = LIMIAR_MEGAGRUPO_PECAS
        n_total = sum(len(g) for g in grupos)
        megagrupos, grupos_pequenos = [], []
        for g in grupos:
            if (n_total > 0 and (len(g) / n_total) > limiar_fracao) or len(g) > limiar_pecas:
                megagrupos.append(g)
            else:
                grupos_pequenos.append(g)

        ok_resultados, grupos_falhos = [], []
        n_lotes = min(len(grupos_pequenos), total_threads)
        threads_filho = max(1, total_threads // max(1, n_lotes))
        lotes_idx = _repartir_lotes(grupos_pequenos, formas, n_lotes) if n_lotes else []
        lotes_req = []
        for indices in lotes_idx:
            itens_q = []
            for idx_g in indices:
                q = dict(base)
                q.pop("pesados", None)
                q.pop("limiar_pesado", None)
                q["elementos"] = [list(e) for e in grupos_pequenos[idx_g]]
                q["threads"] = threads_filho
                itens_q.append(q)
            lotes_req.append({**base, "op": "desenho_lote", "pedidos": itens_q})

        def _exec_lote(lote):
            t0 = time.perf_counter()
            try:
                resp = faixas.rodar_filho(lote, limite_s=300.0 * len(lote["pedidos"]))
            except Exception:
                resp = None
            return resp, time.perf_counter() - t0

        lotes_pares = []
        if lotes_req:
            with ThreadPoolExecutor(max_workers=n_lotes) as ex:
                futuros = [ex.submit(_exec_lote, lote) for lote in lotes_req]
                lotes_pares = [fut.result() for fut in futuros]
        lotes_resp = [p[0] for p in lotes_pares]
        max_lote_s = max((p[1] for p in lotes_pares), default=0.0)

        resultados = [None] * len(grupos_pequenos)
        for indices, resp_lote in zip(lotes_idx, lotes_resp):
            if isinstance(resp_lote, dict) and not resp_lote.get("ok") and (resp_lote.get("erro") or {}).get("tipo") == "Divergente":
                return resp_lote
            if _eh_timeout_resp(resp_lote):
                n_timeouts += 1
            itens_r = resp_lote.get("resultados") if isinstance(resp_lote, dict) and resp_lote.get("ok") else None
            if isinstance(itens_r, list):
                for pos, idx_g in enumerate(indices):
                    if pos < len(itens_r):
                        resultados[idx_g] = itens_r[pos]
                        if _eh_timeout_resp(itens_r[pos]):
                            n_timeouts += 1

        for grupo, res in zip(grupos_pequenos, resultados):
            if isinstance(res, dict) and not res.get("ok") and (res.get("erro") or {}).get("tipo") == "Divergente":
                return res
            if isinstance(res, dict) and res.get("ok") and isinstance(res.get("svg"), str) and res.get("svg"):
                ok_resultados.append(res)
            else:
                grupos_falhos.append(grupo)

        if not megagrupos and not ok_resultados:
            return fallback()

        falhas_filhos = set()

        def _rodar_grupo_faixas(grupo):
            nonlocal n_timeouts
            q_faixas = {k: v for k, v in base.items() if k not in ("pesados", "limiar_pesado")}
            q_faixas["elementos"] = [list(e) for e in grupo]
            q_faixas["threads"] = total_threads
            r_faixas = _planta_em_faixas(q_faixas, fase, 8, f=f, abrir_s=abrir_s, sem_normal=True)
            if isinstance(r_faixas, dict) and not r_faixas.get("ok") and (r_faixas.get("erro") or {}).get("tipo") == "Divergente":
                return r_faixas
            if isinstance(r_faixas, dict) and r_faixas.get("ok") and isinstance(r_faixas.get("svg"), str) and r_faixas.get("svg"):
                ok_resultados.append(r_faixas)
                t_faixas = r_faixas.get("tempos") or {}
                n_timeouts += int(t_faixas.get("n_timeouts", 0))
                if "n_faixas" in t_faixas:
                    faixas_execs.append(t_faixas)
            else:
                if _eh_timeout_resp(r_faixas):
                    n_timeouts += 1
                if isinstance(r_faixas, dict):
                    n_timeouts += int(r_faixas.get("n_timeouts", 0))
                    if "n_faixas" in r_faixas:
                        faixas_execs.append(r_faixas)
                falhas_filhos.update(i for i, _ in grupo)
            return None

        for grupo in megagrupos:
            erro_div = _rodar_grupo_faixas(grupo)
            if erro_div is not None:
                return erro_div

        if grupos_falhos:
            t_rf0 = time.perf_counter()
            for grupo in grupos_falhos:
                erro_div = _rodar_grupo_faixas(grupo)
                if erro_div is not None:
                    return erro_div
            refaz_faixas_s = time.perf_counter() - t_rf0

        if not ok_resultados:
            return fallback()

        if falhas_filhos:
            try:
                if f is None:
                    f = _abrir_ifc(pedido.get("arquivo"))
                falhas_filhos = {i for i in falhas_filhos if not _eh_abertura(f, i)}
            except Exception:
                pass
        faltantes = [i for i, _ in elementos if i in falhas_filhos]

        svgs_ok = [r["svg"] for r in ok_resultados]
        if any(faixas._PROJ.search(s) for s in svgs_ok):
            svg = faixas.unir_planta(svgs_ok)
        else:
            svg = svgs_ok[0]
            extras = [m.group(0) for s in svgs_ok[1:] for m in _GRUPO_ELEM.finditer(s)]
            if extras:
                idx = svg.rfind("</svg>")
                bloco = "\n" + "\n".join(extras) + "\n"
                svg = (svg[:idx] + bloco + svg[idx:]) if idx != -1 else (svg + bloco)

        svg = _injetar_silhuetas(svg, pesados_svg)

        ordem = {guid: idx for idx, (_i, guid) in enumerate(elementos)}
        matches = list(_GRUPO_ELEM.finditer(svg))
        if len(matches) > 1:
            ordenados = [m.group(0) for m in sorted(matches, key=lambda m: ordem.get(m.group(1), len(ordem)))]
            partes, pos = [], 0
            for m, novo in zip(matches, ordenados):
                partes.append(svg[pos : m.start()])
                partes.append(novo)
                pos = m.end()
            partes.append(svg[pos:])
            svg = "".join(partes)
        if faltantes:
            svg = re.sub(r"<svg\b([^>]*?)(/?)>", rf'<svg\1 data-obim-incompleta="{len(faltantes)}"\2>', svg, count=1)
    except Exception:
        return fallback()

    def junta(chave):
        return list(dict.fromkeys(x for r in ok_resultados for x in (r.get(chave) or ())))

    enviados = junta("enviados")
    enviados.extend(info["id"] for info in pesados_info)
    enviados = list(dict.fromkeys(enviados))
    falhas_set = falhas_filhos | {i for r in ok_resultados for i in (r.get("falhas_geometria") or ())}
    falhas = [i for i, _ in elementos if i in falhas_set]
    tempos = {
        "abrir_s": 0.0,
        **{
            k: float(sum(float((r.get("tempos") or {}).get(k, 0.0)) for r in ok_resultados))
            for k in ("geo_s", "write_s", "finalize_s")
        },
    }
    if pedido.get("motor_visivel"):
        tempos["motor_s"] = float(sum(float((r.get("tempos") or {}).get("motor_s", 0.0)) for r in ok_resultados))
    _aplicar_tempos_relogio(
        tempos, pesados_s=pesados_s, formas_s=formas_s, agrupar_s=agrupar_s, max_lote_s=max_lote_s,
        refaz_faixas_s=refaz_faixas_s, n_timeouts=n_timeouts, n_grupos=len(grupos), maior_grupo=max((len(g) for g in grupos), default=0),
        megagrupo_direto=bool(megagrupos),
    )
    if faixas_execs:
        tempos["n_faixas"] = sum(int(s.get("n_faixas", 0)) for s in faixas_execs)
        tempos["faixas_s"] = [float(x) for s in faixas_execs for x in (s.get("faixas_s") or ())]
        tempos["faixas_abrir_s"] = [float(x) for s in faixas_execs for x in (s.get("faixas_abrir_s") or ())]
        tempos["faixas_total_s"] = float(sum(float(s.get("faixas_total_s", 0.0)) for s in faixas_execs))
    resp = {
        "ok": True,
        "svg": svg,
        "n_paths": len(re.findall(r"<path\b", svg)),
        "enviados": enviados,
        "caixas": junta("caixas"),
        "em_cache": junta("em_cache"),
        "pesados": pesados_info,
        "falhas_geometria": falhas,
        "tempos": tempos,
        "grupos": len(grupos),
        "grupos_ids": [[i for i, _ in g] for g in grupos],
    }
    if pedido.get("motor_visivel"):
        resp["motor_pecas"] = junta("motor_pecas")
    if faltantes:
        resp["incompleta"] = True
        resp["faltantes"] = faltantes
    return resp


@contextlib.contextmanager
def _sem_rastro(f):
    """Executa mutacoes no modelo IFC dentro de transacao descartada ao sair."""
    if f.transaction is not None:
        yield
        return
    f.begin_transaction()
    try:
        yield
    finally:
        f.discard_transaction()


_MOTIVOS_QUEDA_CACHE = frozenset({
    "sem_arquivo_salvo",
    "opcoes_incompativeis",
    "cache_ausente",
    "cache_invalido",
    "cache_incompleto",
    "malha_invalida",
    "secao_aberta",
    "erro_motor",
})


def _desenhar_planta_cache(f, pedido, malhas_mundo, elementos_validos, fase, abrir_s):
    """Delega o desenho da planta pelo cache para `planta_cache` (T24c)."""
    ref = [malhas_mundo]
    del malhas_mundo
    return planta_cache.desenhar_planta_cache(
        f, pedido, ref.pop(), elementos_validos, fase=fase, abrir_s=abrir_s
    )


def _elementos_validos_cache(f, pedido: dict) -> list[tuple[int, str]]:
    """Filtra pedido['elementos'] removendo IfcOpeningElement e elementos sem Representation."""
    validos: list[tuple[int, str]] = []
    for id_step, gid in pedido.get("elementos") or ():
        try:
            el = f.by_id(int(id_step))
        except Exception:
            el = None
        if el is None or el.is_a("IfcOpeningElement"):
            continue
        if getattr(el, "Representation", None) is None:
            continue
        validos.append((int(id_step), str(gid)))
    return validos


def _anexar_telemetria_cache(
    resp: dict,
    *,
    via_cache: bool,
    queda: str | None,
    n_faltantes: int,
    cache_s: float,
    secoes_parciais: int = 0,
) -> dict:
    """Anexa telemetria de despacho pelo cache sem sobrescrever faltantes/incompleta da T19i1."""
    resp["via_cache"] = bool(via_cache)
    resp["queda"] = queda
    resp["n_faltantes"] = int(n_faltantes)
    resp["secoes_parciais"] = int(secoes_parciais)
    tempos = dict(resp.get("tempos") or {})
    tempos["cache_s"] = float(cache_s)
    motor_s = tempos.get("motor_s")
    tempos["motor_s"] = float(motor_s) if motor_s is not None else 0.0
    resp["tempos"] = tempos
    return resp


def _tentar_planta_pelo_cache(
    f,
    pedido: dict,
    pasta_cache: str | Path,
    fase,
    abrir_s: float,
) -> tuple[dict | None, str | None, int, float]:
    """Tenta desenhar a planta pelo cache. Retorna (resp_ok, queda, n_faltantes, cache_s)."""
    t0 = time.perf_counter()
    elementos_validos = _elementos_validos_cache(f, pedido)

    if pedido.get("moveis_como_caixa"):
        return None, "opcoes_incompativeis", 0, time.perf_counter() - t0

    arq = pedido.get("arquivo")
    if not arq or not Path(arq).is_file():
        return None, "sem_arquivo_salvo", len(elementos_validos), time.perf_counter() - t0

    caminho_banco = Path(pasta_cache) / cache_geometria.NOME_BANCO
    if not caminho_banco.is_file():
        return None, "cache_ausente", len(elementos_validos), time.perf_counter() - t0

    cab_json = cache_geometria._json_canonico(
        cache_geometria.cabecalho_atual(tesselacao=construtor.TESSELACAO)
    )
    con = None
    cache = None
    try:
        con = cache_geometria._conectar(caminho_banco)
        if not cache_geometria._banco_integro(con, cab_json):
            return None, "cache_invalido", len(elementos_validos), time.perf_counter() - t0
        cache = cache_geometria.CacheGeometria(caminho_banco, con)
        con = None
        doc = cache_geometria.documento_de(arq)
        malhas_mundo, faltantes = cache_leitura.malhas_do_cache(
            cache, doc, [gid for _, gid in elementos_validos]
        )
    except Exception:
        return None, "cache_invalido", len(elementos_validos), time.perf_counter() - t0
    finally:
        if cache is not None:
            cache.fechar()
        elif con is not None:
            cache_geometria._fechar_con(con)

    cache_s = time.perf_counter() - t0
    if faltantes:
        return None, "cache_incompleto", len(faltantes), cache_s

    _ref_malhas = [malhas_mundo]
    del malhas_mundo
    try:
        resp_ok, motivo = _desenhar_planta_cache(f, pedido, _ref_malhas.pop(), elementos_validos, fase, abrir_s)
    except Exception:
        return None, "erro_motor", 0, cache_s

    if isinstance(resp_ok, dict) and resp_ok.get("ok") is True and motivo is None:
        return _anexar_telemetria_cache(
            resp_ok,
            via_cache=True,
            queda=None,
            n_faltantes=0,
            cache_s=cache_s,
            secoes_parciais=int(resp_ok.get("secoes_parciais") or 0),
        ), None, 0, cache_s

    motivo_final = motivo if motivo in _MOTIVOS_QUEDA_CACHE else "erro_motor"
    return None, motivo_final, 0, cache_s


def processar(pedido: dict, fase=None) -> dict:
    erro = _conferir_assinatura(pedido)
    if erro is not None:
        return erro
    vista = pedido.get("vista")
    eh_corte = isinstance(vista, dict) and vista.get("tipo") == "CORTE"
    n_faixas = None
    if not eh_corte and pedido.get("faixa") is None and "faixas" in pedido and not (type(pedido["faixas"]) is int and pedido["faixas"] == 1):
        try:
            n_faixas = faixas._validar_n(pedido["faixas"])
        except faixas.FaixasInvalidas as e:
            return {"ok": False, "erro": {"tipo": "FaixasInvalidas", "mensagem": str(e), "rastro": ""}}
    pasta_cache = pedido.get("pasta_cache_geometria")
    usar_cache = not eh_corte and pedido.get("faixa") is None and pasta_cache is not None and str(pasta_cache) != ""
    try:
        t_a0 = time.perf_counter()
        pav_guid = vista.get("pavimento") if isinstance(vista, dict) else None
        f = (
            _abrir_ifc(pedido.get("arquivo"), pav_guid, lazy=True)
            if usar_cache and "lazy" in inspect.signature(_abrir_ifc).parameters
            else _abrir_ifc(pedido.get("arquivo"), pav_guid)
        )
        abrir_s = time.perf_counter() - t_a0
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
    info_queda = None
    with _sem_rastro(f):
        erro = _conferir_elementos(pedido, f)
        if erro is not None:
            return erro
        if eh_corte:
            return _processar_base(pedido, fase, f=f, abrir_s=abrir_s)
        if pedido.get("faixa") is not None:
            return _planta_recortada(pedido, fase, f=f, abrir_s=abrir_s)
        if usar_cache:
            resp_cache, motivo_queda, n_faltantes, cache_s = _tentar_planta_pelo_cache(
                f, pedido, pasta_cache, fase, abrir_s
            )
            if resp_cache is not None:
                return resp_cache
            info_queda = (motivo_queda, n_faltantes, cache_s)
            # queda: o pavimento inteiro vai ao motor; sub-pedidos nao reabrem o cache
            pedido = {k: v for k, v in pedido.items() if k != "pasta_cache_geometria"}
    if info_queda is not None:
        t_r0 = time.perf_counter()
        f = _abrir_ifc(pedido.get("arquivo"), pav_guid)
        abrir_s += time.perf_counter() - t_r0
    with _sem_rastro(f):
        if n_faixas is not None:
            resp = _planta_em_faixas(pedido, fase, n_faixas, f=f, abrir_s=abrir_s)
        elif pedido.get("componentes"):
            resp = _planta_por_componentes(pedido, fase, f=f, abrir_s=abrir_s)
        else:
            resp = _processar_base(pedido, fase, f=f, abrir_s=abrir_s)
    if info_queda is not None and isinstance(resp, dict):
        motivo_queda, n_faltantes, cache_s = info_queda
        _anexar_telemetria_cache(
            resp, via_cache=False, queda=motivo_queda, n_faltantes=n_faltantes, cache_s=cache_s
        )
    return resp


def processar_lote(pedido: dict, fase=None) -> dict:
    """Processa um lote de pedidos de desenho reaproveitando cada IFC aberto."""
    pedidos = pedido.get("pedidos") if isinstance(pedido, dict) else None
    if not isinstance(pedidos, list) or not pedidos:
        return {
            "ok": False,
            "erro": {"tipo": "ProtocoloInvalido", "mensagem": "Pedido de lote sem lista 'pedidos' não vazia", "rastro": ""},
        }
    global _ARQ_LOTE
    anterior_tls = getattr(_LOTE_TLS, "cache", None)
    cache: dict[tuple[str, str | None, bool], object] = {}
    _LOTE_TLS.cache = cache
    eh_main = threading.current_thread() is threading.main_thread()
    anterior = _ARQ_LOTE
    if eh_main:
        _ARQ_LOTE = cache
    try:
        resultados = []
        for q in pedidos:
            try:
                resultados.append(processar(q, fase))
            except Exception as e:
                resultados.append({
                    "ok": False,
                    "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()},
                })
        return {"ok": True, "resultados": resultados}
    finally:
        _LOTE_TLS.cache = anterior_tls
        if eh_main:
            _ARQ_LOTE = anterior
