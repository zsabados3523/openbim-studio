# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S03-T06: seleção por clique (raio x triângulos), sem tela e com tela.

Teste pesado (1 milhão de triângulos): defina OBIM_MODELO_GRANDE=caminho/modelo-grande-1m.ifc.
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from obrigatorio import pular_sem_tela

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes"))

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from viewport_qrhi.camera import Camera  # noqa: E402
from viewport_qrhi.cubo_rhi import CuboViewport, cubo_padrao  # noqa: E402
from viewport_qrhi.carregador import DTYPE_OBJETO, LoteMalha  # noqa: E402
from viewport_qrhi.selecao import (CaixasObjetos, Malha, malha_de_ifc, pick, pick_caixas, pick_caixas_raio,  # noqa: E402
                                   pick_raio)


def _cubo(centro, lado=1.0):
    v, i = cubo_padrao()
    return v[:, :3] * lado + np.asarray(centro, dtype=np.float32), i.reshape(-1, 3)


def test_raio_acerta_e_erra_cubo():
    m = Malha([("a", *_cubo((0, 0, 0)))])
    assert pick_raio(m, (5, 0, 0), (-1, 0, 0))[0] == "a"
    assert pick_raio(m, (5, 0, 0), (1, 0, 0))[0] is None  # de costas
    assert pick_raio(m, (5, 2, 0), (-1, 0, 0))[0] is None  # passa ao lado
    assert pick_raio(m, (5, 0.4, 0.4), (-1, 0, 0))[0] == "a"


def test_vence_o_mais_proximo_em_qualquer_ordem():
    for ordem in ((0, 3, 6), (6, 3, 0), (3, 0, 6)):
        m = Malha([(f"c{x}", *_cubo((x, 0, 0))) for x in ordem])
        idv, t = pick_raio(m, (10, 0, 0), (-1, 0, 0))
        assert idv == "c6" and t == pytest.approx(3.5)
        assert pick_raio(m, (-10, 0, 0), (1, 0, 0))[0] == "c0"


def test_raio_paralelo_ao_eixo_fora_da_caixa():
    m = Malha([("a", *_cubo((0, 0, 0)))])
    assert pick_raio(m, (5, 0, 3), (-1, 0, 0))[0] is None


def test_pick_pela_camera_centro_e_canto():
    m = Malha([("a", *_cubo((0, 0, 0)))])
    cam = Camera(distancia=5.0)
    assert pick(m, cam, 200, 150, 400, 300) == "a"
    assert pick(m, cam, 2, 2, 400, 300) is None
    # o pixel (x, y) com y para baixo: logo acima do cubo deve errar, em cima dele acerta
    assert pick(m, cam, 200, 20, 400, 300) is None


def test_escala_de_tela_nao_muda_o_resultado():
    m = Malha([("a", *_cubo((0, 0, 0)))])
    cam = Camera(distancia=5.0)
    assert pick(m, cam, 200, 150, 400, 300) == pick(m, cam, 400, 300, 800, 600) == "a"


