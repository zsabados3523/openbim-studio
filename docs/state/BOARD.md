# Quadro da F0

> Atualizado: 2026-10-17 (noite). Só o que está **aberto**. Visão da máquina; o PO lê `docs/PAINEL_DO_PROJETO.md`. Fonte: `v2/03_fase0_especificacao.md`. Status de uma palavra: PRONTA · EM_ANDAMENTO · PAUSADA · BLOQUEADA · AGUARDA_PO · AGUARDA_OPUS · ABERTA · NAO_INICIADA · CONTINUA. Fatias e cartões fechados, com a história de cada um (lotes, reprovações, PRs): `arquivo/BOARD-historico-2026-10-15.md` e `LOG.md`.

## Fatias
| Fatia | Nome | Tam. | Status | Nota |
|---|---|---|---|---|
| F0-S01 | Repositório, licenças e pesquisa | P | FECHADA | Aceita pelo PO (2026-10-15). Abertos sem bloquear: termos do conda-forge, SINAPI (requisito da F5) |
| F0-S02 | CI Windows+Linux e app esqueleto | G | FECHADA | Aceita pelo PO (2026-10-15). Resta o cartão F0-S02-T23 (antes do primeiro release) |
| F0-S03 | Protótipo de viewport (Qt RHI) | M | FECHADA | Portão aprovado pelo PO. Restam T27 e T28 (abaixo). Relatório: `reports/F0-S03.md` |
| F0-S04 | Ponte Python↔C++ (híbrido vs C++ puro) | G, crítica | AGUARDA_PO | T17a e T17b mescladas (pedidos 152 e 155). Medição oficial na tela real feita em 2026-10-17; relatório `reports/F0-S04.md` (pedido 158). Metas não atingidas: memória do pesado (6,84 GB), M2b em IFC real, parede de 150 aberturas na forma 2; PO mandou manter as metas e abrir os cartões T21 e T22. Falta a decisão do PO (T19: ADR-001 e ADR-004) e a pergunta do build incremental do Windows (`PO.md`, A16) |
| F0-S05 | Oplog, undo e merge | M | NAO_INICIADA | Depende da S04. Requisitos de gravação: `cards/F0-S05/F0-S05-T00-requisitos-gravacao.md` |
| F0-S06 | Planta e corte (HLR) + vista no `.obim` | G, crítica | NAO_INICIADA | Contém T3 |
| F0-S07 | Tipo paramétrico por script | P | NAO_INICIADA | Depende da S04 |
| F0-S08 | Corpus e gabaritos | P | CONTINUA | Downloads só com ok do PO |
| F0-S09 | UX com o PO (wireframes) | M | AGUARDA_PO | Entrevista feita; falta aceite do resumo (pergunta A13 em `PO.md`) |
| F0-S10 | Calibração e portão | P | NAO_INICIADA | Depende de S03 a S07 |
| F1-PRE-T01 | Comportamento básico de janela e navegação | M | NAO_INICIADA | Antes da F1; cartão `cards/F1-PRE-T01.md` |
| Portão F0 | Go/no-go | — | NAO_INICIADA | Depende de S10 e S09 (`v2/03` §5) |

