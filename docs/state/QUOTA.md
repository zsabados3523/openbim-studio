# Cota (plano Claude Pro)

> Medição obrigatória nas semanas 1–4 da F0 (`v2/04` §6). Percentuais lidos de `/usage` pelo PO. Gatilho de plano avaliado no fim da semana 4: parou por limite em ≥2 dias/semana em 3 de 4 semanas; fila opus com item >7 dias; projeção da 1.0 acima de 42 meses.

## Orçamento semanal
| Fatia da semana | Alvo |
|---|---|
| sonnet (líder + implementador) | ~70% |
| opus (lotes, 1–2 por semana) | ~20% |
| reserva | ~10% |
| haiku | residual |

Regras: sem sessão opus com menos de 25% da semana restante; sem subagente paralelo se a janela de 5 h passou de 60%; uso do PO em outras conversas sai do mesmo bolo (anotar estimativa).

## Registro
`?` = não medido e sem como recuperar (ver Pendência de medição). "Antes" e "depois" = valor mostrado por `/usage` no começo e no fim da sessão.

| Data | Sessão | Modelo | Tarefa | Janela 5 h antes → depois | Semana antes → depois | Parou por limite? | Obs. |
|---|---|---|---|---|---|---|---|
| 2026-10-10 | 1 | sonnet | PREP: CLAUDE.md, docs/state, cartões S01 e S02 | 22% → 29% | 2% → 3% | não | Informado pelo PO. Sessão de preparação: +7 pontos na janela, +1 ponto na semana. |
| 2026-10-10 | 2 | sonnet (+ haiku em 5 subagentes) | S01: git, LICENSE, esqueleto, READMEs, fichas de licença A–D, push | 29% → 34% | 3% → 3% | não | Informado pelo PO. Leitura de páginas públicas feita por haiku. |
| 2026-10-11 | 3 | sonnet | S02 T07 a T11 (CI Windows, instalador NSIS, poda por pacote) e início de T12–T14 | 0% (janela nova) | semana: 3% → 8% | não | PO informou 8% semana e 0% janela no início desta sessão |
| 2026-10-11 | 3b | opus (lote 2, sessão do PO) + sonnet (aplicar resultado) | Lote Opus 2: tabela, v2/05, AppImage, instalador, sonda, CI | 18% (após o lote e o início desta sessão) | semana 10% | não | O PO informou 18% (janela) e 10% (semana) ao pedir "Leia docs/state e continue"; sem separar o custo do lote |
| 2026-10-11 | 4 | opus (lote 3, sessão do PO) + sonnet (sonda 3b, N1, D1) | Lote Opus 3; sonda 3b; correções T21 e T22; PR 5 e 6 | 18% → 20% (informado após o lote 3 e as correções) | 10% → 14% | não | O PO informou 20% (janela) e 14% (semana) ao pedir para seguir as recomendações; o lote 3 custou cerca de 2 pontos de semana, sem separar do restante |
| 2026-10-12 | 6 | sonnet (+ opus lote 6 na sessão do PO + subagentes sonnet T08-0/T08-A) | Lote 6 aplicado, T05 mesclada, T08-0, T08-A | 77% → renovada → 33% | 22% → 24% | não | Informado pelo PO ao pedir para continuar (janela 33%, semana 24%) |
| 2026-10-12 | 6b | sonnet (+ opus lotes 7 e 8 na sessão do PO + ~12 subagentes sonnet) | S03 fechada: T08 completa, T26, T26b, T06b, relatório final | 33% → 53% | 24% → 32% | não | Informado pelo PO; semana reseta na quarta-feira |
| 2026-10-13 | 7 | sonnet + opus (lotes 11 a 22, sessão do PO e do líder) + subagentes sonnet | S04: T05 a T16b e lotes 11 a 22 | não medido | não medido → 75% (fim da tarde) | não informado | Só consta a nota solta "janela 67%, semanal 75%" (fim da tarde). Números antes/depois **não foram anotados**: não inventar. |
| 2026-10-14 | 8 | sonnet + opus (lotes 23 a 28) | S04: T11c, T12, T14a, T14b; plano v2/02 Revisão 3; inventário | não medido → 90% (renova 20:50Z) | 13% usado (semanal, relatório do dia; semana renovou 09:00Z) | **Sim**: janela em 90% ao fim do dia, pausa combinada | Opus gasto no dia: lotes 23 a 28 (cerca de 6). Números de início do dia não medidos. |

## Pendência de medição
**Fechada em 2026-10-15 (F0-RG-20).** Os números de `/usage` de 13/10 (antes e depois) e de 14/10 (início da janela e fim da semana) não foram anotados na hora e não existem em outro lugar: ficam marcados **"não medido"**. Não inventar. Os valores conhecidos de 13 e 14/10 são os da tabela acima (notas soltas do PO). Daqui em diante, o fim de cada sessão pede ao PO os percentuais e grava antes/depois; se o PO não informar, escrever "não informado" na hora, sem `?`.
Regra de abertura do Opus em vigor: semanal acima de 25% restante e janela abaixo de 70% (D9).

## Resumo semanal (preencher no fim de cada semana)
| Semana | Dias parados por limite | Custo médio por fatia (P/M/G) em % semanal | Fila opus mais antiga (dias) |
|---|---|---|---|
| 1 (10 a 14/10) | 1 dia com pausa por limite (14/10, janela em 90%); sem medida nos demais | Não calculável: faltam antes/depois de 13 e 14/10 | 0 (a fila Opus só tinha itens pausados pela D1) |
- 2026-10-13 (fim da tarde): janela 67%, semanal 75% (25% restante, no limite). Opus pausado até a renovação; sem novos subagentes em paralelo (janela >60%).
- 2026-10-16/17 (sessão longa do líder, sonnet + opus lotes 32 a 51): semanal 55% → 76%; janela de 5 h passou de 100% duas vezes (renovou 14:30Z e 00:30Z). Opus por lotes com autorização do PO acima de 70% da janela. Piso de 25% semanal restante atingido: sem novo lote Opus até a renovação semanal em 2026-10-21 09:00Z.
