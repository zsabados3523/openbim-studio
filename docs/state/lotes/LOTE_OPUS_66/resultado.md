<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_66: resultado (revisão Opus em lote, esforço médio, 2026-10-20)
Revisor: Opus. Não escrevi nenhum dos PRs revisados nem os oráculos. Li o pedido, `LOTE_OPUS_65/resultado.md` (§1 PR 222, §2 ponto 3, §4), os cartões T34, T29e, T30b3, T23 e T30, os relatórios `F0-S04-T34.md` (no ramo), `F0-S04-T23.md` (no ramo do 231) e `F0-S04-T30-placa.md` (no `main`), e os diffs com `git diff origin/main...<ramo>` depois de `git fetch origin` (base `main` = 1e99e64). Não li `~/openbim-medicao` nem nenhum IFC.

## 0. O que eu rodei (Linux, ambiente `openbim`, `xvfb-run` + `QT_QPA_PLATFORM=offscreen`; nenhuma janela na tela real)
1. **228 (com 227 por baixo, ponta d06f425):** `test_s04_t29e_pos_emitir_oraculo.py`, `test_s04_t29b_reinicio_oraculo.py`, `test_viewport_processo.py`, `test_viewport_carregador.py`, `test_viewport_queda_registro.py`, `test_s04_abertura.py` → **104 passaram, 4 pulados, 0 falharam** (282 s). `sonda_ensaio_t33.py --auto-teste` → ok.
2. **Mutações contra o oráculo 228** (locais, desfeitas com `git checkout`; árvore limpa no fim):
   - medir `pos_emitir` **antes** de `emitir` no filho → 2 falham (`..._medida_depois_dos_lotes` e `test_fim_traz_pos_emitir_do_ultimo_bloco`);
   - no pai, gravar a medida **depois** de criar o registro do bloco novo (iria para o bloco N+1) → 2 falham (`test_registro_do_pai_...` e `test_decisoes_do_vigia_...`).
   O oráculo pega os dois erros que importam (ordem no filho e bloco certo no pai).
3. **229 (ponta 3acaf25):** módulo compilado com `prototypes/s04/obimcore/build.sh` numa pasta temporária (build 8,4 s, sem aviso do compilador); `test_s04_t30d3_reenvio_oraculo.py`, `test_s04_t30d2_sublotes_oraculo.py`, `test_s04_cena.py`, `test_s04_t30a1_sem_oraculo.py` → **35 passaram, 0 pulados**. O teste `test_troca_nao_sobe_a_geracao_e_limpar_sobe`, que no lote 65 pulava pela guarda, agora **roda e passa sem edição**.
4. **CI (gh pr checks):** 222, 227, 229 e 231 com todos os checks verdes, `linux` e `windows` incluídos; os três primeiros e o 231 estão `CLEAN/MERGEABLE`. O **228 não tem CI** (a base dele é o ramo do 227, e o CI só roda em PR para o `main`).

Não rodei: Windows/MSVC (fica com o CI), a placa, as 30 execuções do T34.

## 1. Vereditos por PR

### PR 222 (T34 corrigido): **APROVADO**
1. A correção 1 do lote 65 foi cumprida exatamente: em `test_t15c_iii_...`, o laço `for y in [x, *rep["iii"]]` aplica `maior_intervalo_ms < 50`, `quadros >= 20 × gil_preso_ms / 1000`, `conteiner_python is False` e classe `PySide6.` à execução principal **e** a cada uma das 3 repetições. A conferência de `conf["iii"]` ficou (nada saiu).
2. Números iguais: 0,7; 700 ms; 0,8/0,3; 50 ms; 20 quadros/s. Nenhum caso removido. Só o arquivo de teste e o relatório.
3. A regra "≥ 700 ms" vale pela mediana das 3 repetições, e o desenho é conferido em cada uma delas, com o número de quadros proporcional à duração de cada uma: agora "o desenho não parou durante pelo menos ~700 ms" é provado na mesma medida.
4. Mutação (principal livre) reprova: mediana 1,00 > 0,7. 30/30 na rodada final; tabela completa no relatório.
5. CI do próprio PR verde, inclusive `windows` (a conferência de 700 ms no Windows passou nesta rodada).
- Sobre a falha isolada 29/30: ver §2, ponto 1. Não bloqueia.

