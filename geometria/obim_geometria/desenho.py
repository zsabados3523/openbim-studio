# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de desenho de planta (anotação temporária, ajustes e serializador SVG)."""
import re
import time
import traceback

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.ifcopenshell_wrapper as W
import ifcopenshell.util.placement


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
        scale = float(vista["escala"])
        u = 1.0 / scale
        ox, oy, oz = (float(c) for c in vista["origem_pav"])
        altura_corte_m = float(vista["altura_corte_m"])
        z_cut_project = oz + (altura_corte_m - oz * scale) * u

        if fase is not None:
            fase("geometria")

        created = []
        try:
            corpos = [
                c
                for c in f.by_type("IfcGeometricRepresentationSubContext")
                if c.ContextIdentifier == "Body"
            ]
            if corpos:
                corpo = corpos[0]
            else:
                ctx = f.by_type("IfcGeometricRepresentationContext")[0]
                corpo = f.create_entity(
                    "IfcGeometricRepresentationSubContext",
                    ContextIdentifier="Body",
                    ContextType="Model",
                    ParentContext=ctx,
                    TargetView="MODEL_VIEW",
                )
                created.append(corpo)

            xs = [ox]
            ys = [oy]
            for id_step, _ in elementos:
                elem = f.by_id(id_step)
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

            pt_block = f.create_entity(
                "IfcCartesianPoint", Coordinates=(float(x_loc), float(y_loc), 0.0)
            )
            pos_block = f.create_entity("IfcAxis2Placement3D", Location=pt_block)
            bloco = f.create_entity(
                "IfcBlock",
                Position=pos_block,
                XLength=float(lx),
                YLength=float(ly),
                ZLength=depth,
            )
            csg = f.create_entity("IfcCsgSolid", TreeRootExpression=bloco)
            rep = f.create_entity(
                "IfcShapeRepresentation",
                ContextOfItems=corpo,
                RepresentationIdentifier="Body",
                RepresentationType="CSG",
                Items=[csg],
            )
            d_axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, -1.0))
            d_ref = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
            loc_ann = f.create_entity(
                "IfcCartesianPoint", Coordinates=(float(ox), float(oy), float(z_cut_project))
            )
            pl_ann = f.create_entity(
                "IfcAxis2Placement3D",
                Location=loc_ann,
                Axis=d_axis,
                RefDirection=d_ref,
            )
            lpl_ann = f.create_entity("IfcLocalPlacement", RelativePlacement=pl_ann)
            pshape = f.create_entity("IfcProductDefinitionShape", Representations=[rep])
            ann = f.create_entity(
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
            sr.setFile(f)

            num_threads = max(1, int(pedido.get("threads") or 1))
            include_elems = [f.by_id(i) for i, _ in elementos] + [ann]

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
        finally:
            for e in reversed(created):
                try:
                    f.remove(e)
                except Exception:
                    pass

        selecionados = {id_step for id_step, _ in elementos}
        enviados = [sh.id for sh in shapes if sh.id in selecionados]
        enviados_set = set(enviados)
        falhas = [id_step for id_step, _ in elementos if id_step not in enviados_set]
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
            "caixas": [],
            "falhas_geometria": falhas,
            "tempos": tempos,
        }
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
