# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e2: `selecionar` em CORTE pelo auxiliar (op `caixas`). Especificação: `cards/F0-S06/F0-S06-T07e-especificacao.md` (§2, §4, §5 casos 7 e 10).
Não editar este arquivo na implementação; quem tira os `@AINDA_NAO_E2` (xfail estrito) é o autor do oráculo, em commit próprio, depois da e2.
CONTRATO: `selecionar(ifc, gid, *, categorias_ocultas=(), pavimento=None, executor=None, limite_s=LIMITE_PADRAO_S, cancelar=None)`. CORTE: o pai monta os candidatos (todo IfcElement
com Representation e de classe não oculta) e a faixa, faz `auxiliar.preparar(ifc, {"op": "caixas", "elementos": [[id, GlobalId], ...]})` + `auxiliar.executar(p, limite_s=, cancelar=,
executor=)` (1 pedido, `fechar()` no fim) e filtra `caixas_envolventes` pela faixa em intervalo FECHADO; `falhas_geometria` = as do auxiliar (ordenadas). PLANTA nunca chama o executor.
Erro do auxiliar (`AuxiliarCaiu`, `FalhaNoAuxiliar`, `DesenhoCancelado`, ...) sobe como está. `selecao.py` não contém `ifcopenshell.geom`, `.iterator(` nem `import os`.
Constantes abaixo = resultado do caminho antigo (iterator no pai), gravado em 02/11 sobre `s06_t07e_aux.modelo(...)` (ids STEP determinísticos)."""
import re
from pathlib import Path

import pytest
import s06_t07e_aux as T
from test_s06_t07e_auxiliar_oraculo import _loc, _x, tmp_aux  # noqa: F401

AINDA_NAO_E2 = pytest.mark.xfail(strict=True, raises=TypeError, reason="T07e2: selecionar ainda não aceita `executor` (CORTE ainda usa ifcopenshell.geom no pai)")
AINDA_NAO_E2_TEXTO = pytest.mark.xfail(strict=True, raises=AssertionError, reason="T07e2: selecao.py ainda tem geometria no pai")
SELECAO = Path(__file__).resolve().parent.parent / "app" / "openbim_app" / "desenho" / "selecao.py"
# (esq, off, base, k) -> (ids, falhas, faixa) do caminho antigo
ANTIGO = {0: ((32, 45, 71), (58,), ((324550.0, 7405472.0, -0.5), (324560.0, 7405476.0, 3.5))),
          1: ((37, 50, 76), (63,), ((0.0, -1.0, -0.5), (10.0, 3.0, 3.5))),
          2: ((32, 45, 71), (58,), ((0.0, -1.0, -2.0), (10.0, 3.0, 2.0)))}
EXATO = ((0.0, -1.0, -0.5), (10.0, 3.0, 3.5))  # faixa de `T.modelo()` (IFC4, sem deslocamento)


def _s():
    import obim_geometria.local  # noqa: F401
    from openbim_app.desenho import selecao
    return selecao


def _fake(caixas, falhas=(), visto=None):
    def executor(pedido):
        if visto is not None:
            visto.append(pedido)
        return {"ok": True, "caixas_envolventes": {str(k): v for k, v in caixas.items()}, "falhas_geometria": list(falhas)}
    return executor


@AINDA_NAO_E2
@pytest.mark.parametrize("i", [0, 1, 2])
def test_a_corte_pede_caixas_e_da_o_mesmo_resultado_do_caminho_antigo(tmp_aux, i):
    S, L = _s(), _loc()
    f, d = T.modelo(*T.MODELOS[i])
    pedidos = []

    def espiao(pedido):
        pedidos.append(pedido)
        return L.executar(pedido)
    s = S.selecionar(f, d["vc"], executor=espiao)
    ids, falhas, faixa = ANTIGO[i]
    assert s.ids == ids and s.falhas_geometria == falhas and s.tipo == "CORTE" and s.sem_geometria == 0 and s.ocultos_por_classe == {}
    assert s.faixa == (pytest.approx(faixa[0], abs=1e-9), pytest.approx(faixa[1], abs=1e-9))
    assert len(pedidos) == 1 and pedidos[0]["op"] == "caixas"  # um pedido só, op `caixas`
    assert sorted(i_ for i_, _ in pedidos[0]["elementos"]) == [d[n].id() for n in ("P", "M", "falha", "Q")]
    assert all(g == f.by_id(i_).GlobalId for i_, g in pedidos[0]["elementos"]) and not list(tmp_aux.glob("obim-desenho-*"))


@AINDA_NAO_E2
def test_a_categoria_oculta_nao_vai_ao_auxiliar_e_conta(tmp_aux):
    S, L = _s(), _loc()
    f, d = T.modelo()
    pedidos = []
    s = S.selecionar(f, d["vc"], categorias_ocultas=("IfcWall",), executor=_fake({d["M"].id(): [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]}, visto=pedidos))
    assert [i for i, _ in pedidos[0]["elementos"]] == [d["M"].id()] and s.ids == (d["M"].id(),) and s.ocultos_por_classe == {"IfcWall": 3} and s.falhas_geometria == ()


@AINDA_NAO_E2
def test_b_planta_nunca_pede_geometria(tmp_aux):
    S = _s()
    f, d = T.modelo()

    def proibido(pedido):
        raise AssertionError("PLANTA chamou o executor")
    s = S.selecionar(f, d["vp"], executor=proibido)
    assert s.tipo == "PLANTA" and s.ids == tuple(sorted(d[n].id() for n in ("P", "M", "falha"))) and s.falhas_geometria == () and s.faixa is None


@AINDA_NAO_E2_TEXTO
def test_c_selecao_sem_geometria_no_pai():
    txt = SELECAO.read_text(encoding="utf-8")
    proibidos = [t for t in ("ifcopenshell.geom", ".iterator(", "os.cpu_count", "ifcopenshell_wrapper", "serializers") if t in txt]
    assert not proibidos and not re.search(r"^\s*(import os|from os\b)", txt, re.M), proibidos


@AINDA_NAO_E2
def test_d_faixa_fechada_nos_limites_exatos(tmp_aux):
    S = _s()
    f, d = T.modelo()
    (x0, y0, z0), (x1, y1, z1) = EXATO
    e = 1 / 64
    cx = {d["P"].id(): [x1, y1, z1, x1 + 1, y1 + 1, z1 + 1],  # encosta só no canto máximo: entra
          d["M"].id(): [x0 - 1, y0 - 1, z0 - 1, x0, y0, z0],  # encosta só no canto mínimo: entra
          d["Q"].id(): [x1 + e, 0.0, 0.0, x1 + 1, 1.0, 1.0]}  # 1/64 m fora em X: sai
    s = S.selecionar(f, d["vc"], executor=_fake(cx))
    assert s.ids == tuple(sorted((d["P"].id(), d["M"].id()))) and s.faixa == (EXATO[0], EXATO[1])
    for eixo in range(3):  # 1/64 fora em cada face (mínima e máxima): sai
        for lado in (0, 1):
            c = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
            c[eixo], c[eixo + 3] = (EXATO[1][eixo] + e, EXATO[1][eixo] + 1) if lado else (EXATO[0][eixo] - 1, EXATO[0][eixo] - e)
            assert S.selecionar(f, d["vc"], executor=_fake({d["P"].id(): c})).ids == (), (eixo, lado)


@AINDA_NAO_E2
def test_e_falhas_do_auxiliar_entram_no_resultado(tmp_aux):
    S = _s()
    f, d = T.modelo()
    ordem = [d["Q"].id(), d["falha"].id()]
    s = S.selecionar(f, d["vc"], executor=_fake({d["P"].id(): [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]}, falhas=ordem))
    assert s.falhas_geometria == tuple(sorted(ordem)) and s.ids == (d["P"].id(),)  # falha não entra em ids; ordenada


@AINDA_NAO_E2
def test_f_erro_do_auxiliar_sobe_sem_mascara(tmp_aux):
    S, X = _s(), _x()
    f, d = T.modelo()

    def caiu(pedido):
        raise X.AuxiliarCaiu(3, "geometria")
    with pytest.raises(X.AuxiliarCaiu) as e:
        S.selecionar(f, d["vc"], executor=caiu)
    assert e.value.codigo_saida == 3
    erro = lambda tipo: (lambda pedido: {"ok": False, "erro": {"tipo": tipo, "mensagem": "xyz", "rastro": "r"}})  # noqa: E731
    with pytest.raises(X.FalhaNoAuxiliar, match="RuntimeError: xyz"):
        S.selecionar(f, d["vc"], executor=erro("RuntimeError"))
    with pytest.raises(X.ArquivoDivergente):
        S.selecionar(f, d["vc"], executor=erro("ArquivoDivergente"))
    import threading
    ev = threading.Event()
    ev.set()
    with pytest.raises(X.DesenhoCancelado):
        S.selecionar(f, d["vc"], executor=_fake({}), cancelar=ev)
    assert not list(tmp_aux.glob("obim-desenho-*"))  # a cópia some mesmo no erro
