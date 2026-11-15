# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19d5: poda por caixa/janela ANTES de `silhueta.formas_do_mundo` em `desenho._corte` (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19d5-*.md. Não editar nesta tarefa.
CONTRATO (`pedido["motor_visivel"]` verdadeiro):
1. Os `cands` do motor (não porta/janela, sem HasOpenings, com Representation) cuja caixa em `caixas_coords` não toca a janela (+0,1 m) NÃO são lidos:
   `silhueta.formas_do_mundo` só recebe peças que tocam a janela ou sem caixa válida (ausente = toca).
2. SVG igual ao da T19d4 para as peças que ficam (tampas com os mesmos `d`).
3. Falha do motor (`linhas_visiveis_vista` levanta) ou de `formas_do_mundo`: cai para o HLR com TODAS as peças (grupo da peça fora presente), sem levantar.
4. Sem `motor_visivel`: `formas_do_mundo` não é chamada e nada muda."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from test_s06_t19d2_motor_no_corte_oraculo import ELEGIVEIS, COM_TAMPA, _cena, _roda
from test_s06_t19d4_poda_oraculo import _caixa_uv, _ds, _guids, _dentro

import obim_geometria.silhueta as S
import obim_geometria.visibilidade as V

W = 10.0


def _fora(c):
    return _caixa_uv(c, 7.0, 8.0, -1, 1)


def _coords(c, caixas, chave=int):
    return {chave(c.ids[n]): b for n, b in caixas.items()}


def _espia(monkeypatch, quebra=False):
    """Troca `silhueta.formas_do_mundo` por espião; devolve a lista de ids STEP recebidos (todas as chamadas)."""
    real = S.formas_do_mundo
    vistos = []

    def espiao(f, elementos, *a, **k):
        vistos.append([el.id() for el in elementos])
        if quebra:
            raise RuntimeError("falha injetada em formas_do_mundo")
        return real(f, elementos, *a, **k)

    monkeypatch.setattr(S, "formas_do_mundo", espiao)
    return vistos


def _recebidas(vistos):
    return {i for lote in vistos for i in lote}


@pytest.fixture
def cena(tmp_path):
    c = _cena(tmp_path)
    ref = _roda(c, motor_visivel=True)
    assert ref["ok"], ref.get("erro")
    c.ref = ref
    return c


# ---------------------------------------------------------------- 1: fora da janela não é lido
@pytest.mark.parametrize("chave", [int, str])
def test_candidata_fora_nao_chega_a_formas_do_mundo(monkeypatch, cena, chave):
    c = cena
    vistos = _espia(monkeypatch)
    caixas = {"K1": _dentro(c), "MesaA": _dentro(c), "Moldura": _dentro(c), "Oclusor": _fora(c), "MesaB": _fora(c)}
    r = _roda(c, caixas_coords=_coords(c, caixas, chave), motor_visivel=True)
    assert r["ok"], r.get("erro")
    assert vistos, "formas_do_mundo tem de ser chamada (há candidatas dentro)"
    got = _recebidas(vistos)
    assert not got & {c.ids["Oclusor"], c.ids["MesaB"]}, "candidata fora da janela foi lida"
    assert {c.ids[n] for n in ("K1", "MesaA", "Moldura")} <= got
    assert not got & {c.ids["Porta"], c.ids["Parede"]}, "inelegíveis nunca vão ao motor"


@pytest.mark.parametrize("lado", [-1, 1])
def test_fora_em_v_tambem_nao_e_lida(monkeypatch, cena, lado):
    c = cena
    vistos = _espia(monkeypatch)
    a = 2.0 + 0.1 + 0.2
    v0, v1 = (a, a + 1.0) if lado > 0 else (-a - 1.0, -a)
    r = _roda(c, caixas_coords=_coords(c, {"Oclusor": _caixa_uv(c, -4.0, 4.0, v0, v1)}), motor_visivel=True)
    assert r["ok"]
    assert c.ids["Oclusor"] not in _recebidas(vistos)
    assert c.ids["K1"] in _recebidas(vistos), "peça sem caixa é lida"


def test_candidata_sem_caixa_e_lida(monkeypatch, cena):
    c = cena
    vistos = _espia(monkeypatch)
    r = _roda(c, caixas_coords=_coords(c, {"MesaB": _fora(c)}), motor_visivel=True)  # Oclusor sem entrada
    assert r["ok"]
    got = _recebidas(vistos)
    assert c.ids["Oclusor"] in got and c.ids["MesaB"] not in got


