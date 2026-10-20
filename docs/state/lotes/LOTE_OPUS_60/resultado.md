<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_60: resultado da revisão do T29 (oráculo T29b, reinício T29a, regra R-A T29c)
Revisor: Opus (2026-10-19), classe T3, esforço médio. O Opus não escreveu nenhum dos três PRs; a especificação revisada é a do lote 59 (do Opus), e um erro dela está assumido no item 3.3.

## 0. Vereditos
| PR | ramo | veredito |
|---|---|---|
| **185** (oráculo T29b) | `s04-t29b-oraculo` (1b0951b) | **REPROVADO** (achados 1.1 a 1.5) |
| **188** (reinício T29a) | `s04-t29a-reinicio` (3f66f85) | **APROVADO o conteúdo de 3f66f85**; o merge segue a ordem do §4 (hoje o `linux` fica vermelho por causa dos marcadores do oráculo, não por defeito do código) |
| **189** (regra T29c) | `s04-t29c-regra` (7d7e7ae) | **REPROVADO** (achados 3.1 a 3.4) |

Nada foi aprovado provisoriamente. O 188 está aprovado com o conteúdo exato de 3f66f85, mais um único commit do autor do oráculo que **só apaga** as 7 linhas `@AINDA_NAO` dos testes do T29a (§4). Qualquer outra mudança no 188 pede revisão nova.

## Evidências (rodadas pelo revisor num worktree temporário, já removido; nada do repositório foi editado)
- 189, oráculo com `--runxfail`: 15 de 15 passam, **9 rodadas** seguidas (cerca de 29 s cada).
- 189 sem `--runxfail`: **12 falham** (XPASS estrito) e 3 passam. 188 sem `--runxfail`: **7 falham** (XPASS estrito: bloco 250, reinício forçado, dois reinícios, os 2 de cancelar, os 2 de queda/limite) e 3 passam. É isso que deixa o `linux` do PR 188 vermelho. 185 sozinho: verde.
- 188 com `--runxfail`: 10 passam; falham os 5 do T29c (esperado: o gancho de crescimento ainda não existe).
- Testes existentes no 189 (`test_s04_abertura.py`, `test_viewport_carregador.py`): 39 passam, 2 pulados.
- **Experimento decisivo (o vigia periódico desligado por um plugin do pytest, sem tocar no código):** os 5 testes do T29c **passam 3 de 3** com o vigia desligado. Com o `bloco_fim` ignorado (vigia ligado), falham 2 ou 3 dos 5 em cada rodada (crescer no bloco 2, segundo reinício e fila cheia). Ou seja, **todo disparo que o oráculo vê vem do `bloco_fim`; nenhum teste prova que o vigia decide no meio do bloco.**
- **Caso que distingue (escrito pelo revisor só no rascunho):** crescer 1.100 MB na 1ª peça do bloco 2 e `OBIM_TESTE_PECA_LENTA` de 5 s na última peça do mesmo bloco. Com o vigia ligado: 2 filhos, `decisao_s` 0,36 a 0,38 s, 3 de 3. Com o vigia desligado: `decisao_s` 5,33 s e falha. Mesmo resultado com fila cheia (`fila_max=1`, consumidor lento) no bloco 3: com o vigia, `decisao_s` 0,98 s; sem ele, 5,33 s.

## 1. PR 185: oráculo (REPROVADO)
O que está certo: forma canônica por peça (junta pedaços, gira sem trocar o sentido, ordena, compara bits), controle normal contra normal, `desl` único e igual, `sem_malha`/`simplificadas`/totais exatos, espião de processos (0 filhos vivos ao mesmo tempo, conferido na criação e no início de cada filho), limites padrão na assinatura, isenção, segundo reinício registrado, os dois cancelamentos, queda e limite no bloco refeito, modo isolado. Nada foi afrouxado. O risco de corrida declarado (peça morta como última do bloco 2) é baixo: no caso refeito o reinício forçado acontece no `convertendo` do bloco 2, antes de qualquer peça, e os dois lados passam pelo mesmo caminho de queda (isolado, depois uma peça por vez), cujo resultado não depende da ordem; 9 rodadas verdes.

