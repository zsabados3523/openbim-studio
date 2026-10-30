# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T05, parte b (decisões do líder; contrato em `test_s06_t05_obim_zip_oraculo.py`). Só o autor tira os `@AINDA_NAO`."""
import json
import zipfile

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401
from test_s06_t05_obim_zip_oraculo import AINDA_NAO, G1, IDENT, MAN, U, _fabrica, canon, lat, ob, objetos, proj  # noqa: F401


@AINDA_NAO
def test_21_0_1_0_com_colecoes_reservadas_le_sem_validar(tmp_path):
    m, p = ob(), tmp_path / "velho.obim"
    ruim = {"sem_chave": 1}  # um `vistas` sem `vista_guid` seria recusado no 0.2.0; no 0.1.0 não se valida
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps({**MAN, "versao_formato": "0.1.0", "provisorio": True}))
        z.writestr("vistas/abc.json", json.dumps(ruim))
        z.writestr("styles/e1.json", json.dumps({"x": 1}))
    r = m.ler(p)
    assert r.versao_original == "0.1.0" and r.manifesto["versao_formato"] == "0.2.0" and "provisorio" not in r.manifesto
    assert r.lateral.obter("vistas", "abc") == ruim and r.lateral.obter("styles", "e1") == {"x": 1}


@AINDA_NAO
def test_22_regravar_0_2_x_maior_sai_0_2_0_e_preserva(proj):  # noqa: F811
    m = ob()
    _fabrica(proj)
    o = proj.destino.with_suffix(".obim")
    proj.gravar()
    r = m.ler(o)
    m.escrever(o, r.lateral, {**r.manifesto, "versao_formato": "0.2.7", "campo_027": {"a": 1}})
    proj.tx(2)
    proj.gravar()
    r2 = m.ler(o)
    assert r2.manifesto["versao_formato"] == "0.2.0" and r2.manifesto["campo_027"] == {"a": 1}


@AINDA_NAO
def test_23_viewport_para_vista_ou_prancha_inexistente_vira_orfao(tmp_path):
    m, p = ob(), tmp_path / "f.obim"
    novo = {"prancha": "Z-99", "vista_guid": "Nao$Existe00000000000", "x": 1, "y": 2, "escala": 100}
    vps = {**objetos()["viewports"], "vpx": novo}
    l = lat(viewports=vps)
    m.escrever(p, l, MAN)  # não é rejeitado
    r = m.ler(p).lateral
    assert r.obter("viewports", "vpx") == novo
    assert m.orfaos(r, {G1, "3cUz$7rQ0aLm9XyN2bP_Hd"}, {IDENT})["viewports"] == ["vpx"]
    assert m.orfaos(r, {G1, "3cUz$7rQ0aLm9XyN2bP_Hd", "Nao$Existe00000000000"}, {IDENT})["viewports"] == ["vpx"], "prancha Z-99 inexistente também é órfã"
