#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Oraculo R1-j do AppImage (cartao F0-S04-T17a; LOTE_OPUS_9 §1.5): o modulo C++ `obimcore` esta DENTRO do pacote e, la dentro,
# R1-a (versao e build), R1-d (mesmo modelo dos dois lados), R1-e (uma copia de cada biblioteca) e R1-i (malha igual a do Python)
# passam, com o Python do proprio pacote e as bibliotecas do proprio pacote.
# Uso: test_appimage_ponte.sh IMAGEM
#   IMAGEM = o .AppImage (e extraido numa pasta temporaria) OU uma pasta ja extraida (squashfs-root, a que tem o AppRun).
# Variavel: OBIM_PYTEST_SITE = pasta site-packages que tenha o pytest (puro Python). O pacote NAO ganha pytest: ele entra so
#   neste passo de teste, por links para pytest, _pytest, pluggy, iniconfig, pygments e py no FIM do sys.path. Sem a variavel,
#   procura em python3, /usr/bin/python3 e ~/miniforge3/envs/openbim.
# Roda tudo com QT_QPA_PLATFORM=offscreen (nunca na tela real). Nao edita tests/test_s04_ponte.py: o mesmo arquivo roda aqui.
set -u
[ $# -eq 1 ] || { echo "uso: $0 IMAGEM.AppImage|PASTA_EXTRAIDA" >&2; exit 2; }
ENTRADA="$(readlink -f "$1")"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTES="$(cd "$HERE/../.." && pwd)/tests"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $*"; }

if [ -d "$ENTRADA" ]; then
  R="$ENTRADA"
  [ -f "$R/AppRun" ] || falha "$R nao parece um pacote extraido (sem AppRun)"
else
  [ -f "$ENTRADA" ] || falha "nao achei $ENTRADA"
  passo "extrair o AppImage"
  ( cd "$W" && "$ENTRADA" --appimage-extract >/dev/null ) || falha "--appimage-extract falhou"
  R="$W/squashfs-root"
fi
R="$(readlink -f "$R")"
PY="$R/env/bin/python"

passo "modulo obimcore dentro do pacote (app/obimcore com __init__.py e o modulo compilado)"
[ -f "$R/app/obimcore/__init__.py" ] || falha "faltou app/obimcore/__init__.py dentro do pacote"
compgen -G "$R/app/obimcore/_obimcore*.so" >/dev/null || falha "faltou o modulo compilado app/obimcore/_obimcore*.so dentro do pacote"
[ -x "$PY" ] || falha "faltou o Python do pacote ($PY)"
ach="$(compgen -G "$R/env/lib/python3*/site-packages/_pytest"; compgen -G "$R/env/lib/python3*/site-packages/pytest")"
[ -z "$ach" ] || falha "o pytest nao pode ir dentro do pacote (so entra neste passo de teste): $ach"

passo "RPATH/RUNPATH do modulo: so relativo ao proprio arquivo (\$ORIGIN) e apontando para dentro do pacote"
command -v readelf >/dev/null || falha "sem readelf (binutils) nesta maquina: nao da para conferir o RPATH do modulo"
for so in "$R"/app/obimcore/*.so; do
  while IFS= read -r entrada; do
    [ -n "$entrada" ] || continue
    case "$entrada" in
      '$ORIGIN'*|'${ORIGIN}'*) ;;
      *) falha "$(basename "$so") tem RPATH/RUNPATH que nao e relativo (\$ORIGIN): $entrada" ;;
    esac
    rel="${entrada/\$\{ORIGIN\}/}"; rel="${rel/\$ORIGIN/}"
    destino="$(realpath -m "$(dirname "$so")/$rel")"
    case "$destino/" in
      "$R"/*) ;;
      *) falha "$(basename "$so"): RPATH $entrada aponta para fora do pacote ($destino)" ;;
    esac
  done < <(LC_ALL=C readelf -d "$so" | sed -n 's/.*\(RPATH\|RUNPATH\)[^[]*\[\(.*\)\]/\2/p' | tr ':' '\n')
done

passo "pytest para este passo de teste (fora do pacote; so links para o que o pytest precisa)"
SITE=""
for c in "${OBIM_PYTEST_SITE:-}" "$(python3 -I -c 'import _pytest,os;print(os.path.dirname(os.path.dirname(_pytest.__file__)))' 2>/dev/null)" \
         "$(/usr/bin/python3 -I -c 'import _pytest,os;print(os.path.dirname(os.path.dirname(_pytest.__file__)))' 2>/dev/null)" \
         "$(ls -d "$HOME"/miniforge3/envs/openbim/lib/python3.*/site-packages 2>/dev/null | head -n 1)"; do
  [ -n "$c" ] && [ -d "$c/_pytest" ] && { SITE="$c"; break; }
done
[ -n "$SITE" ] || falha "nao achei um pytest para o passo de teste (defina OBIM_PYTEST_SITE=pasta/site-packages com pytest)"
mkdir -p "$W/pytest_site" "$W/tmp"
for n in pytest _pytest pluggy iniconfig pygments py py.py; do [ -e "$SITE/$n" ] && ln -s "$SITE/$n" "$W/pytest_site/$n"; done
: > "$W/pytest.ini"
echo "   pytest de $SITE"

# Python do pacote, modo -I, montado como o AppRun monta (o proprio arquivo ponte_no_pacote.py e rodado por runpy, alter_sys=True).
# O ambiente e fixado aqui: PYTHONPATH so com o app/ do pacote (o filho do R1-e nao roda em -I e herda isto); sem o site do usuario.
no_pacote() {
  timeout 1500 env -u PYTHONHOME -u PYTHONSTARTUP -u PYTHONUSERBASE -u PYTHONSAFEPATH \
    PYTHONPATH="$R/app" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PATH="$R/env/bin:$PATH" \
    QT_QPA_PLATFORM=offscreen OBIM_S04_OBRIGATORIO=1 LC_ALL=C TMPDIR="$W/tmp" \
    "$PY" -I -c 'import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); runpy.run_module("ponte_no_pacote", run_name="__main__", alter_sys=True)' "$HERE" "$@"
}
prova() {  # prova DESCRICAO SUBCOMANDO ARGS...
  local desc="$1" out; shift
  out="$(no_pacote "$@" 2>&1)" && { echo "$out" | tail -n 3; return 0; }
  echo "$out" | tail -n 60
  falha "$desc"
}

passo "multiprocessing.freeze_support() em app/openbim_app/main.py e no comando Python do AppRun"
prova "freeze_support ausente ou no lugar errado" freeze "$R"

passo "bibliotecas: depois de importar ifcopenshell, PySide6.QtCore e obimcore, nenhuma .so fora do pacote"
prova "biblioteca de fora do pacote (ou modulo nao carregou)" maps "$R"

passo "processo filho spawn abre dentro do pacote (-I), roda uma funcao e devolve o valor"
prova "o filho spawn nao funcionou dentro do pacote" spawn "$R"

passo "R1-a, R1-d, R1-e e R1-i do tests/test_s04_ponte.py, com o Python do pacote (casos pulados contam como falha)"
prova "R1-j reprovou: algum caso de R1-a/d/e/i nao passou, foi pulado ou nao rodou" pytest "$R" "$TESTES" "$W/pytest_site" "$W"
passo "OK: obimcore dentro do pacote e R1-a, R1-d, R1-e, R1-i verdes com o Python e as bibliotecas do pacote"
