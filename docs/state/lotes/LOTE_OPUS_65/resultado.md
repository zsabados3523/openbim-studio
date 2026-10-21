<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_65: resultado (revisão Opus em lote, esforço médio, 2026-10-20)
Revisor: Opus. Não escrevi nenhum dos PRs revisados, nem os oráculos. Li os diffs nos ramos remotos (`git fetch origin` em 2026-10-20), os cartões T30b1, T30b2, T30d3, T34, T23 e T29d, os lotes 62 (§5 e §6), 63 (§3 pontos 1 e 7) e 64 (§2 ponto 5) e os relatórios T34 e T30c (dados reais). Não li `~/openbim-medicao` nem nenhum IFC.

## 0. O que eu rodei (oráculo T30d3 contra o motor do PR 218)
Worktree temporário em `d43d346` (218, que já contém o 217) com `0e5d3bd` (219) mesclado, só local, sem commit em ramo remoto. Módulo compilado com `prototypes/s04/obimcore/build.sh` numa pasta temporária (ambiente `openbim`), testes sob `xvfb-run` e `QT_QPA_PLATFORM=offscreen` (nenhuma janela na tela real).

**Rodada 1** (`--runxfail`): `test_s04_t30d3_reenvio_oraculo.py`, `test_s04_t30d2_sublotes_oraculo.py`, `test_s04_cena.py` → **31 passaram, 1 pulado** (60,7 s). O pulado é `test_troca_nao_sobe_a_geracao_e_limpar_sobe` (guarda: `estatisticas()` sem `geracao`). Medido:
- quadros por troca: 1 KB **2**; 8,97 MiB **5, 5**; 24,24 MiB **5**; 68,27 MiB **5**; 285,36 MiB **5, 5**. Teto = 8 MiB ÷ 2 MiB + 3 = **7**. Igual em toda a faixa, como a escolha T-2 previa.
- `atualizar_ms` mediano: 8,97 MiB 6,72 ms; 285,36 MiB 4,51 ms (limite: 3 × 6,72).
- os contadores `nao_partidos` e `pecas_maiores_que_c` passaram (item 1 do T30d3 e item 10 do T30d2), sem edição.

**Rodada 2** (sem `--runxfail`): T30d3 mais `test_s04_t30a1_sem_oraculo.py`, `test_s04_viewport.py`, `test_s04_viewport_b.py`, `test_s04_viewport_software.py`, `test_s04_selecao.py`, `test_s04_selecao_c.py`, `test_s04_fluxo_a_camera_selecao.py` → **75 passaram, 1 pulado, 5 falharam, todos por XPASS(strict)** (264 s). Os 5 são exatamente os 5 `@AINDA_NAO`:
1. `test_quadros_por_troca_ate_teto_de_c_por_2_mib_mais_3_em_toda_faixa_de_lote`
2. `test_placa_nunca_abaixo_da_cena_menos_a_peca_antiga_em_toda_troca`
3. `test_so_o_sublote_trocado_e_reenviado_bytes_por_troca`
4. `test_troca_repetida_no_mesmo_lote_durante_o_reenvio_mantem_piso_e_estado_final`
5. `test_apagar_em_lote_de_ate_2_mib_leva_no_maximo_2_quadros`

Nenhum outro teste regrediu. Conclusão: o 218 faz o que o oráculo exige, e **com os marcadores no arquivo o 218 deixa o CI vermelho**. Isso decide a ordem de merge (§6).

Não rodei aqui: Windows/MSVC (o 218 **nunca passou pelo CI**: a base dele é `s04-t30b1-cena`, e o CI só roda em PR para o `main`), a placa e a cena inteira do T27 (805,7 MiB).

## 1. Vereditos por PR

