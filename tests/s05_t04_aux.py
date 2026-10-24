# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gerador do oráculo do F0-S05-T04 (quem implementa não edita): `Plano` (sorteio puro com semente; a simulação dos pisos e os casos usam ESTE
código), `aplicar` (uma operação no IFC por `ifcopenshell.api` ou no lateral), `LadoEnsaio` e `Cru` (ifcopenshell sem o módulo novo, para a régua e
a rodada de hoje), `montar` (arquivo livre antes do `Historico`), `dez_mil` (caso 1) e `rodar_filho` (caso pesado num pytest filho, como o V1c).
Semente SEMENTE = 20261023 (`random.Random`): tipo da operação, operações por transação (1 a 3) e alvos; SEMENTE + 1: parâmetros (matrizes, valores);
SEMENTE + 2: a mistura do caso 2. Pisos fixos: N_OPS = 10.000 operações INTEIRAS, 500 por tipo, 1.000 transações mistas (nunca baixar)."""
import contextlib
import copy
import itertools
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
from collections import Counter

import pytest
import s05_conteudo_aux as R

SEMENTE, N_OPS, PISO_TIPO, PISO_MISTAS, PONTO = 20261023, 10_000, 500, 1_000, 500
DENTRO = os.environ.get("OBIM_S05_T04_DENTRO") == "1"  # 1 = este é o pytest filho
TIPOS = ("parede", "nome", "pset_editar", "pset_criar", "mover", "apagar", "lote", "tipo", "pavimento", "lado_criar", "lado_alterar", "lado_apagar")
PESOS = [3] + [1] * 11


class Plano:  # o gerador: puro (só `random`), com as próprias listas de alvos; a simulação dos pisos e os casos usam ESTE mesmo código
    def __init__(s, semente, paredes):
        s.r, s.n, s.paredes, s.psets, s.lado, s.tipos = random.Random(semente), 0, sorted(paredes), [], [], 3

    def estado(s):
        return (list(s.paredes), list(s.psets), list(s.lado), s.tipos)

    def restaurar(s, e):
        s.paredes, s.psets, s.lado, s.tipos = list(e[0]), list(e[1]), list(e[2]), e[3]

    def transacao(s, resto):
        return [s.op() for _ in range(min(s.r.randint(1, 3), resto))]

    def op(s, t=None):
        r, t = s.r, t or s.r.choices(TIPOS, PESOS)[0]
        t = "parede" if t in ("apagar", "lote") and len(s.paredes) < 150 else t
        t = "pset_criar" if t == "pset_editar" and not s.psets else "lado_criar" if t in ("lado_alterar", "lado_apagar") and not s.lado else t
        s.n += 1
        novo, w = f"p{s.n}", r.choice(s.paredes)
        if t == "parede":
            s.paredes.append(novo)
            return (t, novo)
        if t in ("apagar", "lote"):
            alvos = [w] if t == "apagar" else r.sample(s.paredes, r.randint(2, 4))
            s.paredes = [p for p in s.paredes if p not in alvos]
            s.psets = [p for p in s.psets if p[1] not in alvos]  # root.remove_product apaga o pset que só a parede usa
            return (t, w) if t == "apagar" else (t, alvos)
        if t == "pset_criar":
            s.psets.append((novo, w))
            return (t, w, novo)
        if t == "pset_editar":
            return (t, r.choice(s.psets)[0])
        if t == "tipo":
            novo_tipo = r.random() < 0.1
            s.tipos += novo_tipo
            return (t, w, f"t{s.tipos - 1}", novo_tipo)
        if t == "lado_criar":
            s.lado.append((r.choice(("notas", "cotas")), f"o{s.n}"))
            return (t, *s.lado[-1], r.sample(s.paredes, r.randint(1, 3)))
        if t == "lado_alterar":
            return (t, *r.choice(s.lado), r.sample(s.paredes, r.randint(1, 3)))
        if t == "lado_apagar":
            return (t, *s.lado.pop(r.randrange(len(s.lado))))
        return (t, w)  # nome, mover, pavimento


def contar(plano, n_ops=N_OPS, tx=None):  # aplica (ou só sorteia) até n_ops; devolve (contagem por tipo, transações, mistas)
    cont, n_tx, mistas, n = Counter(), 0, 0, 0
    while n < n_ops:
        ops = plano.transacao(n_ops - n)
        tx and tx(ops)
        n, n_tx = n + len(ops), n_tx + 1
        cont.update(o[0] for o in ops)
        mistas += len({o[0].startswith("lado") for o in ops}) == 2
    assert n == n_ops
    return cont, n_tx, mistas


# ---------- aplicação no IFC (ifcopenshell.api) e lateral de ensaio ----------
def _api():
    R.exigir()
    import ifcopenshell.api
    import numpy
    return R.ifcopenshell, ifcopenshell.api.run, numpy, R


def _matriz(P):
    _, _, np, _ = _api()
    a, m = P.uniform(0, 2 * math.pi), np.eye(4)
    m[0, 0] = m[1, 1] = math.cos(a)
    m[0, 1], m[1, 0] = -math.sin(a), math.sin(a)
    m[0, 3], m[1, 3] = P.uniform(-60, 60), P.uniform(-60, 60)
    return m


def aplicar(op, f, lado, c):  # c: contexto da montagem (ids STEP e GlobalId estáveis, mapa plano -> GlobalId, parâmetros P)
    _, api, _, _ = _api()
    t, P, G = op[0], c["P"], c["g"]
    W = f.by_guid(G.get(op[1], op[1])) if t not in ("lote", "parede", "pset_editar") and not t.startswith("lado") else None
    if t == "parede":
        w = api("root.create_entity", f, ifc_class="IfcWall", name=f"T04 {op[1]}")
        rep = api("geometry.add_wall_representation", f, context=f.by_id(c["corpo"]), length=P.uniform(1, 5), height=2.8, thickness=0.15)
        api("geometry.assign_representation", f, product=w, representation=rep)
        api("geometry.edit_object_placement", f, product=w, matrix=_matriz(P))
        api("material.assign_material", f, products=[w], type="IfcMaterialLayerSetUsage", material=f.by_id(c["camadas"]))
        api("spatial.assign_container", f, products=[w], relating_structure=f.by_guid(P.choice(c["andares"])))
        G[op[1]] = w.GlobalId
    elif t == "nome":
        api("attribute.edit_attributes", f, product=W, attributes={P.choice(("Name", "Description")): f"n{P.random()}"})
    elif t in ("pset_criar", "pset_editar"):
        ps = api("pset.add_pset", f, product=W, name=f"T04_{op[2]}") if t == "pset_criar" else f.by_guid(G[op[1]])
        api("pset.edit_pset", f, pset=ps, properties={"Valor": P.random(), "Texto": f"v{P.randint(0, 9)}"})
        G.setdefault(op[-1], ps.GlobalId)
    elif t == "mover":
        api("geometry.edit_object_placement", f, product=W, matrix=_matriz(P))
    elif t == "apagar":
        api("root.remove_product", f, product=W)
    elif t == "lote":  # padrão da sonda do T02 (0 diferenças ao desfazer)
        f.batch()
        for p in op[1]:
            api("root.remove_product", f, product=f.by_guid(G.get(p, p)))
        f.unbatch()
    elif t == "tipo":
        if op[3]:
            G[op[2]] = api("root.create_entity", f, ifc_class="IfcWallType", name=f"Tipo {op[2]}").GlobalId
        api("type.assign_type", f, related_objects=[W], relating_type=f.by_guid(G[op[2]]))
    elif t == "pavimento":
        atual = W.ContainedInStructure[0].RelatingStructure.GlobalId
        api("spatial.assign_container", f, products=[W], relating_structure=f.by_guid(next(a for a in c["andares"] if a != atual)))
    elif t == "lado_apagar":
        lado.apagar(op[1], op[2])
    else:
        obj = {"ifc_guids": [G.get(p, p) for p in op[3]], "texto": f"nota {P.random()}", "n": P.randint(0, 10**6), "ok": P.random() < 0.5}
        (lado.criar if t == "lado_criar" else lado.alterar)(op[1], op[2], obj)


class LadoEnsaio:  # lateral de ensaio, SÓ para a régua e a rodada crua de hoje (não é o contrato do `Lateral`)
    def __init__(s):
        s.d, s.hist, s.fut, s.ops = {}, [], [], []

    def _por(s, c, i, novo):
        s.ops.append(((c, i), s.d.get((c, i)), copy.deepcopy(novo)))
        s.d.pop((c, i)) if novo is None else s.d.__setitem__((c, i), copy.deepcopy(novo))

    def criar(s, c, i, o):
        s._por(c, i, o)
    alterar = criar

    def apagar(s, c, i):
        s._por(c, i, None)

    def canonico(s):
        return json.dumps({f"{c}/{i}": o for (c, i), o in s.d.items()}, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()

    def passo(s, de, para, volta):
        ops = de.pop()
        for k, velho, novo in (reversed(ops) if volta else ops):
            v = velho if volta else novo
            s.d.pop(k, None) if v is None else s.d.__setitem__(k, copy.deepcopy(v))
        para.append(ops)


def montar(base):  # arquivo livre (antes de qualquer Historico): camadas, 3 tipos, pset OBIM_Projeto; GlobalId novos em sequência fixa
    ifcopenshell, api, _, _ = _api()
    import ifcopenshell.util.representation as UR
    cont = itertools.count(1)
    ifcopenshell.guid.new = lambda: ifcopenshell.guid.compress("%032x" % next(cont))  # o caso restaura (fixture `_limpa`; no filho o processo acaba)
    f = ifcopenshell.open(base)
    ls = api("material.add_material_set", f, name="T04", set_type="IfcMaterialLayerSet")
    api("material.edit_layer", f, layer=api("material.add_layer", f, layer_set=ls, material=api("material.add_material", f, name="Concreto")),
        attributes={"LayerThickness": 0.15})
    obim = api("pset.add_pset", f, product=f.by_type("IfcProject")[0], name="OBIM_Projeto")
    api("pset.edit_pset", f, pset=obim, properties={"LadoId": "lado-t04", "Revisao": 1})
    c = {"P": random.Random(SEMENTE + 1), "corpo": UR.get_context(f, "Model", "Body", "MODEL_VIEW").id(), "camadas": ls.id(), "obim": obim.GlobalId,
         "andares": sorted(a.GlobalId for a in f.by_type("IfcBuildingStorey")), "g": {}}
    for i in range(3):
        c["g"][f"t{i}"] = api("root.create_entity", f, ifc_class="IfcWallType", name=f"Tipo t{i}").GlobalId
    return f, c, Plano(SEMENTE, [w.GlobalId for w in f.by_type("IfcWall")])


class Cru:  # ifcopenshell sem o módulo novo (hoje): begin/end/undo/redo nativos + LadoEnsaio
    def __init__(s, f, c):
        s.f, s.c, s.lado = f, c, LadoEnsaio()
        f.set_history_size(10**9)

    def tx(s, ops):
        s.f.begin_transaction()
        s.lado.ops = []
        for op in ops:
            aplicar(op, s.f, s.lado, s.c)
        s.f.end_transaction()
        s.lado.hist.append(s.lado.ops)
        s.lado.fut.clear()

    def desfazer(s):
        s.f.undo()
        s.lado.passo(s.lado.hist, s.lado.fut, True)

    def refazer(s):
        s.f.redo()
        s.lado.passo(s.lado.fut, s.lado.hist, False)

    pode_desfazer = property(lambda s: bool(s.f.history))
    ler = lambda s: contextlib.nullcontext(s.f)  # noqa: E731

    def foto(s):
        return R.foto(s.f, s.lado)


def igual(d, ref, onde):
    dif = R.diferencas(d.foto(), ref)
    assert not dif, f"semente {SEMENTE}, {onde}: {len(dif)} diferenças, primeiras: {dif[:8]}"


def dez_mil(d, plano):  # caso 1: fases A (aplica e fotografa a cada PONTO transações), B (desfaz tudo) e C (refaz tudo)
    t0, fotos = time.monotonic(), {0: d.foto()}
    n_tx = [0]

    def tx(ops):
        d.tx(ops)
        n_tx[0] += 1
        n_tx[0] % PONTO or fotos.__setitem__(n_tx[0], d.foto())
    cont, n, mistas = contar(plano, tx=tx)
    falta = {t: cont[t] for t in TIPOS if cont[t] < PISO_TIPO}
    assert not falta and mistas >= PISO_MISTAS, f"semente {SEMENTE}: pisos não atingidos {falta}, {mistas} mistas"
    with d.ler() as f:  # o modelo segue o plano (a simulação dos pisos vale para o modelo real)
        g = d.c["g"]
        assert sorted(w.GlobalId for w in f.by_type("IfcWall")) == sorted(g.get(p, p) for p in plano.paredes)
        assert sorted(p.GlobalId for p in f.by_type("IfcPropertySet") if p.Name.startswith("T04_")) == sorted(g[p] for p, _ in plano.psets)
    fim, t1, tmp = d.foto(), time.monotonic(), os.path.join(tempfile.mkdtemp(prefix="s05_t04_"), "fim.ifc")
    with d.ler() as f:  # R1 no modelo rico: gravar e reabrir não muda o conteúdo
        f.write(tmp)
        dif = R.diferencas(R.foto(f), R.foto(R.ifcopenshell.open(tmp)))
    assert not dif, f"semente {SEMENTE}: gravar e reabrir mudou o conteúdo: {dif[:8]}"
    for k in range(n, 0, -1):
        k in fotos and igual(d, fotos[k], f"desfazendo, ponto {k}")
        d.desfazer()
    igual(d, fotos[0], "desfazer tudo")
    assert not d.pode_desfazer
    for k in range(n):
        k in fotos and igual(d, fotos[k], f"refazendo, ponto {k}")
        d.refazer()
    igual(d, fim, "refazer tudo")
    try:
        import resource
        pico = f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB"
    except ImportError:  # Windows
        pico = "n/d"
    print(f"\nMEDIDA {type(d).__name__}: {dict(cont)}; {n} transações, {mistas} mistas; A {t1 - t0:.0f} s, total {time.monotonic() - t0:.0f} s; pico {pico}")


def rodar_filho(arquivo, caso, base):  # o `@AINDA_NAO` fica no processo de fora; o filho roda o caso sem marca
    env = dict(os.environ, OBIM_S05_T04_DENTRO="1", OBIM_S05_T04_BASE=base)
    cmd = [sys.executable, "-m", "pytest", "-q", "-s", "-rsxX", "-p", "no:cacheprovider", f"{arquivo}::test_{caso}"]
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, cwd=str(os.path.dirname(os.path.dirname(os.path.abspath(arquivo)))), env=env, capture_output=True, text=True, timeout=5400)
    except subprocess.TimeoutExpired:
        pytest.fail(f"caso {caso} (semente {SEMENTE}): o pytest filho passou de 5400 s; levar ao líder, nunca baixar o número")
    saida, fim = r.stdout + r.stderr, (r.stdout.strip().splitlines() or [""])[-1]  # o stderr pode ter aviso do ifcopenshell depois do resumo
    print("\n".join(x for x in saida.splitlines() if "MEDIDA" in x) + f"\n{caso}: {time.monotonic() - t0:.0f} s no filho")
    if r.returncode == 0 and " passed" in fim and not any(x in fim for x in ("skipped", "xfail", "xpass", "error")):
        return
    if r.returncode == 0 and "skipped" in fim and " passed" not in fim:
        R.pular(f"caso {caso} pulou no filho: {fim}", "OBIM_S05_OBRIGATORIO")
    pytest.fail(f"caso {caso} (semente {SEMENTE}): pytest filho com código {r.returncode}\n{saida[-4000:]}")
