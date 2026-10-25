# SPDX-License-Identifier: AGPL-3.0-or-later
"""Caso gráfico de coordenada UTM (tests/test_s04_fluxo_a.py): modelo em coordenada UTM aberto numa cena com janela, câmera em coordenada do
mundo, seleção e desenho. Roda num processo próprio (`python s04_fluxo_utm_aux.py utm mais|menos`), sob xvfb-run, nunca na tela real."""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
from s04_fluxo_aux import PAREDE, TIPO, assentar


def c_utm(res, sinal):
    import fluxo_a
    from test_s04_viewport import captura
    base = (333000.0, 7400000.0, 0.0) if sinal == "mais" else (-333000.0, -7400000.0, -50.0)
    pasta = Path(tempfile.mkdtemp())
    f0 = fluxo_a.FluxoA(None, janela=False, saida=pasta)  # as paredes já nascem em UTM, antes de qualquer lote ir à cena
    f0.executar(TIPO)
    gs = [f0.executar(PAREDE)[0] for _ in range(3)]
    for g in gs:
        f0.executar({"cmd": "mover", "alvo": g, "dx": base[0], "dy": base[1], "dz": base[2]})
    f0.executar({"cmd": "gravar", "arquivo": "utm.ifc"})
    f = fluxo_a.FluxoA(str(pasta / "utm.ifc"), janela=True, saida=pasta)
    # parede do meio: x de 5 a 9, y 0,075, z 1,4 de altura do centro (no mundo)
    f.executar({"cmd": "camera", "alvo": [7.0 + base[0], 0.075 + base[1], 1.4 + base[2]], "distancia": 30.0, "azimute": -90.0, "elevacao": 20.0})
    f.executar({"cmd": "abrir"})  # nenhum lote pode ser recusado pela cena
    assentar(f)
    centro = lambda: (f.executar({"cmd": "selecionar", "x": "centro", "y": "centro"}) or [None])[0]  # noqa: E731
    res.update(g1=gs[1], janela=bool(f.janela_principal and f.janela_principal.isVisible()), viva=bool(f.cena.viva()), sel_antes=centro())
    antes = captura(f.cena).copy()
    f.executar({"cmd": "mover", "alvo": gs[1], "dx": 0.0, "dy": 0.0, "dz": 1.0})
    assentar(f)
    depois = captura(f.cena).copy()
    res["muda"] = int((np.abs(antes.astype(int) - depois.astype(int)).max(axis=2) > 24).sum())
    res["sel_depois"] = centro()
    f.fechar()
    return res


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 600)) - 20, exit=True)
    nome, *resto = sys.argv[1:]
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + nome]({}, *resto)
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
