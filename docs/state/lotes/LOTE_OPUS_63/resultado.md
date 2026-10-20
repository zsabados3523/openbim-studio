<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_63: resultado (revisão dos PRs 199, 200 e 204 e pontos abertos do T30 e do T33b)
Revisor: Opus, esforço médio, contexto fechado (pedido, lote 62 §5 e §6, cartões T30, T30a1, T30a2, T30d1, ramos remotos `s04-t30d1-oraculo` 6a0a20f, `s04-t30a1-sem` 73a16a2, `s04-t30a2-sublotes` 0e52319, relatório T33b e `carregador.py`/`processo_malhas.py` do `main`). Não li `~/openbim-medicao` nem nenhum IFC. Nada foi mesclado, nem enviado, nem editado fora deste arquivo.

## 0. O que rodei (worktrees temporários em `/tmp`, já removidos; `build.sh` em pasta temporária; `QT_QPA_PLATFORM=offscreen` e `xvfb-run`)
| build | `test_s04_t30a1_sem_oraculo.py` (do PR 199) | `test_s04_cena.py` |
|---|---|---|
| `main` (6d4551e) | 2 passam, `bytes_copia` em xfail; **medido: +788.869 bytes** (lote novo 3.528) | passa |
| PR 200 | 2 passam; `bytes_copia` **XPASS(strict)** = falha por estar consertado; **medido: +2.757 bytes** | passa |
| PR 204 | equivalência **falha**: tabela de `objetos(seq)` diferente nos lotes de 8,2 e 24 MiB (só o último sub-lote) e contagem de lotes (9 contra 5 esperados, etc.) | **7 passam** (sem edição) |

Conta exata do +2.757 do PR 200 (GCC, `sizeof(Objeto)` = 80): lote novo 4 × 816 + 4 × 80 + 4 × 23 (texto do GlobalId) = 3.676; parede removida −816 − 80 − 23 = −919; 3.676 − 919 = **2.757**. É o tamanho exato do critério 2 do T30a1, sem sobra.

Sondas rápidas (só leitura, pasta temporária):
- PR 204, cubos sintéticos: 10.280 cubos (8.388.480 bytes, ≤ C) ficam em 1 sub-lote; 31.000 cubos viram 4 sub-lotes, todos ≤ C, e a união dos GlobalIds, na ordem, é igual à da entrada. A sequência devolvida é a do último sub-lote. Um lote com 1 índice apontando para vértice de outra peça fica inteiro.
- **A ponte aceita índices desalinhados**: um array `<u4` C-contíguo com deslocamento de 2 bytes (`flags.aligned == False`) passa por `vetor()` (`ponte_viewport.cpp:22` só confere a contiguidade). Ver 204, item 1.
- **Cena do T27** (`sonda_t27.lote_de`, 3 paredes): os lotes de 8,97, 24,24, 68,27 e 285,36 MiB **ladrilham** (peças em ordem, sem vértice compartilhado). Em todos, a peça de enchimento sozinha é maior que C. Ver o ponto 2.
- O "segmentation fault" no fim da sonda acontece também no `main`: é a ordem de encerramento da sonda (sem `parar()`), não do PR.

## 1. Veredito por PR

### PR 200 (T30a1, `sem` consertado): **APROVADO**
Conteúdo aprovado: exatamente 73a16a2 (`cena.cpp`, +14 −6). Critérios: 1 (o oráculo do 199 passa nos 2 casos de equivalência, inclusive a imagem igual à da cena remontada), 2 (+2.757, exato), 3 (`tocados` é contado pela tabela antes de alocar `morto` e `usado`; lote sem removido devolve `nullptr` sem alocar nada), 4 (`test_s04_cena.py` passa; CI verde), 5 (20 linhas). Não mexe em `ger_`, `ver_` nem nas travas.
Sugestões (não bloqueiam):
1. `cena.cpp:33`, `:36` e `:52`: cada objeto do lote tocado faz agora 3 buscas em `rem` (antes eram 2). Com dezenas de milhares de peças, guardar num vetor pequeno as posições dos tocados evita a 3ª. Só no lote tocado; fica para quando houver medida.
2. `cena.cpp:79` (preparar): a troca de `assign` pelo construtor reduz o `bytes_copia` absoluto em cerca de 8 bytes por peça. Nenhum oráculo usa número absoluto (rodei), mas números antigos do T32a não se comparam 1 a 1 com os novos. Escrever isso no relatório do T30, não no código.

