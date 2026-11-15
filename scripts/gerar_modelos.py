# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera 5 modelos IFC4 deterministicos e seus manifestos JSON, sem acesso a rede."""
import argparse
import hashlib
import json
import math
import uuid
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import numpy as np

NOMES = ("casa-terrea", "sobrado", "moveis-repetidos", "parede-curva", "laje-com-furo")
_NS = uuid.UUID("a3c19f2e-58d4-4c7b-9e6a-2b4d8f0e1a73")
_DATA_ACESSO = "2026-11-15"
_DATA_HORA_IFC = "2000-01-01T00:00:00"
_VERSAO = "1.0.0"
_run = ifcopenshell.api.run


def _guid(chave: str) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(_NS, chave).hex)


def _mat(x: float = 0.0, y: float = 0.0, z: float = 0.0, graus: float = 0.0) -> np.ndarray:
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return np.array([[c, -s, 0.0, x], [s, c, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]], dtype=float)


def _ent(f, cls: str, nome: str):
    return _run("root.create_entity", f, ifc_class=cls, name=nome)


def _novo(nome_proj: str):
    f = _run("project.create_file", version="IFC4")
    proj = _ent(f, "IfcProject", nome_proj)
    _run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    ctx = _run("context.add_context", f, context_type="Model")
    corpo = _run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    terreno, predio = _ent(f, "IfcSite", "Terreno"), _ent(f, "IfcBuilding", "Edificacao")
    _run("aggregate.assign_object", f, products=[terreno], relating_object=proj)
    _run("aggregate.assign_object", f, products=[predio], relating_object=terreno)
    return f, corpo, predio


def _andar(f, predio, nome: str, elevacao: float):
    a = _ent(f, "IfcBuildingStorey", nome)
    a.Elevation = float(elevacao)
    _run("aggregate.assign_object", f, products=[a], relating_object=predio)
    return a


def _colocar(f, prod, rep, m: np.ndarray, andar=None) -> None:
    _run("geometry.assign_representation", f, product=prod, representation=rep)
    _run("geometry.edit_object_placement", f, product=prod, matrix=m)
    if andar is not None:
        _run("spatial.assign_container", f, products=[prod], relating_structure=andar)


def _laje(f, corpo, andar, nome: str, larg: float, prof: float, esp: float, z: float):
    s = _ent(f, "IfcSlab", nome)
    rep = _run("geometry.add_slab_representation", f, context=corpo, depth=esp, polyline=[(0.0, 0.0), (larg, 0.0), (larg, prof), (0.0, prof)])
    _colocar(f, s, rep, _mat(z=z), andar)
    return s


def _paredes_caixa(f, corpo, andar, larg: float, prof: float, alt: float, esp: float, z: float = 0.0, suf: str = ""):
    specs = (("Sul", larg, 0.0, 0.0, 0.0), ("Leste", prof, larg, 0.0, 90.0), ("Norte", larg, larg, prof, 180.0), ("Oeste", prof, 0.0, prof, 270.0))
    res = {}
    for lado, comp, x, y, ang in specs:
        p = _ent(f, "IfcWall", f"Parede {lado}{suf}")
        rep = _run("geometry.add_wall_representation", f, context=corpo, length=comp, height=alt, thickness=esp)
        m = _mat(x, y, z, ang)
        _colocar(f, p, rep, m, andar)
        res[lado] = (p, m)
    return res


def _build_casa_terrea(f, corpo, predio):
    larg, prof, alt, esp, esp_l = 10.0, 6.0, 2.8, 0.15, 0.15
    andar = _andar(f, predio, "Terreo", 0.0)
    _laje(f, corpo, andar, "Piso", larg, prof, esp_l, -esp_l)
    paredes = _paredes_caixa(f, corpo, andar, larg, prof, alt, esp)
    for lado, n_v, n_e, cls, l_v, a_v, x_l, z_l in (
        ("Sul", "Vao Porta", "Porta 1", "IfcDoor", 0.9, 2.1, 2.0, 0.0),
        ("Sul", "Vao Janela 1", "Janela 1", "IfcWindow", 1.5, 1.2, 6.0, 0.9),
        ("Norte", "Vao Janela 2", "Janela 2", "IfcWindow", 1.5, 1.2, 4.0, 0.9),
    ):
        parede, m_p = paredes[lado]
        vao = _ent(f, "IfcOpeningElement", n_v)
        rep_v = _run("geometry.add_slab_representation", f, context=corpo, depth=a_v,
                     polyline=[(0.0, -0.05), (l_v, -0.05), (l_v, esp + 0.05), (0.0, esp + 0.05)])
        m_v = m_p @ _mat(x=x_l, z=z_l)
        _colocar(f, vao, rep_v, m_v)
        _run("feature.add_feature", f, feature=vao, element=parede)
        esq = _ent(f, cls, n_e)
        fn = "geometry.add_door_representation" if cls == "IfcDoor" else "geometry.add_window_representation"
        _colocar(f, esq, _run(fn, f, context=corpo, overall_width=l_v, overall_height=a_v), m_v, andar)
        _run("feature.add_filling", f, opening=vao, element=esq)
    return ({"IfcWall": 4, "IfcSlab": 1, "IfcDoor": 1, "IfcWindow": 2, "IfcOpeningElement": 3, "IfcBuildingStorey": 1},
            {"area_piso_m2": larg * prof, "pe_direito_m": alt, "largura_m": larg, "profundidade_m": prof},
            ["planta", "aberturas"], "Casa terrea 10x6 m com 1 porta, 2 janelas e vaos.")


