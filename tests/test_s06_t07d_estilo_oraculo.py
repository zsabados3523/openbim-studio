# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07d (estilo do desenho; `cards/F0-S06/F0-S06-T07d.md`). Não editar este arquivo nem `s06_t07d_aux.py` na implementação.
CONTRATO `app/openbim_app/desenho/estilo.py` (função pura sobre texto; sem Qt, sem rede, sem `ifcopenshell`; só biblioteca padrão):
1. `aplicar_estilo(svg: str, escala: str | int | float = "1:100", *, margem_m: float = 0.1) -> str` e `class EstiloInvalido(ValueError)`.
2. ENTRADA = SVG bruto do motor (planta T07b ou corte T07c), em METROS. Contrato OBSERVADO (medido em 5/11 com os modelos dos auxiliares):
   a. PLANTA: sem `viewBox`/`width`/`height`; `y_svg = -Y_mundo` (o norte tem y MENOR, ou seja fica em cima na tela; x cresce para leste). Já é a orientação de desenho: NÃO se espelha nem se gira nada.
      Estrutura: `<g class="IfcBuildingStorey" ifc:guid>` contêiner (filhos `<g>`, nenhum `<path>` direto) com um `<g class="IfcXxx" ifc:name ifc:guid>` por elemento CORTADO (os `<path>` são filhos
      diretos) e um `<g class="projection">` (linhas do que está além, sem guid). O motor injeta um `<style>` próprio cujas regras `.cut path` nunca casam (nenhum grupo tem a classe `cut`).
   b. CORTE: `viewBox="0 0 largura altura"` do bloco da vista (NÃO é o envoltório do desenho: `x_svg = X_local + largura/2` pode passar da largura); `y` cresce para baixo (teto com y menor que o piso).
      Estrutura: `<g class="section">` contendo os grupos `<g class="IfcXxx" ifc:guid>` cortados (folhas) e `<g class="projection">`; `<style>` próprio (`path { stroke-width: 0.3 }` etc.).
   c. Os `d` dos caminhos usam só comandos `M` e `L` absolutos com pares `x,y` separados por vírgula (formato do motor); sem transformação (`transform`) em nenhum nível.
3. SAÍDA (XML válido, texto): mesmos elementos e MESMOS `d` (texto idêntico, mesma ordem); nenhuma transformação, nenhum ponto movido, y continua para baixo.
   a. Raiz: `viewBox="x0 y0 w h"` = envoltório de TODOS os vértices de TODOS os `<path>` expandido de `margem_m` em cada lado (substitui o viewBox cru, se houver); `width`/`height` = `w`/`h` x 1000 / N seguidos de
      `mm` (N = denominador da escala; 1:50 -> 20 mm por metro; 1:100 -> 10 mm por metro). Números em notação decimal comum, valores até 6 casas.
   b. Cada grupo CORTADO (um `<g>` com `ifc:guid` e `<path>` filho direto) ganha o token `cut` em `class` (mantém `IfcXxx`; sem duplicar). O contêiner de pavimento e `<g class="projection">` não ganham `cut`;
      nenhum caminho da projeção tem ancestral `cut`.
   c. EXATAMENTE UM `<style>` (o do motor é descartado). Regras (seletor exato, propriedades em unidades do viewBox = metros do modelo, SEM unidade): `.cut path`: `stroke-width` = 0,5 mm de papel
      x N / 1000, `fill` = cinza escuro `#rrggbb` (cada canal <= 0x60), `fill-rule: evenodd` (furos de porta/janela); `.projection path`: `stroke-width` = 0,25 mm de papel x N / 1000, `fill: none`.
   d. `escala`: `"1:N"` (texto) ou número N (int/float) com N finito > 0; `margem_m` finita >= 0. Fora disso, `str` que não seja SVG, XML malformado, raiz que não é `svg`, ZERO `<path>` (inclui o SVG vazio de planta
      sem elementos, `<svg ...></svg>`: ERRO, não se inventa um desenho de 1x1), `d` sem vértice ou com comando fora de `M`/`L`: `EstiloInvalido`. A entrada nunca é alterada (str imutável).
   e. Idempotente e determinístico, e só depende dos caminhos, da escala e da margem: `aplicar(aplicar(x, e1), e2) == aplicar(x, e2)`.
