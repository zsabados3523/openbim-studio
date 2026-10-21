<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_68: resultado (T19, classe TA, ADR-001 e ADR-004 com números; opus, esforço médio, 2026-10-21)
Autor: Opus. Não escrevi o ADR-004 de 15/10 nem nenhum dos relatórios citados. Li o contexto fechado do pedido (cartão T19; lote 9 §1 a §6; ADR-004; ADR-005 §7.1 e §10; `reports/F0-S04.md`, `F0-S04-threads.md`, `T15f`, `T21`, `T22`, `T23`, `T24` (cabeçalho), `T29-placa-memoria` e `-2`, `T29e-ensaio`, `T30-placa`, `T30c-dados-reais`; lotes 57, 62, 65 e 66; `PO.md`; `v2/03` F0-S04 e §3) e, para conferir o estado do código, só `malha.cpp` (mutex e 1 thread), `fluxo_a.py` (trava simples) e `fluxo_a/CONTRATO.md` (T15). Não li `~/openbim-medicao` nem IFC. Nada rodado além de leitura e `git`; sem commit, sem push, sem merge.

## 1. Entregas (no worktree, sem commit)
1. `docs/adr/ADR-001-stack-hibrido-e-ponte.md` (novo): híbrido decidido pelo PO; números de M1 a M7, M2b depois da T-2, memória do pesado depois do T29, ponte, build; o que ficou aberto (A1 a A8), o que deixa de valer, gatilhos.
2. `docs/adr/ADR-004-processos-threads-e-trava.md` (atualizado): status revisto; §2 com a situação de N1 a N4 (sem medida) e §2.1 com os números da S04; pergunta 4 nova (§5.1) com a avaliação da forma mista e o cartão V1; §6 a §10 revistos; §11 "o que deixa de valer".
3. Este arquivo.
Tamanho: ADR-001 126 linhas (novo) + ADR-004 cerca de 100 linhas alteradas, abaixo de 400.

## 2. Avaliação da forma mista: **PARCIALMENTE sustentada**
| Parte | Veredito | Números |
|---|---|---|
| Geometria numa thread à parte (forma 1 só para a malha) | **Sustentada** | Parede com 150 aberturas, maior atraso do mouse: placa 2,1 / 9,4 / 2,3 ms; Linux local até 16 ms; Windows 3 ms; limiares (metade do cálculo) 101,6 / 107 / 118 ms. Na forma 2: 199 a 204 ms (placa), 212 a 224 (Linux local), 248 a 254 (Windows): reprova nas três |
| Comandos longos em fatias na janela (forma 2) | **Em parte** | Controle sem postador (o comparável): placa 704 contra 924 ms de mediana (forma 2 melhor); Windows 810 contra 135 ms (forma 1 melhor); Linux local 719 contra 502 ms na mediana, mas 725 contra 1.196 no máximo (dividido). Com postador, mouse mediano 13 ms contra 679 a 952 (placa) e 14 contra 89 ms (Windows), mas o postador é uma terceira thread Python que piora a forma 1 (`CONTRATO.md`). Piso da forma 2: uma chamada só, `spatial.assign_container`, de cerca de 0,7 s (placa) e 0,8 s (Windows), medida só na base sintética |
| As duas juntas | **Hipótese** | Nunca medida. A forma 2 de hoje calcula a malha na janela (blocos de 25 peças); a mista precisa de uma entrega à thread de geometria com o comando ainda dono da trava de escrita, caminho que não existe |
| "Melhor tempo de resposta sem sacrificar nenhuma das duas" | **Não sustentado como fato** | A mista herda o piso de 0,7 a 0,8 s e o código de cessão por comando da forma 2, e acrescenta a entrega e a regra de trava (ADR-004 §5.1, regras 1 a 6). O ganho esperado é plausível; só o V1 mede |
Nota: a ideia do PO coincide com a recomendação do autor do T15 (`threads.md`, "Recomendação para o ADR-004"). A decisão de 17/10 ("reforçar a forma 1") **não** é volta automática se o V1 reprovar: na placa, com uma terceira thread Python (o programa terá a de arquivo), a forma 1 deixou a janela surda por mais de 1 s nas três rodadas (pulso 1.155 a 1.876 ms), o que fere o lote 9 §5.1. Se o V1 reprovar, a pergunta volta ao PO com forma 1 e forma 2 lado a lado e os custos.

