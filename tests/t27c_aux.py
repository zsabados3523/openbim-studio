# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliares compartilhados do oraculo F1-S01-T27c (usados pelas partes A e B)."""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell.api, numpy as np

from obim_geometria import caixas as geo_caixas, local
from openbim_app import vistas_ifc
from openbim_app.desenho import corte as CO
from test_s06_t27b_corte_cache_oraculo import _add_caixa, _novo_ifc_base, _salvar_e_construir, _sql

RAIZ = Path(__file__).resolve().parents[1]
_STUB_DESENHO = {"ok": True, "svg": "<svg/>", "n_paths": 0, "tempos": {"geo_s": 0.0}, "caixas": []}

def _add_vista_corte(f, nome: str, origem, tamanho, *, angulo_graus: float = 0.0) -> str:
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:50", origem=origem, tamanho=tamanho)
    rad = math.radians(angulo_graus); c, s = math.cos(rad), math.sin(rad)
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(s, -c, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(c, s, 0.0))
    bloco = f.by_guid(gid).Representation.Representations[0].Items[0].TreeRootExpression
    bloco.Position.Location.Coordinates = (-tamanho[0] / 2.0, -tamanho[1] / 2.0, -tamanho[2])
    return gid

def _rodar_selecao(f, gid_vista: str, arq: Path, *, pasta_cache=None, sessao=None, prof=None):
    pedidos: list[dict] = []
    def _exec(ped: dict) -> dict:
        pedidos.append(dict(ped))
        return dict(_STUB_DESENHO) if ped.get("op") == "desenho" else local.executar(ped)
    res = CO.gerar_corte(
        f, gid_vista, caminho_ifc=arq, pasta_cache_geometria=pasta_cache,
        sessao_selecao=sessao, profundidade_corte=prof, ocultar_secundarias=False, executor=_exec,
    )
    return res.selecao, pedidos

def _espiar_caixas(monkeypatch) -> list[set[int]]:
    chamadas: list[set[int]] = []
    real_proc = geo_caixas.processar
    monkeypatch.setattr(geo_caixas, "processar", lambda ped, f=None: (chamadas.append({int(i) for i, _ in ped.get("elementos", ())}), real_proc(ped, f))[1])
    return chamadas

def _cena_variada(tmp_path: Path) -> SimpleNamespace:
    f, body, pav = _novo_ifc_base()
    espec = [
        ("IfcWall", "W1", (0.0, 0.0, 0.0), (4.0, 0.25, 3.0)), ("IfcWall", "W2", (0.0, 3.0, 0.0), (4.0, 0.25, 3.0)),
        ("IfcWall", "W3", (0.0, 0.25, 0.0), (0.25, 2.75, 3.0)), ("IfcWall", "W4", (3.75, 0.25, 0.0), (0.25, 2.75, 3.0)),
        ("IfcColumn", "P1", (1.5, 1.5, 0.0), (0.5, 0.5, 3.0)), ("IfcBeam", "V1", (0.5, 1.0, 2.5), (3.0, 0.25, 0.5)),
        ("IfcSlab", "L1", (0.0, 0.0, -0.25), (4.0, 3.25, 0.25)), ("IfcFurniture", "M1", (2.5, 1.5, 0.0), (1.0, 0.75, 0.75)),
        ("IfcWall", "W_LONGE", (12.0, 12.0, 0.0), (2.0, 0.25, 3.0)),
    ]
    gids = {n: _add_caixa(f, body, pav, cls, n, pos, dim).GlobalId for cls, n, pos, dim in espec}
    vistas = {
        "y_largo": _add_vista_corte(f, "CY_L", (2.0, 0.5, 1.5), (3.0, 2.5, 2.0), angulo_graus=0.0),
        "y_estreito": _add_vista_corte(f, "CY_E", (1.75, 1.0, 1.5), (1.0, 1.5, 1.0), angulo_graus=0.0),
        "x_plano": _add_vista_corte(f, "CX", (1.0, 1.5, 1.5), (2.5, 2.5, 2.0), angulo_graus=-90.0),
        "obliquo": _add_vista_corte(f, "COBL", (2.0, 1.5, 1.5), (3.0, 2.5, 2.5), angulo_graus=30.0),
        "vazio": _add_vista_corte(f, "CVAZ", (-10.0, -10.0, 1.5), (2.0, 2.0, 2.0), angulo_graus=0.0),
    }
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="variada.ifc")
    return SimpleNamespace(arq=arq, pasta=pasta, f=f2, gids=gids, vistas=vistas)

def _assert_sel_eq(nov, ref) -> None:
    assert nov.ids == ref.ids and set(nov.caixas_envolventes) == set(ref.caixas_envolventes)
    assert all(np.allclose(nov.caixas_envolventes[i], ref.caixas_envolventes[i], atol=1e-5) for i in ref.ids)

def _comparar_cache(f2, gid_v: str, arq: Path, pasta: Path):
    ref, nov = _rodar_selecao(f2, gid_v, arq, pasta_cache=None)[0], _rodar_selecao(f2, gid_v, arq, pasta_cache=pasta)[0]
    _assert_sel_eq(nov, ref)
    return ref, nov

def _add_faceset(f, body, pav, nome: str, pos, pts, *, faces=None, tris=None):
    api, coords = ifcopenshell.api.run, f.create_entity("IfcCartesianPointList3D", CoordList=pts)
    el = api("root.create_entity", f, ifc_class="IfcWall", name=nome)
    item = f.create_entity("IfcPolygonalFaceSet", Coordinates=coords, Closed=True, Faces=[f.create_entity("IfcIndexedPolygonalFace", CoordIndex=fi) for fi in faces]) if faces is not None else f.create_entity("IfcTriangulatedFaceSet", Coordinates=coords, Closed=True, CoordIndex=tris)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[f.create_entity("IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body", RepresentationType="Tessellation", Items=[item])])
    m = np.eye(4, dtype=np.float64); m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    api("spatial.assign_container", f, products=[el], relating_structure=pav)
    return el

def _cena_solda(tmp_path: Path, nome: str, *, com_parede: bool = False, y_corte: float = -0.5) -> SimpleNamespace:
    f, body, pav = _novo_ifc_base()
    pts = [(0.9999996, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)]
    w = _add_faceset(f, body, pav, "W_SOLDA", (0.0, 0.0, 0.0), pts, tris=[(1, 2, 3), (5, 3, 4), (5, 4, 2), (2, 4, 3)])
    wb = _add_caixa(f, body, pav, "IfcWall", "W_B", (2.0, 0.0, 0.0), (1.0, 1.0, 1.0)) if com_parede else None
    v1 = _add_vista_corte(f, "C_LARGA", (1.5, -0.5, 0.5), (6.0, 2.0, 2.0))
    v2 = _add_vista_corte(f, "C_SOLDA", (3.0, y_corte, 0.5), (4.0, 2.0, 2.0))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome=nome)
    id_b = f2.by_guid(wb.GlobalId).id() if wb is not None else None
    return SimpleNamespace(arq=arq, pasta=pasta, f=f2, id_solda=f2.by_guid(w.GlobalId).id(), id_b=id_b, v1=v1, v2=v2)
