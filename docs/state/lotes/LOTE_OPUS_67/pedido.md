<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_67: revisão do PR 235 (T34b: guardar a mensagem do teste instável do T15c) (F0-S04)
Pedido do líder (2026-10-21), **classe T3, revisão Opus, esforço médio**. Responda **aprovado ou reprovado com lista numerada**. Escreva só `docs/state/lotes/LOTE_OPUS_67/resultado.md` (num worktree seu, sem commit; informe o caminho); não implemente, não faça merge, não leia `~/openbim-medicao` nem IFC. Você não escreveu este PR.

## Contexto fechado
`LOTE_OPUS_66/resultado.md` §2 ponto 1 (seu parecer sobre a falha 29/30), cartão `docs/state/cards/F0-S04/F0-S04-T34b.md`, `docs/state/reports/F0-S04-T34.md`. Código no ramo remoto `s04-t34b-mensagem` (`git fetch origin`; `git diff origin/main...origin/s04-t34b-mensagem`):
- `tests/test_s04_t15c_conferencias.py` (+27): `registrar()` (print e `GITHUB_STEP_SUMMARY` só se definido) com as 5 razões (join, ocupada), as 3 janelas, `razao_exec` e `resposta`; `@guarda_mensagem` nos testes (i) e (iii) grava a mensagem inteira da falha antes de subir.
- `docs/state/reports/F0-S04-T34b.md` (+9). Bateria de 10 execuções: 10/10 passaram; `razao_exec` 0,97 a 1,13, nenhuma entre 0,3 e 0,8; a parte (b) do cartão (mediana de `razao_exec`) **não foi feita**, por não ter sido necessária.

## Pontos
1. Nenhum número mudou (0,7; 700 ms; 0,3; 0,8; 50 ms; 20 quadros/s); nenhum caso removido; a falha continua subindo (o decorador não engole exceção, não troca falha por pulo).
2. `registrar()` e o decorador não alteram o resultado do teste em nenhum caminho (nem quando `GITHUB_STEP_SUMMARY` não existe ou não é gravável).
3. A parte (b) fora do PR é aceitável (cartão: só se `razao_exec` inconclusiva voltar)?
4. Windows: só com o CI (os testes do T15c rodam no `windows-viewport-a`). Algum risco no Windows (caminho do arquivo de resumo, codificação)?
5. Aprovar para mesclar?

## Entrega
Veredito; respostas 1 a 5; perguntas ao PO (só o que é dele); resumo de 3 linhas em português simples, sem siglas; linha do LOG. Retorno final em caveman. Não aprove provisoriamente.