### PR 199 (T30d1, oráculo do `sem`): **APROVADO**
Conteúdo aprovado: 6a0a20f **mais um commit do autor do oráculo** (o agente que escreveu o T30d1, nunca o implementador do T30a1) que mude **só** isto em `tests/test_s04_t30a1_sem_oraculo.py`:
- apagar a linha 20 (`AINDA_NAO = pytest.mark.xfail(...)`);
- apagar a linha 147 (`@AINDA_NAO`);
- na linha 4, trocar o trecho "`@AINDA_NAO` (xfail estrito): `bytes_copia` sem sobra." por "`bytes_copia` sem sobra: passa desde o T30a1 (PR 200)."

Nada mais. O líder confere com `git diff 6a0a20f` (3 linhas).
Confirmado: falha hoje pelo motivo certo (+788.869 bytes no `main`, contra o limite de 3.528 + 64 KiB) e passa com o T30a1. A equivalência passa com o `sem` de hoje e com o consertado. Cobre os casos do cartão: 1 peça, várias do mesmo lote, todas de um lote de 1 KB e de 80 KB, lotes diferentes, nenhuma, marcador vazio e lote só com marcador.
Sugestões (não bloqueiam):
1. `:140` e `caso(..., limite=900)`: o cartão pedia "≤ 120 s cada". 900 é teto de espera, não duração (rodou em cerca de 33 s). Corrigir o **texto do cartão** ("teto de espera do caso; o padrão da casa é 400 s"), não o teste.
2. `:86-90`: a caixa é conferida só pelo centro (o `alvo` da câmera). A imagem final igual à da cena remontada cobre o tamanho da caixa, porque o `enquadrar` depende dele. Fica assim, mas o T30d2 confere a caixa direto, se o acessor do ponto 5 existir.

### PR 204 (T30a2, sub-lotes): **REPROVADO**
1. **(bloqueia: comportamento indefinido)** `cena.cpp:70` lê os índices por `reinterpret_cast<const uint32_t*>(I.p)`, e o comentário diz "numpy: alinhado". Não é garantido: a ponte só confere a contiguidade (`ponte_viewport.cpp:22`), e a sonda mostrou um array desalinhado aceito. As leituras em `:71`, `:86` e `:112` dependem disso. O `main` usava `memcpy` (seguro), então isso é uma regressão. No x86 funciona por sorte; o compilador pode vetorizar supondo alinhamento de 4 bytes. Conserto dentro de `cena.cpp` (a ponte é proibida): ler cada índice por `memcpy` para uma variável local, por meio de uma função pequena (`uint32_t indice(const unsigned char* p, size_t k)`). **Sem** copiar os índices para um buffer temporário antes de partir, porque isso quebra o "sem montar antes" (critério 4). O comentário de `:70` sai.
2. **(bloqueia: contrato do critério 1 e do lote 62 §5.2.3)** `cena.cpp:119` marca `nao_partido` em **todo** sub-lote maior que C. Isso mistura dois casos que o cartão separa: (a) peça maior que C, sozinha num sub-lote de um lote que ladrilha, que é o comportamento certo; (b) lote que não pode ser partido. Na cena do T27, os "8 de 13 lotes que não partem" são **todos do caso (a)**: os lotes ladrilham, e o enchimento é uma peça só, de até 285 MiB (conferido acima). O contador fez parecer que os lotes não partem. Pior: um lote do caso (b) com até C não é contado em lugar nenhum. Conserto: dois campos em `Dados` e em `Totais`: `nao_partidos` (lote de entrada que não ladrilha e passa de C) e `pecas_maiores_que_c` (sub-lote de uma só peça maior que C). Os dois ficam calculados na cena; a exposição ao Python fica para o T30b (ponto 3).
3. **(corrigir junto)** `cena.cpp:42`: `sem` copia `nao_partido` do lote antigo. Depois de remover peças, o sub-lote pode ficar menor que C e continuar marcado. Recalcular os dois campos do item 2 a partir do resultado (tamanho e número de peças do lote refeito).
4. **(bloqueia o merge, não é defeito do código)** O PR 204 sozinho no `main` deixa o oráculo T30d1 vermelho (ver §0). Ele só entra junto com o T30d2 (ponto 4), na ordem do §2.
5. **(sugestão, não bloqueia)** `cena.cpp:83-90`: o teste de "partível" é tudo ou nada. Uma única peça com vértice compartilhado faz o lote inteiro ficar sem partir, mesmo que outras fronteiras fechem. O lote 62 §5.2.3 falava em partir "onde a faixa de vértices fecha". A forma mais simples é aceitável **se** a medida do ponto 2 der zero lotes do caso (b) com parede nos dados reais. Se der algum, a divisão parcial vira cartão próprio.
6. **(processo, registrar no LOG)** O critério 5 do cartão mandava parar com `AGUARDA_OPUS` quando a fração partível desse menos de 100%. O líder mandou seguir. Como nada foi mesclado e o caso veio a este lote, não reprova. Mas a leitura do 0,75% estava errada (item 2 e ponto 2), e era isso que a parada devia pegar.

