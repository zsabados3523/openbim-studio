# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes da cena (limpeza, câmera, animação e substituição de malhas).
Reaproveita os auxiliares de `test_s04_viewport.py`/`test_s04_viewport_b.py` e roda cada caso em subprocesso sob `xvfb-run`.
Casos de limpeza (valem hoje): (a) limpar() durante a subida da grade de 1 milhão, 8 vezes, pausas variadas; (b) fatias_enviadas parado com a cena estável;
(c) Cena.objetos(seq): vetores 1D, guid, caixa NaN sem geometria, ValueError (limpar, sequência desconhecida, faixa fora do lote).
Casos de câmera e substituição (GUARDA: pula enquanto faltar algum método de METODOS_T09; FALHA com OBIM_S04_T09_OBRIGATORIO=1). API ESPERADA (nomes em português; o
implementador segue estas assinaturas e convenções; tudo é chamado da thread da janela, só enfileira e volta logo; a thread de desenho aplica):
 * Cena.orbitar(dx: float, dy: float) -> None   dx, dy em PIXELS do mouse (dx > 0 = arrastou para a direita). 0,5 grau por pixel, exato:
     azimute -= 0,5*dx; elevacao = clamp(elevacao + 0,5*dy, -89, 89). Entradas somadas na ordem; nenhuma se perde (200 chamadas = 200 aplicadas).
 * Cena.mover(dx: float, dy: float) -> None     pan em pixels: o modelo anda JUNTO com o mouse (dx > 0: conteúdo vai para a direita na imagem;
     dy > 0: vai para baixo). No plano do alvo, 1 pixel do mouse = 1 pixel da imagem (±25%). Muda `alvo`, não muda distancia/azimute/elevacao.
 * Cena.aproximar(fator: float) -> None         fator > 1 aproxima: distancia = distancia / fator (fator <= 0: ValueError).
 * Cena.enquadrar() -> None                      alvo = centro da caixa da cena (todos os lotes), distancia tal que a caixa cabe na imagem
     com folga; azimute e elevacao ficam como estão.
 * Cena.camera() -> dict(alvo, distancia, azimute, elevacao)   (já existe) devolve o estado JÁ APLICADO pela thread de desenho.
 * Cena.definir_camera(...)                      (já existe) continua valendo; Z para cima, graus, posição = alvo + distancia*(cos e cos a, cos e sin a, sin e).
 * Cena.animar_orbita(graus_por_s: float) -> None  azimute += graus_por_s * (tempo real decorrido), por relógio (não por quadro); o sinal manda
     no sentido. Parar: Cena.parar_animacao() -> None (a câmera para NA HORA e não anda mais). Não mexe em alvo/distancia/elevacao.
 * Cena.atualizar(lote_novo: LoteMalha | None, guids_remover: list[str]) -> int   troca/remove malhas por GlobalId (objeto.guid, 22 chars):
     (1) remove da cena, em todos os lotes, os objetos cujo guid está em guids_remover OU em lote_novo.objetos; (2) acrescenta lote_novo (se não None);
     devolve a sequência, ESTRITAMENTE maior que qualquer devolvida antes (adicionar_lote ou atualizar), mesmo se nada mudou (guid inexistente).
     Dado errado: TypeError/ValueError e a cena fica intacta. estatisticas()["triangulos"] e ["triangulos_na_placa"] contam só o que ficou.
     perder_contexto() recompõe a placa SEM os removidos.
 * Cena.objetos(seq) ganha a chave "deslocamento" (float64, 3 números = LoteMalha.deslocamento do lote). Um lote com deslocamento diferente
     do primeiro: ValueError (cena intacta) OU aceito (então objetos() devolve o deslocamento do lote, ou o do primeiro se o C++ refez os vértices).
