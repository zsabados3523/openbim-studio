# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo do merge por GlobalId (F0-S05-T11); contrato em `test_s05_t11_merge_oraculo.py`. Código de teste; não editar.
`Cop` (uma cópia editável: IFC aberto da base gravada + lateral em dicionário; GlobalIds novos com prefixo próprio, em sequência fixa, então as
cópias criam GlobalIds diferentes e ids STEP IGUAIS), `cenario` (base + cópias A e B com 200 edições cada, semente fixa; valida o cenário ANTES de chamar
a API: tocados por foto, interseção = conflitos planejados, pisos por tipo, colisão de ids STEP), `esperado` (a foto que o merge tem de ter, calculada só
das fotos da base e das cópias: elemento que uma cópia mudou = o dela; conflito e o que ninguém mudou = o da base; multiconjunto sem GlobalId = base +
variação de A + variação de B), `confere` (a conferência comum). Partição do cenário: A edita os andares 0 a 2 e B os 3 a 5 (cada relação de pavimento
é tocada por uma cópia só); lateral: ids pares para A e ímpares para B."""
import contextlib
import copy
import itertools
import math
import random
import sys
from collections import Counter, namedtuple
from importlib import import_module
from pathlib import Path

import s05_conteudo_aux as R

RAIZ = Path(__file__).resolve().parent.parent
SEMENTE, N_EDICOES = 20261023, 200
PISOS = {"nome": 20, "mover": 10, "pset_criar": 10, "pset_editar": 3, "apagar": 15, "criar": 15, "lado_criar": 5, "lado_alterar": 5, "lado_apagar": 5}
PESOS = {"nome": 3, "mover": 2, "pset_criar": 2, "pset_editar": 1, "apagar": 3, "criar": 3, "lado_criar": 2, "lado_alterar": 2, "lado_apagar": 2}
CONF_ADD = ("0conflitoWallAAAAAAAAA", "0conflitoWallBBBBBBBBB")  # GlobalIds criados nas DUAS cópias com conteúdo diferente (casos pequenos)
Cenario = namedtuple("Cenario", "base a b conflitos esperada fotos cont")  # base/a/b = (arquivo IFC, Lateral); fotos = (f0, fa, fb, l0, la, lb)


def juntar_fn():  # primeira linha de cada caso @AINDA_NAO: módulo ou função ausente = ImportError (único motivo aceito no xfail)
    sys.path.insert(0, str(RAIZ / "prototypes" / "s05"))
    try:
        return import_module("merge").juntar
    except (ImportError, AttributeError) as e:
        raise ImportError(f"prototypes/s05/merge: juntar ausente ({e!r})") from e


def api(*a, **k):
    import ifcopenshell.api
    return ifcopenshell.api.run(*a, **k)


class Cop:
    def __init__(s, caminho, lado, prefixo, semente=SEMENTE):
        R.exigir()
        import ifcopenshell
        import ifcopenshell.util.representation as UR
        s.f, s.lado, s.p, s.r, s.cont = ifcopenshell.open(str(caminho)), copy.deepcopy(lado), prefixo, random.Random(semente), itertools.count(1)
        s.ctx, s.cont_t, s.psets = UR.get_context(s.f, "Model", "Body", "MODEL_VIEW"), Counter(), {}

    @contextlib.contextmanager
    def _guids(s):  # GlobalIds novos = prefixo + sequência fixa; só durante a chamada (a fixture `_limpa` também restaura)
        antes = R.ifcopenshell.guid.new
        R.ifcopenshell.guid.new = lambda: R.ifcopenshell.guid.compress(s.p + "%031x" % next(s.cont))
        try:
            yield
        finally:
            R.ifcopenshell.guid.new = antes

    def par(s):
        from openbim_app.lateral import Lateral
        return s.f, Lateral(copy.deepcopy(s.lado))

    def andares(s):
        return sorted(s.f.by_type("IfcBuildingStorey"), key=lambda a: a.Name)

    def paredes(s, andar):
        return [w.GlobalId for r in andar.ContainsElements for w in r.RelatedElements if w.is_a("IfcWall")]

    def parede(s, andar=None, guid=None, nome="nova", exato=False):  # andar None = parede solta (sem geometria nem pavimento)
        with s._guids():
            w = api("root.create_entity", s.f, ifc_class="IfcWall", name=nome if exato else f"{nome} {s.p}{s.r.random()}")
            if guid:
                w.GlobalId = guid
            if andar is not None:
                api("geometry.assign_representation", s.f, product=w, representation=api(
                    "geometry.add_wall_representation", s.f, context=s.ctx, length=s.r.uniform(1, 5), height=2.8, thickness=0.15))
                s.mover(w.GlobalId)
                api("spatial.assign_container", s.f, products=[w], relating_structure=andar)
        return w.GlobalId

    def nome(s, g, valor=None, attr="Name"):
        api("attribute.edit_attributes", s.f, product=s.f.by_guid(g), attributes={attr: valor or f"{s.p}{s.r.random()}"})

    def mover(s, g):
        import numpy
        a, m = s.r.uniform(0, 2 * math.pi), numpy.eye(4)
        m[0, 0] = m[1, 1] = math.cos(a)
        m[0, 1], m[1, 0] = -math.sin(a), math.sin(a)
        m[0, 3], m[1, 3] = s.r.uniform(-60, 60), s.r.uniform(-60, 60)
        api("geometry.edit_object_placement", s.f, product=s.f.by_guid(g), matrix=m)

    def pset(s, g, editar=False):
        with s._guids():
            ps = s.psets[g] if editar else api("pset.add_pset", s.f, product=s.f.by_guid(g), name="T11_x")
            s.psets[g] = ps
            api("pset.edit_pset", s.f, pset=ps, properties={"Valor": s.r.random(), "Texto": f"v{s.r.randint(0, 9)}"})

    def apagar(s, g):
        s.psets.pop(g, None)
        api("root.remove_product", s.f, product=s.f.by_guid(g))

    def lado_obj(s, vivas):
        return {"texto": f"{s.p}{s.r.random()}", "n": s.r.randint(0, 10**6), "ifc_guids": s.r.sample(vivas, min(2, len(vivas)))}


def foto(par):
    return R.foto(par[0], par[1])


def _lado_dict(par):
    return {c: {i: par[1].obter(c, i) for i in par[1].ids(c)} for c in par[1].colecoes()}


def _edicoes(c, vivas, lado_ids, andares):  # 200 edições aleatórias de uma cópia (só em `vivas` e `lado_ids`); devolve a contagem por tipo
    cont = Counter()
    while sum(cont.values()) < N_EDICOES:
        t, n = c.r.choices(list(PESOS), list(PESOS.values()))[0], sum(cont.values())
        t = "criar" if t == "apagar" and len(vivas) < 30 else t
        t = "pset_criar" if t == "pset_editar" and not [g for g in c.psets if g in vivas] else t
        t = "lado_criar" if t in ("lado_alterar", "lado_apagar") and not lado_ids else t
        w = c.r.choice(vivas)
        if t == "criar":
            vivas.append(c.parede(c.r.choice(andares)))
        elif t == "apagar":
            vivas.remove(w), c.apagar(w)
        elif t == "pset_criar":
            c.pset(c.r.choice([g for g in vivas if g not in c.psets]))
        elif t == "pset_editar":
            c.pset(c.r.choice([g for g in c.psets if g in vivas]), editar=True)
        elif t == "nome":
            c.nome(w)
        elif t == "mover":
            c.mover(w)
        elif t == "lado_criar":
            k = c.r.choice(("notas", "cotas"))
            c.lado[k][f"{c.p}{n}"] = c.lado_obj(vivas)
            lado_ids.append((k, f"{c.p}{n}"))
        elif t == "lado_alterar":
            k, i = c.r.choice(lado_ids)
            c.lado[k][i] = c.lado_obj(vivas)
        else:
            k, i = lado_ids.pop(c.r.randrange(len(lado_ids)))
            del c.lado[k][i]
        cont[t] += 1
    return cont


def tocados(f0, fx, l0, lx):
    return ({g for g in f0["com"].keys() | fx["com"].keys() if f0["com"].get(g) != fx["com"].get(g)},
            {(c, i) for c in l0.keys() | lx.keys() for i in l0.get(c, {}).keys() | lx.get(c, {}).keys() if l0.get(c, {}).get(i) != lx.get(c, {}).get(i)})


def esperado(f0, fa, fb, l0, la, lb, conf_ifc, conf_lado):
    com, sem, lado = {}, Counter(), {}
    for g in f0["com"].keys() | fa["com"].keys() | fb["com"].keys():
        v = f0["com"].get(g) if g in conf_ifc else next((x["com"].get(g) for x in (fa, fb) if x["com"].get(g) != f0["com"].get(g)), f0["com"].get(g))
        v is None or com.__setitem__(g, v)
    for k in f0["sem"].keys() | fa["sem"].keys() | fb["sem"].keys():
        n = f0["sem"][k] + (fa["sem"][k] - f0["sem"][k]) + (fb["sem"][k] - f0["sem"][k])
        assert n >= 0, f"cenário: contagem negativa de {k}"
        n and sem.__setitem__(k, n)
    for c in l0.keys() | la.keys() | lb.keys():
        for i in l0.get(c, {}).keys() | la.get(c, {}).keys() | lb.get(c, {}).keys():
            ref = l0.get(c, {}).get(i)
            v = ref if (c, i) in conf_lado else next((x.get(c, {}).get(i) for x in (la, lb) if x.get(c, {}).get(i) != ref), ref)
            v is None or lado.setdefault(c, {}).__setitem__(i, v)
    from openbim_app.lateral import Lateral
    return {"esquema": f0["esquema"], "com": com, "sem": sem, "lado": bytes(Lateral(lado).canonico())}


def base_gravada(tmp, paredes=600, por_andar=100):  # base em disco + lateral da base (50 notas e 30 cotas que apontam para paredes)
    R.exigir()
    sys.path.insert(0, str(RAIZ / "scripts"))
    import gerar_modelo_grande
    caminho = tmp / "base.ifc"
    gerar_modelo_grande.gerar(str(caminho), paredes=paredes, por_andar=por_andar)
    g = [w.GlobalId for w in R.ifcopenshell.open(str(caminho)).by_type("IfcWall")]
    return caminho, {"notas": {f"n{i:03d}": {"texto": f"nota {i}", "ifc_guids": [g[i]]} for i in range(50)},
                     "cotas": {f"c{i:03d}": {"texto": f"cota {i}", "ifc_guids": [g[i], g[i + 1]]} for i in range(30)}}


def duas(base_ifc, lado=None):  # base pequena (a fixture `base_ifc`): (par da base, cópia A, cópia B)
    from openbim_app.lateral import Lateral
    lado = lado or {"notas": {"n1": {"texto": "um"}, "n2": {"texto": "dois"}}}
    return (R.ifcopenshell.open(base_ifc), Lateral(lado)), Cop(base_ifc, lado, "a", SEMENTE), Cop(base_ifc, lado, "b", SEMENTE + 1)


def esp(c, conf_ifc=(), conf_lado=()):  # a foto esperada para esses conflitos (ver `esperado`)
    return esperado(*c.fotos, set(conf_ifc), set(conf_lado))


def fechar(base, A, B, conf_ifc=(), conf_lado=(), inter_ifc=(), esperada=None, cont=None):  # valida o cenário ANTES da API e monta o `Cenario`
    pa, pb = A.par(), B.par()
    fotos = (foto(base), foto(pa), foto(pb), _lado_dict(base), _lado_dict(pa), _lado_dict(pb))
    ta, tb = tocados(*fotos[0:2], *fotos[3:5]), tocados(fotos[0], fotos[2], fotos[3], fotos[5])
    assert ta[0] & tb[0] == set(conf_ifc) | set(inter_ifc) and ta[1] & tb[1] == set(conf_lado), f"cenário: interseção {sorted(ta[0] & tb[0])[:5]}, {sorted(ta[1] & tb[1])}"
    c = Cenario(base, pa, pb, list(conf_ifc) + [f"{k}/{i}" for k, i in conf_lado], None, fotos, cont)
    return c._replace(esperada=esperada or esp(c, conf_ifc, conf_lado))


def cenario(tmp, com_conflitos):
    caminho, lado0 = base_gravada(tmp)
    from openbim_app.lateral import Lateral
    base = (R.ifcopenshell.open(str(caminho)), Lateral(lado0))
    A, B = Cop(caminho, lado0, "a", SEMENTE), Cop(caminho, lado0, "b", SEMENTE + 1)
    an_a, an_b = A.andares(), B.andares()
    reservadas = sorted(base[0].by_type("IfcWall")[k].GlobalId for k in range(0, 600, 29)[:20]) if com_conflitos else []
    pools = [[g for a in an[i:i + 3] for g in c.paredes(a) if g not in reservadas] for c, an, i in ((A, an_a, 0), (B, an_b, 3))]
    ids = [[(k, i) for k in lado0 for i in lado0[k] if int(i[1:]) % 2 == p and int(i[1:]) > 1] for p in (0, 1)]  # índices 0 e 1 (n000, n001, c000, c001) são dos conflitos
    if com_conflitos:
        for k, g in enumerate(reservadas):  # as duas cópias mexem no mesmo elemento: o mesmo atributo ou atributos diferentes, sempre valores diferentes
            A.nome(g, f"A{k}"), B.nome(g, f"B{k}", "Name" if k < 10 else "Description")
    cont = [_edicoes(A, pools[0], ids[0], an_a[0:3]), _edicoes(B, pools[1], ids[1], an_b[3:6])]
    for x in cont:
        faltam = {t: x[t] for t in PISOS if x[t] < PISOS[t]}
        assert not faltam, f"cenário: pisos não atingidos {faltam}"
    c = fechar(base, A, B, reservadas, cont=cont)
    novos = [{e.id() for e in p[0]} - {e.id() for e in base[0]} for p in (c.a, c.b)]
    choques = [i for i in novos[0] & novos[1] if str(c.a[0].by_id(i)) != str(c.b[0].by_id(i))]
    assert len(choques) >= 100, f"cenário: só {len(choques)} ids STEP novos colidem com conteúdo diferente"
    return c


def confere(r, c, tmp, onde="", ignorar=()):  # tipos, independência das entradas, conflitos exatos, conteúdo igual ao esperado, gravar e reabrir
    entradas = (c.base, c.a, c.b)
    assert isinstance(r.modelo, R.ifcopenshell.file) and all(r.modelo is not x[0] for x in entradas), f"{onde}: modelo tem de ser um arquivo novo"
    assert all(r.lateral is not x[1] for x in entradas), f"{onde}: lateral tem de ser novo"
    assert len(r.conflitos) == len(set(r.conflitos)) and sorted(r.conflitos) == sorted(c.conflitos), f"{onde}: conflitos {sorted(r.conflitos)} (esperado {sorted(c.conflitos)})"
    cheia = foto((r.modelo, r.lateral))
    m, e = dict(cheia, com=dict(cheia["com"])), dict(c.esperada, com=dict(c.esperada["com"]))
    for g in ignorar:
        m["com"].pop(g, None), e["com"].pop(g, None)
    dif = R.diferencas(m, e)
    assert not dif, f"{onde}: {len(dif)} diferenças, primeiras: {dif[:8]}"
    for x, f in zip(entradas, (c.fotos[0], c.fotos[1], c.fotos[2])):
        assert R.diferencas(foto(x), f) == [], f"{onde}: o merge mudou uma entrada"
    r.modelo.write(str(tmp / "juntado.ifc"))
    dif = R.diferencas(foto((R.ifcopenshell.open(str(tmp / "juntado.ifc")), r.lateral)), cheia)
    assert not dif, f"{onde}: gravar e reabrir o resultado mudou o conteúdo: {dif[:8]}"
