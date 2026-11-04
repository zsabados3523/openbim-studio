# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T11, reassociação assistida de GlobalIds trocados (v2/02 §6.3; ADR-002 §4/§11). 
CONTRATO (API PROPOSTA NESTE TESTE; os documentos fixam a regra, não nomes nem limiares). `openbim_app/reassociacao.py`, funções puras, sem Qt,
sem ifcopenshell, sem arquivo, sem relógio:
- Elemento = dict `{"guid": str, "classe": str, "nome": str|None, "tag": str|None, "caixa": (x0,y0,z0,x1,y1,z1)|None}` (metros).
- `vistas` = `{vista_id: [elemento, ...]}`: o que cada vista referencia, com os dados da última gravação. `atuais` = lista de elementos do IFC de agora.
- `contar_quebradas(vistas, atuais) -> {vista_id: n}`: referência quebrada = guid que não está em `atuais`. Todas as vistas entram (0 incluso),
  chaves em ordem de `vista_id`; guid repetido na mesma vista conta uma vez.
- `propor(vistas, atuais, tol_alta=TOL_ALTA, tol_baixa=TOL_BAIXA) -> {"alta": [...], "baixa": [...], "orfaos": [...]}`. Só entram referências
  quebradas. alta/baixa: `{"vista", "guid_antigo", "guid_novo"}`; órfão: `{"vista", "guid_antigo", "motivo"}`. Cada lista em ordem (vista, guid_antigo).
  Regra: candidato = mesma `classe` e identidade igual (Tag igual e não vazio; sem Tag nos dois lados, Name igual e não vazio). Distância d = entre os
  CENTROS das caixas, euclidiana 3D. d <= tol_alta -> alta; tol_alta < d <= tol_baixa -> baixa; d > tol_baixa -> órfão "sem_candidato".
  Tag diferente (ambas preenchidas) com Name igual -> não é candidato por identidade forte: entra só como baixa se d <= tol_baixa.
  Mais de um candidato dentro de tol_baixa para o mesmo antigo -> órfão "ambiguo" (nunca chute). Um mesmo novo pedido por 2 guids antigos
  distintos -> os dois órfãos "disputado". Caixa ausente, NaN ou inf (do antigo) -> órfão "caixa_invalida"; candidato com caixa inválida é ignorado.
  tol inválida (negativa, NaN, tol_baixa < tol_alta) -> ValueError. Mesmo guid antigo em várias vistas: mesma decisão em cada uma.
- `aplicar(vistas, proposta, confirmados) -> vistas novo`: `confirmados` = lista de `(vista, guid_antigo)`. Só altera o campo `guid` das referências
  confirmadas. Confirmado que não é alta/baixa da proposta (inclui órfão e desconhecido) -> ValueError e nada muda. `[]` -> cópia igual. Aplicar de novo
  é no-op. Órfãos nunca são apagados nem trocados. Nenhuma função muda a entrada.
- REVISÃO (T11B, decisões do líder após reprovação do Argon): (1) candidato FORTE = Tag igual e não vazia (ou sem Tag nos dois lados e Name igual);
  FRACO = Name igual e não vazio com Tag diferente (ambas preenchidas) OU Tag vazia/ausente em um lado só. Fraco só é considerado se não há forte
  (dentro de tol_baixa) para aquele antigo; fraco é sempre BAIXA, nunca alta; mais de um fraco -> "ambiguo". Na disputa por um mesmo novo, forte
  vence fraco (o fraco vira órfão "disputado"); dois fortes ou dois fracos -> os dois "disputado". (2) "bloqueados": novo cujo guid já é referenciado
  intacto em alguma vista não é candidato. (3) guid ausente/None na referência = quebrada, órfão "sem_guid", nunca confirmável; guid None em `atuais` nunca
  conta como intacto nem como candidato. (4) decisão por (vista, guid_antigo): o mesmo guid com dados diferentes em vistas diferentes decide cada um com
  os seus dados. (5) escala: propor não pode ser O(antigos x atuais) (índice por Tag/Name). (6) caixa cujo centro estoura (1e308) é "caixa_invalida"
  ou tem distância correta, nunca inf silencioso.
