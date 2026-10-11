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
`?` = ainda não informado pelo PO. "Antes" e "depois" = valor mostrado por `/usage` no começo e no fim da sessão.

| Data | Sessão | Modelo | Tarefa | Janela 5 h antes → depois | Semana antes → depois | Parou por limite? | Obs. |
|---|---|---|---|---|---|---|---|
| 2026-10-10 | 1 | sonnet | PREP: CLAUDE.md, docs/state, cartões S01 e S02 | 22% → 29% | 2% → 3% | não | Informado pelo PO. Sessão de preparação: +7 pontos na janela, +1 ponto na semana. |
| 2026-10-10 | 2 | sonnet (+ haiku em 5 subagentes) | S01: git, LICENSE, esqueleto, READMEs, fichas de licença A–D, push | 29% → 34% | 3% → 3% | não | Informado pelo PO. Leitura de páginas públicas feita por haiku. |
| 2026-10-11 | 3 | sonnet | S02 T07 a T11 (CI Windows, instalador NSIS, poda por pacote) e início de T12–T14 | 0% (janela nova) | semana: 3% → 8% | não | PO informou 8% semana e 0% janela no início desta sessão |
| 2026-10-11 | 3b | opus (lote 2, sessão do PO) + sonnet (aplicar resultado) | Lote Opus 2: tabela, v2/05, AppImage, instalador, sonda, CI | 18% (após o lote e o início desta sessão) | semana 10% | não | O PO informou 18% (janela) e 10% (semana) ao pedir "Leia docs/state e continue"; sem separar o custo do lote |
| 2026-10-11 | 4 | opus (lote 3, sessão do PO) + sonnet (sonda 3b, N1, D1) | Lote Opus 3; sonda 3b; correções T21 e T22; PR 5 e 6 | 18% → 20% (informado após o lote 3 e as correções) | 10% → 14% | não | O PO informou 20% (janela) e 14% (semana) ao pedir para seguir as recomendações; o lote 3 custou cerca de 2 pontos de semana, sem separar do restante |

## Resumo semanal (preencher no fim de cada semana)
| Semana | Dias parados por limite | Custo médio por fatia (P/M/G) em % semanal | Fila opus mais antiga (dias) |
|---|---|---|---|
| 1 | | | |
