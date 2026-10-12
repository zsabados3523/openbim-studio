# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abre a janela. Uso: python -m viewport_qrhi [arquivo.ifc] [--api opengl|vulkan]

Sem arquivo: o cubo. Com arquivo: as malhas do IFC chegam em lotes (S03-T05)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QRhiWidget  # noqa: E402

from viewport_qrhi.adaptador import AdaptadorCarga  # noqa: E402
from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402

APIS = {"opengl": QRhiWidget.Api.OpenGL, "vulkan": QRhiWidget.Api.Vulkan, "d3d11": QRhiWidget.Api.Direct3D11, "d3d12": QRhiWidget.Api.Direct3D12}


def main() -> int:
    app = QApplication(sys.argv)
    api = None
    if "--api" in sys.argv:
        api = APIS[sys.argv[sys.argv.index("--api") + 1]]
    arquivos = [a for a in sys.argv[1:] if a.lower().endswith(".ifc")]
    w = CuboViewport(api=api, girar=False)
    w.setWindowTitle("Viewport QRhi (protótipo)")
    w.resize(1024, 700 if arquivos else 480)
    w.show()
    if arquivos:
        ad = AdaptadorCarga(w)
        ad.progresso.connect(lambda f, t: w.setWindowTitle(f"Carregando {f}/{t} produtos"))
        ad.terminou.connect(lambda r: w.setWindowTitle(
            f"{r.estado}: {r.triangulos} triângulos, {r.produtos_com_malha} produtos, {r.tempos.get('total_s', 0):.1f} s"
            + (f" ({r.erro})" if r.erro else "")))
        ad.abrir(arquivos[0])
        w._adaptador = ad  # mantém vivo
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
