# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19e1: uma só triangulação paralela no pai da planta por componentes (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19e1-formas-compartilhadas.md. Não editar nesta tarefa.
Medido (casarão, SUBSOLO REBAIXADO, 57 elementos): a preparação do pai leva 329 s, 237 s deles em 57 `create_shape` um por um (1 thread) + `dividir_elementos` triangula tudo de novo.
CONTRATO:
1. `silhueta.formas_do_mundo(f, elementos, threads=None) -> dict[int, forma]`: `elementos` = lista de entity_instance; UM `ifcopenshell.geom.iterator` (USE_WORLD_COORDS, `nucleos.limitar_threads(threads)`, `include=` os elementos);
   chave = id STEP, valor = a forma do iterador (tem `.geometry.verts/.faces`, iguais aos de `create_shape` em coordenadas do mundo). Elemento sem geometria fica de fora. Lista vazia -> {}. Nunca levanta (erro -> o que já coletou).
2. `desenho._pesadas_para_svg(f, pedido, elementos, altura_corte_m, formas=None)`: mesmo retorno de hoje. Se `formas` (dict) é dado, é cache e é PREENCHIDO: ids ainda ausentes vêm de UMA chamada a `silhueta.formas_do_mundo`
   (nunca `create_shape` por elemento) e cada candidato usa `formas[id]` em `faces_e_silhueta`; quem não aparece no dict cai no comportamento antigo (`create_shape` do próprio elemento).
3. `componentes.dividir_elementos(arquivo, elementos, folga=FOLGA, threads=None, formas=None)`: ids presentes em `formas` usam essas formas; o iterador só roda para os que faltam (nenhum -> não roda, e o arquivo nem é aberto);
   as pegadas são calculadas em `ThreadPoolExecutor(max_workers=limitar_threads(threads))`. Resultado idêntico ao de antes.
