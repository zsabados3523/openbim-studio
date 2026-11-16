# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g4c2: correcoes da revisao do g4c. Nao editar nesta tarefa.

1. Retry de `Divergente` (corte e planta, 2a tentativa sem `caminho_ifc`): `filho=None` em todo `auxiliar.executar` do retry.
2. Corrida: o gerente tem geracao de arquivo (sobe em `invalidar()` e `salvar()`). Pedido que pediu na geracao N e roda na N+1 chama o motor
   sem `caminho_ifc` em `opcoes` e com `filho` ausente/None.
3. Vazamento: criar filho de um caminho novo fecha e esquece filhos de OUTROS caminhos sem pedido em `_ativos`; com pedido ativo, fica."""
from __future__ import annotations

import threading

import pytest
from test_s06_t19g4c_gerente_filho_oraculo import (  # noqa: F401  (fixtures e apoio do oraculo g4c)
    FilhoFalso, Motor, app, cena, espia, _esperar_n, _gerente, corte, local, planta,
)

from openbim_app.desenho import auxiliar as A
from openbim_app.desenho.gerente import GerenteDesenho

ABERTO = dict(revisao=1, revisao_salva=1)


# ------------------------------------------------------------------ 1. retry sem filho persistente
@pytest.mark.parametrize("tipo", ["corte", "planta"])
def test_retry_divergente_usa_processo_descartavel(tipo, cena, monkeypatch):
    f, gp, gc, salvo = cena
    orig, vistos = A.executar, []

    def falso(p, **kw):
        com_arquivo = "assinatura" in p.pedido  # 1a tentativa (caminho_ifc); a 2a usa IFC reduzido
        vistos.append((com_arquivo, kw.get("filho")))
        if com_arquivo and p.pedido.get("op") == "desenho":
            raise A.Divergente("arquivo mudou")
        return orig(p, **{**kw, "executor": kw.get("executor") or local.executar})

    monkeypatch.setattr(A, "executar", falso)
    ff = FilhoFalso()
    if tipo == "corte":
        corte.gerar_corte(f, gc, caminho_ifc=salvo, filho=ff)
    else:
        planta.gerar_planta(f, gp, caminho_ifc=salvo, filho=ff)
    assert any(c and fi is ff for c, fi in vistos), "controle: a 1a tentativa usa o filho"
    assert any(not c for c, _ in vistos), "o retry (IFC reduzido) deveria ter rodado"
    assert all(fi is None for c, fi in vistos if not c), f"retry nao pode usar o filho persistente: {vistos}"


# ------------------------------------------------------------------ 2. corrida pedir x invalidar/salvar
def _arq(tmp_path, nome="a.ifc"):
    p = tmp_path / nome
    p.write_text("ISO-10303-21;")
    return p


@pytest.mark.parametrize("acao", [None, "invalidar", "salvar"])
def test_pedido_de_geracao_velha_nao_usa_filho_nem_arquivo(acao, app, espia, tmp_path):
    m = Motor()
    solta = threading.Event()
    g = _gerente(GerenteDesenho, m, filho_persistente=True)
    original = g._rodar  # segura o pedido em voo ANTES de ele olhar a geracao
    g._rodar = lambda *a, **k: (solta.wait(10), original(*a, **k))[1]
    g.pedir("corte", object(), "V1", caminho_ifc=_arq(tmp_path), **ABERTO)
    if acao:
        getattr(g, acao)()  # o arquivo em disco pode ter mudado: o pedido em voo e velho
    solta.set()
    _esperar_n(m, 1)
    op, kw = m.chamadas[0]
    if acao:
        assert "caminho_ifc" not in op and kw.get("filho") is None
    else:
        assert "caminho_ifc" in op and kw.get("filho") is espia.instancias[0]
    g.fechar()


# ------------------------------------------------------------------ 3. vazamento de filhos de outros caminhos
def test_filho_de_outro_caminho_ocioso_e_fechado(app, espia, tmp_path):
    a, b = _arq(tmp_path, "a.ifc"), _arq(tmp_path, "b.ifc")
    m = Motor()
    g = _gerente(GerenteDesenho, m, filho_persistente=True)
    ch = g.pedir("corte", object(), "V1", caminho_ifc=a, **ABERTO)
    _esperar_n(m, 1)
    g.cancelar(ch)  # sem pedido ativo para A
    fa = espia.instancias[0]
    g.pedir("corte", object(), "V2", caminho_ifc=b, **ABERTO)
    _esperar_n(m, 2)
    assert espia.n("fechar", fa) >= 1, "filho de A (ocioso) deveria fechar ao abrir B"
    assert fa not in g._filhos_doc.values() and len(g._filhos_doc) == 1
    g.fechar()


def test_filho_de_outro_caminho_com_pedido_ativo_continua(app, espia, tmp_path):
    a, b = _arq(tmp_path, "a.ifc"), _arq(tmp_path, "b.ifc")
    m = Motor()
    solta = threading.Event()
    g = _gerente(GerenteDesenho, m, filho_persistente=True)
    original = g._rodar  # segura o pedido em voo ANTES de ele olhar a geracao
    g._rodar = lambda *a, **k: (solta.wait(10), original(*a, **k))[1]
    g.pedir("corte", object(), "V1", caminho_ifc=a, **ABERTO)  # A fica em voo (motor preso)
    fa = espia.instancias[0]
    g.pedir("corte", object(), "V2", caminho_ifc=b, **ABERTO)
    assert espia.n("fechar", fa) == 0 and fa in g._filhos_doc.values(), "A tem pedido ativo: nao pode fechar"
    solta.set()
    _esperar_n(m, 2)
    g.fechar()
