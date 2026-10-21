<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F0-S04-T29e: ensaio do arquivo pesado, 3 aberturas (relatório)

Rodado em 2026-10-21, tela virtual (xvfb), `main` em `016287e` (T29e já mesclado: medida `pos_emitir_mb` presente em `processo_malhas.py`; critérios (d′) e (e) na sonda). Módulo nativo recompilado do mesmo `main` (build 4,6 s, sem erro). 3 aberturas seguidas, bloco 250, `rodar_t33.sh 3 --bloco 250`, sob o cadeado da máquina, sem mudar nada de produção, de teste ou de sonda. Só números; nada do arquivo vai ao repositório. Saídas (fora do repositório): `~/openbim-medicao/2026-10-21-T29e/t33_r1.json`, `t33_r2.json`, `t33_r3.json`.

## Resultado por abertura
| | r1 | r2 | r3 |
|---|---|---|---|
| estado | concluido | concluido | concluido |
| tempo total (s) | 59,63 | 59,33 | 59,44 |
| blocos / filhos | 61 / 2 | 61 / 2 | 61 / 2 |
| reinícios | 1 (bloco 22, fonte `vigia`) | 1 (bloco 22, `vigia`) | 1 (bloco 22, `vigia`) |
| tempo perdido no reinício (s) (decisão + morte) | 20,92 (20,92 + 0,0003) | 20,91 (20,79 + 0,11) | 20,72 (20,61 + 0,12) |
| decisão do vigia (MB, base → decisão) | 1.935 → 2.958 | 1.832 → 2.888 | 1.821 → 2.834 |
| picos dos filhos (MB) | 2.958 / 4.921 | 2.888 / 4.978 | 2.834 / 4.929 |
| pico do pai (MB) | 1.046 | 1.050 | 1.052 |
| conta A (limite 6.000) | 5.967 | **6.028** | 5.982 |
| conta B | 5.588 | 5.704 | 5.609 |
| filhos vivos juntos (amostras) | 0 | 0 | 0 |
| peças com malha / sem malha / simplificadas / isoladas | 14.804 / 6 / 0 / 0 | igual | igual |
| triângulos / vértices | 8.595.714 / 22.816.436 | igual | igual |
| `tarde`, `decisao_tarde`, `nao feito`, `visto so no fim` | 0 | 0 | 0 |
| atraso do laço de eventos (M5): máx / p95 (ms) | 569,8 / 0,2 | 583,7 / 0,2 | 569,9 / 0,2 |

## Critérios (lote 65 §4)
Todos os valores abaixo são dos blocos com leitura. Os blocos 1 e 23 (1º de cada filho) não têm `max_mb`/`primeira_mb`; o bloco 22 (o do reinício) não tem `pos_emitir_mb`.

| critério | r1 | r2 | r3 |
|---|---|---|---|
| fonte `vigia` no bloco 22 | passou | passou | passou |
| `tarde_zero` | passou | passou | passou |
| (c) atraso de armar: bloco 22 (limite 0,5 s) | 0,031 | 0,046 | 0,047 |
| (c) pior atraso de armar em qualquer bloco (s) | 0,217 (bl. 41) | 0,223 (bl. 39) | 0,213 (bl. 58) |
| silêncio máximo (limite < 20 s): blocos / reinício | 12,80 (bl. 23) / 3,69 | 13,70 (bl. 23) / 3,66 | 12,73 (bl. 23) / 3,59 |
| (b) crescimento (`crescimento_ok`, limite ≤ 500 MB, fora do bloco 22 e dos 1os blocos): pior | 272,5 (bl. 60) passou | 203,7 (bl. 60) passou | 274,2 (bl. 17) passou |
| (b) no bloco 22 (excluído do critério) | 1.023,9 | 1.055,3 | 1.012,9 |
| `primeira_vs_base_ok` (±50 MB) | **falso** | **falso** | **falso** |
| (a) `max − primeira` nos blocos onde a primeira ficou fora de ±50 | 0,0 em todos | 0,0 em todos | 0,0 em todos |
| (a) pior `max − primeira` em qualquer bloco | 1.023,9 (bl. 22) | 1.055,3 (bl. 22) | 1.012,9 (bl. 22) |
| (d′) pior abs(base(N+1) − pos_emitir(N)) (limite 50) | 0,0 | 0,0 | 0,0 |
| (e) pior `pos_emitir − fim` (limite < 1.000) | 177,6 (bl. 23) | 177,5 (bl. 23) | 99,7 (bl. 23) |
| (e) maior leitura (limite < 6.000) | 4.296,7 (`pos_emitir`, bl. 23) | 4.355,6 (idem) | 4.252,5 (idem) |
| (d) antigo (informativo): pior abs(base(N+1) − fim(N)) | 177,6 (bl. 23) | 177,5 (bl. 23) | 99,7 (bl. 23) |
| (d) antigo: pares acima de 50 MB (de 59) | 1 | 1 | 1 |
| `base_vs_pos_emitir_ok` / `pos_emitir_vs_fim_ok` / `base_vs_fim_ok` | passou / passou / falso | passou / passou / falso | passou / passou / falso |

Blocos com a primeira leitura fora de ±50 MB da base (todos no 2º filho, todos para **baixo**; diferença primeira − base, em MB; nesses blocos (b) = diferença e (c) = atraso):
- r1: bloco 24 (−220,6; atraso 0,191 s), 25 (−2.149,5; 0,195 s), 44 (−248,2; 0,207 s).
- r2: bloco 24 (−2.190,9; 0,193 s), 25 (−76,5; 0,192 s), 40 (−244,6; 0,208 s).
- r3: bloco 24 (−1.734,1; 0,193 s), 25 (−365,3; 0,169 s), 26 (−62,8; 0,205 s), 40 (−54,4; 0,205 s).

## Pontos fora do critério, só registrados
- A conta A da r2 (6.028 MB) ficou **acima** do limite de 6.000 MB (r1: 5.967; r3: 5.982). Não é um dos critérios de parada da sonda; é o limite de memória do produto. Não interpretei.
- O atraso do laço de eventos (M5) deu 570 a 584 ms nas 3 aberturas (meta M5 < 200 ms); o p95 é 0,2 ms. Nesta rodada o campo veio preenchido (na 2ª rodada veio vazio).
- Nenhum critério de parada da sonda reprovou além do `primeira_vs_base_ok`, que já falhava na rodada anterior. Nada foi afrouxado.
- `err` de cada abertura contém só o aviso "No stream support: No module named 'lark'" e o de localidade (não colados aqui).

## O que NÃO prova
- Tela virtual (software, máquina dividida) **não prova a meta de 60 s** nem a placa: os 59,3 a 59,6 s ficam logo abaixo de 60 s, mas é software; a placa deu 52,7 s no T24 e a medida oficial é lá.
- 3 aberturas do mesmo arquivo, mesma configuração: mostram repetição, não cobrem outros arquivos.
- Não mede Windows nem macOS (não se aplicam aqui).
- O atraso do laço de eventos aqui é o da sonda, em software, não a régua M5 do fluxo A.
