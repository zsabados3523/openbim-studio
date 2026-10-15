# Proposta: revisão das fatias concluídas e controle de riscos da F0

> Status: **PROPOSTA, aguarda decisão do PO.** Escrita em 2026-10-14. Não altera `v2/` nem `CLAUDE.md`.
> Classe: TA (plano de fase). Pelo `v2/04` §3, o texto final deve passar por um lote Opus antes de virar plano; o PO aprova o resumo.
> Fontes: `v2/02` §11 (riscos R1 a R15), `v2/03` (fatias e portões), `docs/state/BOARD.md`, `docs/state/LOG.md`, `docs/state/PO.md`.

## 1. Por que agora

S01, S02 e S03 estão concluídas. A S04 começou (T01 e T02 feitas; o PR da T02 aguarda revisão). Antes de gastar cota com a parte mais difícil (a ponte entre Python e C++), vale conferir se a base está certa:

- S01 foi aceita, mas parte da pesquisa de licenças ainda está "não verificada" e a revisão da tabela foi feita por IA no papel de arquiteto.
- S02 tem tarefas com conferência pendente (T17 e T18 aguardam lote Opus 3; o pacote AppImage ainda não tem o runtime verificado) e um item que bloqueia o primeiro release (T23).
- S03 foi aprovada com exceções (memória de 6 GB "na prática", Windows só em máquina virtual, teste de tempo afrouxado de 16 para 100 ms).

Objetivo desta proposta: **revisar cada fatia concluída com o mesmo roteiro, transformar as pendências em cartões e reduzir os riscos listados em §4 antes de avançar.**

## 2. Regra de andamento proposta

- **Pausa de tarefas T3 na S04** (da T03 em diante) até as revisões de S01, S02 e S03 terminarem. A T01 e a T02 seguem como estão.
- Tarefas T0 e T1 podem seguir normalmente.
- Cada revisão é uma fatia por vez, na ordem S01, S02, S03. Não se misturam fatias num mesmo lote Opus (regra do lote: um módulo por sessão).
- Antes de abrir qualquer sessão Opus: conferir `get_usage`. Semanal acima de 25% restante e janela de 5 h abaixo de 60%, senão espera (regra já existente em `CLAUDE.md` item 6).

## 3. Roteiro de revisão de cada fatia

Cada fatia passa pelos mesmos seis passos. A saída é sempre uma lista numerada com **aprovado** ou **reprovado**.

1. **Aceite contra o plano.** Conferir cada critério de aceite de `v2/03` § daquela fatia, um por um, com a evidência (arquivo, relatório, run de CI). Critério sem evidência conta como não atendido.
2. **Pendências declaradas.** Listar tudo que a fatia deixou "aberto", "não verificado" ou "pendente". Cada item vira uma de três coisas: corrigir agora (até 30 linhas), cartão novo, ou registro com data e dono.
3. **Coerência dos documentos.** `BOARD.md`, `LOG.md`, `PO.md`, relatórios e `docs/PAINEL_DO_PROJETO.md` dizem a mesma coisa sobre a fatia? Uma informação, uma fonte.
4. **Testes.** Suíte completa verde em Linux e Windows, com a contagem de testes que passam, pulam e falham anotada.
5. **Qualidade do código e do texto.** Revisão de reuso e simplificação só nos arquivos da fatia. Não reescreve nada fora dos cartões de correção.
6. **Relatório de uma página** em `docs/state/reports/`: o que está aprovado, o que mudou, o que ficou aberto e o que muda no plano.

Nada é corrigido sem cartão. Correção pequena pode ser feita direto no cartão de revisão, com diff de até 400 linhas.

### 3.1 S01: repositório, licenças e pesquisa (primeira a revisar)

Pontos já identificados nos documentos, que o roteiro deve confirmar ou fechar:

