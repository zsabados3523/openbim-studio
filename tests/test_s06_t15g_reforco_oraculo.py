# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo F0-S06-T15g: compatibilidade com estilo 2D e suporte a milímetros no pré-filtro XY.
Cartão: docs/state/cards/F0-S06/F0-S06-T15g-culling-xy-moveis-corte.md.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import sys
from typing import Any

import pytest

import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app import vistas_ifc
from openbim_app.desenho import corte, estilo, selecao


class ExecutorEspiao:
    """Intermediário que armazena requisições do processo auxiliar para inspeção."""

    def __init__(self, delegate=local.executar):
        self.delegate = delegate
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, pedido: dict[str, Any]) -> dict[str, Any]:
        self.chamadas.append(copy.deepcopy(pedido))
        return self.delegate(pedido)

    @property
    def pedidos_caixas(self) -> list[dict[str, Any]]:
        return [p for p in self.chamadas if p.get("op") == "caixas"]

    @property
    def ids_pedidos_caixas(self) -> set[int]:
        return {item[0] for p in self.pedidos_caixas for item in p.get("elementos", [])}


def _criar_corte_xyz(
    f: Any,
    nome: str,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    k: float = 1.0,
) -> str:
    """Cria vista CORTE cobrindo o paralelepípedo [xmin, xmax] x [ymin, ymax] x [zmin, zmax]."""
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    tamanho = (dx * k, dz * k, dy * k)
    origem = (xmin * k, ymin * k, zmin * k)
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=origem, tamanho=tamanho)
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -dy * k))
    return gid


def _modelo_parede_movel(schema: str = "IFC4"):
    """Modelo com parede cortada e móvel (IfcFurniture) na vista de corte."""
    exigir()
    f, pavs = X.estrutura(schema)
    parede = X.caixa(f, "IfcWall", "Parede", 0.5, -0.1, 0.0, 4.0, 0.2, 2.8)
    movel = X.caixa(f, "IfcFurniture", "Movel", 1.0, -0.1, 0.0, 1.0, 0.6, 1.2)
    X.conter(f, pavs[0], parede, movel)
    gid = _criar_corte_xyz(f, f"Corte_Moveis_{schema}", xmin=-0.5, xmax=6.5, ymin=0.0, ymax=5.0, zmin=-0.5, zmax=3.5)
    return f, gid, parede, movel


def test_compatibilidade_estilo_corte_caixa2d():
    """Caso 6: SVG gerado com móveis caixa 2D no corte é processado com sucesso por estilo.aplicar_estilo."""
    f, gid, parede, movel = _modelo_parede_movel("IFC4")
    c = corte.gerar_corte(f, gid, moveis_caixa2d=True, executor=local.executar)

    svg_50 = estilo.aplicar_estilo(c.svg, "1:50")
    assert isinstance(svg_50, str) and "<svg" in svg_50 and "</svg>" in svg_50
    assert B.svg_valido(svg_50), "SVG estilizado em 1:50 deve ser XML válido"
    assert 'viewBox="' in svg_50
    assert 'width="' in svg_50 and 'height="' in svg_50
    assert "<style" in svg_50
    assert movel.GlobalId in svg_50
    assert parede.GlobalId in svg_50

    svg_100 = estilo.aplicar_estilo(c.svg, "1:100")
    assert isinstance(svg_100, str) and B.svg_valido(svg_100), "SVG estilizado em 1:100 deve ser XML válido"
    assert movel.GlobalId in svg_100


