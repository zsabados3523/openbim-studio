# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08, ROUND 2 (aparencia e robustez), a partir da revisao do `prancha.py` do Gemini. Contrato base: docstring de
`test_s06_t08_prancha_oraculo.py`. Acrescenta ao contrato:
- ACHADO 1: `rect#moldura` e `rect#carimbo-caixa` tem atributos `stroke` (nao `none`, cor escura) e `stroke-width` > 0, e a borda aparece DESENHADA (pixels escuros no SVG
  desenhado pelo Qt e no PDF desenhado pelo `pdftoppm`).
- ACHADO 2: todo `<text>` do carimbo tem atributo `font-size` explicito (numero, ou numero com sufixo `px`/`mm`; 1 unidade = 1 mm) entre 2 e 5. Caixa estimada do texto = largura
  0,6*font-size*numero de caracteres, altura font-size, de x (ou x-largura/2 com `text-anchor="middle"`, x-largura com `end`) e de y-font-size ate y (linha de base). Cabe em
  `carimbo-caixa` e nao cruza a de outro texto. Vale para os dados normais e para nomes de tamanho medio em A4.
- ACHADO 3: caractere de controle (categoria Cc, mais U+FFFE, U+FFFF e substituto solto) em `projeto`, `titulo` ou `folha` (`criar_prancha`) ou em `vista_guid`
  (`colocar_viewport`) = `PranchaInvalida` antes de `lado.criar`. `montar_svg` nunca produz XML mal formado: entrada hostil que entrou por outro caminho (lateral lido de
  `.obim` antigo) ou levanta `PranchaInvalida` ou sai bem formada.
