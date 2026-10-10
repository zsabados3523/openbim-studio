# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teste da janela principal (F0-S02-T04), sem exibir a janela."""
import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QLabel

from openbim_app.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    w = MainWindow()
    yield w
    w.close()


def _titles(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_menus(window):
    menus = {a.text().replace("&", ""): a.menu() for a in window.menuBar().actions()}
    assert set(menus) == {"Arquivo", "Ajuda"}
    assert _titles(menus["Arquivo"]) == ["Abrir IFC…", "Sair"]
    assert _titles(menus["Ajuda"]) == ["Sobre"]


def test_central_placeholder_and_status(window):
    central = window.centralWidget()
    assert isinstance(central, QLabel)
    assert central.text() == "A viewport 3D entra na fatia S03"
    assert window.statusBar() is not None


def _mime(path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    return mime


def test_drop_ifc_shows_name(window):
    mime = _mime("/tmp/Casa.ifc")
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    assert "Casa.ifc" in window.statusBar().currentMessage()


def test_drop_non_ifc_rejected(window):
    mime = _mime("/tmp/foto.png")
    enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    enter.setAccepted(True)
    window.dragEnterEvent(enter)
    assert not enter.isAccepted()


def test_selftest_mode(qapp, capsys):
    from openbim_app.main import main

    assert main(["openbim", "--selftest"]) == 0
    assert "OK" in capsys.readouterr().out
