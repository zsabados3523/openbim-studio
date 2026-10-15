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


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _registro_isolado(tmp_path, monkeypatch):
    """O registro de erros (F0-RG-11) grava numa pasta do teste e solta os ganchos ao fim; nada vai à pasta real do usuário."""
    monkeypatch.setenv("OPENBIM_LOG_DIR", str(tmp_path / "logs-openbim"))
    yield
    from openbim_app import registro
    registro.parar()
