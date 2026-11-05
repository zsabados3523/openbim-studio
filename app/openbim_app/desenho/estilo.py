# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estilo de desenho 2D: espessuras, hachura e enquadramento em SVG.

Limite conhecido: aspas simples nos atributos e comentários XML não
são suportados nem testados (o SVG vem sempre do motor de corte/planta).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

CUT_LINE_WIDTH_MM = 0.5
PROJECTION_LINE_WIDTH_MM = 0.25
_NUMBER_PATTERN = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_POINT_PATTERN = re.compile(r"(%s),(%s)" % (_NUMBER_PATTERN, _NUMBER_PATTERN))
_D_PATTERN = re.compile(r"(?:M\s*P(?:\s+L\s*P|\s+(?=L)L\s*P)*\s*)+".replace("P", r"%s,%s" % (_NUMBER_PATTERN, _NUMBER_PATTERN)))
_SVG_ROOT_PATTERN = re.compile(r"<svg\b[^>]*>")
_LEAF_GROUP_PATTERN = re.compile(r'(<g\b[^>]*\bifc:guid="[^"]*"[^>]*>)(\s*<path\b)')


class EstiloInvalido(ValueError):
    """Erro de entrada SVG, escala ou margem invalida."""


def _parse_scale(scale: str | int | float) -> float:
    if isinstance(scale, bool):
        raise EstiloInvalido("Escala nao pode ser booleano")
    if isinstance(scale, str):
        match = re.fullmatch(r"1:(%s)" % _NUMBER_PATTERN, scale)
        if not match:
            raise EstiloInvalido(f"Escala em formato invalido: {scale!r}")
        denom = float(match.group(1))
    elif isinstance(scale, (int, float)):
        denom = float(scale)
    else:
        raise EstiloInvalido(f"Tipo de escala invalido: {type(scale).__name__}")
    if not math.isfinite(denom) or denom <= 0:
        raise EstiloInvalido(f"Denominador de escala deve ser finito e positivo: {scale!r}")
    return denom


def _format_coord(val: float) -> str:
    if not math.isfinite(val):
        raise EstiloInvalido("Valor nao finito no desenho")
    out = f"{round(float(val), 6) + 0.0:.6f}".rstrip("0").rstrip(".")
    return out or "0"


def _add_cut_class(match: re.Match[str]) -> str:
    opening_tag = match.group(1)
    class_attr = re.search(r'\bclass="([^"]*)"', opening_tag)
    if class_attr:
        if "cut" in class_attr.group(1).split():
            return match.group(0)
        opening_tag = opening_tag.replace(
            class_attr.group(0),
            f'class="{class_attr.group(1).strip()} cut"',
            1,
        )
    else:
        opening_tag = opening_tag[:-1] + ' class="cut">'
    return opening_tag + match.group(2)


def aplicar_estilo(svg: str, escala: str | int | float = "1:100", *, margem_m: float = 0.1) -> str:
    """Aplica regras graficas, envoltorio e dimensoes em mm ao SVG bruto.

    Nota: limite conhecido, aspas simples e comentarios XML nao suportados
    (SVG vem sempre do motor).
    """
    if not isinstance(svg, str):
        raise EstiloInvalido("SVG deve ser string")
    scale_denom = _parse_scale(escala)
    if (
        isinstance(margem_m, bool)
        or not isinstance(margem_m, (int, float))
        or not math.isfinite(margem_m)
        or margem_m < 0
    ):
        raise EstiloInvalido(f"Margem invalida: {margem_m!r}")

    try:
        root = ET.fromstring(svg)
    except ET.ParseError as err:
        raise EstiloInvalido(f"XML malformado: {err}") from err

    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise EstiloInvalido("Raiz deve ser elemento svg")

    xs: list[float] = []
    ys: list[float] = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] != "path":
            continue
        d = elem.get("d") or ""
        if not _D_PATTERN.fullmatch(d.strip()):
            raise EstiloInvalido(f"Caminho invalido: {d!r}")
        for x_str, y_str in _POINT_PATTERN.findall(d):
            x = float(x_str)
            y = float(y_str)
            if not math.isfinite(x) or not math.isfinite(y):
                raise EstiloInvalido("Ponto nao finito")
            xs.append(x)
            ys.append(y)

    if not xs:
        raise EstiloInvalido("SVG sem caminhos validos")

    margin = float(margem_m)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    box_x = min_x - margin
    box_y = min_y - margin
    box_w = (max_x - min_x) + 2 * margin
    box_h = (max_y - min_y) + 2 * margin

    root_match = _SVG_ROOT_PATTERN.search(svg)
    if not root_match:
        raise EstiloInvalido("Tag svg nao encontrada")

    raw_header = root_match.group(0)
    cleaned_header = re.sub(r'\s+(?:viewBox|width|height)="[^"]*"', "", raw_header)
    new_header = (
        cleaned_header[:-1].rstrip("/")
        + f' viewBox="{_format_coord(box_x)} {_format_coord(box_y)} {_format_coord(box_w)} {_format_coord(box_h)}"'
        + f' width="{_format_coord(box_w * 1000 / scale_denom)}mm"'
        + f' height="{_format_coord(box_h * 1000 / scale_denom)}mm">'
    )

    cut_width = _format_coord(CUT_LINE_WIDTH_MM * scale_denom / 1000)
    proj_width = _format_coord(PROJECTION_LINE_WIDTH_MM * scale_denom / 1000)
    css = (
        '\n<style type="text/css">\n'
        f'.cut path {{ stroke: #000000; stroke-width: {cut_width}; fill: #333333; fill-rule: evenodd; }}\n'
        f'.projection path {{ stroke: #222222; stroke-width: {proj_width}; fill: none; }}\n'
        '</style>'
    )

    body = svg[root_match.end():]
    body = re.sub(r"\s*<style\b[^>]*/>|\s*<style\b[^>]*?(?<!/)>.*?</style>", "", body, flags=re.S)
    body = _LEAF_GROUP_PATTERN.sub(_add_cut_class, body)

    return svg[:root_match.start()] + new_header + css + body
