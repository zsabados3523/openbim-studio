# Relatório F0-S02-T10: AppImage Linux (P1)

1. Montei o AppImage do app esqueleto (pasta do ambiente + código + lançador), sem Qt estático e sem executável único.
2. Tamanho: AppImage 927 MiB (971 MB), AppDir 3,4 GB. A meta é 600 MB: NÃO ATINGIDA (ver opções no arquivo de pesquisa).
3. Montagem leva 51 s (com o ambiente runtime já criado; criar o ambiente levou 11 s com cache).
4. Abre a janela offscreen sem Python do sistema (`env -i`): SIM; primeira abertura 8,5 s sem FUSE, 0,5 s com FUSE.
5. `--appimage-extract`: funciona (4 s). Troca de biblioteca: SIM, com .so do Qt trocado o autoteste continua OK.
6. Pasta `licenses/` (AGPL, LGPL-3, LGPL-2.1, GPL-3, inventário, textos dos pacotes), `LGPL-COMO-TROCAR.md` e `FONTES.md`: presentes.
7. Máquina de teste: Zorin OS 18.1. Ubuntu LTS e Fedora: NÃO TESTADO (ficam para a T14).
8. Testes do projeto: 18 passam; `reuse lint` conforme.
9. Opção para o tamanho: tirar vtk/viskores (arrastados pelo OCCT, não usados no app) deu 540 MB em experimento; precisa de decisão do PO.
10. Detalhes: docs/research/2026-10-10-appimage-p1.md.
