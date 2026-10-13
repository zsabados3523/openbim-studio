# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S04-T16 (abertura: orçamento de peças lentas, modo isolado mais barato) e da S03-T08-G. Sem tela, sem Qt.
Especificação: docs/state/reports/LOTE_OPUS_9.md (T16), LOTE_OPUS_8.md §2.3 itens 3 e 4, LOTE_OPUS_7.md §1.4 (opção ii). Casos P13/P14/P18
ficam em test_viewport_processo.py (rodar junto: devem continuar verdes); aqui há também as condições do P14 com o modo isolado novo.
GUARDA: pula enquanto `CarregadorMalhas.__init__` não aceitar `max_pecas_condenadas` e `max_espera_s`; FALHA com OBIM_S04_T16_OBRIGATORIO=1.
CONTRATO PARA O IMPLEMENTADOR (nomes exatos; o oráculo não depende de mais nada):
 * CarregadorMalhas(..., max_pecas_condenadas=20, max_espera_s=120.0). Orçamento estourado = (peças já mostradas como caixa por lentidão
   ou queda) > N  OU  (soma, em segundos, de TODAS as esperas por peça lenta: a do bloco no modo normal, a do modo isolado e a da
   confirmação) > T. Só é conferido quando um bloco estoura `limite_peca_s` no modo normal. Estourado: TODAS as peças ainda pendentes
   daquele bloco, inclusive a que travou, viram caixa de uma vez (sem modo isolado); os blocos seguintes seguem no modo normal. Sem o
   orçamento estourado, nada muda (modo isolado). Peça sem geometria nunca entra nesse caso (os casos não a põem no bloco).
 * Resumo (`ResumoCarga.mensagens`): uma linha com o número EXATO de peças mostradas como caixa de uma vez (as pendentes dos blocos
   cortados, inclusive a que travou), com as palavras "peça" e "caixa", sem jargão (nada de isolado, iterador, bloco, thread, timeout,
   lote, budget). O número aparece sozinho (não colado a outro dígito, ponto ou vírgula). Toda peça cortada entra em `simplificadas`.
 * processo_malhas.entrada(tx, params) continua sendo o ponto de entrada do filho (tx só precisa de `.send((tipo, dados))`); params
   com as chaves de hoje (caminho, threads, tamanho_bloco, excluir, biblioteca, max_bytes_lote, ids, isolado, desl). Com
   isolado=True o filho cria UM `ifcopenshell.geom.iterator` para todos os ids pedidos (a confirmação da peça acusada é outro filho,
   com ids=[acusada], e só acontece quando o pai vê a espera estourar) e entrega as peças como hoje (`lote`, `sem_malha`, `fim`).
 * Gancho novo no filho (S03-T08-G, item 2): OBIM_TESTE_MATAR_NO_FIM=1 faz um filho em modo isolado sair com código 3 depois do
   último `lote` e antes do `fim`. Pai: sem pendentes depois de um filho que cai, segue (não termina em "erro").
 * S03-T08-G item 1: peça cuja posição (ObjectPlacement) não pode ser lida pela caixa vai para `sem_malha` com motivo (nunca caixa
   em posição zero). Régua do custo (b): CI virtual = mediana das razões dos casos <= 2,0 e nenhuma >= 4,0; OBIM_S04_ESTRITO=1 = todas <= 2,0.
Nada aqui usa a tela real; os casos de carga rodam o filho de verdade (spawn)."""
import inspect
import os
import re
import sys
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
    _confere_caixas, _instancia, _lentas, _mapa, _gerar_mapeadas, _mundo, _regra_de_ouro, _tempo_carga, m600,
    sem_filhos_sobrando,
)
from test_viewport_carregador import CarregadorMalhas, _novo, _por_produto  # noqa: E402

OBRIG = os.environ.get("OBIM_S04_T16_OBRIGATORIO") == "1"
ESTRITO = os.environ.get("OBIM_S04_ESTRITO") == "1"
PARAMS = ("max_pecas_condenadas", "max_espera_s")
TEM_T16 = CarregadorMalhas is not None and all(p in inspect.signature(CarregadorMalhas.__init__).parameters for p in PARAMS)
LARANJA = (255, 140, 0, 255)
PROIBIDAS = ("isolad", "iterador", "bloco", "thread", "timeout", "lote", "budget")
LENTA_S = 4  # atraso injetado; o limite de cada caso é 1 s


def _pular(msg):
    (pytest.fail if OBRIG else pytest.skip)(f"\n!!! aguarda S04-T16: {msg} (oráculo da abertura NÃO FOI EXECUTADO) !!!\n")


@pytest.fixture(autouse=True)
def t16():
    TEM_T16 or _pular(f"CarregadorMalhas sem os parâmetros {PARAMS}")


def _parede_sem_geometria(f, corpo):
    p = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="sem geometria")
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=0.0, YDim=0.15)
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Depth=2.8,
                             Position=f.create_entity("IfcAxis2Placement3D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
                             ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    ifcopenshell.api.run("geometry.assign_representation", f, product=p, representation=rep)
    return p


def _gerar_layout(caminho, layout):
    """Uma peça por letra, em ordem de id: n normal (todas da mesma família), S lenta (família própria), R sem geometria,
    B lenta com posição ilegível (RefDirection de 2 componentes: o conversor lê, o cálculo da caixa em Python não)."""
    f, corpo = _novo()
    cubo, prods = _mapa(f, corpo, 1.0, 1.0, 1.0), []
    for k, t in enumerate(layout):
        pos = (k % 10 * 3.0, k // 10 * 3.0, 0.0)
        if t == "R":
            p = _parede_sem_geometria(f, corpo)
        else:
            p = _instancia(f, corpo, cubo if t == "n" else _mapa(f, corpo, 2.0, 1.0, 3.0), pos, f"{t}{k}")
        if t == "B":
            p.ObjectPlacement.RelativePlacement.RefDirection = f.createIfcDirection((0.0, 1.0))
        prods.append(p)
    f.write(str(caminho))
    ids = [p.id() for p in prods]
    assert ids == sorted(ids)
    return SimpleNamespace(caminho=caminho, ids=ids, lentas=[(p.id(), p.GlobalId) for p, t in zip(prods, layout) if t in "SB"],
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


def _carga(m, monkeypatch, lentas=True, **kw):
    """(lotes, resumo, laranjas, referência sem lentidão); confere o que vale em todo caso."""
    ref_lotes, ref, _ = _tempo_carga(m.caminho)
    assert ref.estado == "concluido" and ref.simplificadas == []
    lentas and _lentas(monkeypatch, *[(g, LENTA_S) for _, g in m.lentas])
    lotes, r, _ = _tempo_carga(m.caminho, limite_peca_s=1.0, **kw)
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    ids = [int(i) for lt in lotes for i in lt.objetos["id_step"]]
    assert len(ids) == len(set(ids)), "peça entregue duas vezes"
    _regra_de_ouro(r)
    lar = _laranjas(lotes)
    assert {s[0] for s in r.simplificadas} == lar, "caixa laranja e `simplificadas` não batem"
    return lotes, r, lar, ref_lotes


def _confere_resumo(r, n):
    linhas = [x for x in r.mensagens if re.search(rf"(?<![\d.,]){n}(?![\d.,])", x) and "caixa" in x.lower() and "peça" in x.lower()]
    assert linhas, f"nenhuma linha do resumo diz '{n}' peça(s) em caixa: {r.mensagens}"
    for x in linhas:
        assert not [w for w in PROIBIDAS if w in x.lower()], f"jargão no resumo: {x!r}"


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
