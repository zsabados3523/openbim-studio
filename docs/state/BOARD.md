# Quadro da F0

> Atualizado: 2026-10-14 (correção do inventário). Visão da máquina; o PO lê `docs/PAINEL_DO_PROJETO.md`. Fonte: `v2/03_fase0_especificacao.md`. Legenda de status: PRONTA · EM_ANDAMENTO · BLOQUEADA (aguarda dependência) · AGUARDA_PO · AGUARDA_OPUS · FEITA · CONTÍNUA.

## Fatias
| Fatia | Nome | Tam. | Depende de | Status | Cartões | Observação |
|---|---|---|---|---|---|---|
| F0-S01 | Repositório, licenças e pesquisa | P | — | FEITA (2026-10-11; aprovada no lote Opus 2) | S01-T01 a T12 | Revisão em curso (R1 a R3, 2026-10-14). Abertos sem bloquear: termos do conda-forge, SINAPI (autorização da CAIXA para automação, requisito da F5), ReportLab (aceito pelo PO em 2026-10-15); Qt Shader Tools fechado pela R2; espelho Codeberg depois |
| F0-S02 | CI Windows+Linux e app esqueleto | M→G (tratada como G) | S01 | CONCLUÍDA (aceite do PO em 2026-10-11, Windows e Linux) | S02-T01 a T16 | S02-T01 pode começar quando S01-T01 estiver feita |
| F0-S03 | Protótipo de viewport (Qt RHI) | M | S02; S08 contínuo | CONCLUÍDA (2026-10-12; PO aprovou o portão: atingido no Linux, Windows em software; placa real no Windows é risco para a S10) | S03-T01 a T08, T25 a T27 (tabela abaixo) | Abertos, sem bloquear: T27 (P17 no CI), T28 (Windows físico); T08-G está feita; T23 virou item do plano. Relatório: reports/F0-S03.md. Metas medidas na máquina do PO; memória somada 6,8 GB contra meta de 6 GB, aceita "na prática" (ver PO.md) |
| F0-S04 | Ponte Python↔C++ (híbrido vs C++ puro) | G, crítica | S02 | PAUSADA nas T3 que faltam (D1, 2026-10-14); só terminam PR 83 (T12) | 19 cartões e sufixos (tabela abaixo); relatório: reports/LOTE_OPUS_9.md | Etapa 1 (T01 a T04c) e etapa 2 até T14b feitas. Nenhuma meta medida oficialmente (medições M1 a M6 só na máquina do PO). Contém T3 (ponte, threads) |
| F0-S05 | Oplog, undo e merge | M | S04 | NÃO INICIADA | — | Contém T3 (transações, gravação do par). Precisa de formato mínimo provisório do `.obim` antes do ADR-003 |
| F0-S06 | Planta e corte (HLR) + vista no `.obim` | G, crítica | S02; S08 contínuo | NÃO INICIADA | — | Contém T3 (HLR, arquivo lateral) |
| F0-S07 | Tipo paramétrico por script | P | S04 | NÃO INICIADA | — | |
| F0-S08 | Corpus e gabaritos | P, contínuo | — (pasta `corpus/` nasce na S01-T03) | CONTÍNUA (não iniciada) | — | Downloads só com ok do PO. Corpus do PO entra depois, sem bloquear |
| F0-S09 | UX com o PO (wireframes) | M | — (paralelo) | NÃO INICIADA | — | Precisa de 1 h de entrevista com o PO |
| F0-S10 | Calibração e portão | P | S03, S04, S05, S06, S07 | NÃO INICIADA | — | Mede cota; avalia gatilho de plano |
| F1-PRE-T01 | Comportamento básico de janela e navegação (testes de regressão) | M | S04 (T12) | NÃO INICIADA | docs/state/cards/F1-PRE-T01.md; antes da Fase 1; pedido do PO 2026-10-13 | T2 (viewport em lote opus) |
| Portão F0 | Go/no-go | — | S10 e S09 | — | — | Regras em `03` §5 |