### PR 217 (T30b1): **APROVADO**
1. Instantâneo: `instantaneo()` tira `lotes_`, `ger_` e `ver_` sob um único `DadosCena::m_`; `lotes()` passa a usar esse instantâneo. Nenhuma trava nova; `mc_` intocado; `estatisticas()` mantém a ordem `Motor::m_` → `DadosCena::m_`.
2. Contadores: dois campos no fim de `Estatisticas` (inicialização por posição, e o único lugar que monta a estrutura foi atualizado) e uma linha na ponte. Definição escrita no cabeçalho de `cena.h`, inclusive o que acontece depois de `sem`; ela bate com o código de `sem` (`nao_partido && grande`, `peca_maior_que_c && grande && objs.size() == 1`) e com os casos do oráculo, que passaram.
3. `ger_` não muda neste PR (critério 1): `atualizar` continua subindo `ger_` como hoje. O motor ainda lê `geracao()` e `proximo()` separados. Isso é aceitável **só como passo intermediário**: `proximo()` confere `c.ger` contra `ger_` sob a mesma trava, então a leitura do 217 é coerente; o 218 passa para o instantâneo.
4. Escopo: só os arquivos permitidos, +16/−6. CI verde.
- Nota (não bloqueia, vai para o T30b3, §3): o comentário novo de `ger_` em `cena.h` ("sobe em limpar() e em atualizar que refaz lotes") vale com o 217 e **fica errado depois do 218**. O 218 não pode tocar em `cena.h`.

### PR 218 (T30b2): **APROVADO**, com as condições de merge do §6 (não são correções de código)
1. Critério 1 (bytes por troca): reenvia só posição nova ou posição com ponteiro diferente. Como `sem` mantém a posição e a sequência do sub-lote refeito, e os outros ponteiros não mudam, só o refeito e o lote novo entram na fila. O oráculo confere isso por quadros (teto(bytes ÷ 2 MiB) + 3): a folga de 3 quadros é menor que um sub-lote a mais (4 quadros), então reenviar um sub-lote a mais reprovaria. Medido: 5 quadros contra teto 7–8.
2. Critério 2 (piso): durante a troca o desenho continua com a versão antiga em `g.pos`; `tri_placa` só muda em `entrar()`, pela diferença de triângulos. Nenhum zeramento fora de `limpar()` e da perda de contexto. Passou no oráculo.
3. Critério 3 (entrada atômica): com algum trocado, nada entra até `tudo` (fila consumida e nada pendente); aí lote novo e trocados entram juntos no mesmo quadro, e `seq_placa_` vai para a sequência do último lote (a S, porque o refeito mantém a sequência antiga e o lote novo, ou o marcador vazio, é sempre o último). Sem trocado, continua o prefixo contínuo de antes. Conferi que `entrar()` nunca recebe posição fora de ordem: no ramo `tudo`, todas as posições de `g.pos.size()` a `n−1` estão em `prontos`, e o `std::map` as percorre em ordem.
4. Critério 4 (troca repetida): `vigente()` descarta de `prontos` e de `pend` a versão que ficou velha; a nova volta para a fila. Passou (4 trocas seguidas no mesmo lote).
5. Critério 5: `limpar()` sobe `ger_` → `s.ger != g.ger` → tudo zera e é reenviado. Na perda de contexto, a `Gpu` nasce com `ger = −1`: reenvio total. A defesa `s.lotes.size() < g.pos.size()` nunca dispara sem `limpar()`, porque `atualizar` nunca encolhe `lotes_`.
6. Critério 6 (fatia de 28 bytes): `m = min(total − off, (ORCAMENTO_BYTES − gasto) / un * un)` com `if (!m) break;`. O quadro nunca passa de `ORCAMENTO_BYTES` (antes passava 20 bytes). `ORCAMENTO_BYTES`, `ORCAMENTO_TEMPO` e `OBIM_QUADRO_MS` estão intactos. Conferido só no diff: não há contador de bytes por quadro no Python.
7. Critério 7 (travas): `enviar()` roda na thread de desenho sem `Motor::m_`; `instantaneo()` pega só `DadosCena::m_`; o único `Motor::m_` dentro de `enviar` é o de `info_`, sozinho, como antes; `mc_` intocado. Nenhuma trava nova.
8. Falha do `create()`: o lote não se perde (`--prox`, `break`, repete no quadro seguinte), e a entrada atômica não acontece nesse quadro.
9. `cena.cpp`: só a retirada do `++ger_` (1 linha), como o cartão permite.
10. Critério 8 (testes existentes): rodada 2 do §0, verde no Linux.
- Observações (não bloqueiam):
  - cada quadro copia todos os ponteiros (contagem atômica) mesmo com a cena parada. Nos dados reais são 153 a 172 sub-lotes (T30c): custo desprezível;
  - durante a troca, a placa guarda a versão velha e a nova do sub-lote (≈ +8 MiB de memória de vídeo por troca);
  - uma sequência sem fim de trocas adia a entrada dos lotes novos que chegam enquanto isso. Na abertura não há troca, então isso não acontece.
  - Sobra código morto: `DadosCena::proximo`, `Cursor` e o comentário de `proximo` em `cena.h` (vai para o T30b3).

