# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T04, parte 2: vista e prancha na TRANSAÇÃO do oplog (desfazer/refazer, erro, fora da transação, 10.000 operações misturadas;
ADR-003 §8 e §11 itens b, c, f). CONTRATO: o cabeçalho de `test_s06_t04_vistas_ifc_oraculo.py` (não editar nenhum dos dois). Em `Historico.transacao`,
`t.ifc` e `t.lado` como na S05. "Igual" = `s05_conteudo_aux.foto` (conteúdo, modelo e lateral, sem tolerância). Não editar este arquivo na implementação;
quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio, depois da implementação."""
import random

import pytest
import s05_conteudo_aux as R
import s06_t04_aux as A
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)
from s06_t04_sessao_aux import Sessao

AINDA_NAO = pytest.mark.xfail(strict=True, reason="F0-S06-T04: openbim_app.vistas_ifc ainda não existe")
SEMENTE, N_OPS = 20261029, 10_000


@pytest.fixture(params=A.ESQUEMAS)
def sessao(request):
    R.exigir()
    s = Sessao(A.novo_arquivo(request.param))
    yield s
    s.encerrar()


@AINDA_NAO
def test_desfazer_e_refazer_vista_e_prancha(sessao):
    import openbim_app.vistas_ifc as V
    s, f0 = sessao, sessao.foto()
    caixa = {}

    def uma(t):
        caixa["v"] = V.criar_vista(t.ifc, "Planta", "PLANTA", escala="1:50")
        t.lado.criar("viewports", "vp1", {"vista_guid": caixa["v"]})

    r1 = s.tx(uma)
    gid = caixa["v"]
    assert gid in r1.criados and ("viewports", "vp1") in r1.lado_criados
    f1 = s.foto()

    def duas(t):
        V.criar_prancha(t.ifc, "A-01", "Térreo")
        V.colocar_vista(t.ifc, "A-01", gid)
    s.tx(duas)
    f2 = s.foto()
    assert s.desfazer() is not None and R.diferencas(f1, s.foto()) == []
    assert s.desfazer() is not None and R.diferencas(f0, s.foto()) == []
    assert s.refazer() is not None and R.diferencas(f1, s.foto()) == [] and V.ler_vista(s.f, gid)["nome"] == "Planta"
    assert s.refazer() is not None and R.diferencas(f2, s.foto()) == []
    assert V.ler_prancha(s.f, "A-01")["vistas"] == [gid] and A.vista_ifc(s.f, gid)["ann"].GlobalId == gid, "GlobalId estável no refazer"
    s.tx(lambda t: V.apagar_vista(t.ifc, gid))
    assert V.listar_vistas(s.f) == [] and V.ler_prancha(s.f, "A-01")["vistas"] == []
    assert s.desfazer() is not None and R.diferencas(f2, s.foto()) == []
    assert V.ler_prancha(s.f, "A-01")["vistas"] == [gid], "desfazer do apagar traz a vista de volta com o mesmo GlobalId"
    s.tx(lambda t: V.apagar_prancha(t.ifc, "A-01"))
    assert s.desfazer() is not None and R.diferencas(f2, s.foto()) == []


@AINDA_NAO
def test_erro_dentro_da_transacao_volta_tudo(sessao):
    import openbim_app.vistas_ifc as V
    s, f0 = sessao, sessao.foto()

    def ruim(t):
        V.criar_vista(t.ifc, "X", "PLANTA")
        V.criar_prancha(t.ifc, "A-01", "x")
        t.lado.criar("viewports", "vp1", {})
        raise ZeroDivisionError
    with pytest.raises(ZeroDivisionError):
        s.tx(ruim)
    assert R.diferencas(f0, s.foto()) == [] and not s.h.pode_desfazer and not s.h.quebrado
    s.tx(lambda t: V.criar_prancha(t.ifc, "A-01", "agora vai"))
    assert V.ler_prancha(s.f, "A-01")["titulo"] == "agora vai"


@AINDA_NAO
def test_chave_repetida_dentro_da_transacao_nao_suja(sessao):
    import openbim_app.vistas_ifc as V
    s = sessao
    s.tx(lambda t: V.criar_prancha(t.ifc, "A-01", "um"))
    f1 = s.foto()

    def dup(t):
        with pytest.raises(V.IdentificacaoRepetida):
            V.criar_prancha(t.ifc, "A-01", "dois")
    s.tx(dup)
    assert R.diferencas(f1, s.foto()) == []


@AINDA_NAO
def test_escrita_fora_da_transacao_e_recusada(sessao):
    import openbim_app.vistas_ifc as V
    from openbim_app.transacao import EdicaoForaDeTransacao
    s, f0 = sessao, sessao.foto()
    with s.s.escrever() as esc:
        for fn in (lambda: V.criar_vista(esc.arquivo, "X", "PLANTA"), lambda: V.criar_prancha(esc.arquivo, "A-01", "x")):
            with pytest.raises(EdicaoForaDeTransacao):
                fn()
    assert R.diferencas(f0, s.foto()) == [] and not s.h.quebrado


# ---------- 10.000 operações misturadas (cartão: "continuam passando") ----------
def _mistura(s, V, rnd, n):  # n operações INTEIRAS em transações de 1 a 3; devolve o espelho {vistas: {gid: nome}, pranchas: {num: [gid]}}
    vistas, pranchas, feitas, k = {}, {}, 0, 0
    while feitas < n:
        ops = min(rnd.randint(1, 3), n - feitas)

        def tx(t):
            nonlocal k
            for _ in range(ops):
                k += 1
                c = rnd.choices(("cv", "av", "cp", "ap", "pv"), (4, 3, 2, 2, 4))[0]
                c = "av" if c == "cv" and len(vistas) >= 30 else "ap" if c == "cp" and len(pranchas) >= 15 else c  # população estável (~30 vistas, ~15 pranchas)
                if c == "av" and len(vistas) > 3:
                    g = rnd.choice(sorted(vistas))
                    V.apagar_vista(t.ifc, g)
                    del vistas[g]
                    for p in pranchas.values():
                        if g in p:
                            p.remove(g)
                elif c == "ap" and len(pranchas) > 2:
                    p = rnd.choice(sorted(pranchas))
                    V.apagar_prancha(t.ifc, p)
                    del pranchas[p]
                elif c == "cp":
                    p = f"F-{k}.{rnd.randint(0, 9)}"
                    V.criar_prancha(t.ifc, p, f"Folha {k}")
                    pranchas[p] = []
                elif c == "pv" and vistas and pranchas:
                    p, g = rnd.choice(sorted(pranchas)), rnd.choice(sorted(vistas))
                    if g not in pranchas[p]:
                        V.colocar_vista(t.ifc, p, g)
                        pranchas[p].append(g)
                else:
                    g = V.criar_vista(t.ifc, f"Vista {k % 7}", rnd.choice(("PLANTA", "CORTE")), escala=rnd.choice(("1:50", "1:100")))
                    vistas[g] = f"Vista {k % 7}"
                    t.lado.criar("viewports", f"vp{k}", {"vista_guid": g})
        s.tx(tx)
        feitas += ops
        if feitas % 1000 < 3:  # confere o espelho a cada ~1.000 operações
            assert {x["gid"]: x["nome"] for x in V.listar_vistas(s.f)} == vistas
            assert {p["numero"]: p["vistas"] for p in V.listar_pranchas(s.f)} == pranchas
    return vistas, pranchas


@AINDA_NAO
def test_dez_mil_operacoes_misturadas(sessao):
    import openbim_app.vistas_ifc as V
    s, f0 = sessao, sessao.foto()
    vistas, pranchas = _mistura(s, V, random.Random(SEMENTE), N_OPS)
    assert len(vistas) >= 3 and len(pranchas) >= 2
    f1, passos = s.foto(), 0
    while s.h.pode_desfazer:
        assert s.desfazer() is not None
        passos += 1
    assert passos > 3000 and s.h.descartados == 0 and R.diferencas(f0, s.foto()) == []
    while s.refazer() is not None:
        pass
    assert R.diferencas(f1, s.foto()) == []
    assert {x["gid"]: x["nome"] for x in V.listar_vistas(s.f)} == vistas and {p["numero"]: p["vistas"] for p in V.listar_pranchas(s.f)} == pranchas
