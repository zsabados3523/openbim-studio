# Quadro da F0

> Atualizado: 2026-10-10 (sessão 2). Fonte: `v2/03_fase0_especificacao.md`. Legenda de status: PRONTA · EM_ANDAMENTO · BLOQUEADA (aguarda dependência) · AGUARDA_PO · AGUARDA_OPUS · FEITA · CONTÍNUA.

## Fatias
| Fatia | Nome | Tam. | Depende de | Status | Cartões | Observação |
|---|---|---|---|---|---|---|
| F0-S01 | Repositório, licenças e pesquisa | P | — | EM_ANDAMENTO | S01-T01 a T12 | Falta: lote Opus (T11, T12); espelho Codeberg depois |
| F0-S02 | CI Windows+Linux e app esqueleto | M→G (tratada como G) | S01 | BLOQUEADA | S02-T01 a T15 | S02-T01 pode começar quando S01-T01 estiver feita |
| F0-S03 | Protótipo de viewport (Qt RHI) | M | S02; S08 contínuo | NÃO INICIADA (sem cartões) | — | |
| F0-S04 | Ponte Python↔C++ (híbrido vs C++ puro) | G, crítica | S02 | NÃO INICIADA | — | Contém T3 (ponte, threads) |
| F0-S05 | Oplog, undo e merge | M | S04 | NÃO INICIADA | — | Contém T3 (transações, gravação do par). Precisa de formato mínimo provisório do `.obim` antes do ADR-003 |
| F0-S06 | Planta e corte (HLR) + vista no `.obim` | G, crítica | S02; S08 contínuo | NÃO INICIADA | — | Contém T3 (HLR, arquivo lateral) |
| F0-S07 | Tipo paramétrico por script | P | S04 | NÃO INICIADA | — | |
| F0-S08 | Corpus e gabaritos | P, contínuo | — (pasta `corpus/` nasce na S01-T03) | CONTÍNUA (não iniciada) | — | Downloads só com ok do PO. Corpus do PO entra depois, sem bloquear |
| F0-S09 | UX com o PO (wireframes) | M | — (paralelo) | NÃO INICIADA | — | Precisa de 1 h de entrevista com o PO |
| F0-S10 | Calibração e portão | P | S03, S04, S05, S06, S07 | NÃO INICIADA | — | Mede cota; avalia gatilho de plano |
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
| F0-S01-T11 | Tabela mestre de licenças e THIRD_PARTY.md | T2 | sonnet | **opus (lote, exigido pelo aceite)** | T06–T09 | AGUARDA_OPUS (tabela escrita) |
| F0-S01-T12 | ADR-009: licenças e política de conteúdo | TA | opus (lote) | PO (resumo) | T11 | BLOQUEADA |
| F0-S02-T01 | Ficha: dependências no conda-forge/vcpkg/wheels | T2 | sonnet | opus (insumo do ADR-005) | S01-T01 | FEITA (revisão no lote opus) |
| F0-S02-T02 | Esboço do ADR-005 (dependências e build) | TA | opus (lote) | PO (resumo) | S02-T01, S01-T09 | AGUARDA_OPUS |
| F0-S02-T03 | Ambiente de desenvolvimento reproduzível | T2 | sonnet | sonnet; amostra opus | S02-T01 | BLOQUEADA (precisa instalar) |
| F0-S02-T04 | App esqueleto: janela, menu, arrastar-e-soltar | T1 | sonnet | sonnet | S02-T03, S01-T03 | BLOQUEADA |
| F0-S02-T05 | Abrir IFC e mostrar contagem de elementos | T2 | sonnet | sonnet; amostra opus | S02-T04 | BLOQUEADA |
| F0-S02-T06 | CI Linux (build, teste, artefato, REUSE) | T2 | sonnet | sonnet; amostra opus | S02-T05, S01-T01 | BLOQUEADA |
| F0-S02-T07 | CI Windows | T2 | sonnet | sonnet; amostra opus | S02-T06 | BLOQUEADA |
| F0-S02-T08 | CI macOS melhor esforço | T1 | sonnet | sonnet | S02-T06 | BLOQUEADA |
| F0-S02-T09 | Bloquear merge sem Windows+Linux verdes | T0 | PO (líder guia) | PO | S02-T07 | BLOQUEADA |
| F0-S02-T10 | Pacote Linux (AppImage) | T2 | sonnet | sonnet; amostra opus | S02-T06, S02-T02 | BLOQUEADA |
| F0-S02-T11 | Instalador Windows | T2 | sonnet | sonnet; amostra opus | S02-T07, S02-T02 | BLOQUEADA |
| F0-S02-T12 | Teste de gravação de vídeo headless | T2 | sonnet | sonnet | S02-T04 | BLOQUEADA |
| F0-S02-T13 | Medir metas de build e tamanho | T1 | sonnet | sonnet | S02-T10, S02-T11 | BLOQUEADA |
| F0-S02-T14 | Roteiro de aceite do PO e relatório da S02 | T1 | sonnet | PO | S02-T10, S02-T11 | BLOQUEADA |
| F0-S02-T15 | ADR-005 final (decisão com testes) | TA | opus (lote) | PO (resumo) | S02-T13, S02-T02 | BLOQUEADA |

Nenhum cartão de S01 ou S02 é T3 (ver LOG.md).
