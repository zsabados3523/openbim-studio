# Fila do lote Opus

> Atualizado: 2026-10-14. Esta fila guarda só o que **aguarda** lote. Lotes feitos ficam no `LOG.md` e em `arquivo/lotes-1-a-28/LOTE_OPUS_N/resultado.md` (lotes 1 a 28; pedido ao lado, em `pedido.md`). Lotes novos ficam em `lotes/LOTE_OPUS_N/` (`pedido.md` e `resultado.md` juntos).
> Regras: lote = 1 sessão Opus com 2–4 itens do mesmo módulo, contexto fechado, saída "aprovado ou reprovado" com lista numerada. Abrir só com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9, 2026-10-14; a exceção de cota de 13/10 acabou). Item esperando mais de 7 dias conta para o gatilho de plano (QUOTA.md).
> Nesta etapa de revisão da F0 nenhuma sessão Opus foi aberta: só cartões escritos e registro aqui.

## Aguardando lote
| # | Item | Origem | Entrou em | Pré-requisito | Prioridade |
|---|---|---|---|---|---|
| 2 | (feito) Revisão da fatia S02: lote 30 em 2026-10-15, 1 aprovado e 4 reprovados por texto, correções aplicadas; relatório `lotes/LOTE_OPUS_30/resultado.md` | PROPOSTA_REVISAO_F0 §3.2 | 2026-10-14 | Concluído; sai da fila | — |
| 3 | (feito) Revisão da fatia S03: lote 31 em 2026-10-15, 5 itens reprovados por texto, correções aplicadas; relatório `lotes/LOTE_OPUS_31/resultado.md` | PROPOSTA_REVISAO_F0 §3.3 | 2026-10-14 | Concluído; sai da fila | — |
| 4 | T14c (Fluxo B, janela Qt Widgets; ramo `s04-t14c`, 501 linhas, exceção aceita) | LOG 2026-10-14 | 2026-10-14 | **Pausada pela D1** até S01 a S03 revisadas e D1 a D8 respondidas | Baixa até a D1 acabar |
| 5 | T15, T17, T18, T19 (cartões esqueleto; T19 é ADR, decisão do PO) | BOARD | 2026-10-14 | Pausadas pela D1; reescrever cartões antes | Baixa até a D1 acabar |

## Já despachado (resumo; detalhes no LOG)
- **Lote 29 (S01), 2026-10-15: APROVADO 6 de 6** (`lotes/LOTE_OPUS_29/resultado.md`). Aberto pelo líder com a exceção de cota do PO.
- Lotes 1 a 28 executados entre 2026-10-10 e 2026-10-14. O último, lote 28, **aprovou a T12** (PR 83; mescla quando `linux` e `windows` ficarem verdes).
- Opcionais do Opus que ficaram sem cartão (do relatório do dia 14/10): T14b (visibilidade hidden, guarda NOMINMAX), duração zero do juiz de metas (limite conhecido), lote 24 de T16b (estado morto, `sem_malha` por peça, medir modo uma-peça no arquivo real do PO). Viram cartão quando a D1 acabar.

## Pedido do PO (2026-10-15): revisão completa
Revisão Opus de **tudo** (código, arquitetura, documentos), depois da implementação. Se feita antes da S10, cobre todo o projeto implementado até então. Recomendo no fim da S04, antes do portão da F0. Ainda sem lote nem data; abrir só com o uso conferido (regra D9) ou com ok do PO por evento.
