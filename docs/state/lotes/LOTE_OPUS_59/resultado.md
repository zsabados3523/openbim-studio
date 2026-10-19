<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_59: resultado

**CONCLUÍDO** (planejamento, classe TA, esforço médio). Nada foi implementado, medido nem aberto. Autor: Opus. Este texto especifica e recomenda; o PO deixou a escolha de G e da opção da troca para o líder seguir a recomendação (pedido, "Regra do PO"). Pela regra 6 do `CLAUDE.md`, a implementação e o oráculo que nascerem daqui são revisados por **outra** sessão Opus, e oráculo e implementação ficam com subagentes diferentes.

Li só o contexto fechado: `LOTE_OPUS_58/resultado.md`, `reports/F0-S04-T24.md`, `T25.md`, `T26.md`, `T27.md`, os cartões T29, T30 e T32, `PO.md` (A24 a A31), `carregador.py`, `processo_malhas.py`, `nucleo/motor.h`, `nucleo/cena.h` e `nucleo/cena.cpp`. **Não li** `motor.cpp`, o arquivo da ponte (`ponte_viewport.cpp`), `selecao.h`, `formato_malha.py`, `fluxo_a.py`, as sondas, os testes nem dados brutos. O que depende deles está marcado "não lido".

Convenções (as do lote 58): **medido** = número de relatório; **pelo código** = leitura do código citado, com linha, sem medida; **estimativa** = conta feita aqui sobre números medidos; **hipótese** = causa não provada, sempre com o teste que a confirma; **a conferir** = comportamento do Qt que não verifiquei no código do Qt. Metas intocadas: conta A < 6.000 MB e abrir ≤ 60 s pela pior de 5 aberturas na placa (A28); M2b p95 < 200 ms também para a parede vinda do arquivo (A30); orçamento por quadro 2 MiB e 4 ms (A21, A31); `limite_peca_s` 20 s; `fluxo_a.py` é régua (A29). Windows não foi medido: o que se diz dele vale só pelo desenho.

## 0. Resumo para o PO (5 linhas, sem siglas)
1. Memória do arquivo pesado: recomendo que o programa reinicie o processo do 3D quando uma parte crescer mais de 1 GB dentro dela (fora a primeira parte de cada processo). Nos números já gravados isso acerta só a parte pesada e custa menos de 1 s a mais.
2. Antes de mexer no seu arquivo, tudo se testa com modelos de teste. Depois, uma sessão sua na placa com 5 aberturas, como você pediu.
3. Troca da parede: achei no código por que a tela joga a cena inteira fora a cada troca; é uma linha só, e a cópia da cena já fica certa. Dá para trocar só o pedaço tocado e esconder a parede velha na hora.
4. Achado novo: refazer a cópia de um pedaço grande na memória custa tempo (cerca de 0,1 s num pedaço de 68 MB, ainda não confirmado). Por isso o próximo teste mede esse tempo e uma versão mais rápida, antes de escolher.
5. Nenhuma recomendação mexe em meta, régua, limite ou orçamento da tela. Preciso de você em 3 pontos curtos (seção 7).

