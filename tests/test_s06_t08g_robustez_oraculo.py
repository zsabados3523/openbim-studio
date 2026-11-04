# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo do F0-S06-T08g (robustez de `prancha.py`), a partir da revisao Sonnet que reprovou a T08f. Mantem TODO o contrato de `test_s06_t08*`. Contrato novo:
- Entrada ruim da planta = `SvgInvalido` (a classe exata, nunca `ValueError`, `TypeError`, `OverflowError`, `MemoryError`, `RecursionError`, `ZeroDivisionError`) e
  SEM travar nem gastar memoria: path malformado (`Z` seguido de numero solto, comando sem argumentos, `S`/`T` no inicio, flag de arco diferente de 0 e 1, inclusive `1e999`,
  raio absurdo como 1e200), atributo numerico que nao e numero finito (`x="abc"`, `"nan"`, `"inf"`, `width="10mm"`), `d` que nao comeca por `M`/`m`,
  mais de 200 niveis de elementos aninhados (limite de profundidade 200; 150 niveis valem).
- Desempenho: `normalizar_planta` de SVG com 20000 `path` com curvas C e arcos A: pico de memoria (tracemalloc) < 60 MB e tempo < 5 s. `montar_svg` com um `<style>` de 100 KB
  sem `{` (e plantas grandes em geral) nao pode ter custo quadratico: < 1 s.
- Lateral adulterado (lido de `.obim` mexido a mao): `escala` 0, negativa, nao numerica, `nan`, `bool`, ou `carimbo` que nao e dict = erro da familia `PranchaInvalida`,
  nunca `ZeroDivisionError`/`AttributeError`/`TypeError`.
Cada caso roda num subprocesso (`python -I`) com limite de tempo e de memoria (RLIMIT_AS 1,5 GB), entao um travamento vira falha do teste, nao do pytest.
Os casos de entrada ruim valem como regressao: sem marcadores (a T08g foi corrigida)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

resource = pytest.importorskip("resource", reason="RLIMIT_AS so existe em sistemas Unix; no Windows a conferencia de memoria vale so no Linux")


APP = Path(__file__).resolve().parent.parent / "app"

PRE = f'''
import sys, time, json, tracemalloc
sys.path.insert(0, {str(APP)!r})
import openbim_app.prancha as m
S = 'xmlns="http://www.w3.org/2000/svg"'
def env(c, extra=""): return f'<svg {{S}} {{extra}}>{{c}}</svg>'
class Falso:
    def __init__(self, prancha, viewport): self.p, self.v = prancha, viewport
    def ids(self, c): return ["1"]
    def obter(self, c, i): return self.p if c == "pranchas" else self.v
def lateral(**sobre):
    p = {{"identification": "P", "formato": "A3", "carimbo": {{"projeto": "x", "titulo": "t", "data": "2026-11-01", "folha": "1"}}}}
    v = {{"prancha": "P", "vista_guid": "v", "x": 20, "y": 20, "escala": 100}}
    for k, val in sobre.items():
        (p if k == "carimbo" else v)[k] = val
    return Falso(p, v)
PLANTA = '<svg ' + S + ' viewBox="0 0 10 10"><rect width="1" height="1"/></svg>'
'''


def rodar(corpo, tempo=20, mem_mb=1500):
    """Executa `corpo` (Python; define `r` = texto de saida) no subprocesso. Devolve (saida, segundos_dentro, estourou_tempo)."""
    cod = PRE + f'''
t0 = time.time()
r = "OK"
try:
    exec({corpo!r})
except BaseException as e:
    r = type(e).__name__ + "|" + ",".join(c.__name__ for c in type(e).__mro__)
print(json.dumps([r, time.time() - t0, tracemalloc.get_traced_memory()[1] / 2**20 if tracemalloc.is_tracing() else 0]))
'''
    def lim():
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 2**20,) * 2)
    try:
        p = subprocess.run([sys.executable, "-I", "-c", cod], capture_output=True, text=True, timeout=tempo, preexec_fn=lim)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", float(tempo), True
    if p.returncode:
        return "MORREU " + p.stderr[-200:], 0.0, False
    r, seg, pico = json.loads(p.stdout.strip().splitlines()[-1])
    return r, seg, pico


def caso(nome, *args):
    return pytest.param(nome, *args, id=nome)


