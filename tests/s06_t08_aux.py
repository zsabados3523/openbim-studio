# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ajudantes do oraculo da F0-S06-T08 (prancha minima). Sem ifcopenshell. Mede o SVG de saida de dois jeitos independentes: compondo as
transformacoes do arquivo (preciso) e desenhando com Qt (pixels, nao depende da estrutura interna da implementacao)."""
import re
import xml.etree.ElementTree as ET

from obrigatorio import pular

NS = "{http://www.w3.org/2000/svg}"
GUID = "0$Fq3Zk1D5Pv2wX4yAbC_E"  # GlobalId de verdade tem `$`
IDENT = "A-01.2 / rev B"  # Identification com espaco, ponto e barra
DADOS = dict(formato="A3", projeto="Casa da Praia", titulo="Planta do térreo", data="2026-11-01", folha="01/03")
PX_MM = 4  # pixels por mm nas conferencias por desenho


def planta(vb=(-1, -1, 12, 8), alvo=(0, 0, 10, 6), extra=""):
    """SVG de planta SINTETICO: unidade = metro; `viewBox` = (minx, miny, largura, altura); `alvo` = retangulo vermelho (x, y, w, h) em metros."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="999px" height="999px" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}">'
            f'<rect id="alvo" x="{alvo[0]}" y="{alvo[1]}" width="{alvo[2]}" height="{alvo[3]}" fill="#ff0000"/>{extra}</svg>')


class Lado:
    """O que `t.lado` de uma transacao oferece (criar/alterar/apagar), em cima de um `Lateral`; so para os casos sem IFC."""
    def __init__(self, lateral=None):
        from openbim_app.lateral import Lateral
        self.lat = lateral if lateral is not None else Lateral()
        self.chamadas = []

    def criar(self, c, i, o):
        self.chamadas.append(("criar", c, i))
        self.lat._criar(c, i, o)


def montar(escala=50, x=20, y=20, formato="A3", vb=(-1, -1, 12, 8), alvo=(0, 0, 10, 6), guid=GUID, ident=IDENT, **sobre):
    """Cria prancha e viewport num `Lado` novo; devolve (lado, svg_da_planta). `sobre` troca campos do carimbo."""
    import openbim_app.prancha as P
    lado = Lado()
    P.criar_prancha(lado, ident, **{**DADOS, "formato": formato, **sobre})
    P.colocar_viewport(lado, ident, guid, x, y, escala)
    return lado, planta(vb, alvo)


def saida(**kw):
    """SVG da prancha (texto) para os mesmos parametros de `montar`."""
    import openbim_app.prancha as P
    lado, svg = montar(**kw)
    return P.montar_svg(lado.lat, kw.get("ident", IDENT), kw.get("guid", GUID), svg)


def _compor(a, b):  # matrizes (a, b, c, d, e, f) do SVG: a depois b (b aplica primeiro)
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _matriz(texto):
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for nome, args in re.findall(r"(translate|scale)\(([^)]*)\)", texto or ""):
        n = [float(v) for v in re.split(r"[ ,]+", args.strip())]
        if nome == "translate":
            t = (1.0, 0.0, 0.0, 1.0, n[0], n[1] if len(n) > 1 else 0.0)
        else:
            t = (n[0], 0.0, 0.0, n[1] if len(n) > 1 else n[0], 0.0, 0.0)
        m = _compor(m, t)
    return m


def medir(svg, ident="alvo"):
    """(x, y, largura, altura) em mm da folha do elemento `ident`, compondo `transform` (so translate e scale) de todos os ancestrais."""
    raiz = ET.fromstring(svg)

    def busca(no, acumulada):
        acumulada = _compor(acumulada, _matriz(no.get("transform")))
        if no.get("id") == ident:
            return no, acumulada
        for f in no:
            r = busca(f, acumulada)
            if r:
                return r
        return None
    r = busca(raiz, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    assert r, f"sem elemento id={ident!r} na prancha"
    no, m = r
    x, y, w, h = (float(no.get(k)) for k in ("x", "y", "width", "height"))
    return m[4] + m[0] * x, m[5] + m[3] * y, m[0] * w, m[3] * h


def folha_mm(svg):
    """(largura, altura) em mm lidas de width/height do `<svg>` raiz (unidade `mm`) e conferidas com o viewBox (1 unidade = 1 mm)."""
    raiz = ET.fromstring(svg)
    w, h = raiz.get("width"), raiz.get("height")
    assert w.endswith("mm") and h.endswith("mm"), (w, h)
    vb = [float(v) for v in raiz.get("viewBox").split()]
    assert vb[0] == vb[1] == 0 and (vb[2], vb[3]) == (float(w[:-2]), float(h[:-2])), (vb, w, h)
    return vb[2], vb[3]


def textos(svg, grupo="carimbo"):
    """[(texto, x, y)] de todos os `<text>` dentro do grupo `grupo`."""
    raiz = ET.fromstring(svg)
    g = next(e for e in raiz.iter(NS + "g") if e.get("id") == grupo)
    return [("".join(t.itertext()).strip(), float(t.get("x")), float(t.get("y"))) for t in g.iter(NS + "text")]


def imagem(svg_bytes, largura_mm, altura_mm):
    """Desenha o SVG com Qt a PX_MM pixels por mm, em QImage branca; precisa de QGuiApplication (a fixture `qt` cria)."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(svg_bytes)
    assert r.isValid(), "Qt nao leu o SVG de saida"
    img = QImage(int(round(largura_mm * PX_MM)), int(round(altura_mm * PX_MM)), QImage.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    r.render(p)
    p.end()
    return img


def caixa_vermelha(img, px_mm=PX_MM):
    """Caixa (x, y, w, h) em mm dos pixels vermelhos (r>200, g<60, b<60); None se nao ha."""
    import numpy as np
    n = img.sizeInBytes() // img.height() // 4
    a = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), n, 4)[:, :img.width()]  # BGRA
    m = (a[:, :, 2] > 200) & (a[:, :, 1] < 60) & (a[:, :, 0] < 60)
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    return xs.min() / px_mm, ys.min() / px_mm, (xs.max() - xs.min() + 1) / px_mm, (ys.max() - ys.min() + 1) / px_mm


def exigir_qt():
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtSvg import QSvgRenderer  # noqa: F401
    except ImportError as e:
        pular(f"S06-T08: sem PySide6 ({e}); teste NAO FOI EXECUTADO", "OBIM_S06_OBRIGATORIO")
    return QGuiApplication.instance() or QGuiApplication([])
