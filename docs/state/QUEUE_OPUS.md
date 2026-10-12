# Fila do lote Opus

> Regras (`v2/04` §3.1 e §7): lote = 1 sessão opus com 2–4 itens do mesmo módulo; contexto fechado (especificação, diffs, resultados, sem ler o repositório); saída fixa = aprovado ou reprovado com lista numerada. Nunca abrir com menos de 25% da cota semanal restante. Item esperando >7 dias conta para o gatilho de plano. Lotes 1 e 2 executados (2026-10-10 e 2026-10-11). Lote 1 pronto em 2026-10-10: pedido em `docs/state/LOTE_OPUS_1.md`.**

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

## Lote 2 (pedido pronto em `docs/state/LOTE_OPUS_2.md`, 2026-10-10; itens abaixo + revisão do AppImage e sonda C++)
| # | Item | Origem | Entrou em | Prioridade |
|---|---|---|---|---|
| 1 | Conferir o diff da correção da tabela mestre (v2) e os arquivos que ficaram fora do lote 1: `THIRD_PARTY.md`, `docs/state/reports/F0-S01.md` e a lista de componentes de `v2/03` S01 | S01-T11 | 2026-10-10 | Média |
| 2 | (se o PO confirmar) revisar o texto novo de `v2/05` §3 proposto pelo líder | v2/05 | 2026-10-10 | Baixa |
| 3 | Amostra de revisão (1 em 3 das T2): sonda C++ S02-T16 (`prototypes/cpp_probe/`, `docs/research/2026-10-10-sonda-cpp.md`). Pergunta: a conclusão "IfcOpenShell 0.9 usa `ifcopenshell::file` e libs `libifcopenshell.*` compartilhadas" fecha o teste 2 do ADR-005 e muda o teste 5 (R1)? | S02-T16 | 2026-10-10 | Média |
| 4 | **Revisão obrigatória** do AppImage P1 (S02-T10): `packaging/linux/` (AppRun com PYTHONHOME fixo, build_appimage.sh), `docs/research/2026-10-10-appimage-p1.md`. Checar as obrigações do ADR-009 §5.3 (bibliotecas separadas, sem trava contra troca, licenses/, LGPL-COMO-TROCAR.md, FONTES.md) e a poda de vtk/viskores se o PO aprovar | S02-T10 | 2026-10-10 | Alta |

## Já despachado: lote 2 (2026-10-11)
Resultado em `docs/state/reports/LOTE_OPUS_2.md`. Tabela mestre APROVADA; v2/05 APROVADO; AppImage e instalador REPROVADOS (7 e 4 defeitos, só correções curtas); sonda C++ amostra aprovada; CI com 1 defeito (lista de licenças permitidas). Próximo lote (lote 3): conferir os diffs dos cartões S02-T17 e S02-T18, amostra de S02-T19 e S02-T20, ADR-005 final (S02-T15).

## Lote 3 (pedido pronto em `docs/state/LOTE_OPUS_3.md`, 2026-10-11)
T17/T18 (correções do lote 2), amostra de T19/T20 e ADR-005 final (T15). Cota semanal usada: 12%. Aguarda o ok do PO.

## Lote 6: FEITO (2026-10-12), resultado em `reports/LOTE_OPUS_6.md`
Lote 7 (a abrir): revisão do oráculo T08-0, de T08-A/B1/B2 e da T26 (oráculo e código). Cada cartão T3 espera o lote; nada entra no `main` sem aprovado.

## Lote 9 (a preparar): especificação da S04 (ponte Python↔C++, híbrido vs C++ puro; TA + T3)
Itens: especificar os dois fluxos (A híbrido e B C++ puro), o corpus, o oráculo das metas de v2/03 (compartilhar o modelo sem cópia, 200 ms p95 por parede, GIL, 1.000 paredes em 20 s), ADR-001 e ADR-004 (threads); dividir em cartões ≤400 linhas. Incluir os pontos do lote 8 §2.3 (iterador por peça, orçamento de peças lentas) e a seleção por triângulo. Aguarda o PO.
