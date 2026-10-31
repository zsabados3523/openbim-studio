# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07b, rodada 3 (parecer Opus `reports/F0-S06-T07b-revisao.md`): planta COMPLETA, aberturas, altura da vista, recorte e arquivo intocado. O contrato
inteiro está na docstring de `test_s06_t07b_planta_oraculo.py` (itens 1 a 9). Os casos com `@AINDA_NAO` (xfail estrito) falham com a montagem da rodada 2 (anotação
`DRAWING` temporária) e passam com a montagem "pavimento" do motor; quem os libera é o autor do oráculo, em commit próprio, depois da implementação.
MONTAGEM PROVADA (referência descartável): sem anotação e sem criar entidade no arquivo. `ifcopenshell.geom.settings(ELEMENT_HIERARCHY=True)` com `section-height-from-storeys`
= True, `svg-project` = True e `section-height` = (altura do corte no mundo) - (`IfcBuildingStorey.Elevation` x escala da unidade), pois o motor soma o `Elevation` do
pavimento a `section-height` (o `Elevation` pode ser local ao edifício: usar a diferença). O motor emite um grupo `IfcBuildingStorey` por pavimento do ARQUIVO, e os
de cima repetem a projeção (inclusive o que está acima do corte): a planta fica só com o grupo do pavimento da vista (`ifc:guid` = GlobalId dele), cortando os outros do texto."""
import pytest
import s06_t04_aux as A
import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T07b rodada 3: planta ainda não é completa (montagem por anotação)")
MOD = pytest.mark.parametrize("esq,off,base,k,rel", B.MODELOS)


def P():
    exigir()
    import openbim_app.desenho.planta as P_
    return P_


def espiao_de(monkeypatch, antes_do_write=None):
    import ifcopenshell.geom as G
    escritos, original = [], G.serializers.svg

    class Espiao:
        def __init__(self, *a, **k):
            self._r = original(*a, **k)

        def write(self, shape):
            escritos.append((shape.id, getattr(shape, "type", None)))
            if antes_do_write:
                antes_do_write()
            return self._r.write(shape)

        def __getattr__(self, nome):
            return getattr(self._r, nome)
    monkeypatch.setattr(G.serializers, "svg", Espiao)
    return escritos


@AINDA_NAO
@MOD
def test_planta_completa_o_que_esta_abaixo_do_corte_aparece(esq, off, base, k, rel):
    P_ = P()
    f, pavs, g = B.modelo(esq, off, base, k, rel)
    for s in (0, 1):
        p = P_.gerar_planta(f, B.planta(f, pavs[s], f"V{s}"))
        pts = B.pontos(p.svg, off)
        assert B.grupo(p.svg, g[f"Xc{s}"]) is not None  # cortado: linha cheia no grupo do elemento
        assert (3.0, 1.0) in pts and (3.3, 1.3) in pts  # Xb, inteira abaixo do corte (z 0,5 a 0,95): aparece
        assert (5.0, 5.0) in pts and (0.0, 5.0) in pts  # laje 0,2 m abaixo do pavimento: aparece
        assert (2.0, 1.0) not in pts and (2.3, 1.3) not in pts  # Xa, inteira acima do corte (z 1,45 a 1,9): não aparece
        assert p.svg.count('class="IfcBuildingStorey"') == 1 and f'ifc:guid="{pavs[s].GlobalId}"' in p.svg  # só o grupo do pavimento da vista
        assert p.svg.count('class="projection"') == 1 and not any(g[n] in p.svg for n in g if not n.endswith(str(s)))


@AINDA_NAO
@pytest.mark.parametrize("esq", X.ESQUEMAS)
def test_movel_baixo_viga_e_louca_abaixo_do_corte_aparecem(esq):
    P_ = P()
    f, pavs, g = B.modelo(esq, vaos=())
    casos = (("mesa", X.MOVEL[esq], 10.0, 0.0, 1.2, 0.8, 0.75), ("viga", "IfcBeam", 20.0, 0.9, 3.0, 0.2, 0.2), ("louca", "IfcFlowTerminal", 30.0, 0.1, 0.4, 0.4, 0.3))
    for nome, cls, x, z, dx, dy, dz in casos:  # topos de 0,3 a 0,9 m abaixo do corte (1,2 m); nenhum cruza o plano
        X.conter(f, pavs[0], X.caixa(f, cls, nome, x, 1.0, z, dx, dy, dz))
    pts = B.pontos(B.planta_svg(f, P_, pavs[0]), (0.0, 0.0))
    assert all((x, 1.0) in pts and (round(x + dx, 2), round(1.0 + dy, 2)) in pts for _, _, x, _, dx, dy, _ in casos)
    oculto = B.pontos(P_.gerar_planta(f, B.planta(f, pavs[0], "V3"), categorias_ocultas=("IfcBeam",)).svg, (0.0, 0.0))
    assert (20.0, 1.0) not in oculto and (10.0, 1.0) in oculto


@AINDA_NAO
@pytest.mark.parametrize("esq,off,base,k,rel", [B.MODELOS[0], B.MODELOS[3]])
def test_aberturas_nao_vao_ao_serializador_nem_viram_retangulo_fantasma(monkeypatch, esq, off, base, k, rel):
    P_ = P()
    f, pavs, g = B.modelo(esq, off, base, k, rel, abertura_contida=True, vaos=(("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0), ("jan", "IfcWindow", 3.0, 0.9, 1.0, 1.0)))
    gv = B.planta(f, pavs[1])
    escritos = espiao_de(monkeypatch)
    p = P_.gerar_planta(f, gv)
    assert any(f.by_id(i).is_a("IfcOpeningElement") for i in p.selecao.ids)  # a seleção da T07a continua com as aberturas
    assert escritos and not any(t == "IfcOpeningElement" for _, t in escritos) and {i for i, _ in escritos} <= set(p.selecao.ids)
    assert B.grupo(p.svg, g["Oporta1"]) is None and B.grupo(p.svg, g["Ojan1"]) is None and 'class="IfcOpeningElement"' not in p.svg
    assert len(B.subcaminhos(B.grupo(p.svg, g["P1"]))) == 3 and B.grupo(p.svg, g["porta1"]) is not None  # a parede continua furada: 3 pedaços


@AINDA_NAO
@pytest.mark.parametrize("dist", [51.0, 200.0, 600.0])
def test_solido_longe_da_propria_origem_sem_vizinho_aparece(dist):
    P_ = P()
    f, pavs = X.estrutura("IFC4", X.GEO, 0.0)
    e = X.caixa(f, "IfcBuildingElementProxy", "Solo", X.GEO[0], X.GEO[1], 1.0, 0.4, 0.4, 0.4)  # origem no pavimento
    e.Representation.Representations[0].Items[0].SweptArea.Position.Location.Coordinates = (dist + 0.2, 0.2)  # sólido deslocado em X
    X.conter(f, pavs[0], e)
    p = P_.gerar_planta(f, B.planta(f, pavs[0]))
    sub = B.subcaminhos(B.grupo(p.svg, e.GlobalId))
    assert sub and abs(B.caixa_de(sub[0])[0] - (X.GEO[0] + dist)) < 0.01


@AINDA_NAO
def test_altura_de_corte_da_vista_e_padrao_de_1_2_m():
    P_ = P()
    f, pavs, g = B.modelo("IFC4", X.GEO, 12.5, 1.0, True)
    for h, aparece, some in ((None, "Xc0", "Xb0"), (0.6, "Xb0", "Xc0"), (1.9, "Xa0", "Xb0")):
        gv = B.planta(f, pavs[0], f"V{h}")
        if h is not None:  # `OBIM_Vista.AlturaCorte` (nome provisório do ADR-003 §3.1): metros acima do pavimento
            ps = A.api("pset.add_pset", f, product=f.by_guid(gv), name="OBIM_Vista")
            A.api("pset.edit_pset", f, pset=ps, properties={"AlturaCorte": h})
        p = P_.gerar_planta(f, gv)
        assert p.altura_corte == pytest.approx(12.5 + (1.2 if h is None else h), abs=1e-6)
        assert B.grupo(p.svg, g[aparece]) is not None and B.grupo(p.svg, g[some]) is None  # Xb z 0,5-0,95; Xc z 1,0-1,4; Xa z 1,45-1,9
    for ruim in (0.0, -1.0):
        gv = B.planta(f, pavs[1], f"R{ruim}")
        ps = A.api("pset.add_pset", f, product=f.by_guid(gv), name="OBIM_Vista")
        A.api("pset.edit_pset", f, pset=ps, properties={"AlturaCorte": ruim})
        import openbim_app.desenho.selecao as S
        with pytest.raises(S.SelecaoInvalida):
            P_.gerar_planta(f, gv)


@AINDA_NAO
def test_nao_cria_entidade_no_arquivo_nem_durante_a_geracao(monkeypatch):
    P_ = P()
    f, pavs, g = B.modelo("IFC4", X.GEO, 12.5, 1.0, True, n_moveis=2)
    gv = B.planta(f, pavs[1])
    antes, n_total = f.to_string(), len(list(f))
    vistos = []
    espiao_de(monkeypatch, lambda: vistos.append(len(list(f))))  # a cada write, o arquivo tem o mesmo tamanho
    P_.gerar_planta(f, gv)
    assert vistos and set(vistos) == {n_total} and f.to_string() == antes


@AINDA_NAO
def test_excecao_antes_do_serializador_nao_deixa_entidade_solta(monkeypatch):
    P_ = P()
    import ifcopenshell.guid
    f, pavs, g = B.modelo("IFC4", n_moveis=2)
    gv = B.planta(f, pavs[0])
    antes = f.to_string()

    def quebra(*a, **k):
        raise RuntimeError("guid quebrado")
    monkeypatch.setattr(ifcopenshell.guid, "new", quebra)
    try:
        P_.gerar_planta(f, gv)  # quem não usa guid nem chega a falhar; quem usa tem de limpar
    except RuntimeError:
        pass
    assert f.to_string() == antes