### PR 219 (T30d3): **APROVADO**
1. Cobre os itens 1 a 7 do cartão, com estas ressalvas aceitas:
   - "troca não sobe `ger_`": fica atrás de guarda (§3, ponto 3);
   - instantâneo coerente: sem API no Python, coberto pelo piso de triângulos e pelo diff;
   - bytes por troca: por teto de quadros, não por contador de bytes (suficiente, ver o 218 item 1);
   - item 7: caso novo `c_limpar` em vez de editar o `c_desenho` do T30d2, que é de outro cartão (correto).
2. Nenhum número afrouxado em relação ao lote 62 §6.4: teto(C ÷ 2 MiB) + 3, 3 × no `atualizar_ms`, ≤ 2 quadros no apagar, pixel a pixel na perda de contexto, `bytes_copia` ±(5 × 816 + 64 KiB). O piso (cena − 12 triângulos da parede antiga) é o critério 2 do §6.2.
3. Os 5 `@AINDA_NAO` (§0) falham no `main` puro (CI verde do 219) e viram XPASS com o 218 (medido).
4. **Cena de 387 MiB: aceita.** Com reenvio por posição, os quadros por troca dependem do lote tocado, não do resto da cena. O item 4 é relativo, na mesma cena. Os 5 tamanhos do §6.4 estão todos ali. A cena inteira (805,7 MiB) fica para a sonda (T30c) e para a sessão da placa (A33), sem bloquear.
5. Quem tira os marcadores: o autor do oráculo T30d3, em commit próprio **no ramo do 218** (§6).

### PR 222 (T34): **REPROVADO**, 1 correção
1. **(bloqueia)** A janela presa (iii) ficou separada da conferência que depende dela. Antes, a mesma execução do `conferencias.json` conferia `gil_preso_ms ≥ 700` **e** que o desenho não parou durante esse tempo (`maior_intervalo_ms < 50`, `quadros ≥ 20 × gil_preso_ms / 1000`). Agora o ≥ 700 é conferido pela mediana das 3 repetições de `c_rep`, mas as conferências do desenho continuam só na execução do JSON, cuja duração ninguém confere mais. "O desenho não parou durante pelo menos 700 ms" deixou de ser provado na mesma medida. **Correção:** em `test_t15c_iii_...`, aplicar às 3 amostras de `rep["iii"]` as mesmas conferências que já valem para `conf["iii"]`: `maior_intervalo_ms < 50`, `quadros ≥ 20 × gil_preso_ms / 1000`, `conteiner_python is False` e classe `PySide6.`. Fica também a de `conf["iii"]` (nada sai). Nenhum número muda. Depois, 30 execuções de novo no Linux, com a tabela no relatório.
2. O resto está certo:
   - 0,7, 700 ms, 0,8/0,3, 50 ms e 20 quadros/s iguais; nenhum caso saiu;
   - a mutação reprova (mediana 1,01);
   - mediana de 5 e de 3 é forma legítima de medir: a chance de passar quando não há efeito **cai** (precisa de 3 de 5 abaixo de 0,7), e a de falhar por acaso também cai.
   - Controle (i) separado da execução do JSON: aceito, porque o controle prova que o método distingue na máquina, e o `razao_exec` da execução do JSON continua com a faixa inconclusiva 0,3–0,8.
   - Sugestão (não bloqueia): imprimir as 5 razões e as 3 janelas no resumo do CI (`GITHUB_STEP_SUMMARY`). Hoje o `print` só aparece quando o teste falha, então não sabemos como o Windows ficou perto dos 700 ms.
3. Windows: a conferência de 700 ms fica com o CI, aceito. Se ela falhar no Windows de novo com mediana abaixo de 700, é medida real (máquina mais lenta segura menos), não sorte: abre cartão próprio, sem baixar o 700.

