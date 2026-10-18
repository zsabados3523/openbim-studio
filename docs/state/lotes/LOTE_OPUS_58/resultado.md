<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_58: resultado

**CONCLUÍDO** (planejamento, classe TA, esforço médio). Nada foi implementado, medido nem escolhido. Este texto **especifica** as opções dos dois itens; a escolha é do PO. Autor: Opus. Pela regra 6 do `CLAUDE.md`, quem revisar a implementação e o oráculo que nascerem daqui é **outra sessão Opus**; o oráculo e a implementação ficam com subagentes diferentes.

Li só o contexto fechado do pedido: `reports/F0-S04-T24.md` (com o §13), `reports/F0-S04-T25.md` (com o §9 e o §10), `reports/F0-S04-T21.md`, `reports/F0-S04-T22.md`, `lotes/LOTE_OPUS_57/resultado.md`, `nucleo/motor.h`, `viewport_qrhi/carregador.py` e `viewport_qrhi/processo_malhas.py`. **Não li** `cena.h`/`cena.cpp`, `formato_malha.py`, `fluxo_a.py`, as sondas, o ADR-004, o cartão T12, `v2/03`, IFC do PO nem dados brutos. O que depende deles está marcado "não lido", e o tamanho dos cartões dessas partes é estimativa.

Convenções (as mesmas do lote 57): "medido" = número de relatório; "pelo código" = leitura do código citado, sem medida; **estimativa** = conta feita aqui sobre números medidos, nunca medida; **hipótese** = causa não provada, sempre com o teste que a confirma. Metas: pico somado (conta A, pai + maior filho) **< 6.000 MB** e abrir **≤ 60 s**, pela **pior** das rodadas na placa real; M2b **p95 < 200 ms**. O orçamento por quadro (2 MiB e 4 ms) é limite existente (A21) e não muda em nenhuma opção recomendada.

## 0. Resumo para o PO (5 linhas, sem siglas)
1. Memória do arquivo pesado: a combinação "partes de 250 peças + processo do 3D começado de novo logo antes da parte pesada" passou na sua placa nas 3 aberturas, mas com folga pequena (106 MB). Falta o programa saber sozinho onde reiniciar.
2. Para isso recomendo: o programa vigia quanto a memória cresce dentro de cada parte e, se uma parte crescer demais, refaz só aquela parte num processo novo. Antes de programar, dá para simular essa regra com os números que já foram medidos, sem abrir nenhum arquivo seu.
3. Trocar uma parede no arquivo detalhado demora cerca de 6,8 s porque a tela joga fora tudo e reenvia. Mandar de novo só o pedaço tocado não basta: o pedaço da parede tem 24 MB e daria cerca de 250 ms, acima da meta de 200 ms.
4. Para a parede, recomendo esconder a parede antiga na hora sem reenviar nada, mostrar a nova (como criar uma parede, que hoje leva cerca de 60 ms) e arrumar o resto da tela devagar, sem a cena sumir. Antes, um teste só com modelos de teste, sem arquivo seu.
5. Nenhuma opção recomendada mexe em meta, régua, limite, orçamento da tela ou teste. Preciso de você em 7 decisões curtas (seção 6).

## 1. Erros e contradições nos relatórios e no lote 57
1. **T25 §10.4 (a conta do pedido): os números de quadros estão fracionados e falta o quadro a mais.** O T25 §9 arredonda para cima (27,42 MiB: 13,71 → 14 quadros). Já o §10.4 usa 12,12 quadros para 24,24 MiB e deixa de fora o +1 visto em **todos** os tamanhos (detalhado: 402,88 previstos → 404 vistos; 25 MB: 22,85 → 24; sintéticas: +0 ou +1, T25 §5). Quadro não se divide: a parte que sobra de um lote ocupa um quadro inteiro. Feita do mesmo jeito do §9, a conta é **quadros = teto(lote ÷ 2 MiB) + 1** (estimativa, com base no padrão medido):
   - 24,24 MiB: 13 + 1 = **14 quadros**, cerca de 227 ms (16,2 ms por quadro) a 235 ms (16,77 ms, a média medida: 6.775 ÷ 404);
   - 68,27 MiB: 35 + 1 = **36 quadros**, cerca de 583 a 604 ms;
   - 285,36 MiB: 143 + 1 = **144 quadros**, cerca de 2,3 a 2,4 s.

   Falta ainda a parte do comando, que não é quadro: no detalhado na placa, T22 dá 6.748,3 ms no total contra 6.723,7 ms de quadro, ou seja **24,6 ms** (as fases medianas somam 24,8: comando 3,1 + gravar 0,02 + malha 19,7 + lote 0,3 + envio 1,7; medianas não se somam exatamente). Com ela, a 2-A pura no lote de 24,24 MiB fica em **cerca de 250 a 260 ms** (estimativa). A conclusão do T25 ("não chega a 200 ms") **está certa e fica mais forte**: a frase "cerca de 202 ms, sem folga" subestima a conta. Os 196 ms a 16,2 ms por quadro também não valem.
   - A aritmética em si confere: 24,24 ÷ 2 = 12,12; × 16,7 = 202,4; × 16,8 = 203,6; × 16,2 = 196,3; 68,27 ÷ 2 = 34,14; × 16,7 = 570,1; × 16,8 = 573,5. O erro está no modelo, não nas contas.
   - Pela mesma regra, o 25 MB (§9) fica em 15 quadros, cerca de 243 a 252 ms, e não 227 a 234 ms. O §9 também deixou o +1 de fora.
2. **O que a conta do §10.4 deixa de fora** (o pedido manda dizer):
   - (a) o +1 quadro (acima);
   - (b) o lote novo: 1.152 bytes, que cabe na sobra do último quadro; só pesa se o lote refeito fechar exatamente num múltiplo de 2 MiB (estimativa);
   - (c) o limite de 4 ms: na placa real, **404 = 403 + 1** indica que o limite de bytes é o que manda (inferência da medida, não prova). Na placa ele não cortou quadros de forma visível; em software o T25 §3 tem 24 de 468 trocas com o primeiro quadro menor (hipótese do T25: os 4 ms). No Windows/WARP não foi medido;
   - (d) os 24,6 ms do comando (acima);
   - (e) a cópia na memória do lote refeito dentro de `cena.atualizar` (hoje 1,7 ms para enviar ao C++ no detalhado; refazer um lote de 24 MiB custa mais, não medido; `cena.*` não lido).
