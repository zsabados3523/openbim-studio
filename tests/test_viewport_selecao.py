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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes"))

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from viewport_qrhi.camera import Camera  # noqa: E402
from viewport_qrhi.cubo_rhi import CuboViewport, cubo_padrao  # noqa: E402
from viewport_qrhi.selecao import Malha, malha_de_ifc, pick, pick_raio  # noqa: E402


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
        pytest.skip("precisa de tela: rode com QT_QPA_PLATFORM=xcb")
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
