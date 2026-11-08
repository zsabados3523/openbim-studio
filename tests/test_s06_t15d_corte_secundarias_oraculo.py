# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15d: peças finas e acabamento fora do corte vertical por padrão.
Cartão: docs/state/cards/F0-S06/F0-S06-T15d-culling-corte.md.

CONTRATO:
1. Em `app/openbim_app/desenho/corte.py`:
   `gerar_corte(ifc, gid_vista, *, categorias_ocultas=(), ocultar_secundarias=True, ...)`
   - Parâmetro keyword-only `ocultar_secundarias: bool = True`.
   - Quando `ocultar_secundarias=True` (padrão), combina `categorias_ocultas` com
     `selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS` ("IfcMember", "IfcPlate", "IfcMechanicalFastener", "IfcRailing").
   - Quando `ocultar_secundarias=False`, usa apenas `tuple(categorias_ocultas)`.
   - Repassa a combinação final de categorias para `selecao.selecionar`.
2. Em `app/openbim_app/desenho/selecao.py`:
   - Rota CORTE: elementos pertencentes a `categorias_ocultas` são contados em `ocultos_por_classe`
     e NÃO entram em `visiveis_com_rep`.
   - Elementos ocultos não são enviados para cálculo de caixas envolventes (`op: caixas`) nem entram em `ids`.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401 (fixture autouse e guarda)

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app import vistas_ifc
from openbim_app.desenho import corte, selecao

SECUNDARIAS_ESPERADAS = ("IfcMember", "IfcPlate", "IfcMechanicalFastener", "IfcRailing")


def _criar_corte(f: Any, nome: str = "Corte_T15d", origem=(-0.5, 0.0, -0.5), tamanho=(7.0, 4.5, 6.0)) -> str:
    """Cria vista CORTE com vistas_ifc.criar_vista voltada para +Y cortando em Y=0."""
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:100", origem=origem, tamanho=tamanho)
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -tamanho[2]))
    return gid


def _modelo_sintetico_corte(schema: str = "IFC4"):
    """Cria modelo sintético com pavimento e 5 elementos cruzando o plano de corte (Y=0) e profundidade (Y>0):
    parede (IfcWall), montante (IfcMember), chapa (IfcPlate), parafuso (IfcMechanicalFastener) e
    guarda-corpo (IfcRailing).
    """
    exigir()
    f, pavs = X.estrutura(schema)
    parede = X.caixa(f, "IfcWall", "parede", 0.5, -0.1, 0.0, 1.0, 0.2, 2.0)
    montante = X.caixa(f, "IfcMember", "montante", 2.0, -0.1, 0.0, 0.2, 0.2, 2.0)
    chapa = X.caixa(f, "IfcPlate", "chapa", 2.5, -0.1, 0.0, 0.5, 0.2, 2.0)
    parafuso = X.caixa(f, "IfcMechanicalFastener", "parafuso", 3.5, -0.1, 0.0, 0.1, 0.2, 0.1)
    guardacorpo = X.caixa(f, "IfcRailing", "guardacorpo", 4.0, -0.1, 0.0, 1.0, 0.2, 1.0)

    X.conter(f, pavs[0], parede, montante, chapa, parafuso, guardacorpo)
    gid = _criar_corte(f, f"Corte_T15d_{schema}")
    elementos = {
        "IfcWall": parede,
        "IfcMember": montante,
        "IfcPlate": chapa,
        "IfcMechanicalFastener": parafuso,
        "IfcRailing": guardacorpo,
    }
    return f, gid, pavs[0], elementos


def test_assinatura_gerar_corte_ocultar_secundarias():
    """Inspeciona assinatura de corte.gerar_corte: ocultar_secundarias é keyword-only com default True."""
    assert hasattr(selecao, "CATEGORIAS_PADRAO_PLANTA_OCULTAS"), (
        "selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS deve existir"
    )
    assert selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS == SECUNDARIAS_ESPERADAS, (
        f"CATEGORIAS_PADRAO_PLANTA_OCULTAS esperada {SECUNDARIAS_ESPERADAS}, "
        f"obtida {selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS}"
    )

    sig = inspect.signature(corte.gerar_corte)
    assert "ocultar_secundarias" in sig.parameters, (
        "corte.gerar_corte deve declarar o parâmetro ocultar_secundarias"
    )
    param = sig.parameters["ocultar_secundarias"]
    assert param.default is True, (
        f"ocultar_secundarias deve ter default True, obtido: {param.default!r}"
    )
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"ocultar_secundarias deve ser keyword-only (*), obtido: {param.kind}"
    )
    assert param.annotation in (bool, "bool"), (
        f"ocultar_secundarias deve ter tipo bool, obtido: {param.annotation}"
    )

    sig_sel = inspect.signature(selecao.selecionar)
    assert "ocultar_secundarias" not in sig_sel.parameters, (
        "selecao.selecionar não deve receber ocultar_secundarias (contrato T07a inalterado)"
    )


