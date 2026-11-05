# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo F0-S06-T07a2 (mutantes do diff do DeepSeek): valores absolutos, `next()` que levanta, árvore (ordem e formato), sessão (erros e conjunto
fechado do corte) e threads do desenho. Usa os ganchos do arquivo principal `test_s06_t07a2_selecao_desempenho_oraculo.py` (contrato no docstring dele)."""
import time

import pytest
import s06_t07_aux as X
import s06_t07e_aux as T
from s05_conteudo_aux import _limpa, exigir  # noqa: F401
from test_s06_t07a2_selecao_desempenho_oraculo import Espia, Executor, _cortes, _cx, _ok, modelo  # noqa: F401


def test_caixas_valores_absolutos(modelo):
    _, d, ped, _ = modelo
    r = _ok(_cx(ped, threads=1))["caixas_envolventes"]
    assert r[str(d["P"].id())] == [0.0, 0.0, 0.0, 5.0, 0.25, 3.0] and r[str(d["M"].id())] == [1.0, 2.0, 0.0, 1.5, 2.5, 1.5]
    assert r[str(d["Q"].id())] == [0.0, 0.0, 3.0, 5.0, 0.25, 6.0]


def test_next_que_levanta_e_registrado_e_resultado_completo(modelo, monkeypatch):
    _, _, ped, _ = modelo
    ref = _ok(_cx(ped, threads=1))
    esp = Espia(monkeypatch, next_falha=True)
    r = _ok(_cx(ped, threads=1))
    assert r["caixas_envolventes"] == ref["caixas_envolventes"] and r["falhas_geometria"] == ref["falhas_geometria"]
    assert r["erros_iterator"] and r["erros_iterator"][0]["mensagem"] == "next quebrou" and len(esp.construcoes) >= 2


def test_arvore_ordem_de_entrada_e_formato_invalido():
    exigir()
    from obim_geometria.caixas import ArvoreCaixas
    a = ArvoreCaixas({"30": [0, 0, 0, 1, 1, 1], "10": [0, 0, 0, 1, 1, 1], "20": [0, 0, 0, 1, 1, 1]})
    assert a.cruzando((0, 0, 0), (1, 1, 1)) == [10, 20, 30]
    for ruim in ([0, 0, 2, 1, 1, 1], [0, 0, 0, 1, 1], [0, 0, 0, 1, 1, 1, 1]):
        with pytest.raises(ValueError):
            ArvoreCaixas({"1": ruim})
    with pytest.raises(ValueError):
        a.cruzando((0, 0, 2), (1, 1, 1))
    with pytest.raises(ValueError):
        a.cruzando((0, 0, 0), (1, 1))


def test_selecao_com_sessao_confere_conjunto_absoluto_do_corte():
    exigir()
    from openbim_app.desenho import selecao
    f, pavs, dentro, fora = X.faixa("IFC4")
    ga, gb = _cortes(f, pavs)
    ses, ex = selecao.SessaoSelecao(), Executor()
    for _ in range(2):  # 1a vez calcula, 2a vem da sessão: o mesmo conjunto fechado (encostar conta, 1/64 m fora não)
        s = selecao.selecionar(f, ga, executor=ex, sessao=ses)
        assert X.nomes(f, s) == dentro and not (X.nomes(f, s) & fora)
        assert s.falhas_geometria == (X.id_de(f, "falha"), X.id_de(f, "falha2"), X.id_de(f, "so_eixo"))
    sb = selecao.selecionar(f, gb, executor=ex, sessao=ses)
    assert sb == selecao.selecionar(f, gb, executor=Executor()) and len(ex.pedidos) == 1
    assert not (set(sb.ids) & set(sb.falhas_geometria))


def test_sessao_invalidar_tudo_limpa_tambem_os_erros():
    exigir()
    from obim_geometria import local
    from openbim_app.desenho import selecao
    f, d = T.modelo()
    ses = selecao.SessaoSelecao()
    com_erro = lambda p: {**local.executar(p), "erros_iterator": [{"tipo": "RuntimeError", "mensagem": "boom"}]}
    assert selecao.selecionar(f, d["vc"], executor=com_erro, sessao=ses).erros_geometria == ("RuntimeError: boom",)
    assert selecao.selecionar(f, d["vc"], executor=local.executar, sessao=ses).erros_geometria == ("RuntimeError: boom",)  # erro da sessão persiste
    ses.invalidar()
    assert selecao.selecionar(f, d["vc"], executor=local.executar, sessao=ses).erros_geometria == ()


def test_desenho_usa_limitar_threads(monkeypatch):
    exigir()
    from obim_geometria import local, nucleos as N
    from openbim_app.desenho import auxiliar, planta
    f, d = T.modelo()
    with pytest.raises(auxiliar.FalhaNoAuxiliar, match="ThreadsInvalidas"):
        planta.gerar_planta(f, d["vp"], executor=lambda p: local.executar({**p, "threads": 0}))
    monkeypatch.setattr(N, "nucleos_fisicos", lambda: 3)
    esp = Espia(monkeypatch)
    planta.gerar_planta(f, d["vp"], executor=lambda p: local.executar({k: v for k, v in p.items() if k != "threads"}))
    assert [c[0] for c in esp.construcoes] == [3]
    planta.gerar_planta(f, d["vp"], executor=lambda p: local.executar({**p, "threads": 64}))
    assert esp.construcoes[-1][0] == 3


def test_um_elemento_com_threads_1_e_muitas(modelo):
    _, d, ped, _ = modelo
    um = [ped["elementos"][0]]
    a, b = _ok(_cx({**ped, "elementos": um}, threads=1)), _ok(_cx({**ped, "elementos": um}, threads=8))
    assert a["caixas_envolventes"] == b["caixas_envolventes"] and list(a["caixas_envolventes"]) == [str(d["P"].id())] and a["falhas_geometria"] == []


def test_elemento_divergente_continua_erro_explicito(modelo):
    _, _, ped, _ = modelo
    r = _cx({**ped, "elementos": [[ped["elementos"][0][0], "0000000000000000000000"]]})
    assert r["ok"] is False and r["erro"]["tipo"] == "ArquivoDivergente"


# ---------- 5. desempenho relativo (razão, não segundos) ----------
def test_desempenho_segundo_corte_da_sessao_bem_mais_rapido_que_o_primeiro():
    exigir()
    from obim_geometria import local
    from openbim_app.desenho import selecao
    f, pavs = X.estrutura("IFC4")
    for i in range(400):
        X.conter(f, pavs[i % 2], X.caixa(f, "IfcBuildingElementProxy", f"e{i}", (i % 20) * 1.0, (i // 20) * 1.0, 0.0, 0.5, 0.5, 0.5))
    ga = X.vista(f, "CORTE", pavs[0], origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 6.0), nome="A")
    gb = X.vista(f, "CORTE", pavs[0], origem=(5.0, 5.0, 0.0), tamanho=(10.0, 10.0, 6.0), nome="B")
    ses = selecao.SessaoSelecao()
    t0 = time.perf_counter()
    selecao.selecionar(f, ga, executor=local.executar, sessao=ses)
    frio = time.perf_counter() - t0
    if not 0.05 <= frio <= 60.0:
        pytest.skip(f"ambiente rápido ou lento demais para razão confiável (primeiro corte {frio:.3f} s)")
    melhor = min(_tempo(lambda: selecao.selecionar(f, gb, executor=local.executar, sessao=ses)) for _ in range(3))
    assert melhor < 0.5 * frio, f"2o corte {melhor:.3f} s contra 1o {frio:.3f} s"  # esperado: ordem de 10x ou mais

def _tempo(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0
