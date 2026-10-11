<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Ficha de pesquisa: gravação de vídeo de roteiro sem tela (F0-S02-T12)

- Data: 2026-10-11 · Autor: líder (sonnet) · Fontes: experimento próprio (nenhuma fonte externa)
- Pergunta (`v2/03` S02, `v2/04` §8): dá para gravar um vídeo curto de um roteiro automático do app, sem tela, no Linux e no CI Windows?
- Método: `tests/video/gravar_roteiro.py` abre a janela (Qt, modo sem tela), executa um roteiro de 4 passos (janela, abrir IFC, abrir arquivo inexistente, reabrir), captura a janela em cada passo com `QWidget.grab()` e monta um GIF animado e um WebP com Pillow, que já vêm no ambiente. Nada novo foi instalado.
- Resultado Linux (local): funcionou. 4 quadros de 1024x700, GIF de 17 KB e WebP de 15 KB em 0,17 s. Exemplo: `docs/state/reports/F0-S02-video/roteiro.gif`.
- Resultado Windows: ver `docs/state/reports/F0-S02-video.md` (resultado lido do CI).
- Vídeo de verdade (MP4/WebM) exige um codificador. O `ffmpeg` do conda-forge usado antes vinha na compilação GPL com x264/x265 e foi removido do pacote do app (achado de licença da T10/T11); usar um codificador só no CI, em ambiente separado, exigiria uma compilação LGPL do ffmpeg ou o codificador VP9 (libvpx, BSD). **Não instalado**: precisa de ok do PO e de checagem de licença.
