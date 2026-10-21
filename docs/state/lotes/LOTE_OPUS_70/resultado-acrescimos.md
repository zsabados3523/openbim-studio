<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_70: revisão curta dos acréscimos aos oráculos (PRs 245, 246, 247; opus, esforço médio, 2026-10-21)
Sou o mesmo revisor do `resultado.md`. Não escrevi os acréscimos: são de outro Opus, o autor do oráculo.

Commits revistos:
- 245: f11b884;
- 246: b5204b4, com head 03b36d1 (traz o 245 e o main por merge);
- 247: e00eed4.

Implementações usadas só para rodar os testes, copiadas por um tempo no meu worktree e já desfeitas:
- V1: d653422;
- P1: 82b52c6, com o `obimcore` compilado no rascunho com o C++ do P1.

Os mutantes também foram temporários. `git status` limpo, salvo os dois arquivos do lote 70.

## Veredito
| PR | Veredito |
|---|---|
| 245 | **REPROVADO**: 1 item |
| 246 | **APROVADO** (head 03b36d1) |
| 247 | **APROVADO** (e00eed4) |

## Evidência (Linux, `xvfb-run -a`, chaves `OBIM_S04_V1_OBRIGATORIO=1` e `OBIM_S04_P1_OBRIGATORIO=1`)
- Com as implementações de referência e `--runxfail`: **36 de 36, 3 de 3 execuções**, ~50 s cada.
- Mutantes que o oráculo antigo não pegava, agora todos pegos:

| Mutante | Antes | Agora |
|---|---|---|
| Veredito: 1 rodada > 200 ms tolerada; sem a exigência de janelas ≥ 20; sem a regra 3x parado; `<=` no 200 e no limite do M5; `4_controle_1s` com `<=`; `4_surda` com `<` (6 mutantes) | nenhum pego | **6 de 6 pegos** |
| Trava: outra thread entra no C++ com um leitor ativo | não pego | **pego** pelo teste novo do 247 |
| Mista: espera ocupada com `processEvents` no lugar de `QEventLoop.exec` + sinal | não pego | **pego** (`exec` = 0) |
| Mista: sem `join` | não pego | **pego** (`lote-geometria` viva depois de `medir`) |

- O teste novo do empréstimo que falha (246) cobre os dois caminhos: tipo errado devolvido (`TypeError`, 1 saída) e entrada recusada (o erro sobe, 0 saídas). Com o C++ antigo ele fica em falha esperada.
- A reentrada com `espera=None` (247) roda numa thread com `join(2)`: se travar, falha e não trava o pytest.

## 1. PR 245: REPROVADO
1. **A espera artificial de 0,2 s depois do `emit` (`pos_s`) reprova uma implementação que o cartão aceita.** Para pegar a falta do `join`, o espião faz a thread de geometria dormir 0,2 s depois do `emit`, e isso vale em toda execução do ensaio. Um `join` correto passa então a custar 200 ms na janela.
   - Mutante válido que testei: reiniciar o relógio da fatia logo depois do `exec()`, antes do `join`. O cartão diz só "join da thread" e "a espera não é fatia".
   - Resultado: **reprovado** em `test_v1_regra_2_..._a_espera_nao_e_fatia`, com uma fatia de 200,8 ms contra o limite de 150 ms. Com geometria de verdade a thread termina logo depois do `emit`, e esses 200 ms não existem.
   - Ou seja, o acréscimo apertou o contrato sem querer.
   - Correção barata: usar `pos_s` só numa execução própria em que as fatias não são conferidas (por exemplo a do composto, com `mouse=False`) e conferir `vivas` logo depois dela; nas outras execuções do ensaio, `pos_s = 0`. Isso também deixa a prova do `join` mais firme. Hoje, depois da malha, o comando ainda faz ~100 operações da `api` (cerca de 100 a 200 ms no Windows), o que pode encostar nos 0,2 s. No composto o que sobra depois da última malha são ~6 operações.

As reescritas para caber em 400 linhas **são equivalentes**:
- `_ok` como `lambda`: com "erro" o `pytest.fail` levanta; sem, devolve `r`, igual ao de antes;
- `_dentro` como `lambda`: igual;
- `QTimer(interval=5, timeout=tenta)`: o PySide6 aceita propriedade e sinal no construtor, e o espião repassa `**k`. A prova é que os testes das tentativas (≥ 5 e ≥ 3 dentro da espera) passam com a referência.

