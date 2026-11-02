# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08i (memoria e tamanho de erro em `prancha.py`), da revisao 3 da T08h. Entradas gigantes nao podem gastar memoria sem limite
nem gerar mensagem de erro gigante. Cada caso roda num subprocesso (`python -I`) com limite de tempo e de memoria virtual (3 GB, so para nao derrubar a
maquina); o pico medido e o RSS maximo (`VmHWM` de `/proc/self/status`, que e do processo novo: `ru_maxrss` herda o pico do pai no exec) do subprocesso, que inclui o texto de entrada.
- 20 MB de `<rect/>` dentro de 199 `<g class="IfcWall">` em `montar_svg`: `SvgInvalido` OU pico < 800 MB e < 8 s.
- 64 MB de `<g/>` em `normalizar_planta`: `SvgInvalido` (teto de 1 milhao de elementos, checado ANTES de montar a arvore) OU pico < 800 MB.
- `polyline` com 20 MB de pontos: `SvgInvalido` (conta no mesmo contador de comandos do path) OU pico (RSS do subprocesso, texto de entrada incluso) < 150 MB.
- `d` ou atributo numerico com 20 MB de lixo: `SvgInvalido` com `len(str(erro)) < 500`.
Regressao da T08i (marcadores retirados)."""
import json
import resource
import subprocess
import sys

import pytest

import test_s06_t08g_robustez_oraculo as G



def rodar_rss(corpo, tempo=90, mem_mb=3000):
    """Devolve (resultado, segundos, pico_rss_mb, tamanho_da_mensagem). resultado = 'OK' ou 'Classe|mro'."""
    cod = G.PRE + f'''
import resource
def pico_mb():
    for linha in open("/proc/self/status"):
        if linha.startswith("VmHWM:"):
            return int(linha.split()[1]) / 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
t0 = time.time()
r, n = "OK", 0
try:
    exec({corpo!r})
except BaseException as e:
    r = type(e).__name__ + "|" + ",".join(c.__name__ for c in type(e).__mro__)
    n = len(str(e))
print(json.dumps([r, time.time() - t0, pico_mb(), n]))
'''
    def lim():
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 2**20,) * 2)
    try:
        p = subprocess.run([sys.executable, "-I", "-c", cod], capture_output=True, text=True, timeout=tempo, preexec_fn=lim)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", float(tempo), 0.0, 0
    if p.returncode:
        return "MORREU " + p.stderr[-200:], 0.0, 0.0, 0
    return tuple(json.loads(p.stdout.strip().splitlines()[-1]))


def _recusou(r):
    return r.startswith("SvgInvalido|")


def test_01_20mb_de_rect_em_199_niveis_ifcwall():
    corpo = ("c = '<g class=\"IfcWall\">' * 199 + '<rect/>' * 2900000 + '</g>' * 199\n"
             "m.montar_svg(lateral(), 'P', 'v', env(c, 'viewBox=\"0 0 10 10\"'))")
    r, seg, rss, _ = rodar_rss(corpo)
    assert _recusou(r) or (r == "OK" and rss < 800 and seg < 8), f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB"


@pytest.mark.parametrize("extra", [pytest.param("", id="sem_viewbox"), pytest.param("viewBox=\"0 0 1 1\"", id="com_viewbox")])
def test_02_64mb_de_g_vazio_em_normalizar(extra):
    """O pico vale MESMO quando a funcao acaba recusando (hoje recusa so no fim, 'sem desenhavel', depois de 2,6 GB e 30 s): o teto de elementos tem de agir antes de montar a arvore."""
    corpo = f"m.normalizar_planta(env('<g/>' * 16000000, {extra!r}))"
    r, seg, rss, _ = rodar_rss(corpo)
    assert (_recusou(r) or r == "OK") and rss < 800, f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB"


def test_03_polyline_de_20mb():
    corpo = "m.normalizar_planta(env('<polyline points=\"' + '1,1 ' * 5000000 + '\"/>'))"
    r, seg, rss, _ = rodar_rss(corpo)
    assert _recusou(r) or (r == "OK" and rss < 150), f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB"


@pytest.mark.parametrize("nome,corpo", [
    pytest.param("d_com_lixo", "m.normalizar_planta(env('<path d=\"M0 0 ' + 'x' * 20000000 + '\"/>'))", id="d_com_lixo"),
    pytest.param("d_sem_M_com_lixo", "m.normalizar_planta(env('<path d=\"' + 'L' * 20000000 + '\"/>'))", id="d_sem_M_com_lixo"),
    pytest.param("x_com_lixo", "m.normalizar_planta(env('<rect x=\"' + 'z' * 20000000 + '\" width=\"1\" height=\"1\"/>'))", id="x_com_lixo"),
    pytest.param("viewbox_com_lixo", "m.montar_svg(lateral(), 'P', 'v', '<svg ' + S + ' viewBox=\"' + 'q' * 20000000 + '\"><rect width=\"1\" height=\"1\"/></svg>')", id="viewbox_com_lixo"),
    pytest.param("points_com_lixo", "m.normalizar_planta(env('<polyline points=\"' + 'p' * 20000000 + '\"/>'))", id="points_com_lixo"),
])
def test_04_mensagem_de_erro_curta(nome, corpo):
    r, seg, rss, n = rodar_rss(corpo)
    assert _recusou(r), f"{nome}: veio {r!r}"
    assert n < 500, f"{nome}: mensagem com {n} caracteres"


def test_05_comentario_e_cdata_nao_contam_como_elemento():
    """2 milhoes de `<g/>` DENTRO de comentario e de CDATA nao sao elementos: a planta e valida e nao pode ser recusada pelo teto de 1 milhao."""
    corpo = ("fal = '<g/>' * 2000000\n"
             "m.normalizar_planta(env('<!--' + fal + '--><style><![CDATA[' + fal + ']]></style><rect width=\"1\" height=\"1\"/>'))")
    r, seg, rss, _ = rodar_rss(corpo)
    assert r == "OK", f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB"


def test_06_polyline_acima_de_5_milhoes_de_numeros_e_recusada():
    """O teto de 5 milhoes de comandos tambem vale para `points` (mesmo contador do path)."""
    corpo = "m.normalizar_planta(env('<polyline points=\"' + '1,1 ' * 2600000 + '\"/>'))"
    r, seg, rss, _ = rodar_rss(corpo)
    assert _recusou(r), f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB"


@pytest.mark.parametrize("nome,corpo", [
    pytest.param("escala_lista_gigante", "m.montar_svg(lateral(escala=[1] * 3000000), 'P', 'v', PLANTA)", id="escala_lista_gigante"),
    pytest.param("escala_texto_20MB", "m.montar_svg(lateral(escala='x' * 20000000), 'P', 'v', PLANTA)", id="escala_texto_20MB"),
    pytest.param("x_lista_gigante", "m.montar_svg(lateral(x=[1] * 3000000), 'P', 'v', PLANTA)", id="x_lista_gigante"),
    pytest.param("formato_20MB", "p = lateral(); p.p['formato'] = 'A' * 20000000\nm.montar_svg(p, 'P', 'v', PLANTA)", id="formato_20MB"),
    pytest.param("data_20MB", "m.montar_svg(lateral(carimbo={'projeto': 'x', 'titulo': 't', 'data': '2' * 20000000, 'folha': '1'}), 'P', 'v', PLANTA)", id="data_20MB"),
    pytest.param("rotacao_lista_gigante", "m.montar_svg(lateral(rotacao=[1] * 3000000), 'P', 'v', PLANTA)", id="rotacao_lista_gigante"),
    pytest.param("criar_prancha_formato_20MB", "class L:\n    def criar(self, *a): pass\nm.criar_prancha(L(), 'P', 'Z' * 20000000, 'x', 't', '2026-11-01', '1')", id="criar_prancha_formato_20MB"),
    pytest.param("colocar_viewport_rotacao_lista", "class L:\n    def criar(self, *a): pass\nm.colocar_viewport(L(), 'P', 'v', 0, 0, 100, [1] * 3000000)", id="colocar_viewport_rotacao_lista"),
])
def test_07_lateral_mensagem_curta(nome, corpo):
    r, seg, rss, n = rodar_rss(corpo)
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"{nome}: veio {r!r}"
    assert n < 500, f"{nome}: mensagem com {n} caracteres"


@pytest.mark.parametrize("nome,corpo,limite_mb", [
    pytest.param("montar_900mil_rects_199_niveis", "c = '<g class=\"IfcWall\">' * 199 + '<rect width=\"1\" height=\"1\"/>' * 900000 + '</g>' * 199\nm.montar_svg(lateral(), 'P', 'v', env(c, 'viewBox=\"0 0 10 10\"'))", 710, id="montar_900mil_rects_199_niveis"),
    pytest.param("normalizar_900mil_rects_199_niveis", "c = '<g>' * 199 + '<rect width=\"1\" height=\"1\"/>' * 900000 + '</g>' * 199\nm.normalizar_planta(env(c))", 470, id="normalizar_900mil_rects_199_niveis"),
])
def test_08_abaixo_do_teto_nao_empilha_irmaos(nome, corpo, limite_mb):
    """900 mil elementos (abaixo do teto de 1 milhao) sob 199 niveis: as pilhas de iteradores nao podem empilhar todos os irmaos de uma vez
    (referencia medida: 647 MB em `montar_svg`, 407 MB em `normalizar_planta`; empilhar os irmaos acrescenta mais de 110 MB)."""
    r, seg, rss, _ = rodar_rss(corpo)
    assert r == "OK" and rss < limite_mb and seg < 15, f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB (limite {limite_mb})"


# ---------- T08j: custo do expat e surrogates (revisao 4) ----------
SV = "'<svg ' + S + '>'"
FUNCS = [("normalizar", "m.normalizar_planta({x})"), ("montar", "m.montar_svg(lateral(), 'P', 'v', {x})")]


def _por_funcao(chamada, x):
    return chamada.format(x=x)


@pytest.mark.parametrize("func", [pytest.param(n, id=n) for n, _ in FUNCS])
@pytest.mark.parametrize("nome,lixo,mult", [
    pytest.param("comentario_aberto", "<!--", 40000, id="comentario_aberto"),
    pytest.param("instrucao_aberta", "<?", 80000, id="instrucao_aberta"),
    pytest.param("cdata_aberto", "<![CDATA[", 20000, id="cdata_aberto"),
])
def test_09_abertura_sem_fim_e_barrada_rapido(func, nome, lixo, mult):
    x = f"{SV} + {lixo!r} * {mult}"
    corpo = _por_funcao(dict(FUNCS)[func], x)
    r, seg, rss, _ = rodar_rss(corpo)
    assert _recusou(r) and seg < 2, f"veio {r!r}, {seg:.1f}s"


@pytest.mark.parametrize("func", [pytest.param(n, id=n) for n, _ in FUNCS])
@pytest.mark.parametrize("nome,x", [
    pytest.param("10M_elementos_unicode", f"{SV} + '<\\u00e9/>' * 10000000 + '</svg>'", id="10M_elementos_unicode"),
    pytest.param("8M_aninhados_unicode", f"{SV} + '<\\u00e9>' * 8000000 + '</\\u00e9>' * 8000000 + '</svg>'", id="8M_aninhados_unicode"),
])
def test_10_elementos_unicode_gigantes_recusados_sem_memoria(func, nome, x):
    r, seg, rss, _ = rodar_rss(_por_funcao(dict(FUNCS)[func], x))
    assert _recusou(r) and rss < 300, f"veio {r!r}, {seg:.1f}s, pico {rss:.0f} MB"


@pytest.mark.parametrize("func", [pytest.param(n, id=n) for n, _ in FUNCS])
@pytest.mark.parametrize("nome,x", [
    pytest.param("em_text", f"{SV} + '<text>\\ud800</text><rect width=\"1\" height=\"1\"/></svg>'", id="em_text"),
    pytest.param("em_id", f"{SV} + '<rect id=\"a\\ud800b\" width=\"1\" height=\"1\"/></svg>'", id="em_id"),
    pytest.param("depois_do_svg", f"{SV} + '<rect width=\"1\" height=\"1\"/></svg>\\ud800'", id="depois_do_svg"),
])
def test_11_surrogate_solitario_e_svginvalido(func, nome, x):
    r, seg, rss, _ = rodar_rss(_por_funcao(dict(FUNCS)[func], x))
    assert _recusou(r), f"{nome}: veio {r!r}"


# ---------- T08j: fronteiras exatas do _validar_xml ----------
@pytest.mark.parametrize("nome,corpo,ok", [
    pytest.param("elementos_1000000_com_svg", "m.normalizar_planta(env('<g/>' * 999999, 'viewBox=\"0 0 1 1\"'))", True, id="elementos_1000000_com_svg"),
    pytest.param("elementos_1000001_com_svg", "m.normalizar_planta(env('<g/>' * 1000000, 'viewBox=\"0 0 1 1\"'))", False, id="elementos_1000001_com_svg"),
    pytest.param("199_g_e_rect", "m.normalizar_planta(env('<g>' * 199 + '<rect width=\"1\" height=\"1\"/>' + '</g>' * 199))", True, id="199_g_e_rect"),
    pytest.param("200_g_e_rect", "m.normalizar_planta(env('<g>' * 200 + '<rect width=\"1\" height=\"1\"/>' + '</g>' * 200))", False, id="200_g_e_rect"),
    pytest.param("irmaos_nao_somam_profundidade", "m.normalizar_planta(env('<g/>' * 5000 + '<rect width=\"1\" height=\"1\"/>'))", True, id="irmaos_nao_somam_profundidade"),
])
def test_12_fronteiras_do_validar_xml(nome, corpo, ok):
    r, seg, rss, _ = rodar_rss(corpo)
    if ok:
        assert r == "OK", f"{nome}: veio {r!r}"
    else:
        assert _recusou(r), f"{nome}: veio {r!r}"


@pytest.mark.parametrize("nome,corpo", [
    pytest.param("doctype_simples", "m.normalizar_planta('<!DOCTYPE svg>' + env('<rect width=\"1\" height=\"1\"/>'))", id="doctype_simples"),
    pytest.param("doctype_publico", "m.normalizar_planta('<!DOCTYPE svg PUBLIC \"-//W3C//DTD SVG 1.1//EN\" \"x.dtd\">' + env('<rect width=\"1\" height=\"1\"/>'))", id="doctype_publico"),
    pytest.param("doctype_minusculo", "m.normalizar_planta('<!doctype svg>' + env('<rect width=\"1\" height=\"1\"/>'))", id="doctype_minusculo"),
    pytest.param("entidade_interna", "m.normalizar_planta('<!DOCTYPE svg [<!ENTITY a \"b\">]>' + env('<rect width=\"1\" height=\"1\"/>'))", id="entidade_interna"),
    pytest.param("doctype_em_bytes", "m.normalizar_planta(('<!DOCTYPE svg>' + env('<rect width=\"1\" height=\"1\"/>')).encode())", id="doctype_em_bytes"),
    pytest.param("bytes_nao_utf8", "m.normalizar_planta(env('<!--').encode() + b'\\xff\\xfe' + b'--><rect width=\"1\" height=\"1\"/></svg>')", id="bytes_nao_utf8"),
    pytest.param("bytes_nao_utf8_no_atributo", "m.normalizar_planta(b'<svg ' + S.encode() + b'><rect id=\"\\xc3\\x28\" width=\"1\" height=\"1\"/></svg>')", id="bytes_nao_utf8_no_atributo"),
    pytest.param("xml_malformado_nao_fecha", "m.normalizar_planta(env('<rect width=\"1\" height=\"1\"/>')[:-6])", id="xml_malformado_nao_fecha"),
])
def test_13_doctype_entidade_e_bytes_invalidos(nome, corpo):
    r, seg, rss, _ = rodar_rss(corpo)
    assert _recusou(r), f"{nome}: veio {r!r}"
