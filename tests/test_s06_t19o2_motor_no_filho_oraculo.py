# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19o2: o filho da planta desenha as peças elegíveis pelo motor de visibilidade (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19o2-motor-no-filho.md. Não editar nesta tarefa.
Medido (SUBSOLO real): 7 móveis abaixo do corte, 83 s no HLR, ~5 s no motor (`visibilidade.linhas_visiveis_multi`).
CONTRATO (`desenho.processar`, PLANTA, `pedido["motor_visivel"] = True`; ausente/False = comportamento de hoje, sem a chave `motor_pecas` ou com `[]`):
1. Peça ELEGÍVEL = não porta/janela, sem `HasOpenings`, com geometria, maior z do mundo <= `altura_corte_m` e sem vizinho INELEGÍVEL cuja caixa XY (com folga 1 mm) cruze a dela. Elegíveis saem do HLR e são desenhadas por `linhas_visiveis_multi` (oclusão entre as elegíveis do mesmo pedido); o grupo `<g class=... ifc:guid=...>` delas tem `<path>`s e NENHUM `data-silhueta`.
2. Resposta ganha `motor_pecas` (lista de ids desenhados pelo motor), `enviados` os inclui, `falhas_geometria` não. Peça inteira acima do corte: some, como no HLR, sem entrar em falhas.
3. Cobertura bilateral >= 0.999 (TOL da T19b1) contra o desenho sem a chave, em todos os casos.
4. Com `componentes: True` a chave vai aos filhos e `motor_pecas` do pai é a união das dos filhos."""
from __future__ import annotations

import copy

from s06_t07_aux import *  # noqa: F401,F403  (garante o caminho dos auxiliares)
import numpy as np
from test_s06_t19b1_visibilidade_oraculo import TOL, _amostra, _caixa, _cobertura, _dist
from test_s06_t19b2_visibilidade_hlr_oraculo import _coplanares
from test_s06_t19h_componentes_oraculo import Espiao, _cena, _guids, _segs

import obim_geometria.desenho as D

CORTE = 0.5


def _confere(ref, r, malhas):
    """Motor x HLR. O HLR desenha diagonais coplanares da triangulação (sem traço no contrato do motor, ver T19b2): o trecho do HLR que só cai sobre elas não conta."""
    a, b = _segs(ref["svg"]), _segs(r["svg"])
    assert len(a) and len(b)
    cop, resto = [], []
    for m in malhas:
        c, rs = _coplanares(m)
        cop.append(c)
        resto.append(rs)
    cop, resto = np.concatenate(cop), np.concatenate(resto)
    p, w = _amostra(a)
    ficar = ~((_dist(p, cop) <= TOL) & (_dist(p, resto) > TOL))
    cob = float(w[ficar & (_dist(p, b) <= TOL)].sum() / w[ficar].sum())
    assert cob >= 0.999, f"linha do HLR faltando no motor ({cob:.4f})"
    assert _cobertura(b, a) >= 0.999, "linha sobrando no motor"


def _par(tmp_path, malhas, **kw):
    ped, ids = _cena(tmp_path, malhas, corte=CORTE, **kw)
    ref = D.processar(copy.deepcopy(ped))
    r = D.processar({**copy.deepcopy(ped), "motor_visivel": True})
    assert ref["ok"] and r["ok"]
    return ped, ids, ref, r


def test_elegiveis_vao_ao_motor_e_batem_com_o_hlr(tmp_path):
    malhas = [_caixa(0, 0, 0, 1, 1, 0.3), _caixa(3, 0, 0, 4, 1, 0.3), _caixa(20, 0, 0, 22, 2, 0.2), _caixa(21, 1, 0, 23, 3, 0.4)]  # a última cobre o canto da 3ª
    ped, ids, ref, r = _par(tmp_path, malhas)
    assert sorted(r["motor_pecas"]) == sorted(ids) and not r["falhas_geometria"]
    assert set(ids) <= set(r["enviados"])
    assert "data-silhueta" not in r["svg"] and {g for _i, g in ped["elementos"]} <= set(_guids(r["svg"]))  # o HLR sem corte não grava guid nas projeções; o motor grava
    _confere(ref, r, malhas)


def test_vizinho_inelegivel_sobreposto_mantem_o_hlr(tmp_path):
    malhas = [_caixa(0, 0, 0, 2, 2, 0.3), _caixa(1, 1, 0, 3, 3, 1.0), _caixa(10, 0, 0, 11, 1, 0.3)]  # [1] cruza o corte e sobrepõe [0]
    ped, ids, ref, r = _par(tmp_path, malhas)
    assert r["motor_pecas"] == [ids[2]]
    _confere(ref, r, malhas)


def test_peca_acima_do_corte_some_sem_virar_falha(tmp_path):
    malhas = [_caixa(0, 0, 0, 1, 1, 0.3), _caixa(5, 0, 1.0, 6, 1, 2.0)]
    ped, ids, ref, r = _par(tmp_path, malhas)
    assert r["motor_pecas"] == [ids[0]] and not r["falhas_geometria"] and not ref["falhas_geometria"]
    assert ped["elementos"][1][1] not in r["svg"] and ped["elementos"][1][1] not in ref["svg"]
    _confere(ref, r, malhas)


def test_porta_fica_no_hlr(tmp_path):
    malhas = [_caixa(0, 0, 0, 1, 1, 0.3), _caixa(5, 0, 0, 6, 1, 0.3)]
    ped, ids, ref, r = _par(tmp_path, malhas, classes={0: "IfcDoor"})
    assert r["motor_pecas"] == [ids[1]]
    _confere(ref, r, malhas)


def test_sem_a_chave_nada_muda(tmp_path):
    ped, _ = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 0.3), _caixa(3, 0, 0, 4, 1, 0.3)], corte=CORTE)
    a = D.processar(copy.deepcopy(ped))
    b = D.processar({**copy.deepcopy(ped), "motor_visivel": False})
    assert a["svg"] == b["svg"] and not a.get("motor_pecas") and not b.get("motor_pecas")


def test_componentes_repassa_a_chave_aos_filhos(monkeypatch, tmp_path):
    malhas = [_caixa(0, 0, 0, 1, 1, 0.3), _caixa(3, 0, 0, 4, 1, 0.3), _caixa(6, 0, 0, 7, 1, 0.3)]
    ped, ids = _cena(tmp_path, malhas, corte=CORTE)
    ref = D.processar(copy.deepcopy(ped))
    esp = Espiao(monkeypatch)
    r = D.processar({**copy.deepcopy(ped), "componentes": True, "motor_visivel": True})
    assert r["ok"] and sorted(r["motor_pecas"]) == sorted(ids) and r["grupos"] == 3
    assert all(c.get("motor_visivel") for c in esp.chamadas)
    _confere(ref, r, malhas)
