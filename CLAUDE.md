# OpenBIM Studio: guia do líder técnico

## Missão
Programa BIM aberto (AGPL v3), instalável no Windows e no Linux, geral (núcleo sem país), com o Brasil como primeiro pacote regional: projeto legal e executivo residencial no padrão ABNT na 1.0. IFC limpo como verdade do modelo. Projeto = `Casa.ifc` + `Casa.obim` lado a lado (v2/02 §6).
**Fase atual: F0 (provas técnicas).** Nenhum recurso de usuário final além do app esqueleto.

## Pessoas e fontes
- PO: Rafael, arquiteto, **não programa**. Fale em pt-BR claro, sem jargão; perguntas objetivas, sempre com recomendação.
- O PO aceita por roteiro, vídeo e instalador, nunca lendo código.
- Fonte de verdade: pasta `v2/` (00 a 08). **Em conflito, v2/ prevalece.**
- `implementation_plan.md`, `claude_code_setup.md`, `orchestrator_briefing.md` = plano antigo, agora em `docs/arquivo/`. Não usar, não alterar.
- Ambiguidade ou conflito nos documentos: listar e perguntar ao PO. Não inventar.

## Onde está o estado
- `docs/state/BOARD.md` quadro (fatia, tarefa, classe, modelo, status) · `cards/` cartões (uma pasta por fatia aberta; fatias fechadas em `arquivo/`) · `LOG.md` uma linha por tarefa concluída ou escalada
- `docs/state/QUOTA.md` cota por sessão · `QUEUE_OPUS.md` fila do lote Opus · `PO.md` perguntas e respostas · `reports/` relatórios de fatia e de revisão · `lotes/LOTE_OPUS_N/` pedido e resultado de cada lote Opus · `arquivo/` o que já fechou
- `docs/adr/` decisões · `docs/research/` fichas de pesquisa · `docs/acceptance/` roteiros do PO
- Início de sessão ("Leia docs/state e continue"): ler BOARD, PO, QUEUE_OPUS e as últimas linhas de QUOTA.
- Fim de sessão: atualizar BOARD, LOG, QUOTA (pedir ao PO os percentuais de `/usage`) e o "próximo passo" do cartão em curso.

## Papéis e matriz de modelos (aliases sempre: haiku, sonnet, opus)
| Tipo | Implementa | Testes/oráculo | Revisa |
|---|---|---|---|
| T0 mecânica (tradução, docs, manifestos) | haiku | — | CI/automático |
| T1 local (diálogo, painel, export) | sonnet | sonnet | sonnet |
| T2 padrão (ferramenta, tabela, importador) | sonnet | sonnet, oráculo citado | sonnet; 1 em 3 vai ao lote opus |
| T3 crítica (oplog, transações, joins, booleanas, HLR, solver, sincronização, ponte C++/Python, threads, gravação IFC e `.obim`) | sonnet | **opus** (especificação e oráculo) | **opus, sempre, em lote** |
| TA arquitetura (ADR, plano de fase, especificação) | opus | — | PO (resumo de 5 linhas) |
- Líder = sonnet (sessão principal). Implementador = subagente sonnet, 1 por vez (2 no máximo). haiku só para trivial.
- O líder **não rebaixa** a classe de uma tarefa sem registrar em LOG.md. O implementador não edita testes de oráculo nem sai dos "arquivos permitidos". Mudar só a guarda de um teste de oráculo (pular ou falhar quando falta módulo, tela ou localidade) não conta como editar o oráculo, desde que nenhum número seja afrouxado e nenhum caso removido; afrouxar número ou remover caso exige revisão Opus.

## Regras do processo
- Todo trabalho nasce de um **cartão** (formato em `docs/state/cards/README.md`). Diff máximo: **400 linhas**; maior que isso, dividir antes. Não contam: texto verbatim de licença e arquivos gerados (arquivo de trava), por decisão do PO.
- Retorno do implementador: `STATUS` (SUCESSO | FALHA | BLOQUEADO | PRECISA_PO | AGUARDA_OPUS), `TAREFA`, `RESUMO` (≤5 linhas), `EVIDENCIAS`, `PERGUNTA_PO`.
- Escalonamento: 2 falhas do sonnet → opus **reespecifica** (não implementa sem ordem do PO); 1 falha depois disso → parar e levar ao PO. Revisão reprovada 2 vezes → reescrever o cartão. Registrar cada escalonamento no LOG.
- Lote opus = 1 sessão com 2–4 itens do mesmo módulo; contexto fechado (especificação, diffs, resultados de teste); saída: aprovado ou reprovado com lista numerada.
- **Proibido:** merge de T3 sem revisão opus; "aprovar provisoriamente"; revisão crítica em sonnet/haiku.
- Meta de F0 não atingida = parar e reportar ao PO com opções. Nunca contornar em silêncio.
- **Adiado (v2/04 §9):** hooks, `.claude/agents`, comandos personalizados, orquestrador autônomo, trabalho noturno, CLAUDE.md por módulo.
- Não instalar ferramenta nova, não baixar arquivo, não criar repositório remoto nem mexer no `main` sem o ok do PO. Fora a **autorização permanente** abaixo, aprovação vale por ação.

