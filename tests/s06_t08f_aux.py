# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ajudantes do oraculo da F0-S06-T08f (planta real: viewBox, espessura de linha, formatos e rotacao). Contrato: docstring de `test_s06_t08f_oraculo.py`.
Mede de dois jeitos independentes: lendo o SVG (`caixa_vb`, `A.medir`) e desenhando com Qt (`desenhar`, `espessura_mm`, `A.caixa_vermelha`)."""
import inspect
import re

import s06_t08_aux as A
from s06_t08_aux import IDENT, GUID

NS = A.NS
SVG = 'xmlns="http://www.w3.org/2000/svg"'
PX = 4  # pixels por mm nos desenhos


def P(*exigidos, formato=None, rotacao=False):
    """Importa `openbim_app.prancha`. Confere que a API da T08f existe (ImportError se faltar)."""
    import openbim_app.prancha as m
    for nome in exigidos:
        if not hasattr(m, nome):
            raise ImportError(f"prancha.{nome} ainda nao existe")
    if formato and formato not in m.FORMATOS:
        raise ImportError(f"formato {formato} ainda nao existe em FORMATOS")
    if rotacao and "rotacao" not in inspect.signature(m.colocar_viewport).parameters:
        raise ImportError("colocar_viewport ainda nao tem o parametro rotacao")
    return m


def envolver(corpo, extra_raiz=""):
    """SVG de planta SEM viewBox (como o do motor), 1 unidade = 1 m."""
    return f'<svg {SVG} {extra_raiz}>{corpo}</svg>'


# Recorte sintetico no formato do ifcopenshell (serializers.svg): sem viewBox, `xmlns:ifc`, `<defs>` com marcadores grandes, `<style>` em CDATA,
# `g.section` com produtos `g.IfcXxx` (corte, SEM a classe `cut`) e `g.projection IfcXxx` com `path.outline`. Caixa do desenho: (-2, -1) a (6, 4.2) m.
MOTOR = f'''<svg {SVG} xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ifc="http://www.ifcopenshell.org/ns">
    <defs>
        <marker id="arrowend" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 10 7" />
        </marker>
    </defs>
    <style type="text/css" >
    <![CDATA[
        .cut path {{ stroke: #222222; fill: #444444; fill-rule: evenodd; }}
        path.outline {{ stroke: #000000; stroke-width: 0.35px; stroke-opacity: 1; }}
        .IfcDoor path {{ fill: none; }}
    ]]>
    </style>
    <g ifc:name="Elevation Planta" class="section">
        <g id="product-1-body" class="IfcWallStandardCase" ifc:name="Parede:Generica - 200 mm:1" ifc:guid="0mmjvCPT58FfhmvZp_sE_Z" >
            <path d="M-2,-1 L6,-1 L6,-0.8 L-2,-0.8 L-2,-1 Z"/>
        </g>
        <g id="product-1-proj" class="projection IfcWallStandardCase" ifc:guid="0mmjvCPT58FfhmvZp_sE_Z" >
            <path class="outline" d="m -2,-1 l 8,0 v 5.2 h -8 z"/>
        </g>
        <g id="product-2-body" class="IfcDoor" ifc:guid="3NVTn3MP54geHCWb3Uvaei" >
            <path d="M1,2 A1,1 0 0 1 2,1"/>
        </g>
        <rect id="alvo" x="-2" y="-1" width="8" height="5.2" fill="none"/>
    </g>
</svg>'''
MOTOR_VB = (-2.5, -1.5, 9.0, 6.2)  # caixa do desenho + margem de 0,5 m


def caixa_vb(svg):
    """(minx, miny, largura, altura) do `viewBox` da raiz de `svg` (texto); AssertionError se nao ha."""
    import xml.etree.ElementTree as ET
    vb = ET.fromstring(svg).get("viewBox")
    assert vb, "svg sem viewBox"
    n = [float(v) for v in re.split(r"[,\s]+", vb.strip())]
    assert len(n) == 4, vb
    return tuple(n)


def desenhar(svg, W, H, px=PX):
    """QImage RGB32 branca (W x H mm a `px` pixels por mm) com o SVG desenhado com antialiasing."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(svg.encode("utf-8") if isinstance(svg, str) else svg)
    assert r.isValid(), "Qt nao leu o SVG"
    img = QImage(int(round(W * px)), int(round(H * px)), QImage.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    r.render(p)
    p.end()
    return img


def cinza(img):
    """Matriz numpy (altura, largura) com a escuridao de cada pixel, 0 (branco) a 1 (preto), pelo canal verde."""
    import numpy as np
    n = img.sizeInBytes() // img.height() // 4
    a = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), n, 4)[:, :img.width()]
    return 1.0 - a[:, :, 1] / 255.0


def espessura_mm(img, y_mm, x0_mm, x1_mm, meia_banda_mm=2.0, px=PX):
    """Espessura em mm de um traco horizontal preto centrado em y_mm: soma da escuridao de cada coluna na faixa y_mm +- meia_banda_mm, media nas colunas de x0 a x1."""
    g = cinza(img)
    r0, r1 = int(round((y_mm - meia_banda_mm) * px)), int(round((y_mm + meia_banda_mm) * px))
    c0, c1 = int(round(x0_mm * px)), int(round(x1_mm * px))
    return float(g[r0:r1, c0:c1].sum(axis=0).mean()) / px


def montar_com(formato="A3", escala=100, x=20, y=20, rotacao=None, planta=None, **sobre):
    """Cria prancha e viewport (com `rotacao` se dada) num `Lado`; devolve (lado, planta_svg)."""
    import openbim_app.prancha as m
    lado = A.Lado()
    m.criar_prancha(lado, IDENT, **{**A.DADOS, "formato": formato, **sobre})
    if rotacao is None:
        m.colocar_viewport(lado, IDENT, GUID, x, y, escala)
    else:
        m.colocar_viewport(lado, IDENT, GUID, x, y, escala, rotacao=rotacao)
    return lado, (planta if planta is not None else A.planta())


def escuros(img):
    """Mascara numpy dos pixels escuros (r, g, b < 100) de uma QImage RGB32."""
    import numpy as np
    n = img.sizeInBytes() // img.height() // 4
    a = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), n, 4)[:, :img.width()]
    return (a[:, :, 0] < 100) & (a[:, :, 1] < 100) & (a[:, :, 2] < 100)
