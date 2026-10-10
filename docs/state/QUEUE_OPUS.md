# Fila do lote Opus

> Regras (`v2/04` §3.1 e §7): lote = 1 sessão opus com 2–4 itens do mesmo módulo; contexto fechado (especificação, diffs, resultados, sem ler o repositório); saída fixa = aprovado ou reprovado com lista numerada. Nunca abrir com menos de 25% da cota semanal restante. Item esperando >7 dias conta para o gatilho de plano. **Nenhum lote foi executado. Lote 1 pronto em 2026-10-10: pedido em `docs/state/LOTE_OPUS_1.md`.**

## Lote 1: licenças e dependências (módulo único)
| # | Item | Origem | Pré-requisito | Entrou em | Prioridade |
|---|---|---|---|---|---|
| 1 | Revisar a tabela mestre de licenças (aceite da S01 exige o papel Arquiteto). Pontos já conhecidos: OCCT é LGPL-2.1-only (05 §3 cobre só "2.1+/3"); libdxfrw com licença disputada; condições de relink do LGPL no empacotamento | S01-T11 | T06 a T09 feitas (prontas em 2026-10-10) | 2026-10-10 | Alta |
| 2 | Escrever o ADR-009 (licenças e política de conteúdo) a partir da tabela revisada, com resumo de 5 linhas em pt-BR para o PO | S01-T12 | Item 1 aprovado | 2026-10-10 | Alta |
| 3 | Esboçar o ADR-005 (conda-forge vs vcpkg vs híbrido): critérios, opções, plano de testes. Não é decisão; a decisão final vem depois dos testes de build (S02-T15) | S02-T02 | S02-T01 e S01-T09 feitas (prontas em 2026-10-10) | 2026-10-10 | Alta |
| 4 | Conferir a classificação T0–T3 dos 27 cartões de S01 e S02 (nenhum T3) e o limite de 400 linhas | Cartões | — | 2026-10-10 | Baixa (só se sobrar cota) |

Itens 1 a 3 formam o lote mínimo; o item 4 entra só se a cota permitir. O líder prepara o pedido de lote (pacote de contexto) e avisa "lote opus pronto".

## Já despachados
- Lote 1 (2026-10-10): itens 1 a 4 executados. Resultado em `docs/state/reports/LOTE_OPUS_1.md`. T11 reprovada (12 defeitos); ADR-009 e esboço do ADR-005 entregues.

## Lote 2 (pendente)
| # | Item | Origem | Entrou em | Prioridade |
|---|---|---|---|---|
| 1 | Conferir o diff da correção da tabela mestre (v2) e os arquivos que ficaram fora do lote 1: `THIRD_PARTY.md`, `docs/state/reports/F0-S01.md` e a lista de componentes de `v2/03` S01 | S01-T11 | 2026-10-10 | Média |
| 2 | (se o PO confirmar) revisar o texto novo de `v2/05` §3 proposto pelo líder | v2/05 | 2026-10-10 | Baixa |
| 3 | Amostra de revisão (1 em 3 das T2): sonda C++ S02-T16 (`prototypes/cpp_probe/`, `docs/research/2026-10-10-sonda-cpp.md`). Pergunta: a conclusão "IfcOpenShell 0.9 usa `ifcopenshell::file` e libs `libifcopenshell.*` compartilhadas" fecha o teste 2 do ADR-005 e muda o teste 5 (R1)? | S02-T16 | 2026-10-10 | Média |
