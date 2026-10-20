<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_66: revisão dos PRs 222, 227, 228 e 229 (T34 corrigido, T29e implementação e oráculo, T30b3) e leitura da medição na placa (F0-S04)
Pedido do líder (2026-10-20), **classe T3, revisão Opus em lote, esforço médio**. Responda **aprovado ou reprovado com lista numerada** por PR. Escreva só `docs/state/lotes/LOTE_OPUS_66/resultado.md` (num worktree seu, sem commit; informe o caminho); não implemente, não faça merge, não leia `~/openbim-medicao`, nenhum IFC. Você não escreveu nenhum destes.

## Contexto fechado
`LOTE_OPUS_65/resultado.md` (seus pareceres: §1 correção do 222; §2 ponto 3 e §4); cartões `docs/state/cards/F0-S04/F0-S04-T34.md`, `T29e.md`, `T30b3.md`. Código nos ramos remotos (`git fetch origin`):
- **PR 222** `s04-t34-estavel` (T34 corrigido, ponta 5de620d): `tests/test_s04_t15c_conferencias.py` + `reports/F0-S04-T34.md`. Agora as conferências do desenho (maior_intervalo < 50, quadros ≥ 20 × gil/1000, contêiner PySide6) valem na execução principal e em cada uma das 3 repetições de `rep["iii"]`; ≥ 700 ms pela mediana. 30/30 passaram na rodada final (mediana das medianas 0,496; maior amostra isolada 0,578). **Aviso do autor:** uma bateria anterior com o mesmo código teve 29/30 (uma falha em `test_t15c_i_...` com as 5 razões do controle normais, 0,48 a 0,51; a mensagem não foi guardada; causa desconhecida; na rodada final não houve nenhuma).
- **PR 227** `s04-t29e-pos-emitir` (T29e implementação, +46/−12 depois do code-simplifier): `processo_malhas.py`, `carregador.py`, `sonda_ensaio_t33.py`.
- **PR 228** `s04-t29e-oraculo` (base do 227): `tests/test_s04_t29e_pos_emitir_oraculo.py` (179 linhas), 23 passam e 1 pula (Windows).
- **PR 229** `s04-t30b3-geracao` (T30b3): `geracao` exposta, `proximo()`/`Cursor` removidos. Pergunta do implementador: `DadosCena::geracao()` ficou sem uso (o motor usa `instantaneo()`): tirar em cartão à parte?

## Pontos
1. **222:** a correção 1 do lote 65 foi cumprida; números iguais; mutação reprova. A falha isolada 29/30 sem mensagem guardada: aceita, pede cartão à parte para `razao_exec`/resposta, ou pede nova bateria (de quantas execuções)? Windows com o CI.
2. **227:** a medida `pos_emitir_mb` e os critérios (d′) e (e) como decididos no lote 65 §4: `pos_emitir_mb` logo depois de `emitir`, dentro da PRÓXIMA mensagem `bloco` (e do `fim` no último); o pai só grava em `_reg`; nenhum tipo de mensagem novo; vigia, G, teto, bloco e reinício intocados; o (d) antigo continua calculado e gravado.
3. **228:** o oráculo cobre os 4 itens do §4 item 4; casos de borda (d′) 50 passa e 50,1 para, (e) 999 passa e 1.000 para (no teste: `fim` = 1000 e `pos_emitir` 1999 passa, 2000 para), leitura 6.000 para; a leitura "o registro do bloco N guarda a medida feita depois de `emitir` do bloco N (a mensagem chega no bloco N+1)" é a certa para a sonda? Nenhum número afrouxado?
4. **229:** `Totais::ger` sob `DadosCena::m_`, sem trava nova, `mc_` intacto, nenhum `nb::eval` novo; o teste de `geracao` do T30d3 passa sem edição. Tirar `DadosCena::geracao()` agora ou em cartão à parte?
5. **Medição na placa (somente leitura de um resumo meu):** o T30b2 está no `main` (cb434a5). O líder mediu a troca de parede na RTX 3070 do PO; os números estão em `reports/F0-S04-T30-placa.md` se o PR já estiver mesclado (senão o líder cola o resumo no pedido). Diga se a meta M2b (< 200 ms, p95, parede criada e do arquivo) fecha e o que fazer se não.
6. **Ordem de merge** de 222, 227, 228 e 229.

## Entrega
Veredito por PR; respostas 1 a 6; perguntas ao PO (só o que é dele); resumo de 5 linhas em português simples, sem siglas; linha do LOG. Resultado em português claro; retorno final em caveman. Não aprove provisoriamente.