# ---------- 1 e 4: entradas ruins dao SvgInvalido, rapido, sem estourar memoria ----------
RUINS = [
    caso("z_numero_solto", '<path d="M0 0 L1 1 Z 5"/>'),
    caso("d_sem_M", '<path d="L1 1"/>'),
    caso("d_numero", '<path d="1 2"/>'),
    caso("d_vazio_sem_comando", '<path d="  "/>'),
    caso("comando_no_lugar_do_numero", '<path d="M 1 L 2 3"/>'),
    caso("S_inicial", '<path d="S 1 2 3 4"/>'),
    caso("T_inicial", '<path d="T 1 2"/>'),
    caso("Q_inicial", '<path d="Q 1 2 3 4"/>'),
    caso("flag_2", '<path d="M0 0 A1 1 0 2 0 5 5"/>'),
    caso("flag_1e999", '<path d="M0 0 A1 1 0 1e999 0 5 5"/>'),
    caso("flag_varrimento_2", '<path d="M0 0 A1 1 0 0 2 5 5"/>'),
    caso("flag_varrimento_1e999", '<path d="M0 0 A1 1 0 0 1e999 5 5"/>'),
    caso("circulo_raio_1e200", '<circle cx="0" cy="0" r="1e200"/>'),
    caso("circulo_raio_negativo", '<circle cx="0" cy="0" r="-1"/>'),
    caso("coordenada_1e300", '<path d="M0 0 L1e300 5"/>'),
    caso("coordenada_1e13", '<path d="M1e13 0 L1 5"/>'),
    caso("raio_1e200", '<path d="M0 0 A1e200 1e200 0 0 0 5 5"/>'),
    caso("largura_10mm", '<rect width="10mm" height="1"/>'),
    caso("x_abc", '<rect x="abc" width="1" height="1"/>'),
    caso("x_nan", '<rect x="nan" width="1" height="1"/>'),
    caso("x_inf", '<rect x="inf" width="1" height="1"/>'),
    caso("raio_inf", '<circle cx="0" cy="0" r="1e999"/>'),
    caso("linha_texto", '<line x1="a" y1="0" x2="1" y2="1"/>'),
    caso("points_impar", '<polyline points="1,2 3"/>'),
]


@pytest.mark.parametrize("nome,corpo", RUINS)
def test_01_entrada_ruim_da_planta_e_svginvalido(nome, corpo):
    r, seg, _ = rodar(f"m.normalizar_planta(env({corpo!r}))", tempo=10, mem_mb=1000)
    assert r.startswith("SvgInvalido|"), f"{nome}: veio {r!r} em {seg:.1f}s"
    assert seg < 2, f"{nome}: demorou {seg:.1f}s para recusar"


def test_02_z_numero_solto_nao_estoura_memoria():
    r, seg, _ = rodar("m.normalizar_planta(env('<path d=\"M0 0 L1 1 Z 5\"/>'))", tempo=10, mem_mb=400)
    assert r.startswith("SvgInvalido|"), f"veio {r!r}"


# ---------- 2 e 3: desempenho ----------
@pytest.mark.parametrize("nome", [caso("curvas_e_arcos")])
def test_03_vinte_mil_paths_memoria_e_tempo(nome):
    corpo = ("paths = ''.join(f'<path d=\"M{i} 0 C{i+1} 5 {i+2} 5 {i+3} 0 A2 2 0 0 1 {i+7} 0\"/>' for i in range(20000))\n"
             "tracemalloc.start()\nt1 = time.time()\nm.normalizar_planta(env(paths))\nseg = time.time() - t1\n"
             "pico = tracemalloc.get_traced_memory()[1] / 2**20\nr = 'OK' if (pico < 60 and seg < 5) else f'LENTO_OU_PESADO pico={pico:.0f}MB tempo={seg:.1f}s'")
    r, _, _ = rodar(corpo, tempo=60, mem_mb=1500)
    assert r == "OK", r


