#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Teste do instalador no CI (ADR-005 teste 7, ADR-009 §5.3): instala em silêncio, confere arquivos e licenças,
# abre o app isolado (--selftest) com variáveis de ambiente "sujas", troca uma DLL do Qt, instala por cima,
# confirma que a desinstalação preserva arquivos do usuário e não deixa sobras.
# Uso: test_installer.sh INSTALADOR.exe PASTA_DESTINO_WINDOWS (sem espaços: o /D= do NSIS não aceita)
set -u
# O bash do Git for Windows converte argumentos como /S em caminhos; o NSIS precisa recebê-los como estão.
export MSYS2_ARG_CONV_EXCL="*"
EXE="$1"; DEST="$2"
D="$(cygpath -u "$DEST")"
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $(date +%H:%M:%S) $*"; }

instalar() {
  local t0=$(date +%s)
  "$EXE" /S "/D=$DEST" &
  local pid=$! t=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15; t=$((t + 15))
    echo "   ${t}s: destino $(du -sm "$D" 2>/dev/null | cut -f1) MB"
    [ "$t" -ge 420 ] && { kill "$pid" 2>/dev/null; falha "instalador não terminou em ${t}s"; }
  done
  wait "$pid" || falha "instalador saiu com código $?"
  local dur=$(( $(date +%s) - t0 ))
  echo "   instalação levou ${dur}s"
  [ "$dur" -le 300 ] || falha "instalação levou ${dur}s (meta: até 300 s)"
}

selftest() {  # $1 = rótulo; ambiente sujo e Python isolado (-I), como o atalho
  local t0=$(date +%s) out dur
  out="$(timeout 120 env -i SYSTEMROOT="$SYSTEMROOT" TEMP="$TEMP" QT_QPA_PLATFORM=offscreen \
        PYTHONPATH='C:\nao-existe' PYTHONHOME='C:\nao-existe' PYTHONUSERBASE='C:\nao-existe' \
        "$D/env/python.exe" -I "$D/app/OpenBIM-Studio.pyw" --selftest 2>&1)"
  dur=$(( $(date +%s) - t0 ))
  out="$(printf "%s" "$out" | tail -n 1 | tr -d '\r')"
  echo "   $1: '$out' em ${dur}s"
  [ "$out" = "OK" ] || falha "$1: selftest não imprimiu OK"
  [ "$dur" -le 10 ] || falha "$1: abriu em ${dur}s (meta: até 10 s)"
}

passo "instalando em $DEST"
instalar
passo "conteúdo instalado"
for f in app/OpenBIM-Studio.pyw Uninstall.exe LGPL-COMO-TROCAR.md FONTES.md licenses/AGPL-3.0-or-later.txt \
         licenses/LGPL-3.0.txt licenses/LGPL-2.1.txt licenses/GPL-3.0.txt licenses/OCCT-exception-1.0.txt \
         licenses/INVENTARIO.md licenses/REMOVIDOS.md env/python.exe env/Library/bin/Qt6Core.dll; do
  [ -f "$D/$f" ] || falha "faltou $f"
done
grep -rqi "GNU LESSER GENERAL PUBLIC LICENSE" "$D/licenses/pacotes" || falha "sem texto da LGPL em licenses/pacotes"
ach=$(find "$D/env" \( -iname 'avcodec*' -o -iname 'avformat*' -o -iname 'x264*' -o -iname 'x265*' -o -iname 'vtk*.dll' -o -iname 'TKIVtk*' \) -not -path '*/conda-meta/*' | head -n 5)
[ -z "$ach" ] || falha "achou arquivo podado: $ach"

passo "abrindo o app (isolado, com variáveis de ambiente sujas)"
selftest "primeira abertura"

passo "troca de uma DLL do Qt (sem trava de hash/assinatura)"
Q="$D/env/Library/bin/Qt6Core.dll"
a=$(sha256sum "$Q" | cut -d' ' -f1); printf '\0' >> "$Q"; b=$(sha256sum "$Q" | cut -d' ' -f1)
[ "$a" != "$b" ] || falha "a troca não mudou a DLL"
selftest "com a DLL trocada"

passo "instalando por cima (a DLL trocada deve voltar ao original)"
instalar
c=$(sha256sum "$Q" | cut -d' ' -f1)
[ "$c" = "$a" ] || falha "instalar por cima não restaurou a DLL original"
selftest "depois da reinstalação"

passo "desinstalando (um arquivo do usuário na pasta deve sobreviver)"
echo "meu arquivo" > "$D/arquivo-do-usuario.txt"
MSYS2_ARG_CONV_EXCL="*" timeout 300 "$D/Uninstall.exe" /S "_?=$DEST" || falha "desinstalador saiu com código $?"
sleep 3
rm -f "$D/Uninstall.exe"
[ -f "$D/arquivo-do-usuario.txt" ] || falha "a desinstalação apagou um arquivo do usuário"
rm -f "$D/arquivo-do-usuario.txt"
for x in env app licenses; do [ ! -e "$D/$x" ] || falha "sobrou $x depois de desinstalar"; done
rmdir "$D" 2>/dev/null
passo "OK: instalação, abertura isolada, troca de DLL, reinstalação e desinstalação sem sobras"
