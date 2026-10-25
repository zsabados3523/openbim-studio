#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Monta o instalador Windows (NSIS): pasta do ambiente conda de runtime + código de app/ + textos de licença.
# Uso: OBIMCORE_DIR=pasta/obimcore build_installer.sh RUNTIME_ENV SAIDA_DIR   (rodar no bash do Git for Windows, com makensis no PATH)
#   RUNTIME_ENV  ambiente criado com: conda env create -f packaging/runtime-environment.yml -p <pasta>
#   SAIDA_DIR    pasta de trabalho/saída (fora do repositório); recebe pacote/ e OpenBIM-Studio-Setup.exe
#   OBIMCORE_DIR (obrigatória): a pasta obimcore/ (com __init__.py e UM _obimcore*.pyd) que native/obimcore/build.sh gera.
#   O pacote não tem compilador: o módulo vem pronto do ambiente de desenvolvimento e entra em app\obimcore\.
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

# O pacote sem o módulo C++ não é mais um pacote válido: falha com mensagem clara, antes de apagar ou copiar qualquer coisa.
OBIMCORE_DIR="${OBIMCORE_DIR:-}"
shopt -s nullglob; PYDS=("$OBIMCORE_DIR"/_obimcore*.pyd); shopt -u nullglob
if [ ! -f "$OBIMCORE_DIR/__init__.py" ] || [ "${#PYDS[@]}" -ne 1 ]; then
  echo "Falta o módulo obimcore: defina OBIMCORE_DIR com a pasta obimcore/ (__init__.py e exatamente um _obimcore*.pyd) gerada por native/obimcore/build.sh (valor atual: '${OBIMCORE_DIR}', .pyd achados: ${#PYDS[@]})" >&2
  exit 1
