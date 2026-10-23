<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S04: relatório de fechamento da fatia (2026-10-23)

Autor: redator (sonnet, cartão T1 de documentos). Só junta o que já está escrito nos relatórios, no `LOG.md`, no `BOARD.md`, em `PO.md` e nos ADR; nenhum número novo foi medido aqui. "CI" aqui é o teste automático que roda no GitHub a cada alteração. Roteiro de aceite para você: `docs/acceptance/S04.md`.

## Resumo para o PO (5 linhas)
1. A fatia S04 chegou ao fim técnico: a estrutura híbrida (Python mais núcleo em C++) e a forma mista das threads foram aceitas por você em 23/10 (ADR-001 e ADR-004).
2. Na sua placa de vídeo, todas as metas de velocidade passaram, inclusive a troca de parede nos seus arquivos reais (cerca de 49 ms; antes 399 e 6.749) e o arquivo pesado (52 s e 5.858 MB contra 6.000).
3. Duas coisas ficaram abaixo do que se queria, e você aceitou: o teste automático do Windows leva cerca de 12 min (meta 10, objetivo mantido para a F1) e a folga de memória do pesado é só de 42 MB no pior caso já visto.
4. Fica aberto, com cartão e dono: a trava rara do Windows sem placa compatível (F1), o Windows com placa real (T28, seu), e quatro números do ADR-004 sem medida. O CI do Linux já foi encurtado (T23L, PR 275 mesclado: 9:15).
5. Falta só o seu aceite pelo roteiro `docs/acceptance/S04.md`; depois disso a S04 pode ser marcada FECHADA.

## 1. Metas da S04 contra o medido final
Fonte principal: `reports/F0-S04-M1F.md` (placa real RTX 3070, Linux, `main` em 67cbd70, 2026-10-23, uma execução, base sintética de 3.000 paredes, juiz estrito aprovado, saída dos dois fluxos igual). Medição anterior (2026-10-17): `reports/F0-S04.md`.

| Meta | Alvo | Medido final | Antes (17/10) | Situação | Fonte |
|---|---|---|---|---|---|
| M1. Mesmo modelo sem cópia nos dois sistemas | todos os casos passam | passam no Linux e no Windows (CI) e dentro do AppImage e do instalador | igual | atingida | `F0-S04.md`, CI |
| M2. Criar 1 parede e atualizar a viewport | p95 < 200 ms | 33,1 / 49,7 ms (mediana / p95) | 32,9 / 49,7 | atingida | `M1F` |
| M2b. Trocar a geometria de uma parede | p95 < 200 ms | sintética 32,8 / 49,4 ms; IFC real: 49,6 ms (detalhado, 222 MB) e 48,9 ms (25 MB) | 49,3 / 65,9 (sintética); 6.749 e 399 ms (real) | atingida | `M1F`, `T30-placa.md` |
| M3. Editar propriedade | p95 < 50 ms | 0,7 / 2,4 ms | 0,74 / 1,47 | atingida (o máximo, 64,5 ms, passa de 50, mas o limite é do p95) | `M1F` |
| M4. Lote de 1.000 paredes | < 20 s | 2,16 s | 2,15 s | atingida | `M1F` |
| M5. Janela não congela no lote | maior intervalo < 200 ms | 17,3 ms | 17,9 ms | atingida | `M1F` |
| M6. Razão híbrido contra C++ puro | acompanhamento | folga mínima 4,02; `pesa` falso | 3,04 | registrada, sem peso | `M1F` |
| M7. Linhas de código | registrar | `obimcore` 1.407; fluxo A 1.170; fluxo B 1.278 | 1.259 / 1.013 / 1.278 | registrada | `M1F` |
| Abrir o pesado (318 MB) | <= 60 s | 52,2 s (bloco 250) | 40,5 s (bloco 1.000) | atingida | `M1F` |
| Memória do pesado | < 6,0 GB | 5.858 MB (bloco 250; 3 rodadas, pior 5.859). Com bloco 1.000: 6.354 MB (não fecha, como já se sabia) | 6.841 MB | atingida com o bloco 250 e um reinício planejado | `M1F`, `T29-placa-memoria*.md` |
| Atraso do mouse na abertura | < 200 ms | 61,7 ms (pesado) | 62,8 | atingida | `M1F` |
| Simples e detalhado no bloco 250 | mesmas 3 metas | simples 1,91 s, 955 MB, 14,4 ms; detalhado 26,7 s, 3.568 MB, 52,2 ms | detalhado 19,2 s, 5.063 MB (bloco 1.000) | atingida (detalhado 3,3 s mais lento e 1,4 GB mais leve) | `M1F` |
| Forma mista das threads (V1) | réguas do ADR-004 §5.1 | `veredito` ok no Linux local e na placa; Windows (informativo) também ok; V1b no IFC de 25 MB: maior fatia 165,5 ms (forma 2) e 176,7 ms (mista), antes 1.018 e 1.082; V1m `lote` com 0,3% fora (aceito como ruído) | maior fatia acima de 1.000 ms | atingida, com 1 item aceito pelo PO | `F0-S04-V1.md` |
| CI do Windows | 10 min | mediana 11:58 (11:57, 12:16, 11:58), antes 17:48 | 17:48 | **não atingida; PO aceitou cerca de 12 min** | `T23d.md` |
| CI do Linux | 10 min | mediana 9:15 (7:20, 9:23, 9:15), antes 39:31 | 39:31 | atingida na mediana, com pouca folga; PR 275 mesclado | `T23L.md` |

