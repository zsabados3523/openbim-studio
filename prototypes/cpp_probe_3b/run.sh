#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Sonda 3b (ADR-005): compila e liga um programa que inclui ifcparse/file.h.
# Roda no CI (Linux e Windows) com o ambiente `openbim` ativo, criado pela trava; não instala nada. Mede tempo limpo e incremental.
# Uso: bash run.sh <pasta-de-saida> <arquivo.ifc>
set -euo pipefail
OUT="$(realpath -m "$1")"; IFC="$(realpath "$2")"; B="$OUT/build_3b"
cd "$(dirname "$0")"
mkdir -p "$OUT"; rm -rf "$B"
# Nada é instalado aqui (cartão F0-S04-T01): o ambiente já vem com zlib, libxml2-devel e libboost-devel
# (environment.yml / arquivo de trava). Se faltar algo, avisa e para.
if [ "${RUNNER_OS:-}" = "Windows" ]; then INC="$CONDA_PREFIX/Library/include"; else INC="$CONDA_PREFIX/include"; fi
for f in zlib.h libxml2/libxml/parser.h boost/version.hpp; do
  [ -f "$INC/$f" ] || { echo "ERRO: falta $INC/$f; o ambiente precisa de zlib, libxml2-devel e libboost-devel (ver environment.yml)"; exit 2; }
done
# Prova do Qt6GuiPrivate: o CMake acha o componente (usado depois pelo desenho 3D); registra e segue.
Q="$OUT/qt_guiprivate"; rm -rf "$Q"; mkdir -p "$Q"
printf 'cmake_minimum_required(VERSION 3.20)\nproject(qt_guiprivate LANGUAGES CXX)\nfind_package(Qt6 REQUIRED COMPONENTS Gui GuiPrivate)\nmessage(STATUS "Qt6GuiPrivate achado: ${Qt6_DIR}")\n' > "$Q/CMakeLists.txt"
qt_saida=$(cmake -S "$Q" -B "$Q/b" -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" -DQT_NO_PRIVATE_MODULE_WARNING=ON 2>&1 || true)
if grep -q "Qt6GuiPrivate achado" <<<"$qt_saida"; then QT_OK=1; echo "QT6GUIPRIVATE: achado"; else QT_OK=0; echo "QT6GUIPRIVATE: NAO achado"; echo "$qt_saida" | tail -15; fi
# No Windows, sem -G o CMake escolhe o Visual Studio do runner; o MSVC (mesmo compilador das bibliotecas do conda-forge); o c++ do MinGW do runner não serve.
if [ "${RUNNER_OS:-}" = "Windows" ]; then GEN=(-A x64); else GEN=(-G Ninja); fi
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
[ "$QT_OK" = 1 ] || exit 3
