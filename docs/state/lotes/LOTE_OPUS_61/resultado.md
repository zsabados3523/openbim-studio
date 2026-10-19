<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_61: resultado da revisão da diferença do T29 (oráculo atualizado, retrabalho do 189, commits de marcadores)
Revisor: Opus (2026-10-19), classe T3, esforço médio. O Opus não escreveu nenhum dos três PRs. Especificação: lote 59 §2 e lote 60 (pareceres do Opus).

## 0. Vereditos
| PR | ramo (ponta revisada) | veredito |
|---|---|---|
| **185** (oráculo T29b) | `s04-t29b-oraculo` (c95b123) | **REPROVADO** (achado 1.1, um só, pequeno) |
| **188** (reinício T29a) | `s04-t29a-reinicio` (7537247) | **APROVADO**: 3f66f85 igual (mesmo SHA), merge do oráculo sem nada a mais, commit de marcadores certo. Entra depois do 185 corrigido, pelo critério mecânico do §4 (não volta ao Opus) |
| **189** (regra T29c) | `s04-t29c-regra` (70ca17b) | **REPROVADO** (achados 3.1 a 3.3; o 3.1 é o desvio da frase) |

Nada aprovado provisoriamente. O que falta é pouco (cerca de 3 linhas no oráculo e cerca de 20 no produto) e vai a um **lote 62** curto (§4).

## Evidências (rodadas pelo revisor em worktrees temporários no rascunho, já removidos; nada do repositório foi editado)
- 189 sem `--runxfail`: **16 passam**, 3 rodadas completas (cerca de 78 s cada). 188: 11 passam e 5 `xfail` (os do T29c). 185 sozinho: 3 passam e 13 `xfail`. 189, testes existentes (`test_s04_abertura.py`, `test_viewport_carregador.py`): 39 passam, 2 pulados.
- **Vigia desligado** (plugin do pytest fora do arquivo, `_vigiar` vazio): falham exatamente 3, `crescer_em_bloco...`, `segundo_reinicio...` e `fila_cheia...`, todos por "filhos de conversão: 1" (esperado 2). **Vigia desligado e o `bloco_fim` voltando a disparar** (comportamento reprovado do 7d7e7ae): falham os mesmos 3, por `perdido_s` 10,3 s contra o teto de 10. Confirma o que o autor do oráculo declarou: os testes agora só passam se o vigia decidir no meio do bloco.
- Folga dos testes de peça lenta (Linux, 2 rodadas): `perdido_s` 0,36 a 0,40 s (crescer, segundo), 0,97 a 0,98 s (fila cheia), contra o teto de 10 s. No Windows do CI o `windows-testes` do 189 passou com o oráculo rodando (393 passam, mesmo número de pulados de antes; nenhum teste do T29b pulado).
- **Mutação "vigia sem teto de 1 reinício"** (o vigia reinicia de novo mesmo depois do 1º): o `segundo_reinicio...` original **passa 3 de 3**. Ver 1.1.
- **Mutação "sem isenção do 1º bloco"**: o teste de isenção falha 3 de 3. Bom.
- Variante do `segundo_reinicio...` escrita só no rascunho (2ª peça lenta no fim do bloco onde está o 2º crescimento, e a frase "visto só no fim do bloco" proibida): com o código do 189 passa 2 de 2 (a frase vem do vigia: "reinício pedido e não feito (bloco 4): já houve 1 reinício"); com a mutação "sem teto" falha 2 de 2 (3 filhos em vez de 2).
- O campo novo de atraso de armar já mostra a janela cega: no teste de fila cheia, `atraso_armar_s` = 0,80 s no bloco vigiado (fila de 1, consumidor de 0,2 s por lote). O campo funciona, e a janela cega existe.

## 1. PR 185: oráculo (REPROVADO, 1 achado)
Atendidos do lote 60: **1.1** (peça lenta de 10 s depois da que cresce, `perdido_s < 10` nos 3 testes do caminho real; demonstrado acima), **1.2** (isenção: lenta no fim do 1º bloco, e a mutação sem isenção é pega; modo isolado: lenta na posição 2, que cai no mesmo filho isolado de "uma peça por vez" em que a peça 0 cresce, e o próprio teste exige `pico_filho_mb ≥ 1000`, o que prova que esse filho cresceu e terminou), **1.3** (resumo: filhos, `reinicios == [2]`, `perdido_s > 0`, a linha do reinício planejado, tempos do filho novo), **1.4** (`desl` vazio com 3 proxies sem geometria no bloco 1; o filho novo recebe `desl` None e o resultado é igual ao normal), **1.5** (os novos entraram marcados), **1.6** (`reinicios == [2]` no cancelar). Nada afrouxado. Uma mudança em `conferir_igual` (o motivo de `sem_malha` comparado só até o primeiro ":", porque o registro do conversor traz hora) é aceita: motivos diferentes continuam diferentes, e a regra de ouro ("o conversor não devolveu a peça") é conferida à parte.

