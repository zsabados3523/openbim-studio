<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S04-T15: em que thread rodar um comando Python longo (relatório para o ADR-004)

Máquina deste relatório (uma execução, 2026-10-16): Linux 7.0.0-38, Intel Core i5-12600KF (16 threads), 23 GB, `xvfb-run -a`, desenho `gl`, base de 300 paredes, lote de 1.000 paredes, 3 rodadas por forma. Cada célula é mediana / p95 / máximo das 3 rodadas (com 3 valores o p95 é interpolado). Números do CI (Linux e Windows): a preencher com o run do CI. Os JSON brutos saem de `lote.py`, `conferencias.py` e `lote.main_pesada`.

## Resumo para o PO
Medi três jeitos de rodar um comando longo; em todos o desenho do 3D segue fluido, menos na forma de referência (a antiga), que parou até 1,4 s.
Se o comando roda numa thread à parte (forma 1), o mouse fica sem resposta cerca de 0,9 s por vez no lote de 1.000 paredes; se roda em fatias na janela (forma 2), a resposta típica é de 14 ms, com paradas de até 0,7 s.
A parede com 150 aberturas, com o cálculo do desenho feito fora do bloqueio, não parou a janela: pior atraso de 2 ms contra 214 ms do cálculo (o portão aprovado pedia menos de 107 ms).
Recomendo comandos longos em fatias na thread da janela e o cálculo do desenho em thread própria; o Windows ainda precisa ser medido pelo teste automático na nuvem.
A decisão final é sua no T19 (ADR-001 e ADR-004).

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
Nas duas formas todo evento agendado foi tratado. O que explica a espera longa da forma 1 não foi medido aqui.

## Conferência (i)
`QEventLoop.exec()` ocioso solta o bloqueio do interpretador? Sim. Uma thread Python contou voltas por 1 s: com a principal em `join` 28.568.361; em `exec` 27.730.825 (razão 0,97, limite do "sim" 0,8); com a principal ocupada em Python 14.743.583 (razão 0,52, controle positivo abaixo de 0,7, a medida vale).

## Conferência (ii)
Medida no lote de 1.000 paredes sem janela, com uma thread vigia dormindo 1 ms em laço. A causa das paradas do F7 segue em aberto (lote 40, item 9); esta conferência descreve o que foi medido e não aponta culpado.
- Intervalo de troca de 5 ms (padrão): lote 1.982 ms; atraso do vigia p95 296 ms, máximo 758 ms.
- Intervalo de troca de 1 ms: lote 2.041 ms; atraso do vigia p95 190 ms, máximo 517 ms. Reduziu os atrasos do vigia nesta execução, sem eliminá-los; uma execução só.
- O módulo do IfcOpenShell importa as funções de soltar e retomar o bloqueio: sim.
- Chamadas longas (>= 100 ms) que soltam o bloqueio: abrir um IFC grande (141 ms) solta, a principal manteve 0,98 da taxa de voltas; gravar um IFC grande (485 ms) não solta, manteve 0,04. Isto responde só "solta ou não solta"; não se mostrou que isso cause as paradas do F7.

## Conferência (iii)
Com a thread da janela presa em C e o bloqueio preso por 790 ms, o desenho apresentou 49 quadros com maior intervalo de 17 ms (critério da T05: abaixo de 50 ms; pelo menos 20 quadros por segundo). O contêiner da viewport é a classe do PySide6 (`QWidget`, sem subclasse Python) e nenhum arquivo do fluxo instala filtro, liga sinal ou subclassifica componente de desenho.

## Parede com 150 aberturas
Decisão do PO depois do lote 4: aceitar na S03 que a janela parasse cerca de 0,2 s nessa parede e resolver na S04. Parede de 60 x 0,3 x 3,0 m com 150 aberturas (o MAB do lote 4) na base de 300 paredes; `mover` de 0,01 m, sinal alternado. Cálculo do desenho dela (`obimcore.malhas`, mediana de 3 chamadas): `malha_ms` = 214 ms, 1.004 triângulos. A edição refez essa malha (duração do comando 1,15 vezes `malha_ms`).
Portão (regra de parada (b), aprovada pelo PO em 2026-10-16): mediana do maior atraso de M5b na forma 1 abaixo da metade de `malha_ms`.
| | Forma 1 | Forma 2 |
|---|---|---|
| duração da edição | 247 / 250 / 250 ms | 250 / 252 / 253 ms |
| maior atraso do mouse (por rodada) | 2,0 / 2,1 / 8,5 ms | 220 / 207 / 212 ms |
| maior intervalo entre quadros (M5) | 17 / 17 / 16 ms | 17 / 17 / 17 ms |
| pulso, maior intervalo | 11 / 11 / 27 ms | 220 / 208 / 214 ms |
| maior fatia | não se aplica | 220 / 208 / 214 ms (`obimcore.malhas`) |
Resultado: mediana na forma 1 de 2,1 ms contra o limite de 107 ms: o portão passa com folga nesta máquina. Na forma 2 a janela para pelo tempo do cálculo (cerca de 0,2 s), como esperado com uma peça só. Windows: a preencher com o run do CI (a folga sobre 100 ms de `malha_ms` lá é desconhecida).

## Recomendação para o ADR-004
Comando Python longo (muitas chamadas curtas, como criar 1.000 paredes): rodar em fatias na thread da janela (forma 2); cálculo de malha, em thread própria de geometria com o interpretador solto (mapa do ADR-004 §6), que é o que a parede de 150 aberturas mostrou funcionar (2 ms de atraso).
Números: forma 2 tem resposta típica de 14 ms contra 898 ms da forma 1; o pior caso da forma 2 (cerca de 0,7 s) é de uma chamada única que não se parte, e o da forma 1 chega a 1,34 s. A forma 3 (desenho em Python) parou 1,4 s e fica descartada.
Nos 3 jeitos o quadro do núcleo ficou em 17 a 18 ms, então a escolha vale só para a resposta ao mouse e ao pulso, não para o desenho.
Mudaríamos de ideia se: a causa dos 0,9 s da forma 1 fosse achada e o M5b dela caísse para menos de 50 ms (a forma 1 é mais simples de escrever); o Windows mostrar o contrário no CI; ou aparecer um jeito de partir a chamada de 0,7 s (derruba o pior caso da forma 2).
Custo: a forma 2 pede pontos de cessão em cada comando longo (código por comando, mantido no `fluxo_a`); a geometria em thread própria é uma tarefa já prevista no ADR-004 §6, fora desta. Quem decide é o PO no T19.

## Como reproduzir
Na pasta `prototypes/s04/fluxo_a`, com o `obimcore` no `PYTHONPATH` (nunca na tela real):
- Formas 1 e 2, M5 e M5b: `xvfb-run -a python lote.py threads.json --base 300 --quantidade 1000 --rodadas 3`
- Conferências (i), (ii), (iii) e forma 3: `xvfb-run -a python conferencias.py conferencias.json --base 300 --quantidade 1000 --rodadas 3`
- Parede com 150 aberturas: `xvfb-run -a python -c "import ifcopenshell, lote; lote.main_pesada(['pesada.json', '--base', '300', '--aberturas', '150', '--rodadas', '3'])"`
- Oráculo: `OBIM_CI=1 OBIM_S04_T15_OBRIGATORIO=1 xvfb-run -a pytest -q tests/test_s04_t15d_parede_pesada.py`
