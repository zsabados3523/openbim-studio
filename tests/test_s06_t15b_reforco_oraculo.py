# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo F0-S06-T15b: georreferenciamento sem notação científica e móvel aéreo acima do corte."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401
from test_s06_t15b_moveis_caixa2d_oraculo import _NUM_PAR, _verificar_caixa_2d_no_svg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "geometria"))

import obim_geometria.local as local
from openbim_app.desenho import auxiliar, planta


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
