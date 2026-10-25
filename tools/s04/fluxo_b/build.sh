#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Constrói o módulo `fluxo_b_paredes`. Roda com o ambiente `openbim` ativo; não instala nada.
# Uso: bash build.sh <pasta-de-saida>   (cria <pasta-de-saida>/fluxo_b_paredes*.so|.pyd; ponha a pasta no PYTHONPATH; o teste também a lê de OBIM_S04_FLUXO_B_DIR)
set -euo pipefail
OUT="$(python -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")"; B="$OUT/build_fluxo_b"
cd "$(dirname "$0")"
: "${CONDA_PREFIX:?ative o ambiente openbim}"
[ "${CLEAN:-}" = 1 ] && rm -rf "$B" "$OUT"/fluxo_b_paredes*
mkdir -p "$OUT"
if [ "${RUNNER_OS:-}" = "Windows" ]; then GEN=(-A x64); else GEN=(-G Ninja); fi  # Windows: MSVC (mesmo compilador do conda-forge)
cmake -S . -B "$B" "${GEN[@]}" -DCMAKE_BUILD_TYPE=Release -DOBIM_SAIDA="$OUT" -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake --build "$B" --config Release
