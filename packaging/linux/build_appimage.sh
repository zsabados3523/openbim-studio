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

# 1b. Poda de pacotes nao usados (decisao do PO, cartao F0-S02-T10, opcao 1).
# O pacote conda `occt` depende de `vtk` (que depende de `viskores`) so para o modulo de
# visualizacao do OCCT (libTKIVtk). O app NAO usa isso: a geometria do ifcopenshell nao precisa de
# VTK (verificado: ifcopenshell.geom.create_shape funciona sem eles) e a janela e Qt. Remove-los
# tira ~1,4 GB sem compressao. Padroes removidos (relativos a env/), em uma unica variavel:
PODA_PADROES=(
  'lib/libvtk*'                              # bibliotecas VTK
  'lib/libviskores*'                         # bibliotecas Viskores (dependencia do VTK)
  'lib/python3*/site-packages/vtkmodules'    # ligacoes Python do VTK
  'lib/python3*/site-packages/vtk.py'
  'lib/python3*/site-packages/vtk-*'         # vtk-*.dist-info / .egg-info
  'lib/vtk-*'                                # hierarquias de wrappers
  'lib/cmake/vtk-*'
  'lib/cmake/viskores-*'
  'share/viskores-*'
  'bin/vtk*'
)
# Nao remove share/licenses/VTK: o texto da licenca (BSD) fica em licenses/pacotes/ por cortesia.
shopt -s nullglob
for pad in "${PODA_PADROES[@]}"; do
  for alvo in "$APPDIR"/env/$pad; do rm -rf "$alvo"; done
done
shopt -u nullglob

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
printf '\n> Nota: os pacotes vtk, vtk-base, vtk-io-ffmpeg e viskores aparecem acima mas foram **removidos na montagem** (ver REMOVIDOS.md).\n' >> "$APPDIR/licenses/INVENTARIO.md"
# arquivos de licenca que os pacotes conda trazem (share/licenses/<pacote>/)
if [ -d "$ENV_DIR/share/licenses" ]; then cp -a "$ENV_DIR/share/licenses" "$APPDIR/licenses/pacotes"; fi
cp "$HERE/LGPL-COMO-TROCAR.md" "$APPDIR/"
cat > "$APPDIR/licenses/REMOVIDOS.md" <<'EOF'
<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Pacotes removidos do AppImage na montagem

Os pacotes conda abaixo fazem parte do ambiente de runtime (e continuam listados em FONTES.md e em
INVENTARIO.md, com a marca "removido na montagem"), mas seus arquivos NAO estao neste AppImage:

- `vtk`, `vtk-base`, `vtk-io-ffmpeg` (BSD-3-Clause): bibliotecas `libvtk*` e Python `vtkmodules`.
- `viskores` (BSD-3-Clause): bibliotecas `libviskores*`.

Motivo: o pacote `occt` do conda-forge exige o VTK so para o modulo de visualizacao do OCCT
(`libTKIVtk`), que o OpenBIM Studio nao usa. Sem eles o pacote cai de ~927 MiB para o tamanho da
meta (<= 600 MB). A geometria (ifcopenshell + OCCT) funciona sem VTK. Como nada do VTK/Viskores
e distribuido, nao ha obrigacao de fonte para eles; o texto da licenca (em `pacotes/VTK`) fica por cortesia.
Efeito colateral conhecido: `libTKIVtk.so*` do OCCT permanece no pacote, mas nao carrega (nao e usada).
Padroes removidos: ver `PODA_PADROES` em `packaging/linux/build_appimage.sh`.
EOF
LISTA="$("$CONDA" list -p "$ENV_DIR" --explicit | grep -E '^https?://')"
python3 - "$HERE/FONTES.md.in" "$APPDIR/FONTES.md" "$LISTA" <<'PY'
import sys
src, dst, lista = sys.argv[1:4]
import re
marca = re.compile(r"/(vtk|vtk-base|vtk-io-ffmpeg|viskores)-\d")
lista = "\n".join(l + "   # removido na montagem" if marca.search(l) else l for l in lista.splitlines())
open(dst, "w", encoding="utf-8").write(open(src, encoding="utf-8").read().replace("@@LISTA@@", lista))
PY
cp "$APPDIR/FONTES.md" "$APPDIR/licenses/FONTES.md"

# 4. Gera o AppImage (sem FUSE o appimagetool roda extraido)
"$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$IMAGE" || ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$IMAGE"
echo "AppDir: $(du -sh "$APPDIR" | cut -f1)  AppImage: $(du -h "$IMAGE" | cut -f1)  tempo: $(( $(date +%s) - START )) s"
