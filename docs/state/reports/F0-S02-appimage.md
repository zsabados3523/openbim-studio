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
