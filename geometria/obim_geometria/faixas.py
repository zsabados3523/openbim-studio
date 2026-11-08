# SPDX-License-Identifier: AGPL-3.0-or-later
"""Planejamento e montagem do corte em faixas paralelas (F0-S06-T15o).

Funções puras sobre itens `(id, guid, u0, u1)`, onde u é a horizontal da tela em
metros. O dono da faixa é definido pelo centro do item: a <= centro < b.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import re
import threading
import time

TOL = 1e-6


class FaixasInvalidas(ValueError):
    """Pedido de faixas inválido (n ou SVGs incompatíveis)."""


def _validar_n(n) -> int:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise FaixasInvalidas(f"número de faixas inválido: {n!r}")
    return n


def limites(itens, n, *, so_primeira=()) -> list[tuple[float | None, float | None]]:
    """Faixas contíguas da esquerda para a direita; só as bordas internas são cortes."""
    n = _validar_n(n)
    primeira = set(so_primeira)
    centros = sorted({
        (float(it[2]) + float(it[3])) / 2.0 for it in itens if it[0] not in primeira
    })
    if len(centros) < 2 or n == 1:
        return [(None, None)]
    m = len(centros)
    posicoes = sorted({
        idx for k in range(1, n)
        if 1 <= (idx := round(k * m / n)) <= m - 1
    })
    bordas = [None] + [(centros[i - 1] + centros[i]) / 2.0 for i in posicoes] + [None]
    return list(zip(bordas, bordas[1:]))


def dividir(itens, n, *, so_primeira=()) -> list[list[list]]:
    """Itens que encostam em cada faixa (fechado, com halo); `so_primeira` só na faixa 0."""
    n = _validar_n(n)
    if not itens:
        return []
    primeira = set(so_primeira)
    faixas = []
    for k, (a, b) in enumerate(limites(itens, n, so_primeira=primeira)):
        itens_faixa = []
        for it in itens:
            i, guid, u0, u1 = it[0], it[1], float(it[2]), float(it[3])
            if i in primeira:
                if k == 0:
                    itens_faixa.append([i, guid])
            elif (b is None or u0 <= b + TOL) and (a is None or u1 >= a - TOL):
                itens_faixa.append([i, guid])
        faixas.append(itens_faixa)
    return faixas


_ROOT = re.compile(r"<svg\b[^>]*>", re.S | re.I)
_VIEWBOX = re.compile(r"\bviewBox\s*=\s*[\"']([^\"']*)[\"']", re.I)
_PROJ = re.compile(r"<g\b[^>]*\bclass=[\"']projection[\"'][^>]*>(.*?)</g>", re.S)
_PATH = re.compile(r"<path\b[^>]*>", re.S)
_GTAG = re.compile(r"<g\b[^>]*>|</g>", re.S | re.I)


def _viewbox(svg: str) -> tuple[float, ...]:
    raiz = _ROOT.search(svg)
    vb = _VIEWBOX.search(raiz.group(0)) if raiz else None
    if vb is None:
        raise FaixasInvalidas("SVG sem raiz ou sem viewBox")
    try:
        return tuple(float(v) for v in vb.group(1).split())
    except ValueError as e:
        raise FaixasInvalidas(f"viewBox inválido: {vb.group(1)!r}") from e


def _grupos(svg: str, aceitar) -> list[tuple[int, int, str]]:
    """Grupos <g> aceitos em qualquer nível, como (início, fim, texto), sem aninhar."""
    achados, profundidade, inicio, nivel = [], 0, None, 0
    for m in _GTAG.finditer(svg):
        tag = m.group(0)
        if tag.startswith("</"):
            if profundidade:
                profundidade -= 1
                if inicio is not None and profundidade == nivel:
                    achados.append((inicio, m.end(), svg[inicio:m.end()]))
                    inicio = None
        elif tag.rstrip().endswith("/>"):
            if inicio is None and aceitar(tag):
                achados.append((m.start(), m.end(), tag))
        else:
            if inicio is None and aceitar(tag):
                inicio, nivel = m.start(), profundidade
            profundidade += 1
    return achados


def _produto(tag: str) -> bool:
    return bool(re.search(r'\bid\s*=\s*["\']product-', tag))


def _caixa(tag: str) -> bool:
    return bool(re.search(
        r'\bclass\s*=\s*["\']Ifc(?:Furniture|FurnishingElement|SystemFurnitureElement)["\']',
        tag,
    ))


def unir(svgs) -> str:
    """Une SVGs já recortados: cabeçalho do primeiro, uma projeção, grupos e caixas de todos."""
    svgs = list(svgs)
    if not svgs:
        raise FaixasInvalidas("nenhum SVG para unir")
    if len(svgs) == 1:
        _viewbox(svgs[0])
        return svgs[0]
    vb = _viewbox(svgs[0])
    for svg in svgs[1:]:
        if _viewbox(svg) != vb:
            raise FaixasInvalidas("viewBox incompatível entre as faixas")

    caminhos = []
    grupos, caixas = [], []
    for svg in svgs:
        proj = _PROJ.search(svg)
        if proj is None:
            raise FaixasInvalidas("SVG sem grupo de projeção")
        caminhos.extend(_PATH.findall(proj.group(1)))
    for svg in svgs[1:]:
        prod = _grupos(svg, _produto)
        box = _grupos(svg, _caixa)
        grupos.extend(t for _, _, t in prod)
        caixas.extend(t for _, _, t in box)

    proj = _PROJ.search(svgs[0])
    unido = svgs[0][:proj.start(1)] + "\n" + "\n".join(caminhos) + "\n" + svgs[0][proj.end(1):]
    secao = re.search(r"<g\b[^>]*\bclass=[\"']section[\"'][^>]*>", unido)
    if secao is not None and grupos:
        unido = unido[:secao.end()] + "\n" + "".join(grupos) + unido[secao.end():]
    if caixas:
        unido = unido.replace("</svg>", "".join(caixas) + "</svg>", 1)
    return unido


def _erro(tipo: str, mensagem: str) -> dict:
    return {"ok": False, "erro": {"tipo": tipo, "mensagem": f"faixa: {mensagem}", "rastro": ""}}


_SPAWN = threading.Lock()


def rodar_filho(pedido: dict) -> dict:
    """Roda `obim_geometria.processo.entrada` num processo spawn; nunca levanta."""
    from obim_geometria.processo import entrada

    limite_s = float(os.environ.get("OBIM_FAIXAS_LIMITE_S", "300"))
    ctx = multiprocessing.get_context("spawn")
    rx, tx = ctx.Pipe(duplex=False)
    proc, resposta, fase = None, None, ""
    try:
        proc = ctx.Process(target=entrada, args=(tx, json.dumps(pedido)), daemon=True)
        atual = multiprocessing.current_process()
        antigo_daemon = atual.daemon
        with _SPAWN:
            if antigo_daemon:
                atual.daemon = False
            try:
                proc.start()
            finally:
                atual.daemon = antigo_daemon
        tx.close()
        inicio = time.monotonic()
        while resposta is None:
            if time.monotonic() - inicio > limite_s:
                return _erro("AuxiliarEstourouTempo", f"filho excedeu {limite_s:g} s (fase '{fase}')")
            if rx.poll(0.05):
                try:
                    bruto = rx.recv_bytes()
                except (EOFError, OSError):
                    break
                try:
                    msg = json.loads(bruto.decode("utf-8"))
                except Exception as e:
                    return _erro("ProtocoloInvalido", f"resposta não é JSON: {e}")
                if not isinstance(msg, dict):
                    return _erro("ProtocoloInvalido", "resposta não é um dicionário")
                if msg.get("tipo") == "fase":
                    fase = msg.get("fase", fase)
                elif msg.get("tipo") == "resposta":
                    resposta = msg.get("dados")
            elif not proc.is_alive():
                while rx.poll(0.01):
                    try:
                        bruto = rx.recv_bytes()
                    except (EOFError, OSError):
                        break
                    try:
                        msg = json.loads(bruto.decode("utf-8"))
                    except Exception as e:
                        return _erro("ProtocoloInvalido", f"resposta não é JSON: {e}")
                    if not isinstance(msg, dict):
                        return _erro("ProtocoloInvalido", "resposta não é um dicionário")
                    if msg.get("tipo") == "fase":
                        fase = msg.get("fase", fase)
                    elif msg.get("tipo") == "resposta":
                        resposta = msg.get("dados")
                        break
                break
        if isinstance(resposta, dict):
            return resposta
        return _erro("AuxiliarCaiu", f"filho saiu sem resposta (código {getattr(proc, 'exitcode', None)}, fase '{fase}')")
    except Exception as e:
        return _erro(type(e).__name__, str(e))
    finally:
        for c in (rx, tx):
            try:
                c.close()
            except Exception:
                pass
        if proc is not None:
            try:
                if proc.is_alive():
                    proc.kill()
                proc.join(timeout=5.0)
            except Exception:
                pass
