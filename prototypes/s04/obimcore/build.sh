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


def erro(msg):  # sem assert: vale também com PYTHONOPTIMIZE
    sys.exit("OBIMCORE: reescrita do RPATH recusada: " + msg)


for arq in sys.argv[1:]:
    b = bytearray(open(arq, "rb").read())
    if b[:4] != b"\x7fELF" or b[4] != 2 or b[5] != 1:
        erro(f"{arq} não é ELF de 64 bits little-endian")
    shoff, = struct.unpack_from("<Q", b, 0x28)
    tam, num = struct.unpack_from("<HH", b, 0x3A)
    sec = [struct.unpack_from("<IIQQQQII", b, shoff + i * tam) for i in range(num)]  # nome, tipo, flags, end., posição, tamanho, link, info
    din = [s for s in sec if s[1] == 6]  # SHT_DYNAMIC; sh_link = .dynstr
    if len(din) != 1:
        erro(f"{arq}: sem .dynamic única")
    din = din[0]
    txt = sec[din[6]][4]
    rp, refs = [], []  # rp: RPATH/RUNPATH; refs: todo texto da .dynstr usado por outro nome
    for o in range(din[4], din[4] + din[5], 16):
        tag, val = struct.unpack_from("<qQ", b, o)
        if tag in (15, 29):
            rp.append(val)
        elif tag in (1, 14, 0x7ffffffd, 0x7fffffff):  # NEEDED, SONAME, AUXILIARY, FILTER
            refs.append(val)
    for s in sec:
        if s[6] != din[6] or s[1] not in (11, 0x6ffffffe, 0x6ffffffd):
            continue
        if s[1] == 11:  # .dynsym: st_name
            refs += [struct.unpack_from("<I", b, s[4] + k)[0] for k in range(0, s[5], 24)]
            continue
        p = s[4]
        for _ in range(s[7]):  # verneed (0x6ffffffe) ou verdef (0x6ffffffd)
            if s[1] == 0x6ffffffe:
                _, cnt, arq_nome, aux, prox = struct.unpack_from("<HHIII", b, p)
                refs.append(arq_nome)
            else:
                _, _, _, cnt, _, aux, prox = struct.unpack_from("<HHHHIII", b, p)
            q = p + aux
            for _ in range(cnt):
                if s[1] == 0x6ffffffe:
                    _, _, _, nome, prox_aux = struct.unpack_from("<IHHII", b, q)
                else:
                    nome, prox_aux = struct.unpack_from("<II", b, q)
                refs.append(nome)
                q += prox_aux
            p += prox
    if len(rp) != 1:
        erro(f"{arq}: esperava 1 entrada RPATH/RUNPATH, achei {len(rp)}")
    ini = txt + rp[0]
    fim = b.index(0, ini)
    novo = bytes(b[ini:fim]).split(b":")[0]
    if not novo.startswith(b"$ORIGIN"):
        erro(f"{arq}: o primeiro caminho não é relativo: {bytes(b[ini:fim])!r}")
    zero = ini + len(novo)  # daqui até `fim` o texto é apagado
    for r in refs:  # o ligador junta finais iguais na .dynstr: nenhum outro nome pode usar o trecho apagado
        o = txt + r
        if o < fim and b.index(0, o) > zero:
            erro(f"{arq}: outro nome da .dynstr (posição {r}) usa parte do texto do RPATH; apagar o corromperia")
    b[ini:fim] = novo + b"\0" * (fim - ini - len(novo))
    open(arq + ".novo", "wb").write(b)
    os.chmod(arq + ".novo", os.stat(arq).st_mode & 0o7777)  # mantém a permissão (rwx) do módulo
    os.replace(arq + ".novo", arq)
    print("OBIMCORE: RPATH de", arq.rsplit("/", 1)[-1], "=", novo.decode())
PY
fi
python - "$t0" "$t1" <<'PY'
import sys
a, b = map(float, sys.argv[1:3])
print(f"OBIMCORE: build {b-a:.1f} s")
PY