def test_gerar_corte_oculta_pecas_finas_por_padrao():
    """Por padrão (ocultar_secundarias=True implícito), parede é gerada no SVG e em c.selecao.ids;
    peças finas (IfcMember, IfcPlate, IfcMechanicalFastener, IfcRailing) ficam fora do SVG e de c.selecao.ids,
    constando em c.selecao.ocultos_por_classe.
    """
    f, gid, _pav, elementos = _modelo_sintetico_corte("IFC4")
    c = corte.gerar_corte(f, gid, executor=local.executar)

    parede = elementos["IfcWall"]
    assert c.selecao.ids == (parede.id(),), (
        f"Apenas a parede deve estar em c.selecao.ids por padrão, obtido: {c.selecao.ids}"
    )
    assert parede.GlobalId in c.svg, "Parede deve constar no SVG"
    g_parede = B.grupo(c.svg, parede.GlobalId)
    assert g_parede is not None, "Parede deve ter grupo no SVG"
    assert len(B.subcaminhos(g_parede)) > 0, "Parede deve ter traçados no SVG"
    assert c.n_paths > 0

    for cls in SECUNDARIAS_ESPERADAS:
        elem = elementos[cls]
        assert elem.id() not in c.selecao.ids, f"{cls} não deve estar em c.selecao.ids"
        assert elem.GlobalId not in c.svg, f"{cls} não deve estar no SVG"
        assert B.grupo(c.svg, elem.GlobalId) is None, f"{cls} não deve ter grupo no SVG"
        assert c.selecao.ocultos_por_classe.get(cls) == 1, (
            f"{cls} deve constar com contagem 1 em ocultos_por_classe"
        )

    assert c.selecao.ocultos_por_classe == {cls: 1 for cls in SECUNDARIAS_ESPERADAS}
    assert "IfcWall" not in c.selecao.ocultos_por_classe
    assert c.selecao.sem_geometria == 0


def test_gerar_corte_com_ocultar_secundarias_falso():
    """Com ocultar_secundarias=False, todas as peças secundárias constam em c.selecao.ids e são geradas."""
    f, gid, _pav, elementos = _modelo_sintetico_corte("IFC4")
    c = corte.gerar_corte(f, gid, ocultar_secundarias=False, executor=local.executar)

    esperados_ids = {e.id() for e in elementos.values()}
    assert set(c.selecao.ids) == esperados_ids
    assert len(c.selecao.ids) == 5

    for cls, elem in elementos.items():
        assert elem.id() in c.selecao.ids, f"{cls} deve constar em c.selecao.ids"
        assert elem.GlobalId in c.svg, f"{cls} deve constar no SVG"
        g = B.grupo(c.svg, elem.GlobalId)
        assert g is not None, f"{cls} deve ter grupo no SVG"
        assert len(B.subcaminhos(g)) > 0, f"{cls} deve ter traçados no SVG"

    assert c.selecao.ocultos_por_classe == {}
    assert c.n_paths >= 5