def _build_sobrado(f, corpo, predio):
    larg, prof, alt, esp, esp_l = 10.0, 6.0, 2.8, 0.15, 0.2
    elev_sup = alt + esp_l
    terreo, superior = _andar(f, predio, "Terreo", 0.0), _andar(f, predio, "Superior", elev_sup)
    for idx, (andar, z_p, z_l) in enumerate(((terreo, 0.0, -esp_l), (superior, elev_sup, alt))):
        _laje(f, corpo, andar, f"Laje {idx + 1}", larg, prof, esp_l, z_l)
        _paredes_caixa(f, corpo, andar, larg, prof, alt, esp, z=z_p, suf=f" P{idx + 1}")
    degraus, piso_d = 15, 0.25
    espelho = elev_sup / degraus
    pts = [(0.0, 0.0), (degraus * piso_d, 0.0)]
    for i in range(degraus, 0, -1):
        pts.extend([(i * piso_d, i * espelho), ((i - 1) * piso_d, i * espelho)])
    pts.append((0.0, 0.0))
    curva = f.create_entity("IfcIndexedPolyCurve", Points=f.create_entity("IfcCartesianPointList2D", CoordList=pts), SelfIntersect=False)
    perfil = f.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=curva)
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, ExtrudedDirection=f.create_entity("IfcDirection", (0.0, 0.0, 1.0)), Depth=1.0)
    rep_esc = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    m_esc = np.array([[1.0, 0.0, 0.0, 1.5], [0.0, 0.0, -1.0, 2.5], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]], dtype=float)
    _colocar(f, _ent(f, "IfcStair", "Escada"), rep_esc, m_esc, terreo)
    zb, zc = elev_sup + alt, elev_sup + alt + 1.5
    vt = [[(0.0, 0.0, zb), (larg, 0.0, zb), (larg, prof, zb), (0.0, prof, zb), (3.0, 3.0, zc), (7.0, 3.0, zc)]]
    ft = [[[0, 1, 5, 4], [1, 2, 5], [2, 3, 4, 5], [3, 0, 4], [0, 3, 2, 1]]]
    rep_t = _run("geometry.add_mesh_representation", f, context=corpo, vertices=vt, faces=ft)
    _colocar(f, _ent(f, "IfcRoof", "Telhado 4 Aguas"), rep_t, _mat(), superior)
    return ({"IfcBuildingStorey": 2, "IfcWall": 8, "IfcSlab": 2, "IfcStair": 1, "IfcRoof": 1},
            {"pe_direito_m": alt, "elevacao_pavimento_superior_m": elev_sup, "aguas_telhado": 4},
            ["planta", "corte", "escada", "telhado"], "Sobrado de 2 pavimentos com escada e telhado de 4 aguas.")


