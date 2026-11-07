# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15c: cache de projeção 2D por tipo de geometria repetida na planta.
Cartão: cards/F0-S06/F0-S06-T15c-cache-tipo.md.
"""
from __future__ import annotations

import inspect
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401 (fixture autouse e guarda)

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app.desenho import estilo, planta, selecao


def _pontos_de_path(d: str) -> list[tuple[float, float]]:
    """Extrai lista de coordenadas (x, y) de um atributo SVG path d."""
    nums = [float(x) for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2]))


def _extrair_grupo_e_pontos(svg: str, guid: str) -> tuple[str, list[tuple[float, float]]]:
    """Localiza o grupo para guid no SVG e extrai classe e vértices (x, y)."""
    try:
        root = ET.fromstring(svg)
        uri = "http://www.ifcopenshell.org/ns"
        el = root.find(f'.//*[@{{{uri}}}guid="{guid}"]')
        if el is None:
            for elem in root.iter():
                if elem.attrib.get(f"{{{uri}}}guid") == guid or elem.attrib.get("ifc:guid") == guid:
                    el = elem
                    break
        if el is not None:
            cls = el.attrib.get("class", "")
            pts = []
            for path in el.iter():
                if path.tag.endswith("path") and "d" in path.attrib:
                    pts.extend(_pontos_de_path(path.attrib["d"]))
            if pts:
                return cls, pts
    except Exception:
        pass
    padrao = r'<g\b([^>]*\bifc:guid=[\"\']' + re.escape(guid) + r'[\"\'][^>]*)>(.*?)</g>'
    tag_m = re.search(padrao, svg, re.DOTALL)
    assert tag_m is not None, f"Grupo para guid={guid!r} não encontrado no SVG"
    abertura, conteudo = tag_m.group(1), tag_m.group(2)
    cls_m = re.search(r'\bclass=[\"\']([^\"]+)[\"\']', abertura)
    cls = cls_m.group(1) if cls_m else ""
    paths = re.findall(r'<path\b[^>]*\bd=[\"\']([^\"\']+)[\"\']', conteudo)
    assert len(paths) >= 1, f"Grupo guid={guid!r} deve conter ao menos um elemento <path>"
    pts = []
    for d in paths:
        pts.extend(_pontos_de_path(d))
    assert len(pts) >= 4, f"Caminho do guid={guid!r} deve conter ao menos 4 pontos, obtido: {len(pts)}"
    return cls, pts


def _obter_em_cache(p) -> tuple[int, ...]:
    """Obtém a tupla de step IDs resolvidos via cache 2D de p.em_cache ou retorno correspondente."""
    em_cache = getattr(p, "em_cache", None)
    if em_cache is None and isinstance(p, dict):
        em_cache = p.get("em_cache")
    assert em_cache is not None, "Planta (ou retorno correspondente) deve expor em_cache"
    assert isinstance(em_cache, (tuple, list)), f"em_cache deve ser tupla ou lista, obtido: {type(em_cache)}"
    assert all(isinstance(x, int) for x in em_cache), f"IDs em em_cache devem ser inteiros: {em_cache}"
    return tuple(em_cache)


def _modelo_sintetico_t15c(schema: str = "IFC4", posicoes: list[tuple[float, float]] | None = None):
    """Modelo sintético com 1 parede e 5 pilares com mesma IfcShapeRepresentation."""
    exigir()
    if posicoes is None:
        posicoes = [(1.0, 1.0), (3.0, 1.0), (5.0, 1.0), (1.0, 3.0), (3.0, 3.0)]

    f, pavs = X.estrutura(schema)
    pav = pavs[0]
    parede = X.caixa(f, "IfcWall", "parede", 0.0, 0.0, 0.0, 5.0, 0.2, 3.0)
    pilar0 = X.caixa(f, "IfcColumn", "pilar_0", posicoes[0][0], posicoes[0][1], 0.0, 0.4, 0.4, 3.0)
    forma = pilar0.Representation.Representations[0]

    pilares = [pilar0]
    for i, (px, py) in enumerate(posicoes[1:], start=1):
        c = X.elemento(f, "IfcColumn", f"pilar_{i}")
        c.ObjectPlacement = f.create_entity(
            "IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, px, py, 0.0))
        )
        c.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
        pilares.append(c)

    X.conter(f, pav, parede, *pilares)
    gid = X.vista(f, "PLANTA", pav, nome=f"V_T15c_{schema}")
    return f, gid, pav, parede, pilares, posicoes


def test_assinatura_gerar_planta_cache_tipo():
    """Caso 1: Inspeciona gerar_planta: parâmetro cache_tipo keyword-only com default True e tipo bool."""
    sig = inspect.signature(planta.gerar_planta)
    assert "cache_tipo" in sig.parameters, "gerar_planta deve declarar o parâmetro cache_tipo"
    param = sig.parameters["cache_tipo"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, f"cache_tipo deve ser keyword-only (*), obtido: {param.kind}"
    assert param.default is True, f"cache_tipo deve ter default True, obtido: {param.default!r}"
    assert param.annotation in (bool, "bool"), f"Anotação de cache_tipo deve ser bool, obtido: {param.annotation!r}"
    assert list(sig.parameters)[:2] == ["ifc", "gid_vista"], "Primeiros 2 parâmetros devem ser ifc e gid_vista"
    assert "em_cache" in planta.Planta.__dataclass_fields__, "Dataclass Planta deve conter campo em_cache"


def test_pedido_passa_cache_tipo_booleano():
    """Confere que gerar_planta repassa cache_tipo estritamente como booleano no dicionário pedido."""
    f, gid, _pav, _parede, _pilares, _pos = _modelo_sintetico_t15c()
    pedidos = []

    def espia(pedido):
        pedidos.append(dict(pedido))
        return local.executar(pedido)

    for val, esperado in [(None, True), (False, False), (1, True), (0, False)]:
        kw = {} if val is None else {"cache_tipo": val}
        planta.gerar_planta(f, gid, executor=espia, **kw)
        assert pedidos[-1]["cache_tipo"] is esperado
        assert type(pedidos[-1]["cache_tipo"]) is bool
    assert len(pedidos) == 4


def test_instancias_repetidas_reaproveitam_geometria_em_cache():
    """Caso 2: 1 parede e 5 pilares idênticos; cache_tipo=True reaproveita projeção 2D das réplicas."""
    f, gid, _pav, parede, pilares, posicoes = _modelo_sintetico_t15c()

    p = planta.gerar_planta(f, gid, cache_tipo=True, executor=local.executar)

    assert isinstance(p.em_cache, tuple), f"p.em_cache deve ser tupla, obtido: {type(p.em_cache)}"
    assert all(isinstance(x, int) for x in p.em_cache), f"IDs em p.em_cache devem ser inteiros: {p.em_cache}"
    assert len(p.em_cache) == 4, f"Esperados 4 pilares em cache, obtido {len(p.em_cache)}: {p.em_cache}"
    ids_replicas = {c.id() for c in pilares[1:]}
    assert set(p.em_cache) == ids_replicas, f"IDs em cache divergem das réplicas: {p.em_cache} vs {ids_replicas}"
    assert pilares[0].id() not in p.em_cache, "A primeira instância deve ser calculada no motor 3D, não do cache"
    assert parede.id() not in p.em_cache, "A parede não é réplica de pilar"

    assert parede.id() in p.selecao.ids
    for c in pilares:
        assert c.id() in p.selecao.ids

    tol = 0.02
    for i, (col, (px, py)) in enumerate(zip(pilares, posicoes)):
        cls, pts = _extrair_grupo_e_pontos(p.svg, col.GlobalId)
        assert "IfcColumn" in cls.split(), f"pilar {i} deve ter classe IfcColumn, obtido: {cls!r}"

        xs, ys = [pt[0] for pt in pts], [pt[1] for pt in pts]
        xmin_esp, xmax_esp = px, px + 0.4
        ymin_esp, ymax_esp = -(py + 0.4), -py

        assert abs(min(xs) - xmin_esp) <= tol, f"pilar {i} xmin incorreto: {min(xs)} vs {xmin_esp}"
        assert abs(max(xs) - xmax_esp) <= tol, f"pilar {i} xmax incorreto: {max(xs)} vs {xmax_esp}"
        assert abs(min(ys) - ymin_esp) <= tol, f"pilar {i} ymin incorreto: {min(ys)} vs {ymin_esp}"
        assert abs(max(ys) - ymax_esp) <= tol, f"pilar {i} ymax incorreto: {max(ys)} vs {ymax_esp}"

    g_parede = B.grupo(p.svg, parede.GlobalId)
    assert g_parede is not None, "Parede deve estar presente no SVG"
    assert len(B.subcaminhos(g_parede)) > 0

    p_padrao = planta.gerar_planta(f, gid, executor=local.executar)
    assert p_padrao.em_cache == p.em_cache


def test_desativar_cache_tipo():
    """Caso 3: Com cache_tipo=False, nenhum elemento é resolvido via cache e todos são gerados diretamente."""
    f, gid, _pav, parede, pilares, _pos = _modelo_sintetico_t15c()

    p = planta.gerar_planta(f, gid, cache_tipo=False, executor=local.executar)

    assert isinstance(p.em_cache, tuple), f"p.em_cache deve ser tupla, obtido: {type(p.em_cache)}"
    assert p.em_cache == (), f"em_cache deve ser vazio quando cache_tipo=False, obtido: {p.em_cache}"

    assert parede.id() in p.selecao.ids
    g_parede = B.grupo(p.svg, parede.GlobalId)
    assert g_parede is not None

    for col in pilares:
        assert col.id() in p.selecao.ids
        cls, pts = _extrair_grupo_e_pontos(p.svg, col.GlobalId)
        assert len(pts) >= 4
        assert "IfcColumn" in cls.split()


def test_compatibilidade_estilo():
    """Caso 4: estilo.aplicar_estilo processa o SVG gerado com cache sem erro e preserva guids."""
    f, gid, _pav, parede, pilares, _pos = _modelo_sintetico_t15c()

    p = planta.gerar_planta(f, gid, cache_tipo=True, executor=local.executar)

    for escala in ("1:50", "1:100"):
        svg_estilizado = estilo.aplicar_estilo(p.svg, escala)
        assert isinstance(svg_estilizado, str)
        assert B.svg_valido(svg_estilizado), f"SVG estilizado em {escala} deve ser XML válido"
        assert "<style" in svg_estilizado
        assert 'viewBox="' in svg_estilizado
        assert 'width="' in svg_estilizado and 'height="' in svg_estilizado

        assert parede.GlobalId in svg_estilizado
        for col in pilares:
            assert col.GlobalId in svg_estilizado


def test_precisao_posicionamento_instancia_em_cache():
    """Caso 5: Compara coordenadas do pilar gerado via cache contra sem cache; tolerância < 0.001 m."""
    f, gid, _pav, _parede, pilares, _pos = _modelo_sintetico_t15c()

    p_cache = planta.gerar_planta(f, gid, cache_tipo=True, executor=local.executar)
    p_direto = planta.gerar_planta(f, gid, cache_tipo=False, executor=local.executar)

    for i, col in enumerate(pilares):
        _cls_c, pts_cache = _extrair_grupo_e_pontos(p_cache.svg, col.GlobalId)
        _cls_d, pts_direto = _extrair_grupo_e_pontos(p_direto.svg, col.GlobalId)

        xs_c, ys_c = [pt[0] for pt in pts_cache], [pt[1] for pt in pts_cache]
        xs_d, ys_d = [pt[0] for pt in pts_direto], [pt[1] for pt in pts_direto]

        assert abs(min(xs_c) - min(xs_d)) < 0.001, f"pilar {i} xmin diverge entre cache e direto"
        assert abs(max(xs_c) - max(xs_d)) < 0.001, f"pilar {i} xmax diverge entre cache e direto"
        assert abs(min(ys_c) - min(ys_d)) < 0.001, f"pilar {i} ymin diverge entre cache e direto"
        assert abs(max(ys_c) - max(ys_d)) < 0.001, f"pilar {i} ymax diverge entre cache e direto"

        for pt_c in pts_cache:
            d_min = min(math.hypot(pt_c[0] - pt_d[0], pt_c[1] - pt_d[1]) for pt_d in pts_direto)
            assert d_min < 0.001, f"Vértice cache {pt_c} do pilar {i} diverge por {d_min:.6f} m (> 0.001 m)"

        for pt_d in pts_direto:
            d_min = min(math.hypot(pt_d[0] - pt_c[0], pt_d[1] - pt_c[1]) for pt_c in pts_cache)
            assert d_min < 0.001, f"Vértice direto {pt_d} do pilar {i} ausente no cache por {d_min:.6f} m"

