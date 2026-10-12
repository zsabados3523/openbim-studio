# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teste do AdaptadorCarga (S03-T05-C1, B-8): viewport falso, sem tela."""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototypes"))
sys.path.insert(0, str(RAIZ / "scripts"))

from gerar_modelo_grande import gerar  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from viewport_qrhi.adaptador import AdaptadorCarga  # noqa: E402


class _ViewportFalso:
    def __init__(self):
        self.lotes, self.enquadros, self.limpezas = [], 0, 0

    def limpar(self):
        self.lotes, self.limpezas = [], self.limpezas + 1

    def adicionar_lote(self, lote):
        self.lotes.append(lote)

    def enquadrar(self):
        self.enquadros += 1

    def estatisticas(self):
        return {"triangulos": sum(len(x.indices) // 3 for x in self.lotes)}


def test_adaptador_m600(tmp_path):
    app = QApplication.instance() or QApplication([])
    caminho = tmp_path / "m600.ifc"
    gerar(caminho, paredes=600, por_andar=200)
    vp, fim = _ViewportFalso(), []
    ad = AdaptadorCarga(vp)
    ad.terminou.connect(fim.append)
    ad.abrir(caminho)
    limite = time.perf_counter() + 120
    while not fim and time.perf_counter() < limite:
        QCoreApplication.processEvents()
    assert fim and fim[0].estado == "concluido"
    assert vp.estatisticas()["triangulos"] == 7200 and vp.enquadros >= 1 and vp.limpezas == 1
    assert ad.cancelar() is True
    assert app is not None