### PR 227 (T29e implementação): **APROVADO**
1. Filho (`processo_malhas.py`): `pos_emitir = pico_memoria_mb(atual=True)` logo depois de `emitir(prods, feitos)`; vai como campo `pos_emitir_mb` na **próxima** mensagem `bloco` (`None` no 1º bloco do filho) e no `fim`. Nenhum tipo novo de mensagem (o oráculo confere o conjunto de tipos).
2. Pai (`carregador.py`): `_gravar_pos_emitir` só escreve `self._reg["pos_emitir_mb"]` e é chamado **antes** de o registro do bloco novo substituir `self._reg`, então o valor cai no registro do bloco N (o que fez o `emitir`). Não toca em `_base_mb`, `_pedido`, `_decisao`, `_prox_vigia` nem nos tempos. Num filho novo, `_reg` volta a `None` ao começar (linha do `_rodar`) e o 1º `bloco` traz `None`: o bloco em que o filho morreu fica com `pos_emitir_mb = None`, o que é verdade (nunca emitiu).
3. Vigia, G = 1.000 MB, teto 6.000 MB, bloco 250, 60 s e regra de reinício: intocados (o diff não toca em nenhum deles).
4. Sonda: (d′) `|base(N+1) − pos_emitir(N)| ≤ 50`, pareando N e N+1 do mesmo filho; (e) `pos_emitir(N) − fim(N) < 1.000` e toda leitura (`fim`, `pos_emitir`, `base`, `max`) `< 6.000`. O (d) antigo continua calculado e gravado como `base_vs_fim_ok`, fora de `PARADAS`, em `INFORMATIVAS`. `G_MB` e `TETO_MB` só lidos.
5. Escopo: só os 3 arquivos permitidos, +44/−12. CI verde.
- Observações (não bloqueiam):
  - a docstring da sonda ainda diz "`false` = reprovou" para todo `parada.<nome>`; `base_vs_fim_ok` falso **não** para o ensaio. O líder lê `PARADAS`, não a docstring. Corrigir na próxima vez que alguém mexer na sonda;
  - (e) sai `None` quando nenhum bloco tem `pos_emitir_mb`, mesmo que alguma leitura passe de 6.000. Num ensaio com o código novo isso só acontece se nenhum bloco chegar a emitir. Regra de leitura: **`None` nunca conta como "passou"**.

### PR 228 (T29e oráculo): **APROVADO**
1. Cobre os 4 itens do §4 item 4 do lote 65:
   - item 1: ordem no canal (`bloco_fim` → `lote`… → leitura → `bloco` com o campo), com a medida de memória trocada por um contador, o que mostra a ordem das leituras sem depender da memória real; e o `fim` traz a medida do último bloco;
   - item 2: registro do pai com o valor em todos os blocos; mesmo caso do T29b com `OBIM_TESTE_CRESCER_MB` (reinício no bloco 2 pela vigia, `perdido_s < LENTA_S`, decisão ≥ 1.000 MB, nenhum `tarde`); os testes T29b passam sem edição (§0);
   - item 3: casos de borda de `calcular_parada`;
   - item 4: função única `pico_memoria_mb` com `WorkingSetSize`; teste no Windows que pula fora dele; os testes de memória real pulam no macOS.
