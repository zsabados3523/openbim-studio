# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08f, parte 1 (viewBox da planta do motor). Origem: demonstracao com planta real (relatorio `F0-S06-T08-demo-planta-real.md`, achado 1):
o SVG do ifcopenshell vem SEM `viewBox`, em metros. Mantem TODO o contrato de `test_s06_t08_*` (nada afrouxado). Duas decisoes de contrato mudaram, de proposito:
`montar_svg` aceita planta sem `viewBox` (antes `SvgInvalido`) e `"A0"` deixou de ser formato invalido (ver parte 3).
Partes: este arquivo (viewBox), `test_s06_t08f_espessura_oraculo.py` (largura de linha em mm no papel), `test_s06_t08f_formatos_oraculo.py` (A2/A1/A0 e rotacao).
CONTRATO NOVO em `openbim_app/prancha.py` (ainda so stdlib no import):
- `normalizar_planta(svg_texto, margem_m=0.5) -> str` (`svg_texto`: str ou bytes UTF-8; devolve str). Mesmas recusas de XML do `montar_svg`: `SvgInvalido` para vazio, XML mal
  formado, raiz que nao e `<svg>` com namespace, `<!DOCTYPE`/`<!ENTITY`, tipo que nao e str/bytes. `margem_m` numero finito >= 0 e nao `bool` (`PranchaInvalida`).
  * Se a raiz ja tem `viewBox` (qualquer texto): devolve o texto recebido IGUAL, sem validar o valor.
  * Senao: calcula a caixa (em metros, 1 unidade = 1 m) dos elementos desenhaveis e devolve o MESMO texto com ` viewBox="minx miny w h"` inserido na tag raiz e nada mais mudado
    (CDATA, prefixos como `ifc:`, ordem e espacos intactos: tirando o atributo inserido sai o texto original). viewBox = caixa expandida de `margem_m` em cada lado.
  * Desenhaveis: `path`, `polyline`, `polygon`, `line`, `circle`, `rect` (`x`/`y` ausentes valem 0). `width`/`height` da raiz sao ignorados. Fora da conta tudo dentro de
    `defs`, `marker`, `clipPath`, `mask`, `pattern`, `symbol`, `style`, `title`, `desc`, `metadata`, `text`. Sem nenhum desenhavel = `SvgInvalido`. Largura ou altura final <= 0
    (por exemplo uma linha reta com margem 0) = `SvgInvalido`.
  * `path`: comandos M L H V C S Q T A Z, absolutos e relativos, numeros separados por espaco, virgula ou colados (`M1-2L3.5.5`), expoente, pares implicitos depois de M/L,
    `Z` volta ao inicio do subcaminho. Retas: caixa EXATA. Curvas (C, S, Q, T): a caixa do viewBox contem a curva e cabe na caixa dos pontos de controle. Arcos A: contem os
    extremos reais do arco e cabe na caixa da elipse inteira. Comando malformado = `SvgInvalido`.
  * `transform` (no elemento ou em qualquer ancestral): so `translate(tx[ ty])` e `scale(sx[ sy])`, em lista (aplica da direita para a esquerda, como no SVG). `rotate`,
    `matrix`, `skewX`, `skewY` = `SvgInvalido`.
