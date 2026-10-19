# Fila do lote Opus

> Atualizado: 2026-10-18. Esta fila guarda só o que **aguarda** lote. Lotes feitos ficam no `LOG.md` e em `arquivo/lotes-1-a-28/LOTE_OPUS_N/resultado.md` (lotes 1 a 28; pedido ao lado, em `pedido.md`). Lotes novos ficam em `lotes/LOTE_OPUS_N/` (`pedido.md` e `resultado.md` juntos).
> Regras: lote = 1 sessão Opus com 2–4 itens do mesmo módulo, contexto fechado, saída "aprovado ou reprovado" com lista numerada. Abrir só com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9, 2026-10-14; a exceção de cota de 13/10 acabou). Item esperando mais de 7 dias conta para o gatilho de plano (QUOTA.md).
> Nesta etapa de revisão da F0 nenhuma sessão Opus foi aberta: só cartões escritos e registro aqui.

## Aguardando lote
| # | Item | Origem | Entrou em | Pré-requisito | Prioridade |
|---|---|---|---|---|---|
| 2 | (feito) Revisão da fatia S02: lote 30 em 2026-10-15, 1 aprovado e 4 reprovados por texto, correções aplicadas; relatório `lotes/LOTE_OPUS_30/resultado.md` | PROPOSTA_REVISAO_F0 §3.2 | 2026-10-14 | Concluído; sai da fila | — |
| 3 | (feito) Revisão da fatia S03: lote 31 em 2026-10-15, 5 itens reprovados por texto, correções aplicadas; relatório `lotes/LOTE_OPUS_31/resultado.md` | PROPOSTA_REVISAO_F0 §3.3 | 2026-10-14 | Concluído; sai da fila | — |
| 5 | T17 (módulo no AppImage e instalador; revisão Opus obrigatória, cartão esqueleto a reescrever), T18 (T1), T19 é ADR (decisão do PO) | BOARD | 2026-10-14 | Semanal acima de 25% restante (renova em 21/10) | Média |
| 6 | Revisão completa do projeto pelo Opus (pedido do PO de 2026-10-15), ao fim da S04, antes do portão da F0 | PO | 2026-10-15 | Depois da T19 | Média |
| 7 | (feito) **Lote 57 (planejamento, classe TA, sem implementação):** T20 fase 1 (opções para o pico de memória do arquivo pesado) e T22 (opções para o M2b em IFC real). Feito em 2026-10-18; relatório `lotes/LOTE_OPUS_57/resultado.md` | PO (2026-10-17); `reports/F0-S04-T21.md`, `reports/F0-S04-T22.md` | 2026-10-17 | Concluído; sai da fila | — |
| 8 | (feito) **Lote 58 (planejamento, classe TA, esforço médio, sem implementação):** especificação da 1-B com bloco 250 (T20) e da troca de geometria abaixo de 200 ms no detalhado (T22). Feito em 2026-10-18; relatório `lotes/LOTE_OPUS_58/resultado.md`. Os cartões T3 só nascem depois da escolha do PO (perguntas A25 a A31 em `PO.md`) | PO (2026-10-18); `reports/F0-S04-T24.md` §13, `reports/F0-S04-T25.md` §10 | 2026-10-18 | Concluído; sai da fila | — |
| 9 | **Lote 62 (T3/TA):** decidir entre T-2 (teto de lote dentro de `cena`) e T-3 (compactação adiada) para a troca de geometria, com os números do `reports/F0-S04-T32a.md` (`sem` consertado 234,8 ms em 285 MiB, sem consertado não chega a 100 ms; 2-G tem de somar esse tempo); depois especificar o T32b e o T30a a T30d. Pré-requisito: conferência `jq` do T32a por outro agente (PR 193 mesclado) | T32a | 2026-10-19 | Semanal > 25% restante e janela < 70% | Média |

## Já despachado (resumo; detalhes no LOG)
- **Lote 29 (S01), 2026-10-15: APROVADO 6 de 6** (`lotes/LOTE_OPUS_29/resultado.md`). Aberto pelo líder com a exceção de cota do PO.
- Lotes 1 a 28 executados entre 2026-10-10 e 2026-10-14. O último, lote 28, **aprovou a T12** (PR 83; mescla quando `linux` e `windows` ficarem verdes).
- Opcionais do Opus que ficaram sem cartão (do relatório do dia 14/10): T14b (visibilidade hidden, guarda NOMINMAX), duração zero do juiz de metas (limite conhecido), lote 24 de T16b (estado morto, `sem_malha` por peça, medir modo uma-peça no arquivo real do PO). Viram cartão quando a D1 acabar.

## Pedido do PO (2026-10-15): revisão completa
Revisão Opus de **tudo** (código, arquitetura, documentos), depois da implementação. Se feita antes da S10, cobre todo o projeto implementado até então. Recomendo no fim da S04, antes do portão da F0. Ainda sem lote nem data; abrir só com o uso conferido (regra D9) ou com ok do PO por evento.
