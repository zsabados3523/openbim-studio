# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19l: um filho processa vários grupos, abrindo o IFC uma vez (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19l-lote.md. Não editar nesta tarefa.
Medido (casarão, 212 MB): cada filho gasta 6,5 s só abrindo o arquivo; 37 grupos = 4 min de CPU. Agora o pai reparte os grupos em ate `threads` LOTES e cada filho processa o seu lote.
CONTRATO:
1. `desenho.processar_lote(pedido, fase=None)`, `pedido = {"op": "desenho_lote", "pedidos": [q1, q2, ...]}` (cada q = pedido de desenho de PLANTA completo): devolve `{"ok": True, "resultados": [r1, r2, ...]}`, r_i = o que
   `processar(q_i)` devolveria, na ordem. O arquivo é aberto UMA vez por par (`arquivo`, `vista.pavimento`) distinto do lote (itens de pavimentos diferentes NUNCA compartilham o `f` isolado: o isolamento do 1º apagaria o pavimento do 2º). `desenho._ARQ_LOTE` volta a `None` ao fim do lote (também com item que levanta). Item que levanta -> `{"ok": False, "erro": {...}}` naquele item, os outros seguem.
   `pedidos` ausente ou vazio -> `{"ok": False, "erro": {...}}`.
2. `processo.entrada` aceita `op == "desenho_lote"`: envia `{"tipo": "resposta", "dados": <resultado do lote>}`.
3. `desenho._planta_por_componentes`: em vez de um `faixas.rodar_filho` por grupo, chama `faixas.rodar_filho(lote)` por LOTE, `lote = {**base, "op": "desenho_lote", "pedidos": [q...]}` (q como antes: sem `componentes`/`pesados`/`limiar_pesado`,
   `threads` = max(1, threads // nº de lotes)); nº de lotes = min(grupos, threads); repartição gulosa por peso decrescente (peso do grupo = nº de triângulos das formas, ou nº de elementos se faltar); `limite_s` do lote = 300 s x itens.
   Item ok False/ausente, ou lote que morre: só os elementos daquele(s) grupo(s) entram em `falhas_geometria` (regra 3 da T19h). Resposta idêntica à de antes (`grupos`, `grupos_ids` na ordem original etc.)."""
from __future__ import annotations

import copy

import ifcopenshell
import pytest

import obim_geometria.desenho as D
import obim_geometria.processo as P
from test_s06_t19h_componentes_oraculo import Espiao, _caixa, _cena, _prisma_ou


def _pedidos(ped, ids, grupos):
    out = []
    for g in grupos:
        q = copy.deepcopy(ped)
        q["elementos"] = [[ids[k], e[1]] for k in g for e in [ped["elementos"][k]]]
        out.append(q)
    return out


def test_lote_igual_ao_individual_e_abre_o_arquivo_uma_vez(monkeypatch, tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(6, 0, 0, 7, 1, 1)], corte=0.5)
    pedidos = _pedidos(ped, ids, [[0], [1], [2]])
    ref = [D.processar(copy.deepcopy(q)) for q in pedidos]
    abertos = []
    orig = ifcopenshell.open
    monkeypatch.setattr(ifcopenshell, "open", lambda *a, **k: abertos.append(1) or orig(*a, **k))
    r = D.processar_lote({"op": "desenho_lote", "pedidos": copy.deepcopy(pedidos)})
    assert r["ok"] and len(r["resultados"]) == 3
    for a, b in zip(ref, r["resultados"]):
        assert b["ok"] and b["svg"] == a["svg"] and b["enviados"] == a["enviados"] and b["falhas_geometria"] == a["falhas_geometria"]
    assert len(abertos) == 1, f"arquivo aberto {len(abertos)} vezes"


def test_item_que_levanta_nao_derruba_os_outros(tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1)], corte=0.5)
    ruim = copy.deepcopy(ped)
    ruim["vista"] = {"tipo": "PLANTA", "escala": 1.0, "altura_corte_m": 0.5, "pavimento": "GUID-QUE-NAO-EXISTE"}
    ok1, ok2 = _pedidos(ped, ids, [[0], [1]])
    r = D.processar_lote({"op": "desenho_lote", "pedidos": [ok1, ruim, ok2]})
    assert r["ok"] and [x["ok"] for x in r["resultados"]] == [True, False, True] and r["resultados"][1]["erro"]["tipo"]


@pytest.mark.parametrize("pedidos", [None, []], ids=["ausente", "vazio"])
def test_lote_sem_pedidos(pedidos):
    ped = {"op": "desenho_lote"}
    if pedidos is not None:
        ped["pedidos"] = pedidos
    r = D.processar_lote(ped)
    assert r["ok"] is False and r["erro"]["tipo"]


def test_entrada_aceita_desenho_lote(tmp_path):
    import json
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1)], corte=0.5)
    class Tx:
        def __init__(self):
            self.msgs = []
        def send_bytes(self, b):
            self.msgs.append(json.loads(b.decode("utf-8")))
        def close(self):
            pass
    tx = Tx()
    P.entrada(tx, json.dumps({"protocolo": 1, "op": "desenho_lote", "pedidos": [ped]}))
    resp = [m for m in tx.msgs if m.get("tipo") == "resposta"]
    assert len(resp) == 1 and resp[0]["dados"]["ok"] and len(resp[0]["dados"]["resultados"]) == 1 and resp[0]["dados"]["resultados"][0]["ok"]


def _cena_grupos(tmp_path):
    malhas = [_prisma_ou(450, 0.5, 1.0, 0, 0), _caixa(5, 0, 0, 6, 1, 1), _caixa(8, 0, 0, 9, 1, 1), _caixa(11, 0, 0, 12, 1, 1)]
    return _cena(tmp_path, malhas, corte=0.5)


@pytest.mark.parametrize("threads,n_lotes", [(1, 1), (2, 2), (8, 4)])
def test_pai_reparte_os_grupos_em_lotes(monkeypatch, tmp_path, threads, n_lotes):
    ped, ids = _cena_grupos(tmp_path)
    ped.update({"componentes": True, "threads": threads})
    esp = Espiao(monkeypatch)
    lotes, limites = [], []
    orig = esp.__call__
    def espia(p, *a, **k):
        lotes.append(copy.deepcopy(p))
        limites.append(k.get("limite_s", a[0] if a else None))
        return orig(p, *a, **k)
    monkeypatch.setattr("obim_geometria.faixas.rodar_filho", espia)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["grupos"] == 4 and len(lotes) == n_lotes and all(l["op"] == "desenho_lote" for l in lotes)
    vistos = sorted(i for l in lotes for q in l["pedidos"] for i, _ in q["elementos"])
    assert vistos == sorted(ids) and all("componentes" not in q and "pesados" not in q for l in lotes for q in l["pedidos"])
    assert all(q["threads"] == max(1, threads // n_lotes) for l in lotes for q in l["pedidos"])
    assert sorted(limites) == sorted(300.0 * len(l["pedidos"]) for l in lotes)
    if threads == 2:  # guloso por peso: o prisma de 450 lados (muito mais triângulos) fica sozinho; as 3 caixas juntas
        tam = sorted(len(l["pedidos"]) for l in lotes)
        assert tam == [1, 3]
        sozinho = next(l for l in lotes if len(l["pedidos"]) == 1)
        assert [i for i, _ in sozinho["pedidos"][0]["elementos"]] == [ids[0]]


def test_falha_de_um_item_so_marca_os_elementos_do_grupo(monkeypatch, tmp_path):
    ped, ids = _cena_grupos(tmp_path)
    ped.update({"componentes": True, "threads": 2})
    Espiao(monkeypatch, falha=lambda p: "raise" if ids[2] in {i for i, _ in p["elementos"]} else None)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["falhas_geometria"] == [ids[2]] and r["grupos"] == 4


def test_lote_que_morre_marca_todos_os_seus_grupos(monkeypatch, tmp_path):
    ped, ids = _cena_grupos(tmp_path)
    ped.update({"componentes": True, "threads": 2})
    import obim_geometria.faixas as F
    orig = None
    def morre_se_tem(p, *a, **k):
        if any(ids[1] in {i for i, _ in q["elementos"]} for q in p["pedidos"]):
            raise RuntimeError("lote morreu (simulado)")
        return {"ok": True, "resultados": [D.processar(copy.deepcopy(q)) for q in p["pedidos"]]}
    monkeypatch.setattr(F, "rodar_filho", morre_se_tem)
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and set(r["falhas_geometria"]) == {ids[1], ids[2], ids[3]}, "o lote das 3 caixas morreu junto; o prisma (outro lote) fica"


def test_arq_lote_volta_a_none(tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1)], corte=0.5)
    assert D._ARQ_LOTE is None
    D.processar_lote({"op": "desenho_lote", "pedidos": [copy.deepcopy(ped)]})
    assert D._ARQ_LOTE is None
    ruim = copy.deepcopy(ped)
    ruim["vista"] = {**ruim["vista"], "pavimento": "GUID-QUE-NAO-EXISTE"}
    D.processar_lote({"op": "desenho_lote", "pedidos": [ruim]})
    assert D._ARQ_LOTE is None


def test_itens_de_pavimentos_diferentes_nao_compartilham_o_f_isolado(monkeypatch, tmp_path):
    import pathlib
    import s06_t07_aux as X
    f, pavs = X.estrutura("IFC4", n_pav=2)
    els = []
    for i, p in enumerate(pavs):
        e = X.caixa(f, "IfcBuildingElementProxy", f"P{i}", 2.0 * i, 0, 0, 1, 1, 1)
        X.conter(f, p, e)
        els.append(e)
    arq = str(pathlib.Path(tmp_path) / "dois.ifc")
    f.write(arq)
    pedidos = [{"arquivo": arq, "elementos": [[e.id(), e.GlobalId]], "threads": 1,
                "vista": {"tipo": "PLANTA", "escala": 1.0, "altura_corte_m": 50.0, "pavimento": p.GlobalId}} for e, p in zip(els, pavs)]
    abertos = []
    orig = ifcopenshell.open
    monkeypatch.setattr(ifcopenshell, "open", lambda *a, **k: abertos.append(1) or orig(*a, **k))
    r = D.processar_lote({"op": "desenho_lote", "pedidos": pedidos})
    assert r["ok"] and [x["ok"] for x in r["resultados"]] == [True, True] and len(abertos) == 2


def test_lote_real_no_pai_abre_o_arquivo_por_lote_e_nao_por_grupo(monkeypatch, tmp_path):
    import obim_geometria.faixas as F
    ped, ids = _cena_grupos(tmp_path)
    ped.update({"componentes": True, "threads": 2})
    monkeypatch.setattr(F, "rodar_filho", lambda p, *a, **k: D.processar_lote(p))
    abertos = []
    orig = ifcopenshell.open
    monkeypatch.setattr(ifcopenshell, "open", lambda *a, **k: abertos.append(1) or orig(*a, **k))
    r = D.processar(copy.deepcopy(ped))
    assert r["ok"] and r["grupos"] == 4 and not r["falhas_geometria"]
    assert len(abertos) <= 1 + 2, f"{len(abertos)} aberturas: 1 do pai + 2 lotes, não 1 por grupo (4)"
