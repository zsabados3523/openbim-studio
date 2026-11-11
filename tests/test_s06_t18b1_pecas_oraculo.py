# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T18b-1 (`obim_geometria.pecas`): pedido de uma peça, extração/mescla do grupo exato no SVG com silhuetas, `refinar_peca` com executor, `rodar_filho(limite_s)`."""
from __future__ import annotations

import copy
import re

import pytest
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)
from s06_t17_aux import partes
from s06_t18a_aux import modelo_denso, pedido_planta

import obim_geometria.faixas as F
import obim_geometria.local as L
import obim_geometria.pecas as P

A = '<g class="IfcWall" ifc:guid="GA"><path d="M 0,0 L 1,0 L 1,1 Z"/></g>'
B_SIL = '<g class="IfcFurniture" ifc:guid="GB" data-silhueta="1"><path d="M 0,0 L 2,0 L 2,2 Z" fill-rule="evenodd"/></g>'
B_EX = '<g class="IfcFurniture" ifc:guid="GB"><path d="M 0,0 L 2,0 L 2,2 L 0,2 Z"/><path d="M 1,1 L 2,1"/></g>'
C = '<g class="IfcSlab" ifc:guid="GC"><path d="M 5,5 L 6,5 Z"/></g>'


def svg(*gs):
    return '<svg xmlns:ifc="x"><g class="projection">' + "".join(gs) + "</g></svg>"


def test_mesclar_troca_so_a_silhueta_mantem_ordem():
    r = P.mesclar_pesado(svg(A, B_SIL, C), "GB", B_EX)
    assert r == svg(A, B_EX, C) and "data-silhueta" not in r


def test_mesclar_idempotente_e_sem_silhueta_devolve_igual():
    once = P.mesclar_pesado(svg(A, B_SIL, C), "GB", B_EX)
    assert P.mesclar_pesado(once, "GB", B_EX) == once
    assert P.mesclar_pesado(svg(A, C), "GB", B_EX) == svg(A, C)  # sem silhueta daquele guid
    assert P.mesclar_pesado(svg(A, B_EX, C), "GB", B_EX) == svg(A, B_EX, C)  # ja exato: nao duplica
    outro = P.mesclar_pesado(svg(A, B_SIL, C), "GA", A)  # silhueta so de outro guid: nada muda
    assert outro == svg(A, B_SIL, C)


def test_mesclar_nao_deixa_silhueta_e_exato_juntos():
    r = P.mesclar_pesado(svg(A, B_SIL, C), "GB", B_EX)
    assert r.count('ifc:guid="GB"') == 1


def test_extrair_grupo_ignora_silhueta_e_guid_inexistente():
    s = svg(A, B_SIL, B_EX, C)
    assert P.extrair_grupo(s, "GB") == B_EX
    assert P.extrair_grupo(s, "GA") == A
    assert P.extrair_grupo(svg(A, B_SIL), "GB") is None
    assert P.extrair_grupo(s, "ZZ") is None


def _pedido_fake():
    return {"op": "desenho", "arquivo": "x.ifc", "threads": 4, "faixas": 3, "pesados": "silhueta", "limiar_pesado": 50,
            "elementos": [[1, "GA"], [2, "GB"], [3, "GC"]], "caixas_coords": {1: [0, 0, 0, 1, 1, 1], "2": [0, 0, 0, 2, 2, 2], 3: [5, 5, 0, 6, 6, 1]}, "vista": {"k": 1}}


def test_pedido_peca_filtra_e_nao_muta():
    p = _pedido_fake()
    antes = copy.deepcopy(p)
    q = P.pedido_peca(p, 2)
    assert p == antes and q is not p
    assert [e[0] for e in q["elementos"]] == [2] and q["elementos"][0][1] == "GB"
    assert {int(k) for k in q["caixas_coords"]} == {2}
    assert "faixas" not in q and "pesados" not in q and "limiar_pesado" not in q and q["threads"] == 1
    assert q["op"] == "desenho" and q["arquivo"] == "x.ifc" and q["vista"] == {"k": 1}


