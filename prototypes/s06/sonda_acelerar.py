# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda de medicao rigorosa de aceleracao (F0-S06-T01e, refaz T01d).

Mede 5 ideias e atende as 8 exigencias da revisao:
1. Caixa nativa barata somada no tempo frio.
2. finalize (HLR) medido isolado.
3. Nucleos reais via afinidade de CPU (16n, 4n, 1n).
4. Equivalencia por conjunto de paths ordenado e diff de paths.
5. Cache real por elemento (invalida 1 elemento, mede redesenho quente).
6. Grupos sem duplicar anotacao; prova da causa de excesso de linhas.
7. Hipoteses (profundidade, buffer) marcadas como hipotese.
8. Limpeza de IFC em /tmp e modelo de referencia sem dados do PO.
"""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from OCC.Core.BRepTools import breptools
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.ifcopenshell_wrapper as W

PO_ENV = "OBIM_IFC_REFERENCIA"
SAIDA = Path("/tmp/s06-acelerar")
ALTURA, Y_CORTE, META_S = 1.2, 7.46, 10.0


def _sm():
    s = importlib.util.spec_from_file_location("sonda_motores", Path(__file__).with_name("sonda_motores.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _cfg(poly=True, guid=None, defl=None):
    st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
    for k, v in {"dimensionality": W.SURFACES_AND_SOLIDS, "iterator-output": W.NATIVE,
                 "apply-default-materials": True, "svg-write-poly": True, "svg-xmlns": True,
                 "svg-poly": poly, "door-arcs": True}.items():
        st.set(k, v)
    if guid:
        st.set("elevation-ref-guid", guid)
        st.set("svg-without-storeys", True)
    else:
        st.set("section-height", ALTURA)
    if defl is not None:
        st.set("mesher-linear-deflection", defl)
    return st


def _ser(f, st, itens):
    buf = ifcopenshell.geom.serializers.buffer()
    sr = ifcopenshell.geom.serializers.svg(buf, st)
    sr.setFile(f)
    t0 = time.perf_counter()
    for el in itens:
        sr.write(el)
    t1 = time.perf_counter()
    sr.finalize()
    t2 = time.perf_counter()
    return buf.get_value(), t1 - t0, t2 - t1


def extrair_caixas_nativas(itens, n_workers=16):
    t0 = time.perf_counter()
    unique_strs = {el.geometry.id: el.geometry.item(0).serialize() for el in itens if el.geometry.size() > 0}

    def _calc(s):
        shp = breptools.ReadFromString(s)
        b = Bnd_Box()
        brepbndlib.Add(shp, b)
        return b.Get() if not b.IsVoid() else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        cache_box = dict(zip(unique_strs.keys(), ex.map(_calc, unique_strs.values())))

    bboxes = {}
    for el in itens:
        gid = el.geometry.id
        lbox = cache_box.get(gid)
        if lbox:
            x1, y1, z1, x2, y2, z2 = lbox
            corners = np.array([
                [x1, y1, z1, 1], [x1, y1, z2, 1], [x1, y2, z1, 1], [x1, y2, z2, 1],
                [x2, y1, z1, 1], [x2, y1, z2, 1], [x2, y2, z1, 1], [x2, y2, z2, 1]
            ])
            M = np.array(el.transformation.matrix).reshape((4, 4), order='F')
            wpts = corners @ M.T
            bboxes[el.id] = (wpts[:, :3].min(axis=0), wpts[:, :3].max(axis=0))
    return bboxes, time.perf_counter() - t0


def extrair_paths(svg_str):
    paths = set()
    tot_len = 0.0
    raw_paths = re.findall(r'<path\b[^>]*\sd=\"([^\"]+)\"', svg_str)
    for d in raw_paths:
        coords = []
        for sp in re.split(r'[Mm]', d):
            if not sp.strip():
                continue
            pairs = re.findall(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)[,\s]+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', sp)
            if len(pairs) >= 2:
                arr = np.array([(float(x), float(y)) for x, y in pairs], dtype=float)
                tot_len += float(np.sum(np.sqrt(np.sum(np.diff(arr, axis=0)**2, axis=1))))
                coords.append(" ".join(f"{round(float(x), 2):.2f},{round(float(y), 2):.2f}" for x, y in pairs))
            elif len(pairs) == 1:
                coords.append(f"{round(float(pairs[0][0]), 2):.2f},{round(float(pairs[0][1]), 2):.2f}")
        paths.add("M " + " Z M ".join(coords))
    hash_ord = hashlib.md5("\n".join(sorted(paths)).encode("utf-8")).hexdigest()[:8]
    return len(raw_paths), paths, round(tot_len, 2), hash_ord


def _merge_svg(svg_list):
    paths = []
    for s in svg_list:
        paths.extend(re.findall(r'(<path\b[^>]+>)', s))
    return '<svg xmlns="http://www.w3.org/2000/svg">\n' + "\n".join(paths) + "\n</svg>"


def _worker_grp(args):
    p_ifc, elem_ids, poly, guid, defl, n_th = args
    fc = ifcopenshell.open(p_ifc)
    st = _cfg(poly, guid, defl)
    t0 = time.perf_counter()
    prods = [fc.by_id(eid) for eid in elem_ids if fc.by_id(eid).is_a("IfcProduct")]
    if guid:
        prods.append(fc.by_guid(guid))
    itens = list(ifcopenshell.geom.iterator(st, fc, n_th, include=prods))
    t_geo = time.perf_counter() - t0
    buf = ifcopenshell.geom.serializers.buffer()
    sr = ifcopenshell.geom.serializers.svg(buf, st)
    sr.setFile(fc)
    t1 = time.perf_counter()
    for el in itens:
        sr.write(el)
    t_esc = time.perf_counter() - t1
    t2 = time.perf_counter()
    sr.finalize()
    t_fin = time.perf_counter() - t2
    return buf.get_value(), t_geo, t_esc, t_fin


def rodar_grupos(p_ifc, elem_ids, guid, n_grp, n_th_each):
    chunks = [elem_ids[i::n_grp] for i in range(n_grp)]
    t0 = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_grp) as ex:
        futs = [ex.submit(_worker_grp, (p_ifc, c, True, guid, None, n_th_each)) for c in chunks]
        results = [fu.result() for fu in futs]
    t_exec = time.perf_counter() - t0
    t_j0 = time.perf_counter()
    svg_merged = _merge_svg([r[0] for r in results])
    t_juncao = time.perf_counter() - t_j0
    return svg_merged, t_exec + t_juncao, max(r[1] for r in results), max(r[2] for r in results), max(r[3] for r in results), t_juncao


def com_afinidade(n_cores, fn, *args):
    orig = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, set(range(min(n_cores, os.cpu_count() or 16))))
        return fn(*args)
    finally:
        os.sched_setaffinity(0, orig)


def limpar_tmp():
    rem = 0
    for pat in ("*.ifc",):
        for p in list(Path("/tmp").glob(pat)) + list(Path("/tmp/s06-acelerar").glob(pat)):
            try:
                p.unlink()
                rem += 1
            except Exception:
                pass
    return rem


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--relatorio", type=str, default=None)
    args = ap.parse_args(argv)
    R = args.repeticoes
    SAIDA.mkdir(parents=True, exist_ok=True)
    sm = _sm()

    p_ifc = Path(os.environ.get(PO_ENV, "referencia.ifc"))
    if not p_ifc.exists():
        print(f"Erro: IFC {p_ifc} nao encontrado", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    f = ifcopenshell.open(str(p_ifc))
    t_leitura = time.perf_counter() - t0

    mn = np.array([-11.78, -21.93, 0.0])
    mx = np.array([9.74, 13.11, 8.44])

    t0 = time.perf_counter()
    guid_corte = sm._anotar_corte(f, mn, mx, Y_CORTE)
    t_anot = time.perf_counter() - t0
    ann_id = f.by_guid(guid_corte).id()

    ifc_temp = SAIDA / "modelo_temp.ifc"
    f.write(str(ifc_temp))

    st_nat = _cfg(True)
    t0 = time.perf_counter()
    nat = list(ifcopenshell.geom.iterator(st_nat, f, 16))
    geo_16n = time.perf_counter() - t0

    bboxes_nat, t_box_16n = extrair_caixas_nativas([e for e in nat if e.id != ann_id], 16)

    t0_1 = time.perf_counter()
    com_afinidade(1, lambda: list(ifcopenshell.geom.iterator(st_nat, f, 1)))
    geo_1n = time.perf_counter() - t0_1
    t0_4 = time.perf_counter()
    com_afinidade(4, lambda: list(ifcopenshell.geom.iterator(st_nat, f, 4)))
    geo_4n = time.perf_counter() - t0_4

    _, t_box_4n = extrair_caixas_nativas([e for e in nat if e.id != ann_id], 4)
    _, t_box_1n = extrair_caixas_nativas([e for e in nat if e.id != ann_id], 1)

    planta_itens = [e for e in nat if e.id != ann_id]
    corte_itens = nat

    planta_culled = [e for e in planta_itens if not (e.id in bboxes_nat and bboxes_nat[e.id][0][2] > ALTURA)]
    corte_culled = [e for e in nat if e.id == ann_id or (e.id in bboxes_nat and bboxes_nat[e.id][1][1] >= 6.5)]
    um_prod = [f.by_type("IfcWall")[0]]

    resultados = []
    base_paths = {}

    def registrar(nome, vista, itens_ser, guid, extra16, extra4, extra1, reps=R):
        st = _cfg(True, guid)
        tf_list, te_list, tf_h_list = [], [], []
        ult_s = ""
        for _ in range(reps):
            s, te, tf_h = _ser(f, st, itens_ser)
            te_list.append(te)
            tf_h_list.append(tf_h)
            tf_list.append(te + tf_h + extra16)
            ult_s = s
        tf16, tesc16, tfin16 = statistics.mean(tf_list), statistics.mean(te_list), statistics.mean(tf_h_list)

        def _run_single(extra):
            s, te, tf_h = _ser(f, st, itens_ser)
            return te + tf_h + extra

        tf4 = com_afinidade(4, _run_single, extra4) if extra4 is not None else None
        tf1 = com_afinidade(1, _run_single, extra1) if extra1 is not None else None

        np_c, sp_c, comp_m, h_ord = extrair_paths(ult_s)
        if nome == "0_baseline_todos":
            base_paths[vista] = (sp_c, comp_m)
            falt, exced, dif_p = 0, 0, 0.0
        else:
            b_s, b_c = base_paths[vista]
            falt, exced = len(b_s - sp_c), len(sp_c - b_s)
            dif_p = ((comp_m - b_c) / b_c) * 100.0 if b_c else 0.0

        r = {"nome": nome, "vista": vista, "n": len(itens_ser), "tf16": tf16, "tf4": tf4, "tf1": tf1,
             "tesc16": tesc16, "tfin16": tfin16, "tq16": None, "paths": np_c, "comp": comp_m,
             "dif_comp": dif_p, "falt": falt, "exced": exced, "hash": h_ord}
        resultados.append(r)
        print(f"[{nome} - {vista}] Frio 16n={tf16:.2f}s | 4n={tf4 or 0:.2f}s | 1n={tf1 or 0:.2f}s | HLR={tfin16:.2f}s | paths={np_c} | dif={dif_p:+.1f}% (-{falt}, +{exced})", flush=True)
        return r

    # 1. Baseline
    c_b16, c_b4, c_b1 = t_leitura + t_anot + geo_16n, t_leitura + t_anot + geo_4n, t_leitura + t_anot + geo_1n
    registrar("0_baseline_todos", "planta", planta_itens, None, c_b16, c_b4, c_b1)
    registrar("0_baseline_todos", "corte", corte_itens, guid_corte, c_b16, c_b4, c_b1)

    # 2. Culling com caixa barata
    c_c16, c_c4, c_c1 = c_b16 + t_box_16n, c_b4 + t_box_4n, c_b1 + t_box_1n
    registrar("1_culling_caixa_barata", "planta", planta_culled, None, c_c16, c_c4, c_c1)
    registrar("1_culling_caixa_barata", "corte", corte_culled, guid_corte, c_c16, c_c4, c_c1)

    # 3. Cache real por elemento
    for vista, it_v, guid in [("planta", planta_culled, None), ("corte", corte_culled, guid_corte)]:
        st = _cfg(True, guid)
        tqs = []
        for _ in range(R):
            t_r0 = time.perf_counter()
            novo_el = list(ifcopenshell.geom.iterator(st, f, 1, include=um_prod))[0]
            t_rec = time.perf_counter() - t_r0
            it_q = [novo_el if e.id == um_prod[0].id() else e for e in it_v]
            _, te, tf = _ser(f, st, it_q)
            tqs.append(t_rec + te + tf)
        next(r for r in resultados if r["nome"] == "1_culling_caixa_barata" and r["vista"] == vista)["tq16"] = statistics.mean(tqs)

    # 4. Grupos paralelos
    e_ids = [e.id for e in nat if e.id != ann_id]
    for n_g in (2, 4):
        for vista, guid in [("planta", None), ("corte", guid_corte)]:
            s_m, t_tot16, _, _, _, _ = rodar_grupos(str(ifc_temp), e_ids, guid, n_g, max(1, 16 // n_g))
            _, t_tot4, _, _, _, _ = com_afinidade(4, rodar_grupos, str(ifc_temp), e_ids, guid, n_g, 1)
            np_c, sp_c, comp_m, h_ord = extrair_paths(s_m)
            b_s, b_c = base_paths[vista]
            resultados.append({"nome": f"2_grupos_{n_g}p", "vista": vista, "n": len(nat), "tf16": t_tot16 + t_leitura + t_anot,
                               "tf4": t_tot4 + t_leitura + t_anot, "tf1": None, "tesc16": 0.0, "tfin16": 0.0, "tq16": None,
                               "paths": np_c, "comp": comp_m, "dif_comp": ((comp_m - b_c)/b_c)*100.0 if b_c else 0.0,
                               "falt": len(b_s - sp_c), "exced": len(sp_c - b_s), "hash": h_ord})

    # 5. Culling + 2 grupos
    for vista, it_c, guid in [("planta", planta_culled, None), ("corte", corte_culled, guid_corte)]:
        ids_c = [e.id for e in it_c if e.id != ann_id]
        s_m, t_tot16, _, _, _, _ = rodar_grupos(str(ifc_temp), ids_c, guid, 2, 8)
        _, t_tot4, _, _, _, _ = com_afinidade(4, rodar_grupos, str(ifc_temp), ids_c, guid, 2, 1)
        np_c, sp_c, comp_m, h_ord = extrair_paths(s_m)
        b_s, b_c = base_paths[vista]
        resultados.append({"nome": "3_comb_cull_2grp", "vista": vista, "n": len(it_c), "tf16": t_tot16 + c_c16 - geo_16n,
                           "tf4": t_tot4 + c_c4 - geo_4n, "tf1": None, "tesc16": 0.0, "tfin16": 0.0, "tq16": None,
                           "paths": np_c, "comp": comp_m, "dif_comp": ((comp_m - b_c)/b_c)*100.0 if b_c else 0.0,
                           "falt": len(b_s - sp_c), "exced": len(sp_c - b_s), "hash": h_ord})

    # 6. Variacao de Deflexao (1 rep)
    for defl in (0.05, 0.10):
        for vista, guid in [("planta", None), ("corte", guid_corte)]:
            st_d = _cfg(True, guid, defl=defl)
            t0 = time.perf_counter()
            nat_d = list(ifcopenshell.geom.iterator(st_d, f, 16))
            g_d = time.perf_counter() - t0
            it_d = [e for e in nat_d if e.id != ann_id] if vista == "planta" else nat_d
            s_val, te, tf_h = _ser(f, st_d, it_d)
            np_c, sp_c, comp_m, h_ord = extrair_paths(s_val)
            b_s, b_c = base_paths[vista]
            resultados.append({"nome": f"4_deflexao_{str(defl).replace('.', '')}", "vista": vista, "n": len(it_d),
                               "tf16": t_leitura + t_anot + g_d + te + tf_h, "tf4": None, "tf1": None,
                               "tesc16": te, "tfin16": tf_h, "tq16": None, "paths": np_c, "comp": comp_m,
                               "dif_comp": ((comp_m - b_c)/b_c)*100.0 if b_c else 0.0, "falt": len(b_s - sp_c), "exced": len(sp_c - b_s), "hash": h_ord})

    # 7. Hipotese: Profundidade de corte limitada (1 rep)
    for prof in (3.0, 5.0):
        c_prof = [e for e in corte_itens if e.id == ann_id or (e.id in bboxes_nat and bboxes_nat[e.id][1][1] >= 6.5 and bboxes_nat[e.id][0][1] <= Y_CORTE + prof)]
        s_val, te, tf_h = _ser(f, _cfg(True, guid_corte), c_prof)
        np_c, sp_c, comp_m, h_ord = extrair_paths(s_val)
        b_s, b_c = base_paths["corte"]
        resultados.append({"nome": f"5_hipotese_prof_{int(prof)}m", "vista": "corte", "n": len(c_prof),
                           "tf16": c_c16 + te + tf_h, "tf4": None, "tf1": None, "tesc16": te, "tfin16": tf_h, "tq16": None,
                           "paths": np_c, "comp": comp_m, "dif_comp": ((comp_m - b_c)/b_c)*100.0 if b_c else 0.0,
                           "falt": len(b_s - sp_c), "exced": len(sp_c - b_s), "hash": h_ord})

    cab = ["Ideia", "Vista", "Elems", "Frio 16n (s)", "Frio 4n (s)", "Frio 1n (s)", "HLR fin (s)",
           "Quente (s)", "Paths", "Comp (m)", "Dif Comp (%)", "Diff Paths (-/+)", "Hash", "Meta 10s"]
    linhas = []
    for r in resultados:
        tf16_s = f"{r['tf16']:.2f}" if r["tf16"] is not None else "-"
        tf4_s = f"{r['tf4']:.2f}" if r["tf4"] is not None else "-"
        tf1_s = f"{r['tf1']:.2f}" if r["tf1"] is not None else "-"
        tfin_s = f"{r['tfin16']:.2f}" if r["tfin16"] is not None else "-"
        tq_s = f"{r['tq16']:.2f}" if r["tq16"] is not None else "-"
        diff_p = f"-{r['falt']}, +{r['exced']}"
        if r["falt"] == 0 and r["exced"] == 0 and abs(r["dif_comp"]) < 0.1:
            meta = "SIM (FRIO)" if r["tf16"] and r["tf16"] <= 10.0 else ("SIM (QUENTE)" if r["tq16"] and r["tq16"] <= 10.0 else "NAO (>10s)")
        elif "hipotese_prof" in r["nome"]:
            meta = "HIPOTESE (<10s)" if r["tf16"] <= 10.0 else "HIPOTESE (>10s)"
        else:
            meta = "NAO (DIFERENTE)"
        linhas.append([r["nome"], r["vista"], r["n"], tf16_s, tf4_s, tf1_s, tfin_s, tq_s, r["paths"], f"{r['comp']:.1f}", f"{r['dif_comp']:+.1f}%", diff_p, r["hash"], meta])

    tabela_md = "| " + " | ".join(cab) + " |\n|" + "---|" * len(cab) + "\n" + "\n".join("| " + " | ".join(str(c) for c in l) + " |" for l in linhas)
    (SAIDA / "tabela_sonda_acelerar.md").write_text(tabela_md, encoding="utf-8")
    (SAIDA / "resultados.json").write_text(json.dumps(resultados, indent=2), encoding="utf-8")

    meta_info = {
        "t_leitura": round(t_leitura, 3), "t_anot": round(t_anot, 3),
        "geo_16n": round(geo_16n, 2), "geo_4n": round(geo_4n, 2), "geo_1n": round(geo_1n, 2),
        "t_box_16n": round(t_box_16n, 3), "t_box_4n": round(t_box_4n, 3), "t_box_1n": round(t_box_1n, 3),
        "c_c16": round(c_c16, 2), "c_c4": round(c_c4, 2), "c_c1": round(c_c1, 2)
    }
    (SAIDA / "meta_info.json").write_text(json.dumps(meta_info, indent=2), encoding="utf-8")
    limpar_tmp()
    print("\nTabela de resultados:\n" + tabela_md, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
