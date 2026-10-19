<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_62: resultado: revisão final curta do T29 e decisão T-1, T-2 ou T-3 do T32
Revisor: Opus (2026-10-19), classe T3, esforço médio. O Opus não escreveu nenhum dos três PRs nem o T32a. Contexto: lotes 58 (§3.3, §3.9), 59 (§1 e §3), 60 e 61; relatório `F0-S04-T32a.md` e cartão T32 (PR 193); código de `origin/s04-g0b-descartavel` (b437b40b), lido só para os números.

## 0. Vereditos
| PR | ponta revisada | veredito |
|---|---|---|
| **185** (oráculo T29b) | 908a49f | **REPROVADO** (achado 1.1, uma linha) |
| **188** (reinício T29a) | 117c412 | **APROVADO** pelo critério mecânico do lote 61 §4. Depois da correção do 185, o merge da nova ponta volta a ser conferido pelo mesmo critério (§2) |
| **189** (regra T29c) | c77bfe5 (produto de 40dfadb) | **APROVADO o produto de 40dfadb**. O ramo recebe a nova ponta do 185 por merge e é conferido pelo critério mecânico do §3.3 |

Nada foi aprovado provisoriamente. Este é o **3º parecer reprovado do 185** (lotes 60, 61 e 62). A regra do `CLAUDE.md` ("revisão reprovada 2 vezes → reescrever o cartão") se aplica. O cartão do T29b ganha o texto exato do §1.2, e o líder registra o escalonamento no LOG.

## Evidências (rodadas pelo revisor num worktree temporário no rascunho, já removido; nada do repositório foi editado além deste arquivo)
- 189 (c77bfe5), oráculo sem `--runxfail`: **16 passam** (88 s). Testes existentes `test_s04_abertura.py` e `test_viewport_carregador.py`: 39 passam, 2 pulados.
- **Mutação "vigia sem teto de 1"** (`_decidir` reinicia mesmo com `reinicios` cheio): `segundo_reinicio...` **falha 2 de 2** com "filhos de conversão: 3". O teste novo pega o teto.
- **Mutação "vigia sem a frase"** (teto mantido, `est["msgs"].append("reinício pedido e não feito ...")` trocado por `pass`): `segundo_reinicio...` **passa**. Ver 1.1.
- Linha restaurada `assert any("reinício pedido e não feito" in m for m in r.mensagens)`, junto da proibição nova, com o código do 189: **passa 2 de 2**. A mensagem vem do vigia: "reinício pedido e não feito (bloco 4): já houve 1 reinício". `registro_reinicio`: fonte `vigia`, bloco 2, `atraso_armar_s` cerca de 0,0001 s, `decisao_tarde` falso, `max_silencio_s` cerca de 0,15 s. `pico_filhos_mb`: dois valores lidos (cerca de 1.171 MB cada).
- 3f66f85 é ancestral de 188 e 189 (mesmo SHA). `git diff 3f66f85 origin/s04-t29a-reinicio -- prototypes/` vazio. `git diff 7537247 117c412`: só o arquivo do oráculo, com 4 inserções e 3 deleções, iguais às de 908a49f. `git diff origin/s04-t29b-oraculo origin/s04-t29a-reinicio -- tests/`: só 7 linhas `@AINDA_NAO` apagadas.
- `git diff 40dfadb origin/s04-t29c-regra`: só o oráculo (as mesmas 4 inserções e 3 deleções). `git diff origin/s04-t29b-oraculo origin/s04-t29c-regra -- tests/`: só 12 `@AINDA_NAO` e a constante `AINDA_NAO` apagados. `git log origin/main..origin/s04-t29c-regra --no-merges -- tests/` lista só commits T29b (1b0951b, c95b123, 7537247, 70ca17b, 908a49f). Escopo contra o `main`: `carregador.py`, `processo_malhas.py` e o oráculo.
- CI das três pontas: tudo verde já na 1ª tentativa (`linux`, `windows`, `appimage`, `instalador-windows` e os demais). A regra do `main` (`rules/branches/main`) exige `linux`, `windows`, `appimage` e `instalador-windows`, **sem** exigir ramo atualizado. Nenhum dos PRs 185, 188, 189 e 193 tem merge automático armado.
- Houve uma repetição (`run_attempt` 2) no run 39239969257 do 188 (ponta antiga 7537247, cancelado depois). Não há linha própria dela no LOG (ver §4).