| # | Ponto | Por que importa |
|---|---|---|
| S01-a | O aceite pede a tabela "revisada pelo papel Arquiteto". A revisão feita foi de IA (Opus no papel de arquiteto). | O PO precisa confirmar se aceita esse parecer como o aceite ou se quer conferir ele mesmo um resumo de 5 linhas. |
| S01-b | Termos do SINAPI não verificados (site da CAIXA com redirecionamento em loop). A ficha está com "Revisado por: pendente". | Só importa na F5, mas a ficha não pode ficar com revisão pendente como se estivesse pronta. |
| S01-c | Qt Shader Tools: módulo só sob GPL-3 ou comercial. Está fora da lista de 14 módulos da ficha B, e a revisão pediu registrar a lacuna. | Precisa ficar claro se entra no instalador ou só no build. A regra da própria tabela é evitar módulos só GPL-3. |
| S01-d | Termos do conda-forge e de ReportLab ainda não verificados. | O conda-forge é canal, não licença; o que vale é a licença de cada pacote. Confirmar que a linha diz isso. |
| S01-e | Itens da lista do `v2/03` (PlaneGCS, libslvs, pythonocc-core, LibreDWG, ezdxf) estão cobertos na tabela mestre? | O critério pede a lista completa. A revisão apontou lacunas de cobertura; confirmar se foram fechadas. |
| S01-f | Espelho no Codeberg adiado. | Decisão já tomada; só registrar na revisão. |

**Saída esperada da revisão S01:** aprovado com as pendências fechadas ou viradas em cartão, e uma linha no `PO.md` com o parecer do PO sobre S01-a.

### 3.2 S02: testes automáticos, AppImage e instalador

Pontos a conferir:

- T17 e T18 (correções do lote 2) aguardam conferência Opus no lote 3. Essa conferência precisa acontecer antes de a fatia ser considerada revisada.
- Runtime do appimagetool ainda pendente (`BOARD.md`). Sem isso, o pacote Linux não está fechado.
- T23 ("antes do primeiro release") bloqueia release público e não começou. Deve constar no plano como pré-requisito, não como detalhe.
- Tempo do build no Windows (cerca de 15 a 16 min, meta de 10): aceito pelo PO com revisão na S04. Confirmar que a revisão está registrada como cartão.
- Teste de instalação em máquina limpa e no roteiro do PO: conferir se o roteiro `docs/acceptance/` está atualizado com as correções de T21 e T22.
- Instalador e AppImage: confirmar que as licenças dos arquivos empacotados batem com a tabela da S01 (ponto de contato entre as duas fatias).

### 3.3 S03: protótipo de visualização

Pontos a conferir:

- Meta de memória de 6 GB: a medição com o arquivo real deu 6,8 GB (conta conservadora) e 6,2 GB (maior soma ao mesmo tempo). A aceitação "na prática" está registrada em `PO.md`. A revisão deve deixar claro que a meta original **não** foi atingida e que a decisão final fica para a S04 com o modelo real.
- Windows só em software (máquina virtual, sem placa real). O risco da placa real está registrado para a S10. Confirmar que existe um cartão ou item de checagem para isso.
- Teste de tempo da seleção: limite passou de 16 ms para 100 ms por causa do robô do Windows (18 ms medido). A revisão deve registrar isso como **exceção de teste**, com o motivo, e propor uma forma de medir que não dependa do robô (por exemplo, medir na máquina do PO, ou usar a mediana de várias rodadas).
- Relatório `reports/F0-S03.md`: conferir se as exceções aparecem no mesmo lugar em que aparecem as metas.

## 4. Riscos da F0 e como a proposta responde

Os riscos abaixo vêm da análise anterior. A coluna "relação" aponta o item equivalente em `v2/02` §11, quando existe.

