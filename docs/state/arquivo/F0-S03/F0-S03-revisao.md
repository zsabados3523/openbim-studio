<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Revisão da S03 (protótipo de viewport 3D)
Data: 2026-10-15 · Cartões: F0-S03-R1 (seções 1 e 2), R2 (seção 3) e R3 (seções 4 a 6 e lista final). Roteiro: `PROPOSTA_REVISAO_F0.md` §3 e §3.3. Status: **lote Opus 31 feito (`lotes/LOTE_OPUS_31/resultado.md`): 5 itens reprovados só por texto, correções aplicadas em 2026-10-15, sem novo lote; falta a resposta do PO às perguntas (a), (b) e (c)**.

## Resumo de 5 linhas para o PO
1. A S03 provou o essencial no Linux com placa real e arquivo seu (317 MB, 8,6 milhões de triângulos): abre em 36,6 s (meta 60 s), 60 quadros por segundo (meta 30), janela sem travar mais de 62 ms (meta 200 ms); esses três números vêm de **uma única execução** na tela real (`LOG.md:97`). A seleção mede 7 a 12 ms (meta 100 ms) e é por caixa, não por triângulo (`F0-S03.md:11`).
2. **Três metas não foram atingidas como estavam escritas; você aceitou duas (E1, E2) e a terceira (E3) espera sua resposta:** memória (6,8 GB contra 6 GB, "atingida na prática"), Windows só em software (sem placa real nem Intel integrada) e o teste de tempo da seleção (o teste exigia 16 ms; no Windows do GitHub mediu 18 ms, e o limite do teste passou a 100 ms, que é a meta do plano; decisão do líder, `LOG.md:108`). Agora as três aparecem lado a lado com a meta original.
3. O que falta medir de verdade é o **Windows com placa real**. Não existe tarefa para isso; escrevi o cartão `F0-S03-T28` (roteiro para você rodar num Windows físico antes do portão final).
4. As correções pequenas T08-G (feita) e T27 (teste da reabertura da janela 3D no CI, ainda aberta) não bloqueiam nada.
5. **Perguntas:** (a) aceita a S03 com as três exceções E1 a E3? E1 e E2 você já aceitou em 2026-10-12; **a E3 (limite do teste de tempo de 16 ms para 100 ms) foi decisão do líder e ainda não teve resposta sua**. Recomendo sim. (b) Aprova o cartão T28 (medir num Windows físico, antes do portão final), já com as exigências do lote 31? Recomendo sim. (c) Regra do teste de tempo: aquecer uma vez, rodar 7 vezes e testar a **mediana** contra 100 ms no CI (o robô de testes do GitHub)? Recomendo sim; detalhes na seção 3.

## 1. Aceite contra o plano (`v2/03`, F0-S03)
Fonte dos números da placa real (36,6 s, 60,5 FPS, 61,8 ms, 6,2 e 6,8 GB): `LOG.md:97` e `PO.md:101`, **execução única na tela real, Linux, placa real**; o padrão de 8 fios e bloco de 1.000 está em `F0-S03-T08-D.md:31`. A linha JSON do `medir.py` dessa execução: sem fonte conferida (não está em nenhum relatório); pendência: gravá-la em relatório (arquivo fora da lista desta correção).