Achados:
1.1 **(bloqueia)** Os testes do T29c passam sem o mecanismo principal (vigia no meio do bloco). Correção: em `test_crescer_em_bloco_que_nao_e_o_primeiro...`, `test_segundo_reinicio...` e `test_fila_cheia...`, acrescentar `OBIM_TESTE_PECA_LENTA` de **L = 10 s** (abaixo de `limite_peca_s` 20; nenhum limite muda) numa peça **posterior** à que cresce, no mesmo bloco, e afirmar `r.tempos["perdido_s"] < L` (o filho velho morreu antes de terminar a peça lenta). 10 s dá margem para o início do filho no Windows do CI. O caso de fila cheia fica com `fila_max=1`, `pausa_s=0.2` e o mesmo L. Critério de aceite do próprio teste: ele tem de **falhar** com o vigia desligado (o autor do oráculo demonstra isso uma vez, por plugin ou monkeypatch fora do arquivo, e registra no retorno).
1.2 **(bloqueia)** A isenção e o modo isolado também precisam da peça lenta depois da que cresce (no 1º bloco e no modo isolado), senão passam porque o vigia não teve tempo, e não porque a regra isenta. Mesma L.
1.3 **(bloqueia)** §2.4 do lote 59 pede "resumo: mensagens juntadas, tempos somados, número de filhos". Hoje só a mensagem "não feito" é conferida. Acrescentar no reinício forçado: `r.filhos == len(esp.conversao)`, `r.reinicios == [2]`, `r.tempos["perdido_s"] > 0`, linha "reinício planejado do filho no bloco 2" em `r.mensagens`, e `r.tempos` com as chaves `abrir_s`, `listar_s`, `geometria_s` do filho novo presentes e maiores que zero (o filho morto não manda `fim`; os tempos dele estão só em `perdido_s`).
1.4 **(bloqueia)** Caso da tabela §2.3 do lote 59 ("`desl` vazio: o filho novo calcula o seu; oráculo cobre") ausente. Modelo com o bloco 1 inteiro sem geometria (por exemplo 3 `IfcBuildingElementProxy` com representação vazia e ids menores que as paredes), reinício forçado no bloco 2: conferir igual à abertura normal (mesmo `desl` nos lotes).
1.5 **(bloqueia, mecânica)** Marcadores `xfail(strict=True)`: ver §4. Os testes novos de 1.1 a 1.4 entram no 185 **também marcados** (o `main` ainda não tem o T29); quem remove os marcadores é o autor do oráculo, em commits próprios.
1.6 (sugestão) O teste de cancelar entre a morte e o filho novo pode conferir também `r.reinicios == [2]` (prova que o cancelamento veio depois da morte planejada, não antes).

## 2. PR 188: caminho do reinício (APROVADO, conteúdo 3f66f85)
Conferido no código: `reinicio` tratado em `_ler` antes da rede de segurança e do bloco de falhas, sem tocar em `espera`, `seguidos`, `acusadas`, `iso`; o filho seguinte recebe os não resolvidos em ordem e o mesmo `est["desl"]`; `_reiniciar` lê o pico (VmHWM) antes do `kill`, espera `exitcode` em passos de `FATIA_S` conferindo o cancelamento, e só então devolve; o `finally` de `_executar` ainda mata e faz `join` se o cancelamento chegar durante a espera (sem zumbi); tudo o que estiver no canal depois da decisão é descartado sem entrar em `resolvidos`; `fim` agora junta as mensagens; tempos somados; `filhos`, `reinicios`, `decisao_s`, `morte_s`, `perdido_s`. Gancho `OBIM_TESTE_REINICIO_BLOCO` como especificado (ignora o 1º bloco do filho, teto 2 só com 2 valores). Bloco padrão 250. Limites padrão intactos.

Sugestões (não bloqueiam; podem ir no retrabalho do 189):
2.1 `carregador.py`, `fim` (`est["msgs"].extend`): no modo isolado cada filho manda até 50 linhas do registro do conversor; com muitos filhos o resumo repete linhas. Tirar repetidas mantendo a ordem.
2.2 `perdido_s` começa em `inicio` (depois de `start()`), não conta o tempo de criar o processo; e já inclui `decisao_s` e `morte_s`. Dizer isso num comentário, para ninguém somar os três.
2.3 A espera por `exitcode` não tem teto (só o cancelamento a interrompe). Registrar aviso no log se passar de 5 s.

## 3. PR 189: regra R-A (REPROVADO)
Conferido e certo: G = 1.000 MB na unidade de `pico_memoria_mb` (kB ÷ 1.024; VmRSS no Linux, `WorkingSetSize` no Windows); a base vem do filho (`bloco`, logo depois de `convertendo`, depois de soltar a memória do gancho); arma só com `_conv ≥ 2` e modo normal; desarma em `lote`, `sem_malha`, `fim` e na decisão; no máximo 1 reinício (o 2º vira "reinício pedido e não feito"); `fase` intacta; gancho `OBIM_TESTE_CRESCER_MB` escreve de verdade.