3. **Pedaços além de 2 por lote: há uma causa no código** (pelo código, não medido; o T25 §5 a deixou como hipótese de "lote cortado na fronteira"). Em `motor.h` linha 219, a fatia de vértices é arredondada para múltiplo de 28 bytes. Como 2.097.152 dividido por 28 deixa resto 8, depois da fatia grande sobram 8 bytes de orçamento e o laço ainda manda **uma fatia mínima de 28 bytes** (o `max(un, ...)`). Assim, todo quadro na fase de vértices tem 2 fatias e passa o orçamento em 20 bytes (2.097.172). Nos índices, que têm 4 bytes, o resto é 0. Isso é compatível com 839 pedaços para 43 lotes no detalhado. Não muda o tempo, mas **o oráculo não pode supor 1 pedaço por 2 MiB**. Os 20 bytes acima do orçamento são do desenho de hoje: não é para "consertar" em silêncio, porque seria mudar o limite.
4. **Cabeçalho do T25 contra o §10.** A linha 3 diz "Nenhuma tela real ... foi tocado", mas o §10 é uma rodada na tela real. A frase vale só para as seções 1 a 9; o cabeçalho deve dizer isso.
5. **T25 §10.5 e §9: "2-G não depende do tamanho do lote".** Isso vale para esconder pelo desenho (§3.4 abaixo). Na variante que zera os índices na placa, o envio é do tamanho dos **índices da peça antiga**: 144 bytes numa parede e cerca de 19 MB numa peça de 1,6 milhão de triângulos (estimativa: 12 bytes por triângulo).
6. **Lote 57, erros já refutados pelas medidas.** Ficam registrados com clareza:
   - 1-B: estimativa de cerca de 5.330 MB (medido 6.511 em software e 6.345 na placa com bloco 1.000);
   - oráculo "igual byte a byte" (refutado: duas aberturas normais já diferem, T24 §5 e §13 item 3);
   - cerca de 390 lotes de 2 MiB no detalhado (medido: 13 lotes, 11 acima de 2 MiB, maior 285,36 MiB);
   - 2-A "cerca de 75 a 110 ms" no detalhado (pela conta do item 1: cerca de 250 ms no lote de 24 MiB, cerca de 600 ms no de 68 MiB).
7. **Dispersão contra folga.** O pedido fala em dispersão de "cerca de 0,1 GB entre dias". Dentro do mesmo dia, na placa (T24 §13), a faixa das 3 rodadas de `n250` vai de 6.130 a 6.327 MB, ou seja **197 MB**, quase o dobro da folga de 106 MB da `rb250`. A faixa de `rb250` é de 93 MB (5.801 a 5.894) e a de `n1000` de 110 MB. A folga de 106 MB é **menor que a dispersão já vista numa configuração vizinha**, e isso não aparece no texto do §13.
8. **T24 §2, notas fora de ordem** (1, 2, 4, 3). Só forma.
9. **Conferências que bateram** (§10 abaixo): as diferenças do T24 §13 (−309, −846, −368, −974, −128, +10,25 s, +3,79 s), a comparação tela real contra virtual (103 a 221 MB; 8,0 a 9,1 s), 335.655 − 224.439 = 111.216 e 2 × 111.216 = 222.432 = 8.818.146 − 8.595.714, a linha de 1 arena (448.854) e a soma dos 13 lotes (805,72 MiB). O "402,88" do T25 §10.2 inclui as 30 paredes criadas (844.896.960 bytes); sem elas, 402,86.

## 2. Item 1: implementação da 1-B com bloco 250 (memória do arquivo pesado)

### 2.1 O que os números permitem afirmar
**Medido (placa real, T24 §13, 3 rodadas intercaladas):**
- `rb250` (filho novo antes do bloco 22 de 250): A 5.867 / 5.894 MB (mediana / pior), abrir 52,3 / 52,7 s. Cumpre as duas metas nas 3 rodadas, com folga de 106 MB e 7,3 s na pior.
- Controles acima da meta nas 3: `n250` 6.176 / 6.327; `n1000` 6.713 / 6.809; `rb1000` 6.345 / 6.395.
- **Custo de um reinício na placa: 3,79 s** (52,26 − 48,47). Custo do bloco 250 sem reinício: +6,46 s (48,47 − 42,01).
- O bloco pesado num filho novo já leva o filho a 4.855 a 4.872 MB com bloco 250 (T24 §7, em software). **Esse é o piso da família "começar limpo"**: mais reinícios não baixam disso.
- Antes do bloco pesado, o filho normal com bloco 250 já carrega 1.849 a 1.864 MB, cerca de 942 a 957 MB acima da base de 907 (T24 §7, em software).
- As contagens (peças, triângulos, sem malha, simplificadas) são iguais nas 12 aberturas na placa. O `hash_fluxo` muda entre aberturas.

**Não permitem afirmar:**
- Que outra posição de reinício, ou mais de um reinício, também passa: só **um reinício antes do bloco 22** foi medido.
- Por que `rb250` fica 309 MB abaixo de `n250` (T24 §13, limitação 5).
- Nada sobre o simples na placa, nada sobre o detalhado com bloco 250, nada sobre o Windows.
- Que a folga se mantém em outro dia: a dispersão dentro de um dia chegou a 197 MB (§1 item 7).

**Limite duro de tempo** (aritmética): 60 − 52,7 = 7,3 s de folga; ÷ 3,79 s por reinício = **no máximo 1 reinício a mais** (2 no total) no pesado, e isso já sem folga. Toda regra tem de reiniciar **uma vez, no lugar certo**.

### 2.2 O que muda no produto (comum às opções)
1. **Bloco padrão de 1.000 para 250**: `CarregadorMalhas.__init__(tamanho_bloco=1000)` em `carregador.py` linha 134. Muda o produto para todo arquivo (**pergunta 1 ao PO**). No pesado, os lotes do aplicativo passam de 93 para 132 (T24 §5), o que pesa no item 2 e no M5.
2. **Reinício planejado, um caminho próprio.** Hoje o protótipo funcionou porque o 1º filho tinha `ids=None`. Em `_ler` (linhas 312 a 319), quando `falha is None` o código roda `for i in (ids or [])` e manda para `sem_malha` todo id pedido que não chegou ("o conversor não devolveu a peça"). **Se um filho que já é reinício parar de forma planejada, as peças pendentes dele somem em silêncio** (pelo código, não medido). Especificação:
   - O filho que para de forma planejada manda uma mensagem nova, por exemplo `("reinicio", {"proximo_bloco": k})`, **antes** do `fim`. O pai abre o filho seguinte com os ids que ainda não foram resolvidos, na mesma fronteira de bloco e com o mesmo `desl`.
   - Esse caminho **não** toca `espera`, `seguidos`, `acusadas` nem `iso`, não entra no modo isolado e não passa pela "rede de segurança" do `sem_malha`.
   - O `fim` de cada filho hoje **sobrescreve** `est["msgs"]` (linha 528) e **soma** `tempos` (linhas 526 e 527): o `abrir_s` do resumo passa a ser a soma dos filhos. Especificar: as mensagens se juntam (não se sobrescrevem) e os tempos se somam, com o número de filhos no resumo.
   - Os filhos andam **estritamente em sequência**: o filho seguinte só começa depois do `join` do anterior. É o que mantém honesta a conta A (pai + maior filho).
