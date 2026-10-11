# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S03-T04: câmera orbital (pura) e ligação ao mouse do viewport."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes"))

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from viewport_qrhi.camera import DIST_MAX, DIST_MIN, Camera  # noqa: E402
from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402


def test_orbita_preserva_distancia_ao_alvo():
    c = Camera(alvo=(1, 2, 3), distancia=5.0)
    for dx, dy in [(40, 10), (-300, 25), (7, -900), (1000, 1000)]:
        c.orbitar(dx, dy)
        assert np.linalg.norm(c.posicao - c.alvo) == pytest.approx(5.0)


def test_orbita_limita_elevacao_e_matriz_muda():
    c = Camera()
    antes = c.matriz_vista().copy()
    c.orbitar(50, 0)
    assert not np.allclose(antes, c.matriz_vista())
    c.orbitar(0, 100000)
    assert c.elevacao == pytest.approx(89.0)
    c.orbitar(0, -1000000)
    assert c.elevacao == pytest.approx(-89.0)
    assert np.all(np.isfinite(c.matriz_vista()))


def test_mover_desloca_alvo_e_posicao_juntos():
    c = Camera()
    off = c.posicao - c.alvo
    alvo0 = c.alvo.copy()
    c.mover(30, -20)
    assert not np.allclose(c.alvo, alvo0)
    assert np.allclose(c.posicao - c.alvo, off)
    # deslocamento fica no plano da tela (perpendicular à frente)
    assert (c.alvo - alvo0) @ c.eixos()[2] == pytest.approx(0.0, abs=1e-9)


def test_zoom_respeita_minimo_e_maximo():
    c = Camera(distancia=3.0)
    c.aproximar(1)
    assert c.distancia < 3.0
    c.aproximar(-1)
    assert c.distancia == pytest.approx(3.0)
    c.aproximar(10000)
    assert c.distancia == DIST_MIN
    c.aproximar(-10000)
    assert c.distancia == DIST_MAX


def test_vista_poe_alvo_na_frente_e_z_para_cima():
    c = Camera(alvo=(0, 0, 0), distancia=4.0)
    p = c.matriz_vista() @ np.array([0, 0, 0, 1.0])
    assert p[:3] == pytest.approx([0, 0, -4.0])
    up = c.matriz_vista() @ np.array([0, 0, 1, 0.0])  # Z do mundo aponta para cima na tela
    assert up[1] > 0


# --- com tela ---
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _quadro(w):
    n0 = []
    w.frameSubmitted.connect(lambda: n0.append(1))
    w.update()
    t = QElapsedTimer()
    t.start()
    while not n0 and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    return bool(n0)


def _mouse(w, tipo, pos, botao, botoes, mods=Qt.NoModifier):
    p = QPointF(*pos)
    ev = QMouseEvent(tipo, p, w.mapToGlobal(p), botao, botoes, mods)
    QApplication.sendEvent(w, ev)


def _arrastar(w, botao, mods=Qt.NoModifier):
    _mouse(w, QEvent.MouseButtonPress, (100, 100), botao, botao, mods)
    _mouse(w, QEvent.MouseMove, (140, 120), Qt.NoButton, botao, mods)
    _mouse(w, QEvent.MouseButtonRelease, (140, 120), botao, Qt.NoButton, mods)


def test_mouse_liga_na_camera_sem_tela(app):
    w = CuboViewport(girar=False)
    w.resize(320, 240)
    v0 = w.camera.matriz_vista().copy()
    _arrastar(w, Qt.LeftButton)
    assert not np.allclose(v0, w.camera.matriz_vista())
    assert w.camera.alvo == pytest.approx([0, 0, 0])  # orbitar não move o alvo
    _arrastar(w, Qt.MiddleButton)
    assert not np.allclose(w.camera.alvo, 0)
    alvo = w.camera.alvo.copy()
    _arrastar(w, Qt.LeftButton, Qt.ShiftModifier)
    assert not np.allclose(alvo, w.camera.alvo)
    d = w.camera.distancia
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)
    assert w.camera.distancia < d


def test_mouse_muda_o_quadro(app, tmp_path):
    w = CuboViewport(girar=False)
    w.resize(320, 240)
    w.show()
    if not _quadro(w) or w.rhi() is None:
        w.close()
        pytest.skip("sem contexto gráfico: rode com QT_QPA_PLATFORM=xcb e tela real")
    antes = w.grab_image()
    assert antes.save(str(tmp_path / "antes.png"))
    _arrastar(w, Qt.LeftButton)
    assert _quadro(w)
    depois = w.grab_image()
    assert depois.save(str(tmp_path / "depois.png"))
    assert antes != depois
    w.close()
