# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ponto de entrada do aplicativo."""
import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main(argv=None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("OpenBIM Studio")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