2. Bordas conferidas: (d′) 50 passa, 50,1 para, nos dois sentidos (±); (e) `fim` 1.000 com `pos_emitir` 1.999 e 1.999,9 passam, 2.000 para; leitura de 6.000 para em cada um dos 4 campos, com 5.999 passando. Bate com "< G" e "< teto" do lote 65.
3. **A leitura "o registro do bloco N guarda a medida feita depois de `emitir` do bloco N (a mensagem chega no bloco N+1)" é a certa para a sonda.** A sonda pareia `pos_emitir(N)` com `base(N+1)` para (d′) e com `fim(N)` do mesmo registro para (e); as duas contas precisam do valor no registro do bloco N. A mutação que grava no N+1 reprova (§0).
4. Nenhum número afrouxado: 50, 1.000, 6.000, bloco alvo 22 e os casos do T29b iguais; `test_numeros_do_produto_nao_mudam` trava os quatro.
5. 23 passam e 1 pula (o do Windows), como o pedido diz.
- Sugestão (não bloqueia): conferir também `sonda.G_MB == carregador.G_CRESCIMENTO_MB`, para que a sonda nunca se desencontre do produto se G mudar por decisão futura.
- Condição de merge (não é correção de código): o 228 precisa de CI verde em `linux` e `windows` antes de entrar. Ver §3.

### PR 229 (T30b3): **APROVADO**
1. `Totais::ger` é lido em `totais()` sob o mesmo `DadosCena::m_`, na mesma linha que lê `lotes_.size()`. Nenhuma trava nova; `mc_` intocado; `estatisticas()` mantém `Motor::m_` → `DadosCena::m_`.
2. `Estatisticas::geracao` (int64) é o último campo; o único lugar que monta a estrutura foi atualizado na mesma ordem. Uma linha na ponte (`r["geracao"] = s.geracao`); nenhum `nb::eval` novo.
3. Código morto fora: `DadosCena::proximo` e `Cursor` (nenhum uso no `git grep`). Comentários de `ger_` ("sobe só em `limpar()`; `atualizar` NÃO o sobe, T30b2") e do cabeçalho de `cena.h` corrigidos, como o lote 65 pediu.
4. Teste de `geracao` do T30d3 deixou de pular e passa sem edição; T30d2, cena e T30a1 passam (§0). CI verde, Windows incluído.
5. Escopo: só `cena.h`, `cena.cpp`, `motor.h` (estrutura e `estatisticas()`) e a linha da ponte.

### PR 231 (T23c): **APROVADO**, sem condição
As 3 rodadas não são condição deste PR: os aceites de correção (1, mesmos testes, e 2, checks obrigatórios) estão conferidos abaixo, a mudança não pode enfraquecer teste nenhum (não toca em comando, chave nem limite), e o lote 65 já aprovou e mesclou o PR 224 com 1 rodada, deixando as 3 rodadas para o relatório T23 final. Aqui é igual: as 3 rodadas e o texto corrigido são tarefa do relatório T23 final (§2, ponto 6), não deste merge.
1. Só `.github/actions/ambiente-windows/action.yml`, `.github/workflows/ci.yml` (+16/−9) e o relatório. Nenhum comando de teste, chave ou variável de ambiente mudou; logo nenhum teste removido, pulado a mais ou com limite maior (aceite 1).
2. Nomes obrigatórios intactos (`linux`, `windows`, `appimage`, `instalador-windows`); o `needs` de `windows` é o mesmo do 224 (`windows-testes`, `windows-obimcore`, `windows-viewport-a`, `windows-viewport-b`, `windows-fluxo-b`); `conferir_ci_windows.py` passa no CI do próprio PR (aceite 2).
3. Cache de pacotes: o passo só roda se `cache_env` não acertou, e fica **antes** de "Criar o ambiente", que é o único que precisa dele. Com o ambiente vindo do cache, os 1,3 GB não são baixados. A chave e a versão da ação são as mesmas; nenhuma ferramenta nova. O aviso `cache-hit` mostra "não usado" quando o passo é pulado.
4. `windows-medicoes` e `windows-sonda` com `needs: windows` e `if: ${{ !cancelled() }}`: continuam fora do bloqueio, rodam também quando o `windows` falha (o que é bom: a informação não se perde) e deixam de disputar máquina com a fila crítica. Não há ciclo: o `windows` não depende deles.
- Observações (não bloqueiam): a execução inteira no GitHub fica mais longa (os dois informativos, 8 a 9 min, começam só depois do `windows`), mas isso está fora da medida de sucesso do cartão, que termina no `windows` e no `instalador-windows`. O cache de pacotes deixa de ser lido pelos trabalhos de teste quando o ambiente acerta; como as duas chaves mudam juntas quando a trava muda, isso não cria falha nova.

