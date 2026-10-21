# Quadro da F0

> Atualizado: 2026-10-18 (noite; nova sessão de orquestração: T26, T27 e lote Opus 59 feitos). Só o que está **aberto**. Visão da máquina; o PO lê `docs/PAINEL_DO_PROJETO.md`. Fonte: `v2/03_fase0_especificacao.md`. Status de uma palavra: PRONTA · EM_ANDAMENTO · PAUSADA · BLOQUEADA · AGUARDA_PO · AGUARDA_OPUS · ABERTA · NAO_INICIADA · CONTINUA. Fatias e cartões fechados, com a história de cada um (lotes, reprovações, PRs): `arquivo/BOARD-historico-2026-10-15.md` e `LOG.md`.

## Fatias
| Fatia | Nome | Tam. | Status | Nota |
|---|---|---|---|---|
| F0-S01 | Repositório, licenças e pesquisa | P | FECHADA | Aceita pelo PO (2026-10-15). Abertos sem bloquear: termos do conda-forge, SINAPI (requisito da F5) |
| F0-S02 | CI Windows+Linux e app esqueleto | G | FECHADA | Aceita pelo PO (2026-10-15). Resta o cartão F0-S02-T23 (antes do primeiro release) |
| F0-S03 | Protótipo de viewport (Qt RHI) | M | FECHADA | Portão aprovado pelo PO. Restam T27 e T28 (abaixo). Relatório: `reports/F0-S03.md` |
| F0-S04 | Ponte Python↔C++ (híbrido vs C++ puro) | G, crítica | EM_ANDAMENTO | Medição oficial de 2026-10-17 (`reports/F0-S04.md`) reprovou 3 metas; o PO manteve as metas. (1) Memória do pesado: **fecha na placa** (5.863 MB, abertura 51,6 s; T20/T29/T29e). (2) Troca de parede (M2b): **fecha na placa** (pior 82,8 ms contra 200; T30). (3) Parede de 150 aberturas na forma 2: reforçar a forma 1, decisão formal no T19. Também faltam: decisão do PO sobre a meta de 10 min do CI (T23), T34b, roteiro T18 (depois da decisão do T19) e T19 (ADR-001 e ADR-004, decisão do PO) |
| F0-S05 | Oplog, undo e merge | M | NAO_INICIADA | Depende da S04. Requisitos de gravação: `cards/F0-S05/F0-S05-T00-requisitos-gravacao.md` |
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
| F0-S04-T15f/g | Instabilidade do caso lote (queda por corrupção de memória) | T3 | FEITA | T15g mesclada (pedido 145); falta confirmar 3 rodadas verdes seguidas do Windows no CI |
| F0-S04-T17 | Módulo no AppImage e instalador | T2 | FEITA | T17a (pedidos 151 e 152) e T17b (oráculo no 156, implementação no 155, mesclada em 2026-10-17; Opus lotes 53 e 56). Instalador 310,6 MB. Achados abertos sem bloqueio no `LOG.md` |
| F0-S04-T18 | Tempos de build e relatório da fatia | T1 | EM_ANDAMENTO | Medição oficial feita (2026-10-17). Relatório no pedido 158 e cartões/registros no pedido seguinte. Falta: roteiro de aceite do PO (A18: escrito depois da decisão do T19). A16 respondida em 2026-10-17 (cartão T23) |
| F0-S04-T19 | ADR-001 e ADR-004 com números | TA | EM_ANDAMENTO (lote Opus 68) | PO decidiu em 2026-10-21: ADR-001 híbrido; ADR-004 forma mista (forma 1 nos cálculos de geometria, forma 2 nos comandos longos). Opus escreve os ADR e avalia a forma mista contra os números; depois resumo de 5 linhas ao PO |
| F0-S04-V1 | Validar a forma mista (ADR-004 §5.1) | T3 | EM_ANDAMENTO | Oráculo (PRs 245 e 246) reprovado pelo lote 70 por acréscimos; Opus autor acrescenta; implementação pronta localmente (14/14); medição Linux local, Windows (informativo) e placa depois |
| F0-S04-P1 | Porta única do modelo (3C) | T3 | EM_ANDAMENTO | Oráculo (PRs 246 e 247) reprovado pelo lote 70 por acréscimos; implementação pronta localmente (18/18) |
| F0-S04-V1b | `--ifc` em `lote.py` e maior fatia num IFC real | T2 | NAO_INICIADA | Depois do V1; arquivo de 25 MB liberado pelo PO (2026-10-21), tela virtual |
| F0-S04-T20 | Memória final do viewport abaixo de 6,0 GB | T3 | FEITA (meta fecha na placa, 2 medições) | Via T29 + T29e. Placa real (2026-10-21, RTX 3070, bloco 250): 1ª medição pico somado 5.863 / 5.874 / 5.861 MB; 2ª (`main` f10af50, com reinícios gravados pelo T29f): 5.895 / 5.785 / 5.958 MB (pior 5.958; meta < 6.000), abertura 51,2 s (≤ 60), atraso máx 45 a 62 ms; 1 reinício por abertura no bloco 22 (fonte vigia), desenho pela placa (`software` falso). Relatórios `reports/F0-S04-T29-placa-memoria.md` e `-2.md`; ensaio em tela virtual `reports/F0-S04-T29e-ensaio.md` |
| F0-S04-T21 | Onde vai a memória ao abrir o arquivo pesado | T2 | FEITA | Relatório `reports/F0-S04-T21.md` e sonda no `main` (PRs 162 e 163); alimentou o plano do T20 (lote Opus 57) |
| F0-S04-T22 | O que pesa no M2b com modelos reais | T2 | FEITA | Relatório `reports/F0-S04-T22.md` no `main` (PR 161): placa real 49 / 399 / 6.748 ms; levou aos diagnósticos T25 e T27 e ao conserto T30 |
| F0-S04-T25 | Diagnóstico barato da troca de geometria (M2b), cenas sintéticas | T2 | FEITA | Relatório `reports/F0-S04-T25.md` (PRs 168, 170, 183): hipótese confirmada nos contadores (a troca reenvia a cena inteira); levou ao T27, T32 e T30 |
| F0-S04-T23 | Encurtar a cadeia de testes do Windows no CI | T2 | EM_ANDAMENTO (a feito; b a fazer) | T23a, T23b, T23c e T23e (opção (a), instalador) feitos. Fila de testes mediana 17m48 (rodadas 17m41, 18m01, 17m47); instalador 12m07. Falta (b) T23d: dividir os 4 grupos de teste (PO 2026-10-21); depois T23L (Linux). Se não chegar a 10 min, volta ao PO com os números |
| F0-S04-T23e | Encurtar a montagem do instalador do Windows | T3 | FEITA (PR 243 mesclado) | Lote Opus 70 aprovou. Instalador pronto em 12m07 (mediana de 3 rodadas; antes 16m55); script do instalador 338 s → 56 a 89 s; instalador +1% (313,8 MB); instalação do teste 47 s → 15 s. A fila de testes (cerca de 17m45) é agora o que segura a meta de 10 min: próximo T23d (dividir os 4 grupos de teste) |
| F0-S04-T23L | Encurtar o CI do Linux (cartão irmão do T23) | T2 | RASCUNHO | Depois do T23e e T23d; o `appimage` já é curto (3 min), o tempo está no trabalho `linux` (cerca de 30 min) |
| F0-S04-T24 | Testes baratos da memória do arquivo pesado | T2 | FEITA | Relatório `reports/F0-S04-T24.md` (PRs 169, 171, 173): tela real com bloco 250 em 5.867 / 5.894 MB. A pergunta A24 virou o cartão T29 (código no `main`) |
| F0-S04-T26 | R-0: simular a regra de reinício nos números gravados do T24 | T2 | FEITA | MESCLADO (PR 178, 2026-10-18; revisão sonnet aprovada): relatório `reports/F0-S04-T26.md`. R-A serve nos dados: 0 reinícios falsos em 12 aberturas; tempo perdido 0,57 a 1,77 s (G de 0,5 a 2,0 GB); pior total 53,31 a 54,51 s. Precisa isentar o 1º bloco de cada filho. Regra "memória que sobrou" refutada. Não escolhe G: decisão no T29 |
| F0-S04-T27 | G-0a: troca de geometria com os 13 tamanhos de lote (sintético, tela virtual) | T2 | FEITA | MESCLADO (PR 179). Cena inteira reenviada: ~404 quadros em toda troca (45 de 45). Opus (lote 59): o "modelo não vale" usou a entrada errada; com a cena inteira acerta; causa em `cena.cpp` linha 110 e `motor.h` linha 203 |
| F0-S04-T32 | G-0b: T32a (instrumentação e tempo de `atualizar`); T32b cancelado | T3 | FEITA (T32a; T32b cancelado) | Lote Opus 62 (2026-10-19): decisão **T-2, teto de lote C = 8 MiB dentro de `cena`** (T-1 não fecha: 234,8 + cerca de 60 ms ≈ 295 ms em 285 MiB; T-3 herda o salto e soma thread). T32b dispensável. PR 193 (relatório T32a): tirar as duas sondas do PR e corrigir 3 textos antes de mesclar; conferência dos números por `jq` por outro agente (líder). Próximo: T30a1 |
| F0-S04-T29 | Bloco 250 mais reinício planejado (R-A, G = 1.000 MB, isenção do 1º bloco do filho) | T3 | FEITA (código no `main`) | Mesclados em ordem: 185 (21:23Z), 188 (00:12Z), 189 (00:46Z), cada um com commit de merge e CI verde na ponta que entrou (conferências mecânicas do lote 62 feitas, 0 linhas de diferença no código aprovado). Falta: cartão T1/T2 da sonda de ensaio, ensaio do pesado em tela virtual (A32 liberada) e medição oficial na placa. Resultados em `lotes/LOTE_OPUS_60/61/62` |
| F0-S04-T30 | M2b abaixo de 200 ms no detalhado (T-2: teto de lote C = 8 MiB dentro de `cena`) | T3 | FEITA (meta fecha na placa; lote Opus 66 aprovou) | Troca de parede na RTX 3070 (2026-10-20, `main` cb434a5): mediana 32,7 / 32,6 / 48,9 ms (sintética, 25 MB, detalhado), p95 até 49,6 ms, pior 82,8 ms (parede criada), contra 49 / 399 / 6.748 antes. Relatório `reports/F0-S04-T30-placa.md`. T30a1 a a3, b1 a b3, c e d1 a d3 no `main` |
| F0-S04-T30a1 | `sem` consertado na cena (reescopo: `ger_` e instantâneo foram para o T30b) | T3 | FEITA (PR 200 mesclado) | Aprovado pelo lote Opus 63 (73a16a2); `bytes_copia` +2.757 bytes exato contra +788.869 antes |
| F0-S04-T30d1 | Oráculo do `sem` consertado | T3 | EM_REVISAO (PR 199) | Aprovado pelo lote Opus 63 com 1 commit do autor do oráculo (3 linhas); merge depois do 200 (já no main) |
| F0-S04-T30a3 | Acessor `Cena.dados_lote(seq)` (leitura bit a bit) | T3 | FEITA (PR 210 mesclado) | Aprovado pelo lote Opus 64 (a97da0e) |
| F0-S04-T30d2 | Oráculo dos sub-lotes (11 exigências) | T3 | FEITA (PR 211 mesclado) | Aprovado pelo lote Opus 64 (5d837cf); marcadores tirados pelo autor do oráculo no ramo do 204 (181de50) |
| F0-S04-T30a2 | Divisão em sub-lotes de até 8 MiB dentro de `preparar` | T3 | APROVADO (PR 204), entra por último | Lote Opus 64 aprovou 710ad57. Ordem: 210 → 211 → 204 (mesclar o `main` no ramo, autor do oráculo tira as 4 linhas, CI verde, merge). Depois: cartões T30b e T30c |
| F0-S04-T33 | Sonda do ensaio da R-A no pesado (tela virtual) | T2 | FEITA (ensaio de 1 abertura feito) | Sonda mesclada (PR 203); padrão do bloco corrigido para 250 (PR 206). Ensaio T33b, 2ª rodada (bloco 250, tela virtual, 1 abertura): 60,75 s, 1 reinício `vigia` no bloco 22, conta A 5.921 MB, 5 de 6 critérios de parada passaram; falhou `primeira_vs_base_ok` (memória do filho caiu em 4 blocos). Levado ao Opus (lote 63, ponto 7). Relatório `reports/F0-S04-T33b.md`. Faltam até 2 aberturas e a placa |
| F0-S04-T34 | Teste instável do T15c | T3 | FEITA (PR 222) | Aprovado pelo lote Opus 66; falha rara 29/30 vira o cartão T34b |
| F0-S04-T34b | Guardar a mensagem do teste instável do T15c e, se voltar, `razao_exec` pela mediana | T3 | FEITA (PR 235 mesclado) | Parte (a) feita; Opus (lote 67 + revisão curta) aprovou. Parte (b) NÃO feita: só se `razao_exec` inconclusiva (0,3 a 0,8) voltar a aparecer (bateria de 10: 0,97 a 1,13) |
| F0-S04-T29f | `medir.py` grava `reinicios`, `registro_reinicio` e `desenho` | T2 | FEITA (PR 234 mesclado) | Provou na placa o reinício (bloco 22, vigia) e o desenho pela RTX 3070 |
| F0-S04-T30b1 | Cena: instantâneo coerente e contadores no Python | T3 | FEITA (PR 217 mesclado) | Aprovado pelo lote Opus 65 |
| F0-S04-T30b2 | Motor: reenvio por posição, entrada atômica e troca sem subir `ger_` | T3 | APROVADO (PR 218), falta tirar os 5 `@AINDA_NAO` e o CI | Lote Opus 65 aprovou; main mesclado no ramo; autor do oráculo T30d3 tira os marcadores em commit próprio; depois T30b3 |
| F0-S04-T30d3 | Oráculo do reenvio, do instantâneo e dos contadores | T3 | FEITA (PR 219 mesclado) | Aprovado pelo lote Opus 65; 5 `@AINDA_NAO` valem até o 218 |
| F0-S04-T30c | Sondas de sub-lote nos dados reais (só números) | T2 | FEITA (PR 220; relatório PR 221) | T2_VALE nos 3 IFC do PO (`reports/F0-S04-T30c-dados-reais.md`) |
| F0-S04-T30b3 | Expor `geracao` ao Python e limpar código morto (`proximo`, `Cursor`) | T3 | FEITA (PR 229 mesclado) | Aprovado pelo lote Opus 66. `DadosCena::geracao()` sem uso sai no próximo cartão que mexer em `cena.h` |
| F0-S04-T29e | Medida `pos_emitir_mb` e critério novo (d′, e) do ensaio do pesado | T3 | FEITA (PRs 227 e 228 mesclados) | Aprovado pelo lote Opus 66 (oráculo no Linux: 104 passaram; 2 mutações reprovam). Ensaio do pesado em `reports/F0-S04-T29e-ensaio.md` |

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