3. **Como o produto sabe onde reiniciar**: as opções da §2.3. Duas regras não valem pelos números (§2.4).

### 2.3 Opções de regra para o reinício
**Opção R-A: crescimento dentro do bloco; refazer o bloco num filho novo (recomendada para o teste barato).**
1. **O que muda.**
   - O pai já acorda a cada 50 ms (`FATIA_S`, `rx.poll`). Passa a ler também a memória residente **atual** do filho: no Linux por `/proc/<pid>/statm`; no Windows por `WorkingSetSize` (a estrutura PMC já existe em `pico_memoria_mb`).
   - O `pico_memoria_mb` **não serve**: devolve o pico (`VmHWM` / `PeakWorkingSetSize`), não o valor atual.
   - Se, num bloco que **não** é o primeiro deste filho, a memória crescer mais que um limiar G desde o começo do bloco, o pai **encerra o filho** (morte planejada) e refaz aquele mesmo bloco num filho novo.
   - No modo normal, os lotes de um bloco só saem no fim do bloco (`emitir` depois de `_bloco`) e o `sem_malha` também. Por isso nada do bloco interrompido chegou ao pai e não há duplicata (pelo código).
   - No máximo 1 reinício por abertura (pelo limite de tempo da §2.1). Se a regra pedir um segundo, ele é registrado e não acontece.
   - Classe **T3** (vigia, processo auxiliar, morte de processo).
2. **Números.**
   - O bloco 22 no filho normal cresce 3.295 a 3.416 MB (software). Os blocos leves de 250 crescem bem menos, mas **isso não foi medido** bloco a bloco com 250 (com 1.000, o bloco 5 cresce 457 MB e o 1, 923 MB; T21 §4).
   - O filho interrompido chega a no máximo 1.864 + G MB, mais o que crescer em 50 ms. Com G até cerca de 2,5 GB ele fica abaixo do pico do filho novo (cerca de 4.900) e **não muda a conta A** (estimativa).
   - Custo: 3,79 s do reinício mais o tempo perdido no bloco até cruzar G. A curva do T21 §3 sobe de 2,4 a 4,5 GB em cerca de 4 s no bloco pesado; para G de 1 GB, perderia cerca de 1 a 2 s (**estimativa**). Na pior rodada, 52,7 + 1 a 2 ≈ 54 a 55 s.
   - **Não permitem afirmar:** quanto tempo se perde de fato, nem que nenhum bloco leve passa de G.
3. **Risco.**
   - Morte planejada confundida com queda ou com o limite: tem de ter caminho próprio (§2.2 item 2).
   - Memória atual no Windows (conjunto de trabalho) pode ser cortada pelo sistema e enganar a regra (T28).
   - Corrida: o pai mata o filho no meio de um `send`; o canal é de mão única e o pai descarta o que vier depois da decisão (pelo código, `_executar` já mata e faz `join`).
   - Tempo perdido maior que o estimado leva a mais de 60 s.
4. **Custo.** Cartão de implementação T3 de 150 a 250 linhas; oráculo à parte (§2.6).
5. **Teste barato antes.** **R-0** (§2.5): simulação sobre as curvas já gravadas pelo T24, sem abrir arquivo.
6. **Por que recomendo.** Não precisa conhecer o arquivo, acerta por construção o "bloco pesado num filho limpo" que foi medido, e o arquivo que não tem bloco pesado nunca reinicia (sem custo no simples).

**Opção R-B: peso previsto pelo IFC na listagem; o filho para antes do bloco pesado** (é a B1 do lote 57).
1. **O que muda.** Depois de listar, o filho calcula, sem geometria, um peso por produto (por exemplo, número de coordenadas e de faces das representações, multiplicado pelos itens mapeados). Antes de começar um bloco cujo peso passe de um limiar P, se esse não for o primeiro bloco do filho, ele manda `reinicio` e para. Decisão **dentro do filho, entre blocos**: sem corrida com o pai. Classe **T3**.
2. **Números.** Nenhum. O T21 §5 mostra que a memória por peça não segue os triângulos (1,6 milhão: cerca de 3,0 GB; 335 mil: cerca de 1,0 GB cada) e que o tempo também não. **Não se sabe se o peso do IFC acerta as peças pesadas.** O custo de calcular o peso também não foi medido.
3. **Risco.** Errar a previsão em outro arquivo (geometria booleana ou de varredura, pequena no IFC e grande na malha) deixa a memória passar sem aviso. O limiar P precisa de dados de mais de um arquivo.
4. **Custo.** Sonda T2 (R-1, §2.5) de cerca de 150 linhas mais o cartão T3 de 150 a 250 linhas.
5. **Teste barato antes.** **R-1**: abrir o pesado sem geometria (cerca de 4 s), calcular o peso de todos os produtos e ver se as posições 5.310, 5.311 e 5.317 ficam no topo. Precisa do arquivo do PO (ok e horário); roda em tela virtual.
6. **Recomendação.** Plano B da R-A, ou como complemento (R-C).

**Opção R-C: R-B para prever, R-A como rede de segurança.** Reinicia antes do bloco previsto como pesado (sem tempo perdido). Se a previsão errar, a R-A pega o bloco que cresceu demais. Ainda no máximo 1 reinício. Custo: soma das duas (2 cartões T3, ou 1 de até 400 linhas). Só faz sentido se o R-1 mostrar que a previsão acerta no pesado.