## 2. Respostas aos pontos 1 a 7
1. **222:** correção 1 cumprida, números iguais, mutação reprova (§1). **A falha isolada 29/30: aceito, sem nova bateria agora, e peço cartão à parte.** Motivos:
   - as 5 razões do controle estavam normais (0,48 a 0,51), então a mediana passou; a janela presa é outro teste, e a preparação do JSON é comum aos 7 (só um falhou). **Provavelmente** a falha veio de uma conferência que o T34 não tocou e que já existia antes: `razao_exec` na faixa inconclusiva 0,3–0,8 (a própria mensagem diz "repetir; se persistir, levar ao PO") ou `resposta` diferente do esperado, ambas da execução única do JSON. **Não dá para excluir** a conferência nova do T34 sobre `rep["i"]` (`len == 5`, `join > 0`, `ocupada/join`), porque o `print` das razões sai antes de qualquer conferência e a mensagem não foi guardada;
   - o critério 2 do cartão T34 é "30 execuções seguidas sem falhar por essa conferência": a bateria final cumpre, 30/30, com o código exato deste PR;
   - uma bateria nova de 30 sem guardar a mensagem não diria a causa; com 1 falha em 60, também não daria número. O cartão abaixo guarda a mensagem e resolve a dúvida.
   **Cartão novo F0-S04-T34b** (T3, P, autor de teste diferente do T15c e do T34, revisa Opus): (a) gravar no resumo do CI (`GITHUB_STEP_SUMMARY`) e no `print` as 5 razões (com `join` e `ocupada`), as 3 janelas, `razao_exec` e `resposta` da execução do JSON, e guardar a mensagem de qualquer falha numa bateria (a sugestão do lote 65 §1, que não foi feita); (b) se `razao_exec` inconclusiva voltar a aparecer no CI ou numa bateria, medir `razao_exec` também pela mediana, com os mesmos 0,3 e 0,8, sem mudar a resposta. Nenhum número muda. Windows: com o CI, como no lote 65 (se o 700 cair abaixo no Windows pela mediana, é medida real e abre cartão, sem baixar o 700).
2. **227:** a medida e os critérios estão como decididos no lote 65 §4 (§1, itens 1 a 4): medida logo depois de `emitir`, dentro do próximo `bloco` e do `fim`; o pai só grava em `_reg`; nenhum tipo de mensagem novo; vigia, G, teto, bloco e reinício intocados; o (d) antigo calculado e gravado, sem parar.
3. **228:** cobre os 4 itens; as bordas (d′) 50/50,1, (e) 1.999/2.000 com `fim` = 1.000 e leitura de 6.000 estão lá e certas; a leitura "registro do bloco N = medida depois do `emitir` do bloco N, chegando no bloco N+1" é a certa para a sonda (§1, PR 228 item 3); nenhum número afrouxado; as duas mutações reprovam.
4. **229:** `Totais::ger` sob `DadosCena::m_`, sem trava nova, `mc_` intacto, nenhum `nb::eval` novo, teste de `geracao` do T30d3 passa sem edição. **`DadosCena::geracao()`: não tirar agora, nem com cartão só para isso.** É uma leitura sob a trava, sem quem a chame, sem risco; abrir nova rodada de revisão T3 por 1 linha custa mais do que vale. Tirar no **próximo cartão que já for mexer em `cena.h`** (anotar no "próximo passo" do cartão T30 e na linha do LOG), com `git grep` antes.
5. **Medição na placa: a meta M2b fecha.** Pela tabela do `F0-S04-T30-placa.md` (main em cb434a5, RTX 3070, 3 rodadas por caso): o **pior** valor isolado de qualquer troca é 49,7 a 65,2 ms ao trocar a parede do arquivo e 78,4 a 82,8 ms ao criar parede, nos três casos (sintética, 25 MB e detalhado). Como o p95 nunca passa do pior valor, o p95 fica abaixo de 83 ms nos dois tipos de parede, contra o limite de 200 ms. O critério 9 do T30 pede 25 MB e detalhado, 3 rodadas, parede criada e do arquivo separadas: está tudo lá. O detalhado caiu de 6.748 ms para 48,9 ms de mediana. Duas ressalvas, que não reabrem a meta:
   - o relatório não escreve o p95 calculado; deveria escrevê-lo por caso e por tipo (vem do JSON fora do repositório). Pedido ao líder, no próximo commit de estado, sem nova medição: acrescentar a linha do p95; corrigir a "Leitura", que diz que o pior valor isolado foi 65,2 ms quando a própria tabela mostra 82,8 ms ao criar parede (65,2 é o pior da parede do arquivo); e chamar as colunas de "parede do arquivo" e "parede criada", os termos do critério 9 do T30 (hoje "Trocar" e "Criar");
   - é a sonda `sonda_m2b` numa máquina; a medição oficial completa da S04 (juiz estrito, passos A a P) não foi refeita. Fica para a medição de fechamento da S04, como o próprio relatório diz.
   Se não tivesse fechado, o caminho seria o do cartão T30 (opção 2-G ou C = 2 MiB, com novo lote Opus); não é o caso.
