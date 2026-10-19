#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# F0-S04-T32a: uma rodada da sonda_t32.py, em tela virtual (nunca a tela real), sob o cadeado da máquina compartilhada.
# uso: rodar_t32.sh N hoje|consertado   (saídas em ~/openbim-medicao/2026-10-19-T32; SAIDA_T32 troca a pasta, para ensaios)
# O módulo medido é o do ramo descartável, construído em $M/build (build.sh de prototypes/s04/obimcore). No modo consertado a variável
# OBIM_SEM_CONSERTADO=1 liga o `sem` consertado do ramo; no modo hoje ela fica vazia.
set -u
M=$HOME/openbim-medicao/2026-10-19-T32; R="$(cd "$(dirname "$0")/../../.." && pwd)"
n=${1:?informe o número da rodada}; modo=${2:?informe hoje ou consertado}
case "$modo" in hoje) SEM="" ;; consertado) SEM=1 ;; *) echo "modo inválido: $modo" >&2; exit 2 ;; esac
O=${SAIDA_T32:-$M}; mkdir -p "$O" "$O/tmp"
uptime > "$O/t32_${modo}_r$n.uptime"  # carga da máquina compartilhada ao pedir a vez; o JSON guarda a carga dentro do cadeado
exec flock "$HOME/openbim-medicao/medicao.lock" env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 LC_ALL=C \
  PYTHONPATH="$M/build" TMPDIR="$O/tmp" OBIM_LIMITE=${LIM:-3600} OBIM_SEM_CONSERTADO="$SEM" \
  timeout ${LIM:-3600} "$HOME/miniforge3/envs/openbim/bin/python" "$R/prototypes/s04/sondas/sonda_t32.py" rodada --modo "$modo" --saida "$O/t32_${modo}_r$n.json" > "$O/t32_${modo}_r$n.out" 2> "$O/t32_${modo}_r$n.err"
