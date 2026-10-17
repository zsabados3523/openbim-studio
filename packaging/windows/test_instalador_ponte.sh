#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Oraculo R1-j do instalador Windows (cartao F0-S04-T17b; LOTE_OPUS_9 §1.5; ADR-005 §7.1 prova 7), par de packaging/linux/test_appimage_ponte.sh:
# o modulo `obimcore` esta DENTRO da pasta instalada e, la dentro, R1-a/d/e/i passam com o Python (-I) e as DLLs do proprio pacote.
# Uso (bash do Git for Windows): test_instalador_ponte.sh PASTA_INSTALADA  |  test_instalador_ponte.sh --autoteste (partes sem Windows, em qualquer sistema)
# QUANDO: com o programa instalado (`Setup.exe /S /D=C:\pasta\sem\espacos`) e ANTES de o test_installer.sh desinstalar (ele desinstala no fim).
# OBIM_PYTEST_SITE (obrigatoria) = site-packages do ambiente de DESENVOLVIMENTO com pytest. O pacote NAO ganha pytest: so pytest, _pytest, pluggy,
#   iniconfig, pygments, packaging, colorama e py sao enxergados dali, no fim do caminho de busca. Offscreen, OBIM_S04_OBRIGATORIO=1 (pulo vira falha).
# O IMPLEMENTADOR ENTREGA (e este script confere): app\obimcore\__init__.py + um _obimcore*.pyd (saida do build.sh, sem editar); env\Library\bin;
#   vcruntime140*.dll em env\ (junto do python.exe: ele a carrega antes do add_dll_directory), msvcp140*.dll em env\ ou env\Library\bin, todas com versao
#   >= a do ligador do .pyd; freeze_support() no OpenBIM-Studio.pyw antes de
#   abrir o app; licenses\nanobind-BSD-3-Clause.txt e licenses\tsl-robin-map-MIT.txt (iguais a packaging/licenses-texts) e, no INVENTARIO.md, uma
#   linha com nanobind + BSD-3-Clause e outra com robin_map + MIT. PROVA 7: compilador = versao do LIGADOR no cabecalho PE do .pyd (MSVC 14.NN grava
#   14 e NN); runtime = versao do arquivo (VS_FIXEDFILEINFO) de toda vcruntime140*/msvcp140*.dll do pacote e das carregadas; compara maior.menor.
# OBIM_TESTE_SIMULADO=1 = ENSAIO em Linux (env/bin/python, _obimcore*.so): pula so os passos c e d (DLLs, runtime do Visual C++) e termina em
#   "OK SIMULADO"; recusado no Windows. REVISOR, no log do CI do Windows, conferir: as versoes impressas (ligador x runtime), o filho pythonw, os
#   9 casos, e se o R1-e passa (os filhos nao herdam add_dll_directory; "DLL load failed" no filho do s04_aux r1e = levar ao lider, nao afrouxar o teste).
set -u
export MSYS2_ARG_CONV_EXCL="*"   # o bash do Git for Windows nao pode reescrever os argumentos
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $*"; }
if [ "${1:-}" = "--autoteste" ]; then exec "$(command -v python3 || command -v python)" -I "$HERE/ponte_no_pacote_win.py" autoteste; fi
[ $# -eq 1 ] || { echo "uso: $0 PASTA_INSTALADA | --autoteste" >&2; exit 2; }
SIM=0; [ "${OBIM_TESTE_SIMULADO:-}" = 1 ] && SIM=1
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) [ "$SIM" = 0 ] || falha "OBIM_TESTE_SIMULADO=1 e proibido no Windows (o CI nunca pode rodar simulado)" ;;
  *) [ "$SIM" = 1 ] || falha "este oraculo so vale no Windows (Git bash). Em Linux, so como ensaio: OBIM_TESTE_SIMULADO=1" ;;
esac
if [ "$SIM" = 1 ]; then
  wp() { printf '%s' "$1"; }; up() { readlink -f "$1"; }
  D="$(up "$1")"; PY="$D/env/bin/python"; PYW="$PY"; EXT=so; SP="$D/env/lib/python3*/site-packages"
else
  wp() { cygpath -w "$1"; }; up() { cygpath -u "$1"; }
  D="$(up "$1")"; PY="$D/env/python.exe"; PYW="$D/env/pythonw.exe"; EXT=pyd; SP="$D/env/Lib/site-packages"
fi
REPO="$(cd "$HERE/../.." && pwd)"; W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
HW="$(wp "$HERE/ponte_no_pacote_win.py")"; DW="$(wp "$D")"

passo "estrutura: app/obimcore com __init__.py e o modulo compilado, env/Library/bin, sem pytest dentro do pacote"
[ -f "$D/app/obimcore/__init__.py" ] || falha "faltou app/obimcore/__init__.py dentro da pasta instalada"
n="$(compgen -G "$D/app/obimcore/_obimcore*.$EXT" | wc -l)"; [ "$n" = 1 ] || falha "esperava 1 app/obimcore/_obimcore*.$EXT, achei $n"
[ -f "$PY" ] || falha "faltou o Python do pacote ($PY)"
{ [ "$SIM" = 1 ] || [ -d "$D/env/Library/bin" ]; } || falha "faltou env/Library/bin (pasta das DLLs que o __init__.py do modulo mostra ao carregador)"
ach="$(compgen -G "$SP/_pytest"; compgen -G "$SP/pytest"; compgen -G "$D/env/conda-meta/pytest-*.json")"
[ -z "$ach" ] || falha "o pytest nao pode ir dentro do pacote (so entra neste passo de teste): $ach"

