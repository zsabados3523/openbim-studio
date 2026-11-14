# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de linhas visíveis para uma única peça (vista de cima, sem corte vertical)."""
from __future__ import annotations

import time
import traceback

import ifcopenshell
import ifcopenshell.geom
import numpy as np

from obim_geometria import visibilidade


def _fmt(v: float) -> str:
    return f"{round(float(v), 6) + 0.0:.6f}"


def _tem_item_mapeado(el) -> bool:
    rep_prod = getattr(el, "Representation", None)
    for rep in getattr(rep_prod, "Representations", None) or ():
        for it in getattr(rep, "Items", None) or ():
            if it.is_a("IfcMappedItem"):
                return True
    return False


def _inelegivel(motivo: str) -> dict:
    return {"ok": False, "elegivel": False, "motivo": motivo}


def _grupo_svg(el, polilinhas) -> tuple[str, int]:
    paths = []
    for poli in polilinhas:
        pts = np.asarray(poli, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[0] < 2 or pts.shape[1] < 2:
            continue
        cmds = [f"M {_fmt(pts[0, 0])},{_fmt(-pts[0, 1])}"]
        cmds.extend(f"L {_fmt(p[0])},{_fmt(-p[1])}" for p in pts[1:])
        paths.append(f'<path d="{" ".join(cmds)}"/>')
    return f'<g class="{el.is_a()}" ifc:guid="{el.GlobalId}">{"".join(paths)}</g>', len(paths)


def processar(pedido: dict, fase=None) -> dict:
    """Gera o grupo `<g>` da peça usando `visibilidade.linhas_visiveis` se ela for elegível."""
    try:
        t_a0 = time.perf_counter()
        f = ifcopenshell.open(pedido.get("arquivo"))
        abrir_s = time.perf_counter() - t_a0

        elementos = pedido.get("elementos") or ()
        if not elementos:
            return _inelegivel("sem_geometria")
        id_step, guid = elementos[0][0], elementos[0][1]
        try:
            el = f.by_id(id_step)
        except Exception:
            el = None
        if el is None or getattr(el, "GlobalId", None) != guid:
            return {"ok": False, "erro": {"tipo": "ArquivoDivergente", "mensagem": f"ID {id_step} diverge do arquivo", "rastro": ""}}

        if fase is not None:
            fase("geometria")

        if el.is_a("IfcDoor") or el.is_a("IfcWindow"):
            return _inelegivel("porta_janela")
        if getattr(el, "HasOpenings", None):
            return _inelegivel("aberturas")
        if _tem_item_mapeado(el):
            return _inelegivel("mapeada")
        if getattr(el, "Representation", None) is None:
            return _inelegivel("sem_geometria")

        t_g0 = time.perf_counter()
        cfg = ifcopenshell.geom.settings()
        cfg.set(cfg.USE_WORLD_COORDS, True)
        try:
            forma = ifcopenshell.geom.create_shape(cfg, el)
            geo = forma.geometry
            vs, fs = geo.verts, geo.faces
        except Exception:
            return _inelegivel("sem_geometria")
        geo_s = time.perf_counter() - t_g0

        if not vs or not fs or len(vs) < 3 or len(fs) < 3:
            return _inelegivel("sem_geometria")
        verts = np.asarray(vs, dtype=np.float64).reshape(-1, 3)
        tris = np.asarray(fs, dtype=np.int64).reshape(-1, 3)
        if len(verts) == 0 or len(tris) == 0:
            return _inelegivel("sem_geometria")

        vista = pedido.get("vista") or {}
        if vista.get("tipo") == "CORTE":
            return _inelegivel("vista_corte")
        altura_corte_m = float(vista.get("altura_corte_m", float("inf")))
        if float(verts[:, 2].max()) > altura_corte_m:
            return _inelegivel("cruza_corte")

        if fase is not None:
            fase("motor")
        t_m0 = time.perf_counter()
        polilinhas = visibilidade.linhas_visiveis(verts, tris)
        motor_s = time.perf_counter() - t_m0

        grupo, n_paths = _grupo_svg(el, polilinhas)
        return {
            "ok": True,
            "grupo": grupo,
            "n_paths": n_paths,
            "tempos": {
                "abrir_s": float(abrir_s),
                "geo_s": float(geo_s),
                "motor_s": float(motor_s),
            },
        }
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
