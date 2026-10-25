# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T04, segunda leva (autor do oráculo; quem implementa não edita; `@AINDA_NAO` = o mesmo xfail estrito do arquivo principal, sai no mesmo commit). Casos que o ADR-002 pede
e a primeira leva não cobria:
L1 (§4.2): `file.add` fora da transação levanta e MARCA o histórico como quebrado (as dependências criadas não dá para limpar).
L2 (cartão T04, item 5; §4.2 "uma transação nossa = um Transaction + a lista do lateral"): editar o lateral fora da transação é recusado e não muda nada.
L3 (§4.4: o diário tem registros `desfazer` e `refazer`; "o que está na memória = base + diário"): `anotar` é chamado uma vez em cada desfazer e
   refazer que fez algo (nenhuma vez quando devolve None); se ele falha, o passo volta nos dois lados, as pilhas ficam como estavam e o erro sobe.
L4 (§4.4): `codificar` que falha (operação que não vira JSON) descarta a transação: erro sobe, foto e pilhas iguais, nada anotado.
L5 (§4.2): `end_transaction` de terceiros fora da nossa transação (empilha a sentinela) é detectado: a transação seguinte levanta `HistoricoQuebrado`.
L6 (§4.2 "Se o próprio rollback do descarte levantar: HistoricoQuebrado"): exceção dentro da transação e o `rollback` do `Transaction` aberto falha ->
   `HistoricoQuebrado` (não a exceção original), `quebrado` verdadeiro, e a transação seguinte recusa."""
import pytest
import s05_t04_aux as A
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from test_s05_t04_transacao_oraculo import Real, _mods, _pilhas, novo  # noqa: F401  (fixture `novo`)


def test_l1_add_fora_da_transacao_quebra_o_historico(novo):
    T, _, _ = _mods()
    d, _ = novo()
    outro = A.R.ifcopenshell.file(schema=d.f.schema_identifier)
    w = outro.createIfcWall(A.R.ifcopenshell.guid.new(), None, "de fora", None, None,
                            outro.createIfcLocalPlacement(None, outro.createIfcAxis2Placement3D(outro.createIfcCartesianPoint((1.0, 2.0, 3.0)))))
    with d.s.escrever() as esc:
        with pytest.raises((T.EdicaoForaDeTransacao, T.HistoricoQuebrado)):
            esc.arquivo.add(w)
    assert d.h.quebrado, "file.add fora da transação deixou dependências soltas sem marcar o histórico quebrado (ADR-002 §4.2)"


def test_l2_lateral_fora_da_transacao_recusado(novo):
    d, _ = novo()
    c0 = d.lat.canonico()
    for nome, args in (("criar", ("notas", "fora", {"n": 1})), ("alterar", ("notas", "fora", {"n": 2})), ("apagar", ("notas", "fora"))):
        fn = getattr(d.lat, nome, None)
        if fn is not None:
            with pytest.raises(Exception):
                fn(*args)
        assert d.lat.canonico() == c0, f"Lateral.{nome} fora da transação mudou o lateral (some do desfazer em silêncio)"


class _Anotar:
    def __init__(s):
        s.tipos, s.falhar = [], False

    def __call__(s, tipo, *a, **k):
        if s.falhar:
            raise OSError(28, "disco cheio (ensaio)")
        s.tipos.append(tipo)


def test_l3_anotar_em_desfazer_e_refazer(novo):
    an = _Anotar()
    d, plano = novo(anotar=an)
    d.tx([plano.op("nome"), plano.op("lado_criar")])
    d.tx([plano.op("parede")])
    assert an.tipos == ["transacao", "transacao"]
    for passo in (d.desfazer, d.refazer):  # desfazer: o passo 2 está no histórico; refazer: depois de desfazer, está no refazer
        if passo is d.refazer:
            d.desfazer()
        f0, p0, n0 = d.foto(), _pilhas(d), len(an.tipos)
        an.falhar = True
        with pytest.raises(OSError):
            passo()
        an.falhar = False
        A.igual(d, f0, f"anotar falhou em {passo.__name__}")
        assert (_pilhas(d), d.h.pode_desfazer, len(an.tipos)) == (p0, True, n0) and not d.h.quebrado
        assert passo() is not None and an.tipos[-1] == passo.__name__, f"{passo.__name__} não foi anotado"
    while d.desfazer() is not None:
        pass
    n = len(an.tipos)
    assert d.desfazer() is None and len(an.tipos) == n, "desfazer sem nada a fazer foi anotado"


def test_l4_codificar_que_falha_descarta(novo):
    T, _, _ = _mods()
    an, falha = _Anotar(), [False]

    def codificar(ops):
        if falha[0]:
            raise ValueError("operação que não vira JSON (ensaio)")
        return [dict(o) for o in ops]
    d, plano = novo(anotar=an, codificar=codificar)
    d.tx([plano.op("nome")])
    d.tx([plano.op("lado_criar")])
    d.desfazer()
    f0, p0, n0 = d.foto(), _pilhas(d), len(an.tipos)
    falha[0] = True
    with pytest.raises(ValueError):
        d.tx([plano.op("parede"), plano.op("lado_criar")])
    A.igual(d, f0, "codificar falhou")
    assert (_pilhas(d), len(an.tipos)) == (p0, n0) and p0[2] and not d.h.quebrado


def test_l5_end_transaction_de_terceiros_detectado(novo):
    T, _, _ = _mods()
    d, plano = novo()
    d.tx([plano.op("nome")])
    with d.s.escrever() as esc:
        esc.arquivo.end_transaction()  # terceiro fecha "a transação" que não é dele
        with pytest.raises(T.HistoricoQuebrado):
            with d.h.transacao(esc) as t:
                A.aplicar(plano.op("nome"), t.ifc, t.lado, d.c)
    assert d.h.quebrado


class _Erro(Exception):
    pass


def test_l6_rollback_do_descarte_falha_quebra_o_historico(novo):
    T, _, _ = _mods()
    d, plano = novo()
    d.tx([plano.op("nome")])
    with pytest.raises(T.HistoricoQuebrado):
        with d.s.escrever() as esc, d.h.transacao(esc) as t:
            A.aplicar(plano.op("nome"), t.ifc, t.lado, d.c)
            t.ifc.transaction.rollback = lambda: 1 / 0  # o Transaction aberto (o nosso): o descarte vai falhar
            raise _Erro("dentro")
    assert d.h.quebrado, "rollback do descarte falhou e o histórico não ficou quebrado (ADR-002 §4.2)"
    with pytest.raises(T.HistoricoQuebrado):
        d.tx([plano.op("nome")])