## 1. Erros e contradições nos relatórios, cartões e no lote 58
1. **T27 §2 e §3 item 1, "o modelo não vale": conclusão forte demais.** O cartão do T27 aplicou o modelo "teto(bytes ÷ 2 MiB) + 1" ao lote **tocado**, mas hoje o programa envia a **cena inteira** (§3.1 abaixo, pelo código). Com os bytes que de fato são enviados (844.858.176), o mesmo modelo acerta dentro de 1 quadro em 45 de 45 (medido no T27). Leitura certa: o modelo vale; a entrada usada no cartão estava errada. Para a 2-A (reenviar só o lote tocado) o modelo continua sem teste, porque a 2-A não existe.
2. **T27 §2, "lotes não vazios: cada troca e cada criar soma 1".** Pelo código, `sem` (`cena.cpp` linhas 31 a 50) devolve um lote **vazio** quando tira a única peça de um lote, e esse lote continua em `lotes_` (linha 104 só troca o ponteiro). `totais().lotes` conta todos (linha 137). Na troca de uma parede criada (lote de 1 KB), o lote antigo fica vazio e o novo entra: o número de lotes **não vazios** não muda; o que sobe 1 é o total. Provável erro de rótulo. Teste: contar os lotes com `triangulos > 0` antes e depois de cada troca.
3. **T27 §3 item 2, hipótese da "rajada de pedaços do fim": o código explica.** Cada parede criada ou trocada vira um lote de 1.152 bytes no fim da fila (`atualizar` linha 109), com 2 pedaços (vértices e índices). Na ordem dos casos da rodada (criar, troca no lote de 1 KB, 8,97, 24, 68, 285 MiB), o número de lotes pequenos não vazios cresce 3 por caso (3, 3, 6, 9, 12, 15; a troca no lote de 1 KB não soma, item 2). O maior número de pedaços num quadro visto foi 8, 13, 19, 25 e 31 ≈ 2 × (3, 6, 9, 12, 15) + 1 ou 2: o quadro que atravessa a fila de lotes pequenos. **Pelo código, compatível; teste:** contador por fase e por lote no T32.
4. **T27 §4 e T25 §5/§10.2, o "+1 quadro" sem causa.** Hipótese forte pelo código: o laço de quadros (`motor.h` linhas 232 a 299) faz `enviar` logo depois de `beginFrame` e só grava a sequência depois de `endFrame`. Se o comando volta enquanto um quadro já passou do `enviar` (desenho e apresentação em curso), esse quadro é apresentado sem nada novo e conta como 1. Com cena de 8,8 milhões de triângulos em software, o desenho ocupa quase todo o quadro, então isso é o normal (404); quando o comando cai durante a espera do relógio, não há quadro em voo (403, visto em 4 de 45). "Criar" = 2 quadros = 1 em voo + 1 de envio. **Teste:** no T32, registrar por quadro se `enviar` já viu a mudança; o primeiro quadro contado deve ter 0 bytes da troca em 41 de 45 e o caso de 403 nenhum quadro desses. Consequência: o +1 é latência real (entra no M2b), mas não é custo de envio.
5. **Lote 58 §3.2, "identidade estável por lote (não lido)".** Ela já existe: `sem` copia a sequência do lote (`cena.cpp` linha 40, `r->seq = d.seq`) e a troca mantém a posição do lote na fila (linha 104). O lote refeito tem a mesma sequência e o mesmo lugar.
6. **Lote 58 §3.4, "compactação em segundo plano".** A cópia compacta sem a peça antiga **já é feita na hora**, dentro de `atualizar` (linha 104, fora do mutex). O que seria "em segundo plano" é só o **reenvio** do lote refeito à placa.
7. **Lote 58 §3.4 e §3.5, "2-G ≈ 60 ms para qualquer lote": deixa de fora o custo de `atualizar`.** O M2b mede do comando até o quadro com a sequência nova, e `atualizar` (com `sem`) está no caminho. Pelo código, `sem` refaz o lote tocado vértice a vértice (`insert` de 28 bytes, linha 41) e índice a índice (`push_back`, linha 42), sem reservar espaço; e cria o vetor `morto` do tamanho dos índices **de todo lote da cena**, antes de saber se o lote foi tocado (linha 32). **Hipótese com número:** no T25 §10.2 (placa), com os mesmos 404 quadros, a troca no lote de 24,24 MiB levou 6.798 ms e a do lote de 68,27 MiB 6.886 ms, contra 6.775 ms no lote de 1 KB: **+23 ms e +111 ms**, cerca de 1,0 a 1,6 ms por MiB. Se for `sem`, a 2-G sem mais nada daria (estimativa): cerca de 85 ms no lote de 24 MiB, **cerca de 170 ms no de 68 MiB** (sem folga) e cerca de 330 a 520 ms no de 285 MiB (falha). Base fraca: só 3 trocas no lote de 68 MiB. **Teste barato, sem C++:** medir o tempo da chamada `atualizar` pelo Python, por tamanho de lote tocado (T32a, §3.4).
8. **Lote 58 §1 item 2(e), "hoje 1,7 ms para enviar ao C++".** Os 1,7 ms do T22 são da troca de parede **criada** (lote de 1 KB), não de um lote grande; não servem para estimar `sem` num lote de 24 a 285 MiB (item 7).
9. **T26 §6 item 2, taxa de crescimento.** O T26 usa "cerca de 1 GB/s". A tabela B do próprio T26 mostra mais: `n250` real de 0,5 para 1,0 GB em 0,30 a 0,40 s (1,25 a 1,7 GB/s) e `rb250` real em 0,20 s (cerca de 2,5 GB/s). A conta do filho morto refeita está na §2.1; a conclusão (abaixo do filho novo) não muda.
10. **T26 §5, silêncio "somado" entre filhos.** O vigia conta o silêncio **de cada filho** (`ultimo` nasce em cada `_executar`, `carregador.py` linha 395). Somar o tempo perdido do filho velho com os 3,79 s do novo não corresponde a nada que o vigia veja. O que importa: o filho velho cala no máximo o tempo até cruzar G; o filho novo repete o silêncio do `rb250` (13,68 a 13,83 s na tela real). Inofensivo, mas a frase deve sair.
11. **T26 §2, "a isenção do primeiro bloco é precisa para G = 0,5 GB".** Também é precisa com G = 1,0 GB: o primeiro bloco cresce até 965 MB, a 35 MB de 1.000 (folga que não é folga). E, para qualquer G, sem a isenção o bloco 22 do filho novo (3.909 a 3.982 MB) reiniciaria de novo. A isenção é obrigatória sempre.
12. **Unidade de G.** `pico_memoria_mb` divide kB por 1.024 (`processo_malhas.py` linha 56): o "MB" do projeto é MiB. O T26 diz "1 GB = 1.000 MB" nessa unidade. G tem de ser escrito no código na mesma unidade da sonda do T24, senão o limiar muda 4,9% sem ninguém ver.
13. **Cartão T29, "o filho (ou o pai, na R-A) manda `reinicio`".** Na R-A quem decide e mata é o pai; o filho não manda nada. O reinício planejado é um **valor de retorno próprio** de `_executar`/`_rodar` (§2.2), não uma mensagem.
14. **Cartão T32:** cita `sonda_t28.py` e `rodar_t28.sh` (número antigo; agora T32); proíbe `obimcore/` mas permite `nucleo/motor.h`, que fica em `prototypes/s04/obimcore/nucleo/` (contradição; escrever caminhos completos); pede custo de desenho "em quadros por segundo" no software (só vale como comparação relativa na mesma rodada).
15. **Cartão T30:** "`viewport_qrhi` (desenho com saltos)" nos arquivos permitidos está errado: o desenho é o laço de `motor.h` linhas 287 a 291; "identidade estável por lote em `cena.*`" já existe (item 5); critério 5 pede p95 < 200 ms no sintético de 285 MiB, mas milissegundos de software não valem: o sintético só dá contadores em tela virtual, e os milissegundos dele pedem a placa (pergunta 2 ao PO).
16. **T25 §3, hipótese do limite de 4 ms cortando o 1º quadro.** Outra hipótese pelo código: o relógio de 4 ms começa antes do laço (`motor.h` linha 204) e inclui o `create()` dos buffers do lote (linhas 211 a 213); criar um buffer de dezenas de MiB pode passar de 4 ms. E `uploadStaticBuffer` só enfileira (a cópia real para a placa acontece no `beginPass`/`endFrame`; a conferir na documentação do Qt), então o limite de 4 ms mede o enfileirar, não o envio. Teste: T32a, tempo de `create()` e de enfileirar por quadro.
17. **Conferências que bateram (T26).** Tabela D: piores reais 0,57; 0,87; 1,27; 1,77 s (de 0,47/0,49/0,57; 0,87/0,79/0,87; 1,17/1,09/1,27; 1,47/1,49/1,77); 52,74 + perdido = 53,31; 53,61; 54,01; 54,51; + 3,79 = 57,10; 57,40; 57,80; 58,30. Maior bloco leve 340 MB (virtual `rb250_r2`), 333 na real; folga de 4,97 s no silêncio (20 − 15,03). Tudo confere.

## 2. Item 1: T29, regra R-A, G, matar no meio do bloco e oráculo

### 2.1 Valor de G (opções e recomendação)
**O que os números permitem afirmar (T26, medido nos dados do T24, uma máquina, um arquivo):** 0 reinícios falsos com G de 0,5 a 2,0 GB em 12 aberturas; maior bloco leve 340 MB; bloco 22 num filho já usado cresce 3.295 a 3.416 MB; tempo até cruzar G no pior real 0,57 (0,5 GB), 0,87 (1,0), 1,27 (1,5), 1,77 s (2,0). **Não permitem afirmar:** nada sobre o simples, o detalhado e o 25 MB com bloco 250 no carregador (nenhum crescimento de bloco medido neles), nada sobre o Windows, nada sobre matar no meio do bloco.

**Conta do filho morto (estimativa, corrige o T26 §6.2):** começo do bloco 22 até 1.948 MB (real `n250_r3`) + G + o que cresce entre a amostra e a morte. Com a leitura a cada 50 ms (`FATIA_S`), mais o atraso da morte (hipótese: até cerca de 0,1 s), a 1,7 a 2,5 GB/s: cerca de 0,25 a 0,4 GB. Para G = 1,0 GB: cerca de 1.948 + 1.000 + 400 ≈ **3,35 GB**, contra 4.302 a 4.391 MB do filho novo no fim do bloco 22 (real, `rb250`) e 4,9 GB de pico. Como os filhos andam em sequência, o maior filho continua sendo o novo: **G até cerca de 2 GB não toca a folga de 106 MB** (estimativa; a medida oficial confirma).

**Critério:** (a) margem contra reinício falso, que importa mais do que parece, porque só há **1 reinício** por abertura: um reinício falso num bloco médio gasta o único reinício, e um bloco pesado depois passa sem proteção; (b) tempo perdido; (c) folga da memória (G ≤ 2 GB não a afeta, acima).

