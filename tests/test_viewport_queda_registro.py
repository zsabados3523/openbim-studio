# SPDX-License-Identifier: AGPL-3.0-or-later
"""Queda do processo de geometria deixa o motivo no registro (F0-RG-11, achado B21)."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_viewport_processo import _tempo_carga, mapeadas1, requer_a, requer_limite  # noqa: E402,F401


@requer_a
@requer_limite
def test_queda_do_filho_grava_o_codigo_de_saida(mapeadas1, monkeypatch, caplog):
    caminho, [(id_l, guid)] = mapeadas1
    monkeypatch.setenv("OBIM_TESTE_MATAR_FILHO", guid)
    with caplog.at_level(logging.WARNING, logger="openbim.viewport"):
        _, r, _ = _tempo_carga(caminho)
    assert r.estado == "concluido" and [s[0] for s in r.simplificadas] == [id_l]
    assert "código de saída 3" in caplog.text  # os._exit(3) do gancho de teste
    assert "código de saída 3" in r.simplificadas[0][4]  # e na explicação mostrada ao usuário
