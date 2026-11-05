# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo de robustez do F0-S06-T07d (complemento de `test_s06_t07d_estilo_oraculo.py`; mesmo contrato). Não editar na implementação. Contrato extra de `aplicar_estilo`:
1. Todo número escrito (viewBox, width/height, stroke-width) em decimal comum (6 casas, sem zeros à direita inúteis), NUNCA com notação científica (`e`).
2. Coordenada que estoura (`1e400`) ou largura/altura/traço que daria `inf`/`nan` => `EstiloInvalido`; `inf`/`nan` nunca aparecem no SVG de saída.
3. Gramática estrita de `d`: um ou mais subcaminhos `M x,y (L x,y)*` (espaços/quebras entre tokens). Recusa: sem `M` inicial, `M` ou `L` sem ponto, `M M`, número colado (`0,0-1,2`).
4. Todo `<style>` da entrada some, auto-fechado (`<style/>`) ou não, em qualquer número; saída com exatamente 1; o conteúdo vizinho (grupos, `d`) não é tocado.
LIMITE CONHECIDO (decisão do PO/líder): o SVG vem sempre do motor; aspas simples nos atributos e comentários XML com marcação dentro não são suportados nem testados."""
import re

import pytest
import s06_t07d_aux as Z
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)


def ap(svg, *a, **k):
    import openbim_app.desenho.estilo as E
    return E.aplicar_estilo(svg, *a, **k)


def svg_d(*ds_, extra=""):
    return Z.CAB + extra + "".join(f'<path d="{d}"/>' for d in ds_) + "</svg>"


def numeros(s):
    r = re.search(r"<svg\b[^>]*>", s).group(0)
    css = "".join(e.text or "" for e in Z.estilos(s))
    return re.findall(r'(?:viewBox|width|height)="([^"]*)"', r) + re.findall(r"stroke-width:\s*([^;\s]*)", css)


@pytest.mark.parametrize("d,esc,m", [("M0,0 L0.00001,0.00001", "1:1000000", 0.0), ("M0,0 L0.00001,0.00001", "1:100", 0.0), ("M0,0 L1e17,1", "1:100", 0.1), ("M0,0 L100,1", "1:0.00001", 0.1),
                                      ("M0,0 L1,1", "1:1000000000000", 0.1)])
def test_sem_notacao_cientifica(d, esc, m):
    s = ap(svg_d(d), esc, margem_m=m)
    assert numeros(s) and not any(re.search(r"[eE]", re.sub("mm$", "", n)) for n in numeros(s)), numeros(s)
    assert not re.search(r"\b(?:inf|nan)\b", s, re.I)


@pytest.mark.parametrize("d,esc", [("M0,0 L1e400,1", "1:100"), ("M-1e400,0 L1,1", "1:100"), ("M0,0 L1,1", "1:1e-308"), ("M-1e308,0 L1e308,1", "1:100"), ("M0,0 L1e300,1", "1:1e-10")])
def test_estouro_vira_erro(d, esc):
    import openbim_app.desenho.estilo as E
    with pytest.raises(E.EstiloInvalido):
        ap(svg_d(d), esc)


@pytest.mark.parametrize("d", ["0,0 1,1", "L 0,0", "L0,0 L1,1", "M M 0,0 L", "M0,0 L", "M0,0 L1,1 L", "M0,0 L1,1 M", "M0,0-1,2", "M0,0 L1,1-2,3", "M", "M0,0,1,1"])
def test_gramatica_recusa(d):
    import openbim_app.desenho.estilo as E
    with pytest.raises(E.EstiloInvalido):
        ap(svg_d("M5,5 L6,6", d))


@pytest.mark.parametrize("d", ["M0,0", "M 0,0 L 1,1", "M0,0 L1,1 M2,2 L3,3", "M0,0\n L1,1\n\tL2,0", "M-1.5,2e1 L0,1"])
def test_gramatica_aceita(d):
    assert Z.ds(ap(svg_d(d))) == [d]


def test_style_auto_fechado_e_multiplos():
    g = '<g class="IfcWall" ifc:guid="G1"><path d="M1,2 L6,2"/></g>'
    for extra in ('<style/>' + g, '<style type="text/css"/>' + g, '<style>a{}</style>' + g + '<style/>' + '<style>b{}</style>', '<style/>' + g + '<style>x{}</style>', g + '<style/><style/>'):
        s = ap(svg_d("M0,0 L1,1", extra=extra))
        assert len(Z.estilos(s)) == 1 and "a{}" not in s and "b{}" not in s and "x{}" not in s
        assert Z.ds(s) == Z.ds(svg_d("M0,0 L1,1", extra=extra))
        assert Z.grupos_folha(s)[0] == [] or "cut" in Z.classes(Z.grupos_folha(s)[0][0])
