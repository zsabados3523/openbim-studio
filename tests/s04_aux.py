# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apoio do oráculo R1 (S04-T02): modelos por script, referência em Python e casos em subprocesso (r1e|r1f|r1g)."""
import gc
import importlib
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ESQUEMAS = ("IFC2X3", "IFC4", "IFC4X3")
PAREDES, LAJES = 240, 12
NUCLEOS = {"parse": r"ifcopenshell\.parse", "geometry": r"ifcopenshell\.geometry(?!\.writer)", "TKernel": "TKernel",
           "Qt6Core": "Qt6Core"}

def preparar_dono():  # IFC2x3 exige histórico de dono na API: aponta para o que o próprio arquivo tem
    import ifcopenshell.api.owner.settings as cfg
    cfg.get_user = lambda ifc: (ifc.by_type("IfcPersonAndOrganization") or [None])[0]
    cfg.get_application = lambda ifc: (ifc.by_type("IfcApplication") or [None])[0]

def gerar_modelos(pasta):
    """Um IFC por esquema só com ifcopenshell.api: paredes de medidas e giros variados e lajes em L."""
    import ifcopenshell.api
    api = ifcopenshell.api.run
    preparar_dono()
    saida = {e: Path(pasta) / f"s04_{e.lower()}.ifc" for e in ESQUEMAS}
    for esq in ESQUEMAS:
        f = api("project.create_file", version=esq)
        if esq == "IFC2X3":
            api("owner.add_person_and_organisation", f, person=api("owner.add_person", f, identification="t", family_name="T"),
                organisation=api("owner.add_organisation", f, identification="o", name="T"))
            api("owner.add_application", f)
        api("root.create_entity", f, ifc_class="IfcProject")
        api("unit.assign_unit", f)
        ctx = api("context.add_context", f, context_type="Model")
        corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
        eixo = api("context.add_context", f, context_type="Plan", context_identifier="Axis", target_view="GRAPH_VIEW", parent=api("context.add_context", f, context_type="Plan"))
        andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey")
        api("aggregate.assign_object", f, products=[andar], relating_object=api("root.create_entity", f, ifc_class="IfcBuilding"))
        itens = []
        for i in range(PAREDES + LAJES):
            if i < PAREDES:
                e = api("root.create_entity", f, ifc_class="IfcWall", name=f"Parede {i}")
                rep = api("geometry.add_wall_representation", f, context=corpo, length=2.0 + i % 7 * 0.75,
                          height=2.4 + i % 5 * 0.2, thickness=0.1 + i % 4 * 0.05)
            else:
                e, k = api("root.create_entity", f, ifc_class="IfcSlab", name=f"Laje {i}"), 3.0 + i % 3
                rep = api("geometry.add_slab_representation", f, context=corpo, depth=0.2,
                          polyline=[(0, 0), (2 * k, 0), (2 * k, k), (k, k), (k, 2 * k), (0, 2 * k)])
            api("geometry.assign_representation", f, product=e, representation=rep)
            if i < PAREDES and i % 5 == 0:  # achado 12: parede com eixo (o iterador pode entregá-lo)
                api("geometry.assign_representation", f, product=e, representation=api("geometry.add_axis_representation", f, context=eixo, axis=[(0, 0), (2.0 + i % 7 * 0.75, 0)]))
            a, m = np.radians(i * 37 % 360), np.eye(4)
            m[:2, :2] = [[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]
            m[:3, 3] = (i % 20 * 6.0, i // 20 * 6.0, i % 3 * 3.0)
            api("geometry.edit_object_placement", f, product=e, matrix=m)
            itens.append(e)
            if i == 1:  # achado 12: uma parede com abertura (exercita a booleana)
                v = api("root.create_entity", f, ifc_class="IfcOpeningElement", name="Abertura")
                api("geometry.assign_representation", f, product=v, representation=api("geometry.add_wall_representation", f, context=corpo, length=0.8, height=1.0, thickness=0.6))
                api("geometry.edit_object_placement", f, product=v, matrix=m @ np.array([[1, 0, 0, 0.5], [0, 1, 0, -0.2], [0, 0, 1, 0.5], [0, 0, 0, 1.0]]))
                api("feature.add_feature", f, feature=v, element=e)
        api("spatial.assign_container", f, products=itens, relating_structure=andar)
        f.write(str(saida[esq]))
    return saida

def contagem_python(f, classe):  # classe=None: toda instância
    return sum(1 for _ in f) if classe is None else len(f.by_type(classe))

def guids_com_geometria(f):  # a abertura não é elemento visível: entra só pelo furo da parede
    return sorted(p.GlobalId for p in f.by_type("IfcProduct") if p.Representation and not p.is_a("IfcOpeningElement"))

def versao_conda(pacote, campo="version"):
    for j in (Path(sys.prefix) / "conda-meta").glob(f"{pacote}-[0-9]*.json"):
        return json.loads(j.read_text()).get(campo)

def normalizar(m):  # item de `malhas` (dict ou objeto) -> (vértices Nx3, triângulos Mx3, caixa de 6 números ou None)
    v, i, c = (m[k] if isinstance(m, dict) and k in m else getattr(m, k, None) for k in ("posicoes", "indices", "caixa"))
    return np.asarray(v, float).reshape(-1, 3), np.asarray(i, np.int64).reshape(-1, 3), None if c is None else np.asarray(c, float).ravel()

def por_guid(res, guids):  # `malhas` devolve dict {guid: item} ou lista na ordem pedida
    res = res if isinstance(res, dict) else dict(zip(guids, list(res)))
    return {g: res[g] for g in guids}

def impressao(v, t):  # (triângulos, caixa [mín, máx], volume = soma de tetraedros)
    p = v[t]
    return len(t), np.concatenate([v.min(0), v.max(0)]), abs(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6)

def referencia(f, guids):  # create_shape do Python com as opções da S03 (mundo, sem soldar vértices) e a MESMA biblioteca do C++
    import ifcopenshell.geom
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    cfg.set("weld-vertices", False)
    r = {}
    for g in guids:
        s = ifcopenshell.geom.create_shape(cfg, f.by_guid(g), geometry_library="hybrid-cgal-simple-opencascade").geometry
        r[g] = impressao(np.array(s.verts, float).reshape(-1, 3), np.array(s.faces, np.int64).reshape(-1, 3))
    return r

def diferencas(obtido, ref):  # triângulos exatos; caixa e volume a 1e-6 relativo
    erros = []
    for g, (n, caixa, vol) in ref.items():
        v, t, c = normalizar(obtido[g])
        n2, caixa2, vol2 = impressao(v, t)
        erros += [f"{g}: triângulos {n2} != {n}"] * (n2 != n) + [f"{g}: caixa difere"] * (not np.allclose(caixa2, caixa, rtol=1e-6, atol=1e-9))
        erros += [f"{g}: volume {vol2} != {vol}"] * (not np.isclose(vol2, vol, rtol=1e-6, atol=1e-12))
        erros += [f"{g}: 'caixa' devolvida difere"] * (c is not None and not np.allclose(c, caixa, rtol=1e-6, atol=1e-9))
    return erros

def rss_kb():
    if sys.platform.startswith("linux"):
        return next(int(x.split()[1]) for x in Path("/proc/self/status").read_text().splitlines() if x.startswith("VmRSS"))
    import ctypes  # Windows: PROCESS_MEMORY_COUNTERS = 9 palavras de 8 bytes (cb+contagem, Peak, WorkingSetSize, ...)
    b = (ctypes.c_size_t * 9)()
    b[0] = ctypes.sizeof(b)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1), b, ctypes.sizeof(b))  # -1 = o próprio processo
    return b[2] // 1024