6. **231:** aprovo mesclar a mudança do CI (§1). Sobre o relatório e o texto das opções, **concordo com as três opções, mas o texto tem de ser corrigido no relatório final antes de ir ao PO:**
   - o aceite 3 do cartão e o lote 65 (§1, PR 224, item 4) pedem **3 rodadas, mediana e pior, a partir da 2ª**; há 1. Com o 231 no `main`, as rodadas seguintes vêm de envios novos, com duas regras:
     - **um de cada vez**, sem outro PR rodando ao mesmo tempo (lote 65 §1, PR 224, item 5a): esperar cada CI terminar antes do próximo envio;
     - **cuidado com o 222**: ele acrescenta 5 + 3 repetições ao `test_s04_t15c_conferencias.py`, que no Windows roda no `windows-viewport-a` (linha 378 do `ci.yml`), justamente na fila crítica. Uma rodada do 222, ou qualquer rodada depois dele no `main`, não é comparável com o "antes" sem descontar esse tempo. Preferir o 229 (só C++, faz o instalador rodar, não muda teste) e envios pequenos próprios; se usar rodada com o 222, o relatório anota os segundos a mais;
     O relatório T23 final usa essas rodadas;
   - "a fila crítica passou a ser os testes (viewport-a e viewport-b, ~17 min)" está incompleto: pela tabela do próprio relatório, `windows-testes` levou 989 s (16,5 min) e `windows-fluxo-b` 694 s (11,6 min). **Os quatro trabalhos de teste passam de 10 min**, não só os dois do viewport;
   - por isso a opção (b) tem de dizer que seriam os quatro trabalhos de teste divididos, e não só viewport-a/b; e o texto tem de dizer, com número, que **nenhuma das opções sozinha chega a 10 min**: (a) sozinha deixa os testes em 16 a 17 min; (b) sozinha deixa o instalador em 14,5 min; só (a) e (b) juntas podem chegar perto, e com a variação de máquina medida (ambiente de 158 a 283 s) a folga é pequena;
   - "viewport-a ficou mais lento por variação de máquina" é uma hipótese; escrever como hipótese, não como causa;
   - manter (c) rever a meta como opção do PO, sem escolha do implementador; lembrar também que o Linux (cerca de 33 min) segue fora de 10 min (pergunta 2 do cartão T23, ainda aberta).