### PR 224 (T23b): **APROVADO** para mesclar
1. Só `ci.yml`. Nenhum teste removido nem pulado a mais, nenhum limite maior. Contagens no CI do próprio PR (run 39479653845) iguais às do cartão T23: ponte 21; viewport A 75 + 1 pulado; T15a 10, T15b 12, T15c 7, T15d 4, T15e 13, T15g 7; R1-j 9. `OBIM_CI=1` mantido no passo da ponte.
2. Nomes obrigatórios intactos (`linux`, `windows`, `appimage`, `instalador-windows`). `windows-obimcore` está no `needs` de `windows`, o agregador confere `needs.*.result`, e o `conferir_ci_windows.py` (T23a) roda e passa.
3. O R1-j prova o mesmo módulo: a mesma chave `obimcore-win-<run_id>` e os mesmos arquivos ("Cache hit ... obimcore-win-39479653845"), agora compilados no `windows-obimcore`. Os 21 testes da ponte rodam sobre outro build do mesmo commit e da mesma trava, no `windows-viewport-a`. O módulo que vai no instalador é provado pelo R1-j, como antes.
4. Meta de 10 min não atingida (27m03). Pela regra do `CLAUDE.md`, isso **não se contorna**: segue a T23c e, no fim, o relatório T23 com opções ao PO, como o cartão já manda. Uma rodada não vale como número: são 3 rodadas, mediana e pior, a partir da 2ª.
5. Para a T23c, além das hipóteses (1) a (4) do cartão:
   - (a) separar a espera por máquina livre do tempo de trabalho na tabela (os 7 min de fila do job novo), medindo com nenhum outro PR rodando ao mesmo tempo;
   - (b) ver se `windows-sonda` e `windows-medicoes` (informativos) disputam máquina com a fila crítica e podem começar depois dela;
   - (c) gravar o cache do módulo logo depois do build, com a mesma ação já fixada (`actions/cache/save` da mesma versão; versão nova é pergunta ao PO);
   - (d) o build limpo agora roda duas vezes (`windows-obimcore` e `windows-viewport-a`, ≈ 87 s cada, em paralelo): só tirar se o ganho for medido.

## 2. Respostas aos pontos 1 a 6 (e 7)
1. **218:** critérios 1 a 7 conferidos (§1). Oráculo rodado: os 5 `@AINDA_NAO` viram XPASS (§0). Nada a corrigir no código.
2. **217:** instantâneo e contadores certos. A leitura separada de `geracao()`/`proximo()` é coerente e só vale até o 218.
3. **219:** cobre 1 a 7, nenhum número afrouxado, os 5 marcadores conferidos, cena de 387 MiB aceita.
   - **Decisão sobre `geracao`: expor**, em cartão novo **F0-S04-T30b3** (T3, P, ≤ 30 linhas; implementa sonnet, outro agente que não o do T30b2; revisa Opus no próximo lote):
     - `Totais` ganha `ger` lido sob o mesmo `DadosCena::m_` em `totais()`;
     - `Estatisticas::geracao` em `motor.h`;
     - 1 linha na ponte (`r["geracao"]`);
     - corrigir os comentários de `ger_` e de `proximo` em `cena.h`;
     - tirar `proximo()` e `Cursor`, se nada mais os usar (hoje ninguém usa: `git grep`).
     - Arquivos: `cena.h`, `cena.cpp`, `motor.h` (só `Estatisticas` e `estatisticas()`), `ponte_viewport.cpp` (1 linha).
     - Motivo: "troca não sobe `ger_`" e "`limpar()` sobe" são critérios escritos (lote 62 §6.1, lote 63 §3 ponto 1). O piso de triângulos pega a troca que subisse `ger_`, mas **não** pega um `limpar()` que deixasse de subir, porque o motor reenviaria por ponteiro e a imagem sairia igual. Custa 3 linhas, e a guarda do oráculo passa a valer sozinha, sem edição.
     - Não bloqueia 217, 218 nem 219.
4. **222:** números iguais, nenhum caso saiu, a mutação reprova e a mediana é legítima. Os valores únicos do JSON principal deixarem de ser o limite é aceitável para o controle (i), **não** para a janela (iii) sem as conferências do desenho nas repetições: correção 1 do §1. Windows: com o CI.
5. **T29d** (cartão novo): ver §4.
6. **Ordem de merge:** ver §6.
7. **224:** aprovado; T23c como no §1.

