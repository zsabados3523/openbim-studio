# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ponto de entrada do aplicativo."""
import sys

from .localidade import criar_aplicacao, numerico_ok
from .main_window import MainWindow


def main(argv=None) -> int:
    app = criar_aplicacao(sys.argv if argv is None else argv)
    app.setApplicationName("OpenBIM Studio")
    window = MainWindow()
    if "--selftest" in (sys.argv if argv is None else argv):
        ok = bool(window.windowTitle()) and numerico_ok()
        print("OK" if ok else "FALHA")
        window.close()
        return 0 if ok else 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
