# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15n (parte a): caixas por pontos do face set.
Ref: docs/state/cards/F0-S06/F0-S06-T15n-caixas-rapidas.md.
"""
from __future__ import annotations

import pytest
from s06_t15n_aux import *  # noqa: F401,F403


# ---------- 1. face set simples, placement girado e aninhado ----------
@pytest.mark.parametrize("esq,tipo", [("IFC4", "poly"), ("IFC4", "tri"), ("IFC4", "fbsm"), ("IFC4", "sbsm"), ("IFC2X3", "fbsm")])
@pytest.mark.parametrize("giro", ["z30", "inclinado"])
def test_face_set_caixa_igual_ao_iterator_e_sem_iterator(tmp_path, monkeypatch, esq, tipo, giro):
    f, pavs = base(esq)
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    if giro == "z30":
        peca(f, pavs[1], "P", tipo, (4.0, 2.5, 0.25), ref=(c, s, 0.0))
    else:
        _girado(f, pavs[1], "P", tipo)
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, "P")
    ref = ref_iterator(arq, [p["elementos"][0][0]])
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, [p["elementos"][0][0]])
    assert res["falhas_geometria"] == [] and res["erros_iterator"] == []
    assert esp.incluidos == [] and esp.create_shape == [], "face set puro não pode usar o iterator"
    assert res["passagens_iterator"] == 0


# ---------- 2. unidade em milímetros ----------
@pytest.mark.parametrize("tipo", ["poly", "tri", "fbsm", "sbsm"])
def test_unidade_milimetro_caixa_em_metros(tmp_path, monkeypatch, tipo):
    f, pavs = base()
    peca(f, pavs[0], "P", tipo, (4000.0, 2500.0, 250.0), dims=(2000.0, 1000.0, 500.0), ref=(0.8, 0.6, 0.0))
    mapa = mapa_de(f, tipo, dims=(2000.0, 1000.0, 500.0))
    mapeada(f, pavs[1], "M", mapa, (100.0, 200.0, 0.0), (50.0, 60.0, 70.0), escala=2.0)
    X.em_milimetros(f)
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, "P", "M")
    ids = [e[0] for e in p["elementos"]]
    ref = ref_iterator(arq, ids)
    assert 1.0 < ref[ids[0]][3] < 40.0, "referência deve estar em metros (sanidade da unidade)"
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, ids)
    assert esp.incluidos == [] and esp.create_shape == []


# ---------- 3. IfcMappedItem ----------
@pytest.mark.parametrize("tipo", ["poly", "tri", "fbsm", "sbsm"])
def test_mapeada_duas_instancias_placements_diferentes(tmp_path, monkeypatch, tipo):
    f, pavs = base()
    mapa = mapa_de(f, tipo)
    mapeada(f, pavs[0], "A", mapa, (1.0, 2.0, 0.0), (0.5, 0.0, 0.0))
    mapeada(f, pavs[1], "B", mapa, (-3.0, 5.0, 0.4), (0.0, 1.5, 0.25), escala=1.5, ref=(0.6, 0.8, 0.0))
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, "A", "B")
    ids = [e[0] for e in p["elementos"]]
    ref = ref_iterator(arq, ids)
    assert ref[ids[0]] != pytest.approx(ref[ids[1]], abs=0.1), "instâncias devem ficar em lugares diferentes"
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, ids)
    assert esp.incluidos == [] and esp.create_shape == [], "mapeada de face set também é caminho rápido"
