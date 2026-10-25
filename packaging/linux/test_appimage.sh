#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Teste das obrigacoes de licenca do AppImage (ADR-005 testes 7 e 8) e do autoteste.
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

passo "montado de verdade (FUSE), sem extrair: e o que o usuario faz ao dar duplo clique"
out="$(env -u APPIMAGE_EXTRACT_AND_RUN "$IMG" --selftest 2>&1 | tail -n 1)"
if [ "$out" = "OK" ]; then
  echo "   montado: OK"
elif [ -n "${OBIM_EXIGIR_FUSE:-}" ]; then
  falha "montado (sem extrair) nao abriu ($out); sem libfuse2 o usuario veria o mesmo"
else
  echo "   AVISO: montagem nao testada aqui ($out); precisa de libfuse2 (OBIM_EXIGIR_FUSE=1 torna isto obrigatorio)"
fi

passo "ambiente sujo: PYTHONPATH e PYTHONHOME do usuario nao podem atrapalhar (modo isolado)"
out="$(PYTHONPATH=/nao/existe PYTHONHOME=/nao/existe PYTHONUSERBASE=/nao/existe QT_QPA_PLATFORM=offscreen "$IMG" --appimage-extract-and-run --selftest 2>&1 | tail -n 1)"
[ "$out" = "OK" ] || falha "com PYTHONPATH/PYTHONHOME do usuario o programa nao abriu ($out)"

passo "extrair (direito de trocar bibliotecas: LGPL-COMO-TROCAR.md passo 1)"
( cd "$W" && "$IMG" --appimage-extract >/dev/null ) || falha "--appimage-extract falhou"
R="$W/squashfs-root"
for f in licenses/AGPL-3.0-or-later.txt licenses/LGPL-3.0.txt licenses/LGPL-2.1.txt licenses/GPL-3.0.txt \
         licenses/OCCT-exception-1.0.txt licenses/nanobind-BSD-3-Clause.txt licenses/tsl-robin-map-MIT.txt licenses/INVENTARIO.md licenses/REMOVIDOS.md licenses/FONTES.md \
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
passo "seletor nativo: plugin do portal no pacote e AppRun o ativa"
PT="$R/env/lib/qt6/plugins/platformthemes/libqxdgdesktopportal.so"
[ -s "$PT" ] || falha "faltou o plugin do portal ($PT)"
[ -s "$R/env/lib/libQt6DBus.so.6" ] || falha "faltou libQt6DBus (o plugin precisa dela)"
grep -q "QT_QPA_PLATFORMTHEME=xdgdesktopportal" "$R/AppRun" || falha "AppRun nao ativa o tema do portal"
out="$(env -u DBUS_SESSION_BUS_ADDRESS QT_QPA_PLATFORM=offscreen "$R/AppRun" --selftest 2>&1 | tail -n 1)"
[ "$out" = "OK" ] || falha "sem barramento D-Bus o programa nao abriu ($out)"
out="$(QT_QPA_PLATFORMTHEME=xdgdesktopportal DBUS_SESSION_BUS_ADDRESS=unix:path=/nao/existe QT_QPA_PLATFORM=offscreen "$R/AppRun" --selftest 2>&1 | tail -n 1)"
[ "$out" = "OK" ] || falha "com o portal ativo mas sem portal real o programa nao abriu ($out)"
passo "OK: licencas presentes, nada podado reapareceu, troca de biblioteca funciona"