## Cartões de S01 e S02
| Cartão | Título | Classe | Implementa | Revisa | Depende de | Status |
|---|---|---|---|---|---|---|
| F0-S01-T01 | Git local e repositórios remotos | T0 | líder (sonnet) + PO | PO | — | FEITA (push em 2026-10-10; espelho Codeberg adiado) |
| F0-S01-T02 | Arquivo LICENSE (AGPL v3, texto oficial) | T0 | haiku | líder confere hash | — | FEITA |
| F0-S01-T03 | Esqueleto do repositório e modelo de ficha | T0 | haiku | líder | — | FEITA |
| F0-S01-T04 | README e CONTRIBUTING em pt-BR | T1 | sonnet | sonnet | T03 | FEITA |
| F0-S01-T05 | README e CONTRIBUTING em inglês | T0 | haiku | líder | T04 | FEITA |
| F0-S01-T06 | Fichas de licença A: núcleo BIM e geometria | T2 | sonnet | opus (lote) | T03 | FEITA (revisão no lote opus) |
| F0-S01-T07 | Fichas de licença B: interface, ponte e PDF | T2 | sonnet | opus (lote) | T03 | FEITA (revisão no lote opus) |
| F0-S01-T08 | Fichas de licença C: formatos e solver | T2 | sonnet | opus (lote) | T03 | FEITA (revisão no lote opus) |
| F0-S01-T09 | Fichas de licença D: distribuição e empacotamento | T2 | sonnet | opus (lote) | T03 | FEITA (revisão no lote opus) |
| F0-S01-T10 | Ficha de pesquisa: termos do SINAPI | T1 | sonnet | sonnet | T03 | FEITA (termos não verificados: site inacessível) |
| F0-S01-T11 | Tabela mestre de licenças e THIRD_PARTY.md | T2 | sonnet | **opus (lote, exigido pelo aceite)** | T06–T09 | FEITA (aprovada no lote Opus 2, 2026-10-11; 4 observações aplicadas) |
| F0-S01-T12 | ADR-009: licenças e política de conteúdo | TA | opus (lote) | PO (resumo) | T11 | FEITA (aceito pelo PO) |
| F0-S02-T01 | Ficha: dependências no conda-forge/vcpkg/wheels | T2 | sonnet | opus (insumo do ADR-005) | S01-T01 | FEITA (revisão no lote opus) |
| F0-S02-T02 | Esboço do ADR-005 (dependências e build) | TA | opus (lote) | PO (resumo) | S02-T01, S01-T09 | FEITA (esboço aprovado pelo PO; decisão final na T15) |
| F0-S02-T03 | Ambiente de desenvolvimento reproduzível | T2 | sonnet | sonnet; amostra opus | S02-T01 | FEITA (amostra opus: não sorteada) |
| F0-S02-T04 | App esqueleto: janela, menu, arrastar-e-soltar | T1 | sonnet | sonnet | S02-T03, S01-T03 | FEITA |
| F0-S02-T05 | Abrir IFC e mostrar contagem de elementos | T2 | sonnet | sonnet; amostra opus | S02-T04 | FEITA |
| F0-S02-T06 | CI Linux (build, teste, artefato, REUSE) | T2 | sonnet | sonnet; amostra opus | S02-T05, S01-T01 | FEITA (verde em 2026-10-10, run 38078371976; linux ~60 s) |
| F0-S02-T07 | CI Windows | T2 | sonnet | sonnet; amostra opus | S02-T06 | FEITA (verde; windows ~15 min com ambiente limpo e instalador; run 38110728020) |
| F0-S02-T08 | CI macOS melhor esforço | T1 | sonnet | sonnet | S02-T06 | FEITA (verde; macos ~90 s, não bloqueia) |
| F0-S02-T09 | Bloquear merge sem Windows+Linux verdes | T0 | PO (líder guia) | PO | S02-T07 | FEITA em 2026-10-10 (regra no GitHub: `linux` e `windows` obrigatórios; trabalho vai por ramo + PR) |
| F0-S02-T10 | Pacote Linux (AppImage) | T2 | sonnet | **opus, obrigatória** | S02-T06, S02-T02 | REPROVADA no lote Opus 2 (7 defeitos, nenhum pede refazer a montagem); correções no cartão S02-T17; APROVADA no lote opus 3 (7 de 7); 389 MB no CI |
| F0-S02-T11 | Instalador Windows (NSIS) | T2 | sonnet | **opus, obrigatória** | S02-T07, S02-T02 | REPROVADA no lote Opus 2 (4 defeitos); correções no cartão S02-T18; APROVADA no lote opus 3 (4 de 4; defeito novo N1 no cartão T21); 309 MB no CI |
| F0-S02-T12 | Teste de gravação de vídeo headless | T2 | sonnet | sonnet | S02-T04 | FEITA no plano B (capturas e GIF); MP4 aguarda ok do PO |
| F0-S02-T13 | Medir metas de build e tamanho | T1 | sonnet | sonnet | S02-T10, S02-T11, S02-T16 | FEITA (relatório F0-S02-metricas.md; build incremental do Windows aceito pelo PO, revisão na S04) |
| F0-S02-T14 | Roteiro de aceite do PO e relatório da S02 | T1 | sonnet | PO | S02-T10, S02-T11 | FEITA (PO executou o roteiro nos dois sistemas: tudo ok, 2026-10-11) |
| F0-S02-T15 | ADR-005 final (decisão com testes) | TA | opus (lote) | PO (resumo) | S02-T13, S02-T02 | FEITA (lote opus 3; PO aprovou: ADR-005 aceito, 2026-10-11) |
| F0-S02-T21 | Instalador não apaga arquivos do usuário (N1) | T2 | sonnet | sonnet | S02-T18 | FEITA (no `main`, conferido em 2026-10-15) |
| F0-S02-T22 | Inventário: parênteses e lista (D1 e ajustes) | T2 | sonnet | sonnet | S02-T20 | FEITA (no `main`, conferido em 2026-10-15) |
| F0-S02-T23 | Antes do primeiro release | T2 | sonnet | opus (lote) | T17, T18, T22 | NÃO INICIADA (bloqueia release público) |
| F0-S02-T24 | Seletor de arquivos nativo no AppImage (portal do desktop) | T2 | sonnet | sonnet | S02-T17 | FEITA (no `main`, conferido em 2026-10-15; AppRun ativa o portal do desktop quando há D-Bus; teste no CI; o PO confere no passo 15 do roteiro) |
| F0-S02-T16 | Sonda C++ mínima (pacote IfcOpenShell e módulo nanobind) | T2 | sonnet | sonnet; amostra opus | S02-T03 | FEITA (amostra aprovada no lote Opus 2; testes 2 e 3 do ADR-005 fecham só no Linux; ver S02-T19) |
| F0-S02-T17 | Correções do AppImage (lote opus 2, defeitos 1 a 7) | T2 | sonnet | **opus, em lote (diff)** | S02-T10 | FEITA no CI (verde, 389 MB, testes de licença e troca de .so); falta conferência opus (lote 3); runtime do appimagetool pendente |
| F0-S02-T18 | Correções do instalador Windows (defeitos 1 a 4 e riscos 5 a 7) | T2 | sonnet | **opus, em lote (diff)** | S02-T11, S02-T17 | FEITA no CI (verde, 309 MB sem MKL, testes de reinstalação, DLL trocada e arquivo do usuário); falta conferência opus (lote 3) |
| F0-S02-T19 | Teste 2 no Windows e sonda 3b (cabeçalhos pesados) | T2 | sonnet | sonnet; amostra opus | S02-T16 | FEITA (teste 2 fechado nos dois sistemas; sonda 3b passou: Linux 4,8 s, Windows 19,4 s; PR 5; amostra opus no lote 3) |
| F0-S02-T20 | Lista de licenças permitidas no inventário (teste 9 do ADR-005) | T2 | sonnet | sonnet; amostra opus | S02-T06 | FEITA (CI verde, 24 testes; achou MKL e runtimes da Microsoft no Windows; amostra opus no lote 3) |


