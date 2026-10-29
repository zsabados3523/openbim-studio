# SPDX-License-Identifier: AGPL-3.0-or-later
"""Merge de três vias por estado (ADR-002 §4.7): a unidade é o elemento inteiro, identificado pelo GlobalId.

Regra por item (elemento ou objeto do lateral): mudou só numa cópia = vem dessa cópia; em nenhuma = fica como na base;
mudou nas duas com conteúdo diferente = conflito, fica como na base. Relação (IfcRelationship) nunca é dona: o conteúdo
dela não conta a lista de membros, e os membros são a união das duas cópias (ver `_membros_finais`). Relação sem membro
final sai; cópia que apagou a relação (tirou o último membro) não conta como mudança. Referência nova a elemento que a
outra cópia apagou = conflito do elemento; alvo pendente de referência de relação viva volta como na base (`_restaura`).
Montagem: arquivo novo; cada entidade é recriada na montagem (ids STEP novos, sem colisão); entidade sem GlobalId vem
se for alcançável a partir de um elemento ou se só aponta para o que já entrou e ninguém vivo a deixou de fora
(dono inverso: cor, camada, aspecto de forma, georreferência; `_Montagem.orfaos`); entidade não-raiz igual à da base é
compartilhada.
"""
import hashlib
from collections import namedtuple

import ifcopenshell

Resultado = namedtuple("Resultado", "modelo lateral conflitos")
MEMBROS = ("RelatedElements", "RelatedObjects")
ORDEM = {"base": 0, "a": 1, "b": 2}


def _raiz(v):
    return isinstance(v, ifcopenshell.entity_instance) and v.id() != 0 and v.is_a("IfcRoot")


def _tem_raiz(v):
    return _raiz(v) or (isinstance(v, (list, tuple)) and any(_raiz(x) for x in v))


def _membro_idx(e):  # índice do atributo de membros de uma relação; None se não é relação
    if not e.is_a("IfcRelationship"):
        return None
    return next((i for i in range(len(e)) if e.attribute_name(i) in MEMBROS), None)


def _alcance(itens):  # GlobalIds das raízes alcançáveis por referência a partir de `itens` (sem atravessar raízes)
    out, pilha, visto = set(), list(itens), set()
    while pilha:
        v = pilha.pop()
        if isinstance(v, (list, tuple)):
            pilha.extend(v)
        elif isinstance(v, ifcopenshell.entity_instance) and v.id() != 0:
            if v.is_a("IfcRoot"):
                out.add(v.GlobalId)
            elif v.id() not in visto:
                visto.add(v.id())
                pilha.extend(v)
    return out


class _Fonte:
    def __init__(s, nome, arquivo):
        s.nome, s.f, s.memo = nome, arquivo, {}
        s.raizes = {e.GlobalId: e for e in arquivo.by_type("IfcRoot")}
        s.cache, s.refs_c, s.refs_nm = {}, {}, {}

    def valor(s, v):
        if isinstance(v, ifcopenshell.entity_instance):
            if v.id() == 0:
                return ("T", v.is_a(), v.wrappedValue)
            return ("G", v.GlobalId) if v.is_a("IfcRoot") else ("E", s.hash(v))
        if isinstance(v, (list, tuple)):
            return ("L", tuple(s.valor(x) for x in v))
        return v

    def hash(s, e):  # conteúdo de entidade sem GlobalId, por valor (referências por conteúdo)
        if e.id() not in s.memo:
            s.memo[e.id()] = hashlib.blake2b(repr((e.is_a(), tuple(s.valor(x) for x in e))).encode(), digest_size=16).hexdigest()
        return s.memo[e.id()]

    def conteudo(s, g):  # None = ausente; relação sem a lista de membros
        if g not in s.cache:
            e = s.raizes.get(g)
            if e is None:
                s.cache[g] = None
            else:
                mi = _membro_idx(e)
                s.cache[g] = (e.is_a(), tuple(s.valor(x) for i, x in enumerate(e) if i != mi))
        return s.cache[g]

    def membros(s, g):
        e = s.raizes.get(g)
        mi = _membro_idx(e) if e is not None else None
        return [] if mi is None else [x.GlobalId for x in e[mi] if _raiz(x)]

    def refs(s, g):  # raízes que g referencia, membros incluídos; ausente = vazio
        if g not in s.refs_c:
            s.refs_c[g] = _alcance(list(s.raizes[g])) if g in s.raizes else set()
        return s.refs_c[g]

    def ref_nm(s, g):  # raízes referenciadas fora da lista de membros
        if g not in s.refs_nm:
            e = s.raizes.get(g)
            if e is None:
                s.refs_nm[g] = set()
            else:
                mi = _membro_idx(e)
                s.refs_nm[g] = _alcance([v for i, v in enumerate(e) if i != mi])
        return s.refs_nm[g]