### 3.1 (bloqueia) `bloco_fim` não pode disparar o reinício
- O `bloco_fim` chega **depois** de o bloco inteiro ter sido convertido, isto é, depois do pico. A própria especificação (lote 59 §2.2 item 4) diz: depois que o bloco começa a emitir, o pico já passou e matar não ajuda. O `bloco_fim` está exatamente nesse ponto.
- Conta, com os números do T26: no pesado, o bloco 22 dura 13,7 a 15,0 s e cresce cerca de 3,4 GB a partir de cerca de 1.948 MB. Uma decisão no `bloco_fim` deixa o filho velho chegar a cerca de 5,3 GB (pai cerca de 1.047 MB: conta A cerca de 6,35 GB, acima de 6.000) e perde o bloco inteiro (cerca de 15 s: abrir cerca de 52,74 + 15 = 68 s, acima de 60). Ou seja, quando o `bloco_fim` decide, a meta já falhou nas duas réguas, e o reinício só custa tempo.
- O "fila cheia" falhava sem ele porque, no modelo de teste, o bloco termina em milissegundos: não há tempo para o pai alcançar o filho. Não é o caso real (bloco 22 de 14 s; cruza G em cerca de 0,87 s).
- **Decisão:** desvio **não aceito como gatilho**. A mensagem `bloco_fim` **fica**, mas só como registro: se o vigia estava armado e `rss_fim − base ≥ G`, gravar "crescimento de X MB visto só no fim do bloco k: reinício não feito (tarde)"; sempre guardar a memória do fim do bloco no registro por bloco (3.3). Não conflita com "referência dada pelo filho": a base continua sendo a do `bloco`.

### 3.2 (bloqueia) Vigia dentro de `_colocar` é código morto: remover
`carregador.py` linha 245. O pai só entra em `_colocar` ao tratar um `lote`, e o `lote` desarma antes (`_base_mb = None`). Se o lote é do bloco k, já desarmou; se é do bloco k−1, o `bloco` de k está atrás dele no canal e ainda não armou. Nunca age. O comentário diz que cobre o pai cego, e não cobre. Remover a chamada, o parâmetro `est` de `_colocar` e o comentário.

### 3.3 Erro da especificação (do Opus, lote 59 §2.2 item 3) e o que fazer
A leitura "dentro da espera de `_colocar`" não resolve a cegueira do pai, porque o pai não pode armar sem ler o `bloco`, que está atrás dos lotes do bloco anterior. A janela cega real é: do envio do `bloco` k pelo filho até o pai sair do último `_colocar` do bloco k−1. Ela só importa se for comparável ao tempo até cruzar G (0,57 a 1,77 s, conforme G; 0,87 s com G = 1.000 MB). Não há dado sobre ela. Portanto:
- **Agora (no retrabalho do 189, bloqueia):** medir. O `bloco` passa a levar também `t` (hora de parede do filho, `time.time()`), e o pai registra por bloco: número global, filho, `base_mb`, maior memória lida pelo vigia, `fim_mb` (do `bloco_fim`), **atraso de armar** (hora em que o pai armou menos `t`). Campo novo `ResumoCarga.blocos` (lista de dicionários; só blocos do modo normal). E, por reinício, `ResumoCarga.registro_reinicio` (lista de dicionários: bloco, fonte `"vigia"` ou `"gancho"`, `base_mb`, memória na decisão, atraso de armar). Manter `reinicios` como está (lista de inteiros), que o oráculo usa.
- **Depois do ensaio, se o atraso de armar no bloco 22 passar de 0,5 s, ou se o reinício não for decidido pelo vigia:** parar e levar ao Opus. Alternativas já avaliadas: (a) **vigia no filho** (recomendada se for preciso): uma thread do filho lê a própria VmRSS a cada 50 ms durante o bloco vigiado e, ao cruzar G, sai com um código reservado; o pai trata esse código como reinício, depois de ler normalmente o que está no canal (os lotes do bloco anterior são legítimos). Antes, uma sonda curta: a thread de leitura precisa rodar enquanto o iterador converte (o iterador precisa soltar o GIL; não verificável daqui). (b) o pai continuar lendo o canal enquanto a fila está cheia, aplicando as mensagens de controle e guardando os lotes em ordem: mais simples de provar, mas aumenta a memória do pai (lotes guardados), que entra na conta A.

