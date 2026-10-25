# SPDX-License-Identifier: AGPL-3.0-or-later
"""Régua de comparação por conteúdo do fluxo de gravação (ADR-002 §4.2 e §4.8).
Código auxiliar de teste (não é de `app/`). `foto(arquivo, lateral=None, sem_pset_obim=False)` e
`diferencas(a, b)` (lista legível; vazia = igual). Entidade com GlobalId: chave = GlobalId, valor = (classe, atributos na ordem do esquema, sem os
derivados). Referência a entidade com GlobalId = ("G", GlobalId); sem GlobalId = ("E", resumo) com resumo = blake2b da forma canônica (classe e
atributos, recursivo, memória por id; inversos fora). Valor tipado (id 0) = ("T", classe, valor). SET/BAG = multiconjunto (ordenado), LIST/ARRAY em
ordem; o tipo vem do esquema, nunca do tipo Python. Números exatos (sem tolerância). Entidades sem GlobalId: multiconjunto (classe, resumo) de TODAS.
Fora: ids STEP, cabeçalho; com sem_pset_obim, o pset `OBIM_Projeto`, as propriedades dele e a relação que o liga. Lateral: `canonico()`.
Granularidade de `diferencas`: uma linha por GlobalId cujo valor mudou (classe e primeiro atributo diferente) e uma por (classe, resumo) do
multiconjunto cuja contagem difere; uma forma sem GlobalId que mudou dá DUAS linhas (a velha e a nova).
Fixtures comuns da S05 (importar no módulo de teste): `base_ifc` (gerar_modelo_grande, 300 paredes, sha256 impresso) e `_limpa` (autouse: solta o
registry da classe dos arquivos do caso e volta `ifcopenshell.guid.new`). Guarda: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import gc
import hashlib
import sys
from collections import Counter
from pathlib import Path

import pytest
from obrigatorio import pular

try:
    import ifcopenshell
    import ifcopenshell.guid
    import ifcopenshell.ifcopenshell_wrapper as W
except ImportError as e:  # o módulo carrega; cada caso que usa a régua pula
    ifcopenshell = W = None
    _SEM = repr(e)


def exigir():
    if ifcopenshell is None:
        pular(f"\n!!! S05: sem ifcopenshell ({_SEM}); teste NÃO FOI EXECUTADO !!!\n", "OBIM_S05_OBRIGATORIO")


@pytest.fixture(scope="session")
def base_ifc(tmp_path_factory):
    exigir()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import gerar_modelo_grande
    p = tmp_path_factory.mktemp("s05") / "base.ifc"
    gerar_modelo_grande.gerar(str(p), paredes=300)
    print(f"\nbase S05 {p} sha256 {hashlib.sha256(p.read_bytes()).hexdigest()}")
    return str(p)


@pytest.fixture(autouse=True)
def _limpa():
    if ifcopenshell is None:
        yield
        return
    reg, novo, antes = ifcopenshell.file.registry, ifcopenshell.guid.new, set(ifcopenshell.file.registry)
    yield
    ifcopenshell.guid.new = novo
    for k in set(reg) - antes:
        reg.pop(k, None)
    gc.collect()

_DECL = {}


def _tipo(t):  # None (escalar, entidade, seleção) ou (é_multiconjunto, tipo do elemento)
    if isinstance(t, W.aggregation_type):
        return (t.type_of_aggregation_string() in ("set", "bag"), _tipo(t.type_of_element()))
    if isinstance(t, W.named_type):
        d = t.declared_type()
        return _tipo(d.declared_type()) if isinstance(d, W.type_declaration) else None
    return None


def _decl(esquema, classe):  # [(índice, nome, tipo)] sem os derivados
    k = (esquema, classe)
    if k not in _DECL:
        d = W.schema_by_name(esquema).declaration_by_name(classe)
        _DECL[k] = [(i, a.name(), _tipo(a.type_of_attribute())) for i, (a, der) in enumerate(zip(d.all_attributes(), d.derived())) if not der]
    return _DECL[k]


class _Foto:
    def __init__(s, arquivo):
        s.esq, s.memo = arquivo.schema_identifier, {}

    def valor(s, v, t):
        if isinstance(v, ifcopenshell.entity_instance):
            if not v.id():
                return ("T", v.is_a(), s.valor(v.wrappedValue, None))
            return ("G", v.GlobalId) if v.is_a("IfcRoot") else ("E", s.resumo(v))
        if isinstance(v, (tuple, list)):
            multi, el = t if t else (False, None)
            itens = [s.valor(x, el) for x in v]
            return ("S", tuple(sorted(itens, key=repr))) if multi else ("L", tuple(itens))
        return v

    def atributos(s, e):
        return tuple(s.valor(e[i], t) for i, _, t in _decl(s.esq, e.is_a()))

    def resumo(s, e):
        if e.id() not in s.memo:
            s.memo[e.id()] = hashlib.blake2b(repr((e.is_a(), s.atributos(e))).encode(), digest_size=16).hexdigest()
        return s.memo[e.id()]


def foto(arquivo, lateral=None, sem_pset_obim=False):
    fora = set()
    if sem_pset_obim:
        for ps in arquivo.by_type("IfcPropertySet"):
            if ps.Name == "OBIM_Projeto":
                fora |= {ps.id(), *(p.id() for p in ps.HasProperties or ()), *(r.id() for r in ps.DefinesOccurrence or ())}
    f, com, sem = _Foto(arquivo), {}, Counter()
    for e in arquivo:
        if e.id() in fora:
            continue
        if e.is_a("IfcRoot"):
            com[e.GlobalId] = (e.is_a(), f.atributos(e))
        else:
            sem[(e.is_a(), f.resumo(e))] += 1
    return {"esquema": f.esq, "com": com, "sem": sem, "lado": None if lateral is None else bytes(lateral.canonico())}


def diferencas(a, b):
    d = []
    for g in sorted(a["com"].keys() | b["com"].keys()):
        x, y = a["com"].get(g), b["com"].get(g)
        if x == y:
            continue
        if x is None or y is None:
            d.append(f"{g} ({(x or y)[0]}): só na {'segunda' if x is None else 'primeira'} foto")
        elif x[0] != y[0]:
            d.append(f"{g}: classe {x[0]} contra {y[0]}")
        else:
            j = next(j for j, (p, q) in enumerate(zip(x[1], y[1])) if p != q)
            d.append(f"{g} ({x[0]}): {_decl(a['esquema'], x[0])[j][1]} = {x[1][j]!r:.150} contra {y[1][j]!r:.150}")
    for k in sorted(a["sem"].keys() | b["sem"].keys()):
        if a["sem"][k] != b["sem"][k]:
            d.append(f"sem GlobalId {k[0]} {k[1]}: {a['sem'][k]} contra {b['sem'][k]}")
    if a["lado"] != b["lado"]:
        d.append(f"lateral: canonico() difere ({(a['lado'] or b'')[:120]!r} contra {(b['lado'] or b'')[:120]!r})")
    return d
