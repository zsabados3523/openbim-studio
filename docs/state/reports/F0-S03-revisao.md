<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Revisão da S03 (protótipo de viewport 3D)
Data: 2026-10-15 · Cartões: F0-S03-R1 (seções 1 e 2), R2 (seção 3) e R3 (seções 4 a 6 e lista final). Roteiro: `PROPOSTA_REVISAO_F0.md` §3 e §3.3. Status: **R1, R2 e R3 prontas; falta o lote Opus 31 e a resposta do PO**.

## Resumo de 5 linhas para o PO
1. A S03 provou o essencial no Linux com placa real e arquivo seu (317 MB, 8,6 milhões de triângulos): abre em 36,6 s (meta 60 s), 60 quadros por segundo (meta 30), seleção em 7 a 12 ms (meta 100 ms), janela sem travar mais de 62 ms (meta 200 ms).
2. **Três metas não foram atingidas como estavam escritas, e você aceitou cada uma:** memória (6,8 GB contra 6 GB, "atingida na prática"), Windows só em software (sem placa real nem Intel integrada) e o teste de tempo da seleção (o teste exigia 16 ms; no Windows do GitHub mediu 18 ms, e o limite do teste passou a 100 ms, que é a meta do plano). Agora as três aparecem lado a lado com a meta original.
3. O que falta medir de verdade é o **Windows com placa real**. Não existe tarefa para isso; escrevi o cartão `F0-S03-T28` (roteiro para você rodar num Windows físico antes do portão final).
4. As correções pequenas T08-G (feita) e T27 (teste da reabertura da janela 3D no CI, ainda aberta) não bloqueiam nada.
5. **Perguntas:** (a) aceita a S03 com essas três exceções registradas? Recomendo sim. (b) Aprova o cartão T28 (medir num Windows físico, antes do portão final)? Recomendo sim. (c) Para o teste de tempo, prefere medir só na sua máquina ou usar a mediana de várias rodadas no CI? Recomendo a mediana.

## 1. Aceite contra o plano (`v2/03`, F0-S03)
| # | Métrica do portão | Evidência | Atendido |
|---|---|---|---|
| 1 | Abrir IFC de ~100 MB sem cache em menos de 60 s | 36,6 s com arquivo de 317 MB (`reports/F0-S03.md`, `F0-S03-T08-D.md`) | Sim |
| 2 | 30 FPS ou mais com ~1 milhão de triângulos | 60 FPS com 8,6 milhões (placa real, Linux) | Sim |
| 3 | Seleção por clique em menos de 100 ms | 7,5 ms (sintético de 1 milhão) e 11,7 ms (corpus); `tests/test_viewport_selecao.py` com limite de 100 ms | Sim |
| 4 | RAM menor que 6 GB | Maior soma ao mesmo tempo 6,2 GB; conta conservadora 6,8 GB | **Não atingida; aceita pelo PO** |
| 5 | Funciona no Windows e no Linux, inclusive Intel integrada no Windows | Linux: sim. Windows: desenho do cubo e testes do processo separado passam no CI por software; placa real e Intel não medidas | **Parcial** |
| 6 | Saída: benchmark reproduzível e relatório por sistema | `prototypes/viewport_qrhi/medir.py`; `reports/F0-S03.md`; tabela por sistema só para o Linux | Parcial (Windows) |
| 7 | Janela não trava (meta interna, atraso máximo menor que 200 ms) | 62 ms na tela real (a primeira medição deu 300 ms em tela virtual; ver `F0-S03-T08.md`) | Sim |

## 2. Exceções, com a meta original ao lado (D8)
| # | Meta original | Medido | Motivo | Quem aprovou, quando | Onde está registrado |
|---|---|---|---|---|---|
| E1 | Memória menor que 6 GB | 6,2 GB (maior soma) e 6,8 GB (conservador) com arquivo 8,6 vezes maior que a referência; com 1 milhão de triângulos, 833 MB | Processo separado de leitura segura (filho) soma com o pai; arquivo real é muito maior que o modelo de referência | PO, 2026-10-12 ("atingida na prática") | `PO.md` (decisões após a T08-D) e `reports/F0-S03.md`, linha de memória; **valor final na S04** |
| E2 | Funciona no Windows e Linux, incluindo placa real e Intel integrada | Windows só em software (VM e CI) | A VM do PO não tem placa real | PO, 2026-10-12 (portão dado como atingido no Linux, risco para a S10) | `reports/F0-S03.md` ponto 1; **cartão `F0-S03-T28` (novo)** |
| E3 | Teste de tempo da seleção: 16 ms (meta do cartão da T06b) | 18 ms no executor Windows do GitHub | O robô do Windows é mais lento e oscila; o limite do teste passou a 100 ms, que é a meta de `v2/03` | Líder, 2026-10-12 (`LOG.md`); o PO viu na revisão (pergunta (c) abaixo) | Comentário em `tests/test_viewport_selecao.py:240` e `LOG.md`; **não aparecia em `reports/F0-S03.md`** (corrigido) |

