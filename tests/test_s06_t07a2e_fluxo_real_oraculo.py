# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07a2E (rodada 2 do Argon): FLUXO REAL `caixas.processar` -> `selecao.selecionar`, sem trocar `erros_iterator` por mock.
Contrato: erro de `get()`/`next()` de elemento só é registrado em passagem de 1 elemento (com `ids=[esse]`); passagem de vários NÃO registra esse erro (o ruim é
isolado depois). Erro SEM `ids` só para falha de nível do iterator (vale para todo o pedido). Espia = o de `test_s06_t07a2_selecao_desempenho_oraculo.py`."""
import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401
from test_s06_t07a2_selecao_desempenho_oraculo import Espia, _cx, _ok

MSG = "falhou sem numero"
ERRO = "RuntimeError: " + MSG


def _modelo(bons=5):
    """5 proxies + 1 parede 'ruim' (a 3a criada, no meio), todos dentro do volume de um corte que pega tudo."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    els = []
    for i in range(bons + 1):
        if i == 2:
            els.append(X.caixa(f, "IfcWall", "ruim", i * 1.0, 1.0, 0.0, 0.5, 0.5, 0.5))
        else:
            els.append(X.caixa(f, "IfcBuildingElementProxy", f"b{i}", i * 1.0, 1.0, 0.0, 0.5, 0.5, 0.5))
    X.conter(f, pavs[0], *els)
    g = X.vista(f, "CORTE", pavs[0], origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 6.0))
    return f, g, X.id_de(f, "ruim")


def _espia(mp, ruim):
    return Espia(mp, ruim={ruim}, teto=80, msg=lambda i: MSG)


def test_lote_com_um_ruim_registra_um_erro_so_com_ids_do_ruim(tmp_path, monkeypatch):
    f, g, ruim = _modelo()
    arq = tmp_path / "m.ifc"
    f.write(str(arq))
    ped = {"op": "caixas", "arquivo": str(arq), "threads": 1,
           "elementos": [[e.id(), e.GlobalId] for e in f.by_type("IfcElement") if getattr(e, "Representation", None)]}
    _espia(monkeypatch, ruim)
    r = _ok(_cx(ped))
    assert r["falhas_geometria"] == [ruim] and len(r["caixas_envolventes"]) == 5
    assert r["erros_iterator"] == [{"tipo": "RuntimeError", "mensagem": MSG, "ids": [ruim]}]


def test_selecao_real_erro_so_do_ruim_e_igual_com_e_sem_sessao(monkeypatch):
    from obim_geometria import local
    from openbim_app.desenho import selecao
    f, g, ruim = _modelo()
    _espia(monkeypatch, ruim)
    ses = selecao.SessaoSelecao()
    s1 = selecao.selecionar(f, g, executor=local.executar, sessao=ses)
    assert s1.erros_geometria == (ERRO,) and s1.falhas_geometria == (ruim,) and s1 == selecao.selecionar(f, g, executor=local.executar)
    oculta = ("IfcWall",)  # esconde o ruim no 2o corte
    s2 = selecao.selecionar(f, g, executor=local.executar, sessao=ses, categorias_ocultas=oculta)
    assert s2.erros_geometria == () and s2.falhas_geometria == () and s2 == selecao.selecionar(f, g, executor=local.executar, categorias_ocultas=oculta)
    s3 = selecao.selecionar(f, g, executor=local.executar, sessao=ses)  # volta: um erro só, sem duplicar
    assert s3 == s1


def test_invalidar_o_ruim_limpa_o_erro_e_nao_deixa_erro_nos_bons(monkeypatch):
    from obim_geometria import local
    from openbim_app.desenho import selecao
    f, g, ruim = _modelo()
    esp = _espia(monkeypatch, ruim)
    ses = selecao.SessaoSelecao()
    assert selecao.selecionar(f, g, executor=local.executar, sessao=ses).erros_geometria == (ERRO,)
    esp.ruim.clear()  # o elemento "foi consertado"
    ses.invalidar([ruim])
    s = selecao.selecionar(f, g, executor=local.executar, sessao=ses)
    assert s.erros_geometria == () and s.falhas_geometria == () and ruim in s.ids
    assert s == selecao.selecionar(f, g, executor=local.executar)


def test_erro_de_nivel_do_iterator_sem_ids_vale_para_todo_o_pedido():
    exigir()
    from obim_geometria import local
    from openbim_app.desenho import selecao
    f, g, ruim = _modelo()
    nivel = lambda p: {**local.executar(p), "erros_iterator": [{"tipo": "RuntimeError", "mensagem": "init"}]}
    ses = selecao.SessaoSelecao()
    assert selecao.selecionar(f, g, executor=nivel, sessao=ses).erros_geometria == ("RuntimeError: init",)
    ses.invalidar([ruim])  # outros elementos ainda guardam o erro de nível
    assert selecao.selecionar(f, g, executor=local.executar, sessao=ses).erros_geometria == ("RuntimeError: init",)
    ocultar = ("IfcWall", "IfcBuildingElementProxy")  # tudo oculto: nada visível, nada a reportar
    assert selecao.selecionar(f, g, executor=local.executar, sessao=ses, categorias_ocultas=ocultar).erros_geometria == ()
