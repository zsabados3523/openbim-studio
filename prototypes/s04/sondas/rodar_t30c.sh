#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# F0-S04-T30c: sondas de sub-lote em tela virtual (nunca a tela real), sob o cadeado da máquina compartilhada.
# uso: rodar_t30c.sh ifc ARQ.ifc [N]     sonda_t30c.py com o IFC dado (argumento; o IFC do PO fica fora do repositório); saída N (padrão 1)
#      rodar_t30c.sh sintetica [N]       a mesma sonda na cena sintética do T27 (13 lotes)
#      rodar_t30c.sh troca N [args]      medição por troca (sonda_t27.py rodada) com o lote_de em várias peças; args: --cena cheia|reduzida --paredes 3
# Saídas em ~/openbim-medicao/2026-10-20-T30c (SAIDA_T30C troca a pasta); OBIM_BUILD = pasta com o obimcore compilado (padrão ~/openbim-medicao/build).
set -u
LIM=${LIM:-3600}
R="$(cd "$(dirname "$0")/../../.." && pwd)"
O=${SAIDA_T30C:-$HOME/openbim-medicao/2026-10-20-T30c}; mkdir -p "$O/tmp"
modo=${1:?informe o modo: ifc | sintetica | troca}; shift
case "$modo" in
  ifc) arq=${1:?informe o IFC}; n=${2:-1}; CMD=("$R/prototypes/s04/sondas/sonda_t30c.py" ifc "$arq" --saida "$O/t30c_ifc_r$n.json") ;;
  sintetica) n=${1:-1}; CMD=("$R/prototypes/s04/sondas/sonda_t30c.py" sintetica --cena cheia --saida "$O/t30c_sint_r$n.json") ;;
  troca) n=${1:?informe o número da rodada}; shift; CMD=("$R/prototypes/s04/sondas/sonda_t27.py" rodada --rotulo t30c --saida "$O/t30c_troca_r$n.json" "$@") ;;
  *) echo "modo desconhecido: $modo" >&2; exit 2 ;;
esac
exec flock "$HOME/openbim-medicao/medicao.lock" env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 LC_ALL=C \
  PYTHONPATH="${OBIM_BUILD:-$HOME/openbim-medicao/build}" TMPDIR="$O/tmp" OBIM_LIMITE=$LIM \
  timeout $LIM "$HOME/miniforge3/envs/openbim/bin/python" "${CMD[@]}" > "$O/t30c_${modo}_r$n.out" 2> "$O/t30c_${modo}_r$n.err"
