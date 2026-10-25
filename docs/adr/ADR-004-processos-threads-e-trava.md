<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# ADR-004: Processos, threads e trava do modelo

Status: aceito

## Contexto
O modelo IFC vive numa única instância de `ifcopenshell.file` que o Python e o módulo C++ `obimcore` leem sem cópia (ADR-001). Isso levanta quatro perguntas: onde roda a geometria, se várias peças podem ser calculadas ao mesmo tempo, quem protege o modelo e em que thread roda um comando longo.

Havia dois caminhos de geometria:
- **Processo auxiliar** (`viewport/viewport_qrhi/processo_malhas.py`, `spawn`): protegido (vigia de 20 s por peça, modo isolado, reinícios), mas com a segunda cópia do modelo na memória.
- **Dentro do processo da janela** (`native/obimcore/nucleo/malha.cpp`): uma cópia só e edição rápida, mas sem proteção: uma peça ruim derruba o programa. Um `std::mutex` deixa uma passada de geometria por vez, com 1 thread, porque quatro passadas simultâneas derrubaram o processo em cerca de 10% das rodadas (contra 0 quedas em 55 em série). A causa provável, o registro global de mensagens do IfcOpenShell, é leitura de cabeçalhos, não experimento.

A trava do modelo era só uma convenção (`threading.Lock` no fluxo A; o C++ lia sem conferir trava).

## Opções
**1. Onde roda a geometria.** 1A tudo no processo da janela; 1B sempre em processo separado (duas cópias do modelo e ida e volta a cada edição); **1C misto**: editar no processo da janela, abrir arquivos e isolar peças suspeitas no auxiliar.
**2. Várias peças ao mesmo tempo.** 2A uma passada por vez com 1 thread; 2B várias passadas simultâneas sem o mutex (só depois de provar a causa da queda); **2C uma passada por vez, várias threads dentro da passada** (o iterador de geometria do IfcOpenShell divide as peças).
**3. Trava do modelo.** 3A convenção; 3B dono único (toda leitura e escrita vira mensagem para uma thread); **3C porta única** com trava de leitura e escrita.
**4. Comando longo.** 4A o comando inteiro numa thread Python à parte; 4B o comando na thread da janela, cedendo ao Qt a cada 8 ms ou mais entre operações; **4C mista**: comandos longos na thread da janela em fatias, e todo cálculo de malha numa thread à parte com o bloqueio do interpretador solto dentro do `obimcore`.

## Decisão
**1C.** O modelo de trabalho vive no processo da janela, com uma cópia. A primeira tesselação do arquivo inteiro e as peças que estouraram o tempo rodam no processo auxiliar descartável, em blocos de 250 peças, com um reinício planejado no meio (bloco de 22, por vigia de crescimento de memória) para caber nos 6 GB. Uma vigia dentro do processo grava o diário e oferece reiniciar se uma edição comum passar de 20 s; não dá para cancelar o OCCT por dentro.

**2C.** O mutex entre passadas fica. Edições pequenas usam 1 thread; abertura e lotes grandes usam várias threads, no auxiliar (já é assim) e, se for medido seguro, no processo.

**3C.** `SessaoModelo` (`app/openbim_app/sessao_modelo.py`) é a única dona do arquivo, com duas portas: `ler()` (vários leitores) e `escrever()` (um só, sem leitores). Transação, malha e atualização da cena acontecem dentro de `escrever()`. O `obimcore` confere que há trava segura antes de soltar o interpretador; sem trava, erro claro. Ordem das travas: modelo, mutex da geometria, `Motor::m_`, `DadosCena::m_`, `mc_`. A thread de desenho nunca pega a trava do modelo nem toca em Python. Nenhuma chamada a `ifcopenshell.geom` fora do `obimcore` e do auxiliar enquanto o editor está aberto.

**4C.** Regras:
1. Comando curto roda direto na janela; comando que pode passar de 100 ms cede ao Qt a cada 8 ms.
2. Toda malha roda na thread de geometria; a janela entrega o pedido e volta ao laço; o resultado volta por sinal enfileirado.
3. O C++ lê o modelo enquanto o comando dono de `escrever()` espera a geometria, sem escrever.
4. Durante as fatias, leitura de painel só por tentativa sem espera; comando novo recebe "modelo ocupado" (reentrada proibida).
5. Nenhum objeto Qt é criado ou tocado fora da thread da janela (corrupção de memória reproduzida no Linux).

