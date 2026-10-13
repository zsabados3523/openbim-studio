# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da seleção por triângulo e da memória (S04-T10; LOTE_OPUS_9 §1 a §6, cartão F0-S04-T10; casos de `test_viewport_selecao.py` da S03).
Cada caso gráfico roda em SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1), como `test_s04_cena.py`.
GUARDA: pula enquanto faltar `Cena.selecionar` (e, nos casos que os usam, `atualizar`, `orbitar`, `mover`, `aproximar`); FALHA com OBIM_S04_T10_OBRIGATORIO=1.
API ESPERADA (o implementador segue; o oráculo não depende de mais nada):
 * Cena.selecionar(x: float, y: float) -> str | None
     (x, y) em PIXELS da viewport, os mesmos de `capturar()` (origem no canto superior esquerdo, y para baixo; escala 1 nos testes). Devolve o
     GlobalId (22 caracteres, `str`) do objeto cujo TRIÂNGULO o raio do pixel acerta primeiro (o mais perto da câmera), ou None se nenhum triângulo
     (não a caixa do objeto: vão de parede, canto de peça em L e intervalo entre pedaços do mesmo objeto em lotes diferentes dão None).
     Usa a câmera JÁ APLICADA (a de `camera()`) e a cena já gravada na cópia compacta do C++ (não espera a placa). Chamada da thread da janela.
     x ou y fora de [0, largura) x [0, altura) da viewport, ou NaN/inf: ValueError, sem alterar a cena.
 * Depois de `atualizar`, `limpar` ou `perder_contexto`, nunca devolve objeto removido.
