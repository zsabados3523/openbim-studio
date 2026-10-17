<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S04-T15: em que thread rodar um comando Python longo (relatório para o ADR-004)

Máquina deste relatório (uma execução, 2026-10-16): Linux 7.0.0-38, Intel Core i5-12600KF (16 threads), 23 GB, `xvfb-run -a`, desenho `gl`, base de 300 paredes, lote de 1.000 paredes, 3 rodadas por forma. Cada célula é mediana / p95 / máximo das 3 rodadas (com 3 valores o p95 é interpolado). Números do CI (Linux e Windows): a preencher com o run do CI. O número oficial do lote 9 §2.3, com placa de vídeo real, fica pendente: só se mede na máquina do PO, com o ok dele (aqui o desenho é por software). Os JSON brutos saem de `lote.py`, `conferencias.py` e `lote.main_pesada`.

## Resumo para o PO
Medi três jeitos de rodar um comando longo. O desenho do 3D seguiu fluido nos dois bons (17 ms entre quadros); no jeito antigo, de referência, parou até 1,4 s.
Sem o mouse sintético, a janela fica surda no pior caso por 0,5 s (comando numa thread à parte, forma 1) e 0,7 s (em fatias na janela, forma 2); nas piores rodadas, 1,2 s e 0,7 s.
Com o mouse sintético o atraso da forma 1 mais que dobrou (1,1 s contra 0,5 s) e o da forma 2 ficou igual: a forma 1 piora a cada thread Python a mais.
A parede com 150 aberturas, com o desenho calculado fora do bloqueio, não parou a janela: maior atraso de 8,5 ms contra 214 ms do cálculo.
Recomendo a forma 2 (pior caso estável) com o cálculo do desenho em thread própria; o Windows ainda será medido na nuvem e a decisão é sua.

## Forma 1
Comando em thread Python; a janela fica no laço de eventos. Lote de 1.000 paredes (duração 2.203 / 2.262 / 2.269 ms; sem o mouse sintético: 2.137 ms).
- M5, maior intervalo entre quadros do núcleo: 17 / 18 / 18 ms (parado: 18 / 19 / 19 ms); nenhuma janela de 1 s abaixo de 62 quadros.
- Pulso (temporizador de 10 ms na janela), maior intervalo: 1.145 / 1.325 / 1.345 ms (controle, sem mouse: 502 / 1.127 / 1.196 ms).
- Fatias: não se aplica.

## Forma 2
Comando na thread da janela, cedendo ao Qt a cada 8 ms ou mais, entre as operações. Mesmo lote (duração 2.237 / 2.260 / 2.262 ms).
- M5, maior intervalo entre quadros: 17 / 17 / 17 ms (parado: 18 / 19 / 20 ms); nenhuma janela de 1 s abaixo de 62 quadros.
- Pulso, maior intervalo: 711 / 716 / 716 ms (controle: 719 / 724 / 725 ms).
- Fatias: cerca de 180 por rodada; maior fatia 710 / 715 / 716 ms, de uma única chamada da API que a forma 2 não consegue partir.

## Forma 3
Referência: forma 1 com a viewport Python da S03 (sem portão; esperava-se que reprovasse). Lote de 2.099 / 2.118 / 2.201 ms.
- M5, maior intervalo entre quadros: 1.212 / 1.418 / 1.441 ms (rodadas: 843, 1.441, 1.212 ms), com janelas de 1 s de 0 a 6 quadros; parado ela desenha 120 a 127 quadros em 2 s.
- Pulso, maior intervalo: 859 / 936 / 945 ms.
- Mostra o tamanho do problema que as formas 1 e 2 resolvem: o desenho fora do Python mantém 17 a 18 ms.