def test_modelo_grande_pequeno_sintetico_tempo():
    """Rápido: 20 mil cubos (240 mil triângulos) gerados em memória."""
    n = 141
    objs = [(i, *_cubo(((i % n) * 3.0, (i // n) * 3.0, 0))) for i in range(n * n // 1)]
    m = Malha(objs)
    cam = Camera(alvo=(210, 210, 0), distancia=600.0)
    pick(m, cam, 200, 150, 400, 300)
    t0 = time.perf_counter()
    r = pick(m, cam, 200, 150, 400, 300)
    dt = (time.perf_counter() - t0) * 1000
    print(f"pick com {m.n_triangulos} triangulos: {dt:.1f} ms")
    assert r is not None and dt < 100


@pytest.mark.skipif(not os.environ.get("OBIM_MODELO_GRANDE"), reason="defina OBIM_MODELO_GRANDE (teste pesado)")
def test_pick_modelo_1_milhao_de_triangulos():
    t0 = time.perf_counter()
    m = malha_de_ifc(os.environ["OBIM_MODELO_GRANDE"])
    print(f"malha: {m.n_triangulos} triangulos, {len(m.ids)} objetos, carga {time.perf_counter() - t0:.1f} s")
    assert m.n_triangulos >= 900_000
    centro = (m.caixa_min.min(axis=0) + m.caixa_max.max(axis=0)) / 2
    alvo = m.triangulos[m.fim[0] - 1, 0]  # ponto de um triângulo do 1o objeto
    cam = Camera(alvo=centro, distancia=float(np.linalg.norm(m.caixa_max.max(axis=0) - m.caixa_min.min(axis=0))) * 1.5)
    pick(m, cam, 400, 300, 800, 600)  # aquece
    tempos, achou = [], 0
    for x, y in [(400, 300), (200, 150), (600, 450), (100, 500), (700, 100), (400, 50), (50, 300), (750, 550)]:
        t0 = time.perf_counter()
        r = pick(m, cam, x, y, 800, 600)
        tempos.append((time.perf_counter() - t0) * 1000)
        achou += r is not None
    # tempo com acerto garantido: do olho da câmera ao centro de objetos escolhidos (inclui raios que
    # atravessam muitas caixas), mais um raio rasante que cruza a fila inteira de paredes
    rng = np.random.default_rng(1)
    olho = cam.posicao
    for k in rng.integers(0, len(m.ids), 10):
        c = m.triangulos[m.ini[k]:m.fim[k]].reshape(-1, 3).mean(axis=0).astype(np.float64)
        t0 = time.perf_counter()
        r, _ = pick_raio(m, olho, c - olho)
        tempos.append((time.perf_counter() - t0) * 1000)
        achou += r is not None
    z0 = float(m.caixa_min[:, 2].min()) + 1.0
    t0 = time.perf_counter()
    r, _ = pick_raio(m, (-100.0, 1.0, z0), (1.0, 0.0, 0.0))
    tempos.append((time.perf_counter() - t0) * 1000)
    achou += r is not None
    assert achou >= 9, achou
    print(f"pick 1M triangulos: mediana {np.median(tempos):.1f} ms, maximo {max(tempos):.1f} ms, acertos {achou}/19")
    # verificação de verdade: raio direto ao centro de um triângulo do 1o objeto acerta o objeto certo ou um mais perto
    tri = m.triangulos[m.ini[0]]
    c = tri.mean(axis=0).astype(np.float64)
    n = np.cross(tri[1] - tri[0], tri[2] - tri[0]).astype(np.float64)
    n /= np.linalg.norm(n)
    idv, t = pick_raio(m, c + 0.5 * n, -n)  # raio de frente, de 0,5 m, contra o triângulo
    assert idv == m.ids[0] and t == pytest.approx(0.5, abs=1e-3)
    assert max(tempos) < 100


# ---- com tela ----
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _clique(w, x, y):
    p = QPointF(x, y)
    for tipo, bot, bots in ((QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton),
                            (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton)):
        QApplication.sendEvent(w, QMouseEvent(tipo, p, w.mapToGlobal(p), bot, bots, Qt.NoModifier))


def test_clique_no_cubo_seleciona_e_fora_da_none(app):
    if os.environ.get("QT_QPA_PLATFORM", "offscreen") == "offscreen":
        pular_sem_tela("precisa de tela: rode com QT_QPA_PLATFORM=xcb")
    w = CuboViewport(girar=False)
    w.definir_angulo(35.0)
    w.resize(400, 300)
    quadros = []
    w.frameSubmitted.connect(lambda: quadros.append(1))
    w.show()
    t = QElapsedTimer()
    t.start()
    while not quadros and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    assert quadros, "nenhum quadro desenhado"
    ids = []
    w.clicado.connect(ids.append)
    _clique(w, w.width() / 2, w.height() / 2)
    _clique(w, 3, 3)
    w.close()
    assert ids == [1, None]
    assert w.pick(w.width() / 2, w.height() / 2) == 1 and w.pick(3, 3) is None


# ---- T06b: seleção só por caixas (modo de lotes, sem triângulos) ----
def _lote(objs, desl=(0.0, 0.0, 0.0), indice=0):
    """objs: lista de (id_step, guid, caixa_min, caixa_max); a caixa está no espaço do lote (antes do deslocamento)."""
    ob = np.zeros(len(objs), DTYPE_OBJETO)
    for k, (i, g, lo, hi) in enumerate(objs):
        ob[k]["id_step"], ob[k]["guid"], ob[k]["caixa_min"], ob[k]["caixa_max"] = i, g.encode(), lo, hi
    return LoteMalha(indice, np.empty(0), np.empty(0, np.uint32), ob, np.asarray(desl, np.float64), 0, 0)


def _caixa_em(c, r=0.5):
    c = np.asarray(c, np.float64)
    return c - r, c + r


def test_caixas_clique_acerta_id_e_guid_e_vazio_nada():
    lotes = [_lote([(10, "GUID_A" + "0" * 16, *_caixa_em((0, 0, 0))), (20, "GUID_B" + "0" * 16, *_caixa_em((5, 0, 0)))])]
    c = CaixasObjetos(lotes)
    assert pick_caixas_raio(c, (10, 0, 0), (-1, 0, 0))[:2] == (20, "GUID_B" + "0" * 16)  # a mais próxima
    assert pick_caixas_raio(c, (-10, 0, 0), (1, 0, 0))[:2] == (10, "GUID_A" + "0" * 16)
    assert pick_caixas_raio(c, (10, 3, 0), (-1, 0, 0)) == (None, None, np.inf)  # vazio
    assert pick_caixas_raio(c, (10, 0, 0), (1, 0, 0))[0] is None  # de costas
    cam = Camera(distancia=5.0)
    assert pick_caixas(c, cam, 200, 150, 400, 300)[0] == 10
    assert pick_caixas(c, cam, 2, 2, 400, 300) is None


def test_caixas_usam_o_deslocamento():
    desl = (1000.0, -2000.0, 30.0)
    c = CaixasObjetos([_lote([(7, "G" * 22, *_caixa_em((0, 0, 0)))], desl=desl)])
    assert pick_caixas_raio(c, (1010.0, -2000.0, 30.0), (-1, 0, 0))[0] == 7  # mundo = caixa + deslocamento
    assert pick_caixas_raio(c, (10.0, 0.0, 0.0), (-1, 0, 0))[0] is None  # sem o deslocamento erraria
    assert pick_caixas_raio(c, (1010.0, -2000.0, 30.0), (-1, 0, 0))[2] == pytest.approx(9.5)
    # lotes com deslocamentos diferentes entram no mesmo espaço
    c2 = CaixasObjetos([_lote([(1, "A" * 22, *_caixa_em((0, 0, 0)))], desl=(100, 0, 0)),
                        _lote([(2, "B" * 22, *_caixa_em((0, 0, 0)))], desl=(0, 0, 0), indice=1)])
    assert pick_caixas_raio(c2, (200, 0, 0), (-1, 0, 0))[0] == 1
    assert pick_caixas_raio(c2, (-200, 0, 0), (1, 0, 0))[0] == 2


def test_peca_dividida_em_varios_lotes_e_um_objeto():
    # a viga 5 tem 3 pedaços em 3 lotes (x = 0..1, 4..5, 8..9); a 6 fica no meio, entre os pedaços
    lotes = [_lote([(5, "V" * 22, (0, 0, 0), (1, 1, 1))], indice=0),
             _lote([(6, "W" * 22, (2, 0, 0), (3, 1, 2))], indice=1),
             _lote([(5, "V" * 22, (4, 0, 0), (5, 1, 1))], indice=2),
             _lote([(5, "V" * 22, (8, 0, 0), (9, 1, 1))], indice=3)]
    c = CaixasObjetos(lotes)
    assert len(c) == 2
    assert np.allclose(c.caixa_min[c.ids == 5], (0, 0, 0)) and np.allclose(c.caixa_max[c.ids == 5], (9, 1, 1))
    # raio por cima, sobre o vão entre pedaços (x = 6,5): a caixa unida da peça 5 pega, mesmo sem pedaço ali
    assert pick_caixas_raio(c, (6.5, 0.5, 10), (0, 0, -1))[:2] == (5, "V" * 22)
    assert pick_caixas_raio(c, (2.5, 0.5, 10), (0, 0, -1))[0] == 6  # a caixa de 6 é mais alta que a união da 5: entra antes
    assert pick_caixas_raio(c, (-1, 0.5, 0.5), (1, 0, 0))[0] == 5
    assert pick_caixas_raio(c, (20, 0.5, 0.5), (-1, 0, 0))[0] == 5


def test_caixas_vazias_e_lote_sem_objetos():
    assert pick_caixas_raio(CaixasObjetos([]), (0, 0, 0), (1, 0, 0)) == (None, None, np.inf)
    assert len(CaixasObjetos([_lote([])])) == 0


def _grade_1m(n=83_334):
    """Equivalente ao modelo sintético de 1 milhão de triângulos: n paredes de 12 triângulos, em 5 andares."""
    por_andar = n // 5 + 1
    lado = int(np.ceil(np.sqrt(por_andar)))
    lotes, k = [], 0
    while k < n:
        m = min(5000, n - k)
        ob = np.zeros(m, DTYPE_OBJETO)
        idx = np.arange(k, k + m)
        andar, r = idx // por_andar, idx % por_andar
        c = np.stack([(r % lado) * 3.0, (r // lado) * 3.0, andar * 4.0], axis=1)
        ob["id_step"], ob["guid"] = idx + 1, b"G"
        ob["caixa_min"], ob["caixa_max"] = c - 0.5, c + 0.5
        lotes.append(LoteMalha(len(lotes), np.empty(0), np.empty(0, np.uint32), ob, np.array([10.0, 20.0, 0.0]), 0, 0))
        k += m
    return lotes, lado


def test_pior_caso_raio_atravessa_muitas_caixas_dentro_de_100_ms():
    # Limite do portão da S03 (v2/03): 100 ms. Os 16 ms (um quadro) eram meta do cartão e oscilavam no executor Windows do GitHub (18 ms).
    lotes, lado = _grade_1m()
    c = CaixasObjetos(lotes)
    assert len(c) == 83_334
    d0 = np.array([10.0, 20.0, 0.0])
    # raio rasante que cruza a fila inteira (todas as caixas da linha y=0 do andar 0) e raio vertical pelos 5 andares
    casos = [((d0[0] - 50, d0[1], d0[2]), (1, 0, 0)), ((d0[0], d0[1], 100.0), (0, 0, -1)),
             ((d0[0] - 50, d0[1] + 0.4, d0[2]), (1, 0, 0.0001)), ((d0[0] - 50, d0[1] + 3 * (lado // 2), 8.0), (1, 0, 0))]
    pick_caixas_raio(c, *casos[0])  # aquece
    tempos = []
    for o, dr in casos:
        t0 = time.perf_counter()
        r = pick_caixas_raio(c, o, dr)
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r[0] is not None, (o, dr)
    # o raio que acerta a 1a caixa da fila, de longe: devolve a mais próxima e não uma qualquer
    assert pick_caixas_raio(c, (d0[0] - 50, d0[1], d0[2]), (1, 0, 0))[0] == 1
    print(f"pick por caixas, 83334 objetos: max {max(tempos):.2f} ms, mediana {np.median(tempos):.2f} ms")
    assert max(tempos) < 100.0, tempos


@pytest.mark.skipif(not os.environ.get("OBIM_MODELO_GRANDE"), reason="defina OBIM_MODELO_GRANDE (teste pesado)")
def test_pior_caso_no_modelo_grande_real():
    m = malha_de_ifc(os.environ["OBIM_MODELO_GRANDE"])
    ob = np.zeros(len(m.ids), DTYPE_OBJETO)
    ob["id_step"], ob["guid"] = np.arange(1, len(m.ids) + 1), b"G"
    ob["caixa_min"], ob["caixa_max"] = m.caixa_min, m.caixa_max
    c = CaixasObjetos([LoteMalha(0, np.empty(0), np.empty(0, np.uint32), ob, np.zeros(3), 0, 0)])
    k = len(m.ids) // 2
    alvo = (m.caixa_min[k] + m.caixa_max[k]).astype(np.float64) / 2
    olho = (m.caixa_min.min(axis=0) + m.caixa_max.max(axis=0)).astype(np.float64) / 2 + (-200.0, -200.0, 150.0)
    pick_caixas_raio(c, olho, alvo - olho)
    t0 = time.perf_counter()
    r = pick_caixas_raio(c, olho, alvo - olho)  # atravessa a nuvem de caixas até a do meio
    dt = (time.perf_counter() - t0) * 1000
    print(f"pick por caixas no modelo real: {len(c)} objetos, {dt:.2f} ms")
    assert r[0] is not None and dt < 100.0


def test_viewport_em_lotes_pick_so_com_caixas(app):
    """Com tela: lotes liberados após o envio (sem triângulos) e o clique ainda acha o objeto."""
    if os.environ.get("QT_QPA_PLATFORM", "offscreen") == "offscreen":
        pular_sem_tela("precisa de tela: rode com QT_QPA_PLATFORM=xcb")
    w = CuboViewport(girar=False)
    w.limpar()
    lote = _lote([(42, "Z" * 22, *_caixa_em((0, 0, 0), 1.0))], desl=(0, 0, 0))
    w.adicionar_lote(lote)
    w.resize(400, 300)
    w.enquadrar()
    assert w.pick(200, 150) == 42 and w.pick_objeto(200, 150) == (42, "Z" * 22)
    assert w.pick(2, 2) is None
    w.close()