## 1. PR 185: oráculo (REPROVADO)
O que foi pedido no lote 61 §1.1 está feito: há uma peça lenta em `3*BLOCO-1`, a frase "visto só no fim do bloco" está proibida, e o teste agora pega a falta do teto (mutação acima). O arquivo tem 398 linhas. Fora deste teste, nada mudou desde c95b123, e nenhum outro teste passa sem testar o que diz (conferido no lote 61 por mutação e não tocado desde então).

1.1 **(bloqueia)** `tests/test_s04_t29b_reinicio_oraculo.py`, `test_segundo_reinicio_pedido_com_teto_padrao_e_registrado_e_nao_feito` (linha 328 do 185):
- O lote 61 mandou **acrescentar** a proibição. O commit **trocou** por ela a linha `assert any("reinício pedido e não feito" in m for m in r.mensagens), r.mensagens`.
- Com isso, a metade "registrado" do teste (lote 59 §2.4, "segundo reinício registrado") deixou de ser conferida em todo o arquivo. A mutação que tira a frase do vigia passa.
- Tirar uma conferência de um caso especificado é afrouxar o oráculo, e isso não é aceito.
- A frase também é o que a sonda do ensaio vai contar (lote 61 §6 item 2).

1.2 **Correção (texto exato para o cartão do T29b; autor do oráculo, commit próprio no 185):** acrescentar, logo **depois** da linha 328, a linha que saiu, sem mudar nada:
```
    assert any("reinício pedido e não feito" in m for m in r.mensagens), r.mensagens
```
O arquivo fica com 399 linhas (teto 400). Não acrescentar mais nada.

**Critério mecânico (não volta ao Opus).** O líder confere três coisas:
1. `git diff 908a49f <nova ponta> -- tests/` mostra exatamente essa linha acrescentada e nada mais.
2. O commit só toca esse arquivo.
3. O oráculo do 189, depois do merge, dá 16 passam sem `--runxfail`.

Qualquer diferença disso volta ao Opus.

## 2. PR 188: caminho do reinício (APROVADO, critério mecânico)
O critério do lote 61 §4 item 4 foi cumprido em 117c412: 3f66f85 com o mesmo SHA, `prototypes/` igual, e o merge trouxe só as 4 inserções e 3 deleções do oráculo. Depois que a nova ponta do 185 for mesclada no 188 (commit de merge), o líder repete as três conferências e registra no LOG:
- `git merge-base --is-ancestor 3f66f85 origin/s04-t29a-reinicio`;
- `git diff 3f66f85 origin/s04-t29a-reinicio -- prototypes/` vazio;
- `git diff <nova ponta do 185> origin/s04-t29a-reinicio -- tests/` mostra só as 7 linhas `@AINDA_NAO` apagadas.

