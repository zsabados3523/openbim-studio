# SPDX-License-Identifier: AGPL-3.0-or-later
"""S03-T05-C1, B-2: a leitura do pico de memória funciona (Linux e Windows), sem tela."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prototypes" / "viewport_qrhi"))

import medir  # noqa: E402


def test_pico_memoria_positivo():
    assert medir.pico_memoria_mb() > 0
