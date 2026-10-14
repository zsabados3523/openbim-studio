# Fila do lote Opus

> Atualizado: 2026-10-14. Esta fila guarda só o que **aguarda** lote. Lotes feitos ficam no `LOG.md` e em `reports/LOTE_OPUS_N.md` (1 a 28). Pedidos antigos `LOTE_OPUS_1..9.md` na pasta `docs/state/` já têm resultado.
> Regras: lote = 1 sessão Opus com 2–4 itens do mesmo módulo, contexto fechado, saída "aprovado ou reprovado" com lista numerada. Abrir só com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9, 2026-10-14; a exceção de cota de 13/10 acabou). Item esperando mais de 7 dias conta para o gatilho de plano (QUOTA.md).
> Nesta etapa de revisão da F0 nenhuma sessão Opus foi aberta: só cartões escritos e registro aqui.

## Aguardando lote
| # | Item | Origem | Entrou em | Pré-requisito | Prioridade |
|---|---|---|---|---|---|
| 1 | Revisão da fatia S01 (cartões `F0-S01-R1` a `R3`; relatório numerado em `reports/`) | PROPOSTA_REVISAO_F0 §3.1 | 2026-10-14 | Cartões R1 e R2 prontos; PO lê o resumo (D6) | Alta |
| 2 | Revisão da fatia S02 (T17/T18 já conferidas no lote 3; falta runtime do appimagetool, T23, tempo do Windows) | PROPOSTA_REVISAO_F0 §3.2 | 2026-10-14 | Lote 1 feito; cartões `F0-S02-R*` ainda por escrever | Média |
| 3 | Revisão da fatia S03 (exceções: memória 6 GB, Windows em VM, teste de tempo 16→100 ms) | PROPOSTA_REVISAO_F0 §3.3 | 2026-10-14 | Lote 2 feito; cartões `F0-S03-R*` ainda por escrever | Média |
| 4 | T14c (Fluxo B, janela Qt Widgets; ramo `s04-t14c`, 501 linhas, exceção aceita) | LOG 2026-10-14 | 2026-10-14 | **Pausada pela D1** até S01 a S03 revisadas e D1 a D8 respondidas | Baixa até a D1 acabar |
| 5 | T15, T17, T18, T19 (cartões esqueleto; T19 é ADR, decisão do PO) | BOARD | 2026-10-14 | Pausadas pela D1; reescrever cartões antes | Baixa até a D1 acabar |

## Já despachado (resumo; detalhes no LOG)
- Lotes 1 a 28 executados entre 2026-10-10 e 2026-10-14. O último, lote 28, **aprovou a T12** (PR 83; mescla quando `linux` e `windows` ficarem verdes).
- Opcionais do Opus que ficaram sem cartão (do relatório do dia 14/10): T14b (visibilidade hidden, guarda NOMINMAX), duração zero do juiz de metas (limite conhecido), lote 24 de T16b (estado morto, `sem_malha` por peça, medir modo uma-peça no arquivo real do PO). Viram cartão quando a D1 acabar.