## 3. PR 189: regra R-A (APROVADO o produto de 40dfadb)
### 3.1 Os três pontos do lote 61, conferidos no código
1. **Frase.** O ramo `bloco_fim` de `_tratar` grava `fim_mb` e `tarde = True`. A mensagem é sempre "crescimento de X MB visto só no fim do bloco k: reinício não feito (tarde)", com "; já houve 1 reinício" no fim quando for o caso, e **nunca** "reinício pedido e não feito". Essa frase só aparece em `_decidir` (vigia, com o teto cheio). O `bloco_fim` desarma (`_base_mb = None`) e **não grava `_pedido` nem `_decisao` em nenhum caminho**. Os únicos lugares que gravam `_pedido` continuam sendo `_decidir` e `_gancho_reinicio`.
2. **Campos.**
   - `max_silencio_s` por bloco: o intervalo é medido antes de tratar a mensagem, e `ultimo` é refeito depois de `_colocar`, então o tempo do pai na fila cheia não entra.
   - `max_silencio_s` por reinício: o maior silêncio do filho inteiro, ou o silêncio em curso na hora da decisão (`t_decisao − ultimo`).
   - `primeira_mb`: a 1ª leitura do vigia depois de armar. O `_vigiar` só lê com o vigia armado, então o campo fica `None` em bloco não armado, como deve.
   - `decisao_tarde`: o canal é esvaziado só depois de o `exitcode` existir, sem aplicar nada. Erro de leitura do filho morto é ignorado. Fica verdadeiro se havia um `bloco_fim` entre as mensagens descartadas.
3. **`pico_filhos_mb`.** Cada filho nasce com `None`, e `_pico` trata o `None`. Nenhum outro uso de `est["picos"]` supõe número (só passa ao resumo).

Marcadores: 70ca17b e o 7537247 mesclado só apagam linhas. Nenhum teste existente foi editado. 40dfadb só toca `carregador.py`, com 31 linhas a mais e 15 a menos.

### 3.2 Sugestões (não bloqueiam; não pedir agora, para não abrir outro ciclo T3)
3.2.1 `carregador.py`, linha 553: o `return` de `_reiniciar` tem mais de 200 colunas; quebrar quando o arquivo for tocado de novo.
3.2.2 O silêncio que antecede a mensagem `bloco` k entra no `max_silencio_s` do bloco k, e não no do k−1. Isso é aceitável, mas a sonda do ensaio deve dizer que essa é a regra.

### 3.3 Critério mecânico depois do merge da nova ponta do 185 no 189
- `git diff 40dfadb origin/s04-t29c-regra -- prototypes/` vazio.
- `git diff <nova ponta do 185> origin/s04-t29c-regra -- tests/` mostra só os 12 `@AINDA_NAO` e a constante `AINDA_NAO` apagados.
- O oráculo dá 16 passam sem `--runxfail`, com `linux` e `windows` verdes.

## 4. Ordem e CI
Plano confirmado, com quatro acréscimos:
1. **Sequência.** Primeiro a correção 1.2 no 185. Depois o merge da nova ponta no 188 e no 189, com as conferências dos §2 e §3.3. Em seguida, o merge no `main` com commit de merge (sem achatar), na ordem **185, 188, 189**.
2. **CI depois de cada merge.** Cada PR só entra com `linux`, `windows`, `appimage` e `instalador-windows` verdes **na ponta que vai entrar**. A regra do `main` não obriga o ramo a estar atualizado, então os verdes de hoje (contra o `main` 9dc9bb7) não bastam depois que o anterior entrar. Mesclar o `main` no ramo seguinte (commit de merge; as conferências dos §2 e §3.3 continuam valendo, porque o `main` traz o 185 e documentos) e esperar o CI novo.
3. **Merge automático.** Não armar merge automático nos PRs 188 e 189 antes de o anterior entrar: a regra do `main` não impede que o 189 entre antes do 188.
4. **Repetições de CI.** As condições do lote 61 §5 continuam valendo. A repetição já feita no 188 (run 39239969257, tentativa 2) ganha uma linha no LOG agora, e conta nas 5 tentativas.

Não falta mais nada para mesclar. Antes do ensaio, continua valendo o lote 61 §6 (sonda em cartão T1 ou T2 à parte).

## 5. T32: decisão T-1, T-2 ou T-3
### 5.1 A conta
A meta é de 200 ms (p95) do comando ao quadro com a parede nova, para a parede criada **e** para a do arquivo (A30). O detalhado tem um lote de 285,36 MiB (T25 §10.1). Na placa, um quadro dura cerca de 16,8 ms (T25 §10.2) e a parte do comando cerca de 25 ms (lote 58 §3.3).