O resto está certo: divisão na fronteira de peça; leitura direta da entrada, sem montar o lote grande (o pico fica em lote + tabela de objetos, abaixo de lote + C); um único `DadosCena::m_` e um único `++ver_` em `adicionar_lote` e em `atualizar`; devolve a sequência do último sub-lote; deslocamento conferido pelo lote de entrada; `objetos(seq)` com faixas rebaixadas ao buffer do sub-lote; `test_s04_cena.py` passa sem edição; `ger_`, `ver_` e a ordem das travas intactos; o motor (`motor.h:223-224`) só avança `seq_placa_` com o sub-lote completo e em ordem, então a sequência S aparece só com todos os sub-lotes na placa. Diff: 118 linhas.

## 2. Ordem de merge e o marcador `@AINDA_NAO` (ponto 6)
1. **PR 200** primeiro (CI verde sozinho, porque o oráculo ainda não está no `main`).
2. **PR 199** depois. O **autor do oráculo T30d1**, em commit próprio, mescla o `main` (já com o 200) no ramo dele e tira o marcador com exatamente as 3 linhas do §1. Com `linux` e `windows` verdes nesse commit, merge. Isso mostra no CI o oráculo passando contra a implementação. Quem tira o marcador é o autor do oráculo, depois de o 200 estar no `main`, nunca o implementador.
3. **PR 204**: só depois da correção dos itens 1 a 3 (mesmo implementador, que não toca em teste), do T30a3 (ponto 5) e do T30d2 (ponto 4). Ordem: T30d2 entra antes, com as conferências adaptadas valendo nos dois casos (com sub-lote e sem) e as novas em `@AINDA_NAO`. Depois entra o 204, com o autor do T30d2 tirando os marcadores em commit próprio no mesmo esquema. Revisão Opus do 204 corrigido e do T30d2 no próximo lote.

## 3. Respostas aos pontos 1 a 5 e 7

### Ponto 1 (reescopo): de acordo, com dois ajustes no cartão T30b
"Troca não sobe `ger_`" e "instantâneo coerente" só fazem sentido junto do reenvio por posição. Sozinhos, a placa ficaria com o lote velho. Ir para o T30b está certo. Do §6.1 do lote 62, nada fica sem dono **se** o cartão T30b ganhar:
1. os dois critérios, escritos como no §6.1 (critérios 3 e 4 do T30a1): troca não sobe `ger_`; `limpar()` sobe; ponteiros, `ger_` e `ver_` tirados juntos sob `DadosCena::m_`;
2. **arquivos permitidos** `cena.h` e `cena.cpp`, só para esses dois itens. Hoje o §6.2 permite só `motor.h`, e o `ger_` vive em `cena.cpp`. Mais `ponte_viewport.cpp` só nas linhas de `estatisticas` (ponto 3);
3. o oráculo desses dois itens no T30d2 ou num T30d3, por outro agente. O T30d1 não os cobre.

