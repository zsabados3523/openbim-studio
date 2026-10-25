# SPDX-License-Identifier: AGPL-3.0-or-later
"""Câmera orbital pura (sem Qt, testável sem tela). Eixo Z para cima (padrão BIM).

Matrizes são numpy 4x4 em notação de linhas (v' = M @ v), convenção OpenGL.

Congelado: este arquivo é a versão em Python da câmera. O produto usa a versão em C++
(`native/obimcore/nucleo/camera.*`). Só corrigir defeito aqui; recurso novo vai para o C++ (ADR-004).
"""
from __future__ import annotations

import math

import numpy as np

ELEVACAO_MAX = 89.0  # graus; evita gimbal lock no polo
DIST_MIN = 0.1
DIST_MAX = 10000.0


class Camera:
    def __init__(self, alvo=(0.0, 0.0, 0.0), distancia=3.2, azimute=-45.0, elevacao=30.0,
                 fov=45.0, proporcao=4 / 3, perto=0.05, longe=20000.0):
        self.alvo = np.array(alvo, dtype=np.float64)
        self.distancia = float(np.clip(distancia, DIST_MIN, DIST_MAX))
        self.azimute = float(azimute)  # graus, em torno de Z
        self.elevacao = float(np.clip(elevacao, -ELEVACAO_MAX, ELEVACAO_MAX))
        self.fov = fov
        self.proporcao = proporcao
        self.perto = perto
        self.longe = longe

    # --- geometria ---
    def _direcao(self) -> np.ndarray:
        az, el = math.radians(self.azimute), math.radians(self.elevacao)
        return np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])

    @property
    def posicao(self) -> np.ndarray:
        return self.alvo + self.distancia * self._direcao()

    def eixos(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(direita, cima, frente) da câmera; frente aponta para o alvo."""
        frente = -self._direcao()
        direita = np.cross(frente, [0.0, 0.0, 1.0])
        direita /= np.linalg.norm(direita)  # elevação limitada a ±89° => nunca zero
        cima = np.cross(direita, frente)
        return direita, cima, frente

    # --- ações ---
    def orbitar(self, dx: float, dy: float, graus_por_pixel: float = 0.4) -> None:
        self.azimute = (self.azimute - dx * graus_por_pixel) % 360.0
        self.elevacao = float(np.clip(self.elevacao + dy * graus_por_pixel, -ELEVACAO_MAX, ELEVACAO_MAX))

    def mover(self, dx: float, dy: float, altura_pixels: float = 480.0) -> None:
        """Desloca alvo e posição juntos, no plano da tela."""
        por_pixel = 2.0 * self.distancia * math.tan(math.radians(self.fov) / 2) / max(altura_pixels, 1.0)
        direita, cima, _ = self.eixos()
        self.alvo = self.alvo + (-dx * direita + dy * cima) * por_pixel

    def aproximar(self, passos: float) -> None:
        """`passos` > 0 aproxima, < 0 afasta (cada passo = 10%)."""
        self.distancia = float(np.clip(self.distancia * (0.9 ** float(np.clip(passos, -200, 200))), DIST_MIN, DIST_MAX))

    # --- matrizes ---
    def matriz_vista(self) -> np.ndarray:
        d, c, f = self.eixos()
        m = np.eye(4)
        m[0, :3], m[1, :3], m[2, :3] = d, c, -f
        m[:3, 3] = -m[:3, :3] @ self.posicao
        return m

    def matriz_projecao(self) -> np.ndarray:
        t = 1.0 / math.tan(math.radians(self.fov) / 2)
        n, f = self.perto, self.longe
        m = np.zeros((4, 4))
        m[0, 0] = t / self.proporcao
        m[1, 1] = t
        m[2, 2] = (f + n) / (n - f)
        m[2, 3] = 2 * f * n / (n - f)
        m[3, 2] = -1.0
        return m
