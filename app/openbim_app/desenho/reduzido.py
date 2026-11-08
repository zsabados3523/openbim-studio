# SPDX-License-Identifier: AGPL-3.0-or-later
"""IFC reduzido para desenho de planta/corte, preservando os mesmos `id_step`.

Escreve texto STEP (ISO-10303-21) só com o fecho necessário ao desenho: elementos
selecionados, anotação da vista, `IfcProject` e as relações inversas (Voids, Fills,
Aggregates, ContainedInSpatialStructure, AssociatesMaterial, DefinesByType e o pset
da anotação). Listas de relações são filtradas ao que entrou; relação sem nenhum
relacionado é descartada. Não carrega geometria no app (ADR-004 regra 9).
"""
from __future__ import annotations

import locale
import os
import time

import ifcopenshell

ET = ifcopenshell.entity_instance

_RELS = frozenset({
    "IfcRelVoidsElement",
    "IfcRelFillsElement",
    "IfcRelAggregates",
    "IfcRelContainedInSpatialStructure",
    "IfcRelAssociatesMaterial",
    "IfcRelDefinesByType",
    "IfcRelProjectsElement",
})
# Lado escalar ("um") das relações 1:N: só entram pelo lado do relacionado.
_RELATING_DE = {
    "IfcRelAggregates": "RelatingObject",
    "IfcRelContainedInSpatialStructure": "RelatingStructure",
    "IfcRelAssociatesMaterial": "RelatingMaterial",
    "IfcRelDefinesByType": "RelatingType",
    "IfcRelDefinesByProperties": "RelatingPropertyDefinition",
}


def _cabecalho(ifc) -> str:
    return (
        "ISO-10303-21;\nHEADER;\n"
        "FILE_DESCRIPTION(('ViewDefinition [ReferenceView]'),'2;1');\n"
        "FILE_NAME('reduzido.ifc','',(''),(''),'','','');\n"
        "FILE_SCHEMA(('%s'));\n"
        "ENDSEC;\nDATA;\n" % ifc.schema_identifier
    )


def _aceita(rel, origem, anotacao_id: int, incl: set[int], selecionados: set[int]) -> bool:
    cls = rel.is_a()
    if cls == "IfcRelVoidsElement" or cls == "IfcRelProjectsElement":
        return True
    if cls == "IfcRelFillsElement":
        preenchimento = getattr(rel, "RelatedBuildingElement", None)
        return preenchimento is not None and (preenchimento.id() in incl or preenchimento.id() in selecionados)
    if cls == "IfcRelDefinesByProperties" and origem.id() != anotacao_id:
        return False
    attr = _RELATING_DE.get(cls)
    if attr is None:
        return False
    um = getattr(rel, attr, None)
    return um is None or um.id() != origem.id()


def _linha_rel(rel, incl: set[int]) -> str | None:
    s = rel.to_string()
    for attr in rel:
        if not isinstance(attr, tuple) or not attr:
            continue
        if not all(isinstance(x, ET) for x in attr):
            continue
        ids = [x.id() for x in attr]
        velho = "(" + ",".join("#%d" % i for i in ids) + ")"
        if velho not in s:
            continue
        mantidos = [i for i in ids if i in incl]
        if not mantidos:
            return None
        s = s.replace(velho, "(" + ",".join("#%d" % i for i in mantidos) + ")", 1)
    return s


def _coletar(ifc, ids, anotacao_id: int) -> tuple[list[int], dict[int, str]]:
    proj = ifc.by_type("IfcProject")[0]
    anot = ifc.by_id(anotacao_id)
    selecionados = {int(i) for i in ids}
    incl: set[int] = set()
    rels: dict[int, object] = {}
    fila: list[object] = []
    inspecionados: set[int] = set()

    def refs(valor, pilha):
        if isinstance(valor, ET):
            pilha.append(valor)
        elif isinstance(valor, tuple):
            for item in valor:
                refs(item, pilha)

    def fecho(raizes):
        pilha = list(raizes)
        while pilha:
            e = pilha.pop()
            i = e.id()
            if i == 0 or i in incl:
                continue
            incl.add(i)
            if e.is_a("IfcObjectDefinition"):
                fila.append(e)
            for a in e:
                refs(a, pilha)

    def incluir_rel(rel):
        if rel.id() in rels:
            return
        rels[rel.id()] = rel
        for a in rel:
            if isinstance(a, ET):
                fecho([a])

    fecho([ifc.by_id(i) for i in ids] + [anot, proj])

    pos = 0
    while pos < len(fila):
        e = fila[pos]
        pos += 1
        if e.id() in inspecionados:
            continue
        inspecionados.add(e.id())
        for rel in ifc.get_inverse(e):
            cls = rel.is_a()
            if cls not in _RELS and cls != "IfcRelDefinesByProperties":
                continue
            if rel.id() in rels:
                continue
            if not _aceita(rel, e, anotacao_id, incl, selecionados):
                continue
            incluir_rel(rel)

    linhas: dict[int, str] = {}
    for i in incl:
        linhas[i] = ifc.by_id(i).to_string()
    for i, rel in rels.items():
        s = _linha_rel(rel, incl)
        if s is not None:
            linhas[i] = s
    return sorted(linhas), linhas


def _executar(ifc, ids, anotacao_id: int, saida) -> dict:
    tempos: dict[str, float] = {}
    t = time.perf_counter()
    ordem, linhas = _coletar(ifc, ids, anotacao_id)
    tempos["coleta_s"] = time.perf_counter() - t

    t = time.perf_counter()
    texto = ";\n".join(linhas[i] for i in ordem)
    tempos["texto_s"] = time.perf_counter() - t

    t = time.perf_counter()
    with open(saida, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(_cabecalho(ifc))
        fp.write(texto)
        fp.write(";\nENDSEC;\nEND-ISO-10303-21;\n")
    tempos["grava_s"] = time.perf_counter() - t

    tempos["n_entidades"] = len(ordem)
    tempos["mb"] = os.path.getsize(saida) / 1e6
    return tempos


def escrever_reduzido(ifc, ids, anotacao_id, saida) -> dict:
    """Escreve `saida` com o IFC reduzido e devolve tempos (s), `n_entidades` e `mb`."""
    anterior = locale.setlocale(locale.LC_NUMERIC)
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
        return _executar(ifc, ids, anotacao_id, saida)
    finally:
        locale.setlocale(locale.LC_NUMERIC, anterior)
