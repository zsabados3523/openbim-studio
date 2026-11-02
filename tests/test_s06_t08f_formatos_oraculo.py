# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08f, parte 3 (folhas A2, A1, A0 e viewport girado 90 graus). Origem: achado 6 da demonstracao (casa de 21 x 29 m em 1:100 = 210 x 290 mm: a altura de
290 mm nao cabe na area util de A3, 252 mm; girada, cabe). Contrato (`openbim_app/prancha.py`):
- `FORMATOS` ganha `"A2": (594.0, 420.0)`, `"A1": (841.0, 594.0)`, `"A0": (1189.0, 841.0)` (largura, altura em mm, paisagem; A4 e A3 iguais). Todo o resto da folha vale
  para os cinco: moldura a 10 mm, `carimbo-caixa` em (10, H-35) de (W-20) x 25, os 4 textos do carimbo inteiros dentro da caixa, PDF de 1 pagina do tamanho da folha.
- `colocar_viewport(lado, identification, vista_guid, x_mm, y_mm, escala, rotacao=0)`: `rotacao` e 0 ou 90 (graus, sentido HORARIO na tela, inteiro, nao `bool`). Qualquer outro
  valor (45, 180, 270, -90, 360, 90.5, "90", None, True, False, nan, inf) = `RotacaoInvalida` (nova, subclasse de `PranchaInvalida`, logo `ValueError`), ANTES de `lado.criar`.
- Gravacao: com rotacao 90 o objeto em `viewports/` ganha `"rotacao": 90`; com 0 (ou omitida) o objeto fica EXATAMENTE como antes (sem a chave; `.obim` antigo continua valendo e
  ausente = 0). `ler_viewport` devolve `"rotacao": 90` so quando e 90 (com 0 o dict continua `{"x", "y", "escala"}`). Reabrir o `.obim` mantem a rotacao. Objeto de `viewports/`
  com rotacao fora de 0/90 (lateral hostil) = `RotacaoInvalida` no `montar_svg`.
