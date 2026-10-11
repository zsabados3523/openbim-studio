# Relatório F0-S02-T10: AppImage Linux (P1)

1. Montei o AppImage do app esqueleto (pasta do ambiente + código + lançador), sem Qt estático e sem executável único.
2. Mudança (decisão do PO, opção 1): a montagem agora poda vtk, viskores e vtkmodules (variável `PODA_PADROES` no script). Antes: 971 311 608 bytes (927 MiB). Agora: **565 377 528 bytes (539,2 MiB)**, meta de 600 000 000 bytes: ATINGIDA. AppDir 3,4 GB para 2,0 GB.
3. Montagem leva 39 s (era 51 s), com o ambiente runtime já criado.
4. Abre a janela offscreen sem Python do sistema (`env -i`): SIM (`--selftest` OK, 0,45 s com FUSE).
5. `--appimage-extract`: funciona (2,5 s). Troca de biblioteca: SIM, com .so do Qt alterado o autoteste continua OK.
6. Geometria sem vtk: `ifcopenshell.geom` e `.util` importam; uma parede IFC4 foi tesselada (8 vértices, 12 triângulos, medidas corretas) com `create_shape`. Resíduo: `libTKIVtk` do OCCT fica sem as libs VTK e não carrega (não é usado).
7. Pasta `licenses/` (AGPL, LGPL-3, LGPL-2.1, GPL-3, inventário, textos dos pacotes, `REMOVIDOS.md`), `LGPL-COMO-TROCAR.md` e `FONTES.md` (vtk/viskores marcados "removido na montagem"): presentes.
8. Máquina de teste: Zorin OS 18.1. Ubuntu LTS, Fedora e duplo clique: NÃO TESTADO (T13/T14).
9. Testes do projeto: 18 passam; `reuse lint` conforme (108/108).
10. Detalhes: docs/research/2026-10-10-appimage-p1.md.

## Atualização 2026-10-11 (cartão S02-T17, correção do lote Opus 2)
- **Poda atual:** por pacote (`scripts/prune_packages.py`): vtk, vtk-base, vtk-io-ffmpeg, viskores e ffmpeg, mais 134 pacotes que só eles exigiam (ffmpeg GPL com x264/x265, openvino, hdf5, proj, pillow, libcurl, pulseaudio e o **Mesa**). O script falha se aparecer outro pacote mantido que dependa de algo removido além do `occt`. Também foram apagados `libTKIVtk*` e as pastas vazias do VTK.
- **Mesa fora (decisão do PO, 2026-10-11):** em computador sem driver de vídeo funcionando (máquina virtual, acesso remoto) o programa depende do Mesa do sistema. Teste em máquina virtual sem aceleração entra no roteiro T14; se não abrir, o Mesa volta.
- **Tamanho:** 373 MiB (~391 MB) na montagem local; o CI mediu 389 MB.
- **Licenças:** `licenses/pacotes/` tem os textos de 277 pacotes (do cache do conda, via `collect_package_licenses.py`); LGPL-3, LGPL-2.1, GPL-3 e a exceção do OCCT vêm de `packaging/licenses-texts/` (a montagem falha se faltar algum).
- **Testes no CI** (`packaging/linux/test_appimage.sh`): autoteste, `--appimage-extract`, presença dos arquivos de licença, texto da LGPL em `pacotes/`, ausência de `libav*`, `libx26*`, `libvtk*`, `libTKIVtk*`, e troca de uma biblioteca do Qt (um byte a mais) seguida do autoteste.
- **Pendente, com data (2026-10-11):** fixar o "runtime" do appimagetool (peça que vai dentro do AppImage, hoje baixada pelo appimagetool de uma tag móvel) com versão e sha256 via `--runtime-file`; e os itens 8 a 10 do relatório do lote 2 (fontes por 3 anos, tela Sobre) para o cartão "antes do primeiro release".
