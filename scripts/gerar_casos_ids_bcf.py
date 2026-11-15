# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gera casos deterministicos de IDS 1.0 e BCF 2.1/3.0 com seus manifestos JSON."""
import argparse
import json
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import ifcopenshell

_NS_UUID = uuid.UUID("7f4c2b1e-9d3a-4e8b-a612-0c5d8e3f9a41")
_NS_IDS = "http://standards.buildingsmart.org/IDS"
_DATA_ISO = "2026-11-15"
_DATA_HORA_BCF = "2026-11-15T00:00:00Z"
_AUTOR_BCF = "openbim-studio@example.org"
_ZIP_DATA = (1980, 1, 1, 0, 0, 0)

# (arquivo, modelo, titulo, passa, [(nome_spec, classe_ifc, attr, valor_ou_none, aplicaveis, passam)])
_CASOS_IDS = (
    (
        "casa-terrea-passa.ids",
        "casa-terrea",
        "Casa terrea - requisitos basicos de identificacao",
        True,
        (
            ("Paredes com Name preenchido", "IFCWALL", "Name", None, 4, 4),
            ("Porta com Name exato", "IFCDOOR", "Name", "Porta 1", 1, 1),
            ("Janelas com Name preenchido", "IFCWINDOW", "Name", None, 2, 2),
        ),
    ),
    (
        "casa-terrea-falha.ids",
        "casa-terrea",
        "Casa terrea - conferencia com falhas esperadas",
        False,
        (
            ("Paredes com Name preenchido", "IFCWALL", "Name", None, 4, 4),
            ("Paredes com Description preenchido", "IFCWALL", "Description", None, 4, 0),
            ("Janelas com Name Janela 1", "IFCWINDOW", "Name", "Janela 1", 2, 1),
        ),
    ),
    (
        "sobrado-passa.ids",
        "sobrado",
        "Sobrado - requisitos basicos de identificacao",
        True,
        (
            ("Escada com Name Escada", "IFCSTAIR", "Name", "Escada", 1, 1),
            ("Telhado com Name Telhado 4 Aguas", "IFCROOF", "Name", "Telhado 4 Aguas", 1, 1),
            ("Pavimentos com Name preenchido", "IFCBUILDINGSTOREY", "Name", None, 2, 2),
        ),
    ),
)

_TOPICOS_BCF = (
    ("bcf-topico-1-porta", "Conferir especificacao da porta", "IfcDoor", 1),
    ("bcf-topico-2-janelas", "Verificar dimensoes das janelas", "IfcWindow", 2),
    ("bcf-topico-3-paredes", "Revisar alinhamento das paredes", "IfcWall", 4),
)
_VERSOES_BCF = (("topicos-2-1.bcf", "2.1"), ("topicos-3-0.bcf", "3.0"))


def _uuid(chave: str) -> str:
    return str(uuid.uuid5(_NS_UUID, chave))


def _xml_bytes(raiz: ET.Element) -> bytes:
    ET.indent(raiz, space="  ")
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=True) + b"\n"


def _sub_texto(pai: ET.Element, tag: str, texto: str, **atrib: str) -> ET.Element:
    el = ET.SubElement(pai, tag, atrib)
    el.text = texto
    return el


def _ids_tag(nome: str) -> str:
    return f"{{{_NS_IDS}}}{nome}"


def _ids_simple(pai: ET.Element, nome: str, valor: str) -> None:
    cont = ET.SubElement(pai, _ids_tag(nome))
    _sub_texto(cont, _ids_tag("simpleValue"), valor)


def _montar_ids(titulo: str, specs: tuple) -> bytes:
    ET.register_namespace("", _NS_IDS)
    raiz = ET.Element(_ids_tag("ids"))
    info = ET.SubElement(raiz, _ids_tag("info"))
    _sub_texto(info, _ids_tag("title"), titulo)
    _sub_texto(info, _ids_tag("date"), _DATA_ISO)
    specs_el = ET.SubElement(raiz, _ids_tag("specifications"))
    for nome_spec, classe, attr, valor, _aplic, _ok in specs:
        spec = ET.SubElement(specs_el, _ids_tag("specification"), {"name": nome_spec, "ifcVersion": "IFC4"})
        aplic = ET.SubElement(spec, _ids_tag("applicability"))
        ent = ET.SubElement(aplic, _ids_tag("entity"))
        _ids_simple(ent, "name", classe)
        reqs = ET.SubElement(spec, _ids_tag("requirements"))
        facet = ET.SubElement(reqs, _ids_tag("attribute"))
        _ids_simple(facet, "name", attr)
        if valor is not None:
            _ids_simple(facet, "value", valor)
    return _xml_bytes(raiz)


