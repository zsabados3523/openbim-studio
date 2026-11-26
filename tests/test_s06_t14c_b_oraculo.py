# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T14c (parte B): leitura sem migracao (.obim, prancha, .obimpack e divergencia) com nomes novos vs antigos."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import s06_t04_aux as A
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)

LADO = "6c2f7b50-8e1f-4d63-ab54-2d1ef6b80177"
OUTRO_LADO = "00000000-0000-4000-8000-000000000099"
GID = "2xQ0hZ1u8Ek9aBc3DeFgHi"
OUTRO_GID = "9zzzzzzzzzzzzzzzzzzzzz"
G1 = "0$Fq3Zk1D5Pv2wX4yAbC_E"
IDENT = "A-01"
PLANTA_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 6"><rect x="0" y="0" width="10" height="6"/></svg>'
IFC_CRU = b"ISO-10303-21;\nDATA;\n#1=IFCPROJECT('x');\nENDSEC;\nEND-ISO-10303-21;\n" * 10
OBIM_CRU = b"PK-obim-simulado-\x00\x01\x02" * 20


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _man_obim_novo(*, ifc_name="Casa.ifc", ifc_sha="0" * 64, ifc_size=100, gid=GID, side_id=LADO, revision=2, **sobre):
    man = {
        "format": "obim-lateral",
        "format_version": "0.2.0",
        "SideId": side_id,
        "Revision": revision,
        "ifc_name": ifc_name,
        "ifc_sha256": ifc_sha,
        "ifc_size": ifc_size,
        "ifc_project_globalid": gid,
        "program_version": "0.1.0",
        "date": "2026-11-25T00:00:00Z",
    }
    man.update(sobre)
    return man


def _man_obim_antigo(*, ifc_nome="Casa.ifc", ifc_sha="0" * 64, ifc_tamanho=100, gid=GID, lado=LADO, rev=2):
    return {
        "formato": "obim-lateral",
        "versao_formato": "0.2.0",
        "LadoId": lado,
        "Revisao": rev,
        "ifc_nome": ifc_nome,
        "ifc_sha256": ifc_sha,
        "ifc_tamanho": ifc_tamanho,
        "ifc_projeto_globalid": gid,
        "programa_versao": "0.1.0",
        "data": "2026-11-25T00:00:00Z",
    }


def _escrever_zip_obim(caminho, manifesto, objetos=None):
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifesto))
        for col, itens in (objetos or {}).items():
            for uid, obj in itens.items():
                z.writestr(f"{col}/{uid}.json", json.dumps(obj))
    return caminho


def _nome_manifesto_obimpack(mod):
    nome = getattr(mod, "NOME_MANIFESTO", "manifesto.json")
    assert nome in ("manifesto.json", "manifest.json"), f"NOME_MANIFESTO inesperado: {nome!r}"
    return nome


def _escrever_zip_obimpack(caminho, nome_man, manifesto, ifc=IFC_CRU, obim=OBIM_CRU):
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Casa.ifc", ifc)
        z.writestr("Casa.obim", obim)
        z.writestr(nome_man, json.dumps(manifesto))
    return caminho


def _man_obimpack_novo(ifc=IFC_CRU, obim=OBIM_CRU):
    return {
        "format": "obimpack",
        "package_version": "1.0.0",
        "files": [
            {"nome": "Casa.ifc", "tamanho": len(ifc), "sha256": _sha_bytes(ifc)},
            {"nome": "Casa.obim", "tamanho": len(obim), "sha256": _sha_bytes(obim)},
        ],
    }


def _man_obimpack_antigo(ifc=IFC_CRU, obim=OBIM_CRU):
    return {
        "formato": "obimpack",
        "versao_pacote": "1.0.0",
        "arquivos": [
            {"nome": "Casa.ifc", "tamanho": len(ifc), "sha256": _sha_bytes(ifc)},
            {"nome": "Casa.obim", "tamanho": len(obim), "sha256": _sha_bytes(obim)},
        ],
    }


def _fazer_ifc(pasta, *, gid=GID, props_pset=None, nome="Casa.ifc"):
    exigir()
    import ifcopenshell.api

    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arq = A.novo_arquivo("IFC4")
    proj = arq.by_type("IfcProject")[0]
    proj.GlobalId = gid
    A.annotation(arq, "Planta 1").GlobalId = G1
    A.folha(arq, IDENT, "Prancha 1")
    if props_pset is not None:
        ps = ifcopenshell.api.run("pset.add_pset", arq, product=proj, name="OBIM_Project")
        if props_pset:
            ifcopenshell.api.run("pset.edit_pset", arq, pset=ps, properties=props_pset)
    caminho = pasta / nome
    arq.write(str(caminho))
    return caminho


