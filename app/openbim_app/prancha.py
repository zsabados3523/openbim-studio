# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prancha minima e viewport (F0-S06-T08).
Sem Qt nem ifcopenshell no topo; gravacao no lateral (.obim), SVG e PDF."""
import math
import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

FORMATOS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}
MARGEM_MM = 10.0
CARIMBO_ALTURA_MM = 25.0

_QT_APP = None


class PranchaInvalida(ValueError):
    """Erro de validacao de prancha ou viewport."""


class FormatoInvalido(PranchaInvalida):
    """Formato de folha nao suportado."""


class EscalaInvalida(PranchaInvalida):
    """Escala invalida para o viewport."""


class SvgInvalido(PranchaInvalida):
    """SVG da planta invalido ou malformado."""


class ViewportForaDaFolha(PranchaInvalida):
    """Viewport fora da area util da prancha ou sobre o carimbo."""


class PranchaNaoEncontrada(PranchaInvalida):
    """Prancha ou viewport nao encontrado."""


def _contem_controle(texto):
    if not isinstance(texto, str):
        return True
    for ch in texto:
        code = ord(ch)
        if unicodedata.category(ch) in ("Cc", "Cs") or code in (0xFFFE, 0xFFFF):
            return True
    return False


def _obter_prancha(lateral, identification):
    for uid in lateral.ids("pranchas"):
        p = lateral.obter("pranchas", uid)
        if p.get("identification") == identification:
            return p
    raise PranchaNaoEncontrada(f"prancha {identification!r} nao encontrada")


def _obter_viewport(lateral, identification, vista_guid):
    for uid in lateral.ids("viewports"):
        v = lateral.obter("viewports", uid)
        if v.get("prancha") == identification and v.get("vista_guid") == vista_guid:
            return v
    raise PranchaNaoEncontrada(f"viewport nao encontrado para {identification!r} / {vista_guid!r}")


def criar_prancha(lado, identification, formato, projeto, titulo, data, folha):
    """Cria prancha na colecao 'pranchas' do lateral."""
    if not isinstance(identification, str) or not identification or identification != identification.strip() or _contem_controle(identification):
        raise PranchaInvalida("identification vazia ou com espaco nas pontas")
    if not isinstance(formato, str) or formato not in FORMATOS:
        raise FormatoInvalido(f"formato desconhecido: {formato!r}")
    for campo, val in (("projeto", projeto), ("titulo", titulo), ("folha", folha)):
        if not isinstance(val, str) or not val.strip() or _contem_controle(val):
            raise PranchaInvalida(f"{campo} vazio ou invalido")
    if not isinstance(data, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data):
        raise PranchaInvalida(f"formato de data invalido: {data!r}")
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        raise PranchaInvalida(f"data fora do calendario real: {data!r}")

    uid = str(uuid.uuid4())
    obj = {
        "identification": identification,
        "formato": formato,
        "carimbo": {
            "projeto": projeto,
            "titulo": titulo,
            "data": data,
            "folha": folha,
        },
    }
    lado.criar("pranchas", uid, obj)
    return uid


def colocar_viewport(lado, identification, vista_guid, x_mm, y_mm, escala):
    """Cria viewport na colecao 'viewports' do lateral."""
    if not isinstance(identification, str) or not identification or identification != identification.strip() or _contem_controle(identification):
        raise PranchaInvalida("identification vazia ou com espaco nas pontas")
    if not isinstance(vista_guid, str) or not vista_guid or _contem_controle(vista_guid):
        raise PranchaInvalida("vista_guid vazio ou invalido")
    for v in (x_mm, y_mm):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise PranchaInvalida("coordenada x ou y invalida")
    if isinstance(escala, bool) or not isinstance(escala, (int, float)) or not math.isfinite(escala) or escala <= 0:
        raise EscalaInvalida("escala invalida: deve ser numero finito > 0")

    uid = str(uuid.uuid4())
    obj = {
        "prancha": identification,
        "vista_guid": vista_guid,
        "x": x_mm,
        "y": y_mm,
        "escala": escala,
    }
    lado.criar("viewports", uid, obj)
    return uid


def ler_viewport(lateral, identification, vista_guid):
    """Le viewport do lateral e devolve {'x', 'y', 'escala'}."""
    v = _obter_viewport(lateral, identification, vista_guid)
    return {"x": v["x"], "y": v["y"], "escala": v["escala"]}


def montar_svg(lateral, identification, vista_guid, planta_svg):
    """Monta SVG 1.1 da prancha com folha, moldura, viewport e carimbo."""
    prancha = _obter_prancha(lateral, identification)
    viewport = _obter_viewport(lateral, identification, vista_guid)

    if _contem_controle(vista_guid):
        raise PranchaInvalida(f"vista_guid contem caractere de controle: {vista_guid!r}")

    carimbo = prancha.get("carimbo", {})
    for campo in ("projeto", "titulo", "folha", "data"):
        val = carimbo.get(campo, "")
        if not isinstance(val, str) or _contem_controle(val):
            raise PranchaInvalida(f"{campo} no carimbo contem caractere de controle: {val!r}")
    data_str = carimbo.get("data", "")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data_str):
        raise PranchaInvalida(f"formato de data invalido no carimbo: {data_str!r}")

    formato = prancha.get("formato")
    if formato not in FORMATOS:
        raise FormatoInvalido(f"formato desconhecido: {formato!r}")
    W, H = FORMATOS[formato]

    if isinstance(planta_svg, bytes):
        try:
            planta_str = planta_svg.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SvgInvalido(f"bytes nao utf-8: {e}") from e
    elif isinstance(planta_svg, str):
        planta_str = planta_svg
    else:
        raise SvgInvalido("planta_svg deve ser str ou bytes")

    if not planta_str.strip():
        raise SvgInvalido("svg vazio")

    if "<!doctype" in planta_str.lower() or "<!entity" in planta_str.lower():
        raise SvgInvalido("doctype ou entity proibido no svg da planta")

    try:
        planta_root = ET.fromstring(planta_str)
    except ET.ParseError as e:
        raise SvgInvalido(f"xml da planta malformado: {e}") from e

    if planta_root.tag != "{http://www.w3.org/2000/svg}svg":
        raise SvgInvalido("raiz do svg da planta nao e <svg> com namespace")

    vb = planta_root.get("viewBox")
    if not vb:
        raise SvgInvalido("svg da planta sem viewBox")

    partes = re.split(r"[,\s]+", vb.strip())
    if len(partes) != 4:
        raise SvgInvalido("viewBox precisa conter 4 numeros")

    try:
        minx, miny, w, h = (float(p) for p in partes)
    except ValueError as e:
        raise SvgInvalido(f"viewBox contem valores nao numericos: {e}") from e

    if not (math.isfinite(minx) and math.isfinite(miny) and math.isfinite(w) and math.isfinite(h)):
        raise SvgInvalido("viewBox contem valores infinitos ou NaN")

    if w <= 0 or h <= 0:
        raise SvgInvalido("largura e altura do viewBox devem ser maiores que zero")

    x = viewport["x"]
    y = viewport["y"]
    escala = viewport["escala"]
    s = 1000.0 / escala
    vw = w * s
    vh = h * s

    tol = 1e-9
    if x < 10.0 - tol or y < 10.0 - tol or (x + vw) > (W - 10.0) + tol or (y + vh) > (H - 35.0) + tol:
        raise ViewportForaDaFolha("viewport fora da area util da prancha")

    root = ET.Element(
        "{http://www.w3.org/2000/svg}svg",
        {
            "width": f"{W:g}mm",
            "height": f"{H:g}mm",
            "viewBox": f"0 0 {W:g} {H:g}",
        },
    )

    ET.SubElement(
        root,
        "{http://www.w3.org/2000/svg}rect",
        {
            "id": "folha",
            "x": "0",
            "y": "0",
            "width": f"{W:g}",
            "height": f"{H:g}",
            "fill": "#ffffff",
        },
    )

    ET.SubElement(
        root,
        "{http://www.w3.org/2000/svg}rect",
        {
            "id": "moldura",
            "x": "10",
            "y": "10",
            "width": f"{W - 20:g}",
            "height": f"{H - 20:g}",
            "fill": "none",
            "stroke": "#000000",
            "stroke-width": "0.5",
        },
    )

    tx = x - minx * s
    ty = y - miny * s
    vp_elem = ET.SubElement(
        root,
        "{http://www.w3.org/2000/svg}g",
        {
            "id": "viewport",
            "data-vista": vista_guid,
            "transform": f"translate({tx:.10g}, {ty:.10g}) scale({s:.10g})",
        },
    )
    for child in planta_root:
        vp_elem.append(child)

    carimbo_elem = ET.SubElement(root, "{http://www.w3.org/2000/svg}g", {"id": "carimbo"})
    ET.SubElement(
        carimbo_elem,
        "{http://www.w3.org/2000/svg}rect",
        {
            "id": "carimbo-caixa",
            "x": "10",
            "y": f"{H - 35:g}",
            "width": f"{W - 20:g}",
            "height": "25",
            "fill": "none",
            "stroke": "#000000",
            "stroke-width": "0.5",
        },
    )

    fs = 4.0
    folga = 5.0
    linhas = [
        [carimbo.get("projeto", ""), carimbo.get("data", ""), carimbo.get("folha", "")],
        [carimbo.get("titulo", ""), f"1:{escala:g}"],
    ]
    baselines = [H - 22.0, H - 13.0]

    for line_items, y_base in zip(linhas, baselines):
        x_curr = 15.0
        for val in line_items:
            val_str = str(val)
            w_est = 0.6 * fs * len(val_str)
            txt_elem = ET.SubElement(
                carimbo_elem,
                "{http://www.w3.org/2000/svg}text",
                {
                    "x": f"{x_curr:g}",
                    "y": f"{y_base:g}",
                    "font-size": f"{fs:g}",
                },
            )
            txt_elem.text = val_str
            x_curr += w_est + folga

    raw = ET.tostring(root, encoding="unicode")
    m = re.search(r'xmlns:(ns\d+)="http://www.w3.org/2000/svg"', raw)
    if m:
        pfx = m.group(1)
        raw = raw.replace(f'xmlns:{pfx}="http://www.w3.org/2000/svg"', 'xmlns="http://www.w3.org/2000/svg"')
        raw = raw.replace(f"<{pfx}:", "<").replace(f"</{pfx}:", "</")

    try:
        ET.fromstring(raw)
    except ET.ParseError as e:
        raise PranchaInvalida(f"svg gerado malformado: {e}") from e

    return raw


def exportar_svg(lateral, identification, vista_guid, planta_svg, destino):
    """Exporta prancha como arquivo SVG em UTF-8."""
    destino = Path(destino)
    conteudo = montar_svg(lateral, identification, vista_guid, planta_svg)
    destino.write_bytes(conteudo.encode("utf-8"))
    return destino


def exportar_pdf(lateral, identification, vista_guid, planta_svg, destino):
    """Exporta prancha como PDF de 1 pagina do tamanho da folha."""
    global _QT_APP
    destino = Path(destino)
    conteudo = montar_svg(lateral, identification, vista_guid, planta_svg)

    prancha = _obter_prancha(lateral, identification)
    formato = prancha.get("formato")
    if formato not in FORMATOS:
        raise FormatoInvalido(f"formato desconhecido: {formato!r}")
    W, H = FORMATOS[formato]

    from PySide6.QtCore import QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance()
    if app is None:
        _QT_APP = app = QGuiApplication([])

    if isinstance(conteudo, str):
        svg_bytes = conteudo.encode("utf-8")
    elif isinstance(conteudo, bytes):
        svg_bytes = conteudo
    else:
        raise SvgInvalido("conteudo svg deve ser str ou bytes")

    renderer = QSvgRenderer(svg_bytes)
    if not renderer.isValid():
        raise SvgInvalido("Qt nao conseguiu ler o SVG montado")

    writer = QPdfWriter(str(destino))
    page_size = QPageSize(QSizeF(W, H), QPageSize.Unit.Millimeter)
    writer.setPageSize(page_size)
    layout = QPageLayout(page_size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))
    writer.setPageLayout(layout)

    painter = QPainter(writer)
    try:
        renderer.render(painter, QRectF(0, 0, writer.width(), writer.height()))
    finally:
        painter.end()

    return destino
