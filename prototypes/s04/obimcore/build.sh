#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Constrói o módulo `obimcore` (S04-T03) e anota os tempos. Roda com o ambiente `openbim` ativo; não instala nada.
# Uso: bash build.sh <pasta-de-saida>   (cria <pasta-de-saida>/obimcore/ com __init__.py e o módulo; ponha a pasta no PYTHONPATH)
# Primeira execução = build limpo; as seguintes são incrementais. Para medir os dois: CLEAN=1 apaga o build antes.
set -euo pipefail
OUT="$(python -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")"; B="$OUT/build_obimcore"  # caminho nativo (no Windows, o do CMake)
cd "$(dirname "$0")"
: "${CONDA_PREFIX:?ative o ambiente openbim}"
[ "${CLEAN:-}" = 1 ] && rm -rf "$B" "$OUT/obimcore"
mkdir -p "$OUT/obimcore"
# No Windows, o gerador do Visual Studio (MSVC, mesmo compilador do conda-forge); o c++ do MinGW do runner não serve.
if [ "${RUNNER_OS:-}" = "Windows" ]; then GEN=(-A x64); else GEN=(-G Ninja); fi
# Pacote Python: o __init__ importa o ifcopenshell ANTES do módulo (esquemas registrados) e, no Windows, mostra ao carregador
# onde estão as DLLs do ambiente (o PATH não vale para extensões a partir do Python 3.8).
cat > "$OUT/obimcore/__init__.py" <<'PY'
# SPDX-License-Identifier: AGPL-3.0-or-later
import os
import sys
if sys.platform == "win32":
    for _d in (os.path.join(sys.prefix, "Library", "bin"), os.path.join(sys.prefix, "Library", "mingw-w64", "bin")):
        if os.path.isdir(_d):
            os.add_dll_directory(_d)
import ifcopenshell  # noqa: E402,F401  (antes do módulo C++)
from . import _obimcore  # noqa: E402
globals().update({k: v for k, v in vars(_obimcore).items() if not k.startswith("_")})
PY
agora() { python -c "import time; print(time.time())"; }
t0=$(agora)
cmake -S . -B "$B" "${GEN[@]}" -DCMAKE_BUILD_TYPE=Release -DOBIM_SAIDA="$OUT" -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake --build "$B" --config Release
t1=$(agora)
python - "$t0" "$t1" <<'PY'
import sys
a, b = map(float, sys.argv[1:3])
print(f"OBIMCORE: build {b-a:.1f} s")
PY