| # | Métrica do portão | Evidência | Atendido |
|---|---|---|---|
| 1 | Abrir IFC de ~100 MB sem cache em menos de 60 s | 36,6 s com arquivo de 317 MB (`LOG.md:97`; **1 execução**, evidência fraca mas existente) | Sim |
| 2 | 30 FPS ou mais com ~1 milhão de triângulos | 60,5 FPS com 8,6 milhões (`LOG.md:97`; placa real, Linux; **1 execução**) | Sim |
| 3 | Seleção por clique em menos de 100 ms | 7,5 ms (sintético de 1 milhão) e 11,7 ms (corpus) (`F0-S03.md:11`). **Seleção por caixa**, não por triângulo (desde a T08-D o pai não guarda triângulos; `arquivo/F0-S03/cartoes/F0-S03-T06b.md`, atualização de 2026-10-12); precisão de triângulo na S04 (T10). `tests/test_viewport_selecao.py` com limite de 100 ms | Sim (por caixa) |
| 4 | RAM menor que 6 GB | Placa real: maior soma ao mesmo tempo 6,2 GB; conta conservadora 6,8 GB (`LOG.md:97`). Em desenho por software o mesmo padrão dá 6,9 GB (`F0-S03-T08-D.md:25`). Faixa: 6,2 a 6,9 GB | **Não atingida; exceção E1, aceita pelo PO** |
| 5 | Funciona no Windows e no Linux, inclusive Intel integrada no Windows | Linux: sim. Windows: desenho do cubo e testes do processo separado passam no CI por software; placa real e Intel não medidas | **Parcial (E2, cartão T28)** |
| 6 | Saída: benchmark reproduzível e relatório por sistema | `prototypes/viewport_qrhi/medir.py`; `reports/F0-S03.md`; tabela por sistema só para o Linux | Parcial (Windows) |
| 7 | Janela não trava (meta interna, atraso máximo menor que 200 ms) | 61,8 ms na tela real (`LOG.md:97`; **1 execução**). Em tela virtual (software) deu 298 a 312 ms, meta não atingida (`F0-S03-T08.md:12`) | Sim (só com placa real) |
| 8 | Pedido do texto de `v2/03`: desenho por D3D11 no Windows e Vulkan ou OpenGL no Linux | Linux: OpenGL por software no CI e local (`F0-S03-ci-desenho.md:17`); Linux com placa real: qual interface gráfica foi usada, sem fonte conferida (`medir.py` não grava). Windows: receita pede D3D11 (`F0-S03-ci-desenho.md:14`); resultado do aviso do CI, sem fonte conferida nos relatórios | Parcial |
| 9 | Pedido do texto de `v2/03`: QRhi isolado atrás de interface própria e versão do Qt fixada | Interface `Viewport` (`arquivo/F0-S03/cartoes/F0-S03-T03.md:5`); Qt 6.11.2 fixado em `environment.yml:12-13`; T03 e T04 aprovadas na amostra do lote Opus 4 (`arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md:11`) | Sim |
| 10 | Pedido do texto de `v2/03`: leitura de geometria pelo iterador multithread do IfcOpenShell | Aceito pelo PO como atendido pelo iterador C++ chamado do Python (`PO.md:91`); número de fios medido em `F0-S03-T08-D.md`, tabela | Sim |
| 11 | Pedido do texto de `v2/03`: orbitar, arrastar e aproximar | Câmera da T04 (`arquivo/F0-S03/cartoes/F0-S03-T04.md`), aprovada na amostra do lote Opus 4 (`arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md:11`) | Sim |

