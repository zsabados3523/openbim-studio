#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# N aberturas (1 a 3) da sonda_ensaio_t33.py, cada uma em processo próprio, em tela virtual (nunca a tela real), sob o cadeado da máquina compartilhada.
# uso: IFC_T33=/caminho/arquivo.ifc rodar_t33.sh [N] [args da sonda: --fios, --bloco, --bloco-alvo]
# saídas em ~/openbim-medicao/<data>-T33/ (pasta nova; SAIDA_T33 troca a pasta, para ensaios). O caminho do IFC vem só da variável: nunca entra em arquivo do repositório.
set -u
R="$(cd "$(dirname "$0")/../../.." && pwd)"
N=${1:-1}
shift
[[ "$N" =~ ^[1-3]$ ]] || { echo "N tem de ser 1, 2 ou 3" >&2; exit 2; }
IFC=${IFC_T33:?defina IFC_T33 com o caminho do arquivo}
O=${SAIDA_T33:-$HOME/openbim-medicao/$(date +%F)-T33}
mkdir -p "$O/tmp" || exit 2
for k in $(seq 1 "$N"); do
  [ -e "$O/t33_r$k.json" ] && { echo "já existe $O/t33_r$k.json: use outra pasta (SAIDA_T33)" >&2; exit 2; }
  uptime > "$O/t33_r$k.uptime"  # carga da máquina compartilhada ao pedir a vez
  flock "$HOME/openbim-medicao/medicao.lock" env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 LC_ALL=C \
    TMPDIR="$O/tmp" timeout "${LIM:-3600}" "$HOME/miniforge3/envs/openbim/bin/python" "$R/prototypes/s04/sondas/sonda_ensaio_t33.py" rodar "$IFC" \
    --rotulo "t33_r$k" --saida "$O/t33_r$k.json" "$@" > "$O/t33_r$k.out" 2> "$O/t33_r$k.err" || echo "abertura $k terminou com erro (ver $O/t33_r$k.err; não colar no relatório)" >&2
done
