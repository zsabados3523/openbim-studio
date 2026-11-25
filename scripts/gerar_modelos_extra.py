# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera 2 modelos IFC4 extras deterministicos e seus manifestos JSON, sem acesso a rede."""
import argparse
import json
from pathlib import Path

import ifcopenshell

from gerar_modelos import (
    _DATA_ACESSO,
    _VERSAO,
    _andar,
    _colocar,
    _ent,
    _finalizar_e_gravar,
    _mat,
    _novo,
    _paredes_caixa,
    _run,
)

NOMES = ("estrutura-pilares-vigas", "paredes-com-camadas")


def _build_estrutura_pilares_vigas(f, corpo, predio):
    vao_x, vao_y, alt_pilar, sec_pilar = 6.0, 4.0, 3.0, 0.3
    larg_viga, alt_viga = 0.2, 0.4
    andar = _andar(f, predio, "Terreo", 0.0)

    perfil_pilar = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=sec_pilar, YDim=sec_pilar)
    rep_pilar = _run("geometry.add_profile_representation", f, context=corpo, profile=perfil_pilar, depth=alt_pilar)
    for idx, (cx, cy) in enumerate(((0.0, 0.0), (vao_x, 0.0), (vao_x, vao_y), (0.0, vao_y)), start=1):
        _colocar(f, _ent(f, "IfcColumn", f"Pilar P{idx}"), rep_pilar, _mat(x=cx, y=cy), andar)

    perfil_viga = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=larg_viga, YDim=alt_viga)
    comp_x, comp_y = vao_x - sec_pilar, vao_y - sec_pilar
    rep_x = _run(
        "geometry.add_profile_representation",
        f,
        context=corpo,
        profile=perfil_viga,
        depth=comp_x,
        placement_zx_axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    )
    rep_y = _run(
        "geometry.add_profile_representation",
        f,
        context=corpo,
        profile=perfil_viga,
        depth=comp_y,
        placement_zx_axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    )
    z_viga = alt_pilar - alt_viga / 2.0
    vigas = (
        ("Viga Sul", rep_x, sec_pilar / 2.0, 0.0, 0.0),
        ("Viga Norte", rep_x, sec_pilar / 2.0, vao_y, 0.0),
        ("Viga Oeste", rep_y, 0.0, sec_pilar / 2.0, 90.0),
        ("Viga Leste", rep_y, vao_x, sec_pilar / 2.0, 90.0),
    )
    for nome_v, rep_v, x, y, ang in vigas:
        _colocar(f, _ent(f, "IfcBeam", nome_v), rep_v, _mat(x=x, y=y, z=z_viga, graus=ang), andar)

    return (
        {"IfcColumn": 4, "IfcBeam": 4, "IfcBuildingStorey": 1},
        {
            "quantidade_pilares": 4,
            "quantidade_vigas": 4,
            "altura_pilar_m": alt_pilar,
            "vao_x_m": vao_x,
            "vao_y_m": vao_y,
            "secao_pilar_m": sec_pilar,
        },
        ["planta", "corte", "estrutura"],
        "Estrutura de 4 pilares (0,3x0,3 m, h=3,0 m) em vao 6x4 m e 4 vigas de topo (0,2x0,4 m).",
    )


def _build_paredes_com_camadas(f, corpo, predio):
    larg, prof, alt, esp = 5.0, 4.0, 2.8, 0.18
    andar = _andar(f, predio, "Terreo", 0.0)
    paredes = _paredes_caixa(f, corpo, andar, larg, prof, alt, esp)

    camadas = _run("material.add_material_set", f, name="Alvenaria Reboco Tijolo", set_type="IfcMaterialLayerSet")
    mat_reboco = _run("material.add_material", f, name="Reboco")
    mat_tijolo = _run("material.add_material", f, name="Tijolo")
    for mat, esp_c in ((mat_reboco, 0.02), (mat_tijolo, 0.14), (mat_reboco, 0.02)):
        camada = _run("material.add_layer", f, layer_set=camadas, material=mat)
        camada.LayerThickness = esp_c

    _run(
        "material.assign_material",
        f,
        products=[p for p, _ in paredes.values()],
        type="IfcMaterialLayerSet",
        material=camadas,
    )
    return (
        {"IfcWall": 4, "IfcMaterialLayerSet": 1, "IfcMaterialLayer": 3, "IfcBuildingStorey": 1},
        {"espessura_total_m": esp, "camadas": 3, "pe_direito_m": alt},
        ["planta", "corte", "composicao-de-parede"],
        "Caixa de 4 paredes 5x4 m (h=2,8 m, e=0,18 m) ligadas a um IfcMaterialLayerSet de 3 camadas.",
    )


_BUILDERS = {
    "estrutura-pilares-vigas": _build_estrutura_pilares_vigas,
    "paredes-com-camadas": _build_paredes_com_camadas,
}


def _ordenar_relacoes_materiais(f) -> None:
    for rel in f.by_type("IfcRelAssociatesMaterial"):
        rel.RelatedObjects = sorted(rel.RelatedObjects, key=lambda o: o.id())
    for ls in f.by_type("IfcMaterialLayerSet"):
        ls.MaterialLayers = sorted(ls.MaterialLayers, key=lambda c: c.id())


def gerar_todos(pasta_corpus="corpus", pasta_manifestos="corpus/manifestos") -> list[Path]:
    """Gera os 2 modelos IFC4 extras em `pasta_corpus` e os manifestos em `pasta_manifestos`."""
    dir_corpus, dir_manif = Path(pasta_corpus), Path(pasta_manifestos)
    dir_corpus.mkdir(parents=True, exist_ok=True)
    dir_manif.mkdir(parents=True, exist_ok=True)
    gerados, prog = [], f"IfcOpenShell {ifcopenshell.version}"
    for nome in NOMES:
        f, corpo, predio = _novo(nome)
        contagens, valores, cobre, obs = _BUILDERS[nome](f, corpo, predio)
        _ordenar_relacoes_materiais(f)
        arq = dir_corpus / f"{nome}.ifc"
        sha, tam = _finalizar_e_gravar(f, nome, arq)
        manif = {
            "nome": nome,
            "origem": "scripts/gerar_modelos_extra.py",
            "versao_ou_commit": _VERSAO,
            "data_acesso": _DATA_ACESSO,
            "sha256": sha,
            "tamanho_bytes": tam,
            "licenca": "propria",
            "atribuicao": "OpenBIM Studio (AGPL-3.0-or-later)",
            "pode_ir_no_git": "nao",
            "esquema": "IFC4",
            "programa_de_origem": prog,
            "contagens": contagens,
            "valores_conhecidos": valores,
            "cobre": cobre,
            "observacoes": obs,
        }
        (dir_manif / f"{nome}.json").write_text(
            json.dumps(manif, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        gerados.append(arq)
    return gerados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera os 2 modelos IFC4 extras do corpus e seus manifestos.")
    parser.add_argument("pasta_corpus", nargs="?", default="corpus")
    parser.add_argument("pasta_manifestos", nargs="?", default="corpus/manifestos")
    args = parser.parse_args(argv)
    gerar_todos(args.pasta_corpus, args.pasta_manifestos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
