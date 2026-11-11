# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuração do pytest: põe app/ no caminho e força Qt sem tela."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# O Qt aplica a localidade do sistema ao processo ao criar o QApplication; em pt_BR o IfcOpenShell passa a gravar
# números com vírgula nos modelos gerados nos testes. Localidade "C" mantém a saída igual em todas as máquinas.
os.environ["LC_ALL"] = "C"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "geometria"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from obrigatorio import ligar_ci  # noqa: E402

ligar_ci()  # OBIM_CI=1: liga as chaves de obrigatório antes de qualquer teste ler o ambiente

if os.environ.get("GITHUB_ACTIONS"):
    # Guarda de travamento no CI: se a sessão passar de 40 min, grava no resumo do job o teste em andamento e a pilha de
    # todas as threads e encerra (o pytest captura o stderr, então o resumo é o único lugar que sobrevive).
    import threading
    import time
    import traceback

    _atual = {"id": "?", "t": time.monotonic()}

    def pytest_runtest_logstart(nodeid, location):
        _atual["id"], _atual["t"] = nodeid, time.monotonic()

    def _vigia():
        time.sleep(2400)
        destino = os.environ.get("GITHUB_STEP_SUMMARY")
        linhas = [f"### TRAVADO: teste em andamento {_atual['id']} ha {time.monotonic() - _atual['t']:.0f} s"]
        for tid, fr in sys._current_frames().items():
            linhas.append(f"thread {tid}:")
            linhas.extend("    " + x.rstrip() for x in traceback.format_stack(fr)[-8:])
        if destino:
            with open(destino, "a", encoding="utf-8") as f:
                f.write("\n".join(linhas) + "\n")
        os._exit(1)

    threading.Thread(target=_vigia, daemon=True).start()


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
    """O registro de erros grava numa pasta do teste e solta os ganchos ao fim; nada vai à pasta real do usuário."""
    monkeypatch.setenv("OPENBIM_LOG_DIR", str(tmp_path / "logs-openbim"))
    yield
    from openbim_app import registro
    registro.parar()