fi
# R-ABI: o módulo foi compilado no ambiente de desenvolvimento; as travas dos dois ambientes (e o ambiente de runtime de verdade) têm de ter a MESMA
# compilação destes pacotes. O ambiente real conta porque, numa montagem local, ele pode estar atrás da trava.
for pkg in ifcopenshell occt pyside6 qt6-main; do
  dev="$(tr -d '\r' < "$REPO/environment.win-64.lock" | grep -m1 -oE "/$pkg-[0-9][^/#]*" || true)"
  run="$(tr -d '\r' < "$REPO/packaging/runtime-environment.win-64.lock" | grep -m1 -oE "/$pkg-[0-9][^/#]*" || true)"
  [ -n "$dev" ] && [ "$dev" = "$run" ] || { echo "R-ABI: $pkg difere entre a trava de desenvolvimento ('$dev') e a de runtime ('$run'); o módulo obimcore não serve neste pacote" >&2; exit 1; }
  nome="${dev#/}"; nome="${nome%.conda}"; nome="${nome%.tar.bz2}"
  [ -f "$ENV_DIR/conda-meta/$nome.json" ] || { echo "R-ABI: o ambiente de runtime $ENV_DIR não tem $nome (a trava pede este build); refaça o ambiente pela trava" >&2; exit 1; }
done

rm -rf "$PKG"
mkdir -p "$PKG/app" "$PKG/licenses"

# 1. Ambiente inteiro em modo pasta (DLLs em arquivos separados). Sem cabeçalhos nem bibliotecas de compilação.
cp -a "$ENV_DIR" "$PKG/env"
rm -rf "$PKG/env/Library/include" "$PKG/env/include" "$PKG/env/Library/share/doc" "$PKG/env/Library/man"
find "$PKG/env" -name '*.a' -delete

# 1b. Poda de pacotes não usados (mesma decisão do AppImage).
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

# 1b3. etc/conda/test-files/<pacote>: arquivos de teste da compilação no conda-forge (alguns pacotes novos, como o
# x264, passaram a trazer isso em 2026-10-14). Só servem ao conda-build, o app não usa. Sem isso sobra a pasta
# de um pacote podado (ex.: x264) e o teste do instalador a acusa como arquivo podado.
rm -rf "$PKG/env/etc/conda/test-files"

# 1c. Arquivos que só servem para COMPILAR contra as bibliotecas (o app roda sem eles): bibliotecas de
# importação .lib, cmake, pkg-config, documentação, símbolos de depuração e testes.
rm -rf "$PKG/env/Library/lib/cmake" "$PKG/env/Library/lib/pkgconfig" "$PKG/env/Library/share/man" \
       "$PKG/env/Library/share/gtk-doc" "$PKG/env/Library/share/doc" "$PKG/env/Library/share/info"
find "$PKG/env" \( -name '*.lib' -o -name '*.pdb' -o -name '*.exp' \) -delete
echo "Maiores pastas do ambiente (MB):"
du -sm "$PKG"/env/* "$PKG"/env/Library/* "$PKG"/env/Lib/site-packages/* 2>/dev/null | sort -rn | head -14

# 1d. Runtime do Visual C++ (prova 7 do ADR-005 §7.1). O python.exe procura o vcruntime140.dll primeiro na própria pasta (env\) e só depois
# no Windows; sem a cópia aqui, o pacote usaria o do sistema (que pode ser mais velho que o do compilador do módulo, ou faltar em outra máquina).
# Só usa o que o próprio pacote conda vc14_runtime já traz (fixado na trava): se estiver só em Library\bin, copia para env\.
for f in "$PKG"/env/Library/bin/vcruntime140*.dll; do
  if [ -f "$f" ] && [ ! -f "$PKG/env/$(basename "$f")" ]; then cp "$f" "$PKG/env/"; fi
done
[ -f "$PKG/env/vcruntime140.dll" ] || { echo "Prova 7: o ambiente de runtime não traz vcruntime140.dll (nem em env\\, nem em env\\Library\\bin); o vc14_runtime da trava deveria trazer" >&2; exit 1; }
{ [ -f "$PKG/env/msvcp140.dll" ] || [ -f "$PKG/env/Library/bin/msvcp140.dll" ]; } || { echo "Prova 7: o ambiente de runtime não traz msvcp140.dll" >&2; exit 1; }
echo "Runtime do Visual C++ no pacote:"; ls -l "$PKG"/env/vcruntime140*.dll "$PKG"/env/msvcp140*.dll "$PKG"/env/Library/bin/msvcp140*.dll "$PKG"/env/Library/bin/vcruntime140*.dll 2>/dev/null || true

# 2. Código do app, módulo C++ e lançador
cp -a "$REPO/app/openbim_app" "$PKG/app/"
find "$PKG/app" -name __pycache__ -type d -prune -exec rm -rf {} +
mkdir -p "$PKG/app/obimcore"  # só o __init__.py e o .pyd, nada do diretório de compilação
cp "$OBIMCORE_DIR/__init__.py" "${PYDS[0]}" "$PKG/app/obimcore/"
cp "$HERE/OpenBIM-Studio.pyw" "$PKG/app/"
# Prova 7 já aqui (o teste test_instalador_ponte.sh repete depois de instalar): runtime do pacote >= ligador do .pyd. Falhar agora poupa montar 300 MB à toa.
python -I "$HERE/ponte_no_pacote_win.py" vcrt "$(cygpath -w "$PKG")" || { echo "Prova 7 reprovou: runtime do Visual C++ do pacote mais velho que o compilador do obimcore (ver acima)" >&2; exit 1; }

# 3. Licenças, como trocar, fontes
cp "$REPO/LICENSES/AGPL-3.0-or-later.txt" "$PKG/licenses/"
for f in LGPL-3.0 LGPL-2.1 GPL-3.0 OCCT-exception-1.0 nanobind-BSD-3-Clause tsl-robin-map-MIT; do   # a montagem falha se faltar algum
  [ -f "$REPO/packaging/licenses-texts/$f.txt" ] || { echo "falta packaging/licenses-texts/$f.txt" >&2; exit 1; }
  cp "$REPO/packaging/licenses-texts/$f.txt" "$PKG/licenses/"
done
CONDA_PREFIX="$ENV_DIR" python "$REPO/scripts/license_inventory.py" "$PKG/licenses/INVENTARIO.md" "--removidos=$OUT/removidos.txt" > "$OUT/inventario.log" || { sed -n '/## Não conda-forge/,$p' "$OUT/inventario.log"; echo "INVENTÁRIO DE LICENÇAS REPROVOU (ver acima)" >&2; exit 1; }
printf '
> Nota: os pacotes listados em REMOVIDOS.md aparecem acima mas foram **removidos na montagem**.
' >> "$PKG/licenses/INVENTARIO.md"
# O módulo obimcore leva código de terceiros que não é pacote do ambiente de runtime, então o inventário não o lista:
# nanobind (BSD-3-Clause) e tsl::robin_map (MIT) vão compilados DENTRO do módulo (avisos nesta pasta); Eigen (MPL-2.0) e Boost (BSL-1.0) só como cabeçalhos na compilação.
printf '\n> Nota: o módulo `app\\obimcore` (código do projeto) leva compilados dentro dele o **nanobind 3.1.0 (BSD-3-Clause)** e o **tsl::robin_map (MIT)**, com os avisos de copyright em `nanobind-BSD-3-Clause.txt` e `tsl-robin-map-MIT.txt` (esta pasta); usou cabeçalhos do Eigen (MPL-2.0) e do Boost (BSL-1.0) só na compilação; e usa IfcOpenShell, OCCT e Qt por bibliotecas dinâmicas (pasta `env\\`, LGPL-COMO-TROCAR.md).\n' >> "$PKG/licenses/INVENTARIO.md"
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
# gzip -6 (o -9 custava ~80 s a mais por ~1% de tamanho); o instalador guarda o env.tgz sem recomprimir. O conteúdo extraído é o mesmo.
T_TGZ=$(date +%s)
tar -cf - -C "$PKG" env | gzip -6 > "$OUT/env.tgz"
rm -rf "$OUT/env-pronto" && mv "$PKG/env" "$OUT/env-pronto"
echo "env.tgz: $(du -h "$OUT/env.tgz" | cut -f1) ($(( $(date +%s) - T_TGZ )) s)"

# 4. Gera o instalador
# makensis: variável MAKENSIS, ou o do PATH (no CI vem do pacote conda-forge `nsis`, ambiente separado)
MAKENSIS="${MAKENSIS:-$(command -v makensis || true)}"
[ -n "$MAKENSIS" ] || { echo "makensis nao encontrado (defina MAKENSIS)" >&2; exit 1; }
WPKG="$(cygpath -w "$PKG")"; WEXE="$(cygpath -w "$EXE")"
T_NSIS=$(date +%s)
MSYS2_ARG_CONV_EXCL='*' "$MAKENSIS" -V2 "-DPASTA_PACOTE=$WPKG" "-DSAIDA=$WEXE" "-DVERSAO=$VERSAO" "-DENV_TGZ=$(cygpath -w "$OUT/env.tgz")" "$(cygpath -w "$HERE/openbim-studio.nsi")"
echo "makensis: $(( $(date +%s) - T_NSIS )) s"
echo "Ambiente (descompactado): $(du -sh "$OUT/env-pronto" | cut -f1)  Pacote (sem ambiente): $(du -sh "$PKG" | cut -f1)  Instalador: $(du -h "$EXE" | cut -f1)  tempo: $(( $(date +%s) - START )) s"