def _gerar_ids(dir_ids: Path) -> None:
    casos = []
    for arquivo, modelo, titulo, passa, specs in _CASOS_IDS:
        (dir_ids / arquivo).write_bytes(_montar_ids(titulo, specs))
        especs = {
            nome: {"aplicaveis": aplic, "passam": ok, "passa": ok == aplic}
            for nome, _cls, _attr, _val, aplic, ok in specs
        }
        casos.append({"arquivo": arquivo, "modelo": modelo, "passa": passa, "especificacoes": especs})
    manif = {"casos": casos}
    (dir_ids / "manifesto.json").write_text(
        json.dumps(manif, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _montar_bcf_version(versao: str) -> bytes:
    raiz = ET.Element("Version", {"VersionId": versao})
    if versao == "2.1":
        _sub_texto(raiz, "DetailedVersion", versao)
    return _xml_bytes(raiz)


def _montar_markup(versao: str, guid_topico: str, guid_vp: str, titulo: str) -> bytes:
    raiz = ET.Element("Markup")
    topico = ET.SubElement(
        raiz,
        "Topic",
        {"Guid": guid_topico, "TopicType": "Issue", "TopicStatus": "Open"},
    )
    _sub_texto(topico, "Title", titulo)
    _sub_texto(topico, "CreationDate", _DATA_HORA_BCF)
    _sub_texto(topico, "CreationAuthor", _AUTOR_BCF)
    _sub_texto(topico, "Description", titulo)
    pai_vp = topico if versao == "3.0" else raiz
    vps = ET.SubElement(pai_vp, "Viewpoints", {"Guid": guid_vp})
    _sub_texto(vps, "Viewpoint", "viewpoint.bcfv")
    return _xml_bytes(raiz)


def _montar_visinfo(versao: str, guid_vis: str, ifc_guids: list[str]) -> bytes:
    raiz = ET.Element("VisualizationInfo", {"Guid": guid_vis})
    comps = ET.SubElement(raiz, "Components")
    sel = ET.SubElement(comps, "Selection")
    for g in ifc_guids:
        ET.SubElement(sel, "Component", {"IfcGuid": g})
    if versao == "2.1":
        ET.SubElement(comps, "Visibility", {"DefaultVisibility": "true"})
    return _xml_bytes(raiz)


def _gravar_zip_deterministico(destino: Path, entradas: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(destino, "w") as zf:
        for nome, dados in entradas:
            zi = zipfile.ZipInfo(filename=nome, date_time=_ZIP_DATA)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, dados)


def _extrair_topicos(modelo_casa) -> list[dict]:
    topicos = []
    for chave, titulo, cls, qtd in _TOPICOS_BCF:
        guids = sorted(e.GlobalId for e in modelo_casa.by_type(cls))[:qtd]
        if len(guids) != qtd:
            raise ValueError(f"Esperados {qtd} elementos {cls} em casa-terrea.ifc, achados {len(guids)}")
        topicos.append({"chave": chave, "guid": _uuid(chave), "titulo": titulo, "ifc_guids": guids})
    topicos.sort(key=lambda t: t["guid"])
    return topicos


def _gerar_bcf(dir_bcf: Path, modelo_casa) -> None:
    topicos = _extrair_topicos(modelo_casa)
    casos = []
    for arquivo, versao in _VERSOES_BCF:
        entradas: list[tuple[str, bytes]] = [("bcf.version", _montar_bcf_version(versao))]
        topicos_manif = []
        for t in topicos:
            guid_t = t["guid"]
            guid_vp = _uuid(f"{t['chave']}:vp:{versao}")
            guid_vis = _uuid(f"{t['chave']}:vis:{versao}")
            entradas.append((f"{guid_t}/markup.bcf", _montar_markup(versao, guid_t, guid_vp, t["titulo"])))
            entradas.append((f"{guid_t}/viewpoint.bcfv", _montar_visinfo(versao, guid_vis, t["ifc_guids"])))
            topicos_manif.append({"guid": guid_t, "titulo": t["titulo"], "ifc_guids": t["ifc_guids"]})
        _gravar_zip_deterministico(dir_bcf / arquivo, entradas)
        casos.append(
            {
                "arquivo": arquivo,
                "versao_bcf": versao,
                "modelo": "casa-terrea",
                "quantidade_topicos": len(topicos_manif),
                "topicos": topicos_manif,
            }
        )
    manif = {"casos": casos}
    (dir_bcf / "manifesto.json").write_text(
        json.dumps(manif, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def gerar_todos(
    pasta_modelos: str | Path = "corpus",
    pasta_ids: str | Path = "corpus/ids",
    pasta_bcf: str | Path = "corpus/bcf",
) -> tuple[Path, Path]:
    """Le os modelos do T04 e gera os casos IDS 1.0 e BCF 2.1/3.0 com manifestos."""
    dir_modelos = Path(pasta_modelos)
    dir_ids, dir_bcf = Path(pasta_ids), Path(pasta_bcf)
    modelos = {
        nome: ifcopenshell.open(str(dir_modelos / f"{nome}.ifc"))
        for nome in ("casa-terrea", "sobrado")
    }
    dir_ids.mkdir(parents=True, exist_ok=True)
    dir_bcf.mkdir(parents=True, exist_ok=True)
    _gerar_ids(dir_ids)
    _gerar_bcf(dir_bcf, modelos["casa-terrea"])
    return dir_ids, dir_bcf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera casos proprios IDS 1.0 e BCF 2.1/3.0.")
    parser.add_argument("pasta_modelos", nargs="?", default="corpus")
    parser.add_argument("pasta_ids", nargs="?", default="corpus/ids")
    parser.add_argument("pasta_bcf", nargs="?", default="corpus/bcf")
    args = parser.parse_args(argv)
    gerar_todos(args.pasta_modelos, args.pasta_ids, args.pasta_bcf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
