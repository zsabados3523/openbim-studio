# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prancha minima e viewport (F0-S06-T08).
Sem Qt nem ifcopenshell no topo; gravacao no lateral (.obim), SVG e PDF."""
import math
import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET
import xml.parsers.expat
from datetime import datetime
from pathlib import Path

FORMATOS = {
    "A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
    "A1": (841.0, 594.0), "A0": (1189.0, 841.0),
}
MARGEM_MM, CARIMBO_ALTURA_MM = 10.0, 25.0
LINHA_CORTE_MM, LINHA_PROJECAO_MM = 0.35, 0.18
_QT_APP = None
_FORMAS = {"path", "line", "polyline", "polygon", "circle", "ellipse", "rect"}
_IGNORADOS = {"defs", "marker", "clipPath", "mask", "pattern", "symbol", "style", "title", "desc", "metadata", "text"}
_CMD_ARITY = {"Z": 0, "H": 1, "V": 1, "M": 2, "L": 2, "T": 2, "S": 4, "Q": 4, "C": 6, "A": 7}
_CMD_CHARS = set("MmLlHhVvCcSsQqTtAaZz")
_PATH_TOKEN_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?[0-9]*)(?:[eE][-+]?[0-9]+)?)")
_NUM_ASCII_RE = re.compile(r"^[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?[0-9]*)(?:[eE][-+]?[0-9]+)?$")
_NUM_TOKEN_RE = re.compile(r"[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?[0-9]*)(?:[eE][-+]?[0-9]+)?")
_SEP_RE = re.compile(r"[\s,]*")
_TETO_ELEMENTOS = 1_000_000
_TETO_PROFUNDIDADE = 200
_LIMITE_COMANDOS = 5_000_000


def _resumo(valor, limite=80):
    if isinstance(valor, str):
        texto = valor[:limite] + ("..." if len(valor) > limite else "")
        return repr(texto)
    texto = repr(valor)
    return texto if len(texto) <= limite else texto[:limite] + "..."


def _resumo_trecho(texto, ini, fim=None):
    fim_real = len(texto) if fim is None else fim
    tamanho = min(fim_real - ini, 80)
    trecho = texto[ini:ini + tamanho] + ("..." if fim_real - ini > tamanho else "")
    return repr(trecho)


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


def _obter_viewport(lateral, identification, view_guid):
    for uid in lateral.ids("viewports"):
        v = lateral.obter("viewports", uid)
        if not isinstance(v, dict):
            raise PranchaInvalida(f"viewport deve ser dict, recebido {type(v).__name__}")
        if v.get("prancha") == identification and v.get("view_guid") == view_guid:
            return v
    raise PranchaNaoEncontrada(f"viewport nao encontrado para {_resumo(identification)} / {_resumo(view_guid)}")


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


def colocar_viewport(lado, identification, view_guid, x_mm, y_mm, escala, rotacao=0):
    """Cria viewport na colecao 'viewports' do lateral."""
    if isinstance(rotacao, bool) or not isinstance(rotacao, int) or rotacao not in (0, 90):
        raise RotacaoInvalida(f"rotacao invalida: {_resumo(rotacao)}")
    if not isinstance(identification, str) or not identification or identification != identification.strip() or _contem_controle(identification):
        raise PranchaInvalida("identification vazia ou com espaco nas pontas")
    if not isinstance(view_guid, str) or not view_guid or _contem_controle(view_guid):
        raise PranchaInvalida("view_guid vazio ou invalido")
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
    obj = {"prancha": identification, "view_guid": view_guid, "x": x_mm, "y": y_mm, "escala": escala}
    if rotacao == 90:
        obj["rotacao"] = 90
    lado.criar("viewports", uid, obj)
    return uid


def ler_viewport(lateral, identification, view_guid):
    """Le viewport do lateral e devolve {'x', 'y', 'escala'} (e 'rotacao' se 90)."""
    try:
        v = _obter_viewport(lateral, identification, view_guid)
    except KeyError as e:
        raise PranchaInvalida(f"falha ao acessar viewport no lateral: {e}") from e
    try:
        res = {"x": v["x"], "y": v["y"], "escala": v["escala"]}
        if v.get("rotacao") == 90:
            res["rotacao"] = 90
    except KeyError as e:
        raise PranchaInvalida(f"campo obrigatorio {e} ausente no viewport") from e
    return res


def _validar_xml(texto):
    """Le o XML em uma passada linear (expat) antes de montar a arvore."""
    parser = xml.parsers.expat.ParserCreate()
    estado = {"elementos": 0, "profundidade": 0}

    def inicio(name, attrs):
        estado["elementos"] += 1
        if estado["elementos"] > _TETO_ELEMENTOS:
            raise SvgInvalido(f"teto de elementos excedido (>{_TETO_ELEMENTOS})")
        estado["profundidade"] += 1
        if estado["profundidade"] - 1 > _TETO_PROFUNDIDADE:
            raise SvgInvalido(f"profundidade maxima excedida (>{_TETO_PROFUNDIDADE})")

    def fim(name):
        estado["profundidade"] -= 1

    def doctype(name, sysid, pubid, has_internal_subset):
        raise SvgInvalido("doctype ou entity proibido no svg da planta")

    def entidade(*args):
        raise SvgInvalido("doctype ou entity proibido no svg da planta")

    parser.StartElementHandler = inicio
    parser.EndElementHandler = fim
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entidade
    try:
        parser.Parse(texto, True)
    except SvgInvalido:
        raise
    except (xml.parsers.expat.ExpatError, UnicodeError) as e:
        raise SvgInvalido(f"xml da planta malformado: {e}") from e


def _parse_transform(t_str):
    if not t_str or not t_str.strip():
        return (1.0, 1.0, 0.0, 0.0)
    t_str = t_str.strip()
    if len(t_str) > 1000:
        raise SvgInvalido("transform excede limite de tamanho (1000 caracteres)")
    try:
        calls = list(re.finditer(r"([a-zA-Z_][a-zA-Z0-9_-]*)\s*\(([^()]*)\)", t_str))
        if not calls:
            raise SvgInvalido("transform invalido")
        last_end, ops = 0, []
        for m in calls:
            if re.search(r"[^\s,]", t_str[last_end : m.start()]):
                raise SvgInvalido("caracteres invalidos no transform")
            last_end = m.end()
            fn, args_str = m.group(1), m.group(2)
            if fn not in ("translate", "scale"):
                raise SvgInvalido(f"transform {fn} nao suportado")
            num_pat = r"[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?[0-9]*)(?:[eE][-+]?[0-9]+)?"
            if re.search(r"[^\s,]", re.sub(num_pat, "", args_str)):
                raise SvgInvalido("argumentos invalidos no transform")
            args = re.findall(num_pat, args_str)
            if fn == "translate" and len(args) in (1, 2):
                ops.append((1.0, 1.0, _num(args[0]), _num(args[1]) if len(args) == 2 else 0.0))
            elif fn == "scale" and len(args) in (1, 2):
                ops.append((_num(args[0]), _num(args[1]) if len(args) == 2 else _num(args[0]), 0.0, 0.0))
            else:
                raise SvgInvalido(f"numero invalido de argumentos em {fn}")
        if re.search(r"[^\s,]", t_str[last_end:]):
            raise SvgInvalido("caracteres invalidos no transform")
        sx, sy, tx, ty = 1.0, 1.0, 0.0, 0.0
        for op_sx, op_sy, op_tx, op_ty in reversed(ops):
            sx, tx = op_sx * sx, op_sx * tx + op_tx
            sy, ty = op_sy * sy, op_sy * ty + op_ty
            if not (math.isfinite(sx) and math.isfinite(sy) and math.isfinite(tx) and math.isfinite(ty)):
                raise SvgInvalido("transform resultou em valor nao finito")
            if abs(sx) > 1e12 or abs(sy) > 1e12 or abs(tx) > 1e12 or abs(ty) > 1e12:
                raise SvgInvalido("transform resultou em valor excessivo")
        return (sx, sy, tx, ty)
    except (ValueError, OverflowError, TypeError, ZeroDivisionError) as e:
        raise SvgInvalido(f"transform invalido: {e}") from e


def _compose_transforms(parent_tr, child_tr):
    try:
        p_sx, p_sy, p_tx, p_ty = parent_tr
        c_sx, c_sy, c_tx, c_ty = child_tr
        sx, sy = p_sx * c_sx, p_sy * c_sy
        tx, ty = p_sx * c_tx + p_tx, p_sy * c_ty + p_ty
        if not (math.isfinite(sx) and math.isfinite(sy) and math.isfinite(tx) and math.isfinite(ty)):
            raise SvgInvalido("transform composto nao finito")
        if abs(sx) > 1e12 or abs(sy) > 1e12 or abs(tx) > 1e12 or abs(ty) > 1e12:
            raise SvgInvalido("transform composto excessivo")
        return (sx, sy, tx, ty)
    except (ValueError, OverflowError, TypeError, ZeroDivisionError) as e:
        raise SvgInvalido(f"erro ao compor transform: {e}") from e


class _BBox:
    __slots__ = ("min_x", "min_y", "max_x", "max_y", "has_pts")

    def __init__(self):
        self.min_x = float("inf")
        self.min_y = float("inf")
        self.max_x = float("-inf")
        self.max_y = float("-inf")
        self.has_pts = False

    def add(self, x, y):
        if not (math.isfinite(x) and math.isfinite(y)):
            raise SvgInvalido("coordenada calculada nao finita")
        if abs(x) > 1e12 or abs(y) > 1e12:
            raise SvgInvalido("coordenada calculada excessiva")
        if x < self.min_x: self.min_x = x
        if x > self.max_x: self.max_x = x
        if y < self.min_y: self.min_y = y
        if y > self.max_y: self.max_y = y
        self.has_pts = True


def _eval_cubic(p0, p1, p2, p3, t):
    omt = 1.0 - t
    omt2 = omt * omt
    t2 = t * t
    return (omt2 * omt * p0[0] + 3.0 * omt2 * t * p1[0] + 3.0 * omt * t2 * p2[0] + t2 * t * p3[0],
            omt2 * omt * p0[1] + 3.0 * omt2 * t * p1[1] + 3.0 * omt * t2 * p2[1] + t2 * t * p3[1])


def _process_cubic(add_pt, p0, p1, p2, p3):
    add_pt(p0[0], p0[1])
    add_pt(p3[0], p3[1])
    for c in (0, 1):
        v0, v1, v2, v3 = p0[c], p1[c], p2[c], p3[c]
        a = 3.0 * (-v0 + 3.0 * v1 - 3.0 * v2 + v3)
        b = 6.0 * (v0 - 2.0 * v1 + v2)
        k = 3.0 * (v1 - v0)
        if abs(a) > 1e-12:
            disc = b * b - 4.0 * a * k
            if disc >= 0.0:
                sq = math.sqrt(disc)
                t1 = (-b - sq) / (2.0 * a)
                t2 = (-b + sq) / (2.0 * a)
                if 0.0 < t1 < 1.0:
                    add_pt(*_eval_cubic(p0, p1, p2, p3, t1))
                if 0.0 < t2 < 1.0:
                    add_pt(*_eval_cubic(p0, p1, p2, p3, t2))
        elif abs(b) > 1e-12:
            t = -k / b
            if 0.0 < t < 1.0:
                add_pt(*_eval_cubic(p0, p1, p2, p3, t))


def _eval_quad(p0, p1, p2, t):
    omt = 1.0 - t
    return (omt * omt * p0[0] + 2.0 * omt * t * p1[0] + t * t * p2[0],
            omt * omt * p0[1] + 2.0 * omt * t * p1[1] + t * t * p2[1])


def _process_quad(add_pt, p0, p1, p2):
    add_pt(p0[0], p0[1])
    add_pt(p2[0], p2[1])
    for c in (0, 1):
        v0, v1, v2 = p0[c], p1[c], p2[c]
        denom = v0 - 2.0 * v1 + v2
        if abs(denom) > 1e-12:
            t = (v0 - v1) / denom
            if 0.0 < t < 1.0:
                add_pt(*_eval_quad(p0, p1, p2, t))


def _process_arc(add_pt, x0, y0, rx, ry, x_rot, laf, sf, x1, y1):
    add_pt(x0, y0)
    add_pt(x1, y1)
    rx, ry = abs(float(rx)), abs(float(ry))
    if rx > 1e12 or ry > 1e12 or not (math.isfinite(rx) and math.isfinite(ry)):
        raise SvgInvalido("raio enorme ou invalido no arco")
    if rx < 1e-12 or ry < 1e-12 or (x0 == x1 and y0 == y1):
        return
    phi = math.radians(float(x_rot))
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1_p = cos_phi * dx + sin_phi * dy
    y1_p = -sin_phi * dx + cos_phi * dy
    lambda_r = (x1_p * x1_p) / (rx * rx) + (y1_p * y1_p) / (ry * ry)
    if lambda_r > 1.0:
        s_r = math.sqrt(lambda_r)
        rx *= s_r
        ry *= s_r
        if rx > 1e12 or ry > 1e12 or not (math.isfinite(rx) and math.isfinite(ry)):
            raise SvgInvalido("raio ajustado enorme no arco")
    large_arc, sweep = bool(int(laf)), bool(int(sf))
    sign = -1.0 if large_arc == sweep else 1.0
    numer = max(0.0, rx * rx * ry * ry - rx * rx * y1_p * y1_p - ry * ry * x1_p * x1_p)
    denom = rx * rx * y1_p * y1_p + ry * ry * x1_p * x1_p
    factor = sign * math.sqrt(numer / denom) if denom != 0.0 else 0.0
    cx_p = factor * (rx * y1_p / ry)
    cy_p = factor * (-ry * x1_p / rx)
    cx = cos_phi * cx_p - sin_phi * cy_p + (x0 + x1) / 2.0
    cy = sin_phi * cx_p + cos_phi * cy_p + (y0 + y1) / 2.0

    def vec_angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
        if lu == 0.0 or lv == 0.0:
            return 0.0
        val = max(-1.0, min(1.0, dot / (lu * lv)))
        a = math.acos(val)
        return -a if ux * vy - uy * vx < 0.0 else a

    theta1 = vec_angle(1.0, 0.0, (x1_p - cx_p) / rx, (y1_p - cy_p) / ry)
    dtheta = vec_angle((x1_p - cx_p) / rx, (y1_p - cy_p) / ry, (-x1_p - cx_p) / rx, (-y1_p - cy_p) / ry) % (2.0 * math.pi)
    if not sweep and dtheta > 0.0:
        dtheta -= 2.0 * math.pi
    elif sweep and dtheta < 0.0:
        dtheta += 2.0 * math.pi

    def pt_at(t):
        return (cx + rx * cos_phi * math.cos(t) - ry * sin_phi * math.sin(t),
                cy + rx * sin_phi * math.cos(t) + ry * cos_phi * math.sin(t))

    a1 = math.atan2(-ry * sin_phi, rx * cos_phi)
    a2 = math.atan2(ry * cos_phi, rx * sin_phi)
    candidates = (a1, a1 + math.pi, a2, a2 + math.pi, 0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi)

    for t_cand in candidates:
        if sweep:
            diff = (t_cand - theta1) % (2.0 * math.pi)
            if diff <= dtheta + 1e-9:
                add_pt(*pt_at(theta1 + diff))
        else:
            diff = (theta1 - t_cand) % (2.0 * math.pi)
            if diff <= abs(dtheta) + 1e-9:
                add_pt(*pt_at(theta1 - diff))


def _parse_path(d, add_pt, cmd_counter):
    if not d or not d.strip():
        raise SvgInvalido("path vazio")
    last_end = 0

    def gen():
        nonlocal last_end
        for m in _PATH_TOKEN_RE.finditer(d):
            st = m.start()
            if st > last_end and d[last_end:st].strip(" \t\r\n,"):
                raise SvgInvalido(f"caractere invalido no path: {_resumo_trecho(d, last_end, st)}")
            last_end = m.end()
            yield m.group(1)
        if d[last_end:].strip(" \t\r\n,"):
            raise SvgInvalido(f"caractere invalido no fim do path: {_resumo_trecho(d, last_end)}")

    it = gen()
    first = next(it, None)
    if first is None or first not in ("M", "m"):
        raise SvgInvalido("path deve comecar com M/m")

    next_tok = first
    last_cmd = None
    curr_x = curr_y = start_x = start_y = 0.0
    last_ctrl = None

    while next_tok is not None:
        if next_tok in _CMD_CHARS:
            cmd = next_tok
            next_tok = next(it, None)
        else:
            if last_cmd is None or last_cmd in "Zz":
                raise SvgInvalido("numero solto apos Z/z ou sem comando")
            cmd = "l" if last_cmd == "m" else ("L" if last_cmd == "M" else last_cmd)

        u = cmd.upper()
        need = _CMD_ARITY[u]
        cmd_counter[0] += 1
        if cmd_counter[0] > _LIMITE_COMANDOS:
            raise SvgInvalido("limite de comandos excedido (> 5 milhoes)")

        is_rel = cmd.islower()
        if u == "Z":
            curr_x, curr_y = start_x, start_y
            add_pt(curr_x, curr_y)
            last_ctrl = None
            last_cmd = cmd
            continue

        raw = [0.0] * need
        for k in range(need):
            if next_tok is None:
                raise SvgInvalido("faltam argumentos para comando no path")
            if next_tok in _CMD_CHARS:
                raise SvgInvalido("comando no lugar de numero")
            if u == "A" and k in (3, 4) and next_tok not in ("0", "1"):
                raise SvgInvalido("flags de arco devem ser 0 ou 1")
            try:
                val = float(next_tok)
            except (ValueError, OverflowError) as e:
                raise SvgInvalido(f"numero invalido no path: {_resumo(next_tok)}") from e
            if not math.isfinite(val) or abs(val) > 1e12:
                raise SvgInvalido("numero nao finito ou excessivo no path")
            if u == "A" and k in (0, 1) and val < 0:
                raise SvgInvalido("raio negativo no arco")
            raw[k] = val
            next_tok = next(it, None)

        if u == "H":
            curr_x = curr_x + raw[0] if is_rel else raw[0]
            add_pt(curr_x, curr_y)
            last_ctrl = None
        elif u == "V":
            curr_y = curr_y + raw[0] if is_rel else raw[0]
            add_pt(curr_x, curr_y)
            last_ctrl = None
        elif u in ("M", "L"):
            curr_x = curr_x + raw[0] if is_rel else raw[0]
            curr_y = curr_y + raw[1] if is_rel else raw[1]
            if u == "M":
                start_x, start_y = curr_x, curr_y
            add_pt(curr_x, curr_y)
            last_ctrl = None
        elif u == "A":
            rx, ry, rot, laf, sf, x1, y1 = raw
            if is_rel:
                x1 += curr_x
                y1 += curr_y
            _process_arc(add_pt, curr_x, curr_y, rx, ry, rot, laf, sf, x1, y1)
            curr_x, curr_y = x1, y1
            last_ctrl = None
        elif u in ("C", "S"):
            if u == "C":
                args = [v + (curr_x if i % 2 == 0 else curr_y) for i, v in enumerate(raw)] if is_rel else raw
                p1 = (args[0], args[1])
                p2 = (args[2], args[3])
                p3 = (args[4], args[5])
            else:
                args = [v + (curr_x if i % 2 == 0 else curr_y) for i, v in enumerate(raw)] if is_rel else raw
                p1 = (2.0 * curr_x - last_ctrl[0], 2.0 * curr_y - last_ctrl[1]) if (last_cmd in "CcSs" and last_ctrl is not None) else (curr_x, curr_y)
                p2 = (args[0], args[1])
                p3 = (args[2], args[3])
            _process_cubic(add_pt, (curr_x, curr_y), p1, p2, p3)
            curr_x, curr_y = p3
            last_ctrl = p2
        elif u in ("Q", "T"):
            if u == "Q":
                args = [v + (curr_x if i % 2 == 0 else curr_y) for i, v in enumerate(raw)] if is_rel else raw
                p1 = (args[0], args[1])
                p2 = (args[2], args[3])
            else:
                args = [v + (curr_x if i % 2 == 0 else curr_y) for i, v in enumerate(raw)] if is_rel else raw
                p1 = (2.0 * curr_x - last_ctrl[0], 2.0 * curr_y - last_ctrl[1]) if (last_cmd in "QqTt" and last_ctrl is not None) else (curr_x, curr_y)
                p2 = (args[0], args[1])
            _process_quad(add_pt, (curr_x, curr_y), p1, p2)
            curr_x, curr_y = p2
            last_ctrl = p1
        last_cmd = cmd


def _process_elem_bbox(elem, tag, tr, bbox, cmd_counter):
    sx, sy, tx, ty = tr
    def add_pt(px, py):
        bbox.add(sx * px + tx, sy * py + ty)

    if tag == "rect":
        x, y = _num(elem.get("x", "0")), _num(elem.get("y", "0"))
        w, h = _num(elem.get("width", "0")), _num(elem.get("height", "0"))
        if w < 0 or h < 0:
            raise SvgInvalido("rect negativo")
        add_pt(x, y)
        add_pt(x + w, y)
        add_pt(x + w, y + h)
        add_pt(x, y + h)
    elif tag in ("circle", "ellipse"):
        cx, cy = _num(elem.get("cx", "0")), _num(elem.get("cy", "0"))
        rx = _raio(elem.get("r" if tag == "circle" else "rx", "0"))
        ry = rx if tag == "circle" else _raio(elem.get("ry", "0"))
        add_pt(cx - rx, cy)
        add_pt(cx + rx, cy)
        add_pt(cx, cy - ry)
        add_pt(cx, cy + ry)
    elif tag == "line":
        add_pt(_num(elem.get("x1", "0")), _num(elem.get("y1", "0")))
        add_pt(_num(elem.get("x2", "0")), _num(elem.get("y2", "0")))
    elif tag in ("polyline", "polygon"):
        pts_str = elem.get("points", "").strip()
        if not pts_str:
            raise SvgInvalido("points vazio")
        last_end = 0
        pendente = None
        pontos = 0
        for m in _NUM_TOKEN_RE.finditer(pts_str):
            if not _SEP_RE.fullmatch(pts_str, last_end, m.start()):
                raise SvgInvalido("caracteres invalidos em points")
            last_end = m.end()
            cmd_counter[0] += 1
            if cmd_counter[0] > _LIMITE_COMANDOS:
                raise SvgInvalido("limite de comandos excedido (> 5 milhoes)")
            try:
                valor = float(m.group(0))
            except (ValueError, OverflowError) as e:
                raise SvgInvalido("numero invalido em points") from e
            if not math.isfinite(valor) or abs(valor) > 1e12:
                raise SvgInvalido("numero nao finito ou excessivo em points")
            if pendente is None:
                pendente = valor
            else:
                add_pt(pendente, valor)
                pendente = None
                pontos += 1
        if not _SEP_RE.fullmatch(pts_str, last_end):
            raise SvgInvalido("caracteres invalidos em points")
        if not pontos or pendente is not None:
            raise SvgInvalido("quantidade impar de pontos em polyline/polygon")
    elif tag == "path":
        _parse_path(elem.get("d", ""), add_pt, cmd_counter)


def _localizar_tag_raiz(svg_str):
    pos = 0
    n = len(svg_str)
    while pos < n:
        while pos < n and svg_str[pos] in " \t\r\n":
            pos += 1
        if pos >= n:
            break
        if svg_str.startswith("<!--", pos):
            fim = svg_str.find("-->", pos + 4)
            if fim == -1:
                raise SvgInvalido("comentario nao fechado antes da raiz")
            pos = fim + 3
            continue
        if svg_str.startswith("<?", pos):
            fim = svg_str.find("?>", pos + 2)
            if fim == -1:
                raise SvgInvalido("instrucao de processamento ou declaracao xml nao fechada antes da raiz")
            pos = fim + 2
            continue
        if svg_str.startswith("<![CDATA[", pos):
            fim = svg_str.find("]]>", pos + 9)
            if fim == -1:
                raise SvgInvalido("cdata nao fechado antes da raiz")
            pos = fim + 3
            continue
        if svg_str.startswith("<!DOCTYPE", pos) or svg_str.startswith("<!doctype", pos):
            idx = pos + 9
            depth = 0
            quote = None
            while idx < n:
                ch = svg_str[idx]
                if quote is not None:
                    if ch == quote:
                        quote = None
                elif ch in ('"', "'"):
                    quote = ch
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth = max(0, depth - 1)
                elif ch == ">" and depth == 0:
                    pos = idx + 1
                    break
                idx += 1
            else:
                raise SvgInvalido("doctype nao fechado antes da raiz")
            continue
        if svg_str[pos] == "<":
            m = re.match(r"<([a-zA-Z_][a-zA-Z0-9_.-]*:)?svg(?=[\s/>])", svg_str[pos:])
            if m:
                return pos + m.end()
            raise SvgInvalido("tag raiz <svg> nao encontrada")
        raise SvgInvalido(f"caractere inesperado antes da raiz: {_resumo(svg_str[pos])}")
    raise SvgInvalido("tag raiz <svg> nao encontrada")


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
    _validar_xml(svg_str)
    try:
        root = ET.fromstring(svg_str)
    except (ET.ParseError, UnicodeError) as e:
        raise SvgInvalido(f"xml da planta malformado: {e}") from e
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise SvgInvalido("raiz do svg da planta nao e <svg> com namespace")

    if root.get("viewBox") is not None:
        return svg_str

    bbox = _BBox()
    cmd_counter = [0]
    stack = [(iter([root]), (1.0, 1.0, 0.0, 0.0))]
    while stack:
        it, tr = stack[-1]
        try:
            elem = next(it)
        except StopIteration:
            stack.pop()
            continue
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag in _IGNORADOS:
            continue
        total_tr = _compose_transforms(tr, _parse_transform(elem.get("transform", "")))
        _process_elem_bbox(elem, tag, total_tr, bbox, cmd_counter)
        stack.append((iter(elem), total_tr))

    if not bbox.has_pts:
        raise SvgInvalido("sem nenhum elemento desenhavel")

    minx = bbox.min_x - margem_m
    miny = bbox.min_y - margem_m
    w = (bbox.max_x - bbox.min_x) + 2.0 * margem_m
    h = (bbox.max_y - bbox.min_y) + 2.0 * margem_m
    if w <= 0 or h <= 0 or not (math.isfinite(minx) and math.isfinite(miny) and math.isfinite(w) and math.isfinite(h)):
        raise SvgInvalido("largura ou altura final <= 0")

    idx = _localizar_tag_raiz(svg_str)
    return svg_str[:idx] + f' viewBox="{minx:.10g} {miny:.10g} {w:.10g} {h:.10g}"' + svg_str[idx:]


def _calcular_corte_node(elem, estado_pai):
    cls_str = elem.get("class", "")
    if not cls_str:
        return estado_pai
    classes = cls_str.split()
    if "projection" in classes:
        return False
    if "cut" in classes or any(c.startswith("Ifc") and c not in ("IfcBuildingStorey", "IfcBuilding", "IfcSite", "IfcProject") for c in classes):
        return True
    return estado_pai


def _ajustar_style_text(text, largura_corte, largura_proj):
    if not text or "{" not in text:
        return text
    if len(text) > 2_000_000:
        raise SvgInvalido("elemento style excede tamanho maximo")
    out = []
    idx = 0
    n = len(text)
    while idx < n:
        open_brace = text.find("{", idx)
        if open_brace == -1:
            out.append(text[idx:])
            break
        close_brace = text.find("}", open_brace + 1)
        if close_brace == -1:
            out.append(text[idx:])
            break
        sel = text[idx:open_brace]
        corpo = text[open_brace + 1:close_brace]
        last_open = sel.rfind("{")
        if last_open != -1:
            out.append(sel[:last_open])
            sel = sel[last_open:]
        toks = re.findall(r"[a-zA-Z0-9_-]+", sel)
        is_corte = False if "projection" in toks else ("cut" in toks or any(t.startswith("Ifc") and t not in ("IfcBuildingStorey", "IfcBuilding", "IfcSite", "IfcProject") for t in toks))
        larg = largura_corte if is_corte else largura_proj
        novo_corpo = re.sub(r'stroke-width\s*:\s*[^;]+', f'stroke-width:{larg:.6g}', corpo)
        out.append(f"{sel}{{{novo_corpo}}}")
        idx = close_brace + 1
    return "".join(out)


def _ajustar_espessuras(planta_root, escala):
    largura_corte = LINHA_CORTE_MM * escala / 1000.0
    largura_proj = LINHA_PROJECAO_MM * escala / 1000.0
    pat = r"stroke-width\s*:[^;]+"

    stack = [(iter([planta_root]), False)]
    while stack:
        it, estado_pai = stack[-1]
        try:
            no = next(it)
        except StopIteration:
            stack.pop()
            continue
        tag = no.tag.split("}")[-1] if "}" in no.tag else no.tag
        estado_atual = _calcular_corte_node(no, estado_pai)
        if tag == "style" and no.text:
            no.text = _ajustar_style_text(no.text, largura_corte, largura_proj)
        if tag in _IGNORADOS:
            continue
        if tag in _FORMAS:
            largura = largura_corte if estado_atual else largura_proj
            if "stroke-width" in no.attrib:
                no.set("stroke-width", f"{largura:.6g}")
            st = no.get("style", "")
            if st:
                no.set("style", re.sub(pat, f"stroke-width:{largura:.6g}", st) if re.search(pat, st) else st.rstrip(";") + f";stroke-width:{largura:.6g}")
            else:
                no.set("style", f"stroke-width:{largura:.6g}")
        stack.append((iter(no), estado_atual))


def _validar_prancha_e_viewport(prancha, viewport, view_guid):
    if not isinstance(prancha, dict) or not isinstance(viewport, dict):
        raise PranchaInvalida("prancha ou viewport invalido")
    if not isinstance(view_guid, str) or _contem_controle(view_guid):
        raise PranchaInvalida(f"view_guid contem caractere de controle ou invalido: {_resumo(view_guid)}")

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


def montar_svg(lateral, identification, view_guid, planta_svg):
    """Monta SVG 1.1 da prancha com folha, moldura, viewport e carimbo."""
    prancha = _obter_prancha(lateral, identification)
    viewport = _obter_viewport(lateral, identification, view_guid)
    formato, carimbo, rotacao = _validar_prancha_e_viewport(prancha, viewport, view_guid)
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

    _ajustar_espessuras(planta_root, escala)

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
        "id": "viewport", "data-vista": view_guid, "transform": transform_vp
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


def exportar_svg(lateral, identification, view_guid, planta_svg, destino):
    """Exporta prancha como arquivo SVG em UTF-8."""
    destino = Path(destino)
    conteudo = montar_svg(lateral, identification, view_guid, planta_svg)
    destino.write_bytes(conteudo.encode("utf-8"))
    return destino


def exportar_pdf(lateral, identification, view_guid, planta_svg, destino):
    """Exporta prancha como PDF de 1 pagina do tamanho da folha."""
    global _QT_APP
    destino = Path(destino)
    conteudo = montar_svg(lateral, identification, view_guid, planta_svg)
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
