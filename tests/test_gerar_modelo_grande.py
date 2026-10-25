# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do gerador de modelo grande, tamanho pequeno."""
import importlib.util
import multiprocessing
import pathlib

import ifcopenshell
import ifcopenshell.geom

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "gerar_modelo_grande.py"
_spec = importlib.util.spec_from_file_location("gerar_modelo_grande", _SCRIPT)
gm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gm)


def test_abre_e_tem_a_quantidade_pedida(tmp_path):
    p = tmp_path / "g.ifc"
    gm.gerar(p, paredes=50, por_andar=20)
    f = ifcopenshell.open(str(p))
    assert len(f.by_type("IfcWall")) == 50
    assert len(f.by_type("IfcBuildingStorey")) == 3


def test_triangulos_pelo_iterador(tmp_path):
    p = tmp_path / "g.ifc"
    gm.gerar(p, paredes=20, por_andar=10)
    f = ifcopenshell.open(str(p))
    it = ifcopenshell.geom.iterator(ifcopenshell.geom.settings(), f, multiprocessing.cpu_count())
    tri, n = 0, 0
    if it.initialize():
        while True:
            tri += len(it.get().geometry.faces) // 3
            n += 1
            if not it.next():
                break
    assert n == 20
    assert tri == 20 * gm.TRIANGULOS_POR_PAREDE


def test_deterministico(tmp_path):
    a, b = tmp_path / "a.ifc", tmp_path / "b.ifc"
    gm.gerar(a, paredes=30, por_andar=10)
    gm.gerar(b, paredes=30, por_andar=10)
    assert a.read_bytes() == b.read_bytes()
