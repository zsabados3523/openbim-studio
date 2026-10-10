# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuração do pytest: põe app/ no caminho e força Qt sem tela."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
