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

# 1b. Poda de pacotes nao usados (decisao do PO, cartao F0-S02-T10, opcao 1; ampliada em F0-S02-T11).
# O pacote conda `occt` depende de `vtk` so para o modulo de visualizacao do OCCT (libTKIVtk); o `vtk`
# arrasta `vtk-io-ffmpeg`, `ffmpeg` (compilacao GPL, com x264 e x265) e ~130 pacotes de video, audio e
# aceleracao. O app NAO usa nada disso (verificado: selftest e ifcopenshell.geom.create_shape funcionam).
# prune_packages.py remove as raizes abaixo e so os pacotes que apenas elas exigem.
python3 "$REPO/scripts/prune_packages.py" "$APPDIR/env" "$OUT/removidos.txt" --esperado=occt vtk vtk-base vtk-io-ffmpeg viskores ffmpeg

# 1c. Resíduo do OCCT: libTKIVtk* (modulo de visualizacao do proprio OCCT) fica quebrada sem o VTK
# (faltam 11 bibliotecas). Apagar a biblioteca e as pastas vazias do VTK; o app nao usa nada disso.
rm -f "$APPDIR"/env/lib/libTKIVtk*
for d in "$APPDIR"/env/lib/vtk-* "$APPDIR"/env/lib/cmake/vtk-* "$APPDIR"/env/lib/python3*/site-packages/vtkmodules "$APPDIR"/env/lib/python3*/site-packages/vtk-*; do
  [ -d "$d" ] && find "$d" -depth -type d -empty -delete   # so apaga pastas vazias (as com arquivos ficam e aparecem no teste do CI)
done

# 2. Codigo do app, lancador, desktop e icone
cp -a "$REPO/app/openbim_app" "$APPDIR/app/"
find "$APPDIR/app" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m 755 "$HERE/AppRun" "$APPDIR/AppRun"
cp "$HERE/openbim-studio.desktop" "$APPDIR/"
cp "$HERE/openbim-studio.svg" "$APPDIR/openbim-studio.svg"
[ -f "$HERE/openbim-studio.png" ] && cp "$HERE/openbim-studio.png" "$APPDIR/openbim-studio.png" && cp "$HERE/openbim-studio.png" "$APPDIR/.DirIcon"

# 3. Licencas, como trocar, fontes
# Textos verbatim guardados no repositorio (packaging/licenses-texts/); a montagem FALHA se faltar algum.
cp "$REPO/LICENSES/AGPL-3.0-or-later.txt" "$APPDIR/licenses/"
for f in LGPL-3.0 LGPL-2.1 GPL-3.0 OCCT-exception-1.0; do
  [ -f "$REPO/packaging/licenses-texts/$f.txt" ] || { echo "falta packaging/licenses-texts/$f.txt" >&2; exit 1; }
  cp "$REPO/packaging/licenses-texts/$f.txt" "$APPDIR/licenses/"
done
CONDA_PREFIX="$ENV_DIR" python3 "$REPO/scripts/license_inventory.py" "$APPDIR/licenses/INVENTARIO.md" >/dev/null
printf '\n> Nota: os pacotes listados em REMOVIDOS.md aparecem acima mas foram **removidos na montagem**.\n' >> "$APPDIR/licenses/INVENTARIO.md"
# arquivos de licenca que cada pacote conda traz (info/licenses do cache do conda)
python3 "$REPO/scripts/collect_package_licenses.py" "$ENV_DIR" "$APPDIR/licenses/pacotes" | tee "$OUT/licencas-coletadas.txt"
cp "$HERE/LGPL-COMO-TROCAR.md" "$APPDIR/"
SPDX_ID="SPDX-License-Identifier"  # montado assim para o reuse lint nao ler como etiqueta deste script
{
  printf '<!--\n%s: AGPL-3.0-or-later\n-->\n# Pacotes removidos do AppImage na montagem\n\n' "$SPDX_ID"
  printf 'Estes pacotes conda fazem parte do ambiente de runtime (constam em FONTES.md e INVENTARIO.md, com a marca "removido na montagem"), mas seus arquivos NAO estao neste AppImage.\n\n'
  printf 'Motivo: o pacote `occt` do conda-forge exige o VTK so para o modulo de visualizacao do OCCT (`libTKIVtk`), e o VTK arrasta o ffmpeg (compilacao GPL com x264/x265) e dezenas de bibliotecas de video, audio e aceleracao que o OpenBIM Studio nao usa. A geometria (ifcopenshell + OCCT) e a janela (Qt) funcionam sem eles. Nada deles e distribuido.\n'
  printf 'Tambem foram apagados `libTKIVtk*` (arquivo do pacote occt, modulo de visualizacao do proprio OCCT que ficou sem as bibliotecas do VTK) e as pastas vazias do VTK. Retirar um arquivo nao e modificar o OCCT. O texto das licencas dos removidos fica em `pacotes/` quando o pacote o trazia, por cortesia.\n\nLista (nome versao licenca):\n\n'
  sed 's/^/- /' "$OUT/removidos.txt"
} > "$APPDIR/licenses/REMOVIDOS.md"
LISTA="$("$CONDA" list -p "$ENV_DIR" --explicit | grep -E '^https?://')"
REMOVIDOS="$OUT/removidos.txt" python3 - "$HERE/FONTES.md.in" "$APPDIR/FONTES.md" "$LISTA" <<'PY'
import sys
src, dst, lista = sys.argv[1:4]
import re
import os
rem = {l.split()[0] for l in open(os.environ["REMOVIDOS"], encoding="utf-8") if l.strip()}
nome = lambda l: re.sub(r"-[^-]+-[^-]+$", "", l.rstrip("/").rsplit("/", 1)[-1].replace(".conda", "").replace(".tar.bz2", ""))
lista = "\n".join(l + "   # removido na montagem" if nome(l) in rem else l for l in lista.splitlines())
open(dst, "w", encoding="utf-8").write(open(src, encoding="utf-8").read().replace("@@LISTA@@", lista))
PY
cp "$APPDIR/FONTES.md" "$APPDIR/licenses/FONTES.md"

# 4. Gera o AppImage (sem FUSE o appimagetool roda extraido)
"$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$IMAGE" || ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$IMAGE"
echo "AppDir: $(du -sh "$APPDIR" | cut -f1)  AppImage: $(du -h "$IMAGE" | cut -f1)  tempo: $(( $(date +%s) - START )) s"
