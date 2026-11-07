# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15b: móveis e equipamentos pesados como caixa 2D na planta.
Cartão: cards/F0-S06/F0-S06-T15b-moveis-caixa2d.md.

CONTRATO:
1. Em `app/openbim_app/desenho/planta.py`:
   - `gerar_planta` declara o parâmetro keyword-only `moveis_como_caixa: bool = True`.
   - No pedido enviado ao executor auxiliar: `pedido["moveis_como_caixa"] = bool(moveis_como_caixa)`.
   - `Planta.caixas` (já presente na dataclass) conterá a tupla de inteiros dos IDs simplificados.
2. Em `geometria/obim_geometria/desenho.py`:
   - Quando `moveis_como_caixa` for `True`:
     Elementos das classes de mobiliário (`IfcFurnishingElement`, `IfcSystemFurnitureElement`)
     presentes na seleção não vão para o iterador de corte 3D pesado (`ifcopenshell.geom.serializers.svg`).
     Em vez disso, sua caixa envolvente 2D no plano da planta (x de xmin a xmax; y no SVG de -ymax a -ymin)
     é emitida como um retângulo fechado dentro de `<g class="<ClasseIFC>" ifc:guid="<GUID>"><path d="..." /></g>`.
     Seus IDs constam em `res["caixas"]` e em `res["enviados"]`.
   - Quando `moveis_como_caixa` for `False`:
     Os elementos seguem o fluxo 3D normal e `res["caixas"]` é `[]`.
