# packaging

Receitas de empacotamento e instalador para Windows e Linux.

## Linux (AppImage, montagem P1 do ADR-005)
Pasta `linux/`:
- `runtime-environment.yml`: ambiente conda só de execução (mesmas versões fixas do `environment.yml`, sem compiladores, cmake, ninja, nanobind e pytest).
- `build_appimage.sh SAIDA_DIR APPIMAGETOOL`: monta o AppDir (pasta `env/` copiada, código de `app/`, `AppRun`, desktop, ícone, `licenses/`, `LGPL-COMO-TROCAR.md`, `FONTES.md`) e gera o `.AppImage`. Os arquivos grandes ficam em `SAIDA_DIR`, fora do repositório.
- `AppRun`, `openbim-studio.desktop`, `openbim-studio.svg/.png` (ícone próprio), `LGPL-COMO-TROCAR.md`, `FONTES.md.in` (modelo).

Passo a passo:
1. `conda env create -f packaging/linux/runtime-environment.yml -p ~/miniforge3/envs/openbim-runtime`
2. Baixar o `appimagetool-x86_64.AppImage` (MIT, github.com/AppImage/appimagetool) e conferir o sha256 (ver `docs/research/2026-10-10-appimage-p1.md`).
3. `packaging/linux/build_appimage.sh /caminho/saida /caminho/appimagetool-x86_64.AppImage`
4. Teste rápido: `QT_QPA_PLATFORM=offscreen ./OpenBIM-Studio-x86_64.AppImage --selftest` imprime `OK`.

Windows (NSIS): ainda não existe (cartão T11).