### 2.4 Regras que não valem (pelos números)
- **Memória que sobrou antes do bloco (B2 do lote 57: "reinicia se o filho passar da base + X").** Para o pesado passar com a folga medida, o bloco pesado tem de começar quase limpo: o pico pior foi 5.894 MB com o filho começando na base. Começar o bloco com X MB acima da base soma cerca de X ao pico (estimativa). Então X teria de ser menor que 106 MB. Mas já antes do bloco 22 o filho tem cerca de 950 MB acima da base, e com bloco 1.000 já depois do bloco 1 tinha 923 MB (T21 §4). Com X abaixo de 106 MB, a regra reiniciaria em quase todo bloco: 60 blocos × 3,79 s. **Não vale.**
- **Posição fixa ou "a cada N blocos".** A sonda usou a posição medida (bloco 22). O produto não conhece o arquivo. E "a cada N blocos" só acerta por coincidência, com no máximo 1 reinício pago pela folga. **Não vale como regra geral.**
- **Menos fios só no bloco pesado.** Pode mudar a malha das peças 2 e 3 (224.439 com 8 fios e 335.655 com 1, hipótese dos fios; §2.6 item 3) e a saída. Não vale até o teste R-2 separar a causa.
- **Variáveis do alocador como solução** (T24 §6): as que agem custam de 2 a 6 vezes o tempo; as outras não provaram efeito e só valem no Linux.
- **Isolar a peça pesada num filho só dela**: o vigia de 20 s pode dispará-lo e a peça vira caixa (lote 57 §2.6).
- **Aceitar a mediana, ou rodadas em tela virtual, como prova.** A meta vale pela pior rodada na placa.

### 2.5 Folga: o que o desenho pode criar sem afrouxar a meta
A meta continua 6.000 MB e 60 s pela pior rodada. Como o bloco pesado num filho novo é o piso (§2.1), **mais reinícios não criam folga**. Folga só pode vir de dentro do bloco pesado ou do pai:
1. **Soltar as malhas do bloco aos poucos.** Hoje `_bloco` guarda em `achados` as malhas do bloco inteiro até `emitir`. Mandar lotes durante o bloco (como o modo isolado já faz com `juntar`, a cada 0,2 s) tira essa retenção.
   - **Teto (estimativa):** o tamanho das malhas do bloco pesado. Com bloco 1.000, o bloco 6 mandou 257 MB ao pai (T21 §4); com 250, no máximo isso.
   - Muda a composição dos lotes (a saída por peça fica igual; o oráculo é por peça). Classe T3.
   - Não sabemos quanto da subida de cerca de 3,95 GB no filho novo é malha guardada e quanto é memória de trabalho do conversor.
2. **Bloco menor só no primeiro bloco do filho novo** (por exemplo 50 peças em volta das pesadas). O T21 mostra que bloco menor baixa o filho (8 fios: 5.207 com 250 contra 5.734 com 1.000), mas o efeito no bloco pesado sozinho não foi medido. Estimativa: no máximo o mesmo teto do item 1. Mexe no tempo.
3. **Mais rigor na prova, nunca menos.** Pergunta 4 ao PO: medir **5 rodadas** (ou 3 em dois dias) e usar a pior. Isso não cria folga, mas diz se os 106 MB se mantêm.
4. **Não vale como folga:** malloc só no Linux, menos fios, limite de peça maior, ou contar a meta sem o pai.

**Testes baratos do item 1** (antes de qualquer código de produto):
- **R-0 (custo zero, sem abrir arquivo; T2).** Ler os dados numéricos que o T24 já gravou (`n250_r*`, `rb250_r*`, em tela virtual e na tela real; só campos numéricos, como no T24 §11) e calcular:
  - a memória do filho no começo e no fim de cada bloco de 250;
  - o crescimento de cada bloco;
  - o instante em que o bloco 22 cruza G = 0,5; 1,0; 1,5 e 2,0 GB;
  - quantos blocos leves passariam de G;
  - o maior silêncio por bloco na **tela real** (§2.6 item 4).

  Simula a R-A e confirma a regra que não vale (§2.4). Se as curvas não tiverem resolução suficiente (10 amostras por segundo, marcas de bloco), o R-0 diz isso, e o R-1 faz a medida.
  - **Precisa do ok do PO** só para ler os dados numéricos fora do repositório (pergunta 3); nenhum IFC é aberto.
- **R-1 (arquivo do PO, ok e horário, tela virtual, cerca de 10 min; T2).** Peso do IFC por produto (R-B) **e** o teste dos fios das peças 2 e 3 (R-2, §2.6). Só se o R-0 não bastar, ou se o PO escolher a R-B.

### 2.6 Riscos e o que o oráculo cobre (pontos 3 a 6 do pedido)
1. **Saída não é igual byte a byte; oráculo por peça.** Para cada `id_step`:
   - triângulos e vértices exatos;
   - caixa (mín e máx do `DTYPE_OBJETO`) exata;
   - uma **forma canônica** da malha da peça (triângulos como trios de vértices posição/normal/cor, ordenados) com comparação **exata**.

   Também: `sem_malha` (ids e motivos), `simplificadas` (vazia no pesado), `produtos_total`, número de peças com malha, triângulos totais. Não se compara: número de lotes, ordem dos lotes, `hash_fluxo`.
   - **Regra de controle:** o oráculo tem de passar primeiro em **normal contra normal** (duas aberturas do produto de hoje). Se a forma canônica exata falhar aí, quem escreve o oráculo **para e reporta**, com a causa medida (hipótese do T24 §5: a numeração das cores pelo `np.unique`). Tolerância só com causa medida e aprovação do revisor Opus, nunca inventada.
2. **Mesmos fios dos dois lados.** O oráculo compara produto contra produto com o mesmo `threads`. O passe de 1 fio do T21 **não** é referência.
3. **As peças de 224.439 contra 335.655 triângulos.** Teste **R-2** (dentro do R-1):
   - converter as peças 2 e 3 sozinhas, num processo novo, com 1, 2, 4 e 8 fios;
   - e o bloco 22 inteiro com 8 fios.

   Se 1 fio der 335.655 e 8 der 224.439, a causa é o número de fios. Se 8 sozinha der 335.655, a causa é o contexto do bloco (outra hipótese).
   - Consequência que independe da 1-B: o **modo isolado do produto** usa `threads` = 1 (linha 365). Se a causa for o número de fios, uma peça que cai no modo isolado já sai com outra malha hoje. Isso vira um achado à parte, registrado no LOG, fora deste cartão.
   - Guarda do oráculo: no pesado, a mudança não pode levar nenhuma peça ao modo isolado (0 entradas, como hoje).
4. **Limite de 20 s por peça (silêncio do filho).**
   - Com reinício, o bloco pesado é o 1º do filho novo. O silêncio medido foi de 13,3 a 14,7 s com 250 e de 14,4 a 15,1 s com 1.000, em software (folga de 3,6 a 6,7 s).
   - Com bloco 250 há menos peças no bloco mandando `feitos`, mas a peça 1 domina o silêncio (aviso 16,6 a 17,4 s depois do início do bloco, limite superior; T24 §4).
   - **Falta medir:** o maior silêncio na tela real (R-0, se os dados tiverem as marcas) e no Windows (T28).
   - A R-A também pede: a morte planejada não é contada como "limite", e o bloco refeito começa com o relógio zerado. Na fase "abrindo"/"listando" do filho novo vale `limite_abrir_s` (600 s), como hoje (pelo código, linha 371).
   - Nenhuma opção muda `limite_peca_s`.
