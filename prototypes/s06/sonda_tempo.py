# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda de tempo por etapa no modelo de referencia (F0-S06-T01c).

Mede leitura, geometria (cache nativo e tesselado com 1, 4 e N nucleos), serializacao SVG
(escrita + finalize, onde roda o HLR) por variante (a1 HLR padrao, a2 svg-poly, d shapely)
e filtro (todos, sem_mob_vazios, sem_mob_com_space, faixa), em planta e corte (3 posicoes Y).
Custos de caixa envolvente sao contabilizados no filtro faixa. Metricas geometricas
(bbox, comprimento total e hash de coordenadas) comparam a equivalencia de saida.
Saidas em /tmp/s06-sonda-tempo.
Uso: python sonda_tempo.py [--repeticoes 3] [--nucleos 16]
"""
import argparse
import hashlib
import importlib.util
import os
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.ops import polygonize

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.ifcopenshell_wrapper as W

PO = Path(os.environ.get("OBIM_IFC_REFERENCIA", "referencia.ifc"))
SAIDA = Path("/tmp/s06-sonda-tempo")
META_S = 10.0
ALTURA = 1.2
EXCL_BASE = ("IfcFurnishingElement", "IfcOpeningElement", "IfcAnnotation", "IfcGrid", "IfcDistributionPort")
EXCL_SEM_SPACE = EXCL_BASE + ("IfcSpace",)
FILTROS = ("todos", "sem_mob_vazios", "sem_mob_com_space", "faixa")
Y_CORTES = (2.5, 7.46, 10.0)


def _sm():
    spec = importlib.util.spec_from_file_location("sonda_motores", Path(__file__).with_name("sonda_motores.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cfg(poly, guid=None):
    st = ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)
    for k, v in {"dimensionality": W.SURFACES_AND_SOLIDS, "iterator-output": W.NATIVE, "apply-default-materials": True,
                 "svg-write-poly": True, "svg-xmlns": True, "svg-poly": poly, "door-arcs": True}.items():
        st.set(k, v)
    if guid:
        st.set("elevation-ref-guid", guid)
        st.set("svg-without-storeys", True)
    else:
        st.set("section-height", ALTURA)
    return st


def _geo(f, st, nucleos):
    t0 = time.perf_counter()
    itens = list(ifcopenshell.geom.iterator(st, f, nucleos))
    return itens, time.perf_counter() - t0


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


def _geom_svg(svg_str):
    # Nota: comprimento e aproximado (arcos A e comandos relativos nao tratados).
    pts = []
    tot_len = 0.0
    for d in re.findall(r'\sd=\"([^\"]+)\"', svg_str):
        subpaths = re.split(r'[Mm]', d)
        for sp in subpaths:
            if not sp.strip():
                continue
            pairs = re.findall(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)[,\s]+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', sp)
            if len(pairs) >= 2:
                arr = np.array([(float(x), float(y)) for x, y in pairs], dtype=float)
                diff = np.diff(arr, axis=0)
                tot_len += float(np.sum(np.sqrt(np.sum(diff**2, axis=1))))
                pts.append(arr)
            elif len(pairs) == 1:
                pts.append(np.array([(float(pairs[0][0]), float(pairs[0][1]))], dtype=float))
    if not pts:
        return {"bbox": (0.0, 0.0, 0.0, 0.0), "comprimento": 0.0, "hash": "-"}
    all_pts = np.vstack(pts)
    mn, mx = all_pts.min(axis=0), all_pts.max(axis=0)
    rounded = np.round(all_pts, 2).tobytes()
    return {
        "bbox": (round(float(mn[0]), 2), round(float(mn[1]), 2), round(float(mx[0]), 2), round(float(mx[1]), 2)),
        "comprimento": round(tot_len, 2),
        "hash": hashlib.md5(rounded).hexdigest()[:8],
    }


def _escolhe(itens, bbox, vista, filtro, y, anot_ids):
    out = []
    anot_vals = set(anot_ids.values())
    alvo_anot = anot_ids.get(y)
    for el in itens:
        if el.id in anot_vals:
            if vista == "corte" and el.id == alvo_anot:
                out.append(el)
            continue
        if filtro in ("sem_mob_vazios", "faixa") and el.type in EXCL_SEM_SPACE:
            continue
        if filtro == "sem_mob_com_space" and el.type in EXCL_BASE:
            continue
        if filtro == "faixa" and el.id in bbox:
            mn, mx = bbox[el.id]
            if vista == "planta" and not (mn[2] < ALTURA and mx[2] > 0):
                continue
            if vista == "corte" and not (mn[1] <= y <= mx[1]):
                continue
        out.append(el)
    return out


def _d(sm, sel, vista, y):
    T = np.concatenate([
        np.asarray(e.geometry.verts, float).reshape(-1, 3)[np.asarray(e.geometry.faces, int).reshape(-1, 3)] for e in sel
    ])
    eixo, valor, corte = (2, ALTURA, False) if vista == "planta" else (1, y, True)
    eixos2d = [i for i in range(3) if i != eixo]
    seg = sm._secao(T, eixo, valor)
    poligonos = list(polygonize(shapely.union_all(shapely.linestrings(seg[:, :, eixos2d])))) if len(seg) else []
    lado = (T[:, :, eixo] >= valor).all(1) if corte else (T[:, :, eixo] <= valor).all(1)
    contorno = []
    if lado.any():
        try:
            proj = shapely.union_all(shapely.polygons(T[lado][:, :, eixos2d]), grid_size=1e-3)
            if not proj.is_empty:
                contorno = list(getattr(proj.boundary, "geoms", [proj.boundary]))
        except Exception:
            try:
                poly_objs = shapely.make_valid(shapely.polygons(T[lado][:, :, eixos2d]))
                proj = shapely.union_all(poly_objs, grid_size=1e-3)
                if not proj.is_empty:
                    contorno = list(getattr(proj.boundary, "geoms", [proj.boundary]))
            except Exception:
                contorno = []

    tot_len = sum(p.length for p in poligonos) + sum(c.length for c in contorno)
    all_bounds = [p.bounds for p in poligonos] + [c.bounds for c in contorno]
    bbox_d = ((round(min(b[0] for b in all_bounds), 2), round(min(b[1] for b in all_bounds), 2),
               round(max(b[2] for b in all_bounds), 2), round(max(b[3] for b in all_bounds), 2))
              if all_bounds else (0.0, 0.0, 0.0, 0.0))
    all_coords = []
    for p in poligonos:
        all_coords.extend(p.exterior.coords)
    for c in contorno:
        all_coords.extend(c.coords)
    h = hashlib.md5(np.round(np.array(all_coords), 2).tobytes()).hexdigest()[:8] if all_coords else "-"
    return len(poligonos) + len(contorno), {"bbox": bbox_d, "comprimento": round(tot_len, 2), "hash": h}


def _media(v):
    return statistics.mean(v)


def _tabela(cab, linhas):
    out = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    out += ["| " + " | ".join(str(c) for c in l) + " |" for l in linhas]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--nucleos", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args(argv)
    R, N = args.repeticoes, args.nucleos
    SAIDA.mkdir(parents=True, exist_ok=True)
    sm = _sm()
    print(f"ifcopenshell {ifcopenshell.version}, Python {sys.version.split()[0]}, nucleos da maquina {os.cpu_count()}, "
          f"N={N}, repeticoes {R}")

    leitura = []
    for _ in range(R):
        t0 = time.perf_counter()
        ifcopenshell.open(str(PO))
        leitura.append(time.perf_counter() - t0)
    f = ifcopenshell.open(str(PO))

    # Geometria tesselada (1 e 4 nucleos com 1 repeticao; N nucleos com R repeticoes)
    st_t = ifcopenshell.geom.settings(USE_WORLD_COORDS=True)
    geo_t, tess = {}, None
    for n in (1, 4):
        tess, dt = _geo(f, st_t, n)
        geo_t[n] = dt
    ts = []
    for _ in range(R):
        tess, dt = _geo(f, st_t, N)
        ts.append(dt)
    geo_t[N] = _media(ts)

    t0_b = time.perf_counter()
    bbox = {}
    for e in tess:
        v = np.asarray(e.geometry.verts, float).reshape(-1, 3)
        bbox[e.id] = (v.min(0), v.max(0))
    dt_bbox = time.perf_counter() - t0_b
    mn = np.min([b[0] for b in bbox.values()], 0)
    mx = np.max([b[1] for b in bbox.values()], 0)

    # Anotar cortes em memoria para as 3 posicoes Y
    guids = {y: sm._anotar_corte(f, mn, mx, y) for y in Y_CORTES}
    anot_ids = {y: f.by_guid(g).id() for y, g in guids.items()}
    y_meio = 7.46

    # Geometria nativa para a1/a2 (1 e 4 nucleos com 1 rep; N com R reps)
    st_geo = _cfg(False)
    geo_n, nat = {}, None
    for n in (1, 4):
        nat, dt = _geo(f, st_geo, n)
        geo_n[n] = dt
    ts = []
    for _ in range(R):
        nat, dt = _geo(f, st_geo, N)
        ts.append(dt)
    geo_n[N] = _media(ts)

    tot, linhas_tabela = {}, []
    # 1. Planta (todas as variantes e filtros)
    for var, poly in (("a1", False), ("a2", True)):
        for filtro in FILTROS:
            sel = _escolhe(nat, bbox, "planta", filtro, y_meio, anot_ids)
            loops, fins, svg = [], [], ""
            for _ in range(R):
                svg, a, b = _ser(f, _cfg(poly), sel)
                loops.append(a)
                fins.append(b)
            g = _geom_svg(svg)
            ser = _media(loops) + _media(fins)
            paths = len(re.findall(r'<path\b', svg))
            # Custo honesto: faixa paga geo_n + ser + geo_t; os outros pagam geo_n + ser
            custo_bb_1 = (geo_t[1] + dt_bbox) if filtro == "faixa" else 0.0
            custo_bb_4 = (geo_t[4] + dt_bbox) if filtro == "faixa" else 0.0
            custo_bb_N = (geo_t[N] + dt_bbox) if filtro == "faixa" else 0.0
            t1 = geo_n[1] + ser + custo_bb_1
            t4 = geo_n[4] + ser + custo_bb_4
            tN = geo_n[N] + ser + custo_bb_N
            tot[(var, "planta", filtro)] = {"n": len(sel), "ser": ser, "t1": t1, "t4": t4, "tN": tN,
                                            "paths": paths, "polilinhas": "-", "g": g, "bb_cost": custo_bb_N}
            linhas_tabela.append((var, "planta", filtro, len(sel), f"{_media(loops):.2f}", f"{_media(fins):.2f}",
                                  f"{ser:.2f}", f"{custo_bb_N:.2f}" if custo_bb_N else "-",
                                  f"{t1:.2f}", f"{t4:.2f}", f"{tN:.2f}", paths, "-",
                                  f"{g['bbox']}", f"{g['comprimento']:.1f}", g["hash"]))

    for filtro in FILTROS:
        sel = _escolhe(tess, bbox, "planta", filtro, y_meio, anot_ids)
        ts, pecas, gd = [], 0, None
        for _ in range(R):
            t0 = time.perf_counter()
            pecas, gd = _d(sm, sel, "planta", y_meio)
            ts.append(time.perf_counter() - t0)
        t_d = _media(ts)
        # Nota: dt_bbox (~0.028 s) nao e somado no total de d faixa porque geo_t ja esta
        # na base; o bbox custa ~0,03 s e NAO foi somado nesta linha (diferenca de centesimos, ver relatorio).
        t1, t4, tN = geo_t[1] + t_d, geo_t[4] + t_d, geo_t[N] + t_d
        tot[("d", "planta", filtro)] = {"n": len(sel), "ser": t_d, "t1": t1, "t4": t4, "tN": tN,
                                        "paths": "-", "polilinhas": pecas, "g": gd, "bb_cost": 0.0}
        linhas_tabela.append(("d", "planta", filtro, len(sel), "-", "-", f"{t_d:.2f}", "-",
                              f"{t1:.2f}", f"{t4:.2f}", f"{tN:.2f}", "-", pecas,
                              f"{gd['bbox']}", f"{gd['comprimento']:.1f}", gd["hash"]))

    # 2. Corte Y=7.46 (meio, principal)
    guid_meio = guids[y_meio]
    for var, poly in (("a1", False), ("a2", True)):
        for filtro in FILTROS:
            sel = _escolhe(nat, bbox, "corte", filtro, y_meio, anot_ids)
            loops, fins, svg = [], [], ""
            for _ in range(R):
                svg, a, b = _ser(f, _cfg(poly, guid_meio), sel)
                loops.append(a)
                fins.append(b)
            g = _geom_svg(svg)
            ser = _media(loops) + _media(fins)
            paths = len(re.findall(r'<path\b', svg))
            custo_bb_1 = (geo_t[1] + dt_bbox) if filtro == "faixa" else 0.0
            custo_bb_4 = (geo_t[4] + dt_bbox) if filtro == "faixa" else 0.0
            custo_bb_N = (geo_t[N] + dt_bbox) if filtro == "faixa" else 0.0
            t1 = geo_n[1] + ser + custo_bb_1
            t4 = geo_n[4] + ser + custo_bb_4
            tN = geo_n[N] + ser + custo_bb_N
            tot[(var, "corte", filtro)] = {"n": len(sel), "ser": ser, "t1": t1, "t4": t4, "tN": tN,
                                           "paths": paths, "polilinhas": "-", "g": g, "bb_cost": custo_bb_N}
            linhas_tabela.append((var, "corte", filtro, len(sel), f"{_media(loops):.2f}", f"{_media(fins):.2f}",
                                  f"{ser:.2f}", f"{custo_bb_N:.2f}" if custo_bb_N else "-",
                                  f"{t1:.2f}", f"{t4:.2f}", f"{tN:.2f}", paths, "-",
                                  f"{g['bbox']}", f"{g['comprimento']:.1f}", g["hash"]))

    for filtro in FILTROS:
        sel = _escolhe(tess, bbox, "corte", filtro, y_meio, anot_ids)
        ts, pecas, gd = [], 0, None
        for _ in range(R):
            t0 = time.perf_counter()
            pecas, gd = _d(sm, sel, "corte", y_meio)
            ts.append(time.perf_counter() - t0)
        t_d = _media(ts)
        # Nota: dt_bbox (~0.028 s) nao e somado no total de d faixa porque geo_t ja esta
        # na base; o bbox custa ~0,03 s e NAO foi somado nesta linha (diferenca de centesimos, ver relatorio).
        t1, t4, tN = geo_t[1] + t_d, geo_t[4] + t_d, geo_t[N] + t_d
        tot[("d", "corte", filtro)] = {"n": len(sel), "ser": t_d, "t1": t1, "t4": t4, "tN": tN,
                                       "paths": "-", "polilinhas": pecas, "g": gd, "bb_cost": 0.0}
        linhas_tabela.append(("d", "corte", filtro, len(sel), "-", "-", f"{t_d:.2f}", "-",
                              f"{t1:.2f}", f"{t4:.2f}", f"{tN:.2f}", "-", pecas,
                              f"{gd['bbox']}", f"{gd['comprimento']:.1f}", gd["hash"]))

    # 3. Cortes em 3 posicoes Y (Y=2.5, Y=7.46, Y=10.0) para provar equivalencia e variacao
    linhas_3y = []
    for y_pos in Y_CORTES:
        guid_y = guids[y_pos]
        for f_nome in ("faixa", "sem_mob_vazios"):
            for var, poly in (("a1", False), ("a2", True)):
                sel = _escolhe(nat, bbox, "corte", f_nome, y_pos, anot_ids)
                svg, a, b = _ser(f, _cfg(poly, guid_y), sel)
                g = _geom_svg(svg)
                paths = len(re.findall(r'<path\b', svg))
                linhas_3y.append((y_pos, var, f_nome, len(sel), f"{a+b:.2f}", paths, "-",
                                  f"{g['bbox']}", f"{g['comprimento']:.1f}", g["hash"]))
            sel_d = _escolhe(tess, bbox, "corte", f_nome, y_pos, anot_ids)
            t0 = time.perf_counter()
            pecas_d, gd = _d(sm, sel_d, "corte", y_pos)
            dt_d = time.perf_counter() - t0
            linhas_3y.append((y_pos, "d", f_nome, len(sel_d), f"{dt_d:.2f}", "-", pecas_d,
                              f"{gd['bbox']}", f"{gd['comprimento']:.1f}", gd["hash"]))

    # Relatorio no stdout e arquivo
    print(f"\n## Leitura do IFC: {_media(leitura):.3f} s (media de {R})")
    print(f"\n## Geometria: tesselada 1 nucleo {geo_t[1]:.2f} s, 4 nucleos {geo_t[4]:.2f} s, {N} nucleos {geo_t[N]:.2f} s")
    print(f"## Geometria: nativa (a1/a2) 1 nucleo {geo_n[1]:.2f} s, 4 nucleos {geo_n[4]:.2f} s, {N} nucleos {geo_n[N]:.2f} s")
    print(f"## BBox: calculo das caixas a partir dos vertices {dt_bbox:.3f} s")

    cab = ["Var", "Vista", "Filtro", "Elems", "Esc (s)", "Fin (s)", "Ser (s)", "BBox (s)",
           "Tot 1n (s)", "Tot 4n (s)", f"Tot {N}n (s)", "Paths a1/a2", "Polis d", "BBox 2D", "Comp (m)", "Hash"]
    print("\n## Tabela Principal (Corte Y=7.46 m)")
    print(_tabela(cab, linhas_tabela))

    cab_y = ["Y (m)", "Var", "Filtro", "Elems", "Ser (s)", "Paths a1/a2", "Polis d", "BBox 2D", "Comp (m)", "Hash"]
    print("\n## Comparativo de Cortes em 3 Posicoes Y")
    print(_tabela(cab_y, linhas_3y))

    print(f"\n## Meta de {META_S:.0f} s (honestos, com leitura fora)")
    for vista in ("planta", "corte"):
        print(f"\n### {vista.capitalize()}:")
        atendidas = []
        for (v, vis, fi), d in tot.items():
            if vis == vista:
                status = "OK" if d["tN"] <= META_S else "NAO"
                atendidas.append((v, fi, d["tN"], d["t4"], d["t1"], status))
                print(f"- {v} + {fi:18s}: {N}n={d['tN']:5.2f} s [{status}], 4n={d['t4']:5.2f} s, 1n={d['t1']:5.2f} s")

    print("\n## CALCULO do Cache (2*geo + ser, planta + corte a1 todos)")
    ser_p = tot[("a1", "planta", "todos")]["ser"]
    ser_c = tot[("a1", "corte", "todos")]["ser"]
    sem = 2 * geo_n[N] + ser_p + ser_c
    com = geo_n[N] + ser_p + ser_c
    print(f"CALCULO sem reuso: {sem:.2f} s; CALCULO com reuso: {com:.2f} s (economia teorica de {geo_n[N]:.2f} s)")

    # Validacao do cache
    f_val = ifcopenshell.open(str(PO))
    guid_val = sm._anotar_corte(f_val, mn, mx, y_meio)
    svg_dir = sm._svg_motor(f_val, False, guid_val)
    paths_dir = len(re.findall(r'<path\b', svg_dir))
    g_dir = _geom_svg(svg_dir)
    print(f"\n## Validacao direta: paths direta={paths_dir} vs cache={tot[('a1', 'corte', 'todos')]['paths']}, "
          f"hash={g_dir['hash']} vs cache={tot[('a1', 'corte', 'todos')]['g']['hash']}")

    # Gravar em arquivo texto
    with open(SAIDA / "resultado_sonda_tempo.txt", "w", encoding="utf-8") as fp:
        fp.write(f"N={N}, R={R}\n")
        fp.write(_tabela(cab, linhas_tabela) + "\n\n")
        fp.write(_tabela(cab_y, linhas_3y) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