## 2. Exceções, com a meta original ao lado (D8)
| # | Meta original | Medido | Motivo | Quem aprovou, quando | Onde está registrado |
|---|---|---|---|---|---|
| E1 | Memória menor que 6 GB | 6,2 GB (maior soma) e 6,8 GB (conservador) na placa real (`LOG.md:97`); 6,9 GB em software (`F0-S03-T08-D.md:25`); com 1 milhão de triângulos, 833 MB (`LOG.md:87`). Arquivo 8,6 vezes maior que a referência | **Uma peça só:** a mobília MOB_CAF_001 leva o processo filho a 3,9 GB (`F0-S03-T08-D.md:10`). Menos de 6 GB somados só com 1 ou 2 fios de execução, e aí a abertura passa de 60 s (`F0-S03-T08-D.md:11`, tabela linhas 22 e 26). A soma do filho com o pai é só parte da causa | PO, 2026-10-12 ("atingida na prática"; `PO.md:100`) | `PO.md:100`, `LOG.md:106` e `reports/F0-S03.md`, linha de memória; **valor final na S04** |
| E2 | Funciona no Windows e Linux, incluindo placa real e Intel integrada | Windows só em software (VM e CI) | A VM do PO não tem placa real | PO, 2026-10-12: portão dado como atingido no Linux, risco para a S10 (`PO.md:104`; `LOG.md:103`) | `reports/F0-S03.md` ponto 1; **cartão `F0-S03-T28`** |
| E3 | Teste de tempo da seleção: 16 ms (meta do cartão T06b) | 18 ms no executor Windows do GitHub | O robô do Windows é mais lento e oscila; o limite do teste passou a 100 ms, que é a meta de `v2/03` | Líder, 2026-10-12 (`LOG.md:108`), tarefa T2; **aprovação do PO pendente (pergunta (a))** | Comentário em `tests/test_viewport_selecao.py:240`, `LOG.md:108`, nota em `arquivo/F0-S03/cartoes/F0-S03-T06b.md` (acrescentada nesta correção) e `reports/F0-S03.md` |

Observação: o 16 ms era mais rígido que a meta do plano (100 ms). A meta original de `v2/03` continua cumprida (7 a 12 ms no Linux; Windows medido em 18 ms pelo robô). Depois desta correção, 16 ms vira meta de acompanhamento (E3).

## 3. Pendências abertas (cartão R2)
| # | Pendência | Estado conferido | Destino (cartão) | Dono e prazo |
|---|---|---|---|---|
| 1 | T08-G (guardas e posição ilegível) | **Feita no `main`**: `prototypes/viewport_qrhi/processo_malhas.py:320` registra "S03-T08-G" | Quadro corrigido | — |
| 2 | T27 (rodar `test_viewport_adaptador.py` no passo de desenho do CI) | **Aberta**: `.github/workflows/ci.yml` não cita o teste (o passo de desenho roda só `tests/test_viewport_qrhi.py`, linhas 95 e 264) | `cards/F0-S03/F0-S03-T27.md` (30 linhas, informativa) | Líder; antes do fim da S04 |
| 3 | T23 (antes do primeiro lançamento) | Entrou no plano em `v2/03` (2026-10-15) | Fechado aqui | — |
| 4 | Windows com placa real e Intel integrada | Sem cartão antes desta revisão | `cards/F0-S03/F0-S03-T28.md` | PO executa; antes do portão da F0 (S10) |
| 5 | Teste de tempo sem depender do robô | Proposta abaixo | Decisão do PO (pergunta (c)) | PO decide; líder aplica no teste |
| 6a | Peças lentas (lote 8 §2.3 item 2: orçamento de peças lentas) | Modo isolado e orçamento nas confirmações: T16 e T16b, feitas (`BOARD.md:110`; `LOG.md:125`, `:127`). A pergunta ao usuário sobre o orçamento total de peças condenadas: sem fonte conferida de cartão | T16/T16b; relatórios `arquivo/lotes-1-a-28/LOTE_OPUS_20/resultado.md` e `arquivo/lotes-1-a-28/LOTE_OPUS_21/resultado.md` | — (pergunta ao usuário: sem dono conferido) |
| 6b | Seleção por triângulo (lote 8 §2.3) | Feita: T10 (`BOARD.md:103`; `LOG.md:119`) | T10; relatório `arquivo/lotes-1-a-28/LOTE_OPUS_16/resultado.md` | — |
| 6c | "Iterador por peça" e custo medido no arquivo real (lote 8 §2.3 item 1); reabertura da janela (item 5) | Sem cartão nomeado para o custo do iterador por peça; o modo isolado entrou nas T16/T16b. Reabertura da janela: só o teste da T27 está previsto (`F0-S03.md:23` cita os dois) | T16/T16b (iterador); T27 (reabertura) | Líder; medir o custo do iterador por peça antes do fim da S04 (sem cartão: abrir um) |
| 7 | macOS | Experimental; nenhuma verificação nesta revisão | Segue como está | — |
| 8 | **Valor final da memória na S04** (`F0-S03.md:21`, ponto 2) | Não decidido | Cartão que decide: sem fonte conferida. Candidatos: T10 (memória da cópia compacta, `arquivo/F0-S04/cartoes/F0-S04-T10.md:10`) e T18 (tabela meta × medido, `arquivo/F0-S04/cartoes/F0-S04-T18.md:10`). Proposta: T18, com revisão do Opus | PO decide; líder prepara a tabela; antes do portão da S04 (data: sem fonte conferida; a S04 está pausada por D1, `PO.md:162`) |
| 9 | Placa de vídeo perdida: lotes liberados não voltam e `lotes_perdidos` conta quantos (`F0-S03-T08-D.md:39-40`). No Windows a troca de tela ou de driver é mais comum | Custo conhecido, ainda não medido no Windows | Verificar no roteiro do T28 e registrar o custo | PO executa; antes do portão da F0 (S10) |