"""
from __future__ import annotations

import inspect
import re
import sys
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
from openbim_app.desenho import auxiliar, estilo, planta, selecao

_NUM_PAR = re.compile(r"(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)[,\s]+(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")


def _modelo_sintetico_t15b(schema: str = "IFC4", com_sistema: bool = True):
    """Cria modelo sintético com pavimento em cota 0 e corte a 1.2 m:
    - Parede: IfcWall de (0,0,0) dim (2.0, 0.2, 2.0)
    - Laje: IfcSlab de (0,0,0) dim (2.0, 2.0, 0.2)
    - Móvel: IfcFurnishingElement de (1.0, 2.0, 0.0) dim (0.8, 0.6, 1.5)
    - Sistema: IfcSystemFurnitureElement de (3.0, 2.0, 0.0) dim (1.2, 0.8, 1.5) (se IFC4 e com_sistema)
    """
    exigir()
    f, pavs = X.estrutura(schema)
    pav = pavs[0]

    parede = X.caixa(f, "IfcWall", "parede", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    laje = X.caixa(f, "IfcSlab", "laje", 0.0, 0.0, 0.0, 2.0, 2.0, 0.2)
    movel = X.caixa(f, "IfcFurnishingElement", "movel", 1.0, 2.0, 0.0, 0.8, 0.6, 1.5)
    elementos = {"IfcWall": parede, "IfcSlab": laje, "IfcFurnishingElement": movel}

    if schema != "IFC2X3" and com_sistema:
        sistema = X.caixa(f, "IfcSystemFurnitureElement", "sistema", 3.0, 2.0, 0.0, 1.2, 0.8, 1.5)
        elementos["IfcSystemFurnitureElement"] = sistema
        X.conter(f, pav, parede, laje, movel, sistema)
    else:
        X.conter(f, pav, parede, laje, movel)

    gid = X.vista(f, "PLANTA", pav, nome=f"V_T15b_{schema}")
    return f, gid, pav, elementos


def _verificar_caixa_2d_no_svg(
    svg: str,
    guid: str,
    classe: str,
    xmin: float,
    xmax: float,
    ymin_svg: float,
    ymax_svg: float,
    tol: float = 0.02,
) -> None:
    """Verifica que o elemento possui grupo com a classe e guid corretos,
    e que seu caminho geométrico forma um retângulo 2D fechado correspondente aos
    limites projetados da caixa com todos os 4 cantos presentes.
    """
    tag_m = re.search(r"<g\b([^>]*\bifc:guid=[\"\']" + re.escape(guid) + r"[\"\'][^>]*)>(.*?)</g>", svg, re.DOTALL)
    assert tag_m is not None, f"Grupo para guid={guid!r} não encontrado no SVG gerado"
    abertura, conteudo = tag_m.group(1), tag_m.group(2)

    cls_m = re.search(r'\bclass=[\"\']([^\"]+)[\"\']', abertura)
    assert cls_m is not None, f"Atributo class ausente no grupo guid={guid!r}"
    classes_grupo = cls_m.group(1).split()
    assert classe in classes_grupo, f"Classe {classe!r} não encontrada nas classes do grupo: {classes_grupo}"

    paths = re.findall(r"<path\b[^>]*>", conteudo)
    assert len(paths) >= 1, f"Grupo guid={guid!r} deve conter ao menos um elemento <path>"

    d_m = re.search(r'\bd=[\"\']([^\"]+)[\"\']', paths[0])
    assert d_m is not None, f"Atributo d ausente no caminho de guid={guid!r}"
    d = d_m.group(1).strip()
    pts = [(float(x), float(y)) for x, y in _NUM_PAR.findall(d)]
    assert len(pts) >= 4, f"Caminho deve ter pelo menos 4 vértices para representar retângulo 2D, obtido: {len(pts)}"

    fechado = (abs(pts[0][0] - pts[-1][0]) <= tol and abs(pts[0][1] - pts[-1][1]) <= tol) or ("Z" in d.upper())
    assert fechado, f"Caminho do móvel deve ser fechado (primeiro igual ao último ou com Z): {d!r}"

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert abs(min(xs) - xmin) <= tol, f"xmin incorreto: esperado {xmin}, obtido {min(xs)}"
    assert abs(max(xs) - xmax) <= tol, f"xmax incorreto: esperado {xmax}, obtido {max(xs)}"
    assert abs(min(ys) - ymin_svg) <= tol, f"ymin_svg incorreto: esperado {ymin_svg}, obtido {min(ys)}"
    assert abs(max(ys) - ymax_svg) <= tol, f"ymax_svg incorreto: esperado {ymax_svg}, obtido {max(ys)}"

    # Garante que todos os 4 cantos do retângulo 2D estão presentes (impede diagonais, triângulos e degenerações)
    cantos_esperados = [(xmin, ymin_svg), (xmax, ymin_svg), (xmax, ymax_svg), (xmin, ymax_svg)]
    cantos_encontrados = [
        c for c in cantos_esperados
        if any(abs(x - c[0]) <= tol and abs(y - c[1]) <= tol for x, y in pts)
    ]
    assert len(cantos_encontrados) == 4, (
        f"A geometria deve conter todos os 4 cantos do retângulo. "
        f"Esperados {cantos_esperados}, encontrados {cantos_encontrados} em {pts}"
    )

    for x, y in pts:
        assert (xmin - tol) <= x <= (xmax + tol), f"Vértice ({x}, {y}) fora dos limites X=[{xmin}, {xmax}]"
        assert (ymin_svg - tol) <= y <= (ymax_svg + tol), f"Vértice ({x}, {y}) fora dos limites Y=[{ymin_svg}, {ymax_svg}]"


def test_assinatura_gerar_planta_moveis_como_caixa():
    """Caso 1: Inspeciona gerar_planta: parâmetro moveis_como_caixa keyword-only com default True e tipo bool."""
    sig = inspect.signature(planta.gerar_planta)
    assert "moveis_como_caixa" in sig.parameters, "gerar_planta deve declarar o parâmetro moveis_como_caixa"
    param = sig.parameters["moveis_como_caixa"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, f"moveis_como_caixa deve ser keyword-only (*), obtido: {param.kind}"
    assert param.default is True, f"moveis_como_caixa deve ter default True, obtido: {param.default!r}"
    assert param.annotation in (bool, "bool"), f"Anotação de moveis_como_caixa deve ser bool, obtido: {param.annotation!r}"
    assert list(sig.parameters)[:2] == ["ifc", "gid_vista"], "Primeiros 2 parâmetros devem ser ifc e gid_vista"


def test_moveis_simplificados_em_caixa_2d_por_padrao():
    """Caso 2: Modelo com parede, laje e móvel; por padrão moveis_como_caixa=True simplifica o móvel em caixa 2D."""
    f, gid, _pav, elementos = _modelo_sintetico_t15b(schema="IFC4", com_sistema=False)
    parede = elementos["IfcWall"]
    laje = elementos["IfcSlab"]
    movel = elementos["IfcFurnishingElement"]

    p = planta.gerar_planta(f, gid, moveis_como_caixa=True, executor=local.executar)

    assert isinstance(p.caixas, tuple), f"p.caixas deve ser tupla, obtido: {type(p.caixas)}"
    assert all(isinstance(x, int) for x in p.caixas), f"Elementos de p.caixas devem ser inteiros: {p.caixas}"
    assert movel.id() in p.selecao.ids, "Móvel deve constar na seleção"
    assert parede.id() in p.selecao.ids, "Parede deve constar na seleção"
    assert movel.id() in p.caixas, f"Móvel deve constar em p.caixas, obtido: {p.caixas}"
    assert parede.id() not in p.caixas, "Parede estrutural não deve estar em p.caixas"
    assert laje.id() not in p.caixas, "Laje não deve estar em p.caixas"

    # Movel de (1.0, 2.0, 0.0) dim (0.8, 0.6, 1.5):
    # x: [1.0, 1.8], y_mundo: [2.0, 2.6] => y_svg: [-2.6, -2.0]
    _verificar_caixa_2d_no_svg(p.svg, movel.GlobalId, "IfcFurnishingElement", xmin=1.0, xmax=1.8, ymin_svg=-2.6, ymax_svg=-2.0)

    g_parede = B.grupo(p.svg, parede.GlobalId)
    assert g_parede is not None, "Parede deve continuar no SVG"
    assert len(B.subcaminhos(g_parede)) > 0, "Parede deve ter caminhos desenhados"

    p_padrao = planta.gerar_planta(f, gid, executor=local.executar)
    assert p_padrao.caixas == p.caixas
    _verificar_caixa_2d_no_svg(p_padrao.svg, movel.GlobalId, "IfcFurnishingElement", xmin=1.0, xmax=1.8, ymin_svg=-2.6, ymax_svg=-2.0)


def test_desativar_moveis_como_caixa():
    """Caso 3: Com moveis_como_caixa=False: p.caixas == () e móvel desenhado normalmente pelo motor 3D."""
    f, gid, _pav, elementos = _modelo_sintetico_t15b(schema="IFC4", com_sistema=False)
    parede = elementos["IfcWall"]
    movel = elementos["IfcFurnishingElement"]

    p = planta.gerar_planta(f, gid, moveis_como_caixa=False, executor=local.executar)

    assert isinstance(p.caixas, tuple), f"p.caixas deve ser tupla, obtido: {type(p.caixas)}"
    assert p.caixas == (), f"p.caixas deve ser vazio (), obtido: {p.caixas}"
    assert movel.id() in p.selecao.ids
    assert parede.id() in p.selecao.ids

    g_movel = B.grupo(p.svg, movel.GlobalId)
    assert g_movel is not None, "Móvel deve estar presente no SVG mesmo desativando simplificação"
    assert len(B.subcaminhos(g_movel)) > 0, "Móvel deve conter caminhos do motor 3D"
    g_parede = B.grupo(p.svg, parede.GlobalId)
    assert g_parede is not None, "Parede deve estar presente no SVG"


def test_estilo_aplicavel_em_moveis_caixa2d():
    """Caso 4: Aplica estilo.aplicar_estilo(p.svg, '1:50') e confere SVG válido e estilizado sem exceção."""
    f, gid, _pav, elementos = _modelo_sintetico_t15b(schema="IFC4", com_sistema=False)
    movel = elementos["IfcFurnishingElement"]

    p = planta.gerar_planta(f, gid, moveis_como_caixa=True, executor=local.executar)

    svg_50 = estilo.aplicar_estilo(p.svg, "1:50")
    assert isinstance(svg_50, str) and "<svg" in svg_50 and "</svg>" in svg_50
    assert B.svg_valido(svg_50), "SVG estilizado em 1:50 deve ser XML válido"
    assert 'viewBox="' in svg_50
    assert 'width="' in svg_50 and 'height="' in svg_50
    assert "<style" in svg_50
    assert movel.GlobalId in svg_50

    svg_100 = estilo.aplicar_estilo(p.svg, "1:100")
    assert isinstance(svg_100, str) and B.svg_valido(svg_100)
    assert movel.GlobalId in svg_100


def test_cobertura_classes_mobiliario():
    """Caso 5: Tanto IfcFurnishingElement quanto IfcSystemFurnitureElement são tratados como caixa quando moveis_como_caixa=True."""
    f, gid, _pav, elementos = _modelo_sintetico_t15b(schema="IFC4", com_sistema=True)
    parede = elementos["IfcWall"]
    furn = elementos["IfcFurnishingElement"]
    sys_furn = elementos["IfcSystemFurnitureElement"]

    p = planta.gerar_planta(f, gid, moveis_como_caixa=True, executor=local.executar)

    assert furn.id() in p.caixas, "IfcFurnishingElement deve estar em p.caixas"
    assert sys_furn.id() in p.caixas, "IfcSystemFurnitureElement deve estar em p.caixas"
    assert parede.id() not in p.caixas, "IfcWall não deve estar em p.caixas"
    assert set(p.caixas) == {furn.id(), sys_furn.id()}

    _verificar_caixa_2d_no_svg(p.svg, furn.GlobalId, "IfcFurnishingElement", xmin=1.0, xmax=1.8, ymin_svg=-2.6, ymax_svg=-2.0)
    _verificar_caixa_2d_no_svg(p.svg, sys_furn.GlobalId, "IfcSystemFurnitureElement", xmin=3.0, xmax=4.2, ymin_svg=-2.8, ymax_svg=-2.0)


def test_sem_moveis_caixas_vazio():
    """Modelo com apenas parede (sem móveis): p.caixas deve ser tupla vazia () mesmo com moveis_como_caixa=True."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]
    parede = X.caixa(f, "IfcWall", "parede", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    X.conter(f, pav, parede)
    gid = X.vista(f, "PLANTA", pav, nome="V_SemMoveis")

    p = planta.gerar_planta(f, gid, moveis_como_caixa=True, executor=local.executar)
    assert isinstance(p.caixas, tuple)
    assert p.caixas == ()
    assert parede.id() in p.selecao.ids


def test_pedido_passa_moveis_como_caixa_booleano():
    """Confere que gerar_planta repassa moveis_como_caixa estritamente como booleano no dicionário pedido."""
    f, gid, _pav, _elementos = _modelo_sintetico_t15b(schema="IFC4", com_sistema=False)
    pedidos_recebidos = []

    def espia(pedido):
        pedidos_recebidos.append(dict(pedido))
        return local.executar(pedido)

    planta.gerar_planta(f, gid, executor=espia)
    assert len(pedidos_recebidos) == 1
    assert "moveis_como_caixa" in pedidos_recebidos[0]
    assert pedidos_recebidos[0]["moveis_como_caixa"] is True
    assert type(pedidos_recebidos[0]["moveis_como_caixa"]) is bool

    planta.gerar_planta(f, gid, moveis_como_caixa=False, executor=espia)
    assert len(pedidos_recebidos) == 2
    assert pedidos_recebidos[1]["moveis_como_caixa"] is False
    assert type(pedidos_recebidos[1]["moveis_como_caixa"]) is bool

    planta.gerar_planta(f, gid, moveis_como_caixa=1, executor=espia)
    assert len(pedidos_recebidos) == 3
    assert pedidos_recebidos[2]["moveis_como_caixa"] is True
    assert type(pedidos_recebidos[2]["moveis_como_caixa"]) is bool

    planta.gerar_planta(f, gid, moveis_como_caixa=0, executor=espia)
    assert len(pedidos_recebidos) == 4
    assert pedidos_recebidos[3]["moveis_como_caixa"] is False
    assert type(pedidos_recebidos[3]["moveis_como_caixa"]) is bool


def test_desenho_processar_respeita_moveis_como_caixa(monkeypatch):
    """Confere o contrato direto de obim_geometria.desenho.processar:
    Quando moveis_como_caixa=True:
    - elementos de mobiliário NÃO vão para o ifcopenshell.geom.iterator 3D
    - constam em res["caixas"] e em res["enviados"]
    - são emitidos como caixa 2D no res["svg"]
    Quando False:
    - caixas é vazia, elementos vão para o motor 3D.
    """
    import ifcopenshell.geom
    f, gid, pav, elementos = _modelo_sintetico_t15b(schema="IFC4", com_sistema=False)
    parede = elementos["IfcWall"]
    movel = elementos["IfcFurnishingElement"]

    vista = {
        "tipo": "PLANTA",
        "altura_corte_m": 1.2,
        "origem_pav": [0.0, 0.0, 0.0],
        "escala": 1.0,
        "pavimento": pav.GlobalId,
    }
    elems = [[parede.id(), parede.GlobalId], [movel.id(), movel.GlobalId]]

    includes_capturados = []
    real_iterator = ifcopenshell.geom.iterator

    def espia_iterator(*args, **kwargs):
        inc = kwargs.get("include") or (args[3] if len(args) > 3 else None)
        includes_capturados.append([e.id() for e in inc] if inc else [])
        return real_iterator(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "iterator", espia_iterator)

    # 1. Com moveis_como_caixa=True
    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "moveis_como_caixa": True}) as p:
        res = local.executar(p.pedido)

    assert res["ok"] is True
    assert isinstance(res["caixas"], list), f"res['caixas'] deve ser lista, obtido: {type(res['caixas'])}"
    assert movel.id() in res["caixas"]
    assert parede.id() not in res["caixas"]
    assert movel.id() in res["enviados"]
    assert parede.id() in res["enviados"]
    assert res["falhas_geometria"] == []
    # Móvel não pode ter ido para o iterator 3D pesado
    assert len(includes_capturados) == 1
    assert movel.id() not in includes_capturados[0], "Móvel não deve ir para o ifcopenshell.geom.iterator quando moveis_como_caixa=True"
    assert parede.id() in includes_capturados[0], "Parede deve ir para o ifcopenshell.geom.iterator"
    # Caixa emitida no SVG retornado por processar
    _verificar_caixa_2d_no_svg(res["svg"], movel.GlobalId, "IfcFurnishingElement", xmin=1.0, xmax=1.8, ymin_svg=-2.6, ymax_svg=-2.0)

    # 2. Com moveis_como_caixa=False
    includes_capturados.clear()
    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "moveis_como_caixa": False}) as p:
        res_falso = local.executar(p.pedido)

    assert res_falso["ok"] is True
    assert res_falso["caixas"] == []
    assert movel.id() in res_falso["enviados"]
    assert len(includes_capturados) == 1
    assert movel.id() in includes_capturados[0], "Móvel deve ir para o iterator 3D normal quando moveis_como_caixa=False"