Observação sobre o Windows: tudo no Windows saiu do CI com desenho por software (WARP); Windows com placa real não foi medido (cartão T28).

## 2. Decisões do PO nesta fatia (com data)
| Data | Decisão | Onde está |
|---|---|---|
| 2026-10-17 | Manter todas as metas e as réguas rigorosas; abrir cartões para reduzir a memória do pesado (T21, T20) e analisar a troca de parede em IFC real (T22); manter a meta de 10 min do CI e abrir o T23 | `PO.md`, `LOG.md` |
| 2026-10-21 | ADR-001: manter a estrutura híbrida, C++ puro rejeitado. ADR-004: forma mista (forma 1 para cálculos de geometria, forma 2 para comandos longos), condicionada à validação V1 | `PO.md`, ADR-001, ADR-004 |
| 2026-10-22 | Troca de parede com 25 MB reprovou na mesma operação (1.018 ms): partir a chamada longa `assign_container` (V1c) e manter a forma mista | `LOG.md` |
| 2026-10-22 | T07e (limite de espera em `Motor::parar()`): mesclar como proteção parcial, adiar a correção de fundo (dispositivo de desenho único por programa) à F1 e fechar a S04 com o risco documentado. WARP fica adiado à F1 | `cards/F1-D3D11-dispositivo-unico.md`, `LOG.md` |
| 2026-10-23 | Aceitar o 0,3% do `4_controle_forma2` (124,59 contra 124,25 ms) como ruído, sem repetir e sem mudar a régua | `F0-S04-V1.md`, `LOG.md` |
| 2026-10-23 | Aceitar ADR-001 (híbrido) e ADR-004 (forma mista), junto com o detalhado 3,3 s mais lento e 1,4 GB mais leve no bloco 250 | ADR-001, ADR-004, `LOG.md` |
| 2026-10-23 | Aceitar cerca de 12 min no CI do Windows (meta de 10 min segue como objetivo da F1; cartão `F1-CI-cadeia-instalador`) | `T23d.md`, `LOG.md` |

## 3. O que ficou aberto e onde mora
| Item | Onde mora | Situação |
|---|---|---|
| Trava rara ao fechar vista 3D no Windows sem placa compatível (WARP): 1 em 300 voltas | `cards/F1-D3D11-dispositivo-unico.md` | adiado à F1 por decisão do PO; o programa já não congela ao sair (T07e) |
| CI do Windows de 12 min contra a meta de 10 | `cards/F1-CI-cadeia-instalador.md` | adiado à F1 |
| Windows com placa de vídeo real (inclui a margem de 2,2% de `4_surda` vista com WARP) | cartão `F0-S03-T28` | dono: PO, antes da entrega final |
| N1 a N4 do ADR-004 (abrir o arquivo duas vezes, mandar edição ao auxiliar, várias linhas dentro de um cálculo, teste da queda) | ADR-004 §2 e §10 | sem medida; dependem de cartões próprios |
| T04b (registro local de mensagens e fim do mutex) | `BOARD.md` | PAUSADA |
| T29 e T34b parte (b) | `BOARD.md`, `cards` | só se a medida inconclusiva (`razao_exec` entre 0,3 e 0,8) voltar a aparecer; nenhuma ação agora |
| `DadosCena::geracao()` sem uso | `BOARD.md` (T30b3) | sai no próximo cartão que mexer em `cena.h` |
| Sugestão de incluir `<string>` no código do T07e | este relatório (sugestão passada pelo líder; sem registro anterior no repositório) | sem cartão; entra junto com o próximo cartão que mexer no código do T07e |
| CI do Linux (T23L) | PR 275, relatório `reports/F0-S04-T23L.md` | mesclado; mediana 9:15 |
| Termos do conda-forge, SINAPI | `BOARD.md` (S01) | já abertos antes, sem bloquear |

