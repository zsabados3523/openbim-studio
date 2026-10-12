# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interface própria do viewport 3D (o resto do programa só conhece esta)."""
from __future__ import annotations

from PySide6.QtGui import QImage


class Viewport:
    """Contrato mínimo de um viewport 3D.

    Não usa `abc.ABC` de propósito: widgets do Qt têm metaclasse própria e
    misturar as duas dá erro. Quem herdar deve implementar os dois métodos.
    """

    def set_mesh(self, vertices, indices) -> None:
        """Troca a malha. `vertices`: N linhas de 6 floats (x, y, z, r, g, b);
        `indices`: triângulos, 3 inteiros por face."""
        raise NotImplementedError

    def grab_image(self) -> QImage:
        """Devolve o quadro atual como imagem."""
        raise NotImplementedError

    # --- lotes de malha do IFC (S03-T05) ---
    def limpar(self) -> None:
        """Remove todos os lotes e solta os buffers da placa."""
        raise NotImplementedError

    def adicionar_lote(self, lote) -> None:
        """Só na thread da interface. Cria 2 buffers para este lote; nunca recria os anteriores."""
        raise NotImplementedError

    def enquadrar(self) -> None:
        """Ajusta alvo, distância e planos da câmera à caixa de tudo que foi adicionado."""
        raise NotImplementedError

    def estatisticas(self) -> dict:
        """`lotes`, `triangulos`, `vertices`, `bytes_gpu`, `buffers_criados`."""
        raise NotImplementedError