def _objs_novos():
    return {
        "views": {"v1": {"view_guid": G1}},
        "sheets": {
            "p1": {
                "identification": IDENT,
                "format": "A3",
                "titleblock": {"project": "Projeto Alpha", "title": "Planta Terreo", "date": "2026-11-25", "sheet": "01/01"},
            }
        },
        "viewports": {"vp1": {"sheet": IDENT, "view_guid": G1, "x": 20.0, "y": 20.0, "scale": 50.0}},
    }


def _objs_antigos():
    return {
        "views": {"v1": {"view_guid": G1}},
        "sheets": {
            "p1": {
                "identification": IDENT,
                "formato": "A3",
                "titleblock": {"project": "Projeto Alpha", "title": "Planta Terreo", "date": "2026-11-25", "sheet": "01/01"},
            }
        },
        "viewports": {"vp1": {"prancha": IDENT, "view_guid": G1, "x": 20.0, "y": 20.0, "escala": 50.0}},
    }


def test_01_obim_zip_ler_aceita_nomes_novos_e_recusa_manifesto_antigo(tmp_path):
    import openbim_app.gravacao_par as GP
    import openbim_app.obim_zip as Z

    novo = _escrever_zip_obim(tmp_path / "novo.obim", _man_obim_novo(), _objs_novos())
    lido = Z.ler(novo)
    assert lido.manifesto["format"] == "obim-lateral"
    assert lido.manifesto["format_version"] == "0.2.0"
    assert lido.versao_original == "0.2.0" and lido.somente_leitura is False
    assert lido.lateral.obter("viewports", "vp1")["sheet"] == IDENT
    assert lido.lateral.obter("viewports", "vp1")["scale"] == 50.0
    GP._conferir_obim(novo)

    antigo = _escrever_zip_obim(tmp_path / "antigo.obim", _man_obim_antigo(), _objs_antigos())
    with pytest.raises(Z.ObimInvalido):
        Z.ler(antigo)
    with pytest.raises(ValueError):
        GP._conferir_obim(antigo)

    sem_versao_nova = _man_obim_novo()
    sem_versao_nova["versao_formato"] = sem_versao_nova.pop("format_version")
    parcial = _escrever_zip_obim(tmp_path / "parcial.obim", sem_versao_nova, _objs_novos())
    with pytest.raises(ValueError):
        GP._conferir_obim(parcial)
    try:
        r = Z.ler(parcial)
    except Z.ObimInvalido:
        pass
    else:
        assert r.somente_leitura is True and r.versao_original is None


@pytest.mark.parametrize(
    "vp_ruim",
    [
        {"prancha": IDENT, "view_guid": G1, "x": 20.0, "y": 20.0, "scale": 50.0},
        {"sheet": IDENT, "view_guid": G1, "x": 20.0, "y": 20.0, "escala": 50.0},
        {"prancha": IDENT, "view_guid": G1, "x": 20.0, "y": 20.0, "escala": 50.0},
    ],
    ids=["prancha_antiga", "escala_antiga", "ambos_antigos"],
)
def test_02_obim_zip_recusa_viewport_com_chaves_antigas(tmp_path, vp_ruim):
    import openbim_app.obim_zip as Z
    from openbim_app.lateral import Lateral

    bom = tmp_path / "vp_novo.obim"
    Z.escrever(bom, Lateral(_objs_novos()), _man_obim_novo())
    assert Z.ler(bom).lateral.obter("viewports", "vp1")["sheet"] == IDENT

    objs = _objs_novos()
    objs["viewports"]["vp1"] = vp_ruim
    p = _escrever_zip_obim(tmp_path / "vp_antigo.obim", _man_obim_novo(), objs)
    with pytest.raises(Z.ObimInvalido):
        Z.ler(p)

    saida = tmp_path / "nao_grava.obim"
    with pytest.raises(Z.ObimInvalido):
        Z.escrever(saida, Lateral(objs), _man_obim_novo())
    assert not saida.exists()


def test_03_obim_zip_orfaos_usa_chave_sheet():
    import openbim_app.obim_zip as Z
    from openbim_app.lateral import Lateral

    lat_novo = Lateral(_objs_novos())
    assert Z.orfaos(lat_novo, {G1}, {IDENT}) == {"vistas": [], "pranchas": [], "viewports": []}
    assert Z.orfaos(lat_novo, {G1}, set())["viewports"] == ["vp1"]

    objs_antigo = _objs_novos()
    objs_antigo["viewports"]["vp1"] = {"prancha": IDENT, "view_guid": G1, "x": 20.0, "y": 20.0, "escala": 50.0}
    lat_antigo = Lateral(objs_antigo)
    assert Z.orfaos(lat_antigo, {G1}, {IDENT})["viewports"] == ["vp1"]


