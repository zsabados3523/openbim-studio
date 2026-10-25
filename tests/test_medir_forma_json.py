# SPDX-License-Identifier: AGPL-3.0-or-later
"""O JSON do medir.py traz reinicios, registro_reinicio e desenho (só a forma; modelo gerado, sem IFC de terceiros)."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototypes" / "viewport_qrhi"))
sys.path.insert(0, str(RAIZ / "scripts"))

import medir  # noqa: E402
import pytest  # noqa: E402
from gerar_modelo_grande import gerar  # noqa: E402


def test_json_traz_reinicios_e_desenho(tmp_path):
    pytest.importorskip("PySide6")
    c = tmp_path / "m12.ifc"
    gerar(c, paredes=12, por_andar=6)
    try:
        r = json.loads(json.dumps(medir.medir(c, 1, 3)))
    except SystemExit as e:  # sem contexto gráfico (offscreen): não há o que medir
        pytest.skip(str(e))
    assert isinstance(r["reinicios"], list) and isinstance(r["registro_reinicio"], list)
    assert isinstance(r["desenho"]["info"], str) and isinstance(r["desenho"]["software"], bool)
    assert r["estado"] == "concluido"
