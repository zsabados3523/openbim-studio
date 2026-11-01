# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08, prancha minima (1 viewport + carimbo fixo, SVG). Fontes: cartao T08; ADR-003 §3.2, §4 e §5 (viewport no `.obim` guarda
`prancha`, `vista_guid`, `x`, `y`, `escala`); P5 do README da S06 (carimbo simples: nome do projeto, titulo, escala, data, folha; sem NBR 13142).
So o autor do oraculo tira os `@AINDA_NAO` (xfail estrito). O PDF, o reabrir e o IFC ficam em `test_s06_t08_pdf_persist_oraculo.py`.
CONTRATO (nomes PROPOSTOS NESTE TESTE; o ADR e o cartao nao nomeiam a API). `openbim_app/prancha.py`, so stdlib no import (sem Qt, sem ifcopenshell;
o Qt entra DENTRO de `exportar_pdf`, depois que a funcao cria `QGuiApplication` se nao houver uma):
- `FORMATOS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}` (largura, altura em mm, paisagem); `MARGEM_MM = 10.0`; `CARIMBO_ALTURA_MM = 25.0`.
- Erros, todos `ValueError` e subclasses de `PranchaInvalida`: `FormatoInvalido`, `EscalaInvalida`, `SvgInvalido`, `ViewportForaDaFolha`, `PranchaNaoEncontrada`.
- `criar_prancha(lado, identification, formato, projeto, titulo, data, folha) -> id`: `lado` = o que `t.lado` da transacao oferece (`criar(colecao, id, obj)`).
  Cria `pranchas/<uuid4>`: `{"identification", "formato", "carimbo": {"projeto", "titulo", "data", "folha"}}`. `identification` texto nao vazio sem espaco
  nas pontas (`PranchaInvalida`); `formato` em FORMATOS (`FormatoInvalido`); `projeto`, `titulo`, `folha` texto nao vazio; `data` "AAAA-MM-DD" de calendario
  real (`PranchaInvalida`). Valida ANTES de chamar `lado.criar`.
- `colocar_viewport(lado, identification, vista_guid, x_mm, y_mm, escala) -> id`: cria `viewports/<uuid4>`: `{"prancha", "vista_guid", "x", "y", "escala"}`.
  `x_mm`, `y_mm` = canto superior esquerdo, na folha, do retangulo do `viewBox` da planta. `escala` = denominador (50 = 1:50): numero finito > 0, nao `bool`
  (`EscalaInvalida`). x e y numeros finitos (`PranchaInvalida`, nao `EscalaInvalida`). Valida antes de `lado.criar`. Nao confere "fora da folha" (precisa da planta).
- `ler_viewport(lateral, identification, vista_guid) -> {"x", "y", "escala"}`; `PranchaNaoEncontrada` se nao ha o par.
- `montar_svg(lateral, identification, vista_guid, planta_svg) -> str`: `lateral` = `Lateral`. `planta_svg` (str ou bytes UTF-8) = `<svg>` com `viewBox`
  "minx miny w h" em METROS (1 unidade = 1 m; `width`/`height` da planta sao ignorados). Saida (SVG 1.1, 1 unidade = 1 mm):
  `<svg width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">` com, nesta ordem: `rect#folha` (fundo branco, 0 0 W H); `rect#moldura` (x=y=10, W-20 por H-20, sem
  preenchimento); `g#viewport` com `data-vista`=vista_guid e `transform` feito so de `translate`/`scale`, filhos da planta copiados na ordem, sem o `<svg>` raiz da
  planta, mapeando (minx, miny) para (x, y) e 1 m para 1000/escala mm; `g#carimbo` com `rect#carimbo-caixa` (x=10, y=H-35, W-20 por 25) e `<text>`s, cada valor
  (projeto, titulo, escala "1:" + `%g` da escala, data, folha) como texto INTEIRO de um `<text>` proprio com x,y dentro da caixa (rotulos em outros `<text>` sao livres).
  Escapa `& < >`. `ViewportForaDaFolha` se o retangulo do viewport (x, y, w*1000/escala, h*1000/escala) sai de x>=10, y>=10, x+w<=W-10, y+h<=H-35 (encostar vale,
  folga 1e-9). `PranchaNaoEncontrada` (prancha ou par inexistente), `SvgInvalido` (XML ruim, raiz que nao e svg, sem `viewBox`, `viewBox` ilegivel/nao positivo,
  `<!DOCTYPE`/`<!ENTITY`, tipo que nao e str/bytes). Pura: nao muda o `Lateral`; mesma entrada, mesma saida.