## 4. T29d: decisão
**Confirmo a leitura do líder** (código no `main`):
- em `processo_malhas.py`, no laço de blocos, `bloco_fim` mede `VmRSS` logo depois de `_bloco` e **antes** de `emitir(prods, feitos)`;
- o `bloco` seguinte mede a base depois de `emitir`, de `_RETIDO.clear()` e de `enviar("fase")`;
- no pai (`carregador.py`, ramos `bloco` e `bloco_fim`), o vigia é armado com essa base e **desarmado** no `bloco_fim`. Entre os dois pontos ninguém vigia.

Então `base(N+1) − fim(N)` é a sobra de `emitir` (montar os lotes, copiar, mandar pelo canal; o alocador nem sempre devolve a memória ao sistema) mais ruído. **Não** é erro do vigia. A premissa da regra (d) do lote 63 ("a base é a memória do fim do bloco anterior") não vale por construção. A regra estava mal definida, não o produto.

1. **A base está no ponto certo.** É a memória real do filho no começo da conversão do bloco, que é o que o vigia (crescimento ≥ G desde o começo do bloco) usa. Não mudar o vigia, G = 1.000 MB, o teto de 6.000 MB, os 60 s, o bloco 250 nem a regra de reinício.
2. **Uma medida nova, sem mudar decisão nenhuma:** `pos_emitir_mb` = `pico_memoria_mb(atual=True)` logo depois de `emitir(prods, feitos)` do bloco N.
   - O filho a manda **dentro da próxima mensagem `bloco`** (campo `pos_emitir_mb`) e, no último bloco, dentro de `fim`. Nenhum tipo novo de mensagem.
   - O pai só a grava no registro do bloco (`est["blocos"]`), sem tocar em `_base_mb`, `_pedido`, `_decisao` nem nos tempos.
   - Arquivos: `prototypes/viewport_qrhi/processo_malhas.py` (a medida), `prototypes/viewport_qrhi/carregador.py` (1 a 2 linhas de registro), `prototypes/s04/sondas/sonda_ensaio_t33.py` (o critério). Classe T3.
3. **Critério novo para o ensaio continuar** (substitui o (d) do lote 63; as condições (a), (b) e (c) ficam como estão):
   - **(d′)** `|base(N+1) − pos_emitir(N)| ≤ 50 MB`: entre os dois pontos só estão `_RETIDO.clear()` (vazio fora do gancho de teste) e uma mensagem. Passar de 50 quer dizer que a base mede outra coisa: para.
   - **(e)** `pos_emitir(N) − fim(N) < G = 1.000 MB` e toda leitura (`fim`, `pos_emitir`, `base`, `max`) `< 6.000 MB`. É o crescimento que o vigia não vê, porque está desarmado durante `emitir`; se chegar a G, para e volta ao Opus. Nenhum número novo: G e teto são os do produto.
   - O (d) antigo continua **calculado e gravado** (falso onde falhar) e só deixa de ser critério de parada. Não se reinterpreta o ±50 do que já foi gravado. É regra de parada nova, decidida aqui, com linha no LOG.
4. **O que o autor do oráculo** (outro agente, não o implementador) exige, em teste novo ou nos do T29, sem editar números existentes:
   1. com o filho em blocos, cada `bloco` a partir do 2º e o `fim` trazem `pos_emitir_mb`, e ela é medida depois de todos os `lote` do bloco anterior (ordem no canal: `bloco_fim` → `lote`… → `bloco` com o campo);
   2. o registro do pai traz o valor e as decisões do vigia não mudam: todos os testes T29/T29b/T29c passam sem edição, com as mesmas decisões nos ganchos `OBIM_TESTE_CRESCER_MB`;
   3. `calcular_parada` da sonda tem os casos de borda (d′) = 50 passa e 50,1 para; (e) 999 passa e 1.000 para; 6.000 para, no padrão dos casos que já existem;
   4. no Windows a medida usa a mesma função (`WorkingSetSize`); no macOS pula, como hoje.
5. **O ensaio gravado não basta.** `t33_r1.json` não tem `pos_emitir_mb`, então (d′) e (e) não se calculam nele. O líder só pode, por `jq`, registrar (a), (b) e (c) do bloco 24, para o histórico. **Nova rodada**, depois do T29d no `main`: o pesado de novo (mesma configuração da 2ª rodada, bloco 250, tela virtual) e as 2 aberturas que faltam.
6. Observação para depois (não entra no T29d, não muda número): `prods` do bloco N continua na memória durante todo o `_bloco` N+1, porque só é trocado quando ele termina. Soltar `prods` logo depois de `emitir` provavelmente baixa o pico em até o tamanho das malhas de um bloco. Com a folga de 79 MB da conta A, vale um cartão de medida próprio (T3), com nova rodada, se o líder quiser.

