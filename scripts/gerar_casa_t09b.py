# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera um IFC4 de demonstração do T09b: paredes simples num pavimento, 2 vistas (planta e corte) e 1 prancha
com as duas. Usa as funções reais de vista/prancha e a gravação do par; no fim apaga o `.obim`, sobrando só o `.ifc`.
Uso: gerar_casa_t09b.py PASTA_DE_SAIDA"""
import math
import sys
import tempfile
from pathlib import Path

import ifcopenshell.api
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

from openbim_app import gravacao_par, vistas_ifc  # noqa: E402
from openbim_app.lateral import Lateral  # noqa: E402
from openbim_app.sessao_modelo import SessaoModelo  # noqa: E402
from openbim_app.transacao import Historico  # noqa: E402

NOME = "Casa-T09b.ifc"


def _base():
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    projeto = api("root.create_entity", f, ifc_class="IfcProject", name="Casa T09b")
    api("unit.assign_unit", f)
    ctx = api("context.add_context", f, context_type="Model")
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    terreno = api("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    predio = api("root.create_entity", f, ifc_class="IfcBuilding", name="Casa")
    piso = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Térreo")
    api("aggregate.assign_object", f, products=[terreno], relating_object=projeto)
    api("aggregate.assign_object", f, products=[predio], relating_object=terreno)
    api("aggregate.assign_object", f, products=[piso], relating_object=predio)
    for nome, comp, x, y, graus in (("Parede 1", 6.0, 0, 0, 0), ("Parede 2", 4.0, 6.0, 0, 90),
                                    ("Parede 3", 6.0, 6.0, 4.0, 180), ("Parede 4", 4.0, 0, 4.0, 270)):
        p = api("root.create_entity", f, ifc_class="IfcWall", name=nome)
        rep = api("geometry.add_wall_representation", f, context=corpo, length=comp, height=2.8, thickness=0.15)
        api("geometry.assign_representation", f, product=p, representation=rep)
        c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
        m = np.array([[c, -s, 0, x], [s, c, 0, y], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        api("geometry.edit_object_placement", f, product=p, matrix=m)
        api("spatial.assign_container", f, products=[p], relating_structure=piso)
    return f


def main(pasta):
    destino = Path(pasta).expanduser().resolve() / NOME
    if destino.exists():
        raise SystemExit(f"recusado: {destino} já existe")
    destino.parent.mkdir(parents=True, exist_ok=True)
    sessao = SessaoModelo(_base())
    lateral = Lateral()
    historico = Historico(sessao, lateral, limite_bytes=None)
    try:
        with sessao.escrever() as esc, historico.transacao(esc) as t:
            planta = vistas_ifc.criar_vista(t.ifc, "Planta Térreo", "PLANTA", escala="1:50",
                                            origem=(1.0, 2.0, 1.2), tamanho=(12.0, 8.0, 3.0))
            corte = vistas_ifc.criar_vista(t.ifc, "Corte AA", "CORTE")
            vistas_ifc.criar_prancha(t.ifc, "A-01", "Plantas e cortes")
            vistas_ifc.colocar_vista(t.ifc, "A-01", corte)
            vistas_ifc.colocar_vista(t.ifc, "A-01", planta)
        with tempfile.TemporaryDirectory() as tmp:
            gravacao_par.gravar_par(sessao=sessao, historico=historico, lateral=lateral, destino=destino,
                                    pasta_projeto=Path(tmp), lado_id="casa-t09b", seq=1)
        destino.with_suffix(".obim").unlink(missing_ok=True)
    finally:
        historico.encerrar()
    print(destino)


if __name__ == "__main__":
    main(sys.argv[1])
