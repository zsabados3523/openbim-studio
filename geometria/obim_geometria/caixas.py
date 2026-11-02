# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cálculo de caixas envolventes (bbox) de produtos IFC em metros (mundo)."""
import traceback
import ifcopenshell
import ifcopenshell.geom


def processar(pedido: dict) -> dict:
    try:
        f = ifcopenshell.open(pedido.get("arquivo"))
        elementos = pedido.get("elementos", [])
        for id_step, guid in elementos:
            try:
                el = f.by_id(id_step)
            except Exception:
                el = None
            if el is None or getattr(el, "GlobalId", None) != guid:
                return {"ok": False, "erro": {"tipo": "ArquivoDivergente", "mensagem": f"ID {id_step} diverge do arquivo", "rastro": ""}}

        s = ifcopenshell.geom.settings()
        s.set(s.USE_WORLD_COORDS, True)
        caixas = {}
        include_elems = [f.by_id(id_step) for id_step, _ in elementos]
        threads = pedido.get("threads", 1)
        it = ifcopenshell.geom.iterator(s, f, threads, include=include_elems)
        if it.initialize():
            while True:
                try:
                    shape = it.get()
                    if shape:
                        verts = shape.geometry.verts
                        if verts:
                            xs, ys, zs = verts[0::3], verts[1::3], verts[2::3]
                            caixas[str(shape.id)] = [
                                float(min(xs)), float(min(ys)), float(min(zs)),
                                float(max(xs)), float(max(ys)), float(max(zs)),
                            ]
                except Exception:
                    pass
                try:
                    if not it.next():
                        break
                except Exception:
                    break
        falhas = [id_step for id_step, _ in elementos if str(id_step) not in caixas]
        return {"ok": True, "caixas_envolventes": caixas, "falhas_geometria": falhas}
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
