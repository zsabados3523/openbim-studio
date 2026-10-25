# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera um IFC grande e sintético para o benchmark, só com IfcOpenShell, sem dado de
terceiros. Repete paredes (caixas de 12 triângulos) em andares. Mesma quantidade = mesmo arquivo.
Uso: gerar_modelo_grande.py SAIDA.ifc [--paredes N] [--por-andar M]"""
import argparse
import math
import uuid

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import numpy as np

TRIANGULOS_POR_PAREDE = 12  # caixa: 6 faces x 2 triângulos
_NS = uuid.UUID("6f1b6f0e-0b1d-4a5e-9b0e-0d1f5a7c9e11")  # fixo, para GlobalIds repetíveis


def _guid(nome):
    return ifcopenshell.guid.compress(uuid.uuid5(_NS, nome).hex)


def gerar(saida, paredes=1000, por_andar=200):
    """Escreve um IFC4 com `paredes` IfcWall distribuídas em andares de `por_andar` paredes."""
    if paredes < 1 or por_andar < 1:
        raise ValueError("paredes e por_andar devem ser >= 1")
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    projeto = api("root.create_entity", f, ifc_class="IfcProject", name="Modelo grande (sintetico)")
    api("unit.assign_unit", f)
    for ua in f.by_type("IfcUnitAssignment"):  # a API monta as unidades com conjunto: fixar a ordem
        ua.Units = sorted(ua.Units, key=lambda u: u.id())
    ctx = api("context.add_context", f, context_type="Model")
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    terreno = api("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    predio = api("root.create_entity", f, ifc_class="IfcBuilding", name="Predio")
    # relações criadas direto, com listas em ordem fixa (a API usa conjuntos e muda a ordem)
    filhos = {projeto: [terreno], terreno: [predio], predio: []}
    contidos = {}
    colunas = max(1, math.isqrt(por_andar))
    andar = None
    for i in range(paredes):
        if i % por_andar == 0:
            n = i // por_andar
            andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name=f"Andar {n + 1}")
            filhos[predio].append(andar)
            contidos[andar] = []
        k = i % por_andar
        p = api("root.create_entity", f, ifc_class="IfcWall", name=f"Parede {i + 1}")
        rep = api("geometry.add_wall_representation", f, context=corpo, length=3.0, height=2.8, thickness=0.15)
        api("geometry.assign_representation", f, product=p, representation=rep)
        m = np.eye(4)
        m[0, 3], m[1, 3], m[2, 3] = (k % colunas) * 4.0, (k // colunas) * 4.0, (i // por_andar) * 3.0
        api("geometry.edit_object_placement", f, product=p, matrix=m)
        contidos[andar].append(p)
    for pai, lista in filhos.items():
        f.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=pai, RelatedObjects=lista)
    for andar, lista in contidos.items():
        f.create_entity(
            "IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(), RelatingStructure=andar, RelatedElements=lista
        )
    # GlobalIds, relações e cabeçalho fixos: o arquivo não muda entre execuções
    for e in f:
        if hasattr(e, "GlobalId") and e.GlobalId:
            e.GlobalId = _guid(f"{e.is_a()}#{e.id()}")
    f.header.file_name.time_stamp = "2000-01-01T00:00:00"
    f.write(str(saida))
    return paredes


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("saida")
    a.add_argument("--paredes", type=int, default=1000, help="quantidade de paredes (12 triângulos cada)")
    a.add_argument("--por-andar", type=int, default=200)
    x = a.parse_args()
    n = gerar(x.saida, x.paredes, x.por_andar)
    print(f"{n} paredes, {n * TRIANGULOS_POR_PAREDE} triângulos esperados -> {x.saida}")


if __name__ == "__main__":
    main()
