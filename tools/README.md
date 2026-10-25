# tools

Ferramentas de medição e fluxos usados em testes. Não fazem parte do produto.

- `s04/fluxo_a/`: fluxo de edição de referência (Python + `ifcopenshell.api` + `obimcore`), com os scripts de lote usados nas medições de desempenho.
- `s04/fluxo_b/`: o mesmo fluxo em C++ puro, congelado. Serve só de comparação de desempenho (ADR-001). Usa `native/obimcore/`.
- `s04/sondas/` e `s04/medir_s04.py`: sondas e medições de desempenho. `medir_s04.py --linhas --raiz DIR` espera `obimcore/`, `fluxo_a/` e `fluxo_b/` lado a lado em `DIR`.

Os testes ficam em `tests/`.
