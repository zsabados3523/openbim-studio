# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T14d: chaves em ingles no `.obim` para `prancha.py` (`titleblock` e `rotation`).

Escopo (chaves gravadas no `.obim` / lateral):
- `sheets/<id>.json`: `carimbo` -> `titleblock`; subchaves `projeto`,`titulo`,`data`,`folha` -> `project`,`title`,`date`,`sheet`.
- `viewports/<id>.json`: `rotacao` -> `rotation` (so existe quando vale 90; ausente em 0).
NAO mudam: ids do SVG (`carimbo`, `carimbo-caixa`), nomes/argumentos/retorno da API Python (`ler_viewport` devolve `escala` e `rotacao`), mensagens e excecoes."""
import json
import re
import xml.etree.ElementTree as ET
import zipfile

import pytest
import s06_t04_aux as A
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)

LADO = "6c2f7b50-8e1f-4d63-ab54-2d1ef6b80177"
GID = "2xQ0hZ1u8Ek9aBc3DeFgHi"
G1, G2, G3 = "0$Fq3Zk1D5Pv2wX4yAbC_E", "3cUz$7rQ0aLm9XyN2bP_Hd", "1aBcDeFgHiJkLmNoPqRsTu"
IDENT = "A-01"
NS = "{http://www.w3.org/2000/svg}"
PLANTA_10x6 = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 6"><rect x="0" y="0" width="10" height="6" fill="none"/></svg>'
PLANTA_21x29 = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 29"><rect x="0" y="0" width="21" height="29" fill="none"/></svg>'
DADOS_PRANCHA = {"formato": "A3", "projeto": "Casa da Colina", "titulo": "Planta Terreo", "data": "2026-11-25", "folha": "01/02"}
CHAVES_ANTIGAS_RE = re.compile(r'"(carimbo|rotacao|projeto|titulo|data|folha)"\s*:')


class _LadoEspiao:
    def __init__(self):
        from openbim_app.lateral import Lateral
        self.lat, self.chamadas = Lateral(), []

    def criar(self, colecao, uid, obj):
        self.chamadas.append((colecao, uid, obj))
        self.lat._criar(colecao, uid, obj)


def _exato(erro, chamada):
    with pytest.raises(erro) as exc:
        chamada()
    assert type(exc.value) is erro, f"esperava {erro.__name__}, veio {type(exc.value).__name__}"
    return exc.value


def _criar_sessao(tmp_path):
    exigir()
    from openbim_app.lateral import Lateral
    from openbim_app.sessao_modelo import SessaoModelo
    from openbim_app.transacao import Historico

    arq = A.novo_arquivo("IFC4")
    destino = tmp_path / "obra" / "Casa.ifc"
    pasta = tmp_path / "local" / "projetos" / LADO
    destino.parent.mkdir(parents=True, exist_ok=True)
    pasta.mkdir(parents=True, exist_ok=True)
    sessao, lat = SessaoModelo(arq), Lateral()
    hist = Historico(sessao, lat, anotar=lambda *a, **k: None)
    return arq, sessao, lat, hist, destino, pasta


def _gravar(sessao, hist, lat, destino, pasta, *, seq=1):
    import openbim_app.gravacao_par as GP
    return GP.gravar_par(
        sessao=sessao, historico=hist, lateral=lat, destino=destino,
        pasta_projeto=pasta, lado_id=LADO, seq=seq, carimbo=True, autosave=False,
    )


def _escrever_zip_obim(caminho, objetos):
    man = {
        "format": "obim-lateral", "format_version": "0.2.0", "SideId": LADO, "Revision": 1,
        "ifc_name": "Casa.ifc", "ifc_sha256": "0" * 64, "ifc_size": 100,
        "ifc_project_globalid": GID, "program_version": "0.1.0", "date": "2026-11-25T00:00:00Z",
    }
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(man))
        for col, itens in objetos.items():
            for uid, obj in itens.items():
                z.writestr(f"{col}/{uid}.json", json.dumps(obj))
    return caminho


_SEM = object()  # sentinela: None e valor invalido a testar


def _objs_novos(*, rotacao=_SEM, titleblock=_SEM):
    tb = (
        {"project": DADOS_PRANCHA["projeto"], "title": DADOS_PRANCHA["titulo"],
         "date": DADOS_PRANCHA["data"], "sheet": DADOS_PRANCHA["folha"]}
        if titleblock is _SEM else titleblock
    )
    vp = {"sheet": IDENT, "view_guid": G1, "x": 10.0, "y": 10.0, "scale": 100.0}
    if rotacao is not _SEM:
        vp["rotation"] = rotacao
    return {
        "views": {"v1": {"view_guid": G1}},
        "sheets": {"p1": {"identification": IDENT, "format": "A3", "titleblock": tb}},
        "viewports": {"vp1": vp},
    }


def _textos_carimbo(svg):
    raiz = ET.fromstring(svg)
    grupo = next((e for e in raiz.iter(NS + "g") if e.get("id") == "carimbo"), None)
    assert grupo is not None, "g#carimbo ausente no SVG"
    caixa = next((e for e in grupo.iter(NS + "rect") if e.get("id") == "carimbo-caixa"), None)
    assert caixa is not None, "rect#carimbo-caixa ausente no SVG"
    return ["".join(t.itertext()) for t in grupo.iter(NS + "text")]


# ---------- (1) criar_prancha grava titleblock com as 4 chaves novas ----------
def test_01_criar_prancha_grava_titleblock_novo_no_lateral_e_obim(tmp_path):
    import openbim_app.prancha as P
    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            id_p = P.criar_prancha(t.lado, IDENT, **DADOS_PRANCHA)
        esperado = {
            "identification": IDENT, "format": "A3",
            "titleblock": {"project": "Casa da Colina", "title": "Planta Terreo", "date": "2026-11-25", "sheet": "01/02"},
        }
        sheet_lat = lat.obter("sheets", id_p)
        assert sheet_lat == esperado and "carimbo" not in sheet_lat
        assert not (set(sheet_lat["titleblock"]) & {"projeto", "titulo", "data", "folha"})

        _gravar(sessao, hist, lat, destino, pasta, seq=1)
        with zipfile.ZipFile(destino.with_suffix(".obim")) as z:
            bruto = z.read(f"sheets/{id_p}.json").decode("utf-8")
        assert json.loads(bruto) == esperado
        assert CHAVES_ANTIGAS_RE.search(bruto) is None, f"chave antiga no JSON bruto: {bruto}"
    finally:
        hist.encerrar()


# ---------- (2) colocar_viewport grava rotation=90 e omite em 0 ----------
def test_02_colocar_viewport_grava_rotation_90_e_omite_em_0(tmp_path):
    import openbim_app.prancha as P
    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            P.criar_prancha(t.lado, IDENT, **DADOS_PRANCHA)
            id_90 = P.colocar_viewport(t.lado, IDENT, G1, 20, 25.5, 50, rotacao=90)
            id_0 = P.colocar_viewport(t.lado, IDENT, G2, 120, 25.5, 100, rotacao=0)
            id_padrao = P.colocar_viewport(t.lado, IDENT, G3, 200, 25.5, 100)

        esp_90 = {"sheet": IDENT, "view_guid": G1, "x": 20, "y": 25.5, "scale": 50, "rotation": 90}
        esp_0 = {"sheet": IDENT, "view_guid": G2, "x": 120, "y": 25.5, "scale": 100}
        esp_padrao = {"sheet": IDENT, "view_guid": G3, "x": 200, "y": 25.5, "scale": 100}

        vp_lat_90 = lat.obter("viewports", id_90)
        assert vp_lat_90 == esp_90 and type(vp_lat_90["rotation"]) is int and "rotacao" not in vp_lat_90
        for uid, esp in ((id_0, esp_0), (id_padrao, esp_padrao)):
            vp_lat = lat.obter("viewports", uid)
            assert vp_lat == esp and "rotation" not in vp_lat and "rotacao" not in vp_lat

        _gravar(sessao, hist, lat, destino, pasta, seq=1)
        with zipfile.ZipFile(destino.with_suffix(".obim")) as z:
            b90 = z.read(f"viewports/{id_90}.json").decode("utf-8")
            b0 = z.read(f"viewports/{id_0}.json").decode("utf-8")
            bp = z.read(f"viewports/{id_padrao}.json").decode("utf-8")

        assert json.loads(b90) == esp_90 and '"rotacao"' not in b90
        assert json.loads(b0) == esp_0 and '"rotation"' not in b0 and '"rotacao"' not in b0
        assert json.loads(bp) == esp_padrao and '"rotation"' not in bp and '"rotacao"' not in bp
    finally:
        hist.encerrar()


# ---------- (3) ida e volta: gravar, reabrir, ler_viewport e SVG ----------
def test_03_ida_e_volta_ler_viewport_e_svg_com_rotacao_90_e_0(tmp_path):
    import openbim_app.obim_zip as Z
    import openbim_app.prancha as P
    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            id_p = P.criar_prancha(t.lado, IDENT, **DADOS_PRANCHA)
            id_v90 = P.colocar_viewport(t.lado, IDENT, G1, 10, 10, 100, rotacao=90)
            P.colocar_viewport(t.lado, IDENT, G2, 20, 25.5, 100, rotacao=0)

        svg90_antes = P.montar_svg(lat, IDENT, G1, PLANTA_21x29)
        svg0_antes = P.montar_svg(lat, IDENT, G2, PLANTA_10x6)
        _gravar(sessao, hist, lat, destino, pasta, seq=1)

        lido = Z.ler(destino.with_suffix(".obim"))
        assert "titleblock" in lido.lateral.obter("sheets", id_p)
        assert lido.lateral.obter("viewports", id_v90).get("rotation") == 90
        # API Python mantem chaves de retorno: escala e rotacao
        assert P.ler_viewport(lido.lateral, IDENT, G1) == {"x": 10, "y": 10, "escala": 100, "rotacao": 90}
        assert P.ler_viewport(lido.lateral, IDENT, G2) == {"x": 20, "y": 25.5, "escala": 100}

        # 21x29 m em 1:100 so cabe em A3 girada 90 graus (290x210 mm <= 400x252 mm)
        svg90_depois = P.montar_svg(lido.lateral, IDENT, G1, PLANTA_21x29)
        svg0_depois = P.montar_svg(lido.lateral, IDENT, G2, PLANTA_10x6)
        assert svg90_depois == svg90_antes and svg0_depois == svg0_antes

        textos = _textos_carimbo(svg90_depois)
        for esperado in ("Casa da Colina", "Planta Terreo", "2026-11-25", "01/02", "1:100"):
            assert textos.count(esperado) == 1, f"{esperado!r} ausente ou duplicado em {textos}"

        vp90_el = next(e for e in ET.fromstring(svg90_depois).iter(NS + "g") if e.get("id") == "viewport")
        vp0_el = next(e for e in ET.fromstring(svg0_depois).iter(NS + "g") if e.get("id") == "viewport")
        assert vp90_el.get("transform", "").startswith("matrix(0 10 -10 0 ")
        assert vp0_el.get("transform", "").startswith("translate(")
    finally:
        hist.encerrar()


def test_04_obim_puro_com_chaves_novas_e_lido_por_ler_viewport_e_montar_svg(tmp_path):
    import openbim_app.obim_zip as Z
    import openbim_app.prancha as P
    lido = Z.ler(_escrever_zip_obim(tmp_path / "novo.obim", _objs_novos(rotacao=90)))
    assert P.ler_viewport(lido.lateral, IDENT, G1) == {"x": 10.0, "y": 10.0, "escala": 100.0, "rotacao": 90}
    svg = P.montar_svg(lido.lateral, IDENT, G1, PLANTA_21x29)
    assert {"Casa da Colina", "Planta Terreo", "2026-11-25", "01/02", "1:100"} <= set(_textos_carimbo(svg))


# ---------- (4) valores invalidos rejeitados com as mesmas excecoes ----------
@pytest.mark.parametrize(
    "campo,valor",
    [("data", "2026-02-30"), ("data", "2026-13-01"), ("data", "2027-02-29"), ("folha", ""), ("folha", "   "),
     ("projeto", "Casa\x00A"), ("titulo", "Planta\nB"), ("folha", "01\x1f/02")],
    ids=["data_30_fev", "data_mes_13", "data_nao_bissexto", "folha_vazia", "folha_espacos", "ctrl_projeto", "ctrl_titulo", "ctrl_folha"],
)
def test_05_criar_prancha_rejeita_valores_invalidos_antes_de_gravar(campo, valor):
    import openbim_app.prancha as P
    lado = _LadoEspiao()
    _exato(P.PranchaInvalida, lambda: P.criar_prancha(lado, IDENT, **{**DADOS_PRANCHA, campo: valor}))
    assert lado.chamadas == []


@pytest.mark.parametrize("rot", [45, True, "90", False, -90, 180, None], ids=repr)
def test_06_colocar_viewport_rejeita_rotacao_invalida_antes_de_gravar(rot):
    import openbim_app.prancha as P
    lado = _LadoEspiao()
    assert issubclass(P.RotacaoInvalida, P.PranchaInvalida)
    _exato(P.RotacaoInvalida, lambda: P.colocar_viewport(lado, IDENT, G1, 20, 20, 100, rotacao=rot))
    assert lado.chamadas == []


@pytest.mark.parametrize("tb_ruim", [None, "texto", 5, ["a"]], ids=["none", "str", "int", "list"])
def test_07_montar_svg_rejeita_titleblock_nao_dict(tb_ruim):
    import openbim_app.prancha as P
    from openbim_app.lateral import Lateral
    objs = _objs_novos(titleblock=tb_ruim)
    _exato(P.PranchaInvalida, lambda: P.montar_svg(Lateral(objs), IDENT, G1, PLANTA_10x6))


@pytest.mark.parametrize("ausente", ["project", "title", "date", "sheet"])
def test_08_montar_svg_rejeita_subchave_de_titleblock_faltando(ausente):
    import openbim_app.prancha as P
    from openbim_app.lateral import Lateral
    objs = _objs_novos()
    objs["sheets"]["p1"]["titleblock"].pop(ausente)
    _exato(P.PranchaInvalida, lambda: P.montar_svg(Lateral(objs), IDENT, G1, PLANTA_10x6))


@pytest.mark.parametrize(
    "campo,valor",
    [("date", "2026-02-30"), ("date", "2026-13-01"), ("project", "A\x00B"), ("title", "T\n1"), ("sheet", "01\x1f/02")],
    ids=["date_30_fev", "date_mes_13", "ctrl_project", "ctrl_title", "ctrl_sheet"],
)
def test_09_montar_svg_rejeita_valores_invalidos_no_titleblock(campo, valor):
    import openbim_app.prancha as P
    from openbim_app.lateral import Lateral
    objs = _objs_novos()
    objs["sheets"]["p1"]["titleblock"][campo] = valor
    _exato(P.PranchaInvalida, lambda: P.montar_svg(Lateral(objs), IDENT, G1, PLANTA_10x6))


@pytest.mark.parametrize("rot", [45, True, "90", False, -90, 180, None], ids=repr)
def test_10_montar_svg_rejeita_rotation_invalida_no_lateral(rot):
    import openbim_app.prancha as P
    from openbim_app.lateral import Lateral
    _exato(P.RotacaoInvalida, lambda: P.montar_svg(Lateral(_objs_novos(rotacao=rot)), IDENT, G1, PLANTA_10x6))


# ---------- (5) .obim com chave antiga carimbo/rotacao recusado (sem migracao) ----------
def test_11_obim_com_carimbo_antigo_recusado_sem_migracao(tmp_path):
    import openbim_app.obim_zip as Z
    import openbim_app.prancha as P

    objs_carimbo = {
        "views": {"v1": {"view_guid": G1}},
        "sheets": {"p1": {"identification": IDENT, "format": "A3",
                          "carimbo": {"projeto": "Casa", "titulo": "Planta", "data": "2026-11-25", "folha": "01/01"}}},
        "viewports": {"vp1": {"sheet": IDENT, "view_guid": G1, "x": 10.0, "y": 10.0, "scale": 100.0}},
    }
    lido = Z.ler(_escrever_zip_obim(tmp_path / "carimbo_antigo.obim", objs_carimbo))
    with pytest.raises(P.PranchaInvalida):
        P.montar_svg(lido.lateral, IDENT, G1, PLANTA_10x6)

    objs_sub = _objs_novos(titleblock={"projeto": "Casa", "titulo": "Planta", "data": "2026-11-25", "folha": "01/01"})
    lido_sub = Z.ler(_escrever_zip_obim(tmp_path / "sub_antigas.obim", objs_sub))
    with pytest.raises(P.PranchaInvalida):
        P.montar_svg(lido_sub.lateral, IDENT, G1, PLANTA_10x6)


@pytest.mark.parametrize("rot_antiga", [90, 0], ids=["rotacao_90", "rotacao_0"])
def test_12_obim_com_rotacao_antiga_recusado_sem_silencio(tmp_path, rot_antiga):
    import openbim_app.obim_zip as Z
    import openbim_app.prancha as P
    objs = _objs_novos()
    objs["viewports"]["vp1"]["rotacao"] = rot_antiga
    lido = Z.ler(_escrever_zip_obim(tmp_path / f"rot_{rot_antiga}.obim", objs))
    with pytest.raises(P.PranchaInvalida):
        P.montar_svg(lido.lateral, IDENT, G1, PLANTA_10x6)
    with pytest.raises(P.PranchaInvalida):
        P.ler_viewport(lido.lateral, IDENT, G1)


# ---------- (6) varredura de texto bruto no zip de um projeto completo ----------
def test_13_varredura_texto_bruto_zip_projeto_completo_sem_chaves_antigas(tmp_path):
    import openbim_app.prancha as P
    _, sessao, lat, hist, destino, pasta = _criar_sessao(tmp_path)
    try:
        with sessao.escrever() as esc, hist.transacao(esc) as t:
            t.lado.criar("views", "v1", {"view_guid": G1})
            t.lado.criar("views", "v2", {"view_guid": G2})
            P.criar_prancha(t.lado, IDENT, **DADOS_PRANCHA)
            P.colocar_viewport(t.lado, IDENT, G1, 10, 10, 100, rotacao=90)
            P.colocar_viewport(t.lado, IDENT, G2, 20, 25.5, 100, rotacao=0)
        _gravar(sessao, hist, lat, destino, pasta, seq=1)

        achados, vistos = [], {}
        with zipfile.ZipFile(destino.with_suffix(".obim")) as z:
            for nome in z.namelist():
                if nome.endswith(".json"):
                    txt = z.read(nome).decode("utf-8")
                    vistos[nome] = txt
                    achados.extend((nome, m.group(1)) for m in CHAVES_ANTIGAS_RE.finditer(txt))

        assert "manifest.json" in vistos
        assert any(n.startswith("sheets/") for n in vistos)
        assert sum(n.startswith("viewports/") for n in vistos) == 2
        assert not achados, f"chaves antigas encontradas no .obim: {achados}"
        junto = "\n".join(vistos.values())
        assert '"titleblock":' in junto and '"rotation":90' in junto
    finally:
        hist.encerrar()
