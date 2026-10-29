# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda de tempo por etapa na casa-2pav (F0-S06-T01c).

Mede leitura, geometria (cache nativo com 1 e N nucleos), serializacao SVG (escrita + finalize, onde roda o HLR)
por variante (a1 HLR padrao, a2 svg-poly, d shapely) e filtro, em planta e corte. Geometria nativa e reaproveitada
entre planta e corte. Reusa sonda_motores.py sem altera-lo. O IFC do PO so e lido; a anotacao de corte vai so para
a copia em memoria. Saidas em /tmp (nao commitar).
Uso: python sonda_tempo.py [--repeticoes 3] [--nucleos 16]
"""
import argparse
import importlib.util
import os
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

PO = Path(os.environ.get("OBIM_IFC_REFERENCIA", "referencia.ifc"))  # IFC do PO: fora do repositorio, caminho pela variavel
SAIDA = Path("/tmp/s06-sonda-tempo")
META_S = 10.0
ALTURA = 1.2
EXCL = ("IfcFurnishingElement", "IfcOpeningElement", "IfcSpace", "IfcAnnotation", "IfcGrid", "IfcDistributionPort")
FILTROS = ("todos", "sem_mob_vazios", "faixa")
VISTAS = ("planta", "corte")


def _sm():
    spec = importlib.util.spec_from_file_location("sonda_motores", Path(__file__).with_name("sonda_motores.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cfg(poly, guid=None):
    """Configuracao do serializador SVG (mesma de sonda_motores._svg_motor). guid: vista de corte."""
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


def _escolhe(itens, bbox, vista, filtro, y, anot):
    """Filtra por vista. planta: sem anotacao; corte: anotacao sempre. 'faixa': caixa na faixa 0 a 1,2 m (planta) ou cruza o plano (corte)."""
    out = []
    for el in itens:
        if el.id == anot:
            if vista == "corte":
                out.append(el)
            continue
        if filtro != "todos" and el.type in EXCL:
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
    """Variante d: secao + projecao com shapely sobre triangulos. Devolve o numero de pecas (linhas) geradas."""
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
        proj = shapely.union_all(shapely.polygons(T[lado][:, :, eixos2d]))
        if not proj.is_empty:
            contorno = list(getattr(proj.boundary, "geoms", [proj.boundary]))
    return len(poligonos) + len(contorno)


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

    # Passe tesselado (variante d e caixas por elemento para os filtros). Tempo por nucleos.
    st_t = ifcopenshell.geom.settings(USE_WORLD_COORDS=True)
    geo_t, tess = {}, None
    for n in (1, N):
        ts = []
        for _ in range(R):
            tess, dt = _geo(f, st_t, n)
            ts.append(dt)
        geo_t[n] = _media(ts)
    bbox = {}
    for e in tess:
        v = np.asarray(e.geometry.verts, float).reshape(-1, 3)
        bbox[e.id] = (v.min(0), v.max(0))
    mn = np.min([b[0] for b in bbox.values()], 0)
    mx = np.max([b[1] for b in bbox.values()], 0)
    y = float((mn[1] + mx[1]) / 2)

    guid = sm._anotar_corte(f, mn, mx, y)  # so na copia em memoria
    anot = f.by_guid(guid).id()

    # Geometria nativa (usada por a1 e a2): tempo com 1 e N nucleos; a ultima lista e reaproveitada.
    st_geo = _cfg(False)
    geo_n, nat = {}, None
    for n in (1, N):
        ts = []
        for _ in range(R):
            nat, dt = _geo(f, st_geo, n)
            ts.append(dt)
        geo_n[n] = _media(ts)

    linhas_ser, linhas_d, tot = [], [], {}
    for var, poly in (("a1", False), ("a2", True)):
        for vista in VISTAS:
            for filtro in FILTROS:
                sel = _escolhe(nat, bbox, vista, filtro, y, anot)
                loops, fins, svg = [], [], ""
                for _ in range(R):
                    svg, a, b = _ser(f, _cfg(poly, guid if vista == "corte" else None), sel)
                    loops.append(a)
                    fins.append(b)
                ln = sm._metricas(svg)[0]
                ser = _media(loops) + _media(fins)
                tot[(var, vista, filtro)] = {"n": len(sel), "loop": _media(loops), "fin": _media(fins), "ser": ser,
                                              "linhas": ln, "t1": geo_n[1] + ser, "tN": geo_n[N] + ser}
                linhas_ser.append((var, vista, filtro, len(sel), f"{_media(loops):.2f}", f"{_media(fins):.2f}",
                                   f"{ser:.2f}", f"{geo_n[1] + ser:.2f}", f"{geo_n[N] + ser:.2f}", ln))
    for vista in VISTAS:
        for filtro in FILTROS:
            sel = _escolhe(tess, bbox, vista, filtro, y, anot)
            ts, pecas = [], 0
            for _ in range(R):
                t0 = time.perf_counter()
                pecas = _d(sm, sel, vista, y)
                ts.append(time.perf_counter() - t0)
            t_d = _media(ts)
            tot[("d", vista, filtro)] = {"n": len(sel), "ser": t_d, "t1": geo_t[1] + t_d, "tN": geo_t[N] + t_d, "linhas": pecas}
            linhas_d.append(("d", vista, filtro, len(sel), "-", "-", f"{t_d:.2f}", f"{geo_t[1] + t_d:.2f}",
                             f"{geo_t[N] + t_d:.2f}", pecas))

    print(f"\n## Leitura do IFC: {_media(leitura):.3f} s (media de {R})")
    print(f"\n## Geometria: tesselada 1 nucleo {geo_t[1]:.2f} s, {N} nucleos {geo_t[N]:.2f} s; "
          f"nativa (a1/a2) 1 nucleo {geo_n[1]:.2f} s, {N} nucleos {geo_n[N]:.2f} s")
    print("\n## Tempo por variante e filtro (s, media; serializacao = escrita + finalize, onde roda o HLR)")
    cab = ["Variante", "Vista", "Filtro", "Elementos", "Escrita (s)", "Finalize (s)", "Serializacao (s)",
           "Total 1 nucleo (s)", f"Total {N} nucleos (s)", "Linhas"]
    print(_tabela(cab, linhas_ser + linhas_d))

    print("\n## Meta de 10 s (total sem leitura, com N nucleos), melhor combinacao por vista")
    for vista in VISTAS:
        melhor = min(((k, d) for k, d in tot.items() if k[1] == vista), key=lambda kd: kd[1]["tN"])
        (v, _, fi), d = melhor
        print(f"- {vista}: {d['tN']:.2f} s ({v}, filtro {fi}); meta {'atendida' if d['tN'] <= META_S else 'NAO atendida'}; "
              f"com leitura {d['tN'] + _media(leitura):.2f} s")
    print("\n## Cache: planta+corte a1 todos (N nucleos)")
    sem = 2 * geo_n[N] + tot[("a1", "planta", "todos")]["ser"] + tot[("a1", "corte", "todos")]["ser"]
    com = geo_n[N] + tot[("a1", "planta", "todos")]["ser"] + tot[("a1", "corte", "todos")]["ser"]
    print(f"sem reuso: {sem:.2f} s; com reuso: {com:.2f} s")

    # Validacao do cache: corte a1 todos deve dar as mesmas linhas que o caminho direto de sonda_motores.
    svg_dir = sm._svg_motor(f, False, guid)
    print(f"\n## Validacao: linhas da corte direta (sonda_motores, a1) {sm._metricas(svg_dir)[0]} "
          f"vs cache {tot[('a1', 'corte', 'todos')]['linhas']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
