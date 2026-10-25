# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teste do AdaptadorCarga: viewport falso, sem tela."""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "viewport"))
sys.path.insert(0, str(RAIZ / "scripts"))

from gerar_modelo_grande import gerar  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402
import pytest  # noqa: E402
from obrigatorio import pular_sem_tela  # noqa: E402

from viewport_qrhi.adaptador import AdaptadorCarga  # noqa: E402
from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402


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


# ---------- P17: troca de janela com a liberação ligada ----------
# Esperado: ao perder lotes, o viewport emite o sinal `contexto_perdido` (sem argumentos) e zera a caixa da cena;
# o `AdaptadorCarga` reabre o arquivo sozinho (mesmo caminho e opções). (Antes dessa correção a cena ficava vazia em silêncio.)


def _esperar(app, cond, limite_s):
    fim = time.perf_counter() + limite_s
    while not cond() and time.perf_counter() < fim:
        QCoreApplication.processEvents()
    return cond()


def _trocar_de_janela(tmp_path):
    """Carrega o M600 num CuboViewport (liberar_apos_envio=True, o padrão), muda o widget de janela e espera a cena
    voltar. Devolve (triângulos antes, triângulos depois, perdas, sinais, quantas vezes a carga terminou)."""
    app = QApplication.instance() or QApplication([])
    caminho = tmp_path / "m600.ifc"
    gerar(caminho, paredes=600, por_andar=200)
    a = QWidget()
    QVBoxLayout(a).addWidget(w := CuboViewport(girar=False))
    a.resize(640, 480)
    quadros, sinais, fins = [], [], []
    w.frameSubmitted.connect(lambda: quadros.append(1))
    if hasattr(w, "contexto_perdido"):
        w.contexto_perdido.connect(lambda: sinais.append(1))
    a.show()
    _esperar(app, lambda: quadros, 5.0)
    if w.rhi() is None or not quadros:
        a.close()
        pular_sem_tela("P17 precisa de tela virtual com contexto gráfico (rode com xvfb e QT_QPA_PLATFORM=xcb)")
    ad = AdaptadorCarga(w)
    ad.terminou.connect(fins.append)
    ad.abrir(caminho)
    assert _esperar(app, lambda: fins, 120.0) and fins[0].estado == "concluido"
    assert _esperar(app, lambda: (e := w.estatisticas())["pendentes"] == 0 and e["bytes_gpu"] > 0, 10.0)
    antes = w.estatisticas()["triangulos"]
    b = QWidget()  # troca de contexto gráfico: o widget muda de janela
    QVBoxLayout(b).addWidget(w)
    b.resize(640, 480)
    n = len(quadros)
    b.show()
    _esperar(app, lambda: len(quadros) > n + 3, 10.0)
    _esperar(app, lambda: len(fins) >= 2 and w.estatisticas()["triangulos"] == antes, 20.0)  # a carga recomeça sozinha
    depois, perdidos = w.estatisticas()["triangulos"], w.lotes_perdidos
    ad.cancelar()
    a.close()
    b.close()
    return antes, depois, perdidos, sinais, len(fins)


def test_p17_troca_de_janela_recarrega_sozinha(tmp_path):
    antes, depois, perdidos, _sinais, fins = _trocar_de_janela(tmp_path)
    assert antes == 7200
    assert depois == antes, f"a cena voltou com {depois} triângulos (eram {antes}; lotes perdidos: {perdidos})"
    assert fins >= 2, "o adaptador não reabriu o arquivo"


def test_p17_sinal_contexto_perdido_emitido(tmp_path):
    antes, depois, _perdidos, sinais, _fins = _trocar_de_janela(tmp_path)
    assert len(sinais) >= 1, "o viewport não emitiu contexto_perdido"
    assert depois == antes == 7200
