# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apoio do oráculo do fluxo B, parte 1 (S04-T13, tests/test_s04_fluxo_b_paredes.py; contrato em prototypes/s04/fluxo_b/CONTRATO.md):
assinatura de um IFC (só ifcopenshell, independente de A e de B), comparação com tolerância, adaptadores A e B e o roteiro passo a passo."""
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve()
RAIZ = AQUI.parent.parent
CONTRATO = RAIZ / "prototypes" / "s04" / "fluxo_b" / "CONTRATO.md"
sys.path[:0] = [str(RAIZ / "prototypes" / "s04" / "fluxo_a"), str(RAIZ / "app"), str(RAIZ / "prototypes"), str(RAIZ / "scripts"), str(AQUI.parent)]  # só a pasta do fluxo A (não prototypes/s04)
FIRE, TOL = "Pset_WallCommon.FireRating", 1e-6
CAMADAS = [0.02, 0.11, 0.02]
PAR = dict(tipo="PAR15", comprimento=4.0, altura=2.8, espessura=0.15)
# Geometria de apoio: o contrato deixa livre COMO ela é montada (compartilhar ou não ponto/direção, perfil retangular ou arbitrário, polilinha ou curva indexada);
# a geometria em si é conferida por create_shape e a ausência de sobras pela checagem de órfãs. Toda outra classe tem de bater em número com o fluxo A.
# Sem exceção (T11c): A e B criam 1 IfcMaterialLayerSetUsage e 1 relação de material por parede (e 1 relação por tipo); a contagem de TODA classe é comparada entre A e B.
# `materiais` segue sendo conferido à parte também (B sozinho: 1 uso por parede, 1 relação por parede e por tipo).
MATERIAL = {"IfcMaterialLayerSetUsage", "IfcRelAssociatesMaterial"}
LIVRES = {"IfcCartesianPoint", "IfcDirection", "IfcAxis2Placement2D", "IfcAxis2Placement3D", "IfcCartesianPointList2D", "IfcCartesianPointList3D", "IfcIndexedPolyCurve",
          "IfcPolyline", "IfcArbitraryClosedProfileDef", "IfcRectangleProfileDef"}
ALFABETO = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$")

def igual(a, b, p="", max_=6):  # lista de diferenças (tolerância 1e-6 nos números)
    if isinstance(a, dict) and isinstance(b, dict):
        d = [f"{p}: chaves só em A {sorted(set(a) - set(b), key=str)[:4]}, só em B {sorted(set(b) - set(a), key=str)[:4]}"] * (set(a) != set(b))
        for k in a.keys() & b.keys():
            d += igual(a[k], b[k], f"{p}/{k}", max_)
    elif isinstance(a, (list, tuple, np.ndarray)) and isinstance(b, (list, tuple, np.ndarray)):
        d = [f"{p}: tamanhos {len(a)} x {len(b)}"] if len(a) != len(b) else sum((igual(x, y, f"{p}[{i}]", max_) for i, (x, y) in enumerate(zip(a, b))), [])
    elif isinstance(a, float) or isinstance(b, float):
        d = [] if isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, abs_tol=TOL) else [f"{p}: {a!r} x {b!r}"]
    else:
        d = [] if a == b else [f"{p}: {a!r} x {b!r}"]
    return d[:max_]

def pontos_eixo(rep):
    it = rep.Items[0]
    return [list(map(float, p)) for p in (it.Points.CoordList if it.is_a("IfcIndexedPolyCurve") else [q.Coordinates for q in it.Points])]

def formas(f):  # id da parede -> (triângulos, canto mínimo, canto máximo, volume), no mundo
    import ifcopenshell.geom as G
    import ifcopenshell.util.shape as SH
    s = G.settings()
    s.set("use-world-coords", True)
    out = {}
    ws = f.by_type("IfcWall")
    it = G.iterator(s, f, 1, include=ws) if ws else None
    if it is not None and it.initialize():
        while True:
            sh = it.get()
            g = sh.geometry
            v = np.array(g.verts).reshape(-1, 3)
            out[sh.id] = (len(g.faces) // 3, v.min(0).tolist(), v.max(0).tolist(), float(SH.get_volume(g)))
            if not it.next():
                break
    return out

def guids(f):
    return [e.GlobalId for e in f.by_type("IfcRoot")]

def assinatura(caminho):  # tudo o que o contrato exige que A e B tenham igual; sem GlobalId (as paredes são achadas pela posição, pois os nomes se repetem)
    import ifcopenshell
    import ifcopenshell.util.element as E
    import ifcopenshell.util.placement as P
    f = ifcopenshell.open(str(caminho))
    forma = formas(f)
    par = lambda x: None if x is None else x.Name  # noqa: E731
    sig = {"esquema": f.schema, "classes": dict(Counter(e.is_a() for e in f if e.is_a() not in LIVRES)),
           "materiais": {c: len(f.by_type(c, include_subtypes=False)) for c in sorted(MATERIAL)},
           "orfas": sorted(e.is_a() for e in f if not e.is_a("IfcRoot") and not e.is_a("IfcRepresentationContext") and not f.get_inverse(e)),
           "nomes": {c: sorted(e.Name for e in f.by_type(c)) for c in ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey")},
           "agrega": sorted((r.RelatingObject.is_a(), r.RelatingObject.Name, o.is_a(), o.Name) for r in f.by_type("IfcRelAggregates") for o in r.RelatedObjects),
           "unidades": sorted(str((u.UnitType, u.Name, u.Prefix)) for u in f.by_type("IfcSIUnit")),
           "atribuicao": sorted(str((u.UnitType, u.Name)) for p in f.by_type("IfcProject") for u in p.UnitsInContext.Units),
           "contextos": sorted(str((c.ContextType, c.ContextIdentifier, getattr(c, "TargetView", None), (getattr(c, "ParentContext", None) or c).ContextType, getattr(c, "CoordinateSpaceDimension", None), getattr(c, "Precision", None)))
                               for c in f.by_type("IfcGeometricRepresentationContext")), "tipos": {}, "paredes": {}}
    for t in f.by_type("IfcWallType"):
        ls = E.get_material(t, should_inherit=False)
        sig["tipos"][t.Name] = dict(pred=t.PredefinedType, conjunto=ls.is_a() + ":" + str(ls.LayerSetName), camadas=[(c.Material.Name, c.LayerThickness) for c in ls.MaterialLayers], descricao=t.Description)
    for w in f.by_type("IfcWall"):
        m, us, tp, ct = P.get_local_placement(w.ObjectPlacement), E.get_material(w, should_inherit=False), E.get_type(w), E.get_container(w)
        reps = {r.RepresentationIdentifier: r for r in w.Representation.Representations}
        psets = {r.RelatingPropertyDefinition.Name: {p.Name: (p.is_a(), p.NominalValue.is_a(), p.NominalValue.wrappedValue) for p in r.RelatingPropertyDefinition.HasProperties}
                 for r in w.IsDefinedBy if r.is_a("IfcRelDefinesByProperties")}
        chave = tuple((np.round(m[:3, 3], 6) + 0.0).tolist())
        assert chave not in sig["paredes"], f"duas paredes na mesma posição {chave}"
        sig["paredes"][chave] = dict(nome=w.Name, objtype=w.ObjectType, pred=w.PredefinedType, tipo=par(tp), pavimento=par(ct), absoluta=w.ObjectPlacement.PlacementRelTo is None, matriz=m.round(9).tolist(),
                                     uso=None if us is None else [us.is_a(), us.ForLayerSet.LayerSetName, getattr(us, "LayerSetDirection", None), getattr(us, "DirectionSense", None), getattr(us, "OffsetFromReferenceLine", None),
                                                                  [(c.Material.Name, c.LayerThickness) for c in us.ForLayerSet.MaterialLayers]],
                                     reps=sorted((i, r.RepresentationType, r.ContextOfItems.ContextIdentifier, [x.is_a() for x in r.Items] if i == "Body" else len(r.Items)) for i, r in reps.items()),
                                     altura=reps["Body"].Items[0].Depth if "Body" in reps else None, eixo=pontos_eixo(reps["Axis"]) if "Axis" in reps else None, psets=psets, forma=forma.get(w.id()))
    return sig

def validar(caminho):  # (erros do ifcopenshell.validate com regras EXPRESS), nível comparado em minúsculas
    import ifcopenshell
    import ifcopenshell.validate as V
    lg = V.json_logger()
    V.validate(ifcopenshell.open(str(caminho)), lg, express_rules=True)
    return [str(s.get("message"))[:160] for s in lg.statements if str(s.get("level")).lower() == "error"]

def alfabeto_ok(g):
    return isinstance(g, str) and len(g) == 22 and set(g) <= ALFABETO and g[0] in "0123"  # 128 bits em 22 caracteres: o 1o vale 0 a 3

# ---------- adaptadores: o mesmo roteiro dos dois lados ----------
class Fluxo:
    def __init__(s, pasta):
        s.pasta, s.ws, s.tipo, s.n = Path(pasta), [], None, 0

    def rodar(s, nome, /, **kw):  # alvo = índice na ordem de criação das paredes (inclusive as desfeitas); devolve a lista de GlobalIds
        if "alvo" in kw:
            kw["alvo"] = s.tipo if kw["alvo"] == "tipo" else s.ws[kw["alvo"]]
        r = s.chamar(nome, kw)
        if nome == "criar_tipo":
            s.tipo = r[0]
        elif nome in ("criar_parede", "criar_paredes_lote"):
            s.ws += r
        return r

class FluxoAd(Fluxo):  # fluxo A, sem janela (o oráculo do fluxo A é o da T11)
    def __init__(s, pasta):
        import fluxo_a
        super().__init__(pasta)
        s.f = fluxo_a.FluxoA(None, janela=False, saida=s.pasta)

    def chamar(s, nome, kw):
        return s.f.executar({"cmd": nome, **kw})

    def ultimo(s):
        return {k: list(s.f.ultimo[k]) for k in ("criados", "alterados", "apagados", "geometria")}

    def pilhas(s):
        return len(s.f.historico), len(s.f._refazer)

    def gravar(s):
        s.n += 1
        s.f.executar({"cmd": "gravar", "arquivo": str(s.pasta / f"a{s.n}.ifc")})
        return s.pasta / f"a{s.n}.ifc"

class FluxoBd(Fluxo):  # a biblioteca C++ pelo módulo nanobind
    def __init__(s, pasta, mod):
        super().__init__(pasta)
        s.b = mod.Paredes()

    def chamar(s, nome, kw):
        return list(getattr(s.b, nome)(**kw))

    def ultimo(s):
        u = s.b.ultimo()
        return {k: list(u[k]) for k in ("criados", "alterados", "apagados", "geometria")}

    def pilhas(s):
        return s.b.pode_desfazer(), s.b.pode_refazer()

    def gravar(s):
        s.n += 1
        s.b.gravar(str(s.pasta / f"b{s.n}.ifc"))
        return s.pasta / f"b{s.n}.ifc"

# ---------- o roteiro curto do cartão (tipo, 20 paredes, edições, desfazer 3, gravar) e a continuação ----------
def roteiro():
    p = [("criar_tipo", dict(nome="PAR15", camadas_m=CAMADAS))] + [("criar_parede", dict(PAR))] * 20
    p += [("editar_propriedades", dict(alvo=i, nome="Parede ção ✓-3" if i == 3 else f"Parede R-{i}", propriedades={FIRE: "R60"})) for i in range(5)]
    p += [("mudar_comprimento", dict(alvo=i, comprimento=5.0)) for i in range(5, 10)]
    p += [("editar_propriedades", dict(alvo=0, propriedades={FIRE: "R120"}))]  # pset já existe: edita no lugar
    p += [("editar_propriedades", dict(alvo=10, nome="Muro 10")), ("mudar_comprimento", dict(alvo=11, comprimento=6.5)), ("editar_propriedades", dict(alvo=12, propriedades={FIRE: "R90"}))]
    p += [("desfazer", {})] * 3 + [("#curto", {})]  # fim do roteiro do cartão (o IFC gravado aqui é o "IFC do roteiro curto")
    p += [("refazer", {}), ("criar_parede", dict(PAR)), ("refazer", {}), ("desfazer", {}), ("criar_parede", dict(PAR)),  # refazer vazio; a grade segue andando
          ("criar_paredes_lote", dict(PAR, quantidade=60)), ("desfazer", {}), ("refazer", {}), ("desfazer", {}), ("refazer", {}), ("#desfazer_tudo", {})]
    return p

def percorrer(a, b, passos):  # executa nos dois, grava e compara depois de CADA passo; devolve [(rótulo, [diferenças])] e as assinaturas de B nos marcos
    out, marcos, mapa = [], {}, {}

    visto = Counter()  # validate com regras EXPRESS leva ~1 s por IFC: valida B nos marcos e nas 2 primeiras vezes de cada tipo de passo (A é validado na sentinela)

    def conferir(rotulo, ra, rb, tipo=None):
        ua, ub = a.ultimo(), b.ultimo()  # antes de gravar (o comando gravar do fluxo A zera o `ultimo`)
        pa, pb = a.gravar(), b.gravar()
        sa, sb = assinatura(pa), assinatura(pb)
        d = igual(sa, sb, "ifc")  # inclusive "classes" (sem exceção de material) e "materiais" (A e B iguais)
        nw, nt = len(sb["paredes"]), len(sb["tipos"])
        d += [f"B: usos de camadas/relações de material {sb['materiais']} (esperado 1 uso por parede e 1 relação por parede e por tipo: {nw}, {nw + nt})"] * (sb["materiais"] != {"IfcMaterialLayerSetUsage": nw, "IfcRelAssociatesMaterial": nw + nt})
        d += [f"A: usos de camadas/relações de material {sa['materiais']} (esperado 1 uso por parede e 1 relação por parede e por tipo: {nw}, {nw + nt}; T11c)"] * (sa["materiais"] != {"IfcMaterialLayerSetUsage": nw, "IfcRelAssociatesMaterial": nw + nt})
        mapa.update({gb: ga for ga, gb in zip(a.ws + [a.tipo], b.ws + [b.tipo])})
        if ra is not None:  # nos marcos não houve comando (o gravar do fluxo A zera o `ultimo`)
            d += igual(ua, {k: [mapa.get(g, g) for g in v] for k, v in ub.items()}, "ultimo") + igual(ra, [mapa.get(g, g) for g in rb], "retorno")
        d += igual(a.pilhas(), b.pilhas(), "pilhas (desfazer, refazer)")
        visto[tipo] += 1
        d += [f"B: {e}" for e in validar(pb)[:3]] if tipo is None or visto[tipo] <= 2 else []
        d += [f"B: sobra de entidade solta {sb['orfas']}"] * bool(sb["orfas"]) + [f"B: GlobalId inválido ou repetido {g}" for g in guids_ruins(pb)[:3]]
        out.append((rotulo, d))
        return sb

    marcos["inicio"] = conferir("início", None, None)
    for i, (nome, kw) in enumerate(passos):
        if nome.startswith("#"):
            if nome == "#desfazer_tudo":  # volta ao começo: o IFC tem de ser o do início
                while a.pilhas()[0]:
                    conferir(f"desfazer final {a.pilhas()[0]}", a.rodar("desfazer"), b.rodar("desfazer"), "desfazer final")
            marcos[nome[1:]] = conferir(nome[1:], None, None)
            continue
        ra, rb = a.rodar(nome, **kw), b.rodar(nome, **kw)
        marcos[f"passo{i}"] = conferir(f"{i}: {nome} {({k: v for k, v in kw.items() if k != 'propriedades'})}", ra, rb, nome)
    return out, marcos

def guids_ruins(caminho):
    import ifcopenshell
    g = guids(ifcopenshell.open(str(caminho)))
    return [x for x in g if not alfabeto_ok(x)] + [x for x, n in Counter(g).items() if n > 1]
