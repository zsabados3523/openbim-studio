#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Monta o instalador Windows (NSIS): pasta do ambiente conda de runtime + código de app/ + textos de licença.
# Uso: build_installer.sh RUNTIME_ENV SAIDA_DIR   (rodar no bash do Git for Windows, com makensis no PATH)
#   RUNTIME_ENV  ambiente criado com: conda env create -f packaging/runtime-environment.yml -p <pasta>
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

# 1b. Poda de pacotes não usados (mesma decisão do PO do AppImage, cartão T10, ampliada na T11).
# O pacote conda `occt` depende de `vtk` só para o módulo de visualização do OCCT (TKIVtk); o `vtk`
# arrasta `vtk-io-ffmpeg`, `ffmpeg` (compilação GPL, com x264 e x265) e dezenas de pacotes de vídeo,
# áudio e aceleração que o app não usa. prune_packages.py remove as raízes abaixo e só os pacotes
# que apenas elas exigem (o inventário e a lista de fontes continuam listando tudo, com a marca).
python "$REPO/scripts/prune_packages.py" "$PKG/env" "$OUT/removidos.txt" --esperado=occt vtk vtk-base vtk-io-ffmpeg viskores ffmpeg

# 1b2. Resíduo do OCCT: TKIVtk*.dll (módulo de visualização do próprio OCCT) fica quebrada sem o VTK.
rm -f "$PKG"/env/Library/bin/TKIVtk*.dll
for d in "$PKG"/env/Lib/site-packages/vtkmodules "$PKG"/env/Lib/site-packages/vtk-* "$PKG"/env/Library/lib/vtk-*; do
  [ -d "$d" ] && find "$d" -depth -type d -empty -delete
done

# 1c. Arquivos que só servem para COMPILAR contra as bibliotecas (o app roda sem eles): bibliotecas de
# importação .lib, cmake, pkg-config, documentação, símbolos de depuração e testes.
rm -rf "$PKG/env/Library/lib/cmake" "$PKG/env/Library/lib/pkgconfig" "$PKG/env/Library/share/man" \
       "$PKG/env/Library/share/gtk-doc" "$PKG/env/Library/share/doc" "$PKG/env/Library/share/info"