| opção | margem sobre o maior bloco leve (340 MB) | perdido, pior real | abrir, pior estimado (52,74 + perdido) | leitura |
|---|---|---|---|---|
| **G1: fixo 1.000 MB (recomendada)** | 660 MB (2,9 vezes) | 0,87 s | 53,61 s (folga 6,4 s) | equilíbrio |
| G2: fixo 500 MB | 160 MB (1,5 vezes) | 0,57 s | 53,31 s | ganha 0,3 s e fica frágil em arquivo não medido |
| G3: dependente (por exemplo, memória atual do filho acima de um valor fixo, ou G = k × maior bloco leve já visto no arquivo) | não simulada | não simulada | não simulada | não vale agora: o R-0 não a testou; refazer a simulação antes |

G = 1,5 ou 2,0 GB também passam, mas compram margem que nenhum dado pede, ao custo de 0,4 a 0,9 s. **Recomendação: G fixo de 1.000 MB**, na unidade de `pico_memoria_mb` (kB ÷ 1.024; §1 item 12), **com isenção do primeiro bloco de cada filho** (obrigatória para qualquer G, §1 item 11). Se a medida oficial mostrar, no simples, no detalhado ou no 25 MB, um bloco que não é o primeiro crescendo mais de 500 MB, parar e levar ao Opus antes de mexer em G.

### 2.2 Especificação da R-A (para o cartão; pelo código citado)
1. **Bloco padrão 250**: `carregador.py` linha 134 (A25).
2. **Leitura da memória atual do filho, a cada `FATIA_S` (50 ms):** Linux, `VmRSS` de `/proc/<pid>/status` (a mesma fonte do campo usado no T26; `pico_memoria_mb` não serve, ele devolve `VmHWM`). Windows, pelo desenho: `WorkingSetSize` da mesma estrutura PMC de `pico_memoria_mb` (linha 39), coerente com a conta A (`PeakWorkingSetSize`); o sistema pode cortar o conjunto de trabalho e enganar a regra (T28 mede).
3. **Referência do começo do bloco dada pelo filho.** Hoje o pai lê as mensagens dentro de `_executar` e, ao receber um `lote`, fica preso em `_colocar` (linha 237) enquanto a fila de 4 está cheia: nesse tempo **não lê o canal nem a memória**. Se a referência fosse a leitura do pai ao receber `convertendo`, ela poderia chegar atrasada, com o filho já crescido. Especificação: logo depois de `("fase", "convertendo")` (`processo_malhas.py` linha 230) o filho manda uma mensagem nova `("bloco", {"rss_mb": x})` com a própria memória atual (`/proc/self/status`; no Windows, `GetCurrentProcess`). A mensagem `fase` não muda (o pai conta blocos por ela, linha 495). E a leitura da memória do filho também roda **dentro da espera de `_colocar`**, para a vigia não ficar cega.
4. **Armar e desarmar.** A vigia arma ao receber `bloco` quando `self._conv ≥ 2` (não é o primeiro bloco deste filho; `_conv` zera em cada `_rodar`, linha 368) e só no modo normal (`isolado` falso). Desarma no primeiro `lote`, `sem_malha` ou `fim` depois dele. **Por que isso basta (pelo código):** no modo normal, os lotes e o `sem_malha` de um bloco só saem depois do bloco (linhas 231 a 235), e o canal é ordenado; quando o pai lê `convertendo` do bloco k, já leu tudo dos blocos anteriores. Entre `convertendo` k e o primeiro `lote` de k só chegam `feitos` (linha 272). Depois que o bloco começa a emitir, o pico já passou e matar não ajuda.
5. **Decisão.** Armada, se `rss_atual − rss_mb ≥ G`, e se ainda não houve reinício nesta abertura: o pai **para de ler o canal**, mata o filho e devolve de `_executar` um valor próprio, por exemplo `{"motivo": "reinicio", "seg": ...}`. Tudo o que estiver no canal depois da decisão é descartado (só `feitos` do bloco k, ou, numa corrida no fim do bloco, lotes de k que não foram contados): nada disso entrou em `est["resolvidos"]`, então volta ao filho novo sem duplicata. Se já houve 1 reinício, registra "reinício pedido e não feito (bloco k)" nas mensagens do resumo e segue.
6. **Caminho próprio em `_ler`.** O retorno `reinicio` é tratado **antes** do bloco de falhas (linhas 320 em diante) e fora da rede de segurança das linhas 312 a 319 (que mandaria as pendentes para `sem_malha` com "o conversor não devolveu a peça"). Não mexe em `espera`, `seguidos`, `acusadas` nem `iso`; não entra no modo isolado. O filho seguinte recebe os ids não resolvidos (em ordem) e o mesmo `est["desl"]`. Como nada do bloco k foi resolvido, a lista começa na fronteira do bloco k e a divisão em blocos de 250 continua a mesma.
7. **Esperar o filho morto sair.** Hoje o `finally` faz `kill()` e `join(2)` (linhas 427 a 429): se o `join` estourar, o filho seguinte nasceria com o anterior ainda vivo. No reinício planejado, o pai só cria o filho seguinte com `exitcode` definido (espera em passos de `FATIA_S`, conferindo o cancelamento). O pico do filho morto já é lido no `finally` antes do `kill` (linha 422) e entra em `pico_filho`.
8. **Resumo.** `est["msgs"]` passa a juntar (hoje a linha 528 sobrescreve), `tempos` continuam somados (526 e 527), e o resumo ganha: número de filhos, bloco do reinício, tempo até a decisão, tempo da morte até a saída. O filho morto não manda `fim`, então os tempos dele (abrir, listar, parte da geometria) entram como "perdido_s", medido pelo pai.
9. **Vigia de 20 s.** A morte planejada nunca conta como "limite" nem como "queda". O filho novo começa com `_fase` vazia, então vale `limite_abrir_s` (600 s) enquanto abre e lista (linha 371), e o relógio do silêncio nasce de novo (linha 395). `limite_peca_s` não muda.
10. **Cancelar no meio do reinício.** Pelo código, `_checar` antes de `filho.start()` (linha 392) e a cada volta do laço (397) já cobre: cancelado entre a morte e o filho novo, nenhum filho nasce; cancelado durante o filho novo, o `finally` o mata. O oráculo confere.
11. **Ganchos novos (só valem com a variável):**
    - `OBIM_TESTE_REINICIO_BLOCO="k1[,k2]"` no **pai**: força a decisão no bloco de número global k (contando os `convertendo` de todos os filhos da abertura), se não for o primeiro bloco do filho (senão registra e ignora). Com 2 valores, o teto sobe para 2 **só neste teste**, para cobrir dois reinícios seguidos (o caso do `sem_malha` silencioso).
    - `OBIM_TESTE_CRESCER_MB="<guid>=<mb>"` no **filho**: ao converter essa peça, aloca e **escreve** `mb` (por exemplo, `numpy.ones`) e guarda até o fim do bloco. Exercita o caminho real (leitura da memória, G, isenção), que o gancho forçado não exercita. Memória alocada sem escrita não aparece na memória residente.
