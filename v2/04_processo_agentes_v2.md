# 04. Processo de agentes v2 (enxuto, plano Claude Pro)

> Substitui `claude_code_setup.md` quando aprovado. Nenhum arquivo `.claude/` é criado agora; a configuração mínima é feita no início da F0, em uma sessão.
> **Revisão 2:** o PO usa **Claude Pro padrão** (não Max). Pro tem limite por janela de 5 h e limite semanal, compartilhados entre Claude e Claude Code; a Anthropic não publica os números absolutos **[verificado em 2026-10-10: fonte em `07` §4]**. Todo este documento parte de "cota escassa e desconhecida, que a F0 mede".

## 1. Diagnóstico do processo original
- 12 subagentes, 8 comandos, 6 hooks e um orquestrador Haiku **antes de existir produto**: custo de montagem e manutenção alto, e cada peça é ponto de falha.
- Orquestrador em `haiku` decidindo roteamento de tarefas críticas: economia pequena, risco alto de erro de julgamento.
- Testes escritos por `haiku` antes do código: em geometria, o teste pode estar errado e o implementador "acerta o erro".
- Aceita-se: estado em disco, cartões de tarefa autocontidos, formato fixo de retorno, worktrees, "caro especifica e revisa". Esses ficam.
- Novo na Revisão 2: com Pro, o recurso mais escasso é a **cota**, não o tempo do PO. Cada sessão `opus` precisa justificar o custo.

## 2. Papéis mínimos (início da F0)
| Papel | Modelo (alias) | Onde roda | Faz | Não faz |
|---|---|---|---|---|
| **Líder técnico** (sessão principal) | **`sonnet`** | sessão principal | Conduz a fatia, escreve cartões de rotina, faz merge, fala com o PO, monta lotes para o `opus` | Especificação de módulo crítico e ADR (vão ao `opus`) |
| **Arquiteto/Revisor crítico** | `opus` | sessão dedicada, **em lote** | Especificações, ADRs, plano de fase, revisão de código crítico (oplog, geometria, HLR, solver, sincronização, ponte C++/Python, gravação IFC/lateral) | Implementar rotina; revisar diffs triviais |
| **Implementador** | `sonnet` | subagente (1 por vez; 2 no máximo) | Implementa cartão, roda testes, produz evidências | Editar testes de oráculo; sair dos arquivos do cartão |
| **Auxiliar** | `haiku` | subagente | Só trivial: traduções, manifestos do corpus, changelog, formatação de relatórios | Qualquer lógica de produto ou teste |

**Por que o líder agora é `sonnet`:** no Pro, uma sessão principal em `opus` gastaria a semana em poucos dias. O risco de julgamento é contido por duas regras: (1) tudo que é T3 ou TA passa obrigatoriamente pelo `opus`; (2) o líder `sonnet` não pode rebaixar a classe de uma tarefa sem registrar em `docs/state/LOG.md`.

### 2.1 Quando crescer (gatilhos, não calendário)
| Gatilho | Mudança |
|---|---|
| Medição da F0 mostra folga de cota > 30% por 3 semanas | Permitir 2 implementadores em paralelo |
| ≥ 3 fatias de desenho 2D na fila (F3) | Especialista "Documentação 2D" (subagente `sonnet` com CLAUDE.md do módulo) |
| CI/empacotamento consome > 20% das sessões | "DevOps" (`sonnet`) |
| Erros repetidos do mesmo tipo | Um hook específico |
| Gatilho de plano (§6) disparado | PO decide se sobe para Max; com Max, volta a valer o paralelismo 2–3 |

## 3. Matriz de modelos
| Tipo de tarefa | Implementa | Testes/oráculo | Revisa |
|---|---|---|---|
| T0 mecânica (tradução, docs, manifestos) | `haiku` | — | automático (CI) |
| T1 local (diálogo, painel, export CSV) | `sonnet` | `sonnet` | `sonnet` |
| T2 padrão (ferramenta de modelagem, tabela, importador) | `sonnet` | `sonnet`, oráculo citado | `sonnet`; amostra de 1 em 3 vai ao lote `opus` |
| T3 crítica (oplog, transações, joins, booleanas, HLR, solver, sincronização, ponte C++/Python, threads, gravação IFC e arquivo lateral) | `sonnet` | **especificação e testes de oráculo: `opus`** | **`opus`, sempre, em lote** |
| TA arquitetura (ADR, plano de fase, especificação de módulo) | `opus` | — | PO (resumo) |

