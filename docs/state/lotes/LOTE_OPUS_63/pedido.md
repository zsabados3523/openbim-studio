<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_63: revisão dos PRs 199, 200 e 204 (T30d1, T30a1, T30a2) e pontos abertos do T30 (F0-S04)
Pedido do líder (2026-10-20), **classe T3, revisão Opus em lote, esforço médio**. Responda **aprovado ou reprovado com lista numerada** por PR. Escreva só `docs/state/lotes/LOTE_OPUS_63/resultado.md`; não edite mais nada, não implemente, não faça merge, não leia `~/openbim-medicao`, nenhum IFC.

## Contexto fechado
`docs/state/lotes/LOTE_OPUS_62/resultado.md` (seu parecer anterior, §6), cartões `docs/state/arquivo/F0-S04/cartoes/F0-S04-T30.md`, `T30a1.md`, `T30a2.md`, `T30d1.md`. Código nos ramos remotos (`git fetch origin`): PR 199 `s04-t30d1-oraculo` (só `tests/test_s04_t30a1_sem_oraculo.py`), PR 200 `s04-t30a1-sem` (só `prototypes/s04/obimcore/nucleo/cena.cpp`), PR 204 `s04-t30a2-sublotes` (`cena.cpp` e `cena.h`, parte do ramo do 200). CI verde nos três (`linux`, `windows`).

## Pontos
1. **Reescopo (a):** "troca não sobe `ger_`" e "instantâneo coerente" saíram do T30a1 e vão para o T30b (sozinhos quebrariam o motor, que só reenvia quando `ger_` sobe). Concorda? Algo do lote 62 §6.1 ficou sem dono?
2. **Critério 5 do T30a2 (b):** a fração partível deu 0,75% na cena do T27 (peça única de enchimento) e 100% nas 41.600 paredes; 8 de 13 lotes do T27 não partem (contador `nao_partidos`). O líder mandou implementar com a leitura "lote sem fronteira fica inteiro". Confirme a leitura e diga o que medir nos dados reais (peças por lote) para a decisão T-2 valer.
3. **`nao_partidos` (c):** não ficou exposto ao Python (`Estatisticas` está em `motor.h`): fica para o T30b. De acordo?
4. **Oráculo T30d1 (d):** supõe um lote por chamada e falha com sub-lotes em duas verificações (contagem e sequência). Deve ser adaptado no T30d2 por autor diferente do implementador do T30a2. Confirme o plano e liste o que o T30d2 deve exigir.
5. **Conferência bit a bit (e):** só existe comparação de imagem pixel a pixel via Python. Pede acessor de depuração? Se sim, em qual cartão.
6. **Veredito numerado** de 200, 204 e 199 (aprovado/reprovado; arquivo/linha; bloqueia ou sugestão). Diga a ordem de merge e se o marcador `@AINDA_NAO` do 199 deve ser removido (por quem e quando).
7. **Ensaio do pesado (T33b, `reports/F0-S04-T33b.md`):** reinício certo (bloco 22, vigia, sem "tarde"), conta A 5.921 MB; só falhou `primeira_vs_base_ok`: em 4 blocos do 2º filho a memória *caiu* (de -75 a -2.031 MB) e a base do vigia ficou acima da memória real. Isso pode atrasar a detecção de um crescimento depois da queda? A base do vigia deve acompanhar a queda (ex.: mínimo entre a base e a leitura)? É mudança no produto do T29 (cartão T3 novo, autor do oráculo diferente) ou a regra atual basta? Não afrouxe número.

## Entrega
Veredito por PR; respostas 1 a 5; perguntas ao PO (só o que é dele); resumo de 5 linhas em português simples, sem siglas; linha do LOG. Resultado em português claro; retorno final em caveman (curto). Não aprove provisoriamente.
