# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo do F0-S05-T04, segunda leva (mutantes vivos do lote Opus 81; autor do oráculo; quem implementa não edita).
Mesmo contrato de `test_s05_t04_transacao_oraculo.py` (ADR-002 §4.1 a §4.3), nada novo. Vale já (o T04 está no main), sem `@AINDA_NAO`.
B1 (§4.1, resumo por dono): "atribuir tipo" (relação criada: todos os objetos dela; relação editada: só quem entrou ou saiu), "apagar" (relação
   apagada junto: o tipo que ficou sem a parede é alterado) e entidade sem GlobalId apagada por `remove` (atingidos pelos inversos: o dono sobe).
B2 (§4.3): `IdInexistente` em alterar e apagar de id que não existe, `IdRepetido` em criar repetido, `ObjetoInvalido` para objeto que não é dict
   e para coleção ou id fora do formato; em todos, a transação volta inteira (foto igual).
B3 (§4.2): transação nossa e `fora_do_historico` não se aninham, nos dois sentidos: `TransacaoAberta`."""
import pytest
import s05_t04_aux as A
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from test_s05_t04_transacao_oraculo import _mods, novo  # noqa: F401  (fixture `novo`)


def _s(r, k):
    return set(getattr(r, k))


def _tx_ifc(d, fn):  # transação com uma função livre sobre o arquivo; devolve o Resumo
    with d.s.escrever() as esc, d.h.transacao(esc) as t:
        fn(t.ifc)
    return t.resumo


def test_b1_resumo_tipo_apagar_e_inversos(novo):
    d, plano = novo()
    G, (w0, w1, w2) = d.c["g"], plano.paredes[:3]
    r = d.tx([("tipo", w0, "t0", False)])  # relação IfcRelDefinesByType criada: a parede e o tipo
    assert (_s(r, "alterados"), _s(r, "criados"), _s(r, "apagados")) == ({w0, G["t0"]}, set(), set()), r
    r = d.tx([("tipo", w1, "t0", False)])  # relação editada: só a parede que entrou
    assert (_s(r, "alterados"), _s(r, "criados")) == ({w1}, set()), r
    r = d.tx([("tipo", w2, "t9", True)])  # tipo novo na mesma transação: criado, não alterado
    assert (_s(r, "criados"), _s(r, "alterados")) == ({G["t9"]}, {w2}), r
    r = d.tx([("apagar", w1)])  # o tipo t0 segue com w0: a relação só perde o apagado
    assert (_s(r, "apagados"), _s(r, "alterados")) == ({w1}, set()), r
    r = d.tx([("apagar", w0)])  # última parede do t0: a relação sai junto, o tipo é alterado
    assert (_s(r, "apagados"), _s(r, "alterados")) == ({w0}, {G["t0"]}), r
    r = d.desfazer()
    assert (_s(r, "criados"), _s(r, "alterados"), _s(r, "apagados")) == ({w0}, {G["t0"]}, set()), r
    w7 = plano.paredes[7]
    r = _tx_ifc(d, lambda f: f.remove(f.by_guid(w7).ObjectPlacement.RelativePlacement))  # sem GlobalId, só nos inversos do apagado
    assert (_s(r, "alterados"), _s(r, "criados"), _s(r, "apagados")) == ({w7}, set(), set()), r


def test_b2_lateral_ids_e_objetos_recusados(novo):
    T, L, _ = _mods()
    d, plano = novo()
    d.tx([("lado_criar", "notas", "n1", plano.paredes[:1])])
    f0 = d.foto()
    casos = [(L.IdInexistente, "alterar", ("notas", "nao_existe", {"a": 1})), (L.IdInexistente, "apagar", ("notas", "nao_existe")),
             (L.IdInexistente, "apagar", ("vazia", "x")), (L.IdRepetido, "criar", ("notas", "n1", {"a": 1})),
             (L.ObjetoInvalido, "criar", ("notas", "n2", [1, 2])), (L.ObjetoInvalido, "criar", ("notas", "n3", "texto")),
             (L.ObjetoInvalido, "alterar", ("notas", "n1", [1])), (L.ObjetoInvalido, "criar", ("manifest", "m", {})),
             (L.ObjetoInvalido, "criar", ("Notas", "x", {})), (L.ObjetoInvalido, "criar", ("notas", "a/b", {})),
             (L.ObjetoInvalido, "criar", ("notas", "x" * 65, {})), (L.ObjetoInvalido, "criar", ("notas", "k", {1: "chave número"}))]
    for erro, nome, args in casos:
        with pytest.raises(erro):
            with d.s.escrever() as esc, d.h.transacao(esc) as t:
                A.aplicar(plano.op("nome"), t.ifc, t.lado, d.c)
                getattr(t.lado, nome)(*args)
        A.igual(d, f0, f"lateral {nome}{args[:2]} recusado: a transação não voltou inteira")
    assert issubclass(L.IdInexistente, KeyError) and issubclass(L.IdRepetido, KeyError) and issubclass(L.ObjetoInvalido, ValueError)


def test_b3_fora_do_historico_e_transacao_nao_se_aninham(novo):
    T, _, _ = _mods()
    d, plano = novo()
    d.tx([plano.op("nome")])
    with d.s.escrever() as esc:
        with d.h.transacao(esc):
            with pytest.raises(T.TransacaoAberta):
                d.h.fora_do_historico(esc).__enter__()
        with d.h.fora_do_historico(esc):
            for fn in (lambda: d.h.transacao(esc).__enter__(), lambda: d.h.desfazer(esc), lambda: d.h.refazer(esc),
                       lambda: d.h.fora_do_historico(esc).__enter__()):
                with pytest.raises(T.TransacaoAberta):
                    fn()
    assert not d.h.quebrado and d.h.pode_desfazer
    d.tx([plano.op("nome")])
