# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T14c (parte A): escrita dos nomes novos em ingles em IFC, .obim e .obimpack, e varredura de texto bruto."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import s06_t04_aux as A
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)

LADO = "6c2f7b50-8e1f-4d63-ab54-2d1ef6b80177"
G1 = "0$Fq3Zk1D5Pv2wX4yAbC_E"
G2 = "3cUz$7rQ0aLm9XyN2bP_Hd"
IDENT = "A-01"

CHAVES_OBIM_NOVAS = {
    "format",
    "format_version",
    "SideId",
    "Revision",
    "ifc_name",
    "ifc_sha256",
    "ifc_size",
    "ifc_project_globalid",
    "program_version",
    "date",
}
CHAVES_OBIM_ANTIGAS = {
    "formato",
    "versao_formato",
    "LadoId",
    "Revisao",
    "ifc_nome",
    "ifc_tamanho",
    "ifc_projeto_globalid",
    "programa_versao",
    "data",
}
CHAVES_OBIMPACK_NOVAS = {"format", "package_version", "files"}
CHAVES_OBIMPACK_ANTIGAS = {"formato", "versao_pacote", "arquivos"}
PALAVRAS_PROIBIDAS = (
    "LadoId",
    "Revisao",
    "versao_formato",
    "ifc_nome",
    "ifc_tamanho",
    "ifc_projeto_globalid",
    "programa_versao",
    "versao_pacote",
    '"prancha":',
    '"escala":',
    '"formato":',
    '"arquivos":',
)


def _sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _criar_sessao(tmp_path):
    exigir()
    from openbim_app.lateral import Lateral
    from openbim_app.sessao_modelo import SessaoModelo
    from openbim_app.transacao import Historico

    arq = A.novo_arquivo("IFC4")
    destino = tmp_path / "obra" / "Casa.ifc"
    pasta = tmp_path / "local" / "projetos" / LADO
    destino.parent.mkdir(parents=True, exist_ok=True)
    pasta.mkdir(parents=True, exist_ok=True)
    sessao = SessaoModelo(arq)
    lat = Lateral()
    hist = Historico(sessao, lat, anotar=lambda *a, **k: None)
    return arq, sessao, lat, hist, destino, pasta


def _gravar(sessao, hist, lat, destino, pasta, *, seq=1, carimbo=True, autosave=False, origem_ifc_sha256=None):
    import openbim_app.gravacao_par as GP

    return GP.gravar_par(
        sessao=sessao,
        historico=hist,
        lateral=lat,
        destino=destino,
        pasta_projeto=pasta,
        lado_id=LADO,
        seq=seq,
        carimbo=carimbo,
        autosave=autosave,
        origem_ifc_sha256=origem_ifc_sha256,
    )


def _pset_obim_cru(caminho_ifc):
    import ifcopenshell

    arq = ifcopenshell.open(str(caminho_ifc))
    proj = arq.by_type("IfcProject")[0]
    psets = [
        r.RelatingPropertyDefinition
        for r in proj.IsDefinedBy or ()
        if r.is_a("IfcRelDefinesByProperties")
        and r.RelatingPropertyDefinition.is_a("IfcPropertySet")
        and r.RelatingPropertyDefinition.Name == "OBIM_Project"
    ]
    assert len(psets) == 1, f"esperado 1 pset OBIM_Project, achado {len(psets)}"
    props = {}
    for prop in psets[0].HasProperties or ():
        if prop.is_a("IfcPropertySingleValue") and prop.NominalValue is not None:
            props[prop.Name] = prop.NominalValue.wrappedValue
    return proj, props


def _manifest_obim_cru(caminho_obim):
    with zipfile.ZipFile(caminho_obim) as z:
        assert "manifest.json" in z.namelist()
        bruto = z.read("manifest.json").decode("utf-8")
        return json.loads(bruto), bruto


def _nome_manifesto_obimpack(mod):
    nome = getattr(mod, "NOME_MANIFESTO", "manifesto.json")
    assert nome in ("manifesto.json", "manifest.json"), f"NOME_MANIFESTO inesperado: {nome!r}"
    return nome