| | T-1 (2-G sobre a cópia refeita, `sem` consertado) | **T-2 (teto de lote C = 8 MiB dentro de `cena`)** | T-3 (2-G com compactação adiada) |
|---|---|---|---|
| O que muda | base comum do lote 59 §3.3 (a) a (e) + faixas visíveis e salto no `drawIndexed` + `sem` consertado | base comum + `preparar` parte o lote em sub-lotes de até 8 MiB na fronteira de peça + `sem` consertado. Sem salto no desenho | tudo da T-1 + `atualizar` só marca as peças escondidas; o `sem` roda depois, numa thread da cena; seleção, caixa, `totais`, `lote(seq)` e perda de contexto respeitam as escondidas |
| `atualizar` no pior lote | **234,8 ms** mediana, 243,7 pior (285 MiB, medido) | o sub-lote tem no máximo cerca de 8 MiB: **4,61 ms** mediana, 6,41 pior (lote de 8,97 MiB, medido) | perto de zero (só marcar); o `sem` de 235 ms sai do caminho, mas continua rodando em segundo plano |
| Estimativa do total, placa | 285 MiB: cerca de 235 + 2 quadros (34) + 25 = **cerca de 295 ms: não fecha**. 68 MiB: 52 a 81 + 59 = 111 a 140 ms (fecha). 24 MiB: cerca de 80 ms | quadros = teto((8 MiB + lote novo) ÷ 2 MiB) + 1 = cerca de 6, isto é, cerca de 100 ms + 25 + 5 = **cerca de 130 ms** em qualquer lote (lote 58 §3.3: 125 ms). Folga de cerca de 70 ms | cerca de 2 quadros + 25 = **cerca de 60 ms**, se o salto funcionar |
| Fecha os 200 ms? | **Não**, com os números de hoje, no lote de 285 MiB | **Sim** (estimativa a partir de um número medido e do modelo de quadros já validado: 404 = teto + 1 em 45 de 45 trocas) | Sim (estimativa), dependendo do salto |
| Classe | T3 | T3 | T3 |
| Risco para a trava `Motor::m_` → `DadosCena::m_` → `mc_` | médio: estado por posição e faixas no motor, lidos pelo laço de desenho | **baixo**: a divisão é feita em `preparar`, fora do mutex; os sub-lotes entram sob um único `DadosCena::m_`, com um único `++ver_`. Nenhuma trava nova; o motor só lê o instantâneo sem segurar `Motor::m_` (base comum) | **alto**: thread nova que toma `DadosCena::m_` e nunca pode chamar o motor (senão a ordem se inverte). A troca do lote compactado sobe `ver_` e faz o laço otimista de um `atualizar` concorrente refazer o `sem` (235 ms a cada volta). Parada da thread em `limpar()` e no destrutor |
| O que ainda não está medido | o salto no OpenGL em software e no D3D11 (T32b critério 5); a decomposição dos 234,8 ms; o `atualizar` sem o desenho em software disputando a CPU; +285 MiB de memória durante o reenvio | o número de lotes (cerca de 101 ou mais no detalhado) e de chamadas de desenho e de `create()` por quadro em software, WARP e placa; o efeito no M5; o custo de `rem.count(guid)` com dezenas de milhares de peças; a parte de lotes que pode ser partida (peças que compartilham vértices) | tudo o que falta à T-1, mais a corrida entre a compactação e uma troca nova no mesmo lote, e a seleção e a caixa com peças escondidas |
| Teste barato que fecha | cronometrar o `sem` consertado no lote de 285 MiB **sem desenho** (só `Cena`, sem janela; ramo descartável, cerca de 20 linhas na sonda). Se ainda passar de cerca de 140 ms, a T-1 morre em qualquer máquina; se cair, ainda falta o salto | contadores do T30d na tela virtual (quadros por troca ≤ teto(C ÷ 2 MiB) + 3 nos 5 lotes) e, antes disso, a parte de lotes que pode ser partida, contada no próprio T30a1 (§6.1) | nenhum barato: pede o salto e a thread prontos |

