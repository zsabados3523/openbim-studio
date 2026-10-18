#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# F0-S04-T25: uma rodada da sonda_t25.py, em tela virtual (nunca a tela real), sob o cadeado da máquina compartilhada.
# uso: rodar_t25.sh ROTULO NUM [args da sonda]   (ROTULO: sint3000, sint10k, sint20k, sint42k ou m25 (arquivo real); saídas em ~/openbim-medicao/2026-10-18-T25/r; SAIDA_T25 troca a pasta, para ensaios)
set -u
M=$HOME/openbim-medicao/2026-10-18-T25; R="$(cd "$(dirname "$0")/../../.." && pwd)"
rot=$1; n=$2; O=${SAIDA_T25:-$M/r}; mkdir -p "$O" "$M/tmp"
declare -A N=([sint3000]=3000 [sint10k]=10000 [sint20k]=20000 [sint42k]=41600)
if [ "$rot" = m25 ]; then FONTE=(--ifc "${IFC_M25:?defina IFC_M25 com o caminho do arquivo de 25 MB}"); else FONTE=(--sintetica "${N[$rot]}"); fi  # m25: arquivo de 25 MB do PO (liberado no chat em 2026-10-18); o caminho vem de IFC_M25 e nunca entra no repositório
exec flock "$HOME/openbim-medicao/medicao.lock" env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 LC_ALL=C \
  PYTHONPATH="$HOME/openbim-medicao/build" TMPDIR="$M/tmp" OBIM_LIMITE=${LIM:-1500} \
  timeout ${LIM:-1500} "$HOME/miniforge3/envs/openbim/bin/python" "$R/prototypes/s04/sondas/sonda_t25.py" rodada --rotulo "$rot" "${FONTE[@]}" --saida "$O/${rot}_r$n.json" "${@:3}" > "$O/${rot}_r$n.out" 2> "$O/${rot}_r$n.err"
