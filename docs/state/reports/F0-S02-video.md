<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Relatório T12: gravação do roteiro sem tela

STATUS: SUCESSO parcial (plano B funciona; vídeo MP4 não testado por falta de ok para instalar codificador)

- **Linux:** funcionou. Capturas da janela em cada passo e GIF animado (17 KB, 4 quadros). Exemplo: `F0-S02-video/roteiro.gif`.
- **Windows (CI):** o passo "Gravação do roteiro" roda no job `windows` e envia `out/video/` no pacote do CI. Resultado: ver tabela abaixo, preenchida com o primeiro run depois do merge.
- **Reproduzir:** `QT_QPA_PLATFORM=offscreen python tests/video/gravar_roteiro.py PASTA docs/acceptance/amostras/casa-simples.ifc`.
- **Recomendação para os roteiros de aceite (5 linhas):**
  1. Use capturas sequenciais e GIF animado como padrão: funcionam sem tela, em qualquer sistema, e não precisam instalar nada.
  2. Cada roteiro de fatia gera uma imagem por passo com o texto do passo na legenda.
  3. Vídeo MP4 só se o PO pedir; exige codificador separado (LGPL ou BSD) em ambiente do CI, com ok do PO.
  4. A gravação nunca bloqueia o CI e não é teste: é só para o PO ver.
  5. Quando houver viewport 3D (S03), refazer o experimento: captura de janela OpenGL sem tela pode exigir outro caminho.

| Sistema | Resultado | Arquivo | Link |
|---|---|---|---|
| Linux (local) | funcionou | roteiro.gif | `F0-S02-video/roteiro.gif` |
| Linux (CI) | passo "Gravação do roteiro" roda sem bloquear (revisão S02, 2026-10-15: conferir no próximo run) | | |
| Windows (CI) | idem | | |
