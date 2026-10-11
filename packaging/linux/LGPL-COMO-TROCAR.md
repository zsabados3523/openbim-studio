<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Como trocar uma biblioteca (LGPL) no OpenBIM Studio

O OpenBIM Studio usa bibliotecas livres sob a licença LGPL (por exemplo Qt/PySide6, Open CASCADE e IfcOpenShell). Você tem o direito de trocar cada uma por outra versão ou compilação sua. O programa **não confere assinatura nem hash** das bibliotecas: ele abre com a que estiver na pasta.

## Onde ficam as bibliotecas
Dentro do pacote, na pasta `env/` (um ambiente conda completo):
- Bibliotecas do programa (Qt, OCCT, IfcOpenShell e outras): `env/lib/*.so*` (ex.: `env/lib/libQt6Core.so.6`, `env/lib/libTKernel.so*`)
- Módulos Python (PySide6, ifcopenshell): `env/lib/python3.12/site-packages/`
- Plugins do Qt: `env/lib/qt6/plugins/`
- O código do programa: `app/openbim_app/`

## Passo a passo
1. Abra um terminal na pasta do arquivo `.AppImage` e extraia: `./OpenBIM-Studio-x86_64.AppImage --appimage-extract` (cria a pasta `squashfs-root/`).
2. Troque o arquivo desejado dentro de `squashfs-root/env/lib/`, mantendo o mesmo nome (a versão nova precisa ser compatível com a mesma série).
3. Teste: `QT_QPA_PLATFORM=offscreen squashfs-root/AppRun --selftest` deve imprimir `OK` (a variável `QT_QPA_PLATFORM=offscreen` só é necessária em máquina sem tela; com tela, basta `squashfs-root/AppRun --selftest`).
4. Para voltar a ter um único arquivo, remonte com o `appimagetool` (MIT): `appimagetool squashfs-root OpenBIM-Studio-trocado.AppImage`. Ou use direto a pasta `squashfs-root/`, que já funciona.

## Terceiro caminho: recompilar
Você também pode compilar a biblioteca a partir do código-fonte (endereços em `FONTES.md`) e colocar o resultado no lugar, como nos passos acima.

## Textos de licença e fontes
- Textos de licença: pasta `licenses/` (dentro do pacote).
- Lista exata dos pacotes e versões (para obter o código-fonte): arquivo `FONTES.md`. O código do OpenBIM Studio e os scripts de montagem estão em https://github.com/zsabados3523/openbim-studio.
