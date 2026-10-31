# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07b (planta SVG bruta; ADR-006 §2, §3 item 0 e §4; cartão `cards/F0-S06/F0-S06-T07-divisao.md`). Não editar este arquivo, `s06_t07b_aux.py`,
`s06_t07_aux.py` nem `test_s06_t07b_entrega_oraculo.py` na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio.
CONTRATO `app/openbim_app/desenho/planta.py` (sem Qt, sem rede, sem display; `desenho/selecao.py` da T07a já existe):
1. `gerar_planta(ifc, gid_vista, *, categorias_ocultas=(), threads=None) -> Planta`. `Planta` = dataclass congelada: `svg` (str: o SVG BRUTO do motor
   `ifcopenshell.geom.serializers.svg`, XML válido de raiz `svg`, SEM viewBox, coordenadas do mundo em METROS e eixo como o motor devolve, inclusive modelo georreferenciado
   a 324550/7405473; o sinal do Y não é testado), `n_paths` (int = quantidade de `<path` no texto de `svg`), `selecao` (a `Selecao` da T07a), `tempos` (dict com
   `geo_s`, `write_s`, `finalize_s`, floats >= 0; só para medir), `unidade_escala` (float, metros por unidade de comprimento do arquivo: 1.0 em metro, 0.001 em milímetro),
   `altura_corte` (float, metros, no MUNDO).
2. A seleção é `selecao.selecionar(ifc, gid_vista, categorias_ocultas=...)`; só esses elementos vão ao serializador, MENOS os `IfcOpeningElement` (o vão da parede
   continua furado; a abertura não é desenhada nem calculada). Vista de tipo CORTE, vista sem pavimento, vista sem TargetView, categoria inexistente -> `selecao.SelecaoInvalida`;
   vista inexistente -> `vistas_ifc.VistaInexistente`.
3. Altura do corte = Z NO MUNDO do pavimento (matriz de `ObjectPlacement` do `IfcBuildingStorey`, resolvida até a raiz, x escala da unidade) + H, com H = propriedade
   `AlturaCorte` (número > 0, em metros acima do pavimento) do pset `OBIM_Vista` da vista, se existir (nome provisório, ADR-003 §3.1), senão 1,2 m; valor <= 0 ou que não é
   número -> `SelecaoInvalida`. O volume (`IfcBlock`) da vista é ignorado. Pavimento em cota 0, positiva, negativa; colocação absoluta ou relativa ao edifício; m ou mm.
4. PLANTA COMPLETA (ADR-006 §5): o que o corte atravessa sai em linha cheia no grupo do elemento (`ifc:guid`); o que fica inteiro abaixo do corte (móvel baixo, laje, viga, louça)
   sai na projeção (grupo `class="projection"`, caminhos sem guid); o que fica inteiro acima não sai. Montagem provada com o motor 0.9.0 (ver `test_s06_t07b_completa_oraculo.py`):
   sem anotação, SEM criar entidade no arquivo (nem durante a geração): `settings(ELEMENT_HIERARCHY=True)` com `section-height-from-storeys`, `svg-project` e `section-height` =
   (altura do corte no mundo) - (`Elevation` do pavimento x escala), porque o motor soma o `Elevation` (que pode ser local ao edifício). O motor emite um grupo
   `IfcBuildingStorey` por pavimento do arquivo e os de cima repetem a projeção: o texto final só traz o grupo do pavimento da vista (`ifc:guid` = o dele); `n_paths` conta o texto final.
   Nenhum filtro apaga desenho: sólido a 600 m da própria origem sem vizinho aparece; elemento a 150 m aparece. O arquivo de entrada NÃO muda (`to_string` igual antes e depois,
   inclusive se o serializador ou outra chamada levantar exceção no meio).
