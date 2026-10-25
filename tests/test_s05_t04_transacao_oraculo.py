# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de transação do histórico (ADR-002 §4.1 a §4.3 e §4.8; casos 1 a 12).
Não editar este arquivo nem `tests/s05_*aux.py` (régua P1, gerador); quem tira os `@AINDA_NAO` (xfail estrito) é o autor do teste, em
commit próprio, depois da implementação (só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`). CONTRATO (só nomes do ADR-002 §4.8; o implementador lê isto e o ADR):
1. `openbim_app.lateral`: `Lateral()`; `obter(c, id)` devolve CÓPIA (ou None); `canonico()` = bytes do JSON canônico do lateral inteiro (não depende da
   ordem de criação); `ObjetoInvalido` (ex.: NaN). Edição do lateral só por `t.lado.criar(c, id, obj)`, `t.lado.alterar(c, id, obj)`, `t.lado.apagar(c, id)`.
2. `openbim_app.transacao`: `Historico(sessao, lateral, limite_bytes=None, codificar=None, anotar=None)`, com `sessao` = `SessaoModelo`. O teste edita o
   arquivo LIVRE antes de construir o `Historico` (montagem); a guarda (sentinela em `arquivo.transaction`) vale a partir da construção. `anotar` é chamado
   uma vez por transação confirmada (passo 5 do §4.2; o teste aceita `*a, **k`) e NUNCA por `fora_do_historico`.
3. `with h.transacao(esc) as t:` (esc = a `Escrita` de `SessaoModelo.escrever()`): `t.ifc` é o arquivo (o teste usa `ifcopenshell.api` sobre ele), `t.lado`
   como em 1; ao sair, `t.resumo`. `h.desfazer(esc)` / `h.refazer(esc)` devolvem `Resumo` ou None (nada a fazer). `Resumo(criados, alterados, apagados,
   lado_criados, lado_alterados, lado_apagados)`: coleções comparadas como conjunto (GlobalId; no lateral, `(coleção, id)` comparado como tupla).
4. `h.pode_desfazer`, `h.pode_refazer`, `h.quebrado` (bool) e `h.descartados` (int) são PROPRIEDADES (lidas sem chamar). Uma transação nossa = um
   `Transaction`: `len(arquivo.history)` e `len(arquivo.future)` andam junto com o nosso histórico. `h.encerrar()` esvazia `history`/`future` e tira
   `int(arquivo.this)` de `ifcopenshell.file.registry`. `with h.fora_do_historico(esc):` edição livre (carimbo do pset `OBIM_Projeto`), fora do histórico.
5. Erros: edição dentro de `escrever()` e fora da transação (atributo, `remove`, `create_entity`) -> `EdicaoForaDeTransacao` ANTES de aplicar (o objeto
   criado sai), sem quebrar o histórico. Transação, desfazer ou refazer dentro de transação -> `TransacaoAberta`. `esc` vencido -> `TravaNaoSegura`
   (`sessao_modelo`). Exceção dentro: tudo volta nos dois lados, histórico e refazer intactos, a exceção original sobe. Falha no `anotar` (depois do
   `end_transaction`): o passo é desfeito nos dois lados, sai do histórico, o refazer se perde, o erro sobe, a próxima transação funciona.
   `UndoSystemError` no desfazer, ou `arquivo.transaction` trocado por terceiros (`begin_transaction`/`discard_transaction` aninhados, sentinela sumida)
   -> `HistoricoQuebrado`, `quebrado` verdadeiro e toda transação, desfazer e refazer seguintes recusam com `HistoricoQuebrado`; o lateral não é mexido.
Gerador, semente 20261023 e pisos (10.000 operações INTEIRAS, 500 por tipo, 1.000 mistas): `tests/s05_t04_aux.py`; régua: `tests/s05_conteudo_aux.py`.
GUARDA (pula, nunca afrouxa): sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 todo pulo vira falha. Casos pesados (1, 2) rodam num pytest FILHO
(OBIM_S05_T04_DENTRO=1; registry do ifcopenshell isolado, como no V1c); o `@AINDA_NAO` deles fica só no processo de fora."""
import errno
import os
import random

import pytest
import s05_t04_aux as A
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t04_aux import SEMENTE, TIPOS, aplicar, igual, montar



class Real:  # o módulo de transações
    def __init__(s, f, c, **kw):
        from openbim_app.lateral import Lateral
        from openbim_app.sessao_modelo import SessaoModelo
        from openbim_app.transacao import Historico
        s.f, s.c, s.s, s.lat = f, c, SessaoModelo(f), Lateral()
        s.h = Historico(s.s, s.lat, **kw)

    def tx(s, ops):
        with s.s.escrever() as esc, s.h.transacao(esc) as t:
            for op in ops:
                aplicar(op, t.ifc, t.lado, s.c)
        return t.resumo

    def desfazer(s):
        with s.s.escrever() as esc:
            return s.h.desfazer(esc)

    def refazer(s):
        with s.s.escrever() as esc:
            return s.h.refazer(esc)

    pode_desfazer = property(lambda s: s.h.pode_desfazer)
    ler = lambda s: s.s.ler()  # noqa: E731

    def foto(s):
        with s.s.ler() as f:
            return A.R.foto(f, s.lat)


@pytest.fixture
def novo(base_ifc):  # fábrica: (Real, plano) sobre um modelo montado; encerra no fim
    feitos = []

    def fazer(**kw):
        f, c, plano = montar(base_ifc)
        feitos.append(Real(f, c, **kw))
        return feitos[-1], plano
    yield fazer
    for d in feitos:
        try:
            d.h.encerrar()
        except Exception:  # noqa: BLE001  (só limpeza; o caso 10 confere o encerrar)
            pass


def pesado_1_dez_mil_e_12_limite_desligado():
    f, c, plano = montar(os.environ["OBIM_S05_T04_BASE"])
    d = Real(f, c, limite_bytes=None)
    A.dez_mil(d, plano)
    assert d.h.descartados == 0 and d.h.pode_desfazer and not d.h.pode_refazer  # caso 12 (refez tudo)
    d.h.encerrar()


def pesado_2_mistura_com_desfazer_e_refazer():
    f, c, plano = montar(os.environ["OBIM_S05_T04_BASE"])
    d, r, pilha, fut = Real(f, c), random.Random(SEMENTE + 2), [], []
    f0 = d.foto()
    for passo in range(2000):
        x, k = r.random(), r.randint(1, 3)
        if x < 0.7:
            pilha.append(plano.estado())
            d.tx(plano.transacao(3))
            if fut:
                fut.clear()
                assert d.refazer() is None, f"semente {SEMENTE}, passo {passo}: transação nova não zerou o refazer"
        for _ in range(k if x >= 0.7 else 0):
            de, para, fn = (pilha, fut, d.desfazer) if x < 0.9 else (fut, pilha, d.refazer)
            tinha = bool(de)
            if tinha:
                para.append(plano.estado())
                plano.restaurar(de.pop())
            assert (fn() is not None) == tinha, f"semente {SEMENTE}, passo {passo}: Resumo/None errado"
        assert (d.h.pode_desfazer, d.h.pode_refazer) == (bool(pilha), bool(fut)), f"semente {SEMENTE}, passo {passo}"
    fim = d.foto()
    while d.desfazer() is not None:
        pass
    igual(d, f0, "mistura: desfazer tudo")
    while d.refazer() is not None:
        pass
    igual(d, fim, "mistura: refazer tudo")
    d.h.encerrar()


# ---------- casos leves do módulo novo (neste processo) ----------
class Erro(Exception):
    pass


def _mods():
    import openbim_app.lateral as L
    import openbim_app.sessao_modelo as S
    import openbim_app.transacao as T
    return T, L, S


def _pilhas(d):
    with d.ler() as f:
        return len(f.history), len(f.future), d.h.pode_refazer


def test_3_excecao_dentro_volta_os_dois_lados(novo):
    d, plano = novo()
    d.tx([plano.op("pset_criar"), plano.op("lado_criar"), plano.op("parede")])
    d.tx([plano.op("nome")])
    f_refazer = d.foto()  # o que o refazer tem de trazer de volta depois de cada exceção (o passo "nome", nunca a transação abortada)
    d.desfazer()
    for t in TIPOS + ("misto",):
        f0, p0, est = d.foto(), _pilhas(d), plano.estado()
        ops = [plano.op(x) for x in ("parede", "lote", "lado_criar", "lado_alterar", "tipo")] if t == "misto" else [
            plano.op(t), plano.op("nome" if t.startswith("lado") else "lado_criar")]
        with pytest.raises(Erro):
            with d.s.escrever() as esc, d.h.transacao(esc) as tr:
                for op in ops:
                    aplicar(op, tr.ifc, tr.lado, d.c)
                raise Erro(t)
        igual(d, f0, f"exceção dentro ({t})")
        assert _pilhas(d) == p0 == (1, 1, True), f"{t}: histórico ou refazer mudou"
        assert d.refazer() is not None
        igual(d, f_refazer, f"exceção dentro ({t}): o refazer não é mais o passo de antes")
        assert d.desfazer() is not None
        igual(d, f0, f"exceção dentro ({t}): desfazer depois do refazer")
        assert _pilhas(d) == p0, f"{t}: pilhas depois de refazer e desfazer"
        plano.restaurar(est)


def test_4_lateral_invalido_volta_o_ifc(novo):
    T, L, _ = _mods()
    d, plano = novo()
    f0 = d.foto()
    with pytest.raises(L.ObjetoInvalido):
        with d.s.escrever() as esc, d.h.transacao(esc) as t:
            aplicar(plano.op("nome"), t.ifc, t.lado, d.c)
            t.lado.criar("notas", "x", {"v": float("nan")})
    igual(d, f0, "lateral inválido")


def test_5_undo_system_error_quebra_o_historico(novo):
    T, _, _ = _mods()
    d, plano = novo()
    d.tx([plano.op("nome"), plano.op("lado_criar")])
    lado0 = d.lat.canonico()
    with d.s.escrever() as esc:
        esc.arquivo.history[-1].rollback = lambda: 1 / 0
        with pytest.raises(T.HistoricoQuebrado):
            d.h.desfazer(esc)
        assert d.lat.canonico() == lado0 and d.h.quebrado
        for fn in (lambda: d.h.transacao(esc).__enter__(), lambda: d.h.desfazer(esc), lambda: d.h.refazer(esc)):
            with pytest.raises(T.HistoricoQuebrado):
                fn()


@pytest.mark.parametrize("como", ["begin", "begin_discard", "sentinela_sumiu"])
def test_5b_transacao_de_terceiros_detectada(novo, como):
    T, _, _ = _mods()
    d, plano = novo()
    with d.s.escrever() as esc:
        with pytest.raises(T.HistoricoQuebrado):
            if como == "sentinela_sumiu":
                esc.arquivo.transaction = None
            with d.h.transacao(esc) as t:
                aplicar(plano.op("nome"), t.ifc, t.lado, d.c)
                if como != "sentinela_sumiu":
                    t.ifc.begin_transaction()  # como ifcopenshell.api.alignment (_get_segment_endpoint.py:43 e :89)
                    como == "begin_discard" and t.ifc.discard_transaction()
        assert d.h.quebrado


def test_5c_falha_do_anotar_desfaz_o_passo(novo):
    class Anotar:
        falhar, n = False, 0

        def __call__(s, *a, **k):
            s.n += 1
            if s.falhar:
                raise OSError(errno.ENOSPC, "disco cheio (ensaio)")
    an = Anotar()
    d, plano = novo(anotar=an)
    d.tx([plano.op("nome")])
    d.tx([plano.op("lado_criar")])
    d.desfazer()
    f0, (nh, _, refazer) = d.foto(), _pilhas(d)
    assert refazer
    an.falhar = True
    with pytest.raises(OSError) as e:
        d.tx([plano.op("parede"), plano.op("lado_criar")])
    assert e.value.errno == errno.ENOSPC
    igual(d, f0, "anotar falhou")
    assert _pilhas(d) == (nh, 0, False) and not d.h.quebrado
    an.falhar = False
    d.tx([plano.op("nome")])
    assert _pilhas(d)[0] == nh + 1


def test_6_edicao_fora_de_transacao_recusada(novo):
    T, _, _ = _mods()
    d, plano = novo()
    with d.s.escrever() as esc:
        f, w = esc.arquivo, esc.arquivo.by_type("IfcWall")[0]
        n, nome = len(f.by_type("IfcWall")), w.Name
        assert nome != "x"
        for fn in (lambda: setattr(w, "Name", "x"), lambda: f.remove(w), lambda: f.create_entity("IfcWall", GlobalId="0" * 22, Name="z")):
            with pytest.raises(T.EdicaoForaDeTransacao):
                fn()
        assert w.Name == nome and len(f.by_type("IfcWall")) == n and not d.h.quebrado
    d.tx([plano.op("nome")])
    assert d.h.pode_desfazer


def test_7_porta_e_transacao_aberta(novo):
    T, _, S = _mods()
    d, plano = novo()
    d.tx([plano.op("nome")])
    with d.s.escrever() as velho:
        pass
    for fn in (lambda: d.h.transacao(velho).__enter__(), lambda: d.h.desfazer(velho), lambda: d.h.refazer(velho)):
        with pytest.raises(S.TravaNaoSegura):
            fn()
    with d.s.escrever() as esc, d.h.transacao(esc):
        for fn in (lambda: d.h.transacao(esc).__enter__(), lambda: d.h.desfazer(esc), lambda: d.h.refazer(esc)):
            with pytest.raises(T.TransacaoAberta):
                fn()


def test_8_resumo_por_dono(novo):
    d, plano = novo()
    G = d.c["g"]
    w, w2 = plano.paredes[:2]
    s = lambda r, k: set(map(tuple, getattr(r, k))) if k.startswith("lado") else set(getattr(r, k))  # noqa: E731
    r = d.tx([("parede", "pz")])
    assert s(r, "criados") == {G["pz"]} and not s(r, "apagados")
    assert s(d.desfazer(), "apagados") == {G["pz"]} and s(d.refazer(), "criados") == {G["pz"]}
    for op in (("nome", w), ("mover", w)):
        r = d.tx([op])
        assert (s(r, "alterados"), s(r, "criados"), s(r, "apagados")) == ({w}, set(), set()), op
    d.tx([("pset_criar", w, "psz")])
    assert s(d.tx([("pset_editar", "psz")]), "alterados") == {w}
    with d.ler() as f:
        rels = {x.GlobalId for x in f.by_type("IfcRelContainedInSpatialStructure")}
    r = d.tx([("pavimento", w)])
    assert w in s(r, "alterados") and not rels & s(r, "alterados")
    assert s(d.tx([("apagar", w2)]), "apagados") == {w2}
    for t, k in (("lado_criar", "lado_criados"), ("lado_alterar", "lado_alterados")):
        assert s(d.tx([(t, "notas", "oz", [w])]), k) == {("notas", "oz")}
    assert s(d.tx([("lado_apagar", "notas", "oz")]), "lado_apagados") == {("notas", "oz")}


def test_9_lateral_canonico_e_obter_copia(novo):
    d, _ = novo()
    objs = [("notas", "a", {"ifc_guid": "x", "n": 1}), ("cotas", "b", {"ifc_guids": ["y", "z"], "t": "ção"}), ("notas", "c", {"v": [1, 2.5, None]})]

    def criar(lista):
        with d.s.escrever() as esc, d.h.transacao(esc) as t:
            for c, i, o in lista:
                t.lado.criar(c, i, o)
    criar(objs)
    c1 = d.lat.canonico()
    d.desfazer()
    for o in reversed(objs):
        criar([o])
    assert d.lat.canonico() == c1, "canonico() depende da ordem de criação"
    o = d.lat.obter("notas", "a")
    o["n"] = 2
    assert d.lat.obter("notas", "a") == {"ifc_guid": "x", "n": 1} and d.lat.canonico() == c1, "obter() não devolveu cópia"


def test_10_encerrar_solta_o_registry(novo):
    import ifcopenshell
    d, plano = novo()
    d.tx([plano.op("parede")])
    d.tx([plano.op("nome")])
    d.desfazer()
    d.h.encerrar()
    assert (list(d.f.history), list(d.f.future)) == ([], []) and int(d.f.this) not in ifcopenshell.file.registry


def test_11_fora_do_historico(novo):
    T, _, _ = _mods()
    _, api, _, _ = A._api()
    chamadas = []
    d, plano = novo(anotar=lambda *a, **k: chamadas.append(1))
    d.tx([plano.op("nome")])
    with d.s.escrever() as esc:
        f, n, pd = esc.arquivo, len(chamadas), d.h.pode_desfazer
        nh, ps = len(f.history), f.by_guid(d.c["obim"])
        with d.h.fora_do_historico(esc):
            api("pset.edit_pset", f, pset=ps, properties={"Revisao": 7, "LadoId": "novo"})
        assert (d.h.pode_desfazer, len(f.history), len(chamadas)) == (pd, nh, n), "fora_do_historico entrou no histórico ou no diário"
        d.h.desfazer(esc)
        assert {p.Name: p.NominalValue.wrappedValue for p in ps.HasProperties} == {"Revisao": 7, "LadoId": "novo"}
        with pytest.raises(T.EdicaoForaDeTransacao):
            api("pset.edit_pset", f, pset=ps, properties={"Revisao": 8})
        assert {p.Name: p.NominalValue.wrappedValue for p in ps.HasProperties}["Revisao"] == 7


# ---------- de fora: cada caso pesado num pytest filho (o `@AINDA_NAO` fica aqui, o filho roda sem marca) ----------
PESADOS = sorted(k for k in list(globals()) if k.startswith("pesado_"))
if A.DENTRO:
    for _k in PESADOS:
        globals()["test_" + _k] = (lambda fn: lambda: fn())(globals()[_k])
else:
    @pytest.mark.parametrize("caso", [pytest.param(k, marks=getattr(globals()[k], "pytestmark", [])) for k in PESADOS])
    def test_pesado_em_subprocesso(caso, base_ifc):  # noqa: F811
        A.rodar_filho(__file__, caso, base_ifc)