Contagem: o arquivo tem 400 linhas, no limite.

## 2. XPASS estrito com implementação parcial
Esperado, por teste, e não é defeito.
- Com `sessao_modelo.py` e o C++ antigo: os 12 testes da trava viram XPASS (vermelho), e os 7 do `obimcore` seguem em falha esperada, incluindo o novo do empréstimo que falha.
- Com o V1 inteiro, todos os testes do V1 viram XPASS.

Os marcadores saem teste por teste, pelo autor do oráculo, no ramo da implementação. `AINDA_NAO` continua sendo importado pelo arquivo do veredito: os marcadores do V1 saem dos dois arquivos no mesmo commit.

## 3. Ordem
- O 246 já traz o 245 por merge (head 03b36d1). Mesclar o 245 primeiro (depois da correção do item 1) e depois o 246 com o main trazido.
- Se o 246 for mesclado antes, ele leva junto o 245 **sem** a correção: não fazer.
- O 247 independe dos outros.
- Antes do merge, conferir `linux` e `windows` verdes.

## 4. Para o PO (3 linhas)
1. Os casos a mais que pedi nos testes foram feitos e pegam todos os erros que antes passavam.
2. Dois dos três pacotes estão aprovados; no terceiro, uma espera artificial do teste reprovaria um programa correto, e a correção é pequena.
3. Nada para você decidir.

## 5. Linha do LOG
`2026-10-21 | F0-S04-V1, P1 | LOTE_OPUS_70, acréscimos (opus, médio, T3 revisão) | PR 246 APROVADO (7 casos do veredito: 6 de 6 mutantes pegos; empréstimo que falha) e PR 247 APROVADO (leitor em outra thread; reentrada com espera=None); PR 245 REPROVADO 1 item (pos_s de 0,2 s reprova join correto fora do relógio da fatia; aplicar só numa execução sem conferência de fatia); reescritas do 245 equivalentes; referências V1 d653422 e P1 82b52c6 com --runxfail 36/36 em 3 de 3 | docs/state/lotes/LOTE_OPUS_70/resultado-acrescimos.md`

## Confirmação do 245 (commit 2ffe756; o 246 o traz em 31d0487)
**PR 245 APROVADO** (2ffe756). Com isso, **PR 246 APROVADO** com head 31d0487, que só acrescenta o merge do 245 corrigido.

O que mudou de f11b884 para 2ffe756:
- `pos_s` vale 0 por padrão. Só passa a 0,2 s na execução do composto, que roda com `mouse=False` e não confere fatias.
- `vivas` é lido logo depois do composto, e `pos_s` volta a 0 em seguida.
- `f.cmds[:] = []` faz o mesmo que o `clear()` de antes.
- Nenhum caso afrouxado e nenhum número mudou. O arquivo continua com 400 linhas.

Conferido no Linux, sob `xvfb-run -a`, com as chaves ligadas e o V1 de referência (d653422) com `--runxfail`:
- mista e veredito: **15 de 15, 3 de 3 execuções**, ~47 s cada;
- mutante "relógio da fatia reiniciado antes do `join`" (válido pelo cartão): **passa**, os 2 testes da regra 2;
- mutante "espera ocupada no lugar do laço e do sinal": **pego** (`exec` = 0);
- mutante "sem `join`": **pego** (3 threads `lote-geometria` vivas depois do composto);
- o mutante do 247 (outra thread com leitor ativo) segue **pego**.

O resto do que está acima continua valendo: XPASS estrito por teste, os marcadores do V1 saem dos dois arquivos juntos, e a ordem é 245 → 246 (com o main trazido) → 247 (independente), com `linux` e `windows` verdes.

Para o PO: o último ajuste nos testes foi feito e conferido; os três pacotes de testes estão aprovados.

Linha do LOG: `2026-10-21 | F0-S04-V1 | LOTE_OPUS_70, confirmação (opus, médio, T3 revisão) | PR 245 APROVADO em 2ffe756 (pos_s só no composto; mutante do relógio antes do join passa; espera ocupada e falta de join pegos; referência V1 15/15 em 3 de 3); PR 246 APROVADO em 31d0487 | docs/state/lotes/LOTE_OPUS_70/resultado-acrescimos.md`