5. **Windows (T28).** "Processo novo devolve a memória ao terminar" é só desenho. O T28 tem de medir, no pesado, 3 rodadas (5 se o PO aceitar):
   - conta A com `PeakWorkingSetSize` do pai e de cada filho;
   - 0 instantes com dois filhos vivos;
   - custo de um reinício (o `spawn` no Windows reabre o Python e importa o IfcOpenShell: pode passar dos 3,79 s);
   - abrir ≤ 60 s;
   - maior silêncio por bloco;
   - na R-A, se a leitura do conjunto de trabalho dispara no mesmo bloco que no Linux;
   - oráculo por peça Windows contra Windows.
6. **Fios da tela (ADR-004, não lido aqui), M5 e saída igual do T12 (não lido).**
   - Pelo código, os reinícios acontecem na thread leitora (`_trabalhar` / `_ler`); a thread da janela não muda, e o pai não abre o arquivo durante a carga.
   - O que pode quebrar:
     - o vigia e os ganchos `OBIM_TESTE_*` (peça lenta, matar filho, falhar caixa, matar no fim) com reinícios;
     - cancelar durante um reinício (tem de entregar "cancelado" sem filho sobrando);
     - o M5 durante a abertura, pelo intervalo de cerca de 3,8 s sem lotes e pelos 132 lotes em vez de 93.
   - Testes: os do oráculo (§2.7), mais o M5 na placa durante a abertura do pesado e do simples.
   - O T12 cobre a gravação do IFC, que esta mudança não toca (pelo código). Quem escrever o oráculo confere o critério exato do T12.
7. **Arquivos que ainda não foram medidos com bloco 250:** o detalhado (abrir, memória, M5) e o simples na placa. Pelo oráculo 8 do lote 57, nada pode piorar neles. O bloco 250 custou +6,5 s no pesado.

### 2.7 Cartões (cada um ≤ 400 linhas)
| cartão | classe | quem | linhas (estimativa) | precisa do PO? |
|---|---|---|---|---|
| R-0: simulação nos dados já gravados | T2 | sonnet | 100 a 150 (script fora do produto) | ok para ler dados numéricos (pergunta 3) |
| R-1 (+ R-2): peso do IFC e fios das peças 2 e 3 | T2 | sonnet | 150 a 250 (sonda) | arquivo pesado, ok e horário; tela virtual |
| Implementação: bloco 250 + reinício planejado + regra escolhida | **T3** | sonnet | 150 a 250 (R-A ou R-B); até 400 (R-C) | não |
| Oráculo: comparação por peça + testes | **T3** (oráculo) | Opus especifica, outro sonnet escreve | 250 a 350 | não (IFC públicos e sintéticos no CI) |
| Medida oficial | T2 | sonnet | sonda existente | placa real, ok e horário |

- **O oráculo** (outro agente, não o implementador) verifica:
  1. comparação por peça (§2.6 item 1) em IFC públicos e sintéticos, com reinício forçado por um gancho novo (`OBIM_TESTE_REINICIO_BLOCO=k`, e um segundo `k2` para **dois reinícios seguidos**, o caso do `sem_malha` silencioso da §2.2);
  2. 0 instantes com dois filhos vivos;
  3. valores padrão de `limite_peca_s` (20), `limite_abrir_s` (600), `max_pecas_condenadas` (20) e `max_espera_s` (120) sem mudança; reinício planejado sem mexer em `espera`, `seguidos` e `acusadas`;
  4. ganchos `OBIM_TESTE_*` com reinício;
  5. cancelar no meio do reinício;
  6. as mensagens juntadas e os tempos somados no resumo;
  7. na máquina do PO, comparação por peça no pesado, novo contra `n1000` e contra `n250`.
- **Medida oficial** (ok do PO): pesado, simples, detalhado e 25 MB na placa, rodadas intercaladas, conta A e conta B, pior rodada ao lado da meta, e o M5.
- **Revisão:** lote Opus com a implementação e o oráculo juntos.

### 2.8 Recomendação do item 1
1. Fazer o **R-0** (custo zero).
2. Se ele mostrar que a R-A reinicia só uma vez, no bloco 22, com tempo perdido abaixo de cerca de 5 s, seguir com a **R-A**.
3. Se não, o R-1 decide entre R-B e R-C.

O PO decide o bloco 250 (pergunta 1) e a régua da prova (pergunta 4).

## 3. Item 2: a troca de geometria abaixo de 200 ms no detalhado (M2b)

### 3.1 O que os números permitem afirmar
**Medido (T25 §10, placa real):**
- A troca manda o mesmo que o reenvio forçado da cena inteira: razão 1,000 em 120 de 120 pares.
- A placa chega a 0 triângulos, e são 404 quadros (cerca de 6,8 s) com qualquer lote tocado.
- Criar uma parede (só acrescenta um lote) leva 2 quadros e **61 / 80 ms** no detalhado (mediana / pior), 48 / 50 ms no 25 MB; o T22 deu 48,9 ms.
- Pelo código: `enviar` limpa a placa quando a geração muda (`motor.h` linha 203), e só lotes completos são desenhados (linhas 223 e 224 e 287).

**Teto por troca** (estimativa, a regra que manda em todas as opções): (200 − 24,6) ÷ 16,77 ≈ 10,5, ou seja **cerca de 10 quadros, contando o +1**. Sobram cerca de 9 quadros de envio, **cerca de 18 MiB por troca**, sem nenhuma folga. Qualquer opção cujo envio cresça com o lote tocado **falha** em 24, 68 e 285 MiB, a não ser que os lotes tenham teto.

**Não permitem afirmar:**
- bytes por quadro (não medidos);
- o efeito do limite de 4 ms na placa;
- parede em lote de outro tamanho;
- mover, apagar, desfazer;
- o M5 com cena grande;
- Windows.

### 3.2 Base comum a todas as opções: "não limpar a placa" com troca atômica
Pelo código de hoje, uma troca sobe a geração e a placa volta a zero. Toda opção abaixo precisa de:
- **identidade estável por lote** em `cena.*` (não lido);
- `enviar` deixa de limpar tudo quando a geração muda: um lote refeito é **trocado na placa só quando o substituto está completo** (o antigo fica desenhado até lá);
- `limpar()` e a perda de contexto seguem reenviando tudo, como hoje.

