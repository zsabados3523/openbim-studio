# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07a: seleção dos elementos a desenhar (ADR-006 §3 item 0; cartão `cards/F0-S06/F0-S06-T07-divisao.md`). Não editar este arquivo
nem `tests/s06_t07_aux.py` na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio, depois da implementação.
CONTRATO `app/openbim_app/desenho/__init__.py` (vazio de lógica) e `desenho/selecao.py` (sem Qt, sem rede; lê o `ifcopenshell.file`, nunca o altera):
1. `selecionar(ifc, gid_vista, *, categorias_ocultas=(), pavimento=None) -> Selecao`. `gid_vista` = GlobalId de IfcAnnotation DRAWING (leia com
   `vistas_ifc.ler_vista`: tipo/origem/tamanho). `categorias_ocultas`: nomes de classe IFC (vale a classe e suas subclasses: "IfcFurnishingElement" tira
   IfcFurniture); nome que não existe no esquema -> `SelecaoInvalida`. `pavimento`: GlobalId de IfcBuildingStorey que vale no lugar do pavimento da vista.
2. `Selecao` = dataclass congelada (frozen) com: `ids` tuple de step ids (`entity.id()`) em ordem crescente, sem repetição; `tipo` "PLANTA"|"CORTE";
   `pavimento` step id do IfcBuildingStorey usado (None no corte sem pavimento); `faixa` None na planta, no corte ((xmin,ymin,zmin),(xmax,ymax,zmax))
   do volume de recorte NO MUNDO, EM METROS = (origem da vista + [0, tamanho]) x escala da unidade de comprimento do arquivo (`ifcopenshell.util.unit`;
   arquivo em milímetro: x 0,001; volume alinhado aos eixos; o IfcBlock nasce em 0,0,0 do posicionamento);
   `ocultos_por_classe` dict {classe concreta: quantos elementos candidatos saíram por categoria oculta}; `sem_geometria` int (candidatos sem Representation).
3. Elemento desenhável = IfcElement (inclui IfcOpeningElement) com `Representation`. Fora: IfcAnnotation, IfcSpace, sem geometria (contados).
4. PLANTA: candidatos = contidos (IfcRelContainedInSpatialStructure) no pavimento da vista, mais descendentes por IfcRelAggregates (em qualquer nível)
   dos contidos, mais as aberturas (IfcRelVoidsElement) dos candidatos e os preenchimentos dessas aberturas (IfcRelFillsElement; a porta pode nem estar
   contida em pavimento). O pavimento da vista = o IfcBuildingStorey que contém a anotação (ou `pavimento=`). Volume da vista ignorado.
   Sem pavimento resolvido, ou resolvido para algo que não é IfcBuildingStorey, ou `pavimento=` que não existe/não é pavimento: `SelecaoInvalida`.
5. CORTE: todo IfcElement com geometria, de QUALQUER pavimento, cujo bounding box NO MUNDO (ifcopenshell.geom, coordenadas de mundo em metros, precisão de
   double) cruza o volume; intervalos FECHADOS (encostar conta). Pavimento da vista é opcional (sem ele: `pavimento` None, sem erro).
6. Móveis (IfcFurnishingElement e filhos) LIGADOS por padrão. Vista de outro programa sem TargetView (tipo None), ou VistaInexistente: erro
   (`SelecaoInvalida` para tipo None; `vistas_ifc.VistaInexistente` propaga). `SelecaoInvalida` herda de ValueError.
7. Determinístico; nenhuma tolerância absoluta pequena (modelo a 324 mil / 7,4 milhões do zero); não depende de cota 0.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import dataclasses

import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="F0-S06-T07a: openbim_app.desenho.selecao ainda não existe")
MOD = pytest.mark.parametrize("esq,off,base", X.MODELOS)


def S():
    exigir()
    import openbim_app.desenho.selecao as S_
    return S_


# ---------- planta ----------
@AINDA_NAO
@MOD
def test_planta_so_do_pavimento_da_vista(esq, off, base):
    exigir()
    f, pavs, esperado = X.casa(esq, off, base)
    S_ = S()
    for i in (0, 1):  # térreo e superior: cada um só com o seu conteúdo (aberturas e portas ligadas, peças de conjunto em 2 níveis)
        g = X.vista(f, "PLANTA", pavs[i], nome=f"V{i}", origem=(off[0], off[1], base + 3.0 * i + 1.2))
        s = S_.selecionar(f, g)
        assert X.nomes(f, s) == esperado[i]
        assert s.tipo == "PLANTA" and s.pavimento == pavs[i].id() and s.faixa is None
        assert s.sem_geometria == 3 and s.ocultos_por_classe == {}
        assert not any(f.by_id(j).is_a("IfcAnnotation") for j in s.ids)