O limite de 400 linhas continua valendo. Se o T30b passar disso com esses itens, dividir antes (T30b1 cena, T30b2 motor), nunca pedir exceção.

### Ponto 2 (critério 5 do T30a2): leitura confirmada, mas a causa do T27 é outra
- **Confirmo a regra:** lote que não ladrilha fica inteiro e é contado (lote 62 §5.2.3).
- **A causa no T27 é outra.** Os 8 lotes "não partidos" do T27 ladrilham. Eles têm uma peça de enchimento maior que C, que fica sozinha, como manda a regra. O 0,75% mede o enchimento, não a troca. Para a decisão T-2, o número que conta **não** é "fração dos bytes em sub-lotes ≤ C". É o **tamanho do sub-lote onde está a peça que se troca**. No T27, com o 204 corrigido, a parede fica num sub-lote pequeno e o enchimento nunca é refeito.
- **O que medir nos dados reais**, com o carregador de hoje e a `Cena` do 204 corrigido, em tela virtual, só números, por outro agente; vai à sonda do T30c ou a um cartão de medida T2:
  1. por lote de entrada: bytes, número de peças, se ladrilha (e, se não, o motivo: fora de ordem, vértice compartilhado ou sobra), número de sub-lotes, maior sub-lote;
  2. peças maiores que C: quantas e de que classe IFC (só o nome da classe e a contagem; nenhum GlobalId);
  3. para cada parede (`IfcWall`, `IfcWallStandardCase`) e demais classes editáveis na 1.0: o tamanho do sub-lote que a contém. Gravar o máximo, o p99 e quantas ficam em sub-lote maior que C;
  4. número total de lotes antes e depois (chamadas de desenho, para o M5 depois).
- **Regra decidida antes de ver os dados:** a T-2 vale se (i) nenhuma parede ficar em sub-lote maior que C e (ii) nenhum lote do caso (b) tiver parede. Se uma parede for, ela mesma, maior que C, o próprio lote novo passa de C, e isso não é caso da T-2: volta ao Opus com o número. Se (ii) falhar, abre-se o cartão da divisão parcial (204, item 5).

### Ponto 3 (`nao_partidos` no Python): de acordo, no T30b
De acordo, com os **dois** campos do 204 item 2 (`nao_partidos` e `pecas_maiores_que_c`): `Estatisticas` em `motor.h` (T30b) e uma linha em `ponte_viewport.cpp:121`. O T30d2 os lê com guarda: pula se o campo não existir, sem afrouxar nada.

