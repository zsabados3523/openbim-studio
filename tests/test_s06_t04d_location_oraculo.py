# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T04d: `Location` de pranchas distintas não pode colidir depois da limpeza do número. Contrato base: cabeçalhos de
`test_s06_t04_vistas_ifc_oraculo.py` e `test_s06_t04_lacunas_oraculo.py` (bug 7) mais:
(1) dois números diferentes ("../x" e "x") que dão o mesmo caminho limpo recebem `Location` DIFERENTES. O primeiro fica com `pranchas/x/layout.svg`
e `pranchas/x/titleblock.svg`; o segundo com a pasta sufixada: `pranchas/x-2/...`, o terceiro `-3` (mesma ideia do `_location_livre` das vistas: usa o
primeiro número livre, olhando todas as `IfcDocumentReference` do arquivo). [P: sufixo na PASTA e não no arquivo, para layout e titleblock ficarem juntos]
(2) determinismo: a mesma sequência de criações dá os mesmos `Location`; apagar uma prancha não renumera as outras; um número liberado pode ser reusado.
(3) estabilidade ao regravar: gravar o IFC, reabrir e criar outra prancha colidente dá o próximo sufixo livre; os `Location` já gravados não mudam.
(4) nada fora de `pranchas/`; nenhum componente vazio, ".", "..", reservado do Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9, com ou sem extensão),
nem terminado em ponto ou espaço. Número que não dá caminho seguro: recusa (`IdentificacaoInvalida`, arquivo intacto) OU grava `Location` seguro
[P: a escolha é do implementador]. A chave exata (`ler_prancha(...)["numero"]`) nunca muda.
(5) sistema de arquivos insensível a maiúscula e a normalização unicode: dois `Location` nunca podem diferir só por caixa ou por NFC/NFD.
(6) `Location` de prancha e de vista nunca colidem entre si (vista chamada "pranchas/x/layout" e prancha "x", em qualquer ordem).
Vale nos 3 esquemas, com o validador (`express_rules=True`) sem erro. Marcadores retirados (T04d implementada); casos que o código
atual já cumpre NÃO levam a marca. Não editar; só o autor retira os marcadores."""
import re
import unicodedata

import ifcopenshell
import ifcopenshell.validate as VAL
import pytest
import s05_conteudo_aux as R
import s06_t04_aux as A
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)

RESERVADOS = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


@pytest.fixture(params=A.ESQUEMAS)
def f(request):
    R.exigir()
    return A.novo_arquivo(request.param)


def V():
    import openbim_app.vistas_ifc as m
    return m


def erros(f):
    log = VAL.json_logger()
    VAL.validate(f, log, express_rules=True)
    return [str(s.get("message", s))[:160] for s in log.statements]


def locs_prancha(f, numero):
    _, por = A.prancha_ifc(f, numero)
    return {k: [r.Location for r in por[k]] for k in ("LAYOUT", "TITLEBLOCK")}


def todas_locations(f):
    return [r.Location for r in f.by_type("IfcDocumentReference") if r.Location]


def chave_fs(loc):  # o que um sistema de arquivos insensível a caixa e a normalização enxerga
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", loc).casefold())


def seguro(loc):
    assert loc.startswith("pranchas/") and "\\" not in loc and ":" not in loc and not loc.startswith("/"), loc
    for c in loc.split("/"):
        assert c not in ("", ".", ".."), f"componente vazio ou relativo em {loc!r}"
        assert not c.endswith((".", " ")) and not c.startswith(" "), f"componente com ponto/espaço na ponta em {loc!r}"
        assert c.split(".")[0].upper() not in RESERVADOS, f"nome reservado do Windows em {loc!r}"
        assert not re.search(r'[<>"|?*\x00-\x1f]', c), f"caractere proibido no Windows em {loc!r}"


# ---------- (1) colisão depois da limpeza ----------
def test_01_dois_numeros_que_limpam_igual_recebem_location_diferente(f):
    v = V()
    v.criar_prancha(f, "x", "um")
    v.criar_prancha(f, "../x", "dois")
    a, b = locs_prancha(f, "x"), locs_prancha(f, "../x")
    assert a == {"LAYOUT": ["pranchas/x/layout.svg"], "TITLEBLOCK": ["pranchas/x/titleblock.svg"]}, "o primeiro perdeu o caminho natural"
    assert b == {"LAYOUT": ["pranchas/x-2/layout.svg"], "TITLEBLOCK": ["pranchas/x-2/titleblock.svg"]}, b
    assert v.ler_prancha(f, "../x")["numero"] == "../x" and v.ler_prancha(f, "x")["numero"] == "x"
    assert erros(f) == []


def test_02_ordem_inversa_a_primeira_criada_fica_com_o_caminho_natural(f):
    v = V()
    v.criar_prancha(f, "../x", "um")
    v.criar_prancha(f, "x", "dois")
    assert locs_prancha(f, "../x")["LAYOUT"] == ["pranchas/x/layout.svg"]
    assert locs_prancha(f, "x")["LAYOUT"] == ["pranchas/x-2/layout.svg"]


def test_03_quatro_numeros_que_limpam_igual_vao_de_x_a_x_3_sem_repetir(f):
    v = V()
    numeros = ["x", "./x", "../x", "..\\x", "/x"]
    for n in numeros:
        try:
            v.criar_prancha(f, n, "t")
        except v.IdentificacaoInvalida:  # recusa vale (bug 7); os aceitos é que não podem colidir
            pass
    aceitos = [n for n in numeros if any(A.numero_de(d) == n for d in A.pranchas_ifc(f))]
    assert len(aceitos) >= 3, f"o teste só vale se ao menos 3 forem aceitos: {aceitos}"
    locs = todas_locations(f)
    assert len(locs) == len(set(locs)) == 2 * len(aceitos), f"Location repetida: {sorted(locs)}"
    pastas = sorted(l.split("/")[1] for l in locs if l.endswith("/layout.svg"))
    assert pastas == ["x"] + [f"x-{i}" for i in range(2, len(aceitos) + 1)], pastas
    for l in locs:
        seguro(l)
    assert erros(f) == []


def test_04_numero_igual_ao_nome_limpo_de_outro_nao_colide_nem_com_prancha_sem_barra(f):
    v = V()
    v.criar_prancha(f, "A-01", "um")
    v.criar_prancha(f, "B", "dois")  # sem colisão nenhuma: caminho natural
    assert locs_prancha(f, "A-01")["LAYOUT"] == ["pranchas/A-01/layout.svg"]
    assert locs_prancha(f, "B")["LAYOUT"] == ["pranchas/B/layout.svg"]
    assert erros(f) == []


def test_05_numeros_que_caem_no_nome_padrao_vazio_nao_colidem(f):
    v = V()
    for n in ("..", "prancha"):  # ".." limpo vira "prancha"; "prancha" é o número literal
        try:
            v.criar_prancha(f, n, "t")
        except v.IdentificacaoInvalida:
            return  # recusar ".." também vale
    locs = todas_locations(f)
    assert len(locs) == len(set(locs)) == 4, sorted(locs)


# ---------- (2) determinismo e estabilidade ----------
def test_06_mesma_sequencia_da_os_mesmos_locations(f):
    v = V()
    outro = A.novo_arquivo(f.schema)
    for arq in (f, outro):
        for n in ("x", "../x", "./x"):
            v.criar_prancha(arq, n, "t")
    assert sorted(todas_locations(f)) == sorted(todas_locations(outro))
    assert len(set(todas_locations(f))) == 6


def test_07_apagar_nao_renumera_as_outras(f):
    v = V()
    for n in ("x", "../x", "./x"):
        v.criar_prancha(f, n, "t")
    v.apagar_prancha(f, "../x")  # sai o "-2"
    assert locs_prancha(f, "x")["LAYOUT"] == ["pranchas/x/layout.svg"]
    assert locs_prancha(f, "./x")["LAYOUT"] == ["pranchas/x-3/layout.svg"], "apagar renumerou a que ficou"
    v.criar_prancha(f, "..\\x", "t")  # o menor sufixo livre é reaproveitado, como em `_location_livre`
    assert locs_prancha(f, "..\\x")["LAYOUT"] == ["pranchas/x-2/layout.svg"]
    locs = todas_locations(f)
    assert len(locs) == len(set(locs)) and erros(f) == []


def test_08_apagar_a_primeira_libera_o_caminho_natural(f):  # cumprido hoje; mata mutante que guarda contador
    v = V()
    v.criar_prancha(f, "x", "t")
    v.apagar_prancha(f, "x")
    assert todas_locations(f) == []
    v.criar_prancha(f, "../x", "t")
    assert locs_prancha(f, "../x")["LAYOUT"] == ["pranchas/x/layout.svg"] and erros(f) == []


def test_09_regravar_e_reabrir_continua_do_proximo_sufixo_livre(f, tmp_path):
    v = V()
    v.criar_prancha(f, "x", "t")
    v.criar_prancha(f, "../x", "t")
    antes = sorted(todas_locations(f))
    caminho = tmp_path / "Casa.ifc"
    f.write(str(caminho))
    g = ifcopenshell.open(str(caminho))
    assert sorted(todas_locations(g)) == antes, "gravar e reabrir mudou Location"
    v.criar_prancha(g, "./x", "t")
    assert locs_prancha(g, "./x")["LAYOUT"] == ["pranchas/x-3/layout.svg"]
    assert locs_prancha(g, "x")["LAYOUT"] == ["pranchas/x/layout.svg"] and locs_prancha(g, "../x")["LAYOUT"] == ["pranchas/x-2/layout.svg"]
    g.write(str(caminho))
    h = ifcopenshell.open(str(caminho))
    assert len(set(todas_locations(h))) == 6 and erros(h) == []


def test_10_colocar_vista_e_ler_prancha_seguem_a_chave_exata_apos_colisao(f):
    v = V()
    g = v.criar_vista(f, "P", "PLANTA")
    v.criar_prancha(f, "x", "um")
    v.criar_prancha(f, "../x", "dois")
    v.colocar_vista(f, "../x", g)
    assert v.ler_prancha(f, "../x")["vistas"] == [g] and v.ler_prancha(f, "x")["vistas"] == []
    assert erros(f) == []


# ---------- (4) nomes estranhos ----------
ESTRANHOS = ["", ".", "..", " ", "x ", "ação", "名前", "😀", "A\u0301", "\u00c1"]  # o código atual já cumpre; só matam mutante
PERIGOSOS_NO_WINDOWS = ["...", "x.", "CON", "con", "aux.txt", "NUL", "Com1", "lpt9.x", "a/CON/b", "x*y", 'a"b', "a|b", "a?b", "a<b>", "tab\tx", "nul\x00x"]


@pytest.mark.parametrize("numero", ESTRANHOS, ids=[repr(n) for n in ESTRANHOS])
def test_11_numero_estranho_recusa_ou_grava_location_seguro(f, numero):
    v = V()
    v.criar_vista(f, "P", "PLANTA")
    antes = R.foto(f)
    try:
        v.criar_prancha(f, numero, "t")
    except v.IdentificacaoInvalida:
        assert R.diferencas(antes, R.foto(f)) == [], f"{numero!r} recusado deixou entidade solta"
        return
    # aceito: chave exata preservada e Location seguro
    assert v.ler_prancha(f, numero)["numero"] == numero
    _, por = A.prancha_ifc(f, numero)
    for r in por["LAYOUT"] + por["TITLEBLOCK"]:
        seguro(r.Location)
    assert erros(f) == []


@pytest.mark.parametrize("numero", PERIGOSOS_NO_WINDOWS, ids=[repr(n) for n in PERIGOSOS_NO_WINDOWS])
def test_12_reservado_ou_proibido_no_windows_nao_vira_pasta(f, numero):
    v = V()
    try:
        v.criar_prancha(f, numero, "t")
    except v.IdentificacaoInvalida:
        return
    _, por = A.prancha_ifc(f, numero)
    for r in por["LAYOUT"] + por["TITLEBLOCK"]:
        seguro(r.Location)


def test_13_numeros_comuns_e_unicode_continuam_com_caminho_natural(f):  # a regra nova não pode mudar o que já vale
    v = V()
    for n, esperado in (("A-01", "A-01"), ("A 1.2/B", "A 1.2/B"), ("ação", "ação"), ("名前", "名前")):
        v.criar_prancha(f, n, "t")
        assert locs_prancha(f, n)["LAYOUT"] == [f"pranchas/{esperado}/layout.svg"], n
    assert erros(f) == []


# ---------- (5) caixa e normalização ----------
def test_14_numeros_que_diferem_so_na_caixa_nao_dao_location_igual_em_sistema_insensivel(f):
    v = V()
    v.criar_prancha(f, "A-01", "um")
    v.criar_prancha(f, "a-01", "dois")  # os dois são números válidos e distintos (chave exata)
    locs = todas_locations(f)
    assert len({chave_fs(l) for l in locs}) == len(locs) == 4, sorted(locs)
    assert locs_prancha(f, "A-01")["LAYOUT"] == ["pranchas/A-01/layout.svg"], "o primeiro perdeu o caminho natural"
    assert v.ler_prancha(f, "a-01")["numero"] == "a-01"
    assert erros(f) == []


def test_15_numeros_nfc_e_nfd_nao_dao_location_igual_em_sistema_que_normaliza(f):
    v = V()
    v.criar_prancha(f, "ç", "um")  # ç precomposto
    v.criar_prancha(f, "ç", "dois")  # c + cedilha combinante
    locs = todas_locations(f)
    assert len({chave_fs(l) for l in locs}) == len(locs) == 4, sorted(locs)
    assert v.ler_prancha(f, "ç")["numero"] == "ç" and v.ler_prancha(f, "ç")["numero"] == "ç"


def test_16_tres_caixas_do_mesmo_numero_viram_tres_pastas_distintas(f):
    v = V()
    for n in ("Aa", "aA", "AA"):
        v.criar_prancha(f, n, "t")
    pastas = [chave_fs(l.split("/")[1]) for l in todas_locations(f) if l.endswith("/layout.svg")]
    assert len(pastas) == 3 and len(set(pastas)) == 3, pastas


# ---------- (6) prancha x vista ----------
def test_17_vista_criada_depois_nao_pega_o_location_de_uma_prancha(f):  # `_location_livre` já olha todas as referências
    v = V()
    v.criar_prancha(f, "x", "t")
    g = v.criar_vista(f, "pranchas/x/layout", "PLANTA")
    locs = todas_locations(f)
    assert len(locs) == len(set(locs)) == 3, sorted(locs)
    assert A.vista_ifc(f, g)["location"] == "pranchas/x/layout-2.svg"


def test_18_prancha_criada_depois_nao_pega_o_location_de_uma_vista(f):
    v = V()
    g = v.criar_vista(f, "pranchas/x/layout", "PLANTA")  # vira "pranchas/x/layout.svg"
    assert A.vista_ifc(f, g)["location"] == "pranchas/x/layout.svg"
    v.criar_prancha(f, "x", "t")
    locs = todas_locations(f)
    assert len(locs) == len(set(locs)) == 3, f"prancha reutilizou Location da vista: {sorted(locs)}"
    assert A.vista_ifc(f, g)["location"] == "pranchas/x/layout.svg", "a vista mudou de Location"
    assert v.ler_prancha(f, "x")["vistas"] == [], "a prancha nova herdou a vista pelo Location repetido"
    assert erros(f) == []


def test_19_vistas_com_nome_que_difere_so_na_caixa_nao_dao_location_igual_em_sistema_insensivel(f):
    v = V()
    v.criar_vista(f, "Planta", "PLANTA")
    v.criar_vista(f, "planta", "PLANTA")
    locs = todas_locations(f)
    assert len({chave_fs(l) for l in locs}) == len(locs) == 2, sorted(locs)


# ---------- mutantes vivos da conferência (um nome ou caractere por caso) ----------
UM_A_UM = (sorted(RESERVADOS) + ["prn.txt", "Lpt1", "com9.a.b"]
           + [f"a{c}b" for c in ("<", ">", '"', "|", "?", "*", "\x00", "\x01", "\x1e", "\x1f")])


@pytest.mark.parametrize("numero", UM_A_UM, ids=[repr(n) for n in UM_A_UM])
def test_20_cada_reservado_e_cada_caractere_proibido_sozinho(f, numero):
    v = V()
    try:
        v.criar_prancha(f, numero, "t")
    except v.IdentificacaoInvalida:
        return
    _, por = A.prancha_ifc(f, numero)
    for r in por["LAYOUT"] + por["TITLEBLOCK"]:
        seguro(r.Location)


def test_21_titleblock_sozinho_de_outro_programa_ocupa_a_pasta(f):  # mutante D1: a pasta só olhava o layout
    v = V()
    d = f.create_entity("IfcDocumentInformation", Name="alheio", Scope="SHEET",
                        **({"DocumentId": "Z"} if f.schema == "IFC2X3" else {"Identification": "Z"}))
    r = f.create_entity("IfcDocumentReference", Location="pranchas/x/titleblock.svg")
    if f.schema == "IFC2X3":
        d.DocumentReferences = [r]
    else:
        r.ReferencedDocument = d
    v.criar_prancha(f, "x", "t")
    assert locs_prancha(f, "x") == {"LAYOUT": ["pranchas/x-2/layout.svg"], "TITLEBLOCK": ["pranchas/x-2/titleblock.svg"]}


def test_22_tres_vistas_de_mesmo_nome_vao_de_x_a_x_3_e_caixa_conta_no_laco(f):  # mutantes E2 e E3 de `_location_livre`
    v = V()
    gs = [v.criar_vista(f, n, "PLANTA") for n in ("x", "X", "x")]
    assert [A.vista_ifc(f, g)["location"] for g in gs] == ["x.svg", "X-2.svg", "x-3.svg"]
    g4 = v.criar_vista(f, "x-2", "PLANTA")  # "x-2.svg" já existe como "X-2.svg" (caixa): sufixa de novo
    assert A.vista_ifc(f, g4)["location"] == "x-2-2.svg"
    locs = todas_locations(f)
    assert len({chave_fs(l) for l in locs}) == len(locs) == 4 and erros(f) == []
