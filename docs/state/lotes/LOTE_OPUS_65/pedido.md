<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_65: revisão dos PRs 217, 218, 219 e 222 (T30b1, T30b2, T30d3, T34) e decisão do T29d (F0-S04)
Pedido do líder (2026-10-20), **classe T3, revisão Opus em lote, esforço médio**. Responda **aprovado ou reprovado com lista numerada** por PR. Escreva só `docs/state/lotes/LOTE_OPUS_65/resultado.md`; não edite mais nada, não implemente, não faça merge, não leia `~/openbim-medicao`, nenhum IFC. Você não escreveu nenhum destes (autores do oráculo e do teste são agentes diferentes dos implementadores).

## Contexto fechado
`LOTE_OPUS_62/resultado.md` §5 e §6, `LOTE_OPUS_63/resultado.md` §3 pontos 1 e 7, `LOTE_OPUS_64/resultado.md` §2 ponto 5; cartões `docs/state/cards/F0-S04/F0-S04-T30b1.md`, `T30b2.md`, `T30d3.md`, `T34.md`, `T29d.md`; relatório `reports/F0-S04-T34.md` (no PR 222) e `reports/F0-S04-T30c-dados-reais.md` (T2_VALE nos 3 IFC do PO). Código nos ramos remotos (`git fetch origin`):
- **PR 217** `s04-t30b1-cena` (T30b1, reescopado: só instantâneo coerente e contadores; `cena.h`, `motor.h` 2 campos, `ponte_viewport.cpp` 1 linha; +16/−6). CI verde.
- **PR 218** `s04-t30b2-motor` (T30b2, empilhado sobre o 217, base `s04-t30b1-cena`): `motor.h` reenvio por posição, entrada atômica; `cena.cpp` só a retirada do `++ger_` da troca. 61 testes existentes passam; o oráculo T30d3 ainda não foi rodado contra ele.
- **PR 219** `s04-t30d3-oraculo` (T30d3, 311 linhas): `tests/test_s04_t30d3_reenvio_oraculo.py`. No `main` puro: 7 passam, 2 pulam (contadores, `geracao`), 5 `@AINDA_NAO`. Cena do teste reduzida a 387 MiB (os 5 tamanhos do lote 62 §6.4).
- **PR 222** `s04-t34-estavel` (T34): `tests/test_s04_t15c_conferencias.py`, forma de medir pela mediana (5 e 3 repetições); 30/30 execuções no Linux; mutação reprova.

## Pontos
1. **218 (T30b2):** critérios 1 a 7 do cartão; mutex (nenhuma trava nova; `Motor::m_` não segurado ao ler o instantâneo; `mc_` intocado; ordem `Motor::m_` → `DadosCena::m_` → `mc_`); entrada atômica (sequência da placa só chega a S com o lote novo e os trocados completos no mesmo quadro); perda de contexto e `limpar()` no meio de uma troca; troca repetida; fatia em múltiplo de 28; `ORCAMENTO_*` e `OBIM_QUADRO_MS` intactos; `triangulos_na_placa` nunca abaixo de cena − peça antiga. Rode o oráculo do 219 contra o 218 (os `@AINDA_NAO` devem virar XPASS) e relate.
2. **217 (T30b1):** o instantâneo e os contadores; o motor ainda lê `geracao()` e `proximo()` separados antes do 218 (o 218 migra).
3. **219 (T30d3):** o oráculo cobre os itens 1 a 7 do cartão, nenhum número afrouxado, os 5 `@AINDA_NAO` listados e quem os tira (autor do oráculo, depois do 217 e do 218 no `main`); cena de 387 MiB aceita? O teste de `geracao` pula para sempre: **expor `geracao` em `estatisticas()` (quem, qual cartão)** ou aceitar que o critério "troca não sobe `ger_`" fique só no diff e no piso de triângulos?
4. **222 (T34):** os números (0,7; 700 ms) não mudaram, nenhum caso saiu, o controle continua controlando (mutação), a mediana de 5 e 3 repetições é uma forma legítima de medir; os valores únicos do `conferencias.json` principal deixaram de ser conferidos nesses dois limites: aceitável? No Windows a conferência de 700 ms fica por conta do CI.
5. **T29d (cartão novo):** a base do vigia está no ponto certo? A premissa da regra (d) do lote 63 vale por construção? Leitura do líder: `bloco_fim` mede antes de `emitir`, o `bloco` seguinte mede a base depois de `emitir` e de `_RETIDO.clear()`. Decida o critério para o ensaio continuar e o que o autor do oráculo exige; nenhum número do produto muda. Diga se o ensaio já gravado basta ou precisa de nova rodada.
6. **Ordem de merge** de 217, 218, 219 e 222 e quem tira os marcadores `@AINDA_NAO` (e quando); se o 218 pode entrar antes do 219 ou só junto.

## Entrega
Veredito por PR; respostas 1 a 6; perguntas ao PO (só o que é dele); resumo de 5 linhas em português simples, sem siglas; linha do LOG. Resultado em português claro; retorno final em caveman (curto). Não aprove provisoriamente.