def agrupar(caminhos):  # {núcleo: caminhos reais distintos}; .so, .so.N e .so.N.M resolvem para o mesmo arquivo
    return {k: sorted({os.path.realpath(c) for c in caminhos if re.search(rx, os.path.basename(c))}) for k, rx in NUCLEOS.items()}

def _importar(ordem=("ifcopenshell", "obimcore")):  # obedece a ordem dada (achado 1); o obimcore importa o ifcopenshell sozinho
    global ifcopenshell
    for nome in ordem:
        importlib.import_module(nome)
    import ifcopenshell
    import ifcopenshell.geom  # noqa: F401
    preparar_dono()
    return importlib.import_module("obimcore")

def caso_r1e(ordem, pasta):
    oc = _importar(ordem.split(","))  # ex.: PySide6.QtCore,ifcopenshell,obimcore
    f = ifcopenshell.open(str(Path(pasta) / "s04_ifc4.ifc"))
    referencia(f, guids_com_geometria(f)[:1])  # o Python carrega a geometria (e o OCCT)
    linhas = Path("/proc/self/maps").read_text().splitlines() if sys.platform.startswith("linux") else None
    real = linhas and agrupar({x.split(None, 5)[5] for x in linhas if len(x.split(None, 5)) == 6})  # o que o SO mapeou de fato
    print(json.dumps({"modulo": agrupar(oc.bibliotecas_carregadas()), "real": real}))

