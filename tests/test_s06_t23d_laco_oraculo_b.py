# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T23d, parte 2: laco do filho com construcao entre pedidos (banco ocupado, erros, estado, casos da revisao Opus).
Os auxiliares e as fixtures vem da parte 1 (test_s06_t23d_laco_oraculo.py). Nao editar nesta tarefa."""
from __future__ import annotations

import sqlite3
import sys
import time

import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda do ambiente)
from test_s06_t19g3_sem_rastro_oraculo import _est, cena  # noqa: F401  (cena e fixtures compartilhados)
from test_s06_t23d_laco_oraculo import Falso, Filho, _banco_ocupado, esperar, estado, novo, terminar  # noqa: F401

def test_banco_ocupado_tres_seguidas_para_e_o_laco_segue(cena, novo, tmp_path):  # mutante 6
    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.01, falhar=_banco_ocupado)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    time.sleep(4.0)
    e = estado(fi, str(salvo))
    assert e["parado"] == "banco_ocupado" and len(ctor.lotes) == 3 and all(x["ids"] == [0, 1, 2] for x in ctor.lotes), (e, len(ctor.lotes))
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True  # atende pedidos
    time.sleep(1.3)
    assert len(ctor.lotes) == 3, "tentou de novo depois de parar"


def test_outra_excecao_para_com_erro_e_o_laco_segue(cena, novo, tmp_path):  # mutante 6
    def boom(n, reg):
        raise RuntimeError("boom-xyz")

    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.01, falhar=boom)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: estado(fi, str(salvo))["parado"] == "erro")
    assert "boom-xyz" in estado(fi, str(salvo))["erro"]
    time.sleep(1.2)
    assert len(ctor.lotes) == 1 and fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True


def test_filho_nao_manda_mensagem_sem_pedido(cena, novo, tmp_path):  # mutante 8
    salvo, _ = cena
    ctor = Falso(range(20), dorme=0.05)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=2)
    fi.silencio(1.0)  # a construcao inteira (10 lotes, 0,5 s) roda sem o pai ler nada; nada e empurrado
    assert estado(fi, str(salvo))["pendentes"] == 0
    time.sleep(0.2)
    n = fi.rx.polls
    time.sleep(1.0)  # D: fila vazia = recv bloqueante, sem girar
    assert fi.rx.polls - n <= 3, f"laco gira com a fila vazia: {fi.rx.polls - n} polls em 1 s"


def test_regra_do_numero_vale_para_as_ops_novas(cena, novo, tmp_path):  # mutante 9
    salvo, pedidos = cena
    ctor = Falso(range(40), dorme=0.05)
    fi = novo(ctor)
    fi.pedir("construir", numero=5, arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    ped = {k: v for k, v in pedidos["A"].items() if k not in ("op", "protocolo")}
    for op, num, campos in (("construir", 5, {"arquivo": str(salvo), "pasta_cache": str(tmp_path / "x")}), ("estado_construcao", 3, {"arquivo": str(salvo)}),
                            ("desenho", 4, ped)):
        d = fi.pedir(op, numero=num, **campos)
        assert d["ok"] is False and d["erro"]["tipo"] == "PedidoVelho", (op, d)
    assert ctor.pastas == [str(tmp_path)] and not any(e[0] == "prior" for e in ctor.eventos), "pedido velho foi executado"
    assert estado(fi, str(salvo))["ativo"] is True  # numero 6 ainda e aceito: o velho nao mudou o ultimo


def test_estado_contagens(cena, novo, tmp_path):  # mutante 10
    salvo, _ = cena
    ctor = Falso(range(20), dorme=0.05, ret=(3, 1, 0))
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    vistos = []
    while True:
        e = estado(fi, str(salvo))
        vistos.append(e["lotes"])
        assert e["feitos"] == 4 * e["lotes"] and e["pendentes"] == 20 - e["feitos"], e
        assert e["tesseladas"] == 3 * e["lotes"] and e["reaproveitadas"] == e["lotes"] and e["falhas"] == 0, e
        assert e["rss_mb"] == 123.5 and e["parado"] is None and e["erro"] is None and e["lote_max_s"] >= (0.04 if e["lotes"] else 0)
        if e["pendentes"] == 0:
            break
        assert e["ativo"] is True
    assert e["lotes"] == 5 and e["feitos"] == 20 and len(set(vistos)) > 1


def test_estado_falhas_e_lote_max_padrao_64(cena, novo, tmp_path):  # mutante 10
    salvo, _ = cena
    ctor = Falso(range(130), dorme=0.01, ret=(2, 1, 1))
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path))
    terminar(fi, str(salvo))
    e = estado(fi, str(salvo))
    assert (e["lotes"], e["tesseladas"], e["reaproveitadas"], e["falhas"]) == (3, 6, 3, 3), e
    assert [len(x["ids"]) for x in ctor.lotes] == [64, 64, 2]


def test_pedido_corta_a_espera_do_banco_ocupado(cena, novo, tmp_path):  # B: poll(1.0), nao sleep(1.0)
    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.05, falhar=lambda n, reg: _banco_ocupado(n, reg) if n == 1 else None)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: ctor.lotes)
    time.sleep(0.15)  # dentro da espera de 1 s
    fi.pedir("abrir", arquivo=str(salvo))
    assert fi.ultimo_t <= 0.4, f"pedido esperou o banco ocupado: {fi.ultimo_t:.2f}s"


@pytest.mark.parametrize("msg", ["cache fechado", "disk I/O error"])
def test_operational_error_que_nao_e_banco_ocupado_vira_erro(cena, novo, tmp_path, msg):  # E
    def falha(n, reg):
        raise sqlite3.OperationalError(msg)

    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.01, falhar=falha)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    time.sleep(0.5)  # sem espera de 1 s nem repeticao
    e = estado(fi, str(salvo))
    assert e["parado"] == "erro" and msg in e["erro"] and len(ctor.lotes) == 1, (e, len(ctor.lotes))


def test_priorizar_com_excecao_nao_derruba_o_laco(cena, novo, tmp_path):  # F1
    salvo, pedidos = cena
    ctor = Falso(range(40), dorme=0.05, prior_erro=True)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=2)
    assert fi.pedir("desenho", **{k: v for k, v in pedidos["A"].items() if k not in ("op", "protocolo")}).get("ok")
    assert any(e[0] == "prior" for e in ctor.eventos)
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True
    terminar(fi, str(salvo))
    assert sorted(ctor.gravados()) == list(range(40)), "fila perdida depois da excecao em priorizar"


def test_construtor_que_nao_importa_responde_erro_e_o_laco_segue(cena, novo, tmp_path, monkeypatch):  # F2: {"aceito": False, "motivo": "erro"}
    salvo, _ = cena
    monkeypatch.setitem(sys.modules, "obim_geometria.construtor", None)  # import_module levanta ImportError
    fi = novo(None)
    d = fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path))
    assert d.get("aceito") is False and d.get("motivo") == "erro", d
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True


def test_rss_com_excecao_vira_parado_erro(cena, novo, tmp_path):  # F3
    def rss(c):
        if c.gravados():
            raise OSError("rss indisponivel")
        return 10.0

    salvo = cena[0]
    fi = novo(Falso(range(12), dorme=0.01, rss=rss))
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: estado(fi, str(salvo)).get("parado") == "erro")
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True


@pytest.mark.parametrize("lote_max", [0, -3])
def test_lote_max_invalido_nao_gira_em_vazio(cena, novo, tmp_path, lote_max):  # H: lote >= 1, fila avanca
    salvo, _ = cena
    ctor = Falso(range(6), dorme=0.01)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=lote_max)
    terminar(fi, str(salvo), 5)
    assert sorted(ctor.gravados()) == list(range(6)) and all(len(x["ids"]) >= 1 for x in ctor.lotes)


# MUTANTES: 1 e 3 test_desenho_passa_a_frente_do_lote; 2 test_construir_responde_antes...; 4 test_memoria_*; 5 test_arquivo_reaberto_zera_*;
# A-H (revisao Opus): A test_banco_ocupado_uma_vez, B test_pedido_corta_a_espera, C test_construir_responde_antes, D test_filho_nao_manda, E test_operational_error_*,
# test_priorizar_com_excecao, test_construtor_que_nao_importa, test_rss_com_excecao, test_memoria_limite_padrao (G), test_lote_max_invalido
# 6 test_banco_ocupado_*, test_outra_excecao_*; 7 test_construir_repetido_*; 8 test_filho_nao_manda_*;
# 9 test_regra_do_numero_*; 10 test_estado_contagens, test_estado_falhas_*  (`Filho.ler` tambem rejeita mensagem sem pedido)
