# 08. Roteiro para iniciar a F0 (sessão 1)

> Base: `04_processo_agentes_v2.md` §10 e `03_fase0_especificacao.md`. Plano Claude Pro: a cota é escassa. Esta primeira sessão é só de **preparação** (sem instalar nada e sem código de produto).

## Antes de abrir a sessão
1. Abra uma **nova sessão** na aba Code, ambiente **local**, pasta `/home/rafael/00 - PROJETOS/openbim-studio` (a raiz, não a `v2/`).
2. **Modelo: Sonnet** (é o líder técnico do plano Pro). Não use Opus nesta sessão.
3. Modo de permissão: o padrão (pede confirmação). Aprove criação de arquivos dentro da pasta do projeto. **Negue** instalação de pacotes ou comandos de rede se aparecerem agora.
4. Leia antes, se puder: `v2/00_resumo_executivo.md` (1 página).
5. Rode `/usage` e anote os percentuais da janela de 5 h e da semana (a F0 mede a cota).

## Prompt para colar

```
Você é o líder técnico do projeto OpenBIM Studio (BIM open source, multiplataforma, AGPL v3). O Product Owner (eu, Rafael) é arquiteto e NÃO programa: fale em pt-BR claro, sem jargão, e traga perguntas objetivas com recomendação.

Leia, nesta ordem: v2/00_resumo_executivo.md, v2/02_plano_mestre_v2.md, v2/03_fase0_especificacao.md, v2/04_processo_agentes_v2.md, v2/05_politica_pesquisa_e_ip.md, v2/06_decisoes_pendentes.md. Os arquivos fora de v2/ (implementation_plan.md etc.) são o plano antigo: NÃO os use nem os altere. Em conflito, v2/ prevalece.

Escopo DESTA sessão (somente preparação, nada de código de produto):
1. Crie o CLAUDE.md mínimo na raiz (até 100 linhas): missão, regras do processo v2 (04), matriz de modelos, regras de cota, política de pesquisa pública-só (05), onde está o estado.
2. Crie docs/state/ com BOARD.md, LOG.md, QUOTA.md, QUEUE_OPUS.md, PO.md, a pasta cards/ e reports/, e docs/adr/, docs/research/, docs/acceptance/ (vazias, com um README curto cada se útil).
3. Escreva os cartões de tarefa (formato do 04 §5) das fatias F0-S01 (repositório, licenças e pesquisa) e F0-S02 (CI Windows+Linux e app esqueleto), divididas em tarefas com diff máximo de 400 linhas. Classifique cada uma (T0/T1/T2/T3) e diga qual modelo implementa e revisa.
4. Preencha BOARD.md com as fatias da F0 (S01 a S10), dependências e status.
5. Registre a primeira linha de QUOTA.md com os percentuais que eu informar de /usage.
6. Monte uma lista curta (máx. 5 itens) do que deve ir no PRIMEIRO lote Opus (por exemplo: revisão da tabela de licenças da S01 e esboço do ADR-005), em QUEUE_OPUS.md. Não execute o lote.

Regras: NÃO instale nada, NÃO rode comandos de rede, NÃO inicialize git nem crie repositório remoto sem me perguntar antes. NÃO crie .claude/agents, hooks ou comandos personalizados (adiados, ver 04 §9). Se algo nos documentos estiver ambíguo ou conflitante, liste e pergunte; não invente.

Ao terminar, responda em pt-BR com: o que criou (lista), o que classificou como T3 e por quê, o que precisa de Opus, perguntas para mim (com recomendação) e o próximo passo sugerido. Não faça mais nada além disso.
```

## Depois da sessão 1
1. Rode `/usage` de novo e informe os percentuais ao líder, se ele pedir.
2. Leia o resumo e responda às perguntas dele.
3. **Sessão 2 (Sonnet):** `Leia CLAUDE.md e docs/state e continue com a F0-S01.` Aqui ele pergunta antes de criar o git, o repositório no GitHub e o espelho no Codeberg. Esses passos são seus (cadastro e conta), ele só orienta.
4. Quando ele disser "lote opus pronto", abra uma sessão com **Opus** e cole o pedido de lote que ele preparou. Uma sessão Opus por lote, nunca com menos de 25% da cota semanal restante.
5. Rotina de cada sessão: `Leia docs/state e continue.` e, ao fim, `/usage`.

## O que você precisa providenciar ao longo da F0
| Quando | O que |
|---|---|
| Semana 1 | Conta no GitHub e (opcional agora) no Codeberg |
| F0-S02 | Uma máquina Windows e uma Linux para instalar o app esqueleto |
| F0-S09 | 1 h de entrevista sobre seus fluxos no Revit/ArchiCAD |
| Até a F2-S04 | Caderno de 20 situações de parede e 3 pranchas de referência |
| Quando tiver | 3 a 5 IFCs seus (IFC4, e se der 2x3) com os PDFs de prancha |
