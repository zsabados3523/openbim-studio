# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera o IFC de amostra do roteiro de aceite: uma casa simples (4 paredes e 1 laje) feita só com
IfcOpenShell, sem nenhum dado de terceiros. Uso: gerar_casa_simples.py SAIDA.ifc"""
import sys

import ifcopenshell
import ifcopenshell.api


def main(saida):
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    projeto = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Casa simples (amostra)")
    ifcopenshell.api.run("unit.assign_unit", f)
    ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    corpo = ifcopenshell.api.run(
        "context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx
    )
    terreno = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    predio = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Casa")
    piso = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Térreo")
    ifcopenshell.api.run("aggregate.assign_object", f, products=[terreno], relating_object=projeto)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[predio], relating_object=terreno)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[piso], relating_object=predio)

    def parede(nome, comp, x, y, graus):
        p = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name=nome)
        rep = ifcopenshell.api.run("geometry.add_wall_representation", f, context=corpo, length=comp, height=2.8, thickness=0.15)
        ifcopenshell.api.run("geometry.assign_representation", f, product=p, representation=rep)
        import math, numpy as np

        c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
        m = np.array([[c, -s, 0, x], [s, c, 0, y], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=p, matrix=m)
        ifcopenshell.api.run("spatial.assign_container", f, products=[p], relating_structure=piso)

    parede("Parede 1", 6.0, 0, 0, 0)
    parede("Parede 2", 4.0, 6.0, 0, 90)
    parede("Parede 3", 6.0, 6.0, 4.0, 180)
    parede("Parede 4", 4.0, 0, 4.0, 270)
    laje = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSlab", name="Laje do piso")
    ifcopenshell.api.run("spatial.assign_container", f, products=[laje], relating_structure=piso)
    f.write(saida)


if __name__ == "__main__":
    main(sys.argv[1])
