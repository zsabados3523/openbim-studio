<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S04-T29: segunda medição (com reinícios gravados), PESADO na placa real
Data: 2026-10-21. Só medição; nada alterado no produto; sem commit. Complementa `F0-S04-T29-placa-memoria.md`.

## Segunda medição (com reinícios gravados)
- `main` em `f10af50` (PR 234, T29f: `medir.py` grava `reinicios`, `registro_reinicio`, `desenho`; conferido no código). Módulo nativo não mudou (nada recompilado). Mesmo método: PESADO, tela real `:0`, sem xvfb, 8 fios, `--bloco 250`, sob `flock`, 3 rodadas, `timeout 600`. Saídas: `/home/rafael/openbim-medicao/2026-10-21-placa-memoria-2/` (última linha de `sondas_PESADO_{1,2,3}.json`). RAM disponível antes e depois: 18 GB. RustDesk ativo e intocado (pode afetar `fps` e `atraso_*`).
- Placa: `glxinfo`: NVIDIA GeForce RTX 3070. Campo `desenho` nas 3 rodadas: `info` = "OpenGL NVIDIA Corporation NVIDIA GeForce RTX 3070/PCIe/SSE2 4.6.0 NVIDIA 580.178.04", `software` = **false**.

| campo | rod. 1 | rod. 2 | rod. 3 | mediana | meta | passou? |
|---|---|---|---|---|---|---|
| `abrir_s` | 51,15 | 51,35 | 51,24 | 51,24 | ≤ 60 | sim x3 |
| `pico_pai_mb` | 925 | 925 | 978 | 925 | n/a | n/a |
| `pico_filho_mb` | 4.970 | 4.860 | 4.980 | 4.970 | n/a | n/a |
| `pico_somado_mb` (campo da meta; pior das 3) | 5.895 | 5.785 | 5.958 | 5.895 (pior 5.958) | < 6.000 | sim x3 |
| `soma_amostrada_max_mb` (informativo) | 5.402 | 5.328 | 5.359 | 5.359 | n/a | n/a |
| `atraso_max_ms` | 45,0 | 46,4 | 61,5 | 46,4 | < 200 | sim x3 |
| `atraso_p95_ms` | 0,2 | 0,2 | 0,2 | 0,2 | < 200 | sim x3 |
| `fps` | 60,4 | 57,8 | 56,4 | 57,8 | n/a | n/a |
| `simplificadas.quantidade` | 0 | 0 | 0 | 0 | n/a | n/a |
| `sem_malha` | 6 | 6 | 6 | 6 | n/a | n/a |
| `filhos_sobrando` | 0 | 0 | 0 | 0 | 0 | sim x3 |

Estado "concluido" nas 3.

### Reinícios (campos `reinicios` e `registro_reinicio`)
| rod. | `reinicios` | bloco | fonte | `base_mb` | `decisao_mb` | `atraso_armar_s` | `decisao_tarde` | `max_silencio_s` |
|---|---|---|---|---|---|---|---|---|
| 1 | [22] | 22 | vigia | 1.796,5 | 2.857,9 | 0,0021 | false | 3,72 |
| 2 | [22] | 22 | vigia | 1.826,3 | 2.882,2 | 0,0061 | false | 3,83 |
| 3 | [22] | 22 | vigia | 1.836,1 | 2.871,2 | 0,0016 | false | 3,74 |

Um reinício por rodada, no bloco 22, pela fonte "vigia". **Tempo perdido:** não existe campo com esse nome; o registro traz só `atraso_armar_s` e `max_silencio_s` (maior silêncio do filho, 3,7 a 3,8 s). Não calculei nem estimei tempo perdido.

## O que NÃO prova
- Não prova que o reinício causou a queda de memória (sem rodada sem reinício nesta versão para comparar); a 1ª medição (`main` anterior) deu `pico_somado_mb` 5.863 de mediana, e esta 5.895: diferença de 32 MB, dentro da variação já vista entre rodadas (até 100 MB).
- Só PESADO, só esta máquina, só Linux; 3 rodadas não são estatística.
- `fps` e `atraso_*` podem ter sido afetados pelo RustDesk.
- Não prova saída igual byte a byte nem conforto de uso.
