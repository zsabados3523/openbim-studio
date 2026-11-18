# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda leve da planta sem HLR (F0-S06-T20a): selecao, formas, componentes, inel_boxes e triangulos."""
from __future__ import annotations

import argparse
from collections import defaultdict
import shutil
import sys
import tempfile
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app"))
sys.path.insert(0, str(RAIZ / "geometria"))

from obim_geometria import componentes, desenho, nucleos, silhueta  # noqa: E402
from openbim_app.desenho import selecao  # noqa: E402


def _resolver_pavimento(f: ifcopenshell.file, chave: str):
    pavs = sorted(f.by_type("IfcBuildingStorey"), key=lambda p: float(p.Elevation) if p.Elevation is not None else 0.0)
    if not pavs:
        raise SystemExit("IFC sem IfcBuildingStorey")
    try:
        cand = f.by_guid(chave)
        if cand is not None and cand.is_a("IfcBuildingStorey"):
            return cand
    except RuntimeError:
        pass
    if chave.lstrip("-").isdigit() and 0 <= int(chave) < len(pavs):
        return pavs[int(chave)]
    alvo = chave.strip().lower()
    for p in pavs:
        if (p.Name or "") == chave or (p.Name or "").strip().lower() == alvo:
            return p
    nomes = ", ".join(f"{i}:{p.Name!r}({p.GlobalId})" for i, p in enumerate(pavs))
    raise SystemExit(f"Pavimento {chave!r} nao encontrado. Disponiveis: {nomes}")


def _altura_corte(f: ifcopenshell.file, pav, corte_m: float) -> float:
    scale = float(ifcopenshell.util.unit.calculate_unit_scale(f))
    oz = float(ifcopenshell.util.placement.get_local_placement(pav.ObjectPlacement)[2, 3]) if pav.ObjectPlacement is not None else float(getattr(pav, "Elevation", 0.0) or 0.0)
    return float(oz * scale + corte_m)


def _maps_elemento(el) -> list[int]:
    rep_prod = getattr(el, "Representation", None)
    if rep_prod is None:
        return []
    ids, vistos = [], set()
    for rep in getattr(rep_prod, "Representations", ()) or ():
        for it in getattr(rep, "Items", ()) or ():
            src = getattr(it, "MappingSource", None) if it.is_a("IfcMappedItem") else None
            if src is not None and src.is_a("IfcRepresentationMap") and src.id() not in vistos:
                vistos.add(src.id())
                ids.append(src.id())
    return ids


def _eh_movel(el) -> bool:
    return el.is_a("IfcFurnishingElement") or el.is_a("IfcSystemFurnitureElement")


def _analisar_inel_boxes(f, hlr_cands: list, pesadas_ids: set[int], formas: dict, altura_corte_m: float):
    candidatas, excluidas, inel = [], 0, []
    for el in hlr_cands:
        dados = desenho._malha_caixa(formas.get(el.id()))
        if dados is None:
            continue
        _v, _t, box_xy, z0, z1 = dados
        if z0 > altura_corte_m:
            excluidas += 1
            continue
        eh_ab = el.is_a("IfcDoor") or el.is_a("IfcWindow")
        if not eh_ab and not getattr(el, "HasOpenings", None) and z1 <= altura_corte_m:
            candidatas.append((el, box_xy))
        else:
            mot = "abertura" if eh_ab else ("HasOpenings" if getattr(el, "HasOpenings", None) else "z1>corte")
            inel.append((el, box_xy, mot))
    for eid in sorted(pesadas_ids):
        dados = desenho._malha_caixa(formas.get(eid))
        if dados is not None and dados[3] <= altura_corte_m:
            inel.append((f.by_id(eid), dados[2], "pesada"))
    if not candidatas or not inel:
        return len(candidatas), len(candidatas), 0, 0, inel, [], excluidas
    cb = np.asarray([b for _el, b in candidatas], dtype=np.float64)
    eh_mv = np.asarray([_eh_movel(el) for el, _b in candidatas], dtype=bool)
    expulsa_cand = np.zeros(len(candidatas), dtype=bool)
    ofensores = []
    for el, box, mot in inel:
        mask = (box[2] + 0.001 >= cb[:, 0]) & (box[0] - 0.001 <= cb[:, 2]) & (box[3] + 0.001 >= cb[:, 1]) & (box[1] - 0.001 <= cb[:, 3])
        if n_c := int(mask.sum()):
            expulsa_cand |= mask
            ofensores.append((int((mask & eh_mv).sum()), n_c, el, mot))
    ofensores.sort(key=lambda x: (-x[0], -x[1], x[2].id()))
    return len(candidatas), len(candidatas) - int(expulsa_cand.sum()), int(expulsa_cand.sum()), int((expulsa_cand & eh_mv).sum()), inel, ofensores, excluidas


