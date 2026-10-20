<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F0-S04-T30c: sub-lotes nos IFC reais do PO (só números)
Rodada de 2026-10-20 em tela virtual (xvfb, `LIBGL_ALWAYS_SOFTWARE=1`), com a sonda `sonda_t30c.py` do PR 220 (commit d7e0548) e o `obimcore` compilado do `main` com o PR 204 (sub-lotes de até C = 8 MiB). Arquivos liberados pelo PO em 2026-10-17 (A17), fora do repositório; aqui só números: nenhum GlobalId, nome de peça ou conteúdo. JSON brutos em `~/openbim-medicao/2026-10-20-T30c/` (fora do repositório).

| Arquivo (peso) | Lotes antes → depois | Não ladrilham | Paredes (classe: peças) | Maior sub-lote de parede | Parede em sub-lote > C | Peças > C por classe |
|---|---|---|---|---|---|---|
| casa simples | 7 → 10 | 0 | IfcWallStandardCase: 30 | 8.293.308 B | 0 | nenhuma |
| casarão (detalhado) | 104 → 153 | 0 | IfcWall: 422 | 8.378.632 B | 0 | IfcFurniture 10, IfcDoor 4, IfcBuildingElementProxy 2 |
| biblioteca (pesado) | 132 → 172 | 0 | IfcWall: 232 | 8.373.364 B | 0 | IfcFurniture 20 |

C = 8.388.608 B. Incoerências: 0 nos três.

## Regra de decisão do lote 63 (escrita antes dos dados)
(i) nenhuma parede em sub-lote maior que C: **vale nos três** (0 paredes; nenhuma parede é, ela mesma, maior que C). (ii) nenhum lote que não ladrilha tem parede: **vale** (nenhum lote deixou de ladrilhar). Veredito da sonda nos três: **T2_VALE**. A decisão T-2 (teto de lote C = 8 MiB dentro de `cena`) está confirmada nos dados reais; o cartão da divisão parcial (204, item 5) não precisa ser aberto.

## O que isso não mostra
Tempo de troca e quadros por troca (o motor reenvia por posição só depois do T30b2) e nada de placa de vídeo. A leitura de (ii) segue a do lote 63 (lote que não ladrilha **e** passa de C); o JSON traz também o total sem filtro de tamanho, que deu 0.