Régua de tempo (1 milhão de triângulos, 50 consultas em pixels variados que acertam geometria): sempre mediana < 100 ms e nenhuma >= 250 ms
(régua do CI virtual); fora do CI (variável CI ausente: máquina do PO) vale também o p95 < 100 ms. Memória: bytes de RSS do processo acrescentados
pela cena com 1 milhão de triângulos (cópia compacta + placa por software), por triângulo, < 200; o valor é impresso (use `pytest -rsP`)."""
import importlib, importlib.util, os, shutil, sys, time  # noqa: E401
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from test_s04_cena import AMARELO, G, cent, com_guids, estavel, pos, tres  # noqa: F401
from test_s04_viewport import CORES, FUNDO, METODOS, RAIZ, captura, esperar, lote, novo, rodar, um
from test_s04_viewport import caso as _caso
from test_s04_viewport_b import grade

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
OBRIG = os.environ.get("OBIM_S04_T10_OBRIGATORIO") == "1"
CI = bool(os.environ.get("CI"))
pular = pytest.fail if OBRIG else pytest.skip
K, N_LAD = 24, 720  # ladrilhos: 24x24 objetos, cada um 30x30 células (2*720*720 = 1 036 800 triângulos)
MIL = "{:022d}".format

def exige(*extra):
    import obimcore
    faltam = [m for m in ("selecionar", *extra) if not hasattr(obimcore.Cena, m)]
    faltam and pular(f"\n!!! aguarda S04-T10: Cena sem {faltam} (seleção por triângulo NÃO FOI EXECUTADA) !!!\n")

@pytest.fixture(scope="module")
def sel():
    if importlib.util.find_spec("obimcore") is None:
        pular("\n!!! aguarda S04-T10: módulo obimcore ausente (oráculo da seleção NÃO FOI EXECUTADO) !!!\n")
    import ifcopenshell, obimcore  # noqa: E401,F401
    faltam = [m for m in METODOS if not hasattr(getattr(obimcore, "Cena", None), m)]
    faltam and pular(f"\n!!! aguarda S04-T07/T08: obimcore sem {faltam} (oráculo da seleção NÃO FOI EXECUTADO) !!!\n")
    exige()
    if not (CI or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("\n!!! sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real !!!\n")

# ---------- auxiliares de imagem (rodam dentro do subprocesso) ----------
def mascara(a, k):  # mesma regra de `classificar`/`cent`: v, g, a = vermelho, verde, azul; "y" amarelo; "f" fundo
    r, g, b = (a[..., i].astype(int) for i in range(3))
    if k == "y":
        return (r > 200) & (g > 180) & (b < 80)
    if k == "f":
        return np.abs(a[..., :3].astype(int) - np.array(FUNDO)).max(-1) <= 12
    x, y, z = {"v": (r, g, b), "g": (g, r, b), "a": (b, r, g)}[k]
    return (x >= 60) & (x > 1.8 * y) & (x > 1.8 * z)

def eros(m, k):
    for _ in range(k):
        p = np.pad(m, 1, constant_values=False)
        m = m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m

def varrer(c, a, esperado, passo=1, bg=3, borda=2):
    """Para cada pixel CONFIANTE (cor `k` erodida `borda`; fundo erodido `bg`) pergunta `selecionar`; esperado = {k: guid} e "f" -> None."""
    out = {}
    for k, guid in {**esperado, "f": None}.items():
        m = eros(mascara(a, k), bg if k == "f" else borda)
        ys, xs = np.nonzero(m)
        pa = passo * 3 if k == "f" else passo
        ok = (ys % pa == 0) & (xs % pa == 0)
        ruins = [(int(x), int(y), c.selecionar(float(x) + 0.5, float(y) + 0.5)) for x, y in zip(xs[ok], ys[ok])]
        ruins = [r for r in ruins if r[2] != guid]
        n = int(ok.sum())
        out[k] = dict(n=n, ruins=len(ruins), ex=ruins[:4])
    return out

def rss():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except ImportError:
        pass
    if sys.platform.startswith("linux"):
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    import ctypes
    from ctypes import wintypes
    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("pf", wintypes.DWORD)] + [(f"s{i}", ctypes.c_size_t) for i in range(8)]
    p = PMC(cb=ctypes.sizeof(PMC))
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(p), p.cb)
    return int(p.s1)  # WorkingSetSize

def um_objeto(cubos, guid):  # vários cubos num ÚNICO objeto (a caixa do objeto cobre os vazios entre eles)
    from viewport_qrhi.carregador import DTYPE_OBJETO
    l = lote(cubos=cubos)
    o = np.zeros(1, DTYPE_OBJETO)
    o[0] = (1, guid.encode(), 0, len(l.indices), 0, len(l.vertices), l.vertices["pos"].min(0), l.vertices["pos"].max(0))
    return replace(l, objetos=o, produtos_feitos=1, produtos_total=1)

def ladrilhos():  # grade de K*K objetos em xadrez vermelho/verde; guid = MIL(t), t = linha*K + coluna; vértices de cada objeto só dele
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    m = N_LAD // K
    nv, nt = (m + 1) ** 2, K * K
    t = np.arange(nt)
    ti, tj = np.divmod(t, K)
    u, v = np.repeat(np.arange(m + 1), m + 1), np.tile(np.arange(m + 1), m + 1)
    esc = 8.0 / N_LAD
    ver = np.zeros(nt * nv, DTYPE_VERTICE)
    ver["pos"][:, 0] = ((tj[:, None] * m + v[None, :] - N_LAD / 2) * esc).ravel()
    ver["pos"][:, 1] = ((ti[:, None] * m + u[None, :] - N_LAD / 2) * esc).ravel()
    ver["normal"][:, 2] = 1
    ver["cor"] = np.repeat(np.where(((ti + tj) % 2 == 0)[:, None], CORES[0], CORES[1]), nv, 0).astype(np.uint8)
    a = (np.arange(m)[:, None] * (m + 1) + np.arange(m)[None, :]).ravel()
    loc = np.stack([a, a + 1, a + m + 2, a, a + m + 2, a + m + 1], -1).ravel()
    ind = (loc[None, :] + (t * nv)[:, None]).ravel().astype(np.uint32)
    p = ver["pos"].reshape(nt, nv, 3)
    o = np.zeros(nt, DTYPE_OBJETO)
    for j in range(nt):
        o[j] = (j, MIL(j).encode(), j * len(loc), len(loc), j * nv, nv, p[j].min(0), p[j].max(0))
    return LoteMalha(0, ver, ind, o, np.zeros(3), nt, nt)

# ---------- casos ----------
def c_basico(res):  # (1) três cubos: varredura densa (inclui as diagonais das faces e as bordas) e (2) erros de coordenada
    c, w, _ = novo(0)
    c.adicionar_lote(tres())
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 36)
    yield 500
    a = captura(c)
    h, lg = a.shape[:2]
    res["tam"], res["cls"] = [lg, h], {k: int(mascara(a, k).sum()) for k in "vga"}
    res["varredura"] = varrer(c, a, {"v": G(0), "g": G(1), "a": G(2)}, passo=1, bg=3, borda=1)
    res["centroides"] = {G(i): [cent(a, k)[1], cent(a, k)[2]] for i, k in enumerate("vga")}
    res["tipo"] = type(c.selecionar(res["centroides"][G(0)][0], res["centroides"][G(0)][1])).__name__
    erros = {}
    for nome, xy in {"x<0": (-1.0, 10.0), "y<0": (10.0, -1.0), "x>=larg": (lg + 1.0, 10.0), "y>=alt": (10.0, h + 1.0), "enorme": (1e9, 1e9),
                     "nan x": (float("nan"), 10.0), "nan y": (10.0, float("nan")), "inf": (float("inf"), 10.0), "-inf": (10.0, float("-inf"))}.items():
        try:
            erros[nome] = f"aceitou {c.selecionar(*xy)!r}"
        except ValueError:
            erros[nome] = "ValueError"
        except BaseException as ex:  # noqa: BLE001
            erros[nome] = "SUJO " + type(ex).__name__
    res["erros"] = erros
    res["depois"] = c.selecionar(*res["centroides"][G(1)])  # a cena continua intacta e a seleção funcional
    res["viva"] = c.viva()
    c.parar()

def c_frente(res):  # cubo verde ATRÁS, cubo vermelho NA FRENTE tapando parte dele: no pixel da sobreposição vale o mais perto
    c, w, _ = novo(0)
    c.adicionar_lote(com_guids(lote(cubos=[((0, 3, 0.5), 1.5, CORES[1])]), G(1)))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12)
    yield 500
    verde_so = eros(mascara(captura(c), "g"), 2)
    c.adicionar_lote(com_guids(lote(cubos=[((0.4, -3, 0), 1.5, CORES[0])]), G(0)))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 24)
    yield 500
    a = captura(c)
    sobre = verde_so & eros(mascara(a, "v"), 2)
    res["n_sobre"], res["n_verde"] = int(sobre.sum()), int((eros(mascara(a, "g"), 2)).sum())
    ys, xs = np.nonzero(sobre)
    got = [c.selecionar(float(x) + 0.5, float(y) + 0.5) for x, y in zip(xs[::3], ys[::3])]
    res["sobre"] = sorted({str(g) for g in got})
    res["varredura"] = varrer(c, a, {"v": G(0), "g": G(1)}, passo=3)
    c.parar()

def c_vao(res):  # parede de tijolos (UM objeto) com vão; atrás do vão um cubo azul; a caixa da parede cobre o vão, o triângulo não
    c, w, _ = novo(0, dict(alvo=(0.0, 0.0, 1.5), distancia=20.0, azimute=-90.0, elevacao=0.0))
    tij = [((x, 0, z), 0.5, CORES[0]) for x in range(-4, 5) for z in range(4) if not (-1 <= x <= 1 and z <= 1)]
    c.adicionar_lote(um_objeto(tij, "W" * 22))
    c.adicionar_lote(com_guids(lote(cubos=[((0, 6, 0.5), 0.8, CORES[2])]), "B" * 22))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12 * len(tij) + 12)
    yield 500
    a = captura(c)
    v = mascara(a, "v")
    fundo = eros(mascara(a, "f"), 3)
    esq, dir_ = np.maximum.accumulate(v, 1), np.maximum.accumulate(v[:, ::-1], 1)[:, ::-1]
    res["n_vao"], res["n_azul"] = int((fundo & esq & dir_).sum()), int(eros(mascara(a, "a"), 2).sum())
    ys, xs = np.nonzero(fundo & esq & dir_)
    res["vao"] = sorted({str(c.selecionar(float(x) + 0.5, float(y) + 0.5)) for x, y in zip(xs[::2], ys[::2])})
    res["varredura"] = varrer(c, a, {"v": "W" * 22, "a": "B" * 22}, passo=3)
    c.parar()

def c_dividido(res):  # o MESMO objeto em dois lotes (x=-4 e x=4) com outro objeto no meio: o intervalo não é do objeto (S03: peça dividida)
    c, w, _ = novo(0)
    for x in (-4, 4):
        c.adicionar_lote(com_guids(lote(cubos=[((x, 0, 0), 1.0, CORES[0])]), "X" * 22))
    c.adicionar_lote(com_guids(lote(cubos=[((0, 0, 0), 1.0, CORES[1])]), "Y" * 22))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 36)
    yield 500
    a = captura(c)
    res["varredura"] = varrer(c, a, {"v": "X" * 22, "g": "Y" * 22}, passo=2)
    c.parar()

def c_remocao(res):  # (3) atualizar/limpar/perder_contexto: nunca devolve objeto removido
    c, w, _ = novo(0)
    c.adicionar_lote(tres())
    esp = lambda n: esperar(lambda: c.estatisticas()["triangulos"] == n and c.estatisticas()["triangulos_na_placa"] == n)  # noqa: E731
    yield from esp(36)
    yield 500
    a = captura(c)
    px = {G(i): (cent(a, k)[1] + 0.5, cent(a, k)[2] + 0.5) for i, k in enumerate("vga")}
    res["antes"] = [c.selecionar(*px[G(i)]) for i in range(3)]
    c.atualizar(None, [G(1)])  # remove o verde (os outros do mesmo lote ficam)
    yield from esp(24)
    yield 500
    res["sem_verde"] = [c.selecionar(*px[G(i)]) for i in range(3)]
    c.atualizar(com_guids(lote(cubos=[((-4, 0, 6), 1.0, AMARELO)]), G(0)), [])  # troca o vermelho: mesmo guid, outro lugar (mais alto)
    yield from esp(24)
    yield 500
    a = captura(c)
    nv = (cent(a, "v")[0], int(mascara(a, "y").sum()))
    ys, xs = np.nonzero(mascara(a, "y"))
    novo_px = (float(xs.mean()) + 0.5, float(ys.mean()) + 0.5)
    res["troca"] = dict(vermelho_px=nv[0], amarelo_px=nv[1], velho=c.selecionar(*px[G(0)]), novo=c.selecionar(*novo_px), azul=c.selecionar(*px[G(2)]))
    n0 = c.estatisticas()["contextos"]
    c.perder_contexto()
    res["ctx"] = yield from esperar(lambda: c.estatisticas()["contextos"] > n0 and c.estatisticas()["triangulos_na_placa"] == 24, 12000)
    yield 500
    res["pos_ctx"] = dict(velho=c.selecionar(*px[G(0)]), verde=c.selecionar(*px[G(1)]), novo=c.selecionar(*novo_px), azul=c.selecionar(*px[G(2)]))
    c.limpar()
    yield from esperar(lambda: c.estatisticas()["triangulos"] == 0)
    yield 300
    res["limpo"] = [c.selecionar(*px[G(i)]) for i in range(3)] + [c.selecionar(*novo_px)]
    c.adicionar_lote(um(0))  # depois de limpar a cena aceita e seleciona o novo
    yield from esp(12)
    yield 500
    a = captura(c)
    res["recolocado"] = c.selecionar(cent(a, "v")[1] + 0.5, cent(a, "v")[2] + 0.5)
    res["viva"] = c.viva()
    c.parar()

def c_camera(res):  # (4) a seleção acompanha a câmera já aplicada: depois de cada movimento, o centro de cada cor acerta o objeto daquela cor
    c, w, _ = novo(0)
    c.adicionar_lote(tres(3))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 36)
    yield 500
    a_ant, res["passos"] = captura(c), {}
    pontos = lambda a: {G(i): (cent(a, k)[1] + 0.5, cent(a, k)[2] + 0.5, cent(a, k)[0]) for i, k in enumerate("vga")}  # noqa: E731
    ant = pontos(a_ant)
    for nome, f, args in (("orbitar_x", c.orbitar, (240, 0)), ("orbitar_y", c.orbitar, (0, 30)), ("mover", c.mover, (60, -20)), ("aproximar", c.aproximar, (1.5,))):
        antes = pos(c)
        f(*args)
        yield from esperar(lambda: pos(c) != antes, 3000)
        yield 450
        a = captura(c)
        atual = pontos(a)
        vis = [g for g, p in atual.items() if p[2] >= 300]
        res["passos"][nome] = dict(
            visiveis=len(vis), certos=sum(c.selecionar(atual[g][0], atual[g][1]) == g for g in vis),
            moveram=[g for g in vis if abs(atual[g][0] - ant[g][0]) + abs(atual[g][1] - ant[g][1]) > 20],
            velho_ainda=[g for g in vis if ant[g][2] >= 300 and c.selecionar(ant[g][0], ant[g][1]) == g and abs(atual[g][0] - ant[g][0]) > 20],
            varredura=varrer(c, a, {k: G(i) for i, k in enumerate("vga")}, passo=5, borda=3))
        ant = atual
    c.parar()

def c_milhao(res, modo):  # (5) 1 milhão de triângulos: tempo de 50 consultas e (6) memória da cópia
    c, w, _ = novo(0, dict(alvo=(0.0, 0.0, 0.0), distancia=7.0, azimute=-90.0, elevacao=70.0))  # perto: o ladrilho tem de ter pixels de sobra
    yield 1000
    g, res["modo"] = (grade(707) if modo == "unico" else ladrilhos()), modo
    res["tri"] = tri = len(g.indices) // 3
    r0 = rss()
    c.adicionar_lote(g)
    res["copia"] = yield from esperar(lambda: c.estatisticas()["triangulos"] == tri, 90000)
    res["placa"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == tri, 150000)
    yield 1500
    r1 = rss()
    res["rss_mb"], res["bytes_por_tri"] = [r0 / 2**20, r1 / 2**20], (r1 - r0) / tri
    res["chaves"] = sorted(k for k in c.estatisticas() if "byte" in k.lower() or "mem" in k.lower())
    a = captura(c)
    d = a[..., 0].astype(int) - a[..., 1].astype(int)  # vermelho (d > 40) ou verde (d < -40), qualquer sombreado
    cls = np.where(d > 40, 1, np.where(d < -40, 2, 0))
    from numpy.lib.stride_tricks import sliding_window_view as swv
    unif = np.zeros(cls.shape, bool)
    j = swv(cls, (5, 5))
    unif[2:-2, 2:-2] = (j.min((-1, -2)) == j.max((-1, -2))) & (j[..., 2, 2] > 0)
    ys, xs = np.nonzero(unif)
    res["n_candidatos"] = len(ys)
    esc = np.random.default_rng(12345).choice(len(ys), 50, replace=False) if len(ys) >= 50 else []
    tempos, hits = [], []
    for i in esc:
        x, y = float(xs[i]) + 0.5, float(ys[i]) + 0.5
        t0 = time.perf_counter()
        h = c.selecionar(x, y)
        tempos.append((time.perf_counter() - t0) * 1000)
        hits.append([h, int(cls[ys[i], xs[i]])])
    res["tempos"], res["hits"] = tempos, hits
    res["cor_ok"] = sum(h is not None and modo == "ladrilhos" and (1 if sum(divmod(int(h), K)) % 2 == 0 else 2) == k for h, k in hits)
    c.parar()

# ---------- testes ----------
def sem_erros(v, minimo=100):  # varredura: cada classe com pelo menos `minimo` pixels e nenhum ruim
    return all(d["ruins"] == 0 for d in v.values()) and all(d["n"] >= minimo for k, d in v.items() if k != "f") and v["f"]["n"] >= minimo

def test_tres_cubos_varredura_densa_acerta_o_objeto_e_fora_da_none(sel):  # borda do triângulo, diagonais das faces, fundo
    r = caso("basico")
    assert r["viva"] and all(r["cls"][k] >= 500 for k in "vga"), r
    assert r["tipo"] == "str", f"selecionar deve devolver o GlobalId como str (ou None): {r['tipo']}"
    assert sem_erros(r["varredura"], 500), f"pixel com objeto errado, buraco entre triângulos ou fundo selecionado: {r['varredura']}"

def test_coordenada_fora_da_janela_ou_nao_finita_levanta_valueerror(sel):
    r = caso("basico")
    assert all(v == "ValueError" for v in r["erros"].values()), r["erros"]
    assert r["depois"] == G(1), f"depois dos erros a seleção deixou de funcionar: {r['depois']}"

def test_o_mais_perto_da_camera_vence_quando_um_cubo_tapa_o_outro(sel):
    r = caso("frente")
    assert r["n_sobre"] >= 200 and r["n_verde"] >= 300, f"controle: a cena deveria ter sobreposição visível: {r}"
    assert r["sobre"] == [G(0)], f"na sobreposição vale o cubo da frente (vermelho {G(0)}): {r['sobre']}"
    assert sem_erros(r["varredura"]), r["varredura"]

def test_vao_de_parede_e_dado_pelo_triangulo_nao_pela_caixa(sel):  # precisão de triângulo: a caixa da parede cobre o vão
    r = caso("vao")
    assert r["n_vao"] >= 100 and r["n_azul"] >= 100, f"controle: o vão deveria mostrar fundo e o cubo azul de trás: {r}"
    assert "W" * 22 not in r["vao"], f"o vão da parede selecionou a parede (seleção só pela caixa): {r['vao']}"
    assert set(r["vao"]) <= {"None"}, f"pixel de fundo dentro do vão devolveu {r['vao']}"
    assert sem_erros(r["varredura"], minimo=20), f"parede -> W, cubo visto pelo vão -> B, fundo -> None: {r['varredura']}"

def test_objeto_dividido_em_lotes_nao_e_selecionavel_no_intervalo(sel):  # S03: peça dividida em vários lotes é um objeto só, mas o vão é vazio
    r = caso("dividido")
    assert sem_erros(r["varredura"]), r["varredura"]

def test_depois_de_atualizar_limpar_e_perder_contexto_nao_devolve_removido(sel):
    exige("atualizar")
    r = caso("remocao", limite=300)
    t, p = r["troca"], r["pos_ctx"]
    assert r["viva"] and r["antes"] == [G(0), G(1), G(2)], r
    assert r["sem_verde"] == [G(0), None, G(2)], f"verde removido ainda selecionável: {r['sem_verde']}"
    assert t["vermelho_px"] < 20 and t["amarelo_px"] >= 300, f"controle: a troca não aparece na imagem: {t}"
    assert t["velho"] is None and t["novo"] == G(0) and t["azul"] == G(2), f"depois de trocar o vermelho (mesmo guid, outro lugar): {t}"
    assert r["ctx"] and p == dict(velho=None, verde=None, novo=G(0), azul=G(2)), f"depois da perda de contexto: {p}"
    assert r["limpo"] == [None] * 4, f"depois de limpar: {r['limpo']}"
    assert r["recolocado"] == G(0), f"depois de limpar e adicionar de novo: {r['recolocado']}"

def test_seleciona_com_a_camera_atual_depois_de_orbitar_mover_e_aproximar(sel):
    exige("orbitar", "mover", "aproximar")
    r = caso("camera", limite=300)
    for nome, d in r["passos"].items():
        assert d["visiveis"] >= 2 and d["certos"] == d["visiveis"], f"{nome}: o centro de cada cubo visível deve acertar o seu objeto: {d}"
        assert sem_erros(d["varredura"], 1), f"{nome}: {d['varredura']}"
    assert len(r["passos"]["orbitar_x"]["moveram"]) >= 2 and not r["passos"]["orbitar_x"]["velho_ainda"], \
        f"a seleção usou uma câmera antiga (o pixel velho ainda acerta o cubo que já saiu dele): {r['passos']['orbitar_x']}"

@pytest.mark.parametrize("modo", ["unico", "ladrilhos"])  # unico = a grade de test_s04_cena (1 objeto, pior caso); ladrilhos = 576 objetos em xadrez
def test_um_milhao_de_triangulos_50_consultas_dentro_de_100_ms(sel, modo):
    r = caso("milhao", modo, limite=700)
    t = np.array(r["tempos"])
    assert r["tri"] >= 999_000 and r["copia"] and len(t) == 50, f"controle: cena de 1 milhão não montou / poucos pixels com geometria: {r['tri']} {r['copia']} {r['n_candidatos']}"
    print(f"SELECAO_1M {modo}: mediana {np.median(t):.2f} ms, p95 {np.percentile(t, 95):.2f} ms, maximo {t.max():.2f} ms, primeira {t[0]:.2f} ms "
          f"({'CI' if CI else 'maquina: p95 estrito'}; placa completa: {r['placa']})")
    assert all(h is not None for h, _ in r["hits"]), f"pixel sobre geometria devolveu None: {[x for x in r['hits'] if x[0] is None][:5]}"
    assert np.median(t) < 100 and t.max() < 250, f"régua do CI: mediana {np.median(t):.1f} ms, máximo {t.max():.1f} ms: {np.round(t, 1).tolist()}"
    assert CI or np.percentile(t, 95) < 100, f"p95 {np.percentile(t, 95):.1f} ms (meta: < 100 ms)"
    if modo == "unico":
        assert {h for h, _ in r["hits"]} == {"G" * 22}, r["hits"][:5]
    else:  # o ladrilho devolvido tem a cor do xadrez que a imagem mostra naquele pixel
        assert r["cor_ok"] == 50, f"{50 - r['cor_ok']} de 50 consultas devolveram um ladrilho de cor diferente da vista: {r['hits']}"

@pytest.mark.parametrize("modo", ["unico", "ladrilhos"])
def test_memoria_da_copia_compacta_com_um_milhao_de_triangulos_e_relatada(sel, modo):
    r = caso("milhao", modo, limite=700)  # a mesma cena do teste de tempo (cache da sessão)
    print(f"MEMORIA_COPIA {modo}: {r['bytes_por_tri']:.1f} bytes por triângulo (RSS {r['rss_mb'][0]:.0f} -> {r['rss_mb'][1]:.0f} MB, "
          f"{r['tri']} triângulos, cena na placa: {r['placa']}; chaves de memória em estatisticas(): {r['chaves']})")
    assert r["copia"] and 0 < r["bytes_por_tri"] < 200, f"memória acrescentada pela cena: {r['bytes_por_tri']:.1f} bytes/triângulo (limite folgado: 200)"

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o oráculo importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