4. `desenho._planta_por_componentes` cria `formas = {}` e a passa às duas chamadas. No thread do pai, `processar(pedido com componentes e pesados="silhueta")` faz 0 `create_shape` e exatamente 1 `iterator`."""
from __future__ import annotations

import copy
import threading

import numpy as np
import pytest
import ifcopenshell
import ifcopenshell.geom

import obim_geometria.componentes as C
import obim_geometria.desenho as D
import obim_geometria.silhueta as S
from test_s06_t19h_componentes_oraculo import Espiao, _caixa, _cena, _prisma_ou


def _els(ped):
    f = ifcopenshell.open(ped["arquivo"])
    return f, [f.by_id(i) for i, _ in ped["elementos"]]


def test_formas_do_mundo_igual_a_create_shape(tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _prisma_ou(40, 0.5, 1.0, 5, 0), _caixa(9, 0, 0, 10, 2, 1)])
    f, els = _els(ped)
    formas = S.formas_do_mundo(f, els, threads=2)
    assert sorted(formas) == sorted(ids)
    cfg = ifcopenshell.geom.settings()
    cfg.set(cfg.USE_WORLD_COORDS, True)
    for el in els:
        ref = ifcopenshell.geom.create_shape(cfg, el).geometry
        got = formas[el.id()].geometry
        gv, rv = (np.unique(np.round(np.asarray(x.verts, float).reshape(-1, 3), 6), axis=0) for x in (got, ref))  # T19g: leitura direta pode reordenar vertices
        assert gv.shape == rv.shape and np.allclose(gv, rv, atol=1e-6) and len(got.faces) == len(ref.faces)


def test_formas_do_mundo_vazio_e_sem_geometria(tmp_path):
    ped, _ = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1)])
    f, els = _els(ped)
    assert S.formas_do_mundo(f, [], threads=1) == {}
    assert S.formas_do_mundo(f, f.by_type("IfcBuildingStorey"), threads=1) == {}


def test_dividir_elementos_com_formas_nao_triangula_de_novo(monkeypatch, tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(0.5, 0.5, 0, 3.5, 0.9, 1)])
    f, els = _els(ped)
    base = C.dividir_elementos(ped["arquivo"], ped["elementos"], threads=1)
    formas = S.formas_do_mundo(f, els, threads=1)
    chamadas = []
    orig = ifcopenshell.geom.iterator
    monkeypatch.setattr(ifcopenshell.geom, "iterator", lambda *a, **k: chamadas.append(1) or orig(*a, **k))
    abertos = []
    orig_open = ifcopenshell.open
    monkeypatch.setattr(ifcopenshell, "open", lambda *a, **k: abertos.append(1) or orig_open(*a, **k))
    assert C.dividir_elementos(ped["arquivo"], ped["elementos"], threads=1, formas=formas) == base
    assert not chamadas and not abertos, "com todas as formas prontas não há iterador nem abertura de arquivo"
    parcial = {k: v for k, v in formas.items() if k != ids[1]}
    assert C.dividir_elementos(ped["arquivo"], ped["elementos"], threads=1, formas=parcial) == base and len(chamadas) == 1


def test_pesadas_para_svg_preenche_formas_com_uma_passada(monkeypatch, tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _prisma_ou(40, 0.5, 1.0, 5, 0), _prisma_ou(40, 0.5, 1.0, 9, 0)], corte=0.5)
    ped.update({"pesados": "silhueta", "limiar_pesado": 100})
    f, els = _els(ped)
    n_cs, n_it = [], []
    o_cs, o_it = ifcopenshell.geom.create_shape, ifcopenshell.geom.iterator
    monkeypatch.setattr(ifcopenshell.geom, "create_shape", lambda *a, **k: n_cs.append(1) or o_cs(*a, **k))
    monkeypatch.setattr(ifcopenshell.geom, "iterator", lambda *a, **k: n_it.append(1) or o_it(*a, **k))
    formas = {}
    svg, info, desenhados, fora = D._pesadas_para_svg(f, ped, ped["elementos"], 0.5, formas=formas)
    assert sorted(desenhados) == sorted(ids[1:]) and [i["id"] for i in info] == ids[1:]
    assert sorted(formas) == sorted(ids) and len(n_it) <= 1 and not n_cs


def test_pai_da_planta_por_componentes_faz_zero_create_shape_e_um_iterador(monkeypatch, tmp_path):
    malhas = [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _prisma_ou(40, 0.5, 1.0, 8, 0), _caixa(12, 0, 0, 13, 1, 1)]
    ped, ids = _cena(tmp_path, malhas, corte=0.5)
    ped.update({"pesados": "silhueta", "limiar_pesado": 100, "componentes": True})
    Espiao(monkeypatch)
    pai = threading.get_ident()
    n_cs, n_it = [], []
    o_cs, o_it = ifcopenshell.geom.create_shape, ifcopenshell.geom.iterator
    def cs(*a, **k):
        if threading.get_ident() == pai:
            n_cs.append(1)
        return o_cs(*a, **k)
    def it(*a, **k):
        if threading.get_ident() == pai:
            n_it.append(1)
        return o_it(*a, **k)
    monkeypatch.setattr(ifcopenshell.geom, "create_shape", cs)
    monkeypatch.setattr(ifcopenshell.geom, "iterator", it)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["grupos"] == 3 and [p["id"] for p in r["pesados"]] == [ids[2]]
    assert not n_cs and len(n_it) <= 1, f"create_shape no pai: {len(n_cs)}, iteradores no pai: {len(n_it)}"


def test_dividir_elementos_ignora_abertura_sem_forma(monkeypatch, tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(6, 0, 0, 7, 1, 1)], classes={2: "IfcOpeningElement"})
    f, els = _els(ped)
    formas = S.formas_do_mundo(f, [e for e in els if not e.is_a("IfcOpeningElement")], threads=1)
    chamadas, abertos = [], []
    o_it, o_open = ifcopenshell.geom.iterator, ifcopenshell.open
    monkeypatch.setattr(ifcopenshell.geom, "iterator", lambda *a, **k: chamadas.append(1) or o_it(*a, **k))
    monkeypatch.setattr(ifcopenshell, "open", lambda *a, **k: abertos.append(1) or o_open(*a, **k))
    C.dividir_elementos(ped["arquivo"], ped["elementos"], threads=1, formas=formas)
    assert not chamadas and not abertos, "IfcOpeningElement nunca tem forma: não pode reabrir o arquivo nem rodar o iterador"
