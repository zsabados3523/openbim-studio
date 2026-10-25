# SPDX-License-Identifier: AGPL-3.0-or-later
"""Liga o `CarregadorMalhas` (thread de trabalho) ao `Viewport` (thread da interface).

Um temporizador da interface tira no máximo 1 lote por disparo (16 ms) e o entrega ao viewport.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

try:
    from .carregador import CarregadorMalhas, LoteMalha, ResumoCarga
except ImportError:  # pragma: no cover
    from carregador import CarregadorMalhas, LoteMalha, ResumoCarga

INTERVALO_MS = 16


class AdaptadorCarga(QObject):
    progresso = Signal(int, int)  # produtos feitos, total
    terminou = Signal(object)  # ResumoCarga
    erro = Signal(str)  # não foi possível iniciar a carga

    def __init__(self, viewport, parent=None):
        super().__init__(parent)
        self.viewport = viewport
        self.carregador: CarregadorMalhas | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVALO_MS)
        self._timer.timeout.connect(self._passo)
        self._ultimo = None  # (caminho, opções) da última carga: o viewport perdeu o modelo, reabre sozinho
        sinal = getattr(viewport, "contexto_perdido", None)
        if sinal is not None:  # a troca de contexto ocorre dentro do desenho: recarrega depois, fora dele
            sinal.connect(lambda: QTimer.singleShot(0, self._reabrir))
        app = QCoreApplication.instance()
        if app is not None:  # B-5: fechar o programa cancela a carga
            app.aboutToQuit.connect(self.cancelar)

    def abrir(self, caminho, **opcoes) -> None:
        """Nova carga. Se houver outra em andamento: cancela, espera terminar e limpa o viewport."""
        if not self.cancelar():  # B-4: a carga velha não terminou; não começa outra por cima
            self.erro.emit("a carga anterior ainda não terminou; tente de novo em instantes")
            return
        self._ultimo = (str(caminho), dict(opcoes))
        self.viewport.limpar()
        self.carregador = CarregadorMalhas(str(caminho), **opcoes)
        self._primeiro = True
        self.carregador.iniciar()
        self._timer.start()

    def _reabrir(self) -> None:
        if self._ultimo is not None:
            self.abrir(self._ultimo[0], **self._ultimo[1])

    def cancelar(self) -> bool:
        """Devolve False se a thread não terminou em 5 s (o carregador velho é mantido)."""
        if self.carregador is not None:
            self._timer.stop()
            self.carregador.cancelar()
            if not self.carregador.aguardar(timeout=5.0):  # nunca mata a thread: espera o `next()` em curso
                return False
            self.carregador = None
        return True

    def _passo(self) -> None:
        x = self.carregador.obter(timeout=0.0)
        if isinstance(x, LoteMalha):
            self.viewport.adicionar_lote(x)
            if self._primeiro:
                self._primeiro = False
                self.viewport.enquadrar()
            self.progresso.emit(x.produtos_feitos, x.produtos_total)
        elif isinstance(x, ResumoCarga):
            self._timer.stop()
            self.viewport.enquadrar()
            self.terminou.emit(x)