**Proposta para o teste de tempo (decisão do PO, não implementada).** A máquina do PO é Linux (`LOG.md:97`) e **não cobre o Windows**; por isso a medida de Windows real fica na T28.
1. Aquecer uma vez (rodada que não conta) e rodar 7 vezes; o teste compara a **mediana** com 100 ms no CI (regra que bloqueia).
2. O teste imprime no registro a mediana e o maior valor das 7 rodadas, para acompanhar a tendência.
3. Os 16 ms ficam como aviso, só na máquina do PO (Linux), sem falhar.
4. A medida no Windows físico fica na T28.
Custo: mudança pequena no teste (arquivo `tests/test_viewport_selecao.py`). Risco: a mediana esconder um pico raro; por isso o maior valor também é impresso.

## 4. Coerência dos documentos
| # | Onde | Divergência | Ação |
|---|---|---|---|
| 1 | `reports/F0-S03.md` | Memória e Windows apareciam; a exceção do teste de tempo (E3) não | Acrescentada; tabela de metas com fonte e exceção por linha (2026-10-15) |
| 2 | `arquivo/F0-S03/F0-S03-ci-desenho.md` | "Passo escrito, ainda não executado no CI" (velho) | Nota de atualização |
| 3 | `BOARD.md`, linha da S03 | Já limpa na correção do inventário; T08-G ainda constava como aberta | Corrigida |
| 4 | `BOARD.md`, tabela da S03 | T08-G "ABERTA" | Corrigida para FEITA; linha da T28 com dono PO e prazo |
| 5 | `PAINEL_DO_PROJETO.md` | S03 "Feita": correto | Nenhuma |
| 6 | `CLAUDE.md` | Cita planos antigos pela raiz | Não editado (A8) |
| 7 | `LOG.md:106` x `LOG.md:102` e `BOARD.md:89` | A linha 106 diz "T26b pendente"; as linhas 102 e 89 dizem T26b FEITA (PR 42) | Linha de correção acrescentada ao fim do `LOG.md`; a linha 106 não foi reescrita |
| 8 | `PO.md` | Resposta do PO de 2026-10-12 ao portão da S03 | Conferida em `PO.md:103-104`; nada a acrescentar. A aceitação da E3 não está em `PO.md` (pendente) |

## 5. Testes
Run `38653866732` (PR 93 com o `main`, 2026-10-14, antes das correções desta revisão): suíte principal Linux 163 passam, 169 pulam, 0 falham (332 no total); Windows 161 passam, 171 pulam, 0 falham. Mais da metade pula nos dois sistemas.
- **Por que pulam (S03):** testes que precisam de tela ou do arquivo do PO pulam sem eles (`arquivo/F0-S03/F0-S03-T05.md:23`; o arquivo do PO fica fora do repositório). A lista exata de quais testes da S03 pulam em cada sistema: sem fonte conferida (precisa do log do run).
- **Diferença de 2 testes entre Linux (163) e Windows (161):** sem fonte conferida.
- **O que roda no passo de desenho:** só `tests/test_viewport_qrhi.py` (`ci.yml:95` no Linux, `ci.yml:264` no Windows), informativo, não bloqueia. O teste do adaptador (reabertura da janela) não roda lá: é a T27.
- **Run do `main` depois do merge desta revisão:** sem fonte conferida (ainda não mesclada); anotar o número do run quando existir.