def _decidir(v0, va, vb, rel=False):  # -> (fonte que vale, conflito); conteúdo None = ausente
    if rel:  # relação: a cópia que a apagou (tirou o último membro) não conta como mudança; o que vale são os membros
        ca, cb = va is not None and va != v0, vb is not None and vb != v0
    else:
        ca, cb = va != v0, vb != v0
    if ca and cb and va != vb:
        return "base", True
    if ca:
        return "a", False
    if cb:
        return "b", False
    return "base", False


class _Montagem:
    def __init__(s, base, fontes):
        s.out = ifcopenshell.file(schema=base.f.schema_identifier)
        s.base, s.fontes = base, fontes
        s.base_ids = {e.id() for e in base.f}
        s.memo, s.pend, s.raiz, s.visto = {}, [], {}, []

    def _chave(s, f, e):
        if e.is_a("IfcRoot"):
            return ("G", e.GlobalId)
        if f.nome == "base" or (e.id() in s.base_ids and f.hash(e) == s.base.hash(s.base.f.by_id(e.id()))):
            return ("base", e.id())
        return (f.nome, e.id())

    def _conv(s, f, v):  # atributo sem raiz: copia as entidades não-raiz
        if isinstance(v, ifcopenshell.entity_instance) and v.id() != 0:
            return s.copia(f, v)
        if isinstance(v, (list, tuple)):
            return [s._conv(f, x) for x in v if not _raiz(x)]
        return v

    def copia(s, f, e, membros=None):
        k = s._chave(f, e)
        if k in s.memo:
            return s.memo[k]
        args, pend, mi = [], [], _membro_idx(e)
        for i, v in enumerate(e):
            if i == mi and membros is not None:
                args.append([])
                pend.append((i, membros, False))
            elif _tem_raiz(v):
                unico = _raiz(v)
                args.append(None if unico else [])
                pend.append((i, [v.GlobalId] if unico else [x.GlobalId for x in v if _raiz(x)], unico))
            else:
                args.append(s._conv(f, v))
        ent = s.out.create_entity(e.is_a(), *args)
        s.memo[k] = ent
        s.visto.append((f, e))
        if e.is_a("IfcRoot"):
            s.raiz[e.GlobalId] = ent
        s.pend += [(ent, i, guids, unico) for i, guids, unico in pend]
        return ent

    def _vivo(s, f, q):  # quem aponta para uma entidade sem GlobalId está na saída (raiz copiada ou não-raiz copiada)
        return q.GlobalId in s.raiz if q.is_a("IfcRoot") else s._chave(f, q) in s.memo

    def orfaos(s):  # não-raiz que só aponta para o que já entrou e ninguém fora da saída a aponta: entra (cor, camada, aspecto, georreferência)
        cand, i = {}, 0
        while True:
            while i < len(s.visto):
                f, e = s.visto[i]
                i += 1
                for x in f.f.get_inverse(e):
                    if not x.is_a("IfcRoot"):
                        cand.setdefault((f.nome, x.id()), (f, x))
            entrou = False
            for k in sorted(cand):
                f, x = cand[k]
                if s._chave(f, x) in s.memo:
                    del cand[k]
                elif all(s._vivo(f, q) for q in f.f.get_inverse(x)) and all(g in s.raiz for g in _alcance([x])):
                    s.copia(f, x)
                    del cand[k]
                    entrou = True
            if not entrou:
                return

    def fechar(s):  # referências a raízes, depois que todas as raízes existem
        for ent, i, guids, unico in s.pend:
            val = s.raiz.get(guids[0]) if unico else [s.raiz[g] for g in guids if g in s.raiz]
            setattr(ent, ent.attribute_name(i), val)
        return s.out


