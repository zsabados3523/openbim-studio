# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T05, bordas da revisão (`docs/state/reports/F0-S06-T05-revisao.md`: M03 a M08, M12, M13, I-1, I-2, D1 a D3). Contrato em
`test_s06_t05_obim_zip_oraculo.py`. Decisões do líder: `gravar_par` recusa só `.obim` de versão maior (somente leitura); `.obim` existente ilegível ou
inválido NÃO trava o salvar (gravado por cima, o antigo vai para `.bak`); `ler` continua validando 0.2.x; `orfaos` simétrico (ADR-003 §6): viewport cuja
prancha ou vista não existe é órfão, também com `identifications` vazio. Marcadores retirados."""
import json
import zipfile

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401
from test_s06_t05_obim_zip_oraculo import G1, G2, IDENT, MAN, U, _fabrica, canon, lat, ob, objetos, proj  # noqa: F401

VP = {"prancha": IDENT, "vista_guid": G1, "x": 1, "y": 2, "escala": 100}


def _viewports(**extra):
    return lat(viewports={**objetos()["viewports"], **extra})


def _zip(p, nome, manifesto=None):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps(MAN if manifesto is None else manifesto))
        z.writestr(zipfile.ZipInfo(nome), b"{}")


def test_01_unidade_windows_e_perigosa(tmp_path):  # M03
    m, p = ob(), tmp_path / "c.obim"
    _zip(p, "C:/x.json")
    with pytest.raises(m.ObimInvalido):
        m.ler(p)
    import openbim_app.gravacao_par as GP
    with pytest.raises(ValueError):
        GP._conferir_obim(p)


def test_02_identification_com_espaco_so_no_fim(tmp_path):  # M04
    m = ob()
    with pytest.raises(m.ObimInvalido):
        m.escrever(tmp_path / "f.obim", lat(pranchas={"x": {"identification": "A-02 "}}), MAN)


@pytest.mark.parametrize("campo", ["x", "y", "escala"])
def test_03_bool_nao_e_numero(tmp_path, campo):  # M05
    m = ob()
    with pytest.raises(m.ObimInvalido):
        m.escrever(tmp_path / "f.obim", _viewports(outro={**VP, "prancha": "B", campo: True}), MAN)


def test_04_y_do_viewport_e_validado(tmp_path):  # M06
    m = ob()
    with pytest.raises(m.ObimInvalido):
        m.escrever(tmp_path / "f.obim", _viewports(outro={**VP, "prancha": "B", "y": "1"}), MAN)


def test_05_mesma_vista_em_duas_pranchas_e_valida(tmp_path):  # M07 (ADR §4)
    m, p = ob(), tmp_path / "f.obim"
    m.escrever(p, _viewports(outro={**VP, "prancha": "B-02"}), MAN)  # (IDENT, G1) já existe; (B-02, G1) é outro par
    assert len(m.ler(p).lateral.ids("viewports")) == 3


@pytest.mark.parametrize("nome", ["../x.json", "/abs/x.json", "C:/x.json", "a\\b.json", "assets/../../x"])
def test_06_extra_perigoso_recusado_e_nada_gravado(tmp_path, nome):  # M08
    m, p = ob(), tmp_path / "f.obim"
    with pytest.raises(m.ObimInvalido):
        m.escrever(p, lat(), MAN, {nome: b"x"})
    assert not p.exists()


@pytest.mark.parametrize("manifesto,porque", [({**MAN, "versao_formato": "0.1.0"}, "versão errada"), ({**MAN, "versao_formato": "9.9.9"}, "versão maior"),
                                              ([], "manifesto lista"), ("texto", "manifesto texto")])
def test_07_conferir_obim_recusa(tmp_path, manifesto, porque):  # M12, M13
    import openbim_app.gravacao_par as GP
    p = tmp_path / "f.obim"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps(manifesto))
    with pytest.raises(ValueError):
        GP._conferir_obim(p)


@pytest.mark.parametrize("manifesto,extras", [({**MAN, "nan": float("nan")}, None), (MAN, {"assets/a.bin": 123}), (MAN, {"assets/a.bin": None})],
                        ids=["manifesto NaN", "extra inteiro", "extra None"])
def test_08_i1_falha_nao_deixa_arquivo(tmp_path, manifesto, extras):
    m, p = ob(), tmp_path / "f.obim"
    with pytest.raises((m.ObimInvalido, TypeError)):
        m.escrever(p, lat(), manifesto, extras)
    assert not p.exists() and not list(tmp_path.iterdir()), "sobrou arquivo parcial no destino"


@pytest.mark.parametrize("nome", ["manifest.json", f"vistas/{U['v1']}.json", f"notas/nx.json"])
def test_09_i2_extra_com_nome_reservado_recusado(tmp_path, nome):
    m, p = ob(), tmp_path / "f.obim"
    with pytest.raises(m.ObimInvalido):
        m.escrever(p, lat(), MAN, {nome: b"{}"})
    assert not p.exists()


def test_10_d3_orfaos_simetrico_com_identifications_vazio():
    m, l = ob(), lat()
    r = m.orfaos(l, {G1, G2}, set())
    assert sorted(r["viewports"]) == sorted((U["vp1"], U["vp2"])) and r["pranchas"] == [U["p1"]] and r["vistas"] == []
    assert m.orfaos(l, {G1, G2}, {IDENT}) == {"vistas": [], "pranchas": [], "viewports": []}


def _velho_ilegivel(proj, base_ifc, como):  # noqa: F811
    X.escrever_par_falso(proj.destino, base_ifc, {"notas": {"n0": {"texto": "primeira"}}}, 5)
    o = proj.destino.with_suffix(".obim")
    if como == "corrompido":
        o.write_bytes(b"isto nao e zip")
    else:  # 0.2.x inválido: vista_guid repetido, como outro programa poderia gravar
        with zipfile.ZipFile(o, "w") as z:
            z.writestr("manifest.json", json.dumps(MAN))
            z.writestr("vistas/a.json", json.dumps({"vista_guid": G1}))
            z.writestr("vistas/b.json", json.dumps({"vista_guid": G1}))
    return o.read_bytes()


@pytest.mark.parametrize("como", ["corrompido", "0.2.x invalido"])
def test_11_d1_obim_antigo_ilegivel_nao_trava_o_salvar(proj, base_ifc, como):  # noqa: F811
    m = ob()
    _fabrica(proj)
    ruim = _velho_ilegivel(proj, base_ifc, como)
    proj.gravar()
    o = proj.destino.with_suffix(".obim")
    assert proj.destino.with_name("Casa.obim.bak").read_bytes() == ruim, "o arquivo ilegível tem de ir para o .bak"
    assert canon(m.ler(o).lateral) == canon(proj.lat) and not any(proj.pasta.glob("gravacao*"))


def test_12_d2_ler_continua_validando_0_2_x(tmp_path):
    m, p = ob(), tmp_path / "f.obim"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps(MAN))
        z.writestr("vistas/a.json", json.dumps({"vista_guid": G1}))
        z.writestr("vistas/b.json", json.dumps({"vista_guid": G1}))
    with pytest.raises(m.ObimInvalido):
        m.ler(p)
