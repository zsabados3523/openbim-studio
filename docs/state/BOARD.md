# Quadro da F0

> Atualizado: 2026-10-23 (S04 fechada: aceite do PO pelo roteiro `docs/acceptance/S04.md`; relatório `reports/F0-S04-fechamento.md`; S05 aberta; T01 e T01b feitas; P6 decidida, mapa juntado ao painel). Só o que está **aberto**. Visão da máquina; o PO lê `docs/PAINEL_DO_PROJETO.md`. Fonte: `v2/03_fase0_especificacao.md`. Status de uma palavra: PRONTA · EM_ANDAMENTO · PAUSADA · BLOQUEADA · AGUARDA_PO · AGUARDA_OPUS · ABERTA · NAO_INICIADA · CONTINUA. Fatias e cartões fechados, com a história de cada um (lotes, reprovações, PRs): `arquivo/BOARD-historico-2026-10-15.md` e `LOG.md`.

## Fatias
| Fatia | Nome | Tam. | Status | Nota |
|---|---|---|---|---|
| F0-S01 | Repositório, licenças e pesquisa | P | FECHADA | Aceita pelo PO (2026-10-15). Abertos sem bloquear: termos do conda-forge, SINAPI (requisito da F5) |
| F0-S02 | CI Windows+Linux e app esqueleto | G | FECHADA | Aceita pelo PO (2026-10-15). Resta o cartão F0-S02-T23 (antes do primeiro release) |
| F0-S03 | Protótipo de viewport (Qt RHI) | M | FECHADA | Portão aprovado pelo PO. Restam T27 e T28 (abaixo). Relatório: `reports/F0-S03.md` |
| F0-S04 | Ponte Python↔C++ (híbrido vs C++ puro) | G, crítica | FECHADA | Aceita pelo PO em 2026-10-23 (roteiro `docs/acceptance/S04.md`). Relatório: `reports/F0-S04-fechamento.md` |
| F0-S05 | Oplog, undo e merge | M | EM_ANDAMENTO | Plano e cartões T01 a T12 em `cards/F0-S05/README.md` (ordem, dependências, perguntas P1 a P6 ao PO; P1 a P5 aprovadas pelo PO em 2026-10-23, P6 aprovada pelo PO em 2026-10-23). Requisitos G1 a G6, M1 e M2 do T00 copiados nos cartões |
| F0-S06 | Planta e corte (HLR) + vista no `.obim` | G, crítica | NAO_INICIADA | Contém T3 |
| F0-S07 | Tipo paramétrico por script | P | NAO_INICIADA | Depende da S04 |
| F0-S08 | Corpus e gabaritos | P | CONTINUA | Downloads só com ok do PO |
| F0-S09 | UX com o PO (wireframes) | M | AGUARDA_PO | Entrevista aceita pelo PO em 2026-10-15, com um ajuste (A13 em `PO.md`: depois dos eixos vem a estrutura; paredes não presas a eixos). Faltam os desenhos de tela (wireframes), que começam quando o PO mandar as imagens |
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
| F1-D3D11-dispositivo-unico | Um dispositivo D3D11 por processo (herdeiro do F0-S04-T07e) | T3 | NAO_INICIADA | Adiado à F1 pelo PO (2026-10-22); `cards/F1-D3D11-dispositivo-unico.md` |
| F1-CI-cadeia-instalador | Cadeia do instalador no CI do Windows (meta de 10 min) | T3 | NAO_INICIADA | Adiado à F1 (2026-10-23); `cards/F1-CI-cadeia-instalador.md` |
| F0-S05-T01 | Organização: quadro, mapa e painel | T1 | FEITA | P6 decidida pelo PO em 23/10: quadro e painel ficam; mapa juntado ao painel e apagado em T01b. Relatório `reports/F0-S05-T01-organizacao.md` |
| F0-S05-T01b | Juntar o mapa no painel e atualizar o CLAUDE.md (P6) | T0 | FEITA | Cartão `cards/F0-S05/F0-S05-T01b.md`; `docs/MAPA_DO_PROJETO.md` apagado; CLAUDE.md com o painel |
| F0-S05-T02 | Sondas do ifcopenshell (só números) | T2 | FEITA | Relatório `reports/F0-S05-T02.md`; PR 282 mesclado; Windows do CI não medido (PO: fica para o T10); achados para o T03: chaves de `inverses` em JSON e vazamento do `registry` |
| F0-S05-T03 | ADR-002, rascunho | TA | EM_REVISAO (PR 283) | Opus lote 78 escreveu; lote 79 reprovou (14 problemas) e o autor corrigiu; falta nova revisão (janela de 5 h acima de 70%) e o aceite do PO |
| F0-S05-T04 | Transação única IFC + lateral, prova das 10.000 | T3 | NAO_INICIADA | Depende de T03; P1, P2 |
| F0-S05-T05 | Diário de transações e recuperação | T3 | NAO_INICIADA | Depende de T04; P4, P5 |
| F0-S05-T06 | Gravação atômica de um arquivo | T3 | NAO_INICIADA | Depende de T03 |
| F0-S05-T07 | Gravação do par com diário | T3 | NAO_INICIADA | Depende de T04, T06; P2 |
| F0-S05-T08 | Limite de memória do desfazer | T3 | NAO_INICIADA | Depende de T02, T04, T05 |
| F0-S05-T09 | Autosave na pasta local | T3 | NAO_INICIADA | Depende de T05, T07; P5 |
| F0-S05-T10 | Medição das metas (5 ms em 50 MB) | T2 | NAO_INICIADA | Depende de T04, T05, T07, T08; P3 |
| F0-S05-T11 | Protótipo de merge (não é portão) | T3 | NAO_INICIADA | Depende de T04, T05 |
| F0-S05-T12 | Fechamento: ADR-002 com números | TA + T1 | NAO_INICIADA | Depende de T10, T11 |

## Revisão geral da F0 (2026-10-15)
Cartões F0-RG-01 a RG-25 (relatório `reports/F0-REVISAO-GERAL-2026-10-15.md`, Parte D). Andamento de cada um: `LOG.md` e os PRs no GitHub.
Revisão final da noite: `reports/F0-RG-25-revisao-final.md`. Cartões novos que saíram dela:

| Cartão | Título | Classe | Status | Nota |
|---|---|---|---|---|
| F0-RG-26 | Duas travas a mais na régua do intervalo máximo | T3 | PRONTA | Aprovado pelo PO; revisão Opus de outra sessão |
| F0-RG-27 | Seleção devolveu objeto já removido (teste concorrente) | T3 | FEITA | Corrigida: PR 132 mesclado (2026-10-15); causa era a régua do teste, não o C++ |
| F0-RG-28 | CLAUDE.md: pasta dos relatórios Opus e guarda dos oráculos | TA | AGUARDA_PO | PO aprova o texto exato |

## Feito (resumo; detalhes no histórico)
- S01: T01 a T12, R1 a R3. S02: T01 a T22, T24, T25 (PR 98), R1 a R3. S03: T01 a T08 (todas as partes), T25, T26 e emendas, R1 a R3. F0-PLANO-T01.
- S04: T01 a T04c, T05, T06 a T06c, T07 a T08, T09, T10, T10c, T11 a T11c, T12 (PR 83), T13, T14, T14a/b/c/d, T15 (a a i, inclui o relatório das threads), T16, T16b, T17a e T17b (pedidos 151, 152, 156 e 155), medição oficial da T18 (2026-10-17).

Os cartões não têm campo de status; este quadro é a fonte. Ao mudar o status de um cartão, mudar aqui e no `LOG.md`.