| F0-S01-R1 | Revisão S01: aceite contra o plano e cobertura | T2 | sonnet | opus (lote) | PR 93 | FEITA (2026-10-14); lote 29 aprovou |
| F0-S01-R2 | Revisão S01: pendências de licença (SINAPI, Qt Shader Tools, conda-forge, ReportLab) | T2 | sonnet | opus (lote) | R1 | FEITA (2026-10-14); ReportLab decidido pelo PO; lote 29 aprovou |
| F0-S01-R3 | Revisão S01: coerência, testes e relatório para o lote Opus | T2 | sonnet | opus (lote) | R1, R2 | FEITA (2026-10-14); lote 29 aprovou |
| F0-S02-R1 | Revisão S02: aceite contra o plano e metas com a meta original | T2 | sonnet | opus (lote) | S01-R3 | FEITA (2026-10-15); lote Opus 30 feito, correções aplicadas |
| F0-S02-R2 | Revisão S02: pendências abertas e licenças dos pacotes | T2 | sonnet | opus (lote) | S02-R1 | FEITA (2026-10-15); lote Opus 30 feito, correções aplicadas |
| F0-S02-R3 | Revisão S02: coerência, testes e relatório para o lote Opus | T2 | sonnet | opus (lote) | S02-R1, S02-R2 | FEITA (2026-10-15); lote Opus 30 feito, correções aplicadas |
| F0-S02-T25 | Reduzir o tempo do job `windows` do CI (incremental) | T2 | sonnet | sonnet; amostra opus | S02 revisada | NÃO INICIADA (pedido do PO, 2026-10-15) |
| F0-PLANO-T01 | T23 no plano (`v2/03`) | TA | opus/sonnet | PO (resumo) | — | FEITA (2026-10-15; PO aprovou) |
| F0-S03-R1 | Revisão S03: aceite e exceções com a meta original | T2 | sonnet | opus (lote) | S02-R3 | FEITA (2026-10-15); lote Opus 31 feito, correções aplicadas |
| F0-S03-R2 | Revisão S03: pendências, risco do Windows, teste de tempo | T2 | sonnet | opus (lote) | S03-R1 | FEITA (2026-10-15); lote Opus 31 feito, correções aplicadas |
| F0-S03-R3 | Revisão S03: coerência, testes e relatório para o lote Opus | T2 | sonnet | opus (lote) | S03-R1, S03-R2 | FEITA (2026-10-15); lote Opus 31 feito, correções aplicadas |

