# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lançador do pacote Windows: usa o Python da pasta env\\ e o código em app\\.

Não confere hash nem assinatura de nenhuma DLL: você pode trocar as bibliotecas (ver LGPL-COMO-TROCAR.md).
"""
import os
import sys

aqui = os.path.dirname(os.path.abspath(__file__))  # ...\app
raiz = os.path.dirname(aqui)
env = os.path.join(raiz, "env")
for sub in ("Library\\bin", "Library\\mingw-w64\\bin", "Library\\usr\\bin", "bin", "Scripts"):
    pasta = os.path.join(env, sub)
    if os.path.isdir(pasta):
        os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")
        os.add_dll_directory(pasta)
os.environ["PYTHONNOUSERSITE"] = "1"
sys.path.insert(0, aqui)

from openbim_app.main import main  # noqa: E402

sys.exit(main())