Aliases sempre (`haiku`, `sonnet`, `opus`), sem versões fixas.

### 3.1 Como usar o `opus` no Pro (regras de lote)
- **Lote** = uma sessão `opus` com 2–4 itens do mesmo módulo: ex. "ADR-002 + revisão dos diffs T3 do oplog da semana".
- **Diffs curtos:** cada diff enviado à revisão crítica tem ≤ 400 linhas alteradas; maior que isso, o cartão é dividido antes.
- **Contexto fechado:** o lote recebe só a especificação, os diffs e os resultados de teste; não lê o repositório.
- **Saída fixa:** aprovado / reprovado com lista numerada de defeitos; o `sonnet` corrige; o `opus` revê só o delta.
- Planejamento de fase inteira: uma sessão `opus` por fase, preparada pelo líder com um resumo de ≤ 2 páginas.

### 3.2 Escalonamento
- 2 falhas do implementador `sonnet` na mesma tarefa → o cartão volta ao `opus` para **reespecificar** (não para implementar; implementação em `opus` só com autorização do PO, por custo).
- 1 falha após reespecificação → parar e levar ao PO com hipótese.
- Revisão reprovada 2 vezes → reescrever o cartão.
- Registrar cada escalonamento em `docs/state/LOG.md` (uma linha).

## 4. Estado em disco (mínimo)
```
CLAUDE.md                 (≤ 100 linhas: missão, regras, comandos de build/test, onde está o estado)
docs/state/BOARD.md       quadro: fatia, tarefa, classe, modelo, status
docs/state/cards/         cartões de tarefa
docs/state/LOG.md         uma linha por tarefa concluída/escalada
docs/state/QUOTA.md       registro semanal de cota (ver §6)
docs/state/QUEUE_OPUS.md  fila de itens aguardando lote opus
docs/state/PO.md          perguntas pendentes ao PO (com recomendação) e respostas
docs/state/reports/       relatórios por fatia e por portão
docs/adr/  docs/research/  docs/acceptance/ (roteiros)
```
Comandos personalizados: nenhum no início. Se o PO repetir o mesmo pedido > 5 vezes, criar o comando correspondente (provavelmente `/status` e `/retomar` primeiro).

## 5. Cartão de tarefa e formato de retorno
```markdown
# F2-S04-T03: Join de paredes em L
- Classe: T3 · Implementa: sonnet · Revisa: opus (lote) · Oráculo: invariante de volume + caderno de joins casos 1-6
- Depende de: T01, T02 · Tamanho máximo do diff: 400 linhas
## Objetivo (1 parágrafo, linguagem de arquiteto)
## Ler antes (lista fechada)
## Arquivos permitidos
## Critérios de aceite (comandos + evidência)
## Armadilhas conhecidas
## Fora de escopo
```
```
STATUS: SUCESSO | FALHA | BLOQUEADO | PRECISA_PO | AGUARDA_OPUS
TAREFA: <id>
RESUMO: <≤ 5 linhas>
EVIDENCIAS: <testes n/n, caminhos de capturas/vídeo/relatório>
PERGUNTA_PO: <se houver, pt-BR simples, com recomendação>
```

## 6. Orçamento de cota por semana
Como os números absolutos não são públicos, o orçamento é em **fração da cota semanal** mostrada por `/usage` no Claude Code **[verificar na F0: o comando e o que ele exibe; fontes secundárias em `07` §4]**.

| Fatia da semana | Alvo | Uso |
|---|---|---|
| `sonnet` (líder + implementador) | ~70% | trabalho de rotina |
| `opus` (lotes) | ~20% | 1–2 lotes por semana |
| Reserva | ~10% | correção urgente, conversa com o PO |
| `haiku` | residual | trivial |

**Regras de ritmo:** nunca abrir sessão `opus` com menos de 25% da cota semanal restante; nenhum subagente paralelo se a janela de 5 h atual já passou de 60%; o PO usa o Claude para outras coisas, e isso sai do mesmo bolo (registrar estimativa).