### 5.2 Decisão (recomendação para o líder seguir; o PO deixou a escolha com ele)
**T-2, com C = 8 MiB** (bytes de vértices e índices por sub-lote), dentro de `cena` no C++ (A29), com o orçamento de 2 MiB e 4 ms intocado (A31).

- **Por que T-2.** É a única das três em que o tempo de `atualizar` fica limitado por construção, com um número medido (4,6 a 6,4 ms), e não depende do salto no desenho, que nunca foi testado.
- **Por que não T-1.** Ela não fecha no lote de 285 MiB com os números do T32a, e o salto continua sem teste.
- **Por que não T-3.** Ela herda todos os riscos da T-1 e soma uma thread nova.
- **Se o T30d ou a placa mostrarem que C = 8 MiB não cabe:** os dados se reavaliam antes de mudar C. C = 4 MiB é a alternativa: menos quadros e o dobro de lotes. C = 16 MiB não vale (lote 58: 192 ms, sem folga).
- **Número já gravado para o líder conferir por `jq`** (outro agente; eu não leio `~/openbim-medicao`): nos JSON do T32a, casos `troca_8MiB`, campos `atualizar_ms`, `t_create_ms_max` e `quadro_max_ped`. É o custo de `atualizar` e de `create()` de um lote do tamanho de C.
- **Condições que vêm com a T-2** (entram nos cartões):
  1. **Honestidade da sequência.** O sub-lote refeito mantém a sequência antiga, e o lote novo leva a S. A sequência da placa só pode chegar a S no quadro em que o lote novo **e** todos os sub-lotes refeitos da mesma troca estão completos na placa. Até lá, o lote novo não é desenhado e o antigo continua. Nenhum quadro mostra as duas paredes nem nenhuma.
  2. **Mutex.** A divisão é feita dentro de `preparar` (a cópia que já existe), lendo direto da entrada, sem montar antes o lote grande. Assim o pico de memória do pai na abertura não sobe, o que importa porque a folga da conta A no pesado é de cerca de 106 MB. Os sub-lotes entram sob um único `DadosCena::m_`, com sequências seguidas e um único `++ver_`. `adicionar_lote` devolve a sequência do último sub-lote.
  3. **Onde partir.** Só na fronteira de peça e só onde a faixa de vértices fecha: nenhum índice do sub-lote aponta para fora dos vértices dele. Lote que não pode ser partido fica inteiro e é contado num campo novo de `totais()`. Peça maior que C fica sozinha num sub-lote.
  4. **`objetos(seq)`.** Devolve a tabela do sub-lote dessa sequência (faixas válidas no buffer dele). Isso é contrato da ponte: `tests/test_s04_cena.py` (oráculo) tem de passar **sem edição**; se algum caso dele usar lote maior que C ou supor um lote por chamada, parar e levar ao Opus. As sondas que leem `objetos(seq)` (`sonda_t25.py`) se adaptam em cartão próprio (T30c).
  5. **`sem` consertado.** Reserva exata, trechos contínuos, `morto` só no lote tocado. Sobe junto, para `bytes_copia` não crescer (lote 59 §3.2).
  6. **Fatia de 28 bytes** (sugestão): o motor pode alinhar o pedaço de vértices para baixo, em múltiplo de 28, sem mudar `ORCAMENTO_BYTES`. Hoje um quadro passa 20 bytes do orçamento (2.097.172 contra 2.097.152). O oráculo confere bytes por quadro ≤ `ORCAMENTO_BYTES`.

