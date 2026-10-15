# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S04-T16 (abertura: orçamento de peças lentas, modo isolado mais barato) e da S03-T08-G. Sem tela, sem Qt.
Especificação: docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_9/resultado.md (T16), arquivo/lotes-1-a-28/LOTE_OPUS_8/resultado.md §2.3 itens 3 e 4, arquivo/lotes-1-a-28/LOTE_OPUS_7/resultado.md §1.4 (opção ii), arquivo/lotes-1-a-28/LOTE_OPUS_20/resultado.md (T16b: ordem do iterador, orçamento no laço de confirmações, cópias fora da contagem). Casos P13/P14/P18
ficam em test_viewport_processo.py (rodar junto: devem continuar verdes); aqui há também as condições do P14 com o modo isolado novo.
GUARDA: pula enquanto `CarregadorMalhas.__init__` não aceitar `max_pecas_condenadas` e `max_espera_s`; FALHA com OBIM_S04_T16_OBRIGATORIO=1.
CONTRATO PARA O IMPLEMENTADOR (nomes exatos; o oráculo não depende de mais nada):
 * CarregadorMalhas(..., max_pecas_condenadas=20, max_espera_s=120.0). Orçamento estourado = (número de peças ACUSADAS e confirmadas
   por lentidão ou queda; as cópias da mesma peça-base NÃO contam, uma peça "membro" com 285 cópias conta 1) > N  OU  (soma, em
   segundos, de TODAS as esperas por peça lenta: a do bloco no modo normal, a do modo isolado e a da confirmação) > T.
   Quando é conferido (LOTE_OPUS_20, bloqueante 2): (1) quando um bloco estoura `limite_peca_s` no modo normal; (2) em qualquer
   falha (espera estourada ou queda do conversor) que aconteça DEPOIS da primeira acusada confirmada da carga, mesmo dentro do
   isolamento/confirmação das pendentes (é o que protege o laço de confirmações: nunca "erro" por reinício). A 1ª acusada de uma
   carga nunca é cortada por isso, e uma acusada que acabou de ser confirmada não leva as vizinhas já pendentes do mesmo bloco só
   porque o orçamento passou (os casos a1/a2 dependem disto). Estourado: TODAS as peças ainda pendentes daquele bloco (ou das
   pendentes em isolamento), inclusive a que travou, viram caixa de uma vez; os blocos seguintes seguem no modo normal. Sem o
   orçamento estourado, nada muda (modo isolado). Peça sem geometria dentro de um bloco cortado vira CAIXA (não `sem_malha`),
   comportamento atual registrado em d5; fora de um bloco cortado ela continua indo para `sem_malha`.
 * Ordem do iterador (LOTE_OPUS_20, bloqueante 1 e 3): o iterador do IfcOpenShell entrega as peças na ordem das REPRESENTAÇÕES, não na
   dos ids (threads=1: a das representações; threads>1: embaralhada). Nada no carregador pode supor ids crescentes na entrega. Casos
   d1 a d3 montam o arquivo assim (`_gerar_layout(..., ordem=)`): `lentas_antes` (representações das lentas criadas primeiro, como
   no s25.ifc: lenta com id MAIOR entregue na posição 0) e `inversa` (entrega do maior id para o menor). Exigências: estado
   "concluido" (nunca "erro" por mais de 20 reinícios), todas e só as lentas viram caixa quando o orçamento não estoura, no máximo
   `_k_filhos` = 4 + ceil(log2(n)) por lenta processos de CONVERSÃO abertos (os da caixa não contam; contados em
   `multiprocessing.context.SpawnProcess.start` com `target.__name__ == "entrada"`), tempo total < 3 x `_main_estimado` (d2, com 3 lentas: 5 x) (3 x a
   referência sem lentidão medida na mesma execução + n_lentas x (limite + 1 s), calibrado no `main`: 3,1 s para 1 lenta em 26
   peças e 6,1 s para 3 lentas em 23). Duas implementações provadas contra estes casos (variantes descartáveis, nunca commitadas): (i) dividir ao meio as
   pendentes não anunciadas e confirmar cada metade com um filho isolado (8 filhos no s25.ifc, ~4,8 s); (ii) um filho em modo "uma
   peça por iterador" só para as pendentes não anunciadas, depois que a confirmação da primeira candidata não reproduz (5 filhos).
 * Resumo (`ResumoCarga.mensagens`): uma linha com o número EXATO de peças mostradas como caixa de uma vez (as pendentes dos blocos
   cortados, inclusive a que travou), com as palavras "peça" e "caixa", sem jargão (nada de isolado, iterador, bloco, thread, timeout,
   lote, budget). O número aparece sozinho (não colado a outro dígito, ponto ou vírgula). Toda peça cortada entra em `simplificadas`.
 * processo_malhas.entrada(tx, params) continua sendo o ponto de entrada do filho (tx só precisa de `.send((tipo, dados))`); params
   com as chaves de hoje (caminho, threads, tamanho_bloco, excluir, biblioteca, max_bytes_lote, ids, isolado, desl). Com
   isolado=True o filho cria UM `ifcopenshell.geom.iterator` para todos os ids pedidos (a confirmação da peça acusada é outro filho,
   com ids=[acusada], e só acontece quando o pai vê a espera estourar) e entrega as peças como hoje (`lote`, `sem_malha`, `fim`).
 * O oráculo conta iteradores trocando o atributo `ifcopenshell.geom.iterator`: o filho tem de chamá-lo como
   `ifcopenshell.geom.iterator(...)` na hora da chamada (nada de `from ifcopenshell.geom import iterator` no topo).
 * Custo (b): roda `entrada` neste processo e divide `fim["tempos"]["geometria_s"]` pelo número de ids; a referência é o modo
   normal (isolado=False) com threads=1 nos mesmos ids; razão = mediana do isolado / mediana do normal (5 rodadas alternadas, 2 modelos).
 * Caixa substituta = peça cujos vértices são todos laranja (255, 140, 0, 255); o conjunto dessas peças tem de ser igual a `simplificadas`.
 * Gancho novo no filho (S03-T08-G, item 2): OBIM_TESTE_MATAR_NO_FIM=1 faz um filho em modo isolado sair com código 3 depois do
   último `lote` e antes do `fim`. Pai: sem pendentes depois de um filho que cai, segue (não termina em "erro").
 * S03-T08-G item 1: peça cuja posição (ObjectPlacement) não pode ser lida pela caixa vai para `sem_malha` com motivo (nunca caixa
   em posição zero). Régua do custo (b): CI virtual = mediana das razões dos casos <= 2,0 e nenhuma >= 4,0; OBIM_S04_ESTRITO=1 = todas <= 2,0.