@AINDA_NAO
def test_planta_ignora_volume_da_vista():
    exigir()
    f, pavs, esperado = X.casa("IFC4", X.GEO, 0.0)
    g = X.vista(f, "PLANTA", pavs[0], origem=(0.0, 0.0, 99.0), tamanho=(0.5, 0.5, 0.5))
    assert X.nomes(f, S().selecionar(f, g)) == esperado[0]


@AINDA_NAO
def test_ids_ordenados_deterministicos_e_congelados():
    exigir()
    f, pavs, _ = X.casa("IFC4")
    g = X.vista(f, "PLANTA", pavs[0])
    a, b = S().selecionar(f, g), S().selecionar(f, g)
    assert a == b and a.ids == tuple(sorted(set(a.ids))) and all(f.by_id(i).is_a("IfcElement") for i in a.ids)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.ids = ()


@AINDA_NAO
def test_pavimento_explicito_vale_no_lugar_do_da_vista():
    exigir()
    f, pavs, esperado = X.casa("IFC2X3")
    g = X.vista(f, "PLANTA", pavs[0])
    assert X.nomes(f, S().selecionar(f, g, pavimento=pavs[1].GlobalId)) == esperado[1]
    g2 = X.vista(f, "PLANTA", None, nome="solta")  # sem pavimento próprio, com pavimento= explícito
    assert X.nomes(f, S().selecionar(f, g2, pavimento=pavs[0].GlobalId)) == esperado[0]


# ---------- interruptor por categoria ----------
@AINDA_NAO
@MOD
def test_moveis_ligados_por_padrao_e_oculta_so_a_categoria(esq, off, base):
    exigir()
    f, pavs, esperado = X.casa(esq, off, base)
    g = X.vista(f, "PLANTA", pavs[0])
    assert "M0" in X.nomes(f, S().selecionar(f, g))
    s = S().selecionar(f, g, categorias_ocultas=("IfcFurnishingElement",))
    assert X.nomes(f, s) == esperado[0] - {"M0"} and s.ocultos_por_classe == {X.MOVEL[esq]: 1}
    s = S().selecionar(f, g, categorias_ocultas=("IfcWindow", "IfcDoor"))
    assert X.nomes(f, s) == esperado[0] - {"W0", "D0"} and s.ocultos_por_classe == {"IfcWindow": 1, "IfcDoor": 1}
    s = S().selecionar(f, X.vista(f, "PLANTA", pavs[1], nome="V1"), categorias_ocultas=("IfcSlab", "IfcCovering"))  # só conta o que existe
    assert s.ocultos_por_classe == {"IfcSlab": 1}


@AINDA_NAO
def test_categoria_inexistente_e_recusada():
    exigir()
    f, pavs, _ = X.casa("IFC4")
    g = X.vista(f, "PLANTA", pavs[0])
    with pytest.raises(S().SelecaoInvalida):
        S().selecionar(f, g, categorias_ocultas=("IfcNaoExiste",))
    assert issubclass(S().SelecaoInvalida, ValueError)


# ---------- erros ----------
@AINDA_NAO
def test_vista_sem_pavimento_ou_com_pavimento_invalido():
    exigir()
    import openbim_app.vistas_ifc as V
    f, pavs, _ = X.casa("IFC4")
    g = X.vista(f, "PLANTA", None)
    with pytest.raises(S().SelecaoInvalida):
        S().selecionar(f, g)
    with pytest.raises(S().SelecaoInvalida):
        S().selecionar(f, g, pavimento="3zzzzzzzzzzzzzzzzzzzzz")  # não existe
    with pytest.raises(S().SelecaoInvalida):
        S().selecionar(f, g, pavimento=pavs[0].Decomposes[0].RelatingObject.GlobalId)  # existe, mas é o edifício
    X.conter(f, pavs[0].Decomposes[0].RelatingObject, f.by_guid(g))  # vista contida no edifício, não num pavimento
    with pytest.raises(S().SelecaoInvalida):
        S().selecionar(f, g)
    with pytest.raises(V.VistaInexistente):
        S().selecionar(f, "3zzzzzzzzzzzzzzzzzzzzz")


@AINDA_NAO
def test_vista_de_outro_programa_sem_tipo():
    exigir()
    import s06_t04_aux as A
    f, pavs, _ = X.casa("IFC4")
    a = A.annotation(f, "Alheia")
    X.conter(f, pavs[0], a)
    with pytest.raises(S().SelecaoInvalida):
        S().selecionar(f, a.GlobalId)