Observação: o 16 ms era mais rígido que a meta do plano (100 ms). A meta original de `v2/03` continua cumprida (7 a 12 ms no Linux; Windows medido em 18 ms pelo robô).

## 3. Pendências abertas (cartão R2)
| # | Pendência | Estado conferido | Destino | Dono |
|---|---|---|---|---|
| 1 | T08-G (guardas e posição ilegível) | **Feita no `main`**: `prototypes/viewport_qrhi/processo_malhas.py:320` registra "S03-T08-G" | Quadro corrigido | — |
| 2 | T27 (rodar `test_viewport_adaptador.py` no passo de desenho do CI) | **Aberta**: `.github/workflows/ci.yml` não cita o teste | Segue aberta; cartão de 30 linhas, informativa | Líder |
| 3 | T23 (antes do primeiro lançamento) | Entrou no plano em `v2/03` (2026-10-15) | Fechado aqui | — |
| 4 | Windows com placa real e Intel integrada | Sem cartão | **Cartão novo `F0-S03-T28`** | PO executa |
| 5 | Teste de tempo sem depender do robô | Proposta abaixo | **Decisão do PO** | PO |
| 6 | Itens do lote 8 §2.3 (iterador por peça, orçamento de peças lentas, seleção por triângulo) | Tratados na S04: T16/T16b (peças lentas) e T10 (seleção por triângulo), feitas | Fechado | — |
| 7 | macOS | Experimental; nenhuma verificação nesta revisão | Segue como está | — |

**Proposta para o teste de tempo (decisão do PO, não implementada):** (1) manter o limite de 100 ms como regra do CI; (2) acrescentar a mediana de várias rodadas como medida oficial, para o robô oscilar menos; (3) manter os 16 ms como meta de acompanhamento, medida só na máquina do PO. Custo: mudança pequena no teste. Risco: esconder lentidão real no Windows; por isso a medição em Windows físico (T28).

## 4. Coerência dos documentos
| # | Onde | Divergência | Ação |
|---|---|---|---|
| 1 | `reports/F0-S03.md` | Memória e Windows apareciam; a exceção do teste de tempo (E3) não | Acrescentada |
| 2 | `reports/F0-S03-ci-desenho.md` | "Passo escrito, ainda não executado no CI" (velho) | Nota de atualização |
| 3 | `BOARD.md`, linha da S03 | Já limpa na correção do inventário; T08-G ainda constava como aberta | Corrigida |
| 4 | `BOARD.md`, tabela da S03 | T08-G "ABERTA" | Corrigida para FEITA |
| 5 | `PAINEL_DO_PROJETO.md` | S03 "Feita": correto | Nenhuma |
| 6 | `CLAUDE.md` | Cita planos antigos pela raiz | Não editado (A8) |

## 5. Testes
Run `38653866732` (PR 93 com o `main`, 2026-10-14): suíte principal Linux 163 passam, 169 pulam, 0 falham; Windows 161 passam, 171 pulam, 0 falham. Passo de desenho do cubo: informativo, não bloqueia. A maior parte dos "pulam" são testes que precisam de tela ou do arquivo do PO.

## 6. Qualidade e plano
- Os arquivos da S03 (`prototypes/viewport_qrhi/`, testes do viewport) foram aprovados nos lotes Opus 4 a 8; nada foi reescrito aqui.
- **Velocidade (P2):** a S03 foi feita de 2026-10-11 a 2026-10-12 e é fatia de integração com medição na máquina do PO; a S04 mostrou que pontes e threads levam muito mais. Não usar a S03 para prever a S04.
- **O que muda no plano:** nada em `v2/` sem cartão aprovado. Novo cartão `F0-S03-T28`; memória final na S04.

## Lista numerada para o lote Opus (preencher: aprovado ou reprovado)
1. R1, seção 1: os 7 critérios estão certos, com evidência suficiente? → _
2. R1, seção 2: as três exceções estão com a meta original, motivo e aprovação corretos? → _
3. R2, seção 3: o destino de cada pendência e a proposta do teste de tempo são adequados? → _
4. R2: o cartão T28 cobre o risco do Windows com placa real? → _
5. R3: as correções de coerência e os números de teste estão corretos? → _
