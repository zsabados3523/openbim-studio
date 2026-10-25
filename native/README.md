# native

Código nativo (C++) do programa.

- `obimcore/`: módulo `obimcore`, ligado ao Python por nanobind. Malha, cena, seleção e a thread de desenho do viewport. Compilado por `obimcore/build.sh` (saída em `out/s04/obimcore/`) e empacotado no AppImage e no instalador (ver `packaging/README.md`). Decisões em `docs/adr/ADR-001` e `ADR-004`.

Os testes ficam em `tests/`.
