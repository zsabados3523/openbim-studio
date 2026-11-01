# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08, entradas ruins e exportacao de SVG. Contrato (API) no docstring de `test_s06_t08_prancha_oraculo.py`.
Erro tipado = a classe EXATA pedida (as subclasses de `PranchaInvalida` nao se confundem entre si)."""
import math
import os

import pytest
import s06_t08_aux as A
from s06_t08_aux import DADOS, GUID, IDENT, Lado, montar, planta

pytestmark = pytest.mark.xfail(strict=True, raises=(ImportError, AttributeError, AssertionError, TypeError, NameError),
                               reason="@AINDA_NAO: openbim_app/prancha.py ainda nao existe (F0-S06-T08)")


def P():
    import openbim_app.prancha as m
    return m


def exato(erro, chamada):
    with pytest.raises(erro) as e:
        chamada()
    assert type(e.value) is erro, f"esperava {erro.__name__}, veio {type(e.value).__name__}"


# ---------- escala ----------
@pytest.mark.parametrize("ruim", [0, 0.0, -50, -0.001, "50", "1:50", None, True, False, float("nan"), float("inf"), float("-inf"), [50], {"a": 1}])
def test_01_escala_ruim(ruim):
    m = P()
    lado = Lado()
    exato(m.EscalaInvalida, lambda: m.colocar_viewport(lado, IDENT, GUID, 20, 20, ruim))
    assert lado.chamadas == [], "criou viewport apesar da escala ruim"


@pytest.mark.parametrize("ok", [1, 0.5, 50, 100.0, 62.5, 1e6])
def test_02_escala_boa_passa(ok):
    m = P()
    lado = Lado()
    m.colocar_viewport(lado, IDENT, GUID, 20, 20, ok)
    assert lado.chamadas and m.ler_viewport(lado.lat, IDENT, GUID)["escala"] == ok


@pytest.mark.parametrize("x,y", [("a", 1), (1, "a"), (None, 1), (1, None), (True, 1), (1, False), (math.nan, 1), (1, math.inf)])
def test_03_posicao_ruim(x, y):
    m = P()
    lado = Lado()
    exato(m.PranchaInvalida, lambda: m.colocar_viewport(lado, IDENT, GUID, x, y, 50))
    assert lado.chamadas == []


@pytest.mark.parametrize("ident,guid", [("", GUID), (None, GUID), (7, GUID), (IDENT, ""), (IDENT, None), (IDENT, 3)])
def test_04_chaves_ruins_do_viewport(ident, guid):
    m = P()
    lado = Lado()
    exato(m.PranchaInvalida, lambda: m.colocar_viewport(lado, ident, guid, 20, 20, 50))
    assert lado.chamadas == []


# ---------- prancha ----------
@pytest.mark.parametrize("formato", ["A0", "a3", "A3 ", "", None, 3, "A5", ("A3",)])
def test_05_formato_ruim(formato):
    m = P()
    lado = Lado()
    exato(m.FormatoInvalido, lambda: m.criar_prancha(lado, IDENT, **{**DADOS, "formato": formato}))
    assert lado.chamadas == []


@pytest.mark.parametrize("campo,valor", [("data", "2026-13-01"), ("data", "2026-02-30"), ("data", "01/11/2026"), ("data", "2026-1-1"), ("data", ""),
                                         ("data", None), ("data", 20261101), ("projeto", ""), ("projeto", "   "), ("projeto", None),
                                         ("titulo", ""), ("titulo", 5), ("folha", ""), ("folha", None)])
def test_06_campo_do_carimbo_ruim(campo, valor):
    m = P()
    lado = Lado()
    exato(m.PranchaInvalida, lambda: m.criar_prancha(lado, IDENT, **{**DADOS, campo: valor}))
    assert lado.chamadas == []


@pytest.mark.parametrize("ident", ["", " A-01", "A-01 ", None, 1, "\tA"])
def test_07_identification_ruim(ident):
    m = P()
    lado = Lado()
    exato(m.PranchaInvalida, lambda: m.criar_prancha(lado, ident, **DADOS))
    assert lado.chamadas == []


def test_08_data_bissexta_vale():
    m = P()
    lado = Lado()
    m.criar_prancha(lado, IDENT, **{**DADOS, "data": "2028-02-29"})
    exato(m.PranchaInvalida, lambda: m.criar_prancha(lado, "B", **{**DADOS, "data": "2027-02-29"}))


# ---------- SVG da planta ----------
RUINS_SVG = {
    "vazio": "", "so texto": "nao e svg", "xml cortado": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'>",
    "raiz html": "<html xmlns='http://www.w3.org/2000/svg'/>", "raiz svg fora do namespace": "<svg viewBox='0 0 1 1'/>",
    "sem viewBox": "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>",
    "viewBox com 3 numeros": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10'/>",
    "viewBox texto": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='a b c d'/>",
    "largura zero": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 0 5'/>",
    "altura negativa": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 5 -1'/>",
    "viewBox infinito": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 inf 5'/>",
    "viewBox nan": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 nan 5'/>",
    "doctype": "<!DOCTYPE svg [<!ENTITY a 'b'>]><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 5 5'>&a;</svg>",
    "numero": 5, "None": None, "lista": ["<svg/>"], "bytes nao utf8": b"\xff\xfe<svg",
}


@pytest.mark.parametrize("nome", list(RUINS_SVG))
def test_09_svg_invalido(nome, tmp_path):
    m = P()
    lado, _ = montar()
    ruim = RUINS_SVG[nome]
    exato(m.SvgInvalido, lambda: m.montar_svg(lado.lat, IDENT, GUID, ruim))
    destino = tmp_path / "p.svg"
    exato(m.SvgInvalido, lambda: m.exportar_svg(lado.lat, IDENT, GUID, ruim, destino))
    assert os.listdir(tmp_path) == [], "exportar_svg deixou arquivo apos erro"


def test_10_viewbox_com_virgula_ou_exponencial_vale():
    m = P()
    lado, _ = montar(escala=100, vb=(0, 0, 12, 8))
    svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0,0,1.2e1,8'><rect id='alvo' x='0' y='0' width='12' height='8'/></svg>"
    aprox = A.medir(m.montar_svg(lado.lat, IDENT, GUID, svg))
    assert aprox[2:] == pytest.approx((120, 80))


# ---------- viewport fora da folha ----------
# A4 a 1:100 com viewBox 12 x 8 m = 120 x 80 mm; area util: x em [10, 167], y em [10, 95]
@pytest.mark.parametrize("x,y", [(10, 10), (167, 95), (167, 10), (10, 95), (100, 50)])
def test_11_dentro_da_area_util_inclusive(x, y):
    m = P()
    lado, svg = montar(escala=100, formato="A4", x=x, y=y)
    assert m.montar_svg(lado.lat, IDENT, GUID, svg)


@pytest.mark.parametrize("x,y,porque", [(9.99, 10, "esquerda"), (10, 9.99, "topo"), (167.01, 10, "direita"), (10, 95.01, "sobre o carimbo"),
                                        (-5, 10, "x negativo"), (10, 500, "abaixo da folha"), (1e9, 1e9, "longe")])
def test_12_fora_da_area_util(x, y, porque, tmp_path):
    m = P()
    lado, svg = montar(escala=100, formato="A4", x=x, y=y)
    exato(m.ViewportForaDaFolha, lambda: m.montar_svg(lado.lat, IDENT, GUID, svg))
    exato(m.ViewportForaDaFolha, lambda: m.exportar_svg(lado.lat, IDENT, GUID, svg, tmp_path / "p.svg"))
    assert os.listdir(tmp_path) == []


def test_13_escala_grande_demais_para_a_folha():
    m = P()
    lado, svg = montar(escala=50, formato="A4", x=10, y=10)  # 12 x 8 m a 1:50 = 240 x 160 mm: cabe em A4 (277 x 165)
    assert m.montar_svg(lado.lat, IDENT, GUID, svg)
    lado, svg = montar(escala=20, formato="A4", x=10, y=10)  # 600 x 400 mm: nao cabe
    exato(m.ViewportForaDaFolha, lambda: m.montar_svg(lado.lat, IDENT, GUID, svg))
    lado, svg = montar(escala=50, formato="A3", x=10, y=10, vb=(0, 0, 12, 8))
    assert m.montar_svg(lado.lat, IDENT, GUID, svg)
    lado, svg = montar(escala=20, formato="A3", x=10, y=10, vb=(0, 0, 21, 5))  # 1050 mm de largura, nao cabe nem em A3
    exato(m.ViewportForaDaFolha, lambda: m.montar_svg(lado.lat, IDENT, GUID, svg))


def test_14_a_area_conta_o_viewbox_e_nao_o_retangulo_desenhado():
    m = P()  # alvo pequeno, viewBox grande: 30 x 20 m a 1:50 = 600 x 400 mm nao cabe, mesmo que o desenho seja so um pontinho
    lado, _ = montar(escala=50, formato="A3")
    exato(m.ViewportForaDaFolha, lambda: m.montar_svg(lado.lat, IDENT, GUID, planta(vb=(0, 0, 30, 20), alvo=(0, 0, 1, 1))))


# ---------- inexistente ----------
def test_15_prancha_ou_viewport_inexistente():
    m = P()
    lado, svg = montar()
    exato(m.PranchaNaoEncontrada, lambda: m.montar_svg(lado.lat, "A-99", GUID, svg))
    exato(m.PranchaNaoEncontrada, lambda: m.montar_svg(lado.lat, IDENT, "outra-vista", svg))
    exato(m.PranchaNaoEncontrada, lambda: m.montar_svg(Lado().lat, IDENT, GUID, svg))
    lado2 = Lado()
    m.criar_prancha(lado2, IDENT, **DADOS)  # prancha existe, mas sem viewport
    exato(m.PranchaNaoEncontrada, lambda: m.montar_svg(lado2.lat, IDENT, GUID, svg))
    lado3 = Lado()
    m.colocar_viewport(lado3, IDENT, GUID, 20, 20, 50)  # viewport sem prancha
    exato(m.PranchaNaoEncontrada, lambda: m.montar_svg(lado3.lat, IDENT, GUID, svg))


# ---------- exportar_svg ----------
def test_16_exportar_svg_grava_o_mesmo_que_montar(tmp_path):
    m = P()
    lado, svg = montar()
    destino = tmp_path / "Planta.svg"
    r = m.exportar_svg(lado.lat, IDENT, GUID, svg, destino)
    assert str(r) == str(destino)
    dados = destino.read_bytes()
    assert dados == m.montar_svg(lado.lat, IDENT, GUID, svg).encode("utf-8")
    assert "Planta do térreo".encode("utf-8") in dados, "acento tem de sair em UTF-8"
    assert os.listdir(tmp_path) == ["Planta.svg"]
    m.exportar_svg(lado.lat, IDENT, GUID, svg, str(destino))  # str tambem vale; sobrescreve
    assert destino.read_bytes() == dados


def test_17_erro_nao_altera_arquivo_existente(tmp_path):
    m = P()
    lado, svg = montar(escala=100, formato="A4", x=500, y=10)
    destino = tmp_path / "Planta.svg"
    destino.write_bytes(b"antigo")
    exato(m.ViewportForaDaFolha, lambda: m.exportar_svg(lado.lat, IDENT, GUID, svg, destino))
    assert destino.read_bytes() == b"antigo"
    assert os.listdir(tmp_path) == ["Planta.svg"]