find "$PKG/env" \( -name '*.lib' -o -name '*.pdb' -o -name '*.exp' \) -delete
echo "Maiores pastas do ambiente (MB):"
du -sm "$PKG"/env/* "$PKG"/env/Library/* "$PKG"/env/Lib/site-packages/* 2>/dev/null | sort -rn | head -14

# 2. Código do app e lançador
cp -a "$REPO/app/openbim_app" "$PKG/app/"
find "$PKG/app" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$HERE/OpenBIM-Studio.pyw" "$PKG/app/"

# 3. Licenças, como trocar, fontes
cp "$REPO/LICENSES/AGPL-3.0-or-later.txt" "$PKG/licenses/"
for f in LGPL-3.0 LGPL-2.1 GPL-3.0 OCCT-exception-1.0; do   # a montagem falha se faltar algum
  [ -f "$REPO/packaging/licenses-texts/$f.txt" ] || { echo "falta packaging/licenses-texts/$f.txt" >&2; exit 1; }
  cp "$REPO/packaging/licenses-texts/$f.txt" "$PKG/licenses/"
done
CONDA_PREFIX="$ENV_DIR" python "$REPO/scripts/license_inventory.py" "$PKG/licenses/INVENTARIO.md" >/dev/null
printf '
> Nota: os pacotes listados em REMOVIDOS.md aparecem acima mas foram **removidos na montagem**.
' >> "$PKG/licenses/INVENTARIO.md"
python "$REPO/scripts/collect_package_licenses.py" "$ENV_DIR" "$PKG/licenses/pacotes" | tee "$OUT/licencas-coletadas.txt"
cp "$HERE/LGPL-COMO-TROCAR.md" "$PKG/"
SPDX_ID="SPDX-License-Identifier"  # montado assim para o reuse lint nao ler como etiqueta deste script
{
  printf '<!--\n%s: AGPL-3.0-or-later\n-->\n# Pacotes removidos do instalador na montagem\n\n' "$SPDX_ID"
  printf 'Estes pacotes conda fazem parte do ambiente de runtime (constam em FONTES.md e INVENTARIO.md, com a marca "removido na montagem"), mas seus arquivos NÃO estão neste instalador.\n\n'
  printf 'Motivo: o pacote `occt` do conda-forge exige o VTK só para o módulo de visualização do OCCT (`TKIVtk`), e o VTK arrasta o ffmpeg (compilação GPL com x264/x265) e dezenas de bibliotecas de vídeo, áudio e aceleração que o OpenBIM Studio não usa. A geometria (ifcopenshell + OCCT) e a janela (Qt) funcionam sem eles. Nada deles é distribuído.\n'
  printf 'Efeito conhecido: as DLLs `TKIVtk*` do OCCT (que ficaram sem as bibliotecas do VTK) também foram apagadas, junto com as pastas vazias do VTK; retirar um arquivo não é modificar o OCCT. O texto das licenças dos removidos fica em `pacotes\\` quando o pacote o trazia, por cortesia.\n\nLista (nome versão licença):\n\n'
  sed 's/^/- /' "$OUT/removidos.txt"
} > "$PKG/licenses/REMOVIDOS.md"
LISTA="$("${CONDA_EXE:-conda}" list -p "$ENV_DIR" --explicit | grep -E '^https?://')"
REMOVIDOS="$OUT/removidos.txt" python - "$REPO/packaging/linux/FONTES.md.in" "$PKG/FONTES.md" "$LISTA" <<'PY'
import os, re, sys
src, dst, lista = sys.argv[1:4]
rem = {l.split()[0] for l in open(os.environ["REMOVIDOS"], encoding="utf-8") if l.strip()}
nome = lambda l: re.sub(r"-[^-]+-[^-]+$", "", l.rstrip("/").rsplit("/", 1)[-1].replace(".conda", "").replace(".tar.bz2", ""))
lista = "\n".join(l + "   # removido na montagem" if nome(l) in rem else l for l in lista.splitlines())
txt = open(src, encoding="utf-8").read().replace("@@LISTA@@", lista)
txt = txt.replace("linux-64", "win-64").replace("do AppImage", "do instalador").replace("vtk, viskores", "ver REMOVIDOS.md")
open(dst, "w", encoding="utf-8").write(txt)
PY
cp "$PKG/FONTES.md" "$PKG/licenses/FONTES.md"

# 3b. O ambiente (~1 GB, dezenas de milhares de arquivos) vai num único tar.gz dentro do instalador:
# o makensis (32 bits) estoura a memória com tantos arquivos soltos. O instalador extrai com o tar.exe do Windows.
tar -cf - -C "$PKG" env | gzip -9 > "$OUT/env.tgz"
rm -rf "$OUT/env-pronto" && mv "$PKG/env" "$OUT/env-pronto"
echo "env.tgz: $(du -h "$OUT/env.tgz" | cut -f1)"

# 4. Gera o instalador
# makensis: variável MAKENSIS, ou o do PATH (no CI vem do pacote conda-forge `nsis`, ambiente separado)
MAKENSIS="${MAKENSIS:-$(command -v makensis || true)}"
[ -n "$MAKENSIS" ] || { echo "makensis nao encontrado (defina MAKENSIS)" >&2; exit 1; }
WPKG="$(cygpath -w "$PKG")"; WEXE="$(cygpath -w "$EXE")"
MSYS2_ARG_CONV_EXCL='*' "$MAKENSIS" -V2 "-DPASTA_PACOTE=$WPKG" "-DSAIDA=$WEXE" "-DVERSAO=$VERSAO" "-DENV_TGZ=$(cygpath -w "$OUT/env.tgz")" "$(cygpath -w "$HERE/openbim-studio.nsi")"
echo "Ambiente (descompactado): $(du -sh "$OUT/env-pronto" | cut -f1)  Pacote (sem ambiente): $(du -sh "$PKG" | cut -f1)  Instalador: $(du -h "$EXE" | cut -f1)  tempo: $(( $(date +%s) - START )) s"
