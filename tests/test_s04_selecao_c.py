# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de seleção: escala de tela, sincronia, caixas, plano `perto`, memória dos GlobalId (lacunas 7a a 7h).
Cada caso gráfico roda em SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1), como `test_s04_selecao.py`.
DECISÃO: `Cena.selecionar(x, y)` recebe pixels LÓGICOS (os do mouse do Qt) e converte por devicePixelRatio da janela; faixa válida = [0, largura/escala) x [0, altura/escala).
API DE TESTE (deve existir EXATAMENTE com este nome): `Cena.definir_escala_teste(r: float)`: passa a usar r (> 0) no lugar do devicePixelRatio real;
  pixel físico = lógico * r. Sem ela, os casos (a) com escala simulada PULAM (ou FALHAM com OBIM_S04_T10C_OBRIGATORIO=1). Os casos com QT_SCALE_FACTOR real
  (dpr de verdade, sem API de teste) e os casos (b) a (j) NÃO são guardados: falham até a funcionalidade ser implementada, e é isso o esperado hoje.
Regra de todos os casos de imagem: cada pixel CONFIANTE da captura (cor erodida) tem de selecionar o objeto daquela cor, e o fundo, None."""
import importlib.util, os, sys, threading, time  # noqa: E401
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from test_s04_cena import AMARELO, G, cent, com_guids, tres
from test_s04_selecao import MIL, eros, mascara, sel, um_objeto, varrer  # noqa: F401  (`sel`: fixture de guarda)
from test_s04_viewport import CORES, RAIZ, captura, cubo, esperar, lote, novo, quadros, rodar, um
from test_s04_viewport import caso as _caso

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
OBRIG = os.environ.get("OBIM_S04_T10C_OBRIGATORIO") == "1"
CI = bool(os.environ.get("CI"))
ESC = {"v": G(0), "g": G(1), "a": G(2)}

def exige_escala():
    import obimcore
    if not hasattr(obimcore.Cena, "definir_escala_teste"):
        (pytest.fail if OBRIG else pytest.skip)("\n!!! aguarda a cena: sem `definir_escala_teste` (escala simulada NÃO FOI EXECUTADA) !!!\n")

def ok(v, minimo=100, cores=3):  # varredura: nenhum pixel ruim; fundo e pelo menos `cores` classes com `minimo` pixels
    boas = [k for k, d in v.items() if k != "f" and d["n"] >= minimo]
    return all(d["ruins"] == 0 for d in v.values()) and v["f"]["n"] >= minimo and len(boas) >= cores

def varrer_r(c, a, esperado, r, passo=2, borda=2):  # como `varrer`, mas pergunta em coordenadas LÓGICAS: (pixel físico + 0,5) / r
    out = {}
    for k, guid in {**esperado, "f": None}.items():
        ys, xs = np.nonzero(eros(mascara(a, k), 3 if k == "f" else borda))
        pa = passo * 3 if k == "f" else passo
        s = (ys % pa == 0) & (xs % pa == 0)
        ruins = [(int(x), int(y)) for x, y in zip(xs[s], ys[s]) if c.selecionar((float(x) + 0.5) / r, (float(y) + 0.5) / r) != guid]
        out[k] = dict(n=int(s.sum()), ruins=len(ruins), ex=ruins[:4])
    return out

def espera(c, n):  # cena com n triângulos na placa e alguns quadros depois
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == n)
    yield 500

def erro_de(f, *a):
    try:
        return f"aceitou {f(*a)!r}"
    except ValueError:
        return "ValueError"
    except BaseException as ex:  # noqa: BLE001
        return "SUJO " + type(ex).__name__

# ---------- construções ----------
def fileira(n=41_700, passo=0.2):  # n objetos de DOIS cubos pequenos (y = -0,15 e +0,15) ao longo de +x: a caixa do objeto cobre o eixo, os triângulos não
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    tp, tn, ti = cubo((0, 0, 0), 1.0, 0)
    cen = np.zeros((n, 2, 3), np.float32)
    cen[:, :, 0], cen[:, 0, 1], cen[:, 1, 1] = (np.arange(n) * passo)[:, None], -0.15, 0.15
    ver = np.zeros((n, 2, 24), DTYPE_VERTICE)
    ver["pos"], ver["normal"], ver["cor"] = cen[:, :, None, :] + 0.05 * tp, tn, CORES[1]
    ind = (np.array(ti, np.uint32) + (24 * np.arange(2 * n, dtype=np.uint32)).reshape(n, 2)[:, :, None]).reshape(-1)
    p, o = ver["pos"].reshape(n, 48, 3), np.zeros(n, DTYPE_OBJETO)
    k = np.arange(n)
    o["id_step"], o["guid"], o["primeiro_indice"], o["n_indices"] = k + 1, [MIL(j).encode() for j in range(n)], k * 72, 72
    o["primeiro_vertice"], o["n_vertices"], o["caixa_min"], o["caixa_max"] = k * 48, 48, p.min(1), p.max(1)
    return LoteMalha(0, ver.reshape(-1), ind, o, np.zeros(3), n, n)

def com_caixa(l, mexe):  # tabela com caixas ERRADAS: mexe = {linha: (função do centro e da meia-diagonal -> (min, max))}
    o = l.objetos.copy()
    for j, f in mexe.items():
        c, h = (o["caixa_min"][j] + o["caixa_max"][j]) / 2, (o["caixa_max"][j] - o["caixa_min"][j]) / 2
        o["caixa_min"][j], o["caixa_max"][j] = f(c, h)
    return replace(l, objetos=o)

# ---------- casos ----------
def c_escala(res, modo):  # (a) o mesmo ponto lógico seleciona o mesmo objeto em qualquer escala; modo "teste": definir_escala_teste; "real": dpr do QT_SCALE_FACTOR
    c, w, cont = novo(0)
    c.adicionar_lote(tres())
    yield from espera(c, 36)
    a = captura(c)
    h, lg = a.shape[:2]
    res.update(tam=[lg, h], cls={k: int(mascara(a, k).sum()) for k in "vga"}, por_escala={})
    for r in ([1.0, 1.25, 1.5, 2.0] if modo == "teste" else [cont.devicePixelRatioF()]):
        modo == "teste" and c.definir_escala_teste(r)
        erros = {"alem_x": erro_de(c.selecionar, lg / r + 1.0, 10.0), "alem_y": erro_de(c.selecionar, 10.0, h / r + 1.0)}
        r > 1.1 and erros.update(fisico_alem=erro_de(c.selecionar, lg * 0.9, 10.0))  # pixel físico ainda dentro, lógico já fora
        res["por_escala"][str(r)] = dict(r=r, varredura=varrer_r(c, a, ESC, r), erros=erros, ultimo=erro_de(c.selecionar, (lg - 1.0) / r, (h - 1.0) / r))
    c.parar()

def c_desl(res):  # (b) deslocamento do lote diferente de zero: a seleção concorda com o desenho; outro deslocamento é recusado e a cena segue
    c, w, _ = novo(0)
    desl = np.array([1000.0, -2000.0, 30.0])
    c.adicionar_lote(replace(tres(), deslocamento=desl))
    yield from espera(c, 36)
    a = captura(c)
    res["cls"], res["v1"] = {k: int(mascara(a, k).sum()) for k in "vga"}, varrer(c, a, ESC, passo=2, bg=3, borda=1)
    c.adicionar_lote(replace(com_guids(lote(cubos=[((-4, 0, 6), 1.0, AMARELO)]), "Z" * 22), deslocamento=desl))  # mesmo deslocamento: entra
    yield from espera(c, 48)
    a = captura(c)
    ys, xs = np.nonzero(mascara(a, "y"))
    res["amarelo"] = [int(len(ys)), c.selecionar(float(xs.mean()) + 0.5, float(ys.mean()) + 0.5) if len(ys) else "sem pixels"]
    res["outro"] = erro_de(c.adicionar_lote, replace(um(0), deslocamento=np.zeros(3)))
    res["v2"] = varrer(c, a, {**ESC, "y": "Z" * 22}, passo=3, bg=3, borda=1)
    c.parar()

def c_sem_tabela(res):  # (c) lote vazio, lote sem tabela de objetos (tapa, mas não é selecionável) e objeto da tabela sem geometria
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    c, w, _ = novo(0)
    yield from esperar(lambda: len(quadros(c)) > 5)
    res["vazia"] = erro_de(c.selecionar, 10.0, 10.0)
    c.adicionar_lote(LoteMalha(0, np.zeros(0, DTYPE_VERTICE), np.zeros(0, np.uint32), np.zeros(0, DTYPE_OBJETO), np.zeros(3), 0, 0))
    yield 300
    res["so_vazio"] = erro_de(c.selecionar, 10.0, 10.0)
    c.adicionar_lote(com_guids(lote(cubos=[((0, 3, 0.5), 1.5, CORES[1])]), G(1)))  # verde atrás, com tabela
    yield from espera(c, 12)
    verde_so = eros(mascara(captura(c), "g"), 2)
    c.adicionar_lote(replace(lote(cubos=[((0.4, -3, 0), 1.5, CORES[0])]), objetos=np.zeros(0, DTYPE_OBJETO)))  # vermelho NA FRENTE, sem tabela
    yield from espera(c, 24)
    a = captura(c)
    sobre = verde_so & eros(mascara(a, "v"), 2)
    ys, xs = np.nonzero(sobre)
    res["n_sobre"], res["sobre"] = int(sobre.sum()), sorted({str(c.selecionar(float(x) + 0.5, float(y) + 0.5)) for x, y in zip(xs[::3], ys[::3])})
    res["v1"] = varrer(c, a, {"v": None, "g": G(1)}, passo=3)
    l = lote(cubos=[((4, 0, 0), 1.0, CORES[2])])  # azul com tabela de DUAS linhas: a segunda é um objeto sem geometria
    o = np.zeros(2, DTYPE_OBJETO)
    o[0], o[1] = (1, b"A" * 22, 0, 36, 0, 24, *l.vertices["pos"][:24].min(0)[None], *l.vertices["pos"][:24].max(0)[None]), (2, b"E" * 22, 0, 0, 0, 0, np.zeros(3), np.zeros(3))
    c.adicionar_lote(replace(l, objetos=o))
    yield from espera(c, 36)
    c.atualizar(None, ["E" * 22])  # remover o objeto sem geometria não derruba nada
    yield from espera(c, 36)
    a = captura(c)
    res["azul"], res["v2"] = int(eros(mascara(a, "a"), 2).sum()), varrer(c, a, {"v": None, "g": G(1), "a": "A" * 22}, passo=3)
    res["viva"] = c.viva()
    c.parar()

def c_fileira(res):  # (d) o raio atravessa ~41 700 caixas (1 milhão de triângulos) sem tocar triângulo; depois acerta um cubo no fim da fila
    c, w, _ = novo(0, dict(alvo=(0.0, 0.0, 0.0), distancia=8400.0, azimute=0.0, elevacao=0.0))  # câmera em x = 8400, olhando para -x ao longo da fileira
    yield from esperar(lambda: len(quadros(c)) > 5)
    g = fileira()
    tri = res["tri"] = len(g.indices) // 3
    c.adicionar_lote(g)
    res["copia"] = yield from esperar(lambda: c.estatisticas()["triangulos"] == tri, 90000)
    yield 1000
    h, lg = captura(c).shape[:2]  # só para saber o tamanho: o pixel do centro dá o raio exato ao longo do eixo
    cx, cy = lg / 2, h / 2
    medir = lambda: [(time.perf_counter(), c.selecionar(cx, cy), time.perf_counter()) for _ in range(15)]  # noqa: E731
    c.selecionar(cx, cy)  # aquece
    m = medir()
    res["vazio"] = [(m_[2] - m_[0]) * 1000 for m_ in m]
    res["hit_vazio"] = sorted({str(m_[1]) for m_ in m})
    c.adicionar_lote(com_guids(lote(cubos=[((-5.0, 0, 0), 1.0, CORES[0])]), "T" * 22))
    yield from esperar(lambda: c.estatisticas()["triangulos"] == tri + 12, 20000)
    m = medir()
    res["fim"], res["hit_fim"] = [(m_[2] - m_[0]) * 1000 for m_ in m], sorted({str(m_[1]) for m_ in m})
    c.parar()

def c_antes_do_quadro(res):  # (e) antes do primeiro quadro apresentado, e sem iniciar, selecionar levanta ValueError; depois funciona
    import obimcore
    c, w, _ = novo(0)
    res["logo"] = erro_de(c.selecionar, 10.0, 10.0)  # a janela acabou de ser mostrada: o laço de eventos ainda não rodou
    c.adicionar_lote(tres())
    res["logo_com_lote"] = erro_de(c.selecionar, 10.0, 10.0)
    outra = obimcore.Cena(True)  # nunca iniciada
    res["nunca_iniciada"] = erro_de(outra.selecionar, 1.0, 1.0)
    yield from espera(c, 36)
    res["depois"] = erro_de(c.selecionar, 10.0, 10.0)
    c.parar()

def c_redim(res):  # (f) redimensionar (e orbitar junto): câmera e tamanho andam juntos; depois de assentar, a seleção é a da imagem capturada
    c, w, cont = novo(0)
    c.adicionar_lote(tres())
    yield from espera(c, 36)
    res["etapas"] = []
    for tam, ent in (((900, 300), (240, 0)), ((330, 700), (0, 30)), ((640, 640), (60, -20)), ((480, 400), (0, 0))):
        w.resize(*tam)
        ent != (0, 0) and c.orbitar(*ent)
        durante = []
        for i in range(12):  # tempestade: consultas enquanto o tamanho e a câmera mudam
            yield 12
            durante.append(erro_de(c.selecionar, 30.0 + i, 30.0))
        yield 900
        a = captura(c)
        e = dict(tam=list(a.shape[:2]), cont=[cont.width(), cont.height()], dpr=cont.devicePixelRatioF(), durante=sorted(set(durante)))
        e["varredura"] = varrer(c, a, ESC, passo=4, bg=3, borda=2)
        res["etapas"].append(e)
    c.parar()

def c_threads(res):  # (g) selecionar em outra thread enquanto o laço principal troca objetos (atualizar) e esvazia a cena (limpar)
    c, w, _ = novo(0)
    yield from esperar(lambda: len(quadros(c)) > 5)
    a = captura(c)
    px, log, parar = (a.shape[1] / 2, a.shape[0] / 2), [], threading.Event()
    def laco():
        while not parar.is_set():
            t0 = time.perf_counter()
            try:
                r = c.selecionar(*px)
            except BaseException as ex:  # noqa: BLE001
                r = "ERRO " + repr(ex)
            log.append((t0, time.perf_counter(), r))
    gs = [MIL(k) for k in range(80)]
    cubo_g = lambda k: com_guids(lote(cubos=[((0, 0, 0), 1.0, CORES[k % 3])]), gs[k])  # noqa: E731
    th = threading.Thread(target=laco, daemon=True)
    th.start()
    c.adicionar_lote(cubo_g(0))
    marcas = [(time.perf_counter(), gs[0])]
    yield 100
    for k in range(1, 60):  # troca o objeto (mesmo lugar, outro GlobalId); o antigo some na mesma operação
        c.atualizar(cubo_g(k), [gs[k - 1]])
        marcas.append((time.perf_counter(), gs[k]))
        yield 15
    c.limpar()  # a rodada seguinte parte da cena vazia (dois objetos no mesmo lugar seriam ambíguos)
    yield 150
    fases = []
    for k in range(60, 80):
        c.adicionar_lote(cubo_g(k))
        add = time.perf_counter()
        yield 40
        ini = time.perf_counter()
        c.limpar()
        ret = time.perf_counter()
        yield 120
        fases.append((add, ini, ret, time.perf_counter(), gs[k]))
    parar.set()
    th.join(10)
    res["travou"], res["n"], res["viva"] = th.is_alive(), len(log), c.viva()
    res["erros"] = sorted({str(r) for *_, r in log if isinstance(r, str) and r.startswith("ERRO")})
    ruins = []
    for t0, t1, r in log:  # troca: depois que `atualizar` k voltou, o resultado é gs[k] (ou gs[k+1] se a próxima já estava em curso)
        ks = [i for i, (t, _) in enumerate(marcas) if t <= t0]
        if ks and t0 < marcas[-1][0] and r not in {gs[ks[-1]], gs[ks[-1] + 1]}:
            ruins.append(("troca", ks[-1], r))
    for i, (add, ini, ret, fim, g) in enumerate(fases):  # RG-27: julga a chamada INTEIRA (t0 a t1), como "sumiu"
        prox = fases[i + 1][4] if i + 1 < len(fases) else None  # o objeto k+1 só existe depois de `fim` (gravado antes de adicioná-lo)
        ruins += [("removido", g, r) for t0, t1, r in log if ret < t0 < fim and r is not None and not (r == prox and t1 > fim)]  # depois de limpar() voltar: None (ou k+1, se a chamada passou de `fim`)
        ruins += [("sumiu", g, r) for t0, t1, r in log if add < t0 and t1 < ini and r != g]  # antes de limpar: o objeto adicionado
    res["ruins"], res["n_apos_limpar"] = ruins[:6], sum(1 for *_, ret, fim, _g in fases for t0, t1, _ in log if ret < t0 and t1 < fim)  # só chamadas que TÊM de dar None
    c.parar()

def c_caixas(res):  # (h) a tabela mente (caixa menor, deslocada); vale a caixa dos triângulos, no preparar e depois de atualizar (sem)
    c, w, _ = novo(0)
    c.adicionar_lote(com_caixa(tres(), {0: lambda c_, h: (c_ - 0.05, c_ + 0.05), 1: lambda c_, h: (c_ + 100 - h, c_ + 100 + h)}))
    yield from espera(c, 36)
    a = captura(c)
    res["v1"] = varrer(c, a, ESC, passo=2, bg=3, borda=1)
    c.atualizar(None, [G(2)])  # remove o azul: o lote é refeito (`sem`) e as caixas dos que ficam têm de continuar certas
    yield from esperar(lambda: c.estatisticas()["triangulos"] == 24)
    yield 700
    a = captura(c)
    res["n_azul"], res["v2"] = int(mascara(a, "a").sum()), varrer(c, a, {"v": G(0), "g": G(1)}, passo=2, bg=3, borda=1)
    c.parar()

def c_perto(res):  # (i) cubinho entre a câmera e o plano `perto` não é desenhado e não pode ser selecionado; o cubo grande atrás sim
    c, w, _ = novo(0, dict(alvo=(0.0, 0.0, 0.0), distancia=3000.0, azimute=-90.0, elevacao=0.0))
    c.adicionar_lote(com_guids(lote(cubos=[((0, 0, 0), 500.0, CORES[1])]), G(1)))
    c.adicionar_lote(com_guids(lote(cubos=[((0, -3000.0 + 0.2, 0), 0.03, CORES[0])]), "N" * 22))  # t entre 0,17 e 0,23 do olho
    yield from espera(c, 24)
    a = captura(c)
    h, lg = a.shape[:2]
    cam = c.camera()
    pos_y = -float(cam["distancia"])
    mn, mx = np.array([-500, -3000.0 + 0.17, -500]), np.array([500, 500.0, 500])  # caixa da cena (só o y interessa para o `perto`)
    centro, raio = (mn + mx) / 2, np.linalg.norm(mx - mn) / 2
    longe = (np.linalg.norm(np.array([0.0, pos_y, 0.0]) - centro) + raio) * 1.1  # mesma conta do viewport.cpp
    res.update(perto=max(longe / 10000, 0.05), t_max=0.2 + 0.03 + (3000 - float(cam["distancia"])), cam=float(cam["distancia"]),
               pixel=a[h // 2, lg // 2].tolist(), verde=int(mascara(a, "g").sum()), vermelho=int(mascara(a, "v").sum()))
    res["centro"], res["em_volta"] = c.selecionar(lg / 2, h / 2), sorted({str(c.selecionar(lg / 2 + dx, h / 2 + dy)) for dx in (-3, 0, 3) for dy in (-3, 0, 3)})
    c.parar()

def c_bytes(res):  # (j) bytes_copia conta o texto dos GlobalId: o mesmo modelo com GlobalId de 22 caracteres pesa >= 20 B/objeto a mais
    c, w, _ = novo(0)
    n = 3000
    base = lote(cubos=[((j % 50 * 3, -100 - j // 50 * 3, 0), 1.0, CORES[0]) for j in range(n)])
    def com(nomes):
        o = base.objetos.copy()
        o["guid"] = [x.encode() for x in nomes]
        return replace(base, objetos=o)
    c.adicionar_lote(com([str(j) for j in range(n)]))  # curtos (cabem no texto embutido do std::string)
    res["curto"] = c.estatisticas()["bytes_copia"]
    c.limpar()
    c.adicionar_lote(com([MIL(j) for j in range(n)]))
    res["longo"], res["n"] = c.estatisticas()["bytes_copia"], n
    c.parar()
    yield 0

# ---------- testes ----------
@pytest.mark.parametrize("r", ["1.0", "1.25", "1.5", "2.0"])
def test_mesmo_ponto_logico_seleciona_o_mesmo_objeto_em_escala_simulada(sel, r):
    exige_escala()
    d = caso("escala", "teste", limite=300)
    e = d["por_escala"][r]
    assert all(d["cls"][k] >= 500 for k in "vga"), f"controle: a cena deveria mostrar os 3 cubos: {d['cls']}"
    assert ok(e["varredura"], 100), f"escala {r}: pixel lógico (físico/{r}) selecionou o objeto errado: {e['varredura']}"
    assert all(v == "ValueError" for v in e["erros"].values()), f"escala {r}: a faixa válida é a LÓGICA: {e['erros']}"
    assert e["ultimo"] != "ValueError", f"escala {r}: o último pixel lógico válido foi recusado: {e['ultimo']}"

@pytest.mark.parametrize("fator", ["1.25", "1.5", "2"])  # devicePixelRatio de verdade (QT_SCALE_FACTOR), sem API de teste; mouse do Qt = pixels lógicos
def test_com_devicepixelratio_real_o_clique_logico_acerta_o_objeto(sel, fator):
    d = caso("escala", "real", limite=300, extra=[("QT_SCALE_FACTOR", fator)])
    (e,) = d["por_escala"].values()
    assert abs(e["r"] - float(fator)) < 1e-6 and all(d["cls"][k] >= 300 for k in "vga"), f"controle: dpr {e['r']}, cubos {d['cls']}"
    assert ok(e["varredura"], 100), f"dpr {fator}: o clique em pixels lógicos selecionou o objeto errado (a imagem está em pixels físicos): {e['varredura']}"
    assert all(v == "ValueError" for v in e["erros"].values()), e["erros"]

def test_deslocamento_de_lote_diferente_de_zero_concorda_com_o_desenho(sel):
    r = caso("desl", limite=300)
    assert all(r["cls"][k] >= 500 for k in "vga"), r["cls"]
    assert ok(r["v1"], 200), f"com deslocamento (1000, -2000, 30) a seleção deixou de concordar com a imagem: {r['v1']}"
    assert r["amarelo"][0] >= 300 and r["amarelo"][1] == "Z" * 22, f"segundo lote com o mesmo deslocamento: {r['amarelo']}"
    assert r["outro"] == "ValueError", f"lote com outro deslocamento deve ser recusado: {r['outro']}"
    assert ok(r["v2"], 90, 4), f"depois de recusar o lote, a cena segue certa: {r['v2']}"

def test_lote_sem_tabela_e_objeto_sem_geometria(sel):
    r = caso("sem_tabela", limite=300)
    assert r["vazia"] == "aceitou None" and r["so_vazio"] == "aceitou None", f"cena vazia / lote vazio: {r['vazia']} {r['so_vazio']}"
    assert r["n_sobre"] >= 200, f"controle: o vermelho deveria tapar parte do verde: {r['n_sobre']}"
    assert r["sobre"] == ["None"], f"o mais perto é geometria SEM objeto (tapa, mas não é selecionável): {r['sobre']}"
    assert ok(r["v1"], 100, 2), f"vermelho sem tabela -> None; verde com tabela -> verde: {r['v1']}"
    assert r["viva"] and r["azul"] >= 300 and ok(r["v2"], 100), f"objeto da tabela sem geometria quebrou a cena ou a seleção: {r['v2']}"

def test_raio_que_cruza_41_mil_caixas_sem_tocar_triangulo_dentro_de_100_ms(sel):
    r = caso("fileira", limite=700)
    assert r["tri"] >= 1_000_000 and r["copia"], f"controle: a cena de 1 milhão de triângulos não montou: {r['tri']} {r['copia']}"
    assert r["hit_vazio"] == ["None"] and r["hit_fim"] == ["T" * 22], f"o raio passa entre os cubinhos de cada objeto e acerta o cubo do fim: {r['hit_vazio']} {r['hit_fim']}"
    for k, nome in (("vazio", "só caixas"), ("fim", "caixas e depois o acerto")):
        t = np.array(r[k])
        print(f"RAIO_FILEIRA {nome}: mediana {np.median(t):.2f} ms, p95 {np.percentile(t, 95):.2f} ms, máximo {t.max():.2f} ms ({'CI' if CI else 'máquina'})")
        assert np.median(t) < 100 and t.max() < 250, f"{nome}: mediana {np.median(t):.1f} ms, máximo {t.max():.1f} ms: {np.round(t, 1).tolist()}"
        assert CI or np.percentile(t, 95) < 100, f"{nome}: p95 {np.percentile(t, 95):.1f} ms"

def test_antes_do_primeiro_quadro_levanta_valueerror(sel):
    r = caso("antes_do_quadro", limite=200)
    assert r["logo"] == r["logo_com_lote"] == r["nunca_iniciada"] == "ValueError", f"sem quadro apresentado não há tamanho: {r}"
    assert r["depois"] == "aceitou None", f"depois do primeiro quadro (pixel de fundo) deve devolver None: {r['depois']}"

def test_depois_de_redimensionar_a_selecao_concorda_com_a_imagem_capturada(sel):
    r = caso("redim", limite=400)
    assert len(r["etapas"]) == 4
    for e in r["etapas"]:
        assert abs(e["tam"][1] - round(e["cont"][0] * e["dpr"])) <= 2 and abs(e["tam"][0] - round(e["cont"][1] * e["dpr"])) <= 2, f"controle: captura x contêiner: {e}"
        assert set(e["durante"]) <= {"ValueError", "aceitou None"} | {f"aceitou '{G(i)}'" for i in range(3)}, f"durante o redimensionamento: {e['durante']}"
        assert ok(e["varredura"], 50, 2), f"depois de redimensionar para {e['tam']} a seleção usou câmera e tamanho de quadros diferentes: {e['varredura']}"

def test_selecionar_em_outra_thread_durante_atualizar_e_limpar(sel):
    r = caso("threads", limite=300)
    assert r["viva"] and not r["travou"] and not r["erros"], f"travou, caiu ou levantou exceção: {r}"
    assert r["n"] >= 300 and r["n_apos_limpar"] >= 20, f"controle: poucas consultas concorrentes ({r['n']}, {r['n_apos_limpar']} depois de limpar)"
    assert not r["ruins"], f"objeto removido devolvido (troca/limpar) ou objeto presente não devolvido: {r['ruins']}"

def test_caixa_da_tabela_errada_nao_esconde_o_objeto(sel):
    r = caso("caixas", limite=300)
    assert ok(r["v1"], 200), f"caixa da tabela menor/deslocada: o objeto tem de ser achado pela caixa dos triângulos (preparar): {r['v1']}"
    assert r["n_azul"] < 20 and ok(r["v2"], 200, 2), f"depois de atualizar (sem) a caixa dos que ficaram continua errada: {r['v2']}"

def test_geometria_entre_a_camera_e_o_plano_perto_nao_e_selecionavel(sel):
    r = caso("perto", limite=300)
    assert r["t_max"] < 0.8 * r["perto"], f"controle: o cubinho deveria estar inteiro antes do plano perto ({r['t_max']:.2f} x {r['perto']:.2f})"
    assert r["pixel"][1] > 150 and r["pixel"][0] < 100 and r["verde"] >= 5000, f"controle: o desenho recorta o cubinho e mostra o cubo grande: {r}"
    assert r["centro"] == G(1) and r["em_volta"] == [f"{G(1)}"], f"o raio deve começar em t = perto (como o desenho): {r['centro']} {r['em_volta']}"

def test_bytes_da_copia_inclui_o_texto_dos_globalid(sel):
    r = caso("bytes", limite=200)
    extra = (r["longo"] - r["curto"]) / r["n"]
    print(f"BYTES_GUID: curto {r['curto']} B, longo {r['longo']} B, diferença {extra:.1f} B por objeto (esperado >= 20)")
    assert r["curto"] > 0 and extra >= 20, f"bytes_copia não cresce com o tamanho dos GlobalId: {extra:.1f} B/objeto"

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o teste importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