### Ponto 4 (oráculo T30d2): plano confirmado
Autor: um agente diferente do implementador do T30a2 (e do T30b). Revisão Opus em lote. Arquivos: o T30d1 adaptado e um teste novo. Se passar de 400 linhas, dividir em T30d2a (adaptação e divisão) e T30d2b (desenho e memória). O T30d2 deve exigir:
1. **Adaptar o T30d1** sem afrouxar nada: a tabela de uma chamada é a concatenação de `objetos(q)` para q de (sequência anterior + 1) até a devolvida; a contagem de lotes esperada vem dessas faixas mais os marcadores; nenhuma conferência supõe um lote por chamada. As conferências de forma, tabela, caixa, imagem e `bytes_copia` ficam iguais.
2. **Sequência:** as sequências de uma chamada são seguidas, a devolvida é a última, crescem entre chamadas; `atualizar` com lote novo maior que C devolve a do último sub-lote; o marcador continua sendo 1 lote.
3. **Teto:** todo sub-lote ≤ C (nv × 28 + ni × 4), salvo o de uma única peça maior que C e o lote que não ladrilha (um só sub-lote com a entrada inteira). Casos: lote de exatamente C; C mais 1 peça (10.280 e 10.281 cubos); peça gigante no início, no meio e no fim; lote com vértice compartilhado; tabela fora de ordem.
4. **Forma canônica da união** igual à da entrada, em bits, por GlobalId. Pelo acessor do ponto 5, se existir (guarda); senão, pela imagem, como no T30d1. As faixas de `objetos(q)` começam em 0 em cada sub-lote e são contíguas.
5. **Desenho:** captura da cena com sub-lotes igual, pixel a pixel, à da mesma cena entregue já partida pelo Python e à captura depois de `perder_contexto()`.
6. **Honestidade na abertura:** no primeiro quadro com sequência ≥ S (`relogio()`), `triangulos_na_placa` já inclui todos os sub-lotes da chamada.
7. **Erros atômicos:** índice ou objeto inválido e deslocamento diferente recusam o lote inteiro com `ValueError`, e a cena fica intacta (nenhum sub-lote publicado).
8. **Índices desalinhados** (deslocamento de 2 bytes) dão o mesmo resultado que os alinhados (guarda do 204 item 1).
9. **`bytes_copia`** depois de adicionar um lote de cerca de 24 MiB: soma exata dos sub-lotes, ±64 KiB.
10. **Contadores** `nao_partidos` e `pecas_maiores_que_c` certos nos casos do item 3, com guarda até o T30b.
11. **Memória** (só Linux; pula nos outros): zerar o pico com `/proc/self/clear_refs` e conferir que `adicionar_lote` de cerca de 64 MiB sobe o `VmHWM` em no máximo lote + C + 16 MiB.

Os itens do T30b (troca por posição, quadros por troca, captura no quadro de S, troca repetida, apagar em ≤ 2 quadros) continuam no T30d do lote 62 §6.4, que fica para depois do T30b.

### Ponto 5 (conferência bit a bit): sim, pedir o acessor, em cartão próprio
Imagem igual não prova bytes iguais (normais, cor e triângulos degenerados podem não mudar pixel). Para o T30a2 (renumeração de índices) e o T30b (reenvio por posição) vale ter conferência direta. **Cartão novo T30a3** (classe T3, porque é ponte entre C++ e Python; até cerca de 30 linhas; só `ponte_viewport.cpp`): `Cena.dados_lote(seq)` devolve cópias numpy, só de leitura, dos vértices e índices do lote, usando o `lote(seq)` que já existe. Implementa um sonnet, revisa o Opus no lote do T30b. Entra antes do T30d2, que o usa com guarda.

### Ponto 7 (ensaio do pesado): a regra atual basta; não mudar o T29 agora, com uma conferência decidida de antemão
- **A queda é real, não é erro de medida:** o filho manda a base por `VmRSS` (`processo_malhas.py:247`) e o pai lê `VmRSS` do mesmo processo. Não há troca de pico por memória atual.
- **Atrasa a detecção?** Contando a partir do ponto mais baixo, sim: o vigia só pede quando a memória volta a `base + 1000 MB`. Em valor absoluto, não: o gatilho fica no mesmo nível que teria sem a queda, e o que o teto de 6.000 MB protege é o valor absoluto (conta A). A base é refeita a cada bloco (`carregador.py:632-641`), então a diferença não passa para o bloco seguinte.
- **Mínimo entre a base e a leitura: não recomendo.** A regra ficaria mais sensível, reagindo a um crescimento que não ameaça o teto, e só há **1 reinício** permitido. No 1º filho, isso pode gastar o reinício cedo, antes do bloco 22, que é onde ele é preciso. No 2º filho, os 4 blocos com queda, o reinício já foi gasto: o pedido viraria só "pedido e não feito". Mudaria o produto que acabou de acertar o bloco 22, sem ganho no teto absoluto.
- **Conferência (o líder roda por `jq` no JSON que já existe, outro agente; eu não leio):** para os blocos 24, 25, 32 e 40:
  - (a) `max_mb − primeira_mb` (crescimento a partir do ponto baixo);
  - (b) `max_mb − base_mb`;
  - (c) `atraso_armar_s`;
  - (d) `base_mb` contra o `fim_mb` do bloco anterior do mesmo filho.
