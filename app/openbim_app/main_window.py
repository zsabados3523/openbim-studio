# SPDX-License-Identifier: AGPL-3.0-or-later
"""Janela principal: menus, barra de status, área central reservada e arrastar-e-soltar de .ifc."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMessageBox

from openbim_app.ifc_summary import IfcSummaryError, count_by_class, format_summary


def _ifc_paths(mime):
    """Caminhos locais de arquivos .ifc presentes nos dados arrastados."""
    if not mime.hasUrls():
        return []
    paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
    return [p for p in paths if p.lower().endswith(".ifc")]


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("OpenBIM Studio"))
        self.resize(1024, 700)
        self.setAcceptDrops(True)
        self.show_error_dialogs = True  # testes desligam para não abrir diálogo
        self.last_error = None
        self._error_box = None

        placeholder = QLabel(self.tr("A viewport 3D entra na fatia S03"))
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)

        self._build_menus()
        self.statusBar().showMessage(self.tr("Pronto"))

    def _build_menus(self):
        file_menu = self.menuBar().addMenu(self.tr("&Arquivo"))
        self.action_open = QAction(self.tr("Abrir IFC…"), self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self._choose_and_open)
        self.action_quit = QAction(self.tr("Sair"), self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(self.close)
        file_menu.addAction(self.action_open)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

        help_menu = self.menuBar().addMenu(self.tr("A&juda"))
        self.action_about = QAction(self.tr("Sobre"), self)
        self.action_about.triggered.connect(self._show_about)
        help_menu.addAction(self.action_about)

    def _choose_and_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Abrir IFC"), "", self.tr("Arquivos IFC (*.ifc)")
        )
        if path:
            self.open_ifc(path)

    def open_ifc(self, path):
        """Abre o IFC, mostra o resumo no painel central. Devolve o texto de erro ou None."""
        error = self.ifc_error_text(path)
        if error is not None:
            self.last_error = error
            self.statusBar().showMessage(error)
            if self.show_error_dialogs:
                # Não bloqueante (open), para nunca travar a janela.
                box = QMessageBox(QMessageBox.Icon.Warning, self.tr("Erro ao abrir IFC"), error, parent=self)
                box.open()
                self._error_box = box
        return error

    def ifc_error_text(self, path):
        """Lê o arquivo (resumo vai ao painel) e devolve a mensagem de erro, ou None se ok."""
        try:
            summary = count_by_class(path)
        except IfcSummaryError as exc:
            return str(exc)
        self.last_error = None
        self.centralWidget().setText(format_summary(summary))
        self.statusBar().showMessage(
            self.tr("%1: %2 elementos (%3)")
            .replace("%1", summary.file_name)
            .replace("%2", str(summary.total))
            .replace("%3", summary.schema)
        )
        return None

    def _show_about(self):
        QMessageBox.about(
            self,
            self.tr("Sobre"),
            self.tr("OpenBIM Studio: programa BIM aberto (AGPL v3)."),
        )

    def dragEnterEvent(self, event):
        if _ifc_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = _ifc_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.open_ifc(paths[0])
