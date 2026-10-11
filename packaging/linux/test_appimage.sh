#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Teste das obrigacoes de licenca do AppImage (ADR-009 §5.3, ADR-005 testes 7 e 8) e do autoteste.
# Uso: test_appimage.sh IMAGEM.AppImage   (rodar com QT_QPA_PLATFORM=offscreen em maquina sem tela)
set -u
IMG="$(readlink -f "$1")"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
falha() { echo "FALHA: $*"; exit 1; }
passo() { echo "==> $*"; }

passo "autoteste do AppImage montado"
out="$("$IMG" --appimage-extract-and-run --selftest 2>&1 | tail -n 1)"
[ "$out" = "OK" ] || falha "selftest nao imprimiu OK ($out)"

passo "extrair (direito de trocar bibliotecas: LGPL-COMO-TROCAR.md passo 1)"
( cd "$W" && "$IMG" --appimage-extract >/dev/null ) || falha "--appimage-extract falhou"
R="$W/squashfs-root"
for f in licenses/AGPL-3.0-or-later.txt licenses/LGPL-3.0.txt licenses/LGPL-2.1.txt licenses/GPL-3.0.txt \
         licenses/OCCT-exception-1.0.txt licenses/INVENTARIO.md licenses/REMOVIDOS.md licenses/FONTES.md \
         LGPL-COMO-TROCAR.md env/lib/libQt6Core.so.6; do
  [ -e "$R/$f" ] || falha "faltou $f"
done
grep -rqi "GNU LESSER GENERAL PUBLIC LICENSE" "$R/licenses/pacotes" || falha "sem texto da LGPL em licenses/pacotes"
n=$(find "$R/licenses/pacotes" -mindepth 1 -maxdepth 1 | wc -l)
[ "$n" -ge 200 ] || falha "licenses/pacotes tem so $n pastas"

passo "ausencia do que foi podado (ffmpeg GPL, x264/x265, VTK)"
ach=$(find "$R/env" \( -name 'libav*' -o -name 'libsw*' -o -name 'libx264*' -o -name 'libx265*' -o -name 'libvtk*' -o -name 'libTKIVtk*' \) -not -path '*/conda-meta/*' | head -n 5)
[ -z "$ach" ] || falha "achou biblioteca podada: $ach"

passo "troca de uma biblioteca do Qt (sem trava de hash/assinatura)"
Q="$R/env/lib/libQt6Core.so.6"
Q="$(readlink -f "$Q")"
sha_antes=$(sha256sum "$Q" | cut -d' ' -f1)
printf '\0' >> "$Q"      # arquivo diferente, ainda carregavel
sha_depois=$(sha256sum "$Q" | cut -d' ' -f1)
[ "$sha_antes" != "$sha_depois" ] || falha "a troca nao mudou o arquivo"
out="$(QT_QPA_PLATFORM=offscreen "$R/AppRun" --selftest 2>&1 | tail -n 1)"
[ "$out" = "OK" ] || falha "com a biblioteca trocada o programa nao abriu ($out)"
passo "OK: licencas presentes, nada podado reapareceu, troca de biblioteca funciona"