## 4. Riscos conhecidos
1. **Teste instável no Windows**: `test_contadores_de_soltura_t07b[destruir-janela]` trava cerca de 1 vez em 110 a 300 voltas por causa de um impasse interno do WARP ao destruir o dispositivo de desenho (`reports/F0-S04-T07c.md`). Hoje é tratado repetindo o CI à mão, até 5 tentativas por ocorrência (regra do `CLAUDE.md`). Só afeta quem usa WARP (sem placa compatível).
2. **Folga de memória do pesado**: o pior valor já visto é 5.958 MB contra 6.000 (folga de 42 MB); o valor típico fica em 5.858 MB. Depende do bloco 250 e do reinício planejado.
3. **CI do Windows em cerca de 12 min**, acima da meta de 10 min (folga negativa); piso da cadeia do instalador: 9:17 a 11:58 sozinha.
4. **CI do Linux em 9:15**, com pouca folga contra os 10 min; em 2 de 3 rodadas um trabalho esperou 2:38 a 3:19 por máquina livre (fila da conta no GitHub).
5. **Margens apertadas na forma mista** (1% a 4,3% em itens que comparam a mista com a forma 2) e `4_surda` no Windows com 2,2%; o Windows com placa real decide (T28).
6. **Dependência externa do CI**: em 2026-10-22 uma versão nova do Miniforge quebrou o CI do Windows em todos os PRs; foi corrigido fixando a versão 26.7.2-1 (PR 276). Pode repetir com outras versões novas.

## 5. Principais pedidos (PRs) e lotes Opus
Pedidos principais, em ordem de assunto (todos mesclados, salvo o 275):
- Threads, memória e troca de parede: T29 (185, 188, 189), T30 e subcartões (200, 204, 210, 211, 217 a 221, 229), T29e (227, 228), T29f (234), T34 (222), T34b (235), medições na placa (230, 233, 237).
- Forma mista: oráculos V1 e P1 (245 a 247), V1 (250), P1 (251), medição V1m (255), V1b (259), V1c (261), medição do V1c (266), registro da decisão (267).
- Windows: T23c (231), T23e instalador (243), T23d divisão em 11 partes (269 e 270), correção do Miniforge (276).
- Trava do WARP: T07c (257), T07e (262), validação (264), registro e cartão F1 (265).
- Decisão e aceite: ADR-001 e ADR-004 (241, 271), M1F (273), roteiro de aceite (274).
- **Aberto:** T23L, CI do Linux (275, em revisão).

Lotes Opus 68 a 77 (resultados em `docs/state/lotes/LOTE_OPUS_N/resultado.md`; o 74 está registrado só no `LOG.md`, sem pasta; não há registro do 75 no repositório):
| Lote | Assunto | Resultado |
|---|---|---|
| 68 | ADR-001 e ADR-004 com os números (T19) | escrito; levado ao PO |
| 69 | Especificação e oráculo de V1, V1b e P1 | cartões criados |
| 70 | T23e e oráculos V1 e P1 | T23e aprovado e mesclado; 245 a 247 aprovados após acréscimos |
| 71 | Implementação de V1 e P1 | aprovados (PRs 250 e 251); cartão V1 dividido |
| 72 | Relatório de medição V1 | aprovado com 6 correções de texto |
| 73 | V1c | aprovado, com a troca do selo do `fluxo_a.py` e 2 linhas do `ci.yml` |
| 74 | T07e | reprovado por 3 correções pequenas, aplicadas; depois mesclado como proteção parcial |
| 76 | Revisão do isolamento do oráculo V1c | aprovado após corrigir o vazamento |
| 77 | Revisão do texto do ADR-004 | correções dos itens 7 e 8 aplicadas |

## 6. O que fica de fora deste relatório
Aceite do PO pelo roteiro `docs/acceptance/S04.md` (pendente). Windows com placa real (T28). Os números do uso de cota estão em `QUOTA.md`.