## 3. Cartões necessários
| ID proposto | O quê | Classe | Depende | Aceite |
|---|---|---|---|---|
| V1 | Validar a forma mista: forma nova "mista" em `prototypes/s04/fluxo_a/lote.py` (formas 1 e 2 intactas, `fluxo_a.py` intacto) e medição | **T3** (threads, entrega ao C++); oráculo por subagente diferente; revisão Opus | — | ADR-004 §5.1, critérios 1 a 7 (mesma régua do T15, nenhum número novo afrouxado; sessão na placa com ok do PO) |
| V1b | `--ifc` em `lote.py` e medir a maior fatia da forma 2 e da mista num IFC real do PO | T2 (oráculo citado) | V1; liberação do arquivo pelo PO | ADR-004 §5.1, critério 8 (acima de 1 s: reprova a parte "fatias" e vai ao PO) |
| P1 | Porta única do modelo (decisão 3C): trava de leitura e escrita, `obimcore` confere a trava | T3; oráculo; revisão Opus | — | ADR-004 §5 (3C) e §5.1 regras 3 e 4 (leitura de painel sem espera, reentrada proibida) |
| I1 | Implementar a 4C no produto (comandos longos com cessão, thread de geometria, retorno por sinal enfileirado) | T3; oráculo; revisão Opus | V1 aprovado, P1, RG-05 | ADR-004 §5.1 regras 1 a 6; os números do V1 repetidos no produto |
| M1F | Medição de fechamento da S04 na placa: roteiro oficial inteiro (juiz estrito) depois de T29 e T30, e simples e detalhado com bloco 250 (condição A25) | T1 (medição) | ok e horário do PO | ADR-001 §7, A1 e A2; memória pela régua A28 (5 aberturas, vale a pior) |
| T23 (a) e (b) | Instalador do Windows, depois dividir os quatro trabalhos de teste | já decididos pelo PO (21/10) | — | ADR-005 §10 item 7; meta de 10 min intocada |
O T04b continua pausado; N1 a N4 viram condição dos cartões que dependem deles (ADR-004 §8), não do V1.

## 4. Perguntas ao PO (só o que é dele)
1. **Aprova o texto do ADR-001** (híbrido, com os pontos abertos A1 a A8)? Recomendação: sim; ele só passa a "aceito" depois da medição de fechamento (M1F).
2. **Aprova a forma mista como direção, condicionada ao cartão V1, sabendo que, se a validação falhar, a escolha volta a você entre forma 1 e forma 2 com os custos?** Recomendação: sim. Os números sustentam a metade da geometria; a metade dos comandos só em parte, e a mistura não foi medida.
3. **Libera um arquivo seu para o V1b** (maior operação única num modelo real) e **uma sessão na placa** para o V1 e para a medição de fechamento? Recomendação: o de 25 MB em tela virtual primeiro; o detalhado e o pesado na sessão da placa, no horário que você escolher.

## 5. Resumo para o PO (5 linhas, sem siglas)
1. O programa continua metade Python, metade C++, como planejado: o modelo é o mesmo dos dois lados, as metas de velocidade passam, e o que falhou em 17/10 estava na parte em C++ comum aos dois caminhos e já foi corrigido.
2. Na sua placa de vídeo, a memória do arquivo pesado passou por pouco (5,96 contra 6,0 gigabytes) e a troca de parede ficou abaixo de 83 milésimos de segundo, contra 200.
3. Sua ideia mista está meio comprovada: o cálculo das peças numa linha à parte funciona nas três máquinas; picar os comandos longos na janela só ganhou na sua máquina, e tem uma parada de 0,7 segundo que não some.
4. As duas juntas nunca foram medidas: proponho um cartão que mede a mistura com as mesmas réguas; se falhar, a escolha volta a você com as duas formas puras e o custo de cada uma, porque tudo na linha à parte também deixou a janela parada mais de 1 segundo na sua placa.
5. Faltam ainda a medição final completa na placa, conferir os arquivos simples e detalhado, o Windows com placa real e o teste automático do Windows, que está em 17 minutos contra 10.

## 6. Linha do LOG
`2026-10-21 | F0-S04-T19 | LOTE_OPUS_68 (opus, médio, TA) | ADR-001 escrito (híbrido, decisão do PO; M1 a M5 atingidas, M6 folga mínima 3,04 e 2,63; M2b pior 82,8 ms depois da T-2; pesado pior 5.958 MB em 6 aberturas, folga 42 MB; abertos: medição de fechamento, condição A25, Windows com placa, cadeia do Windows 17 min contra 10, custo da ponte e tempo de agente não medidos); ADR-004 atualizado (N1 a N4 seguem sem medida; pergunta 4 nova: forma mista PARCIALMENTE sustentada, geometria à parte sustentada nas 3 máquinas, fatias só em parte (controle: placa 704 contra 924 ms, Windows 810 contra 135, Linux local dividido; piso de 0,7 a 0,8 s), a mistura é hipótese; direção do PO condicionada ao cartão V1 (T3); se reprovar, volta ao PO com forma 1 e forma 2 lado a lado, sem volta automática); cartões propostos V1, V1b, P1, I1, M1F; 3 perguntas ao PO | docs/state/lotes/LOTE_OPUS_68/resultado.md`