def test_04_prancha_montar_svg_aceita_novas_e_recusa_antigas():
    import openbim_app.prancha as P
    from openbim_app.lateral import Lateral

    svg = P.montar_svg(Lateral(_objs_novos()), IDENT, G1, PLANTA_SVG)
    assert 'width="420mm"' in svg and "1:50" in svg

    sheet_antiga = _objs_novos()
    sheet_antiga["sheets"]["p1"]["formato"] = sheet_antiga["sheets"]["p1"].pop("format")
    with pytest.raises(P.FormatoInvalido):
        P.montar_svg(Lateral(sheet_antiga), IDENT, G1, PLANTA_SVG)

    vp_prancha_antiga = _objs_novos()
    vp_prancha_antiga["viewports"]["vp1"]["prancha"] = vp_prancha_antiga["viewports"]["vp1"].pop("sheet")
    with pytest.raises(P.PranchaNaoEncontrada):
        P.montar_svg(Lateral(vp_prancha_antiga), IDENT, G1, PLANTA_SVG)

    vp_escala_antiga = _objs_novos()
    vp_escala_antiga["viewports"]["vp1"]["escala"] = vp_escala_antiga["viewports"]["vp1"].pop("scale")
    with pytest.raises(P.EscalaInvalida):
        P.montar_svg(Lateral(vp_escala_antiga), IDENT, G1, PLANTA_SVG)


def test_05_obimpack_abrir_aceita_chaves_novas_e_recusa_antigas(tmp_path):
    from openbim_app import obimpack

    nome_man = _nome_manifesto_obimpack(obimpack)
    ok = _escrever_zip_obimpack(tmp_path / "ok.obimpack", nome_man, _man_obimpack_novo())
    dest_ok = tmp_path / "dest_ok"
    ifc_out, obim_out = obimpack.abrir(ok, dest_ok)
    assert ifc_out.read_bytes() == IFC_CRU and obim_out.read_bytes() == OBIM_CRU

    antigo = _escrever_zip_obimpack(tmp_path / "antigo.obimpack", nome_man, _man_obimpack_antigo())
    dest_bad = tmp_path / "dest_bad"
    with pytest.raises(obimpack.ObimpackInvalido):
        obimpack.abrir(antigo, dest_bad)
    assert not dest_bad.exists() or not any(dest_bad.rglob("*"))


@pytest.mark.parametrize(
    "troca",
    [("format", "formato"), ("package_version", "versao_pacote"), ("files", "arquivos")],
    ids=["formato_antigo", "versao_pacote_antiga", "arquivos_antigo"],
)
def test_06_obimpack_recusa_cada_chave_antiga_isolada(tmp_path, troca):
    from openbim_app import obimpack

    nome_man = _nome_manifesto_obimpack(obimpack)
    ok = _escrever_zip_obimpack(tmp_path / "ok.obimpack", nome_man, _man_obimpack_novo())
    obimpack.abrir(ok, tmp_path / "dest_ok")

    nova, antiga = troca
    man = _man_obimpack_novo()
    man[antiga] = man.pop(nova)
    pacote = _escrever_zip_obimpack(tmp_path / f"{antiga}.obimpack", nome_man, man)
    dest = tmp_path / "dest"
    with pytest.raises(obimpack.ObimpackInvalido):
        obimpack.abrir(pacote, dest)
    assert not dest.exists() or not any(dest.rglob("*"))


def test_07_divergencia_detecta_nomes_novos_d1_d2_d3_d5_d6(tmp_path):
    import openbim_app.divergencia as DV

    ifc = _fazer_ifc(tmp_path / "d1", props_pset={"SideId": LADO, "Revision": 2})
    obim = ifc.with_suffix(".obim")
    sha_ifc = _sha_bytes(ifc.read_bytes())
    _escrever_zip_obim(obim, _man_obim_novo(ifc_sha=sha_ifc, ifc_size=ifc.stat().st_size), _objs_novos())

    r1 = DV.classificar(ifc)
    assert r1.caso == "D1" and r1.vinculado is True and r1.versao_lateral == "0.2.0"

    r6 = DV.classificar(obim)
    assert r6.caso == "D6" and r6.via_obim is True and r6.ifc == ifc and r6.aviso is None

    _escrever_zip_obim(obim, _man_obim_novo(ifc_sha=sha_ifc, ifc_size=ifc.stat().st_size, revision=4), _objs_novos())
    assert DV.classificar(ifc).caso == "D3"

    _escrever_zip_obim(obim, _man_obim_novo(ifc_sha=sha_ifc, ifc_size=ifc.stat().st_size, side_id=OUTRO_LADO), _objs_novos())
    assert DV.classificar(ifc).caso == "D5"

    _escrever_zip_obim(obim, _man_obim_novo(ifc_sha=sha_ifc, ifc_size=ifc.stat().st_size, gid=OUTRO_GID), _objs_novos())
    assert DV.classificar(ifc).caso == "D5"

    _escrever_zip_obim(obim, _man_obim_novo(ifc_sha="f" * 64, ifc_size=ifc.stat().st_size), _objs_novos())
    assert DV.classificar(ifc).caso == "D2"