## Cartões abertos
| Cartão | Título | Classe | Status | Nota |
|---|---|---|---|---|
| F0-S02-T23 | Antes do primeiro release | T2 | NAO_INICIADA | Bloqueia release público |
| F0-S03-T27 | Teste da reabertura (P17) no CI | T1 | ABERTA | Sem bloquear; cartão em `cards/F0-S03/` |
| F0-S03-T28 | Medir o viewport num Windows físico | T1 | NAO_INICIADA | Aprovada pelo PO; dono: PO; antes da entrega final |
| F0-S04-T04b | Registro local de mensagens e fim do mutex | T3 | PAUSADA | D1 |
| F0-S04-T15f/g | Instabilidade do caso lote (queda por corrupção de memória) | T3 | FEITA | T15g mesclada (pedido 145); falta confirmar 3 rodadas verdes seguidas do Windows no CI |
| F0-S04-T17 | Módulo no AppImage e instalador | T2 | FEITA | T17a (pedidos 151 e 152) e T17b (oráculo no 156, implementação no 155, mesclada em 2026-10-17; Opus lotes 53 e 56). Instalador 310,6 MB. Achados abertos sem bloqueio no `LOG.md` |
| F0-S04-T18 | Tempos de build e relatório da fatia | T1 | EM_ANDAMENTO | Medição oficial feita (2026-10-17). Relatório no pedido 158 e cartões/registros no pedido seguinte. Falta: roteiro de aceite do PO e a pergunta do build incremental do Windows (A16) |
| F0-S04-T19 | ADR-001 e ADR-004 com números | TA | NAO_INICIADA | Decisão do PO; números oficiais prontos em `reports/F0-S04.md` e `reports/F0-S04-threads.md` |
| F0-S04-T20 | Memória final do viewport abaixo de 6,0 GB | T3 | PAUSADA | Cartão-mãe. Medido 6,84 GB (2026-10-17); PO manteve a meta e mandou abrir cartão; a retomada pede o ok do PO (A17) |
| F0-S04-T21 | Onde vai a memória ao abrir o arquivo pesado | T2 | AGUARDA_PO | Rascunho (etapa 1 do T20, só medir); sem ok do PO não começa |
| F0-S04-T22 | O que pesa no M2b com modelos reais | T2 | EM_REVISAO | Relatório COMPLETO em `reports/F0-S04-T22.md` (PR 161): placa real 49 / 399 / 6.748 ms; cena inteira provavelmente reenviada a 2 MiB por quadro (hipótese 1, não provada); opções A a E com o PO |
| F0-S04-T23 | Encurtar a cadeia de testes do Windows no CI | T2 | AGUARDA_PO | Rascunho (a escrever → rascunho para o PO): meta de 10 min do ADR-005 mantida pelo PO (A16, 2026-10-17); hoje 34 min 05 s; 4 tarefas T23a a T23d; piso estimado só com o CI de 15 a 17 min (o resto está em `packaging/`); sem ok do PO não começa |

## Revisão geral da F0 (2026-10-15)
Cartões F0-RG-01 a RG-25 (relatório `reports/F0-REVISAO-GERAL-2026-10-15.md`, Parte D). Andamento de cada um: `LOG.md` e os PRs no GitHub.
Revisão final da noite: `reports/F0-RG-25-revisao-final.md`. Cartões novos que saíram dela:

| Cartão | Título | Classe | Status | Nota |
|---|---|---|---|---|
| F0-RG-26 | Duas travas a mais na régua do intervalo máximo | T3 | PRONTA | Aprovado pelo PO; revisão Opus de outra sessão |
| F0-RG-27 | Seleção devolveu objeto já removido (teste concorrente) | T3 | PRONTA | Aprovado pelo PO; fase 1 é diagnóstico |
| F0-RG-28 | CLAUDE.md: pasta dos relatórios Opus e guarda dos oráculos | TA | AGUARDA_PO | PO aprova o texto exato |

## Feito (resumo; detalhes no histórico)
- S01: T01 a T12, R1 a R3. S02: T01 a T22, T24, T25 (PR 98), R1 a R3. S03: T01 a T08 (todas as partes), T25, T26 e emendas, R1 a R3. F0-PLANO-T01.
- S04: T01 a T04c, T05, T06 a T06c, T07 a T08, T09, T10, T10c, T11 a T11c, T12 (PR 83), T13, T14, T14a/b/c/d, T15 (a a i, inclui o relatório das threads), T16, T16b, T17a e T17b (pedidos 151, 152, 156 e 155), medição oficial da T18 (2026-10-17).

Os cartões não têm campo de status; este quadro é a fonte. Ao mudar o status de um cartão, mudar aqui e no `LOG.md`.