@pytest.mark.parametrize("nome,tamanho", [pytest.param("style_100k", 100_000, id="style_100k"), caso("style_pequeno", 10_000)])
def test_04_style_grande_sem_chave_e_rapido(nome, tamanho):
    corpo = (f"st = 'a' * {tamanho}\nplanta = '<svg ' + S + ' viewBox=\"0 0 10 10\"><style>' + st + '</style><rect width=\"1\" height=\"1\"/></svg>'\n"
             "import s06_t08_aux as A\nlado, _ = A.montar()\nt1 = time.time()\nm.montar_svg(lado.lat, A.IDENT, A.GUID, planta)\nseg = time.time() - t1\n"
             "r = 'OK' if seg < 1 else f'LENTO {seg:.1f}s'")
    r, _, _ = rodar(f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n" + corpo, tempo=60)
    assert r == "OK", r


# ---------- 5: profundidade ----------
@pytest.mark.parametrize("nome,n,esperado", [
    caso("profundidade_150", 150, "OK"),
    caso("profundidade_3000", 3000, "SvgInvalido"),
    caso("profundidade_201", 201, "SvgInvalido"),
])
def test_05_profundidade_de_elementos(nome, n, esperado):
    corpo = (f"c = '<g>' * {n} + '<rect width=\"1\" height=\"1\"/>' + '</g>' * {n}\n"
             "m.normalizar_planta(env(c))")
    r, _, _ = rodar(corpo, tempo=20)
    assert r == "OK" if esperado == "OK" else r.startswith("SvgInvalido|"), f"{nome}: veio {r!r}"


def test_06_profundidade_tambem_em_montar_svg_com_viewbox():
    for n, esperado in ((150, "OK"), (201, "SvgInvalido")):
        corpo = (f"c = '<g>' * {n} + '<rect width=\"1\" height=\"1\"/>' + '</g>' * {n}\n"
                 "m.montar_svg(lateral(), 'P', 'v', env(c, 'viewBox=\"0 0 10 10\"'))")
        r, _, _ = rodar(corpo, tempo=20)
        assert (r == "OK") if esperado == "OK" else r.startswith("SvgInvalido|"), f"{n} niveis: veio {r!r}"
    """A planta ja tem viewBox: `normalizar_planta` nem olha dentro, e a recursao de `montar_svg` (espessuras) e que tem de recusar."""
    corpo = ("c = '<g>' * 3000 + '<rect width=\"1\" height=\"1\"/>' + '</g>' * 3000\nplanta = env(c, 'viewBox=\"0 0 10 10\"')\n"
             "m.montar_svg(lateral(), 'P', 'v', planta)")
    r, _, _ = rodar(corpo, tempo=20)
    assert r.startswith("SvgInvalido|"), f"veio {r!r}"


# ---------- 6: lateral adulterado ----------
ESCALAS = [("zero", "0"), ("negativa", "-5"), ("texto", "'x'"), ("nula", "None"), ("bool", "True"), ("nan", "float('nan')"), ("infinita", "float('inf')")]
CARIMBOS = [("string", "'x'"), ("nulo", "None"), ("numero", "5"), ("lista", "[1]"), ("campo_numerico", "{'projeto': 1, 'titulo': 't', 'data': '2026-11-01', 'folha': '1'}")]


@pytest.mark.parametrize("nome,valor", [pytest.param(n, v, id=f"escala_{n}") for n, v in ESCALAS])
def test_07_escala_adulterada(nome, valor):
    r, _, _ = rodar(f"m.montar_svg(lateral(escala={valor}), 'P', 'v', PLANTA)")
    assert r.startswith("EscalaInvalida|"), f"escala {nome}: veio {r!r}"


@pytest.mark.parametrize("nome,valor", [pytest.param(n, v, id=f"carimbo_{n}") for n, v in CARIMBOS])
def test_08_carimbo_adulterado(nome, valor):
    r, _, _ = rodar(f"m.montar_svg(lateral(carimbo={valor}), 'P', 'v', PLANTA)")
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"carimbo {nome}: veio {r!r}"


@pytest.mark.parametrize("campo,valor", [("x", "'a'"), ("x", "None"), ("x", "float('nan')"), ("y", "float('inf')"), ("y", "True"), ("x", "[1]")])
def test_08b_coordenadas_adulteradas(campo, valor):
    r, _, _ = rodar(f"m.montar_svg(lateral({campo}={valor}), 'P', 'v', PLANTA)")
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"{campo}={valor}: veio {r!r}"


@pytest.mark.parametrize("quem", ["prancha", "viewport"])
@pytest.mark.parametrize("valor", ["None", "5", "[1]", "'x'"])
def test_08c_objeto_nao_dict(quem, valor):
    ps, vs = (valor, "ok.v") if quem == "prancha" else ("ok.p", valor)
    r, _, _ = rodar(f"ok = lateral()\nm.montar_svg(Falso({ps}, {vs}), 'P', 'v', PLANTA)")
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"{quem}={valor}: veio {r!r}"


def test_09_lateral_sadio_continua_valendo():
    r, _, _ = rodar("m.montar_svg(lateral(), 'P', 'v', PLANTA)")
    assert r == "OK", r


# ---------- T08h: entradas gigantes e casos de borda (revisao 2) ----------
def H(nome, *args):
    return pytest.param(nome, *args, id=nome)


def _ok_rapido(corpo, limite_s, tempo=30, mem_mb=1024, esperado="OK"):
    """Roda `corpo` (que chama a funcao a medir) e exige: resultado `esperado` e menos de `limite_s` s dentro do subprocesso."""
    r, seg, _ = rodar(corpo, tempo=tempo, mem_mb=mem_mb)
    ok = r == "OK" if esperado == "OK" else r.startswith(esperado + "|")
    assert ok, f"veio {r!r} em {seg:.1f}s"
    assert seg < limite_s, f"demorou {seg:.1f}s (limite {limite_s}s)"


@pytest.mark.parametrize("nome,corpo,limite", [
    H("path_5MB_de_curvas", "d = 'M0 0 ' + 'C1 1 2 2 3 3 ' * 400000\nm.normalizar_planta(env('<path d=\"' + d + '\"/>'))", 20),
    H("path_20MB_de_retas", "d = 'M0 0 ' + 'L1 1 ' * 4000000\nm.normalizar_planta(env('<path d=\"' + d + '\"/>'))", 20),
    H("style_abre_chave_40000", "st = 'a{' * 40000\nm.montar_svg(lateral(), 'P', 'v', '<svg ' + S + ' viewBox=\"0 0 10 10\"><style>' + st + '</style><rect width=\"1\" height=\"1\"/></svg>')", 3),
    H("rects_250mil_199_niveis", "c = '<g class=\"a\">' * 199 + '<rect width=\"1\" height=\"1\"/>' * 250000 + '</g>' * 199\nm.montar_svg(lateral(), 'P', 'v', env(c, 'viewBox=\"0 0 10 10\"'))", 3),
    H("arco_raio_1e-200", "m.normalizar_planta(env('<path d=\"M0 0 A1e-200 1e-200 0 0 0 5 5\"/>'))", 2),
])
def test_10_entradas_gigantes_dentro_do_limite(nome, corpo, limite):
    _ok_rapido(corpo, limite, mem_mb=350 if nome.startswith("path_") else 1024)


@pytest.mark.parametrize("nome,corpo,limite", [
    H("transform_a_abre_parenteses_200000", "t = 'a(' * 200000\nm.normalizar_planta(env('<g transform=\"' + t + '\"><rect width=\"1\" height=\"1\"/></g>'))", 3),
    H("defs_com_1000_g_aninhados", "c = '<defs>' + '<g>' * 1000 + '</g>' * 1000 + '</defs><rect width=\"1\" height=\"1\"/>'\nm.montar_svg(lateral(), 'P', 'v', env(c, 'viewBox=\"0 0 10 10\"'))", 3),
    H("viewbox_1e308", "m.montar_svg(lateral(), 'P', 'v', '<svg ' + S + ' viewBox=\"1e308 0 0.001 0.001\"><rect width=\"1\" height=\"1\"/></svg>')", 3),
    H("x_com_sublinhado", "m.normalizar_planta(env('<rect x=\"1_0\" width=\"1\" height=\"1\"/>'))", 3),
    H("x_digitos_arabes", "m.normalizar_planta(env('<rect x=\"\u0661\u0660\" width=\"1\" height=\"1\"/>'))", 3),
    H("x_digitos_largura_total", "m.normalizar_planta(env('<rect x=\"\uff11\uff10\" width=\"1\" height=\"1\"/>'))", 3),
    H("path_com_digitos_arabes", "m.normalizar_planta(env('<path d=\"M\u0661 0 L5 5\"/>'))", 3),
])
def test_11_recusa_com_svginvalido(nome, corpo, limite):
    _ok_rapido(corpo, limite, esperado="SvgInvalido")


@pytest.mark.parametrize("nome,corpo", [
    H("escala_10_elevado_400", "m.montar_svg(lateral(escala=10**400), 'P', 'v', PLANTA)"),
    H("formato_lista", "p = lateral(); p.p['formato'] = ['A3']\nm.montar_svg(p, 'P', 'v', PLANTA)"),
    H("formato_dict", "p = lateral(); p.p['formato'] = {'a': 1}\nm.montar_svg(p, 'P', 'v', PLANTA)"),
    H("data_9999_99_99", "m.montar_svg(lateral(carimbo={'projeto': 'x', 'titulo': 't', 'data': '9999-99-99', 'folha': '1'}), 'P', 'v', PLANTA)"),
    H("data_2026_02_30", "m.montar_svg(lateral(carimbo={'projeto': 'x', 'titulo': 't', 'data': '2026-02-30', 'folha': '1'}), 'P', 'v', PLANTA)"),
])
def test_12_lateral_adulterado_e_pranchainvalida(nome, corpo):
    r, _, _ = rodar(corpo)
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"{nome}: veio {r!r}"


# ---------- T08h: tetos e fronteiras (mutantes sobreviventes) ----------
@pytest.mark.parametrize("nome,corpo,limite", [
    H("caixa_transform_escala_1e10", "m.normalizar_planta(env('<g transform=\"scale(1e10)\"><path d=\"M0 0 L1e10 0 L0 1\"/></g>'))", 3),
    H("caixa_translate_somado_1e12", "m.normalizar_planta(env('<g transform=\"translate(1e12)\"><rect x=\"1e12\" width=\"1\" height=\"1\"/></g>'))", 3),
    H("svg_texto_maior_que_64MB", "m.normalizar_planta('<svg ' + S + '><!--' + 'x' * (64 * 2**20) + '--><rect width=\"1\" height=\"1\"/></svg>')", 20),
    H("svg_bytes_maior_que_64MB", "m.normalizar_planta(('<svg ' + S + '><!--' + 'x' * (64 * 2**20) + '--><rect width=\"1\" height=\"1\"/></svg>').encode())", 20),
    H("transform_valido_com_1500_caracteres", "t = 'translate(1) ' * 120\nm.normalizar_planta(env('<g transform=\"' + t + '\"><rect width=\"1\" height=\"1\"/></g>'))", 3),
    H("mais_de_5_milhoes_de_comandos", "d = 'M0 0 ' + 'L1 1 ' * 5100000\nm.normalizar_planta(env('<path d=\"' + d + '\"/>'))", 40),
    H("style_maior_que_2MB", "st = 'a{}' * 750000\nm.montar_svg(lateral(), 'P', 'v', '<svg ' + S + ' viewBox=\"0 0 10 10\"><style>' + st + '</style><rect width=\"1\" height=\"1\"/></svg>')", 5),
])
def test_13_tetos_e_caixa(nome, corpo, limite):
    _ok_rapido(corpo, limite, tempo=60, mem_mb=1500, esperado="SvgInvalido")


def test_13b_transform_900_caracteres_continua_valendo():
    _ok_rapido("t = 'translate(1) ' * 60\nm.normalizar_planta(env('<g transform=\"' + t + '\"><rect width=\"1\" height=\"1\"/></g>'))", 3)


DATA_AR = "\u0662\u0660\u0662\u0666-\u0660\u0661-\u0660\u0661"


@pytest.mark.parametrize("nome,corpo", [
    H("escala_1e13", "m.montar_svg(lateral(escala=1e13), 'P', 'v', PLANTA)"),
    H("x_1e13", "m.montar_svg(lateral(x=1e13), 'P', 'v', PLANTA)"),
    H("y_10_elevado_400", "m.montar_svg(lateral(y=10**400), 'P', 'v', PLANTA)"),
    H("data_digitos_arabes_no_lateral", "m.montar_svg(lateral(carimbo={'projeto': 'x', 'titulo': 't', 'data': " + repr(DATA_AR) + ", 'folha': '1'}), 'P', 'v', PLANTA)"),
])
def test_14_lateral_fronteiras(nome, corpo):
    r, _, _ = rodar(corpo)
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"{nome}: veio {r!r}"


def test_14b_criar_prancha_data_digitos_arabes():
    corpo = ("class L:\n    def criar(self, *a): pass\n"
             "m.criar_prancha(L(), 'P', 'A3', 'x', 't', " + repr(DATA_AR) + ", '1')")
    r, _, _ = rodar(corpo)
    assert "|" in r and "PranchaInvalida" in r.split("|")[1].split(","), f"veio {r!r}"


@pytest.mark.parametrize("args,classe", [
    pytest.param("1e13, 0, 100", "PranchaInvalida", id="x_1e13"),
    pytest.param("0, -1e13, 100", "PranchaInvalida", id="y_menos_1e13"),
    pytest.param("10**400, 0, 100", "PranchaInvalida", id="x_10_elevado_400"),
    pytest.param("0, 10**400, 100", "PranchaInvalida", id="y_10_elevado_400"),
    pytest.param("float('nan'), 0, 100", "PranchaInvalida", id="x_nan"),
    pytest.param("0, 0, 10**400", "EscalaInvalida", id="escala_10_elevado_400"),
    pytest.param("0, 0, 1e13", "EscalaInvalida", id="escala_1e13"),
    pytest.param("0, 0, float('inf')", "EscalaInvalida", id="escala_inf"),
])
def test_15_colocar_viewport_fronteiras(args, classe):
    corpo = "class L:\n    def criar(self, *a): pass\nm.colocar_viewport(L(), 'P', 'v', " + args + ")"
    r, _, _ = rodar(corpo)
    assert r.startswith(classe + "|"), f"veio {r!r}"
