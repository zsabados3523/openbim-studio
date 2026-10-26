# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de oráculo do F0-S05-T08: limite de memória do desfazer (ADR-002 §4.6 e §4.8; requisitos M1 e M2 do T00).
Não editar este arquivo na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio,
depois da implementação (só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`).
CONTRATO (`app/openbim_app/transacao.py`, sem Qt, sem `obimcore`; nomes do ADR-002 §4.6 e §4.8; [P] = escolha do teste onde o ADR não fixa nome):
1. [P] Constantes de módulo: `LIMITE_PADRAO_BYTES = 256 * 1024 * 1024` (268.435.456 B, ADR-002 §4.6) e `FATOR_CUSTO = 12`.
2. [P] `custo_passo(ifc_ops, lado_ops)` -> `int`: custo em bytes de um passo =
   `len(json.dumps({"ifc": ifc_ops, "lado": list(lado_ops)}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) * FATOR_CUSTO`.
3. `Historico(sessao, lateral, limite_bytes=LIMITE_PADRAO_BYTES, codificar=None, anotar=None, avisar=None)`:
   - `limite_bytes` padrão = `LIMITE_PADRAO_BYTES` (256 MiB); `limite_bytes=None` desliga o limite (`h.limite_bytes is None`, nunca descarta).
   - `h.limite_bytes` pode ser lido e ajustado (`h.limite_bytes = novo`); inteiro `<= 0` (ou `bool`) levanta `ValueError`.
     Ao reduzir `h.limite_bytes` fora de transação aberta, o corte dos passos excedentes do histórico ocorre na hora.
   - [P] `h.bytes_historico` (propriedade `int`): soma dos custos (`custo_passo`) dos passos atualmente em `history` (`_lh`) mais `future` (`_lf`);
     vai a `0` em `h.encerrar()`.
   - `h.descartados` (propriedade `int`, §4.8): total acumulado de passos descartados do começo do histórico por limite de memória.
4. Regra de descarte (ADR-002 §4.6, M1 e M2):
   - Ocorre só depois que a transação inteira (incluindo `end_transaction` e `anotar`) confirmou sem erro, ou ao diminuir `h.limite_bytes`
     fora de transação. NUNCA descarta no meio de uma transação aberta, nem quando a transação falha dentro do `with`, em `codificar` ou em `anotar`.
   - Enquanto `limite_bytes is not None` e `bytes_historico > limite_bytes`: remove o passo mais antigo dos dois lados juntos
     (`arquivo.history.pop(0)` e `_lh.pop(0)`) e incrementa `descartados` em 1.
   - Um passo maior que o limite fica sozinho (§4.6): quando `future` está vazio (`not _lf`), mantém pelo menos 1 passo em `_lh`
     (a transação recém-confirmada nunca é descartada por si mesma).
   - O refazer (`arquivo.future` e `_lf`) NUNCA é cortado (M2): mesmo que `h.limite_bytes` seja reduzido abaixo do custo de `future`,
     podem sair todos os passos de `history`, mas nenhum de `future`.
5. Aviso só no desfazer impossível (§4.6, M1) [P: parâmetro `avisar`]:
   - Quando `h.desfazer(esc)` é chamado com `not h.pode_desfazer` E `h.descartados > 0`, devolve `None` e, se `avisar` foi dado,
     chama `avisar(msg)` uma vez com `msg` (`str` não vazia em pt-BR).
   - NUNCA chama `avisar` durante `transacao` (descarte silencioso), nem em `desfazer` possível (`pode_desfazer` verdadeiro),
     nem em `desfazer` vazio quando `descartados == 0`, nem em `refazer`.
GUARDA: sem ifcopenshell, pula; com `OBIM_S05_OBRIGATORIO=1` todo pulo vira falha. `test_regua_*` valida a régua e vale já (sem `@AINDA_NAO`)."""
import errno
import gc
import json
import tracemalloc

import pytest
import s05_t04_aux as A
import s05_t05_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t04_aux import SEMENTE, aplicar, igual
from test_s05_t04_transacao_oraculo import Real, _mods, _pilhas, novo  # noqa: F401  (fixture `novo`)
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local  # noqa: F401  (fixtures)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T08: limite de memória do desfazer ainda não implementado em transacao.py")


def _custo_esperado(ifc_ops, lado_ops):
    raw = json.dumps({"ifc": ifc_ops, "lado": list(lado_ops)}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return len(raw) * 12


def _passo_ultimo(d):
    with d.ler() as f:
        return _custo_esperado(f.history[-1].operations, d.h._lh[-1])


def test_regua_custo_e_tracemalloc_sem_limite(novo):
    """Sem limite, os passos acumulam em `history` e `_lh`, o custo varia por tipo de operação e o `tracemalloc` mede o crescimento."""
    d, plano = novo(limite_bytes=None)
    w = plano.paredes[0]
    d.tx([("lado_criar", "notas", "n0", [w])])
    d.tx([("nome", w)])
    c_nome = _passo_ultimo(d)
    d.tx([("parede", "p_regua")])
    c_parede = _passo_ultimo(d)
    assert c_nome < 5_000 and c_parede > 50_000 and c_parede > c_nome * 20
    gc.collect()
    tracemalloc.start()
    try:
        m0 = tracemalloc.get_traced_memory()[0]
        for i in range(40):
            d.tx([("mover", w), ("nome", w), ("lado_alterar", "notas", "n0", [w])])
        gc.collect()
        m1 = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()
    assert m1 - m0 > 200_000, f"tracemalloc não mediu o crescimento do histórico sem limite: {m1 - m0} B"


@AINDA_NAO
def test_1_padrao_256mb_desligado_e_custo_por_memoria(novo):
    """M1: padrão 256 MiB, `None` desliga, ajustável; limite é por memória (muitos passos leves cabem, 1 pesado estoura) e passo > limite fica sozinho."""
    T, _, _ = _mods()
    assert T.LIMITE_PADRAO_BYTES == 256 * 1024 * 1024 == 268_435_456 and T.FATOR_CUSTO == 12
    d_padrao, plano = novo()
    assert d_padrao.h.limite_bytes == T.LIMITE_PADRAO_BYTES and d_padrao.h.bytes_historico == 0 and d_padrao.h.descartados == 0
    d_off, _ = novo(limite_bytes=None)
    assert d_off.h.limite_bytes is None
    for inv in (0, -1, -100, False, True):
        with pytest.raises(ValueError):
            novo(limite_bytes=inv)
        with pytest.raises(ValueError):
            d_padrao.h.limite_bytes = inv

    w = plano.paredes[0]
    d, _ = novo(limite_bytes=30_000)  # ~30 KB: cabem ~20 edições de nome (~1,3 KB cada), mas 1 parede (~115 KB) passa do limite
    for _ in range(15):
        d.tx([("nome", w)])
    with d.ler() as f:
        assert len(f.history) == len(d.h._lh) == 15 and d.h.descartados == 0
    assert 10_000 <= d.h.bytes_historico <= 30_000

    # Um único passo maior que `limite_bytes` (criar parede ~115 KB > 30 KB) descarta os 15 anteriores e fica SOZINHO (ADR-002 §4.6).
    f_antes_parede = d.foto()
    d.tx([("parede", "p_pesada"), ("lado_criar", "notas", "np", [w])])
    with d.ler() as f:
        c_pesada = T.custo_passo(f.history[-1].operations, d.h._lh[-1])
        assert c_pesada == _custo_esperado(f.history[-1].operations, d.h._lh[-1]) > 30_000
        assert len(f.history) == len(d.h._lh) == 1
    assert d.h.descartados == 15 and d.h.bytes_historico == c_pesada and d.h.pode_desfazer
    assert d.desfazer() is not None
    igual(d, f_antes_parede, "desfazer do passo único maior que o limite")
    assert not d.h.pode_desfazer and d.h.pode_refazer
    d.h.encerrar()
    assert d.h.bytes_historico == 0


@AINDA_NAO
def test_2_descarta_mais_antigo_dos_dois_lados_e_desfaz_restante(novo):
    """M1 + régua T04: ao passar do limite saem os mais antigos dos dois lados juntos (IFC e lateral) e os restantes desfazem igual."""
    T, _, _ = _mods()
    d, plano = novo(limite_bytes=None)
    w0, w1 = plano.paredes[:2]
    fotos = [d.foto()]
    custos = []
    # 6 passos mistos (IFC + lateral) com tamanhos conhecidos
    passos = [
        [("nome", w0), ("lado_criar", "notas", "n1", [w0])],
        [("mover", w0), ("lado_criar", "notas", "n2", [w1])],
        [("pset_criar", w1, "ps1"), ("lado_alterar", "notas", "n1", [w0, w1])],
        [("mover", w1), ("lado_criar", "cotas", "c1", [w0])],
        [("nome", w1), ("lado_alterar", "notas", "n2", [w0])],
        [("mover", w0), ("lado_apagar", "cotas", "c1")],
    ]
    for ops in passos[:4]:
        d.tx(ops)
        custos.append(_passo_ultimo(d))
        fotos.append(d.foto())
    assert d.h.bytes_historico == sum(custos) and d.h.descartados == 0

    # Ajusta o limite para caber exatamente os passos 2, 3 e 4 (índices 1, 2, 3): o passo 1 (índice 0) sai na hora dos dois lados.
    d.h.limite_bytes = sum(custos[1:4])
    with d.ler() as f:
        assert len(f.history) == len(d.h._lh) == 3
    assert d.h.descartados == 1 and d.h.bytes_historico == sum(custos[1:4])

    # Passo 5 entra e derruba o passo 2; depois o passo 6 (`mover` ~22 KB) com limite para (passo 5 + passo 6) derruba os passos 3 e 4 de uma vez (`while`).
    d.tx(passos[4])
    custos.append(_passo_ultimo(d))
    fotos.append(d.foto())
    assert d.h.descartados == 2 and d.h.bytes_historico == sum(custos[2:5]) <= d.h.limite_bytes

    d.h.limite_bytes = custos[2] + custos[3] + custos[4]  # ainda cabem os 3 (passos 3, 4 e 5)
    assert d.h.descartados == 2
    # Agora reduz o teto na própria transação 6: ao fechar, `custos[4] + custos[5]` cabe, mas `custos[3] + custos[4] + custos[5]` não (derruba 2 passos no `while`).
    with d.s.escrever() as esc, d.h.transacao(esc) as t:
        for op in passos[5]:
            aplicar(op, t.ifc, t.lado, d.c)
        d.h.limite_bytes = custos[4] + custos[1] + 2_000
    custos.append(_passo_ultimo(d))
    fotos.append(d.foto())
    with d.ler() as f:
        assert len(f.history) == len(d.h._lh) == 2
    assert d.h.descartados == 4 and d.h.bytes_historico == sum(custos[4:6]) <= d.h.limite_bytes

    # Desfaz os 2 passos restantes (6 e 5): chega exatamente a fotos[4] (depois do passo 4) e para ali.
    for idx_esperado in (5, 4):
        assert d.h.pode_desfazer
        assert d.desfazer() is not None
        igual(d, fotos[idx_esperado], f"desfazer até foto {idx_esperado}")
    assert not d.h.pode_desfazer and d.desfazer() is None
    igual(d, fotos[4], "depois do último desfazer possível o estado fica em fotos[4]")

    # Sequência com o gerador do T04 (semente fixa): 60 transações com limite de ~250 KB, desfaz tudo que sobrou e confere cada ponto.
    d2, plano2 = novo(limite_bytes=250_000)
    fotos2 = [d2.foto()]
    for _ in range(60):
        d2.tx(plano2.transacao(3))
        fotos2.append(d2.foto())
        with d2.ler() as f:
            assert len(f.history) == len(d2.h._lh) >= 1
        assert d2.h.descartados + len(d2.h._lh) == len(fotos2) - 1
    k = d2.h.descartados
    assert k >= 20, f"semente {SEMENTE}: limite de 250 KB deveria descartar pelo menos 20 passos em 60 transações, descartou {k}"
    for idx in range(len(fotos2) - 2, k - 1, -1):
        assert d2.desfazer() is not None
        igual(d2, fotos2[idx], f"gerador T04: desfazer para o passo {idx}")
    assert not d2.h.pode_desfazer and d2.desfazer() is None
    igual(d2, fotos2[k], f"gerador T04: base retida no passo {k}")


@AINDA_NAO
def test_3_refazer_intacto_e_soma_historico_mais_refazer(novo):
    """M2 + ADR-002 §4.6: limite vale sobre `history + future`, mas descartar passos antigos NUNCA corta `future` (refazer intacto)."""
    d, plano = novo(limite_bytes=None)
    w = plano.paredes[0]
    fotos = [d.foto()]
    custos = []
    for i in range(5):
        d.tx([("mover", w), ("lado_criar" if i == 0 else "lado_alterar", "notas", "nr", [w])])
        custos.append(_passo_ultimo(d))
        fotos.append(d.foto())

    # Desfaz os 2 últimos (passos 5 e 4 vão para `future`; passos 1, 2 e 3 ficam em `history`).
    assert d.desfazer() is not None and d.desfazer() is not None
    igual(d, fotos[3], "antes do corte com refazer cheio")
    assert _pilhas(d) == (3, 2, True) and d.h.bytes_historico == sum(custos)

    # Reduz `limite_bytes` para caber só 1 passo de `history` mais os 2 de `future`: saem os passos 1 e 2 de `history`; `future` intacto.
    d.h.limite_bytes = custos[2] + custos[3] + custos[4]
    assert _pilhas(d) == (1, 2, True) and d.h.descartados == 2 and d.h.bytes_historico == sum(custos[2:])

    # Desfaz o passo 3 restante e refaz 3, 4 e 5 inteiros até fotos[5].
    assert d.desfazer() is not None
    igual(d, fotos[2], "desfez o passo 3")
    assert not d.h.pode_desfazer and _pilhas(d) == (0, 3, True)
    for idx in (3, 4, 5):
        assert d.refazer() is not None
        igual(d, fotos[idx], f"refazer até foto {idx}")
    assert not d.h.pode_refazer and d.refazer() is None

    # Mesmo se `limite_bytes` for reduzido abaixo do próprio custo de `future`, `history` esvazia mas `future` NUNCA é cortado (M2).
    assert d.desfazer() is not None and d.desfazer() is not None
    assert _pilhas(d) == (1, 2, True)
    d.h.limite_bytes = 1_000  # menor que um único passo de `future`
    assert _pilhas(d) == (0, 2, True) and d.h.descartados == 3 and not d.h.pode_desfazer
    for idx in (4, 5):
        assert d.refazer() is not None
        igual(d, fotos[idx], f"refazer preservado mesmo acima do limite: foto {idx}")


@AINDA_NAO
def test_4_diario_intacto_e_recuperacao_completa(local, casa):
    """M2: descartar passos antigos da memória não apaga nem corrompe o diário (T05); `recuperar` reconstrói desde a base original."""
    D = X.mod()
    f, c, plano = X.preparar(casa)
    diario = D.Diario.abrir(D.lado_id_de(f, X.sha(casa)), str(casa))
    r = Real(f, c, limite_bytes=45_000, codificar=D.codificar_ifc, anotar=diario.anotar)
    try:
        n_acoes = 0
        for _ in range(12):
            r.tx(plano.transacao(2))
            n_acoes += 1
        assert r.h.descartados >= 4, f"esperava descartes no histórico em memória, descartados={r.h.descartados}"
        assert r.desfazer() is not None
        assert r.refazer() is not None
        r.tx([plano.op("nome"), plano.op("lado_criar")])
        n_acoes += 3
        foto_final = r.foto()
    finally:
        diario.fechar()
        r.h.encerrar()

    cam = X.caminho_diario(local)
    regs, avisos = D.ler_diario(str(cam))
    assert avisos == [] and len(regs) == 1 + n_acoes
    assert [reg["seq"] for reg in regs] == list(range(len(regs)))
    assert [reg["tipo"] for reg in regs] == ["base"] + ["transacao"] * 12 + ["desfazer", "refazer", "transacao"]

    foto_rec, avisos_rec, arq_rec, _ = X.recuperar(casa, cam)
    assert avisos_rec == []
    X.igual(foto_rec, foto_final, "recuperar do diário depois de descartar passos da memória")
    X.R.ifcopenshell.file.registry.pop(int(arq_rec.this), None)


@AINDA_NAO
def test_5_memoria_estavel_tracemalloc_sequencia_longa(novo):
    """Critério 5 (T00 / ADR-002 §4.6): memória MEDIDA com `tracemalloc` fica estável numa sequência longa com limite pequeno."""
    d, plano = novo(limite_bytes=120_000)  # ~120 KB: comporta ~4 a 5 passos de mover+nome+lateral (~25 KB cada)
    w = plano.paredes[0]
    d.tx([("pset_criar", w, "ps_mem"), ("lado_criar", "notas", "n_mem", [w])])
    gc.collect()
    tracemalloc.start()
    try:
        m_base = tracemalloc.get_traced_memory()[0]
        medidas = {}
        for i in range(1, 201):
            d.tx([("mover", w), ("nome", w), ("lado_alterar", "notas", "n_mem", [w])])
            assert d.h.bytes_historico <= d.h.limite_bytes
            if i in (20, 60, 120, 200):
                gc.collect()
                medidas[i] = tracemalloc.get_traced_memory()[0] - m_base
    finally:
        tracemalloc.stop()
    # Sem descarte, 180 passos extras (do 20 ao 200) acumulariam > 900 KB no tracemalloc; com limite de 120 KB, a variação fica < 120 KB.
    crescimento_20_a_200 = medidas[200] - medidas[20]
    assert d.h.descartados >= 180 and len(d.h._lh) <= 8
    assert crescimento_20_a_200 < 120_000, f"memória no tracemalloc cresceu entre o passo 20 e o 200: {medidas}"
    assert medidas[200] < 250_000, f"memória retida acima do esperado para limite de 120 KB: {medidas}"


@AINDA_NAO
def test_6_aviso_so_no_desfazer_impossivel(novo):
    """M1 + ADR-002 §4.6: descarte é silencioso; `avisar` só é chamado quando `desfazer` é pedido com histórico vazio e `descartados > 0`."""
    avisos = []
    d, plano = novo(limite_bytes=None, avisar=avisos.append)
    w = plano.paredes[0]

    # 1. Histórico vazio sem descarte (`descartados == 0`): `desfazer` devolve None e NÃO avisa.
    assert d.desfazer() is None and d.refazer() is None and avisos == []
    d.tx([("nome", w), ("lado_criar", "notas", "n1", [w])])
    c1 = _passo_ultimo(d)
    assert d.desfazer() is not None and avisos == []
    assert d.desfazer() is None and avisos == []  # desfez tudo sem ter descartado nada: não avisa
    assert d.refazer() is not None and avisos == []

    # 2. Passa do limite e descarta o passo 1: descarte na transação é silencioso (`avisos == []`).
    d.h.limite_bytes = c1 + 100
    d.tx([("nome", w), ("lado_alterar", "notas", "n1", [w])])
    assert d.h.descartados == 1 and len(d.h._lh) == 1 and avisos == []

    # 3. Desfazer do passo 2 (ainda possível) e refazer/desfazer dele: NÃO avisa.
    assert d.desfazer() is not None and avisos == []
    assert d.refazer() is not None and avisos == []
    assert d.desfazer() is not None and avisos == []

    # 4. Agora `not pode_desfazer` e `descartados == 1`: pedir mais um `desfazer` devolve None E emite o aviso em pt-BR.
    assert not d.h.pode_desfazer and d.h.descartados == 1
    assert d.desfazer() is None
    assert len(avisos) == 1 and isinstance(avisos[0], str) and len(avisos[0].strip()) >= 10
    # `refazer` (possível ou impossível) nunca chama `avisar`.
    assert d.refazer() is not None and d.refazer() is None and len(avisos) == 1


@AINDA_NAO
def test_7_descarte_nunca_no_meio_nem_em_transacao_abortada(novo):
    """ADR-002 §4.6: nunca descarta no meio de uma transação aberta, nem quando a transação aborta ou falha em `codificar`/`anotar`."""
    falhar_cod, falhar_an = [False], [False]

    def cod(ops):
        if falhar_cod[0]:
            raise ValueError("falha simulada no codificar")
        return [dict(o) for o in ops]

    def anotar(*a):
        if falhar_an[0]:
            raise OSError(errno.ENOSPC, "disco cheio simulado no anotar")

    d, plano = novo(limite_bytes=None, codificar=cod, anotar=anotar)
    w = plano.paredes[0]
    f0 = d.foto()
    d.tx([("nome", w), ("lado_criar", "notas", "n1", [w])])
    f1 = d.foto()
    d.tx([("mover", w), ("lado_alterar", "notas", "n1", [w])])
    f2 = d.foto()
    # 1. No meio da transação (depois de criar parede pesada e até reduzindo `limite_bytes`, antes de sair do `with`), NADA é descartado.
    lim_dois = d.h.bytes_historico
    d.h.limite_bytes = lim_dois  # exato para os 2 passos atuais; qualquer passo novo estoura o limite
    assert d.h.descartados == 0 and len(d.h._lh) == 2

    class Abortar(Exception):
        pass

    with pytest.raises(Abortar):
        with d.s.escrever() as esc, d.h.transacao(esc) as t:
            aplicar(("parede", "p_meio"), t.ifc, t.lado, d.c)
            t.lado.alterar("notas", "n1", {"texto": "x" * 5000})
            d.h.limite_bytes = 1_000
            assert d.h.descartados == 0 and len(t.ifc.history) == 2 and len(d.h._lh) == 2, "descartou no meio da transação aberta"
            d.h.limite_bytes = lim_dois
            raise Abortar()
    assert d.h.descartados == 0 and len(d.h._lh) == 2
    igual(d, f2, "depois de abortar no meio")

    # 2. Falha em `codificar` e falha em `anotar` (depois do `end_transaction`): os 2 passos antigos continuam intactos (`descartados == 0`).
    for flag, erro in ((falhar_cod, ValueError), (falhar_an, OSError)):
        flag[0] = True
        with pytest.raises(erro):
            d.tx([("parede", "p_falha"), ("lado_alterar", "notas", "n1", [w])])
        flag[0] = False
        with d.ler() as f:
            assert len(f.history) == len(d.h._lh) == 2 and d.h.descartados == 0 and d.h.bytes_historico == lim_dois
        igual(d, f2, f"depois de falha em {erro.__name__}")

    # Os 2 passos antigos ainda desfazem até f1 e f0 sem perda.
    assert d.desfazer() is not None and not A.R.diferencas(d.foto(), f1)
    assert d.desfazer() is not None and not A.R.diferencas(d.foto(), f0)

    # 3. Reduzir `limite_bytes` dentro de uma transação válida só descarta ao fechar o `with`, nunca antes.
    d.refazer(), d.refazer()
    with d.s.escrever() as esc, d.h.transacao(esc) as t:
        aplicar(("nome", w), t.ifc, t.lado, d.c)
        d.h.limite_bytes = 1_000
        assert d.h.descartados == 0 and len(t.ifc.history) == 2 and len(d.h._lh) == 2, "descartou antes do fim da transação"
    assert d.h.descartados == 2 and len(d.h._lh) == 1

