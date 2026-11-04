# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08f, parte 2 (largura de linha constante em mm NO PAPEL). Origem: achado 3 da demonstracao: o motor emite `stroke-width` em unidades da planta
(0,35 = 35 cm), e dentro do `g#viewport` (scale 1000/escala) a linha virava 7 mm a 1:50. O `QSvgRenderer` do Qt nao conhece `vector-effect`, entao a
implementacao reescreve a largura no proprio desenho. Contrato (`openbim_app/prancha.py`):
- Constantes publicas `LINHA_CORTE_MM = 0.35` e `LINHA_PROJECAO_MM = 0.18` (largura no papel, em mm).
- `montar_svg` (portanto `exportar_svg` e `exportar_pdf`) faz toda forma da planta (`path`, `line`, `polyline`, `polygon`, `circle`, `ellipse`, `rect`) ser desenhada com
  largura de traco = LINHA_CORTE_MM (corte) ou LINHA_PROJECAO_MM (projecao) NO PAPEL, em qualquer escala (a largura na unidade da planta e mm*escala/1000).
  Vale qualquer origem do `stroke-width` da planta: atributo, `style=""` do elemento, regra de `<style>` (classe, descendente) ou nenhum (padrao do SVG = 1 unidade). Ela
  descarta a largura de origem. Nao muda cor, opacidade, preenchimento, nem acrescenta traco onde nao havia `stroke`.
- Corte ou projecao (as duas classes no mesmo elemento: projecao vence), olhando o elemento e seus ancestrais, do mais proximo ao mais distante, pelo primeiro que decide: classe `projection` = projecao; classe `cut` = corte;
  classe `Ifc...` (menos `IfcBuildingStorey`, `IfcBuilding`, `IfcSite`, `IfcProject`, que nunca decidem) sem `projection` = corte (e assim que o motor marca o corte: `<g class="IfcWall...">`, e
  nunca emite `cut`); ninguem decide = projecao.
