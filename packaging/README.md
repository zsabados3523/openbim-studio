# packaging

Receitas de empacotamento e instalador para Windows e Linux.

## Linux (AppImage, ver ADR-005)
Pasta `linux/`:
- (o ambiente de execução fica em `packaging/runtime-environment.yml` e na trava `runtime-environment.*.lock`, usados por Linux e Windows) ambiente conda só de execução (mesmas versões fixas do `environment.yml`, sem compiladores, cmake, ninja, nanobind e pytest).
- `build_appimage.sh SAIDA_DIR APPIMAGETOOL` (exige `OBIMCORE_DIR`, ver abaixo): monta o AppDir (pasta `env/` copiada, código de `app/` e o módulo C++ em `app/obimcore/`, `AppRun`, desktop, ícone, `licenses/`, `LGPL-COMO-TROCAR.md`, `FONTES.md`) e gera o `.AppImage`. Os arquivos grandes ficam em `SAIDA_DIR`, fora do repositório.
- `AppRun`, `openbim-studio.desktop`, `openbim-studio.svg/.png` (ícone próprio), `LGPL-COMO-TROCAR.md`, `FONTES.md.in` (modelo).

Passo a passo:
1. `conda env create -f packaging/runtime-environment.yml -p ~/miniforge3/envs/openbim-runtime`
2. Baixar o `appimagetool-x86_64.AppImage` (MIT) na versão fixa 1.9.1 e conferir o sha256:
   ```bash
   curl -fsSL -o appimagetool-x86_64.AppImage https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
   echo "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0  appimagetool-x86_64.AppImage" | sha256sum -c -
   chmod +x appimagetool-x86_64.AppImage
   ```
   É o mesmo passo do CI (`.github/workflows/ci.yml`). Não use a tag `continuous`: ela muda sem aviso.
3. Compilar o módulo C++ no ambiente de desenvolvimento (o pacote não tem compilador): `bash native/obimcore/build.sh out/s04`, que cria `out/s04/obimcore/`.
4. `OBIMCORE_DIR=$PWD/out/s04/obimcore packaging/linux/build_appimage.sh /caminho/saida /caminho/appimagetool-x86_64.AppImage`. Sem `OBIMCORE_DIR` (ou sem os dois arquivos do módulo) a montagem falha de propósito, e também falha se `ifcopenshell`, `occt`, `pyside6` ou `qt6-main` forem de compilações diferentes nas duas travas (`environment.linux-64.lock` e `packaging/runtime-environment.linux-64.lock`).
5. Teste rápido: `QT_QPA_PLATFORM=offscreen ./OpenBIM-Studio-x86_64.AppImage --selftest` imprime `OK`.
6. O módulo dentro do pacote: `OBIM_PYTEST_SITE=<pasta site-packages com pytest> QT_QPA_PLATFORM=offscreen bash packaging/linux/test_appimage_ponte.sh OpenBIM-Studio-x86_64.AppImage` (também aceita a pasta já extraída). Confere que o `RPATH` do módulo é só relativo e aponta para dentro do pacote, que `freeze_support()` está no programa e no `AppRun`, que um processo filho `spawn` abre dentro do pacote e que R1-a, R1-d, R1-e e R1-i do `tests/test_s04_ponte.py` passam com o Python e as bibliotecas do pacote. O pytest nunca entra no pacote.

O módulo é código do projeto (AGPL v3, cabeçalho SPDX no `__init__.py` gerado); o texto da licença já vai em `licenses/AGPL-3.0-or-later.txt`, e o inventário de licenças só trata de pacotes conda, então segue coerente.

## Windows (NSIS, ver ADR-005)
Pasta `windows/`: `build_installer.sh RUNTIME_ENV SAIDA_DIR` (exige `OBIMCORE_DIR`, ver abaixo; monta `pacote/` com `env/`, `app/` e o módulo C++ em `app/obimcore/`, `licenses/`, `LGPL-COMO-TROCAR.md`, `FONTES.md` e gera `OpenBIM-Studio-Setup.exe` com `openbim-studio.nsi`), `OpenBIM-Studio.pyw` (lançador), `LGPL-COMO-TROCAR.md`. O CI (job `instalador-windows`; o job `windows` só reúne os resultados dos testes do Windows) cria o ambiente de runtime, gera o instalador e testa instalar, abrir (`--selftest`) e desinstalar sem sobras. Instalação por usuário, sem administrador. Sem assinatura: o SmartScreen avisa (esperado até a v0.3).

Módulo C++ no instalador:
1. O pacote não tem compilador. O módulo vem do job `windows-viewport-a` (`bash native/obimcore/build.sh out/s04`, com o Visual C++ do runner), que guarda a pasta `obimcore/` (só `__init__.py` e o `.pyd`) e o pytest no cache do CI; o job `instalador-windows` espera esse job (`needs`) e restaura o cache (falha se não vier).
2. `OBIMCORE_DIR=<pasta>/obimcore bash packaging/windows/build_installer.sh RUNTIME_ENV SAIDA_DIR`. Sem `OBIMCORE_DIR` (ou sem `__init__.py` e exatamente um `_obimcore*.pyd`) a montagem falha de propósito; também falha se `ifcopenshell`, `occt`, `pyside6` ou `qt6-main` forem de compilações diferentes nas duas travas (`environment.win-64.lock` e `packaging/runtime-environment.win-64.lock`) ou se o ambiente de runtime real não tiver exatamente o build da trava.
3. Runtime do Visual C++ (ADR-005): o `vcruntime140*.dll` do pacote conda `vc14_runtime` (o que a trava fixa) tem de ficar em `env\`, junto do `python.exe`; se o pacote conda só o trouxer em `env\Library\bin`, a montagem copia para `env\`. A montagem confere (e o oráculo repete depois de instalar) que a versão dele é igual ou mais nova que a do ligador que gerou o `.pyd`. Nada é baixado de fora da trava.
4. Depois de instalar, e antes de desinstalar: `OBIM_PYTEST_SITE=<site-packages com pytest> bash packaging/windows/test_instalador_ponte.sh <pasta instalada, sem espaços>` (o pytest nunca entra no pacote). O CI faz isso no passo "o módulo dentro do instalador".