- `montar_svg` / `exportar_svg` / `exportar_pdf` chamam `normalizar_planta` antes de usar a planta: planta sem `viewBox` passa a valer (o resto do contrato nao muda).
GUARDA: sem PySide6 ou numpy, os casos com desenho pulam (falham com OBIM_S06_OBRIGATORIO=1)."""
import xml.etree.ElementTree as ET

import pytest
import s06_t08_aux as A
import s06_t08f_aux as F
from s06_t08_aux import GUID, IDENT, NS
from s06_t08f_aux import MOTOR, MOTOR_VB, envolver



def N():
    return F.P("normalizar_planta").normalizar_planta


def aprox(obtido, esperado, tol=1e-6):
    assert len(obtido) == len(esperado) and all(abs(a - b) <= tol for a, b in zip(obtido, esperado)), f"{obtido} != {esperado}"


def caixa_de(corpo, **kw):
    """(xmin, ymin, xmax, ymax) que `normalizar_planta` achou para `corpo`, com margem 0."""
    x, y, w, h = F.caixa_vb(N()(envolver(corpo), margem_m=0, **kw))
    return x, y, x + w, y + h


# ---------- o recorte no formato do motor ----------
def test_01_planta_do_motor_ganha_viewbox_em_metros():
    aprox(F.caixa_vb(N()(MOTOR)), MOTOR_VB)  # marcador gigante do <defs> e texto do <style> nao entram na caixa


def test_02_so_o_atributo_muda():
    saida = N()(MOTOR)
    sem = ET.fromstring(saida)
    assert sem.get("viewBox")
    import re
    assert re.sub(r' viewBox="[^"]*"', "", saida, count=1) == MOTOR, "alem do viewBox o texto tem de ficar byte a byte igual"
    assert "<![CDATA[" in saida and 'ifc:guid="0mmjvCPT58FfhmvZp_sE_Z"' in saida and 'xmlns:ifc="http://www.ifcopenshell.org/ns"' in saida
    assert N()(MOTOR.encode("utf-8")) == saida, "bytes = texto"
    assert N()(saida) == saida, "idempotente: com viewBox devolve igual"


@pytest.mark.parametrize("vb", ["0 0 1 1", "  1,2,3,4 ", "lixo", "0 0 -5 0"])
def test_03_com_viewbox_devolve_igual_sem_validar(vb):
    texto = f'<?xml version="1.0"?>\n<svg {F.SVG} viewBox="{vb}" width="9"><rect x="0" y="0" width="50" height="50"/></svg>'
    assert N()(texto) == texto
    assert N()(texto, margem_m=7) == texto


def test_04_margem():
    corpo = '<rect x="1" y="2" width="3" height="4"/>'
    aprox(F.caixa_vb(N()(envolver(corpo), margem_m=0)), (1, 2, 3, 4))
    aprox(F.caixa_vb(N()(envolver(corpo))), (0.5, 1.5, 4, 5))
    aprox(F.caixa_vb(N()(envolver(corpo), margem_m=2)), (-1, 0, 7, 8))
    aprox(F.caixa_vb(N()(envolver(corpo), 0.25)), (0.75, 1.75, 3.5, 4.5))
    m = F.P("normalizar_planta")
    for ruim in (-0.1, float("nan"), float("inf"), True, "1", None):
        with pytest.raises(m.PranchaInvalida):
            m.normalizar_planta(envolver(corpo), margem_m=ruim)


# ---------- cada tipo de elemento ----------
CASOS = {
    "path absoluto": ('<path d="M1 2 L5 3 H7 V9 Z"/>', (1, 2, 7, 9)),
    "path relativo": ('<path d="m1 2 l4 1 h2 v6 z"/>', (1, 2, 7, 9)),
    "z volta ao inicio": ('<path d="M0 0 L2 0 L2 2 z m 5 5 l 1 1"/>', (0, 0, 6, 6)),
    "numeros colados": ('<path d="M1-2L3.5.5"/>', (1, -2, 3.5, 0.5)),
    "pares implicitos": ('<path d="M0 0 10 5 3 -4"/>', (0, -4, 10, 5)),
    "pares implicitos relativos": ('<path d="m1 1 2 2 -1 -5"/>', (1, -2, 3, 3)),
    "expoente e virgula": ('<path d="M1e1,2E0 L-1.5e1,0"/>', (-15, 0, 10, 2)),
    "varios subcaminhos": ('<path d="M0 0 L1 1 M8 -3 L9 4"/>', (0, -3, 9, 4)),
    "polyline": ('<polyline points="1,2 3,4 -1,0"/>', (-1, 0, 3, 4)),
    "polygon com espaco": ('<polygon points="0 0 4 0 4 3"/>', (0, 0, 4, 3)),
    "line": ('<line x1="1" y1="2" x2="5" y2="-3"/>', (1, -3, 5, 2)),
    "circle": ('<circle cx="3" cy="4" r="2"/>', (1, 2, 5, 6)),
    "rect": ('<rect x="1" y="2" width="3" height="4"/>', (1, 2, 4, 6)),
    "rect sem x e y": ('<rect width="2" height="2"/>', (0, 0, 2, 2)),
    "uniao": ('<rect x="0" y="0" width="1" height="1"/><circle cx="10" cy="-5" r="1"/><line x1="-3" y1="2" x2="0" y2="2"/>', (-3, -6, 11, 2)),
}


@pytest.mark.parametrize("nome", list(CASOS))
def test_05_caixa_exata(nome):
    corpo, esperado = CASOS[nome]
    aprox(caixa_de(corpo), esperado)


def test_06_curvas_dentro_do_intervalo():
    # cubica: extremo real y=7,5; pontos de controle chegam a y=10
    x0, y0, x1, y1 = caixa_de('<path d="M0 0 C0 10 10 10 10 0"/>')
    assert x0 <= 1e-9 and x1 >= 10 - 1e-9 and x1 <= 10 + 1e-9 and y0 <= 1e-9 and 7.5 - 1e-3 <= y1 <= 10 + 1e-9, (x0, y0, x1, y1)
    # quadratica: extremo real y=5; controle em y=10
    x0, y0, x1, y1 = caixa_de('<path d="M0 0 Q5 10 10 0"/>')
    assert 5 - 1e-3 <= y1 <= 10 + 1e-9 and x0 <= 1e-9 and x1 >= 10 - 1e-9
    # relativa igual a absoluta
    assert caixa_de('<path d="m0 0 c0 10 10 10 10 0"/>') == caixa_de('<path d="M0 0 C0 10 10 10 10 0"/>')


@pytest.mark.parametrize("d,exato,elipse", [
    ("M0 0 A2 2 0 0 1 4 0", (0, -2, 4, 0), (0, -2, 4, 2)),   # sweep 1 (horario na tela, y para baixo): semicirculo para cima
    ("M0 0 A2 2 0 0 0 4 0", (0, 0, 4, 2), (0, -2, 4, 2)),    # sweep 0: para baixo
    ("m0 0 a2 2 0 0 1 4 0", (0, -2, 4, 0), (0, -2, 4, 2)),   # relativo
])
def test_07_arcos(d, exato, elipse):
    x0, y0, x1, y1 = caixa_de(f'<path d="{d}"/>')
    t = 1e-3
    assert x0 <= exato[0] + t and y0 <= exato[1] + t and x1 >= exato[2] - t and y1 >= exato[3] - t, "nao contem o arco"
    assert x0 >= elipse[0] - t and y0 >= elipse[1] - t and x1 <= elipse[2] + t and y1 <= elipse[3] + t, "maior que a elipse inteira"


# ---------- transformacoes ----------
TR = {
    "translate": ('<g transform="translate(10 20)"><rect x="0" y="0" width="2" height="3"/></g>', (10, 20, 12, 23)),
    "translate so tx": ('<g transform="translate(5)"><rect x="0" y="0" width="1" height="1"/></g>', (5, 0, 6, 1)),
    "scale": ('<g transform="scale(2)"><rect x="1" y="1" width="2" height="2"/></g>', (2, 2, 6, 6)),
    "scale sx sy": ('<line transform="scale(2 3)" x1="1" y1="1" x2="2" y2="2"/>', (2, 3, 4, 6)),
    "aninhados": ('<g transform="translate(5,5)"><g transform="scale(2)"><rect x="1" y="1" width="1" height="1"/></g></g>', (7, 7, 9, 9)),
    "lista scale depois translate (aplica o da direita primeiro)": ('<rect transform="translate(1 1) scale(2)" width="1" height="1"/>', (1, 1, 3, 3)),
    "lista translate depois scale": ('<rect transform="scale(2) translate(1 1)" width="1" height="1"/>', (2, 2, 4, 4)),
    "pai com scale, filho com translate": ('<g transform="scale(2)"><rect transform="translate(1 1)" width="1" height="1"/></g>', (2, 2, 4, 4)),
    "scale negativo": ('<rect transform="scale(-1 1)" x="1" y="0" width="2" height="1"/>', (-3, 0, -1, 1)),
}


@pytest.mark.parametrize("nome", list(TR))
def test_08_transformacoes(nome):
    corpo, esperado = TR[nome]
    aprox(caixa_de(corpo), esperado)


@pytest.mark.parametrize("t", ["rotate(45)", "matrix(1 0 0 1 5 5)", "skewX(10)", "translate(1 1) rotate(90)"])
def test_09_transformacao_nao_suportada(t):
    m = F.P("normalizar_planta")
    with pytest.raises(m.SvgInvalido):
        m.normalizar_planta(envolver(f'<g transform="{t}"><rect width="1" height="1"/></g>'))


# ---------- o que fica fora da caixa e as recusas ----------
def test_10_defs_style_texto_e_afins_nao_contam():
    fora = ('<defs><path d="M-100 -100 L100 100"/></defs><clipPath id="c"><rect x="-50" y="-50" width="500" height="500"/></clipPath>'
            '<marker><polygon points="0 0 99 99 0 99"/></marker><mask><circle cx="0" cy="0" r="300"/></mask><pattern><rect width="400" height="400"/></pattern>'
            '<symbol><line x1="0" y1="0" x2="777" y2="0"/></symbol><title>t</title><desc>d</desc><metadata/><style>a{}</style><text x="500" y="500">Sala</text>')
    aprox(caixa_de('<rect x="1" y="1" width="2" height="2"/>' + fora), (1, 1, 3, 3))
    aprox(caixa_de(fora + '<rect x="1" y="1" width="2" height="2"/>'), (1, 1, 3, 3))


@pytest.mark.parametrize("corpo", ["", "<defs><rect width='5' height='5'/></defs>", "<style>a{}</style>", "<text x='1' y='1'>x</text>", "<g/>"])
def test_11_sem_desenhavel(corpo):
    m = F.P("normalizar_planta")
    with pytest.raises(m.SvgInvalido):
        m.normalizar_planta(envolver(corpo))


@pytest.mark.parametrize("svg", ["", "   ", "nao e svg", f"<svg {F.SVG}><rect width='1' height='1'/>", "<html xmlns='http://www.w3.org/2000/svg'/>",
                                 "<svg><rect width='1' height='1'/></svg>",
                                 f"<!DOCTYPE svg [<!ENTITY a 'b'>]><svg {F.SVG}><rect width='1' height='1'/></svg>", None, 3, b"\xff\xfe\x00"])
def test_12_entrada_ruim(svg):
    m = F.P("normalizar_planta")
    with pytest.raises(m.SvgInvalido) as e:
        m.normalizar_planta(svg)
    assert type(e.value) is m.SvgInvalido


def test_13_caixa_sem_area():
    m = F.P("normalizar_planta")
    reta = envolver('<line x1="0" y1="2" x2="9" y2="2"/>')
    with pytest.raises(m.SvgInvalido):
        m.normalizar_planta(reta, margem_m=0)
    aprox(F.caixa_vb(m.normalizar_planta(reta)), (-0.5, 1.5, 10, 1))  # com a margem padrao ganha area
    with pytest.raises(m.SvgInvalido):
        m.normalizar_planta(envolver('<circle cx="1" cy="1" r="0"/>'), margem_m=0)


def test_14_width_height_da_raiz_sao_ignorados():
    svg = f'<svg {F.SVG} width="999px" height="1px"><rect x="0" y="0" width="4" height="2"/></svg>'
    aprox(F.caixa_vb(N()(svg)), (-0.5, -0.5, 5, 3))


# ---------- montar_svg, exportar_svg e exportar_pdf aceitam planta sem viewBox ----------
def test_15_montar_svg_com_planta_do_motor():
    m = F.P("normalizar_planta")
    lado, _ = F.montar_com(escala=100, x=20, y=30)
    svg = m.montar_svg(lado.lat, IDENT, GUID, MOTOR)
    assert svg == m.montar_svg(lado.lat, IDENT, GUID, m.normalizar_planta(MOTOR)), "planta crua = planta normalizada"
    assert svg == m.montar_svg(lado.lat, IDENT, GUID, MOTOR.encode("utf-8"))
    x, y, w, h = A.medir(svg)
    aprox((x, y, w, h), (25, 35, 80, 52), tol=1e-6)  # alvo (-2,-1,8,5.2) m a 1:100; viewBox comeca em (-2.5,-1.5): 0,5 m = 5 mm de folga
    assert A.medir(svg, "alvo")[:2] == pytest.approx((25, 35))


def test_16_fora_da_folha_conta_a_caixa_normalizada():
    m = F.P("normalizar_planta")
    lado, _ = F.montar_com(formato="A4", escala=20, x=10, y=10)  # 9 x 6,2 m a 1:20 = 450 x 310 mm
    with pytest.raises(m.ViewportForaDaFolha) as e:
        m.montar_svg(lado.lat, IDENT, GUID, MOTOR)
    assert type(e.value) is m.ViewportForaDaFolha
    lado, _ = F.montar_com(formato="A4", escala=50, x=10, y=10)  # 180 x 124 mm cabe em 277 x 165
    m.montar_svg(lado.lat, IDENT, GUID, MOTOR)
    lado, _ = F.montar_com(formato="A4", escala=50, x=10, y=51)  # 124 mm de altura: encosta em y+h = 175 = topo do carimbo (vale)
    m.montar_svg(lado.lat, IDENT, GUID, MOTOR)
    lado, _ = F.montar_com(formato="A4", escala=50, x=10, y=51.001)
    with pytest.raises(m.ViewportForaDaFolha):
        m.montar_svg(lado.lat, IDENT, GUID, MOTOR)


def test_17_exportar_svg_e_pdf_sem_viewbox(tmp_path):
    m = F.P("normalizar_planta")
    lado, _ = F.montar_com(escala=100, x=20, y=30)
    alvo = tmp_path / "p.svg"
    m.exportar_svg(lado.lat, IDENT, GUID, MOTOR, alvo)
    assert alvo.read_bytes().decode("utf-8") == m.montar_svg(lado.lat, IDENT, GUID, MOTOR)
    A.exigir_qt()
    pdf = tmp_path / "p.pdf"
    m.exportar_pdf(lado.lat, IDENT, GUID, MOTOR, pdf)
    assert pdf.read_bytes().startswith(b"%PDF-")
    erro = tmp_path / "erro.svg"
    with pytest.raises(m.SvgInvalido):
        m.exportar_svg(lado.lat, IDENT, GUID, envolver("<defs/>"), erro)
    assert not erro.exists()


def test_18_desenho_do_motor_cai_onde_deve(tmp_path):
    A.exigir_qt()
    m = F.P("normalizar_planta")
    lado, _ = F.montar_com(escala=100, x=20, y=30)
    plano = f'<svg {F.SVG}><rect id="alvo" x="-2" y="-1" width="8" height="5.2" fill="#ff0000"/><defs><rect x="-50" y="-50" width="500" height="500"/></defs></svg>'
    svg = m.montar_svg(lado.lat, IDENT, GUID, plano)
    cx, cy, cw, ch = A.caixa_vermelha(A.imagem(svg.encode(), *A.folha_mm(svg)))
    aprox((cx, cy, cw, ch), (25, 35, 80, 52), tol=0.6)


# ---------- precisao ----------
def test_19_coordenadas_grandes_nao_perdem_precisao():
    """Coordenadas de projeto georreferenciado (UTM) tem 7 digitos inteiros: o viewBox tem de guardar tudo, nao so 6 algarismos."""
    corpo = '<rect x="345678.123" y="7654321.987" width="4" height="3"/>'
    aprox(F.caixa_vb(N()(envolver(corpo), margem_m=0)), (345678.123, 7654321.987, 4, 3), tol=1e-3)
    aprox(F.caixa_vb(N()(envolver(corpo))), (345677.623, 7654321.487, 5, 4), tol=1e-3)


def _densa(pontos, n=400001):
    """Pontos (n, 2) da curva de Bezier (de Casteljau) com muitos passos: o 'exato' do teste, sem depender da implementacao."""
    import numpy as np
    t = np.linspace(0, 1, n)[:, None]
    p = [np.array(q, dtype=float)[None, :] for q in pontos]
    while len(p) > 1:
        p = [(1 - t) * a + t * b for a, b in zip(p, p[1:])]
    return p[0]


@pytest.mark.parametrize("d,controle", [
    ("M0 0 C2 9 10 3 10 0", [(0, 0), (2, 9), (10, 3), (10, 0)]),
    ("M0 0 Q12 9 10 0", [(0, 0), (12, 9), (10, 0)]),
    ("M0 0 C-3 4 14 -6 10 5", [(0, 0), (-3, 4), (14, -6), (10, 5)]),
])
def test_20_curvas_assimetricas_contem_o_extremo_exato(d, controle):
    import numpy as np
    pts = _densa(controle)
    x0, y0, x1, y1 = caixa_de(f'<path d="{d}"/>')
    t = 1e-4
    assert x0 <= pts[:, 0].min() + t and y0 <= pts[:, 1].min() + t and x1 >= pts[:, 0].max() - t and y1 >= pts[:, 1].max() - t, (x0, y0, x1, y1)
    c = np.array(controle)
    assert x0 >= c[:, 0].min() - t and y0 >= c[:, 1].min() - t and x1 <= c[:, 0].max() + t and y1 <= c[:, 1].max() + t, "maior que o poligono de controle"


def test_21_arco_assimetrico_contem_o_extremo_exato():
    import math
    r, cx, cy = 500.0, 100.0, 200.0
    a1, a2 = math.radians(200), math.radians(320)  # sentido horario na tela (y para baixo): passa pelo topo (270 graus)
    p1, p2 = (cx + r * math.cos(a1), cy + r * math.sin(a1)), (cx + r * math.cos(a2), cy + r * math.sin(a2))
    x0, y0, x1, y1 = caixa_de(f'<path d="M{p1[0]!r} {p1[1]!r} A500 500 0 0 1 {p2[0]!r} {p2[1]!r}"/>')
    t = 1e-4
    assert y0 <= cy - r + t, f"topo do arco (y={cy - r}) fora da caixa: {y0}"
    assert x0 <= p1[0] + t and x1 >= p2[0] - t and y1 >= p1[1] - t
    assert x0 >= p1[0] - t and x1 <= p2[0] + t and y1 <= p1[1] + t, "arco de 120 graus nao chega aos lados da circunferencia"


def test_22_arco_de_elipse_girada_contem_o_extremo_exato():
    """Elipse com rotacao (x_rot = 30): os extremos nao estao nos eixos; a caixa sai da conta independente em numpy."""
    import math
    import numpy as np
    rx, ry, phi, cx, cy = 500.0, 200.0, math.radians(30), 100.0, 50.0
    ponto = lambda t: (cx + rx * math.cos(phi) * np.cos(t) - ry * math.sin(phi) * np.sin(t), cy + rx * math.sin(phi) * np.cos(t) + ry * math.cos(phi) * np.sin(t))
    t1, t2 = math.radians(20), math.radians(140)  # parametro crescente = sweep 1; 120 graus = arco pequeno
    (xa, ya), (xb, yb) = ponto(t1), ponto(t2)
    xs, ys = ponto(np.linspace(t1, t2, 400001))
    x0, y0, x1, y1 = caixa_de(f'<path d="M{float(xa)!r} {float(ya)!r} A500 200 30 0 1 {float(xb)!r} {float(yb)!r}"/>')
    t = 1e-4
    assert x0 <= xs.min() + t and y0 <= ys.min() + t and x1 >= xs.max() - t and y1 >= ys.max() - t, ((x0, y0, x1, y1), (xs.min(), ys.min(), xs.max(), ys.max()))
    folga = math.hypot(rx * math.cos(phi), ry * math.sin(phi)), math.hypot(rx * math.sin(phi), ry * math.cos(phi))  # semi-eixos da caixa da elipse inteira
    assert x0 >= cx - folga[0] - t and x1 <= cx + folga[0] + t and y0 >= cy - folga[1] - t and y1 <= cy + folga[1] + t


def test_23_arco_no_sentido_anti_horario_contem_o_extremo_exato():
    """sweep 0: o angulo diminui (de 340 para 220 graus, passando pelo topo, 270)."""
    import math
    r, cx, cy = 500.0, 100.0, 200.0
    a1, a2 = math.radians(340), math.radians(220)
    p1, p2 = (cx + r * math.cos(a1), cy + r * math.sin(a1)), (cx + r * math.cos(a2), cy + r * math.sin(a2))
    x0, y0, x1, y1 = caixa_de(f'<path d="M{p1[0]!r} {p1[1]!r} A500 500 0 0 0 {p2[0]!r} {p2[1]!r}"/>')
    t = 1e-4
    assert y0 <= cy - r + t, f"topo do arco (y={cy - r}) fora da caixa: {y0}"
    assert x0 <= p2[0] + t and x1 >= p1[0] - t and y1 >= p2[1] - t
    assert x0 >= p2[0] - t and x1 <= p1[0] + t and y1 <= p1[1] + t, "arco de 120 graus nao chega aos lados da circunferencia"