1.1 **(bloqueia)** `tests/test_s04_t29b_reinicio_oraculo.py`, `test_segundo_reinicio_pedido_com_teto_padrao_e_registrado_e_nao_feito` (linhas 322 a 327): o teste **passa sem testar** o teto do vigia. O 2º crescimento cai no bloco 2 do filho novo (posições 6 a 8), que termina em milissegundos; o vigia não chega a ver, e a frase exigida vem do `bloco_fim`. Prova: com o teto removido do vigia o teste continua verde 3 de 3. Nenhum outro teste cobre o teto de 1 (o `dois_reinicios` usa o gancho com 2 valores, que sobe o teto para 2). Correção (autor do oráculo, o teste continua marcado no 185):
   - peça lenta também em `3 * BLOCO - 1` (fim do bloco do 2º crescimento): `"OBIM_TESTE_PECA_LENTA": "<guid 5>=10,<guid 8>=10"` (o gancho já aceita vários pares);
   - acrescentar `assert not any("visto só no fim do bloco" in m for m in r.mensagens), r.mensagens`.
   O teste fica em cerca de 21 s. O diff do arquivo fica em cerca de 398 linhas (teto 400: não acrescentar mais nada).

## 2. PR 188: caminho do reinício (APROVADO)
- 3f66f85 é o mesmo commit (mesmo SHA) que o lote 60 aprovou; não houve rebase, só merge. `git diff 3f66f85 origin/s04-t29a-reinicio -- prototypes/` vazio; `git diff c95b123 f596fda -- tests/` vazio (o merge não trouxe nada além do oráculo).
- 7537247: só o arquivo do oráculo, 7 linhas apagadas, todas `@AINDA_NAO`, nas 6 funções do T29a (bloco 250, reinício forçado, dois reinícios, os 2 de cancelar, queda e limite, este com 2 casos) e no `desl` vazio. Nenhum assert mexido. Ficam marcados os 5 do T29c.
- Escopo (três pontos contra o `main`): só `carregador.py` e o arquivo do oráculo.
- CI do 188: `linux` verde; `windows-viewport-a` falhou (ver §5).

## 3. PR 189: regra R-A (REPROVADO, 3 achados)
Conferido e certo no retrabalho bfb2797:
- **3.1 do lote 60:** o `bloco_fim` só registra: grava `fim_mb`, escreve texto e desarma (`_base_mb = None`). **Não pede reinício em nenhum caminho**: nunca toca `_pedido` nem `_decisao`; o `_vigiar` que vem logo depois da mensagem sai sem fazer nada porque a base já é None. Os únicos lugares que gravam `_pedido` são `_decidir` (vigia) e `_gancho_reinicio` (gancho de teste). O plugin "só `bloco_fim`" acima mostra que o oráculo pegaria a volta do gatilho tardio.
- **3.2:** o vigia dentro de `_colocar` saiu (o 189 não mexe em `_colocar` em relação ao 188).
- **3.3:** `bloco` leva `t` (hora de parede do filho); `ResumoCarga.blocos` (bloco, filho, `base_mb`, `max_mb`, `fim_mb`, `atraso_armar_s`, `armado`, `falhas_leitura`; só modo normal); `ResumoCarga.registro_reinicio` (bloco, fonte `vigia` ou `gancho`, `base_mb`, `decisao_mb`, `atraso_armar_s`); `reinicios` continua lista de inteiros.
- **3.4:** falha de leitura conta por filho, vai ao registro do bloco e dá aviso no log na 1ª de cada filho.
- **3.5.1:** `pico_filhos_mb`, um por filho, o morto com o pico lido antes do `kill`. **3.5.2:** comentário do macOS. **2.1:** mensagens repetidas tiradas mantendo a ordem. **2.2:** comentário de que `perdido_s` já inclui `decisao_s` e `morte_s`. **2.3:** aviso no log se o filho morto não sair em 5 s.
- Autoria: `git log origin/main..origin/s04-t29c-regra --no-merges -- tests/test_s04_t29b_reinicio_oraculo.py` lista só commits T29b (1b0951b, c95b123, 7537247, 70ca17b); `git diff <c>^ <c> -- tests/` vazio para 3f66f85, 7d7e7ae e bfb2797. 70ca17b: só linhas apagadas (a constante `AINDA_NAO` e 5 `@AINDA_NAO`). Os merges 4355651 e ec0983b não trazem nada além dos ramos de origem (`git diff bfb2797 70ca17b -- prototypes/` vazio). Escopo: só `carregador.py`, `processo_malhas.py` e o oráculo. Produto do 189 sobre o 188: 129 linhas a mais e 28 a menos.