- Valores propostos (PERGUNTA_PO): `TOL_ALTA = 0.5` m, `TOL_BAIXA = 2.0` m."""
import copy
import math
import random

import pytest
from _reassociacao_ajudantes import P, _mod, antigos, atuais_ok, el, ids  # noqa: F401


def test_contar_por_vista():
    m = _mod()
    v = {"V2": [el("a1"), el("a1"), el("ok")], "V1": [el("a1"), el("a2")], "V0": []}
    r = m.contar_quebradas(v, [el("ok")])
    assert r == {"V0": 0, "V1": 2, "V2": 1} and list(r) == ["V0", "V1", "V2"]


def test_contar_sem_quebradas_e_listas_vazias():
    m = _mod()
    assert m.contar_quebradas({"V1": [el("a")]}, [el("a")]) == {"V1": 0}
    assert m.contar_quebradas({}, [el("a")]) == {}
    assert m.contar_quebradas({"V1": [el("a")]}, []) == {"V1": 1}


def test_renomeado_mesmo_tag_outro_nome_e_alta():
    novo = [el("n1", nome="Outro nome", tag="T1")]
    r = P({"V1": [el("a1", nome="P1", tag="T1")]}, novo)
    assert ids(r["alta"]) == [("V1", "a1", "n1")] and r["baixa"] == [] and r["orfaos"] == []


def test_sem_tag_casa_por_name():
    r = P({"V1": [el("a1", tag=None, nome="P9")]}, [el("n1", tag=None, nome="P9")])
    assert ids(r["alta"]) == [("V1", "a1", "n1")]


def test_movido_pouco_alta_movido_mais_baixa_longe_orfao():
    v = {"V1": [el("a1", tag="T1")]}
    assert ids(P(v, [el("n1", tag="T1", x=0.3)])["alta"]) == [("V1", "a1", "n1")]
    assert ids(P(v, [el("n1", tag="T1", x=1.5)])["baixa"]) == [("V1", "a1", "n1")]
    r = P(v, [el("n1", tag="T1", x=5.0)])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"] == [{"vista": "V1", "guid_antigo": "a1", "motivo": "sem_candidato"}]


def test_apagado_vira_orfao_preservado():
    m = _mod()
    v = antigos()
    r = P(v, [el("n1", tag="T1")])
    assert [(o["vista"], o["guid_antigo"], o["motivo"]) for o in r["orfaos"]] == [("V1", "a2", "sem_candidato")]
    novo = m.aplicar(v, r, [("V1", "a1"), ("V2", "a1")])
    assert [e["guid"] for e in novo["V1"]] == ["n1", "a2"] and novo["V1"][1] == v["V1"][1]  # órfão intacto, em silêncio nada some


def test_classe_diferente_nao_casa():
    r = P({"V1": [el("a1", classe="IfcWall")]}, [el("n1", classe="IfcSlab")])
    assert r["alta"] == r["baixa"] == [] and ids(r["orfaos"]) == [("V1", "a1", None)] and r["orfaos"][0]["motivo"] == "sem_candidato"


def test_tag_diferente_name_igual_so_baixa():
    v = {"V1": [el("a1", tag="T1", nome="P1")]}
    r = P(v, [el("n1", tag="T9", nome="P1")])
    assert r["alta"] == [] and ids(r["baixa"]) == [("V1", "a1", "n1")]
    assert P(v, [el("n1", tag="T9", nome="P1", x=3.0)])["baixa"] == []


def test_vazio_nao_e_identidade():
    r = P({"V1": [el("a1", tag="", nome="")]}, [el("n1", tag="", nome="")])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"
    r = P({"V1": [el("a1", tag=None, nome=None)]}, [el("n1", tag=None, nome=None)])
    assert r["alta"] == r["baixa"] == []


def test_empate_vira_orfao_ambiguo_nunca_chute():
    r = P({"V1": [el("a1")]}, [el("n1", x=0.1), el("n2", x=0.2)])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"] == [{"vista": "V1", "guid_antigo": "a1", "motivo": "ambiguo"}]


def test_candidato_fora_da_tolerancia_nao_causa_ambiguidade():
    r = P({"V1": [el("a1")]}, [el("n1", x=0.1), el("n2", x=9.0)])
    assert ids(r["alta"]) == [("V1", "a1", "n1")] and r["orfaos"] == []


def test_um_novo_pedido_por_dois_antigos_vira_disputado():
    v = {"V1": [el("a1"), el("a2", nome="P1b")]}
    r = P(v, [el("n1")])
    assert r["alta"] == r["baixa"] == [] and [(o["guid_antigo"], o["motivo"]) for o in r["orfaos"]] == [("a1", "disputado"), ("a2", "disputado")]


def test_mesmo_guid_antigo_em_duas_vistas_mesma_decisao():
    r = P(antigos(), atuais_ok())
    assert ids(r["alta"]) == [("V1", "a1", "n1"), ("V1", "a2", "n2"), ("V2", "a1", "n1")]


@pytest.mark.parametrize("x,lista", [(0.5, "alta"), (0.5000001, "baixa"), (2.0, "baixa"), (2.0000001, "orfaos")])
def test_limiares_nas_bordas(x, lista):
    r = P({"V1": [el("a1")]}, [el("n1", x=x)])
    assert len(r[lista]) == 1 and sum(len(r[k]) for k in r) == 1


def test_limiares_configuraveis_e_invalidos():
    v = {"V1": [el("a1")]}
    assert ids(P(v, [el("n1", x=1.0)], tol_alta=1.0)["alta"]) == [("V1", "a1", "n1")]
    assert P(v, [el("n1", x=3.0)], tol_baixa=3.0)["baixa"] != []
    for kw in ({"tol_alta": -1.0}, {"tol_alta": float("nan")}, {"tol_alta": 3.0, "tol_baixa": 1.0}, {"tol_baixa": float("inf")}):
        with pytest.raises(ValueError):
            P(v, [el("n1")], **kw)


@pytest.mark.parametrize("ruim", [None, (0, 0, 0, math.nan, 1, 1), (0, 0, 0, math.inf, 1, 1), (0, 0, -math.inf, 1, 1, 1)])
def test_caixa_invalida(ruim):
    r = P({"V1": [el("a1", caixa=ruim)]}, [el("n1")])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"] == [{"vista": "V1", "guid_antigo": "a1", "motivo": "caixa_invalida"}]
    r = P({"V1": [el("a1")]}, [el("n1", caixa=ruim)])  # candidato inválido é ignorado
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"
    r = P({"V1": [el("a1")]}, [el("n1", caixa=ruim), el("n2", x=0.1)])  # e não gera ambiguidade
    assert ids(r["alta"]) == [("V1", "a1", "n2")]


def test_listas_vazias():
    assert P({}, []) == {"alta": [], "baixa": [], "orfaos": []}
    assert P({"V1": []}, [el("n1")]) == {"alta": [], "baixa": [], "orfaos": []}
    r = P({"V1": [el("a1")]}, [])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"


def test_referencia_intacta_nao_entra_na_proposta():
    r = P({"V1": [el("ok"), el("a1")]}, [el("ok"), el("n1")])
    assert ids(r["alta"]) == [("V1", "a1", "n1")] and r["baixa"] == [] and r["orfaos"] == []


def test_total_da_proposta_igual_ao_contado():
    m = _mod()
    v = antigos()
    a = [el("n1", tag="T1", x=1.5), el("n3", tag="T7", x=9.0)]
    r = m.propor(v, a)
    quebradas = sum(m.contar_quebradas(v, a).values())
    assert len(r["alta"]) + len(r["baixa"]) + len(r["orfaos"]) == quebradas == 3


def test_ordem_deterministica_independe_da_ordem_de_entrada():
    m = _mod()
    v = {f"V{i}": [el(f"a{j}", tag=f"T{j}", nome=f"N{j}", x=float(j) * 4) for j in range(4)] for i in range(3)}
    a = [el(f"n{j}", tag=f"T{j}", nome=f"N{j}", x=float(j) * 4 + 0.2 * (j % 3)) for j in range(4)]
    base = m.propor(v, a)
    assert [(e["vista"], e["guid_antigo"]) for e in base["alta"]] == sorted((e["vista"], e["guid_antigo"]) for e in base["alta"])
    rnd = random.Random(20261023)
    for _ in range(5):
        v2 = {k: rnd.sample(v[k], len(v[k])) for k in rnd.sample(list(v), len(v))}
        a2 = rnd.sample(a, len(a))
        assert m.propor(v2, a2) == base


def test_entrada_nao_mutada():
    m = _mod()
    v, a = antigos(), atuais_ok()
    v0, a0 = copy.deepcopy(v), copy.deepcopy(a)
    m.contar_quebradas(v, a)
    r = m.propor(v, a)
    r0 = copy.deepcopy(r)
    novo = m.aplicar(v, r, [("V1", "a1")])
    assert v == v0 and a == a0 and r == r0
    assert novo is not v and novo["V1"][1] is not v["V1"][1]  # cópia, sem compartilhar objetos


def test_nada_aplicado_sem_confirmacao():
    m = _mod()
    v = antigos()
    r = m.propor(v, atuais_ok())
    assert m.aplicar(v, r, []) == v
    assert m.contar_quebradas(v, atuais_ok()) == {"V1": 2, "V2": 1}


def test_aplicar_so_o_confirmado_e_so_o_guid():
    m = _mod()
    v = antigos()
    r = m.propor(v, atuais_ok())
    novo = m.aplicar(v, r, [("V1", "a1")])
    assert [e["guid"] for e in novo["V1"]] == ["n1", "a2"] and [e["guid"] for e in novo["V2"]] == ["a1"]  # V2 não confirmada
    assert {k: x for k, x in novo["V1"][0].items() if k != "guid"} == {k: x for k, x in v["V1"][0].items() if k != "guid"}
    assert m.contar_quebradas(novo, atuais_ok()) == {"V1": 1, "V2": 1}


def test_aplicar_em_lote_de_alta_zera_quebradas():
    m = _mod()
    v = antigos()
    r = m.propor(v, atuais_ok())
    novo = m.aplicar(v, r, [(e["vista"], e["guid_antigo"]) for e in r["alta"]])
    assert m.contar_quebradas(novo, atuais_ok()) == {"V1": 0, "V2": 0}


def test_baixa_so_aplica_se_confirmada_explicitamente():
    m = _mod()
    v = {"V1": [el("a1")]}
    r = m.propor(v, [el("n1", x=1.5)])
    assert m.aplicar(v, r, [(e["vista"], e["guid_antigo"]) for e in r["alta"]]) == v  # "aceitar todas as altas" não leva a baixa
    assert m.aplicar(v, r, [("V1", "a1")])["V1"][0]["guid"] == "n1"


@pytest.mark.parametrize("conf", [[("V1", "a2")], [("V9", "a1")], [("V1", "zzz")], [("V1", "a1"), ("V1", "a2")]])
def test_confirmar_orfao_ou_desconhecido_falha_sem_mudar_nada(conf):
    m = _mod()
    v = antigos()
    r = m.propor(v, [el("n1", tag="T1")])  # a2 é órfão
    v0 = copy.deepcopy(v)
    with pytest.raises(ValueError):
        m.aplicar(v, r, conf)
    assert v == v0


def test_aplicar_idempotente():
    m = _mod()
    v = antigos()
    r = m.propor(v, atuais_ok())
    conf = [(e["vista"], e["guid_antigo"]) for e in r["alta"]]
    uma = m.aplicar(v, r, conf)
    assert m.aplicar(uma, r, conf) == uma
    assert m.aplicar(uma, r, conf + conf) == uma
    assert m.propor(uma, atuais_ok()) == {"alta": [], "baixa": [], "orfaos": []}


def test_orfao_continua_visivel_na_proxima_proposta():
    m = _mod()
    v = antigos()
    a = [el("n1", tag="T1")]
    r = m.propor(v, a)
    novo = m.aplicar(v, r, [(e["vista"], e["guid_antigo"]) for e in r["alta"]])
    assert m.contar_quebradas(novo, a) == {"V1": 1, "V2": 0}
    assert [(o["vista"], o["guid_antigo"]) for o in m.propor(novo, a)["orfaos"]] == [("V1", "a2")]


# --- reforço contra mutantes vivos (tol_* bool = inválida; caixa só com exatamente 6 números) ---
def test_guid_quebrado_repetido_na_mesma_vista_entra_uma_vez():
    r = P({"V1": [el("a1"), el("a1")]}, [el("n1")])
    assert ids(r["alta"]) == [("V1", "a1", "n1")]
    r = P({"V1": [el("a1", classe="X"), el("a1", classe="X")]}, [el("n1")])
    assert len(r["orfaos"]) == 1


def test_tolerancia_zero_e_iguais_sao_validas():
    v = {"V1": [el("a1")]}
    assert ids(P(v, [el("n1")], tol_alta=0.0, tol_baixa=0.0)["alta"]) == [("V1", "a1", "n1")]
    assert ids(P(v, [el("n1", x=1.0)], tol_alta=1.0, tol_baixa=1.0)["alta"]) == [("V1", "a1", "n1")]
    with pytest.raises(ValueError):
        P(v, [el("n1")], tol_alta=True)


@pytest.mark.parametrize("ruim", [(0, 0, 0, 1, 1, 1, 9), (0, 0, 0, 1, 1)])
def test_caixa_com_tamanho_errado_e_invalida(ruim):
    r = P({"V1": [el("a1", caixa=ruim)]}, [el("n1")])
    assert r["orfaos"] == [{"vista": "V1", "guid_antigo": "a1", "motivo": "caixa_invalida"}]


@pytest.mark.parametrize("novo", [(0, 0, 0, 3, 1, 1), (0, 0, 0, 1, 3, 1), (0, 0, 0, 1, 1, 3), (0, 1, 0, 1, 2, 1), (0, 0, 1, 1, 1, 2)])
def test_distancia_usa_centros_nos_tres_eixos(novo):
    r = P({"V1": [el("a1")]}, [el("n1", caixa=novo)])
    assert ids(r["baixa"]) == [("V1", "a1", "n1")] and r["alta"] == []


def test_baixa_e_orfaos_ordenados_dentro_da_vista():
    v = {"V1": [el("a3", tag="T3", x=0.0), el("a1", tag="T1", x=10.0), el("a2", tag="T2", x=20.0), el("b2", tag="Q2", x=30.0), el("b1", tag="Q1", x=40.0)]}
    a = [el("n3", tag="T3", x=1.0), el("n1", tag="T1", x=11.0), el("n2", tag="T2", x=21.0)]
    r = P(v, a)
    assert [e["guid_antigo"] for e in r["baixa"]] == ["a1", "a2", "a3"]
    assert [e["guid_antigo"] for e in r["orfaos"]] == ["b1", "b2"]
