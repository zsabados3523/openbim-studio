# F0-S05: Oplog, desfazer e gravação do par (plano da fatia)
Autor: opus (TA), 2026-10-23. Fonte: `v2/03` F0-S05, `v2/02` §6.1 a §6.7, T00 (G1 a G6, M1, M2), ADR-001 §9 (gatilho do Rust), ADR-004 §5 (porta 3C) e §5.1 (4C).

## Metas (de `v2/03`; meta não atingida = parar e levar ao PO)
| Meta | Cartão que prova |
|---|---|
| 10.000 operações aleatórias (IFC e lateral misturados) + desfazer tudo = IFC igual por conteúdo e lateral igual | T04 |
| Matar o processo no meio de uma sequência: reabrir recupera até a última transação confirmada | T05 |
| Matar o processo durante a gravação do par: reabrir acha um par coerente | T07 |
| Aplicar 1 operação: menos de 5 ms em média num modelo de 50 MB | T10 |
| Merge (insumo para a 2.0, **não é portão**): 200 edições disjuntas em cada cópia convergem; mesmo elemento = conflito detectado | T11 |

## Ordem e dependências
| Ordem | Cartão | Título | Classe | Implementa | Oráculo | Revisa | Depende de | Pergunta PO |
|---|---|---|---|---|---|---|---|---|
| 0 | T00 | Requisitos de gravação e de memória | T3 (texto) | — | — | — | — | — |
| 1 | T01 | Organização: quadro, mapa e painel | T1 | sonnet | — | sonnet | — | P6 |
| 1 | T02 | Sondas do ifcopenshell (só números) | T2 | sonnet | — | sonnet; números ao lote do T03 | — | P3 |
| 2 | T03 | ADR-002, rascunho (especificação de partida) | TA | opus | — | PO (resumo) | T02 | P1 a P5 |
| 3 | T04 | Transação única IFC + lateral, desfazer, prova das 10.000 | T3 | sonnet | opus | opus, lote | T03 | P1, P2 |
| 3 | T06 | Gravação atômica de um arquivo (G1, G2, G3, G5, G6) | T3 | sonnet | opus | opus, lote | T03 | — |
| 4 | T05 | Diário de transações e recuperação depois da queda | T3 | sonnet | opus | opus, lote | T04 | P4, P5 |
| 4 | T07 | Gravação do par com diário de gravação (G4) | T3 | sonnet | opus | opus, lote | T04, T06 | P2 |
| 5 | T08 | Limite de memória do desfazer (M1, M2) | T3 | sonnet | opus | opus, lote | T02, T04, T05 | — |
| 5 | T09 | Autosave na pasta local | T3 | sonnet | opus | opus, lote | T05, T07 | P5 |
| 6 | T10 | Medição das metas (5 ms em 50 MB e bateria final) | T2 (medição) | sonnet | opus (régua) | opus, lote do T12 | T04, T05, T07, T08 | P3 |
| 6 | T11 | Protótipo de merge por GlobalId | T3 | sonnet | opus | opus, lote | T04, T05 | — |
| 7 | T12 | Fechamento: ADR-002 com números, relatório, roteiro do PO | TA + T1 | opus (ADR) e sonnet | — | PO | T10, T11 | — |
T01 não bloqueia nada. Mesma ordem = pode correr junto (no máximo 2 implementadores, `CLAUDE.md`).

## Regras que valem para todos os T3 desta fatia
- Oráculo escrito por um subagente opus **antes** da implementação, em PR próprio, com `@AINDA_NAO` (falha esperada estrita); quem tira os marcadores é o autor do oráculo, em commit próprio. O implementador não edita `tests/`.
- A revisão Opus é **outra** sessão, nunca a que escreveu o oráculo nem o ADR do mesmo item. Diff de implementação de até 400 linhas; passou, dividir antes.
- Código novo em `app/openbim_app/` (sem Qt, sem `obimcore`), por cima de `SessaoModelo` (a escrita só dentro de `escrever()`, a gravação dentro de `ler()`). `prototypes/s04/fluxo_a/fluxo_a.py` e `lote.py` são régua (A29): não mudam. Nomes finais dos arquivos saem do T03.
- Oráculos rodam no Linux e no Windows do CI (`linux` e `windows` obrigatórios), com guarda que pula sem módulo e vira falha com `OBIM_S05_OBRIGATORIO=1`.

## Lotes Opus previstos (2 a 4 itens do mesmo módulo; contexto fechado)
- Lote A: T03 (ADR-002 rascunho) e especificação dos oráculos do T04 e do T06.
- Lote B: revisão do T04 e do T06; oráculos do T05 e do T07.
- Lote C: revisão do T05 e do T07; oráculos do T08 e do T09.
- Lote D: revisão do T08, T09 e T11 (oráculo do T11 escrito no lote C ou num lote curto).
- Lote E: T12 (ADR-002 com números) e conferência dos números do T10.

## Perguntas ao PO (respostas mudam os cartões marcados acima)
- **P1. Comparar o IFC sem o programa `ifcdiff`.** `v2/03` pede "ifcdiff vazio", mas ele não está instalado no ambiente (conferido em 2026-10-23) e instalar pede seu ok. Recomendo: comparação própria por conteúdo (todos os campos de todos os objetos, sem depender da ordem interna do ifcopenshell, como já fizemos na S04), sem instalar nada.
- **P2. Arquivo lateral provisório na S05.** O formato do `.obim` só fecha na S06 (ADR-003). Recomendo: na S05, um `.obim` mínimo (o ZIP com o manifesto de `v2/02` §6.2 e objetos simples), marcado "provisório"; a S06 completa sem quebrar.
- **P3. O que conta nos "5 ms por operação" e em qual modelo.** Recomendo: medir aplicar uma edição pequena (mudar nome, propriedade ou posição) na memória, com o registro do desfazer; a anotação no diário de segurança é medida à parte; modelo sintético de 50 MB gerado pelo nosso script (repetível). Se quiser, um de seus IFC entra como medida extra, só se você liberar no chat.
- **P4. O que é "transação confirmada" depois de uma queda.** Recomendo: cada edição é anotada no diário na hora (protege contra o programa fechar sozinho, que é o que a meta testa); forçar a gravação no disco a cada 2 segundos e ao gravar. Numa queda de energia pode-se perder até os últimos 2 segundos.
- **P5. Recuperar e salvar automático.** Recomendo: ao reabrir depois de uma queda, perguntar "Recuperar o trabalho de HH:MM?" e abrir a cópia recuperada sem gravar por cima do seu `Casa.ifc`; salvamento automático do par a cada 5 minutos, na pasta local do programa.
- **P6. Quadro, mapa e painel.** Pergunta do cartão T01, feita depois do levantamento.

## Decisões do PO (2026-10-23, no chat)
P1 a P5 **aprovadas como recomendadas** (comparação própria por conteúdo sem ifcdiff; `.obim` mínimo provisório; 5 ms = edição pequena em memória com desfazer, em modelo sintético de 50 MB; diário na hora com escrita forçada a cada 2 s e ao gravar; perguntar "Recuperar o trabalho de HH:MM?" e nunca gravar por cima do `Casa.ifc`, salvamento automático a cada 5 min). P6 (quadro, mapa e painel) segue aberta para depois do levantamento do T01. Ordem: T01 e T02 abrem agora.
