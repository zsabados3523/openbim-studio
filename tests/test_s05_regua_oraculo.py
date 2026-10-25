# SPDX-License-Identifier: AGPL-3.0-or-later
"""Autoteste da régua de comparação por conteúdo (`tests/s05_conteudo_aux.py`; R1 a R4) e mutantes de
estrutura (cada um tem de aparecer, e sumir ao desfazer). Vale já (sem `@AINDA_NAO`). Os mutantes por tipo de operação do gerador de transações ficam em
`tests/test_s05_t04_gerador_oraculo.py`. Não editar."""
import math

import s05_conteudo_aux as R
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)


def api(*a, **k):
    import ifcopenshell.api
    return ifcopenshell.api.run(*a, **k)


def _abrir(base):
    R.exigir()
    return R.ifcopenshell.open(base)


def _cadeia(f, e):  # donos com GlobalId e quantas entidades sem GlobalId mudam de forma quando `e` muda
    sem, donos, fila = set(), set(), [e]
    while fila:
        x = fila.pop()
        if x.is_a("IfcRoot"):
            donos.add(x.GlobalId)
        elif x.id() not in sem:
            sem.add(x.id())
            fila += list(f.get_inverse(x))
    return donos, len(sem)


def _parte(dif):  # (GlobalIds citados, linhas do multiconjunto sem GlobalId)
    return {x.split(" ")[0] for x in dif if not x.startswith(("sem GlobalId", "lateral"))}, sum(x.startswith("sem GlobalId") for x in dif)


def _parede_com_ponto_proprio(f):  # parede cujo ponto de posição só ela usa e tem 3 coordenadas diferentes
    return [w for w in f.by_type("IfcWall") if len(f.get_inverse(p := w.ObjectPlacement.RelativePlacement.Location)) == 1
            and len(set(p.Coordinates)) == 3]


def test_regua_r1_gravar_reabrir_e_ids_novos(base_ifc, tmp_path):
    f = _abrir(base_ifc)
    api("pset.edit_pset", f, pset=api("pset.add_pset", f, product=f.by_type("IfcWall")[3], name="R1"), properties={"Valor": 0.1, "T": "ç"})
    a = R.foto(f)
    f.write(str(tmp_path / "b.ifc"))
    assert R.diferencas(a, R.foto(R.ifcopenshell.open(str(tmp_path / "b.ifc")))) == []
    g = R.ifcopenshell.file(schema=f.schema_identifier)
    lixo = g.createIfcCartesianPoint((9.0, 9.0, 9.0))  # desloca os ids da cópia
    for e in f.by_type("IfcRoot"):
        g.add(e)
    g.remove(lixo)
    assert sum(g.by_guid(e.GlobalId).id() == e.id() for e in f.by_type("IfcRoot")) < len(f.by_type("IfcRoot")) / 2, "a cópia não trocou os ids"
    assert R.diferencas(a, R.foto(g)) == []


def test_regua_r2_granularidade(base_ifc):
    f = _abrir(base_ifc)
    w = _parede_com_ponto_proprio(f)[0]
    ps = api("pset.add_pset", f, product=w, name="R2")
    api("pset.edit_pset", f, pset=ps, properties={"Valor": 0.5})
    a = R.foto(f)
    w.Name = "outro nome"
    assert _parte(R.diferencas(a, R.foto(f))) == ({w.GlobalId}, 0)
    a, pv = R.foto(f), ps.HasProperties[0]
    api("pset.edit_pset", f, pset=ps, properties={"Valor": 0.125})
    assert _parte(R.diferencas(a, R.foto(f))) == ({ps.GlobalId}, 2 * _cadeia(f, pv)[1]) == ({ps.GlobalId}, 2)
    a, pt = R.foto(f), w.ObjectPlacement.RelativePlacement.Location
    pt.Coordinates = (pt.Coordinates[0] + 1.0,) + tuple(pt.Coordinates[1:])
    donos, n = _cadeia(f, pt)
    assert _parte(R.diferencas(a, R.foto(f))) == (donos, 2 * n) and donos == {w.GlobalId} and n >= 3


def test_regua_r3_desfazer_pela_metade_aparece(base_ifc):
    f = _abrir(base_ifc)
    f.set_history_size(10)
    w, a = f.by_type("IfcWall")[0], R.foto(f)
    for tirar in (False, True):  # sem tirar: igual (controle); tirando a última edição do Transaction: diferente
        f.begin_transaction()
        w.Name, w.Description = "A", "B"
        f.end_transaction()
        tirar and f.history[-1].operations.pop()
        f.undo()
        assert bool(R.diferencas(a, R.foto(f))) == tirar
        w.Description = None


def test_regua_r4_set_e_list(base_ifc):
    f = _abrir(base_ifc)
    a, rel = R.foto(f), f.by_type("IfcRelContainedInSpatialStructure")[0]
    rel.RelatedElements = tuple(reversed(rel.RelatedElements))
    assert R.diferencas(a, R.foto(f)) == [], "ordem de SET deu diferença"
    pt = _parede_com_ponto_proprio(f)[0].ObjectPlacement.RelativePlacement.Location
    pt.Coordinates = (pt.Coordinates[1], pt.Coordinates[0], pt.Coordinates[2])
    assert R.diferencas(a, R.foto(f)), "ordem de LIST não deu diferença"


def test_regua_pega_cada_mutante_de_estrutura(base_ifc):  # cada mutação feita numa transação nativa e desfeita: diferença, depois 0 diferenças
    f = _abrir(base_ifc)
    f.set_history_size(100)
    w, w2 = _parede_com_ponto_proprio(f)[:2]
    pt, dr, ag = w.ObjectPlacement.RelativePlacement.Location, f.by_type("IfcDirection")[0], f.by_type("IfcRelAggregates")[-1]
    assert len(ag.RelatedObjects) >= 2 and w.Description is None
    a = R.foto(f)
    mut = {"texto": (lambda: setattr(w, "Name", w.Name + "x"), 1), "real no próximo float": (lambda: setattr(pt, "Coordinates", (math.nextafter(
        pt.Coordinates[0], math.inf),) + tuple(pt.Coordinates[1:])), 1), "None vira valor": (lambda: setattr(w, "Description", "d"), 1),
        "referência trocada": (lambda: setattr(w, "ObjectPlacement", w2.ObjectPlacement), 1), "ordem de LIST": (lambda: setattr(pt, "Coordinates", (
            pt.Coordinates[1], pt.Coordinates[0], pt.Coordinates[2])), 1), "ordem de SET": (lambda: setattr(ag, "RelatedObjects", tuple(reversed(
                ag.RelatedObjects))), 0), "órfã nova": (lambda: f.createIfcCartesianPoint((1.5, 2.5, 3.5)), 1),
        "duplicada": (lambda: f.createIfcDirection(dr.DirectionRatios), 1), "sem GlobalId apagada": (lambda: f.remove(pt), 1),
        "GlobalId trocado": (lambda: setattr(w, "GlobalId", R.ifcopenshell.guid.new()), 1)}
    for nome, (fn, ve) in mut.items():
        f.begin_transaction()
        fn()
        f.end_transaction()
        assert bool(R.diferencas(a, R.foto(f))) == bool(ve), f"mutante {nome!r}: esperado {'diferença' if ve else 'igual'}"
        f.undo()
        assert R.diferencas(a, R.foto(f)) == [], f"mutante {nome!r}: desfeito e ainda diferente"
