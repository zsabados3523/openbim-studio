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
# Linux (T17a): o g++ do conda acrescenta ao RPATH o caminho ABSOLUTO do ambiente de desenvolvimento. Dentro do pacote isso seria uma biblioteca
# de fora (R1-e), então fica só o primeiro caminho, o relativo ao pacote ($ORIGIN/../../env/lib). Reescreve a string no lugar (não há patchelf).
if [ "$(uname -s)" = Linux ]; then
python - "$OUT"/obimcore/_obimcore*.so <<'PY'
import os, struct, sys
for arq in sys.argv[1:]:
    b = bytearray(open(arq, "rb").read())
    assert b[:5] == b"\x7fELF\x02", arq
    shoff, = struct.unpack_from("<Q", b, 0x28)
    entsize, num = struct.unpack_from("<HH", b, 0x3A)
    sec = [struct.unpack_from("<IIQQQQII", b, shoff + i * entsize) for i in range(num)]
    din = next(s for s in sec if s[1] == 6)  # SHT_DYNAMIC; sh_link = tabela de textos
    txt = sec[din[6]][4]
    achou = 0
    for o in range(din[4], din[4] + din[5], 16):
        tag, val = struct.unpack_from("<qQ", b, o)
        if tag in (15, 29):  # DT_RPATH, DT_RUNPATH
            ini = txt + val
            fim = b.index(0, ini)
            novo = bytes(b[ini:fim]).split(b":")[0]
            assert novo.startswith(b"$ORIGIN"), (arq, bytes(b[ini:fim]))
            b[ini:fim] = novo + b"\0" * (fim - ini - len(novo))
            achou += 1
    assert achou == 1, f"{arq}: esperava 1 RPATH, achei {achou}"
    open(arq + ".novo", "wb").write(b)
    os.replace(arq + ".novo", arq)
    print("OBIMCORE: RPATH de", arq.rsplit("/", 1)[-1], "=", novo.decode())
PY
fi
python - "$t0" "$t1" <<'PY'
import sys
a, b = map(float, sys.argv[1:3])
print(f"OBIMCORE: build {b-a:.1f} s")
PY
