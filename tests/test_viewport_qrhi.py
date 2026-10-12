# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S03-T03: o QRhiWidget desenha o cubo e o quadro não é de uma cor só."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes"))

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QRhiWidget  # noqa: E402

from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _desenhar(app, api=None):
    """Mostra o widget, espera o primeiro quadro e devolve (widget, imagem)."""
    w = CuboViewport(api=api, girar=False)
    w.definir_angulo(35.0)  # mostra mais de uma face
    w.resize(320, 240)
    quadros = []
    w.frameSubmitted.connect(lambda: quadros.append(1))
    w.show()
    t = QElapsedTimer()
    t.start()
    while not quadros and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    return w, quadros


def test_cubo_desenha_quadro_nao_uniforme(app, tmp_path):
    w, quadros = _desenhar(app)
    exigir = os.environ.get("OBIM_EXIGIR_DESENHO") == "1"  # passo informativo do CI (T25): sem desenho = falha, não pulo
    if w.rhi() is None or not quadros:
        w.close()
        if exigir:
            pytest.fail("OBIM_EXIGIR_DESENHO=1 mas o QRhi não foi criado (sem GPU/OpenGL/D3D utilizável)")
        pytest.skip(
            "sem contexto gráfico (QT_QPA_PLATFORM=%s): o QRhiWidget não criou o QRhi; "
            "rode com tela real para validar o desenho" % os.environ.get("QT_QPA_PLATFORM", "?")
        )
    img = w.grab_image()
    png = tmp_path / "cubo.png"
    assert img.save(str(png))
    saida = os.environ.get("OBIM_PNG_SAIDA")  # o CI guarda o PNG como prova
    if saida:
        Path(saida).mkdir(parents=True, exist_ok=True)
        img.save(str(Path(saida) / "cubo.png"))
    print("RHI backend:", w.rhi().backendName(), "| cores:", len({img.pixel(x, y) for x in range(0, 320, 4) for y in range(0, 240, 4)}))
    assert png.stat().st_size > 0
    assert not img.isNull() and img.width() == 320 and img.height() == 240
    cores = {img.pixel(x, y) for x in range(0, img.width(), 4) for y in range(0, img.height(), 4)}
    assert len(cores) >= 3, f"imagem quase uniforme: {len(cores)} cores"
    w.close()


def test_set_mesh_troca_malha(app):
    w = CuboViewport(girar=False)
    w.set_mesh([[0, 0, 0, 1, 0, 0], [1, 0, 0, 0, 1, 0], [0, 1, 0, 0, 0, 1]], [0, 1, 2])
    assert w._vertices.shape == (3, 6) and w._indices.tolist() == [0, 1, 2]
