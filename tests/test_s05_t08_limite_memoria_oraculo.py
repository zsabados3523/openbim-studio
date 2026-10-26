# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de oráculo do F0-S05-T08: limite de memória do desfazer (ADR-002 §4.6 e §4.8; requisitos M1 e M2 do T00).
Não editar este arquivo na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio,
depois da implementação (só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`).
CONTRATO (`app/openbim_app/transacao.py`, sem Qt, sem `obimcore`; nomes do ADR-002 §4.6 e §4.8):
1. `Historico(sessao, lateral, limite_bytes=256 * 1024 * 1024, codificar=None, anotar=None, avisar=None)`:
   - `limite_bytes` padrão = `256 * 1024 * 1024` (256 MiB = 268.435.456 B, ADR-002 §4.6); `limite_bytes=None` desliga o limite (nunca descarta).
   - `h.limite_bytes` pode ser lido e ajustado (`h.limite_bytes = novo`, inteiro `> 0` ou `None`); inteiro `<= 0` (ou `bool`) levanta `ValueError`.
     Ao reduzir `h.limite_bytes` fora de transação aberta, o corte dos passos excedentes do histórico ocorre na hora; `None` desliga o descarte.
   - `h.descartados` (propriedade `int`, ADR-002 §4.8): total acumulado de passos descartados do começo do histórico por limite de memória;
     volta a `0` em `h.encerrar()`.
2. Custo de um passo e regra de descarte (ADR-002 §4.6, M1 e M2):
   - Custo de um passo = tamanho em bytes UTF-8 do registro JSON do passo (operações IFC normalizadas para JSON como em `diario.codificar_ifc` —
     `inverses` como lista de pares e tuplas como listas, mesmo quando `codificar=None` — mais operações do lateral) × 12.
   - O limite `limite_bytes` vale sobre a soma dos custos de `history` mais `future`.
   - O descarte ocorre só depois que a transação inteira (incluindo `end_transaction` e `anotar`) confirmou sem erro, ou ao diminuir `h.limite_bytes`
     fora de transação. NUNCA descarta no meio de uma transação aberta, nem quando a transação falha dentro do `with`, em `codificar` ou em `anotar`.
   - Enquanto `limite_bytes is not None` e o custo total (`history + future`) passar de `limite_bytes`: remove o passo mais antigo do histórico dos
     dois lados juntos (IFC e lateral) e incrementa `descartados` em 1.
   - Um passo maior que o limite fica sozinho (§4.6): quando `future` está vazio, mantém pelo menos 1 passo em `history`
     (a transação recém-confirmada nunca é descartada por si mesma).
   - O refazer (`future`) NUNCA é cortado (M2): mesmo que `h.limite_bytes` seja reduzido abaixo do custo de `future`,
     podem sair todos os passos de `history`, mas nenhum de `future`.
3. CONTRATO NOVO (decisão do orquestrador — aviso de desfazer impossível, §4.6 e M1):
   - Parâmetro opcional `avisar=None` no construtor de `Historico`, callable `avisar(msg: str)` que recebe uma string não vazia em português.
   - Chamado SÓ quando `h.desfazer(esc)` é pedido e não é mais possível porque passos foram descartados (`h.descartados > 0` e `not h.pode_desfazer`),
     devolvendo `None`. Se `desfazer(esc)` for chamado repetidas vezes nessa condição, chama `avisar` em cada tentativa; após `h.encerrar()`,
     `descartados == 0` e não avisa.
   - NUNCA chama `avisar` durante `transacao` (descarte silencioso), nem em `desfazer` possível (`pode_desfazer` verdadeiro),
     nem em `desfazer` vazio quando `descartados == 0`, nem em `refazer`.
GUARDA: sem ifcopenshell, pula; com `OBIM_S05_OBRIGATORIO=1` todo pulo vira falha. `test_regua_*` valida só pressupostos do gerador/ambiente."""
import errno
import gc
import json
import tracemalloc

import pytest
import s05_t04_aux as A
import s05_t05_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t04_aux import SEMENTE, aplicar, igual
from test_s05_t04_transacao_oraculo import Real, _pilhas, novo  # noqa: F401  (fixture `novo`)
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local  # noqa: F401  (fixtures)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T08: limite de memória do desfazer ainda não implementado em transacao.py")


def _tam_json_diario(ifc_codificado, lado_ops):
    return len(json.dumps({"ifc": ifc_codificado, "lado": list(lado_ops)}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _achar_corte(d, teto=250_000, passo=500):
    """Deduza o custo acumulado pelo comportamento: baixa `limite_bytes` até descartar o 1º passo excedente."""
    d0 = d.h.descartados
    while d.h.descartados == d0 and teto > passo:
        teto -= passo
        d.h.limite_bytes = teto
    assert d.h.descartados > d0, "não descartou nenhum passo ao baixar limite_bytes"
    return teto


def test_regua_pressupostos_gerador_e_ambiente(novo):
    """Valida só os pressupostos do gerador (T04/T05) e do ambiente (`tracemalloc`), sem testar o limite de T08."""
    D = X.mod()
    vistos = []
    d, plano = novo(limite_bytes=None, codificar=D.codificar_ifc, anotar=lambda _, ifc, lado: vistos.append(_tam_json_diario(ifc, lado)))
    w = plano.paredes[0]
    for ops in ([("lado_criar", "notas", "n0", [w])], [("nome", w)], [("mover", w)], [("parede", "p_regua")]):
        d.tx(ops)
    _, tam_nome, tam_mover, tam_parede = vistos
    assert tam_nome < 500 < tam_mover < 4_000 < tam_parede and tam_parede > tam_nome * 20
    for _ in range(10):  # deleções do gerador (`inverses`) passam por `codificar_ifc` + JSON sem TypeError
        d.tx(plano.transacao(3))
    assert len(vistos) == 14 and X.pilhas(d) == (14, 0, True, False)
    gc.collect()
    tracemalloc.start()
    try:
        m0 = tracemalloc.get_traced_memory()[0]
        for _ in range(40):
            d.tx([("mover", w), ("nome", w), ("lado_alterar", "notas", "n0", [w])])
        gc.collect()
        m1 = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()
    assert m1 - m0 > 150_000, f"tracemalloc não mediu o acúmulo de 40 passos sem limite no ambiente: {m1 - m0} B"


@AINDA_NAO
def test_1_padrao_256mb_desligado_e_custo_por_memoria(novo):
    """M1: padrão 256 MiB, `None` desliga, ajustável; custo ~ JSON×12 deduzido pelo comportamento; passo > limite fica sozinho."""
    D = X.mod()
    d_padrao, plano = novo()
    assert d_padrao.h.limite_bytes == 256 * 1024 * 1024 == 268_435_456 and d_padrao.h.descartados == 0
    for inv in (0, -1, -100, False, True):
        with pytest.raises(ValueError):
            novo(limite_bytes=inv)
        with pytest.raises(ValueError):
            d_padrao.h.limite_bytes = inv
    # Confere pelo comportamento que o custo de 1 passo segue `tamanho_json * 12` (ADR-002 §4.6).
    tams = []
    d_off, _ = novo(limite_bytes=None, codificar=D.codificar_ifc, anotar=lambda _, ifc, lado: tams.append(_tam_json_diario(ifc, lado)))
    assert d_off.h.limite_bytes is None
    w = plano.paredes[0]
    for _ in range(4):
        d_off.tx([("mover", w)])
    c_deduzido = _achar_corte(d_off, teto=150_000, passo=500) // 4
    assert tams[-1] * 10 <= c_deduzido <= tams[-1] * 14, f"custo comportamental ({c_deduzido} B) longe de JSON×12 ({tams[-1] * 12} B)"
    # Limite de 30 KB: cabem >10 edições leves de nome (~1,5 KB cada), depois começa a descartar; 1 parede pesada (~88 KB) fica sozinha.
    d, _ = novo(limite_bytes=30_000)
    for _ in range(12):
        d.tx([("nome", w)])
    assert X.pilhas(d) == (12, 0, True, False) and d.h.descartados == 0
    for _ in range(18):
        d.tx([("nome", w)])
    n_hist, n_fut, pode_d, pode_r = X.pilhas(d)
    assert d.h.descartados >= 6 and n_hist == 30 - d.h.descartados >= 10 and (n_fut, pode_d, pode_r) == (0, True, False)
    # Um único passo maior que `limite_bytes` (criar parede ~88 KB > 30 KB) descarta os 30 anteriores e fica SOZINHO (ADR-002 §4.6).
    f_antes_parede = d.foto()
    d.tx([("parede", "p_pesada"), ("lado_criar", "notas", "np", [w])])
    assert d.h.descartados == 30 and X.pilhas(d) == (1, 0, True, False) and d.desfazer() is not None
    igual(d, f_antes_parede, "desfazer do passo único maior que o limite")
    assert X.pilhas(d) == (0, 1, False, True)
    d.h.encerrar()
    assert d.h.descartados == 0 and X.pilhas(d) == (0, 0, False, False)


@AINDA_NAO
def test_2_descarta_mais_antigo_dos_dois_lados_religa_e_desfaz_restante(novo):
    """M1 + régua T04: descarta os mais antigos dos dois lados juntos, aceita desligar/religar `limite_bytes=None` e desfaz o restante."""
    d, plano = novo(limite_bytes=None)
    w0, w1 = plano.paredes[:2]
    fotos = [d.foto()]
    passos = [
        [("mover", w0), ("lado_criar", "notas", "n1", [w0])], [("mover", w1), ("lado_criar", "notas", "n2", [w1])],
        [("mover", w0), ("lado_alterar", "notas", "n1", [w0, w1])], [("mover", w1), ("lado_criar", "cotas", "c1", [w0])],
        [("mover", w0), ("lado_alterar", "notas", "n2", [w0])], [("mover", w1), ("lado_apagar", "cotas", "c1")],
        [("mover", w0), ("lado_alterar", "notas", "n1", [w1])],
    ]
    for ops in passos[:5]:
        d.tx(ops)
        fotos.append(d.foto())
    assert X.pilhas(d) == (5, 0, True, False) and d.h.descartados == 0
    # Deduz o custo médio `c` de 1 passo pelo comportamento (corta o passo 1 ao cruzar 5*c; sobram 4) e ajusta teto para 3 passos (`3,5*c`).
    c = _achar_corte(d, teto=180_000, passo=500) // 5
    assert X.pilhas(d) == (4, 0, True, False) and d.h.descartados == 1
    d.h.limite_bytes = int(3.5 * c)
    assert X.pilhas(d) == (3, 0, True, False) and d.h.descartados == 2
    # Passo 6 derruba o passo 3; depois o passo 7 reduz o teto para 2 passos (`2,5*c`) dentro da transação e derruba 4 e 5 no `while`.
    d.tx(passos[5])
    fotos.append(d.foto())
    assert X.pilhas(d) == (3, 0, True, False) and d.h.descartados == 3
    with d.s.escrever() as esc, d.h.transacao(esc) as t:
        for op in passos[6]:
            aplicar(op, t.ifc, t.lado, d.c)
        d.h.limite_bytes = int(2.5 * c)
    fotos.append(d.foto())
    assert X.pilhas(d) == (2, 0, True, False) and d.h.descartados == 5
    # Desfaz os 2 passos restantes (7 e 6): chega exatamente a fotos[5] (depois do passo 5) e para ali.
    for idx_esperado in (6, 5):
        assert d.h.pode_desfazer and d.desfazer() is not None
        igual(d, fotos[idx_esperado], f"desfazer até foto {idx_esperado}")
    assert X.pilhas(d) == (0, 2, False, True) and d.desfazer() is None
    igual(d, fotos[5], "depois do último desfazer possível o estado fica em fotos[5]")
    # Desligar o limite (`limite_bytes = None`) após ter limite ativo para de descartar; religar volta a cortar na hora.
    d.h.limite_bytes = None
    assert d.h.limite_bytes is None and d.h.descartados == 5
    for _ in range(4):
        d.tx([("mover", w0), ("lado_alterar", "notas", "n2", [w0])])
    assert X.pilhas(d) == (4, 0, True, False) and d.h.descartados == 5
    d.h.limite_bytes = int(1.5 * c)
    assert X.pilhas(d) == (1, 0, True, False) and d.h.descartados == 8
    # Sequência com o gerador do T04 (semente fixa, inclui deleções com `inverses` e `codificar=None`): 60 transações com teto de 250 KB.
    d2, plano2 = novo(limite_bytes=250_000)
    fotos2 = [d2.foto()]
    for _ in range(60):
        d2.tx(plano2.transacao(3))
        fotos2.append(d2.foto())
        n_hist, n_fut, pode_d, pode_r = X.pilhas(d2)
        assert n_hist >= 1 and (n_fut, pode_d, pode_r) == (0, True, False) and d2.h.descartados + n_hist == len(fotos2) - 1
    k = d2.h.descartados
    assert k >= 20, f"semente {SEMENTE}: limite de 250 KB deveria descartar pelo menos 20 passos em 60 transações, descartou {k}"
    for idx in range(len(fotos2) - 2, k - 1, -1):
        assert d2.desfazer() is not None
        igual(d2, fotos2[idx], f"gerador T04: desfazer para o passo {idx}")
    assert not d2.h.pode_desfazer and d2.desfazer() is None
    igual(d2, fotos2[k], f"gerador T04: base retida no passo {k}")


@AINDA_NAO
def test_3_refazer_intacto_e_ciclo_completo_com_descarte_automatico(novo):
    """M2 + ADR-002 §4.6: limite vale sobre `history + future`, `future` nunca é cortado, e o ciclo completo transação->desfazer->refazer bate."""
    d, plano = novo(limite_bytes=None)
    w = plano.paredes[0]
    d.tx([("lado_criar", "notas", "nr", [w])])
    fotos = [d.foto()]
    for _ in range(5):
        d.tx([("mover", w), ("lado_alterar", "notas", "nr", [w])])
        fotos.append(d.foto())
    c = _achar_corte(d, teto=180_000, passo=500) // 5  # corta a criação inicial (`lado_criar`); sobram os 5 passos iguais em `history`
    assert _pilhas(d) == (5, 0, False) and d.h.descartados == 1
    # Desfaz os 2 últimos (passos 5 e 4 vão para `future`) e reduz `limite_bytes` para 3 passos (`3,5*c`): saem 1 e 2 de `history`; `future` intacto.
    assert d.desfazer() is not None and d.desfazer() is not None
    igual(d, fotos[3], "antes do corte com refazer cheio")
    assert _pilhas(d) == (3, 2, True)
    d.h.limite_bytes = int(3.5 * c)
    assert _pilhas(d) == (1, 2, True) and d.h.descartados == 3
    # Desfaz o passo 3 restante e refaz 3, 4 e 5 inteiros até fotos[5].
    assert d.desfazer() is not None
    igual(d, fotos[2], "desfez o passo 3")
    assert not d.h.pode_desfazer and _pilhas(d) == (0, 3, True)
    for idx in (3, 4, 5):
        assert d.refazer() is not None
        igual(d, fotos[idx], f"refazer até foto {idx}")
    assert not d.h.pode_refazer and d.refazer() is None
    # Mesmo se `limite_bytes` for reduzido abaixo do próprio custo de `future`, `history` esvazia mas `future` NUNCA é cortado (M2).
    assert d.desfazer() is not None and d.desfazer() is not None and _pilhas(d) == (1, 2, True)
    d.h.limite_bytes = 1_000
    assert _pilhas(d) == (0, 2, True) and d.h.descartados == 4 and not d.h.pode_desfazer
    for idx in (4, 5):
        assert d.refazer() is not None
        igual(d, fotos[idx], f"refazer preservado mesmo acima do limite: foto {idx}")
    # Ciclo completo com descarte automático pelo teto: 6 transações (teto para 3) -> desfazer até o fim (com aviso) -> refazer completo.
    avisos = []
    d2, plano2 = novo(limite_bytes=int(3.5 * c), avisar=avisos.append)
    w2 = plano2.paredes[0]
    d2.tx([("lado_criar", "notas", "nc", [w2])])
    fotos2 = [d2.foto()]
    for _ in range(6):
        d2.tx([("mover", w2), ("lado_alterar", "notas", "nc", [w2])])
        fotos2.append(d2.foto())
    assert _pilhas(d2) == (3, 0, False) and d2.h.descartados == 4 and avisos == []
    for idx in (5, 4, 3):
        assert d2.desfazer() is not None
        igual(d2, fotos2[idx], f"ciclo automático: desfazer até foto {idx}")
    assert not d2.h.pode_desfazer and _pilhas(d2) == (0, 3, True) and avisos == []
    assert d2.desfazer() is None and len(avisos) == 1
    igual(d2, fotos2[3], "ciclo automático: parada na base retida")
    for idx in (4, 5, 6):
        assert d2.refazer() is not None
        igual(d2, fotos2[idx], f"ciclo automático: refazer até foto {idx}")
    assert _pilhas(d2) == (3, 0, False) and d2.refazer() is None and len(avisos) == 1


@AINDA_NAO
def test_4_diario_intacto_e_recuperacao_completa(local, casa):
    """M2: descartar passos antigos da memória não apaga nem corrompe o diário (T05); `recuperar` reconstrói desde a base original."""
    D = X.mod()
    f, c, plano = X.preparar(casa)
    diario = D.Diario.abrir(D.lado_id_de(f, X.sha(casa)), str(casa))
    r = Real(f, c, limite_bytes=45_000, codificar=D.codificar_ifc, anotar=diario.anotar)
    try:
        for _ in range(12):
            r.tx(plano.transacao(2))
        assert r.h.descartados >= 4 and r.desfazer() is not None and r.refazer() is not None
        r.tx([plano.op("nome"), plano.op("lado_criar")])
        foto_final = r.foto()
    finally:
        diario.fechar()
        r.h.encerrar()
    cam = X.caminho_diario(local)
    regs, avisos = D.ler_diario(str(cam))
    assert avisos == [] and [reg["seq"] for reg in regs] == list(range(16))
    assert [reg["tipo"] for reg in regs] == ["base"] + ["transacao"] * 12 + ["desfazer", "refazer", "transacao"]
    foto_rec, avisos_rec, arq_rec, _ = X.recuperar(casa, cam)
    assert avisos_rec == []
    X.igual(foto_rec, foto_final, "recuperar do diário depois de descartar passos da memória")
    X.R.ifcopenshell.file.registry.pop(int(arq_rec.this), None)


@AINDA_NAO
def test_5_memoria_estavel_tracemalloc_sequencia_longa(novo):
    """Critério 5 (T00 / ADR-002 §4.6): memória medida com `tracemalloc` (amostras 20, 60, 120, 200) fica estável em razão do custo real."""
    d, plano = novo(limite_bytes=None)
    w = plano.paredes[0]
    d.tx([("pset_criar", w, "ps_mem"), ("lado_criar", "notas", "n_mem", [w])])
    for _ in range(4):
        d.tx([("mover", w), ("nome", w), ("lado_alterar", "notas", "n_mem", [w])])
    gc.collect()
    tracemalloc.start()
    try:
        m0 = tracemalloc.get_traced_memory()[0]
        for _ in range(10):
            d.tx([("mover", w), ("nome", w), ("lado_alterar", "notas", "n_mem", [w])])
        gc.collect()
        custo_real_1 = (tracemalloc.get_traced_memory()[0] - m0) / 10.0
        assert custo_real_1 > 5_000, f"custo real de 1 passo no tracemalloc abaixo do esperado: {custo_real_1} B"
        d.h.limite_bytes = 120_000  # retém ~4 passos; roda 200 passos conferindo todas as amostras (20, 60, 120, 200)
        medidas = {}
        for i in range(1, 201):
            d.tx([("mover", w), ("nome", w), ("lado_alterar", "notas", "n_mem", [w])])
            if i in (20, 60, 120, 200):
                gc.collect()
                medidas[i] = tracemalloc.get_traced_memory()[0] - m0
    finally:
        tracemalloc.stop()
    n_hist, n_fut, pode_d, pode_r = X.pilhas(d)
    assert d.h.descartados >= 200 and 1 <= n_hist <= 8 and (n_fut, pode_d, pode_r) == (0, True, False)
    for amostra in (60, 120, 200):
        derivacao = medidas[amostra] - medidas[20]
        assert derivacao < 3.5 * custo_real_1, f"vazamento entre passo 20 e {amostra} ({derivacao:.0f} B > 3,5 passos de {custo_real_1:.0f} B): {medidas}"
        assert medidas[amostra] < 9.0 * custo_real_1, f"memória retida no passo {amostra} acima de 9 passos reais ({custo_real_1:.0f} B): {medidas}"


@AINDA_NAO
def test_6_aviso_so_no_desfazer_impossivel_e_repetido(novo):
    """M1 + contrato novo: descarte é silencioso; `avisar` só dispara em `desfazer` com histórico vazio e `descartados > 0` (e zera em `encerrar`)."""
    avisos = []
    d, plano = novo(limite_bytes=None, avisar=avisos.append)
    w = plano.paredes[0]
    # 1. Histórico vazio sem descarte (`descartados == 0`): `desfazer` devolve None e NÃO avisa.
    assert d.desfazer() is None and d.refazer() is None and avisos == []
    d.tx([("mover", w), ("lado_criar", "notas", "n1", [w])])
    assert d.desfazer() is not None and d.desfazer() is None and d.refazer() is not None and avisos == []
    # 2. Adiciona o passo 2 e deduz `c1 + c2` pelo comportamento; fixa o limite em 75% de `c1 + c2` (entre `max(c2, c3)` e `c2 + c3`).
    d.tx([("mover", w), ("lado_alterar", "notas", "n1", [w])])
    soma_1_2 = _achar_corte(d, teto=80_000, passo=500)
    d.h.limite_bytes = int(soma_1_2 * 0.75)
    assert d.h.descartados == 1 and X.pilhas(d) == (1, 0, True, False) and avisos == []
    # Passo 3 cabe sozinho no limite (`c3 <= limite_bytes`), mas `c2 + c3 > limite_bytes`: descarta o passo 2 em silêncio (`avisos == []`).
    d.tx([("mover", w), ("lado_alterar", "notas", "n1", [w])])
    assert d.h.descartados == 2 and X.pilhas(d) == (1, 0, True, False) and avisos == []
    # 3. Desfazer do passo 3 (ainda possível) e refazer/desfazer dele: NÃO avisa.
    assert d.desfazer() is not None and d.refazer() is not None and d.desfazer() is not None and avisos == []
    # 4. Com `not pode_desfazer` e `descartados > 0`, cada `desfazer()` impossível devolve None e chama `avisar(msg)` em pt-BR.
    assert not d.h.pode_desfazer and d.h.descartados == 2
    assert d.desfazer() is None and len(avisos) == 1 and isinstance(avisos[0], str) and len(avisos[0].strip()) >= 10
    assert d.desfazer() is None and len(avisos) == 2
    assert d.refazer() is not None and d.refazer() is None and len(avisos) == 2
    d.h.encerrar()
    assert d.h.descartados == 0 and not d.h.pode_desfazer and not d.h.pode_refazer


@AINDA_NAO
def test_7_descarte_nunca_no_meio_nem_em_transacao_abortada(novo):
    """ADR-002 §4.6: nunca descarta no meio de uma transação aberta, nem quando a transação aborta ou falha em `codificar`/`anotar`."""
    falhar_cod, falhar_an = [False], [False]

    def cod(ops):
        if falhar_cod[0]:
            raise ValueError("falha simulada no codificar")
        return X.mod().codificar_ifc(ops)

    def anotar(*a):
        if falhar_an[0]:
            raise OSError(errno.ENOSPC, "disco cheio simulado no anotar")

    d, plano = novo(limite_bytes=None, codificar=cod, anotar=anotar)
    w = plano.paredes[0]
    f0 = d.foto()
    d.tx([("mover", w), ("lado_criar", "notas", "n1", [w])])
    f1 = d.foto()
    d.tx([("mover", w), ("lado_alterar", "notas", "n1", [w])])
    f2 = d.foto()
    lim_dois = 60_000  # comporta os 2 passos atuais (~47 KB), mas qualquer passo adicional de `mover` (~24 KB) ou `parede` (~88 KB) estoura
    d.h.limite_bytes = lim_dois
    assert d.h.descartados == 0 and X.pilhas(d) == (2, 0, True, False)

    class Abortar(Exception):
        pass

    with pytest.raises(Abortar):
        with d.s.escrever() as esc, d.h.transacao(esc) as t:
            aplicar(("parede", "p_meio"), t.ifc, t.lado, d.c)
            t.lado.alterar("notas", "n1", {"texto": "x" * 5000})
            d.h.limite_bytes = 1_000
            assert d.h.descartados == 0 and len(t.ifc.history) == 2 and d.h.pode_desfazer, "descartou no meio da transação aberta"
            d.h.limite_bytes = lim_dois
            raise Abortar()
    assert d.h.descartados == 0 and X.pilhas(d) == (2, 0, True, False)
    igual(d, f2, "depois de abortar no meio")
    for flag, erro in ((falhar_cod, ValueError), (falhar_an, OSError)):
        flag[0] = True
        with pytest.raises(erro):
            d.tx([("parede", "p_falha"), ("lado_alterar", "notas", "n1", [w])])
        flag[0] = False
        assert X.pilhas(d) == (2, 0, True, False) and d.h.descartados == 0
        igual(d, f2, f"depois de falha em {erro.__name__}")
    assert d.desfazer() is not None and not A.R.diferencas(d.foto(), f1)
    assert d.desfazer() is not None and not A.R.diferencas(d.foto(), f0)
    d.refazer(), d.refazer()
    with d.s.escrever() as esc, d.h.transacao(esc) as t:
        aplicar(("nome", w), t.ifc, t.lado, d.c)
        d.h.limite_bytes = 1_000
        assert d.h.descartados == 0 and len(t.ifc.history) == 2 and d.h.pode_desfazer, "descartou antes do fim da transação"
    assert d.h.descartados == 2 and X.pilhas(d) == (1, 0, True, False)
