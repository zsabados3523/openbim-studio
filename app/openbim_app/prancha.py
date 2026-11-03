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

FORMATOS = {
    "A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
    "A1": (841.0, 594.0), "A0": (1189.0, 841.0),
}
MARGEM_MM, CARIMBO_ALTURA_MM = 10.0, 25.0
_QT_APP = None
_NUM_ASCII_RE = re.compile(r"^[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?[0-9]*)(?:[eE][-+]?[0-9]+)?$")


def _resumo(valor, limite=80):
    if isinstance(valor, str):
        texto = valor[:limite] + ("..." if len(valor) > limite else "")
        return repr(texto)
    texto = repr(valor)
    return texto if len(texto) <= limite else texto[:limite] + "..."


class PranchaInvalida(ValueError): """Erro de validacao de prancha ou viewport."""
class FormatoInvalido(PranchaInvalida): """Formato de folha nao suportado."""
class EscalaInvalida(PranchaInvalida): """Escala invalida para o viewport."""
class SvgInvalido(PranchaInvalida): """SVG da planta invalido ou malformado."""
class ViewportForaDaFolha(PranchaInvalida): """Viewport fora da area util da prancha ou sobre o carimbo."""
class PranchaNaoEncontrada(PranchaInvalida): """Prancha ou viewport nao encontrado."""
class RotacaoInvalida(PranchaInvalida): """Rotacao invalida para o viewport."""


def _num(val):
    if isinstance(val, bool):
        raise SvgInvalido(f"valor booleano invalido: {_resumo(val)}")
    if isinstance(val, (int, float)):
        if not math.isfinite(val) or abs(val) > 1e12:
            raise SvgInvalido(f"valor nao finito ou excessivo: {_resumo(val)}")
        return float(val)
    if not isinstance(val, str):
        raise SvgInvalido(f"valor invalido: {_resumo(val)}")
    if len(val) > 1024:
        raise SvgInvalido(f"valor numerico invalido: {_resumo(val)}")
    val = val.strip()
    if not val or len(val) > 64 or not _NUM_ASCII_RE.fullmatch(val):
        raise SvgInvalido(f"valor numerico invalido: {_resumo(val)}")
    try:
        f = float(val)
    except (ValueError, TypeError, OverflowError) as e:
        raise SvgInvalido(f"valor numerico invalido: {_resumo(val)}") from e
    if not math.isfinite(f) or abs(f) > 1e12:
        raise SvgInvalido(f"valor nao finito ou excessivo: {_resumo(val)}")
    return f


def _raio(val):
    r = _num(val)
    if r < 0:
        raise SvgInvalido("raio negativo")
    return r


def _contem_controle(texto):
    if not isinstance(texto, str):
        return True
    return any(unicodedata.category(c) in ("Cc", "Cs") or ord(c) in (0xFFFE, 0xFFFF) for c in texto)


def _obter_prancha(lateral, identification):
    for uid in lateral.ids("pranchas"):
        p = lateral.obter("pranchas", uid)
        if not isinstance(p, dict):
            raise PranchaInvalida(f"prancha deve ser dict, recebido {type(p).__name__}")
        if p.get("identification") == identification:
            return p
    raise PranchaNaoEncontrada(f"prancha {_resumo(identification)} nao encontrada")


def _obter_viewport(lateral, identification, vista_guid):
    for uid in lateral.ids("viewports"):
        v = lateral.obter("viewports", uid)
        if not isinstance(v, dict):
            raise PranchaInvalida(f"viewport deve ser dict, recebido {type(v).__name__}")
        if v.get("prancha") == identification and v.get("vista_guid") == vista_guid:
            return v
    raise PranchaNaoEncontrada(f"viewport nao encontrado para {_resumo(identification)} / {_resumo(vista_guid)}")


def criar_prancha(lado, identification, formato, projeto, titulo, data, folha):
    """Cria prancha na colecao 'pranchas' do lateral."""
    if not isinstance(identification, str) or not identification or identification != identification.strip() or _contem_controle(identification):
        raise PranchaInvalida("identification vazia ou com espaco nas pontas")
    if not isinstance(formato, str) or formato not in FORMATOS:
        raise FormatoInvalido(f"formato desconhecido: {_resumo(formato)}")
    for campo, val in (("projeto", projeto), ("titulo", titulo), ("folha", folha)):
        if not isinstance(val, str) or not val.strip() or _contem_controle(val):
            raise PranchaInvalida(f"{campo} vazio ou invalido")
    if not isinstance(data, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data):
        raise PranchaInvalida(f"formato de data invalido: {_resumo(data)}")
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        raise PranchaInvalida(f"data fora do calendario real: {_resumo(data)}")

    uid = str(uuid.uuid4())
    obj = {"identification": identification, "formato": formato,
           "carimbo": {"projeto": projeto, "titulo": titulo, "data": data, "folha": folha}}
    lado.criar("pranchas", uid, obj)
    return uid


