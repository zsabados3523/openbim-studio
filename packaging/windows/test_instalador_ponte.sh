#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Teste do instalador Windows (ADR-005 §7.1 prova 7), par de packaging/linux/test_appimage_ponte.sh:
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
# Mudança no teste: a auditoria de DLLs carregadas reprovava QUALQUER modulo fora do pacote e do Windows, mas o antivirus do
#   runner (Windows Defender, provedor AMSI MpOav.dll) e injetado no processo. A regra vigente (classificar() no auxiliar) preserva o proposito, sem lista
#   de excecoes por nome. Modulo de fora do pacote e do Windows REPROVA se: esta sob o prefixo do ambiente de desenvolvimento (OBIM_DEV_PREFIXES, montado
#   aqui e impresso no log; vazio reprova); esta numa pasta do PATH herdado (entrou por busca de nome); tem o mesmo nome de DLL/PYD do pacote; e importado
#   por algum PE do pacote (tabela de imports); e um nucleo (Qt6, TK*, ifcopenshell, ifcgeom, pyside, shiboken, obimcore, python3, runtime do VC);
#   ou tem nome curto 8.3 que nao se resolveu. Modulo do Windows reprova se for nucleo. Qualquer outro (terceiros, como o antivirus) vira a linha
#   "AVISO: modulo de terceiros fora do pacote" e nao reprova.
# Todas as etapas rodam mesmo se uma falhar; o fim lista as que reprovaram e as "NAO EXECUTADA por causa de X" (codigo 1).
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
  *) [ "$SIM" = 1 ] || falha "este teste so vale no Windows (Git bash). Em Linux, so como ensaio: OBIM_TESTE_SIMULADO=1" ;;
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

s_modulo() { [ -f "$D/app/obimcore/__init__.py" ] || falha "faltou app/obimcore/__init__.py dentro da pasta instalada"
  local n; n="$(compgen -G "$D/app/obimcore/_obimcore*.$EXT" | wc -l)"; [ "$n" = 1 ] || falha "esperava 1 app/obimcore/_obimcore*.$EXT, achei $n"
  [ -f "$PY" ] || falha "faltou o Python do pacote ($PY)"; }
s_libbin() { { [ "$SIM" = 1 ] || [ -d "$D/env/Library/bin" ]; } || falha "faltou env/Library/bin (pasta das DLLs que o __init__.py do modulo mostra ao carregador)"; }
s_sem_pytest() { local ach; ach="$(compgen -G "$SP/_pytest"; compgen -G "$SP/pytest"; compgen -G "$D/env/conda-meta/pytest-*.json")"
  [ -z "$ach" ] || falha "o pytest nao pode ir dentro do pacote (so entra neste passo de teste): $ach"; }
s_licencas() { local l
  for l in nanobind-BSD-3-Clause tsl-robin-map-MIT; do
    [ -s "$D/licenses/$l.txt" ] || falha "faltou licenses/$l.txt (ou esta vazio)"
    cmp -s "$D/licenses/$l.txt" "$REPO/packaging/licenses-texts/$l.txt" || falha "licenses/$l.txt difere de packaging/licenses-texts/$l.txt"
  done
  grep -i 'nanobind' "$D/licenses/INVENTARIO.md" | grep -q 'BSD-3-Clause' || falha "INVENTARIO.md nao cita nanobind com BSD-3-Clause na mesma linha"
  grep -iE 'robin[_-]map' "$D/licenses/INVENTARIO.md" | grep -q 'MIT' || falha "INVENTARIO.md nao cita tsl::robin_map com MIT na mesma linha"; }

