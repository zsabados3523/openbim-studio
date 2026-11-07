# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da tarefa F0-S06-T15a: peças finas e de acabamento fora da planta por padrão.
Cartão: cards/F0-S06/F0-S06-T15a-pecas-finas.md.

CONTRATO:
1. `CATEGORIAS_PADRAO_PLANTA_OCULTAS` definida em `app/openbim_app/desenho/selecao.py` como tupla:
   ("IfcMember", "IfcPlate", "IfcMechanicalFastener", "IfcRailing").
2. Em `app/openbim_app/desenho/planta.py`:
   `gerar_planta(ifc, gid_vista, *, categorias_ocultas=(), ocultar_secundarias=True, ...)`
   Quando `ocultar_secundarias=True` (padrão), `gerar_planta` combina `categorias_ocultas` com
   `CATEGORIAS_PADRAO_PLANTA_OCULTAS` para a seleção.
   Quando `ocultar_secundarias=False`, usa apenas `categorias_ocultas`.
3. `selecao.selecionar(ifc, gid_vista, *, categorias_ocultas=(), ...)` permanece inalterado
   em seu comportamento padrão para garantir total retrocompatibilidade com a T07a.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app.desenho import planta, selecao

SECUNDARIAS_ESPERADAS = ("IfcMember", "IfcPlate", "IfcMechanicalFastener", "IfcRailing")


def _modelo_sintetico_t15a(schema: str = "IFC4"):
    """Cria modelo sintético com pavimento e 5 elementos com geometria SweptSolid cruzando z=1.2:
    parede (IfcWall), montante (IfcMember), chapa (IfcPlate), parafuso (IfcMechanicalFastener) e
    guarda-corpo (IfcRailing).
    """
    exigir()
    f, pavs = X.estrutura(schema)
    parede = X.caixa(f, "IfcWall", "parede", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    montante = X.caixa(f, "IfcMember", "montante", 3.0, 0.0, 0.0, 0.1, 0.1, 2.0)
    chapa = X.caixa(f, "IfcPlate", "chapa", 4.0, 0.0, 0.0, 0.5, 0.02, 2.0)
    parafuso = X.caixa(f, "IfcMechanicalFastener", "parafuso", 5.0, 0.0, 0.0, 0.05, 0.05, 2.0)
    guardacorpo = X.caixa(f, "IfcRailing", "guardacorpo", 6.0, 0.0, 0.0, 1.0, 0.1, 2.0)

    X.conter(f, pavs[0], parede, montante, chapa, parafuso, guardacorpo)
    gid = X.vista(f, "PLANTA", pavs[0], nome=f"V_T15a_{schema}")
    elementos = {
        "IfcWall": parede,
        "IfcMember": montante,
        "IfcPlate": chapa,
        "IfcMechanicalFastener": parafuso,
        "IfcRailing": guardacorpo,
    }
    return f, gid, pavs[0], elementos


def test_constante_categorias_padrao_definida():
    """Confere presença e tupla exata em selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS e assinaturas."""
    assert hasattr(selecao, "CATEGORIAS_PADRAO_PLANTA_OCULTAS"), (
        "selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS deve existir"
    )
    c = selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS
    assert isinstance(c, tuple), (
        f"CATEGORIAS_PADRAO_PLANTA_OCULTAS deve ser tupla, recebido: {type(c)}"
    )
    assert c == SECUNDARIAS_ESPERADAS, (
        f"CATEGORIAS_PADRAO_PLANTA_OCULTAS esperada {SECUNDARIAS_ESPERADAS}, obtida {c}"
    )

    # Assinatura de gerar_planta: ocultar_secundarias deve ser keyword-only com default True
    sig = inspect.signature(planta.gerar_planta)
    assert "ocultar_secundarias" in sig.parameters, (
        "gerar_planta deve declarar o parâmetro ocultar_secundarias"
    )
    param_sec = sig.parameters["ocultar_secundarias"]
    assert param_sec.default is True, (
        f"ocultar_secundarias deve ter default True, obtido: {param_sec.default!r}"
    )
    assert param_sec.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"ocultar_secundarias deve ser keyword-only (*), obtido: {param_sec.kind}"
    )

    # Retrocompatibilidade da assinatura de selecao.selecionar: NÃO possui ocultar_secundarias
    sig_sel = inspect.signature(selecao.selecionar)
    assert "ocultar_secundarias" not in sig_sel.parameters, (
        "selecao.selecionar não deve receber ocultar_secundarias (contrato T07a inalterado)"
    )


