# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19n2: o app lê a prévia do pai enquanto o auxiliar roda (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19n2-previa-no-app.md. Não editar nesta tarefa.
CONTRATO:
1. `auxiliar.executar(preparado, *, limite_s, cancelar, executor, previa=None)`: com `previa` callable, `executor is None` e `preparado.pedido["componentes"]` verdadeiro, grava em `preparado.pedido["previa_arquivo"]` o caminho `preparado.pasta / "previa.svg"` ANTES de iniciar o filho; enquanto espera a resposta, quando o arquivo aparece, chama `previa(svg_texto)` UMA vez (thread de quem chamou). Exceção do callback é engolida. Sem `previa`, ou sem `componentes`, ou com `executor`: a chave não existe e o callback nunca é chamado.
2. `planta.gerar_planta(..., previa=None)` repassa `previa=` a `auxiliar.executar`.
3. `gerente._motor_padrao` (planta): chama `gerar_planta(..., componentes=True, previa=cb)` (opção `componentes` do chamador prevalece); `cb(svg)` chama o `previa` do motor com `{"svg": svg, "n_paths": nº de "<path", "tempos": {}, "caixas": [], "em_cache": [], "pesados": [], "parcial": True}`. Corte: não passa `componentes` nem `previa`."""
import inspect
import threading
import time
from types import SimpleNamespace

import pytest

from openbim_app.desenho import auxiliar
from test_s06_t19h_componentes_oraculo import _caixa, _cena


def _preparar(tmp_path, componentes):
    ped, _ = _cena(tmp_path, [_caixa(3 * k, 0, 0, 3 * k + 1, 1, 1) for k in range(18)], corte=0.5)  # 18 grupos em 6 lotes: o auxiliar demora o bastante para a prévia vir antes do fim
    if componentes:
        ped["componentes"] = True
    ped.update({"protocolo": 1, "op": "desenho", "threads": 3})
    ped["vista"].setdefault("origem_pav", [0.0, 0.0, 0.0])
    return auxiliar.preparar(None, ped, caminho_ifc=ped["arquivo"])


def test_previa_chega_antes_da_resposta_e_uma_vez(tmp_path):
    recebidas = []
    with _preparar(tmp_path, True) as p:
        t0 = time.monotonic()
        r = auxiliar.executar(p, previa=lambda s: recebidas.append((time.monotonic() - t0, s)))
        total = time.monotonic() - t0
        assert p.pedido["previa_arquivo"] == str(p.pasta / "previa.svg")
    assert r["ok"] if "ok" in r else r["svg"]
    assert len(recebidas) == 1
    quando, svg = recebidas[0]
    assert isinstance(svg, str) and "<svg" in svg and 'data-obim-previa="1"' in svg
    assert total - quando >= 0.2, "a prévia veio colada no fim: não chegou enquanto o auxiliar rodava"


def test_sem_componentes_ou_sem_callback_nao_ha_arquivo_nem_chamada(tmp_path):
    chamadas = []
    with _preparar(tmp_path, False) as p:
        auxiliar.executar(p, previa=chamadas.append)
        assert "previa_arquivo" not in p.pedido
    assert chamadas == []
    with _preparar(tmp_path, True) as p:
        auxiliar.executar(p)
        assert "previa_arquivo" not in p.pedido


def test_callback_que_levanta_nao_derruba(tmp_path):
    def ruim(_s):
        raise RuntimeError("falha do callback")

    with _preparar(tmp_path, True) as p:
        r = auxiliar.executar(p, previa=ruim)
    assert r["svg"]


def test_gerar_planta_repassa_previa(monkeypatch):
    from s06_t17_aux import ExecutorEspiao, modelo, Pl

    f, _g, gid = modelo()
    vistos = []
    orig = auxiliar.executar

    def espia(p, **kw):
        vistos.append(kw)
        kw = {k: v for k, v in kw.items() if k != "previa"}
        return orig(p, **kw)

    monkeypatch.setattr(auxiliar, "executar", espia)
    cb = lambda s: None  # noqa: E731
    Pl.gerar_planta(f, gid, executor=ExecutorEspiao(), previa=cb)
    assert vistos and vistos[0].get("previa") is cb
    assert inspect.signature(Pl.gerar_planta).parameters["previa"].default is None


def _falso(monkeypatch):
    from openbim_app.desenho import planta as pmod

    est = SimpleNamespace(gerar=[])

    def gerar_planta(ifc, guid, **kw):
        est.gerar.append(kw)
        return SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=(), pesados=(), pedido={})

    monkeypatch.setattr(pmod, "gerar_planta", gerar_planta)
    return est


def test_motor_padrao_liga_componentes_e_traduz_a_previa(monkeypatch):
    from openbim_app.desenho import gerente as gmod

    est = _falso(monkeypatch)
    previas = []
    gmod._motor_padrao("planta", "IFC", "V", {}, cancelar=threading.Event(), progresso=lambda m: None, cache=None, previa=previas.append)
    kw = est.gerar[0]
    assert kw["componentes"] is True and callable(kw["previa"])
    kw["previa"]('<svg><path d="M0,0"/><path d="M1,1"/></svg>')
    assert previas == [{"svg": '<svg><path d="M0,0"/><path d="M1,1"/></svg>', "n_paths": 2, "tempos": {}, "caixas": [], "em_cache": [], "pesados": [], "parcial": True}]


def test_motor_padrao_opcao_do_chamador_prevalece_e_corte_nao_recebe(monkeypatch):
    from openbim_app.desenho import corte as cmod
    from openbim_app.desenho import gerente as gmod

    est = _falso(monkeypatch)
    gmod._motor_padrao("planta", "IFC", "V", {"componentes": False}, cancelar=threading.Event(), progresso=lambda m: None, cache=None)
    assert est.gerar[0]["componentes"] is False
    vistos = {}

    def gerar_corte(ifc, guid, **kw):
        vistos.update(kw)
        return SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=())

    monkeypatch.setattr(cmod, "gerar_corte", gerar_corte)
    gmod._motor_padrao("corte", "IFC", "V", {}, cancelar=threading.Event(), progresso=lambda m: None, cache=None)
    assert "componentes" not in vistos and "previa" not in vistos
