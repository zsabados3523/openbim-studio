<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S05-T01: organização do quadro, do mapa e do painel (2026-10-23)

Autor: sonnet (T1, só documentos). Os três arquivos foram postos em dia com o fim da S04 e o começo da S05. **Nada foi apagado nem fundido**; o corte espera a resposta P6 do PO.

## Números (comandos citados)
Linhas e bytes: `wc -l` e `wc -c`. Edições: `git log --since='30 days ago' --oneline -- <arquivo> | wc -l` (e `git log --oneline -- <arquivo>` para o total, igual ao do mês). Linhas iguais: `comm -12` entre as linhas não vazias, com 20 caracteres ou mais, ordenadas e sem repetição, de cada par (depois da atualização de hoje).

| Arquivo | O que traz | Quem lê | O que repete dos outros | Edições no último mês | Linhas / bytes | Custo de manter |
|---|---|---|---|---|---|---|
| `docs/state/BOARD.md` | Quadro da máquina: fatias, cartões abertos com status de uma palavra, notas longas por cartão | Líder e subagentes | Linhas iguais: 0 com o mapa, 0 com o painel. Conteúdo: as 10 fatias e o status da S04 e da S05 aparecem também nos outros dois | 113 (22 em 11/10, 16 em 20/10, 14 em 18/10) | 96 / 17.073 | Alto, mas é o trabalho normal do líder (muda a cada tarefa) |
| `docs/MAPA_DO_PROJETO.md` | Versão simples: o que construímos, 7 fases, 10 fatias em linguagem de obra, plano de revisão, perguntas do PO | PO | Linhas iguais: 0 com o quadro, 1 com o painel. Conteúdo: tabela das 7 fases e das 10 fatias (17 linhas) repete o painel; "Perguntas" repete a seção 6 do painel | 2 (15/10 e 18/10) | 73 / 6.179 | Médio: ficou 5 dias parado e já dizia "S05 não começou" |
| `docs/PAINEL_DO_PROJETO.md` | Fase atual, plano das 7 fases, fatias, tarefas da S04 e da S05, ferramentas por fase, decisões tomadas, 20 pendências com recomendação | PO | Linhas iguais: 0 com o quadro, 1 com o mapa. Conteúdo: o mapa é um resumo dele | 4 (13/10, 15/10, 15/10, 18/10) | 116 / 14.438 | Alto: é longo e tinha 5 dias de atraso; pede revisão a cada sessão |

Linhas iguais de verdade quase não existem porque cada arquivo foi reescrito à mão; a repetição é de **assunto**: os três dizem o estado da S04 e da S05 (46, 6 e 9 linhas citam a S04 em cada um, por `grep -c`), então uma mudança tem de ser feita em três lugares.

## Conferência de consistência (critério 1, por leitura)
1. S01 a S03 feitas e aceitas: igual nos três.
2. S04: "pronta, aguarda aceite do PO pelo roteiro `docs/acceptance/S04.md`; ADR-001 e ADR-004 aceitos em 23/10": igual nos três.
3. S05: "em andamento, P1 a P5 aprovadas, P6 aberta, T01 a T12": igual nos três.
4. T23 (cerca de 12 min, meta de 10 min vai à F1) e T23L mesclado (9:15): igual no quadro e no painel; o mapa cita os dois em resumo.
5. Item corrigido no quadro: a linha da S04 ainda listava o T23L como aberto; agora diz mesclado.

## Recomendação: manter 2 (quadro e painel), tirar o mapa
Em pt-BR simples: o **quadro** é para a máquina, não dá para cortar. O **mapa** e o **painel** contam a mesma história para você, o mapa em 73 linhas e o painel em 116. O painel já tem tudo o que o mapa tem (fases, fatias, o que falta decidir) e mais (ferramentas por fase, decisões). O mapa só tem de próprio a analogia de obra e o resumo do plano de revisão, que cabem em 10 linhas no painel. Manter os dois custa uma atualização a mais por sessão e já provou que um fica para trás.
- **Para você no dia a dia:** abrir um arquivo só (`docs/PAINEL_DO_PROJETO.md`), com o mesmo conteúdo. O painel ganha no topo um resumo curto "onde estamos e o que preciso de você" e a analogia de obra; nada de decisão sua se perde.
- **Alternativa 1 (manter só o quadro):** seria o menor custo, mas o quadro tem 17 KB de siglas e números de PR; você não consegue ler por ele. Não recomendo.
- **Alternativa 3 (manter os três):** funciona se o líder atualizar os três no fim de cada sessão; hoje o fim de sessão no `CLAUDE.md` não manda atualizar mapa nem painel, e é por isso que ficaram 5 dias parados.

## O que mudaria no `CLAUDE.md` (texto exato vai ao PO; este arquivo não foi alterado)
Hoje o `CLAUDE.md` não cita mapa nem painel. Com o corte, duas frases:
1. Em "Onde está o estado", acrescentar: "`docs/PAINEL_DO_PROJETO.md` visão do PO (fases, fatias, decisões e perguntas abertas); o quadro é a visão da máquina."
2. Em "Fim de sessão", trocar por: "atualizar BOARD, LOG, QUOTA (pedir ao PO os percentuais de `/usage`), o PAINEL (seções 1, 3 e 6) e o 'próximo passo' do cartão em curso."
Depois da sua resposta, um cartão T0 move os 10 trechos do mapa para o painel, apaga o mapa e ajusta as referências (nenhuma outra aponta para o mapa fora de `docs/arquivo/` e do `LOG.md`).

## Pergunta ao PO (P6)
Posso juntar o mapa dentro do painel e apagar o mapa (manter 2: quadro e painel)? Se preferir manter os três, a regra de fim de sessão passa a incluir os três arquivos.
