# Revisão Opus: F0-RG-09 parte 1 (teto de um valor isolado na régua de tempo, PR 117)

- Data: 2026-10-15
- PR: #117, ramo do PR em `d917462`
- Cartão: F0-RG-09 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achado B7)
- Revisor: Opus (não escreveu nada desta tarefa)
- Diff revisado: `prototypes/s04/medir_s04.py` (+7 −3), `tests/s04_fluxo_aux.py` (+4 −2), `tests/test_s04_metas.py` (+2 −1)
- `v2/` e `CLAUDE.md`: não mudam neste PR (conferido no diff contra `main`).
- Regra do PO (PO.md, 2026-10-15): "aquecer, 7 rodadas, mediana contra 100 ms, 16 ms só aviso na máquina do PO". Não pode ser afrouxada.

## Veredito: REPROVADO (só texto; a regra e os testes estão certos)

## O que está certo

1. **Mediana e régua estrita não mudam.** As linhas da mediana (`mediana >= limite`) e do p95 (`ESTRITO`) estão iguais nos dois lugares (`medir_s04.py:_erros` e `s04_fluxo_aux.veredito`). A regra do Rafael (mediana contra o limite) continua como estava. O M5 (maior intervalo < 100 ms) também não muda.
2. **O teto novo só mexe no valor isolado.** `max(3 × limite, 250 ms)` só troca o teto do M3 (limite 50 ms): de 150 para 250 ms. No M2 e no M2b (limite 200 ms) o teto continua 600 ms. É exatamente o caso que derrubou os PRs 103, 105 e 108: um valor solto de 187 ms com a mediana do M3 bem abaixo de 50 ms.
3. **A mesma conta nos dois lugares.** `_teto_ms` (ferramenta) e `teto_ms` (régua do fluxo A) são idênticas.
4. **Os 2 casos novos pegam a quebra nos dois lugares.** A tabela roda contra `s04_fluxo_aux.veredito` (sentinela que roda sempre) e contra `medir_s04.py` (teste parametrizado). Voltar o teto para `3 × limite` em qualquer um dos dois reprova o caso "187" naquele lugar. Tirar o teto reprova o caso "300". O caso antigo "m2 um valor em 650" continua reprovando (teto de 600).

## Correção exigida

1. **O contrato escrito ficou desatualizado.** O cabeçalho de `tests/test_s04_metas.py:11` (que é o contrato da ferramenta) ainda diz "nenhum valor >= 3 x limite", e `tests/test_s04_fluxo_a.py:6` diz "nenhum valor acima de TETO x limite". Trocar, nos dois, por "nenhum valor >= max(3 x limite, 250 ms)". Só texto; não mexer em nenhum caso nem número.

## Parte 2 do RG-09: recomendação (sem mudar a regra do Rafael)

O teste `test_intervalo_maximo_com_o_bloqueio_preso` (`tests/test_s04_viewport.py:77-90`) usa outra régua: 5 rodadas, e **qualquer** rodada com intervalo >= 100 ms reprova. O próprio teste da régua exige reprovar um único 210 ms em 5 rodadas. Esta noite ele derrubou o PR 109 (que nem toca no viewport): fase C com rodadas de 305 e 656 ms, as outras em torno de 32 ms.

Recomendação, alinhada à regra já aprovada pelo Rafael:

- (a) Uma rodada de aquecimento descartada e **7 rodadas** medidas.
- (b) Reprova se a **mediana** dos maiores intervalos de cada rodada for >= 100 ms. É a regra do Rafael, sem afrouxar.
- (c) Teto rígido de valor isolado: reprova se **2 ou mais** das 7 rodadas passarem de 200 ms. Um único pico de máquina passa; um travamento de verdade (a thread de desenho esperando a trava da janela, que fica presa ~750 ms em toda rodada) aparece em todas as rodadas e reprova pela mediana e pelo teto.
- (d) Manter as conferências de mediana < 50 ms e razão lote/parado < 3 como estão.
- (e) O teste da régua passa a exigir: um 210 ms em 7 aprova; dois 210 ms em 7 reprovam; mediana de 100 ms reprova.

Isso **não afrouxa o limite de 100 ms** (a mediana continua contra 100 ms). Muda só o critério do lote Opus 11 ("um valor isolado >= 100 ms reprova"), que não é decisão do Rafael. Por isso não precisa de decisão dele. Deve entrar como cartão próprio (parte 2), com revisão Opus, e ser avisado no resumo para o Rafael.

## Para o implementador

Arquivos permitidos: só o texto do cabeçalho de `tests/test_s04_metas.py` (linha 11) e de `tests/test_s04_fluxo_a.py` (linha 6). Depois volta para nova revisão Opus (T3).