@AINDA_NAO
@MOD
def test_nao_altera_o_ifc(esq, off, base):
    exigir()
    f, pavs, _ = X.casa(esq, off, base)
    g = X.vista(f, "PLANTA", pavs[0])
    g2 = X.vista(f, "CORTE", pavs[0], origem=(off[0], off[1], base), tamanho=(10.0, 10.0, 6.0), nome="C")
    antes, n = f.to_string(), len(list(f))
    S().selecionar(f, g, categorias_ocultas=("IfcDoor",))
    S().selecionar(f, g2)
    assert f.to_string() == antes and len(list(f)) == n


# ---------- corte ----------
@AINDA_NAO
@MOD
def test_corte_cruza_faixa_de_qualquer_pavimento(esq, off, base):
    exigir()
    f, pavs, dentro, fora = X.faixa(esq, off, base)
    g = X.vista(f, "CORTE", pavs[0], origem=(off[0], off[1] + 2.0, base), tamanho=(10.0, 1.0, 6.0))
    s = S().selecionar(f, g)
    assert X.nomes(f, s) == dentro and not (X.nomes(f, s) & fora)  # inclui os do pavimento 1 (vista está no 0), encostar conta, 1/64 m fora não
    assert s.tipo == "CORTE" and s.pavimento == pavs[0].id()
    import pytest as P
    assert s.faixa == (P.approx((off[0], off[1] + 2.0, base), abs=1e-9), P.approx((off[0] + 10.0, off[1] + 3.0, base + 6.0), abs=1e-9))
    s = S().selecionar(f, g, categorias_ocultas=("IfcFurnishingElement",))
    assert X.nomes(f, s) == dentro - {"movel_in"} and s.ocultos_por_classe == {X.MOVEL[esq]: 1}


@AINDA_NAO
def test_corte_sem_pavimento_nao_da_erro_e_faixa_mais_funda():
    exigir()
    f, pavs, dentro, fora = X.faixa("IFC4", X.GEO, 0.0)
    g = X.vista(f, "CORTE", None, origem=(X.GEO[0], X.GEO[1] + 2.0, 0.0), tamanho=(10.0, 1.0, 6.0))
    s = S().selecionar(f, g)
    assert s.pavimento is None and X.nomes(f, s) == dentro
    g2 = X.vista(f, "CORTE", None, origem=(X.GEO[0], X.GEO[1] + 1.0, 0.0), tamanho=(10.0, 3.0, 6.0), nome="C2")  # profundidade ajustada: 1 a 4 m
    assert X.nomes(f, S().selecionar(f, g2)) == dentro | {"fora_lo", "fora_hi"}


@AINDA_NAO
def test_corte_com_arquivo_em_milimetros():
    exigir()
    f, pavs, dentro, fora = X.faixa("IFC4", X.GEO, 0.0)
    g = X.vista(f, "CORTE", pavs[0], origem=(X.GEO[0], X.GEO[1] + 2.0, 0.0), tamanho=(10.0, 1.0, 6.0))
    X.em_milimetros(f)
    s = S().selecionar(f, g)
    toques = {"toque_hi", "toque_lo"}  # encostar não é testado aqui: 0,001 x número não é exato em ponto flutuante
    assert X.nomes(f, s) - toques == dentro - toques and not (X.nomes(f, s) & fora)
    assert s.faixa[0] == pytest.approx((X.GEO[0] * 0.001, (X.GEO[1] + 2.0) * 0.001, 0.0), abs=1e-9)
    assert s.faixa[1] == pytest.approx(((X.GEO[0] + 10.0) * 0.001, (X.GEO[1] + 3.0) * 0.001, 0.006), abs=1e-9)


# ---------- medida ----------
@AINDA_NAO
def test_um_pavimento_de_tres_devolve_ate_40_por_cento():
    exigir()
    f, pavs = X.estrutura("IFC4", X.GEO, 0.0, n_pav=3)
    for i, p in enumerate(pavs):
        z0 = 3.0 * i
        X.conter(f, p, X.caixa(f, "IfcSlab", f"L{i}", X.GEO[0], X.GEO[1], z0, 5.0, 5.0, 0.25))
        X.conter(f, p, *[X.caixa(f, "IfcWall", f"P{i}{k}", X.GEO[0] + k, X.GEO[1], z0, 0.25, 5.0, 3.0) for k in range(4)])
        X.conter(f, p, *[X.caixa(f, "IfcFurniture", f"M{i}_{k}", X.GEO[0] + 0.1 * k, X.GEO[1] + 1.0, z0, 0.25, 0.25, 0.5) for k in range(30)])
    g = X.vista(f, "PLANTA", pavs[1])
    total = len([e for e in f.by_type("IfcElement") if e.Representation])
    s = S().selecionar(f, g)
    assert total == 105 and len(s.ids) == 35 and len(s.ids) <= 0.4 * total
    assert len(S().selecionar(f, g, categorias_ocultas=("IfcFurniture",)).ids) == 5
