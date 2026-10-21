<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# ADR-004: Processos, threads e trava do modelo
- Status: perguntas 1 a 3 **decididas pelo PO** (2026-10-15, no chat do projeto: "Aprovar tudo"; opções 1C, 2C e 3C). Pergunta 4 (§5.1, em que thread roda um comando longo): **direção do PO** (2026-10-21, "forma mista"), **condicionada ao cartão de validação V1** (§5.1); texto da atualização de 2026-10-21 aprovado pelo PO no mesmo dia (resumo de 5 linhas). Os números N1 a N4 **seguem sem medida** (§2). Não passa a "aceito" antes do V1 e dessa aprovação.
- Autor: opus (cartão F0-RG-01, TA) · Data: 2026-10-15
- **Atualização de 2026-10-21 (opus, lote 68, cartão F0-S04-T19):** números da S04 em §2; pergunta 4 nova (§5.1); mapa do §6, consequências (§7), decisão (§8), gatilhos (§9) e "não verificado" (§10) revistos; o que deixa de valer em §11. Fontes novas: `reports/F0-S04.md`, `F0-S04-threads.md`, `F0-S04-T15f-diagnostico.md`, `T21`, `T24`, `T29-placa-memoria` (e `-2`), `T29e-ensaio`, `T30-placa`; lotes Opus 57, 62, 65, 66; `fluxo_a/CONTRATO.md` (T15).

## Resumo da atualização de 2026-10-21 para o PO (5 linhas)
1. Sua ideia mista tem metade comprovada: mandar o cálculo de uma peça pesada para uma linha de trabalho à parte deixou o mouse livre nas três máquinas medidas (até 16 milésimos de segundo, contra 200 a 250 quando o cálculo roda na janela).
2. A outra metade só se comprova em parte: picar os comandos longos na janela foi melhor na sua placa de vídeo, pior no Windows e dividido no Linux sem placa, na maior parada da janela; e tem um piso, uma única operação de cerca de 0,7 segundo que não dá para picar.
3. As duas juntas nunca foram medidas; por isso a forma mista entra como direção, com um cartão de validação que mede a mistura com as mesmas réguas de antes.
4. Se a validação falhar, a escolha volta a você com as duas formas puras e o custo de cada uma (tudo na linha à parte já deixou a janela parada mais de 1 segundo na sua placa quando havia outra linha de trabalho em Python ao lado).
5. A abertura do arquivo pesado continua num processo separado, que agora reinicia sozinho uma vez no meio para caber nos 6 gigabytes.

