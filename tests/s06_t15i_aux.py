# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15i: reaproveitamento de caixas 2D de móveis no corte e planta.
Ref: docs/state/cards/F0-S06/F0-S06-T15i-caixas2d-moveis.md.
"""

from __future__ import annotations

import copy

import dataclasses

from pathlib import Path

import re

import sys

from typing import Any

import ifcopenshell

import ifcopenshell.geom

import ifcopenshell.util.unit

import pytest

import s06_t07_aux as X

from s05_conteudo_aux import _limpa, exigir  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent

GEOMETRIA = RAIZ / "geometria"

if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.desenho as desenho_geo

import obim_geometria.local as local

from openbim_app import vistas_ifc

from openbim_app.desenho import auxiliar, corte, planta, selecao

class ExecutorEspiao:
    """Grava pedidos enviados ao executor auxiliar."""

    def __init__(self, delegate=local.executar):
        self.delegate = delegate
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, pedido: dict[str, Any]) -> dict[str, Any]:
        self.chamadas.append(copy.deepcopy(pedido))
        return self.delegate(pedido)

    @property
    def pedidos_desenho(self) -> list[dict[str, Any]]:
        return [p for p in self.chamadas if p.get("op") == "desenho"]

def _espia_cs(monkeypatch) -> list[int]:
    chamadas: list[int] = []
    real = ifcopenshell.geom.create_shape

    def espia(*args, **kwargs):
        el = args[1] if len(args) > 1 else kwargs.get("element")
        if el is not None:
            chamadas.append(el.id())
        return real(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "create_shape", espia)
    return chamadas

def _dimensoes_svg(svg: str, guid: str) -> tuple[float, float]:
    m = re.search(rf'<g\b[^>]*\b(?:ifc:)?guid=["\']{re.escape(guid)}["\'][^>]*>(.*?)</g>', svg, re.DOTALL)
    assert m is not None, f"Grupo guid={guid} ausente no SVG"
    d_m = re.search(r'\bd=["\']([^"\']+)["\']', m.group(1))
    assert d_m is not None, f"d ausente no grupo guid={guid}"
    nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", d_m.group(1))]
    xs, ys = nums[0::2], nums[1::2]
    return max(xs) - min(xs), max(ys) - min(ys)

def _criar_corte_xyz(f: Any, nome: str, xmin: float, xmax: float, ymin: float, ymax: float, zmin: float, zmax: float, k: float = 1.0) -> str:
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=(xmin * k, ymin * k, zmin * k), tamanho=(dx * k, dz * k, dy * k))
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -dy * k))
    return gid

def _modelo_parede_movel(schema: str = "IFC4", k: float = 1.0):
    exigir()
    f, pavs = X.estrutura(schema)
    if k != 1.0:
        X.em_milimetros(f)
    parede = X.caixa(f, "IfcWall", "Parede", 0.5 * k, 1.0 * k, 0.0 * k, 2.0 * k, 0.2 * k, 2.8 * k)
    movel = X.caixa(f, "IfcFurniture", "Movel", 1.0 * k, 1.0 * k, 0.0 * k, 1.0 * k, 0.6 * k, 1.2 * k)
    X.conter(f, pavs[0], parede, movel)
    gid_corte = _criar_corte_xyz(f, f"Corte_{schema}_{int(k)}", 0.0, 6.0, 0.0, 4.0, 0.0, 3.5, k=k)
    gid_planta = X.vista(f, "PLANTA", pavs[0], nome=f"Planta_{schema}_{int(k)}")
    return f, gid_corte, gid_planta, parede, movel, pavs[0]

def _grupo_path(svg: str, guid: str) -> tuple[list[tuple[float, float]], str]:
    """Pontos (x, y) absolutos do <path> do grupo guid e sua classe CSS."""
    m = re.search(rf'<g\b[^>]*\b(?:ifc:)?guid=["\']{re.escape(guid)}["\'][^>]*>(.*?)</g>', svg, re.DOTALL)
    assert m is not None, f"Grupo guid={guid} ausente no SVG"
    tag = re.search(r"<path\b[^>]*>", m.group(1))
    assert tag is not None, f"<path> ausente no grupo guid={guid}"
    d_m = re.search(r'\bd=["\']([^"\']+)["\']', tag.group(0))
    assert d_m is not None
    nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", d_m.group(1))]
    assert len(nums) == 10, f"Esperados 5 pontos (retângulo fechado), obtido {nums}"
    c_m = re.search(r'\bclass=["\']([^"\']*)["\']', tag.group(0))
    return list(zip(nums[0::2], nums[1::2])), (c_m.group(1) if c_m else "")

def _pts_aprox(a, b, tol=2e-3):
    assert len(a) == len(b)
    for (x0, y0), (x1, y1) in zip(a, b):
        assert x0 == pytest.approx(x1, abs=tol) and y0 == pytest.approx(y1, abs=tol), f"{a} != {b}"

def _pedido_planta(f, movel, pav, alt, caixas):
    return {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "PLANTA", "altura_corte_m": alt, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId},
        "moveis_como_caixa": True,
        "caixas_coords": caixas,
    }

def _rodar_planta(f, pedido):
    with auxiliar.preparar(f, pedido) as p:
        return desenho_geo.processar(p.pedido)

def _modelo_planta_assimetrico():
    """Móvel real em [1,2,0 , 4,7,1] (XYZ todos distintos, não cúbico) fora da origem."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    movel = X.caixa(f, "IfcFurniture", "MovelA", 1.0, 2.0, 0.0, 3.0, 5.0, 1.0)
    X.conter(f, pavs[0], movel)
    return f, movel, pavs[0]