### 5.3 T32b: dispensável como protótipo; o T30 pode começar
- O T32b foi escrito como protótipo da T-1. Com a T-1 descartada, **cancelar o T32b** (registrar no LOG; o cartão T32 fecha com o T32a).
- O que a T-2 ainda precisa medir não se mede melhor num protótipo descartável do que no próprio T30, com oráculo:
  - quadros por troca e bytes por troca: contadores, válidos na tela virtual;
  - cobertura da divisão: contador;
  - chamadas de desenho e efeito no M5: só a placa vale.
- Proxy só de sonda, se o líder quiser um dado antes do T30a: dividir a cena do T27 em lotes de até 8 MiB **pelo Python** e medir chamadas de desenho, tempo relativo de quadro e `atualizar` numa cena com muitas peças (as 41.600 paredes sintéticas). É opcional e não bloqueia. Se for feito, entra como T2 com revisão sonnet (é só sonda, sem C++). Isso é rebaixar a classe, e o líder registra no LOG.

### 5.4 Divisão do T30 (cada cartão ≤ 400 linhas; classe T3; revisão Opus em lote)
| cartão | o quê | linhas (estimativa) | depende de |
|---|---|---|---|
| **T30a1** (cena) | `sem` consertado; `atualizar` não sobe `ger_` quando só troca lotes (`limpar()` continua subindo); instantâneo (ponteiros, `ger_`, `ver_` tirados juntos sob `DadosCena::m_`) | 100 a 160 | T32a |
| **T30a2** (cena) | divisão em `preparar` (§5.2 condições 2 a 4); contador de lotes não partidos em `totais()` | 120 a 200 | T30a1 |
| **T30b** (motor) | reenvio por posição (compara o instantâneo com o que está na placa); fila de trocados atrás dos lotes novos; entrada atômica (condição 1); perda de contexto e `limpar()` reenviam tudo, como hoje; fatia de 28 bytes (opcional) | 200 a 300 | T30a1 (pode correr junto do T30a2) |
| **T30c** (sondas, T2) | `sonda_t25.py` e a sessão da placa (A33) adaptadas a sub-lotes; nenhum limite muda | 80 a 150 | T30a2 |
| **T30d** (oráculo; escrito por um Opus que não seja o revisor) | §6.4 | 300 a 400 | em paralelo (arquivo próprio) |
Some o antigo T30c (salto no desenho).

## 6. Cartões prontos para colar (o líder grava)
### 6.1 F0-S04-T30a1 e T30a2 (cena)
- **Status:** PRONTO depois do T29 no `main` · Classe T3 · Implementa: sonnet · Oráculo: T30d (outro agente) · Revisa: Opus em lote (T30a1, T30a2, T30b e T30d juntos).
- **Critérios T30a1:**
  1. `sem` consertado com o mesmo resultado do `sem` de hoje (mesmos bytes de vértices e índices, mesma tabela, mesma caixa);
  2. `bytes_copia` sobe só o tamanho dos lotes novos;
  3. troca não sobe `ger_`; `limpar()` sobe;
  4. instantâneo coerente (ponteiros, geração e versão do mesmo instante);
  5. `test_s04_cena.py` e os demais testes existentes passam sem edição.
- **Critérios T30a2:**
  1. todo sub-lote ≤ C = 8 MiB, salvo peça maior que C (sozinha) e lote não partível (contado);
  2. a forma canônica (forma do oráculo T29b, por id) da união dos sub-lotes é igual à do lote original, em bits;
  3. `adicionar_lote` devolve a sequência do último sub-lote; um único `++ver_`;
  4. a divisão é feita na cópia de `preparar`, sem montar antes o lote grande; o pico de memória ao adicionar um lote de 285 MiB não passa de 285 MiB + C;
  5. o primeiro passo do implementador é contar a parte de lotes partíveis na cena do T27 e nas 41.600 paredes sintéticas; se for menor que 100%, parar e devolver o número (PRECISA_OPUS);
  6. `objetos(seq)` por sub-lote; `test_s04_cena.py` passa sem edição.