## M5b
Atraso entre um evento de mouse sintético (um a cada 20 ms, agendado desde o início do lote) e o seu tratamento na janela. Sem portão no lote (registro, lote 9 §2.3).
| | Forma 1 | Forma 2 |
|---|---|---|
| mediana do atraso | 898 / 957 / 964 ms | 14 / 14 / 14 ms |
| p95 do atraso | 1.293 / 1.311 / 1.313 ms | 604 / 607 / 607 ms |
| maior atraso | 1.340 / 1.344 / 1.344 ms | 715 / 720 / 720 ms |
| eventos por rodada | 114, 108, 111 | 111, 112, 114 |
Nas duas formas todo evento agendado foi tratado. Para comparar as formas vale o CONTROLE (sem a thread que posta o mouse, maior intervalo do pulso de 10 ms, mediana / p95 / máximo das 3 rodadas): forma 1 502 / 1.127 / 1.196 ms (rodadas 361, 1.196, 502); forma 2 719 / 724 / 725 ms. A forma 1 ganha na mediana e perde no p95 e no máximo. Efeito da thread do mouse, medido (pulso maior, com mouse contra controle): forma 1 1.145 contra 502 ms; forma 2 711 contra 719 ms. O motivo não foi medido; nenhuma função é apontada.
Regra de parada (a), aprovada pelo PO em 2026-10-16: se a mediana do maior intervalo do pulso no controle passar de 1.000 ms nas DUAS formas, parar e levar ao PO. Aqui deu 502 e 719 ms: não dispara. Critério do lote 9 §5.1 ("janela surda por mais de 1 s em operações comuns"): a forma 1 com a thread do mouse passa de 1 s (1.145 ms de pulso, 1.340 ms de atraso do mouse); a forma 2 não (711 ms, 715 ms).

## Conferência (i)
`QEventLoop.exec()` ocioso solta o bloqueio do interpretador? Sim. Uma thread Python contou voltas por 1 s: com a principal em `join` 28.568.361; em `exec` 27.730.825 (razão 0,97, limite do "sim" 0,8); com a principal ocupada em Python 14.743.583 (razão 0,52, controle positivo abaixo de 0,7, a medida vale).

## Conferência (ii)
Medida no lote de 1.000 paredes sem janela, com uma thread vigia dormindo 1 ms em laço. A causa das paradas do F7 segue em aberto (lote 40, item 9); esta conferência descreve o que foi medido e não aponta culpado.
- Intervalo de troca de 5 ms (padrão): lote 1.982 ms; atraso do vigia p95 296 ms, máximo 758 ms.
- Intervalo de troca de 1 ms: lote 2.041 ms; atraso do vigia p95 190 ms, máximo 517 ms. Reduziu os atrasos do vigia nesta execução, sem eliminá-los; uma execução só.
- O módulo do IfcOpenShell importa as funções de soltar e retomar o bloqueio: sim.
- Chamadas longas (>= 100 ms) que soltam o bloqueio: abrir um IFC grande (141 ms) solta, a principal manteve 0,98 da taxa de voltas; gravar um IFC grande (485 ms) não solta, manteve 0,04. Isto responde só "solta ou não solta"; não se mostrou que isso cause as paradas do F7.
- "Tempo de bloqueio por função da API" (lote 9 §5.2): medido por função em `por_funcao` do `conferencias.json` (número de chamadas, duração máxima e soma, atraso do vigia). O atraso do vigia mostra qual função estava em curso quando ele acordou, não quem segurava o bloqueio; por isso não serve para apontar culpado, e a causa segue em aberto.

## Conferência (iii)
Com a thread da janela presa em C e o bloqueio preso por 790 ms, o desenho apresentou 49 quadros com maior intervalo de 17 ms (critério da T05: abaixo de 50 ms; pelo menos 20 quadros por segundo). O contêiner da viewport é a classe do PySide6 (`QWidget`, sem subclasse Python) e nenhum arquivo do fluxo instala filtro, liga sinal ou subclassifica componente de desenho.