Nenhum cartão de S01 ou S02 é T3 (ver LOG.md). A prova do R1 (ponte C++/Python) é T3 e fica na S04.

## Cartões da S03 (estado conferido no `LOG.md`, 2026-10-14)
| Cartão | Título | Classe | Status |
|---|---|---|---|
| F0-S03-T01 | Ficha: viewport com QRhi | T1 | FEITA |
| F0-S03-T02 | Modelo grande para o benchmark | T1 | FEITA |
| F0-S03-T03 | Janela 3D mínima (QRhiWidget) | T2 | FEITA (amostra Opus aprovada) |
| F0-S03-T04 | Câmera | T2 | FEITA (amostra Opus aprovada) |
| F0-S03-T05 (+P0b, C1) | Malhas do IFC em threads, lotes ao viewport | T3 | FEITA (reprovada no lote 5, corrigida) |
| F0-S03-T06, T06b | Seleção por clique | T2 | FEITA (teste de tempo: 16→100 ms, exceção; ver revisão da S03) |
| F0-S03-T07 | Benchmark e relatório da fatia | T1 | FEITA (reports/F0-S03.md) |
| F0-S03-T08-0, 0b, A, B1, B2, C, D, E | Processo separado, limite por peça, memória | T3 | FEITA (D medida na tela real) |
| F0-S03-T08-G | Duas correções pequenas e guardas | T3 | FEITA (no `main`, conferido em 2026-10-15) |
| F0-S03-T25, T25-C1 | Desenho 3D no CI | T2 | FEITA (S03 concluída) |
| F0-S03-T26, T26b | Localidade numérica na gravação do IFC | T3 / T1 | FEITA |
| F0-S03-T27 | Teste da reabertura (P17) no CI | T1 | ABERTA (sem bloquear) |
| F0-S03-T28 | Medir o viewport num Windows físico (placa real e Intel) | T1 | APROVADA pelo PO em 2026-10-15, NÃO INICIADA (PO aceitou em 2026-10-15 deixar para antes da entrega final; dono: PO; prazo original: antes do portão da F0, S10; criada na revisão da S03; texto reforçado no lote Opus 31) |