def test_gerar_planta_oculta_pecas_finas_por_padrao():
    """Chama gerar_planta por padrão (ocultar_secundarias=True implícito): parede desenhada no SVG,
    peças finas fora do SVG e de selecao.ids, presentes em selecao.ocultos_por_classe.
    """
    f, gid, _pav, elementos = _modelo_sintetico_t15a()
    p = planta.gerar_planta(f, gid, executor=local.executar)

    parede = elementos["IfcWall"]
    assert p.selecao.ids == (parede.id(),), (
        f"Apenas a parede deveria ser selecionada por padrão, recebido: {p.selecao.ids}"
    )
    g_parede = B.grupo(p.svg, parede.GlobalId)
    assert g_parede is not None, "Parede deve estar presente no SVG"
    assert len(B.subcaminhos(g_parede)) > 0, "Parede deve ter traçados geométricos no SVG"
    assert parede.GlobalId in p.svg
    assert p.n_paths > 0

    for cls in SECUNDARIAS_ESPERADAS:
        elem = elementos[cls]
        assert elem.id() not in p.selecao.ids, f"{cls} não deve estar em selecao.ids"
        assert elem.GlobalId not in p.svg, f"{cls} não deve estar no SVG"
        assert B.grupo(p.svg, elem.GlobalId) is None, f"{cls} não deve ter grupo no SVG"
        assert p.selecao.ocultos_por_classe.get(cls) == 1, (
            f"{cls} deve constar com contagem 1 em ocultos_por_classe"
        )

    assert p.selecao.ocultos_por_classe == {cls: 1 for cls in SECUNDARIAS_ESPERADAS}
    assert "IfcWall" not in p.selecao.ocultos_por_classe
    assert p.selecao.sem_geometria == 0


def test_gerar_planta_com_ocultar_secundarias_falso():
    """Com ocultar_secundarias=False, todas as peças finas permanecem em selecao.ids e são desenhadas no SVG."""
    f, gid, _pav, elementos = _modelo_sintetico_t15a()
    p = planta.gerar_planta(f, gid, ocultar_secundarias=False, executor=local.executar)

    esperados_ids = {e.id() for e in elementos.values()}
    assert set(p.selecao.ids) == esperados_ids
    assert len(p.selecao.ids) == 5

    for cls, elem in elementos.items():
        assert elem.id() in p.selecao.ids, f"{cls} deve estar em selecao.ids"
        assert elem.GlobalId in p.svg, f"{cls} deve constar no SVG"
        g = B.grupo(p.svg, elem.GlobalId)
        assert g is not None, f"{cls} deve ter grupo no SVG"
        assert len(B.subcaminhos(g)) > 0, f"{cls} deve ter traçados no SVG"

    assert p.selecao.ocultos_por_classe == {}
    assert p.n_paths >= 5


