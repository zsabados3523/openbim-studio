# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15j (parte b): lista aninhada, desempenho, IfcRelProjectsElement e porta não selecionada.
Ref: docs/state/cards/F0-S06/F0-S06-T15j-ifc-reduzido.md (reprovação do revisor)."""
from __future__ import annotations

import re
import time

import ifcopenshell
import pytest

import s06_t07_aux as X
from s05_conteudo_aux import exigir
from test_s06_t15j_reduzido_oraculo import _escrever, _rel, _vao

ESQUEMAS = ("IFC4", "IFC2X3")


def _refs_orfas(caminho):
    """Todo #id referenciado no DATA do STEP tem de ter linha própria (ignora o que está entre apóstrofos)."""
    texto = open(caminho, encoding="utf-8").read().split("DATA;", 1)[1]
    definidos = set(map(int, re.findall(r"^#(\d+)\s*=", texto, re.M)))
    sem_str = re.sub(r"'(?:[^']|'')*'", "''", texto)
    usados = {int(m) for m in re.findall(r"#(\d+)", re.sub(r"^#\d+\s*=", "", sem_str, flags=re.M))}
    return sorted(usados - definidos)


def _vista_pav0(f, pavs):
    return X.vista(f, "PLANTA", pavs[0], tamanho=(10, 10, 3))


def test_fecho_com_lista_aninhada_sem_id_orfao(tmp_path):
    """IFC4: IfcBSplineSurfaceWithKnots tem ControlPointsList = lista de listas de IfcCartesianPoint."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pts = [[f.create_entity("IfcCartesianPoint", Coordinates=(float(i), float(j), 0.0)) for j in range(3)] for i in range(3)]
    sup = f.create_entity("IfcBSplineSurfaceWithKnots", UDegree=2, VDegree=2, ControlPointsList=pts, SurfaceForm="UNSPECIFIED", UClosed=False,
                          VClosed=False, SelfIntersect=False, UMultiplicities=(3, 3), VMultiplicities=(3, 3), UKnots=(0.0, 1.0), VKnots=(0.0, 1.0),
                          KnotSpec="UNSPECIFIED")
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=f.by_type("IfcGeometricRepresentationContext")[0],
                            RepresentationIdentifier="Body", RepresentationType="AdvancedSurface", Items=[sup])
    e = X.elemento(f, "IfcBuildingElementProxy", "Curvo")
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    X.conter(f, pavs[0], e)
    _r, g = _escrever(f, [e], _vista_pav0(f, pavs), tmp_path / "r.ifc")
    assert _refs_orfas(tmp_path / "r.ifc") == []
    s = g.by_id(sup.id())
    assert len(s.ControlPointsList) == 3 and all(len(l) == 3 for l in s.ControlPointsList)
    assert [tuple(p.Coordinates) for l in s.ControlPointsList for p in l] == [(float(i), float(j), 0.0) for i in range(3) for j in range(3)]


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_pavimento_com_3000_elementos_seleciona_50(esq, tmp_path):
    exigir()
    f, pavs = X.estrutura(esq)
    els = [X.elemento(f, "IfcBuildingElementProxy", f"E{i}") for i in range(3000)]
    X.conter(f, pavs[0], *els)
    sel = els[::60]
    assert len(sel) == 50
    t = time.perf_counter()
    r, g = _escrever(f, sel, _vista_pav0(f, pavs), tmp_path / "r.ifc")
    assert time.perf_counter() - t < 10.0
    cont = g.by_type("IfcRelContainedInSpatialStructure")
    assert sorted(e.Name for rel in cont for e in rel.RelatedElements if e.Name.startswith("E")) == sorted(e.Name for e in sel)
    assert {e.Name for e in g.by_type("IfcBuildingElementProxy")} == {e.Name for e in sel}
    assert r["n_entidades"] < 500
    assert _refs_orfas(tmp_path / "r.ifc") == []


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_ifcrelprojectselement_mantida(esq, tmp_path):
    exigir()
    f, pavs = X.estrutura(esq)
    par = X.caixa(f, "IfcWall", "Parede", 0, 0, 0, 5, 0.25, 3)
    proj = X.caixa(f, "IfcProjectionElement", "Saliencia", 1, -0.1, 0, 1, 0.1, 1)
    X.conter(f, pavs[0], par)
    rel = _rel(f, "IfcRelProjectsElement", RelatingElement=par, RelatedFeatureElement=proj)
    for sel in ([par, proj], [par]):
        _r, g = _escrever(f, sel, _vista_pav0(f, pavs), tmp_path / f"r{len(sel)}.ifc")
        rs = g.by_type("IfcRelProjectsElement")
        assert [r.id() for r in rs] == [rel.id()], len(sel)
        assert rs[0].RelatingElement.GlobalId == par.GlobalId and rs[0].RelatedFeatureElement.GlobalId == proj.GlobalId
        assert _refs_orfas(tmp_path / f"r{len(sel)}.ifc") == []


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_porta_nao_selecionada_na_mesma_parede_fica_de_fora(esq, tmp_path):
    exigir()
    f, pavs = X.estrutura(esq)
    par = X.caixa(f, "IfcWall", "Parede", 0, 0, 0, 5, 0.25, 3)
    X.conter(f, pavs[0], par)
    oa, da = _vao(f, esq, "PortaA", par, 0.5)
    ob, db = _vao(f, esq, "PortaB", par, 3.0)
    _r, g = _escrever(f, [par, oa, da], _vista_pav0(f, pavs), tmp_path / "r.ifc")
    assert {d.Name for d in g.by_type("IfcDoor")} == {"PortaA"}
    assert "VPortaA" in {o.Name for o in g.by_type("IfcOpeningElement")}  # a abertura B pode entrar (vem da relação Voids da parede); a porta B não
    for rel in g.by_type("IfcRelFillsElement"):
        assert rel.RelatedBuildingElement.Name == "PortaA"
    for rel in g.by_type("IfcRelDefinesByType"):
        assert [o.Name for o in rel.RelatedObjects] == ["PortaA"]
    with pytest.raises(RuntimeError):
        g.by_id(db.id())
    assert _refs_orfas(tmp_path / "r.ifc") == []