def _build_moveis_repetidos(f, corpo, predio):
    qtd, andar = 8, _andar(f, predio, "Terreo", 0.0)
    tipo = _ent(f, "IfcFurnitureType", "Cadeira Padrao")
    rep = _run("geometry.add_slab_representation", f, context=corpo, depth=0.8, polyline=[(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)])
    _run("geometry.assign_representation", f, product=tipo, representation=rep)
    for i in range(qtd):
        m = _ent(f, "IfcFurniture", f"Movel {i + 1}")
        _run("geometry.edit_object_placement", f, product=m, matrix=_mat(x=(i % 4) * 1.5, y=(i // 4) * 1.5))
        _run("spatial.assign_container", f, products=[m], relating_structure=andar)
        _run("type.assign_type", f, related_objects=[m], relating_type=tipo)
    return ({"IfcBuildingStorey": 1, "IfcFurniture": qtd, "IfcRepresentationMap": 1, "IfcMappedItem": qtd},
            {"quantidade_moveis": qtd}, ["planta", "itens-mapeados"], "8 moveis compartilhando uma unica IfcRepresentationMap.")


def _build_parede_curva(f, corpo, predio):
    raio, angulo, alt, esp = 5.0, 90.0, 2.8, 0.2
    flecha = round(raio * (1.0 - math.cos(math.radians(angulo) / 2.0)), 6)
    andar = _andar(f, predio, "Terreo", 0.0)
    r_in, r_out, ang_rad = raio - esp / 2.0, raio + esp / 2.0, math.radians(angulo)
    angs = (0.0, ang_rad / 2.0, ang_rad)
    pts = [(r_out * math.cos(a), r_out * math.sin(a)) for a in angs] + [(r_in * math.cos(a), r_in * math.sin(a)) for a in reversed(angs)]
    segs = [f.create_entity("IfcArcIndex", (1, 2, 3)), f.create_entity("IfcLineIndex", (3, 4)),
            f.create_entity("IfcArcIndex", (4, 5, 6)), f.create_entity("IfcLineIndex", (6, 1))]
    curva = f.create_entity("IfcIndexedPolyCurve", Points=f.create_entity("IfcCartesianPointList2D", CoordList=pts), Segments=segs, SelfIntersect=False)
    perfil = f.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=curva)
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, ExtrudedDirection=f.create_entity("IfcDirection", (0.0, 0.0, 1.0)), Depth=alt)
    rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    _colocar(f, _ent(f, "IfcWall", "Parede Curva"), rep, _mat(), andar)
    return ({"IfcBuildingStorey": 1, "IfcWall": 1}, {"raio_m": raio, "angulo_graus": angulo, "flecha_m": flecha, "altura_m": alt},
            ["planta", "geometria-curva"], "Parede curva em arco (raio 5 m, 90 graus, altura 2,8 m).")


def _build_laje_com_furo(f, corpo, predio):
    larg, prof, esp, fl, fp = 8.0, 6.0, 0.2, 2.0, 1.5
    andar = _andar(f, predio, "Terreo", 0.0)
    laje = _laje(f, corpo, andar, "Laje com Furo", larg, prof, esp, 0.0)
    vao = _ent(f, "IfcOpeningElement", "Furo na Laje")
    rep_v = _run("geometry.add_slab_representation", f, context=corpo, depth=esp + 0.2, polyline=[(0.0, 0.0), (fl, 0.0), (fl, fp), (0.0, fp)])
    _colocar(f, vao, rep_v, _mat(x=3.0, y=2.0, z=-0.1))
    _run("feature.add_feature", f, feature=vao, element=laje)
    return ({"IfcBuildingStorey": 1, "IfcSlab": 1, "IfcOpeningElement": 1},
            {"area_bruta_m2": larg * prof, "area_furo_m2": fl * fp, "area_liquida_m2": larg * prof - fl * fp},
            ["planta", "furo-em-laje"], "Laje 8x6 m com furo retangular de 2x1,5 m via IfcRelVoidsElement.")


_BUILDERS = {"casa-terrea": _build_casa_terrea, "sobrado": _build_sobrado, "moveis-repetidos": _build_moveis_repetidos,
             "parede-curva": _build_parede_curva, "laje-com-furo": _build_laje_com_furo}


def _finalizar_e_gravar(f, nome: str, destino: Path) -> tuple[str, int]:
    for ua in f.by_type("IfcUnitAssignment"):
        ua.Units = sorted(ua.Units, key=lambda u: u.id())
    for cls, attr in (("IfcRelAggregates", "RelatedObjects"), ("IfcRelContainedInSpatialStructure", "RelatedElements"), ("IfcRelDefinesByType", "RelatedObjects")):
        for rel in f.by_type(cls):
            setattr(rel, attr, sorted(getattr(rel, attr), key=lambda o: o.id()))
    for e in f:
        if hasattr(e, "GlobalId") and e.GlobalId:
            e.GlobalId = _guid(f"{nome}:{e.is_a()}#{e.id()}")
    f.header.file_name.time_stamp = _DATA_HORA_IFC
    f.write(str(destino))
    dados = destino.read_bytes()
    return hashlib.sha256(dados).hexdigest(), len(dados)


def gerar_todos(pasta_corpus="corpus", pasta_manifestos="corpus/manifestos") -> list[Path]:
    """Gera os 5 modelos IFC4 em `pasta_corpus` e os manifestos em `pasta_manifestos`."""
    dir_corpus, dir_manif = Path(pasta_corpus), Path(pasta_manifestos)
    dir_corpus.mkdir(parents=True, exist_ok=True)
    dir_manif.mkdir(parents=True, exist_ok=True)
    gerados, prog = [], f"IfcOpenShell {ifcopenshell.version}"
    for nome in NOMES:
        f, corpo, predio = _novo(nome)
        contagens, valores, cobre, obs = _BUILDERS[nome](f, corpo, predio)
        arq = dir_corpus / f"{nome}.ifc"
        sha, tam = _finalizar_e_gravar(f, nome, arq)
        manif = {"nome": nome, "origem": "scripts/gerar_modelos.py", "versao_ou_commit": _VERSAO,
                 "data_acesso": _DATA_ACESSO, "sha256": sha, "tamanho_bytes": tam, "licenca": "propria",
                 "atribuicao": "OpenBIM Studio (AGPL-3.0-or-later)", "pode_ir_no_git": "nao", "esquema": "IFC4",
                 "programa_de_origem": prog, "contagens": contagens, "valores_conhecidos": valores, "cobre": cobre, "observacoes": obs}
        (dir_manif / f"{nome}.json").write_text(json.dumps(manif, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        gerados.append(arq)
    return gerados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera os 5 modelos IFC4 proprios do corpus e seus manifestos.")
    parser.add_argument("pasta_corpus", nargs="?", default="corpus")
    parser.add_argument("pasta_manifestos", nargs="?", default="corpus/manifestos")
    args = parser.parse_args(argv)
    gerar_todos(args.pasta_corpus, args.pasta_manifestos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
