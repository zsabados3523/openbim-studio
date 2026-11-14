# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refino de peça pesada: pedido de uma peça, extração e mescla do grupo exato no SVG."""
import copy
import re

_G_TAG = re.compile(r"<g\b[^>]*>|</g>", re.S | re.I)
_GUID = re.compile(r"\bifc:guid\s*=\s*[\"']([^\"']*)[\"']", re.I)
_SILHUETA = re.compile(r"\bdata-silhueta\s*=", re.I)


def _grupos(svg: str) -> list[tuple[int, int, str]]:
    """Grupos <g> completos em qualquer nível, como (início, fim, tag de abertura), sem aninhar."""
    achados, pilha = [], []
    for m in _G_TAG.finditer(svg):
        tag = m.group(0)
        if tag.startswith("</"):
            if pilha:
                inicio, abre = pilha.pop()
                achados.append((inicio, m.end(), abre))
        elif tag.rstrip().endswith("/>"):
            achados.append((m.start(), m.end(), tag))
        else:
            pilha.append((m.start(), tag))
    return achados


def _guid(tag: str) -> str | None:
    m = _GUID.search(tag)
    return m.group(1) if m else None


def pedido_peca(pedido: dict, id_step) -> dict:
    """Cópia do pedido restrita a uma peça: só ela em `elementos`, sem faixas/pesados e um thread."""
    q = copy.deepcopy(pedido)
    peca = next((e for e in q.get("elementos") or () if e[0] == id_step), None)
    if peca is None:
        raise KeyError(f"peça {id_step!r} ausente do pedido")
    q["elementos"] = [peca]
    caixas = q.get("caixas_coords")
    if isinstance(caixas, dict):
        filtradas = {}
        for k, v in caixas.items():
            try:
                if int(k) == int(id_step):
                    filtradas[k] = v
            except (TypeError, ValueError):
                continue
        q["caixas_coords"] = filtradas
    for chave in ("faixas", "pesados", "limiar_pesado"):
        q.pop(chave, None)
    q["threads"] = 1
    return q


def extrair_grupo(svg: str, guid: str) -> str | None:
    """Primeiro grupo do `guid` que não é silhueta, completo; None se não houver."""
    for inicio, fim, tag in sorted(_grupos(svg)):
        if _guid(tag) == guid and not _SILHUETA.search(tag):
            return svg[inicio:fim]
    return None


def mesclar_pesado(svg: str, guid: str, grupo_exato: str) -> str:
    """Troca o grupo `data-silhueta` do `guid` pelo exato, mantendo a ordem dos demais."""
    alvos = sorted(a for a in _grupos(svg) if _guid(a[2]) == guid and _SILHUETA.search(a[2]))
    if not alvos:
        return svg
    partes, pos = [], 0
    for i, (inicio, fim, _tag) in enumerate(alvos):
        partes.append(svg[pos:inicio])
        if i == 0:
            partes.append(grupo_exato)
        pos = fim
    partes.append(svg[pos:])
    return "".join(partes)


def _motivo_queda(resp) -> str:
    if not isinstance(resp, dict):
        return "resposta inválida do executor"
    if resp.get("elegivel") is False and resp.get("motivo"):
        return str(resp["motivo"])
    if not resp.get("ok"):
        erro = resp.get("erro")
        msg = erro.get("mensagem") if isinstance(erro, dict) else erro
        return str(msg or resp.get("motivo") or "falha no motor de visibilidade")
    return "grupo ausente na resposta"


def refinar_peca(pedido: dict, id_step, executor=None, limite_s: float = 3600.0, motor: str = "auto") -> dict:
    """Roda a peça sozinha (exata) e devolve o grupo dela; nunca levanta."""
    tempos = {}
    motivo_hlr = None

    def _com_motor(d: dict) -> dict:
        d["motor"] = "hlr"
        if motivo_hlr is not None:
            d["motivo_hlr"] = motivo_hlr
        return d

    try:
        if motor not in ("auto", "hlr"):
            raise ValueError(f"motor inválido: {motor!r}")
        q = pedido_peca(pedido, id_step)
        guid = q["elementos"][0][1]
        if executor is None:
            from obim_geometria import faixas

            executor = lambda p: faixas.rodar_filho(p, limite_s=limite_s)  # noqa: E731
        if motor == "auto":
            try:
                rv = executor({**q, "op": "peca_visivel"})
            except Exception as exc:
                motivo_hlr = f"{type(exc).__name__}: {exc}"
            else:
                if isinstance(rv, dict) and rv.get("ok") and rv.get("grupo"):
                    return {
                        "ok": True,
                        "grupo": rv["grupo"],
                        "tempos": rv.get("tempos") or {},
                        "motor": "visibilidade",
                    }
                motivo_hlr = _motivo_queda(rv)
        r = executor(q)
        if not isinstance(r, dict):
            return _com_motor({"ok": False, "grupo": None, "tempos": tempos, "erro": "resposta inválida do executor"})
        tempos = r.get("tempos") or {}
        if not r.get("ok"):
            erro = r.get("erro")
            msg = erro.get("mensagem") if isinstance(erro, dict) else erro
            return _com_motor({"ok": False, "grupo": None, "tempos": tempos, "erro": str(msg or "falha na peça")})
        grupo = extrair_grupo(r.get("svg") or "", guid)
        if grupo is None:
            return _com_motor({"ok": False, "grupo": None, "tempos": tempos, "erro": f"peça {guid} ausente no SVG"})
        return _com_motor({"ok": True, "grupo": grupo, "tempos": tempos})
    except Exception as e:
        return _com_motor({"ok": False, "grupo": None, "tempos": tempos, "erro": f"{type(e).__name__}: {e}"})
