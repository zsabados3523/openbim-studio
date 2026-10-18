#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# F0-S04-T27: uma rodada da sonda_t27.py, em tela virtual (nunca a tela real), sob o cadeado da máquina compartilhada.
# uso: rodar_t27.sh N [--cena cheia|reduzida]   (saídas em ~/openbim-medicao/2026-10-18-T27/oficial; SAIDA_T27 troca a pasta, para ensaios)
set -u
M=$HOME/openbim-medicao/2026-10-18-T27; R="$(cd "$(dirname "$0")/../../.." && pwd)"
n=${1:?informe o número da rodada}; shift
O=${SAIDA_T27:-$M/oficial}; mkdir -p "$O" "$O/tmp"
uptime > "$O/t27_r$n.uptime"  # carga da máquina compartilhada ao pedir a vez; o JSON guarda a carga dentro do cadeado
exec flock "$HOME/openbim-medicao/medicao.lock" env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 LC_ALL=C \
  PYTHONPATH="$HOME/openbim-medicao/build" TMPDIR="$O/tmp" OBIM_LIMITE=${LIM:-3600} \
  timeout ${LIM:-3600} "$HOME/miniforge3/envs/openbim/bin/python" "$R/prototypes/s04/sondas/sonda_t27.py" rodada --rotulo t27 --saida "$O/t27_r$n.json" "$@" > "$O/t27_r$n.out" 2> "$O/t27_r$n.err"