passo "licencas: nanobind (BSD-3-Clause) e tsl::robin_map (MIT) no pacote, com o texto igual ao do repositorio"
for l in nanobind-BSD-3-Clause tsl-robin-map-MIT; do
  [ -s "$D/licenses/$l.txt" ] || falha "faltou licenses/$l.txt (ou esta vazio)"
  cmp -s "$D/licenses/$l.txt" "$REPO/packaging/licenses-texts/$l.txt" || falha "licenses/$l.txt difere de packaging/licenses-texts/$l.txt"
done
grep -i 'nanobind' "$D/licenses/INVENTARIO.md" | grep -q 'BSD-3-Clause' || falha "INVENTARIO.md nao cita nanobind com BSD-3-Clause na mesma linha"
grep -iE 'robin[_-]map' "$D/licenses/INVENTARIO.md" | grep -q 'MIT' || falha "INVENTARIO.md nao cita tsl::robin_map com MIT na mesma linha"

SITE="$(up "${OBIM_PYTEST_SITE:-/inexistente}" 2>/dev/null)"
[ -d "$SITE/_pytest" ] || falha "defina OBIM_PYTEST_SITE com a pasta site-packages que tem o pytest (fora do pacote); valor: '${OBIM_PYTEST_SITE:-}'"

# Python do pacote em -I, como o atalho. PATH e PYTHONPATH o auxiliar monta como o lancador; o PATH sujo da maquina fica atras (vazamento aparece).
no_pacote() {  # no_pacote INTERPRETADOR ARGS...
  local py="$1" rc; shift
  timeout 1500 env -u PYTHONHOME -u PYTHONSTARTUP -u PYTHONUSERBASE -u PYTHONSAFEPATH -u PYTHONPATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV -u VIRTUAL_ENV \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen OBIM_S04_OBRIGATORIO=1 OBIM_TESTE_SIMULADO="$SIM" LC_ALL=C \
    "$py" -I "$HW" "$@" > "$W/saida.txt" 2>&1
  rc=$?; tr -d '\r' < "$W/saida.txt"; return $rc
}
prova() {  # prova DESCRICAO INTERPRETADOR ARGS...
  local desc="$1" out; shift
  out="$(no_pacote "$@")" && { echo "$out" | tail -n 15; return 0; }
  echo "$out" | tail -n 250; falha "$desc"
}

passo "multiprocessing.freeze_support() em app/openbim_app/main.py e no lancador app/OpenBIM-Studio.pyw (arvore sintatica)"
prova "freeze_support ausente ou no lugar errado" "$PY" freeze "$DW"

if [ "$SIM" = 0 ]; then
  passo "prova 7 (ADR-005): runtime do Visual C++ do pacote >= o do compilador que gerou o .pyd"
  prova "runtime do Visual C++ mais velho que o compilador do .pyd (ou ausente)" "$PY" vcrt "$DW"
  passo "bibliotecas: depois de importar ifcopenshell, PySide6.QtCore e obimcore, todo modulo do processo vem do pacote ou do Windows"
  prova "DLL/PYD de fora do pacote (ou modulo nao carregou)" "$PY" dlls "$DW"
else
  echo "==> PULADO (simulado): prova 7 do runtime do Visual C++ e a conferencia de DLLs carregadas (so o CI do Windows prova)"
fi

spawn() {  # spawn ROTULO INTERPRETADOR: o resultado vai para arquivo (o pythonw nao tem saida de texto)
  rm -f "$W/spawn.txt"
  no_pacote "$2" spawn "$DW" "$(wp "$W/spawn.txt")" > /dev/null; local rc=$?
  [ -f "$W/spawn.txt" ] || falha "$1: o auxiliar nao escreveu o resultado (codigo $rc)"
  tr -d '\r' < "$W/spawn.txt" | tail -n 8
  [ "$rc" = 0 ] && tail -n 1 "$W/spawn.txt" | tr -d '\r' | grep -qx ok || falha "$1: o filho spawn nao funcionou dentro do pacote"
}
passo "processo filho spawn abre dentro do pacote (python -I) e devolve o valor"
spawn "python" "$PY"
if [ "$SIM" = 0 ]; then passo "o mesmo com pythonw -I, como o atalho do menu Iniciar"; spawn "pythonw" "$PYW"; fi

passo "R1-a, R1-d, R1-e e R1-i do tests/test_s04_ponte.py, com o Python do pacote (casos pulados contam como falha; esperados 9)"
prova "R1-j reprovou: algum caso de R1-a/d/e/i nao passou, foi pulado ou nao rodou" "$PY" pytest "$DW" "$(wp "$REPO/tests")" "$(wp "$SITE")" "$(wp "$W")"
if [ "$SIM" = 1 ]; then passo "OK SIMULADO (c e d NAO conferidos; so o CI do Windows prova): estrutura, licencas, freeze_support, filho spawn e 9 casos do pytest"
else passo "OK: obimcore dentro do instalador; R1-a, R1-d, R1-e, R1-i verdes; DLLs so do pacote; runtime do Visual C++ compativel; filho spawn (python e pythonw)"; fi