def colocar_viewport(lado, identification, vista_guid, x_mm, y_mm, escala, rotacao=0):
    """Cria viewport na colecao 'viewports' do lateral."""
    if isinstance(rotacao, bool) or not isinstance(rotacao, int) or rotacao not in (0, 90):
        raise RotacaoInvalida(f"rotacao invalida: {_resumo(rotacao)}")
    if not isinstance(identification, str) or not identification or identification != identification.strip() or _contem_controle(identification):
        raise PranchaInvalida("identification vazia ou com espaco nas pontas")
    if not isinstance(vista_guid, str) or not vista_guid or _contem_controle(vista_guid):
        raise PranchaInvalida("vista_guid vazio ou invalido")
    for v in (x_mm, y_mm):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise PranchaInvalida("coordenada x ou y invalida")
        try:
            vf = float(v)
        except OverflowError as e:
            raise PranchaInvalida("coordenada x ou y invalida") from e
        if not math.isfinite(vf) or abs(vf) > 1e12:
            raise PranchaInvalida("coordenada x ou y invalida")
    if isinstance(escala, bool) or not isinstance(escala, (int, float)):
        raise EscalaInvalida("escala invalida: deve ser numero finito > 0")
    try:
        ef = float(escala)
    except OverflowError as e:
        raise EscalaInvalida("escala invalida") from e
    if not math.isfinite(ef) or ef <= 0 or ef > 1e12:
        raise EscalaInvalida("escala invalida: deve ser numero finito > 0")

    uid = str(uuid.uuid4())
    obj = {"prancha": identification, "vista_guid": vista_guid, "x": x_mm, "y": y_mm, "escala": escala}
    if rotacao == 90:
        obj["rotacao"] = 90
    lado.criar("viewports", uid, obj)
    return uid


def ler_viewport(lateral, identification, vista_guid):
    """Le viewport do lateral e devolve {'x', 'y', 'escala'} (e 'rotacao' se 90)."""
    v = _obter_viewport(lateral, identification, vista_guid)
    res = {"x": v["x"], "y": v["y"], "escala": v["escala"]}
    if v.get("rotacao") == 90:
        res["rotacao"] = 90
    return res


def normalizar_planta(svg_texto, margem_m=0.5):
    """Injeta viewBox na raiz se faltar, calculando a caixa delimitadora dos desenhaveis."""
    if isinstance(margem_m, bool) or not isinstance(margem_m, (int, float)) or not math.isfinite(margem_m) or margem_m < 0 or margem_m > 1e12:
        raise PranchaInvalida("margem_m invalida")
    if isinstance(svg_texto, (bytes, bytearray)):
        if len(svg_texto) > 64 * 1024 * 1024:
            raise SvgInvalido("svg excede limite de 64 MB")
        try:
            svg_str = svg_texto.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SvgInvalido(f"bytes nao utf-8: {e}") from e
    elif isinstance(svg_texto, str):
        if len(svg_texto) > 64 * 1024 * 1024:
            raise SvgInvalido("svg excede limite de 64 MB")
        svg_str = svg_texto
    else:
        raise SvgInvalido("svg_texto deve ser str ou bytes")
    if not svg_str.strip():
        raise SvgInvalido("svg vazio")
    if "<!doctype" in svg_str.lower() or "<!entity" in svg_str.lower():
        raise SvgInvalido("doctype ou entity proibido no svg da planta")
    try:
        root = ET.fromstring(svg_str)
    except (ET.ParseError, UnicodeError) as e:
        raise SvgInvalido(f"xml da planta malformado: {e}") from e
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise SvgInvalido("raiz do svg da planta nao e <svg> com namespace")
    return svg_str


