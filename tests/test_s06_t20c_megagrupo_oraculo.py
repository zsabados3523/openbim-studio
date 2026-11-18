# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T20c: megagrupo vai direto para faixas, sem lote de 300 s (T3). Cartao: docs/state/cards/F0-S06/F0-S06-T20c-megagrupo-direto-em-faixas.md.
Contrato: em `_planta_por_componentes`, grupo com mais de `LIMIAR_MEGAGRUPO_FRACAO` (0,5) das pecas selecionadas OU mais de `LIMIAR_MEGAGRUPO_PECAS` (200) pecas
(comparacao estrita `>`) NAO entra em lote: vai a `_planta_em_faixas(..., 8)`. Grupos pequenos seguem em lote. Mesmo conjunto de pecas no SVG que o caminho
antigo (timeout + retry), sem duplicar. `tempos["megagrupo_direto"]` True/False (chave sempre presente). Com megagrupo: n_timeouts == 0 e refaz_faixas_s == 0.
Cena: cadeia de 5 caixas encostadas (megagrupo, 5/8), par de caixas encostadas e 1 caixa isolada. Constantes mexidas via monkeypatch(raising=False)."""
from __future__ import annotations

import copy

import pytest

import obim_geometria.desenho as D
from test_s06_t19h_componentes_oraculo import _caixa, _cena, _guids
from test_s06_t19i1_nunca_descartar_oraculo import Fake, _cena3


class Espia(Fake):
    """Fake do T19i1 que tambem registra os pedidos de lote (op desenho_lote)."""

    def __init__(self, *a, **k):
        self.lotes = []
        super().__init__(*a, **k)

    def __call__(self, pedido, *a, **k):
        if pedido.get("op") == "desenho_lote":
            self.lotes.append(copy.deepcopy(pedido))
        return super().__call__(pedido, *a, **k)

    def ids_em_lote(self):
        return [i for lt in self.lotes for q in lt["pedidos"] for i, _ in q["elementos"]]


def _cena_mega(tmp_path):
    """8 pecas: cadeia de 5 (megagrupo), par de 2 e 1 isolada. Devolve (pedido, ids_mega, ids_pequenos)."""
    ms = [_caixa(k, 0, 0, k + 1, 1, 1) for k in range(5)] + [_caixa(20, 0, 0, 21, 1, 1), _caixa(21, 0, 0, 22, 1, 1), _caixa(10, 0, 0, 11, 1, 1)]
    ped, ids = _cena(tmp_path, ms, corte=0.5)
    ped.update({"componentes": True, "threads": 2})
    return ped, ids[:5], ids[5:]


def _espia_faixas(monkeypatch):
    chamadas, orig = [], D._planta_em_faixas

    def esp(pedido, fase, n, *a, **k):
        chamadas.append((sorted(i for i, _ in pedido["elementos"]), n))
        return orig(pedido, fase, n, *a, **k)
    monkeypatch.setattr(D, "_planta_em_faixas", esp)
    return chamadas


def _limiares(monkeypatch, fracao=0.5, pecas=200):
    monkeypatch.setattr(D, "LIMIAR_MEGAGRUPO_FRACAO", fracao, raising=False)
    monkeypatch.setattr(D, "LIMIAR_MEGAGRUPO_PECAS", pecas, raising=False)


def _completo(r, ped):
    gs = _guids(r["svg"])
    assert sorted(gs) == sorted(set(gs)), "grupo duplicado no SVG"
    assert set(gs) == {g for _, g in ped["elementos"]}
    assert not r.get("incompleta") and not r.get("faltantes") and not r["falhas_geometria"]


def test_1_megagrupo_nao_entra_em_lote_e_vai_direto_a_faixas(monkeypatch, tmp_path):
    ped, mega, peq = _cena_mega(tmp_path)
    _limiares(monkeypatch)
    fk = Espia(monkeypatch, mega, "lote_morto")  # se o megagrupo entrasse em lote, estouraria por Tempo
    fx = _espia_faixas(monkeypatch)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"]
    assert not set(fk.ids_em_lote()) & set(mega), "megagrupo entrou em lote"
    assert any(set(mega) <= set(ids) and n == 8 for ids, n in fx), f"_planta_em_faixas(n=8) nao chamada com o megagrupo: {fx}"
    t = r["tempos"]
    assert t["n_timeouts"] == 0 and t["refaz_faixas_s"] == 0.0 and t["megagrupo_direto"] is True
    _completo(r, ped)


def test_2_mesmo_conjunto_de_pecas_do_caminho_antigo(monkeypatch, tmp_path):
    ped, mega, peq = _cena_mega(tmp_path)
    # caminho antigo: megagrupo desligado pelos limiares, lote do megagrupo estoura (Tempo) e refaz em faixas
    _limiares(monkeypatch, fracao=2.0, pecas=10**9)
    Espia(monkeypatch, mega, "lote_morto")
    antigo = D.processar(copy.deepcopy(ped))
    assert antigo["ok"] and antigo["tempos"]["n_timeouts"] >= 1
    monkeypatch.undo()
    _limiares(monkeypatch)
    Espia(monkeypatch, mega, "lote_morto")
    novo = D.processar(copy.deepcopy(ped))
    assert novo["ok"] and novo["tempos"]["megagrupo_direto"] is True
    assert sorted(_guids(novo["svg"])) == sorted(_guids(antigo["svg"]))
    assert novo["grupos"] == antigo["grupos"] == 3 and sorted(map(sorted, novo["grupos_ids"])) == sorted(map(sorted, antigo["grupos_ids"]))
    assert sorted(novo["falhas_geometria"]) == sorted(antigo["falhas_geometria"]) and novo.get("incompleta") == antigo.get("incompleta")
    _completo(novo, ped)


def test_3_sem_megagrupo_identico_a_hoje(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)  # grupos 1, 1, 2 de 4 pecas
    _limiares(monkeypatch)
    fk = Espia(monkeypatch, ruins, None)
    fx = _espia_faixas(monkeypatch)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and not fx and not fk.avulsos
    assert sorted(fk.ids_em_lote()) == sorted(ids), "todas as pecas devem ir por lote"
    t = r["tempos"]
    assert t["megagrupo_direto"] is False and t["n_timeouts"] == 0 and t["n_grupos"] == 3 and t["maior_grupo"] == 2
    _completo(r, ped)


def test_3b_sem_megagrupo_com_falha_segue_timeout_e_retry(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)
    _limiares(monkeypatch)
    fk = Espia(monkeypatch, ruins, "lote_morto")
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and fk.avulsos and r["tempos"]["n_timeouts"] >= 1 and r["tempos"]["refaz_faixas_s"] > 0.0
    assert r["tempos"]["megagrupo_direto"] is False
    _completo(r, ped)


def test_4_limiar_estrito_no_limite_nao_vira_megagrupo(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)  # maior grupo 2 de 4 pecas = exatamente 50%
    _limiares(monkeypatch, fracao=0.5, pecas=200)
    Espia(monkeypatch, ruins, None)
    assert D.processar(copy.deepcopy(ped))["tempos"]["megagrupo_direto"] is False
    ped, mega, peq = _cena_mega(tmp_path)  # grupo de 5 de 8 (62,5%) passa de 50%
    _limiares(monkeypatch, fracao=0.5, pecas=200)
    Espia(monkeypatch, mega, None)
    assert D.processar(copy.deepcopy(ped))["tempos"]["megagrupo_direto"] is True
    # limite por contagem: maior grupo = 5; `pecas=5` nao e mega (estrito), `pecas=4` e
    for pecas, esperado in ((5, False), (4, True)):
        _limiares(monkeypatch, fracao=0.99, pecas=pecas)
        Espia(monkeypatch, mega, None)
        assert D.processar(copy.deepcopy(ped))["tempos"]["megagrupo_direto"] is esperado, pecas
    _limiares(monkeypatch, fracao=0.625, pecas=200)  # 5/8 = 0,625 exato: no limite, nao e mega
    Espia(monkeypatch, mega, None)
    assert D.processar(copy.deepcopy(ped))["tempos"]["megagrupo_direto"] is False


def test_5_megagrupo_e_grupos_pequenos_juntos_sem_duplicar(monkeypatch, tmp_path):
    ped, mega, peq = _cena_mega(tmp_path)
    _limiares(monkeypatch)
    fk = Espia(monkeypatch, mega, None)
    fx = _espia_faixas(monkeypatch)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["grupos"] == 3
    assert sorted(fk.ids_em_lote()) == sorted(peq), "grupos pequenos devem ir por lote, cada peca uma vez"
    assert sum(1 for ids, _ in fx if set(mega) & set(ids)) == 1, f"megagrupo deve rodar uma unica vez em faixas: {fx}"
    assert not any(set(peq) & set(ids) for ids, _ in fx)
    assert r["tempos"]["n_grupos"] == 3 and r["tempos"]["maior_grupo"] == 5
    _completo(r, ped)


def test_6_megagrupo_que_falha_em_faixas_vira_faltante_nao_some(monkeypatch, tmp_path):
    ped, mega, peq = _cena_mega(tmp_path)
    _limiares(monkeypatch)
    Espia(monkeypatch, mega, None, refaz_falha=True)  # faixas do megagrupo falham (filho levanta / _processar_base falha)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["incompleta"] is True and sorted(r["faltantes"]) == sorted(mega)
    gs = set(_guids(r["svg"]))
    assert all(g in gs or i in r["faltantes"] for i, g in ped["elementos"]), "peca sumiu em silencio"
    assert {g for i, g in ped["elementos"] if i in peq} <= gs
