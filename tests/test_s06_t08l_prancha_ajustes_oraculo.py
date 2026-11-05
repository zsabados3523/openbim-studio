# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08l (ajustes apontados pelo revisor nas fatias T08/T08f). So testes; mantem o contrato dos `test_s06_t08*`.
Cada item foi conferido contra o codigo: teste SEM marca = o codigo ja cumpre (regressao); `xfail(strict)` X = achado real.
1. `normalizar_planta` injeta o viewBox NA raiz: `<svg` escrito em comentario ou instrucao antes da raiz nao pode receber a injecao (achado real);
   viewBox escrito em comentario, texto, atributo de filho ou atributo com namespace nao conta como o da raiz (ja cumpre).
2. Homonimos: atributos `x:width`, `x:transform`, `x:class` nao valem como `width`, `transform`, `class`; elemento de outro namespace
   (`<x:rect>`) e tratado de forma COERENTE: entra na caixa se e so se recebe a espessura. Se conta ou nao e decisao do PO (ver PERGUNTA_PO do cartao).
3. `ler_viewport` com lateral adulterado: erro da familia `PranchaInvalida`, nunca `KeyError` cru (achado real); nunca devolve silenciosamente.
4. Arcos identicos repetidos nao inflam a caixa nem o tempo (ja cumpre).
5. Elemento com muitos atributos (100 mil, 1 milhao) termina rapido e so pode terminar em OK ou `SvgInvalido` (ja cumpre; o NUMERO do teto e do PO).
6. Folga de tempo: em vez de `seg < 8` absoluto, conta as visitas (exatamente 1 por elemento) e usa razao contra `ET.fromstring` do mesmo texto na mesma maquina."""
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP))
import openbim_app.prancha as m  # noqa: E402

NS = "http://www.w3.org/2000/svg"
S = f'xmlns="{NS}"'


def caixa(texto):
    return tuple(float(v) for v in ET.fromstring(texto).get("viewBox").split())


class Falso:
    def __init__(self, prancha, viewport): self.p, self.v = prancha, viewport
    def ids(self, c): return ["1"]
    def obter(self, c, i): return self.p if c == "pranchas" else self.v


def lateral(escala=100, **viewport):
    p = {"identification": "P", "formato": "A3", "carimbo": {"projeto": "x", "titulo": "t", "data": "2026-11-01", "folha": "1"}}
    v = {"prancha": "P", "vista_guid": "v", "x": 20, "y": 20, "escala": escala}
    v.update(viewport)
    return Falso(p, v)


# ---------- 1: injecao do viewBox ----------
RETA = '<rect width="5" height="5"/>'
ANTES = [
    pytest.param("<!-- <svg a -->", id="comentario_com_svg"),
    pytest.param("<?alvo <svg a ?>", id="instrucao_com_svg"),
    pytest.param("<!-- x --><!-- <svg -->", id="dois_comentarios"),
]


@pytest.mark.parametrize("antes", ANTES)
def test_01_svg_dentro_de_comentario_antes_da_raiz_nao_recebe_o_viewbox(antes):
    saida = m.normalizar_planta(f"{antes}<svg {S}>{RETA}</svg>")
    assert saida.startswith(antes), "o texto antes da raiz tem de sair intacto"
    assert caixa(saida) == (-0.5, -0.5, 6.0, 6.0)


def test_01b_montar_svg_com_comentario_svg_antes_da_raiz():
    saida = m.montar_svg(lateral(), "P", "v", f"<!-- <svg a --><svg {S}>{RETA}</svg>")
    assert ET.fromstring(saida).tag == f"{{{NS}}}svg"


@pytest.mark.parametrize("planta", [
    pytest.param(f'<!-- viewBox="0 0 1 1" --><svg {S}>{RETA}</svg>', id="comentario_antes"),
    pytest.param(f'<svg {S}><!-- viewBox="0 0 1 1" -->{RETA}</svg>', id="comentario_dentro"),
    pytest.param(f'<svg {S}><text>viewBox="0 0 1 1"</text>{RETA}</svg>', id="texto"),
    pytest.param(f'<svg {S}><rect width="5" height="5" viewBox="0 0 1 1"/></svg>', id="atributo_de_filho"),
    pytest.param(f'<svg {S} xmlns:x="urn:x" x:viewBox="0 0 1 1">{RETA}</svg>', id="atributo_com_namespace"),
    pytest.param(f'<svg {S}><style><![CDATA[ a{{}} viewBox="0 0 1 1" <svg ]]></style>{RETA}</svg>', id="cdata"),
    pytest.param(f'<?xml version="1.0"?><!-- c --><svg {S}>{RETA}</svg>', id="declaracao_e_comentario"),
])
def test_02_viewbox_fora_da_raiz_nao_engana_a_deteccao(planta):
    assert caixa(m.normalizar_planta(planta)) == (-0.5, -0.5, 6.0, 6.0)


def test_03_viewbox_da_raiz_e_respeitado_mesmo_com_comentario_igual_antes():
    planta = f'<!-- viewBox="9 9 9 9" --><svg {S} viewBox="0 0 10 10">{RETA}</svg>'
    assert m.normalizar_planta(planta) == planta


def test_04_raiz_com_prefixo_de_namespace_ou_e_recusada_ou_recebe_o_viewbox_na_raiz():
    planta = '<s:svg xmlns:s="%s"><s:rect width="5" height="5"/></s:svg>' % NS
    try:
        saida = m.normalizar_planta(planta)
    except m.SvgInvalido:
        return
    assert caixa(saida) == (-0.5, -0.5, 6.0, 6.0)


def test_05_raiz_com_prefixo_e_viewbox_proprio_passa_no_montar_svg():
    planta = '<s:svg xmlns:s="%s" viewBox="0 0 10 10"><s:rect width="5" height="5"/></s:svg>' % NS
    assert ET.fromstring(m.montar_svg(lateral(), "P", "v", planta)).tag == f"{{{NS}}}svg"


# ---------- 2: homonimos com namespace ----------
@pytest.mark.parametrize("homonimo", [
    pytest.param('x:width="999" x:height="999" x:x="999"', id="medidas"),
    pytest.param('x:transform="translate(999)"', id="transform"),
    pytest.param('x:class="cut" x:style="stroke-width:9" x:href="#a" xlink:href="#b"', id="class_style_href"),
])
def test_06_atributo_com_namespace_nao_vale_como_o_homonimo(homonimo):
    planta = f'<svg {S} xmlns:x="urn:x" xmlns:xlink="http://www.w3.org/1999/xlink"><rect width="5" height="5" {homonimo}/></svg>'
    assert caixa(m.normalizar_planta(planta)) == (-0.5, -0.5, 6.0, 6.0)


def test_07_path_com_d_de_outro_namespace_nao_desenha():
    planta = f'<svg {S} xmlns:x="urn:x"><path d="M0 0 L5 5" x:d="M0 0 L999 999"/></svg>'
    assert caixa(m.normalizar_planta(planta)) == (-0.5, -0.5, 6.0, 6.0)


def test_08_elemento_de_outro_namespace_e_coerente_entre_caixa_e_espessura():
    """Entra na caixa SE E SO SE o montar_svg tambem aplica a espessura nele (ou nos dois ou em nenhum)."""
    planta = f'<svg {S} xmlns:x="urn:x"><x:rect width="500" height="500"/>{RETA}</svg>'
    na_caixa = caixa(m.normalizar_planta(planta))[2] > 100
    saida = m.montar_svg(lateral(escala=10000), "P", "v", planta)
    alvo = [e for e in ET.fromstring(saida).iter() if e.tag == "{urn:x}rect"]
    assert len(alvo) == 1, "o elemento de outro namespace nao pode sumir nem duplicar"
    com_espessura = "stroke-width" in alvo[0].get("style", "")
    assert na_caixa == com_espessura


# ---------- 3: ler_viewport com lateral adulterado ----------
class Quebrado:
    def __init__(self, onde, viewport=None): self.onde, self.v = onde, viewport
    def ids(self, c):
        if self.onde == "ids": raise KeyError(c)
        return ["1"]
    def obter(self, c, i):
        if self.onde == "obter": raise KeyError(i)
        return self.v


def test_09_ler_viewport_sadio_continua_valendo():
    v = {"prancha": "P", "vista_guid": "v", "x": 1, "y": 2, "escala": 50, "rotacao": 90}
    assert m.ler_viewport(Quebrado("nenhum", v), "P", "v") == {"x": 1, "y": 2, "escala": 50, "rotacao": 90}


def test_10_ler_viewport_ja_recusa_viewport_que_nao_e_dict():
    with pytest.raises(m.PranchaInvalida):
        m.ler_viewport(Quebrado("nenhum", None), "P", "v")


def test_11_ler_viewport_de_outro_vista_guid_e_nao_encontrada():
    v = {"prancha": "P", "vista_guid": "outra", "x": 1, "y": 2, "escala": 50}
    with pytest.raises(m.PranchaNaoEncontrada):
        m.ler_viewport(Quebrado("nenhum", v), "P", "v")


@pytest.mark.parametrize("onde,viewport", [
    pytest.param("nenhum", {"prancha": "P", "vista_guid": "v", "y": 2, "escala": 50}, id="sem_x"),
    pytest.param("nenhum", {"prancha": "P", "vista_guid": "v", "x": 1, "escala": 50}, id="sem_y"),
    pytest.param("nenhum", {"prancha": "P", "vista_guid": "v", "x": 1, "y": 2}, id="sem_escala"),
    pytest.param("obter", None, id="obter_levanta_KeyError"),
    pytest.param("ids", None, id="ids_levanta_KeyError"),
])
def test_12_ler_viewport_adulterado_da_erro_do_dominio_e_nao_keyerror(onde, viewport):
    with pytest.raises(m.PranchaInvalida):
        m.ler_viewport(Quebrado(onde, viewport), "P", "v")


# ---------- 4: arcos repetidos ----------
def test_13_arcos_identicos_nao_inflam_a_caixa_nem_o_tempo():
    um = m.normalizar_planta(f'<svg {S}><path d="M0 0 A5 5 0 0 1 10 0"/></svg>')
    muitos_d = "M0 0 " + "A5 5 0 0 1 10 0 " * 100_000
    t0 = time.time()
    muitos = m.normalizar_planta(f'<svg {S}><path d="{muitos_d}"/></svg>')
    assert time.time() - t0 < 8, "100 mil arcos identicos (medido ~0,6 s)"
    assert caixa(muitos) == caixa(um)


def test_14_arcos_que_vao_e_voltam_tem_a_caixa_do_par():
    par = m.normalizar_planta(f'<svg {S}><path d="M0 0 A5 5 0 0 1 10 0 A5 5 0 0 1 0 0"/></svg>')
    d = "M0 0 " + "A5 5 0 0 1 10 0 A5 5 0 0 1 0 0 " * 30_000
    assert caixa(m.normalizar_planta(f'<svg {S}><path d="{d}"/></svg>')) == caixa(par)


# ---------- 5: muitos atributos ----------
@pytest.mark.parametrize("n,limite_s", [pytest.param(100_000, 3, id="100mil"), pytest.param(1_000_000, 12, id="1milhao")])
def test_15_muitos_atributos_terminam_rapido_em_ok_ou_svginvalido(n, limite_s):
    attrs = " ".join(f'a{i}="1"' for i in range(n))
    planta = f'<svg {S}><rect width="5" height="5" {attrs}/></svg>'
    t0 = time.time()
    try:
        saida = m.normalizar_planta(planta)
    except m.SvgInvalido as e:
        assert str(e), "a recusa precisa de mensagem clara"
    else:
        assert caixa(saida) == (-0.5, -0.5, 6.0, 6.0)
    assert time.time() - t0 < limite_s


def test_16_muitos_atributos_tambem_no_montar_svg():
    attrs = " ".join(f'a{i}="1"' for i in range(100_000))
    planta = f'<svg {S} viewBox="0 0 10 10"><rect width="5" height="5" {attrs}/></svg>'
    t0 = time.time()
    try:
        m.montar_svg(lateral(), "P", "v", planta)
    except m.SvgInvalido as e:
        assert str(e)
    assert time.time() - t0 < 5


# ---------- 6: folga de tempo sem afrouxar numero ----------
RODA = f'''
import sys, time, json, xml.etree.ElementTree as ET
sys.path.insert(0, {str(APP)!r})
import openbim_app.prancha as m
S = {S!r}
N = 300000
class Falso:
    p = {{"identification": "P", "formato": "A3", "carimbo": {{"projeto": "x", "titulo": "t", "data": "2026-11-01", "folha": "1"}}}}
    v = {{"prancha": "P", "vista_guid": "v", "x": 20, "y": 20, "escala": 100}}
    def ids(self, c): return ["1"]
    def obter(self, c, i): return self.p if c == "pranchas" else self.v
def com(chave, fn):
    n = [0]; orig = getattr(m, chave)
    def w(*a, **k):
        n[0] += 1
        return orig(*a, **k)
    setattr(m, chave, w)
    t = time.time(); fn(); seg = time.time() - t
    setattr(m, chave, orig)
    return n[0], seg
c = '<g class="IfcWall">' * 199 + '<rect width="1" height="1"/>' * N + '</g>' * 199
svg_vb = '<svg ' + S + ' viewBox="0 0 10 10">' + c + '</svg>'
svg = '<svg ' + S + '>' + c + '</svg>'
t = time.time(); ET.fromstring(svg); base = time.time() - t
vis_n, seg_n = com("_process_elem_bbox", lambda: m.normalizar_planta(svg))
vis_m, seg_m = com("_calcular_corte_node", lambda: m.montar_svg(Falso(), "P", "v", svg_vb))
print(json.dumps([N + 199 + 1, vis_n, vis_m, base, seg_n, seg_m]))
'''


def test_17_normalizar_e_montar_visitam_cada_elemento_uma_vez_e_ficam_perto_do_parser():
    """Contagem exata (nao depende da maquina) + razao contra o parser nativo (varia pouco entre maquinas). Medido: razao ~8 em normalizar, ~7 em montar; limite 30."""
    import resource
    def lim(): resource.setrlimit(resource.RLIMIT_AS, (1500 * 2**20,) * 2)
    p = subprocess.run([sys.executable, "-I", "-c", RODA], capture_output=True, text=True, timeout=120, preexec_fn=lim)
    assert p.returncode == 0, p.stderr[-300:]
    esperado, vis_n, vis_m, base, seg_n, seg_m = json.loads(p.stdout.strip().splitlines()[-1])
    assert vis_n == esperado, f"normalizar visitou {vis_n} vezes, esperado {esperado}"
    assert vis_m == esperado, f"montar_svg visitou {vis_m} vezes, esperado {esperado}"
    assert seg_n < 30 * base, f"normalizar {seg_n:.1f}s contra parser {base:.2f}s"
    assert seg_m < 30 * base, f"montar_svg {seg_m:.1f}s contra parser {base:.2f}s"


# ---------- mutantes vivos nao equivalentes ----------
def test_18_raiz_com_prefixo_sem_viewbox_recebe_o_viewbox_na_tag_da_raiz():
    planta = '<!-- c --><s:svg xmlns:s="%s"><s:rect width="5" height="5"/></s:svg>' % NS
    saida = m.normalizar_planta(planta)
    assert saida.startswith('<!-- c --><s:svg viewBox="')
    assert caixa(saida) == (-0.5, -0.5, 6.0, 6.0)


@pytest.mark.parametrize("antes", [
    pytest.param("\n  ", id="espaco_no_inicio"),
    pytest.param("<!-- a -->\n\t <!-- b -->\r\n", id="espaco_entre_comentarios"),
    pytest.param('<?xml version="1.0"?>\n<?alvo x?>\n', id="declaracao_e_instrucao_com_quebra"),
])
def test_19_espacos_antes_da_raiz_sao_pulados(antes):
    saida = m.normalizar_planta(f"{antes}<svg {S}>{RETA}</svg>")
    assert saida.startswith(antes + '<svg viewBox="')
    assert caixa(saida) == (-0.5, -0.5, 6.0, 6.0)


def test_20_comentario_com_traco_duplo_ou_menor_dentro_nao_confunde():
    antes = "<!-- a - b <svg> <rect/> - ->-->"
    saida = m.normalizar_planta(f"{antes}<svg {S}>{RETA}</svg>")
    assert saida.startswith(antes + '<svg viewBox="')


def test_21_ler_viewport_mensagem_cita_o_campo_ausente():
    with pytest.raises(m.PranchaInvalida, match="escala"):
        m.ler_viewport(Quebrado("nenhum", {"prancha": "P", "vista_guid": "v", "x": 1, "y": 2}), "P", "v")


def test_22_ler_viewport_keyerror_nao_vira_pranchanaoencontrada_nem_vaza():
    for onde in ("ids", "obter"):
        with pytest.raises(m.PranchaInvalida) as e:
            m.ler_viewport(Quebrado(onde), "P", "v")
        assert str(e.value)