def test_refinar_peca_executor_falso_ok_e_falhas_nao_levantam():
    s = svg(A, B_EX)
    chamados = []
    r = P.refinar_peca(_pedido_fake(), 2, executor=lambda q: chamados.append(q) or {"ok": True, "svg": s})
    assert r["ok"] is True and r["grupo"] == B_EX and "tempos" in r and [e[0] for e in chamados[0]["elementos"]] == [2]
    assert P.refinar_peca(_pedido_fake(), 2, executor=lambda q: {"ok": False, "erro": {"tipo": "X", "mensagem": "m", "rastro": ""}})["ok"] is False

    def explode(q):
        raise RuntimeError("boom")
    r = P.refinar_peca(_pedido_fake(), 2, executor=explode)
    assert r["ok"] is False and r["grupo"] is None and isinstance(r["erro"], str) and "boom" in r["erro"]
    r = P.refinar_peca(_pedido_fake(), 2, executor=lambda q: {"ok": True, "svg": svg(A)})  # peca sumiu do SVG
    assert r["ok"] is False or r["grupo"] is None


def test_rodar_filho_limite_s_usa_o_parametro(monkeypatch):
    class Rx:
        def poll(self, t=0):
            return False

    class Tx:
        def close(self):
            pass

    class Proc:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def is_alive(self):
            return True

        def terminate(self):
            pass

        def kill(self):
            pass

        def join(self, *a, **k):
            pass

    class Ctx:
        Process = Proc

        def Pipe(self, duplex=False):
            return Rx(), Tx()
    monkeypatch.setattr(F.multiprocessing, "get_context", lambda *_a, **_k: Ctx())
    monkeypatch.setenv("OBIM_FAIXAS_LIMITE_S", "300")
    r = F.rodar_filho({"op": "desenho"}, limite_s=0.2)
    assert r["ok"] is False and r["erro"]["tipo"] == "AuxiliarEstourouTempo"


def test_integracao_mescla_exato_igual_ao_hlr_do_pedido(tmp_path):
    f, g, v, mov, _p = modelo_denso(24)
    base_p = pedido_planta(f, v, tmp_path / "a")
    base = L.executar(base_p)
    sil_p = pedido_planta(f, v, tmp_path / "b")
    sil_p.update(pesados="silhueta", limiar_pesado=50)
    sil = L.executar(sil_p)
    assert base["ok"] and sil["ok"] and 'data-silhueta="1"' in sil["svg"]
    r = P.refinar_peca(sil_p, mov.id(), executor=L.executar)
    assert r["ok"] and r["grupo"] and "data-silhueta" not in r["grupo"], r
    final = P.mesclar_pesado(sil["svg"], mov.GlobalId, r["grupo"])
    assert "data-silhueta" not in final and final.count('ifc:guid="%s"' % mov.GlobalId) == 1
    d = lambda s: re.findall(r'\sd="([^"]*)"', P.extrair_grupo(s, mov.GlobalId))  # noqa: E731
    assert d(final) == d(base["svg"]) and d(final)
    (_e0, g0), (_e1, g1) = partes(base["svg"], aprox=True), partes(final, aprox=True)
    assert g1 == g0  # pegada da peca e demais grupos iguais, mesmos guids
    assert partes(final)[1] and [k for k, _ in partes(final)[1]] == [k for k, _ in partes(base["svg"])[1]]
    assert P.mesclar_pesado(final, mov.GlobalId, r["grupo"]) == final


def test_integracao_executor_com_falha_nao_levanta(tmp_path):
    f, g, v, mov, _p = modelo_denso(24)
    p = pedido_planta(f, v, tmp_path)
    p.update(pesados="silhueta", limiar_pesado=50)
    antes = copy.deepcopy(p)
    r = P.refinar_peca(p, mov.id(), executor=lambda q: {"ok": False, "erro": {"tipo": "Falha", "mensagem": "m", "rastro": ""}})
    assert r["ok"] is False and p == antes