def test_pre_filtro_xy_corte_respeita_unidade_milimetros():
    """Pré-filtro XY seguro em CORTE converte a coordenada mundial com scale em modelos em milímetros."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    X.em_milimetros(f)
    k = 1000.0
    pav = pavs[0]

    par1 = X.caixa(f, "IfcWall", "Par1MM", 2000.0, 1000.0, 0.0, 2000.0, 200.0, 2500.0)
    par2_pos = X.caixa(f, "IfcWall", "Par2PosMM", 50000.0, 1000.0, 0.0, 2000.0, 200.0, 2500.0)
    par2_neg = X.caixa(f, "IfcWall", "Par2NegMM", -20000.0, 1000.0, 0.0, 2000.0, 200.0, 2500.0)
    X.conter(f, pav, par1, par2_pos, par2_neg)

    gid = _criar_corte_xyz(f, "Corte_MM", xmin=0.0, xmax=10.0, ymin=0.0, ymax=5.0, zmin=0.0, zmax=3.0, k=k)
    espiao = ExecutorEspiao()
    sel = selecao.selecionar(f, gid, executor=espiao)

    assert par2_pos.id() not in espiao.ids_pedidos_caixas, "Parede a +50 m deve ser podada em mm"
    assert par2_neg.id() not in espiao.ids_pedidos_caixas, "Parede a -20 m deve ser podada em mm"
    assert par2_pos.id() not in sel.ids
    assert par2_neg.id() not in sel.ids
    assert par1.id() in espiao.ids_pedidos_caixas
    assert par1.id() in sel.ids


def test_corte_moveis_caixa2d_unidade_milimetros():
    """Gera corte com moveis_caixa2d=True em modelo com unidade milímetro (k=0.001).
    Verifica que c.caixas contém o móvel e que as coordenadas no SVG estão na faixa esperada em metros."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    X.em_milimetros(f)
    k = 1000.0
    pav = pavs[0]

    parede = X.caixa(f, "IfcWall", "ParedeMM", 500.0, -100.0, 0.0, 4000.0, 200.0, 2800.0)
    movel = X.caixa(f, "IfcFurniture", "MovelMM", 1000.0, -100.0, 0.0, 1000.0, 600.0, 1200.0)
    X.conter(f, pav, parede, movel)

    gid = _criar_corte_xyz(f, "Corte_MM_Moveis", xmin=-0.5, xmax=6.5, ymin=0.0, ymax=5.0, zmin=-0.5, zmax=3.5, k=k)
    c = corte.gerar_corte(f, gid, moveis_caixa2d=True, executor=local.executar)

    assert c.unidade_escala == 0.001
    assert movel.id() in c.caixas
    assert parede.id() not in c.caixas

    g_m = re.search(
        r'<g\b([^>]*\bifc:guid=[\"\']' + re.escape(movel.GlobalId) + r'[\"\'][^>]*)>(.*?)</g>',
        c.svg,
        re.DOTALL,
    )
    assert g_m is not None
    _, conteudo = g_m.group(1), g_m.group(2)
    m_d = re.search(r'\bd=[\"\']([^\"\']+)[\"\']', conteudo)
    assert m_d is not None
    coords = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", m_d.group(1))]
    assert len(coords) >= 8
    xs = coords[0::2]
    ys = coords[1::2]
    assert all(0.0 <= x <= 10.0 for x in xs), f"Coordenadas X devem estar em metros (0..10), obtido: {xs}"
    assert all(0.0 <= y <= 10.0 for y in ys), f"Coordenadas Y devem estar em metros (0..10), obtido: {ys}"
    assert min(xs) == pytest.approx(5.0, abs=0.01)
    assert max(xs) == pytest.approx(6.0, abs=0.01)
    assert min(ys) == pytest.approx(0.3, abs=0.01)
    assert max(ys) == pytest.approx(1.5, abs=0.01)