**Regra de honestidade da sequência (vale para todas as opções):** a sequência do comando só pode aparecer no quadro em que a cena desenhada **já é a da cena depois da troca**. Nenhum quadro com a sequência nova pode ter a parede antiga **e** a nova, nem nenhuma das duas. Uma 2-A que deixasse a sequência avançar com o lote novo enquanto o lote antigo (com a parede velha) ainda está desenhado passaria no M2b mostrando a cena errada. **Isso não vale** (§3.6).

Ordem das travas: `Motor::m_` → `DadosCena::m_` → `mc_` (`motor.h` linha 5). A thread de desenho nunca toca no Python. Classe **T3**.

### 3.3 Opção 2-A + teto de lote (reenviar só o lote tocado, com lotes de no máximo C MiB)
1. **O que muda.**
   - A base comum, mais um teto de tamanho por lote, aplicado **dentro de `cena` no C++** quando o lote chega (`adicionar_lote` parte o lote bruto em sub-lotes de até C MiB, **na fronteira de peça**, sem partir peça).
   - Assim vale para os dois fluxos e para o caminho que o juiz mede, sem tocar em `fluxo_a.py` (a guarda de diff do lote 57 §3.3, oráculo 7).
   - Peça maior que C fica num lote só dela.
   - A sequência devolvida ao Python é a do último sub-lote (`cena.*` não lido; estimativa).
2. **Números (estimativa, quadros = teto((C + lote novo) ÷ 2) + 1, mais 24,6 ms):**
   - C = 2 MiB: 3 quadros, cerca de 75 ms;
   - C = 8 MiB: 6 quadros, cerca de 125 ms;
   - C = 16 MiB: 10 quadros, cerca de 192 ms (sem folga: **não vale**).

   O custo fica igual para lotes de 24, 68 ou 285 MiB, porque todos viram sub-lotes de até C.
   - Mais lotes: o detalhado vai de 13 para pelo menos 403 (C = 2) ou pelo menos 101 (C = 8). Isso é o mesmo número de chamadas de desenho por quadro.
   - **Não permitem afirmar:** o custo de 400 chamadas por quadro (desprezível na placa, provavelmente; em software e no WARP, desconhecido), nem o efeito no M5 e na seleção.
3. **Risco.**
   - M5 e ritmo de quadros com muitos lotes (software e Windows).
   - A captura pixel a pixel contra `perder_contexto()` pede a mesma ordem de desenho da cópia compacta.
   - Editar uma peça maior que C custa o tamanho dela (inerente: a geometria nova também tem de subir).
4. **Custo.** 3 cartões (estimativa, `cena.*` não lido): cena (identidade, teto, troca atômica) de 250 a 350 linhas; motor (não limpar, trocar por identidade) de 150 a 250; oráculo de 300 a 400 (outro agente).
5. **Teste barato antes.** **G-0** (§3.7).
6. **Recomendação.** Alternativa à 2-G, se a 2-G se mostrar inviável no G-0.

### 3.4 Opção 2-G por desenho: esconder a peça antiga pulando a faixa dela, sem enviar nada (**recomendada**)
1. **O que muda.**
   - Os índices de cada peça são contínuos no lote: `montar_lote` grava em `DTYPE_OBJETO` o início e o tamanho dos índices da peça (`ii`, `len(idx)`, linha 123). Em `fluxo_a` não foi lido; o formato é o mesmo `LoteMalha`.
   - Esconder a peça = **desenhar o lote em duas chamadas** (`drawIndexed` com contagem e primeiro índice), pulando a faixa dela. **Zero bytes enviados.** Isso evita a dúvida do lote 57 §3.5, se o QRhi aceita reescrever buffer `Immutable`. O `drawIndexed` com primeiro índice é parte pública do QRhi (pela documentação pública do Qt; a conferir no T3, no OpenGL e no D3D11).
   - Na troca, `cena` não sobe a geração: marca a peça antiga como escondida no lote dela e acrescenta o lote novo.
   - **O esconder e a entrada do lote novo valem no mesmo quadro**: o `enviar` aplica a lista de escondidas no quadro em que o lote novo fica completo.
   - Depois, uma **compactação em segundo plano**, dentro do orçamento atual e **atrás** de qualquer lote novo, refaz o lote sem as peças escondidas. A troca atômica da §3.2 mantém o lote antigo (com o salto) desenhado até o substituto ficar completo.
   - Seleção (`cena_.lotes()`) e caixa da cena ignoram as escondidas. Perda de contexto: o reenvio vem da cópia compacta com as escondidas aplicadas.
   - Classe **T3**.
2. **Números (estimativa).**
   - A troca de uma parede custa o mesmo que criar uma parede mais o comando. A referência medida é 61 / 80 ms no detalhado (T25 §10.2) e 48,9 ms (T22). A conta dá 2 quadros (cerca de 33 ms) + 24,6 ms ≈ **cerca de 60 ms**, para lotes de 24, 68 ou 285 MiB.
   - A compactação do lote de 285 MiB leva cerca de 143 quadros (cerca de 2,4 s) em segundo plano, com a cena inteira visível.
   - **Não permitem afirmar:** o custo das chamadas a mais por peça escondida, nem a memória da placa durante a troca de um lote grande (o lote antigo e o substituto juntos: +285 MiB por cerca de 2,4 s; no WARP isso é memória do sistema).
3. **Risco.**
   - Mais estado (escondidas, compactação, seleção, caixa, perda de contexto no meio da compactação).
   - Pixel: pular a faixa mantém a ordem dos outros triângulos. O lote novo vai ao fim, como na cópia compacta, **se** `cena` compacta assim (não lido): o oráculo confere.
   - Muitas peças escondidas no mesmo lote aumentam as chamadas, até a compactação.
   - Windows: D3D11 e WARP só no CI e no T28.
4. **Custo.** 4 cartões (estimativa): cena (identidade, escondidas, troca atômica) de 250 a 350 linhas; motor (desenho com saltos, não limpar, trocar) de 150 a 250; compactação de 150 a 250; oráculo de 300 a 400 (outro agente).
5. **Teste barato antes.** **G-0** (§3.7), com a medida de "criar" como piso de referência.
6. **Recomendação.** É a recomendada: é a única cujo custo **não depende do lote tocado**, não multiplica os lotes da cena e não envia nada para esconder.

**Variante 2-G por índices (lote 57 §3.5):** zerar na placa os índices da peça antiga. Envia 4 bytes por índice: 144 bytes numa parede, cerca de 19 MB numa peça de 1,6 milhão de triângulos (estimativa). Depende de o QRhi aceitar atualizar parte de um buffer `Immutable` (não verificado; talvez trocar para `Static`). Fica atrás da 2-G por desenho; só se o salto no desenho falhar em algum backend.

