# Quadro da F0

> Atualizado: 2026-10-10 (sessão 2). Fonte: `v2/03_fase0_especificacao.md`. Legenda de status: PRONTA · EM_ANDAMENTO · BLOQUEADA (aguarda dependência) · AGUARDA_PO · AGUARDA_OPUS · FEITA · CONTÍNUA.

## Fatias
| Fatia | Nome | Tam. | Depende de | Status | Cartões | Observação |
|---|---|---|---|---|---|---|
| F0-S01 | Repositório, licenças e pesquisa | P | — | FEITA (2026-10-11; aprovada no lote Opus 2) | S01-T01 a T12 | Abertos sem bloquear: termos conda-forge, Qt Shader Tools, ReportLab, SINAPI; espelho Codeberg depois |
| F0-S02 | CI Windows+Linux e app esqueleto | M→G (tratada como G) | S01 | EM_ANDAMENTO | S02-T01 a T16 | S02-T01 pode começar quando S01-T01 estiver feita |
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
| F0-S02-T10 | Pacote Linux (AppImage) | T2 | sonnet | **opus, obrigatória** | S02-T06, S02-T02 | REPROVADA no lote Opus 2 (7 defeitos, nenhum pede refazer a montagem); correções no cartão S02-T17; 389 MB no CI |
| F0-S02-T11 | Instalador Windows (NSIS) | T2 | sonnet | **opus, obrigatória** | S02-T07, S02-T02 | REPROVADA no lote Opus 2 (4 defeitos); correções no cartão S02-T18; o CI verde segue valendo (482 MB, instala/abre/desinstala) |
| F0-S02-T12 | Teste de gravação de vídeo headless | T2 | sonnet | sonnet | S02-T04 | EM ANDAMENTO: experimento no Linux feito (GIF), Windows a confirmar no CI; vídeo MP4 aguarda ok do PO |
| F0-S02-T13 | Medir metas de build e tamanho | T1 | sonnet | sonnet | S02-T10, S02-T11, S02-T16 | ESCRITA (relatório F0-S02-metricas.md); duas pendências: AppImage no CI e build incremental |
| F0-S02-T14 | Roteiro de aceite do PO e relatório da S02 | T1 | sonnet | PO | S02-T10, S02-T11 | ESCRITA (docs/acceptance/F0-S02.md, parte A pronta; parte B aguarda AppImage no CI) |
| F0-S02-T15 | ADR-005 final (decisão com testes) | TA | opus (lote) | PO (resumo) | S02-T13, S02-T02 | BLOQUEADA |
| F0-S02-T16 | Sonda C++ mínima (pacote IfcOpenShell e módulo nanobind) | T2 | sonnet | sonnet; amostra opus | S02-T03 | FEITA (amostra aprovada no lote Opus 2; testes 2 e 3 do ADR-005 fecham só no Linux; ver S02-T19) |
| F0-S02-T17 | Correções do AppImage (lote opus 2, defeitos 1 a 7) | T2 | sonnet | **opus, em lote (diff)** | S02-T10 | FEITA no CI (verde, 389 MB, testes de licença e troca de .so); falta conferência opus (lote 3); runtime do appimagetool pendente |
| F0-S02-T18 | Correções do instalador Windows (defeitos 1 a 4 e riscos 5 a 7) | T2 | sonnet | **opus, em lote (diff)** | S02-T11, S02-T17 | FEITA no CI (verde, 309 MB sem MKL, testes de reinstalação, DLL trocada e arquivo do usuário); falta conferência opus (lote 3) |
| F0-S02-T19 | Teste 2 no Windows e sonda 3b (cabeçalhos pesados) | T2 | sonnet | sonnet; amostra opus | S02-T16 | FEITA (teste 2 fechado nos dois sistemas; sonda 3b passou: Linux 4,8 s, Windows 19,4 s; PR 5; amostra opus no lote 3) |
| F0-S02-T20 | Lista de licenças permitidas no inventário (teste 9 do ADR-005) | T2 | sonnet | sonnet; amostra opus | S02-T06 | FEITA (CI verde, 24 testes; achou MKL e runtimes da Microsoft no Windows; amostra opus no lote 3) |

Nenhum cartão de S01 ou S02 é T3 (ver LOG.md). A prova do R1 (ponte C++/Python) é T3 e fica na S04.