## Resumo para o PO (5 linhas, 2026-10-15)
- Base: relatório `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achados A2, A3, B1, B13); lotes Opus 6 (D3, D4), 9 (§1.4, regras 1 a 8), 10 (mutex, regra 9, T04b); `v2/02 §5`; `v2/03` (S03 e S04, lista de ADRs).
- Escopo: o tema "Threads (UI, geometria, I/O, GIL)" da lista de ADRs de `v2/03 §3`. Não decide a stack (ADR-001, depois das medições da S04) nem o formato da gravação (ADR-003 e cartão RG-06).
- Este rascunho **não altera** `v2/` nem `CLAUDE.md`. A mudança de texto em `v2/02 §5` que a decisão pedir vai no cartão RG-24, com aprovação do PO.

## Resumo para o PO (5 linhas)
1. Hoje o programa tem dois jeitos de gerar o 3D: o da S03 (processo separado, protegido, mas com duas cópias do modelo na memória) e o da S04 (dentro do programa, rápido para editar, mas sem proteção: uma peça ruim pode travar tudo).
2. Nenhum dos dois cumpre ao mesmo tempo o que o plano pede: "uma cópia só do modelo" **e** "várias peças calculadas ao mesmo tempo".
3. **Recomendação:** misturar os dois. Editar acontece num processo só, com uma cópia do modelo. Abrir arquivo grande e calcular peça suspeita vai para um processo auxiliar descartável, que pode ser morto sem perder nada.
4. Várias peças ao mesmo tempo: sim, mas dentro de **uma** passada (o próprio IfcOpenShell divide o trabalho); duas passadas juntas continuam proibidas até o teste T04b provar que é seguro.
5. A trava do modelo deixa de ser "combinação" e vira uma porta única: todo acesso ao modelo, em Python ou C++, passa por ela, e o C++ confere que a trava está segura.

## 1. Contexto
O plano (`v2/02 §5`) desenha **um processo único**: a janela, as ferramentas e o modelo IFC em memória vivem juntos, e o módulo C++ (`obimcore`) lê **a mesma instância** de `ifcopenshell.file`, sem cópia. A S03 pede tesselação "via iterador de geometria multithread" (`v2/03:34`). O plano também diz que o desenho da tela e a tesselação "rodam em threads C++" e não dependem do bloqueio do interpretador Python.

O que existe hoje (conferido no código em `main`, 2026-10-15):

| Caminho | Onde a geometria roda | Cópias do modelo | Peças ao mesmo tempo | Proteção contra peça ruim |
|---|---|---|---|---|
| S03 (Python, `prototypes/viewport_qrhi/`) | Processo filho descartável (`processo_malhas.py`, `spawn`) | 2 se `manter_arquivo` (filho e depois o pai; os picos não se somam) | Sim, no modo rápido (blocos com várias threads) | Sim: vigia de 20 s por peça, modo isolado, caixa laranja, até 20 reinícios |
| S04 (C++, `prototypes/s04/obimcore/`) | Dentro do processo da janela (`malha.cpp`), bloqueio do interpretador solto | 1 (cumpre o plano) | Não: `std::mutex uma_geometria_por_vez` deixa uma passada por vez, com 1 thread (`malha.cpp:28-40`) | Nenhuma: travou ou caiu, o programa todo vai junto (achado B1) |

A trava do modelo também é só combinação (achado B13). O fluxo A usa um `threading.Lock` em Python (`fluxo_a.py:61,156-161`, regra 7 do `CONTRATO.md`). O C++ lê o modelo com o interpretador solto e sem conferir trava nenhuma (`ponte_malha.cpp:27-31`, `malha.cpp:32`), e `executar_roteiro` lê sem a trava (`fluxo_a.py:388`). A regra 9 do lote 10 ("nenhuma thread Python chama `ifcopenshell.geom` enquanto o editor estiver aberto") ainda não tem teste.

Essas três escolhas foram feitas em lotes Opus (6, 9 e 10) sem ADR. A regra do projeto é não contornar em silêncio. Este ADR registra as três e propõe o caminho.

## 2. Números já medidos (não são novos)
| Fato | Número | Fonte |
|---|---|---|
| Abrir o arquivo real do PO pelo caminho S03 | ~37 s, atraso máximo da janela 62 ms, 60 quadros por segundo | `LOG.md` 2026-10-12, F0-S03 |
| Memória no caminho S03 (conta conservadora: pai + maior filho) | 6,8 GB (meta 6 GB); maior soma ao mesmo tempo 6,2 GB | idem; aceito pelo PO "na prática" |
| Pico só do processo filho | 7,2 GB (antes dos ajustes da T08-C) | `LOG.md` 2026-10-12, T08-B1 |
| Maior peça legítima (um móvel, 1,6 milhão de triângulos) | 11,5 s | `LOTE_OPUS_6.md` D4 |
| Quatro passadas de geometria ao mesmo tempo no C++ | caiu em ~10% das rodadas; em série, 0 quedas em 55 | comentário em `malha.cpp:28-30`; `LOTE_OPUS_10.md` |
| Causa provável da queda | registro de mensagens global do IfcOpenShell (`logger::root()`), disputado por passadas simultâneas | `LOTE_OPUS_10.md`, "Recomendação sobre o mutex" (leitura dos cabeçalhos, **não provada**) |
| Experimento que confirmaria a causa | cartão S04-T04b, **adiado** (pausa D1) | `BOARD.md` |

**Faltam números** (entram no RG-02, junto com as metas M1 a M6 da S04):
- N1. Custo de abrir o mesmo IFC duas vezes em série (filho e depois pai), no arquivo real, em tempo e memória.
- N2. Custo de mandar uma edição pequena (1 parede) para um processo auxiliar e trazer a malha de volta, contra a meta de 200 ms da M2.
- N3. Ganho de várias threads **dentro de uma** passada no C++ (`num_threads` do iterador), com 200 rodadas sem queda.
- N4. Resultado do T04b (registro de mensagens local por passada, sem o mutex).

**Situação em 2026-10-21:** N1 a N4 **continuam sem medida**. O T04b está PAUSADO (`BOARD.md`); `malha.cpp` ainda tem o `std::mutex uma_geometria_por_vez` e cria o iterador com 1 thread; o fluxo A ainda usa um `threading.Lock` simples (a porta única 3C não foi feita). Correções da tabela acima: a maior peça tem dois tempos por métodos diferentes, 11,5 s (lote 6) e 15,1 s sozinha (T21 §5), e nenhum dos dois é o tempo dela dentro do carregador (lote 57 §1 item 4); o "6,8 GB" foi substituído pelos números abaixo.

### 2.1 Números da S04 (Linux oficial = máquina do PO, RTX 3070, tela real; Windows = CI, desenho por software)
| Fato | Número | Fonte |
|---|---|---|
| Desenho com thread própria do C++ | M5, maior intervalo entre quadros 16,7 a 17,8 ms nas formas 1 e 2 (Linux oficial); 32 a 33 ms no Windows, igual ao parado; com o bloqueio do interpretador preso 771 ms, 46 quadros e maior intervalo 18 ms | `F0-S04-threads.md`, conferência (iii) |
| Forma 3 (desenho em Python, referência) | maior intervalo 555 a 1.196 ms (oficial) | idem |
| `QEventLoop.exec()` ocioso solta o bloqueio | sim (razão 1,07 oficial; 0,97 Linux local; 1,01 Windows) | idem, conferência (i) |
| Abrir IFC solta o bloqueio; gravar IFC não solta | taxa da outra thread 0,993 contra 0,019 (oficial) | idem, conferência (ii) |
| Abertura do pesado, bloco 250 e 1 reinício planejado do auxiliar (bloco 22, pela vigia) | pico somado pior 5.958 MB em 6 aberturas (meta < 6.000); abrir 50,8 a 51,7 s (meta ≤ 60); atraso máx da janela 45 a 62,7 ms | `T29-placa-memoria` e `-2` |
| Troca de parede depois da T-2 (sub-lotes de até 8 MiB, reenvio só do sub-lote trocado, dentro de `cena`) | pior 82,8 ms em qualquer caso (meta 200); antes 399 e 6.749 ms em IFC real | `T30-placa` |
| Objeto Qt construído fora da thread da janela (postador de mouse da medição) | corrupção de memória reproduzida no Linux (3 de 3) e compatível com a queda 0xC0000374 do Windows | `F0-S04-T15f-diagnostico.md`, lote 43 |

## 3. Pergunta 1: onde a geometria roda
### Opção 1A. Processo único, tudo dentro (o plano, e o caminho S04 de hoje)
- A favor: uma cópia do modelo; edição rápida (sem ida e volta entre processos); código mais simples; cumpre `v2/02 §5` ao pé da letra.
- Contra: uma peça ruim no IFC de um cliente pode travar ou derrubar o programa, sem aviso e com o trabalho não salvo (B1). Uma thread C++ travada dentro do OCCT não pode ser interrompida com segurança: só matar o processo resolve. Abrir o arquivo grande (37 s de geometria) pesa na mesma memória da janela.

### Opção 1B. Processo de geometria sempre separado (o caminho S03 levado para tudo)
- A favor: o programa nunca cai por causa de uma peça; limite de tempo de verdade (matar o filho); já provado na S03.
- Contra: duas cópias do modelo durante a sessão inteira (memória já está acima da meta); cada edição teria de ser repetida no filho ou o filho reabriria o arquivo (risco de os dois modelos divergirem, e latência contra a M2 de 200 ms, **não medida**: N2); contraria a premissa central de `v2/02 §5` e a regra de decisão da S04 ("mesmo modelo sem cópia").

### Opção 1C. Misto: editar num processo, abrir e isolar no auxiliar (**recomendada**)
- **Editar:** o modelo de trabalho vive num processo só (o da janela), com uma cópia. A geometria das edições (poucas peças por comando) roda no `obimcore`, dentro do processo, numa thread de geometria que não é a da janela.
- **Abrir arquivo:** a primeira tesselação do arquivo inteiro roda num processo auxiliar descartável, como na S03 (vigia, 20 s por peça, modo isolado, caixa laranja). O pai abre o modelo para edição em paralelo ou depois (escolha pelo número N1), e os picos não se somam.
- **Peça suspeita:** toda peça que estourou o tempo ou derrubou o auxiliar fica marcada na sessão. Se o usuário editar uma peça marcada, a malha dela é feita no auxiliar (lendo o IFC gravado mais recente ou recebendo só a peça), nunca dentro do processo.
- **Rede de segurança dentro do processo:** a thread de geometria tem um vigia. Se uma edição comum passar do limite (proposta: 20 s, o mesmo da S03), o programa avisa, grava o diário de operações e a cópia de segurança (oplog e autosave da S05) e oferece reiniciar. Não dá para cancelar o OCCT por dentro; o vigia limita o estrago, não o evita.
- A favor: cópia única durante a edição (cumpre o essencial de `v2/02 §5`); o caso mais arriscado (arquivo de terceiro, milhares de peças desconhecidas) fica isolado; reaproveita o que a S03 já provou.
- Contra: dois caminhos de geometria para manter (precisam do mesmo formato de vértices: cartão RG-04); o caso "peça comum que trava na edição" continua derrubando o processo (mitigado pelo diário e pela cópia de segurança); `v2/02 §5` precisa de uma frase nova sobre o processo auxiliar (RG-24).

## 4. Pergunta 2: várias peças ao mesmo tempo
### Opção 2A. Uma passada por vez, 1 thread (o C++ de hoje)
- A favor: 0 quedas em 55 rodadas; simples.
- Contra: não cumpre `v2/03:34`; abrir arquivo grande dentro do processo seria lento (hoje isso não acontece porque a abertura é da S03).

### Opção 2B. Várias passadas simultâneas, sem o mutex
- A favor: máximo de paralelismo.
- Contra: caiu em ~10% das rodadas. Só vale depois que o T04b provar a causa e a correção (N4).

### Opção 2C. Uma passada por vez, várias threads **dentro** da passada (**recomendada**)
- O próprio iterador do IfcOpenShell divide as peças entre threads (`num_threads`). É o "iterador multithread" que o plano pede. O mutex entre passadas fica.
- Edições pequenas (1 a poucas peças): 1 thread, porque dividir não ganha nada.
- Abertura e lotes grandes (no auxiliar, ou dentro do processo acima de um tamanho a medir): várias threads. O auxiliar da S03 já faz isso.
- A favor: cumpre o plano sem o risco medido; o lote 10 já apontou esse caminho.
- Contra: **não medido no C++** (N3). Se cair, volta para 2A dentro do processo e o paralelismo fica só no auxiliar.
- O T04b continua: se provar a causa e a correção, o mutex sai e 2B fica liberada (registrar como revisão deste ADR).

## 5. Pergunta 3: trava do modelo
### Opção 3A. Combinação, como hoje
- A favor: nada a fazer.
- Contra: nada impede um painel, um salvamento automático ou um complemento de ler o modelo no meio de uma edição. Na F1 isso vira travamento aleatório, difícil de reproduzir (B13).

### Opção 3B. Dono único: só uma thread toca no modelo
- Todo pedido (ler ou escrever) vira mensagem para a "thread do modelo".
- A favor: nenhuma trava; impossível ler pela metade.
- Contra: leituras longas (gravar, gerar uma tabela) param as edições; reescreve o fluxo A inteiro; o C++ continuaria precisando de regra própria para ler com o interpretador solto.

### Opção 3C. Porta única com trava de leitura e escrita (**recomendada**)
- Um objeto "sessão do modelo" em Python é o único dono do `ifcopenshell.file`. Ninguém guarda o arquivo solto.
- Duas portas: `ler()` (vários leitores juntos) e `escrever()` (um só, e nenhum leitor junto). A transação, a malha e a `Cena.atualizar` acontecem dentro de `escrever()`, como a regra 7 já manda.
- O `obimcore` recebe a sessão, não o arquivo, e **confere** que a trava de leitura ou de escrita está segura antes de soltar o interpretador. Sem trava: erro claro, não queda.
- Ordem das travas (já respeitada no C++, agora escrita): trava do modelo → mutex da geometria → `Motor::m_` → `DadosCena::m_` → `mc_`. A thread de desenho nunca pega a trava do modelo nem toca em Python.
- Regra 9 vira teste: nenhuma chamada a `ifcopenshell.geom` fora do `obimcore` e do processo auxiliar enquanto o editor estiver aberto.
- A favor: pequena (troca o `threading.Lock` do fluxo A por uma trava de leitura e escrita e passa a sessão ao C++); fecha B13; serve para o salvamento automático e para os painéis da F1.
- Contra: Python não traz trava de leitura e escrita pronta; é código nosso, crítico (classe T3, revisão Opus). Leitor demorado atrasa a próxima edição (mitigação: leituras grandes copiam o que precisam e soltam a trava).

## 5.1 Pergunta 4: em que thread roda um comando Python longo (nova em 2026-10-21)
Formas medidas no T15 (lote 9 §2.3; `F0-S04-threads.md`): **forma 1** = o comando inteiro numa thread Python à parte, a janela no laço de eventos; **forma 2** = o comando na thread da janela, cedendo ao Qt a cada 8 ms ou mais entre operações (chamada da `api`, bloco de até 25 peças de `obimcore.malhas`, `Cena.atualizar`). Nas duas o desenho fica fluido (§2.1); a escolha vale só para a resposta da janela.

### Números (maior intervalo do pulso de 10 ms, por rodada ou mediana / p95 / máximo; mouse = atraso do evento sintético)
| Caso | Forma 1 | Forma 2 | Fonte |
|---|---|---|---|
| Lote de 1.000 paredes, **controle sem postador de mouse**, placa real (base 3.000; rodadas) | 1.363 / 924 / 646 ms | 642 / 704 / 717 ms | `threads.md`, M5b |
| Idem, Linux local, software (base 300; mediana / p95 / máx) | 502 / 1.127 / 1.196 ms | 719 / 724 / 725 ms | idem |
| Idem, Windows, software | 135 / 152 / 153 ms | 810 / 825 / 827 ms | idem |
| Lote, **com postador**, mouse mediano, placa real | 679 / 952 / 893 ms | 13,5 / 13,5 / 13,1 ms | idem |
| Lote, com postador, mouse p95 / maior, placa real | 1.219 a 1.655 / 1.274 a 1.742 ms | 514 a 578 / 631 a 693 ms | idem |
| Lote, mouse mediano, Windows | 89 ms | 14 ms | idem |
| Maior fatia da forma 2 | — | cerca de 696 ms (placa) e 785 a 828 ms (Windows): uma só chamada, `spatial.assign_container`, que a forma 2 não parte | idem |
| Parede com 150 aberturas (base 300), maior atraso do mouse; limiar = metade de `malha_ms` | placa 2,1 / 9,4 / 2,3 ms; Linux local até 16 ms; Windows 3 ms | placa 203,7 / 199,8 / 199,4 ms; Linux local 212 a 224 ms; Windows 248 a 254 ms | idem; limiar 101,6 (placa), 107 e 118 ms |
Cuidados de leitura: (1) o postador de mouse é uma terceira thread Python e piora a forma 1 (`fluxo_a/CONTRATO.md`, T15); para comparar as formas vale o controle, como o próprio relatório diz. (2) Regra (a) da T15 (controle acima de 1 s nas duas formas) não dispara em nenhuma máquina; regra (b) (parede) foi definida sobre a forma 1 e passa; a forma 2 fica acima do mesmo limiar nas três máquinas. (3) A maior fatia da forma 2 só foi medida na base sintética: `lote.py` não aceita IFC (lacuna de `acceptance/S04-medicao-oficial.md`).

### Opções
- **4A. Forma 1 para tudo** (decisão do PO de 17/10: "reforçar a forma 1"). A favor: passa a parede com folga nas três máquinas; ganha no controle do Windows e na mediana do Linux local; código de comando sem pontos de cessão. Contra: na placa real o controle chegou a 1.363 ms numa rodada; com a terceira thread Python a janela ficou surda por mais de 1 s nas três rodadas (pulso 1.155 a 1.876 ms; fere o lote 9 §5.1) e o mouse fica atrasado de 0,7 a 0,95 s (mediana) quando há outra thread Python disputando o bloqueio (o programa terá a thread de arquivo, §6).
- **4B. Forma 2 para tudo.** A favor: mouse mediano de 13 a 14 ms em todas as máquinas; pior caso estável perto da maior chamada única. Contra: reprova a parede de 150 aberturas nas três máquinas; piso de cerca de 0,7 a 0,8 s por chamada que não se parte; pontos de cessão escritos em cada comando longo.
- **4C. Mista (ideia do PO, 2026-10-21; igual à recomendação do autor do T15):** comandos longos na thread da janela, em fatias (forma 2); todo cálculo de malha numa thread à parte, com o bloqueio do interpretador solto dentro do `obimcore` (forma 1 só para a geometria).

### Avaliação da 4C contra os números
- **Geometria à parte: sustentada.** O que foi medido é exatamente uma thread Python que chama `obimcore.malhas` com o bloqueio solto (forma 1 na parede): 2 a 16 ms contra limiares de 101,6 a 118 ms, nas três máquinas. Não foi medida uma thread criada pelo próprio C++; o mapa do §6 passa a dizer "thread à parte que chama o `obimcore`", que é o medido.
- **Comandos em fatias: em parte.** Ganha na placa real (controle 704 contra 924 ms de mediana; mouse 13 contra 679 a 952 ms), perde no Windows (810 contra 135 ms no controle) e divide no Linux local (perde na mediana, ganha no p95 e no máximo). O piso de 0,7 a 0,8 s fica: a mista herda dele, porque a chamada mais longa é da `api`, não da malha.
- **A mistura: hipótese.** Nunca foi medida. Hoje a forma 2 calcula a malha na própria janela (blocos de 25 peças); a 4C troca isso por uma entrega à thread de geometria com o comando ainda dono da trava de escrita, e esse caminho não existe nem foi medido.
- **"Sem sacrificar nenhuma das duas": não sustentado como fato.** A 4C herda o piso e o código de cessão da forma 2 e acrescenta a entrega à thread de geometria e a regra de trava abaixo. O ganho esperado (mouse da forma 2 com a parede da forma 1) é plausível pelos números, mas só o V1 diz.

### Regras de desenho da 4C (entram no cartão de implementação, T3)
1. Comando curto (meta M3: cerca de 1 ms; M2: 33 ms ponta a ponta) roda direto na janela, sem fatias. Comando que pode passar de 100 ms cede ao Qt a cada 8 ms, como no T15.
2. Toda malha (`obimcore.malhas`, e a de `Cena.atualizar` se ela calcular) roda na thread de geometria. A janela nunca espera por ela parada: entrega o pedido e volta ao laço; o resultado volta por sinal enfileirado do Qt.
3. Regra 3 do lote 9 §1.4 reescrita: o C++ lê o modelo **enquanto o comando dono de `escrever()` está parado esperando a geometria**, sem escrever; o comando só continua (`Cena.atualizar`, fim da transação) depois do resultado.
4. Durante as fatias e a espera da geometria, a janela trata eventos: leitura de painel só com tentativa sem espera (mostra o valor anterior, como já faz o fluxo A); comando novo ou desfazer recebe "modelo ocupado" e não entra no meio (reentrada proibida).
5. Nenhum objeto Qt é criado ou tocado fora da thread da janela (T15f: corrupção de memória reproduzida).
6. A ordem das travas do §5 não muda.

### Decisão (direção do PO, condicionada)
**4C**, condicionada ao cartão **V1** (validação: protótipo da forma mista em `lote.py` e medição; classe **T3**, porque mexe em threads e na entrega ao C++; oráculo por subagente diferente; revisão Opus). Critérios de aceite do V1, todos com a mesma régua do T15 e sem mudar nenhum número:
1. A 4C entra como **forma nova** em `lote.py` (forma "mista"); formas 1 e 2 seguem iguais, para os números antigos continuarem comparáveis; `fluxo_a.py` não muda (é régua, A29).
2. Mesmas medidas e mesmas bases: lote de 1.000 paredes (base 3.000 na placa real; base 300 no Linux local e no Windows), 3 rodadas por forma, com e sem postador; parede de 150 aberturas na base 300, 3 rodadas.
3. Parede: maior atraso do mouse da mista, mediana das 3 rodadas, **abaixo da metade de `malha_ms`** (regra (b)), em todas as máquinas.
4. Lote, controle: mediana do maior intervalo do pulso da mista **abaixo de 1.000 ms** (regra (a)) e **não acima da pior rodada da forma 2** medida na mesma sessão; com postador, mediana do atraso do mouse da mista não acima da pior rodada da forma 2 na mesma sessão (a comparação usa a dispersão medida, não uma tolerância nova). Nenhuma rodada da mista com janela surda por mais de 1 s (lote 9 §5.1).
5. M5 inalterado nas três formas (janela de 1 s com 20 quadros ou mais, maior intervalo < 200 ms).
6. Lote "longo com geometria pesada" (o lote de 1.000 com uma parede de 150 aberturas no meio): na mista, a parede não aumenta a mediana do maior atraso do mouse mais que a metade de `malha_ms` dela, contra o mesmo lote sem a parede, na mesma sessão.
7. Medido no Linux local e no Windows do CI (informativo, não bloqueia) e **uma** sessão na placa real (ok e horário do PO).
8. Em separado: maior fatia da forma 2 (e da mista) num IFC real do PO; exige `--ifc` em `lote.py` e a liberação do arquivo no chat. Se passar de 1 s, o V1 reprova a parte "comandos em fatias" e vai ao PO.
Se o V1 reprovar: **a pergunta 4 volta ao PO** com 4A e 4B lado a lado e os números do V1. A 4A não é volta automática: na placa real, com uma terceira thread Python (o programa terá a thread de arquivo, §6), a forma 1 deixou a janela surda por mais de 1 s nas três rodadas (pulso 1.155 a 1.876 ms; controle até 1.363 ms numa rodada), o que fere o critério do lote 9 §5.1. Se só o item 8 reprovar: levar ao PO com as opções (4A, ou partir a chamada longa da `api`).

## 6. Mapa de threads e processos proposto (com 1C, 2C, 3C e 4C; revisto em 2026-10-21)
| Onde | O que faz | Toca no Python? | Toca no modelo? |
|---|---|---|---|
| Thread da janela (Qt) | Interface, eventos, comandos curtos; comandos longos em fatias de 8 ms (4C, se o V1 passar; senão o PO decide entre 4A e 4B) | Sim | Só por `ler()`/`escrever()`; nunca espera geometria parada; leitura de painel só sem espera |
| Thread de desenho (C++) | Desenha a cena imutável | Nunca | Nunca (já é assim: `motor.h`, `cena.cpp`) |
| Thread de geometria (thread à parte que chama o `obimcore`; o trabalho roda em C++ com o interpretador solto) | Toda malha das edições, 1 passada por vez | Só para entrar e sair da chamada | Lê enquanto o comando dono de `escrever()` espera, sem escrever (§5.1, regra 3) |
| Thread de arquivo (Python) | Abrir, gravar, cópia de segurança (fora da janela: B22, RG-05, RG-06); gravar não solta o bloqueio (§2.1) | Sim | `ler()` para gravar; `escrever()` para trocar o modelo aberto |
| Processo auxiliar (descartável) | Tesselação da abertura (bloco de 250 peças, até 1 reinício planejado pela vigia de crescimento) e de peças suspeitas | O seu próprio | Tem a sua cópia só de leitura, enquanto vive |
Nenhuma thread fora da janela cria ou toca objeto Qt (§5.1, regra 5).

## 7. Consequências
- Cartões que dependem desta decisão: RG-04 (um só formato de vértices, porque os dois caminhos ficam), RG-05 (viewport no app com a sessão do modelo única), RG-06 (gravação atômica e diário antes de qualquer reinício), RG-11 (motivo da queda do auxiliar), RG-24 (frase nova em `v2/02 §5`).
- S04-T04b deixa de ser "adiado sem prazo": vira condição para liberar 2B.
- A meta da S03 "iterador multithread" passa a ser cumprida no auxiliar e, se N3 passar, também dentro do processo. Registrar no portão (regra D8) como **atingida por outro caminho**, não como exceção silenciosa.
- Memória: durante a abertura, a meta vale pela soma do pico do pai com o maior pico entre os filhos (conta A), pela pior de 5 aberturas (A28). Número vigente do pesado: pior 5.958 MB em 6 aberturas, folga de 42 MB (§2.1). O reinício planejado do auxiliar (T29, lote 57 opção 1-B) reforça a 1C.
- Pergunta 4 (2026-10-21): cartões V1 (validação da 4C, T3) e, se passar, I1 (implementação da 4C no produto, T3); detalhes em `docs/state/lotes/LOTE_OPUS_68/resultado.md`. O roteiro de aceite da S04 (A18) espera o V1.

## 8. Decisão
| Pergunta | Opções | Recomendação | Decisão do PO |
|---|---|---|---|
| 1. Onde a geometria roda | 1A dentro · 1B sempre separado · 1C misto | **1C** | **1C** (PO, 2026-10-15) |
| 2. Várias peças ao mesmo tempo | 2A uma por vez · 2B várias passadas · 2C várias threads numa passada | **2C** | **2C** (PO, 2026-10-15) |
| 3. Trava do modelo | 3A combinação · 3B dono único · 3C porta única | **3C** | **3C** (PO, 2026-10-15) |
| 4. Thread do comando longo (§5.1) | 4A forma 1 · 4B forma 2 · 4C mista | 4C só com o V1; se o V1 reprovar, volta ao PO (4A ou 4B) | **4C como direção** (PO, 2026-10-21), condicionada ao V1; antes, 17/10: "reforçar a forma 1" |

Próximos passos: os números N1 a N4 seguem sem medida (o RG-02 fechou a S04 sem eles; o T04b está pausado) e entram como condição dos cartões que dependem deles (2B, e as várias threads da 2C dentro do processo). O V1 decide a pergunta 4. Este ADR é revisto por um Opus que não escreveu a parte revista (regra 6 do `CLAUDE.md`) e passa a "aceito" depois do V1 e da aprovação do PO. A frase nova de `v2/02 §5` sobre o processo auxiliar vai no cartão RG-24, com aprovação do PO.

## 9. O que nos faria mudar de ideia
- N2 mostrar que mandar uma edição ao auxiliar custa bem menos de 200 ms → 1B fica viável e mais segura.
- N1 mostrar que abrir duas vezes passa de 30% do tempo de abertura → abrir só no pai e mandar ao auxiliar só as peças, por lista.
- Uma queda de geometria numa edição comum durante a S04 (T11, T15) ou na F1 → isolar também as edições (1B para tudo).
- T04b provar a causa da queda e a correção → tirar o mutex (2B).
- N3 com qualquer queda em 200 rodadas → 2A dentro do processo; paralelismo só no auxiliar.
- V1 reprovado em qualquer critério de 2 a 6 do §5.1 → volta ao PO com 4A e 4B lado a lado (4A já fere o lote 9 §5.1 na placa com uma terceira thread Python).
- Maior chamada única da `api` acima de 1 s num IFC real (V1, item 8) → a parte "comandos em fatias" cai; levar ao PO (4A, ou partir a chamada).
- Placa real no Windows (T28) mostrando o controle da forma 2 acima de 1 s → rever a 4C para o Windows.
- Memória do pesado acima de 6.000 MB em qualquer abertura oficial nova → voltar às opções do lote 57 (1-A alocador, 1-C peça por partes) com o PO.

## 10. Não verificado
- A causa da queda com passadas simultâneas (leitura dos cabeçalhos, não experimento).
- Se o `num_threads` do iterador é seguro dentro do processo do `obimcore` (a S03 só usou no processo filho, que pode cair sem dano).
- O custo real das opções 1B e 1C (N1, N2).
- A forma mista 4C inteira (§5.1): nenhum número dela existe; só das partes.
- Forma 1 e forma 2 em IFC real e com placa real no Windows.
- Por que a forma 1 piora com uma terceira thread Python (o T15 mediu o efeito, não a causa).

## 11. O que deixa de valer (2026-10-21)
- "Os 6,8 GB da S03 continuam sendo o número a bater" (§7): vale o pior de 5 aberturas na placa (§2.1).
- A observação do PO de 17/10 ("a reprovação da forma 2 na parede reforça a forma 1") deixa de ser a direção para os comandos longos; continua valendo para a geometria; se o V1 reprovar, a escolha para os comandos volta ao PO (§5.1), sem volta automática.
- Regra 3 do lote 9 §1.4 ("o C++ lê o modelo apenas dentro de uma chamada feita pela thread do comando"): substituída pela regra 3 do §5.1 quando a 4C for implementada; até lá, continua.
- "Comandos curtos" como única tarefa da thread da janela (§6, versão de 15/10).
