#!/bin/bash
# F0-S05-T02: as sondas, uma vez cada, sem tela. Saídas brutas fora do repositório. Precisa do modelo-grande-1m.ifc (corpus/README.md).
cd "$(dirname "$0")/../../.." || exit 1
O=$HOME/openbim-medicao/2026-10-23-S05-T02; PY=$HOME/miniforge3/envs/openbim/bin/python; S=prototypes/s05/sondas/sondas_ifcopenshell.py
G1M="${G1M:-$HOME/00 - PROJETOS/openbim-studio/corpus/modelo-grande-1m.ifc}"; M=$HOME/openbim-medicao/medicao.lock; export LC_ALL=C; mkdir -p "$O"
[ -f "$O/modelo-50mb.ifc" ] || flock $M $PY scripts/gerar_modelo_grande.py "$O/modelo-50mb.ifc" --paredes 59000
[ -f "$O/modelo-pequeno.ifc" ] || $PY scripts/gerar_modelo_grande.py "$O/modelo-pequeno.ifc" --paredes 300
sha256sum "$O/modelo-50mb.ifc" "$G1M" > "$O/sha256.txt"
for n in tempo custo registro fsync ids ids_comando; do
  flock $M $PY $S $n --saida "$O/$n.json" --ifc "$G1M" --ifc50 "$O/modelo-50mb.ifc" --ifc-pequeno "$O/modelo-pequeno.ifc" --pasta "$O" > "$O/$n.log" 2>&1
  echo "$n rc=$?" >> "$O/fim.txt"
done