- ACHADO 4: `exportar_pdf` cujo SVG montado o Qt nao le = `SvgInvalido`, arquivo nao criado nem alterado (confere `QSvgRenderer.isValid()` antes de abrir o `QPdfWriter`).
- ITEM 5: `montar_svg` nao muda estado global do ElementTree (nenhum `register_namespace`; serializa com `default_namespace` local, por exemplo).
- ITEM 6: data com digitos que nao sao ASCII (fullwidth, arabe-indico) = `PranchaInvalida`.
Marcador: @AINDA_NAO_APAR (xfail estrito); so o autor do oraculo o retira."""
import os
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import s06_t08_aux as A
from obrigatorio import pular
from s06_t08_aux import DADOS, GUID, IDENT, NS, Lado, folha_mm, montar, saida

AINDA = pytest.mark.xfail(strict=True, reason="@AINDA_NAO_APAR: correcoes da revisao da T08 ainda nao feitas")  # casos 09, 12, 14, 15 e 16 sao guarda de regressao: ja passam e ficam sem marcador


def P():
    import openbim_app.prancha as m
    return m


@pytest.fixture(scope="module")
def qt():
    return A.exigir_qt()


def escuros(img):
    """Mascara numpy dos pixels escuros (r, g, b < 100) de uma QImage RGB32."""
    import numpy as np
    n = img.sizeInBytes() // img.height() // 4
    a = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), n, 4)[:, :img.width()]
    return (a[:, :, 0] < 100) & (a[:, :, 1] < 100) & (a[:, :, 2] < 100)


def fracao_borda(mask, px, x0, y0, x1, y1, tol):
    """Fracao dos pontos do segmento (mm) (x0,y0)-(x1,y1), horizontal ou vertical, que tem pixel escuro a ate `tol` pixels do segmento."""
    h, w = mask.shape
    ok = total = 0
    if x0 == x1:
        c = int(round(x0 * px))
        for r in range(int(round(y0 * px)), int(round(y1 * px))):
            total += 1
            ok += bool(mask[r, max(c - tol, 0):min(c + tol + 1, w)].any())
    else:
        r = int(round(y0 * px))
        for c in range(int(round(x0 * px)), int(round(x1 * px))):
            total += 1
            ok += bool(mask[max(r - tol, 0):min(r + tol + 1, h), c].any())
    return ok / total


def bordas(mask, px, W, H, tol):
    """Fracao minima entre as 4 bordas da moldura (10 mm da folha) e a borda de cima da caixa do carimbo, em mm; 6 mm de folga nas pontas."""
    f = [fracao_borda(mask, px, 10, 16, 10, H - 16, tol), fracao_borda(mask, px, W - 10, 16, W - 10, H - 16, tol),
         fracao_borda(mask, px, 16, 10, W - 16, 10, tol), fracao_borda(mask, px, 16, H - 10, W - 16, H - 10, tol),
         fracao_borda(mask, px, 16, H - 35, W - 16, H - 35, tol)]
    return min(f)


# ---------- achado 1: bordas visiveis ----------
@pytest.mark.parametrize("formato", ["A3", "A4"])
@AINDA
def test_01_moldura_e_caixa_tem_stroke(formato):
    P()
    raiz = ET.fromstring(saida(formato=formato, x=10, y=10, escala=100))
    for ident in ("moldura", "carimbo-caixa"):
        r = next(e for e in raiz.iter(NS + "rect") if e.get("id") == ident)
        assert r.get("stroke") not in (None, "", "none", "transparent"), f"{ident} sem stroke visivel: {r.attrib}"
        assert float(r.get("stroke-width")) > 0, f"{ident} sem stroke-width positivo"
        assert r.get("fill") in ("none", None) or r.get("fill-opacity") == "0", "a caixa nao pode tampar o que esta dentro"


@pytest.mark.parametrize("formato", ["A3", "A4"])
@AINDA
def test_02_bordas_desenhadas_pelo_qt(qt, formato):
    P()
    svg = saida(formato=formato, x=20, y=20, escala=100)
    W, H = folha_mm(svg)
    mask = escuros(A.imagem(svg.encode(), W, H))
    assert bordas(mask, A.PX_MM, W, H, 1) >= 0.98, "moldura ou caixa do carimbo nao aparece no desenho"
    miolo = fracao_borda(mask, A.PX_MM, 12.5, 16, 12.5, H - 16, 0)  # faixa entre a moldura e o conteudo: nao pode ter risco
    assert miolo <= 0.05


@pytest.mark.parametrize("formato,W,H", [("A3", 420, 297), ("A4", 297, 210)])
@AINDA
def test_03_bordas_desenhadas_no_pdf(qt, tmp_path, formato, W, H):
    m = P()
    exe = shutil.which("pdftoppm")
    if exe is None:
        pular("S06-T08: sem pdftoppm; bordas no PDF NAO FORAM CONFERIDAS", "OBIM_S06_OBRIGATORIO")
    lado, svg = montar(formato=formato, x=20, y=20, escala=100)
    m.exportar_pdf(lado.lat, IDENT, GUID, svg, tmp_path / "p.pdf")
    subprocess.run([exe, "-r", "100", "-png", "-singlefile", str(tmp_path / "p.pdf"), str(tmp_path / "p")], check=True, capture_output=True)
    from PySide6.QtGui import QImage
    img = QImage(str(tmp_path / "p.png")).convertToFormat(QImage.Format_RGB32)
    assert bordas(escuros(img), 100 / 25.4, W, H, 3) >= 0.98, "bordas nao aparecem no PDF"


# ---------- achado 2: texto do carimbo ----------
def _tam(valor):
    assert valor is not None, "<text> do carimbo sem font-size explicito"
    for suf in ("px", "mm"):
        if valor.endswith(suf):
            valor = valor[:-len(suf)]
    return float(valor)


def caixas_texto(svg):
    raiz = ET.fromstring(svg)
    g = next(e for e in raiz.iter(NS + "g") if e.get("id") == "carimbo")
    out = []
    for t in g.iter(NS + "text"):
        texto = "".join(t.itertext())
        fs = _tam(t.get("font-size"))
        w = 0.6 * fs * len(texto)
        x, y = float(t.get("x")), float(t.get("y"))
        x -= {"middle": w / 2, "end": w}.get(t.get("text-anchor", "start"), 0)
        out.append((texto, fs, x, y - fs, x + w, y))
    return out


def conferir_texto(svg, W, H):
    caixas = caixas_texto(svg)
    assert len(caixas) >= 5
    for texto, fs, x0, y0, x1, y1 in caixas:
        assert 2 <= fs <= 5, f"font-size {fs} de {texto!r} fora de 2..5 mm"
        assert x0 >= 10 and x1 <= W - 10 and y0 >= H - 35 and y1 <= H - 10, f"{texto!r} nao cabe na caixa do carimbo: {(x0, y0, x1, y1)}"
    for i, a in enumerate(caixas):
        for b in caixas[i + 1:]:
            assert a[4] <= b[2] or b[4] <= a[2] or a[5] <= b[3] or b[5] <= a[3], f"textos se sobrepoem: {a[0]!r} e {b[0]!r}"


@pytest.mark.parametrize("formato,W,H", [("A3", 420, 297), ("A4", 297, 210)])
@pytest.mark.parametrize("escala", [50, 100, 62.5])
@AINDA
def test_04_texto_do_carimbo_cabe_e_nao_se_sobrepoe(formato, W, H, escala):
    P()
    conferir_texto(saida(formato=formato, escala=escala, x=10, y=10), W, H)


@AINDA
def test_05_nomes_de_tamanho_medio_em_a4():
    P()
    svg = saida(formato="A4", escala=100, x=10, y=10, projeto="Residencia Unifamiliar Praia X", titulo="Planta baixa do pavimento terreo - Bloco A")
    conferir_texto(svg, 297, 210)
    assert any(c[0] == "Residencia Unifamiliar Praia X" for c in caixas_texto(svg))


@AINDA
def test_06_texto_do_carimbo_aparece_desenhado(qt):
    P()
    svg = saida(formato="A3", escala=100, x=20, y=20)
    mask = escuros(A.imagem(svg.encode(), 420, 297))
    px = A.PX_MM
    for texto, fs, x0, y0, x1, y1 in caixas_texto(svg):
        regiao = mask[int(y0 * px):int(y1 * px), int(x0 * px):int(x1 * px)]
        assert regiao.size and regiao.mean() > 0.02, f"{texto!r} nao foi desenhado onde a caixa estimada diz"


# ---------- achado 3: caractere de controle ----------
def _proibidos():
    cs = [chr(i) for i in range(0x20)] + [chr(0x7F), chr(0x85), chr(0x9F), "￾", "￿", "\ud800"]
    assert all(unicodedata.category(c) == "Cc" for c in cs[:35]), "lista de controles errada"
    return cs


@pytest.mark.parametrize("campo", ["projeto", "titulo", "folha"])
@pytest.mark.parametrize("c", _proibidos(), ids=lambda c: f"U+{ord(c):04X}")
@AINDA
def test_07_controle_no_carimbo_recusado(campo, c):
    m = P()
    lado = Lado()
    with pytest.raises(m.PranchaInvalida):
        m.criar_prancha(lado, IDENT, **{**DADOS, campo: f"a{c}b"})
    assert lado.chamadas == []


@pytest.mark.parametrize("c", ["\x00", "\x01", "\x1f", "\t", "\n", "\x7f", "￾", "\ud800"])
@AINDA
def test_08_controle_no_vista_guid_recusado(c):
    m = P()
    lado = Lado()
    with pytest.raises(m.PranchaInvalida):
        m.colocar_viewport(lado, IDENT, f"G{c}1", 20, 20, 50)
    assert lado.chamadas == []


BOAS = ['Casa & Filhos <Ltda>', '"aspas" \'simples\'', "ação ç ñ 日本語 😀", "a​b", "a ]]> b", "&amp; &lt;", "x y", "Casa x"]


@pytest.mark.parametrize("texto", BOAS)
def test_09_texto_estranho_mas_valido_sai_bem_formado_e_igual(texto):
    P()
    svg = saida(projeto=texto, titulo=texto, folha=texto)
    raiz = ET.fromstring(svg)  # tem de ler
    achados = ["".join(t.itertext()) for t in raiz.iter(NS + "text")]
    assert achados.count(texto) == 3


@pytest.mark.parametrize("c", ["\x00", "\x01", "\x0b", "\x1f", "￾", "￿"])
@AINDA
def test_10_montar_svg_com_lateral_hostil_nunca_sai_mal_formado(c):
    m = P()
    for campo in ("projeto", "vista"):
        lado = Lado()
        lado.lat._criar("pranchas", "p1", {"identification": IDENT, "formato": "A3", "carimbo": {
            "projeto": f"a{c}b" if campo == "projeto" else "Casa", "titulo": "T", "data": "2026-11-01", "folha": "1/1"}})
        guid = f"G{c}" if campo == "vista" else GUID
        lado.lat._criar("viewports", "v1", {"prancha": IDENT, "vista_guid": guid, "x": 20, "y": 20, "escala": 100})
        try:
            saida_ = m.montar_svg(lado.lat, IDENT, guid, A.planta())
        except m.PranchaInvalida:
            continue
        ET.fromstring(saida_)


# ---------- achado 4: Qt nao le o SVG ----------
@pytest.mark.parametrize("lixo", ["<svg", "", "nada de xml", "<svg xmlns='http://www.w3.org/2000/svg'><"])
@AINDA
def test_11_pdf_com_svg_que_o_qt_nao_le(qt, tmp_path, monkeypatch, lixo):
    m = P()
    lado, svg = montar()
    monkeypatch.setattr(m, "montar_svg", lambda *a, **k: lixo)
    destino = tmp_path / "p.pdf"
    with pytest.raises(m.SvgInvalido) as e:
        m.exportar_pdf(lado.lat, IDENT, GUID, svg, destino)
    assert type(e.value) is m.SvgInvalido
    assert os.listdir(tmp_path) == [], "criou PDF apesar do SVG ilegivel"
    destino.write_bytes(b"antigo")
    with pytest.raises(m.SvgInvalido):
        m.exportar_pdf(lado.lat, IDENT, GUID, svg, destino)
    assert destino.read_bytes() == b"antigo"


def test_12_pdf_normal_continua_valido(qt, tmp_path):
    m = P()
    lado, svg = montar()
    m.exportar_pdf(lado.lat, IDENT, GUID, svg, tmp_path / "p.pdf")
    assert (tmp_path / "p.pdf").read_bytes().startswith(b"%PDF-")


# ---------- item 5: estado global do ElementTree ----------
@AINDA
def test_13_montar_svg_nao_registra_namespace_global():
    P()
    app = Path(__file__).resolve().parent.parent / "app"
    tests = Path(__file__).resolve().parent
    codigo = (f"import sys; sys.path[:0] = [{str(app)!r}, {str(tests)!r}]\n"
              "import xml.etree.ElementTree as ET, s06_t08_aux as A, openbim_app.prancha as m\n"
              "lado, svg = A.montar(); m.montar_svg(lado.lat, A.IDENT, A.GUID, svg)\n"
              "dep = ET.tostring(ET.Element('{http://www.w3.org/2000/svg}g'), encoding='unicode')\n"
              "assert 'ns0:' in dep and 'xmlns=' not in dep, dep  # padrao do ElementTree: ninguem registrou o prefixo vazio\n"
              "assert '' not in ET._namespace_map.values(), ET._namespace_map\n")
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout


def test_14_saida_continua_lida_pelo_qt_sem_prefixo_estranho(qt):
    P()
    svg = saida()
    assert svg.startswith("<svg") and 'xmlns="http://www.w3.org/2000/svg"' in svg.split(">")[0], "raiz deve declarar o namespace como padrao"
    assert "ns0:" not in svg


# ---------- item 6: digitos Unicode ----------
@pytest.mark.parametrize("data", ["２０２６-１１-０１", "٢٠٢٦-١١-٠١", "2026-１１-01", "२०२६-११-०१"])
def test_15_data_com_digitos_nao_ascii_recusada(data):
    m = P()
    lado = Lado()
    with pytest.raises(m.PranchaInvalida):
        m.criar_prancha(lado, IDENT, **{**DADOS, "data": data})
    assert lado.chamadas == []


def test_16_data_ascii_continua_valida():
    m = P()
    lado = Lado()
    m.criar_prancha(lado, IDENT, **DADOS)
    assert lado.chamadas