- **Arquivos permitidos:** `prototypes/s04/obimcore/nucleo/cena.h`, `prototypes/s04/obimcore/nucleo/cena.cpp`.
- **Proibido:** `motor.h` (é do T30b), `ponte_viewport.cpp` (salvo um campo novo em `totais`, se precisar), `fluxo_a.py`, `lote.py`, `medir_s04.py`, o juiz, `ORCAMENTO_BYTES`, `ORCAMENTO_TEMPO`, `OBIM_QUADRO_MS`, testes de oráculo.
- **Não medido aqui:** quadros, placa, M5, Windows, MSVC (a dobra dos vetores é outra, 1,5 vez).

### 6.2 F0-S04-T30b (motor)
- **Critérios:**
  1. troca reenvia só o lote novo e os sub-lotes trocados (bytes por troca = bytes deles, conferidos por contador);
  2. em todo quadro da troca, `triangulos_na_placa` ≥ triângulos da cena − triângulos da peça antiga;
  3. a sequência da placa chega a S só com o lote novo e os trocados completos, que entram no mesmo quadro;
  4. troca repetida no mesmo lote durante o reenvio: os critérios 1 a 3 continuam valendo;
  5. perda de contexto e `limpar()` no meio de uma troca reenviam tudo;
  6. bytes por quadro ≤ `ORCAMENTO_BYTES`, se a fatia de 28 bytes for consertada;
  7. nenhuma trava nova: o motor lê o instantâneo sem segurar `Motor::m_`, e `mc_` não é tocado (o revisor confere no diff).
- **Arquivos permitidos:** `prototypes/s04/obimcore/nucleo/motor.h` (e `motor.cpp`, se existir).
- **Proibido:** o mesmo do T30a.

### 6.3 F0-S04-T30c (sondas, T2)
- **O quê:** adaptar `sonda_t25.py` (e a sonda da sessão da placa, A33) a sub-lotes, sem mudar nenhum limite nem o juiz.
- **Grava, por troca:** quadros depois do comando, bytes, sub-lotes tocados, `atualizar_ms`, chamadas de desenho por quadro e número de lotes.

### 6.4 F0-S04-T30d (oráculo)
Lote 58 §3.9, itens 1 a 10, adaptados à T-2 (o item 4 vira "bytes por troca = lote novo + sub-lotes trocados"; as tabelas de escondidas saem), mais:
1. divisão: forma canônica igual, sub-lotes ≤ C, lote não partível contado e desenhado igual;
2. quadros por troca ≤ teto(C ÷ 2 MiB) + 3 nos lotes de 1 KB, 8,97, 24,24, 68,27 e 285,36 MiB (cena do T27, tela virtual, contadores);
3. `atualizar_ms` da troca no lote de 285 MiB ≤ 3 × o da troca no lote de 8,97 MiB, na mesma rodada (relativo; nenhum número de software vale como placa);
4. captura no quadro de S, sem a parede antiga e com a nova; captura depois da troca igual, pixel a pixel, à captura depois de `perder_contexto()` (mesma ordem de desenho por posição);
5. troca repetida no mesmo lote durante o reenvio;
6. apagar em ≤ 2 quadros quando o lote tocado for ≤ 2 MiB;
7. `bytes_copia` sem sobra.

**Não coberto (vai à placa, A33 e A34):** milissegundos e M2b p95, M5 com cerca de 101 lotes ou mais, D3D11, WARP, Windows, fluxo B.

