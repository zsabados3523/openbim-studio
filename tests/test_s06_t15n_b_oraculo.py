# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15n (parte b): caixas por pontos do face set.
Ref: docs/state/cards/F0-S06/F0-S06-T15n-caixas-rapidas.md.
"""
from __future__ import annotations

import pytest
from s06_t15n_aux import *  # noqa: F401,F403


# ---------- 4. fallback: extrusão, parede, brep, item misto ----------
def test_extrusao_parede_brep_e_misto_caem_no_iterator(tmp_path, monkeypatch):
    f, pavs = base()
    ext = X.caixa(f, "IfcBuildingElementProxy", "Ext", 13.0, -6.0, 1.5, 1.0, 2.0, 0.5)
    par = X.caixa(f, "IfcWall", "Par", 14.0, -6.0, 1.5, 3.0, 0.2, 2.8)
    brep = peca(f, pavs[0], "Brep", "brep", (1.0, 1.0, 0.0))
    misto = peca(f, pavs[0], "Misto", "poly", (6.0, 1.0, 0.0))
    extra = X.caixa(f, "IfcBuildingElementProxy", "tmp", 0, 0, 0, 1, 1, 1).Representation.Representations[0].Items[0]
    misto.Representation.Representations[0].Items = list(misto.Representation.Representations[0].Items) + [extra]
    X.conter(f, pavs[0], ext, par)
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, "Ext", "Par", "Brep", "Misto")
    ids = [e[0] for e in p["elementos"]]
    ref = ref_iterator(arq, ids)
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, ids)
    assert esp.ids_iterator == set(ids), "tudo isto tem de passar pelo iterator (nenhum atalho)"
    assert res["passagens_iterator"] >= 1


# ---------- 5. mistura: ordem, ids, falhas ----------
def test_mistura_preserva_ordem_ids_e_falhas(tmp_path, monkeypatch):
    f, pavs = base()
    peca(f, pavs[0], "F1", "poly", (1.0, 1.0, 0.0))
    X.conter(f, pavs[0], X.caixa(f, "IfcWall", "W1", 13.0, -6.0, 1.5, 3.0, 0.2, 2.8))
    peca(f, pavs[1], "F2", "fbsm", (2.0, 3.0, 0.0), ref=(0.0, 1.0, 0.0))
    sem = X.elemento(f, "IfcBuildingElementProxy", "Sem")  # sem representação: sem geometria
    X.conter(f, pavs[0], sem)
    mapeada(f, pavs[1], "M1", mapa_de(f, "tri"), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    X.conter(f, pavs[0], X.caixa(f, "IfcBuildingElementProxy", "E1", 20.0, 0.0, 1.5, 1.0, 1.0, 1.0))
    arq, g = abrir(f, tmp_path)
    ordem = ["E1", "F2", "Sem", "W1", "M1", "F1"]
    p = ped(arq, g, *ordem)
    ids = [e[0] for e in p["elementos"]]
    id_sem = ids[2]
    ok_ids = [i for i in ids if i != id_sem]
    ref = ref_iterator(arq, ok_ids)
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, ok_ids)
    assert str(id_sem) not in res["caixas_envolventes"] and res["falhas_geometria"] == [id_sem]
    assert all(isinstance(k, str) for k in res["caixas_envolventes"]) and len(res["caixas_envolventes"]) == 5
    assert esp.ids_iterator == {ids[0], ids[2], ids[3]}, "só E1, Sem e W1 vão ao iterator"
    assert res["passagens_iterator"] == len(esp.incluidos) == 1
    assert res["erros_iterator"] == []
    # mesmo pedido em outra ordem: mesmas caixas
    p2 = dict(p, elementos=list(reversed(p["elementos"])))
    res2 = local.executar(p2)
    assert res2["caixas_envolventes"] == res["caixas_envolventes"] and res2["falhas_geometria"] == [id_sem]


# ---------- 6 e 8. caminho rápido evita o iterator; contagem, não relógio ----------
def test_muitos_face_sets_zero_iterator_zero_create_shape(tmp_path, monkeypatch):
    f, pavs = base()
    for i in range(60):
        peca(f, pavs[i % 2], f"N{i}", ("poly", "tri", "fbsm", "sbsm")[i % 4], (i * 0.7, -i * 0.3, 0.1 * i), ref=(math.cos(i), math.sin(i), 0.0))
    mapa = mapa_de(f, "poly")
    for i in range(20):
        mapeada(f, pavs[0], f"MM{i}", mapa, (i * 1.0, 0.0, 0.0), (0.0, 0.1 * i, 0.0))
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, *[f"N{i}" for i in range(60)], *[f"MM{i}" for i in range(20)])
    ids = [e[0] for e in p["elementos"]]
    ref = ref_iterator(arq, ids)
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, ids)
    assert len(res["caixas_envolventes"]) == 80
    assert esp.incluidos == [] and esp.create_shape == [] and res["passagens_iterator"] == 0


def test_mistura_grande_iterator_so_recebe_os_nao_face_set(tmp_path, monkeypatch):
    f, pavs = base()
    for i in range(30):
        peca(f, pavs[0], f"F{i}", "poly", (i * 1.0, 0.0, 0.0))
    for i in range(5):
        X.conter(f, pavs[0], X.caixa(f, "IfcBuildingElementProxy", f"X{i}", 40.0 + i, 0.0, 1.5, 0.5, 0.5, 0.5))
    arq, g = abrir(f, tmp_path)
    p = ped(arq, g, *[f"F{i}" for i in range(30)], *[f"X{i}" for i in range(5)])
    ids = [e[0] for e in p["elementos"]]
    ref = ref_iterator(arq, ids)
    esp = Espia(monkeypatch)
    res = local.executar(p)
    iguais(res, ref, ids)
    assert esp.ids_iterator == set(ids[30:]) and len(esp.incluidos) == 1 and res["passagens_iterator"] == 1
