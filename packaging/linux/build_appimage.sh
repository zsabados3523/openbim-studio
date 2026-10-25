#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Monta o AppImage P1 (ADR-005 §5 item 6): pasta do ambiente conda de runtime + codigo de app/ + AppRun.
# Uso: OBIMCORE_DIR=pasta/obimcore build_appimage.sh SAIDA_DIR APPIMAGETOOL
#   SAIDA_DIR    pasta de trabalho/saida (fora do repositorio); recebe AppDir/ e o .AppImage
#   APPIMAGETOOL caminho do appimagetool-x86_64.AppImage (MIT, baixado por quem roda)
# Variaveis: RUNTIME_ENV (padrao ~/miniforge3/envs/openbim-runtime), criado com
#   conda env create -f packaging/runtime-environment.yml
#   OBIMCORE_DIR (obrigatoria): a pasta obimcore/ (com __init__.py e _obimcore*.so) que o build.sh de prototypes/s04/obimcore gera.
#   O pacote nao tem compilador: o modulo vem pronto do ambiente de desenvolvimento e entra em app/obimcore/.
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

# O pacote sem o modulo C++ nao e mais um pacote valido: falha com mensagem clara.
OBIMCORE_DIR="${OBIMCORE_DIR:-}"
if [ ! -f "$OBIMCORE_DIR/__init__.py" ] || ! compgen -G "$OBIMCORE_DIR/_obimcore*.so" > /dev/null; then
  echo "Falta o modulo obimcore: defina OBIMCORE_DIR com a pasta obimcore/ (__init__.py e _obimcore*.so) gerada por prototypes/s04/obimcore/build.sh (valor atual: '${OBIMCORE_DIR}')" >&2
  exit 1