def test_08_divergencia_recusa_manifesto_antigo_completo(tmp_path):
    import openbim_app.divergencia as DV

    ifc = _fazer_ifc(tmp_path / "old", props_pset={"SideId": LADO, "Revision": 2})
    obim = ifc.with_suffix(".obim")
    sha_ifc = _sha_bytes(ifc.read_bytes())
    _escrever_zip_obim(obim, _man_obim_antigo(ifc_sha=sha_ifc, ifc_tamanho=ifc.stat().st_size), _objs_antigos())

    with pytest.raises(DV.LateralRecusado):
        DV.classificar(ifc)
    with pytest.raises(DV.LateralRecusado):
        DV.classificar(obim)


@pytest.mark.parametrize(
    "troca",
    [
        ("SideId", "LadoId"),
        ("Revision", "Revisao"),
        ("ifc_name", "ifc_nome"),
        ("ifc_project_globalid", "ifc_projeto_globalid"),
        ("format_version", "versao_formato"),
    ],
    ids=["LadoId", "Revisao", "ifc_nome", "ifc_projeto_globalid", "versao_formato"],
)
def test_09_divergencia_recusa_cada_chave_antiga_no_manifesto(tmp_path, troca):
    import openbim_app.divergencia as DV

    ifc = _fazer_ifc(tmp_path / troca[1], props_pset={"SideId": LADO, "Revision": 2})
    obim = ifc.with_suffix(".obim")
    man = _man_obim_novo(ifc_sha=_sha_bytes(ifc.read_bytes()), ifc_size=ifc.stat().st_size)
    nova, antiga = troca
    man[antiga] = man.pop(nova)
    _escrever_zip_obim(obim, man, _objs_novos())

    with pytest.raises(DV.LateralIncompativel):
        DV.classificar(ifc)


def test_10_divergencia_ignora_pset_antigo_com_lado_id_e_revisao(tmp_path):
    import openbim_app.divergencia as DV

    ifc_antigo = _fazer_ifc(tmp_path / "pset_antigo", props_pset={"LadoId": OUTRO_LADO, "Revisao": 1})
    obim_antigo = ifc_antigo.with_suffix(".obim")
    _escrever_zip_obim(
        obim_antigo,
        _man_obim_novo(ifc_sha=_sha_bytes(ifc_antigo.read_bytes()), ifc_size=ifc_antigo.stat().st_size, side_id=LADO, revision=5),
        _objs_novos(),
    )
    # Sem migracao: LadoId/Revisao antigos no pset nao sao lidos, entao nao disparam D5 nem D3
    assert DV.classificar(ifc_antigo).caso == "D1"

    ifc_novo_d5 = _fazer_ifc(tmp_path / "pset_novo_d5", props_pset={"SideId": OUTRO_LADO, "Revision": 1})
    _escrever_zip_obim(
        ifc_novo_d5.with_suffix(".obim"),
        _man_obim_novo(ifc_sha=_sha_bytes(ifc_novo_d5.read_bytes()), ifc_size=ifc_novo_d5.stat().st_size, side_id=LADO, revision=5),
        _objs_novos(),
    )
    assert DV.classificar(ifc_novo_d5).caso == "D5"

    ifc_novo_d3 = _fazer_ifc(tmp_path / "pset_novo_d3", props_pset={"SideId": LADO, "Revision": 1})
    _escrever_zip_obim(
        ifc_novo_d3.with_suffix(".obim"),
        _man_obim_novo(ifc_sha=_sha_bytes(ifc_novo_d3.read_bytes()), ifc_size=ifc_novo_d3.stat().st_size, side_id=LADO, revision=5),
        _objs_novos(),
    )
    assert DV.classificar(ifc_novo_d3).caso == "D3"
