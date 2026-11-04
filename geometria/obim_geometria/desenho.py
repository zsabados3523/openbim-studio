# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de desenho de planta (modo pavimento do motor SVG, sem criar entidade no arquivo)."""
import re
import time
import traceback

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.ifcopenshell_wrapper as W
import ifcopenshell.util.element


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
        altura_corte_m = float(vista["altura_corte_m"])
        pav = _pavimento(f, vista)
        elevacao = float(getattr(pav, "Elevation", 0.0) or 0.0)
        section_height = altura_corte_m - elevacao * scale

        if fase is not None:
            fase("geometria")

        selecionados = {id_step for id_step, _ in elementos}
        include_elems = []
        aberturas = set()
        for id_step, _ in elementos:
            el = f.by_id(id_step)
            if el is not None and el.is_a("IfcOpeningElement"):
                aberturas.add(id_step)
            else:
                include_elems.append(el)

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

        num_threads = max(1, int(pedido.get("threads") or 1))

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

        enviados = [sh.id for sh in shapes if sh.id in selecionados]
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
            "caixas": [],
            "falhas_geometria": falhas,
            "tempos": tempos,
        }
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