12. Classe **T3**. Risco: médio a alto (morte de processo, corrida com o canal, vigia).

### 2.3 Matar o filho no meio do bloco: riscos
| risco | o que o código mostra | tratamento |
|---|---|---|
| peças já entregues e não entregues | nada do bloco k foi entregue antes da decisão (§2.2 item 4) | ids = não resolvidos; sem duplicata |
| ids e `desl` | `desl` vem de `est["desl"]` (linha 509); o reinício nunca é no 1º bloco do 1º filho, mas o bloco 1 pode não ter dado nenhum lote | se `desl` for vazio, o filho novo calcula o seu (linha 187), como hoje; oráculo cobre |
| mensagens em voo | só `feitos` de k; numa corrida, lotes de k não contados | parar de ler e descartar (§2.2 item 5) |
| `espera`, `seguidos`, `acusadas`, `iso` | a rede das linhas 312 a 319 e o bloco das linhas 320 a 352 tratariam como falha | caminho próprio (§2.2 item 6) |
| vigia de 20 s | relógio por filho (linha 395) | a morte não é "limite"; o filho novo começa zerado |
| cancelar no meio | `_checar` (linhas 392 e 397) | oráculo |
| dois filhos vivos | `join(2)` pode estourar | esperar `exitcode` (§2.2 item 7) |
| conta A | o filho morto fica em cerca de 3,35 GB (estimativa §2.1), abaixo do novo | medir; os picos de cada filho entram no resumo |
| contrapressão da fila | pai cego em `_colocar` | referência dada pelo filho e leitura dentro da espera (§2.2 item 3) |
| filho preso no meio de `send` | só `feitos` (pequenos) durante o bloco; o canal é de mão única | `kill` resolve; nada do canal é lido depois |
| Windows | `TerminateProcess`; `spawn` reimporta o Python e o IfcOpenShell; conjunto de trabalho cortável | só pelo desenho; T28 mede |
| o que chega depois da decisão | descartado | o oráculo prova que nenhuma peça some nem duplica |

**Conta A (estimativa):** pai (cerca de 1.047 MB na tela virtual, T24 §2) + maior filho = o novo (4,9 GB), como no `rb250`. **Tempo (estimativa):** `rb250` + tempo até a decisão (0,87 s no pior real) + morte e saída (não medido; hipótese: menos de 0,2 s) − o `fim` do filho velho que deixa de existir.

### 2.4 Oráculo do T29b (Opus especifica aqui; outro sonnet escreve; o implementador não toca)
1. **Forma canônica por peça (`id_step`), comparação exata:**
   - juntar **todos os pedaços** da mesma peça em todos os lotes (`_dividir`, `processo_malhas.py` linhas 66 a 77, parte peça grande em vários pedaços com o mesmo id);
   - cada triângulo vira um trio de vértices (posição, normal e cor, em bits exatos do float32 e do uint8), **girado** para começar no menor vértice, **sem trocar a ordem** (mantém o sentido da face);
   - ordenar a lista de triângulos; comparar exato.
   - Também exatos: triângulos e vértices por peça; caixa da peça (mín e máx de todos os pedaços); `desl` igual nos dois lados; `sem_malha` (ids e motivos), `simplificadas`, `produtos_total`, peças com malha, triângulos totais. **Não compara:** número e ordem dos lotes, `hash_fluxo`.
2. **Controle primeiro:** normal contra normal (duas aberturas do produto de hoje, mesmos fios). Se a forma canônica exata falhar aí, quem escreve o oráculo **para e reporta** com a causa medida. Tolerância só com causa medida e aprovação do revisor Opus.
3. **Casos (IFC públicos e sintéticos, no CI Linux e Windows):**
   - reinício forçado (`OBIM_TESTE_REINICIO_BLOCO=k`) contra normal;
   - reinício pelo caminho real (`OBIM_TESTE_CRESCER_MB` numa peça de um bloco que não é o primeiro): reinicia uma vez, no bloco certo;
   - `OBIM_TESTE_CRESCER_MB` no primeiro bloco do filho: **não** reinicia (isenção);
   - dois reinícios (`k1,k2`): nenhuma peça em `sem_malha` com "o conversor não devolveu a peça";
   - segundo reinício pedido com o teto padrão: registrado, não feito;
   - cancelar entre a morte e o filho novo, e durante o filho novo: estado "cancelado", nenhum filho vivo depois de `aguardar`;
   - `OBIM_TESTE_MATAR_FILHO` e `OBIM_TESTE_PECA_LENTA` numa peça do bloco refeito: caminho de queda e de limite de hoje, sem mudança;
   - fila cheia (consumidor lento) durante o bloco vigiado: a regra ainda dispara;
   - 0 instantes com dois filhos vivos (pelo registro de criação e saída de cada filho);
   - valores padrão de `limite_peca_s` (20), `limite_abrir_s` (600), `max_pecas_condenadas` (20), `max_espera_s` (120) e `tamanho_bloco` (250) conferidos na assinatura;
   - resumo: mensagens juntadas, tempos somados, número de filhos;
   - modo isolado: a vigia nunca arma.
4. **Mesmos fios dos dois lados.** O passe de 1 fio do T21 não é referência.
5. **Na máquina do PO (com ok e horário):** comparação por peça no pesado, novo contra `n1000` e contra `n250`; 0 peças no modo isolado.
6. Tamanho: 250 a 350 linhas, em `tests/` (arquivos novos). Classe T3 (oráculo).

### 2.5 Teste barato antes de investir
1. **Sintético em tela virtual (sem o PO):** os casos do oráculo com `OBIM_TESTE_CRESCER_MB` provam a mecânica da morte no meio do bloco. Custo: o próprio oráculo.
2. **R-0b (custo zero, opcional):** rodar de novo o script do T26 com três ajustes: leitura em passos de 50 ms, atraso de 0,1 s até a morte e o pico do filho morto. Responde a §2.1 com número em vez de estimativa. Usa a mesma liberação da A27.
3. **Pesado em tela virtual, 1 a 3 aberturas, com a R-A implementada (ok e horário do PO, pergunta 1):** mede o que só o arquivo real mostra: custo da morte no meio do bloco, pico do filho morto, tempo até a decisão, contagens iguais. Tela virtual não prova meta: só diz se vale chamar a sessão na placa.

