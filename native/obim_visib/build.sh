#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Constroi o modulo `obimvisib` no diretorio de saida informado, sem instalar no ambiente.
set -euo pipefail
OUT="$(python -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")"
B="$OUT/build_obimvisib"
cd "$(dirname "$0")"
: "${CONDA_PREFIX:?ative o ambiente openbim}"
[ "${CLEAN:-}" = 1 ] && rm -rf "$B" "$OUT/obimvisib"
mkdir -p "$OUT/obimvisib"
if [ "${RUNNER_OS:-}" = "Windows" ]; then GEN=(-A x64); else GEN=(-G Ninja); fi

cat > "$OUT/obimvisib/__init__.py" <<'PY'
# SPDX-License-Identifier: AGPL-3.0-or-later
from . import _obimvisib
globals().update({k: v for k, v in vars(_obimvisib).items() if not k.startswith("_")})
PY

cmake -S . -B "$B" "${GEN[@]}" -DCMAKE_BUILD_TYPE=Release -DOBIM_SAIDA="$OUT" -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake --build "$B" --config Release

if [ "$(uname -s)" = Linux ]; then
python - "$OUT"/obimvisib/_obimvisib*.so <<'PY'
import os, struct, sys

def erro(msg):
    sys.exit("OBIMVISIB: RPATH invalido: " + msg)

for arq in sys.argv[1:]:
    b = bytearray(open(arq, "rb").read())
    if b[:4] != b"\x7fELF" or b[4] != 2 or b[5] != 1:
        erro(f"{arq} nao e ELF 64-bit little-endian")
    shoff, = struct.unpack_from("<Q", b, 0x28)
    tam, num = struct.unpack_from("<HH", b, 0x3A)
    sec = [struct.unpack_from("<IIQQQQII", b, shoff + i * tam) for i in range(num)]
    din = [s for s in sec if s[1] == 6]
    if len(din) != 1:
        erro(f"{arq}: sem .dynamic unica")
    din = din[0]
    txt = sec[din[6]][4]
    rp, refs = [], []
    for o in range(din[4], din[4] + din[5], 16):
        tag, val = struct.unpack_from("<qQ", b, o)
        if tag in (15, 29):
            rp.append(val)
        elif tag in (1, 14, 0x7ffffffd, 0x7fffffff):
            refs.append(val)
    for s in sec:
        if s[6] == din[6] and s[1] == 11:
            refs += [struct.unpack_from("<I", b, s[4] + k)[0] for k in range(0, s[5], 24)]
    if len(rp) != 1:
        erro(f"{arq}: esperava 1 entrada RPATH/RUNPATH, achei {len(rp)}")
    ini = txt + rp[0]
    fim = b.index(0, ini)
    novo = bytes(b[ini:fim]).split(b":")[0]
    if not novo.startswith(b"$ORIGIN"):
        erro(f"{arq}: primeiro caminho nao e relativo: {bytes(b[ini:fim])!r}")
    zero = ini + len(novo)
    for r in refs:
        o = txt + r
        if o < fim and b.index(0, o) > zero:
            erro(f"{arq}: outro nome na .dynstr usa parte do RPATH")
    b[ini:fim] = novo + b"\0" * (fim - ini - len(novo))
    open(arq + ".novo", "wb").write(b)
    os.chmod(arq + ".novo", os.stat(arq).st_mode & 0o7777)
    os.replace(arq + ".novo", arq)
PY
fi