GUARDA: os casos com SVG real pulam sem ifcopenshell (falham com OBIM_S05_OBRIGATORIO=1)."""
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import s06_t07d_aux as Z
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)

TOL = 1e-5


def E():
    import openbim_app.desenho.estilo as E_
    return E_


def ap(svg, *a, **k):
    return E().aplicar_estilo(svg, *a, **k)


@pytest.fixture(scope="module")
def planta():
    exigir()
    return Z.cru_planta()


@pytest.fixture(scope="module")
def corte():
    exigir()
    return Z.cru_corte()


def perto(a, b, t=TOL):
    return len(a) == len(b) and all(abs(x - y) <= t for x, y in zip(a, b))


def lados(svg, m):
    x0, y0, x1, y1 = Z.caixa(svg)
    return (x0 - m, y0 - m, x1 - x0 + 2 * m, y1 - y0 + 2 * m)


def test_viewbox_e_envoltorio_exato():
    s = ap(Z.PEQUENO, "1:100", margem_m=0.0)
    assert perto(Z.viewbox(s), (-1.0, 0.0, 9.0, 4.0))
    s = ap(Z.PEQUENO, "1:100", margem_m=0.5)
    assert perto(Z.viewbox(s), (-1.5, -0.5, 10.0, 5.0))
    assert perto(Z.viewbox(ap(Z.PEQUENO)), (-1.1, -0.1, 9.2, 4.2))  # margem padrão 0,1 m


@pytest.mark.parametrize("esc,mm_m", [("1:50", 20.0), ("1:100", 10.0), (100, 10.0), (50.0, 20.0), ("1:20", 50.0), ("1:200", 5.0), (1, 1000.0)])
def test_largura_em_mm_pela_escala(esc, mm_m):
    s = ap(Z.PEQUENO, esc, margem_m=0.0)
    assert perto(Z.mm(s), (9.0 * mm_m, 4.0 * mm_m), 1e-4)
    assert perto(Z.viewbox(s), (-1.0, 0.0, 9.0, 4.0))


def test_tracos_por_escala_e_tipo():
    for esc, n in (("1:50", 50), ("1:100", 100), (200, 200)):
        s = ap(Z.PEQUENO, esc)
        assert abs(Z.traco(s, ".cut path") - 0.5 * n / 1000) <= 1e-6
        assert abs(Z.traco(s, ".projection path") - 0.25 * n / 1000) <= 1e-6
        # em papel: espessura (unidades) x mm por unidade = 0,5 e 0,25 mm
        mm_m = Z.mm(s)[0] / Z.viewbox(s)[2]
        assert abs(Z.traco(s, ".cut path") * mm_m - 0.5) <= 1e-4 and abs(Z.traco(s, ".projection path") * mm_m - 0.25) <= 1e-4
        assert Z.traco(s, ".cut path") > Z.traco(s, ".projection path")


def test_preenchimento_e_regras():
    r = Z.regras(ap(Z.PEQUENO))
    assert Z.luminosidade(r[".cut path"]["fill"]) <= 0x60
    assert r[".cut path"]["fill-rule"] == "evenodd"
    assert r[".projection path"]["fill"] == "none"


def test_classes_dos_grupos_e_um_so_estilo():
    s = ap(Z.PEQUENO)
    assert len(Z.estilos(s)) == 1
    cortados, proj = Z.grupos_folha(s)
    assert len(cortados) == 1 and "cut" in Z.classes(cortados[0]) and "IfcWall" in Z.classes(cortados[0])
    assert len(proj) == 1 and "cut" not in Z.classes(proj[0])


def test_estilo_do_motor_descartado():
    cru = Z.PEQUENO.replace("<g class=\"IfcWall\"", '<style type="text/css">path { stroke-width: 0.3; } .velho { fill: red; }</style><g class="IfcWall"', 1)
    s = ap(cru)
    assert len(Z.estilos(s)) == 1 and "velho" not in s and "0.3" not in "".join(e.text or "" for e in Z.estilos(s))


def test_caminhos_identicos_e_sem_transformacao():
    s = ap(Z.PEQUENO)
    assert Z.ds(s) == Z.ds(Z.PEQUENO)
    assert "transform" not in s


def test_y_continua_para_baixo_no_papel():
    s = ap(Z.PEQUENO, "1:100", margem_m=0.0)
    # ponto (1, 2) do desenho: 2 m abaixo do topo do viewBox e 2 m à direita da borda esquerda -> 20 mm x 20 mm de papel a 1:100
    assert perto(Z.tela_mm((1.0, 2.0), s), (20.0, 20.0), 1e-4)
    assert perto(Z.tela_mm((8.0, 4.0), s), (90.0, 40.0), 1e-4)  # canto inferior direito = tamanho do papel


@pytest.mark.parametrize("svg", [
    "", "   ", "<svg", "nao e xml", "<svg xmlns='http://www.w3.org/2000/svg'><g></svg>", "<html></html>",
    '<svg xmlns="http://www.w3.org/2000/svg" version="1.1"></svg>',  # o SVG vazio da planta (T07b/T07c `_SVG_VAZIO`)
    '<svg xmlns="http://www.w3.org/2000/svg"><g class="projection"></g></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><path d=""/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><path d="M1,2 C1,2 3,4 5,6"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><path d="m1,2 l3,4"/></svg>',
    None, b"<svg/>", 7])
def test_svg_invalido(svg):
    with pytest.raises(E().EstiloInvalido):
        ap(svg)


@pytest.mark.parametrize("esc", ["", "abc", "1:0", "1:-50", "2:100", "100", "1:", ":100", "1:abc", 0, -50, 0.0, float("nan"), float("inf"), None, True, [100], "1:nan", "1:inf"])
def test_escala_invalida(esc):
    with pytest.raises(E().EstiloInvalido):
        ap(Z.PEQUENO, esc)


@pytest.mark.parametrize("m", [-0.1, float("nan"), float("inf"), "0.1", None])
def test_margem_invalida(m):
    with pytest.raises(E().EstiloInvalido):
        ap(Z.PEQUENO, margem_m=m)


def test_idempotente_e_deterministico_pequeno():
    a = ap(Z.PEQUENO, "1:50")
    assert ap(a, "1:50") == a and ap(Z.PEQUENO, "1:50") == a
    assert ap(a, "1:100") == ap(Z.PEQUENO, "1:100")  # só depende dos caminhos, da escala e da margem
    assert ap(a, "1:50", margem_m=0.3) == ap(Z.PEQUENO, "1:50", margem_m=0.3)
    ET.fromstring(a)


def test_modulo_puro():
    src = Path(E().__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:import|from)\s+(?:ifcopenshell|PySide\d*|PyQt\d|openbim_geometria|obim_geometria|openbim_app)\b", src, re.M)


def test_planta_viewbox_justo_e_pontos_preservados(planta):
    cru, _ = planta
    assert "viewBox" not in cru
    s = ap(cru)
    assert perto(Z.viewbox(s), lados(cru, 0.1))
    assert perto(Z.viewbox(ap(cru, margem_m=0)), lados(cru, 0.0))
    assert Z.ds(s) == Z.ds(cru) and Z.vertices(s) == Z.vertices(cru)
    assert "transform" not in s
    r, _ = Z.ancestrais(s)
    assert r.tag == Z.NS_SVG + "svg" and len(Z.estilos(s)) == 1


def test_planta_escalas(planta):
    cru, _ = planta
    a, b = ap(cru, "1:50"), ap(cru, "1:100")
    assert perto(Z.viewbox(a), Z.viewbox(b))
    w = Z.viewbox(b)[2]
    assert perto(Z.mm(b), (w * 10, Z.viewbox(b)[3] * 10), 1e-3) and perto(Z.mm(a), (w * 20, Z.viewbox(a)[3] * 20), 1e-3)


def test_planta_nao_espelhada_norte_em_cima(planta):
    cru, g = planta
    s = ap(cru, "1:100")
    r, _ = Z.ancestrais(s)
    grupo = {x.get(Z.NS_IFC + "guid"): x for x in r.iter(Z.NS_SVG + "g")}

    def pts(nome):
        return [(float(a), float(b)) for p in grupo[g[nome]].findall(Z.NS_SVG + "path") for a, b in Z.NUM.findall(p.get("d"))]
    parede, movel = pts("P0"), pts("M0_0")
    # mundo: parede em y 0..0,25 (x 0..5); móvel ao NORTE (y 2..2,5; x 0,5..1). No papel: móvel ACIMA da parede (y_tela menor) e à direita da borda esquerda da parede.
    tp, tm = [Z.tela_mm(p, s) for p in parede], [Z.tela_mm(p, s) for p in movel]
    assert max(y for _, y in tm) < min(y for _, y in tp)
    assert min(x for x, _ in tm) > min(x for x, _ in tp) and max(x for x, _ in tm) < max(x for x, _ in tp)
    # a parede mede 5 m x 0,25 m: a 1:100 são 50 mm x 2,5 mm, não girada nem espelhada
    assert abs((max(x for x, _ in tp) - min(x for x, _ in tp)) - 50.0) <= 1e-3 and abs((max(y for _, y in tp) - min(y for _, y in tp)) - 2.5) <= 1e-3
    # a parede começa em x = 0 do mundo, que é a borda esquerda do envoltório mais a margem de 0,1 m = 1 mm
    assert abs(min(x for x, _ in tp) - 1.0) <= 1e-3


def test_planta_classes_e_projecao(planta):
    cru, g = planta
    s = ap(cru)
    r, pai = Z.ancestrais(s)
    cortados, proj = Z.grupos_folha(s)
    assert {x.get(Z.NS_IFC + "guid") for x in cortados} == {g[n] for n in ("P0", "M0_0", "Xc0", "Longe0", "porta0")}
    assert all("cut" in Z.classes(x) and any(c.startswith("Ifc") for c in Z.classes(x)) for x in cortados)
    storey = [x for x in r.iter(Z.NS_SVG + "g") if "IfcBuildingStorey" in Z.classes(x)]
    assert storey and all("cut" not in Z.classes(x) for x in storey)
    assert len(proj) == 1
    for p in proj[0].iter(Z.NS_SVG + "path"):
        a = p
        while a in pai:
            a = pai[a]
            assert "cut" not in Z.classes(a)


def test_corte_viewbox_descarta_o_cru_e_pontos_preservados(corte):
    cru, _ = corte
    assert Z.viewbox(cru) == (0.0, 0.0, 7.0, 4.5)
    x0, y0, x1, y1 = Z.caixa(cru)
    assert x1 > 7.0  # o desenho passa do viewBox cru: o estilo tem de recalcular
    s = ap(cru, margem_m=0)
    assert perto(Z.viewbox(s), (x0, y0, x1 - x0, y1 - y0))
    assert perto(Z.viewbox(ap(cru)), lados(cru, 0.1))
    assert Z.ds(s) == Z.ds(cru) and "transform" not in s and len(Z.estilos(s)) == 1
    assert "stroke-width: 0.3" not in s and "path.outline" not in s


def test_corte_y_para_baixo_e_nao_espelhado(corte):
    cru, g = corte
    s = ap(cru, "1:100")
    r, _ = Z.ancestrais(s)
    grupo = {x.get(Z.NS_IFC + "guid"): x for x in r.iter(Z.NS_SVG + "g")}

    def pts(nome):
        return [Z.tela_mm((float(a), float(b)), s) for p in grupo[g[nome]].findall(Z.NS_SVG + "path") for a, b in Z.NUM.findall(p.get("d"))]
    parede, laje, porta = pts("P"), pts("L"), pts("porta")
    # parede 5 m x 3 m = 50 mm x 30 mm; laje (z -0,2..0) ABAIXO da parede (y_tela maior), porta (x 1..2 m) dentro da parede
    assert abs(max(x for x, _ in parede) - min(x for x, _ in parede) - 50.0) <= 1e-3 and abs(max(y for _, y in parede) - min(y for _, y in parede) - 30.0) <= 1e-3
    assert min(y for _, y in laje) >= max(y for _, y in parede) - 1e-3
    assert min(x for x, _ in porta) > min(x for x, _ in parede) and max(x for x, _ in porta) < max(x for x, _ in parede)
    assert abs(max(y for _, y in porta) - max(y for _, y in parede)) <= 1e-3  # a porta nasce no piso (z = 0): base alinhada à da parede


def test_corte_classes_e_tracos(corte):
    cru, g = corte
    s = ap(cru, "1:50")
    cortados, proj = Z.grupos_folha(s)
    assert {x.get(Z.NS_IFC + "guid") for x in cortados} == {g["P"], g["L"], g["porta"]}
    assert all("cut" in Z.classes(x) for x in cortados) and len(proj) == 1 and "cut" not in Z.classes(proj[0])
    assert abs(Z.traco(s, ".cut path") - 0.025) <= 1e-6 and abs(Z.traco(s, ".projection path") - 0.0125) <= 1e-6


def test_planta_e_corte_cortada_mais_grossa_que_projecao(planta, corte):
    for cru, _ in (planta, corte):
        for esc in ("1:50", "1:100"):
            s = ap(cru, esc)
            assert Z.traco(s, ".cut path") > Z.traco(s, ".projection path") > 0
    assert Z.regras(ap(planta[0], "1:100"))[".cut path"] == Z.regras(ap(corte[0], "1:100"))[".cut path"]  # mesmo estilo nas duas vistas


def test_corte_idempotente_deterministico(corte):
    cru, _ = corte
    a = ap(cru, "1:100")
    assert ap(a, "1:100") == a and ap(cru, "1:100") == a and ap(a, "1:50") == ap(cru, "1:50")


def test_vazio_real_da_planta_e_erro():
    exigir()
    import openbim_app.desenho.planta as P
    with pytest.raises(E().EstiloInvalido):
        ap(P._SVG_VAZIO)
