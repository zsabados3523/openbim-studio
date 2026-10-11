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