## 7. PR 193 (relatório T32a): corrigir antes de mesclar
1. **(bloqueia, escopo)** `prototypes/s04/sondas/sonda_t32.py` e `rodar_t32.sh` estão no PR para o `main`, mas o cartão T32 só os permite no ramo descartável. No `main`, a sonda chama `Cena.registros()`, que não existe ali, e não roda. Recomendação: tirar os dois do PR 193. Eles continuam em `origin/s04-g0b-descartavel` (b437b40b, conferido), e o ramo não pode ser apagado. A alternativa é o líder emendar o cartão com uma linha no LOG e uma linha no cabeçalho da sonda dizendo "só roda no ramo descartável, b437b40b".
2. **(corrigir)** Critério 3: "7, 13, 19, 25 e 31 (mesmos números do T27)". O T27 tem **8** para o lote de 1 KB. Escrever "7 (o T27 viu 8, por leitura aproximada por quadro), 13, 19, 25, 31".
3. **(corrigir)** Critério 2: "Nas 7 de 403 quadros" deve virar "Nas 7 trocas de 403 quadros". Acrescentar que com o `sem` consertado não houve nenhuma troca de 403.
4. **(corrigir)** Critério 5: dizer que `atualizar` rodou com a thread de desenho em software (llvmpipe) desenhando 8,8 milhões de triângulos nos mesmos núcleos. O tempo inclui essa disputa e não é número de placa nem de CPU livre. Registrar também a dispersão do lote de 68 MiB consertado (52,1 de mediana contra 81,5 de pior).
5. **(sugestão)** Critério 6: em vez de "fica confirmada", escrever "o contador mostra que o corte de 4 ms só acontece em quadro com `create()` (todos os 94 a 102; nenhum sem); a causa ser o `create()` é a leitura mais provável".
6. **(sugestão)** No mesmo PR (arquivos permitidos), atualizar o cartão T32: T32a feito, T32b cancelado por este lote, próximo passo T30a1. Atualizar também BOARD e LOG.
- O hash confere: `git diff 523e58c b437b40b` muda só `sonda_t32.py` (11 linhas), e a sonda do PR é igual à de b437b40b. A conferência dos números por `jq` fica com o líder.

## 8. Perguntas ao PO
Nenhuma. A escolha da opção foi deixada ao líder. O teto dentro de `cena` já foi aceito pelo PO (A29), e o orçamento continua intocado (A31). A sessão da placa já inclui a troca de parede (A33).

## 9. Resumo para o PO (5 linhas, sem siglas)
1. A parte que reinicia o processo de conversão e a regra que decide o reinício estão aprovadas.
2. O teste corrigido passou a conferir o limite de um reinício, mas uma conferência que já existia foi apagada sem querer; peço que volte (uma linha).
3. Depois disso, os três pedidos entram um de cada vez, cada um com a verificação automática verde.
4. Na troca de parede, consertar a cópia não basta para o pedaço maior do arquivo (235 milésimos de segundo, acima da meta de 200).
5. A saída escolhida é guardar o desenho em pedaços de até 8 megas: cada troca fica em cerca de 130 milésimos de segundo, sem truques no desenho.

## 10. Linha do LOG
`2026-10-19 | F0-S04-T29, T32 | LOTE_OPUS_62 (opus, médio) | 185 REPROVADO (3ª vez: o commit trocou o assert "reinício pedido e não feito" pela proibição em vez de acrescentar; repor a linha, 399 linhas, critério mecânico; cartão T29b reescrito com o texto exato; escalonamento registrado), 188 APROVADO (critério mecânico; repetir depois do novo merge), 189 APROVADO (produto 40dfadb; critério mecânico depois do merge); merge 185→188→189 com CI verde na ponta que entra, sem merge automático, repetição do run 39239969257 registrada; T32: T-2 com C = 8 MiB (atualizar de 285 MiB consertado 234,8 ms não fecha a T-1; T-3 herda o salto e soma uma thread), T32b cancelado, T30 = T30a1, T30a2, T30b, T30c (sondas), T30d (oráculo); PR 193: tirar as sondas do PR (escopo) e 3 correções de texto | docs/state/lotes/LOTE_OPUS_62/resultado.md`