- **Decisão escrita antes de ver os números:**
  - **Segue com a regra atual** se, nos 4 blocos, (a) < 1.000 MB, (b) ≤ 500 MB (o mesmo `crescimento_ok`), (c) ≤ 0,5 s e |base − fim anterior| ≤ 50 MB (a base é a memória real do começo do bloco). Ainda faltam 2 aberturas. O `primeira_vs_base_ok` continua calculado, gravado e **falso** onde falhar (não se reinterpreta o ±50 MB). Uma falha **para baixo** só não para o ensaio se, naquele bloco, as 4 condições acima passarem. Falha para cima, ou para baixo sem as 4 condições, para o ensaio. É uma regra de parada nova, decidida pelo Opus, registrada no LOG; nenhum número muda.
  - **Para e abre cartão T3 novo do T29** (autor do oráculo diferente, revisão Opus) se qualquer uma falhar. (a) ≥ 1.000 MB quer dizer que um crescimento perigoso passou sem gatilho. (d) acima de 50 MB quer dizer que a base mede memória que não é do começo do bloco. O cartão acerta o ponto da medida da base, não o mínimo.
- **Atenção à parte:** a folga da conta A é de 79 MB (5.921 de 6.000). É esse o risco da medida oficial na placa, não esta queda.

## 4. Perguntas ao PO
Nenhuma. Nada aqui muda meta, escopo, licença ou regra do processo. A regra de parada do ponto 7 é do ensaio (critério do Opus), não da meta. Os 6.000 MB, os 60 s e os 200 ms ficam iguais.

## 5. Resumo para o PO (5 linhas, sem siglas)
1. O conserto da cópia da troca de parede está aprovado: a memória extra caiu de 789 mil bytes para o tamanho exato da parede nova.
2. O teste que confere esse conserto também está aprovado; ele entra depois do conserto, com a marca de "ainda não" retirada por quem o escreveu.
3. A divisão do desenho em pedaços de até 8 megas voltou para ajuste: uma leitura de memória insegura e uma contagem que misturava dois casos diferentes.
4. Na cena de teste, os pedaços que "não partiam" eram uma peça enorme de enchimento; a parede trocada fica num pedaço pequeno, que é o que importa.
5. No arquivo pesado, a queda de memória não põe o limite em risco; a regra atual fica, desde que uma conferência rápida dos números confirme.

## 6. Linha do LOG
`2026-10-20 | F0-S04-T30a1, T30a2, T30d1, T33b | LOTE_OPUS_63 (opus, médio) | 200 APROVADO (73a16a2; bytes_copia +2.757 exato contra +788.869 no main), 199 APROVADO (6a0a20f + commit do autor do oráculo tirando só as linhas 20 e 147 e o trecho da linha 4), 204 REPROVADO (leitura de índices desalinhados por reinterpret_cast em cena.cpp:70, 71, 86 e 112; nao_partido mistura peça maior que C com lote sem fronteira, cena.cpp:119, e fica velho no sem, :42; só entra com o T30d2); merge 200 → 199 → (204 corrigido, T30a3, T30d2); reescopo do T30a1 aceito, com ger_ e instantâneo no T30b (que ganha cena.h e cena.cpp nesses dois itens e uma linha da ponte); T27 ladrilha: os 8 "não partidos" são o enchimento maior que C; medir nos dados reais o sub-lote de cada parede; T30a3 novo (acessor dados_lote, T3); T30d2 com 11 exigências; parada do critério 5 do T30a2 ignorada pelo líder registrada; T33b: regra atual basta (sem mínimo), conferência por jq dos blocos 24, 25, 32 e 40 decidida antes, primeira_vs_base_ok segue falso e gravado, regra de parada nova do Opus para a falha para baixo | docs/state/lotes/LOTE_OPUS_63/resultado.md`
