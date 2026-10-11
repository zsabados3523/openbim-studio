# SPDX-License-Identifier: AGPL-3.0-or-later
"""Experimento T12: roda um roteiro automático do app sem tela, captura a janela em cada passo e monta
um GIF animado (e um WebP). Não é teste: é só para o PO ver. Uso: gravar_roteiro.py PASTA_SAIDA IFC"""
import io
import sys
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from openbim_app.main_window import MainWindow  # noqa: E402


def captura(janela):
    app = QApplication.instance()
    app.processEvents()
    img = janela.grab().toImage()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")


def main(saida, ifc):
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    janela = MainWindow()
    janela.show_error_dialogs = False
    janela.show()
    quadros = [("1 janela aberta", captura(janela))]
    janela.open_ifc(ifc)
    quadros.append(("2 IFC aberto", captura(janela)))
    janela.open_ifc(str(saida / "nao-existe.ifc"))
    quadros.append(("3 erro tratado", captura(janela)))
    janela.open_ifc(ifc)
    quadros.append(("4 reaberto", captura(janela)))
    for nome, im in quadros:
        im.save(saida / f"passo-{nome.split()[0]}.png")
    imgs = [im for _, im in quadros]
    t0 = time.time()
    imgs[0].save(saida / "roteiro.gif", save_all=True, append_images=imgs[1:], duration=1200, loop=0)
    imgs[0].save(saida / "roteiro.webp", save_all=True, append_images=imgs[1:], duration=1200, loop=0)
    print(f"{len(imgs)} quadros {imgs[0].size}; GIF+WebP em {time.time() - t0:.2f} s")
    janela.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