def test_01_pset_obim_project_tem_sideid_e_revision_em_duas_gravacoes(tmp_path):
    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            t.lado.criar("notas", "n1", {"texto": "primeira"})
        _gravar(sessao, hist, lat, destino, pasta, seq=1)

        _, props1 = _pset_obim_cru(destino)
        assert set(props1) == {"SideId", "Revision"}, f"propriedades do pset: {props1}"
        assert props1["SideId"] == LADO
        assert props1["Revision"] == 1 and not isinstance(props1["Revision"], bool)
        assert "LadoId" not in props1 and "Revisao" not in props1

        with sessao.escrever() as esc, hist.transacao(esc) as t:
            t.lado.criar("notas", "n2", {"texto": "segunda"})
        _gravar(sessao, hist, lat, destino, pasta, seq=2)

        _, props2 = _pset_obim_cru(destino)
        assert set(props2) == {"SideId", "Revision"}, f"propriedades apos 2a gravacao: {props2}"
        assert props2["SideId"] == LADO
        assert props2["Revision"] == 2 and not isinstance(props2["Revision"], bool)
        assert "LadoId" not in props2 and "Revisao" not in props2
    finally:
        hist.encerrar()


def test_02_manifest_obim_conjunto_fechado_de_chaves_novas(tmp_path):
    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        _gravar(sessao, hist, lat, destino, pasta, seq=1)
        obim = destino.with_suffix(".obim")
        proj, _ = _pset_obim_cru(destino)
        man, _ = _manifest_obim_cru(obim)

        assert set(man) == CHAVES_OBIM_NOVAS, f"chaves do manifest.json: {sorted(man)}"
        assert not (set(man) & CHAVES_OBIM_ANTIGAS)
        assert man["format"] == "obim-lateral"
        assert man["format_version"] == "0.2.0"
        assert man["SideId"] == LADO
        assert man["Revision"] == 1 and not isinstance(man["Revision"], bool)
        assert man["ifc_name"] == "Casa.ifc"
        assert man["ifc_sha256"] == _sha(destino)
        assert man["ifc_size"] == destino.stat().st_size
        assert man["ifc_project_globalid"] == proj.GlobalId
        assert isinstance(man["program_version"], str) and man["program_version"]
        assert isinstance(man["date"], str) and man["date"]

        with sessao.escrever() as esc, hist.transacao(esc) as t:
            t.lado.criar("notas", "n2", {"texto": "rev 2"})
        _gravar(sessao, hist, lat, destino, pasta, seq=2)
        man2, _ = _manifest_obim_cru(obim)

        assert set(man2) == CHAVES_OBIM_NOVAS
        assert man2["SideId"] == LADO and man2["Revision"] == 2
        assert man2["ifc_sha256"] == _sha(destino) and man2["ifc_size"] == destino.stat().st_size
    finally:
        hist.encerrar()