7. **Ordem de merge:**
   1. **231** primeiro (só CI, independente): assim os envios seguintes já servem de rodadas do T23c, um de cada vez e com o cuidado do 222 (§2, ponto 6).
   2. **229** (independente, já verde): atualizar com o `main` se a proteção pedir, `linux` e `windows` verdes, mesclar. É T3: avisar o PO com resumo curto. É a melhor rodada para o T23c (não muda teste).
   3. **222** (independente, já verde): idem.
   4. **228 com o 227 juntos:** mudar a base do 228 para o `main` (o PR passa a conter o 227 mais o oráculo); esperar o **primeiro CI** do 228, `linux` e `windows` verdes; mesclar o 228; o 227 fica mesclado junto, porque os commits dele estão dentro. Assim o código e o oráculo entram no mesmo commit do `main`, e o oráculo roda no Windows antes de entrar. Se preferir mesclar o 227 sozinho antes, só depois do CI verde do 228 já com base no `main`; nunca o 228 sem CI. Avisar o PO (T3).
   5. Depois do T29e no `main`: a nova rodada do pesado em tela virtual (mesma configuração da 2ª rodada, bloco 250) e as 2 aberturas que faltam, como no lote 65 §4 item 5, lendo (a), (b), (c), (d′) e (e).

## 3. Perguntas ao PO
Nenhuma nova agora. A da meta de 10 min do CI no Windows vai ao PO **quando o relatório T23 final tiver as 3 rodadas e o texto corrigido** (§2, ponto 6). Formulação pronta para o líder, com os números: "O CI do Windows caiu de 34 para cerca de 17 min, mas não chega a 10. Para chegar perto, seria preciso mexer no instalador **e** dividir os quatro trabalhos de teste; mesmo assim a folga seria pequena. Quer (a) e (b) juntos, ou prefere rever a meta?" A recomendação de qual escolher é do líder ao PO; a meta é do PO.

## 4. Resumo para o PO (5 linhas, sem siglas)
1. A troca de parede no arquivo detalhado, na sua placa de vídeo, caiu de quase 7 segundos para cerca de 50 milésimos: a meta de 200 milésimos fecha, com folga, tanto para parede criada quanto para parede do arquivo.
2. O teste que falhava por acaso agora confere o desenho em cada repetição e passou 30 de 30; uma falha rara de outra conferência vira um cartão pequeno para guardar a mensagem.
3. A medida de memória depois do envio dos pedaços da conversão está certa e o teste que a confere pega os erros; entram juntos, e depois o ensaio pesado roda de novo.
4. A limpeza do motor de desenho (contador de geração visível e código morto fora) está aprovada.
5. O teste automático do Windows ficou mais rápido, mas segue longe dos 10 minutos; com mais duas rodadas, o líder traz a você as opções, com números.

## 5. Linha do LOG
`2026-10-20 | F0-S04-T34, T29e, T30b3, T23c, T30 (placa) | LOTE_OPUS_66 (opus, médio) | 222 APROVADO (correção do lote 65 cumprida; falha 29/30 aceita: a mediana do controle passou, causa provável razao_exec/resposta, sem mensagem guardada; cartão novo T34b para guardar razao_exec/resposta e, se voltar, medir razao_exec pela mediana, sem mudar número); 227 APROVADO; 228 APROVADO (rodado no Linux com o 227: 104 passaram e 4 pulados com T29b e carregador; 2 mutações, medir antes de emitir e gravar no bloco N+1, reprovam); 229 APROVADO (35 passaram, teste de geracao do T30d3 deixou de pular; DadosCena::geracao() sem uso sai no próximo cartão que mexer em cena.h); 231 APROVADO (como o 224, 3 rodadas ficam para o relatório T23 final, uma de cada vez e descontando o 222 na fila; texto: os 4 trabalhos de teste passam de 10 min e nenhuma opção sozinha chega a 10); M2b FECHA (pior troca 65,2 ms do arquivo e 82,8 ms criada, contra 200; relatório da placa ganha p95 escrito, leitura do pior corrigida e nomes das colunas); ordem 231 → 229 → 222 → 228 com base no main e CI verde (leva o 227 junto) → nova rodada do pesado | docs/state/lotes/LOTE_OPUS_66/resultado.md`