Nada aqui usa a tela real; os casos de carga rodam o filho de verdade (spawn)."""
import inspect
import math
import multiprocessing.context
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_viewport_processo import (  # noqa: E402,F401  (modelos, fixtures e ajudantes compartilhados)
    MM, _confere_caixas, _instancia, _lentas, _mapa, _gerar_mapeadas, _mundo, _regra_de_ouro, _tempo_carga, m600,
    sem_filhos_sobrando,
)
from test_viewport_carregador import CarregadorMalhas, _novo, _por_produto  # noqa: E402

OBRIG = os.environ.get("OBIM_S04_T16_OBRIGATORIO") == "1"
ESTRITO = os.environ.get("OBIM_S04_ESTRITO") == "1"
PARAMS = ("max_pecas_condenadas", "max_espera_s")
TEM_T16 = CarregadorMalhas is not None and all(p in inspect.signature(CarregadorMalhas.__init__).parameters for p in PARAMS)
LARANJA = (255, 140, 0, 255)
PROIBIDAS = ("isolad", "iterador", "bloco", "thread", "timeout", "lote", "budget", "reinici")
LENTA_S = 4  # atraso injetado; o limite de cada caso é 1 s


def _pular(msg):
    (pytest.fail if OBRIG else pytest.skip)(f"\n!!! aguarda S04-T16: {msg} (oráculo da abertura NÃO FOI EXECUTADO) !!!\n")


@pytest.fixture(autouse=True)
def t16():
    TEM_T16 or _pular(f"CarregadorMalhas sem os parâmetros {PARAMS}")


def _rep_sem_geometria(f, corpo, p):
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=0.0, YDim=0.15)
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Depth=2.8,
                             Position=f.create_entity("IfcAxis2Placement3D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
                             ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    ifcopenshell.api.run("geometry.assign_representation", f, product=p, representation=rep)


def _ordem_das_representacoes(layout, ordem):
    """Ordem (índices do layout) em que as representações são criadas. Com threads=1 o iterador do IfcOpenShell entrega as
    peças na ordem das representações, NÃO na ordem dos ids (LOTE_OPUS_20, bloqueante 1). `ids`: igual à dos ids (caso antigo);
    `lentas_antes`: as lentas (S, B, L) primeiro, depois o resto (a lenta é entregue antes de peças de id menor, como no s25.ifc);
    `inversa`: do maior id para o menor (a entrega é a dos ids de trás para a frente)."""
    todos = list(range(len(layout)))
    if ordem == "ids":
        return todos
    if ordem == "inversa":
        return todos[::-1]
    assert ordem == "lentas_antes", ordem
    return [k for k in todos if layout[k] in "SBL"] + [k for k in todos if layout[k] not in "SBL"]


def _gerar_layout(caminho, layout, ordem="ids"):
    """Uma peça por letra, em ordem de id: n normal (todas da mesma família), S lenta (família própria), R sem geometria,
    B lenta com posição ilegível (RefDirection de 2 componentes: o conversor lê, o cálculo da caixa em Python não),
    L lenta da família G e c cópia (não lenta) da mesma família G (uma peça "membro" com muitas cópias), K peça em que o
    conversor cai (OBIM_TESTE_MATAR_FILHO; família própria). Os produtos são criados primeiro (ids crescentes na ordem do
    layout); as representações vêm depois, na ordem `ordem` (ver `_ordem_das_representacoes`)."""
    f, corpo = _novo()
    cubo, familia_g, prods = _mapa(f, corpo, 1.0, 1.0, 1.0), _mapa(f, corpo, 3.0, 1.0, 1.0), []
    for k, t in enumerate(layout):
        prods.append(ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name=f"{t}{k}"))
    for k in _ordem_das_representacoes(layout, ordem):
        t, p = layout[k], prods[k]
        pos = (k % 10 * 3.0, k // 10 * 3.0, 0.0)
        if t == "R":
            _rep_sem_geometria(f, corpo, p)
        else:
            mapa = cubo if t == "n" else familia_g if t in "Lc" else _mapa(f, corpo, 2.0, 1.0, 3.0)
            alvo = f.createIfcCartesianTransformationOperator3D(LocalOrigin=f.createIfcCartesianPoint((1.0 * MM, 0.5 * MM, 0.25 * MM)))
            rep = f.createIfcShapeRepresentation(corpo, "Body", "MappedRepresentation", [f.createIfcMappedItem(MappingSource=mapa, MappingTarget=alvo)])
            ifcopenshell.api.run("geometry.assign_representation", f, product=p, representation=rep)
        m = np.eye(4)
        m[:3, 3] = pos
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=p, matrix=m)
        if t == "B":
            p.ObjectPlacement.RelativePlacement.RefDirection = f.createIfcDirection((0.0, 1.0))
    f.write(str(caminho))
    ids = [p.id() for p in prods]
    assert ids == sorted(ids)
    return SimpleNamespace(caminho=caminho, ids=ids, lentas=[(p.id(), p.GlobalId) for p, t in zip(prods, layout) if t in "SBL"],
                           caidas=[(p.id(), p.GlobalId) for p, t in zip(prods, layout) if t == "K"],
                           por_tipo=lambda t: [i for i, x in zip(ids, layout) if x == t])


def _blocos(m, tb=4):
    return [m.ids[k:k + tb] for k in range(0, len(m.ids), tb)]


def _laranjas(lotes):
    """ids de peça cujos vértices são todos laranja (caixa substituta)."""
    saida = set()
    for lt in lotes:
        for o in lt.objetos:
            a, b = int(o["primeiro_vertice"]), int(o["primeiro_vertice"] + o["n_vertices"])
            if (lt.vertices["cor"][a:b] == np.array(LARANJA, dtype=np.uint8)).all():
                saida.add(int(o["id_step"]))
    return saida


def _carga(m, monkeypatch, lentas=True, medir=None, matar=None, **kw):
    """(lotes, resumo, laranjas, referência sem lentidão); confere o que vale em todo caso. `medir` (dict) recebe
    `t_ref` e `t` (segundos da carga de referência e da carga com lentidão), `filhos` (processos de conversão abertos na
    carga com lentidão; os da caixa não contam) e `ref_estado`. `matar`: guid da peça em que o conversor cai (só depois da referência)."""
    t0 = time.perf_counter()
    ref_lotes, ref, _ = _tempo_carga(m.caminho)
    t_ref = time.perf_counter() - t0
    assert ref.estado == "concluido" and ref.simplificadas == []
    lentas and _lentas(monkeypatch, *[(g, LENTA_S) for _, g in m.lentas])
    matar and monkeypatch.setenv("OBIM_TESTE_MATAR_FILHO", matar)
    filhos, original = [0], multiprocessing.context.SpawnProcess.start

    def contando(self):
        filhos[0] += getattr(self._target, "__name__", "") == "entrada"
        return original(self)

    with mock.patch.object(multiprocessing.context.SpawnProcess, "start", contando):
        lotes, r, dt = _tempo_carga(m.caminho, limite_peca_s=1.0, **kw)
    if medir is not None:
        medir.update(t_ref=t_ref, t=dt, filhos=filhos[0])
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    ids = [int(i) for lt in lotes for i in lt.objetos["id_step"]]
    assert len(ids) == len(set(ids)), "peça entregue duas vezes"
    _regra_de_ouro(r)
    lar = _laranjas(lotes)
    assert {s[0] for s in r.simplificadas} == lar, "caixa laranja e `simplificadas` não batem"
    return lotes, r, lar, ref_lotes


def _sem_jargao(r):
    """Toda linha do resumo que fala de peça ou caixa está em português simples (nenhuma das palavras de PROIBIDAS)."""
    for x in r.mensagens:
        if "caixa" in x.lower() or "peça" in x.lower():
            assert not [w for w in PROIBIDAS if w in x.lower()], f"jargão no resumo: {x!r}"


def _confere_resumo(r, n):
    linhas = [x for x in r.mensagens if re.search(rf"(?<![\d.,]){n}(?![\d.,])", x) and "caixa" in x.lower() and "peça" in x.lower()]
    assert linhas, f"nenhuma linha do resumo diz '{n}' peça(s) em caixa: {r.mensagens}"
    for x in linhas:
        assert not [w for w in PROIBIDAS if w in x.lower()], f"jargão no resumo: {x!r}"
    _sem_jargao(r)


# ---------- (a) orçamento total ----------
def test_a0_padroes_20_pecas_e_120_s():
    p = inspect.signature(CarregadorMalhas.__init__).parameters
    assert p["max_pecas_condenadas"].default == 20 and p["max_espera_s"].default == 120.0


def test_a1_passou_de_n_pecas_o_bloco_que_estoura_vira_caixa_de_uma_vez(tmp_path, monkeypatch):
    m = _gerar_layout(tmp_path / "a1.ifc", "nSnn" "nnnS" "Snnn" "nnnn" "nnSn")
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=4, max_pecas_condenadas=1)
    b1, b2, b3, b4, b5 = _blocos(m)
    assert lar & set(b1) == {b1[1]}, "bloco 1 (orçamento intacto): só a acusada vira caixa, as vizinhas ficam reais"
    assert b2[3] in lar and lar & set(b2) in ({b2[3]}, set(b2)), "bloco 2 pode ir de um jeito ou de outro (> ou >=), mas por inteiro"
    assert set(b3) <= lar and set(b5) <= lar, "orçamento estourado: o bloco que estoura vira caixa inteiro, de uma vez"
    assert not lar & set(b4), "o bloco sem peça lenta depois do corte continua no modo normal (geometria real)"
    assert r.sem_malha == [] and r.produtos_com_malha == 20
    _confere_caixas(lotes, ref, m.ids)
    t_ref = {i: v[0] for i, v in _por_produto(ref).items()}
    assert {i: v[0] for i, v in _por_produto(lotes).items() if i in b4} == {i: t_ref[i] for i in b4}
    _confere_resumo(r, 8 + (4 if set(b2) <= lar else 0))


def test_a2_passou_de_t_segundos_de_espera(tmp_path, monkeypatch):
    m = _gerar_layout(tmp_path / "a2.ifc", "nnnS" "nSnn" "nnnn")
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=4, max_espera_s=1.5)  # o bloco 1 espera 2 s ou mais
    b1, b2, b3 = _blocos(m)
    assert lar & set(b1) == {b1[3]} and set(b2) <= lar and not lar & set(b3)
    assert r.sem_malha == []
    _confere_caixas(lotes, ref, m.ids)
    _confere_resumo(r, 4)


def test_a3_orcamento_padrao_nao_corta_poucas_pecas_lentas(tmp_path, monkeypatch):
    m = _gerar_layout(tmp_path / "a3.ifc", "nSnn" "nnSn")
    _, r, lar, _ = _carga(m, monkeypatch, tamanho_bloco=4)
    assert lar == {m.lentas[0][0], m.lentas[1][0]} and r.produtos_com_malha == 8


# ---------- (b) modo isolado mais barato ----------
class _Tx:
    def __init__(self):
        self.msgs = []

    def send(self, msg):
        self.msgs.append(msg)


def _em_processo(caminho, ids, isolado, threads=1):
    """Roda `processo_malhas.entrada` neste processo. Devolve (triângulos por id, ms por peça, iteradores criados)."""
    from viewport_qrhi import processo_malhas as pm
    criados, orig, tx = [0], ifcopenshell.geom.iterator, _Tx()

    def contar(*a, **k):
        criados[0] += 1
        return orig(*a, **k)

    params = {"caminho": str(caminho), "threads": threads, "tamanho_bloco": 1000, "excluir": ("IfcFeatureElementSubtraction", "IfcSpace"),
              "biblioteca": "hybrid-cgal-simple-opencascade", "max_bytes_lote": 8 * 1024 * 1024, "ids": ids, "isolado": isolado, "desl": None}
    with mock.patch.object(ifcopenshell.geom, "iterator", contar):
        pm.entrada(tx, params)
    erros = [d for t, d in tx.msgs if t == "erro"]
    assert not erros and tx.msgs[-1][0] == "fim", f"o filho não terminou: {erros}"
    lotes = [d for t, d in tx.msgs if t == "lote"]
    return {i: v[0] for i, v in _por_produto(lotes).items()}, tx.msgs[-1][1]["tempos"]["geometria_s"] * 1000 / len(ids), criados[0]


@pytest.fixture
def sem_ganchos(monkeypatch):
    for k in [k for k in os.environ if k.startswith("OBIM_TESTE_")]:
        monkeypatch.delenv(k)


def _ids_paredes(caminho, n):
    return sorted(p.id() for p in ifcopenshell.open(str(caminho)).by_type("IfcWall"))[:n]


def test_b1_modo_isolado_usa_um_iterador_para_o_bloco_e_entrega_tudo(m600, sem_ganchos):
    ids = _ids_paredes(m600, 100)
    normal, _, n_normal = _em_processo(m600, ids, False)
    isolado, _, n_isolado = _em_processo(m600, ids, True)
    assert n_normal == 1 and n_isolado == 1, f"iteradores criados: normal {n_normal}, isolado {n_isolado} (esperado 1 por bloco)"
    assert set(isolado) == set(ids) and isolado == normal


def test_b2_custo_por_peca_do_modo_isolado_ate_2x_o_normal(m600, tmp_path, sem_ganchos):
    mapeadas, _ = _gerar_mapeadas(tmp_path / "map.ifc", normais=80, lentas=0)
    razoes = []
    for nome, caminho, ids in (("paredes", m600, _ids_paredes(m600, 150)), ("mapeadas", mapeadas, _ids_paredes(mapeadas, 80))):
        _em_processo(caminho, ids, True)  # aquecimento
        n, i = [], []
        for _ in range(5):  # alterna, para o ruído do CI pesar igual nos dois
            n.append(_em_processo(caminho, ids, False)[1])
            i.append(_em_processo(caminho, ids, True)[1])
        razoes.append(float(np.median(i) / np.median(n)))
        print(f"\nS04-T16 custo {nome}: normal {np.median(n):.2f} ms/peça, isolado {np.median(i):.2f} ms/peça, razão {razoes[-1]:.2f}")
    assert max(razoes) < 4.0, f"nenhum caso pode passar de 4x o normal: {np.round(razoes, 2).tolist()}"
    assert float(np.median(razoes)) <= 2.0, f"mediana das razões {np.median(razoes):.2f} > 2,0 ({np.round(razoes, 2).tolist()})"
    assert not ESTRITO or max(razoes) <= 2.0, f"OBIM_S04_ESTRITO=1: todos os casos <= 2,0 ({np.round(razoes, 2).tolist()})"


def test_b4_so_a_acusada_e_confirmada_vizinhas_sem_geometria_nao_(tmp_path, monkeypatch):
    """Condições do P14 no modo isolado novo: sem geometria antes e depois da lenta, no mesmo bloco; vizinhas ficam reais."""
    m = _gerar_layout(tmp_path / "b4.ifc", "nRRSnRn")
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=7)
    ruins, [s] = m.por_tipo("R"), m.por_tipo("S")
    assert lar == {s}, f"só a lenta vira caixa; acusadas: {sorted(lar)}"
    assert [x[0] for x in r.sem_malha] == ruins and all("caixa" not in x[3].lower() for x in r.sem_malha)
    assert r.produtos_com_malha == 4 and r.produtos_total == 7


# ---------- (c) S03-T08-G ----------
def test_c1_posicao_ilegivel_vai_para_sem_malha_nunca_caixa_na_origem(tmp_path, monkeypatch):
    m = _gerar_layout(tmp_path / "c1.ifc", "nnBnn")
    ref_lotes, ref, _ = _tempo_carga(m.caminho)
    assert ref.estado == "concluido" and ref.sem_malha == [] and ref.produtos_com_malha == 5  # a peça é legível para o conversor
    _lentas(monkeypatch, *[(g, LENTA_S) for _, g in m.lentas])
    lotes, r, _ = _tempo_carga(m.caminho, limite_peca_s=1.0, tamanho_bloco=5)
    [(b, _)] = m.lentas
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    assert [x[0] for x in r.sem_malha] == [b] and len(r.sem_malha[0][3]) > 10, f"sem_malha: {r.sem_malha}"
    assert r.simplificadas == [] and b not in _mundo(lotes) and r.produtos_com_malha == 4
    _confere_caixas(lotes, ref_lotes, [i for i in m.ids if i != b])  # nenhuma caixa na origem esticando a cena
    _regra_de_ouro(r)


def test_c2_filho_isolado_que_cai_sem_pendentes_nao_vira_erro(tmp_path, monkeypatch):
    from viewport_qrhi import processo_malhas as pm
    if "OBIM_TESTE_MATAR_NO_FIM" not in Path(pm.__file__).read_text(encoding="utf-8"):
        _pular("gancho OBIM_TESTE_MATAR_NO_FIM ausente em processo_malhas.py")
    m = _gerar_layout(tmp_path / "c2.ifc", "nSnn")
    monkeypatch.setenv("OBIM_TESTE_MATAR_NO_FIM", "1")
    lotes, r, lar, _ = _carga(m, monkeypatch, tamanho_bloco=4)
    assert lar == {m.lentas[0][0]} and r.erro is None and r.sem_malha == [] and r.produtos_com_malha == 4


# ---------- (d) a ordem de entrega do iterador não é a dos ids (LOTE_OPUS_20, bloqueantes 1 a 3) ----------
def _k_filhos(n_pecas, n_lentas=1):
    """Teto de processos de conversão abertos por carga: por peça lenta, os 3 fixos (bloco normal, isolado, confirmação da
    acusada) mais 1 de folga e log2(n) da divisão ao meio das pendentes não anunciadas (a divisão ao meio gasta 8 no s25.ifc)."""
    return n_lentas * (4 + math.ceil(math.log2(max(n_pecas, 2))))


def _main_estimado(medir, n_lentas, limite=1.0):
    """Tempo que o `main` gasta no mesmo modelo, estimado a partir da referência medida NESTA execução (escala igual no CI
    do Windows). Calibrado no `main` de 2026-10-13: 1 lenta em 26 peças = 3,1 s (referência 0,4 s); 3 lentas em 23 = 6,1 s."""
    return 3 * medir["t_ref"] + n_lentas * (limite + 1.0)


def _linhas_de_uma_vez(r):
    return [x for x in r.mensagens if "de uma vez" in x.lower()]


def _tem_numero(x, n):
    return re.search(rf"(?<![\d.,]){n}(?![\d.,])", x) is not None


@pytest.mark.parametrize("layout, ordem", [("n" * 25 + "S", "lentas_antes"), ("n" * 12 + "S" + "n" * 12, "inversa")], ids=["s25", "meio_inversa"])
def test_d1_lenta_entregue_antes_de_pecas_de_id_menor(tmp_path, monkeypatch, layout, ordem):
    """a) Modelo como o s25.ifc: 25 paredes normais de id menor, com as representações criadas depois (a lenta sai na
    posição 0 do iterador). Esperado: concluído, só a lenta vira caixa, poucos filhos, tempo < 3x o do `main`."""
    m = _gerar_layout(tmp_path / "d1.ifc", layout, ordem)
    med = {}
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=1000, medir=med)
    [(lenta, _)] = m.lentas
    assert lar == {lenta}, f"só a lenta vira caixa; viraram: {sorted(lar)}"
    assert r.sem_malha == [] and r.produtos_com_malha == len(layout) and r.erro is None
    _confere_caixas(lotes, ref, m.ids)
    _confere_resumo(r, 1)
    assert med["filhos"] <= _k_filhos(len(layout)), f"{med['filhos']} processos de conversão (teto {_k_filhos(len(layout))})"
    teto = 3 * _main_estimado(med, 1)
    print(f"\nS04-T16b d1: {med['t']:.1f} s (teto {teto:.1f} s, referência {med['t_ref']:.2f} s), {med['filhos']} filhos")
    assert med["t"] < teto, f"{med['t']:.1f} s >= 3 x o do main ({teto:.1f} s; referência sem lentidão {med['t_ref']:.2f} s)"


@pytest.mark.parametrize("ordem", ["lentas_antes", "inversa"])
def test_d2_varias_lentas_fora_de_ordem_todas_e_so_elas_viram_caixa(tmp_path, monkeypatch, ordem):
    """b) Três lentas espalhadas, entregues fora da ordem dos ids: todas e só elas viram caixa (orçamento padrão intacto)."""
    layout = "nnnnn" + "S" + "nnnnn" + "S" + "nnnnn" + "S" + "nnnnn"
    m = _gerar_layout(tmp_path / "d2.ifc", layout, ordem)
    med = {}
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=1000, medir=med)
    assert lar == {i for i, _ in m.lentas} and len(lar) == 3, f"todas e só as lentas: {sorted(lar)} contra {m.lentas}"
    assert r.sem_malha == [] and r.produtos_com_malha == len(layout) and r.erro is None
    _confere_caixas(lotes, ref, m.ids)
    _confere_resumo(r, 3)
    assert not _linhas_de_uma_vez(r), "com 3 peças lentas o orçamento padrão (20) não pode cortar nada"
    assert med["filhos"] <= _k_filhos(len(layout), 3), f"{med['filhos']} processos de conversão (teto {_k_filhos(len(layout), 3)})"
    teto = 5 * _main_estimado(med, 3)  # 5x, não 3x: várias lentas somam esperas de confirmação (a divisão ao meio gasta ~2,8x o main)
    print(f"\nS04-T16b d2: {med['t']:.1f} s (teto {teto:.1f} s, referência {med['t_ref']:.2f} s), {med['filhos']} filhos")
    assert med["t"] < teto, f"{med['t']:.1f} s >= 5 x o do main ({teto:.1f} s; referência sem lentidão {med['t_ref']:.2f} s)"


@pytest.mark.parametrize("kw", [{"max_pecas_condenadas": 2}, {"max_espera_s": 3.0}], ids=["orcamento_de_pecas", "orcamento_de_espera"])
def test_d3_o_orcamento_protege_o_laco_de_confirmacoes(tmp_path, monkeypatch, kw):
    """c) Muitas lentas fora de ordem entre muitas peças normais: nunca termina em erro por reinício; passou do orçamento, o
    que ainda estava pendente vira caixa de uma vez e a carga conclui. Toda lenta termina em caixa."""
    layout = "n" * 22 + "SSSS"
    m = _gerar_layout(tmp_path / "d3.ifc", layout, "lentas_antes")
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=1000, **kw)
    assert r.erro is None and r.sem_malha == [] and r.produtos_com_malha == len(layout)
    assert {i for i, _ in m.lentas} <= lar, "toda peça lenta termina em caixa"
    acusadas = {s[0] for s in r.simplificadas if "limite" in s[4].lower()}
    cortadas = lar - acusadas
    assert cortadas, "o orçamento tinha de cortar o que sobrou, de uma vez"
    assert "max_pecas_condenadas" not in kw or len(acusadas) <= kw["max_pecas_condenadas"] + 1, \
        f"{len(acusadas)} acusadas confirmadas; passou de {kw['max_pecas_condenadas']} só pode haver mais uma, a que estourou"
    _confere_caixas(lotes, ref, m.ids)
    _confere_resumo(r, len(cortadas))
    assert any(_tem_numero(x, len(cortadas)) for x in _linhas_de_uma_vez(r)), f"nenhuma linha 'de uma vez' diz {len(cortadas)}: {r.mensagens}"


def test_d4_cada_copia_nao_conta_no_orcamento_so_as_acusadas_confirmadas(tmp_path, monkeypatch):
    """d) Uma peça "membro" lenta com 32 cópias (mesma peça-base) e, depois, outra peça lenta de outra família. As 32 cópias
    não podem estourar sozinhas o limite de 20 (conta só as acusadas confirmadas: 2): a segunda lenta é isolada e só ela
    vira caixa; as vizinhas dela continuam reais."""
    layout = "Lnnn" + "c" * 32 + "nnnS"
    m = _gerar_layout(tmp_path / "d4.ifc", layout)
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=4)
    [(l, _), (s, _)] = m.lentas
    copias = set(m.por_tipo("c"))
    assert lar == {l, s} | copias, f"deviam virar caixa a lenta, as 32 cópias e a outra lenta; sobraram/faltaram: {sorted(lar ^ ({l, s} | copias))}"
    assert not lar & set(m.por_tipo("n")), "peça normal vizinha da segunda lenta não pode virar caixa (o orçamento não estourou)"
    assert r.sem_malha == [] and r.produtos_com_malha == len(layout)
    _confere_caixas(lotes, ref, m.ids)
    assert not _linhas_de_uma_vez(r)
    _sem_jargao(r)


def test_d5_peca_sem_geometria_dentro_de_bloco_cortado_vira_caixa(tmp_path, monkeypatch):
    """e) COMPORTAMENTO ATUAL, registrado conforme o cartão: o bloco cortado pelo orçamento vira caixa inteiro, inclusive a
    peça sem geometria (ela NÃO vai para `sem_malha`). Fora de um bloco cortado ela continua indo para `sem_malha`."""
    m = _gerar_layout(tmp_path / "d5.ifc", "nSnn" "nnnS" "SnRn" "nRnn")
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=4, max_pecas_condenadas=1)
    b1, b2, b3, b4 = _blocos(m)
    r3, r4 = m.por_tipo("R")
    assert set(b3) <= lar and r3 in lar, "bloco cortado vira caixa inteiro, inclusive a peça sem geometria"
    assert r3 in {s[0] for s in r.simplificadas} and r3 not in {x[0] for x in r.sem_malha}
    assert r4 in {x[0] for x in r.sem_malha} and r4 not in lar, "depois do corte, bloco sem peça lenta: a sem geometria continua em `sem_malha`"
    assert r.produtos_com_malha == 15 and r.produtos_total == 16
    _sem_jargao(r)


def test_d6_texto_do_resumo_em_portugues_simples_com_as_tres_causas(tmp_path, monkeypatch):
    """f) Limite, queda do conversor e corte do orçamento no mesmo arquivo: uma linha por causa, com o número exato, sem jargão
    (nada de bloco, isolado, iterador, thread, reiniciar, lote)."""
    m = _gerar_layout(tmp_path / "d6.ifc", "nSnn" "nKnn" "SnSn")
    [(_, guid_k)] = m.caidas
    lotes, r, lar, ref = _carga(m, monkeypatch, tamanho_bloco=4, max_pecas_condenadas=1, matar=guid_k)
    b1, b2, b3 = _blocos(m)
    assert lar & set(b1) == {b1[1]} and lar & set(b2) == {b2[1]} and set(b3) <= lar
    assert r.sem_malha == [] and r.produtos_com_malha == 12
    for n in (1, 4):
        _confere_resumo(r, n)
    assert [x for x in _linhas_de_uma_vez(r) if _tem_numero(x, 4)], r.mensagens
    assert any("limite" not in x.lower() and "caiu" in x.lower() for x in r.mensagens), "linha da queda do conversor"
    assert any(_tem_numero(x, 1) and "passaram de 1 s" in x for x in r.mensagens), "linha do limite de tempo"