### 2.6 Medida oficial futura (placa real; Windows à parte, T28)
Registrar, por abertura (5 do pesado, A28; 3 do simples, do detalhado e do 25 MB, intercaladas):
- conta A e conta B, pico do pai, pico de **cada** filho (inclusive o morto), número de filhos, 0 instantes com dois filhos vivos;
- abrir_s e a decomposição: até a decisão, da morte até a saída, do filho novo até a primeira mensagem;
- bloco do reinício e se foi o certo (pesado: o das 3 peças); reinícios pedidos e não feitos;
- **crescimento máximo de cada bloco que não é o primeiro do filho**, nos 4 arquivos (é o dado que confirma ou derruba a margem de G fora do pesado);
- maior silêncio por bloco, do filho velho antes da morte e do novo;
- memória de referência do bloco dada pelo filho e lida pelo pai (devem bater em ±50 MB);
- contagens, `sem_malha`, `simplificadas`, peças no modo isolado (0);
- M5 durante a abertura;
- pior rodada ao lado da meta; simples e detalhado comparados com o bloco 1.000 (não podem piorar, A25).
- **Windows (T28):** `PeakWorkingSetSize` do pai e de cada filho, `WorkingSetSize` lido pela regra, custo do reinício, se a regra dispara no mesmo bloco do Linux, oráculo por peça Windows contra Windows.

### 2.7 Classe, risco e o que não vale
- Classe **T3** (implementação e oráculo); revisão Opus em lote, as duas juntas.
- **Não vale:** memória que sobrou antes do bloco (refutada pelo T26, tabela E); posição fixa; menos fios; isolar a peça pesada; G escolhido por arquivo; mais de 1 reinício no produto; contar a mediana, a tela virtual ou 3 aberturas como prova (A28); usar `pico_memoria_mb` (pico) como memória atual; tratar o reinício como queda ou limite; mexer em `limite_peca_s`, `max_espera_s` ou nos fios.

## 3. Item 2: troca de geometria, o que o código mostra, e o T32

### 3.1 Onde a troca reenvia a cena inteira (pelo código)
- `cena.cpp` linha 104: em `atualizar`, todo lote que tem uma peça a remover é refeito por `sem` (cópia nova, fora do mutex). O resultado entra no **mesmo lugar** da fila e com a **mesma sequência** (linha 40).
- `cena.cpp` linha 110: `if (mudou) { ++ger_; recalcular_caixa(); }`. **Basta um lote ter perdido uma peça para a geração subir.** Criar (peça nova sem igual na cena) não sobe a geração (linha 111), por isso dá 2 quadros.
- `motor.h` linha 203: quando a geração muda, `enviar` limpa a placa (`g.lotes.clear()`, `tri_placa = 0`) e volta o cursor ao começo da fila. `proximo` (linhas 124 a 128) entrega todos os lotes de novo, a partir da cópia compacta.
- Conclusão: **sim, é limpar e reenviar, disparado em `atualizar`**. A cópia compacta já fica certa na hora (sem a peça antiga, com a nova no fim, caixa recalculada); só a placa é refeita do zero. O lote 58 §3.1 estava certo sobre `motor.h` linha 203; faltava a linha 110.
- **Por que isso ajuda:** como a fila mantém posições e sequências, o motor pode descobrir sozinho **qual** lote mudou, comparando o ponteiro de cada posição com o que está na placa, sem identidade nova na cena.

### 3.2 `bytes_copia` de 844,9 M para 1.160,7 M (pelo código)
- `totais()` soma a **capacidade** dos vetores, não o tamanho (`cena.cpp` linha 139).
- `sem` monta o lote refeito com `insert` de 28 bytes por vértice e `push_back` por índice, **sem reservar** (linhas 41 e 42). Na biblioteca padrão do GCC, cada vetor dobra ao crescer (capacidade = 28 × 2^n bytes para os vértices; 2^n índices), então sobra de 0 a quase 100% do tamanho.
- Conta: a subida foi de 315.806.861 bytes; os 4 lotes tocados somam 405.631.008 bytes (9.405.696 + 25.417.440 + 71.586.240 + 299.221.632). A sobra cabe no intervalo possível (0 a 405,6 MB). Os lotes novos vêm de `preparar` (`assign` e `resize`, sem sobra), e os lotes que viram vazios liberam quase nada.
- **Causa pelo código, com teste exato:** no T32a, calcular a capacidade prevista de cada lote tocado pelos números de vértices e índices dele (dobra do GCC) e comparar com a subida medida (deve bater à parte da tabela de objetos e dos textos dos ids). No Windows (MSVC, que cresce 1,5 vez) a sobra é outra.
- **Consequência:** a cópia compacta do pai cresce até o dobro dos lotes tocados numa sessão de edição. O conserto (reservar o tamanho exato) entra no T30a e não muda limite nenhum. Se algum teste existente conferir `bytes_copia` por igualdade, ele não pode ser afrouxado: o caso vai ao revisor.

### 3.3 O que muda para as opções do T30
Base comum, agora pelo código: (a) `atualizar` deixa de subir `ger_` quando só troca lotes (linha 110; `limpar()` continua subindo); (b) a cena expõe um **instantâneo** (ponteiros dos lotes, geração e versão, tirados juntos sob `DadosCena::m_`, como `proximo`); (c) o motor guarda, por posição, o `Dados` que está na placa e compara com o instantâneo quando a versão muda; (d) lote trocado é reenviado **atrás** de qualquer lote novo e entra na placa **só completo** (o antigo segue desenhado até lá); (e) perda de contexto e `limpar()` reenviam tudo, como hoje. Nenhuma trava nova: o motor só chama a cena sem segurar `Motor::m_` (como `enviar` faz hoje) e não toca `mc_`. A ordem `Motor::m_` → `DadosCena::m_` → `mc_` fica.

**Opção T-1: 2-G no motor, sobre a cópia compacta que `atualizar` já refaz (recomendada, condicionada ao T32).**
- O que muda: base comum + faixas visíveis por posição na placa. A faixa escondida é calculada pelo motor: peças do `Dados` que está na placa e que não estão mais no `Dados` novo da mesma posição (pelos ids). O desenho daquela posição vira várias chamadas `drawIndexed(contagem, 1, primeiro_índice)` (parte pública do QRhi; a conferir no OpenGL ES e no D3D11). As faixas de um instantâneo com sequência S só valem **no quadro em que a sequência da placa chega a S** (o lote novo, de 1 KB, completo): nenhum quadro com S mostra as duas paredes nem nenhuma. Apagar (lote vazio no fim) fica em 1 a 2 quadros. Quando o reenvio do lote trocado termina, troca-se o buffer e as faixas somem. Troca repetida no mesmo lote antes disso: as faixas são recalculadas contra o que está na placa e o reenvio recomeça com o ponteiro mais novo. Mais o conserto de `sem` (reservar, copiar trechos contínuos, criar `morto` só para lote tocado).
- Números (estimativa): quadros = os de "criar" (2); M2b ≈ 2 quadros + parte do comando + **tempo de `atualizar`**. Com `sem` de hoje, cerca de 85 / 170 / 330 a 520 ms nos lotes de 24 / 68 / 285 MiB (§1 item 7, hipótese). Com `sem` consertado, depende do T32a (estimativa grosseira, se ficar perto de cópia de memória: dezenas de ms no lote de 285 MiB). Reenvio do lote trocado: teto(lote ÷ 2 MiB) quadros em segundo plano, cena inteira visível.
- O que os números permitem afirmar: a cena não some e o envio da troca não cresce com o lote. **Não permitem:** o tempo de `sem` (não medido), o custo das chamadas com salto, a memória durante o reenvio (lote antigo em memória e na placa mais o novo: +285 MiB no pior, por cerca de 2,4 s; no software e no WARP isso é memória do sistema).
- Classe T3. Risco: médio (estado por posição, ordem de quadros). Seleção e caixa já usam a cópia compacta certa (`lotes()`, linha 42 de `cena.h`; `recalcular_caixa`); continuam como hoje.