- `montar_svg` com rotacao 90: o desenho da planta (retangulo do viewBox, w x h metros) gira 90 graus horario em torno do seu canto: o canto superior esquerdo do viewBox vai
  para o canto SUPERIOR DIREITO da caixa girada, que tem largura h*1000/escala e altura w*1000/escala mm, com canto superior esquerdo em (x, y). `ViewportForaDaFolha` usa essa
  caixa girada (mesmas regras de borda: x>=10, y>=10, x+largura<=W-10, y+altura<=H-35, encostar vale, folga 1e-9). Com rotacao 0 o `transform` do `g#viewport` continua so
  translate + scale; com 90 pode ser `matrix` ou `rotate`. A espessura de linha (parte 2) e a normalizacao de viewBox (parte 1) valem igual."""
import json
import os
import re
import zipfile
from pathlib import Path

import pytest
import s06_t08_aux as A
import s06_t08f_aux as F
from s06_t08_aux import DADOS, GUID, IDENT, NS, Lado

FORMATOS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}
NOVOS = ("A2", "A1", "A0")


def aprox(obtido, esperado, tol=1e-6):
    assert len(obtido) == len(esperado) and all(abs(a - b) <= tol for a, b in zip(obtido, esperado)), f"{obtido} != {esperado}"


def planta_wh(w, h):
    """Planta com viewBox (0 0 w h) metros e um unico retangulo."""
    return f'<svg {F.SVG} viewBox="0 0 {w:g} {h:g}"><rect x="0" y="0" width="{w:g}" height="{h:g}" fill="none"/></svg>'


def cabe(m, formato, escala, w, h, x, y, rotacao):
    lado, _ = F.montar_com(formato=formato, escala=escala, x=x, y=y, rotacao=rotacao)
    try:
        m.montar_svg(lado.lat, IDENT, GUID, planta_wh(w, h))
        return True
    except m.ViewportForaDaFolha as e:
        assert type(e) is m.ViewportForaDaFolha
        return False


# ---------- formatos ----------
def test_01_tabela_de_formatos():
    m = F.P(formato="A0")
    assert m.FORMATOS == FORMATOS


@pytest.mark.parametrize("formato", list(FORMATOS))
def test_02_folha_moldura_e_carimbo_em_todos_os_formatos(formato):
    F.P(formato="A0")
    W, H = FORMATOS[formato]
    svg = A.saida(formato=formato, escala=100, x=20, y=20)
    assert A.folha_mm(svg) == (W, H)
    raiz = __import__("xml.etree.ElementTree", fromlist=["x"]).fromstring(svg)
    rects = {e.get("id"): e for e in raiz.iter(NS + "rect") if e.get("id")}
    folha, mol, cx = rects["folha"], rects["moldura"], rects["carimbo-caixa"]
    aprox([float(folha.get(k)) for k in ("x", "y", "width", "height")], (0, 0, W, H))
    aprox([float(mol.get(k)) for k in ("x", "y", "width", "height")], (10, 10, W - 20, H - 20))
    aprox([float(cx.get(k)) for k in ("x", "y", "width", "height")], (10, H - 35, W - 20, 25))
    for t, x, y in A.textos(svg):
        fs = 4.0  # font-size de `prancha.py`; o contrato da T08 exige entre 2 e 5
        assert 10 <= x and x + 0.6 * fs * len(t) <= W - 10 and H - 35 <= y - fs and y <= H - 10, (t, x, y)
    assert {t for t, _, _ in A.textos(svg)} >= {DADOS["projeto"], DADOS["titulo"], DADOS["folha"], DADOS["data"], "1:100"}


@pytest.mark.parametrize("formato", list(FORMATOS))
def test_03_area_util_de_cada_formato(formato):
    m = F.P(formato="A0")
    W, H = FORMATOS[formato]
    uw, uh = (W - 20) / 10, (H - 35 - 10) / 10  # metros a 1:100
    assert cabe(m, formato, 100, uw, uh, 10, 10, 0)
    assert not cabe(m, formato, 100, uw + 0.01, uh, 10, 10, 0)
    assert not cabe(m, formato, 100, uw, uh + 0.01, 10, 10, 0)


@pytest.mark.parametrize("formato", NOVOS)
def test_04_pdf_do_tamanho_da_folha(tmp_path, formato):
    A.exigir_qt()
    m = F.P(formato="A0")
    W, H = FORMATOS[formato]
    lado, svg = A.montar(formato=formato, x=20, y=20, escala=100)
    m.exportar_pdf(lado.lat, IDENT, GUID, svg, tmp_path / "p.pdf")
    b = (tmp_path / "p.pdf").read_bytes()
    caixas = re.findall(rb"/MediaBox\s*\[\s*([-\d. ]+)\]", b)
    assert len(caixas) == 1 and len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", b)) == 1
    x0, y0, x1, y1 = (float(v) for v in caixas[0].split())
    assert (x0, y0) == (0, 0) and abs(x1 - W * 72 / 25.4) <= 1.5 and abs(y1 - H * 72 / 25.4) <= 1.5, (caixas, formato)


def test_05_formato_ainda_invalido():
    m = F.P(formato="A0")
    for ruim in ("A5", "a2", "A00", "A2 ", "", None, 2):
        with pytest.raises(m.FormatoInvalido) as e:
            m.criar_prancha(Lado(), IDENT, **{**DADOS, "formato": ruim})
        assert type(e.value) is m.FormatoInvalido


def test_06_a2_desenhado_com_escala_e_posicao():
    A.exigir_qt()
    F.P(formato="A2")
    svg = A.saida(formato="A2", escala=50, x=100, y=60, vb=(0, 0, 12, 8), alvo=(0, 0, 12, 8))
    W, H = A.folha_mm(svg)
    aprox(A.caixa_vermelha(A.imagem(svg.encode(), W, H)), (100, 60, 240, 160), tol=0.5)


# ---------- rotacao: validacao e gravacao ----------
RUINS = [45, 180, 270, -90, 360, 91, 90.5, "90", None, True, False, float("nan"), float("inf"), [90]]


@pytest.mark.parametrize("ruim", RUINS, ids=repr)
def test_07_rotacao_invalida(ruim):
    m = F.P(rotacao=True)
    assert issubclass(m.RotacaoInvalida, m.PranchaInvalida) and issubclass(m.RotacaoInvalida, ValueError)
    lado = Lado()
    m.criar_prancha(lado, IDENT, **DADOS)
    antes = list(lado.chamadas)
    with pytest.raises(m.RotacaoInvalida) as e:
        m.colocar_viewport(lado, IDENT, GUID, 20, 20, 100, rotacao=ruim)
    assert type(e.value) is m.RotacaoInvalida
    assert lado.chamadas == antes, "validar ANTES de lado.criar"


def test_08_gravacao_e_leitura():
    m = F.P(rotacao=True)
    lado = Lado()
    m.criar_prancha(lado, IDENT, **DADOS)
    iv = m.colocar_viewport(lado, IDENT, GUID, 20, 25.5, 50, rotacao=90)
    assert lado.lat.obter("viewports", iv) == {"prancha": IDENT, "vista_guid": GUID, "x": 20, "y": 25.5, "escala": 50, "rotacao": 90}
    assert m.ler_viewport(lado.lat, IDENT, GUID) == {"x": 20, "y": 25.5, "escala": 50, "rotacao": 90}
    for kw in ({}, {"rotacao": 0}):
        l2 = Lado()
        m.criar_prancha(l2, IDENT, **DADOS)
        i2 = m.colocar_viewport(l2, IDENT, GUID, 20, 25.5, 50, **kw)
        assert l2.lat.obter("viewports", i2) == {"prancha": IDENT, "vista_guid": GUID, "x": 20, "y": 25.5, "escala": 50}, "rotacao 0 nao grava a chave"
        assert m.ler_viewport(l2.lat, IDENT, GUID) == {"x": 20, "y": 25.5, "escala": 50}
    assert type(lado.lat.obter("viewports", iv)["rotacao"]) is int


def test_09_reabrir_mantem_rotacao(tmp_path):
    m = F.P(rotacao=True)
    import openbim_app.obim_zip as Z
    from test_s06_t08_pdf_persist_oraculo import MAN
    lado, svg = F.montar_com(escala=100, x=30, y=40, rotacao=90, planta=planta_wh(21, 29))
    antes = m.montar_svg(lado.lat, IDENT, GUID, svg)
    p = tmp_path / "Casa.obim"
    Z.escrever(p, lado.lat, MAN, None)
    r = Z.ler(p)
    assert m.ler_viewport(r.lateral, IDENT, GUID) == {"x": 30, "y": 40, "escala": 100, "rotacao": 90}
    assert m.montar_svg(r.lateral, IDENT, GUID, svg) == antes
    with zipfile.ZipFile(p) as z:
        vp = [n for n in z.namelist() if n.startswith("viewports/")]
        assert len(vp) == 1 and json.loads(z.read(vp[0])) == {"prancha": IDENT, "vista_guid": GUID, "x": 30, "y": 40, "escala": 100, "rotacao": 90}


@pytest.mark.parametrize("hostil", [45, 180, True, "90", None])
def test_10_lateral_hostil(hostil):
    m = F.P(rotacao=True)
    lado, svg = F.montar_com(escala=100)
    uid = next(iter(lado.lat.ids("viewports")))
    obj = dict(lado.lat.obter("viewports", uid), rotacao=hostil)
    lado.lat._criar("viewports", "11111111-2222-4333-8444-555555555555", dict(obj, vista_guid="outra"))
    with pytest.raises(m.RotacaoInvalida):
        m.montar_svg(lado.lat, IDENT, "outra", svg)


# ---------- rotacao: geometria ----------
@pytest.mark.parametrize("escala,x,y", [(100, 20, 30), (50, 15, 12.5)])
def test_11_caixa_girada_e_origem(escala, x, y):
    A.exigir_qt()
    F.P(rotacao=True)
    s = 1000.0 / escala
    lado, _ = F.montar_com(escala=escala, x=x, y=y, rotacao=90)
    plano = A.planta(vb=(0, 0, 10, 6), alvo=(0, 0, 10, 6))
    m = F.P(rotacao=True)
    svg = m.montar_svg(lado.lat, IDENT, GUID, plano)
    aprox(A.caixa_vermelha(A.imagem(svg.encode(), *A.folha_mm(svg))), (x, y, 6 * s, 10 * s), tol=0.5)
    lado0, _ = F.montar_com(escala=escala, x=x, y=y, rotacao=0)
    svg0 = m.montar_svg(lado0.lat, IDENT, GUID, plano)
    aprox(A.caixa_vermelha(A.imagem(svg0.encode(), *A.folha_mm(svg0))), (x, y, 10 * s, 6 * s), tol=0.5)


@pytest.mark.parametrize("escala", [50, 100])
def test_12_sentido_horario_com_viewbox_fora_da_origem(escala):
    A.exigir_qt()
    m = F.P(rotacao=True)
    s = 1000.0 / escala
    x, y = 30, 15
    # viewBox (-1,-1,12,8); marca vermelha em (0,0,2,1) m = canto superior esquerdo do desenho (a 1 m da borda do viewBox)
    lado, plano = F.montar_com(escala=escala, x=x, y=y, rotacao=90, planta=A.planta(vb=(-1, -1, 12, 8), alvo=(0, 0, 2, 1)))
    svg = m.montar_svg(lado.lat, IDENT, GUID, plano)
    # horario: o ponto (u, v) do viewBox (u para a direita, v para baixo) vai para (x + (h - v)*s, y + u*s), h = 8
    esperado = (x + (8 - 2) * s, y + 1 * s, 1 * s, 2 * s)
    aprox(A.caixa_vermelha(A.imagem(svg.encode(), *A.folha_mm(svg))), esperado, tol=0.5)


def test_13_planta_do_motor_girada_sem_viewbox():
    A.exigir_qt()
    m = F.P("normalizar_planta", rotacao=True)
    lado, _ = F.montar_com(escala=100, x=20, y=30, rotacao=90)
    plano = f'<svg {F.SVG}><rect x="-2" y="-1" width="8" height="5.2" fill="#ff0000"/></svg>'  # viewBox sera (-2.5,-1.5, 9, 6.2); girado: 62 x 90 mm
    svg = m.montar_svg(lado.lat, IDENT, GUID, plano)
    # (u, v) = (0,5 .. 8,5 ; 0,5 .. 5,7) m no viewBox -> x = 20 + (6,2 - v)*10, y = 30 + u*10
    aprox(A.caixa_vermelha(A.imagem(svg.encode(), *A.folha_mm(svg))), (20 + (6.2 - 5.7) * 10, 30 + 0.5 * 10, 52, 80), tol=0.6)


# ---------- rotacao: ViewportForaDaFolha ----------
def test_14_casa_de_21_por_29_m():
    m = F.P(rotacao=True, formato="A2")
    assert not cabe(m, "A3", 100, 21, 29, 10, 10, 0), "290 mm de altura > 252 mm de area util de A3"
    assert cabe(m, "A3", 100, 21, 29, 10, 10, 90), "girada: 290 x 210 mm cabe"
    assert not cabe(m, "A3", 75, 21, 29, 10, 10, 90), "girada a 1:75: 387 x 280 mm; 280 > 252"
    assert cabe(m, "A3", 100, 21, 29, 120, 52, 90) and not cabe(m, "A3", 100, 21, 29, 120.001, 52, 90) and not cabe(m, "A3", 100, 21, 29, 120, 52.001, 90)
    for rot in (0, 90):
        assert cabe(m, "A2", 100, 21, 29, 10, 10, rot), "em A2 cabe nos dois sentidos"
    assert not cabe(m, "A2", 50, 21, 29, 10, 10, 90), "1:50 girada: 580 x 420 mm; 580 > 574"
    assert not cabe(m, "A2", 50, 21, 29, 10, 10, 0), "1:50: 420 x 580 mm; 580 > 375"


@pytest.mark.parametrize("formato", list(FORMATOS))
def test_15_fronteira_exata_girada(formato):
    m = F.P(rotacao=True, formato="A0")
    W, H = FORMATOS[formato]
    uw, uh = (W - 20) / 10, (H - 45) / 10  # area util em metros a 1:100
    # planta w x h girada ocupa h*10 de largura e w*10 de altura: w = uh, h = uw encosta nos quatro lados
    assert cabe(m, formato, 100, uh, uw, 10, 10, 90)
    assert not cabe(m, formato, 100, uh + 0.01, uw, 10, 10, 90) and not cabe(m, formato, 100, uh, uw + 0.01, 10, 10, 90)
    assert cabe(m, formato, 100, 1, 1, 10 + uw * 10 - 10, 10 + uh * 10 - 10, 90)
    assert not cabe(m, formato, 100, 1, 1, 10 + uw * 10 - 10 + 0.001, 10, 90) and not cabe(m, formato, 100, 1, 1, 10, 10 + uh * 10 - 10 + 0.001, 90)
    # a mesma planta sem girar nao cabe quando uw != uh (largura e altura trocadas)
    assert cabe(m, formato, 100, uw, uh, 10, 10, 0) and not cabe(m, formato, 100, uh, uw, 10, 10, 0)


def test_16_girar_pode_fazer_caber_e_pode_deixar_de_caber():
    m = F.P(rotacao=True)
    assert cabe(m, "A3", 100, 40, 25, 10, 10, 0) and not cabe(m, "A3", 100, 40, 25, 10, 10, 90)  # 400 x 250 cabe; 250 x 400 nao
    assert not cabe(m, "A3", 100, 25.3, 40, 10, 10, 0) and cabe(m, "A3", 100, 25.2, 40, 10, 10, 90)


def test_17_carimbo_e_moldura_nao_mudam_com_rotacao():
    m = F.P(rotacao=True)
    for formato in ("A4", "A2"):
        l0, s0 = F.montar_com(formato=formato, rotacao=0, planta=A.planta())
        l9, s9 = F.montar_com(formato=formato, rotacao=90, planta=A.planta())
        a, b = m.montar_svg(l0.lat, IDENT, GUID, s0), m.montar_svg(l9.lat, IDENT, GUID, s9)
        tira = lambda t: re.sub(r'<g id="viewport".*?</g>', "", t, flags=re.S)
        assert tira(a) == tira(b)
        assert A.textos(a) == A.textos(b)


def test_18_pdf_girado(tmp_path):
    A.exigir_qt()
    m = F.P(rotacao=True)
    lado, svg = F.montar_com(formato="A3", escala=100, x=10, y=10, rotacao=90, planta=planta_wh(21, 29))
    m.exportar_pdf(lado.lat, IDENT, GUID, svg, tmp_path / "p.pdf")
    assert (tmp_path / "p.pdf").read_bytes().startswith(b"%PDF-")
    lado2, _ = F.montar_com(formato="A3", escala=100, x=10, y=10, rotacao=0)
    with pytest.raises(m.ViewportForaDaFolha):
        m.exportar_pdf(lado2.lat, IDENT, GUID, svg, tmp_path / "q.pdf")
    assert not (tmp_path / "q.pdf").exists()