**Medição na F0 (obrigatória, semanas 1–4):** a cada sessão, o líder anota em `docs/state/QUOTA.md`: data, modelo, tarefa, % da janela de 5 h e % semanal antes/depois (lidos de `/usage`), e se a sessão parou por limite. No fim da semana 4: custo médio por fatia P/M/G em % semanal, por modelo.

**Gatilho para o PO considerar subir de plano** (avaliado no fim da semana 4 e depois a cada portão): qualquer um de
1. o trabalho parou por limite em **≥ 2 dias por semana** em 3 de 4 semanas;
2. a fila `QUEUE_OPUS.md` tem itens esperando **> 7 dias**;
3. a velocidade medida projeta a 1.0 **acima de 42 meses** (teto da faixa em `02` §14).
O líder apresenta: custo extra mensal, ganho estimado de calendário, e a alternativa (cortar escopo). A decisão é do PO; o padrão é continuar no Pro.

## 7. Quando a cota acaba
1. **Janela de 5 h esgotada:** o líder grava o estado (`BOARD.md`, cartão com "próximo passo") e para; nada de trabalho pela metade sem registro.
2. **Cota semanal perto do fim (< 10%):** só T0/T1 e relatórios; nada novo de T3.
3. **Itens que exigem `opus`** entram em `QUEUE_OPUS.md` com prioridade; o trabalho segue em outra tarefa não bloqueada.
4. **Proibido:** rebaixar revisão crítica para `sonnet`/`haiku`, fazer merge de T3 sem revisão `opus`, ou "aprovar provisoriamente".
5. Créditos de uso extra pagos (opção oficial do Pro) **só com autorização explícita do PO**, por evento.
6. Se o trabalho parar por cota, isso conta como dado para o gatilho do §6, não como falha do processo.

## 8. Verificação pelo PO (sem ler código)
| Momento | O que o PO recebe | Tempo do PO |
|---|---|---|
| Fim de fatia visível | Build instalável (link do CI, Windows e Linux), roteiro ≤ 15 passos, vídeo 1–3 min, capturas lado a lado | 10–20 min |
| Fim de fatia técnica (sem UI) | Relatório de 10 linhas: o que prova, número × meta | 2 min |
| Semanal | Relatório: feito, próximo, decisões pendentes, **uso de cota (tabela do §6)**, fila opus | 5 min |
| Portão de fase | Roteiro 30–120 min, tabela de metas, vídeo resumo | 1–3 h |

Formato do roteiro de aceite (`docs/acceptance/F2-S04.md`): passos numerados, resultado esperado de cada passo, caixa ✅/❌, campo de observação. O PO responde no chat em linguagem natural; o líder transforma em tarefa.

Vídeos: gravados automaticamente a partir de testes de interface quando a ferramenta permitir **[não verificado: depende de teste prático na F0-S02, Windows e Linux]**; senão, capturas sequenciais. macOS: sem vídeo (ver `02` §12).

## 9. O que adiar
| Adiado | Até quando |
|---|---|
| Hooks (formatação, guarda de escopo, guarda T3) | Até o erro correspondente aparecer 2 vezes; o CI já bloqueia |
| Orquestrador com loop autônomo | Não no Pro (consome cota sem supervisão) |
| Execução noturna sem supervisão | Não no Pro; reavaliar se subir de plano |
| CLAUDE.md por módulo | Quando o módulo existir |
| Papéis especializados | Gatilhos do §2.1 |

## 10. Início da F0 (passo a passo do PO)
1. Abrir uma sessão Claude Code na pasta do projeto com **`sonnet`**.
2. Pedir: "Leia v2/02, v2/03 e v2/04. Crie o CLAUDE.md mínimo, docs/state/ (incluindo QUOTA.md e QUEUE_OPUS.md) e os cartões da F0-S01 e F0-S02. Não instale nada sem me perguntar."
3. Rodar `/usage` no início e no fim de cada sessão e deixar o líder anotar.
4. Aprovar as permissões conforme pedidas.
5. A cada sessão: "Leia docs/state e continue."
6. Quando o líder disser "lote opus pronto", abrir sessão com `opus` e colar o pedido de lote que ele preparou.
