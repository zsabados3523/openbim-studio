# SPDX-License-Identifier: AGPL-3.0-or-later
"""Único arquivo com o desenho de baixo nível (QRhi): cubo colorido girando.

Se a API do Qt mudar entre versões, só este arquivo precisa de ajuste.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMatrix4x4,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
)
from PySide6.QtWidgets import QRhiWidget

try:  # execução como pacote (testes) ou como script
    from .camera import Camera
    from .selecao import Malha, pick as _pick
    from .viewport import Viewport
except ImportError:  # pragma: no cover
    from camera import Camera
    from selecao import Malha, pick as _pick
    from viewport import Viewport

SHADERS = Path(__file__).resolve().parent / "shaders"
FLOATS_POR_VERTICE = 6  # x, y, z, r, g, b


def cubo_padrao() -> tuple[np.ndarray, np.ndarray]:
    """Cubo de aresta 1 centrado na origem, uma cor por face (24 vértices)."""
    faces = [  # (normal, cor, u, v) com u x v = normal (anti-horário visto de fora)
        ((0, 0, 1), (1.0, 0.2, 0.2), (1, 0, 0), (0, 1, 0)),
        ((0, 0, -1), (0.2, 1.0, 0.2), (0, 1, 0), (1, 0, 0)),
        ((1, 0, 0), (0.2, 0.4, 1.0), (0, 1, 0), (0, 0, 1)),
        ((-1, 0, 0), (1.0, 1.0, 0.2), (0, 0, 1), (0, 1, 0)),
        ((0, 1, 0), (1.0, 0.2, 1.0), (0, 0, 1), (1, 0, 0)),
        ((0, -1, 0), (0.2, 1.0, 1.0), (1, 0, 0), (0, 0, 1)),
    ]
    verts, idx = [], []
    for n, cor, u, v in faces:
        n, u, v = (np.array(a, dtype=np.float32) for a in (n, u, v))
        base = len(verts)
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            pos = 0.5 * n + 0.5 * su * u + 0.5 * sv * v
            verts.append([*pos, *cor])
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


class CuboViewport(QRhiWidget, Viewport):
    """Widget 3D (QRhiWidget) que mostra uma malha colorida girando."""

    clicado = Signal(object)  # id do objeto clicado (ou None) após clique esquerdo sem arrasto

    def __init__(self, parent=None, api: QRhiWidget.Api | None = None, girar: bool = True):
        super().__init__(parent)
        if api is not None:
            self.setApi(api)  # antes de mostrar a janela
        self._vertices, self._indices = cubo_padrao()
        self._malha_nova = True
        self._selecao = None
        self._angulo = 0.0
        self._girar = girar
        self._pronto = False
        self._pipeline = None
        self._rhi_antigo = None
        self.camera = Camera()
        self._ultimo: QPointF | None = None
        if girar:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._passo)
            self._timer.start(16)

    # --- interface Viewport ---
    def set_mesh(self, vertices, indices) -> None:
        self._vertices = np.ascontiguousarray(vertices, dtype=np.float32).reshape(-1, FLOATS_POR_VERTICE)
        self._indices = np.ascontiguousarray(indices, dtype=np.uint32).reshape(-1)
        self._malha_nova = True
        self._selecao = None  # malha de objetos para o pick; None = um objeto único (id 1) com esta malha
        self.update()

    def set_objetos(self, malha: Malha) -> None:
        """Define os objetos (com id) usados pelo `pick`; não muda o que é desenhado."""
        self._selecao = malha

    def pick(self, x: float, y: float):
        """Id do objeto sob o ponto (x, y) em pixels lógicos do widget, ou None.

        Só a razão x/largura importa, então vale em telas com escala (HiDPI), desde que x, y e o
        tamanho do widget estejam na mesma unidade (aqui, lógica).
        """
        if self._selecao is None:
            self._selecao = Malha([(1, self._vertices[:, :3], self._indices)])
        inv = np.linalg.inv(self._matriz_modelo())
        return _pick(self._selecao, self.camera, x, y, self.width(), self.height(), inv)

    def _matriz_modelo(self) -> np.ndarray:
        m = QMatrix4x4()
        m.rotate(self._angulo, 0.3, 1.0, 0.2)
        return np.array(m.data(), dtype=np.float64).reshape(4, 4).T  # data() vem coluna a coluna

    def grab_image(self) -> QImage:
        return self.grabFramebuffer()

    # --- mouse: esquerdo orbita; meio ou shift+esquerdo move; roda aproxima ---
    def mousePressEvent(self, ev) -> None:
        self._ultimo = ev.position()
        self._inicio = ev.position()
        self._arrastou = False

    def mouseReleaseEvent(self, ev) -> None:
        self._ultimo = None
        if ev.button() == Qt.LeftButton and not getattr(self, "_arrastou", True):
            p = ev.position()
            self.clicado.emit(self.pick(p.x(), p.y()))

    def mouseMoveEvent(self, ev) -> None:
        if self._ultimo is None:
            return
        pos = ev.position()
        if (pos - self._inicio).manhattanLength() > 4:
            self._arrastou = True
        dx, dy = pos.x() - self._ultimo.x(), pos.y() - self._ultimo.y()
        self._ultimo = pos
        botoes = ev.buttons()
        if botoes & Qt.MiddleButton or (botoes & Qt.LeftButton and ev.modifiers() & Qt.ShiftModifier):
            self.camera.mover(dx, dy, self.height())
        elif botoes & Qt.LeftButton:
            self.camera.orbitar(dx, dy)
        else:
            return
        self.update()

    def wheelEvent(self, ev) -> None:
        self.camera.aproximar(ev.angleDelta().y() / 120.0)
        self.update()

    # --- giro ---
    def _passo(self) -> None:
        self._angulo = (self._angulo + 1.0) % 360.0
        self.update()

    def definir_angulo(self, graus: float) -> None:
        self._angulo = graus

    # --- QRhiWidget ---
    def initialize(self, cb) -> None:
        rhi = self.rhi()
        if self._pipeline is not None and self._rhi_antigo is not rhi:
            self._pipeline = None  # contexto novo: recursos antigos não valem mais
        if self._pipeline is not None:
            return
        self._rhi_antigo = rhi
        self._vbuf = self._ibuf = None
        self._ubuf = rhi.newBuffer(QRhiBuffer.Dynamic, QRhiBuffer.UniformBuffer, 64)
        self._ubuf.create()
        self._srb = rhi.newShaderResourceBindings()
        self._srb.setBindings([
            QRhiShaderResourceBinding.uniformBuffer(
                0,
                QRhiShaderResourceBinding.VertexStage,
                self._ubuf,
            )
        ])
        self._srb.create()

        pipe = rhi.newGraphicsPipeline()
        pipe.setShaderStages([
            QRhiShaderStage(QRhiShaderStage.Vertex, self._carregar("cubo.vert.qsb")),
            QRhiShaderStage(QRhiShaderStage.Fragment, self._carregar("cubo.frag.qsb")),
        ])
        camada = QRhiVertexInputLayout()
        camada.setBindings([QRhiVertexInputBinding(FLOATS_POR_VERTICE * 4)])
        camada.setAttributes([
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Float3, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Float3, 12),
        ])
        pipe.setVertexInputLayout(camada)
        pipe.setShaderResourceBindings(self._srb)
        pipe.setRenderPassDescriptor(self.renderTarget().renderPassDescriptor())
        pipe.setSampleCount(self.sampleCount())
        pipe.setDepthTest(True)
        pipe.setDepthWrite(True)
        pipe.setCullMode(QRhiGraphicsPipeline.Back)
        pipe.setFrontFace(QRhiGraphicsPipeline.CCW)
        pipe.create()
        self._pipeline = pipe
        self._malha_nova = True
        self._pronto = True

    def _carregar(self, nome: str) -> QShader:
        sh = QShader.fromSerialized((SHADERS / nome).read_bytes())
        if not sh.isValid():
            raise RuntimeError(f"shader inválido: {nome}")
        return sh

    def _subir_malha(self, rub) -> None:
        rhi = self.rhi()
        for b in (self._vbuf, self._ibuf):
            if b is not None:
                b.deleteLater()
        self._vbuf = rhi.newBuffer(QRhiBuffer.Immutable, QRhiBuffer.VertexBuffer, self._vertices.nbytes)
        self._vbuf.create()
        self._ibuf = rhi.newBuffer(QRhiBuffer.Immutable, QRhiBuffer.IndexBuffer, self._indices.nbytes)
        self._ibuf.create()
        rub.uploadStaticBuffer(self._vbuf, 0, self._vertices.nbytes, self._vertices.tobytes())
        rub.uploadStaticBuffer(self._ibuf, 0, self._indices.nbytes, self._indices.tobytes())
        self._n_indices = int(self._indices.size)
        self._malha_nova = False

    def render(self, cb) -> None:
        rhi = self.rhi()
        rub = rhi.nextResourceUpdateBatch()
        if self._malha_nova:
            self._subir_malha(rub)
        tam = self.renderTarget().pixelSize()
        self.camera.proporcao = max(tam.width(), 1) / max(tam.height(), 1)
        proj = QMatrix4x4(self.camera.matriz_projecao().flatten().tolist())
        vista = QMatrix4x4(self.camera.matriz_vista().flatten().tolist())
        modelo = QMatrix4x4()
        modelo.rotate(self._angulo, 0.3, 1.0, 0.2)  # igual a _matriz_modelo (usada no pick)
        mvp = rhi.clipSpaceCorrMatrix() * proj * vista * modelo
        dados = np.array(mvp.data(), dtype=np.float32)  # coluna a coluna, como o GLSL espera
        rub.updateDynamicBuffer(self._ubuf, 0, 64, dados.tobytes())

        cb.beginPass(self.renderTarget(), QColor(30, 30, 40), QRhiDepthStencilClearValue(1.0, 0), rub)
        cb.setGraphicsPipeline(self._pipeline)
        cb.setViewport(QRhiViewport(0, 0, tam.width(), tam.height()))
        cb.setShaderResources()
        cb.setVertexInput(0, [(self._vbuf, 0)], self._ibuf, 0, QRhiCommandBuffer.IndexUInt32)
        cb.drawIndexed(self._n_indices)
        cb.endPass()
