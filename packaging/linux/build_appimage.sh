#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Monta o AppImage P1 (ADR-005 §5 item 6): pasta do ambiente conda de runtime + codigo de app/ + AppRun.
# Uso: build_appimage.sh SAIDA_DIR APPIMAGETOOL
#   SAIDA_DIR    pasta de trabalho/saida (fora do repositorio); recebe AppDir/ e o .AppImage
#   APPIMAGETOOL caminho do appimagetool-x86_64.AppImage (MIT, baixado por quem roda)
# Variavel: RUNTIME_ENV (padrao ~/miniforge3/envs/openbim-runtime), criado com
#   conda env create -f packaging/linux/runtime-environment.yml
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$(mkdir -p "${1:?uso: build_appimage.sh SAIDA_DIR APPIMAGETOOL}" && cd "$1" && pwd)"
TOOL="${2:?informe o caminho do appimagetool}"
ENV_DIR="${RUNTIME_ENV:-$HOME/miniforge3/envs/openbim-runtime}"
CONDA="${CONDA_EXE:-$HOME/miniforge3/bin/conda}"
APPDIR="$OUT/AppDir"
IMAGE="$OUT/OpenBIM-Studio-x86_64.AppImage"
START=$(date +%s)

[ -x "$ENV_DIR/bin/python" ] || { echo "Ambiente de runtime nao encontrado: $ENV_DIR" >&2; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/licenses" "$APPDIR/app"

# 1. Ambiente inteiro em modo pasta (bibliotecas em arquivos separados). Sem cabecalhos/estaticos de compilacao.
cp -a "$ENV_DIR" "$APPDIR/env"
rm -rf "$APPDIR/env/include" "$APPDIR/env/man" "$APPDIR/env/share/man" "$APPDIR/env/share/doc"
find "$APPDIR/env" -name '*.a' -delete

# 2. Codigo do app, lancador, desktop e icone
cp -a "$REPO/app/openbim_app" "$APPDIR/app/"
find "$APPDIR/app" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m 755 "$HERE/AppRun" "$APPDIR/AppRun"
cp "$HERE/openbim-studio.desktop" "$APPDIR/"
cp "$HERE/openbim-studio.svg" "$APPDIR/openbim-studio.svg"
[ -f "$HERE/openbim-studio.png" ] && cp "$HERE/openbim-studio.png" "$APPDIR/openbim-studio.png" && cp "$HERE/openbim-studio.png" "$APPDIR/.DirIcon"

# 3. Licencas, como trocar, fontes
cp "$REPO/LICENSES/AGPL-3.0-or-later.txt" "$APPDIR/licenses/"
for f in LGPL-3 LGPL-2.1 GPL-3; do
  [ -f "/usr/share/common-licenses/$f" ] && cp "/usr/share/common-licenses/$f" "$APPDIR/licenses/$f.txt" || true
done
CONDA_PREFIX="$ENV_DIR" python3 "$REPO/scripts/license_inventory.py" "$APPDIR/licenses/INVENTARIO.md" >/dev/null
# arquivos de licenca que os pacotes conda trazem (share/licenses/<pacote>/)
if [ -d "$ENV_DIR/share/licenses" ]; then cp -a "$ENV_DIR/share/licenses" "$APPDIR/licenses/pacotes"; fi
cp "$HERE/LGPL-COMO-TROCAR.md" "$APPDIR/"
LISTA="$("$CONDA" list -p "$ENV_DIR" --explicit | grep -E '^https?://')"
python3 - "$HERE/FONTES.md.in" "$APPDIR/FONTES.md" "$LISTA" <<'PY'
import sys
src, dst, lista = sys.argv[1:4]
open(dst, "w", encoding="utf-8").write(open(src, encoding="utf-8").read().replace("@@LISTA@@", lista))
PY
cp "$APPDIR/FONTES.md" "$APPDIR/licenses/FONTES.md"

# 4. Gera o AppImage (sem FUSE o appimagetool roda extraido)
"$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$IMAGE" || ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$IMAGE"
echo "AppDir: $(du -sh "$APPDIR" | cut -f1)  AppImage: $(du -h "$IMAGE" | cut -f1)  tempo: $(( $(date +%s) - START )) s"