@pytest.mark.parametrize("invalida", [[0.0, 0.0, 0.0], [float("nan")] * 6, None, "abc", []])
def test_caixa_invalida_e_lida(monkeypatch, cena, invalida):
    c = cena
    vistos = _espia(monkeypatch)
    r = _roda(c, caixas_coords=_coords(c, {"Oclusor": invalida, "MesaB": _fora(c)}), motor_visivel=True)
    assert r["ok"]
    got = _recebidas(vistos)
    assert c.ids["Oclusor"] in got and c.ids["MesaB"] not in got


@pytest.mark.parametrize("lado", [-1, 1])
def test_borda_dentro_da_folga_e_lida(monkeypatch, cena, lado):
    c = cena
    vistos = _espia(monkeypatch)
    a = W / 2 + 0.05
    faixa = (a, a + 1.0) if lado > 0 else (-a - 1.0, -a)
    r = _roda(c, caixas_coords=_coords(c, {"Oclusor": _caixa_uv(c, *faixa, -1.5, 1.5), "MesaB": _fora(c)}), motor_visivel=True)
    assert r["ok"]
    got = _recebidas(vistos)
    assert c.ids["Oclusor"] in got and c.ids["MesaB"] not in got


def test_todas_candidatas_fora_svg_valido(monkeypatch, cena):
    c = cena
    vistos = _espia(monkeypatch)
    caixas = {n: _fora(c) for n in ELEGIVEIS}
    r = _roda(c, caixas_coords=_coords(c, caixas), motor_visivel=True)
    assert r["ok"], r.get("erro")
    assert not _recebidas(vistos), "nenhuma candidata toca a janela: nada a ler (chamada vazia ou nenhuma)"
    ET.fromstring(r["svg"])
    assert r["n_paths"] == len(re.findall(r"<path\b", r["svg"]))


# ---------------------------------------------------------------- 2: o resto do SVG não muda
def test_tampas_das_que_ficam_identicas(cena):
    c = cena
    caixas = {"K1": _dentro(c), "MesaA": _dentro(c), "Moldura": _dentro(c), "Oclusor": _fora(c), "MesaB": _fora(c)}
    r = _roda(c, caixas_coords=_coords(c, caixas), motor_visivel=True)
    assert r["ok"], r.get("erro")
    for n in COM_TAMPA:
        assert _ds(c.ref["svg"], c.guids[n]) and _ds(r["svg"], c.guids[n]) == _ds(c.ref["svg"], c.guids[n]), f"tampa de {n} mudou"
    assert {"Parede", "Porta"} <= _guids(r["svg"], c)


# ---------------------------------------------------------------- 3: falhas caem para o HLR com todas as peças
def test_falha_do_motor_hlr_recebe_todas(monkeypatch, cena):
    c = cena

    def quebra(*a, **k):
        raise RuntimeError("falha injetada")

    monkeypatch.setattr(V, "linhas_visiveis_vista", quebra)
    caixas = {"K1": _fora(c), "Parede": _fora(c), "Porta": _dentro(c)}
    r = _roda(c, caixas_coords=_coords(c, caixas), motor_visivel=True)
    assert r["ok"], r.get("erro")
    assert r["motor_pecas"] == []
    g = _guids(r["svg"], c)
    assert "K1" in g, "na queda o HLR recebe TODAS as peças, também as fora da janela"


def test_excecao_em_formas_do_mundo_cai_para_hlr_com_todas(monkeypatch, cena):
    c = cena
    _espia(monkeypatch, quebra=True)
    caixas = {"K1": _fora(c), "MesaA": _dentro(c)}
    r = _roda(c, caixas_coords=_coords(c, caixas), motor_visivel=True)
    assert r["ok"], r.get("erro")
    g = _guids(r["svg"], c)
    assert "K1" in g and "MesaA" in g, "queda: HLR com todas as peças, também a fora da janela"


# ---------------------------------------------------------------- 4: sem motor_visivel nada muda
@pytest.mark.parametrize("motor", [False, None])
def test_sem_motor_visivel_nao_chama_formas_do_mundo(monkeypatch, cena, motor):
    c = cena
    base = _roda(c)
    vistos = _espia(monkeypatch)
    extra = {} if motor is None else {"motor_visivel": motor}
    r = _roda(c, caixas_coords=_coords(c, {"K1": _fora(c), "Oclusor": _fora(c)}), **extra)
    assert r["ok"] and r["svg"] == base["svg"]
    assert not vistos