### 3.5 Por lote tocado (estimativa; M2b em ms, já com os 24,6 ms do comando)
| opção | 1.152 B (parede criada) | 24,24 MiB | 68,27 MiB | 285,36 MiB (sem parede hoje) |
|---|---|---|---|---|
| hoje (reenvia a cena) | cerca de 6.775 (medido) | cerca de 6.800 (medido) | cerca de 6.890 (medido) | cerca de 6.800 (a cena inteira) |
| 2-A pura (sem teto) | cerca de 60 | cerca de 250 a 260 | cerca de 610 a 630 | cerca de 2.400 |
| 2-A + teto 8 MiB | cerca de 60 | cerca de 125 | cerca de 125 | cerca de 125 |
| 2-A + teto 2 MiB | cerca de 60 | cerca de 75 | cerca de 75 | cerca de 75 |
| 2-G por desenho | cerca de 60 | cerca de 60 | cerca de 60 | cerca de 60 |
| 2-G por índices (parede) | cerca de 60 | cerca de 60 | cerca de 60 | cerca de 60 |

Tudo isso vale para uma parede. Para uma peça grande, toda opção paga pelo menos o tamanho da geometria nova.

### 3.6 O que não vale no item 2
- **2-A pura**: cerca de 250 ms (24 MiB), cerca de 600 ms (68 MiB), cerca de 2,4 s (285 MiB).
- **2-A com a sequência avançando antes de o lote refeito estar na placa** (parede antiga ainda desenhada): passa no número com a cena errada.
- **Reenvio com prioridade para o lote tocado, limpando a placa** (lote 57 §3.6): é a opção C disfarçada.
- **Manter a cena antiga desenhada e reenviar tudo por trás** (troca da cena inteira): a cena deixa de sumir, mas continua cerca de 6,8 s.
- **Lotes menores só no carregador do aplicativo.** O M2b é medido pelo `abrir` do fluxo A (blocos de 500 produtos, lotes até 285 MiB; T25 §9 e §10.6 item 6), não pelo carregador. O carregador já limita os vértices a 8 MiB (`MAX_BYTES_LOTE`, linha 33): com os índices, cerca de 9 MiB por lote, e a 2-A daria cerca de 6 quadros, cerca de 125 ms, **só no caminho do aplicativo** (estimativa). Mexer só ali não muda o número do juiz. Mexer no `abrir` do fluxo A toca `fluxo_a.py`, que está na guarda de diff do lote 57 e nas linhas do M7: **pergunta 5 ao PO**. O teto dentro de `cena` (§3.3) evita isso.
- **Opções C, D e E** (fora de pauta, PO 2026-10-18) e **2-B sem o ok do PO**.
- **Medir só a parede criada pelo roteiro.** A troca de parede do arquivo (lotes de 24 e 68 MiB) tem de cumprir os mesmos 200 ms: pergunta 6.

### 3.7 O que a sonda do T25 não mede e os testes baratos
**Não mede:**
- início e fim do envio por quadro dentro do C++;
- bytes por quadro;
- o lote escolhido (ela não escolhe: 9 trocas no lote de 24 MiB e 1 no de 68 MiB por rodada);
- parede em lote de outro tamanho (8, 47, 123 ou 285 MiB);
- mover, apagar, desfazer, refazer;
- M5 durante a troca;
- o maior intervalo entre dois quadros;
- Windows.

**Testes:**
- **G-0a (sem C++, sem arquivo do PO, tela virtual; T2).** Pela API Python (`adicionar_lote`/`atualizar`), montar uma cena sintética com **os 13 tamanhos de lote do detalhado** (0,55 a 285,36 MiB, 805,7 MiB no total) e paredes dentro dos lotes de 1, 8, 24, 68 e 285 MiB.
  - Medir o comportamento de hoje (quadros e pedaços por troca e por lote tocado) e "criar" como piso.
  - Confirma o modelo "teto + 1" fora do arquivo real e dá a linha de base do oráculo. Em software os contadores valem (T25: o 25 MB deu 24 quadros nos dois); os milissegundos não.
  - Atenção: a cena de cerca de 806 MiB deu `TimeoutError` na abertura em software (T22). Se repetir, reduzir a cena **mantendo os lotes grandes** (por exemplo, só os lotes de 24, 68 e 285 MiB, cerca de 378 MiB), sem tocar em `OBIM_QUADRO_MS`.
- **G-0b (ramo descartável que nunca vai ao `main`, classe T3, sem arquivo do PO).** Instrumentar `enviar`: instante de início e fim, bytes e pedaços por quadro, sequência, e se parou pelos bytes ou pelos 4 ms. Mais um protótipo mínimo do salto no desenho (2-G) numa cena sintética. Mede, em tela virtual:
  - quadros da troca por lote tocado com a 2-G;
  - se o OpenGL aceita o `drawIndexed` com primeiro índice;
  - o custo de desenho com saltos.

  O D3D11 fica para o CI do Windows. Cerca de 150 a 250 linhas. Revisão: lote Opus, como ensaio.
- **Sessão na placa** (ok e horário do PO): só depois da implementação, detalhado e 25 MB, 3 rodadas, M2b e M5, parede criada e parede do arquivo.

### 3.8 2-B (subir o orçamento): só como decisão do PO, com impacto e sem recomendação para fechar a tarefa
- **Orçamento mínimo para 200 ms** (estimativa, cerca de 9 quadros de envio):
  - com 2-A pura: 2,7 MiB (24 MiB), 7,6 MiB (68 MiB), 31,7 MiB (285 MiB);
  - sem 2-A (hoje): cerca de 90 MiB por quadro.
- **O limite de 4 ms** teria de subir junto: não se sabe quanto tempo leva mandar 8 ou 30 MiB num quadro na placa, no software e no WARP.
- **M5 e ritmo dos quadros:** cada quadro com envio maior pode passar de 16,7 ms (quadros perdidos, mouse atrasado). O M5 nunca foi medido com cena grande (`lote.py` sem `--ifc`; lote 57 §3.1).
- A cena continua sumindo e voltando enquanto não houver a base comum da §3.2.