def _membros_finais(g, F, conflitos, vivo):  # união das cópias; membro em conflito volta ao da base; base na ordem da base, novos por GlobalId
    m0, ma, mb = (F[n].membros(g) for n in ("base", "a", "b"))
    s0, sa, sb = set(m0), set(ma), set(mb)

    def fica(x):
        if x in conflitos:
            return x in s0 and x in vivo
        return ((x in s0 and x in sa and x in sb) or (x not in s0 and (x in sa or x in sb))) and x in vivo

    return [x for x in m0 if fica(x)] + sorted(x for x in (sa | sb) - s0 if fica(x))


def _cortados(F, esc, conflitos):  # relação sem membro final sai; elemento novo que só ela usava (pset) sai junto
    fb = F["base"]
    presentes = set(esc)
    cort = {g for g in esc if _membro_idx(F[esc[g]].raizes[g]) is not None and not _membros_finais(g, F, conflitos, presentes)}
    vivo = presentes - cort
    cand = set()
    for g in cort:
        for x in F[esc[g]].refs(g):
            if x in esc and x not in fb.raizes and not F[esc[x]].raizes[x].is_a("IfcProduct"):
                cand.add(x)
    if cand:
        ref_vivas = set()
        for g in vivo:
            ref_vivas |= F[esc[g]].refs(g)
        cort |= cand - ref_vivas
    return cort


def _restaura(F, esc, conflitos, vivo):  # alvo pendente de referência de raiz viva: conflito do alvo, que volta como na base
    mudou = False
    for g in sorted(vivo):
        for x in sorted(F[esc[g]].ref_nm(g)):
            if x in F["base"].raizes and x not in esc:
                conflitos.add(x)
                esc[x] = "base"
                mudou = True
    return mudou


def juntar(base, a, b):
    F = {"base": _Fonte("base", base[0]), "a": _Fonte("a", a[0]), "b": _Fonte("b", b[0])}
    fb = F["base"]
    conflitos, esc = set(), {}
    for g in sorted(F["base"].raizes.keys() | F["a"].raizes.keys() | F["b"].raizes.keys()):
        rel = any(_membro_idx(F[n].raizes[g]) is not None for n in F if g in F[n].raizes)
        nome, conf = _decidir(fb.conteudo(g), F["a"].conteudo(g), F["b"].conteudo(g), rel)
        if conf:
            conflitos.add(g)
        if F[nome].conteudo(g) is not None:
            esc[g] = nome
    for z, o in (("a", "b"), ("b", "a")):  # referência nova a elemento que a outra cópia apagou: conflito do elemento
        for g in sorted(F[z].raizes):
            for x in sorted(F[z].refs(g) - fb.refs(g)):
                if x in fb.raizes and x not in F[o].raizes:
                    conflitos.add(x)
                    esc[x] = "base"
    while True:
        cort = _cortados(F, esc, conflitos)
        if not _restaura(F, esc, conflitos, set(esc) - cort):
            break
    vivo = set(esc) - cort
    m = _Montagem(fb, F)
    for g in sorted(vivo):
        f = F[esc[g]]
        e = f.raizes[g]
        m.copia(f, e, _membros_finais(g, F, conflitos, vivo) if _membro_idx(e) is not None else None)
    m.orfaos()
    modelo = m.fechar()

    lat = [base[1], a[1], b[1]]
    dic = {}
    for c, i in sorted({(c, i) for L in lat for c in L.colecoes() for i in L.ids(c)}):
        vals = [L.obter(c, i) for L in lat]
        nome, conf = _decidir(*vals)
        if conf:
            conflitos.add(f"{c}/{i}")
        val = vals[ORDEM[nome]]
        if val is not None:
            dic.setdefault(c, {})[i] = val
    return Resultado(modelo, type(base[1])(dic), sorted(conflitos))
