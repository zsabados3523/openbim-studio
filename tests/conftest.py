# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuração do pytest: põe app/ no caminho e força Qt sem tela."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# O Qt aplica a localidade do sistema ao processo ao criar o QApplication; em pt_BR o IfcOpenShell passa a gravar
# números com vírgula nos modelos gerados nos testes. Localidade "C" mantém a saída igual no CI e na máquina do PO.
os.environ["LC_ALL"] = "C"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
