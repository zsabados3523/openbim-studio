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


def pytest_terminal_summary(terminalreporter):
    """RG-03: a contagem de pulos aparece sempre; no CI também vai para o resumo do job (GITHUB_STEP_SUMMARY)."""
    pulados = terminalreporter.stats.get("skipped", [])
    passou = len(terminalreporter.stats.get("passed", []))
    falhou = len(terminalreporter.stats.get("failed", [])) + len(terminalreporter.stats.get("error", []))
    linha = f"pytest: {passou} passaram, {falhou} falharam, {len(pulados)} PULADOS"
    terminalreporter.write_line(linha)
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        try:
            with open(destino, "a", encoding="utf-8") as f:
                f.write(f"{linha} ({' '.join(terminalreporter.config.args) or 'tests'})\n\n")
        except OSError:
            pass

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _registro_isolado(tmp_path, monkeypatch):
    """O registro de erros (F0-RG-11) grava numa pasta do teste e solta os ganchos ao fim; nada vai à pasta real do usuário."""
    monkeypatch.setenv("OPENBIM_LOG_DIR", str(tmp_path / "logs-openbim"))
    yield
    from openbim_app import registro
    registro.parar()