def test_corte_movel_projecao_classe_boundary(monkeypatch):
    """Móvel além do plano de corte (cruza=False) quando moveis_caixa2d=True:
    Gera path com class='boundary', consta em c.caixas e NÃO entra no iterador 3D."""
    import ifcopenshell.geom
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    parede = X.caixa(f, "IfcWall", "Parede", 0.5, -0.1, 0.0, 4.0, 0.2, 2.8)
    movel = X.caixa(f, "IfcFurniture", "MovelProj", 1.0, 1.0, 0.0, 1.0, 0.6, 1.2)
    X.conter(f, pav, parede, movel)

    includes_capturados: list[list[int]] = []
    real_iterator = ifcopenshell.geom.iterator

    def espia_iterator(*args, **kwargs):
        settings = args[0] if args else kwargs.get("settings")
        try:
            if not settings.get("elevation-ref-guid"):
                return real_iterator(*args, **kwargs)
        except Exception:
            return real_iterator(*args, **kwargs)
        inc = kwargs.get("include") or (args[3] if len(args) > 3 else None)
        includes_capturados.append([e.id() for e in inc] if inc else [])
        return real_iterator(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "iterator", espia_iterator)

    gid = _criar_corte_xyz(f, "Corte_Movel_Proj", xmin=-0.5, xmax=6.5, ymin=0.0, ymax=5.0, zmin=-0.5, zmax=3.5)
    c = corte.gerar_corte(f, gid, moveis_caixa2d=True, executor=local.executar)

    assert movel.id() in c.caixas, f"Móvel em projeção deve constar em c.caixas, obtido: {c.caixas}"
    assert parede.id() not in c.caixas

    assert len(includes_capturados) == 1
    assert movel.id() not in includes_capturados[0], "Móvel em projeção NÃO deve ir ao iterador 3D"
    assert parede.id() in includes_capturados[0]

    g_m = re.search(
        r'<g\b([^>]*\bifc:guid=[\"\']' + re.escape(movel.GlobalId) + r'[\"\'][^>]*)>(.*?)</g>',
        c.svg,
        re.DOTALL,
    )
    assert g_m is not None, f"Grupo para guid={movel.GlobalId!r} não encontrado no SVG gerado"
    _, conteudo = g_m.group(1), g_m.group(2)
    path_m = re.search(r'<path\b[^>]*\bclass=[\"\']([^\"\']+)[\"\'][^>]*>', conteudo)
    assert path_m is not None, f"Path com classe não encontrado no grupo: {conteudo}"
    assert "boundary" in path_m.group(1).split(), f"Classe do path deve conter 'boundary', obtido: {path_m.group(1)}"
    assert "cut" not in path_m.group(1).split(), f"Classe do path não deve conter 'cut', obtido: {path_m.group(1)}"


def test_corte_moveis_caixa2d_sem_outros_elementos_3d():
    """Corte contendo exclusivamente móvel (zero formas 3D no iterador OpenCASCADE).
    Verifica que o fallback de translação via viewBox posiciona a caixa corretamente dentro da vista."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    movel = X.caixa(f, "IfcFurniture", "MovelSozinho", 1.0, 1.0, 0.0, 1.0, 0.6, 1.2)
    X.conter(f, pav, movel)

    gid = _criar_corte_xyz(f, "Corte_Sozinho", xmin=0.0, xmax=5.0, ymin=0.0, ymax=5.0, zmin=0.0, zmax=3.0)
    c = corte.gerar_corte(f, gid, moveis_caixa2d=True, executor=local.executar)

    assert movel.id() in c.caixas
    assert c.n_paths == 1
    assert "ifc:matrix3=" not in c.svg

    g_m = re.search(
        r'<g\b([^>]*\bifc:guid=[\"\']' + re.escape(movel.GlobalId) + r'[\"\'][^>]*)>(.*?)</g>',
        c.svg,
        re.DOTALL,
    )
    assert g_m is not None
    _, conteudo = g_m.group(1), g_m.group(2)
    m_d = re.search(r'\bd=[\"\']([^\"\']+)[\"\']', conteudo)
    assert m_d is not None
    coords = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", m_d.group(1))]
    assert len(coords) >= 8
    xs = coords[0::2]
    ys = coords[1::2]
    assert all(0.0 <= x <= 5.0 for x in xs), f"Coordenadas X devem estar dentro do viewBox (0..5), obtido: {xs}"
    assert all(0.0 <= y <= 3.0 for y in ys), f"Coordenadas Y devem estar dentro do viewBox (0..3), obtido: {ys}"
    assert min(xs) == pytest.approx(3.5, abs=0.01)
    assert max(xs) == pytest.approx(4.5, abs=0.01)
    assert min(ys) == pytest.approx(0.3, abs=0.01)
    assert max(ys) == pytest.approx(1.5, abs=0.01)