**Opção T-2: 2-A com teto de lote C dentro da cena.**
- O que muda: base comum + `adicionar_lote` parte o lote em sub-lotes de até C MiB na fronteira de peça (renumerando como `sem`, que não supõe vértices próprios por peça, linha 30). Sem salto no desenho.
- Números (estimativa, lote 58 §3.3): C = 2 MiB, cerca de 75 ms; C = 8 MiB, cerca de 125 ms; mais o tempo de `sem`, **que agora fica limitado a um sub-lote de C** (vantagem real sobre a T-1 sem conserto). Lotes: 13 → pelo menos 403 (C = 2) ou 101 (C = 8) no detalhado, o mesmo número de chamadas por quadro.
- Não permitem afirmar: o custo de centenas de chamadas por quadro no software e no WARP, o efeito no M5. Risco extra: uma chamada a `adicionar_lote` passa a gerar várias sequências, e a ponte usa `lote(seq)` para montar a tabela de objetos (ponte não lida). Classe T3.

**Opção T-3: 2-G com compactação adiada (só se o `sem` consertado ainda for lento).**
- O que muda: `atualizar` só marca as peças removidas como escondidas e devolve a sequência; `sem` roda depois, numa thread da cena. Seleção, caixa, `totais`, `lote(seq)` e perda de contexto passam a respeitar as escondidas até a compactação.
- Números: tira `sem` do caminho do M2b. Risco alto (mais estado, mais uma thread, mais pontos de erro na seleção). Classe T3. Só entra se o T32a mostrar que o `sem` consertado passa de cerca de 100 ms no lote de 285 MiB.

**Não vale:** reenvio incremental sozinho, sem salto e sem teto (é a 2-A pura: cerca de 250 ms no lote de 24 MiB, 600 ms no de 68 MiB, 2,4 s no de 285 MiB, mais `sem`); deixar a sequência avançar com a parede antiga ainda desenhada; subir o orçamento (2-B, A31); mexer em `fluxo_a.py` (A29); variante por índices sem antes o salto no desenho falhar.

**Recomendação do item 2:** T32a primeiro (mede, não muda comportamento). Se o `sem` consertado ficar abaixo de cerca de 50 ms no lote de 285 MiB e o salto funcionar no OpenGL em software (T32b), seguir a **T-1**. Se o `sem` consertado ficar alto, comparar T-2 (C = 8 MiB) e T-3 em novo lote Opus, com os números. A 2-G continua a melhor no envio; o que mudou é que o tempo da cópia na memória também tem de caber nos 200 ms.

### 3.4 Cartão T32 reescrito (dividido em T32a e T32b, ambos em ramo descartável)
Texto pronto na §6.2. Pontos centrais:
- **T32a (instrumentação, sem mudar comportamento):** por quadro, dentro do C++: instante de início e fim do `enviar`, bytes e pedaços por fase (vértices, índices), número e tempo de `create()`, motivo da parada (bytes, 4 ms ou fila vazia), geração e versão vistas, sequência da placa, triângulos na placa, chamadas de desenho; mais o tempo da chamada `atualizar` medido pelo Python, por lote tocado, com `sem` de hoje e com um `sem` consertado no ramo; mais a conta exata de `bytes_copia`.
- **T32b (protótipo da T-1):** base comum mínima + salto no desenho + aplicar as faixas junto com a sequência.
- Cena: a mesma do T27 (13 lotes, 805,7 MiB), tela virtual, 3 rodadas, `flock`, `uptime` por rodada.
- **Não mede:** D3D11, WARP, Windows, seleção, caixa, perda de contexto no meio da troca ou do reenvio, M5, fluxo B, placa real, milissegundos como número de placa.

### 3.5 Divisão do T30 (depois do T32; cada cartão ≤ 400 linhas, estimativa)
| cartão | o quê | linhas | depende de |
|---|---|---|---|
| T30a (cena) | `atualizar` sem subir `ger_` na troca; instantâneo com versão; `sem` consertado (reserva, trechos contínuos, `morto` só se tocado) | 120 a 200 | T32 |
| T30b (motor) | reenvio incremental por posição, fila de trocas atrás dos lotes novos, troca atômica do buffer, honestidade da sequência, perda de contexto e `limpar()` como hoje | 200 a 300 | T30a |
| T30c (motor) | faixas visíveis e salto no `drawIndexed`, aplicadas no quadro da sequência S | 100 a 150 | T30b |
| T30d (oráculo, outro agente) | lote 58 §3.9 itens 1 a 10, mais: faixas e captura no meio do reenvio iguais à captura depois de `perder_contexto()`; troca repetida no mesmo lote; apagar em ≤ 2 quadros; tempo de `atualizar` por tamanho de lote; `bytes_copia` sem sobra | 300 a 400 | em paralelo com T30a a T30c (arquivos diferentes) |
Se a escolha for T-2: T30a ganha a divisão em sub-lotes (pode passar de 400 linhas: dividir em T30a1 e T30a2) e o T30c some. Se for T-3: mais um cartão de compactação adiada (200 a 300 linhas). Classe de todos: **T3**; revisão Opus em lote.

## 4. Ordem sugerida
1. **Já e ao mesmo tempo** (arquivos diferentes, um implementador por conjunto, no máximo 2 de uma vez):
   - **T29a** (caminho do reinício e bloco 250, em `carregador.py` e `processo_malhas.py`) e **T29b** (oráculo em `tests/`, outro agente);
   - **T32a** (ramo descartável, só C++ do núcleo e a sonda nova).
2. **T29c** (regra R-A com G, em cima do T29a) e **T32b** (protótipo da T-1, depois do T32a).
3. Lote Opus de revisão do T29 (T29a, T29b e T29c juntos) e, separado ou no mesmo lote se couber, a revisão do T32 como ensaio.
4. Ensaio do pesado em tela virtual com a R-A (pergunta 1).
5. T30a → T30b → T30c, com o T30d em paralelo; revisão Opus em lote.
6. **Uma só sessão na placa** (pergunta 2): pesado 5 vezes, simples, detalhado e 25 MB (memória, abrir, M5), mais o M2b no 25 MB, no detalhado e na cena sintética.
Se nenhuma opção fechar uma meta depois dos testes: parar e levar ao PO com opções (`v2/03`).

