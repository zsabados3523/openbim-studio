# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abre a janela com o cubo girando. Uso: python -m viewport_qrhi [--api opengl|vulkan]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QRhiWidget  # noqa: E402

from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402

APIS = {"opengl": QRhiWidget.Api.OpenGL, "vulkan": QRhiWidget.Api.Vulkan, "d3d11": QRhiWidget.Api.Direct3D11, "d3d12": QRhiWidget.Api.Direct3D12}


def main() -> int:
    app = QApplication(sys.argv)
    api = None
    if "--api" in sys.argv:
        api = APIS[sys.argv[sys.argv.index("--api") + 1]]
    w = CuboViewport(api=api)
    w.setWindowTitle("Viewport QRhi (protótipo)")
    w.resize(640, 480)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
