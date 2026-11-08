# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15j: IFC reduzido (mesmos id_step, escape, relações, igualdade de SVG com o completo).
Ref: docs/state/cards/F0-S06/F0-S06-T15j-ifc-reduzido.md. Hoje falha: o módulo `openbim_app.desenho.reduzido` ainda não existe."""
from __future__ import annotations

import importlib
import inspect
import locale
import os

import ifcopenshell
import ifcopenshell.guid as G
import pytest

import s06_t07_aux as X
from s05_conteudo_aux import exigir
from s06_t15i_aux import _criar_corte_xyz, auxiliar, desenho_geo

ESQUEMAS = ("IFC4", "IFC2X3")
ESPECIAIS = ["D'Ávila", "a\\b", "Móvel ação", "porta \U0001F6AA", "fim\\", "''", "lit \\X2\\00F3\\X0\\ \\S\\a", "x\\\\'y"]


def _reduzido():
    """Import tardio: sem o módulo, o teste FALHA com ImportError claro (não pula)."""
    return importlib.import_module("openbim_app.desenho.reduzido")


def _tipo(f, esq, nome):
    cls, kw = ("IfcDoorType", dict(PredefinedType="DOOR", OperationType="SINGLE_SWING_LEFT")) if esq != "IFC2X3" else (
        "IfcDoorStyle", dict(OperationType="SINGLE_SWING_LEFT", ConstructionType="NOTDEFINED", ParameterTakesPrecedence=False, Sizeable=False))
    return f.create_entity(cls, GlobalId=G.new(), Name=nome, **kw, **X.kw(f))


def _rel(f, cls, **kw):
    return f.create_entity(cls, GlobalId=G.new(), **kw, **X.kw(f))


def _vao(f, esq, nome, hosp, x, tipado=True):
    o = X.caixa(f, "IfcOpeningElement", "V" + nome, x, 0, 0, 1, 0.25, 2)
    d = X.caixa(f, "IfcDoor", nome, x, 0, 0, 1, 0.25, 2)
    _rel(f, "IfcRelVoidsElement", RelatingBuildingElement=hosp, RelatedOpeningElement=o)
    _rel(f, "IfcRelFillsElement", RelatingOpeningElement=o, RelatedBuildingElement=d)
    if tipado:
        _rel(f, "IfcRelDefinesByType", RelatedObjects=[d], RelatingType=_tipo(f, esq, "Tipo " + nome))
    return o, d


def _modelo(esq):
    """Parede, porta com arco (tipo), janela, móvel, nomes com apóstrofo/acento, 30 extras no mesmo pavimento e um pavimento só de extras."""
    exigir()
    f, pavs = X.estrutura(esq, n_pav=3)
    par = X.caixa(f, "IfcWall", "Parede D'Ávila", 0, 0, 0, 5, 0.25, 3)
    jan = X.caixa(f, "IfcWindow", "Janela ação", 3.25, 0, 1, 1, 0.25, 1)
    mov = X.caixa(f, X.MOVEL[esq], "Móvel D'Ávila", 1, 2, 0, 1, 0.5, 0.5)
    extras = [X.caixa(f, "IfcBuildingElementProxy", f"Extra{i}", 6 + i, 3, 0, 0.2, 0.2, 0.2) for i in range(30)]
    X.conter(f, pavs[0], par, jan, mov, *extras)
    X.conter(f, pavs[2], X.caixa(f, "IfcBuildingElementProxy", "ExtraAlto", 0, 0, 6, 1, 1, 1))
    o, d = _vao(f, esq, "Porta Nº1", par, 1.0)
    gp = X.vista(f, "PLANTA", pavs[0], tamanho=(10, 10, 3))
    gc = _criar_corte_xyz(f, "Corte", -0.5, 6.0, -1.0, 2.0, -0.5, 3.5)
    sel = [par, o, d, jan, mov]
    return f, sel, gp, gc, extras, pavs


def _escrever(f, sel, gid, saida):
    r = _reduzido().escrever_reduzido(f, [e.id() for e in sel], f.by_guid(gid).id(), str(saida))
    return r, ifcopenshell.open(str(saida))


def _norm(svg):
    return "\n".join(l for l in svg.splitlines() if l.strip())


def _svg(f, ped, caminho=None):
    with auxiliar.preparar(f, ped, caminho_ifc=caminho) as p:
        r = desenho_geo.processar(p.pedido)
    assert r["ok"] is True
    return _norm(r["svg"])


def _pedido(sel, vista):
    return {"op": "desenho", "protocolo": 1, "elementos": [[e.id(), e.GlobalId] for e in sel], "vista": vista, "moveis_como_caixa": True, "moveis_caixa2d": True}


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_mesmos_id_step_e_retorno(esq, tmp_path):
    f, sel, gp, _gc, _ex, _pavs = _modelo(esq)
    r, g = _escrever(f, sel, gp, tmp_path / "r.ifc")
    ids = [e.id() for e in sel] + [f.by_guid(gp).id()]
    for rel in ("IfcRelVoidsElement", "IfcRelFillsElement", "IfcRelDefinesByType"):
        ids += [x.id() for x in f.by_type(rel)]
    for i in ids:
        assert g.by_id(i).is_a() == f.by_id(i).is_a() and g.by_id(i).GlobalId == f.by_id(i).GlobalId
    assert g.schema == f.schema
    assert g.by_type("IfcProject")[0].UnitsInContext is not None and g.by_type("IfcGeometricRepresentationContext")
    assert isinstance(r["n_entidades"], int) and r["n_entidades"] > 0
    assert r["mb"] == pytest.approx(os.path.getsize(tmp_path / "r.ifc") / 1e6, rel=0.01)


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_escape_ida_e_volta_do_nome(esq, tmp_path):
    f, sel, gp, _gc, _ex, pavs = _modelo(esq)
    alvos = sel[:1] + sel[3:] + [pavs[0], f.by_type("IfcSite")[0]]
    for e, nome in zip(alvos, ESPECIAIS):
        e.Name = nome
    f.by_guid(gp).Name = ESPECIAIS[-1]
    _r, g = _escrever(f, sel, gp, tmp_path / "r.ifc")
    for e, nome in zip(alvos, ESPECIAIS):
        assert g.by_id(e.id()).Name == nome, repr(nome)
    assert g.by_guid(gp).Name == ESPECIAIS[-1]


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_porta_mantem_tipo_e_arco(esq, tmp_path):
    f, sel, gp, _gc, _ex, _pavs = _modelo(esq)
    _r, g = _escrever(f, sel, gp, tmp_path / "r.ifc")
    porta = g.by_id(sel[2].id())
    tipo = porta.IsTypedBy[0].RelatingType if esq != "IFC2X3" else next(r.RelatingType for r in g.get_inverse(porta) if r.is_a("IfcRelDefinesByType"))
    assert tipo.OperationType == "SINGLE_SWING_LEFT"
    sem = _modelo(esq)  # mesmo modelo com a porta SEM tipo: o completo perde o arco, logo o arco existe no completo tipado
    for r in sem[0].by_type("IfcRelDefinesByType"):
        sem[0].remove(r)
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0, 0, 0], "escala": 1.0, "pavimento": f.by_guid(f.by_type("IfcBuildingStorey")[0].GlobalId).GlobalId}
    com = _svg(f, _pedido(sel, vista))
    sem_svg = _svg(sem[0], _pedido(sem[1], dict(vista, pavimento=sem[0].by_type("IfcBuildingStorey")[0].GlobalId)))
    assert com.count("<path") == sem_svg.count("<path") + 1, "o tipo da porta deve dar o caminho do arco"


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_hospedeiro_de_outro_pavimento_com_contained_e_aggregates(esq, tmp_path):
    exigir()
    f, pavs = X.estrutura(esq, n_pav=3)
    h1 = X.caixa(f, "IfcWall", "H1", 0, 0, 3, 4, 0.25, 3)
    h2 = X.caixa(f, "IfcWall", "H2", 0, 5, 3, 4, 0.25, 3)
    conj = X.elemento(f, "IfcElementAssembly", "Conj")
    X.conter(f, pavs[1], h1, conj)
    X.agregar(f, conj, h2)
    o1, d1 = _vao(f, esq, "D1", h1, 1.0)
    o2, d2 = _vao(f, esq, "D2", h2, 1.0)
    gp = X.vista(f, "PLANTA", pavs[0], tamanho=(10, 10, 3))
    _r, g = _escrever(f, [o1, d1, o2, d2], gp, tmp_path / "r.ifc")
    for h in (h1, h2):
        assert g.by_id(h.id()).GlobalId == h.GlobalId
    assert g.by_id(h1.id()).ContainedInStructure[0].RelatingStructure.GlobalId == pavs[1].GlobalId
    assert g.by_id(h2.id()).Decomposes[0].RelatingObject.GlobalId == conj.GlobalId
    assert g.by_id(conj.id()).ContainedInStructure[0].RelatingStructure.GlobalId == pavs[1].GlobalId
    assert g.by_id(pavs[1].id()).Decomposes[0].RelatingObject.is_a("IfcBuilding")


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_listas_filtradas_e_relacao_vazia_descartada(esq, tmp_path):
    f, sel, gp, _gc, extras, pavs = _modelo(esq)
    X.agregar(f, f.by_type("IfcBuilding")[0], X.elemento(f, "IfcElementAssembly", "SoExtras"))  # relação cujo único relacionado fica de fora
    outro = X.elemento(f, "IfcElementAssembly", "Orfa")
    X.agregar(f, outro, X.elemento(f, "IfcElementAssembly", "FilhoOrfao"))
    _r, g = _escrever(f, sel, gp, tmp_path / "r.ifc")
    nomes = {e.Name for e in g.by_type("IfcRoot") if e.Name}
    assert not any(n.startswith("Extra") for n in nomes) and not {"Orfa", "FilhoOrfao", "SoExtras"} & nomes
    assert pavs[2].GlobalId not in {e.GlobalId for e in g.by_type("IfcBuildingStorey")}
    cont = g.by_type("IfcRelContainedInSpatialStructure")
    assert cont and {e.Name for r in cont for e in r.RelatedElements} == {"Parede D'Ávila", "Janela ação", "Móvel D'Ávila", "V"}
    for r in g.by_type("IfcRelAggregates"):
        assert len(r.RelatedObjects) >= 1
    for r in g.by_type("IfcRelDefinesByType"):
        assert len(r.RelatedObjects) == 1
    assert {r.id() for r in g.by_type("IfcRelAggregates")} <= {r.id() for r in f.by_type("IfcRelAggregates")}


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_svg_planta_e_corte_do_reduzido_igual_ao_completo(esq, tmp_path):
    f, sel, gp, gc, _ex, pavs = _modelo(esq)
    planta = _pedido(sel, {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0, 0, 0], "escala": 1.0, "pavimento": pavs[0].GlobalId})
    corte = _pedido(sel, {"tipo": "CORTE", "guid": gc, "escala": 1.0})
    for ped, gid in ((planta, gp), (corte, gc)):
        completo = _svg(f, ped)
        assert sel[4].GlobalId in completo and completo.count("<path") >= 8, "o SVG completo precisa ter conteúdo para a comparação valer"
        _r, _g = _escrever(f, sel, gid, tmp_path / "r.ifc")
        assert _svg(None, ped, caminho=tmp_path / "r.ifc") == completo, ped["vista"]["tipo"]


@pytest.mark.parametrize("esq", ESQUEMAS)
def test_independente_de_lc_numeric(esq, tmp_path):
    f, sel, gp, _gc, _ex, _pavs = _modelo(esq)
    sel[3].ObjectPlacement.RelativePlacement.Location.Coordinates = (3.2578125, 0.0, 1.0)
    antigo = locale.setlocale(locale.LC_NUMERIC)
    for cand in ("de_DE.UTF-8", "pt_BR.UTF-8", "de_DE", "fr_FR.UTF-8"):
        try:
            locale.setlocale(locale.LC_NUMERIC, cand)
            break
        except locale.Error:
            continue
    else:
        pytest.skip("sem localidade com vírgula decimal instalada")
    try:
        assert locale.localeconv()["decimal_point"] == ","
        _r, g = _escrever(f, sel, gp, tmp_path / "r.ifc")
    finally:
        locale.setlocale(locale.LC_NUMERIC, antigo)
    assert tuple(g.by_id(sel[3].id()).ObjectPlacement.RelativePlacement.Location.Coordinates) == (3.2578125, 0.0, 1.0)


def test_modulo_nao_usa_ifcopenshell_geom():
    src = inspect.getsource(_reduzido())
    assert "ifcopenshell.geom" not in src and "import geom" not in src
