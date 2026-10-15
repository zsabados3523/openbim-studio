<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# ADR-004: Processos, threads e trava do modelo
- Status: **RASCUNHO, aguarda decisão do PO.** Nada aqui vale como regra até o PO escolher as opções da seção 8.
- Autor: opus (cartão F0-RG-01, TA) · Data: 2026-10-15
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

## 6. Mapa de threads e processos proposto (com 1C, 2C, 3C)
| Onde | O que faz | Toca no Python? | Toca no modelo? |
|---|---|---|---|
| Thread da janela (Qt) | Interface, eventos, comandos curtos | Sim | Só por `ler()`/`escrever()`; nunca espera geometria |
| Thread de desenho (C++) | Desenha a cena imutável | Nunca | Nunca (já é assim: `motor.h`, `cena.cpp`) |
| Thread de geometria (C++, interpretador solto) | Malha das edições, 1 passada por vez | Não, durante a passada | Lê, com a trava segura por quem chamou |
| Thread de arquivo (Python) | Abrir, gravar, cópia de segurança (fora da janela: B22, RG-05, RG-06) | Sim | `ler()` para gravar; `escrever()` para trocar o modelo aberto |
| Processo auxiliar (descartável) | Tesselação da abertura e de peças suspeitas | O seu próprio | Tem a sua cópia só de leitura, enquanto vive |

## 7. Consequências
- Cartões que dependem desta decisão: RG-04 (um só formato de vértices, porque os dois caminhos ficam), RG-05 (viewport no app com a sessão do modelo única), RG-06 (gravação atômica e diário antes de qualquer reinício), RG-11 (motivo da queda do auxiliar), RG-24 (frase nova em `v2/02 §5`).
- S04-T04b deixa de ser "adiado sem prazo": vira condição para liberar 2B.
- A meta da S03 "iterador multithread" passa a ser cumprida no auxiliar e, se N3 passar, também dentro do processo. Registrar no portão (regra D8) como **atingida por outro caminho**, não como exceção silenciosa.
- Memória: durante a abertura, o pico é o maior entre pai e auxiliar, não a soma (se o pai abrir depois). Os 6,8 GB da S03 continuam sendo o número a bater.

## 8. Decisão (a preencher pelo PO)
| Pergunta | Opções | Recomendação | Decisão do PO |
|---|---|---|---|
| 1. Onde a geometria roda | 1A dentro · 1B sempre separado · 1C misto | **1C** | _pendente_ |
| 2. Várias peças ao mesmo tempo | 2A uma por vez · 2B várias passadas · 2C várias threads numa passada | **2C** | _pendente_ |
| 3. Trava do modelo | 3A combinação · 3B dono único · 3C porta única | **3C** | _pendente_ |

Depois da escolha: os números N1 a N4 são medidos no RG-02; este ADR é revisto por um Opus que não o escreveu (regra 6 do `CLAUDE.md`) e passa a "aceito".

## 9. O que nos faria mudar de ideia
- N2 mostrar que mandar uma edição ao auxiliar custa bem menos de 200 ms → 1B fica viável e mais segura.
- N1 mostrar que abrir duas vezes passa de 30% do tempo de abertura → abrir só no pai e mandar ao auxiliar só as peças, por lista.
- Uma queda de geometria numa edição comum durante a S04 (T11, T15) ou na F1 → isolar também as edições (1B para tudo).
- T04b provar a causa da queda e a correção → tirar o mutex (2B).
- N3 com qualquer queda em 200 rodadas → 2A dentro do processo; paralelismo só no auxiliar.

## 10. Não verificado
- A causa da queda com passadas simultâneas (leitura dos cabeçalhos, não experimento).
- Se o `num_threads` do iterador é seguro dentro do processo do `obimcore` (a S03 só usou no processo filho, que pode cair sem dano).
- O custo real das opções 1B e 1C (N1, N2).