## 5. O que registrar no LOG
"Lote opus 59 | CONCLUÍDO (TA) | T29: R-A com G fixo de 1.000 MB (unidade de `pico_memoria_mb`), isenção do 1º bloco de cada filho sempre, no máximo 1 reinício; referência do bloco dada pelo filho (mensagem `bloco`), vigia também dentro da espera da fila; arma em `convertendo` com `_conv ≥ 2` no modo normal e desarma no 1º `lote`/`sem_malha`/`fim`; retorno próprio `reinicio` fora da rede do `sem_malha`; esperar `exitcode` antes do filho novo; ganchos `OBIM_TESTE_REINICIO_BLOCO` (pai) e `OBIM_TESTE_CRESCER_MB` (filho). Dividido em T29a (caminho), T29c (regra) e T29b (oráculo por peça, juntando pedaços, triângulo girado sem trocar o sentido, controle normal contra normal). T32: troca reenvia a cena por `cena.cpp` linha 110 (`++ger_` em qualquer remoção) e `motor.h` linha 203; a cópia compacta já fica certa; `seq` estável por posição já existe (linha 40). Achado: `sem` sem reserva explica `bytes_copia` (capacidade, linha 139) e pode custar 1,0 a 1,6 ms por MiB (hipótese, T25 §10.2: +23 e +111 ms); a 2-G tem de somar o tempo de `atualizar`. T32 dividido em T32a (instrumentação, tempo de `atualizar`, `bytes_copia`) e T32b (protótipo da 2-G no motor). T30 em T30a a T30d. Contradições: T27 'modelo não vale' (entrada errada), T27 'lotes não vazios', +1 quadro (quadro em voo, hipótese), lote 58 §3.2/§3.4/§1 item 2(e), T26 §5 e §6.2, unidade de G, cartões T29/T30/T32."

## 6. Textos dos cartões prontos para colar (o líder grava)

### 6.1 Cartão T29 (substitui o rascunho)
```markdown
<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F0-S04-T29: Bloco 250 mais reinício planejado do filho (R-A), dividido em T29a, T29c e T29b
- **Status: PRONTO** (regra fechada pelo lote 59) · Classe: **T3** · Implementa: sonnet (T29a, depois T29c, o mesmo ou outro) · Oráculo: T29b, **outro sonnet**, especificado em `lotes/LOTE_OPUS_59/resultado.md` §2.4 · Revisa: **opus, em lote**, T29a + T29c + T29b juntos
- Depende de: T26, `lotes/LOTE_OPUS_58/resultado.md` §2, `lotes/LOTE_OPUS_59/resultado.md` §2, A24, A25, A27, A28. Cartão-mãe: T20.
## Objetivo
Conta A < 6.000 MB e abrir ≤ 60 s no pesado, pela **pior de 5 aberturas** na placa (A28), com bloco padrão 250 e no máximo 1 reinício planejado. Simples e detalhado não podem piorar (A25). **A meta não muda.**
## Regra escolhida
- [x] **R-A**: crescimento dentro do bloco; refazer o bloco num filho novo; no máximo 1 reinício por abertura.
- **G = 1.000 MB** fixo, na unidade de `pico_memoria_mb` (kB ÷ 1.024). **Isenção do 1º bloco de cada filho, sempre.**
- Não valem: memória que sobrou antes do bloco, posição fixa, menos fios, isolar a peça pesada, G por arquivo, mais de 1 reinício.
## T29a: caminho do reinício e bloco 250 (150 a 220 linhas)
1. `tamanho_bloco=250` em `CarregadorMalhas.__init__`.
2. `_executar` aceita um pedido de reinício: para de ler o canal, mata, **espera `exitcode`** (passos de `FATIA_S`, conferindo o cancelamento) e devolve `{"motivo": "reinicio", ...}`.
3. `_ler` trata `reinicio` antes do bloco de falhas e fora da rede das linhas 312 a 319: sem mexer em `espera`, `seguidos`, `acusadas`, `iso`; filho novo com os ids não resolvidos e o mesmo `desl`; filhos em estrita sequência.
4. Resumo: mensagens juntadas (não sobrescrever), tempos somados, número de filhos, bloco do reinício, `perdido_s`; 2º reinício pedido = registrado e não feito.
5. Gancho `OBIM_TESTE_REINICIO_BLOCO="k1[,k2]"` no pai (bloco global; ignorado no 1º bloco do filho; com 2 valores o teto vai a 2 só no teste).
## T29c: regra R-A (120 a 180 linhas)
1. Filho: depois de `("fase", "convertendo")`, manda `("bloco", {"rss_mb": x})` com a própria memória atual (Linux `/proc/self/status` VmRSS; Windows `WorkingSetSize`).
2. Pai: lê a memória atual do filho a cada `FATIA_S`, também dentro da espera de `_colocar`; arma ao receber `bloco` com `_conv ≥ 2` e modo normal; desarma no 1º `lote`, `sem_malha` ou `fim`; dispara se crescer ≥ G e ainda não houve reinício.
3. Gancho `OBIM_TESTE_CRESCER_MB="<guid>=<mb>"` no filho (aloca e escreve; guarda até o fim do bloco).
## Critérios de aceite
1. Oráculo T29b (§2.4 do lote 59) verde, com o controle normal contra normal passando antes.
2. 0 instantes com dois filhos vivos; limites padrão intactos (`limite_peca_s` 20, `limite_abrir_s` 600, `max_pecas_condenadas` 20, `max_espera_s` 120); morte planejada nunca vira "limite" nem "queda".
3. Mesmos fios dos dois lados; 0 peças no modo isolado no pesado.
4. CI `linux` e `windows` verdes.
5. Ensaio do pesado em tela virtual (ok e horário do PO): reinicia 1 vez, no bloco das 3 peças pesadas; contagens iguais ao `n250`.
6. Medida oficial (cartão T2 à parte, ok e horário do PO): lista do lote 59 §2.6, 5 aberturas do pesado, a pior ao lado da meta.
7. Revisão Opus em lote; sem "aprovado provisoriamente".
## Arquivos permitidos
T29a e T29c: `prototypes/viewport_qrhi/carregador.py`, `prototypes/viewport_qrhi/processo_malhas.py`, este cartão, `docs/state/LOG.md`, `docs/state/BOARD.md`. T29b: arquivos **novos** em `tests/` (só o agente do oráculo). **Proibido:** `fluxo_a.py`, `lote.py`, tudo em `prototypes/s04/obimcore/`, limites e metas, testes de oráculo existentes, `QUOTA.md`, IFC do PO no repositório.
## Armadilhas
Pai cego enquanto a fila está cheia; `pico_memoria_mb` é pico, não atual; `join(2)` pode estourar; rede de segurança do `sem_malha`; 1º bloco do filho cresce até 965 MB (isenção); unidade de G; conjunto de trabalho do Windows cortável (T28).
## Fora de escopo
Soltar malhas do bloco aos poucos; bloco menor no 1º bloco do filho novo; G dependente; Windows físico (T28).
## Próximo passo
Abrir T29a e T29b ao mesmo tempo (arquivos diferentes); T29c depois do T29a.
```

