"""TEMPORARIO (nao mesclar): gera o dourado do Windows com o motor de referencia e imprime em base64."""
import base64, hashlib, io, sys
import numpy as np
import pytest

from obim_geometria.visibilidade import linhas_visiveis_multi
from test_s06_t22a_visibilidade_equivalencia_oraculo import _empacotar, todas


@pytest.mark.skipif(sys.platform != "win32", reason="so no Windows")
def test_gera_dourado_windows(capsys):
    out = {}
    for nome, f in todas().items():
        out.update({f"{nome}/{k}": v for k, v in _empacotar(linhas_visiveis_multi(f())).items()})
    buf = io.BytesIO()
    np.savez_compressed(buf, **out)
    raw = buf.getvalue()
    b = base64.b64encode(raw).decode()
    import os
    os.makedirs("out", exist_ok=True)
    open("out/s06_t22a_dourado_windows.npz", "wb").write(raw)
    with capsys.disabled():
        print("\n===GOLD_BEGIN===", flush=True)
        for i in range(0, len(b), 200):
            print(b[i:i + 200], flush=True)
        print("===GOLD_END===", flush=True)
        print("GOLD_SHA256", hashlib.sha256(raw).hexdigest(), len(raw), len(out), flush=True)
