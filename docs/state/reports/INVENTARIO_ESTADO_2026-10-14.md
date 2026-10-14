<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Inventário do estado (etapa 0 da proposta de revisão), 2026-10-14

Escopo: `BOARD.md`, `LOG.md`, `PO.md`, `QUOTA.md`, `QUEUE_OPUS.md`, `docs/PAINEL_DO_PROJETO.md`, cartões e relatórios. Só leitura; nada foi corrigido. Cada achado diz onde está e como conferir.

## Resumo
A informação existe, mas está espalhada e parte está velha. O quadro (`BOARD.md`) não mostra a S04 de verdade; a fila e a cota pararam em 12/10. O `LOG.md` mistura dois formatos. Risco: o próximo orquestrador começa lendo o quadro e entende errado onde o projeto está.

## Achados (ordem de gravidade)
| # | Achado | Onde / como conferir | Proposta |
|---|---|---|---|
| 1 | `BOARD.md` diz "Atualizado: 2026-10-10 (sessão 2)", mas já traz fatos de 13/10. Não tem tabela de cartões da S03 nem da S04 (31 cartões T01 a T19 com sufixos b/c). O status real da S04 só existe no `LOG.md` e no relatório do dia. | `BOARD.md:3`; `ls cards/F0-S04-*` (31) | Cartão de correção: tabela de cartões S03 e S04 gerada a partir do LOG; data certa no cabeçalho |
| 2 | Na linha da S03 do quadro, a coluna "Cartões" contém texto velho ("T05 REPROVADA... PRs 16, 18 e 19 aguardam") que contradiz a coluna Status (CONCLUÍDA). | `BOARD.md`, linha F0-S03 | Limpar; deixar só o que está aberto (T08-G, T27, T23) |
| 3 | Os cartões não têm campo de status. Estado do cartão = procurar no LOG. Cartão T14c, T15, T17 a T19 ainda são "esqueleto" de uma linha de objetivo (copia do título). | `cards/F0-S04-T15.md` etc. | Uma linha `Status:` no formato do cartão; T15, T17, T18, T19 reescritos antes de abrir |
| 4 | `QUEUE_OPUS.md` parou em "Lote 9 (a preparar)". Lotes 10 a 28 aconteceram. A regra do CLAUDE.md manda ler esse arquivo no início da sessão. | `QUEUE_OPUS.md:35` | Reduzir a: itens aguardando lote, com data. Histórico fica no LOG |
| 5 | `QUOTA.md`: última linha de 12/10 (sessão 6b). Faltam 13 e 14/10 (só há notas soltas, ex.: "semanal 75%" e "janela 90%, semanal 13%" no relatório do dia). Medição das semanas 1 a 4 é obrigatória (v2/04 §6) e alimenta o gatilho de plano. | `QUOTA.md` registro | Preencher com os números que o PO informou; pedir `/usage` hoje |
| 6 | `docs/state/LOTE_OPUS_1..9.md` (pedidos) ficam ao lado de `reports/LOTE_OPUS_N.md` (resultados). Do lote 10 em diante só existe o relatório (`LOTE_OPUS_10b`, `24` a `28`...). Dois lugares, duas convenções. | `ls docs/state`, `ls reports` | Mover pedidos para `reports/pedidos/` (ou apagar após o resultado); regra única. Mover é cartão T0 |
| 7 | Dois formatos no `LOG.md`: linhas com `2026-10-12 \| ... \| ...` e linhas com `- 2026-10-13 \| ... \| T3 \| ...`. Várias linhas passam de 600 caracteres e dificultam a busca. | `LOG.md` linhas ~100-140 | Formato fixo de 4 colunas; texto longo vai ao relatório e o LOG aponta |
| 8 | `PAINEL_DO_PROJETO.md` (atualizado 13/10) diz S04 "reta final"; o relatório do dia (14/10) lista T12, T14c, T15, T17 a T19 e medições oficiais pendentes. Duas fontes dizem coisas diferentes. | `PAINEL:9` vs `reports/RELATORIO_DO_DIA_2026-10-14.md` | Painel passa a ser a única visão do PO; BOARD é a visão da máquina; relatório do dia é histórico |
| 9 | `PO.md` cresceu para 170 linhas, com seção "Abertas" (P1 a P7) já respondidas e decisões em ordem cronológica por assunto. Dificulta achar a regra em vigor (ex.: regra do Opus: 25%/60% no CLAUDE.md vs 70% da janela e exceção vencida em 14/10). | `PO.md:67-77`, `PO.md:167-169` | Separar "Regras em vigor" (curta) do "Histórico de respostas". A exceção de cota do Opus venceu em 14/10 09:00Z: marcar como encerrada |
| 10 | O mesmo PR agrupa temas diferentes e o relatório do dia lista decisões pendentes (7 itens) que não estão em `PO.md` como abertas. | relatório do dia, "Precisa da sua autorização" | As 7 viram linhas "Abertas" em `PO.md`, junto com D1 a D8 |
| 11 | Exceções de tamanho de diff (434, 520, 529, 552, 650, 501 linhas) são aceitas caso a caso, "por precedente". A regra de 400 linhas virou sugestão. | `LOG.md` lotes 14, 18, 22, T14b, T14c | Relacionado à D8: registrar exceção com meta original; revisão pelo PO se a regra deve mudar (mexe em CLAUDE.md: só por cartão) |
| 12 | Três reprovações seguidas do Opus no mesmo cartão (T12, 3x) e escalonamento "não repetido" justificado só no LOG. Regra do CLAUDE.md: 2 reprovações = reescrever o cartão. | `LOG.md` 2026-10-14 T12 | Registrar a decisão de processo no `PO.md` (PO conhece?) ou aplicar a regra |
| 13 | Raiz com 3 planos antigos que o CLAUDE.md manda ignorar. `AGENTS.md` aparece na lista de arquivos do projeto, mas não existe no `main` (talvez só na pasta local). | raiz; `git ls-files AGENTS.md` vazio | D2 (mover planos para `docs/arquivo/`); conferir `AGENTS.md` na pasta local do PO |

## O que está bom
- Cada lote Opus tem relatório numerado com aprovado/reprovado em `reports/` (28 relatórios).
- Decisões do PO têm data e ficam em `PO.md`.
- CI com `linux` e `windows` obrigatórios, merge automático só com verde.

## Não verificado
- Contagem de testes verdes por fatia (passo 4 do roteiro): fica para a revisão de cada fatia.
- Conteúdo de `docs/review/` e `docs/design/`: não lido.
- Uso de cota atual (`get_usage`): não consultado; nenhuma sessão Opus foi aberta nesta etapa. Quando for preciso, a regra do CLAUDE.md pede semanal >25% e janela <70%; o texto da mensagem de hoje diz <60%. **Conflito a decidir (veja D9 abaixo na pergunta ao PO).**
