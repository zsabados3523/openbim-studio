#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Teste do instalador no CI: instala em silêncio, confere arquivos e licenças, abre o app (--selftest),
# desinstala e confere que não sobrou nada. Uso: test_installer.sh INSTALADOR.exe PASTA_DESTINO_WINDOWS
set -u
# O bash do Git for Windows converte argumentos como /S em caminhos; o NSIS precisa recebê-los como estão.
export MSYS2_ARG_CONV_EXCL="*"
EXE="$1"; DEST="$2"
D="$(cygpath -u "$DEST")"
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $(date +%H:%M:%S) $*"; }

passo "instalando em $DEST"
"$EXE" /S "/D=$DEST" &
PID=$!
t=0
while kill -0 "$PID" 2>/dev/null; do
  sleep 30; t=$((t + 30))
  echo "   ${t}s: destino $(du -sm "$D" 2>/dev/null | cut -f1) MB; temp do NSIS: $(du -sm "$TEMP"/ns*.tmp 2>/dev/null | tr '\n' ' '); processos: $(tasklist /FO CSV /NH 2>/dev/null | grep -iE '"(tar|xz|7z|OpenBIM-Studio-Setup)[^"]*"' | cut -d, -f1,5 | tr '\n' ' ')"
  [ "$t" -ge 840 ] && { tasklist | grep -iE 'tar|OpenBIM' ; kill "$PID" 2>/dev/null; falha "instalador não terminou em ${t}s"; }
done
wait "$PID" || falha "instalador saiu com código $?"
for _ in $(seq 1 60); do [ -f "$D/Uninstall.exe" ] && break; sleep 2; done
passo "conteúdo instalado"
for f in app/OpenBIM-Studio.pyw Uninstall.exe LGPL-COMO-TROCAR.md FONTES.md licenses/AGPL-3.0-or-later.txt licenses/INVENTARIO.md licenses/REMOVIDOS.md env/python.exe; do
  [ -f "$D/$f" ] || falha "faltou $f"
done
grep -rqi "GNU LESSER GENERAL PUBLIC LICENSE" "$D/licenses/pacotes" || falha "sem texto da LGPL em licenses/pacotes"
passo "abrindo o app (selftest, sem tela)"
out="$(timeout 120 env -i SYSTEMROOT="$SYSTEMROOT" TEMP="$TEMP" QT_QPA_PLATFORM=offscreen "$D/env/python.exe" "$D/app/OpenBIM-Studio.pyw" --selftest 2>&1)"
out="$(printf "%s" "$out" | tail -n 1 | tr -d "\r")"
echo "selftest: $out"
[ "$out" = "OK" ] || falha "selftest não imprimiu OK"
passo "desinstalando"
timeout 300 "$D/Uninstall.exe" /S "_?=$DEST" || falha "desinstalador saiu com código $?"
sleep 3
rm -f "$D/Uninstall.exe"
if [ -d "$D" ] && [ -n "$(ls -A "$D")" ]; then echo "sobras:"; ls -A "$D" | head; falha "sobras após desinstalar"; fi
passo "OK: instalação, abertura e desinstalação sem sobras"
