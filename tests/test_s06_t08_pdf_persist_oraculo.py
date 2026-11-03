# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08, PDF, reabrir o projeto e IFC intocado. Contrato (API) no docstring de `test_s06_t08_prancha_oraculo.py`.
PDF: sem dependencia nova. O ambiente `openbim` NAO tem leitor de PDF nem QtPdf (conferido); a referencia usa `QSvgRenderer` + `QPdfWriter` (PySide6, ja no ambiente) e
`exportar_pdf` cria `QGuiApplication` se nao houver. Conferencia do PDF: (1) so com stdlib: cabecalho `%PDF`, 1 pagina, `MediaBox` do tamanho da folha; (2) se houver
`pdftoppm` (poppler, ferramenta de teste, NAO e dependencia do programa), desenha o PDF e mede o retangulo vermelho (escala e posicao no papel). Sem `pdftoppm`, o
item (2) pula (falha com OBIM_S06_OBRIGATORIO=1)."""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import s06_t08_aux as A
from obrigatorio import pular
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401  (fixtures)
from s06_t08_aux import DADOS, GUID, IDENT, Lado, medir, montar

pytestmark = pytest.mark.xfail(strict=True, raises=(ImportError, AttributeError, AssertionError, TypeError, NameError, KeyError),
                               reason="@AINDA_NAO: openbim_app/prancha.py ainda nao existe (F0-S06-T08)")
MAN = {"formato": "obim-lateral", "versao_formato": "0.2.0", "LadoId": "l", "Revisao": 1, "ifc_nome": "Casa.ifc", "ifc_sha256": "0" * 64, "ifc_tamanho": 1,
       "ifc_projeto_globalid": "p", "programa_versao": "0.1.0", "data": "2026-11-01T00:00:00Z"}
UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def P():
    import openbim_app.prancha as m
    return m


@pytest.fixture(scope="module")
def qt():
    return A.exigir_qt()


# ---------- PDF ----------
def pdf_info(caminho):
    b = Path(caminho).read_bytes()
    caixas = re.findall(rb"/MediaBox\s*\[\s*([-\d. ]+)\]", b)
    return b, [[float(v) for v in c.split()] for c in caixas], len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", b))


@pytest.mark.parametrize("formato,W,H", [("A3", 420, 297), ("A4", 297, 210)])
def test_01_pdf_valido_uma_pagina_do_tamanho_da_folha(qt, tmp_path, formato, W, H):
    m = P()
    lado, svg = montar(formato=formato, x=20, y=20, escala=100)
    destino = tmp_path / "Planta.pdf"
    r = m.exportar_pdf(lado.lat, IDENT, GUID, svg, destino)
    assert str(r) == str(destino) and os.listdir(tmp_path) == ["Planta.pdf"]
    b, caixas, paginas = pdf_info(destino)
    assert b.startswith(b"%PDF-") and b.rstrip().endswith(b"%%EOF")
    assert paginas == 1 and re.search(rb"/Count\s+1(?!\d)", b), f"PDF tem {paginas} paginas"
    assert len(caixas) == 1 and len(caixas[0]) == 4, caixas
    x0, y0, x1, y1 = caixas[0]
    assert (x0, y0) == (0, 0)
    assert abs(x1 - W * 72 / 25.4) <= 1.5 and abs(y1 - H * 72 / 25.4) <= 1.5, f"MediaBox {caixas[0]} nao e {formato} paisagem"


def test_02_pdf_sem_qguiapplication_previa(tmp_path):
    P()  # em processo limpo, sem app Qt criado antes: a funcao se vira
    codigo = ("import sys; sys.path[:0] = [%r, %r]; import s06_t08_aux as A, openbim_app.prancha as m; "
              "lado, svg = A.montar(); m.exportar_pdf(lado.lat, A.IDENT, A.GUID, svg, %r)"
              % (str(Path(__file__).resolve().parent.parent / "app"), str(Path(__file__).resolve().parent), str(tmp_path / "x.pdf")))
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "x.pdf").read_bytes().startswith(b"%PDF-")


def test_03_pdf_com_erro_nao_cria_nem_altera(qt, tmp_path):
    m = P()
    lado, svg = montar(formato="A4", escala=100, x=500)
    destino = tmp_path / "Planta.pdf"
    with pytest.raises(m.ViewportForaDaFolha):
        m.exportar_pdf(lado.lat, IDENT, GUID, svg, destino)
    with pytest.raises(m.SvgInvalido):
        m.exportar_pdf(montar()[0].lat, IDENT, GUID, "<svg", destino)
    with pytest.raises(m.PranchaNaoEncontrada):
        m.exportar_pdf(montar()[0].lat, "A-99", GUID, svg, destino)
    assert os.listdir(tmp_path) == []
    destino.write_bytes(b"antigo")
    with pytest.raises(m.ViewportForaDaFolha):
        m.exportar_pdf(lado.lat, IDENT, GUID, svg, destino)
    assert destino.read_bytes() == b"antigo"


@pytest.mark.parametrize("escala,formato,x,y", [(50, "A3", 20, 20), (100, "A3", 20, 20), (50, "A4", 20, 10), (100, "A4", 30, 40)])
def test_04_pdf_desenhado_tem_escala_e_posicao(qt, tmp_path, escala, formato, x, y):
    m = P()
    exe = shutil.which("pdftoppm")
    if exe is None:
        pular("S06-T08: sem pdftoppm; medida do PDF desenhado NAO FOI EXECUTADA", "OBIM_S06_OBRIGATORIO")
    lado, svg = montar(escala=escala, formato=formato, x=x, y=y)
    pdf = tmp_path / "p.pdf"
    m.exportar_pdf(lado.lat, IDENT, GUID, svg, pdf)
    dpi = 100
    subprocess.run([exe, "-r", str(dpi), "-png", "-singlefile", str(pdf), str(tmp_path / "p")], check=True, capture_output=True)
    from PySide6.QtGui import QImage
    img = QImage(str(tmp_path / "p.png"))
    assert not img.isNull()
    W, H = {"A3": (420, 297), "A4": (297, 210)}[formato]
    px = dpi / 25.4
    assert abs(img.width() - W * px) <= 3 and abs(img.height() - H * px) <= 3, (img.width(), img.height())
    caixa = A.caixa_vermelha(img.convertToFormat(QImage.Format_RGB32), px)
    assert caixa is not None, "alvo vermelho ausente no PDF"
    s = 1000 / escala
    esperado = (x + s, y + s, 10 * s, 6 * s)
    assert all(abs(a - b) <= 0.8 for a, b in zip(caixa, esperado)), f"{caixa} != {esperado}"


# ---------- reabrir ----------
def gravar_e_reabrir(tmp_path, lado, extra=None):
    import openbim_app.obim_zip as Z
    p = tmp_path / "Casa.obim"
    Z.escrever(p, lado.lat, MAN, extra)
    return p, Z.ler(p)


def test_05_reabrir_mantem_posicao_escala_e_desenho(tmp_path):
    m = P()
    lado, svg = montar(escala=62.5, x=20.125, y=33.3, vb=(0, 0, 12, 8))
    antes = m.montar_svg(lado.lat, IDENT, GUID, svg)
    p, r = gravar_e_reabrir(tmp_path, lado)
    assert m.ler_viewport(r.lateral, IDENT, GUID) == {"x": 20.125, "y": 33.3, "escala": 62.5}
    assert m.montar_svg(r.lateral, IDENT, GUID, svg) == antes
    assert medir(m.montar_svg(r.lateral, IDENT, GUID, svg))[:2] == pytest.approx((20.125, 33.3))
    import openbim_app.obim_zip as Z
    q = tmp_path / "Outra.obim"
    Z.escrever(q, r.lateral, r.manifesto)  # ler -> escrever -> ler
    assert m.montar_svg(Z.ler(q).lateral, IDENT, GUID, svg) == antes


def test_06_o_que_vai_no_zip(tmp_path):
    m = P()
    lado, _ = montar(escala=100, x=40, y=50)
    p, _ = gravar_e_reabrir(tmp_path, lado)
    with zipfile.ZipFile(p) as z:
        nomes = z.namelist()
        pr = [n for n in nomes if n.startswith("pranchas/")]
        vp = [n for n in nomes if n.startswith("viewports/")]
        assert len(pr) == 1 and len(vp) == 1, nomes
        assert UUID4.fullmatch(Path(pr[0]).stem) and UUID4.fullmatch(Path(vp[0]).stem), "o nome do arquivo e um UUID4, nunca a chave"
        assert json.loads(z.read(pr[0])) == {"identification": IDENT, "formato": "A3",
                                             "carimbo": {k: DADOS[k] for k in ("projeto", "titulo", "data", "folha")}}
        assert json.loads(z.read(vp[0])) == {"prancha": IDENT, "vista_guid": GUID, "x": 40, "y": 50, "escala": 100}
    assert not [n for n in nomes if n.startswith(("vistas/", "styles/"))], "T08 nao cria vista nem estilo no .obim"


def test_07_par_prancha_vista_repetido_e_recusado_na_gravacao(tmp_path):
    import openbim_app.obim_zip as Z
    m = P()
    lado, _ = montar()
    m.colocar_viewport(lado, IDENT, GUID, 30, 30, 100)  # segundo viewport do mesmo par
    with pytest.raises(Z.ObimInvalido):
        Z.escrever(tmp_path / "Casa.obim", lado.lat, MAN)
    assert not (tmp_path / "Casa.obim").exists()


def test_08_ids_do_lateral_sao_uuid4_e_distintos(tmp_path):
    m = P()
    lado = Lado()
    ids = {m.criar_prancha(lado, f"A-{i}", **DADOS) for i in range(3)} | {m.colocar_viewport(lado, "A-0", f"G{i}", 20, 20, 50) for i in range(3)}
    assert len(ids) == 6 and all(UUID4.fullmatch(i) for i in ids)


# ---------- IFC intocado, dentro da transacao ----------
@pytest.fixture
def proj(tmp_path, base_ifc, monkeypatch):
    exigir()
    from test_s05_t07_par_oraculo import Proj
    for v in ("OBIM_S05_FALHA_EM", "OBIM_S05_MORRER_EM"):
        monkeypatch.delenv(v, raising=False)
    p = Proj(tmp_path, base_ifc)
    yield p
    p.h.encerrar()


def test_09_gravar_par_com_prancha_nao_toca_o_ifc_e_reabre(proj):
    from s05_conteudo_aux import foto
    from s05_t07_aux import LADO, SEQ
    import openbim_app.gravacao_par as G
    import openbim_app.obim_zip as Z
    m = P()
    with proj.s.escrever() as esc, proj.h.transacao(esc) as t:  # so o lateral muda; nenhuma chamada ao ifc na prancha
        m.criar_prancha(t.lado, IDENT, **DADOS)
        m.colocar_viewport(t.lado, IDENT, GUID, 20.5, 30.25, 50)
    svg = A.planta()
    antes = m.montar_svg(proj.lat, IDENT, GUID, svg)
    foto_antes = foto(proj.f, sem_pset_obim=True)
    G.gravar_par(sessao=proj.s, historico=proj.h, lateral=proj.lat, destino=proj.destino, pasta_projeto=proj.pasta, lado_id=LADO, seq=SEQ)
    import ifcopenshell
    assert foto(ifcopenshell.open(str(proj.destino)), sem_pset_obim=True) == foto_antes, "a prancha mexeu no IFC"
    r = Z.ler(proj.destino.with_suffix(".obim"))
    assert r.manifesto["versao_formato"] == "0.2.0"
    assert m.ler_viewport(r.lateral, IDENT, GUID) == {"x": 20.5, "y": 30.25, "escala": 50}
    assert m.montar_svg(r.lateral, IDENT, GUID, svg) == antes
    assert r.lateral.ids("notas"), "o resto do lateral tem de continuar"


def test_10_desfazer_tira_prancha_e_viewport_juntos(proj):
    m = P()
    with proj.s.escrever() as esc, proj.h.transacao(esc) as t:
        m.criar_prancha(t.lado, IDENT, **DADOS)
        m.colocar_viewport(t.lado, IDENT, GUID, 20, 20, 50)
    assert proj.lat.ids("pranchas") and proj.lat.ids("viewports")
    with proj.s.escrever() as esc:
        proj.h.desfazer(esc)
    assert not proj.lat.ids("pranchas") and not proj.lat.ids("viewports")
