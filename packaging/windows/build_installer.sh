#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Monta o instalador Windows (NSIS): pasta do ambiente conda de runtime + código de app/ + textos de licença.
# Uso: build_installer.sh RUNTIME_ENV SAIDA_DIR   (rodar no bash do Git for Windows, com makensis no PATH)
#   RUNTIME_ENV  ambiente criado com: conda env create -f packaging/linux/runtime-environment.yml -p <pasta>
#   SAIDA_DIR    pasta de trabalho/saída (fora do repositório); recebe pacote/ e OpenBIM-Studio-Setup.exe
set -euo pipefail
export PYTHONUTF8=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ENV_DIR="$(cd "${1:?uso: build_installer.sh RUNTIME_ENV SAIDA_DIR}" && pwd)"
OUT="$(mkdir -p "${2:?informe SAIDA_DIR}" && cd "$2" && pwd)"
PKG="$OUT/pacote"
EXE="$OUT/OpenBIM-Studio-Setup.exe"
VERSAO="0.0.1-f0"
START=$(date +%s)

rm -rf "$PKG"
mkdir -p "$PKG/app" "$PKG/licenses"

# 1. Ambiente inteiro em modo pasta (DLLs em arquivos separados). Sem cabeçalhos nem bibliotecas de compilação.
cp -a "$ENV_DIR" "$PKG/env"
rm -rf "$PKG/env/Library/include" "$PKG/env/include" "$PKG/env/Library/share/doc" "$PKG/env/Library/man"
find "$PKG/env" -name '*.a' -delete

# 1b. Poda de pacotes não usados (mesma decisão do PO do AppImage, cartão T10): VTK e Viskores só servem
# ao módulo de visualização do OCCT (TKIVtk), que o app não usa.
shopt -s nullglob
for pad in 'Library/bin/vtk*' 'Library/bin/viskores*' 'Library/lib/vtk*' 'Library/lib/viskores*' \
           'Library/lib/cmake/vtk-*' 'Library/lib/cmake/viskores-*' 'Library/share/viskores-*' \
           'Lib/site-packages/vtkmodules' 'Lib/site-packages/vtk.py' 'Lib/site-packages/vtk-*'; do
  for alvo in "$PKG"/env/$pad; do rm -rf "$alvo"; done
done
shopt -u nullglob

# 2. Código do app e lançador
cp -a "$REPO/app/openbim_app" "$PKG/app/"
find "$PKG/app" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$HERE/OpenBIM-Studio.pyw" "$PKG/app/"

# 3. Licenças, como trocar, fontes
cp "$REPO/LICENSES/AGPL-3.0-or-later.txt" "$PKG/licenses/"
CONDA_PREFIX="$ENV_DIR" python "$REPO/scripts/license_inventory.py" "$PKG/licenses/INVENTARIO.md" >/dev/null
printf '\n> Nota: os pacotes vtk, vtk-base, vtk-io-ffmpeg e viskores aparecem acima mas foram **removidos na montagem** (ver REMOVIDOS.md).\n' >> "$PKG/licenses/INVENTARIO.md"
python "$REPO/scripts/collect_package_licenses.py" "$ENV_DIR" "$PKG/licenses/pacotes" | tee "$OUT/licencas-coletadas.txt"
cp "$HERE/LGPL-COMO-TROCAR.md" "$PKG/"
cat > "$PKG/licenses/REMOVIDOS.md" <<'EOT'
<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Pacotes removidos do instalador na montagem

Os pacotes conda `vtk`, `vtk-base`, `vtk-io-ffmpeg` e `viskores` (BSD-3-Clause) fazem parte do ambiente
de runtime (constam em FONTES.md e INVENTARIO.md, com a marca "removido na montagem"), mas seus arquivos
NÃO estão neste instalador. Motivo: o pacote `occt` do conda-forge exige o VTK só para o módulo de
visualização do OCCT (`TKIVtk`), que o OpenBIM Studio não usa. Nada deles é distribuído; os textos de
licença ficam em `pacotes\` por cortesia. As DLLs `TKIVtk*` do OCCT podem permanecer, mas não carregam
(não são usadas). Padrões removidos: ver `build_installer.sh`.
EOT
LISTA="$("${CONDA_EXE:-conda}" list -p "$ENV_DIR" --explicit | grep -E '^https?://' | sed -E 's#(/(vtk|vtk-base|vtk-io-ffmpeg|viskores)-[0-9].*)$#\1   \# removido na montagem#')"
python - "$REPO/packaging/linux/FONTES.md.in" "$PKG/FONTES.md" "$LISTA" <<'PY'
import sys
src, dst, lista = sys.argv[1:4]
txt = open(src, encoding="utf-8").read().replace("@@LISTA@@", lista)
txt = txt.replace("linux-64", "win-64").replace("do AppImage", "do instalador")
open(dst, "w", encoding="utf-8").write(txt)
PY
cp "$PKG/FONTES.md" "$PKG/licenses/FONTES.md"

# 4. Gera o instalador
MAKENSIS="$(command -v makensis || true)"
[ -n "$MAKENSIS" ] || MAKENSIS="/c/Program Files (x86)/NSIS/makensis.exe"
WPKG="$(cygpath -w "$PKG")"; WEXE="$(cygpath -w "$EXE")"
MSYS2_ARG_CONV_EXCL='*' "$MAKENSIS" -V2 "-DPASTA_PACOTE=$WPKG" "-DSAIDA=$WEXE" "-DVERSAO=$VERSAO" "$(cygpath -w "$HERE/openbim-studio.nsi")"
echo "Pacote: $(du -sh "$PKG" | cut -f1)  Instalador: $(du -h "$EXE" | cut -f1)  tempo: $(( $(date +%s) - START )) s"