def test_modelo_georreferenciado_preserva_dimensoes_sem_notacao_cientifica():
    """Modelo com coordenadas georreferenciadas (offset X.GEO = 324550.0, 7405473.0):
    Verifica que o caminho SVG do móvel usa formato decimal com precisão (:.4f),
    não emite notação científica ('e' ou 'E') e preserva largura e profundidade reais
    com erro menor que 0.001 m.
    """
    exigir()
    ox, oy = X.GEO
    f, pavs = X.estrutura("IFC4", off=(ox, oy))
    pav = pavs[0]

    dx, dy, dz = 0.8, 0.6, 1.5
    parede = X.caixa(f, "IfcWall", "parede", ox, oy, 0.0, 2.0, 0.2, 2.0)
    movel = X.caixa(f, "IfcFurnishingElement", "movel_geo", ox + 1.0, oy + 2.0, 0.0, dx, dy, dz)
    X.conter(f, pav, parede, movel)
    gid = X.vista(f, "PLANTA", pav, nome="V_T15b_GEO")

    p = planta.gerar_planta(f, gid, moveis_como_caixa=True, executor=local.executar)
    assert movel.id() in p.caixas, f"Móvel georreferenciado deve estar em p.caixas: {p.caixas}"

    tag_m = re.search(r"<g\b([^>]*\bifc:guid=[\"']" + re.escape(movel.GlobalId) + r"[\"'][^>]*)>(.*?)</g>", p.svg, re.DOTALL)
    assert tag_m is not None, f"Grupo para guid={movel.GlobalId!r} não encontrado no SVG gerado"
    conteudo = tag_m.group(2)

    paths = re.findall(r"<path\b[^>]*>", conteudo)
    assert len(paths) >= 1, f"Grupo guid={movel.GlobalId!r} deve conter ao menos um elemento <path>"

    d_m = re.search(r'\bd=[\"\']([^\"]+)[\"\']', paths[0])
    assert d_m is not None, f"Atributo d ausente no caminho do móvel {movel.GlobalId!r}"
    d = d_m.group(1).strip()

    # 1. Sem notação científica ('e' ou 'E')
    assert "e" not in d.lower(), f"Caminho SVG não deve conter notação científica ('e'/'E'): {d}"

    # 2. Formato decimal com precisão estrita de 4 casas (:.4f) para todas as coordenadas
    coords = re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", d)
    assert len(coords) >= 8, f"Caminho deve conter coordenadas: {d}"
    assert all(re.match(r"^-?\d+\.\d{4}$", c) for c in coords), (
        f"Todas as coordenadas do caminho SVG devem estar formatadas com 4 casas decimais (:.4f), obtido: {coords}"
    )

    # 3. Dimensões reais preservadas com erro < 0.001 m
    pts = [(float(x), float(y)) for x, y in _NUM_PAR.findall(d)]
    assert len(pts) >= 4, f"Caminho deve ter pelo menos 4 vértices, obtido: {len(pts)}"
    xs = [pt[0] for pt in pts]
    ys = [pt[1] for pt in pts]
    largura = max(xs) - min(xs)
    profundidade = max(ys) - min(ys)
    assert abs(largura - dx) < 0.001, f"Largura real {largura} difere de {dx} em mais de 0.001 m"
    assert abs(profundidade - dy) < 0.001, f"Profundidade real {profundidade} difere de {dy} em mais de 0.001 m"

    # 4. Posições absolutas com erro < 0.001 m
    xmin_esp = ox + 1.0
    xmax_esp = ox + 1.0 + dx
    ymin_svg_esp = -(oy + 2.0 + dy)
    ymax_svg_esp = -(oy + 2.0)
    assert abs(min(xs) - xmin_esp) < 0.001, f"xmin {min(xs)} difere do esperado {xmin_esp}"
    assert abs(max(xs) - xmax_esp) < 0.001, f"xmax {max(xs)} difere do esperado {xmax_esp}"
    assert abs(min(ys) - ymin_svg_esp) < 0.001, f"ymin_svg {min(ys)} difere do esperado {ymin_svg_esp}"
    assert abs(max(ys) - ymax_svg_esp) < 0.001, f"ymax_svg {max(ys)} difere do esperado {ymax_svg_esp}"

    # 5. Validação geométrica completa da caixa com tol=0.001
    _verificar_caixa_2d_no_svg(
        p.svg,
        movel.GlobalId,
        "IfcFurnishingElement",
        xmin=xmin_esp,
        xmax=xmax_esp,
        ymin_svg=ymin_svg_esp,
        ymax_svg=ymax_svg_esp,
        tol=0.001,
    )


