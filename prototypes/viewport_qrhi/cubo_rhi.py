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
BYTES_VERTICE_MALHA = 28  # pos 3xf32, normal 3xf32, cor 4xu8 (LoteMalha)


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
        self._cubo = True  # False depois de limpar()/adicionar_lote: só os lotes aparecem
        self._lotes: list[dict] = []
        self._buffers_criados = 0
        self._caixa = None  # (min, max) de tudo o que foi adicionado, no espaço do lote
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
        self._cubo = True
        self.update()

    # --- lotes de malha (S03-T05): 1 lote = 2 buffers na placa, no máximo 1 lote enviado por quadro ---
    def limpar(self) -> None:
        for e in self._lotes:
            self._soltar(e)
        self._lotes, self._caixa, self._cubo = [], None, False
        self.update()

    @staticmethod
    def _soltar(e: dict) -> None:
        for k in ("vbuf", "ibuf"):
            if e[k] is not None:
                e[k].deleteLater()
                e[k] = None

    def adicionar_lote(self, lote) -> None:
        """Guarda o lote (a T06 usa `objetos`, `pos` e `indices`); o envio à placa é no próximo desenho."""
        self._cubo = False
        self._lotes.append({"lote": lote, "vbuf": None, "ibuf": None})
        if len(lote.objetos):
            lo, hi = lote.objetos["caixa_min"].min(axis=0), lote.objetos["caixa_max"].max(axis=0)
            if self._caixa is not None:
                lo, hi = np.minimum(lo, self._caixa[0]), np.maximum(hi, self._caixa[1])
            self._caixa = (lo.astype(np.float64), hi.astype(np.float64))
        self.update()

    def enquadrar(self) -> None:
        if self._caixa is None:
            return
        lo, hi = self._caixa
        self.camera.alvo = (lo + hi) / 2
        raio = max(float(np.linalg.norm(hi - lo)) / 2, 0.1)
        self.camera.distancia = float(np.clip(raio / np.sin(np.radians(self.camera.fov) / 2) * 1.05, 0.1, 10000.0))
        self.update()

    def estatisticas(self) -> dict:
        enviados = [e for e in self._lotes if e["vbuf"] is not None]
        return {
            "lotes": len(self._lotes),
            "triangulos": sum(int(e["lote"].indices.size) // 3 for e in self._lotes),
            "vertices": sum(int(e["lote"].vertices.size) for e in self._lotes),
            "bytes_gpu": sum(int(e["lote"].vertices.nbytes + e["lote"].indices.nbytes) for e in enviados),
            "buffers_criados": self._buffers_criados,
            "pendentes": len(self._lotes) - len(enviados),
        }

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
        chave = (rhi, self.sampleCount())
        if self._pipeline is not None and self._rhi_antigo != chave:
            self._liberar_recursos()  # contexto ou alvo novo: solta o que é do C++ e refaz
        if self._pipeline is not None:
            return
        self._rhi_antigo = chave
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
        self._criar_pipeline_malha(rhi)
        self._pronto = True

    def _liberar_recursos(self) -> None:
        """Solta buffers, pipelines e bindings (dono = C++, então deleteLater) e marca tudo para reenvio."""
        for e in self._lotes:  # os lotes voltam a ser enviados, 1 por quadro
            self._soltar(e)
        for n in ("_vbuf", "_ibuf", "_ubuf", "_srb", "_pipeline", "_ubuf_m", "_srb_m", "_pipeline_m"):
            o = getattr(self, n, None)
            if o is not None:
                o.deleteLater()
            setattr(self, n, None)
        self._rhi_antigo, self._pronto, self._malha_nova = None, False, True

    def releaseResources(self) -> None:
        self._liberar_recursos()

    def _criar_pipeline_malha(self, rhi) -> None:
        self._ubuf_m = rhi.newBuffer(QRhiBuffer.Dynamic, QRhiBuffer.UniformBuffer, 80)
        self._ubuf_m.create()
        self._srb_m = rhi.newShaderResourceBindings()
        self._srb_m.setBindings([
            QRhiShaderResourceBinding.uniformBuffer(0, QRhiShaderResourceBinding.VertexStage, self._ubuf_m)
        ])
        self._srb_m.create()
        pipe = rhi.newGraphicsPipeline()
        pipe.setShaderStages([
            QRhiShaderStage(QRhiShaderStage.Vertex, self._carregar("malha.vert.qsb")),
            QRhiShaderStage(QRhiShaderStage.Fragment, self._carregar("malha.frag.qsb")),
        ])
        camada = QRhiVertexInputLayout()
        camada.setBindings([QRhiVertexInputBinding(BYTES_VERTICE_MALHA)])
        camada.setAttributes([
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Float3, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Float3, 12),
            QRhiVertexInputAttribute(0, 2, QRhiVertexInputAttribute.UNormByte4, 24),
        ])
        pipe.setVertexInputLayout(camada)
        pipe.setShaderResourceBindings(self._srb_m)
        pipe.setRenderPassDescriptor(self.renderTarget().renderPassDescriptor())
        pipe.setSampleCount(self.sampleCount())
        pipe.setDepthTest(True)
        pipe.setDepthWrite(True)  # sem descarte de faces de trás (cullMode padrão = nenhum)
        pipe.create()
        self._pipeline_m = pipe

    def _enviar_um_lote(self, rub) -> bool:
        """Cria os 2 buffers do primeiro lote ainda não enviado. Devolve True se enviou."""
        e = next((x for x in self._lotes if x["vbuf"] is None), None)
        if e is None:
            return False
        rhi, lote = self.rhi(), e["lote"]
        v, i = lote.vertices.tobytes(), lote.indices.tobytes()
        e["vbuf"] = rhi.newBuffer(QRhiBuffer.Immutable, QRhiBuffer.VertexBuffer, len(v))
        e["vbuf"].create()
        e["ibuf"] = rhi.newBuffer(QRhiBuffer.Immutable, QRhiBuffer.IndexBuffer, len(i))
        e["ibuf"].create()
        rub.uploadStaticBuffer(e["vbuf"], 0, len(v), v)
        rub.uploadStaticBuffer(e["ibuf"], 0, len(i), i)
        self._buffers_criados += 2
        return True

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
        tam = self.renderTarget().pixelSize()
        self.camera.proporcao = max(tam.width(), 1) / max(tam.height(), 1)
        if not self._cubo:
            self._render_lotes(cb, rub, rhi, tam)
            return
        if self._malha_nova:
            self._subir_malha(rub)
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

    def _render_lotes(self, cb, rub, rhi, tam) -> None:
        self._enviar_um_lote(rub)
        if any(e["vbuf"] is None for e in self._lotes):
            self.update()  # ainda há lotes na espera: o próximo vai no quadro seguinte
        cam = self.camera
        if self._caixa is not None:  # perto/longe a cada quadro (V4)
            raio = float(np.linalg.norm(self._caixa[1] - self._caixa[0])) / 2
            centro = (self._caixa[0] + self._caixa[1]) / 2  # B-1: distância ao centro da cena, não ao alvo
            cam.longe = (float(np.linalg.norm(cam.posicao - centro)) + raio) * 1.1
            cam.perto = max(cam.longe / 10000.0, 0.05)
        proj = QMatrix4x4(cam.matriz_projecao().flatten().tolist())
        vista = QMatrix4x4(cam.matriz_vista().flatten().tolist())
        mvp = rhi.clipSpaceCorrMatrix() * proj * vista
        luz = np.append(cam.eixos()[2], 0.0).astype(np.float32)  # direção em que a câmera olha
        rub.updateDynamicBuffer(self._ubuf_m, 0, 64, np.array(mvp.data(), dtype=np.float32).tobytes())
        rub.updateDynamicBuffer(self._ubuf_m, 64, 16, luz.tobytes())
        cb.beginPass(self.renderTarget(), QColor(30, 30, 40), QRhiDepthStencilClearValue(1.0, 0), rub)
        cb.setGraphicsPipeline(self._pipeline_m)
        cb.setViewport(QRhiViewport(0, 0, tam.width(), tam.height()))
        cb.setShaderResources()
        for e in self._lotes:  # uma chamada de desenho por lote
            if e["vbuf"] is not None:
                cb.setVertexInput(0, [(e["vbuf"], 0)], e["ibuf"], 0, QRhiCommandBuffer.IndexUInt32)
                cb.drawIndexed(int(e["lote"].indices.size))
        cb.endPass()