- `exportar_svg(lateral, identification, vista_guid, planta_svg, destino) -> Path`: grava `montar_svg(...)` em UTF-8. Erro = nada criado nem alterado em `destino`.
- `exportar_pdf(...)`: mesma assinatura (PDF, 1 pagina do tamanho da folha); em `..._pdf_persist_oraculo.py`.
GUARDA: sem PySide6 ou numpy, pula (falha com OBIM_S06_OBRIGATORIO=1; o lider pode incluir a chave em `obrigatorio.CHAVES_S05`)."""
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import s06_t08_aux as A
from s06_t08_aux import DADOS, GUID, IDENT, NS, Lado, folha_mm, medir, montar, planta, saida, textos

AINDA_NAO = pytest.mark.xfail(strict=True, raises=(ImportError, AttributeError, AssertionError, TypeError, NameError),
                              reason="@AINDA_NAO: openbim_app/prancha.py ainda nao existe (F0-S06-T08)")
pytestmark = AINDA_NAO


def P():
    import openbim_app.prancha as m  # primeira linha de cada caso: hoje e ela que da o xfail
    return m


@pytest.fixture(scope="module")
def qt():
    return A.exigir_qt()


def aprox(obtido, esperado, tol=1e-6):
    assert len(obtido) == len(esperado) and all(math.isclose(a, b, abs_tol=tol) for a, b in zip(obtido, esperado)), f"{obtido} != {esperado}"


# ---------- escala e posicao, por medida ----------
@pytest.mark.parametrize("escala,larg,alt", [(50, 200, 120), (100, 100, 60), (62.5, 160, 96), (100.0, 100, 60)])
def test_01_escala_medida_no_svg(escala, larg, alt):
    P()
    x, y = 20, 20
    svg = saida(escala=escala, x=x, y=y)
    # alvo: 10 m x 6 m, que comeca 1 m depois do canto (-1, -1) do viewBox: desloca 1 m * (1000/escala) mm
    s = 1000 / escala
    aprox(medir(svg), (x + s, y + s, larg, alt))


def test_02_exemplo_do_cartao_10_m_viram_200_e_100_mm():
    P()
    assert medir(saida(escala=50, vb=(0, 0, 10, 6), alvo=(0, 0, 10, 6)))[2:] == pytest.approx((200, 120))
    assert medir(saida(escala=100, vb=(0, 0, 10, 6), alvo=(0, 0, 10, 6)))[2:] == pytest.approx((100, 60))


def test_03_origem_do_viewbox_nao_zero_e_posicao():
    P()
    svg = saida(escala=50, x=30, y=40, vb=(100, 200, 12, 8), alvo=(101, 201, 10, 6))
    aprox(medir(svg), (30 + 20, 40 + 20, 200, 120))
    svg = saida(escala=100, x=55.5, y=12.25, vb=(-5, -3, 12, 8), alvo=(-5, -3, 3, 2))
    aprox(medir(svg), (55.5, 12.25, 30, 20))  # alvo no canto do viewBox cai exatamente em (x, y)


def test_04_largura_altura_da_planta_sao_ignoradas():
    P()  # a planta de teste declara width/height 999px; so o viewBox manda
    aprox(medir(saida(escala=100, x=20, y=20, vb=(0, 0, 12, 8), alvo=(0, 0, 12, 8)))[2:], (120, 80))


@pytest.mark.parametrize("escala,formato,x,y", [(50, "A3", 20, 20), (100, "A3", 20, 20), (50, "A4", 20, 10), (100, "A4", 30, 40)])
def test_05_escala_e_posicao_desenhadas_pelo_qt(qt, escala, formato, x, y):
    P()  # medida independente da estrutura: desenha com o Qt e mede os pixels vermelhos
    svg = saida(escala=escala, x=x, y=y, formato=formato)
    W, H = folha_mm(svg)
    obtido = A.caixa_vermelha(A.imagem(svg.encode(), W, H))
    assert obtido is not None, "o alvo vermelho nao apareceu no desenho"
    s = 1000 / escala
    aprox(obtido, (x + s, y + s, 10 * s, 6 * s), tol=0.6)


def test_06_cada_viewport_usa_sua_escala_e_sua_prancha():
    m = P()
    lado = Lado()
    m.criar_prancha(lado, "A-01", **DADOS)
    m.criar_prancha(lado, "A-02", **{**DADOS, "titulo": "Outra"})
    m.colocar_viewport(lado, "A-01", "G1", 20, 20, 50)
    m.colocar_viewport(lado, "A-01", "G2", 30, 30, 100)
    m.colocar_viewport(lado, "A-02", "G1", 40, 40, 100)
    pl = planta(vb=(0, 0, 12, 8), alvo=(0, 0, 10, 6))
    aprox(medir(m.montar_svg(lado.lat, "A-01", "G1", pl)), (20, 20, 200, 120))
    aprox(medir(m.montar_svg(lado.lat, "A-01", "G2", pl)), (30, 30, 100, 60))
    aprox(medir(m.montar_svg(lado.lat, "A-02", "G1", pl)), (40, 40, 100, 60))
    assert [t for t, *_ in textos(m.montar_svg(lado.lat, "A-02", "G1", pl)) if t == "Outra"], "carimbo da prancha errada"


# ---------- folha, margens, carimbo ----------
@pytest.mark.parametrize("formato,W,H", [("A3", 420, 297), ("A4", 297, 210)])
def test_07_folha_moldura_e_carimbo(formato, W, H):
    m = P()
    assert m.FORMATOS[formato] == (W, H) and (m.MARGEM_MM, m.CARIMBO_ALTURA_MM) == (10.0, 25.0)
    svg = saida(formato=formato, x=10, y=10, escala=100)
    assert folha_mm(svg) == (W, H)
    aprox(medir(svg, "folha"), (0, 0, W, H))
    aprox(medir(svg, "moldura"), (10, 10, W - 20, H - 20))
    aprox(medir(svg, "carimbo-caixa"), (10, H - 35, W - 20, 25))
    assert ET.fromstring(svg).get("viewBox") == f"0 0 {W} {H}"


def test_08_ordem_dos_elementos_e_marca_da_vista():
    P()
    raiz = ET.fromstring(saida())
    ids = [e.get("id") for e in raiz if e.get("id")]
    assert ids == ["folha", "moldura", "viewport", "carimbo"], ids
    assert next(e for e in raiz if e.get("id") == "viewport").get("data-vista") == GUID
    carimbo = next(e for e in raiz if e.get("id") == "carimbo")
    assert carimbo.find(NS + "rect").get("id") == "carimbo-caixa"


@pytest.mark.parametrize("escala,txt", [(50, "1:50"), (100, "1:100"), (100.0, "1:100"), (62.5, "1:62.5"), (200, "1:200")])
def test_09_texto_do_carimbo(escala, txt):
    P()
    svg = saida(escala=escala, x=10, y=10, formato="A3")
    dados = [t for t, *_ in textos(svg)]
    for esperado in (DADOS["projeto"], DADOS["titulo"], txt, DADOS["data"], DADOS["folha"]):
        assert dados.count(esperado) == 1, f"{esperado!r} deveria ser o texto inteiro de um <text> do carimbo: {dados}"
    for t, x, y in textos(svg):
        assert 10 <= x <= 410 and 262 <= y <= 287, f"texto {t!r} fora da caixa do carimbo ({x}, {y})"


def test_10_carimbo_escapa_texto_e_guarda_acentos():
    P()
    svg = saida(projeto='Casa & <Sol> "Lua"', titulo="Planta ação > térreo")
    textos_ = [t for t, *_ in textos(svg)]
    assert 'Casa & <Sol> "Lua"' in textos_ and "Planta ação > térreo" in textos_
    assert "<Sol>" not in svg


def test_11_viewport_nao_encosta_no_carimbo():
    P()
    svg = saida(escala=100, formato="A4", x=10, y=95, vb=(0, 0, 12, 8), alvo=(0, 0, 12, 8))  # termina em y=175 = topo do carimbo (A4)
    x, y, w, h = medir(svg)
    assert y + h <= medir(svg, "carimbo-caixa")[1] + 1e-6


# ---------- conteudo da planta ----------
EXTRA = ('<g id="g1" class="paredes"><line id="l1" x1="0" y1="0" x2="3" y2="4" stroke="#000"/></g>'
         '<path id="p1" d="M0 0 L1 1"/><text id="t1" x="1" y="1">Sala ação</text>')


def test_12_filhos_da_planta_copiados_e_so_dentro_do_viewport():
    P()
    lado, _ = montar()
    import openbim_app.prancha as m
    raiz = ET.fromstring(m.montar_svg(lado.lat, IDENT, GUID, planta(extra=EXTRA)))
    vp = next(e for e in raiz if e.get("id") == "viewport")
    dentro = [e.get("id") for c in vp for e in c.iter() if e.get("id")]
    assert dentro == ["alvo", "g1", "l1", "p1", "t1"], dentro
    assert (vp.find(f".//{NS}line").get("x2"), vp.find(f".//{NS}line").get("y2")) == ("3", "4")
    assert vp.find(f".//{NS}path").get("d") == "M0 0 L1 1"
    assert "".join(vp.find(f".//{NS}text").itertext()) == "Sala ação"
    fora = [e.get("id") for c in raiz if c.get("id") != "viewport" for e in c.iter() if e.get("id") in ("alvo", "g1", "l1", "p1", "t1")]
    assert not fora, f"conteudo da planta vazou para fora do viewport: {fora}"
    assert sum(1 for e in raiz.iter(NS + "svg")) == 1, "o <svg> da planta nao pode ser aninhado"


def test_13_planta_em_bytes_igual_a_texto():
    m = P()
    lado, svg = montar()
    assert m.montar_svg(lado.lat, IDENT, GUID, svg.encode("utf-8")) == m.montar_svg(lado.lat, IDENT, GUID, svg)


def test_14_pura_e_deterministica():
    m = P()
    lado, svg = montar()
    antes = bytes(lado.lat.canonico())
    a, b = m.montar_svg(lado.lat, IDENT, GUID, svg), m.montar_svg(lado.lat, IDENT, GUID, svg)
    assert a == b and bytes(lado.lat.canonico()) == antes


# ---------- o que fica no lateral ----------
def test_15_objetos_gravados_no_lateral():
    m = P()
    lado = Lado()
    ip = m.criar_prancha(lado, IDENT, **DADOS)
    iv = m.colocar_viewport(lado, IDENT, GUID, 20, 25.5, 50)
    assert lado.lat.obter("pranchas", ip) == {"identification": IDENT, "formato": "A3",
                                              "carimbo": {k: DADOS[k] for k in ("projeto", "titulo", "data", "folha")}}
    assert lado.lat.obter("viewports", iv) == {"prancha": IDENT, "vista_guid": GUID, "x": 20, "y": 25.5, "escala": 50}
    assert m.ler_viewport(lado.lat, IDENT, GUID) == {"x": 20, "y": 25.5, "escala": 50}
    assert ip != iv and len({ip, iv}) == 2
    with pytest.raises(m.PranchaNaoEncontrada):
        m.ler_viewport(lado.lat, IDENT, "outro")
    with pytest.raises(m.PranchaNaoEncontrada):
        m.ler_viewport(lado.lat, "A-99", GUID)


def test_16_hierarquia_de_erros():
    m = P()
    assert issubclass(m.PranchaInvalida, ValueError)
    for nome in ("FormatoInvalido", "EscalaInvalida", "SvgInvalido", "ViewportForaDaFolha", "PranchaNaoEncontrada"):
        assert issubclass(getattr(m, nome), m.PranchaInvalida), nome


def test_17_import_sem_qt_nem_ifcopenshell():
    app = Path(__file__).resolve().parent.parent / "app"
    codigo = (f"import sys; sys.path.insert(0, {str(app)!r}); import openbim_app.prancha as m; "
              "bad = [n for n in ('PySide6', 'ifcopenshell') if n in sys.modules]; assert not bad, bad")
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
