#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Prova T07e4 no instalador Windows (F0-S06-T07e, R3), par de packaging/linux/test_appimage_auxiliar.sh: a pasta instalada tem app\obim_geometria e LGPL-COMO-TROCAR.md;
# o filho do auxiliar nasce sob `python.exe -I` E sob `pythonw.exe -I` (o atalho), acha obim_geometria no pacote e faz `caixas` num IFC pequeno. Quem faz: packaging/geometria_no_pacote.py.
# Uso (bash do Git for Windows): test_instalador_auxiliar.sh PASTA_INSTALADA   (rodar com o programa instalado, antes de o test_installer.sh desinstalar)
# OBIM_TESTE_SIMULADO=1 = ensaio em Linux (env/bin/python; pythonw = o mesmo python, sem a checagem do nome); recusado no Windows.
set -u
export MSYS2_ARG_CONV_EXCL="*"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $*"; }
[ $# -eq 1 ] || { echo "uso: $0 PASTA_INSTALADA" >&2; exit 2; }
SIM=0; [ "${OBIM_TESTE_SIMULADO:-}" = 1 ] && SIM=1
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) [ "$SIM" = 0 ] || falha "OBIM_TESTE_SIMULADO=1 e proibido no Windows" ;;
  *) [ "$SIM" = 1 ] || falha "este teste so vale no Windows (Git bash). Em Linux, so como ensaio: OBIM_TESTE_SIMULADO=1" ;;
esac
if [ "$SIM" = 1 ]; then wp() { printf '%s' "$1"; }; up() { readlink -f "$1"; }; D="$(up "$1")"; PY="$D/env/bin/python"; PYW="$PY"; PWF="--pythonw"
else wp() { cygpath -w "$1"; }; up() { cygpath -u "$1"; }; D="$(up "$1")"; PY="$D/env/python.exe"; PYW="$D/env/pythonw.exe"; PWF="--pythonw"; fi
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
[ -f "$PY" ] && [ -f "$PYW" ] || falha "faltou python.exe ou pythonw.exe em env\\ da pasta instalada"
passo "app\\obim_geometria e LGPL-COMO-TROCAR.md dentro da pasta instalada"
for m in __init__ processo caixas desenho; do [ -f "$D/app/obim_geometria/$m.py" ] || falha "faltou app\\obim_geometria\\$m.py"; done
[ -s "$D/LGPL-COMO-TROCAR.md" ] || falha "faltou LGPL-COMO-TROCAR.md (ou vazio) na raiz da pasta instalada"
mkdir -p "$W/sujo/obim_geometria" "$W/tmp"; echo 'raise ImportError("obim_geometria de fora do pacote")' > "$W/sujo/obim_geometria/__init__.py"
HP="$(wp "$HERE/../geometria_no_pacote.py")"; DW="$(wp "$D")"
roda() {  # roda EXECUTAVEL [--pythonw]: resultado em arquivo (pythonw nao tem stdout); saida e codigo do python do pacote ficam no log e NUNCA sao escondidos
  local exe="$1" extra="${2:-}" res="$W/res-$(basename "$1").json" log="$W/log-$(basename "$1").txt" rc; rm -f "$res"
  timeout 600 env -u PYTHONHOME -u CONDA_PREFIX PYTHONPATH="$(wp "$W/sujo")" PYTHONNOUSERSITE=1 QT_QPA_PLATFORM=offscreen TMPDIR="$(wp "$W/tmp")" \
    "$exe" -I "$HP" "$DW" $extra --saida "$(wp "$res")" > "$log" 2>&1; rc=$?
  [ -s "$log" ] && { echo "--- saida de $(basename "$exe") -I:"; cat "$log"; }
  [ -s "$res" ] && { echo "--- resultado:"; cat "$res"; echo; }
  [ $rc -eq 0 ] || falha "$(basename "$exe") -I saiu com codigo $rc"
  [ -s "$res" ] || falha "$(basename "$exe") -I nao gravou resultado (o filho nem abriu?)"
  grep -q '"erros": \[\]' "$res" || falha "prova reprovou sob $(basename "$exe") -I"
}
passo "filho sob python.exe -I"; roda "$PY"
passo "filho sob pythonw.exe -I (como o atalho)"; roda "$PYW" $PWF
passo "OK: obim_geometria na pasta instalada; filho sob -I e sob pythonw fez caixas num IFC pequeno"
