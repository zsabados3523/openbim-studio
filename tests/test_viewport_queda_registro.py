# SPDX-License-Identifier: AGPL-3.0-or-later
"""Queda do processo de geometria deixa o motivo no registro ."""
import logging
import signal
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes"))

import _queda_alvos  # noqa: E402
from test_viewport_processo import _tempo_carga, mapeadas1  # noqa: E402,F401
from viewport_qrhi import processo_malhas as pm  # noqa: E402
from viewport_qrhi.carregador import CarregadorMalhas  # noqa: E402


def test_queda_do_filho_grava_o_codigo_de_saida(mapeadas1, monkeypatch, caplog):
    caminho, [(id_l, guid)] = mapeadas1
    monkeypatch.setenv("OBIM_TESTE_MATAR_FILHO", guid)
    with caplog.at_level(logging.WARNING, logger="openbim.viewport"):
        _, r, _ = _tempo_carga(caminho)
    assert r.estado == "concluido" and [s[0] for s in r.simplificadas] == [id_l]
    assert "código de saída 3" in caplog.text  # os._exit(3) do gancho de teste
    assert "código de saída 3" in r.simplificadas[0][4]  # e na explicação mostrada ao usuário


def _executar_alvo(alvo):
    c = CarregadorMalhas("nao-existe.ifc")
    return c._executar({"pico_filho": 0}, alvo, {}, lambda tipo, dados: False, lambda: None)


def test_saida_sem_fim_grava_codigo_zero(caplog):
    with caplog.at_level(logging.WARNING, logger="openbim.viewport"):
        r = _executar_alvo(_queda_alvos.sair_zero)
    assert r["motivo"] == "queda" and r["codigo"] == 0
    assert "código de saída 0" in caplog.text


def test_morte_por_sinal_grava_o_codigo_do_sistema(caplog):
    esperado = -signal.SIGTERM if sys.platform != "win32" else signal.SIGTERM  # Linux: -15; Windows: TerminateProcess(15)
    with caplog.at_level(logging.WARNING, logger="openbim.viewport"):
        r = _executar_alvo(_queda_alvos.morrer_por_sinal)
    assert r["motivo"] == "queda" and r["codigo"] == esperado
    assert f"código de saída {esperado}" in caplog.text


def test_tratar_nota_vai_para_o_registro(caplog):
    c = CarregadorMalhas("nao-existe.ifc")
    with caplog.at_level(logging.WARNING, logger="openbim.viewport"):
        assert c._tratar("nota", "x", {}) is False
    assert "Processo de geometria: x" in caplog.text


class _Produto:
    def __init__(self, i):
        self._i = i
        self.GlobalId = f"g{i}"

    def id(self):
        return self._i

    def is_a(self):
        return "IfcWall"


class _Iterador:
    def initialize(self):
        return True

    def get(self):
        raise RuntimeError("estrutura quebrada")


class _SaiuDoFilho(Exception):
    pass


def test_filho_manda_a_nota_antes_de_cair_no_bloco_com_erro(monkeypatch):
    falso = type("IfcOpenShellFalso", (), {})()
    falso.geom = type("Geom", (), {"iterator": staticmethod(lambda *a, **k: _Iterador())})()
    enviadas = []

    def sair(codigo):
        raise _SaiuDoFilho(codigo)

    monkeypatch.setattr(pm.os, "_exit", sair)
    with pytest.raises(_SaiuDoFilho) as e:
        pm._bloco(falso, None, "x.ifc", [_Produto(1), _Produto(2)], {"threads": 1, "biblioteca": "x"},
                  lambda tipo, dados=None: enviadas.append((tipo, dados)), {}, None, entregar=lambda *a: None)
    assert e.value.args == (3,)
    tipo, texto = enviadas[-1]  # a última mensagem antes da saída é a nota com o motivo
    assert tipo == "nota" and "estrutura quebrada" in texto and "2 peças" in texto


def test_falha_da_caixa_substituta_fica_no_registro_e_a_peca_vai_para_sem_malha(mapeadas1, monkeypatch, caplog):
    caminho, [(id_l, guid)] = mapeadas1
    original = CarregadorMalhas._executar

    def executar(self, est, alvo, params, ao_receber, limite):
        if alvo is pm.entrada_caixa:
            raise RuntimeError("falha simulada da caixa")
        return original(self, est, alvo, params, ao_receber, limite)

    monkeypatch.setattr(CarregadorMalhas, "_executar", executar)
    monkeypatch.setenv("OBIM_TESTE_MATAR_FILHO", guid)
    with caplog.at_level(logging.WARNING, logger="openbim.viewport"):
        _, r, _ = _tempo_carga(caminho)
    assert "O processo da caixa substituta falhou" in caplog.text
    sem = {s[0]: s[3] for s in r.sem_malha}
    assert id_l in sem and "não foi possível calcular a caixa" in sem[id_l]