Mapa final: thread da janela (interface, comandos, fatias); thread de desenho em C++ (nunca toca Python nem o modelo); thread de geometria (chama o `obimcore` com o interpretador solto); thread de arquivo em Python (abrir, gravar, copiar); processo auxiliar descartável (abertura e peças suspeitas).

## Números medidos
Linux de referência: RTX 3070, tela real. Windows: CI, desenho por software (WARP).
| Fato | Número |
|---|---|
| Desenho com thread própria em C++ | maior intervalo entre quadros 16,7 a 17,8 ms (Linux), 32 a 33 ms (Windows); desenho em Python: 555 a 1.196 ms |
| Abrir IFC solta o bloqueio do interpretador; gravar IFC não solta | taxa da outra thread 0,993 contra 0,019 |
| Abertura do arquivo pesado, bloco 250 e 1 reinício | pico somado pior 5.958 MB em 6 aberturas (meta 6.000), 50,8 a 52,2 s, atraso máximo da janela 45 a 62,7 ms |
| Troca de parede em IFC real, sub-lotes de até 8 MiB | pior 82,8 ms (antes 399 e 6.749 ms) |
| Mista (4C), atraso do mouse com parede de 150 aberturas | 18,6 a 26,5 ms contra limites de 102 a 145 ms |
| Mista, lote de 1.000 paredes, janela surda | pior 978 ms no Windows (limite 1.000 ms, folga de 2,2%); 716 ms na placa |
| Maior fatia de um comando em IFC real de 25 MB | 1.018 ms com uma única chamada `spatial.assign_container` de 1.000 paredes; 165,5 ms depois de partir em sub-lotes de 100 (`SUBLOTE_CONTAINER`) |
Várias margens são apertadas (1% a 4%) porque a forma mista e a forma em fatias quase empatam; um item da base sintética ficou 0,3% acima do limite e foi aceito como ruído, sem mudar a régua.

## Consequências
- Dois caminhos de geometria para manter; precisam do mesmo formato de vértices (`viewport/viewport_qrhi/formato_malha.py`).
- Uma peça comum que trava na edição ainda derruba o processo; o diário (ADR-002) e a cópia de segurança limitam o dano.
- Leitor demorado atrasa a próxima edição: leituras grandes copiam o que precisam e soltam a trava.
- Memória do arquivo pesado: a meta vale pela soma do pico do pai com o maior pico entre os filhos, pela pior de 5 aberturas.
- Cada comando longo precisa de pontos de cessão ao Qt.

## O que nos faria mudar de ideia
- Mandar uma edição ao auxiliar custar bem menos de 200 ms: 1B fica viável e mais segura.
- Abrir o arquivo duas vezes passar de 30% do tempo de abertura: abrir só no pai e mandar peças por lista.
- Uma queda de geometria numa edição comum: isolar também as edições.
- Provar a causa da queda com passadas simultâneas e a correção: tirar o mutex (2B).
- Qualquer queda em 200 rodadas com várias threads dentro do processo: paralelismo só no auxiliar.
- Outra chamada única da `api` acima de 1 s num IFC real: partir a chamada ou reabrir 4A.
- Memória do pesado acima de 6.000 MB na configuração final: rever o alocador ou processar peça por partes.

## O que ficou em aberto
- Quatro números nunca foram medidos: custo de abrir o mesmo IFC duas vezes em série; custo de mandar uma edição pequena ao auxiliar; ganho de várias threads dentro de uma passada; resultado do experimento com registro de mensagens local por passada.
- A forma 4C foi validada no protótipo (`tools/s04/fluxo_a/lote.py`), não no produto; a divisão em sub-lotes só foi medida no Linux em tela virtual.
- Windows com desenho por software (WARP): destruir o dispositivo D3D11 trava raramente (1 em 300 voltas, mesmo com o limite de 5 s em `Motor::parar()` que evita congelar ao sair). A correção de fundo (um dispositivo D3D11 por processo) é trabalho futuro.
- Windows com placa real: não medido.
