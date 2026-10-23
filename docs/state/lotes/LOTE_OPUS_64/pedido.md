<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_64: revisão dos PRs 204, 210 e 211 (T30a2 corrigido, T30a3, T30d2) (F0-S04)
Pedido do líder (2026-10-20), **classe T3, revisão Opus em lote, esforço médio**. Responda **aprovado ou reprovado com lista numerada** por PR. Escreva só `docs/state/lotes/LOTE_OPUS_64/resultado.md`; não edite mais nada, não implemente, não faça merge, não leia `~/openbim-medicao`, nenhum IFC. Você não escreveu nenhum destes três (o autor do oráculo T30d2 é outro agente).

## Contexto fechado
`docs/state/lotes/LOTE_OPUS_62/resultado.md` §6 e `LOTE_OPUS_63/resultado.md` (seus pareceres anteriores, em especial §3 sobre o 204 e os 11 pontos do T30d2); cartões `docs/state/arquivo/F0-S04/cartoes/F0-S04-T30a2.md`, `T30a3.md`, `T30d2.md`. Código nos ramos remotos (`git fetch origin`):
- **PR 204** `s04-t30a2-sublotes`: `cena.cpp` e `cena.h` (correções do lote 63: índices por `memcpy`, `nao_partido` separado em dois casos, recalculado no `sem`). CI verde (`linux`, `windows`).
- **PR 210** `s04-t30a3-dados-lote` (parte do 204): `ponte_viewport.cpp`, acessor `Cena.dados_lote(seq)`. Ponta a97da0e; o dtype de vértice foi refeito sem terceiro `nb::eval` (o teste `test_formato_malha.py` conta dois). CI verde.
- **PR 211** `s04-t30d2-oraculo` (parte do 199, já no `main`): `tests/test_s04_t30d2_sublotes_oraculo.py` novo e adaptação de `tests/test_s04_t30a1_sem_oraculo.py`. Com 204 e 210 juntos: 13 passam, 1 pulada (contadores `nao_partidos` e `pecas_maiores_que_c` ainda não chegam ao Python: T30b); no `main` puro, 10 passam, 2 xfail estrito, 2 puladas.

## Pontos
1. **204:** os itens 1 a 3 do lote 63 estão resolvidos? Algo novo no diff (limite C, fronteira de peça, sequência devolvida, `ger_`, `bytes_copia`)? Bloqueia ou sugestão.
2. **210:** o acessor mexe só na ponte, devolve cópias somente leitura, falha com `ValueError` em sequência inexistente? Há risco de vida do buffer ou de bloqueio de mutex? Aprovar sem mudar o contrato de formato (`test_formato_malha`)?
3. **211:** as 11 exigências do cartão estão cobertas, nenhuma afrouxada, o item 11 (memória) só em Linux, a adaptação do T30d1 não mudou nenhum número? Quais marcadores `@AINDA_NAO` ainda existem e quem os tira e quando?
4. **Ordem de merge** (204, 210, 211) e se o 204 pode entrar antes dos oráculos como no lote 63, ou só junto.
5. **Pontos para o T30b:** o que o oráculo ainda não cobre (contadores, reenvio por posição, instantâneo) e precisa entrar no cartão.

## Entrega
Veredito por PR; respostas 1 a 5; perguntas ao PO (só o que é dele); resumo de 5 linhas em português simples, sem siglas; linha do LOG. Resultado em português claro; retorno final em caveman (curto). Não aprove provisoriamente.