def _modelo_corte_deslocado(ycam: float):
    """Móvel real [1.5,0.7,0.2 , 3.5,2.0,1.1] (não cúbico); câmera deslocada da origem em (0.4, ycam, 0.3)."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    movel = X.caixa(f, "IfcFurniture", "MovelC", 1.5, 0.7, 0.2, 2.0, 1.3, 0.9)
    X.conter(f, pavs[0], movel)
    gid = _criar_corte_xyz(f, f"CorteDesl_{ycam}", 0.4, 6.4, ycam, ycam + 4.0, 0.3, 3.8)
    return f, gid, movel

_CAIXA_C = [1.5, 0.7, 0.2, 3.5, 2.0, 1.1]

def _pedido_corte(gid, movel, caixas):
    ped = {
        "op": "desenho", "protocolo": 1, "elementos": [[movel.id(), movel.GlobalId]],
        "vista": {"tipo": "CORTE", "guid": gid, "escala": 1.0},
        "moveis_caixa2d": True,
    }
    if caixas is not None:
        ped["caixas_coords"] = caixas
    return ped

_NAN, _INF = float("nan"), float("inf")

_INVALIDAS = {
    "nan": [_NAN, 1.0, 0.0, 2.0, 2.0, 1.0],
    "nan_no_fim": [1.0, 1.0, 0.0, 2.0, 2.0, _NAN],
    "inf": [1.0, 1.0, 0.0, _INF, 2.0, 1.0],
    "menos_inf": [-_INF, 1.0, 0.0, 2.0, 2.0, 1.0],
    "curta5": [1.0, 1.0, 0.0, 2.0, 2.0],
    "vazia": [],
    "none": None,
    "string": "1,1,0,2,2,1",
    "strings_nao_numericas": ["a", "b", "c", "d", "e", "f"],
    "numero": 5.0,
    "invertida_x": [2.0, 1.0, 0.0, 1.0, 2.0, 1.0],
    "invertida_y": [1.0, 2.0, 0.0, 2.0, 1.0, 1.0],
    "invertida_z": [1.0, 1.0, 1.0, 2.0, 2.0, 0.0],
}

__all__ = ['Any', 'ExecutorEspiao', 'GEOMETRIA', 'Path', 'RAIZ', 'X', '_CAIXA_C', '_INVALIDAS', '_criar_corte_xyz', '_dimensoes_svg', '_espia_cs', '_grupo_path', '_limpa', '_modelo_corte_deslocado', '_modelo_parede_movel', '_modelo_planta_assimetrico', '_pedido_corte', '_pedido_planta', '_pts_aprox', '_rodar_planta', 'auxiliar', 'copy', 'corte', 'dataclasses', 'desenho_geo', 'exigir', 'ifcopenshell', 'local', 'planta', 'pytest', 're', 'selecao', 'sys', 'vistas_ifc']