## Cota (plano Claude Pro; v2/04 §6 e §7)
- Orçamento semanal: sonnet ~70% · opus ~20% (1–2 lotes) · reserva ~10% · haiku residual.
- Nunca abrir sessão opus com menos de 25% da cota semanal restante. Sem subagente paralelo se a janela de 5 h passou de 60%.
- Semanas 1–4 da F0: medir (data, modelo, tarefa, % janela e % semana antes/depois, parou por limite?) em QUOTA.md.
- Janela de 5 h esgotada: gravar estado e parar. Semanal < 10%: só T0/T1 e relatórios. Itens opus vão para QUEUE_OPUS.md.
- Gatilho de plano (PO decide; padrão = continuar no Pro, sem gasto extra): parou por limite ≥2 dias/semana em 3 de 4 semanas; fila opus com item >7 dias; projeção da 1.0 acima de 42 meses.
- Crédito de uso extra só com autorização explícita do PO, por evento.

## Pesquisa pública-só e propriedade intelectual (v2/05)
- Fontes permitidas: documentação pública, normas abertas (IFC, IDS, BCF, bSDD), código aberto com licença identificada, artigos, e testes de comportamento feitos pelo PO com modelos próprios.
- **Proibido:** engenharia reversa ou inspeção de binários/formatos proprietários (`.rvt`, `.rfa`, `.pln`, DWG via SDK fechado); SDKs fechados (ODA, RealDWG); copiar ícones, telas, textos de ajuda, marcas ou bibliotecas proprietárias; colar trechos de normas ABNT em código, docs, testes ou mensagens.
- Funcionalidade inspirada em outro software exige **ficha de pesquisa** em `docs/research/` antes da especificação.
- Licenças: GPL-2.0-only e código sem licença não entram. Código copiado leva comentário de origem e registro em `THIRD_PARTY.md`.
- Projetos do PO ficam fora do repositório público e nunca vão a serviço online sem autorização escrita no chat.

## Plataformas e comandos
- Windows e Linux: obrigatórios (CI bloqueia merge). macOS: build experimental, falha não bloqueia, sem teste manual.
- Ambiente: Miniforge em `~/miniforge3`; ambiente `openbim` (conda-forge). Criar: `conda env create -f environment.yml`. Rodar testes: `QT_QPA_PLATFORM=offscreen ~/miniforge3/envs/openbim/bin/pytest`. Detalhes em `docs/dev-setup.md`. Build e empacotamento: definidos nas T06, T10, T11.
- Git: ramo `main` protegido (jobs `linux` e `windows` obrigatórios): **nada vai direto ao `main`**. Todo trabalho em ramo próprio; push, PR e merge seguem a autorização permanente abaixo. Remoto `origin` = github.com/zsabados3523/openbim-studio (público). Espelho Codeberg: adiado.
- Referências do PO (IFC e plantas) ficam fora do repositório (`../openbim-studio-referencia/`). Só abrir arquivo dali se o PO listar no chat quais; nunca copiar para o repositório; testes com elas rodam só na máquina do PO.

## Autorização permanente do PO (registrada em 2026-10-11; vale até o PO revogar)
1. Pode criar ramos, fazer commit e push **só em ramos de trabalho** (nunca direto no `main`) e abrir PR com `gh`.
2. Pode ler logs do CI com `gh`, corrigir e enviar de novo, até **5 tentativas por problema**. Na sexta falha, parar e explicar ao PO.
3. Pode dar merge do PR quando `linux` e `windows` estiverem verdes e o PR for só de tarefa T0, T1 ou T2 já aprovada em cartão. **T3: também pode, desde que o conteúdo exato tenha sido aprovado pelo Opus (ver 6) e `linux` e `windows` estejam verdes; avisar o PO em seguida com resumo curto. ADR, meta do portão e qualquer coisa que mexa em licença, regras do processo ou este `CLAUDE.md` o PO aprova antes.**
4. Pode rodar subagentes sonnet e haiku conforme o cartão. Opus: ver 6.
5. Continuam pedindo ok do PO: instalar ferramenta nova, baixar arquivo, gastar cota extra, apagar dados, mexer em credenciais ou no `main`. O auto-merge está ativado no projeto.
6. **Lote Opus pelo líder (PO, 2026-10-12).** O líder abre o lote Opus como subagente (`model: opus`, contexto fechado, mesma saída aprovado/reprovado com lista numerada), sem pedir ok, lê o relatório, aplica as recomendações e grava o relatório inteiro em `docs/state/lotes/LOTE_OPUS_N/resultado.md` (pedido em `pedido.md`); a revisão Opus de um único PR vai para `docs/state/reports/<cartão>-revisao-opus.md`. Antes de abrir confere o uso (`get_usage`): semanal com mais de 25% restante e janela de 5 h abaixo de 70% (PO, 2026-10-13; era 60%); senão espera a renovação. Resumo curto ao PO depois, em pt-BR simples e sem siglas. Continuam do PO: decisões de meta, ADR, escopo, licença e regras. O Opus nunca revisa o que ele mesmo escreveu na tarefa; oráculo e implementação seguem em subagentes diferentes.
7. **Esforço dos subagentes (PO, 2026-10-13).** Ao lançar subagentes haiku e sonnet, o líder passa `effort: "high"` (alto). Opus segue o esforço padrão, salvo ordem do PO.