def test_gerar_planta_combina_categorias_ocultas_e_secundarias():
    """Combina categorias_ocultas customizadas (inclusive como lista ou sobreposta) com peças finas secundárias;
    e respeita apenas categorias_ocultas quando ocultar_secundarias=False.
    """
    f, gid, _pav, elementos = _modelo_sintetico_t15a()

    # 1. Combinadas com tupla e ocultar_secundarias=True explícito
    p_tupla = planta.gerar_planta(
        f,
        gid,
        categorias_ocultas=("IfcWall",),
        ocultar_secundarias=True,
        executor=local.executar,
    )
    assert p_tupla.selecao.ids == (), "Todos os elementos devem estar ocultos"
    assert p_tupla.n_paths == 0
    esperado_todos_ocultos = {"IfcWall": 1, **{cls: 1 for cls in SECUNDARIAS_ESPERADAS}}
    assert p_tupla.selecao.ocultos_por_classe == esperado_todos_ocultos

    # 2. Combinadas passando lista e ocultar_secundarias omitido (default True deve combinar sem erro de tipo)
    p_lista = planta.gerar_planta(
        f,
        gid,
        categorias_ocultas=["IfcWall"],
        executor=local.executar,
    )
    assert p_lista.selecao.ids == (), "Com default ocultar_secundarias=True e lista, tudo deve estar oculto"
    assert p_lista.selecao.ocultos_por_classe == esperado_todos_ocultos
    assert p_lista.n_paths == 0

    # 3. Sobreposição de categoria já presente nas secundárias (não deve duplicar contagem nem quebrar)
    p_sobreposta = planta.gerar_planta(
        f,
        gid,
        categorias_ocultas=["IfcWall", "IfcMember"],
        ocultar_secundarias=True,
        executor=local.executar,
    )
    assert p_sobreposta.selecao.ids == ()
    assert p_sobreposta.selecao.ocultos_por_classe == esperado_todos_ocultos

    # 4. Quando ocultar_secundarias=False com IfcWall: apenas IfcWall oculta, 4 secundárias desenhadas
    p_sem_sec = planta.gerar_planta(
        f,
        gid,
        categorias_ocultas=["IfcWall"],
        ocultar_secundarias=False,
        executor=local.executar,
    )
    parede = elementos["IfcWall"]
    assert parede.id() not in p_sem_sec.selecao.ids
    assert parede.GlobalId not in p_sem_sec.svg
    assert p_sem_sec.selecao.ocultos_por_classe == {"IfcWall": 1}

    for cls in SECUNDARIAS_ESPERADAS:
        elem = elementos[cls]
        assert elem.id() in p_sem_sec.selecao.ids
        assert elem.GlobalId in p_sem_sec.svg
        assert B.grupo(p_sem_sec.svg, elem.GlobalId) is not None

    # 5. Quando ocultar_secundarias=False mas chamador pede explicitamente uma secundária (IfcMember):
    # apenas IfcMember deve ser ocultada; IfcWall, IfcPlate, IfcMechanicalFastener, IfcRailing continuam
    p_so_membro = planta.gerar_planta(
        f,
        gid,
        categorias_ocultas=["IfcMember"],
        ocultar_secundarias=False,
        executor=local.executar,
    )
    assert p_so_membro.selecao.ocultos_por_classe == {"IfcMember": 1}
    assert elementos["IfcMember"].id() not in p_so_membro.selecao.ids
    for cls in ("IfcWall", "IfcPlate", "IfcMechanicalFastener", "IfcRailing"):
        elem = elementos[cls]
        assert elem.id() in p_so_membro.selecao.ids
        assert B.grupo(p_so_membro.svg, elem.GlobalId) is not None


def test_selecao_pura_retrocompativel():
    """selecao.selecionar pura mantém comportamento idêntico ao T07a sem ocultar peças secundárias por padrão."""
    for esq in ("IFC4", "IFC2X3"):
        f, gid, pav, elementos = _modelo_sintetico_t15a(esq)

        s = selecao.selecionar(f, gid)
        esperados_ids = {e.id() for e in elementos.values()}
        assert set(s.ids) == esperados_ids
        assert len(s.ids) == 5
        assert s.ocultos_por_classe == {}
        assert s.tipo == "PLANTA"
        assert s.pavimento == pav.id()
        assert s.sem_geometria == 0

        # Ocultação explícita pontual em selecao.selecionar só oculta o solicitado (inclusive via lista)
        s_membro = selecao.selecionar(f, gid, categorias_ocultas=["IfcMember"])
        assert s_membro.ocultos_por_classe == {"IfcMember": 1}
        assert elementos["IfcMember"].id() not in s_membro.ids
        for cls in ("IfcWall", "IfcPlate", "IfcMechanicalFastener", "IfcRailing"):
            assert elementos[cls].id() in s_membro.ids
