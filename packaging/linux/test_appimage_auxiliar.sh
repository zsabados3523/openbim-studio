#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Prova T07e4 no AppImage (F0-S06-T07e, R3): o pacote tem app/obim_geometria e LGPL-COMO-TROCAR.md; o filho do auxiliar de geometria nasce sob `python -I`
# (como o AppRun), acha obim_geometria no pacote (nao no PYTHONPATH sujo) e faz a operacao `caixas` num IFC pequeno. Quem faz: packaging/geometria_no_pacote.py.
# Uso: test_appimage_auxiliar.sh IMAGEM   (IMAGEM = .AppImage, extraido numa pasta temporaria, OU pasta ja extraida com o AppRun). Offscreen; nada na tela real.
set -u
[ $# -eq 1 ] || { echo "uso: $0 IMAGEM.AppImage|PASTA_EXTRAIDA" >&2; exit 2; }
ENTRADA="$(readlink -f "$1")"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $*"; }
if [ -d "$ENTRADA" ]; then R="$ENTRADA"; [ -f "$R/AppRun" ] || falha "$R nao parece um pacote extraido (sem AppRun)"
else
  [ -f "$ENTRADA" ] || falha "nao achei $ENTRADA"
  passo "extrair o AppImage"; ( cd "$W" && "$ENTRADA" --appimage-extract >/dev/null ) || falha "--appimage-extract falhou"; R="$W/squashfs-root"
fi
R="$(readlink -f "$R")"; PY="$R/env/bin/python"
[ -x "$PY" ] || falha "faltou o Python do pacote ($PY)"
passo "app/obim_geometria e LGPL-COMO-TROCAR.md dentro do pacote"
for m in __init__ processo caixas desenho; do [ -f "$R/app/obim_geometria/$m.py" ] || falha "faltou app/obim_geometria/$m.py dentro do pacote"; done
[ -s "$R/LGPL-COMO-TROCAR.md" ] || falha "faltou LGPL-COMO-TROCAR.md (ou vazio) na raiz do pacote"
passo "filho sob -I acha obim_geometria do pacote e faz caixas (PYTHONPATH sujo de proposito: -I tem de ignorar)"
mkdir -p "$W/sujo/obim_geometria" "$W/tmp"; echo 'raise ImportError("obim_geometria de fora do pacote")' > "$W/sujo/obim_geometria/__init__.py"
out="$(timeout 600 env -u PYTHONHOME -u CONDA_PREFIX PYTHONPATH="$W/sujo" PYTHONNOUSERSITE=1 PATH="$R/env/bin:$PATH" QT_QPA_PLATFORM=offscreen LC_ALL=C TMPDIR="$W/tmp" \
  "$PY" -I "$HERE/../geometria_no_pacote.py" "$R" 2>&1)"; rc=$?
echo "$out" | tail -n 5
[ $rc -eq 0 ] || falha "prova do auxiliar de geometria reprovou (codigo $rc)"
passo "OK: obim_geometria dentro do pacote; filho sob -I fez caixas num IFC pequeno"