### 6.2 Cartão T32 (substitui o atual)
```markdown
<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F0-S04-T32: G-0b em duas partes: T32a (instrumentação e tempo de `atualizar`) e T32b (protótipo da 2-G no motor)
- **Status: PRONTO** · Classe: **T3** (C++ do núcleo; ramo descartável `s04-g0b-descartavel`, nunca vai ao `main`, sem PR de código) · Tamanho: T32a 120 a 200 linhas, T32b 150 a 250 · Implementa: sonnet · Oráculo: critérios abaixo (lote 59 §3); a conferência dos números por `jq` é feita por **outro agente**, não pelo implementador · Revisa: opus, em lote, como ensaio
- Depende de: T27 (cena e linha de base), `lotes/LOTE_OPUS_59/resultado.md` §1 e §3, A26, A29, A31. Alimenta: T30.
## T32a: instrumentação, sem mudar comportamento
Por quadro, dentro do C++ (anel próprio, lido depois da medida): índice; início e fim do `enviar`; bytes e pedaços por fase (vértices, índices); número e tempo de `create()`; motivo da parada (2 MiB, 4 ms, fila vazia); geração e versão vistas; sequência da placa; triângulos na placa; chamadas de desenho. Pelo Python: tempo da chamada `atualizar` por lote tocado (1 KB, 8,97, 24,24, 68,27, 285,36 MiB), com o `sem` de hoje e com um `sem` consertado só no ramo (reserva exata, cópia de trechos contínuos, `morto` só se o lote for tocado).
Critérios:
1. Bytes enviados por troca hoje = bytes de vértices e índices da cena (exato) em 45 de 45 trocas.
2. "+1 quadro": o 1º quadro contado tem 0 bytes da troca (quadro em voo) nas trocas de 404; nas de 403 não há esse quadro. Se não for assim, o relatório diz o que é, sem ajustar.
3. Pedaços por quadro separados por fase; o quadro de mais pedaços é o que atravessa os lotes pequenos do fim (ou o relatório mostra outra causa).
4. `bytes_copia`: subida prevista pela capacidade dos vetores (dobra do GCC, pelos vértices e índices de cada lote tocado) contra a medida (315.806.861 bytes no T27); com o `sem` consertado, subida só dos lotes novos.
5. Tabela do tempo de `atualizar` por lote tocado, hoje e consertado, mediana e pior de 9 por caso, com `uptime`. Vale como CPU desta máquina, não como número de placa.
6. Tempo de `create()` por quadro (hipótese do 4 ms do T25 §3).
## T32b: protótipo da opção T-1 (lote 59 §3.3)
`atualizar` sem subir `ger_` na troca; instantâneo (ponteiros, geração, versão); motor compara por posição; reenvio do lote trocado atrás dos novos e troca do buffer só completo; faixas visíveis calculadas pelos ids e desenhadas com `drawIndexed(contagem, 1, primeiro_índice)`; faixas valem no quadro em que a sequência da placa chega à do comando.
Critérios:
1. Quadros da troca = quadros de "criar" (mediana 2; nunca mais que criar + 1) nos 5 lotes tocados, 3 rodadas; tabela com "criar" e "apagar" como piso.
2. Em **todos** os quadros da troca e do reenvio: `triangulos_na_placa` ≥ triângulos da cena − triângulos da peça antiga.
3. No quadro com a sequência do comando, captura sem a parede antiga e com a nova (cor própria na parede de teste).
4. Captura no meio do reenvio (salto ativo) e depois dele **iguais pixel a pixel** à captura depois de `perder_contexto()`, mesma câmera. Se diferir, o relatório diz por quê; não afrouxa.
5. OpenGL em software aceita o `drawIndexed` com primeiro índice: aceita / não aceita, com a mensagem (`info()` sem "ERRO" e critério 4). Se não aceitar: 2-G falha no software; apontar T-2 e a variante por índices.
6. Bytes por troca: só o lote novo antes da sequência do comando; o lote trocado depois. Troca repetida no mesmo lote durante o reenvio: critérios 2 a 4 continuam.
7. Chamadas de desenho por quadro com 1, 10 e 100 peças escondidas num lote; tempo de quadro só como comparação relativa na mesma rodada.
8. Ordem das travas: nenhuma trava nova; o motor chama a cena sem segurar `Motor::m_`; `mc_` intocado (o revisor confere no diff).
## Relatório
`docs/state/reports/F0-S04-T32.md`: COMPLETO ou não, resumo de 5 linhas, tabelas, hash do commit medido, números conferidos por outro agente, recomendação sem escolher.
## Arquivos permitidos
No ramo descartável: `prototypes/s04/obimcore/nucleo/motor.h`, `prototypes/s04/obimcore/nucleo/cena.h`, `prototypes/s04/obimcore/nucleo/cena.cpp`, `motor.cpp` (mesma pasta, se precisar) e o arquivo da ponte (`ponte_viewport.cpp`, caminho a confirmar pelo líder), só para expor o anel de instrumentação; novos `prototypes/s04/sondas/sonda_t32.py` e `prototypes/s04/sondas/rodar_t32.sh`. No `main` (PR de documentação): o relatório, este cartão, `docs/state/LOG.md`, `docs/state/BOARD.md`. **Proibido:** qualquer outro arquivo de `prototypes/s04/obimcore/`, `fluxo_a.py`, `lote.py`, `medir_s04.py`, o juiz, `ORCAMENTO_BYTES`, `ORCAMENTO_TEMPO`, `OBIM_QUADRO_MS`, testes de oráculo, `QUOTA.md`, IFC do PO.
## Regras
Tela virtual; `flock ~/openbim-medicao/medicao.lock`; saídas em `~/openbim-medicao/<data>-T32/`; cena sintética do T27; 3 rodadas. Fatia de 28 bytes: relatar, não consertar.
## Não medido (marcar "não coberto" para o T30)
D3D11, WARP, Windows, seleção, caixa, perda de contexto no meio da troca ou do reenvio, M5, fluxo B, placa real, milissegundos de quadro como número de placa, compactação adiada.
## Próximo passo
T32a já (pode rodar junto com o T29a/T29b). T32b depois do T32a. Se o `sem` consertado passar de cerca de 100 ms no lote de 285 MiB, parar depois do T32a e levar ao Opus (T-2 contra T-3).
```

## 7. Perguntas ao PO (só o que é dele)
1. **Libera o arquivo pesado, em tela virtual, para 1 a 3 aberturas de ensaio da regra nova, antes da sessão na placa?** Serve para ver se a morte do processo no meio da parte pesada se comporta como a simulação; não prova a meta. Cerca de 5 a 10 minutos de máquina. **Recomendação:** sim; e qual horário?
2. **Na sessão na placa, inclui também a troca de parede numa cena de teste (sem arquivo seu), com pedaços de até 285 MB?** É o único jeito de ter o tempo em milissegundos do pior caso; na tela virtual só dá para contar quadros. Soma cerca de 10 minutos à sessão. **Recomendação:** sim.
3. **Horário da sessão na placa**, quando o líder avisar que a implementação passou na revisão (pesado 5 vezes, simples, detalhado, 25 MB e a troca de parede).

(G e a escolha da opção da troca o PO já deixou para o líder seguir a recomendação: não são perguntas.)