Montar os dtypes uma vez (achado 10) não é testável: ignorado."""
import importlib, os, sys, time  # noqa: E401
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from test_s04_viewport import (CAM, CORES, FUNDO, RAIZ, agora, caso as _caso, captura, classificar, esperar, lote, novo, quadros,  # noqa: F401
                               rodar, um, viewport)
from test_s04_viewport_b import grade

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
METODOS_T09 = ("orbitar", "mover", "aproximar", "enquadrar", "animar_orbita", "parar_animacao", "atualizar")
AMARELO, G = (240, 220, 30, 255), lambda j: f"{j:022d}"  # noqa: E731
tres = lambda z=0: lote(cubos=[((-4, 0, z), 1.0, CORES[0]), ((0, 0, 0), 1.0, CORES[1]), ((4, 0, 0), 1.0, CORES[2])])  # noqa: E731

def exige_t09():
    import obimcore
    faltam = [m for m in METODOS_T09 if not hasattr(obimcore.Cena, m)]
    if faltam:
        (pytest.fail if os.environ.get("OBIM_S04_T09_OBRIGATORIO") == "1" else pytest.skip)(
            f"\n!!! aguarda a cena: sem {faltam} (camera/orbita/atualizar NÃO FORAM EXECUTADOS) !!!\n")

def com_guids(l, *g):
    o = l.objetos.copy()
    o["guid"] = [x.encode() for x in g]
    return replace(l, objetos=o)

def cent(a, k):  # (pixels, x médio, y médio) da cor v/g/a (mesma regra de `classificar`)
    r, g, b = (a[..., i].astype(int) for i in range(3))
    x, y, z = {"v": (r, g, b), "g": (g, r, b), "a": (b, r, g)}[k]
    m = (x >= 60) & (x > 1.8 * y) & (x > 1.8 * z)
    return (int(m.sum()), float(np.nonzero(m)[1].mean()), float(np.nonzero(m)[0].mean())) if m.any() else (0, -1.0, -1.0)

def amarelo(a):
    return int(((a[..., 0] > 200) & (a[..., 1] > 180) & (a[..., 2] < 80)).sum())

def pos(c):
    d = c.camera()
    return dict(alvo=[float(x) for x in d["alvo"]], dist=float(d["distancia"]), az=float(d["azimute"]), el=float(d["elevacao"]))

def estavel(c, ms=450):  # deixa a thread de desenho aplicar e apresentar
    yield ms
    return pos(c)

# ===================== casos que valem hoje =====================
def c_limpar_corrida(res):
    c, w, _ = novo(0)
    yield 1000
    g, res["finais"] = grade(707), []
    for p in (0, 2, 5, 11, 23, 47, 95, 190):  # pausas variadas entre o início da subida e o limpar()
        c.adicionar_lote(g)
        time.sleep(p / 1000)
        c.limpar()
        yield 30
    c.limpar()
    res["zero"] = yield from esperar(lambda: c.estatisticas()["triangulos"] == 0 and c.estatisticas()["triangulos_na_placa"] == 0, 15000)
    c.adicionar_lote(um(0))
    res["ok"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12, 15000)
    for _ in range(10):  # estável por 500 ms
        res["finais"].append([c.estatisticas()["triangulos_na_placa"], c.estatisticas()["triangulos"]])
        yield 50
    yield 300
    a = captura(c)
    res.update(verde=cent(a, "g")[0], vermelho=cent(a, "v")[0], viva=c.viva())
    c.parar()

def c_fatias_paradas(res):
    c, w, _ = novo(0)
    c.adicionar_lote(lote())
    res["ok"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 7200)
    yield 500
    res["f"] = []
    for _ in range(6):  # 1,5 s de cena estável
        res["f"].append(c.estatisticas()["fatias_enviadas"])
        yield 250
    res["f"].append(c.estatisticas()["fatias_enviadas"])
    res["quadros"] = len(quadros(c, agora() - 1500))
    c.parar()

def c_objetos(res):
    from viewport_qrhi.carregador import DTYPE_OBJETO
    c, w, _ = novo(0)
    b = tres()
    extra = np.zeros(2, DTYPE_OBJETO)
    extra[0], extra[1] = (77, b"S" * 22, 0, 0, 0, 0, np.zeros(3), np.zeros(3)), (78, b"T" * 22, 0, 36, 0, 0, np.zeros(3), np.zeros(3))
    ob = np.concatenate([b.objetos, extra])  # 3 com geometria; 77 sem índices; 78 com índices mas sem vértices
    seq = c.adicionar_lote(replace(b, objetos=ob))
    d, res["tipos"] = c.objetos(seq), {}
    for k, v in d.items():
        res["tipos"][k] = [type(v).__name__, getattr(v, "ndim", None), str(getattr(v, "dtype", "")), list(getattr(v, "shape", []))]
    res["guid"] = list(d["guid"])
    res["id"], res["pi"], res["ni"], res["pv"], res["nv"] = (d[k].tolist() for k in ("id_step", "primeiro_indice", "n_indices", "primeiro_vertice", "n_vertices"))
    res["caixa"] = np.where(np.isnan(d["caixa"]), -9999.0, d["caixa"]).tolist()
    res["esperado"] = [[*map(float, o["caixa_min"]), *map(float, o["caixa_max"])] for o in ob[:3]]
    res["guid_esperado"] = [o["guid"].decode() for o in ob]
    res["id_esperado"], res["pi_esperado"] = ob["id_step"].tolist(), ob["primeiro_indice"].tolist()
    vazio = c.adicionar_lote(replace(b, objetos=np.zeros(0, DTYPE_OBJETO)))  # tabela vazia
    res["vazio"] = [len(c.objetos(vazio)["guid"]), list(c.objetos(vazio)["caixa"].shape)]
    erros, st0 = {}, c.estatisticas()["lotes"]
    fora = ob.copy()
    fora[1]["n_indices"] = len(b.indices)  # primeiro_indice 36 + n_indices > nº de índices
    fora2 = ob.copy()
    fora2[2]["n_vertices"] = len(b.vertices) + 1
    for k, x in {"faixa de indices": fora, "faixa de vertices": fora2}.items():
        try:
            c.adicionar_lote(replace(b, objetos=x))
            erros[k] = "aceitou"
        except ValueError:
            erros[k] = "ValueError"
        except BaseException as ex:  # noqa: BLE001
            erros[k] = "SUJO " + type(ex).__name__
    for k, q in (("seq desconhecida", seq + 1000), ("seq zero", 0)):
        try:
            c.objetos(q)
            erros[k] = "aceitou"
        except ValueError:
            erros[k] = "ValueError"
        except BaseException as ex:  # noqa: BLE001
            erros[k] = "SUJO " + type(ex).__name__
    res["lotes_igual"] = c.estatisticas()["lotes"] == st0
    c.limpar()
    yield 200
    try:
        c.objetos(seq)
        erros["depois de limpar"] = "aceitou"
    except ValueError:
        erros["depois de limpar"] = "ValueError"
    except BaseException as ex:  # noqa: BLE001
        erros["depois de limpar"] = "SUJO " + type(ex).__name__
    res["erros"], res["viva"] = erros, c.viva()
    c.parar()

def test_limpar_no_meio_da_subida_da_grade_de_um_milhao_oito_vezes(viewport):
    r = caso("limpar_corrida", limite=400)
    assert r["viva"] and r["zero"] and r["ok"], r
    assert all(f == [12, 12] for f in r["finais"]), f"depois de limpar+um(0) a placa não ficou em 12 por 500 ms: {r['finais']}"
    assert r["verde"] < 20 and r["vermelho"] >= 20, f"geometria antiga (grade verde) ainda desenhada: verde {r['verde']}, vermelho {r['vermelho']}"

def test_fatias_enviadas_nao_cresce_com_a_cena_estavel(viewport):
    r = caso("fatias_paradas")
    assert r["ok"] and r["f"][0] >= 1 and r["quadros"] >= 20, r
    assert len(set(r["f"])) == 1, f"fatias_enviadas continuou crescendo com a cena parada: {r['f']}"

def test_objetos_tabela_do_lote(viewport):
    r = caso("objetos")
    assert r["viva"] and r["guid"] == r["guid_esperado"] and all(isinstance(g, str) for g in r["guid"]), r["guid"]
    for k, dt in (("id_step", "int32"), ("primeiro_indice", "uint32"), ("n_indices", "uint32"), ("primeiro_vertice", "uint32"), ("n_vertices", "uint32")):
        assert r["tipos"][k][1:3] == [1, dt], f"{k}: esperado vetor 1D {dt}, veio {r['tipos'][k]}"
    assert r["tipos"]["caixa"][1:] == [2, "float32", [5, 6]], r["tipos"]["caixa"]
    assert r["id"] == r["id_esperado"] and r["pi"] == r["pi_esperado"] and r["ni"] == [36, 36, 36, 0, 36] and r["nv"] == [24, 24, 24, 0, 0], r
    assert np.allclose(r["caixa"][:3], r["esperado"], atol=1e-6), r["caixa"]
    assert r["caixa"][3] == r["caixa"][4] == [-9999.0] * 6, f"objeto sem geometria deve ter caixa NaN (nunca zeros): {r['caixa'][3:]}"
    assert r["vazio"] == [0, [0, 6]], r["vazio"]
    assert r["erros"] == {"faixa de indices": "ValueError", "faixa de vertices": "ValueError", "seq desconhecida": "ValueError", "seq zero": "ValueError",
                          "depois de limpar": "ValueError"} and r["lotes_igual"], r["erros"]

# ===================== câmera, animação, substituição (guardados) =====================
def c_camera(res):
    c, w, _ = novo(0)
    c.adicionar_lote(tres(3))  # vermelho 3 m acima (Z para cima: aparece mais alto na imagem)
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 36)
    yield 500
    p0, a0 = pos(c), captura(c)
    res["base"] = dict(p0, v=cent(a0, "v"), g=cent(a0, "g"), a=cent(a0, "a"))
    def pedir(f, *args):  # aplica e espera a câmera mudar (ou 3 s)
        antes = pos(c)
        f(*args)
        yield from esperar(lambda: pos(c) != antes, 3000)
        return (yield from estavel(c))
    def volta():
        c.definir_camera(**CAM)
        yield from esperar(lambda: pos(c)["az"] == CAM["azimute"] and pos(c)["el"] == CAM["elevacao"], 3000)
        yield 300
    res["orb_x"] = yield from pedir(c.orbitar, 40, 0)
    res["orb_y"] = yield from pedir(c.orbitar, 0, 20)
    res["orb_alto"] = yield from pedir(c.orbitar, 0, 1000)
    res["orb_baixo"] = yield from pedir(c.orbitar, 0, -3000)
    yield from volta()
    res["mov_x"] = yield from pedir(c.mover, 40, 0)
    res["mov_x_g"] = cent(captura(c), "g")
    yield from volta()
    res["mov_y"] = yield from pedir(c.mover, 0, 30)
    res["mov_y_g"] = cent(captura(c), "g")
    yield from volta()
    res["apr2"] = yield from pedir(c.aproximar, 2.0)
    res["apr2_g"] = cent(captura(c), "g")[0]
    yield from volta()
    res["apr_meio"] = yield from pedir(c.aproximar, 0.5)
    res["apr_meio_g"] = cent(captura(c), "g")[0]
    try:
        c.aproximar(0.0)
        res["apr_zero"] = "aceitou"
    except ValueError:
        res["apr_zero"] = "ValueError"
    c.definir_camera(alvo=(30.0, 10.0, 5.0), distancia=100.0, azimute=-60.0, elevacao=25.0)
    yield from esperar(lambda: pos(c)["dist"] == 100.0, 3000)
    yield 300
    res["longe_g"] = cent(captura(c), "g")[0]
    res["enq"] = yield from pedir(c.enquadrar)
    a = captura(c)
    res["enq_cls"] = classificar(a)
    nf = np.abs(a[..., :3].astype(int) - np.array(FUNDO)).max(-1) > 25
    res["enq_borda"] = int(nf[:2].sum() + nf[-2:].sum() + nf[:, :2].sum() + nf[:, -2:].sum())
    res["enq_larg"] = float(np.ptp(np.nonzero(nf.any(0))[0]) + 1) / a.shape[1]
    yield from volta()
    t0, antes = time.perf_counter(), pos(c)
    for _ in range(200):
        c.orbitar(1, 0)
    res["fila_ms"], res["fila_az0"] = (time.perf_counter() - t0) * 1000, antes["az"]  # só enfileira: não bloqueia
    yield from esperar(lambda: abs(pos(c)["az"] - (antes["az"] - 100.0)) < 1e-6, 4000)
    res["fila_az"] = pos(c)["az"]
    c.parar()

def test_camera_orbitar_mover_aproximar_enquadrar(viewport):
    exige_t09()
    r = caso("camera", limite=400)
    b, ox, oy = r["base"], r["orb_x"], r["orb_y"]
    assert b["v"][2] < b["g"][2] - 5, f"Z não está para cima: vermelho (z=3) deveria aparecer acima do verde: {b}"
    assert abs(ox["az"] - (CAM["azimute"] - 20.0)) < 1e-6 and abs(ox["el"] - CAM["elevacao"]) < 1e-6 and ox["alvo"] == b["alvo"], f"orbitar(40,0): {ox}"
    assert abs(oy["el"] - (ox["el"] + 10.0)) < 1e-6 and abs(oy["az"] - ox["az"]) < 1e-6, f"orbitar(0,20): {oy}"
    assert 85 <= r["orb_alto"]["el"] <= 89.5 and -89.5 <= r["orb_baixo"]["el"] <= -85, f"elevação sem limite: {r['orb_alto']} {r['orb_baixo']}"
    mx, my = r["mov_x"], r["mov_y"]
    assert mx["alvo"] != b["alvo"] and abs(mx["dist"] - CAM["distancia"]) < 1e-6 and abs(mx["az"] - CAM["azimute"]) < 1e-6, f"mover(40,0): {mx}"
    assert 30 <= r["mov_x_g"][1] - b["g"][1] <= 50 and abs(r["mov_x_g"][2] - b["g"][2]) <= 3, f"mover(40,0): conteúdo andou {r['mov_x_g']} (base {b['g']})"
    assert 22 <= r["mov_y_g"][2] - b["g"][2] <= 38 and abs(r["mov_y_g"][1] - b["g"][1]) <= 3, f"mover(0,30): conteúdo andou {r['mov_y_g']} (base {b['g']})"
    assert abs(r["apr2"]["dist"] - 10.0) < 1e-6 and abs(r["apr_meio"]["dist"] - 40.0) < 1e-6, (r["apr2"], r["apr_meio"])
    assert 2.5 <= r["apr2_g"] / b["g"][0] <= 5.5 and r["apr_meio_g"] < b["g"][0] / 2, f"tamanho na imagem: {r['apr2_g']}, {r['apr_meio_g']} (base {b['g'][0]})"
    assert r["apr_zero"] == "ValueError"
    e = r["enq"]
    assert r["longe_g"] < b["g"][0] / 5, "controle: a câmera longe deveria ver o verde pequeno ou fora da imagem"
    assert np.allclose(e["alvo"], [0.0, 0.0, 1.5], atol=0.1) and 5 < e["dist"] < 80 and abs(e["az"] + 60) < 1e-6 and abs(e["el"] - 25) < 1e-6, f"enquadrar: {e}"
    assert all(r["enq_cls"][k][0] >= 300 for k in "vga") and r["enq_borda"] == 0 and 0.4 <= r["enq_larg"] < 1.0, \
        f"enquadrar: cubos cortados ou pequenos: {r['enq_cls']} borda {r['enq_borda']} largura {r['enq_larg']:.2f}"
    assert r["fila_ms"] < 200, f"orbitar bloqueou a thread da janela: 200 chamadas em {r['fila_ms']:.0f} ms"
    assert abs(r["fila_az"] - (r["fila_az0"] - 100.0)) < 1e-6, f"entradas perdidas ou duplicadas: {r['fila_az0']} -> {r['fila_az']} (esperado -100)"

def c_animar(res):
    c, w, _ = novo(0)
    c.adicionar_lote(tres())
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 36)
    yield 500
    base, res["taxas"] = pos(c), {}
    for taxa in (90.0, -45.0):
        c.animar_orbita(taxa)
        yield 400
        amostras, imgs, t0 = [], [], agora()
        for i in range(5):
            amostras.append((time.perf_counter(), pos(c)["az"]))
            imgs.append(captura(c).astype(np.int16)) if i in (1, 3) else None
            yield 300
        d = lambda a, b: (b - a + 180) % 360 - 180  # noqa: E731
        res["taxas"][str(taxa)] = [d(a[1], b[1]) / (b[0] - a[0]) for a, b in zip(amostras, amostras[1:])]
        res["dif_" + str(taxa)] = float(np.abs(imgs[0] - imgs[1]).mean())
        res["quadros_" + str(taxa)] = len(quadros(c, t0))
        c.parar_animacao()
        yield 300
        p1 = pos(c)
        yield 600
        res["parou_" + str(taxa)] = [p1, pos(c)]
    res["base"], res["viva"] = base, c.viva()
    c.parar()

def test_animacao_de_orbita_por_tempo_e_parada(viewport):
    exige_t09()
    r = caso("animar", limite=300)
    for taxa in (90.0, -45.0):
        med = float(np.median(r["taxas"][str(taxa)]))
        assert abs(med - taxa) <= 0.2 * abs(taxa), f"animar_orbita({taxa}): mediana {med:.1f} graus/s ({r['taxas'][str(taxa)]})"
        assert r[f"quadros_{taxa}"] >= 30 and r[f"dif_{taxa}"] > 0.3, f"animação sem quadros novos/imagem parada: {r[f'quadros_{taxa}']} quadros, dif {r[f'dif_{taxa}']}"
        a, b = r[f"parou_{taxa}"]
        assert a == b, f"parar_animacao() não parou a câmera: {a} -> {b}"
        assert abs(a["el"] - r["base"]["el"]) < 1e-9 and a["alvo"] == r["base"]["alvo"] and abs(a["dist"] - r["base"]["dist"]) < 1e-9, a
    assert r["viva"]

def c_atualizar(res):
    c, w, _ = novo(0)
    seqs = [c.adicionar_lote(tres())]
    espera = lambda n: esperar(lambda: c.estatisticas()["triangulos_na_placa"] == n and c.estatisticas()["triangulos"] == n)  # noqa: E731
    yield from espera(36)
    yield 500
    a0 = captura(c)
    res["ant"] = dict(v=cent(a0, "v")[0], g=cent(a0, "g")[0], a=cent(a0, "a")[0])
    seqs.append(c.atualizar(com_guids(lote(cubos=[((-4, 0, 0), 1.0, AMARELO)]), G(0)), []))  # troca o vermelho (mesmo guid) por amarelo
    res["ok1"] = yield from espera(36)
    yield 500
    a1 = captura(c)
    res["t1"] = dict(v=cent(a1, "v")[0], g=cent(a1, "g")[0], a=cent(a1, "a")[0], am=amarelo(a1))
    seqs.append(c.atualizar(None, [G(1)]))  # remove só o verde (os outros do mesmo lote ficam)
    res["ok2"] = yield from espera(24)
    yield 500
    a2 = captura(c)
    res["t2"] = dict(v=cent(a2, "v")[0], g=cent(a2, "g")[0], a=cent(a2, "a")[0], am=amarelo(a2))
    seqs.append(c.atualizar(None, ["Z" * 22]))  # guid inexistente: nada muda, mas a sequência sobe
    yield 400
    res["tri3"], res["seqs"] = [c.estatisticas()["triangulos"], c.estatisticas()["triangulos_na_placa"]], seqs
    res["guid1"], res["guid0"] = list(c.objetos(seqs[1])["guid"]), "ValueError"
    try:
        res["guid0"] = list(c.objetos(seqs[0])["guid"])
    except ValueError:
        pass
    res["apresentou"] = max(s for _, s in quadros(c)) >= seqs[-1]
    n0 = c.estatisticas()["contextos"]
    c.perder_contexto()
    res["ctx"] = yield from esperar(lambda: c.estatisticas()["contextos"] > n0 and c.estatisticas()["triangulos_na_placa"] == 24, 12000)
    yield 500
    a3 = captura(c)
    res["t3"] = dict(g=cent(a3, "g")[0], a=cent(a3, "a")[0], am=amarelo(a3))
    ruim, erros = replace(um(1), indices=um(1).indices.astype(np.int64)), {}
    for k, args in {"None e nao-lista": (None, 5), "dtype": (ruim, []), "tipo": (1234, [])}.items():
        try:
            c.atualizar(*args)
            erros[k] = "aceitou"
        except (TypeError, ValueError) as ex:
            erros[k] = type(ex).__name__
        except BaseException as ex:  # noqa: BLE001
            erros[k] = "SUJO " + type(ex).__name__
    yield 300
    res["erros"], res["tri_fim"], res["viva"] = erros, [c.estatisticas()["triangulos"], c.estatisticas()["triangulos_na_placa"]], c.viva()
    c.parar()

def test_atualizar_troca_e_remove_por_guid(viewport):
    exige_t09()
    r = caso("atualizar", limite=300)
    s, ant, t1, t2 = r["seqs"], r["ant"], r["t1"], r["t2"]
    assert r["ok1"] and r["ok2"] and r["viva"], r
    assert all(a < b for a, b in zip(s, s[1:])), f"sequência não é estritamente crescente: {s}"
    assert min(ant.values()) >= 300, ant
    assert t1["v"] < 20 and t1["am"] >= 300, f"o objeto antigo (vermelho) não sumiu ou o novo não apareceu: {t1}"
    assert abs(t1["g"] - ant["g"]) <= 0.05 * ant["g"] and abs(t1["a"] - ant["a"]) <= 0.05 * ant["a"], f"objetos que não foram trocados mudaram: {ant} -> {t1}"
    assert t2["g"] < 20 and t2["am"] >= 300 and abs(t2["a"] - ant["a"]) <= 0.05 * ant["a"], f"remoção do verde: {t2}"
    assert r["tri3"] == [24, 24], f"guid inexistente mudou a cena: {r['tri3']}"
    assert r["guid1"] == [G(0)] and (r["guid0"] == "ValueError" or G(0) not in r["guid0"]), (r["guid1"], r["guid0"])
    assert r["apresentou"], "a sequência da última atualização nunca chegou à placa"
    assert r["ctx"] and r["t3"]["g"] < 20 and r["t3"]["am"] >= 300, f"depois da perda de contexto o removido voltou: {r['t3']}"
    assert r["erros"] == {"None e nao-lista": "TypeError", "dtype": "TypeError", "tipo": "TypeError"} or (
        all(v in ("TypeError", "ValueError") for v in r["erros"].values()) and len(r["erros"]) == 3), r["erros"]
    assert r["tri_fim"] == [24, 24], f"erro deixou a cena alterada: {r['tri_fim']}"

def c_deslocamento(res):
    c, w, _ = novo(0)
    d1, d2 = np.array([1000.5, 2000.25, 3.0]), np.array([5.0, 6.0, 7.0])
    get = lambda s: (list(map(float, c.objetos(s)["deslocamento"])) if "deslocamento" in c.objetos(s) else None)  # noqa: E731
    s1 = c.adicionar_lote(replace(um(0), deslocamento=d1))
    res["d1"] = get(s1)
    try:
        s2 = c.adicionar_lote(replace(um(1), deslocamento=d2))
        res["segundo"], res["d2"] = "aceito", get(s2)
    except ValueError:
        res["segundo"], res["d2"] = "ValueError", None
    res["lotes_apos"] = c.estatisticas()["lotes"]
    s3 = c.adicionar_lote(replace(um(2), deslocamento=d1))  # o mesmo deslocamento do primeiro sempre entra
    res["d3"] = get(s3)
    res["lotes_fim"] = c.estatisticas()["lotes"]
    c.parar()
    yield 0

def test_deslocamento_por_lote_em_objetos(viewport):
    exige_t09()
    r = caso("deslocamento")
    assert r["d1"] == [1000.5, 2000.25, 3.0] and r["d3"] == r["d1"], f"objetos() deve devolver o deslocamento do lote: {r}"
    if r["segundo"] == "ValueError":
        assert r["lotes_apos"] == 1 and r["lotes_fim"] == 2, r
    else:
        assert r["d2"] in ([5.0, 6.0, 7.0], r["d1"]) and r["lotes_apos"] == 2 and r["lotes_fim"] == 3, r

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o teste importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