### 3.4 (bloqueia) Falha silenciosa da leitura
`_vigiar` engole qualquer exceção (linha 458 em diante). No Windows, que não foi medido, uma leitura que falhe desliga a regra sem aviso. Registrar aviso no log na primeira falha de cada filho e contar as falhas no registro por bloco.

### 3.5 Sugestões (não bloqueiam)
3.5.1 Guardar o pico de **cada** filho (lista), não só o maior: a medida oficial pede o do filho morto (lote 59 §2.6). Pode ir no mesmo retrabalho.
3.5.2 macOS (experimental): o filho manda como base o pico (`ru_maxrss`), e o pai lê a memória atual por `ps`: o crescimento sai subestimado (nunca reinício falso). Registrar no comentário; não corrigir agora.
3.5.3 As guardas `not self._isolado` não têm teste próprio (o filho isolado não manda `bloco`, e o gancho já para em `_conv < 2`). Aceitável; anotar.
3.5.4 Fora do escopo do T29, para um cartão futuro com o Opus: no laço normal do filho, `prods` do bloco k−1 continua referenciado durante a conversão do bloco k (só é trocado quando `_bloco` volta). Soltar logo depois de `emitir` pode baixar o pico do filho. Medir antes de mexer.

### 3.6 Estabilidade
As 3 rodadas do autor e as 9 do revisor estavam verdes, mas por causa do `bloco_fim`. Depois de 3.1 e 1.1, os testes passam a depender de margens de segundos (peça lenta de 10 s contra decisão em menos de 1 s), não de milissegundos. Pedir 5 rodadas verdes locais e o CI `linux` e `windows` verdes.

## 4. Marcadores `xfail`, autoria do oráculo e ordem de merge
- Os marcadores estão certos no `main` de hoje e errados nos ramos que já têm a implementação. No 188 eles derrubam 7 testes; no 189, 12. **O implementador não os toca.** Quem os remove é o **autor do oráculo**, em commits que **só apagam** linhas `@AINDA_NAO` (e, no último, a constante `AINDA_NAO`). Isso é mudança só de guarda, que aperta e não afrouxa nada (regra do `CLAUDE.md`). O líder confere cada commit desses com `git show --stat` (só o arquivo do oráculo) e `git show` (só linhas apagadas com `@AINDA_NAO`).
- Garantia de que o implementador não editou o oráculo: `git log origin/main..<ramo> --format='%h %an %s' -- tests/test_s04_t29b_reinicio_oraculo.py` só pode listar commits T29b; e `git diff <commit do T29a ou T29c>^ <commit> -- tests/` vazio.
- Os três **não podem** entrar como um PR só (cerca de 528 linhas; o teto é 400). **Entram em sequência**, cada um com `linux` e `windows` verdes no `main`:
  1. Autor do oráculo atualiza o 185 (1.1 a 1.4; testes novos e alterados ainda marcados). Implementador refaz o 189 (3.1 a 3.4, e as sugestões que quiser) sobre o 188 rebaseado.
  2. Autor do oráculo põe no ramo 188 o commit que tira os 7 marcadores do T29a, e no ramo 189 o commit que tira os demais (a lista exata é a que ficar marcada depois do passo 1).
  3. **Lote Opus 61** revisa só a diferença: oráculo atualizado (185), retrabalho do 189 e os dois commits de marcadores. O 188 não volta à revisão se `git range-diff` mostrar 3f66f85 igual depois do rebase.
  4. Merge (commit de merge, sem achatar, para manter a autoria separada): **185, depois 188, depois 189**, cada um só depois do anterior entrar e do seu CI ficar verde. O `main` fica verde em cada passo: 185 entra todo marcado; 188 tira só os marcadores do T29a; 189 tira o resto.