def test_movel_inteiro_acima_do_corte_nao_sai():
    """Móvel inteiro acima da altura de corte (ex: zmin > altura_corte_m, como armário aéreo)
    não deve sair na planta: não entra em p.caixas nem no SVG.
    Testa em cota 0 e em pavimento elevado (cota 3.0 m) para garantir que o corte usa cota
    absoluta do mundo (altura_corte_m) e não cota relativa local do pavimento.
    """
    exigir()
    f, pavs = X.estrutura("IFC4", base=0.0, n_pav=2)
    pav0, pav1 = pavs[0], pavs[1]

    # --- 1. Pavimento 0 (cota 0.0 m, plano de corte em 1.2 m) ---
    parede0 = X.caixa(f, "IfcWall", "parede0", 0.0, 0.0, 0.0, 2.0, 0.2, 3.0)
    # Móvel cortado pela altura de corte (z de 0.0 a 1.5, corte em 1.2 m): deve sair
    movel_baixo0 = X.caixa(f, "IfcFurnishingElement", "movel_baixo0", 1.0, 2.0, 0.0, 0.8, 0.6, 1.5)
    # Móvel com base em z=2.0 m (zmin=2.0 > corte 1.2 m, ex: armário aéreo): NÃO deve sair
    movel_alto0 = X.caixa(f, "IfcFurnishingElement", "armario_aereo0", 3.0, 2.0, 2.0, 0.8, 0.6, 0.8)

    X.conter(f, pav0, parede0, movel_baixo0, movel_alto0)
    gid0 = X.vista(f, "PLANTA", pav0, nome="V_Movel_Aereo_P0")

    p0 = planta.gerar_planta(f, gid0, moveis_como_caixa=True, executor=local.executar)

    assert movel_baixo0.id() in p0.selecao.ids
    assert movel_alto0.id() in p0.selecao.ids

    assert movel_baixo0.id() in p0.caixas, f"Móvel baixo deve estar em p0.caixas: {p0.caixas}"
    assert movel_baixo0.GlobalId in p0.svg, "Móvel baixo deve estar no SVG de p0"
    _verificar_caixa_2d_no_svg(
        p0.svg,
        movel_baixo0.GlobalId,
        "IfcFurnishingElement",
        xmin=1.0,
        xmax=1.8,
        ymin_svg=-2.6,
        ymax_svg=-2.0,
    )

    assert movel_alto0.id() not in p0.caixas, (
        f"Móvel inteiro acima do corte (zmin=2.0 > 1.2) não deve entrar em p0.caixas: {p0.caixas}"
    )
    assert movel_alto0.GlobalId not in p0.svg, (
        f"GUID do móvel acima do corte ({movel_alto0.GlobalId}) não deve sair no SVG de p0"
    )
    assert B.grupo(p0.svg, movel_alto0.GlobalId) is None, (
        "Grupo do móvel acima do corte não deve existir no SVG de p0"
    )

    # Com moveis_como_caixa=False o comportamento 3D nativo também não emite o móvel aéreo
    p0_sem_caixa = planta.gerar_planta(f, gid0, moveis_como_caixa=False, executor=local.executar)
    assert movel_alto0.id() not in p0_sem_caixa.caixas
    assert movel_alto0.GlobalId not in p0_sem_caixa.svg
    assert movel_baixo0.GlobalId in p0_sem_caixa.svg

    # Processamento direto: móvel acima do corte não deve ser reportado como falha de geometria
    elems0 = [[parede0.id(), parede0.GlobalId], [movel_baixo0.id(), movel_baixo0.GlobalId], [movel_alto0.id(), movel_alto0.GlobalId]]
    vista0 = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav0.GlobalId}
    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems0, "vista": vista0, "moveis_como_caixa": True}) as prep0:
        res0 = local.executar(prep0.pedido)
    assert res0["ok"] is True
    assert movel_baixo0.id() in res0["caixas"]
    assert movel_alto0.id() not in res0["caixas"]
    assert movel_alto0.id() not in res0["falhas_geometria"], (
        "Móvel acima do corte não deve constar em falhas_geometria"
    )

    # --- 2. Pavimento 1 (cota 3.0 m, corte no mundo em 4.2 m) ---
    parede1 = X.caixa(f, "IfcWall", "parede1", 0.0, 0.0, 3.0, 2.0, 0.2, 3.0)
    # Móvel no chão do Pav 1 (z de 3.0 a 4.5, corte em 4.2 m): deve sair
    movel_baixo1 = X.caixa(f, "IfcFurnishingElement", "movel_baixo1", 1.0, 2.0, 3.0, 0.8, 0.6, 1.5)
    # Móvel aéreo no Pav 1 (z de 5.0 a 5.8, corte em 4.2 m): NÃO deve sair
    movel_alto1 = X.caixa(f, "IfcFurnishingElement", "armario_aereo1", 3.0, 2.0, 5.0, 0.8, 0.6, 0.8)

    X.conter(f, pav1, parede1, movel_baixo1, movel_alto1)
    gid1 = X.vista(f, "PLANTA", pav1, nome="V_Movel_Aereo_P1")

    p1 = planta.gerar_planta(f, gid1, moveis_como_caixa=True, executor=local.executar)

    assert movel_baixo1.id() in p1.caixas, (
        f"Móvel do Pav 1 (z=3.0 <= corte 4.2) deve sair em p1.caixas; "
        f"se faltar, o motor comparou contra section_height local (1.2) em vez de altura_corte_m (4.2): {p1.caixas}"
    )
    assert movel_baixo1.GlobalId in p1.svg
    assert movel_alto1.id() not in p1.caixas
    assert movel_alto1.GlobalId not in p1.svg
    assert B.grupo(p1.svg, movel_alto1.GlobalId) is None

