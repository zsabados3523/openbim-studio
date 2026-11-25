# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera 5 modelos IFC com erros/casos de borda derivados da casa-terrea e seus manifestos JSON, sem acesso a rede."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import ifcopenshell

import gerar_modelos

NOMES = ("erro-vazio", "erro-truncado", "erro-milimetros", "erro-sem-geometria", "erro-nome-com-acentuação")
_DATA_ACESSO = "2026-11-15"
_DATA_HORA_IFC = "2000-01-01T00:00:00"
_VERSAO = "1.0.0"
_UNIDADE_M = "IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)"
_UNIDADE_MM = "IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)"
_CONTAGENS_CASA = {
    "IfcWall": 4,
    "IfcSlab": 1,
    "IfcDoor": 1,
    "IfcWindow": 2,
    "IfcOpeningElement": 3,
    "IfcBuildingStorey": 1,
}


def _gravar_ifc(f, destino: Path) -> bytes:
    """Ordena listas de relacoes e fixa timestamp antes de gravar para garantir determinismo."""
    for ua in f.by_type("IfcUnitAssignment"):
        ua.Units = sorted(ua.Units, key=lambda u: u.id())
    for cls, attr in (
        ("IfcRelAggregates", "RelatedObjects"),
        ("IfcRelContainedInSpatialStructure", "RelatedElements"),
        ("IfcRelDefinesByType", "RelatedObjects"),
    ):
        for rel in f.by_type(cls):
            setattr(rel, attr, sorted(getattr(rel, attr), key=lambda o: o.id()))
    f.header.file_name.time_stamp = _DATA_HORA_IFC
    f.write(str(destino))
    return destino.read_bytes()


def _montar_manifesto(
    nome: str,
    dados: bytes,
    esquema: str,
    contagens: dict,
    valores: dict,
    cobre: list[str],
    obs: str,
    prog: str,
) -> dict:
    """Monta o dicionario de manifesto com os 15 campos padrao do corpus."""
    return {
        "nome": nome,
        "origem": "scripts/gerar_modelos_erro.py",
        "versao_ou_commit": _VERSAO,
        "data_acesso": _DATA_ACESSO,
        "sha256": hashlib.sha256(dados).hexdigest(),
        "tamanho_bytes": len(dados),
        "licenca": "propria",
        "atribuicao": "OpenBIM Studio (AGPL-3.0-or-later)",
        "pode_ir_no_git": "nao",
        "esquema": esquema,
        "programa_de_origem": prog,
        "contagens": contagens,
        "valores_conhecidos": valores,
        "cobre": cobre,
        "observacoes": obs,
    }


def _gerar_caso(nome: str, ref_path: Path, ref_bytes: bytes, destino: Path) -> tuple[bytes, str, dict, dict, list[str], str]:
    """Gera um dos 5 arquivos de erro em `destino` e retorna seus metadados."""
    if nome == "erro-vazio":
        dados = b""
        destino.write_bytes(dados)
        return dados, "desconhecido", {}, {"motivo": "arquivo vazio"}, ["erro", "arquivo-vazio"], "Arquivo IFC vazio (0 bytes)."

    if nome == "erro-truncado":
        dados = ref_bytes[: len(ref_bytes) // 2]
        destino.write_bytes(dados)
        return (
            dados,
            "IFC4",
            {},
            {"bytes_originais": len(ref_bytes), "fracao_mantida": 0.5},
            ["erro", "arquivo-truncado"],
            "Metade inicial da casa-terrea.ifc, truncado antes de END-ISO-10303-21.",
        )

    if nome == "erro-milimetros":
        assert _UNIDADE_M in ref_bytes.decode("utf-8"), "casa-terrea mudou: ajuste _UNIDADE_M"
        texto = ref_bytes.decode("utf-8").replace(_UNIDADE_M, _UNIDADE_MM)
        dados = texto.encode("utf-8")  # bytes: write_text trocaria \n por \r\n no Windows
        destino.write_bytes(dados)
        return (
            dados,
            "IFC4",
            dict(_CONTAGENS_CASA),
            {"unidade_declarada": "MILLIMETRE", "fator_para_metro": 0.001, "largura_em_unidades": 10.0},
            ["erro", "unidade-milimetros"],
            "Casa-terrea com unidade linear declarada em milimetros mantendo valores numericos em metros.",
        )

    f = ifcopenshell.open(str(ref_path))
    if nome == "erro-sem-geometria":
        for prod in f.by_type("IfcProduct"):
            prod.Representation = None
        dados = _gravar_ifc(f, destino)
        return (
            dados,
            "IFC4",
            dict(_CONTAGENS_CASA),
            {"elementos_com_geometria": 0},
            ["erro", "sem-geometria"],
            "Casa-terrea sem representacao geometrica nos IfcProduct.",
        )

    if nome == "erro-nome-com-acentuação":
        nome_proj = "Residência São João"
        f.by_type("IfcProject")[0].Name = nome_proj
        dados = _gravar_ifc(f, destino)
        return (
            dados,
            "IFC4",
            dict(_CONTAGENS_CASA),
            {"nome_do_projeto": nome_proj},
            ["erro", "nome-acentuado"],
            "Casa-terrea com nome de arquivo e IfcProject.Name acentuados em UTF-8.",
        )

    raise ValueError(f"Modelo de erro desconhecido: {nome}")


def gerar_todos(pasta_corpus="corpus", pasta_manifestos="corpus/manifestos") -> list[Path]:
    """Gera os 5 arquivos de erro em `pasta_corpus` e os manifestos em `pasta_manifestos`."""
    dir_corpus, dir_manif = Path(pasta_corpus), Path(pasta_manifestos)
    dir_corpus.mkdir(parents=True, exist_ok=True)
    dir_manif.mkdir(parents=True, exist_ok=True)
    gerados, prog = [], f"IfcOpenShell {ifcopenshell.version}"

    with tempfile.TemporaryDirectory(prefix="gerar_erro_base_") as tmp_dir:
        base = Path(tmp_dir)
        gerar_modelos.gerar_todos(base / "corpus", base / "manifestos")
        ref_path = base / "corpus" / "casa-terrea.ifc"
        ref_bytes = ref_path.read_bytes()

        for nome in NOMES:
            arq = dir_corpus / f"{nome}.ifc"
            dados, esquema, contagens, valores, cobre, obs = _gerar_caso(nome, ref_path, ref_bytes, arq)
            manif = _montar_manifesto(nome, dados, esquema, contagens, valores, cobre, obs, prog)
            (dir_manif / f"{nome}.json").write_text(
                json.dumps(manif, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            gerados.append(arq)

    return gerados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera os 5 arquivos de erro derivados da casa-terrea e seus manifestos.")
    parser.add_argument("pasta_corpus", nargs="?", default="corpus")
    parser.add_argument("pasta_manifestos", nargs="?", default="corpus/manifestos")
    args = parser.parse_args(argv)
    gerar_todos(args.pasta_corpus, args.pasta_manifestos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