## Cartões da S04 (estado conferido no `LOG.md`, 2026-10-14)
| Cartão | Título | Classe | Status |
|---|---|---|---|
| F0-S04-T01 | Ambiente de compilação travado | T2 | FEITA |
| F0-S04-T02, T02b | Oráculo R1 (e correções) | T3 | FEITA (lote 10b) |
| F0-S04-T03, T04, T04c | Módulo `obimcore`, malha por elemento, ajustes | T3 | FEITA (lote 10b); etapa 1 fechada |
| F0-S04-T04b | Registro local de mensagens e fim do mutex | T3 | ADIADA (D1) |
| F0-S04-T05 | Sonda da thread de desenho | T3 | FEITA (lote 11) |
| F0-S04-T06, T06b, T06c | Oráculo da viewport, relógio e cena | T3 | FEITA (lotes 12 a 15) |
| F0-S04-T07, T07b, T08 | Viewport C++ (janela, cena, fila, relógio) | T3 | FEITA (lotes 12 a 14) |
| F0-S04-T09, T10, T10c | Câmera, seleção por triângulo, memória | T3 | FEITA (lotes 15 a 17) |
| F0-S04-T11, T11b, T11c | Fluxo A (PySide6 + ifcopenshell.api) | T3 | FEITA (lotes 18, 19 e 25; PR 82) |
| F0-S04-T12 | Oráculo das metas e da saída igual | T3 | EM_ANDAMENTO (PR 83; Opus aprovou no lote 28; aguarda CI verde) |
| F0-S04-T13 | Fluxo B, paredes em C++ | T3 | FEITA (lote 22, PR 79) |
| F0-S04-T14 (a, b) | Fluxo B: biblioteca abre a base; núcleo C++ puro | T3 | FEITA (PR 87 e PR 90) |
| F0-S04-T14c | Fluxo B: executável com janela Qt Widgets | T3 | PAUSADA (D1); ramo pronto, 501 linhas |
| F0-S04-T15 | Threads e bloqueio do interpretador | T3 | PAUSADA (D1); cartão é esqueleto, reescrever antes de abrir |
| F0-S04-T16, T16b | Abertura: peças lentas e modo isolado | T3 | FEITA (lote 21, PR 78) |
| F0-S04-T17 | Módulo no AppImage e instalador | T2 | NÃO INICIADA (esqueleto; depende da T15) |
| F0-S04-T18 | Tempos de build e relatório da fatia | T1 | NÃO INICIADA (esqueleto) |
| F0-S04-T19 | ADR-001 e ADR-004 com números | TA | NÃO INICIADA (decisão do PO; esqueleto) |
| F0-S04-T20 | Memória final do viewport abaixo de 6,0 GB (fecha a exceção E1) | T3 | CARTÃO ESCRITO (2026-10-15, a pedido do PO); fase 1 (opções) aguarda; fase 2 depende da retomada da S04 (D1) |

Observação: os cartões não têm campo de status; este quadro é a fonte (achado 3 do inventário). Nova regra: ao mudar o status de um cartão, mudar aqui e no `LOG.md`.