- A moldura (0,5 mm) e o carimbo nao mudam. A geometria (`d`, `points`, `x`...) e o `transform` do `g#viewport` (rotacao 0: translate + scale) nao mudam.
Medida: a prancha e desenhada com Qt (antialiasing) a 4 px/mm; espessura = soma da escuridao da coluna na faixa do traco (precisao de fracao de pixel). Tolerancia: 0,5 px
(0,125 mm); a conta do cartao pedia 1 px, esta e mais apertada e distingue 0,35 de 0,18 (0,68 px de diferenca)."""
import xml.etree.ElementTree as ET

import pytest
import s06_t08_aux as A
import s06_t08f_aux as F
from s06_t08_aux import GUID, IDENT

TOL_MM = 0.5 / F.PX

STYLE = ('<style type="text/css"><![CDATA[ .cut path { stroke: #000000; stroke-width: 0.9px; fill: none; } '
         'path.outline { stroke: #000000; stroke-width: 0.35px; fill: none; } ]]></style>')
# (y em m, elemento, e_corte). Cada traco horizontal vai de x=1 a x=9 m; um por metro de altura.
LINHAS = [
    (1, '<g class="cut"><path d="M1 1 L9 1"/></g>', True),                                                       # regra de <style> por descendente
    (2, '<g class="projection IfcWall"><path class="outline" d="M1 2 L9 2"/></g>', False),                        # regra de <style> por classe
    (3, '<path d="M1 3 L9 3" fill="none" stroke="#000000" stroke-width="0.5"/>', False),                          # atributo
    (4, '<g class="IfcWallStandardCase"><path d="M1 4 L9 4" fill="none" style="stroke:#000000;stroke-width:0.7px"/></g>', True),  # style="" e classe Ifc do motor
    (5, '<path class="cut" d="M1 5 L9 5" fill="none" stroke="#000000" stroke-width="2"/>', True),                 # classe no proprio elemento
    (6, '<line x1="1" y1="6" x2="9" y2="6" style="stroke:#000000"/>', False),                                          # style sem largura: padrao do SVG
    (11, '<line x1="1" y1="11" x2="9" y2="11" stroke="#000000"/>', False),                                           # sem style nem largura
    (7, '<polyline points="1,7 9,7" fill="none" stroke="#000000" style="stroke-width:3"/>', False),
    (8, '<g class="cut"><g class="projection"><path d="M1 8 L9 8" fill="none" stroke="#000000" stroke-width="1.2"/></g></g>', False),  # o mais proximo decide
    (9, '<path class="cut projection" d="M1 9 L9 9" fill="none" stroke="#000000"/>', False),                     # as duas no mesmo elemento: projection vence
    (10, '<g class="IfcProject"><g class="IfcSite"><g class="IfcBuilding"><g class="IfcBuildingStorey"><path d="M1 10 L9 10" fill="none" stroke="#000000"/>'
         '</g></g></g></g>', False),                                                                               # grupos espaciais do IFC nao decidem corte
]
PLANTA = f'<svg {F.SVG} viewBox="0 0 10 12">{STYLE}' + "".join(l[1] for l in LINHAS) + "</svg>"


def tracos(escala, x=20, y=20, planta=PLANTA, formato="A3"):
    m = F.P("LINHA_CORTE_MM", "LINHA_PROJECAO_MM")
    lado, _ = F.montar_com(formato=formato, escala=escala, x=x, y=y)
    svg = m.montar_svg(lado.lat, IDENT, GUID, planta)
    W, H = A.folha_mm(svg)
    return svg, F.desenhar(svg, W, H)


def medir_linha(img, yp, escala, x=20, y=20):
    s = 1000.0 / escala
    return F.espessura_mm(img, y + yp * s, x + 2 * s, x + 8 * s, meia_banda_mm=min(2.0, s / 2 - 0.2))


def test_01_constantes():
    m = F.P("LINHA_CORTE_MM", "LINHA_PROJECAO_MM")
    assert m.LINHA_CORTE_MM == 0.35 and m.LINHA_PROJECAO_MM == 0.18


@pytest.mark.parametrize("escala", [50, 62.5, 100, 200])
@pytest.mark.parametrize("yp,corpo,corte", LINHAS, ids=[f"y{l[0]}" for l in LINHAS])
def test_02_espessura_no_papel_independe_da_escala(escala, yp, corpo, corte):
    A.exigir_qt()
    m = F.P("LINHA_CORTE_MM", "LINHA_PROJECAO_MM")
    _, img = tracos(escala)
    esperado = m.LINHA_CORTE_MM if corte else m.LINHA_PROJECAO_MM
    medido = medir_linha(img, yp, escala)
    assert abs(medido - esperado) <= TOL_MM, f"1:{escala} y={yp}: medido {medido:.3f} mm, esperado {esperado} mm"


def test_03_corte_mais_grosso_que_projecao_e_ordem_certa():
    A.exigir_qt()
    _, img = tracos(100)
    corte, proj = medir_linha(img, 1, 100), medir_linha(img, 3, 100)
    assert corte - proj >= 0.1, (corte, proj)


def test_04_o_resto_do_desenho_nao_muda():
    F.P("LINHA_CORTE_MM")
    m = F.P("LINHA_CORTE_MM")
    lado, _ = F.montar_com(escala=100, x=20, y=20)
    raiz = ET.fromstring(m.montar_svg(lado.lat, IDENT, GUID, PLANTA))
    vp = next(e for e in raiz if e.get("id") == "viewport")
    assert vp.get("transform").replace(" ", "") == "translate(20,20)scale(10)", vp.get("transform")  # origem do viewBox em (0,0)
    d = [e.get("d") for e in vp.iter(A.NS + "path")]
    assert d == ["M1 1 L9 1", "M1 2 L9 2", "M1 3 L9 3", "M1 4 L9 4", "M1 5 L9 5", "M1 8 L9 8", "M1 9 L9 9", "M1 10 L9 10"]
    assert [e.get("points") for e in vp.iter(A.NS + "polyline")] == ["1,7 9,7"]
    assert [e.get("stroke") for e in vp.iter(A.NS + "path")] == [None, None, "#000000", None, "#000000", "#000000", "#000000", "#000000"]  # cor de atributo preservada
    for r in raiz.iter(A.NS + "rect"):
        if r.get("id") in ("moldura", "carimbo-caixa"):
            assert r.get("stroke-width") == "0.5" and r.get("stroke") == "#000000"


def test_05_preenchimento_sem_traco_continua_sem_traco():
    A.exigir_qt()
    m = F.P("LINHA_CORTE_MM")
    planta = A.planta(vb=(0, 0, 10, 6), alvo=(1, 1, 8, 4), extra="<circle cx='5' cy='3' r='1' fill='#ff0000'/>")
    lado, _ = F.montar_com(escala=100, x=20, y=20)
    svg = m.montar_svg(lado.lat, IDENT, GUID, planta)
    W, H = A.folha_mm(svg)
    px = F.PX
    assert not F.escuros(F.desenhar(svg, W, H))[int(25 * px):int(75 * px), int(25 * px):int(115 * px)].any(), "apareceu traco escuro onde so havia preenchimento"
    x, y, w, h = A.caixa_vermelha(A.imagem(svg.encode(), W, H))
    assert (x, y, w, h) == pytest.approx((30, 30, 80, 40), abs=0.3)


def test_06_planta_do_motor_sem_viewbox_de_ponta_a_ponta():
    A.exigir_qt()
    m = F.P("LINHA_CORTE_MM", "LINHA_PROJECAO_MM", "normalizar_planta")
    lado, _ = F.montar_com(escala=50, x=20, y=20)
    corpo = ('<g class="IfcWallStandardCase"><path d="M0 0 L8 0" fill="none" stroke="#000000"/></g>'
             '<g class="projection IfcWallStandardCase"><path class="outline" d="M0 2 L8 2" fill="none"/></g>')
    css = '<style><![CDATA[ path.outline { stroke: #000000; stroke-width: 0.35px; } ]]></style>'
    planta = f'<svg {F.SVG} xmlns:ifc="http://www.ifcopenshell.org/ns">{css}{corpo}</svg>'  # sem viewBox: box (0,0)-(8,2), margem 0,5
    svg = m.montar_svg(lado.lat, IDENT, GUID, planta)
    img = F.desenhar(svg, *A.folha_mm(svg))
    s = 20.0
    corte = F.espessura_mm(img, 20 + 0.5 * s, 20 + 3 * s, 20 + 6 * s, meia_banda_mm=2.0)
    proj = F.espessura_mm(img, 20 + 2.5 * s, 20 + 3 * s, 20 + 6 * s, meia_banda_mm=2.0)
    assert abs(corte - m.LINHA_CORTE_MM) <= TOL_MM and abs(proj - m.LINHA_PROJECAO_MM) <= TOL_MM, (corte, proj)


def test_07_mesma_espessura_no_pdf(tmp_path):
    import shutil
    import subprocess
    exe = shutil.which("pdftoppm")
    if exe is None:
        from obrigatorio import pular
        pular("S06-T08f: sem pdftoppm; espessura no PDF NAO FOI CONFERIDA", "OBIM_S06_OBRIGATORIO")
    A.exigir_qt()
    m = F.P("LINHA_CORTE_MM", "LINHA_PROJECAO_MM")
    lado, _ = F.montar_com(escala=50, x=20, y=20)
    m.exportar_pdf(lado.lat, IDENT, GUID, PLANTA, tmp_path / "p.pdf")
    subprocess.run([exe, "-r", "300", "-png", "-singlefile", str(tmp_path / "p.pdf"), str(tmp_path / "p")], check=True, capture_output=True)
    from PySide6.QtGui import QImage
    img = QImage(str(tmp_path / "p.png")).convertToFormat(QImage.Format_RGB32)
    px = 300 / 25.4
    s = 20.0
    corte = F.espessura_mm(img, 20 + 1 * s, 20 + 2 * s, 20 + 8 * s, meia_banda_mm=2.0, px=px)
    proj = F.espessura_mm(img, 20 + 3 * s, 20 + 2 * s, 20 + 8 * s, meia_banda_mm=2.0, px=px)
    assert abs(corte - 0.35) <= 0.12 and abs(proj - 0.18) <= 0.12, (corte, proj)