# Python do pacote em -I, como o atalho. PATH e PYTHONPATH o auxiliar monta como o lancador; o PATH sujo da maquina fica atras (vazamento aparece).
# OBIM_DEV_PREFIXES (separados por |, formato Windows) = prefixos do ambiente de DESENVOLVIMENTO: o que for carregado dali reprova (ver auditar_dlls).
raiz_amb() {  # raiz_amb CAMINHO(unix): sobe ate achar conda-meta e imprime essa raiz em formato Windows
  local d="$1"; while [ -n "$d" ] && [ "$d" != / ] && [ "$d" != . ]; do [ -d "$d/conda-meta" ] && { wp "$d"; return 0; }; d="$(dirname "$d")"; done; return 1
}
DEVP=""   # o CI roda sem CONDA_PREFIX: as raizes vem de CONDA, CONDA_EXE, python/conda do PATH e do OBIM_PYTEST_SITE (cada uma sobe ate a pasta com conda-meta)
for c in "${CONDA_PREFIX:-}" "${CONDA:-}" "$(dirname "$(dirname "${CONDA_EXE:-.}")")" "$(command -v python 2>/dev/null)" "$(command -v conda 2>/dev/null)" "${OBIM_PYTEST_SITE:-}"; do
  [ -n "$c" ] && [ "$c" != . ] || continue
  r="$(raiz_amb "$(up "$c")")" && case "|$DEVP|" in *"|$r|"*) ;; *) DEVP="$DEVP|$r" ;; esac
done
DEVP="${DEVP#|}"
s_prefixos() {
  echo "prefixos do ambiente de DESENVOLVIMENTO (modulo carregado dali reprova): ${DEVP:-<vazio>}"
  [ "$SIM" = 1 ] && return 0
  [ -n "$DEVP" ] || falha "nenhum prefixo do ambiente de desenvolvimento achado (CONDA_PREFIX, CONDA, CONDA_EXE, python/conda no PATH, OBIM_PYTEST_SITE): a prova de vazamento ficaria desligada"
  local p ps; IFS='|' read -ra ps <<< "$DEVP"
  for p in "${ps[@]}"; do case "$p" in [A-Za-z]:|[A-Za-z]:\\) falha "prefixo so com a letra do disco: $p" ;; esac; done
}
no_pacote() {  # no_pacote INTERPRETADOR ARGS...
  local py="$1" rc; shift
  timeout 1500 env -u PYTHONHOME -u PYTHONSTARTUP -u PYTHONUSERBASE -u PYTHONSAFEPATH -u PYTHONPATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV -u VIRTUAL_ENV \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen OBIM_S04_OBRIGATORIO=1 OBIM_TESTE_SIMULADO="$SIM" LC_ALL=C OBIM_DEV_PREFIXES="$DEVP" \
    "$py" -I "$HW" "$@" > "$W/saida.txt" 2>&1
  rc=$?; tr -d '\r' < "$W/saida.txt"; return $rc
}
prova() {  # prova DESCRICAO INTERPRETADOR ARGS...
  local desc="$1" out; shift
  out="$(no_pacote "$@")" && { echo "$out" | tail -n 15; echo "$out" | grep '^AVISO' | sort -u; return 0; }
  echo "$out" | tail -n 250; falha "$desc"
}
s_freeze() { prova "freeze_support ausente ou no lugar errado" "$PY" freeze "$DW"; }
s_vcrt() { prova "runtime do Visual C++ mais velho que o compilador do .pyd (ou ausente)" "$PY" vcrt "$DW"; }
s_dlls() { prova "DLL/PYD de fora do pacote (ou modulo nao carregou)" "$PY" dlls "$DW"; }
spawn() {  # spawn ROTULO INTERPRETADOR: o resultado vai para arquivo (o pythonw nao tem saida de texto)
  rm -f "$W/spawn.txt"
  no_pacote "$2" spawn "$DW" "$(wp "$W/spawn.txt")" > /dev/null; local rc=$?
  [ -f "$W/spawn.txt" ] || falha "$1: o auxiliar nao escreveu o resultado (codigo $rc)"
  tr -d '\r' < "$W/spawn.txt" | tail -n 30
  [ "$rc" = 0 ] && tail -n 1 "$W/spawn.txt" | tr -d '\r' | grep -qx ok || falha "$1: o filho spawn nao funcionou dentro do pacote"
}
s_spawn_py() { spawn "python" "$PY"; }
s_spawn_pyw() { spawn "pythonw" "$PYW"; }
s_pytest() {
  local site; site="$(up "${OBIM_PYTEST_SITE:-/inexistente}" 2>/dev/null)"
  [ -d "$site/_pytest" ] || falha "defina OBIM_PYTEST_SITE com a pasta site-packages que tem o pytest (fora do pacote); valor: '${OBIM_PYTEST_SITE:-}'"
  prova "provas do pacote reprovaram: algum caso nao passou, foi pulado ou nao rodou" "$PY" pytest "$DW" "$(wp "$REPO/tests")" "$(wp "$site")" "$(wp "$W")"
}

