<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Como trocar uma biblioteca (LGPL) no OpenBIM Studio para Windows

O OpenBIM Studio usa bibliotecas livres sob a licença LGPL (por exemplo Qt/PySide6, Open CASCADE e IfcOpenShell). Você tem o direito de trocar cada uma por outra versão ou compilação sua. O programa **não confere assinatura nem hash** das bibliotecas: ele abre com a que estiver na pasta.

## Onde ficam as bibliotecas
Na pasta de instalação (por padrão `%LOCALAPPDATA%\Programs\OpenBIM Studio`; ao reinstalar por cima, `env\` e `app\` são recriados, então a sua troca precisa ser refeita), dentro de `env\`, que é um ambiente conda completo:
- Bibliotecas do Qt, OCCT, IfcOpenShell (arquivos `.dll`): `env\Library\bin\` (ex.: `Qt6Core.dll`, `TKernel.dll`)
- Módulos Python (PySide6, ifcopenshell): `env\Lib\site-packages\`
- Plugins do Qt: `env\Library\lib\qt6\plugins\` ou `env\Library\plugins\`
- O código do programa: `app\openbim_app\`

## Passo a passo
1. Feche o OpenBIM Studio.
2. Troque o arquivo `.dll` desejado dentro de `env\Library\bin\`, mantendo o mesmo nome (a versão nova precisa ser compatível com a mesma série).
3. Teste: abra o programa pelo atalho, ou rode `env\python.exe -I app\OpenBIM-Studio.pyw --selftest` num terminal, que deve imprimir `OK`.
4. Você também pode compilar a biblioteca a partir do código-fonte (endereços em `FONTES.md`) e colocar o resultado no lugar.

## Textos de licença e fontes
- Textos de licença: pasta `licenses\` (na pasta de instalação).
- Lista exata dos pacotes e versões (para obter o código-fonte): arquivo `FONTES.md`. O código do OpenBIM Studio e os scripts de montagem estão em https://github.com/zsabados3523/openbim-studio.