| # | Risco | Relação | Resposta proposta | Quando |
|---|---|---|---|---|
| P1 | Escopo da 1.0 grande para uma equipe de um PO não programador com IA em plano Pro | R2, R4, R5, R9 | Definir a **1.0 mínima** (ver §5, decisão D3) com ordem de corte aprovada pelo PO | Antes de liberar a S04 |
| P2 | Velocidade inicial (S01 a S03 em 4 dias) não representa os trechos difíceis | R5 | Medir velocidade **por tipo de fatia** (fácil, de integração, de geometria). Não recalibrar o calendário com S01 a S03 | Já na revisão S01 |
| P3 | Escopo cresce sem recalcular prazo (14 mudanças em 13/10) | Nova | Regra: toda mudança de escopo registra no `LOG.md` o efeito em prazo e cota. Sem isso, a mudança não entra | Já, a partir de agora |
| P4 | Portões cedendo um a um (memória, Windows em VM, teste de tempo, regra do 3×) | Nova | Toda exceção registra a **meta original ao lado** e o motivo. O portão F0 (S10) é reavaliado com as metas originais, sem as exceções | Já; reavaliação na S10 |
| P5 | Verificação por IA com erros correlacionados (escritor e revisor erram do mesmo jeito); defeitos de especificação do Opus | Nova | (a) Trazer **um IFC real do PO** antes de fechar a S04 (ver D4). (b) Testes de comportamento com esse arquivo. (c) O PO confirma o aceite do arquiteto em S01 (ver D6) | Antes do fim da S04 |
| P6 | Custo permanente da arquitetura híbrida (Python e C++, duas cópias de bibliotecas que precisam bater de versão, pacotes de 300 a 400 MB, obrigações LGPL) | R1, R2 | A decisão da S04 (ADR-001) inclui um critério de **custo de manutenção em 2 a 3 anos**, com cenário de C++ puro no núcleo e Python só para regras. Não é só desempenho | Na conclusão da S04 |
| P7 | Dois arquivos (IFC limpo + `.obim`) podem separar e causar perda de pranchas e vistas | R14 | Definir cedo o **arquivo padrão de entrega** (ver D7). Hoje o plano prevê `.obimpack` como opção | Decidir no ADR-003 (S05) |
| P8 | Validação com profissional e com prefeitura só no fim (F6) | Nova; R15 em parte | Trazer **um arquiteto de teste** para a F1 (ver D5). Antes do portão F3 (v0.3), testar a planta com uma prefeitura real, ou um escritório que aprove projetos na cidade do PO | Planejar já; executar nas fases F1 e F3 |
| P9 | Desfazer e salvamento só na S05, depois da arquitetura | Nova | Tratar salvamento automático e desfazer como **requisito de qualidade da F1**, não só como funcionalidade. Registrar no plano | Atualizar `v2/02` na próxima revisão |
| P10 | Excesso de documentos e cópias que podem divergir (planos antigos na raiz, `AGENTS.md`, `PAINEL_DO_PROJETO.md`, `BOARD.md`) | Nova | Uma fonte por tipo de informação (ver D2). Revisão S01 inclui o passo 3 de coerência | Na revisão S01 |

Riscos que não mudam: R3 (desenho de plantas), R11 e R12 (placa de vídeo e macOS), R13 (API do Qt), R7 e R8 (licenças e legal). Continuam nos gatilhos atuais de `v2/02` §11.

## 5. Decisões que precisam do PO

Cada uma com a recomendação do líder. Se o PO responder "aceito as recomendações", o orquestrador segue com elas.

