# prototypes

Código de apoio ao núcleo do programa: o módulo nativo, o viewport 3D e os fluxos usados em testes e medições. Esta pasta será reorganizada em `native/`, `viewport/` e `tools/`; os nomes abaixo são os de hoje.

- `s04/obimcore/`: **módulo nativo C++ do produto** (`obimcore`, ligado ao Python por nanobind). Malha, cena, seleção e a thread de desenho do viewport. É compilado por `build.sh` e empacotado no AppImage e no instalador (ver `packaging/README.md`). Decisões em `docs/adr/ADR-001` e `ADR-004`.
- `viewport_qrhi/`: viewport 3D em Python (`QRhiWidget`), câmera, seleção por clique e abertura de IFC em processo auxiliar. Ver o `README.md` da pasta.
- `s04/fluxo_a/`: fluxo de edição de referência (Python + `ifcopenshell.api` + `obimcore`), com os scripts de lote usados nas medições de desempenho.
- `s04/fluxo_b/`: o mesmo fluxo em C++ puro, congelado. Serve só de comparação de desempenho (ADR-001).
- `s04/sondas/` e `s04/medir_s04.py`: sondas e medições de desempenho.

Os testes que exercitam esses módulos ficam em `tests/`.
