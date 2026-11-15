# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19k: a planta de um pavimento não carrega os outros pavimentos no serializador de SVG (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19k-isolar-pavimento.md. Não editar nesta tarefa.
CONTRATO: `desenho.processar` de PLANTA, no filho, tira da cópia em memória do IFC os `IfcBuildingStorey` que não são o do pedido ANTES de serializar (o serializador repete a projeção por pavimento: custo ~ nº de
pavimentos; medido casarão, 10 pavimentos: grupo de 8 peças 619 s -> 82 s, mesmo nº de caminhos). Então: (1) o SVG bruto que chega a `_somente_pavimento` tem no máximo 1 grupo `IfcBuildingStorey`;
(2) o resultado (ok, elementos enviados, caminhos) é o mesmo de um arquivo de 1 pavimento só; (3) o arquivo em disco não muda."""
from __future__ import annotations

import copy
import hashlib
import pathlib

import pytest
import s06_t07_aux as X

import obim_geometria.desenho as D


def _cena(tmp, n_pav):
    f, pavs = X.estrutura("IFC4", n_pav=n_pav)
    els = []
    for i, p in enumerate(pavs):
        e = X.caixa(f, "IfcBuildingElementProxy", f"P{i}", 2.0 * i, 0, 0, 1, 1, 1)
        X.conter(f, p, e)
        els.append(e)
    arq = str(pathlib.Path(tmp) / f"m{n_pav}.ifc")
    f.write(arq)
    ped = {"arquivo": arq, "elementos": [[els[0].id(), els[0].GlobalId]], "threads": 1,
           "vista": {"tipo": "PLANTA", "escala": 1.0, "altura_corte_m": 0.5, "pavimento": pavs[0].GlobalId}}
    return ped, arq


def _bruto(monkeypatch):
    visto = []
    orig = D._somente_pavimento
    def espia(svg, guid):
        visto.append(svg)
        return orig(svg, guid)
    monkeypatch.setattr(D, "_somente_pavimento", espia)
    return visto


def test_serializador_so_ve_o_pavimento_pedido(monkeypatch, tmp_path):
    ped, _ = _cena(tmp_path, 3)
    visto = _bruto(monkeypatch)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["enviados"] == [ped["elementos"][0][0]]
    assert len(visto) == 1 and visto[0].count('class="IfcBuildingStorey"') <= 1, "outros pavimentos chegaram ao serializador"


def test_mesmo_resultado_de_um_arquivo_de_um_pavimento(tmp_path):
    p3, _ = _cena(tmp_path, 3)
    p1, _ = _cena(tmp_path, 1)
    r3, r1 = D.processar(copy.deepcopy(p3)), D.processar(copy.deepcopy(p1))
    assert r3["ok"] and r1["ok"] and r3["n_paths"] == r1["n_paths"] > 0 and r3["falhas_geometria"] == r1["falhas_geometria"] == []


def test_arquivo_em_disco_nao_muda(tmp_path):
    ped, arq = _cena(tmp_path, 3)
    antes = hashlib.sha256(pathlib.Path(arq).read_bytes()).hexdigest()
    assert D.processar(copy.deepcopy(ped))["ok"]
    assert hashlib.sha256(pathlib.Path(arq).read_bytes()).hexdigest() == antes
