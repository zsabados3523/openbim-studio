#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Sonda 3b (ADR-005): compila e liga um programa que inclui ifcparse/file.h.
# Roda no CI (Linux e Windows) com o ambiente `openbim` ativo. Mede tempo limpo e incremental.
# Uso: bash run.sh <pasta-de-saida> <arquivo.ifc>
set -euo pipefail
OUT="$(realpath -m "$1")"; IFC="$(realpath "$2")"; B="$OUT/build_3b"
cd "$(dirname "$0")"
mkdir -p "$OUT"; rm -rf "$B"
# O cmake do IfcOpenShell pede os arquivos de desenvolvimento do zlib e do libxml2 (o ambiente só traz as bibliotecas).
"${CONDA_EXE:-conda}" install -y -c conda-forge --override-channels zlib libxml2-devel libboost-devel >/dev/null
# No Windows, sem -G o CMake escolhe o Visual Studio do runner; o MSVC (mesmo compilador das bibliotecas do conda-forge); o c++ do MinGW do runner não serve.
if [ "${RUNNER_OS:-}" = "Windows" ]; then GEN=(-A x64); else GEN=(-G Ninja); fi
if [ "${RUNNER_OS:-}" = "Windows" ]; then
  echo "--- diagnostico: arquivos boost no ambiente"
  ls "$CONDA_PREFIX/Library/lib" | grep -i boost | head -30 || true
  ls "$CONDA_PREFIX/Library/bin" | grep -i boost | head -10 || true
fi
agora() { python -c "import time; print(time.time())"; }
t0=$(agora)
cmake -S . -B "$B" "${GEN[@]}" -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake --build "$B" --config Release
t1=$(agora)
touch probe_3b.cpp
cmake --build "$B" --config Release
t2=$(agora)
exe=$(find "$B" -name 'probe_3b' -o -name 'probe_3b.exe' | head -1)
saida=$("$exe" "$IFC")
python - "$t0" "$t1" "$t2" "$saida" <<'PY'
import sys
a, b, c = map(float, sys.argv[1:4])
print(f"SONDA3B: build limpo {b-a:.1f} s | incremental {c-b:.1f} s | {sys.argv[4]}")
PY
