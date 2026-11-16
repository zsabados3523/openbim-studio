# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19i1: planta nunca descarta grupo em silencio (T3). Cartao: docs/state/cards/F0-S06/F0-S06-T19i1-nunca-descartar-grupo.md. Nao editar nesta tarefa.
CONTRATO (resumo): grupo que falha no lote (item None/ok False/lote morto; nao Divergente) e refeito pelo caminho de faixas (pedido sem `componentes`);
se falhar de novo: resposta `incompleta=True`, `faltantes` = ids do grupo, ids tambem em `falhas_geometria`, raiz do SVG com `data-obim-incompleta="N"`.
Todo elemento do pedido esta no SVG ou em `faltantes`. Caminho feliz inalterado. `Planta.faltantes=()` + propriedade `incompleta`; gerente repassa em `dados`."""
from __future__ import annotations

import contextlib
import copy
import re
from types import SimpleNamespace

import ifcopenshell.util.unit
import pytest

import obim_geometria.desenho as D
import obim_geometria.faixas as F
from test_s06_t19h_componentes_oraculo import _caixa, _cena, _guids
from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, planta as PL, selecao


def _cena3(tmp_path):
    """4 caixas: A, B isoladas; C e C2 encostadas (um grupo de 2). Devolve (pedido, ids, ids_do_grupo_ruim)."""
    ms = [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(6, 0, 0, 7, 1, 1), _caixa(7, 0, 0, 8, 1, 1)]
    ped, ids = _cena(tmp_path, ms, corte=0.5)
    ped.update({"componentes": True, "threads": 2})
    return ped, ids, ids[2:]


class Fake:
    """Substitui `faixas.rodar_filho`. `modo`: item_none | item_erro | lote_morto | divergente (no grupo ruim do lote). `refaz_falha`: pedido sem lote com id ruim falha."""

    def __init__(self, monkeypatch, ruins, modo=None, refaz_falha=False):
        self.ruins, self.modo, self.refaz_falha, self.avulsos = set(ruins), modo, refaz_falha, []
        monkeypatch.setattr(F, "rodar_filho", self)
        if refaz_falha:  # o refazer tambem cai no caminho normal em-processo: faz ele falhar para o id ruim
            orig = D._processar_base
            monkeypatch.setattr(D, "_processar_base", lambda p, *a, **k: (
                {"ok": False, "erro": {"tipo": "Simulado", "mensagem": "x", "rastro": ""}}
                if self.ruins & {i for i, _ in p.get("elementos") or ()} else orig(p, *a, **k)))

    def _ruim(self, q):
        return bool(self.ruins & {i for i, _ in q["elementos"]})

    def __call__(self, pedido, *a, **k):
        if pedido.get("op") != "desenho_lote":
            self.avulsos.append(copy.deepcopy(pedido))
            if self.refaz_falha and self._ruim(pedido):
                raise RuntimeError("refazer falhou (simulado)")
            return D.processar(copy.deepcopy(pedido))
        if self.modo == "lote_morto" and any(self._ruim(q) for q in pedido["pedidos"]):
            return {"ok": False, "erro": {"tipo": "Tempo", "mensagem": "estourou", "rastro": ""}}
        itens = []
        for q in pedido["pedidos"]:
            if self.modo and self.modo != "lote_morto" and self._ruim(q):
                itens.append(None if self.modo == "item_none" else {"ok": False, "erro": {
                    "tipo": "Divergente" if self.modo == "divergente" else "Simulado", "mensagem": "x", "rastro": ""}})
            else:
                itens.append(D.processar(copy.deepcopy(q)))
        return {"ok": True, "resultados": itens}


def _guid_de(ped):
    return {i: g for i, g in ped["elementos"]}


@pytest.mark.parametrize("modo", ["item_none", "item_erro", "lote_morto"])
def test_a_grupo_que_falha_e_refeito_e_aparece_no_svg(monkeypatch, tmp_path, modo):
    ped, ids, ruins = _cena3(tmp_path)
    fk = Fake(monkeypatch, ruins, modo)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and fk.avulsos, "grupo falho deve ser refeito por pedido sem lote"
    assert all("componentes" not in q for q in fk.avulsos)
    assert set(_guids(r["svg"])) >= set(_guid_de(ped).values())
    assert not r.get("incompleta") and not r.get("faltantes") and not r["falhas_geometria"]
    assert "data-obim-incompleta" not in r["svg"]


@pytest.mark.parametrize("modo", ["item_none", "item_erro"])
def test_b_c_refazer_tambem_falha_marca_incompleta_e_invariante(monkeypatch, tmp_path, modo):
    ped, ids, ruins = _cena3(tmp_path)
    Fake(monkeypatch, ruins, modo, refaz_falha=True)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["incompleta"] is True
    assert sorted(r["faltantes"]) == sorted(ruins) and set(ruins) <= set(r["falhas_geometria"])
    assert re.search(r'<svg\b[^>]*\bdata-obim-incompleta="%d"' % len(ruins), r["svg"])
    gs = set(_guids(r["svg"]))
    for i, g in ped["elementos"]:  # invariante: no SVG ou em faltantes
        assert g in gs or i in r["faltantes"], f"elemento {i} sumiu em silencio"
    assert {_guid_de(ped)[i] for i in ids[:2]} <= gs


def test_d_divergente_propaga_sem_retry(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)
    fk = Fake(monkeypatch, ruins, "divergente")
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente" and not fk.avulsos


def test_e_caminho_feliz_sem_campos_novos(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)
    fk = Fake(monkeypatch, ruins, None)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and not fk.avulsos and r["falhas_geometria"] == []
    assert not r.get("incompleta") and not r.get("faltantes") and "data-obim-incompleta" not in r["svg"]
    assert set(_guids(r["svg"])) == set(_guid_de(ped).values())


def _planta(**kw):
    base = dict(svg="", n_paths=0, selecao=None, tempos={}, unidade_escala=1.0, altura_corte=0.0, caixas=())
    return PL.Planta(**base, **kw)


def test_f_planta_faltantes_padrao_e_propriedade():
    assert _planta().faltantes == () and _planta().incompleta is False
    p = _planta(faltantes=(3, 4))
    assert p.faltantes == (3, 4) and p.incompleta is True


def _stub_gerar(monkeypatch, resposta):
    pav = SimpleNamespace(Elevation=0.0, ObjectPlacement=None, Name="P", GlobalId="PAV")
    ifc = SimpleNamespace(by_guid=lambda g: object(), by_id=lambda i: pav if i == 9 else SimpleNamespace(GlobalId=f"G{i}"))
    sel = SimpleNamespace(ids=[1, 2], pavimento=9, caixas_envolventes={})
    monkeypatch.setattr(vistas_ifc, "ler_vista", lambda *a, **k: {"tipo": "PLANTA"})
    monkeypatch.setattr(selecao, "selecionar", lambda *a, **k: sel)
    monkeypatch.setattr(selecao, "_validar_categorias", lambda *a, **k: None)
    monkeypatch.setattr(PL, "_altura_corte", lambda *a, **k: 1.2)
    monkeypatch.setattr(ifcopenshell.util.unit, "calculate_unit_scale", lambda *a, **k: 1.0)
    monkeypatch.setattr(auxiliar, "preparar", lambda *a, **k: contextlib.nullcontext(None))
    monkeypatch.setattr(auxiliar, "executar", lambda *a, **k: resposta)
    return ifc


def test_f_gerar_planta_preenche_faltantes(monkeypatch):
    base = {"svg": "<svg/>", "n_paths": 0, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []}
    ifc = _stub_gerar(monkeypatch, {**base, "incompleta": True, "faltantes": [2]})
    p = PL.gerar_planta(ifc, "V")
    assert p.faltantes == (2,) and p.incompleta is True
    ifc = _stub_gerar(monkeypatch, base)
    p = PL.gerar_planta(ifc, "V")
    assert p.faltantes == () and p.incompleta is False


@pytest.mark.parametrize("faltantes", [(5, 7), ()])
def test_g_gerente_repassa_incompleta_e_faltantes(monkeypatch, faltantes):
    from openbim_app.desenho import gerente as G
    r = SimpleNamespace(svg="<svg/>", n_paths=0, tempos={"geo_s": 0.0}, caixas=(1,), em_cache=(), pesados=(), pedido={},
                        faltantes=faltantes, incompleta=bool(faltantes))
    monkeypatch.setattr(PL, "gerar_planta", lambda *a, **k: r)
    d = G._motor_padrao("planta", object(), "V", {}, cancelar=None, progresso=lambda *_: None, cache=None)
    assert d["incompleta"] is bool(faltantes) and list(d["faltantes"]) == list(faltantes)
    assert {"svg", "n_paths", "tempos", "caixas", "em_cache", "pesados"} <= set(d)