fi
# R-ABI: o modulo foi compilado no ambiente de desenvolvimento; as travas dos dois ambientes tem de ter a MESMA compilacao destes pacotes.
for pkg in ifcopenshell occt pyside6 qt6-main; do
  dev="$(grep -oE "/$pkg-[0-9][^/#]*" "$REPO/environment.linux-64.lock" | head -n 1)"
  run="$(grep -oE "/$pkg-[0-9][^/#]*" "$REPO/packaging/runtime-environment.linux-64.lock" | head -n 1)"
  [ -n "$dev" ] && [ "$dev" = "$run" ] || { echo "R-ABI: $pkg difere entre a trava de desenvolvimento ('$dev') e a de runtime ('$run'); o modulo obimcore nao serve neste pacote" >&2; exit 1; }
done
# RPATH do modulo: so o relativo ao pacote. Um modulo antigo (com o caminho do ambiente de desenvolvimento) faria o pacote carregar biblioteca de fora (R1-e).
rpath_do_modulo() {  # imprime as entradas de RPATH/RUNPATH do .so, uma por linha (readelf se existir; senao Python puro)
  if command -v readelf > /dev/null; then
    LC_ALL=C readelf -d "$1" | sed -n 's/.*\(RPATH\|RUNPATH\)[^[]*\[\(.*\)\]/\2/p' | tr ':' '\n'
  else
    python3 - "$1" <<'PY'
import struct, sys
b = open(sys.argv[1], "rb").read()
shoff, = struct.unpack_from("<Q", b, 0x28)
tam, num = struct.unpack_from("<HH", b, 0x3A)
sec = [struct.unpack_from("<IIQQQQII", b, shoff + i * tam) for i in range(num)]
din = next(s for s in sec if s[1] == 6)
txt = sec[din[6]][4]
for o in range(din[4], din[4] + din[5], 16):
    tag, val = struct.unpack_from("<qQ", b, o)
    if tag in (15, 29):
        print(b[txt + val:b.index(0, txt + val)].decode().replace(":", "\n"))
PY
  fi
}
for so in "$OBIMCORE_DIR"/_obimcore*.so; do
  rp="$(rpath_do_modulo "$so")"
  [ "$rp" = '$ORIGIN/../../env/lib' ] || { echo "RPATH do modulo $(basename "$so") deve ser so \$ORIGIN/../../env/lib e e '$rp'; recompile com prototypes/s04/obimcore/build.sh" >&2; exit 1; }
done

rm -rf "$APPDIR"
mkdir -p "$APPDIR/licenses" "$APPDIR/app"

# 1. Ambiente inteiro em modo pasta (bibliotecas em arquivos separados). Sem cabecalhos/estaticos de compilacao.
cp -a "$ENV_DIR" "$APPDIR/env"
rm -rf "$APPDIR/env/include" "$APPDIR/env/man" "$APPDIR/env/share/man" "$APPDIR/env/share/doc"
find "$APPDIR/env" -name '*.a' -delete

# 1b. Poda de pacotes nao usados.
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
# Modulo C++: so o __init__.py e o .so, nada do diretorio de compilacao. O RPATH dele ($ORIGIN/../../env/lib) acha o env/ do pacote.
mkdir -p "$APPDIR/app/obimcore"
cp "$OBIMCORE_DIR/__init__.py" "$OBIMCORE_DIR"/_obimcore*.so "$APPDIR/app/obimcore/"
find "$APPDIR/app" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m 755 "$HERE/AppRun" "$APPDIR/AppRun"
cp "$HERE/openbim-studio.desktop" "$APPDIR/"
cp "$HERE/openbim-studio.svg" "$APPDIR/openbim-studio.svg"
[ -f "$HERE/openbim-studio.png" ] && cp "$HERE/openbim-studio.png" "$APPDIR/openbim-studio.png" && cp "$HERE/openbim-studio.png" "$APPDIR/.DirIcon"

# 3. Licencas, como trocar, fontes
# Textos verbatim guardados no repositorio (packaging/licenses-texts/); a montagem FALHA se faltar algum.
cp "$REPO/LICENSES/AGPL-3.0-or-later.txt" "$APPDIR/licenses/"
for f in LGPL-3.0 LGPL-2.1 GPL-3.0 OCCT-exception-1.0 nanobind-BSD-3-Clause tsl-robin-map-MIT; do
  [ -f "$REPO/packaging/licenses-texts/$f.txt" ] || { echo "falta packaging/licenses-texts/$f.txt" >&2; exit 1; }
  cp "$REPO/packaging/licenses-texts/$f.txt" "$APPDIR/licenses/"
done
CONDA_PREFIX="$ENV_DIR" python3 "$REPO/scripts/license_inventory.py" "$APPDIR/licenses/INVENTARIO.md" "--removidos=$OUT/removidos.txt" > "$OUT/inventario.log" || { sed -n '/## Não conda-forge/,$p' "$OUT/inventario.log"; echo "INVENTÁRIO DE LICENÇAS REPROVOU (ver acima)" >&2; exit 1; }
printf '\n> Nota: os pacotes listados em REMOVIDOS.md aparecem acima mas foram **removidos na montagem**.\n' >> "$APPDIR/licenses/INVENTARIO.md"
# O modulo obimcore leva codigo de terceiros que nao e pacote do ambiente de runtime, entao o inventario nao o lista:
# nanobind (BSD-3-Clause) e tsl::robin_map (MIT) vao compilados DENTRO do modulo (avisos nesta pasta); Eigen (MPL-2.0) e Boost (BSL-1.0) so como cabecalhos na compilacao.
printf '\n> Nota: o modulo `app/obimcore` (codigo do projeto) leva compilados dentro dele o **nanobind 3.1.0 (BSD-3-Clause)** e o **tsl::robin_map (MIT)**, com os avisos de copyright em `nanobind-BSD-3-Clause.txt` e `tsl-robin-map-MIT.txt` (esta pasta); usou cabecalhos do Eigen (MPL-2.0) e do Boost (BSL-1.0) so na compilacao; e usa IfcOpenShell, OCCT e Qt por bibliotecas dinamicas (pasta `env/`, LGPL-COMO-TROCAR.md).\n' >> "$APPDIR/licenses/INVENTARIO.md"
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