def test_gerar_corte_combina_categorias_ocultas_e_secundarias():
    """Combina categorias_ocultas com peças finas secundárias quando ocultar_secundarias=True;
    respeita apenas categorias_ocultas quando ocultar_secundarias=False.
    """
    f, gid, _pav, elementos = _modelo_sintetico_corte("IFC4")
    esperado_todos_ocultos = {"IfcWall": 1, **{cls: 1 for cls in SECUNDARIAS_ESPERADAS}}

    # 1. categorias_ocultas como tupla com ocultar_secundarias=True explícito
    c_tupla = corte.gerar_corte(
        f,
        gid,
        categorias_ocultas=("IfcWall",),
        ocultar_secundarias=True,
        executor=local.executar,
    )
    assert c_tupla.selecao.ids == (), "Todos os elementos devem estar ocultos"
    assert c_tupla.n_paths == 0
    assert c_tupla.selecao.ocultos_por_classe == esperado_todos_ocultos
    assert not any(e.GlobalId in c_tupla.svg for e in elementos.values())

    # 2. categorias_ocultas como lista com ocultar_secundarias omitido (default True)
    c_lista = corte.gerar_corte(
        f,
        gid,
        categorias_ocultas=["IfcWall"],
        executor=local.executar,
    )
    assert c_lista.selecao.ids == (), "Com default True e lista, todos devem estar ocultos"
    assert c_lista.selecao.ocultos_por_classe == esperado_todos_ocultos
    assert c_lista.n_paths == 0
    assert not any(e.GlobalId in c_lista.svg for e in elementos.values())

    # 3. categorias_ocultas como conjunto (set) com ocultar_secundarias=True
    c_set = corte.gerar_corte(
        f,
        gid,
        categorias_ocultas={"IfcWall"},
        ocultar_secundarias=True,
        executor=local.executar,
    )
    assert c_set.selecao.ids == (), "Com default True e set, todos devem estar ocultos"
    assert c_set.selecao.ocultos_por_classe == esperado_todos_ocultos
    assert c_set.n_paths == 0

    # 4. Sobreposição de categoria secundária em categorias_ocultas
    c_sobreposta = corte.gerar_corte(
        f,
        gid,
        categorias_ocultas=["IfcWall", "IfcMember"],
        ocultar_secundarias=True,
        executor=local.executar,
    )
    assert c_sobreposta.selecao.ids == ()
    assert c_sobreposta.selecao.ocultos_por_classe == esperado_todos_ocultos

    # 5. ocultar_secundarias=False com IfcWall: apenas parede oculta, 4 secundárias geradas
    c_sem_sec = corte.gerar_corte(
        f,
        gid,
        categorias_ocultas=["IfcWall"],
        ocultar_secundarias=False,
        executor=local.executar,
    )
    parede = elementos["IfcWall"]
    assert parede.id() not in c_sem_sec.selecao.ids
    assert parede.GlobalId not in c_sem_sec.svg
    assert c_sem_sec.selecao.ocultos_por_classe == {"IfcWall": 1}

    for cls in SECUNDARIAS_ESPERADAS:
        elem = elementos[cls]
        assert elem.id() in c_sem_sec.selecao.ids
        assert elem.GlobalId in c_sem_sec.svg
        g = B.grupo(c_sem_sec.svg, elem.GlobalId)
        assert g is not None
        assert len(B.subcaminhos(g)) > 0

    # 6. ocultar_secundarias=False com IfcMember: apenas IfcMember oculta, restantes geradas
    c_so_membro = corte.gerar_corte(
        f,
        gid,
        categorias_ocultas=["IfcMember"],
        ocultar_secundarias=False,
        executor=local.executar,
    )
    assert c_so_membro.selecao.ocultos_por_classe == {"IfcMember": 1}
    assert elementos["IfcMember"].id() not in c_so_membro.selecao.ids
    assert elementos["IfcMember"].GlobalId not in c_so_membro.svg
    for cls in ("IfcWall", "IfcPlate", "IfcMechanicalFastener", "IfcRailing"):
        elem = elementos[cls]
        assert elem.id() in c_so_membro.selecao.ids
        assert elem.GlobalId in c_so_membro.svg
        g = B.grupo(c_so_membro.svg, elem.GlobalId)
        assert g is not None
        assert len(B.subcaminhos(g)) > 0


def test_selecao_corte_ignora_secundarias_antes_de_caixas():
    """Chama selecao.selecionar com categorias_ocultas=CATEGORIAS_PADRAO_PLANTA_OCULTAS.
    Verifica que elementos secundários constam em ocultos_por_classe, fora de ids,
    não constam em sessao._caixas e NÃO são enviados para cálculo de caixas envolventes (op == 'caixas').
    """
    f, gid, _pav, elementos = _modelo_sintetico_corte("IFC4")
    chamadas_executor = []

    def executor_espiao(pedido):
        chamadas_executor.append(pedido)
        return local.executar(pedido)

    sessao = selecao.SessaoSelecao()
    sel = selecao.selecionar(
        f,
        gid,
        categorias_ocultas=selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS,
        sessao=sessao,
        executor=executor_espiao,
    )

    parede = elementos["IfcWall"]
    assert sel.ids == (parede.id(),), f"Apenas a parede deve estar em sel.ids, obtido: {sel.ids}"
    assert sel.ocultos_por_classe == {cls: 1 for cls in SECUNDARIAS_ESPERADAS}

    for cls in SECUNDARIAS_ESPERADAS:
        elem_id = elementos[cls].id()
        assert elem_id not in sel.ids, f"{cls} não deve estar em sel.ids"
        assert elem_id not in sessao._caixas, f"{cls} não deve ser guardada em sessao._caixas"

    # Confere que nenhuma peça secundária foi enviada na requisição de caixas
    pedidos_caixas = [p for p in chamadas_executor if p.get("op") == "caixas"]
    ids_pedidos_caixas = {item[0] for p in pedidos_caixas for item in p.get("elementos", [])}
    for cls in SECUNDARIAS_ESPERADAS:
        assert elementos[cls].id() not in ids_pedidos_caixas, (
            f"{cls} (id {elementos[cls].id()}) foi indevidamente solicitada para cálculo de caixas"
        )
    assert parede.id() in ids_pedidos_caixas, "Parede deveria ter sua caixa calculada"
    assert parede.id() in sessao._caixas, "Parede deveria estar armazenada na sessao"