# Todas as etapas rodam, mesmo se uma falhar; so no fim sai com codigo 1 listando as que reprovaram. Etapa que depende de outra que nao passou
# fica marcada "NAO EXECUTADA por causa de X" (nunca some do relatorio).
FALHOU=" "; NAOEXEC=" "
etapa() {  # etapa ID DESCRICAO FUNCAO [DEPENDE_DE_ID...]
  local id="$1" desc="$2" fn="$3" d; shift 3
  passo "[$id] $desc"
  for d in "$@"; do case "$FALHOU$NAOEXEC" in *" $d "*) echo "NAO EXECUTADA por causa de '$d' (nao passou)"; NAOEXEC="$NAOEXEC$id "; return 0 ;; esac; done
  ( "$fn" ) || FALHOU="$FALHOU$id "
}
etapa modulo "app/obimcore com __init__.py e um modulo compilado; Python do pacote" s_modulo
etapa libbin "env/Library/bin existe" s_libbin
etapa sem_pytest "sem pytest dentro do pacote" s_sem_pytest
etapa licencas "nanobind (BSD-3-Clause) e tsl::robin_map (MIT) no pacote, texto igual ao do repositorio" s_licencas
etapa prefixos "prefixos do ambiente de desenvolvimento achados (a prova de vazamento depende deles)" s_prefixos
etapa freeze "multiprocessing.freeze_support() em app/openbim_app/main.py e em app/OpenBIM-Studio.pyw (arvore sintatica)" s_freeze
if [ "$SIM" = 0 ]; then
  etapa vcrt "prova 7 (ADR-005): runtime do Visual C++ do pacote >= o do compilador do .pyd" s_vcrt modulo
  etapa dlls "usa a geometria e o modulo C++; todo modulo do processo vem do pacote ou do Windows (terceiros so avisam)" s_dlls modulo
else
  echo "==> PULADO (simulado): prova 7 do runtime do Visual C++ e a conferencia de DLLs carregadas (so o CI do Windows prova)"
fi
etapa spawn_py "processo filho spawn abre dentro do pacote (python -I) e devolve o valor" s_spawn_py modulo
[ "$SIM" = 0 ] && etapa spawn_pyw "o mesmo com pythonw -I, como o atalho do menu Iniciar" s_spawn_pyw modulo
etapa pytest "R1-a, R1-d, R1-e e R1-i do tests/test_s04_ponte.py com o Python do pacote (pulado conta como falha; esperados 9)" s_pytest modulo
if [ "$FALHOU$NAOEXEC" != "  " ]; then
  echo "=== RESULTADO: REPROVADO ==="; echo "Etapas que reprovaram:$FALHOU"; echo "Etapas nao executadas (dependem de outra):$NAOEXEC"; exit 1
fi
if [ "$SIM" = 1 ]; then passo "OK SIMULADO (c e d NAO conferidos; so o CI do Windows prova): estrutura, licencas, freeze_support, filho spawn e 9 casos do pytest"
else passo "OK: obimcore dentro do instalador; R1-a, R1-d, R1-e, R1-i verdes; DLLs so do pacote; runtime do Visual C++ compativel; filho spawn (python e pythonw)"; fi