5. Parede cortada = polilinha fechada com o contorno da parede; porta e janela cortadas abrem vão (a parede fica em 2, 3 pedaços); abertura que não cruza o corte não fura.
6. Pavimento sem desenho (selecao vazia) -> `Planta` com `n_paths` 0 e `svg` válido, sem exceção. Determinístico. `threads` só muda o paralelismo, nunca o conjunto desenhado.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import dataclasses
import re

import pytest
import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)

MOD = pytest.mark.parametrize("esq,off,base,k,rel", B.MODELOS)
PORTA = ("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0)
JAN_BAIXA = ("jan", "IfcWindow", 3.0, 0.9, 1.0, 1.0)  # 0,9 a 1,9: cruza o corte
JAN_ALTA = ("jan", "IfcWindow", 3.0, 1.5, 1.0, 1.0)  # 1,5 a 2,5: acima do corte


def P():
    exigir()
    import openbim_app.desenho.planta as P_
    return P_


def pecas(p, g, s, nome):
    return B.subcaminhos(B.grupo(p.svg, g[f"{nome}{s}"]))


def y_ok(caixa, oy, esp, tol=0.01):  # o eixo Y vem como o motor devolve: positivo ou espelhado
    lo, hi = caixa[1], caixa[3]
    return (abs(lo - oy) < tol and abs(hi - oy - esp) < tol) or (abs(lo + oy + esp) < tol and abs(hi + oy) < tol)


@MOD
def test_planta_do_pavimento_em_qualquer_cota_e_unidade(esq, off, base, k, rel):
    P_ = P()
    f, pavs, g = B.modelo(esq, off, base, k, rel)
    for s in (0, 1):
        p = P_.gerar_planta(f, B.planta(f, pavs[s], f"V{s}"))
        assert isinstance(p, P_.Planta) and dataclasses.is_dataclass(p) and p.selecao.pavimento == pavs[s].id()
        assert p.altura_corte == pytest.approx(base + 3.0 * s + 1.2, abs=1e-6) and p.unidade_escala == pytest.approx(1.0 / k)
        assert p.n_paths > 0 and p.n_paths == len(re.findall(r"<path\b", p.svg)) and B.svg_valido(p.svg) and "viewBox" not in p.svg
        assert 'class="projection"' in p.svg and p.svg.count('class="projection"') == 1 and B.subcaminhos(p.svg.split('class="projection"')[1])
        visiveis = {n for n in ("P", "M0_", "Xc", "Longe", "porta") if B.grupo(p.svg, g[f"{n}{s}"]) is not None}
        assert visiveis == {"P", "M0_", "Xc", "Longe", "porta"}  # o que cruza o corte
        assert not any(B.grupo(p.svg, g[f"{n}{s}"]) is not None for n in ("Xa", "Xb", "L"))  # inteiro acima, inteiro abaixo, laje: fora do plano
        assert not any(g[n] in p.svg for n in g if not n.endswith(str(s)))  # nada do outro pavimento
        assert p.tempos.keys() >= {"geo_s", "write_s", "finalize_s"} and all(isinstance(v, float) and v >= 0 for v in p.tempos.values())
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.svg = ""


@MOD
def test_parede_cortada_e_polilinha_fechada_com_a_espessura(esq, off, base, k, rel):
    P_ = P()
    f, pavs, g = B.modelo(esq, off, base, k, rel, esp=0.2, vaos=())
    for s in (0, 1):
        sub = pecas(P_.gerar_planta(f, B.planta(f, pavs[s], f"V{s}")), g, s, "P")
        assert len(sub) == 1 and sub[0][0] == sub[0][-1]
        x0, y0, x1, y1 = B.caixa_de(sub[0])
        assert abs(x0 - off[0]) < 0.01 and abs(x1 - off[0] - 5.0) < 0.01 and y_ok((x0, y0, x1, y1), off[1], 0.2)


@pytest.mark.parametrize("m", [B.MODELOS[0], B.MODELOS[3]])
def test_porta_e_janela_abrem_vao_so_se_cruzam_o_corte(m):
    P_ = P()
    esq, off, base, k, rel = m
    casos = {"sem": ((), 1), "porta": ((PORTA,), 2), "porta_e_janela": ((PORTA, JAN_BAIXA), 3), "janela_alta": ((PORTA, JAN_ALTA), 2), "so_janela_alta": ((JAN_ALTA,), 1)}
    n_paths = {}
    for nome, (vaos, pedacos) in casos.items():
        f, pavs, g = B.modelo(esq, off, base, k, rel, vaos=vaos)
        p = P_.gerar_planta(f, B.planta(f, pavs[1]))
        sub = sorted(pecas(p, g, 1, "P"), key=lambda s: B.caixa_de(s)[0])
        assert len(sub) == pedacos, nome
        if nome == "porta":  # vão de 1 a 2 m na parede de 0 a 5 m
            assert [round(B.caixa_de(s)[0] - off[0], 2) for s in sub] == [0.0, 2.0] and [round(B.caixa_de(s)[2] - off[0], 2) for s in sub] == [1.0, 5.0]
            assert B.grupo(p.svg, g["porta1"]) is not None
        if nome == "porta_e_janela":
            assert B.grupo(p.svg, g["jan1"]) is not None
        if nome in ("janela_alta", "so_janela_alta"):
            assert B.grupo(p.svg, g["jan1"]) is None
        n_paths[nome] = p.n_paths
    assert n_paths["porta"] > n_paths["sem"] and n_paths["porta_e_janela"] > n_paths["porta"] and n_paths["janela_alta"] == n_paths["porta"]


def test_movel_oculto_some_e_ligado_aparece():
    P_ = P()
    for esq in X.ESQUEMAS:
        f, pavs, g = B.modelo(esq, n_moveis=3)
        g0 = B.planta(f, pavs[0])
        ligado = P_.gerar_planta(f, g0)
        assert all(B.grupo(ligado.svg, g[f"M{j}_0"]) is not None for j in range(3)) and ligado.selecao.ocultos_por_classe == {}
        oculto = P_.gerar_planta(f, g0, categorias_ocultas=("IfcFurnishingElement",))
        assert not any(g[f"M{j}_0"] in oculto.svg for j in range(3)) and oculto.selecao.ocultos_por_classe == {X.MOVEL[esq]: 3}
        assert B.grupo(oculto.svg, g["P0"]) is not None and oculto.n_paths < ligado.n_paths
        assert oculto.svg == P_.gerar_planta(f, g0, categorias_ocultas=("IfcFurnishingElement",)).svg


def test_entrada_intacta_deterministica_e_independente_de_threads():
    P_ = P()
    f, pavs, g = B.modelo("IFC4", X.GEO, 12.5, 1.0, True, n_moveis=4)
    gv = B.planta(f, pavs[1])
    antes, n_ann = f.to_string(), len(f.by_type("IfcAnnotation"))
    a, b = P_.gerar_planta(f, gv), P_.gerar_planta(f, gv)
    assert f.to_string() == antes and a.svg == b.svg and a.n_paths == b.n_paths and a.selecao == b.selecao
    um, tres = P_.gerar_planta(f, gv, threads=1), P_.gerar_planta(f, gv, threads=3)
    assert f.to_string() == antes and um.n_paths == tres.n_paths == a.n_paths
    assert set(re.findall(r'ifc:guid="([^"]+)"', um.svg)) == set(re.findall(r'ifc:guid="([^"]+)"', tres.svg)) == set(re.findall(r'ifc:guid="([^"]+)"', a.svg))
    gv2 = X.vista(f, "PLANTA", pavs[1], nome="V2", origem=(0.0, 0.0, 99.0), tamanho=(0.5, 0.5, 0.5))  # volume da vista ignorado
    c = P_.gerar_planta(f, gv2)
    assert c.svg == a.svg and c.altura_corte == a.altura_corte and len(f.by_type("IfcAnnotation")) == n_ann + 1
