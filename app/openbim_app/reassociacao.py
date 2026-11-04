# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reassociação assistida de GlobalIds trocados (v2/02 §6.3; ADR-002 §4/§11).

Funções puras: não leem arquivos, não usam Qt nem ifcopenshell.
Elemento = {"guid", "classe", "nome", "tag", "caixa"} com caixa em metros.
"""
import copy
import math

TOL_ALTA = 0.5
TOL_BAIXA = 2.0


def _centro(caixa):
    if caixa is None:
        return None
    try:
        v = list(caixa)
    except TypeError:
        return None
    if len(v) != 6:
        return None
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        if not math.isfinite(x):
            return None
    # metade de cada extremo evita estouro em caixas perto de 1e308
    return (
        v[0] / 2.0 + v[3] / 2.0,
        v[1] / 2.0 + v[4] / 2.0,
        v[2] / 2.0 + v[5] / 2.0,
    )


def _distancia(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _eh_fraca(tag_antigo, tag_novo):
    """Name igual já é premissa; aqui decide a Tag. Forte nunca cai aqui."""
    tem_a = bool(tag_antigo)
    tem_n = bool(tag_novo)
    if tem_a and tem_n:
        return tag_antigo != tag_novo
    return tem_a != tem_n


def _tolerancia_valida(tol_alta, tol_baixa):
    for t in (tol_alta, tol_baixa):
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            return False
        if not math.isfinite(t) or t < 0:
            return False
    return tol_baixa >= tol_alta


def _preparar_atuais(atuais):
    guids = set()
    por_tag = {}
    por_nome = {}
    for novo in atuais:
        g = novo.get("guid")
        if g is None:
            continue
        guids.add(g)
        classe = novo.get("classe")
        tag = novo.get("tag")
        nome = novo.get("nome")
        item = (g, _centro(novo.get("caixa")), tag)
        if tag:
            por_tag.setdefault((classe, tag), []).append(item)
        if nome:
            por_nome.setdefault((classe, nome), []).append(item)
    return guids, por_tag, por_nome


def _sem_duplicatas(itens):
    """Deduplica candidatos por guid mantendo a menor distância."""
    vistos = {}
    for g, d in itens:
        atual = vistos.get(g)
        if atual is None or d < atual:
            vistos[g] = d
    return vistos


def _decisao(antigo, por_tag, por_nome, tol_alta, tol_baixa, bloqueados):
    centro = _centro(antigo.get("caixa"))
    if centro is None:
        return ("orfao", None, None, "caixa_invalida")

    classe = antigo.get("classe")
    tag = antigo.get("tag")
    nome = antigo.get("nome")

    fortes = []
    if tag:
        for g, c, _t in por_tag.get((classe, tag), ()):
            if c is None or g in bloqueados:
                continue
            d = _distancia(centro, c)
            if d <= tol_baixa:
                fortes.append((g, d))
    elif nome:
        for g, c, t in por_nome.get((classe, nome), ()):
            if c is None or g in bloqueados or t:
                continue
            d = _distancia(centro, c)
            if d <= tol_baixa:
                fortes.append((g, d))

    if fortes:
        unicos = _sem_duplicatas(fortes)
        if len(unicos) > 1:
            return ("orfao", None, None, "ambiguo")
        g, d = next(iter(unicos.items()))
        if d <= tol_alta:
            return ("alta", g, "forte", None)
        return ("baixa", g, "forte", None)

    fracos = []
    if nome:
        for g, c, t in por_nome.get((classe, nome), ()):
            if c is None or g in bloqueados:
                continue
            if not _eh_fraca(tag, t):
                continue
            d = _distancia(centro, c)
            if d <= tol_baixa:
                fracos.append((g, d))

    if fracos:
        unicos = _sem_duplicatas(fracos)
        if len(unicos) > 1:
            return ("orfao", None, None, "ambiguo")
        g, _d = next(iter(unicos.items()))
        return ("baixa", g, "fraca", None)

    return ("orfao", None, None, "sem_candidato")


def _vencedores(registros):
    pedidos = {}
    for r in registros:
        if r["tipo"] in ("alta", "baixa") and r["guid_novo"] is not None:
            d = pedidos.setdefault(r["guid_novo"], {})
            antigo = r["guid_antigo"]
            if d.get(antigo) != "forte":
                d[antigo] = r["forca"]
    vencedores = {}
    for novo, antigos in pedidos.items():
        fortes = {a for a, t in antigos.items() if t == "forte"}
        if fortes:
            vencedores[novo] = next(iter(fortes)) if len(fortes) == 1 else None
        else:
            vencedores[novo] = next(iter(antigos)) if len(antigos) == 1 else None
    return vencedores


def _chave(item):
    g = item["guid_antigo"]
    return (item["vista"], g is None, "" if g is None else g)


def contar_quebradas(vistas, atuais):
    guids_atuais = {e.get("guid") for e in atuais if e.get("guid") is not None}
    resultado = {}
    for vista in sorted(vistas):
        quebradas = set()
        for el in vistas[vista]:
            g = el.get("guid")
            if g is None or g not in guids_atuais:
                quebradas.add(g)
        resultado[vista] = len(quebradas)
    return resultado


def propor(vistas, atuais, tol_alta=TOL_ALTA, tol_baixa=TOL_BAIXA):
    if not _tolerancia_valida(tol_alta, tol_baixa):
        raise ValueError("tolerancia invalida")

    guids_atuais, por_tag, por_nome = _preparar_atuais(atuais)
    bloqueados = {
        el.get("guid")
        for elementos in vistas.values()
        for el in elementos
        if el.get("guid") is not None and el.get("guid") in guids_atuais
    }

    registros = []
    for vista in sorted(vistas):
        vistos = set()
        for el in vistas[vista]:
            g = el.get("guid")
            if g is not None and g in guids_atuais:
                continue
            if g in vistos:
                continue
            vistos.add(g)
            if g is None:
                registros.append(
                    {"vista": vista, "guid_antigo": None, "tipo": "orfao",
                     "forca": None, "guid_novo": None, "motivo": "sem_guid"}
                )
                continue
            tipo, guid_novo, forca, motivo = _decisao(
                el, por_tag, por_nome, tol_alta, tol_baixa, bloqueados
            )
            registros.append(
                {"vista": vista, "guid_antigo": g, "tipo": tipo,
                 "forca": forca, "guid_novo": guid_novo, "motivo": motivo}
            )

    vencedores = _vencedores(registros)

    alta, baixa, orfaos = [], [], []
    for r in registros:
        tipo = r["tipo"]
        if tipo in ("alta", "baixa"):
            vencedor = vencedores.get(r["guid_novo"])
            if vencedor is not None and vencedor == r["guid_antigo"]:
                destino = alta if tipo == "alta" else baixa
                destino.append(
                    {"vista": r["vista"], "guid_antigo": r["guid_antigo"],
                     "guid_novo": r["guid_novo"]}
                )
                continue
            orfaos.append(
                {"vista": r["vista"], "guid_antigo": r["guid_antigo"],
                 "motivo": "disputado"}
            )
        else:
            orfaos.append(
                {"vista": r["vista"], "guid_antigo": r["guid_antigo"],
                 "motivo": r["motivo"]}
            )

    return {
        "alta": sorted(alta, key=_chave),
        "baixa": sorted(baixa, key=_chave),
        "orfaos": sorted(orfaos, key=_chave),
    }


def aplicar(vistas, proposta, confirmados):
    validos = {}
    for lista in ("alta", "baixa"):
        for item in proposta.get(lista, []):
            validos[(item["vista"], item["guid_antigo"])] = item["guid_novo"]
    pares = set()
    for par in confirmados:
        par = tuple(par)
        if par not in validos:
            raise ValueError(f"confirmacao invalida: {par}")
        pares.add(par)

    novo = copy.deepcopy(vistas)
    for vista, elementos in novo.items():
        for el in elementos:
            par = (vista, el.get("guid"))
            if par in pares:
                el["guid"] = validos[par]
    return novo