### 3.1 (bloqueia) Desvio da frase: **não aceito**
- O implementador fez o `bloco_fim` escrever "reinício pedido e não feito (bloco k): crescimento de X MB visto só no fim do bloco, já houve 1 reinício" quando já houve 1 reinício, para o teste `segundo_reinicio...` passar. Não aceito por três motivos: (a) é o que faz o teste passar sem testar o teto do vigia (1.1); (b) **nada foi pedido**: o `bloco_fim` não pede reinício, então a frase diz uma coisa que não aconteceu; (c) no ensaio, um mesmo evento seria contado duas vezes, como "reinício pedido e não feito" e como "visto só no fim do bloco" (lote 60 §7 item 1), sujando justamente a contagem que decide se o vigia funciona. O texto especificado no lote 60 §3.1 era só o "tarde".
- Correção em `carregador.py`, ramo `bloco_fim` de `_tratar`: escrever sempre `f"crescimento de {cresc:.0f} MB visto só no fim do bloco {k}: reinício não feito (tarde)"`, com `"; já houve 1 reinício"` no fim se for o caso; **nunca** o trecho "reinício pedido e não feito". A frase "reinício pedido e não feito" fica só para `_decidir` e `_gancho_reinicio`. Com 1.1 aplicado no oráculo, o teste passa pelo vigia (demonstrado no rascunho).
- Marcar também no registro do bloco: `self._reg["tarde"] = True` (o ensaio conta pelo campo, não pelo texto).

### 3.2 (bloqueia o ensaio; pedir no mesmo retrabalho, senão vira outro ciclo T3) Campos que faltam para a medida
- `max_silencio_s` por bloco no registro (o maior intervalo entre duas mensagens do filho dentro do bloco, sem contar o tempo do pai na fila cheia, como o `ultimo` já faz), e, por reinício, o maior silêncio do filho velho até a morte. Lote 60 §7 item 4.
- `primeira_mb` por bloco: a 1ª leitura do pai depois de armar. É o que permite conferir a base dada pelo filho contra a lida pelo pai (lote 59 §2.6, ±50 MB).
- No registro do reinício: `decisao_tarde` (o vigia decidiu depois de o filho já ter mandado `bloco_fim`). Como fazer sem mudar o caminho: depois de o filho morto sair (`exitcode` definido), esvaziar o canal sem aplicar nada e anotar se havia `bloco_fim` entre as mensagens descartadas; qualquer erro de leitura nesse ponto é ignorado (o filho já está morto e nada disso é contado). Sem isso, uma decisão tardia por causa do pai atrasado apareceria como "vigia" e passaria por boa.

### 3.3 (sugestão) `pico_filhos_mb`
O filho que morre sozinho (queda) fica com 0,0, que parece medida. Usar `None` quando não houve leitura.

## 4. Ordem, lote 62 e critério mecânico do 188
1. Autor do oráculo: 1.1 num commit próprio no 185 (teste ainda marcado). Implementador: 3.1 e 3.2 (e 3.3 se quiser) num commit no 189, sem tocar em `tests/`.
2. Merge da nova ponta do 185 no 188 e no 189 (commit de merge). Se houver conflito perto dos marcadores, quem resolve é o autor do oráculo, mantendo os commits de marcadores só com linhas apagadas.
3. **Lote 62** (curto, contexto fechado): só o commit novo do oráculo, o commit novo do 189 e a conferência de que 7537247 e 70ca17b continuam só apagando marcadores depois do merge. Oráculo do 189 sem `--runxfail`: 16 passam, e a mutação "sem teto" tem de derrubar o `segundo_reinicio...`.
4. **O 188 não volta ao Opus** se, depois do merge da nova ponta do 185: 3f66f85 com o mesmo SHA; `git diff 3f66f85 origin/s04-t29a-reinicio -- prototypes/` vazio; `git diff <nova ponta do 185> origin/s04-t29a-reinicio -- tests/` mostra só as 7 linhas `@AINDA_NAO` apagadas. O líder confere e registra no LOG.
5. Merge com commit de merge (sem achatar): **185, depois 188, depois 189**, cada um só depois do anterior entrar e do seu `linux` e `windows` ficarem verdes.