def _validar_prancha_e_viewport(prancha, viewport, vista_guid):
    if not isinstance(prancha, dict) or not isinstance(viewport, dict):
        raise PranchaInvalida("prancha ou viewport invalido")
    if not isinstance(vista_guid, str) or _contem_controle(vista_guid):
        raise PranchaInvalida(f"vista_guid contem caractere de controle ou invalido: {_resumo(vista_guid)}")

    escala = viewport.get("escala")
    if isinstance(escala, bool) or not isinstance(escala, (int, float)):
        raise EscalaInvalida(f"escala invalida no lateral: {_resumo(escala)}")
    try:
        escala_f = float(escala)
    except OverflowError as e:
        raise EscalaInvalida(f"escala invalida no lateral: {_resumo(escala)}") from e
    if not math.isfinite(escala_f) or escala_f <= 0 or escala_f > 1e12:
        raise EscalaInvalida(f"escala invalida no lateral: {_resumo(escala)}")

    for k in ("x", "y"):
        v = viewport.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise PranchaInvalida(f"coordenada {k} nao pode ser booleano ou nao numerico: {_resumo(v)}")
        try:
            vf = float(v)
        except OverflowError as e:
            raise PranchaInvalida(f"coordenada {k} invalida no lateral: {_resumo(v)}") from e
        if not math.isfinite(vf) or abs(vf) > 1e12:
            raise PranchaInvalida(f"coordenada {k} invalida no lateral: {_resumo(v)}")

    rotacao = viewport.get("rotacao", 0)
    if isinstance(rotacao, bool) or not isinstance(rotacao, int) or rotacao not in (0, 90):
        raise RotacaoInvalida(f"rotacao hostil no lateral: {_resumo(rotacao)}")

    carimbo = prancha.get("carimbo")
    if not isinstance(carimbo, dict):
        raise PranchaInvalida(f"carimbo deve ser dict, recebido {type(carimbo).__name__}")
    for campo in ("projeto", "titulo", "folha", "data"):
        val = carimbo.get(campo, "")
        if not isinstance(val, str) or _contem_controle(val):
            raise PranchaInvalida(f"{campo} no carimbo contem caractere de controle ou nao e str: {_resumo(val)}")

    data_str = carimbo.get("data", "")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data_str):
        raise PranchaInvalida(f"formato de data invalido no carimbo: {_resumo(data_str)}")
    try:
        datetime.strptime(data_str, "%Y-%m-%d")
    except ValueError as e:
        raise PranchaInvalida(f"data fora do calendario real no carimbo: {_resumo(data_str)}") from e

    formato = prancha.get("formato")
    if not isinstance(formato, str) or formato not in FORMATOS:
        raise FormatoInvalido(f"formato desconhecido: {_resumo(formato)}")
    return formato, carimbo, rotacao


def _parse_viewbox(planta_root):
    vb = planta_root.get("viewBox")
    if not vb:
        raise SvgInvalido("svg da planta sem viewBox")
    partes = re.split(r"[,\s]+", vb.strip())
    if len(partes) != 4:
        raise SvgInvalido("viewBox precisa conter 4 numeros")
    try:
        minx, miny, w, h = (_num(p) for p in partes)
    except (ValueError, TypeError, OverflowError) as e:
        raise SvgInvalido(f"viewBox contem valores nao numericos ou invalidos: {e}") from e
    if w <= 0 or h <= 0 or abs(minx) > 1e12 or abs(miny) > 1e12 or w > 1e12 or h > 1e12:
        raise SvgInvalido("largura e altura do viewBox devem ser maiores que zero e finitas")
    return minx, miny, w, h


def _montar_carimbo(root, carimbo, W, H, escala):
    carimbo_elem = ET.SubElement(root, "{http://www.w3.org/2000/svg}g", {"id": "carimbo"})
    ET.SubElement(carimbo_elem, "{http://www.w3.org/2000/svg}rect", {
        "id": "carimbo-caixa", "x": "10", "y": f"{H - 35:g}", "width": f"{W - 20:g}",
        "height": "25", "fill": "none", "stroke": "#000000", "stroke-width": "0.5",
    })
    fs, folga = 4.0, 5.0
    linhas = [
        [carimbo.get("projeto", ""), carimbo.get("data", ""), carimbo.get("folha", "")],
        [carimbo.get("titulo", ""), f"1:{escala:g}"],
    ]
    for line_items, y_base in zip(linhas, [H - 22.0, H - 13.0]):
        x_curr = 15.0
        for val in line_items:
            s_val = str(val)
            txt = ET.SubElement(carimbo_elem, "{http://www.w3.org/2000/svg}text", {
                "x": f"{x_curr:g}", "y": f"{y_base:g}", "font-size": f"{fs:g}",
            })
            txt.text = s_val
            x_curr += 0.6 * fs * len(s_val) + folga


