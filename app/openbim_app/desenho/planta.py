# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geração de planta 2D bruta em SVG via IfcOpenShell (ADR-006 §2, §3 item 0 e §4)."""
from __future__ import annotations

import dataclasses
import os
import re
import time
from typing import Any, Iterable

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.ifcopenshell_wrapper as W
import ifcopenshell.util.placement
import ifcopenshell.util.unit

from openbim_app.desenho import selecao
from openbim_app.desenho.selecao import Selecao, SelecaoInvalida


@dataclasses.dataclass(frozen=True)
class Planta:
    svg: str
    n_paths: int
    selecao: Selecao
    tempos: dict[str, float]
    unidade_escala: float
    altura_corte: float


def gerar_planta(
    ifc: ifcopenshell.file,
    gid_vista: str,
    *,
    categorias_ocultas: Iterable[str] = (),
    threads: int | None = None,
) -> Planta:
    sel = selecao.selecionar(ifc, gid_vista, categorias_ocultas=categorias_ocultas)
    if sel.tipo != "PLANTA":
        raise SelecaoInvalida(f"Vista {gid_vista} não é do tipo PLANTA (tipo={sel.tipo})")

    scale = float(ifcopenshell.util.unit.calculate_unit_scale(ifc))
    u = 1.0 / scale

    pav = ifc.by_id(sel.pavimento)
    if pav.ObjectPlacement is not None:
        M = ifcopenshell.util.placement.get_local_placement(pav.ObjectPlacement)
        ox, oy, oz = float(M[0, 3]), float(M[1, 3]), float(M[2, 3])
    else:
        ox, oy = 0.0, 0.0
        oz = float(getattr(pav, "Elevation", 0.0) or 0.0)

    altura_corte = float(oz * scale + 1.2)

    if not sel.ids:
        return Planta(
            svg='<svg xmlns="http://www.w3.org/2000/svg" version="1.1"></svg>',
            n_paths=0,
            selecao=sel,
            tempos={"geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0},
            unidade_escala=scale,
            altura_corte=altura_corte,
        )

    created: list[Any] = []
    try:
        corpos = [
            c
            for c in ifc.by_type("IfcGeometricRepresentationSubContext")
            if c.ContextIdentifier == "Body"
        ]
        if corpos:
            corpo = corpos[0]
        else:
            ctx = ifc.by_type("IfcGeometricRepresentationContext")[0]
            corpo = ifc.create_entity(
                "IfcGeometricRepresentationSubContext",
                ContextIdentifier="Body",
                ContextType="Model",
                ParentContext=ctx,
                TargetView="MODEL_VIEW",
            )
            created.append(corpo)

        z_cut_project = oz + 1.2 * u
        xs = [ox]
        ys = [oy]
        for eid in sel.ids:
            elem = ifc.by_id(eid)
            plc = getattr(elem, "ObjectPlacement", None)
            if plc is not None:
                try:
                    m = ifcopenshell.util.placement.get_local_placement(plc)
                    xs.append(float(m[0, 3]))
                    ys.append(float(m[1, 3]))
                except Exception:
                    pass

        folga = 50.0 * u
        xmin = min(xs) - folga
        xmax = max(xs) + folga
        ymin = min(ys) - folga
        ymax = max(ys) + folga

        x_loc = xmin - ox
        y_loc = oy - ymax
        lx = xmax - xmin
        ly = ymax - ymin
        depth = 50.0 * u

        pt_block = ifc.create_entity(
            "IfcCartesianPoint", Coordinates=(float(x_loc), float(y_loc), 0.0)
        )
        pos_block = ifc.create_entity("IfcAxis2Placement3D", Location=pt_block)
        bloco = ifc.create_entity(
            "IfcBlock",
            Position=pos_block,
            XLength=float(lx),
            YLength=float(ly),
            ZLength=depth,
        )
        csg = ifc.create_entity("IfcCsgSolid", TreeRootExpression=bloco)
        rep = ifc.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=corpo,
            RepresentationIdentifier="Body",
            RepresentationType="CSG",
            Items=[csg],
        )
        d_axis = ifc.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, -1.0))
        d_ref = ifc.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        loc_ann = ifc.create_entity(
            "IfcCartesianPoint", Coordinates=(float(ox), float(oy), float(z_cut_project))
        )
        pl_ann = ifc.create_entity(
            "IfcAxis2Placement3D",
            Location=loc_ann,
            Axis=d_axis,
            RefDirection=d_ref,
        )
        lpl_ann = ifc.create_entity("IfcLocalPlacement", RelativePlacement=pl_ann)
        pshape = ifc.create_entity("IfcProductDefinitionShape", Representations=[rep])
        ann = ifc.create_entity(
            "IfcAnnotation",
            GlobalId=ifcopenshell.guid.new(),
            Name="Planta",
            ObjectType="DRAWING",
            ObjectPlacement=lpl_ann,
            Representation=pshape,
        )
        created.extend(
            [
                pt_block,
                pos_block,
                bloco,
                csg,
                rep,
                d_axis,
                d_ref,
                loc_ann,
                pl_ann,
                lpl_ann,
                pshape,
                ann,
            ]
        )

        st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
        st.set("dimensionality", W.SURFACES_AND_SOLIDS)
        st.set("iterator-output", W.NATIVE)
        st.set("apply-default-materials", True)
        st.set("svg-write-poly", True)
        st.set("svg-xmlns", True)
        st.set("svg-poly", True)
        st.set("door-arcs", True)
        st.set("elevation-ref-guid", ann.GlobalId)
        st.set("svg-without-storeys", True)

        buf = ifcopenshell.geom.serializers.buffer()
        sr = ifcopenshell.geom.serializers.svg(buf, st)
        sr.setFile(ifc)

        num_threads = (
            max(1, int(threads))
            if threads is not None
            else max(1, os.cpu_count() or 1)
        )
        include_elems = [ifc.by_id(i) for i in sel.ids] + [ann]

        t_g0 = time.perf_counter()
        it = ifcopenshell.geom.iterator(st, ifc, num_threads, include=include_elems)
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
    finally:
        for e in reversed(created):
            try:
                ifc.remove(e)
            except Exception:
                pass

    n_paths = len(re.findall(r"<path\b", svg))
    tempos = {
        "geo_s": float(geo_s),
        "write_s": float(write_s),
        "finalize_s": float(finalize_s),
    }

    return Planta(
        svg=svg,
        n_paths=n_paths,
        selecao=sel,
        tempos=tempos,
        unidade_escala=scale,
        altura_corte=altura_corte,
    )