def test_03_sheet_e_viewport_gravados_no_obim_com_chaves_novas(tmp_path):
    import openbim_app.obim_zip as Z
    import openbim_app.prancha as P

    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            id_p = P.criar_prancha(
                t.lado,
                IDENT,
                formato="A3",
                projeto="Projeto Alpha",
                titulo="Planta Terreo",
                data="2026-11-25",
                folha="01/02",
            )
            id_v1 = P.colocar_viewport(t.lado, IDENT, G1, 20, 25.5, 50)
            id_v2 = P.colocar_viewport(t.lado, IDENT, G2, 120, 25.5, 100, rotacao=90)
        _gravar(sessao, hist, lat, destino, pasta, seq=1)

        obim = destino.with_suffix(".obim")
        with zipfile.ZipFile(obim) as z:
            sheet = json.loads(z.read(f"sheets/{id_p}.json").decode("utf-8"))
            vp1 = json.loads(z.read(f"viewports/{id_v1}.json").decode("utf-8"))
            vp2 = json.loads(z.read(f"viewports/{id_v2}.json").decode("utf-8"))

        assert sheet == {
            "identification": IDENT,
            "format": "A3",
            "titleblock": {
                "project": "Projeto Alpha",
                "title": "Planta Terreo",
                "date": "2026-11-25",
                "sheet": "01/02",
            },
        }
        assert "formato" not in sheet

        assert vp1 == {"sheet": IDENT, "view_guid": G1, "x": 20, "y": 25.5, "scale": 50}
        assert "prancha" not in vp1 and "escala" not in vp1

        assert vp2 == {"sheet": IDENT, "view_guid": G2, "x": 120, "y": 25.5, "scale": 100, "rotation": 90}
        assert "prancha" not in vp2 and "escala" not in vp2

        lido = Z.ler(obim)
        planta_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 6"><rect x="0" y="0" width="10" height="6"/></svg>'
        svg_prancha = P.montar_svg(lido.lateral, IDENT, G1, planta_svg)
        assert 'width="420mm"' in svg_prancha and "1:50" in svg_prancha
    finally:
        hist.encerrar()


def test_04_manifest_obimpack_tem_chaves_novas_e_nenhuma_antiga(tmp_path):
    from openbim_app import obimpack

    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        _gravar(sessao, hist, lat, destino, pasta, seq=1)
        obim = destino.with_suffix(".obim")
        pacote = obimpack.exportar((destino, obim))
        nome_man = _nome_manifesto_obimpack(obimpack)

        with zipfile.ZipFile(pacote) as z:
            assert sorted(z.namelist()) == sorted(["Casa.ifc", "Casa.obim", nome_man])
            man = json.loads(z.read(nome_man).decode("utf-8"))

        assert set(man) == CHAVES_OBIMPACK_NOVAS, f"chaves do obimpack: {sorted(man)}"
        assert not (set(man) & CHAVES_OBIMPACK_ANTIGAS)
        assert man["format"] == "obimpack"
        assert isinstance(man["package_version"], str) and man["package_version"]

        por_nome = {a["nome"]: a for a in man["files"]}
        assert set(por_nome) == {"Casa.ifc", "Casa.obim"}
        assert por_nome["Casa.ifc"] == {"nome": "Casa.ifc", "tamanho": destino.stat().st_size, "sha256": _sha(destino)}
        assert por_nome["Casa.obim"] == {"nome": "Casa.obim", "tamanho": obim.stat().st_size, "sha256": _sha(obim)}
    finally:
        hist.encerrar()


def test_05_varredura_texto_bruto_sem_palavras_antigas(tmp_path):
    import openbim_app.prancha as P
    from openbim_app import obimpack

    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            P.criar_prancha(
                t.lado,
                IDENT,
                formato="A3",
                projeto="Projeto Alpha",
                titulo="Planta Terreo",
                data="2026-11-25",
                folha="01/02",
            )
            P.colocar_viewport(t.lado, IDENT, G1, 20, 25, 50)
        _gravar(sessao, hist, lat, destino, pasta, seq=1)
        obim = destino.with_suffix(".obim")
        pacote = obimpack.exportar((destino, obim))
        nome_man = _nome_manifesto_obimpack(obimpack)

        textos = {"Casa.ifc": destino.read_text(encoding="utf-8", errors="replace")}
        with zipfile.ZipFile(obim) as z:
            for nome in z.namelist():
                if nome.endswith(".json"):
                    textos[f"Casa.obim:{nome}"] = z.read(nome).decode("utf-8")
        with zipfile.ZipFile(pacote) as z:
            textos[f"Casa.obimpack:{nome_man}"] = z.read(nome_man).decode("utf-8")

        achados = []
        for origem, conteudo in textos.items():
            for palavra in PALAVRAS_PROIBIDAS:
                if palavra in conteudo:
                    achados.append((origem, palavra))
        assert not achados, f"palavras antigas encontradas nos arquivos gravados: {achados}"
    finally:
        hist.encerrar()
