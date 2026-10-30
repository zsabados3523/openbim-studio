# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T05, 2a rodada da revisão (R-1, R-2; `docs/state/reports/F0-S06-T05-revisao.md`). Contrato em `test_s06_t05_obim_zip_oraculo.py`.
R-1: só é reservado para `extras` o nome `manifest.json` e o que casa `<coleção>/<id>.json` (regra do `ler`); `vistas/previa.png` e `notas/x.txt` são
entradas desconhecidas dentro de pasta conhecida e têm de passar (ADR-003 §4). R-2: `.obim` de versão maior que não dá para ler por inteiro (ex. 0.3.0 com
`novos/lista.json` = lista) é recusado por `gravar_par`, par e `.bak` intactos; `.obim` ilegível sem versão confiável continua sendo sobrescrito.
Marcadores retirados."""
import json
import zipfile

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401
from test_s06_t05_obim_zip_oraculo import G1, MAN, _fabrica, canon, lat, ob, proj  # noqa: F401

EXTRAS = {"vistas/previa.png": b"\x89PNG\x00\xff", "notas/x.txt": "texto livre ç".encode()}


def _obim_cru(o, manifesto, entradas):
    with zipfile.ZipFile(o, "w") as z:
        z.writestr("manifest.json", json.dumps(manifesto))
        for nome, dados in entradas.items():
            z.writestr(nome, dados)


def test_01_r1_extra_dentro_de_pasta_conhecida_passa_por_escrever(tmp_path):
    m, p = ob(), tmp_path / "f.obim"
    m.escrever(p, lat(), MAN, EXTRAS)
    assert m.ler(p).extras == EXTRAS


def test_02_r1_gravar_par_repassa_extra_dentro_de_pasta_conhecida(proj, base_ifc):  # noqa: F811
    m = ob()
    _fabrica(proj)
    X.escrever_par_falso(proj.destino, base_ifc, {"notas": {"n0": {"texto": "primeira"}}}, 5)
    o = proj.destino.with_suffix(".obim")
    _obim_cru(o, MAN, EXTRAS)
    proj.gravar()
    r = m.ler(o)
    assert r.extras == EXTRAS and canon(r.lateral) == canon(proj.lat), "extra em pasta conhecida perdido ou gravar_par falhou"


def _antigo(proj, base_ifc, manifesto, entradas):  # noqa: F811
    X.escrever_par_falso(proj.destino, base_ifc, {"notas": {"n0": {"texto": "primeira"}}}, 5)
    o = proj.destino.with_suffix(".obim")
    _obim_cru(o, manifesto, entradas)
    return X.Antigo(proj.destino.read_bytes(), o.read_bytes())


@pytest.mark.parametrize("entradas", [{"novos/lista.json": "[1, 2]"}, {"vistas/a.json": "[1, 2]"}], ids=["pasta nova com lista", "vista com lista"])
def test_03_r2_versao_maior_ilegivel_recusa_e_nada_muda(proj, base_ifc, entradas):  # noqa: F811
    _fabrica(proj)
    antigo = _antigo(proj, base_ifc, {**MAN, "versao_formato": "0.3.0", "campo_novo": 1}, entradas)
    with pytest.raises(Exception) as e:
        proj.gravar()
    assert "Casa.obim" in str(e.value)
    assert X.estado_par(proj.destino, antigo, None, proj.pasta) == ("antigo", []), "par mudou, ou sobrou .tmp"
    assert not proj.destino.with_name("Casa.obim.bak").exists() and not proj.destino.with_name("Casa.ifc.bak").exists()
    assert proj.chamadas == []


@pytest.mark.parametrize("manifesto,entradas", [({k: v for k, v in MAN.items() if k != "versao_formato"}, {"novos/lista.json": "[1, 2]"}),
                                               ({**MAN, "versao_formato": "lixo"}, {"vistas/a.json": "[1]"}),
                                               ({**MAN, "versao_formato": 3}, {"vistas/a.json": "[1]"})],
                         ids=["sem versao_formato", "versao texto lixo", "versao nao texto"])
def test_04_r2_sem_versao_confiavel_continua_sobrescrito(proj, base_ifc, manifesto, entradas):  # noqa: F811
    m = ob()
    _fabrica(proj)
    ruim = _antigo(proj, base_ifc, manifesto, entradas).obim
    proj.gravar()
    assert proj.destino.with_name("Casa.obim.bak").read_bytes() == ruim
    assert canon(m.ler(proj.destino.with_suffix(".obim")).lateral) == canon(proj.lat)