## 5. Perguntas ao PO
Nenhuma neste lote. A meta de 10 min do CI no Windows (T23) não foi atingida, mas o cartão T23 já manda levar as opções ao PO no relatório final, depois da T23c. Não é pergunta nova agora.

## 6. Ordem de merge e marcadores
1. **PR 224** (T23b): quando quiser, independente dos outros.
2. **PR 217** (T30b1): já verde; entra sozinho (não muda o comportamento).
3. **PR 219** (T30d3): depois do 217. Com o 217 no `main`, o teste dos contadores passa a valer pela guarda, sem edição. Os 5 `@AINDA_NAO` continuam falhando como esperado (o 217 não muda o reenvio). Conferir verde no CI do 219 depois de atualizado com o `main`.
4. **PR 218** (T30b2): **só depois do 219, nunca antes**:
   - mudar a base do 218 para o `main` e mesclar o `main` (com 217 e 219) no ramo `s04-t30b2-motor`;
   - o **autor do oráculo T30d3**, em commit próprio nesse ramo, tira as 5 linhas `@AINDA_NAO` (e a definição `AINDA_NAO`, se ficar sem uso), e nada mais;
   - o implementador do T30b2 não toca no teste;
   - `linux` **e** `windows` verdes nesse commit. É o **primeiro CI do 218 e o primeiro build dele no MSVC**. Se o Windows falhar, a contagem de 5 tentativas começa ali;
   - o líder confere que o diff do PR é `d43d346` + o merge do `main` + só as linhas dos marcadores.
   - O 218 não pode entrar antes do 219: entraria sem oráculo no `main`. Também não pode entrar com os marcadores ainda no arquivo: viraria vermelho por XPASS(strict) (medido, §0).
5. **PR 222** (T34): depois da correção 1 do §1, das 30 execuções de novo e do CI verde. Não depende dos outros.
6. **T30b3** (cartão novo, ponto 3 do §2): depois do 218 no `main`; Opus no próximo lote.
7. Ao fim do 218, avisar o PO (é T3) com resumo curto.

## 7. Resumo para o PO (5 linhas, sem siglas)
1. A troca de uma parede agora reenvia ao desenho só o pedaço que mudou: leva 5 quadros em qualquer tamanho de arquivo, abaixo do limite de 7.
2. As duas partes dessa mudança e o teste que as confere estão aprovados; entram uma de cada vez, o teste antes do código.
3. O teste que falhava por acaso ficou mais estável, mas falta uma conferência que se perdeu; volta ao autor (uma correção pequena, nenhum número muda).
4. A separação do módulo no teste automático do Windows está aprovada; o tempo caiu de 34 para 27 minutos, ainda longe dos 10, e o próximo passo segue cortando.
5. O alarme de memória da conversão estava medindo certo; a regra de conferência é que comparava dois momentos diferentes. Ganha uma medida a mais, e o ensaio precisa de uma nova rodada.

## 8. Linha do LOG
`2026-10-20 | F0-S04-T30b1, T30b2, T30d3, T34, T23b, T29d | LOTE_OPUS_65 (opus, médio) | 217 APROVADO; 218 APROVADO (oráculo T30d3 rodado contra 218+219 no Linux: 31 passaram e 1 pulado com --runxfail; sem ele 75 passaram, 1 pulado e os 5 @AINDA_NAO em XPASS(strict); quadros por troca 2/5/5/5/5 contra teto 7); 219 APROVADO (cena de 387 MiB aceita; geracao exposta no cartão novo T30b3); 222 REPROVADO 1 vez (conferências do desenho da janela presa têm de valer nas 3 repetições; números iguais); 224 APROVADO (meta de 10 min não atingida: 27m03, segue T23c); ordem 224 a qualquer hora, 217 → 219 → 218 com os 5 marcadores tirados pelo autor do oráculo no ramo do 218 e o 1º CI linux+windows do 218 verde; T29d: base no ponto certo, (d) mal definida, medida nova pos_emitir_mb, critérios (d′) ≤ 50 MB e (e) < G e < teto, nova rodada do pesado e das 2 aberturas | docs/state/lotes/LOTE_OPUS_65/resultado.md`