def montar_svg(lateral, identification, vista_guid, planta_svg):
    """Monta SVG 1.1 da prancha com folha, moldura, viewport e carimbo."""
    prancha = _obter_prancha(lateral, identification)
    viewport = _obter_viewport(lateral, identification, vista_guid)
    formato, carimbo, rotacao = _validar_prancha_e_viewport(prancha, viewport, vista_guid)
    W, H = FORMATOS[formato]

    planta_norm = normalizar_planta(planta_svg)
    try:
        planta_root = ET.fromstring(planta_norm)
    except (ET.ParseError, UnicodeError) as e:
        raise SvgInvalido(f"xml da planta malformado: {e}") from e

    minx, miny, w, h = _parse_viewbox(planta_root)

    try:
        x, y, escala = float(viewport["x"]), float(viewport["y"]), float(viewport["escala"])
        s = 1000.0 / escala
        if not math.isfinite(s) or s <= 0:
            raise SvgInvalido("escala do viewport resultou em valor invalido")
        if rotacao == 0:
            vw, vh = w * s, h * s
            tx_vp = x - minx * s
            ty_vp = y - miny * s
            if not (math.isfinite(vw) and math.isfinite(vh) and math.isfinite(tx_vp) and math.isfinite(ty_vp)):
                raise SvgInvalido("transform do viewport resultou em valor nao finito")
            transform_vp = f"translate({tx_vp:.10g}, {ty_vp:.10g}) scale({s:.10g})"
        else:
            vw, vh = h * s, w * s
            tx_vp = x + (h + miny) * s
            ty_vp = y - minx * s
            if not (math.isfinite(vw) and math.isfinite(vh) and math.isfinite(tx_vp) and math.isfinite(ty_vp)):
                raise SvgInvalido("transform do viewport resultou em valor nao finito")
            transform_vp = f"matrix(0 {s:.10g} {-s:.10g} 0 {tx_vp:.10g} {ty_vp:.10g})"
    except OverflowError as e:
        raise SvgInvalido(f"overflow no calculo do viewport: {e}") from e

    tol = 1e-9
    if x < 10.0 - tol or y < 10.0 - tol or (x + vw) > (W - 10.0) + tol or (y + vh) > (H - 35.0) + tol:
        raise ViewportForaDaFolha("viewport fora da area util da prancha")

    root = ET.Element("{http://www.w3.org/2000/svg}svg", {
        "width": f"{W:g}mm", "height": f"{H:g}mm", "viewBox": f"0 0 {W:g} {H:g}"
    })
    ET.SubElement(root, "{http://www.w3.org/2000/svg}rect", {
        "id": "folha", "x": "0", "y": "0", "width": f"{W:g}", "height": f"{H:g}", "fill": "#ffffff"
    })
    ET.SubElement(root, "{http://www.w3.org/2000/svg}rect", {
        "id": "moldura", "x": "10", "y": "10", "width": f"{W - 20:g}", "height": f"{H - 20:g}",
        "fill": "none", "stroke": "#000000", "stroke-width": "0.5"
    })

    vp_elem = ET.SubElement(root, "{http://www.w3.org/2000/svg}g", {
        "id": "viewport", "data-vista": vista_guid, "transform": transform_vp
    })
    for child in planta_root:
        vp_elem.append(child)
    del planta_root

    _montar_carimbo(root, carimbo, W, H, escala)

    try:
        raw = ET.tostring(root, encoding="unicode")
    except RecursionError as e:
        raise SvgInvalido(f"profundidade excessiva ao serializar svg: {e}") from e
    del root

    m = re.search(r'xmlns:(ns\d+)="http://www.w3.org/2000/svg"', raw)
    if m:
        pfx = m.group(1)
        raw = raw.replace(f'xmlns:{pfx}="http://www.w3.org/2000/svg"', 'xmlns="http://www.w3.org/2000/svg"')
        raw = raw.replace(f"<{pfx}:", "<").replace(f"</{pfx}:", "</")

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
    if not isinstance(formato, str) or formato not in FORMATOS:
        raise FormatoInvalido(f"formato desconhecido: {_resumo(formato)}")
    W, H = FORMATOS[formato]

    from PySide6.QtCore import QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance()
    if app is None:
        _QT_APP = app = QGuiApplication([])

    svg_bytes = conteudo.encode("utf-8")
    renderer = QSvgRenderer(svg_bytes)
    if not renderer.isValid():
        raise SvgInvalido("Qt nao conseguiu ler o SVG montado")

    writer = QPdfWriter(str(destino))
    page_size = QPageSize(QSizeF(W, H), QPageSize.Unit.Millimeter)
    writer.setPageSize(page_size)
    writer.setPageLayout(QPageLayout(page_size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))

    painter = QPainter(writer)
    try:
        renderer.render(painter, QRectF(0, 0, writer.width(), writer.height()))
    finally:
        painter.end()
    return destino
