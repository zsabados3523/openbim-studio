# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ponto de entrada do aplicativo."""
import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main(argv=None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("OpenBIM Studio")
    window = MainWindow()
    if "--selftest" in (sys.argv if argv is None else argv):
        print("OK" if window.windowTitle() else "FALHA")
        window.close()
        return 0 if window.windowTitle() else 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