## 6. Qualidade e plano
- Os arquivos da S03 (`prototypes/viewport_qrhi/`, testes do viewport) foram aprovados nos lotes Opus 4 a 8; nada foi reescrito aqui.
- **Velocidade (P2):** a S03 foi feita de 2026-10-11 a 2026-10-12 e é fatia de integração com medição na máquina do PO; a S04 mostrou que pontes e threads levam muito mais. Não usar a S03 para prever a S04.
- **O que muda no plano:** nada em `v2/` sem cartão aprovado. Novo cartão `F0-S03-T28`; memória final na S04.

## Resultado do lote Opus 31 (2026-10-15, `lotes/LOTE_OPUS_31/resultado.md`)
1. R1, seção 1: **reprovado por texto**; fontes corrigidas para `LOG.md:97`, "1 execução" anotada, pedidos de `v2/03` acrescentados (linhas 8 a 11), seleção por caixa dita. Corrigido.
2. R1, seção 2: **reprovado por texto**; E3 passa a "aprovação do PO pendente", E1 com origem de cada número e motivo da peça única, E2 com `PO.md:104`; nota no cartão T06b. Corrigido.
3. R2, seção 3: **reprovado por texto**; acrescentadas a memória final na S04, a placa perdida, donos e prazos, destino das pendências do lote 8 e a regra concreta do teste de tempo. Corrigido.
4. R2, cartão T28: **reprovado por texto**; cartão reescrito (prova da placa real, Intel, instalação, seleção, 3 execuções, memória total, dois modelos, cancelar, minimizar/suspender) e linha no `BOARD.md`. Corrigido.
5. R3: **reprovado por texto**; testes que pulam, run do `main` (pendente), tabela de `F0-S03.md`, resposta do PO, linha de correção no `LOG.md`, `LOG.md` e `PO.md` conferidos. Corrigido, com "sem fonte conferida" onde o log do run não foi aberto.
Resultado: 5 itens reprovados por texto, nenhum por código ou medida; correções aplicadas; **sem novo lote Opus**.

## Perguntas ao PO (aguardam resposta)
- (a) Aceitar as três exceções E1, E2 e E3? E1 e E2 já foram aceitas (`PO.md:100`, `PO.md:104`); **a E3 ainda não tem resposta do PO**. Recomendo sim.
- (b) Aprovar o cartão T28 (medir num Windows físico, antes do portão da F0), com as exigências do lote 31? Recomendo sim.
- (c) Regra do teste de tempo: aquecer uma vez, 7 rodadas, mediana contra 100 ms no CI, maior valor impresso, 16 ms só como aviso na máquina do PO? Recomendo sim.

## Resposta do PO (2026-10-15)
Aceita o plano. A memória abaixo de 6,0 GB precisa ser tratada (cartão `F0-S04-T20`, escrito em 2026-10-15). O teste no Windows com placa de vídeo (T28) pode ficar para antes da entrega final, porque o PO não tem Windows instalado. Sem resposta explícita sobre a E3 e sobre a regra da mediana: seguem abertas. Registrado em `PO.md`.

### Respostas finais do PO (2026-10-15, segunda mensagem)
Aceita a E3 (limite de 100 ms), o cartão T28 e a regra do teste de tempo (aquecer, 7 rodadas, mediana contra 100 ms). Pedido de revisão completa registrado em `QUEUE_OPUS.md`. Registrado em `PO.md`.