## 5. CI: falhas de hoje
- **185, `linux`**: `tests/test_s04_t15c_conferencias.py:72`, controle positivo de ritmo de thread (`razao_ocupada` 1,14 contra o teto de 0,7). **Sem ligação com o T29**: o 185 só acrescenta o arquivo do oráculo, e o T15c não usa o carregador; segundo o pedido, o mesmo teste já falhou no 191, que não tem código do T29.
- **188, `windows-viewport-a`**: `test_s04_viewport_b.py::test_contadores_de_soltura_t07b[destruir-janela]` travou (limite de 6 min 20 s) em `c_destruir`. **Sem ligação com o T29**: esses testes do viewport só importam tipos (`DTYPE_*`, `LoteMalha`) do carregador, que o T29 não muda; e o `windows-viewport-a` do 189, que contém todo o código do 188 e mais, passou.
- **Repetir só o job que falhou (`gh run rerun --failed`) é aceitável para mesclar**, nestas condições: o teste que falhou está fora dos arquivos e módulos do PR; cada repetição conta nas 5 tentativas por problema (autorização 2 do `CLAUDE.md`) e ganha uma linha no LOG; se o mesmo teste falhar de novo no mesmo PR, ou se falhar qualquer teste do T29, parar.
- **O T15c instável pede cartão à parte, classe T3**: é oráculo de threads; repetir dentro do teste, ou mexer no 0,7, só com revisão Opus (nada de afrouxar). O travamento do `destruir-janela` no Windows: registrar no LOG; se voltar a acontecer, cartão T3 à parte (destruição da janela com a thread de desenho viva).

## 6. Pronto para o ensaio (A32, tela virtual) e para a medida oficial
Com 3.1 e 3.2 feitos, o produto grava tudo do lote 60 §7 que é do carregador. Antes do ensaio:
1. §4 concluído (T29 inteiro no `main`).
2. **Cartão T1 ou T2 à parte para a sonda** (`sonda_memoria_t24.py` ou `medir.py`, fora dos arquivos do T29) que grave, por abertura: `ResumoCarga.blocos`, `registro_reinicio`, `reinicios`, `pico_filhos_mb`, `tempos` (`decisao_s`, `morte_s`, `perdido_s`), as mensagens com "não feito" e com "visto só no fim", a amostragem dos processos filhos do pai (0 instantes com dois vivos), conta A, conta B, pico do pai, M5, e as contagens (peças com malha, triângulos, vértices, `sem_malha`, `simplificadas`, peças no modo isolado). A sonda não muda nenhum limite.
3. Critérios de parada do lote 60 continuam: fonte do reinício do pesado tem de ser `vigia`, no bloco 22; `tarde` e `decisao_tarde` tem de ser 0; `atraso_armar_s` do bloco 22 até 0,5 s (acima disso, parar e levar ao Opus, lote 60 §3.3); `max_silencio_s` abaixo de 20 s; crescimento de bloco que não é o 1º do filho acima de 500 MB fora do bloco 22, parar; `primeira_mb` contra `base_mb` dentro de ±50 MB.
4. Windows (T28): `WorkingSetSize` e `PrivateUsage` lado a lado (lote 60 §5); não é do T29.
A tela virtual não prova meta: só decide se vale chamar a sessão na placa.

## 7. Resumo para o PO (5 linhas, sem siglas)
1. A parte que mata e recomeça o processo de conversão continua aprovada e pode entrar logo depois do teste corrigido.
2. Os testes novos agora provam que a regra decide no meio do bloco, a tempo; conferi desligando a regra, e eles falham como deviam.
3. Sobrou um teste que passava sem conferir o limite de um reinício por abertura; pedi uma peça lenta a mais nele.
4. Também pedi para o programa não escrever "reinício pedido" quando nada foi pedido, e para gravar mais três medidas que o ensaio vai precisar.
5. As duas falhas de hoje na verificação automática não têm ligação com este trabalho; pode repetir só a parte que falhou, e uma delas merece tarefa própria.

## 8. Linha do LOG
`2026-10-19 | F0-S04-T29 | LOTE_OPUS_61 (opus, médio) | 185 REPROVADO (segundo_reinicio passa sem testar o teto: lenta também no bloco do 2º crescimento e proibir "visto só no fim"), 188 APROVADO (3f66f85 igual; entra por critério mecânico depois do 185), 189 REPROVADO (bloco_fim não escreve "reinício pedido e não feito"; campos max_silencio_s, primeira_mb, tarde, decisao_tarde); falhas de CI do T15c e do destruir-janela sem ligação, repetir job vale, T15c pede cartão T3; lote 62 curto; merge 185→188→189 | docs/state/lotes/LOTE_OPUS_61/resultado.md`