| # | Decisão | Recomendação |
|---|---|---|
| D1 | Pausar as tarefas T3 da S04 (da T03 em diante) até as revisões de S01 a S03 | **Sim.** Custa uma ou duas semanas de cota leve e evita construir em cima de base não revisada |
| D2 | Destino dos três planos antigos na raiz (`implementation_plan.md`, `claude_code_setup.md`, `orchestrator_briefing.md`) | **Mover para `docs/arquivo/`**, sem apagar. Reversível e tira a confusão para o orquestrador. Hoje `CLAUDE.md` manda não usar nem alterar, por isso precisa do seu ok |
| D3 | Definir a **1.0 mínima**: o que sai da primeira versão utilizável | Adiar para depois da 1.0 o que for mais caro e menos usado no dia a dia: **DXF, fachadas e detalhes 2D**. Manter **tipos paramétricos** (sem eles não há quadro de esquadrias). Decidir na sessão de escopo, depois da revisão S02 |
| D4 | Trazer **um IFC real seu** (casa pequena, fora do repositório) antes de fechar a S04 | **Sim.** Ele só entra nos testes que rodam na sua máquina, como já previsto em `CLAUDE.md` |
| D5 | Quem será o **arquiteto de teste** para a F1 (uma ou duas pessoas) | Procurar agora, sem prazo de uso. Não precisa programar; precisa abrir um IFC e dizer o que travou |
| D6 | Aceite de S01: confirmar se o parecer de IA para a tabela de licenças basta, ou se você quer ler um resumo de 5 linhas | **Ler o resumo** (cerca de 10 minutos). Assim o aceite vira aceite seu, não só do modelo |
| D7 | Arquivo padrão de entrega (`.ifc` + `.obim` ou `.obimpack`) | **Pode esperar pelo ADR-003** (S05). Só registrar agora que é decisão pendente |
| D8 | Regra para exceções de portão (P4) | **Sim**: exceção registra meta original e motivo; o portão F0 é reavaliado com as metas originais |

## 6. Próximos passos

| Passo | Quem | O que | Saída |
|---|---|---|---|
| 1 | PO | Ler esta proposta e responder D1 a D8 | Respostas registradas em `docs/state/PO.md` |
| 2 | Orquestrador | Etapa 0: inventário do estado (conferir se `BOARD`, `LOG`, `PO` e `PAINEL` dizem o mesmo). Aplicar D2 se aprovado | Relatório curto em `docs/state/reports/` |
| 3 | Orquestrador | Cartões de revisão da S01 (`F0-S01-R1` a `R3`, conforme as pendências S01-a a S01-f) | Cartões em `docs/state/cards/` |
| 4 | Sonnet (implementador) | Corrigir as pendências pequenas da S01 e preparar o pacote de contexto do lote Opus | Pacote pronto |
| 5 | Opus (lote S01, uma sessão) | Revisar a S01 com o roteiro §3 e conferir esta proposta | Lista numerada aprovado ou reprovado; relatório gravado |
| 6 | Orquestrador | Resumo de 5 linhas para o PO sobre S01 e a proposta | Resumo no chat |
| 7 | Orquestrador | Repetir os passos 3 a 6 para S02 (lote separado, cota checada) | Relatório S02 |
| 8 | Orquestrador | Repetir para S03, incluindo a revisão das exceções | Relatório S03 |
| 9 | PO e orquestrador | Sessão de escopo (cerca de 1 hora): fechar D3 e a ordem de corte | `v2/02` atualizado por cartão de revisão aprovado pelo PO |
| 10 | Orquestrador | Liberar a S04 a partir da T03, com os critérios de risco de P5 e P6 incluídos nos cartões | Cartões T03 em diante |

Sem prazo de calendário rígido: cada passo depende da cota da semana e da resposta do PO. Se o portão de cota (25% semanal) não permitir o lote Opus, o passo espera a renovação, e o registro fica em `QUEUE_OPUS.md`.

## 7. O que esta proposta não faz

- Não altera a arquitetura nem decide a S04. Só garante que a S04 comece sobre base revisada e com critérios de custo.
- Não muda o `v2/` nem `CLAUDE.md`. Essas mudanças viram cartões aprovados pelo PO.
- Não reabre decisões já aceitas (licença AGPL "ou posterior", IFC como verdade, Windows e Linux obrigatórios, macOS fora do caminho crítico).
