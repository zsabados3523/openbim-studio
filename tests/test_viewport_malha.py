# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da S03-T05 (Parte 0), V1 a V5: o viewport recebe lotes e desenha (V1 a V4 precisam de tela).

Transcrição de docs/state/reports/LOTE_OPUS_4.md §1.5. Congelado: não afrouxar número nem remover caso.
Sem os métodos novos (S03-T05 parte B) ou sem tela, V1 a V4 pulam com mensagem. V5 sempre roda.
"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from obrigatorio import pular_sem_tela
from PySide6.QtCore import QCoreApplication, QElapsedTimer
from PySide6.QtWidgets import QApplication

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ / "prototypes"))

from test_viewport_carregador import CarregadorMalhas, _carregar, m600  # noqa: E402,F401
from viewport_qrhi.cubo_rhi import CuboViewport  # noqa: E402

NOVOS = ("limpar", "adicionar_lote", "enquadrar", "estatisticas")
assert all(hasattr(CuboViewport, n) for n in NOVOS), "CuboViewport sem os métodos da S03-T05 parte B"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Tela:
    def __init__(self, w):
        self.w, self.quadros = w, []
        w.frameSubmitted.connect(lambda: self.quadros.append(1))

    def desenhar(self, n=1):
        """Pede n quadros e espera cada um. Devolve a imagem do último."""
        for _ in range(n):
            antes = len(self.quadros)
            self.w.update()
            t = QElapsedTimer()
            t.start()
            while len(self.quadros) == antes and t.elapsed() < 5000:
                QCoreApplication.processEvents()
        return self.w.grab_image()


@pytest.fixture
def tela(app):
    w = CuboViewport(girar=False)
    w.resize(320, 240)
    t = _Tela(w)
    w.show()
    e = QElapsedTimer()
    e.start()
    while not t.quadros and e.elapsed() < 5000:
        QCoreApplication.processEvents()
    if w.rhi() is None or not t.quadros:
        w.close()
        pular_sem_tela(
            "sem contexto gráfico (QT_QPA_PLATFORM=%s): V1 a V4 precisam de tela real" % os.environ.get("QT_QPA_PLATFORM", "?")
        )
    yield t
    w.close()


def _pixels(img, passo=2):
    return [img.pixel(x, y) for x in range(0, img.width(), passo) for y in range(0, img.height(), passo)]


def test_v1_desenho_m600(tela, m600, tmp_path):
    w = tela.w
    w.limpar()
    fundo = tela.desenhar().pixel(0, 0)
    lotes, _, _ = _carregar(m600)
    for lt in lotes:
        w.adicionar_lote(lt)
    w.enquadrar()
    img = tela.desenhar(len(lotes) + 2)  # no máximo 1 lote vai à placa por quadro
    img.save(str(tmp_path / "v1.png"))
    assert w.estatisticas()["triangulos"] == 7200
    px = _pixels(img)
    assert len(set(px)) >= 3, "imagem quase uniforme"
    fracao = sum(1 for p in px if p != fundo) / len(px)
    assert 0.05 <= fracao <= 0.95, f"{fracao:.1%} dos pixels fora do fundo"


def test_v2_envio_incremental(tela, m600):
    w = tela.w
    w.limpar()
    lotes, _, _ = _carregar(m600, tamanho_bloco=200)
    assert len(lotes) >= 3
    ant_bytes = 0
    for k, lt in enumerate(lotes, start=1):
        w.adicionar_lote(lt)
        tela.desenhar(2)
        e = w.estatisticas()
        assert e["lotes"] == k and e["buffers_criados"] == 2 * k
        assert e["bytes_gpu"] > ant_bytes
        ant_bytes = e["bytes_gpu"]
    tela.desenhar(3)  # mais quadros, nenhum lote novo: nenhum buffer recriado
    assert w.estatisticas()["buffers_criados"] == 2 * len(lotes) and w.estatisticas()["bytes_gpu"] == ant_bytes


def test_v3_limpar(tela, m600):
    w = tela.w
    lotes, _, _ = _carregar(m600)
    for lt in lotes:
        w.adicionar_lote(lt)
    w.enquadrar()
    assert len(set(_pixels(tela.desenhar(len(lotes) + 2)))) >= 3  # havia o que limpar
    w.limpar()
    e = w.estatisticas()
    assert e["lotes"] == e["triangulos"] == e["vertices"] == e["bytes_gpu"] == 0
    assert len(set(_pixels(tela.desenhar(2)))) == 1, "depois de limpar() só a cor de fundo"


def test_v4_profundidade(tela, m600):
    w = tela.w
    w.limpar()
    lotes, _, _ = _carregar(m600)
    for lt in lotes:
        w.adicionar_lote(lt)
    w.enquadrar()
    tela.desenhar(len(lotes) + 2)  # perto e longe são recalculados a cada quadro
    assert w.camera.perto > 0 and w.camera.longe / w.camera.perto <= 10000


def test_v5_legado_passa_sem_alteracao():
    arqs = [str(RAIZ / "tests" / n) for n in ("test_viewport_qrhi.py", "test_viewport_camera.py")]
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *arqs],
                       cwd=str(RAIZ), env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]


def test_v4_cena_cabe_depois_de_arrastar(tela, m600):
    """P0b-4: depois de enquadrar() e de arrastar (mover), nenhum canto da caixa da cena fica além de
    camera.longe nem (fora da caixa) aquém de camera.perto. Longe: distância à câmera; perto: profundidade na direção da câmera."""
    w = tela.w
    w.limpar()
    lotes, _, _ = _carregar(m600)
    for lt in lotes:
        w.adicionar_lote(lt)
    lo = np.min([lt.objetos["caixa_min"].min(axis=0) for lt in lotes], axis=0).astype(np.float64)
    hi = np.max([lt.objetos["caixa_max"].max(axis=0) for lt in lotes], axis=0).astype(np.float64)
    w.enquadrar()
    cam = w.camera
    cam.mover(-600, 0, 480)
    cam.mover(0, 400, 480)
    tela.desenhar(len(lotes) + 2)  # perto e longe são recalculados a cada quadro
    _, _, frente = cam.eixos()
    cantos = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    prof = (cantos - cam.posicao) @ frente
    dist = float(np.linalg.norm(cantos - cam.posicao, axis=1).max())  # distância (mais estrita que a profundidade)
    assert dist < cam.longe, f"canto mais distante {dist:.1f} >= longe {cam.longe:.1f} (B-1: longe tem de partir do centro da cena)"
    dentro = bool(np.all(cam.posicao >= lo) and np.all(cam.posicao <= hi))
    assert dentro or prof.min() > cam.perto, f"canto mais próximo {prof.min():.3f} <= perto {cam.perto:.3f}"