def rodar(arq: Path, pav_arg: str, corte_m: float = 1.2, limiar_pesado: int = silhueta.LIMIAR_PADRAO, threads: int | None = None) -> None:
    t_tot0 = time.perf_counter()
    n_threads = nucleos.limitar_threads(threads)
    with tempfile.TemporaryDirectory(prefix="obim_sonda_") as tmp:
        copia = Path(tmp) / arq.name
        shutil.copy2(arq, copia)
        t0 = time.perf_counter(); f = ifcopenshell.open(str(copia)); abrir_s = time.perf_counter() - t0
        pav = _resolver_pavimento(f, pav_arg)
        altura_corte_m = _altura_corte(f, pav, corte_m)
        t0 = time.perf_counter()
        cats = selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS
        elems_sel = sorted((e for e in selecao._candidatos_planta(pav) if getattr(e, "Representation", None) and not any(e.is_a(c) for c in cats)), key=lambda e: e.id())
        elementos = [[e.id(), e.GlobalId] for e in elems_sel]
        selecao_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        incl = [e for e in elems_sel if not e.is_a("IfcOpeningElement")]
        formas = silhueta.formas_do_mundo(f, incl, threads=n_threads) if incl else {}
        formas_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        _psvg, pes_info, pes_ids, pes_excl = desenho._pesadas_para_svg(
            f, {"pesados": "silhueta", "limiar_pesado": limiar_pesado, "threads": n_threads, "moveis_como_caixa": False}, elementos, altura_corte_m, formas=formas
        )
        pesadas_s = time.perf_counter() - t0
        restantes = [e for e in elementos if e[0] not in (pes_ids | pes_excl)]
        t0 = time.perf_counter(); grupos = componentes.dividir_elementos(str(copia), restantes, threads=n_threads, formas=formas, f=f); agrupar_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        hlr_cands = [f.by_id(i) for i, _ in restantes if not f.by_id(i).is_a("IfcOpeningElement")]
        n_cand, n_eleg, n_exp, n_mv_exp, inel, ofensores, n_excl = _analisar_inel_boxes(f, hlr_cands, pes_ids, formas, altura_corte_m)
        motor_pre_s = time.perf_counter() - t0
        tri_cls, tri_map, sem_map = defaultdict(lambda: [0, 0]), {}, [0, 0]
        for el in incl:
            sh = formas.get(el.id())
            faces = getattr(getattr(sh, "geometry", None), "faces", None) if sh is not None else None
            nt, c = (len(faces) // 3) if faces else 0, el.is_a()
            tri_cls[c][0] += 1; tri_cls[c][1] += nt
            maps = _maps_elemento(el)
            if not maps:
                sem_map[0] += 1; sem_map[1] += nt
            for mid in maps:
                reg = tri_map.setdefault(mid, [0, 0, set()]); reg[0] += 1; reg[1] += nt; reg[2].add(c)

    tamanhos = sorted((len(g) for g in grupos), reverse=True)
    print(f"pavimento: {pav.Name!r} guid={pav.GlobalId} altura_corte_m={altura_corte_m:.3f} sel={len(elementos)} restantes={len(restantes)} pesadas={len(pes_info)}")
    print(f"tempos: total={time.perf_counter() - t_tot0:.2f}s abrir={abrir_s:.2f}s selecao={selecao_s:.2f}s formas={formas_s:.2f}s pesadas={pesadas_s:.2f}s agrupar={agrupar_s:.2f}s pre_hlr={motor_pre_s:.2f}s")
    print(f"grupos: {len(grupos)} top5={tamanhos[:5]}")
    print(f"maior_grupo: {tamanhos[0] if tamanhos else 0}")
    print(f"inel_boxes: total={len(inel)} candidatas={n_cand} elegiveis={n_eleg} expulsas={n_exp} moveis_expulsos={n_mv_exp} z0>corte={n_excl}")
    por_cls = defaultdict(lambda: [0, 0, 0])
    for nm, nc, el, mot in ofensores:
        st = por_cls[(el.is_a(), mot)]; st[0] += 1; st[1] += nc; st[2] += nm
    for (cls, mot), (qtd, nc, nm) in sorted(por_cls.items(), key=lambda kv: (-kv[1][2], -kv[1][1])):
        print(f"  inel_box_classe: {cls} ({mot}) caixas={qtd} expulsam_cands={nc} expulsam_moveis={nm}")
    for nm, nc, el, mot in ofensores[:15]:
        print(f"  inel_box_peca: id={el.id()} {el.is_a()} {el.Name!r} ({mot}) cands={nc} moveis={nm}")
    print("triangulos por classe:")
    for cls, (n_el, nt) in sorted(tri_cls.items(), key=lambda kv: (-kv[1][1], kv[0])):
        print(f"  {cls}: pecas={n_el} tris={nt}")
    print(f"triangulos por IfcRepresentationMap: maps={len(tri_map)} sem_map_pecas={sem_map[0]} sem_map_tris={sem_map[1]}")
    for mid, (n_el, nt, clss) in sorted(tri_map.items(), key=lambda kv: (-kv[1][1], kv[0]))[:20]:
        print(f"  map #{mid}: pecas={n_el} tris={nt} classes={','.join(sorted(clss))}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sonda leve de planta (sem HLR)")
    ap.add_argument("ifc", type=Path); ap.add_argument("pavimento", help="GlobalId, nome ou indice do pavimento")
    ap.add_argument("--corte", type=float, default=1.2); ap.add_argument("--limiar-pesado", type=int, default=silhueta.LIMIAR_PADRAO); ap.add_argument("--threads", type=int, default=None)
    args = ap.parse_args()
    rodar(args.ifc, args.pavimento, corte_m=args.corte, limiar_pesado=args.limiar_pesado, threads=args.threads)


if __name__ == "__main__":
    main()
