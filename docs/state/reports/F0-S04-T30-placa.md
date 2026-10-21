<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F0-S04-T30: troca de parede na placa real depois do T30b2 (M2b)
Medido em 2026-10-20, das 18:55 às 19:04, na tela real do PO (:0, RTX 3070, driver 580.178.04, OpenGL 4.6, `software: false`), com o `main` em cb434a5 (T30a2 sub-lotes, T30b1, T30b2 reenvio por posição e troca sem subir `ger_`, T30d3 oráculo). Sonda `prototypes/s04/sondas/sonda_m2b.py` (a mesma do T22), 3 rodadas por caso, sob o cadeado da máquina. Arquivos do PO liberados em 2026-10-17 (A17): só números aqui. JSON em `~/openbim-medicao/2026-10-20-placa/` (fora do repositório). Nenhuma rodada deu erro.

## Resultado (ms por troca, do comando ao quadro apresentado; mediana das 3 rodadas e pior valor)
| Caso | Triângulos | Parede do arquivo: mediana · p95 · pior | Parede criada: mediana · p95 · pior | Antes (T22, 2026-10-17) |
|---|---|---|---|---|
| Sintética de 3.000 peças | 38.400 | 32,7 · 49,1 · 49,7 | 33,0 · 49,4 · 82,8 | 49 |
| 25 MB | 501.168 | 32,6 · 48,9 · 49,6 | 32,9 · 49,6 · 81,6 | 399 |
| Detalhado (casarão) | 8.803.050 | 48,9 · 49,4 · 65,2 | 48,9 · 49,4 · 78,4 | 6.748 |

Medianas das 3 rodadas por caso: sintética 32,7 / 32,7 / 32,8; 25 MB 32,6 / 32,6 / 32,6; detalhado 49,0 / 48,9 / 48,7 (muito estáveis). Trocas por rodada: 200, 90 e 30.

## Leitura
A meta M2b (menos de 200 ms) fecha nos três casos com folga: o p95 não passou de 49,6 ms em nenhum caso nem tipo de parede (calculado sobre todas as trocas das 3 rodadas, do JSON fora do repositório); o pior valor isolado foi 65,2 ms na parede do arquivo (detalhado) e 82,8 ms na parede criada (sintética), e a mediana ficou em 32 a 49 ms, que é o tempo de 2 ou 3 quadros de 16,7 ms. A troca passou a custar o mesmo em todos os tamanhos (antes crescia com a cena: 399 ms no 25 MB, 6.748 ms no detalhado). Parede do arquivo = parede que já vinha no IFC; parede criada = parede nova feita no programa (critério 9 do T30). Isto confirma a decisão T-2 (sub-lotes de até 8 MiB + reenvio só do sub-lote trocado) na placa.

## O que isto não mostra
É uma medição da sonda `sonda_m2b` (fluxo A, parede com 12 triângulos trocada em IFC aberto), em uma máquina; a medição oficial completa da S04 (juiz estrito, passos A a P do roteiro) não foi refeita. Memória do pesado (T29/T29e) não faz parte desta rodada.
