<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_67: resultado (revisão Opus, esforço médio, 2026-10-21)
Revisor: Opus. Não escrevi o PR 235 nem os oráculos do T15c e do T34. Li o pedido, `LOTE_OPUS_66/resultado.md` §2 ponto 1, o cartão `F0-S04-T34b.md`, o relatório `F0-S04-T34.md` e o diff `git diff origin/main...origin/s04-t34b-mensagem` (depois de `git fetch origin`; base `main` = f10af50). Não li `~/openbim-medicao` nem nenhum IFC.

## Veredito: **REPROVADO** (uma correção pequena, de 3 a 4 linhas)
1. **Obrigatório.** `registrar()` muda o resultado quando `GITHUB_STEP_SUMMARY` está definido mas não pode ser gravado (pasta inexistente ou arquivo só de leitura): o `open(..., "a")` levanta `FileNotFoundError` / `PermissionError`. Como `registrar()` é chamado **dentro das preparações** `rep` (linhas 99 e 100) e `conf` (linha 116), essa exceção derruba como erro os 6 testes que usam `conf`, inclusive os que passariam. Isso contraria o ponto 2 do pedido e o espírito do cartão ("não muda nenhuma conferência"). Correção: envolver só a gravação no resumo em `try: ... except OSError as e: print(f"T34b: resumo do CI não gravado ({e})", flush=True)`, mantendo o `print` da mensagem antes, como já está. Nenhum outro trecho muda.
2. **Obrigatório.** No relatório `F0-S04-T34b.md`, acrescentar uma linha dizendo que foi conferido o caso do resumo ausente/não gravável (o resultado dos testes não muda) e repetir a falha forçada depois da correção 1.

Depois das correções 1 e 2, não preciso de nova bateria de 10: a correção não toca em nenhuma conferência. Basta o CI (`linux` e `windows`) verde e o diff mostrado ao Opus de novo (revisão curta do mesmo PR, em `reports/`).

### Evidência (rodado no Linux, ambiente `openbim`)
O módulo nativo `obimcore` não está compilado no meu worktree, então **não rodei** `tests/test_s04_t15c_conferencias.py` inteiro (o resultado 10/10 é o do implementador). Conferi `registrar()` e `@guarda_mensagem` importando-os do arquivo do ramo num teste de bancada fora do repositório (scratchpad), com 5 casos: falha de asserção, passa, `pytest.skip`, `pytest.fail` e chamada direta de `registrar()`:
- sem `GITHUB_STEP_SUMMARY`: 2 falharam (asserção e `pytest.fail`), 2 passaram, 1 pulou: igual a sem o decorador; a mensagem saiu no `print`;
- com arquivo gravável: mesmo resultado; o resumo recebeu a mensagem inteira (`mensagem completa X` e a explicação `assert 1 == 2` do pytest);
- com `/nao/existe/summary.md` e com arquivo só de leitura: **3 falharam, 1 passou**: a chamada direta de `registrar()` (que é o que as preparações `rep` e `conf` fazem) passou a falhar. Nos testes com falha de asserção a falha continuou subindo (com o `PermissionError` por cima do `AssertionError`), então a falha não se perde, só fica mais confusa.

## Respostas aos pontos 1 a 5
1. **Sim.** O diff só acrescenta linhas (36 inserções, nenhuma remoção): 0,7; 700 ms; 0,3; 0,8; 50 ms e 20 quadros por segundo estão iguais, nenhum caso saiu. O decorador pega só `AssertionError`, grava e faz `raise` de novo: não engole, não troca falha por pulo (`pytest.skip` e `pytest.fail` passam direto, conferido). `functools.wraps` mantém a assinatura, então o pytest continua injetando `conf` e `rep` (a bateria 10/10 e minha bancada mostram isso).
2. **Não, num caminho.** Sem a variável e com arquivo gravável, nada muda. Com a variável apontando para lugar não gravável, as preparações passam a dar erro (item 1 do veredito). No CI do GitHub o arquivo sempre existe e é gravável, então o risco prático é baixo, mas o pedido exige "em nenhum caminho", e a correção é trivial. Observação sem exigência: `rep` agora lê `join`, `ocupada`, `quadros` e `maior_intervalo_ms` antes dos testes; se faltasse uma dessas chaves, o erro sairia na preparação em vez de no teste. Como os próprios testes (i) e (iii) já leem essas chaves sem proteção, o resultado (não passar) é o mesmo; aceito assim.
3. **Sim.** O cartão condiciona a parte (b) a `razao_exec` inconclusiva voltar a aparecer. Na bateria de 10, `razao_exec` ficou entre 0,97 e 1,13, longe de 0,3 a 0,8. Com a mensagem agora guardada, se a falha voltar ela diz qual conferência foi, e aí se abre a parte (b). Pedido ao líder: deixar o cartão T34b com a parte (b) anotada no "próximo passo" (ou num cartão filho) em vez de fechá-lo inteiro.
4. **Risco baixo.** O passo do `windows-viewport-a` roda em `bash` e o próprio `ci.yml` já grava em `"$GITHUB_STEP_SUMMARY"` (linha 398), então o caminho chega certo ao Python; `open` aceita o caminho do Windows; a codificação está fixada em `utf-8`, que é o que o resumo do GitHub espera; o fim de linha `\r\n` do Windows não atrapalha o Markdown. O `print` sai pela captura do pytest (`-rsP`, sem `-s`), que já mostra os acentos de outros testes; `json.dumps` escreve `não` como `não` (só estético). A correção 1 também protege o Windows se o arquivo estiver preso por outro processo. Confirmação real: só com o CI verde.
5. **Ainda não.** Mesclar depois das correções 1 e 2, com `linux` e `windows` verdes e a revisão curta do Opus sobre o diff corrigido.

## Perguntas ao PO
Nenhuma. É ajuste técnico, sem decisão de meta, escopo ou regra.

## Resumo para o PO (3 linhas, sem siglas)
1. A mudança que guarda a mensagem do teste que falhava por acaso está quase certa: nenhum número foi mexido e a falha continua aparecendo.
2. Falta um cuidado: se o arquivo onde ela escreve o resumo não puder ser gravado, hoje os testes quebram à toa; são 3 ou 4 linhas para corrigir.
3. Depois disso volta para uma conferência rápida e pode entrar; a medição extra que estava prevista não foi necessária, porque o valor ficou longe da faixa duvidosa.

## Linha do LOG
`2026-10-21 | F0-S04-T34b | LOTE_OPUS_67 (opus, médio) | 235 REPROVADO: números e casos intactos, decorador não engole falha (conferido em bancada: skip e pytest.fail passam direto); registrar() derruba as preparações rep/conf quando GITHUB_STEP_SUMMARY não é gravável (FileNotFoundError/PermissionError, 3 em vez de 2 falhas na bancada); correções: try/except OSError só na gravação do resumo + linha no relatório; sem nova bateria; parte (b) fica pendente no cartão (razao_exec 0,97 a 1,13); arquivo inteiro não rodado no revisor (obimcore não compilado) | docs/state/lotes/LOTE_OPUS_67/resultado.md`