## 5. Efeitos no produto (bloco padrão 250)
O que pode piorar sem aparecer nos testes sintéticos: (a) quatro vezes mais iteradores, cada um com o custo fixo de `initialize` e o arranque das threads; (b) mais "caudas" por bloco (threads paradas enquanto a última peça do bloco termina), que pesa mais em arquivos de muitas peças baratas (simples, detalhado, 25 MB); (c) o reaproveitamento de representações mapeadas e caches do conversor se perde de bloco para bloco, o que pode custar tempo onde há muitos itens repetidos (o modelo sintético de paredes não tem); (d) mais lotes pequenos (o último de cada bloco), mais envios à placa. O teste que prova: a medida oficial do lote 59 §2.6, simples, detalhado e 25 MB, 3 aberturas cada, intercaladas, bloco 250 contra bloco 1.000, mesmos fios; não pode piorar (A25). Pode também baixar a memória do filho (blocos menores). **Windows, só pelo desenho:** `WorkingSetSize` pode ser cortado pelo sistema sob pressão de memória; isso tende a esconder crescimento (reinício que falta), mas se a base for lida cortada e as páginas voltarem durante o bloco, pode aparecer crescimento que não é alocação nova (reinício falso). O T28 deve gravar, a cada leitura, `WorkingSetSize` e a memória comprometida do processo (`PrivateUsage`) lado a lado; se divergirem, levar ao Opus antes de trocar a fonte da regra.

## 6. Limites e régua
Conferido: os três PRs mexem só em `prototypes/viewport_qrhi/carregador.py`, `prototypes/viewport_qrhi/processo_malhas.py` e no arquivo novo `tests/test_s04_t29b_reinicio_oraculo.py`. `fluxo_a.py`, `lote.py` e `prototypes/s04/obimcore/` intocados; nenhum teste existente editado; `limite_peca_s` 20, `limite_abrir_s` 600, `max_pecas_condenadas` 20, `max_espera_s` 120 iguais (o oráculo confere na assinatura); metas (6.000 MB, 60 s, M5) sem mudança. O retrabalho do 189 continua dentro dos mesmos arquivos.

## 7. Antes do ensaio (tela virtual, A32) e da medida oficial (placa)
Falta antes do ensaio: §4 passos 1 a 4 concluídos (T29 no `main`), e a sonda de medida (`sonda_memoria_t24.py` ou `medir.py`, cartão T1 ou T2 à parte, fora dos arquivos permitidos do T29) gravando os campos novos. O ensaio e a medida registram, por abertura:
1. bloco do reinício (pesado: o das 3 peças, o 22) e a **fonte** (tem de ser `vigia`); reinícios pedidos e não feitos; avisos "visto só no fim do bloco" (tem de ser 0);
2. **atraso de armar** em cada bloco (o do bloco 22 até 0,5 s; acima disso, parar e levar ao Opus, §3.3);
3. `decisao_s`, `morte_s`, `perdido_s`; base e memória na decisão; **pico do filho morto** (comparar com a estimativa de 3,35 GB do lote 59 §2.1) e de cada filho;
4. maior silêncio do filho velho antes da morte e do filho novo (abaixo de 20 s);
5. 0 instantes com dois filhos vivos (amostragem dos processos filhos do pai);
6. crescimento de cada bloco que não é o primeiro do filho (do registro por bloco), nos 4 arquivos; se algum passar de 500 MB fora do bloco 22, parar e levar ao Opus antes de mexer em G;
7. contagens iguais ao `n250` (peças com malha, triângulos, vértices, `sem_malha`, `simplificadas`), 0 peças no modo isolado, `desl` igual ao do `n1000` e do `n250` (a comparação por peça na máquina do PO é exata);
8. conta A, conta B, pico do pai, M5; na placa, 5 aberturas do pesado com a **pior** ao lado da meta; simples e detalhado contra o bloco 1.000 (A25).
A tela virtual não prova meta: só decide se vale chamar a sessão na placa.

## 8. Resumo para o PO (5 linhas, sem siglas)
1. O reinício do processo de conversão (a parte que mata e recomeça o bloco) está correto e aprovado.
2. A regra que decide quando reiniciar funciona, mas os testes só a viam disparar tarde, no fim do bloco, quando já não ajuda.
3. Pedi para disparar só a tempo, no meio do bloco, e para os testes provarem isso com uma peça lenta de propósito.
4. Também pedi para gravar quanto o programa demora a "ver" o começo de cada bloco; se no arquivo pesado passar de meio segundo, volto com outra solução.
5. Os três pedidos entram um de cada vez, depois de uma revisão curta só das correções; nenhuma meta ou limite mudou.

## 9. Linha do LOG
`2026-10-19 | F0-S04-T29 | LOTE_OPUS_60 (opus, médio) | 185 REPROVADO (oráculo não prova o vigia no meio do bloco; faltam resumo e desl vazio), 188 APROVADO (3f66f85), 189 REPROVADO (bloco_fim só registro, não gatilho; tirar vigia morto de _colocar; registrar fonte, atraso de armar e falha de leitura); merge em sequência 185→188→189 após lote 61 | docs/state/lotes/LOTE_OPUS_60/resultado.md`
