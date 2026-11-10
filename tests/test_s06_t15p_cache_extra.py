# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extras do F0-S06-T15p: ids zero, anotacao da vista na chave, limpar() so de cache."""
import os
import time

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")
from openbim_app.desenho import cache as M  # noqa: E402


def _pedido(guid_vista=None):
    return {"elementos": [], "vista": {"guid": guid_vista} if guid_vista else {}}


def test_tipos_simples_id_zero_nao_viram_ref():
    f = ifcopenshell.file(schema="IFC4")
    a = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="a")
    ls = [f.create_entity("IfcLengthMeasure", 1.0), f.create_entity("IfcLengthMeasure", 2.0)]
    s1 = M._serializar(ls, set())
    assert "$ref" not in repr(s1)
    assert s1[0] != s1[1] and a.id() > 0


def test_anotacao_da_vista_entra_na_chave():
    f = ifcopenshell.file(schema="IFC4")
    proj = f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="P")
    anot = f.create_entity("IfcAnnotation", GlobalId=ifcopenshell.guid.new(), Name="V")
    c = M.CacheDesenho("/nao/usado")
    k1 = c.chave(f, _pedido(anot.GlobalId))
    anot.Name = "V2"
    k2 = c.chave(f, _pedido(anot.GlobalId))
    assert k1 != k2 and proj


def test_limpar_apaga_so_arquivos_de_cache(tmp_path):
    c = M.CacheDesenho(tmp_path, idade_max_s=1)
    velho = time.time() - 100
    nomes = ["a.json", ".x.tmp", "nota.txt", "b.png"]
    for n in nomes:
        p = tmp_path / n
        p.write_text("x")
        os.utime(p, (velho, velho))
    assert c.limpar() == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.png", "nota.txt"]