### 3.9 Oráculo do item 2 (outro agente escreve; um Opus que não seja o revisor especifica)
1. A cada quadro de uma troca, `triangulos_na_placa` ≥ triângulos da cena − triângulos da peça antiga (a cena nunca se esvazia).
2. Nenhum quadro com a sequência do comando mostra a parede antiga e a nova, nem nenhuma das duas (por captura e pela tabela de escondidas).
3. A captura depois da troca é igual, pixel a pixel, à captura depois de `perder_contexto()`, com a mesma câmera. Mesma ordem de desenho da cópia compacta, e ninguém afrouxa esse teste depois.
4. Bytes enviados por troca (2-G): só o lote novo, mais a compactação **depois** de o lote novo entrar. Sem supor 1 pedaço por 2 MiB (§1 item 3).
5. Parede criada **e** parede do arquivo em lotes de 1 KB, 24, 68 e 285 MiB (sintético), e no detalhado na placa.
6. Mover, apagar, desfazer, refazer, `limpar()` e perda de contexto no meio de uma troca **e** no meio de uma compactação; seleção acerta a peça nova e nunca a escondida; caixa da cena igual à do reenvio completo.
7. Fluxo B e jobs do Windows.
8. Guarda de diff: `fluxo_a.py`, `medir_s04.py`, o juiz, `ORCAMENTO_BYTES` e `ORCAMENTO_TEMPO` não mudam.
9. M5 e o juiz estrito do T12 continuam passando.
10. Medida na placa (ok do PO): M2b p95 em 3 rodadas no 25 MB e no detalhado, meta de 200 ms ao lado, parede criada e parede do arquivo separadas.

### 3.10 Recomendação do item 2
1. Fazer o **G-0a** (sem PO).
2. Depois o **G-0b** (protótipo T3 descartável).
3. Se o salto no desenho funcionar, implementar a **2-G por desenho** sobre a base comum da §3.2.
4. Se não funcionar, a **2-A com teto de 8 MiB dentro de `cena`** (ou de 2 MiB, se o M5 aguentar).

A 2-B fica só como decisão do PO.

## 4. Ordem sugerida
1. **Já, sem arquivo do PO:**
   - R-0 (dados já gravados, só com o ok da pergunta 3);
   - G-0a (sintético, tela virtual).

   Um implementador por vez.
2. **G-0b** (ramo descartável, T3, sintético).
3. **Item 1 primeiro na implementação.** Já há uma configuração medida que passa, a mudança é menor (carregador em Python) e fecha uma meta. Se o R-0 não bastar, antes vem o R-1 (sessão com o arquivo pesado em tela virtual).
4. **Item 2** (2-G ou 2-A com teto), conforme o G-0b.
5. **Uma só sessão na placa real** (ok e horário do PO) para os dois: pesado, simples, detalhado e 25 MB (memória, abrir, M5) e M2b no 25 MB e no detalhado. **Nenhum teste mede os dois itens.** O que se divide é a sessão na placa e o ok do PO.

Se nenhuma opção de um item fechar a meta depois dos testes, a regra do `v2/03` vale: parar e levar ao PO com opções.

## 5. Efeito nos ADRs (só aponto; nada é decidido aqui)
- **ADR-004** (não lido aqui): a R-A acrescenta a morte planejada do filho pela thread leitora; a 2-G acrescenta estado na thread de desenho sob `DadosCena::m_`. Ambas mantêm a ordem de travas.
- **ADR-001** (ainda não existe): o M2b em IFC real continua um problema do desenho C++ comum aos dois fluxos.

## 6. Perguntas ao PO (só o que é decisão dele)
1. **Aceita mudar o tamanho padrão das partes de 1.000 para 250 peças**, para todo arquivo? Custo medido na placa: +6,5 s ao abrir o pesado sem reinício. O detalhado ainda não foi medido assim. **Recomendação:** sim, com a condição de que o detalhado e o simples não piorem na medida oficial.
2. **Autoriza testar primeiro (R-0, G-0a, G-0b) e só escolher a regra e a opção depois?** **Recomendação:** sim.
3. **Libera a leitura dos números já gravados pelo T24** (fora do repositório, só campos numéricos, nenhum arquivo seu aberto) para a simulação R-0? **Recomendação:** sim.
4. **Régua da prova da memória:** com folga de 106 MB e dispersão de até 197 MB vista num dia, aceita exigir 5 aberturas (ou 3 em dois dias diferentes) e usar a pior? A meta não muda; a prova fica mais exigente. **Recomendação:** sim, 5 aberturas.
5. **Mexer em como o fluxo A agrupa o arquivo aberto (`fluxo_a.py`) conta como mudar o produto ou mudar a régua?** **Recomendação:** tratar como régua e não mexer. O teto de lote, se escolhido, fica dentro do C++ (`cena`).
6. **A meta de 200 ms vale também para trocar uma parede que veio do arquivo** (lotes de 24 e 68 MB), não só para a parede criada pelo roteiro? **Recomendação:** sim (padrão rigoroso).
7. **Subir o orçamento da tela (2 MiB e 4 ms)**: quer considerar agora? Impacto: §3.8. **Recomendação:** não decidir agora, só se a 2-G e a 2-A com teto falharem.

E o horário da sessão na placa real, quando chegar a hora (seção 4, passo 5).

## 7. O que registrar no LOG
- "Lote opus 58 | CONCLUÍDO (TA) | Especificação do T20 (1-B com bloco 250) e do T22 (M2b < 200 ms).
  - Item 1: bloco 250 + reinício planejado com caminho próprio (hoje o `_ler` mandaria para `sem_malha`, em silêncio, as peças de um 2º reinício). Regras: **R-A recomendada** (crescimento no bloco, refazer em filho novo; no máximo 1 reinício), R-B (peso do IFC), R-C (as duas). Não valem: memória que sobrou antes do bloco (pediria X < 106 MB com ~950 MB já retidos), posição fixa, menos fios. Oráculo por peça, forma canônica exata, controle normal contra normal. Testes: R-0 (dados já gravados), R-1/R-2 (arquivo pesado, peso e fios das peças 2 e 3).
  - Item 2: a conta do T25 §10.4 corrigida (teto + 1 quadro + 24,6 ms: a 2-A pura no lote de 24 MiB dá ~250 ms, no de 68 MiB ~600 ms). **2-G por desenho recomendada** (pular a faixa da peça antiga, 0 bytes, ~60 ms estimados como criar parede), 2-A com teto de lote dentro de `cena` como alternativa, 2-B só decisão do PO. Testes: G-0a (sintético com os 13 tamanhos de lote do detalhado) e G-0b (C++ descartável, T3).
  - Contradições: T25 §10.4 (quadros fracionados, sem o +1), T25 §9 (sem o +1), cabeçalho do T25 contra o §10, fatia de 28 bytes no `enviar` (pedaços a mais; orçamento passado em 20 bytes), folga de 106 MB menor que a dispersão de 197 MB do `n250`, erros já refutados do lote 57."
- Corrigir no T25 (tarefa de texto, com o ok do líder): §10.4 e §9 com teto + 1 e os 24,6 ms; o cabeçalho limitado às seções 1 a 9.