## Parede com 150 aberturas
Decisão do PO depois do lote 4: aceitar na S03 que a janela parasse cerca de 0,2 s nessa parede e resolver na S04. Parede de 60 x 0,3 x 3,0 m com 150 aberturas (o MAB do lote 4) na base de 300 paredes; `mover` de 0,01 m, sinal alternado. Cálculo do desenho dela (`obimcore.malhas`, mediana de 3 chamadas): `malha_ms` = 214 ms, 3.012 triângulos. A edição refez essa malha (duração do comando 1,15 vezes `malha_ms`).
Portão (regra de parada (b), aprovada pelo PO em 2026-10-16): mediana do maior atraso de M5b na forma 1 abaixo da metade de `malha_ms` (107 ms).
Mediana / p95 / máximo das 3 rodadas de cada forma:
| | Forma 1 | Forma 2 |
|---|---|---|
| duração da edição | 247 / 250 / 250 ms | 250 / 253 / 253 ms |
| maior atraso do mouse | 2,1 / 7,9 / 8,5 ms | 212 / 219 / 220 ms |
| M5, maior intervalo entre quadros | 16,7 / 16,8 / 16,9 ms | 16,6 / 16,7 / 16,7 ms |
| pulso, maior intervalo | 11 / 25 / 27 ms | 214 / 220 / 220 ms |
| maior fatia | não se aplica | 214 / 219 / 220 ms (`obimcore.malhas`) |
Resultado: mediana do maior atraso na forma 1 de 2,1 ms (maior de uma rodada: 8,5 ms) contra o limite de 107 ms: o portão passa com folga nesta máquina. Segunda execução local, depois da correção da contagem de triângulos: `malha_ms` 218 ms, 3.012 triângulos, maior atraso do mouse na forma 1 de 5 / 5 / 16 ms (o revisor viu até 15,1 ms), na forma 2 de 224 / 219 / 221 ms. Na forma 2 a janela para pelo tempo do cálculo (cerca de 0,2 s), como esperado com uma peça só. Windows: a preencher com o run do CI (a folga sobre 100 ms de `malha_ms` lá é desconhecida).

## Recomendação para o ADR-004
Comando Python longo (muitas chamadas curtas, como criar 1.000 paredes): rodar em fatias na thread da janela (forma 2); cálculo de malha, em thread própria de geometria com o interpretador solto (mapa do ADR-004 §6), que é o que a parede de 150 aberturas mostrou funcionar (maior atraso de 8,5 ms).
Números (maior intervalo do pulso no controle, mediana / p95 / máximo): forma 1 502 / 1.127 / 1.196 ms; forma 2 719 / 724 / 725 ms. A forma 1 ganha na mediana e perde no p95 e no máximo (uma das 3 rodadas passou de 1 s); com a thread do mouse ela passa de 1 s (1.145 ms) e a forma 2 fica em 711 ms. A forma 2 é o pior caso estável: nunca fica abaixo da maior chamada única (cerca de 0,7 s) mas também não piora com outra thread. O M5b (mouse) vai ao lado: mediana 898 ms na forma 1 contra 14 ms na forma 2, maior atraso 1.344 contra 720 ms. A forma 3 (desenho em Python) parou 1,4 s e fica descartada.
Nos 3 jeitos o quadro do núcleo ficou em 17 a 18 ms, então a escolha vale só para a resposta ao mouse e ao pulso, não para o desenho. A regra de parada (a) não disparou (502 e 719 ms).
Mudaríamos de ideia se: a causa da piora da forma 1 fosse achada e o pulso dela, com a thread do mouse, ficasse abaixo de 500 ms (a forma 1 é mais simples de escrever); o Windows mostrar o contrário no CI; ou aparecer um jeito de partir a chamada de 0,7 s (derruba o pior caso da forma 2).
Custo: a forma 2 pede pontos de cessão em cada comando longo (código por comando, mantido no `fluxo_a`); a geometria em thread própria é uma tarefa já prevista no ADR-004 §6, fora desta. Quem decide é o PO no T19.

## Como reproduzir
Na pasta `prototypes/s04/fluxo_a`, com o `PYTHONPATH` apontando para a pasta que contém o módulo `obimcore` compilado (nunca na tela real):
- Formas 1 e 2, M5 e M5b: `xvfb-run -a python lote.py threads.json --base 300 --quantidade 1000 --rodadas 3`
- Conferências (i), (ii), (iii) e forma 3: `xvfb-run -a python conferencias.py conferencias.json --base 300 --quantidade 1000 --rodadas 3`
- Parede com 150 aberturas: `xvfb-run -a python -c "import ifcopenshell, lote; lote.main_pesada(['pesada.json', '--base', '300', '--aberturas', '150', '--rodadas', '3'])"`
- Oráculo: `OBIM_CI=1 OBIM_S04_T15_OBRIGATORIO=1 xvfb-run -a pytest -q tests/test_s04_t15d_parede_pesada.py`
