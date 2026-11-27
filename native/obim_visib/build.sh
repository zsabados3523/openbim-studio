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


def erro(msg):  # sem assert: vale também com PYTHONOPTIMIZE
    sys.exit("OBIMVISIB: reescrita do RPATH recusada: " + msg)


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
    print("OBIMVISIB: RPATH de", arq.rsplit("/", 1)[-1], "=", novo.decode())
PY
fi
