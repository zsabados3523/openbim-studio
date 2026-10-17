<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S04-T15: em que thread rodar um comando Python longo (relatório para o ADR-004)

Máquina deste relatório (as formas e as conferências: uma execução; a parede com 150 aberturas: duas execuções, rotuladas; 2026-10-16): Linux 7.0.0-38, Intel Core i5-12600KF (16 threads), 23 GB, `xvfb-run -a`, desenho `gl`, base de 300 paredes, lote de 1.000 paredes, 3 rodadas por forma. Cada célula é mediana / p95 / máximo das 3 rodadas (com 3 valores o p95 é interpolado). Linha "Windows" em cada seção: segunda máquina, o Windows do CI do GitHub (job `windows-viewport-a` do [run 38997337768](https://github.com/zsabados3523/openbim-studio/actions/runs/38997337768), 2026-10-17), desenho `d3d11` por software, mesmas bases e 3 rodadas, uma execução numa máquina compartilhada da nuvem; lá o quadro parado já é de 32 ms. Os números do Linux são só os da máquina local acima. O número oficial do lote 9 §2.3, com placa de vídeo real, fica pendente: só se mede na máquina do PO, com o ok dele (aqui o desenho é por software). Os JSON brutos saem de `lote.py`, `conferencias.py` e `lote.main_pesada`.

## Resumo para o PO
Medi três jeitos de rodar um comando longo em duas máquinas (Linux local; Windows da nuvem). O desenho do 3D seguiu fluido nos dois bons (17 ms entre quadros no Linux, 33 ms no Windows, igual ao parado); no jeito antigo, de referência, parou até 1,4 s no Linux e 0,6 s no Windows.
Sem o mouse sintético, a janela fica surda na rodada típica (mediana) por 0,5 s no Linux e 0,14 s no Windows se o comando roda numa thread à parte (forma 1), e por 0,7 s e 0,8 s se roda em fatias na janela (forma 2); na pior rodada, 1,2 s e 0,15 s na forma 1, 0,7 s e 0,8 s na forma 2.
Com o mouse sintético a forma 1 piorou no Linux (1,1 s contra 0,5 s na mediana) e no Windows (0,42 s contra 0,14 s); a forma 2 ficou igual nos dois; mais threads Python não foram medidas.
A parede com 150 aberturas, com o desenho calculado fora do bloqueio, não parou a janela na forma 1: maior atraso de até 16 ms no Linux (duas execuções) e 3 ms no Windows, contra 214 a 236 ms do cálculo.
Os dois sistemas discordam e a escolha é apertada: no Windows a forma 1 foi melhor no pulso e no pior atraso do mouse (só o atraso mediano do mouse foi maior, 89 contra 14 ms); preferi a forma 2 só porque sua pior rodada ficou entre 0,7 e 0,83 s nos dois sistemas, contra até 1,3 s da forma 1 no Linux; com 3 rodadas por máquina e sem placa de vídeo real a margem é pequena, e a decisão é sua.

## Forma 1
Comando em thread Python; a janela fica no laço de eventos. Lote de 1.000 paredes (duração 2.203 / 2.262 / 2.269 ms; sem o mouse sintético: 2.137 ms).
- M5, maior intervalo entre quadros do núcleo: 17 / 18 / 18 ms (parado: 18 / 19 / 19 ms); nenhuma janela de 1 s abaixo de 62 quadros.
- Pulso (temporizador de 10 ms na janela), maior intervalo: 1.145 / 1.325 / 1.345 ms (controle, sem mouse: 502 / 1.127 / 1.196 ms).
- Fatias: não se aplica.
- Windows: duração 2.690 / 2.786 / 2.796 ms; M5 33 / 33 / 33 ms (parado 32); janela de 1 s com no mínimo 58 quadros; pulso 420 / 493 / 501 ms (rodadas 501, 420, 236; controle sem mouse: 135 / 152 / 153 ms, rodadas 153, 135, 115).

## Forma 2
Comando na thread da janela, cedendo ao Qt a cada 8 ms ou mais, entre as operações. Mesmo lote (duração 2.237 / 2.260 / 2.262 ms).
- M5, maior intervalo entre quadros: 17 / 17 / 17 ms (parado: 18 / 19 / 20 ms); nenhuma janela de 1 s abaixo de 62 quadros.
- Pulso, maior intervalo: 711 / 716 / 716 ms (controle: 719 / 724 / 725 ms).
- Fatias: cerca de 180 por rodada; maior fatia 710 / 715 / 716 ms, de uma única chamada da API que a forma 2 não consegue partir.
- Windows: duração 2.658 / 2.715 / 2.721 ms; M5 33 / 33 / 33 ms (parado 32); no mínimo 58 quadros por janela de 1 s; pulso 785 / 823 / 828 ms (controle: 810 / 825 / 827 ms, rodadas 810, 697, 827); cerca de 200 fatias por rodada; a maior fatia (785 / 823 / 828 ms) foi sempre a chamada `spatial.assign_container`, uma única chamada que a forma 2 não parte. Isto diz qual chamada era a maior fatia, não por que a forma 1 foi melhor ou pior.

## Forma 3
Referência: forma 1 com a viewport Python da S03 (sem portão; esperava-se que reprovasse). Lote de 2.099 / 2.118 / 2.201 ms.
- M5, maior intervalo entre quadros: 1.212 / 1.418 / 1.441 ms (rodadas: 843, 1.441, 1.212 ms), com janelas de 1 s de 0 a 6 quadros; parado ela desenha 120 a 127 quadros em 2 s.
- Pulso, maior intervalo: 859 / 936 / 945 ms.
- Windows: M5 maior intervalo 374 / 589 / 613 ms (rodadas 613, 374, 334), com janelas de 1 s de 2 a 24 quadros; parado 122 a 123 quadros em 2 s; pulso 275 / 511 / 537 ms. Parou menos que no Linux, mas bem acima dos 32 ms do núcleo.
- Mostra o tamanho do problema que as formas 1 e 2 resolvem: o desenho fora do Python mantém 17 a 18 ms.

## M5b
Atraso entre um evento de mouse sintético (um a cada 20 ms, agendado desde o início do lote) e o seu tratamento na janela. Sem portão no lote (registro, lote 9 §2.3).
| | Forma 1 | Forma 2 |
|---|---|---|
| mediana do atraso | 898 / 957 / 964 ms | 14 / 14 / 14 ms |
| p95 do atraso | 1.293 / 1.311 / 1.313 ms | 604 / 607 / 607 ms |
| maior atraso | 1.340 / 1.344 / 1.344 ms | 715 / 720 / 720 ms |
| eventos por rodada | 114, 108, 111 | 111, 112, 114 |
Windows, mesma tabela (mediana / p95 / máximo): atraso mediano forma 1 89 / 116 / 119 ms e forma 2 14 / 15 / 15 ms; p95 do atraso 379 / 383 / 383 e 652 / 693 / 697 ms; maior atraso 438 / 509 / 517 e 788 / 824 / 828 ms; eventos por rodada 140, 128, 135 e 133, 132, 137, todos tratados. Controle (pulso, maior intervalo): forma 1 135 / 152 / 153 ms; forma 2 810 / 825 / 827 ms. Com a thread do mouse (pulso): forma 1 420 ms, forma 2 785 ms. No Windows a forma 1 foi melhor no controle e no pior atraso do mouse; a mediana do atraso do mouse é maior nela (89 contra 14 ms).
Nas duas formas todo evento agendado foi tratado. Para comparar as formas vale o CONTROLE (sem a thread que posta o mouse, maior intervalo do pulso de 10 ms, mediana / p95 / máximo das 3 rodadas): forma 1 502 / 1.127 / 1.196 ms (rodadas 361, 1.196, 502); forma 2 719 / 724 / 725 ms. A forma 1 ganha na mediana e perde no p95 e no máximo. Efeito da thread do mouse, medido (pulso maior, com mouse contra controle): forma 1 1.145 contra 502 ms; forma 2 711 contra 719 ms. O motivo não foi medido; nenhuma função é apontada.
Regra de parada (a), aprovada pelo PO em 2026-10-16: se a mediana do maior intervalo do pulso no controle passar de 1.000 ms nas DUAS formas, parar e levar ao PO. Aqui deu 502 e 719 ms: não dispara. Critério do lote 9 §5.1 ("janela surda por mais de 1 s em operações comuns"): a forma 1 com a thread do mouse passa de 1 s (1.145 ms de pulso, 1.340 ms de atraso do mouse); a forma 2 não (711 ms, 715 ms). No Windows nenhuma das duas passa de 1 s (pulso máximo 501 e 828 ms; atraso máximo do mouse 517 e 828 ms) e a regra (a) também não dispara (controle 135 e 810 ms).

## Conferência (i)
`QEventLoop.exec()` ocioso solta o bloqueio do interpretador? Sim. Uma thread Python contou voltas por 1 s: com a principal em `join` 28.568.361; em `exec` 27.730.825 (razão 0,97, limite do "sim" 0,8); com a principal ocupada em Python 14.743.583 (razão 0,52, controle positivo abaixo de 0,7, a medida vale). Windows: em `join` 15.925.890; em `exec` 16.068.958 (razão 1,01); principal ocupada 7.946.605 (razão 0,50): sim, a medida vale.

## Conferência (ii)
Medida no lote de 1.000 paredes sem janela, com uma thread vigia dormindo 1 ms em laço. A causa das paradas do F7 segue em aberto (lote 40, item 9); esta conferência descreve o que foi medido e não aponta culpado.
- Intervalo de troca de 5 ms (padrão): lote 1.982 ms; atraso do vigia p95 296 ms, máximo 758 ms.
- Intervalo de troca de 1 ms: lote 2.041 ms; atraso do vigia p95 190 ms, máximo 517 ms. Reduziu os atrasos do vigia nesta execução, sem eliminá-los; uma execução só.
- O módulo do IfcOpenShell importa as funções de soltar e retomar o bloqueio: sim.
- Chamadas longas (>= 100 ms) que soltam o bloqueio: abrir um IFC grande (141 ms) solta, a principal manteve 0,98 da taxa de voltas; gravar um IFC grande (485 ms) não solta, manteve 0,04. Isto responde só "solta ou não solta"; não se mostrou que isso cause as paradas do F7.
- Windows (mesmo lote de 1.000 paredes, uma execução): troca de 5 ms: lote 2.248 ms, atraso do vigia p95 49 ms, máximo 224 ms; troca de 1 ms: lote 2.253 ms, p95 30 ms, máximo 77 ms. Importa as funções de soltar e retomar: sim. Abrir um IFC grande (363 ms) solta, a principal manteve 0,86 da taxa; gravar (696 ms) não solta, manteve 0,05. Aqui também só "solta ou não solta".
- "Tempo de bloqueio por função da API" (lote 9 §5.2): medido por função em `por_funcao` do `conferencias.json` (número de chamadas, duração máxima e soma, atraso do vigia). O atraso do vigia mostra qual função estava em curso quando ele acordou, não quem segurava o bloqueio; por isso não serve para apontar culpado, e a causa segue em aberto.

## Conferência (iii)
Com a thread da janela presa em C e o bloqueio preso por 790 ms, o desenho apresentou 49 quadros com maior intervalo de 17 ms (critério da T05: abaixo de 50 ms; pelo menos 20 quadros por segundo). O contêiner da viewport é a classe do PySide6 (`QWidget`, sem subclasse Python) e nenhum arquivo do fluxo instala filtro, liga sinal ou subclassifica componente de desenho. Windows: bloqueio preso por 1.380 ms, 82 quadros, maior intervalo 32 ms (critério: abaixo de 50 ms); contêiner `QWidget`, sem subclasse Python.

## Parede com 150 aberturas
Decisão do PO depois do lote 4: aceitar na S03 que a janela parasse cerca de 0,2 s nessa parede e resolver na S04. Parede de 60 x 0,3 x 3,0 m com 150 aberturas (o MAB do lote 4) na base de 300 paredes; `mover` de 0,01 m, sinal alternado. Cálculo do desenho dela (`obimcore.malhas`, mediana de 3 chamadas): `malha_ms` = 214 ms na primeira execução (tabela abaixo); a contagem de 3.012 triângulos vem da segunda execução (`malha_ms` 218 ms), depois de corrigir a contagem: o `pesada.json` da primeira ainda registra 1.004, pela contagem antiga. A edição refez essa malha (duração do comando 1,15 vezes `malha_ms`).
Portão (regra de parada (b), aprovada pelo PO em 2026-10-16): mediana do maior atraso de M5b na forma 1 abaixo da metade de `malha_ms` (107 ms).
Primeira execução, mediana / p95 / máximo das 3 rodadas de cada forma:
| | Forma 1 | Forma 2 |
|---|---|---|
| duração da edição | 247 / 250 / 250 ms | 250 / 253 / 253 ms |
| maior atraso do mouse | 2,1 / 7,9 / 8,5 ms | 212 / 219 / 220 ms |
| M5, maior intervalo entre quadros | 16,7 / 16,8 / 16,9 ms | 16,6 / 16,7 / 16,7 ms |
| pulso, maior intervalo | 11 / 25 / 27 ms | 214 / 220 / 220 ms |
| maior fatia | não se aplica | 214 / 219 / 220 ms (`obimcore.malhas`) |
Resultado: mediana do maior atraso na forma 1 de 2,1 ms (maior de uma rodada: 8,5 ms na primeira execução, 16 ms na segunda) contra o limite de 107 ms: o portão passa com folga nesta máquina. Segunda execução local (3 rodadas por forma): `malha_ms` 218 ms, 3.012 triângulos, maior atraso do mouse, mediana / p95 / máximo, na forma 1 de 5 / 15 / 16 ms (o revisor viu até 15,1 ms) e na forma 2 de 221 / 223 / 224 ms. Na forma 2 a janela para pelo tempo do cálculo (cerca de 0,2 s), como esperado com uma peça só. Windows (CI, 3 rodadas por forma): `malha_ms` 236 ms (acima dos 100 ms exigidos), 3.012 triângulos; portão: metade de `malha_ms` = 118 ms. Forma 1: duração da edição 325 / 356 / 360 ms, maior atraso do mouse 3 / 3 / 3 ms (passa com folga), pulso 16 / 17 / 17 ms. Forma 2: duração 300 / 303 / 303 ms, maior atraso do mouse 248 / 254 / 254 ms, maior fatia 242 / 249 / 249 ms (`obimcore.malhas`), como no Linux.

## Recomendação para o ADR-004
Comando Python longo (muitas chamadas curtas, como criar 1.000 paredes): a preferência é rodar em fatias na thread da janela (forma 2), mas é uma preferência apertada e os dois sistemas medidos discordam. Cálculo de malha, em thread própria de geometria com o interpretador solto (mapa do ADR-004 §6), que é o que a parede de 150 aberturas mostrou funcionar (maior atraso de até 16 ms no Linux em duas execuções, 3 ms no Windows).
Números (maior intervalo do pulso no controle, mediana / p95 / máximo): Linux, forma 1 502 / 1.127 / 1.196 ms e forma 2 719 / 724 / 725 ms; Windows, forma 1 135 / 152 / 153 ms e forma 2 810 / 825 / 827 ms. Com a thread do mouse (pulso, mediana): Linux, forma 1 1.145 ms e forma 2 711 ms; Windows, forma 1 420 ms e forma 2 785 ms. A forma 1 ganhou no Windows no pulso (controle e com o mouse) e no pior atraso do mouse, e no controle do Linux na mediana, mas teve atraso mediano do mouse maior no Windows (89 contra 14 ms); perdeu no Linux com o mouse e no p95 e máximo do controle. A forma 2 foi pior na rodada típica do Windows, mas sua pior rodada ficou entre 0,7 e 0,83 s nos dois sistemas, sempre perto da maior chamada única (cerca de 0,7 s no Linux, 0,8 s no Windows, `spatial.assign_container`); a da forma 1 foi de 0,15 s a 1,3 s conforme sistema e mouse. A preferência pela forma 2 se apoia nessa variação menor entre os sistemas, não numa vitória dela em números: são 3 rodadas por máquina, sem placa de vídeo real, e o Windows é uma máquina compartilhada da nuvem. O M5b (mouse) vai ao lado: atraso mediano 898 contra 14 ms no Linux e 89 contra 14 ms no Windows; maior atraso 1.344 contra 720 ms e 517 contra 828 ms. A forma 3 (desenho em Python) parou 1,4 s no Linux e 0,6 s no Windows, e fica descartada.
Nos 3 jeitos o quadro do núcleo ficou igual ao parado (17 a 18 ms no Linux; 32 a 33 ms no Windows), então a escolha vale só para a resposta ao mouse e ao pulso, não para o desenho. A regra de parada (a) não disparou em nenhum dos dois sistemas (controle 502 e 719 ms; 135 e 810 ms).
Mudaríamos para a forma 1 se: o número com placa real também a favorecer; ou a causa da piora dela com a thread do mouse fosse achada e o pulso ficasse abaixo de 500 ms no Linux (ela é mais simples de escrever); ou aparecer um jeito de partir a chamada de 0,7 a 0,8 s (derruba o pior caso da forma 2, e então a forma 2 passaria a valer mais).
Custo: a forma 2 pede pontos de cessão em cada comando longo (código por comando, mantido no `fluxo_a`); a geometria em thread própria é uma tarefa já prevista no ADR-004 §6, fora desta. Quem decide é o PO no T19.

## Como reproduzir
Na pasta `prototypes/s04/fluxo_a`, com o `PYTHONPATH` apontando para a pasta que contém o módulo `obimcore` compilado (nunca na tela real):
- Formas 1 e 2, M5 e M5b: `xvfb-run -a python lote.py threads.json --base 300 --quantidade 1000 --rodadas 3`
- Conferências (i), (ii), (iii) e forma 3: `xvfb-run -a python conferencias.py conferencias.json --base 300 --quantidade 1000 --rodadas 3`
- Parede com 150 aberturas: `xvfb-run -a python -c "import ifcopenshell, lote; lote.main_pesada(['pesada.json', '--base', '300', '--aberturas', '150', '--rodadas', '3'])"`
- Oráculo: `OBIM_CI=1 OBIM_S04_T15_OBRIGATORIO=1 xvfb-run -a pytest -q tests/test_s04_t15d_parede_pesada.py`