PY = SimpleNamespace(contar=contagem_python, endereco=lambda f: f.file_pointer(), ler_nome=lambda f, g: f.by_guid(g).Name,
                     definir_nome=lambda f, g, n: setattr(f.by_guid(g), "Name", n))  # só Python: linha de base de memória do R1-f

def caso_r1f(pasta, base="modulo", voltas=1000):
    oc = PY if base == "base" else _importar()
    import ifcopenshell.api
    caminhos, dif, rss = [Path(pasta) / f"s04_{e.lower()}.ifc" for e in ESQUEMAS], [], {}
    for i in range(1, int(voltas) + 1):
        f = ifcopenshell.open(str(caminhos[i % 3]))  # os três esquemas
        dif += [(i, "contagem", c) for c in ("IfcWall", None) if oc.contar(f, c) != contagem_python(f, c)]
        dif += [(i, "endereco")] * (oc.endereco(f) != f.file_pointer())
        n0 = oc.contar(f, "IfcWall")
        f.begin_transaction()
        p = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="novo")
        f.end_transaction()
        dif += [(i, "criar")] * (oc.contar(f, "IfcWall") != n0 + 1 or oc.contar(f, None) != contagem_python(f, None))
        oc.definir_nome(f, p.GlobalId, f"nome {i}")
        dif += [(i, "nome")] * (p.Name != f"nome {i}" or oc.ler_nome(f, p.GlobalId) != f"nome {i}")
        f.undo()
        dif += [(i, "desfazer")] * (oc.contar(f, "IfcWall") != n0)
        del f, p
        gc.collect()
        rss[i] = rss_kb() if i in (100, int(voltas)) else 0
    print(json.dumps({"diferencas": dif, "rss100": rss[100], "rss_final": rss[int(voltas)], "voltas": int(voltas)}))

def caso_r1g(pasta, voltas=1000):
    oc = _importar()
    caminho, ruins, tem = str(Path(pasta) / "s04_ifc4.ifc"), 0, hasattr(oc, "malhas")  # `malhas` só chega na T04
    for i in range(int(voltas)):
        ifcopenshell.open(caminho)  # destruído antes de qualquer chamada ao C++
        f = ifcopenshell.open(caminho)
        g = guids_com_geometria(f)[:20]
        ref = referencia(f, g) if tem and i < 5 else None
        cena, n = [oc.malhas(f, g)] if tem else [], oc.contar(f, None)  # "malhas na cena": vivas depois que o arquivo morre
        del f
        gc.collect()
        assert oc.contar(ifcopenshell.open(caminho), None) == n
        ruins += bool(ref and diferencas(por_guid(cena[0], g), ref))
    aceitos, f = [], ifcopenshell.open(caminho)
    for ruim in (42, None, "arquivo.ifc", object(), b"x", ifcopenshell.entity_instance, f.by_type("IfcWall")[0]):
        for ch in (lambda r: oc.contar(r, None), oc.endereco, lambda r: oc.ler_nome(r, "x"), lambda r: oc.malhas(r, []) if tem else oc.endereco(r)):
            try:
                ch(ruim)
                aceitos.append(type(ruim).__name__)
            except Exception:  # erro Python limpo; uma queda mataria o processo (código de saída diferente de 0)
                pass
    print(json.dumps({"malhas_ruins": ruins, "aceitos": aceitos, "fim": True}))

if __name__ == "__main__":
    {"r1e": caso_r1e, "r1f": caso_r1f, "r1g": caso_r1g}[sys.argv[1]](*sys.argv[2:])
