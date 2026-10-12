<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Lote Opus 8: oráculo complementar (T08-0b), correções (T08-E) e ordem de merge da pilha da T08
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-12 · Pedido: `docs/state/LOTE_OPUS_8.md`
- Revisado: `s03-t08-0b` `80ce5b2` (PR 39) e `s03-t08-e` `f3560a6` mais a mesclagem `acb3444` (PR 40; é o mesmo commit do rascunho, PR 37).
- Veredito curto: **os dois aprovados, sem item que bloqueie.** Recomendo entrar tudo de uma vez pelo PR 37 (§3).

| Item | Cartão | Veredito |
|---|---|---|
| 1 | T08-0b (oráculo P13 a P18) | **APROVADO** |
| 2 | T08-E (correções do lote 7) | **APROVADO**, com 8 observações que não bloqueiam (§2.3) |
| 3 | Ordem de merge | **Outra ordem recomendada:** um único merge, o do PR 37 (§3) |

## Resumo para o PO
1. **Os defeitos que achei no lote 7 estão corrigidos.** Refiz as mesmas sondas: a peça sem geometria não é mais acusada no lugar da peça lenta; peças lentas repetidas pelo prédio viram caixa de uma vez, sem esperar de novo; a caixa das paredes comuns sai no lugar e no tamanho certos (antes errava até 59,75 m; agora o erro é zero nas 21 paredes); e quando a janela 3D muda de lugar o modelo **volta sozinho**.
2. **O seu arquivo real continua igual:** abri mais uma vez, em tela virtual: 42,9 s, 14.804 peças com malha e 6 sem, nenhuma virou caixa, nenhum processo sobrou, memória somada de 6.796 MB. Bate com o que foi relatado.
3. **Os testes passam:** 107 passam e 6 pulam na minha máquina (os 6 são os de sempre). No GitHub, Linux e Windows estão verdes.
4. **Um custo novo, que só aparece quando alguma peça estoura o limite** (no seu arquivo, com o limite de 20 s, nenhuma estoura). Para acusar a peça certa, o programa agora converte uma peça por vez nesse trecho, e isso é mais lento: no seu arquivo, cerca de 30 segundos a mais para cada trecho de 1.000 peças onde houver peça lenta. É o preço da correção; aceito no protótipo e deixo anotado para melhorar na S04.
5. **Uma consequência da regra "mesma peça repetida" que vale você conhecer.** Forcei uma peça lenta no seu arquivo (uma peça do tipo "membro", repetida 285 vezes): as outras 284 cópias dela no prédio viraram caixa laranja junto, sem espera. É a regra que você aprovou, agora valendo no arquivo inteiro. Ela existe porque, numa lentidão de verdade, toda cópia é igualmente lenta: sem a regra seriam 284 esperas de 20 s (mais de uma hora e meia).
6. **O que não foi visto no Windows:** o teste da janela que muda de lugar precisa de tela e por isso é pulado no GitHub, nos dois sistemas. Aqui, em tela virtual no Linux, ele passa. Deixo um cartão pequeno para ligá-lo no passo de desenho do GitHub.
7. **Pergunta para você (§4):** recomendo que tudo entre no `main` em **um único merge** (o PR 37, que já está verde nos dois sistemas e tem exatamente o conteúdo que revisei), em vez de seis merges em fila.

## 0. Como este lote foi feito
- Lido: o pedido, `LOTE_OPUS_7.md` (§1.3, §1.4, §1.6, §4), os dois cartões, os dois diffs, e, na ponta, a parte de leitura e vigia dos filhos em `carregador.py`, a conversão e a caixa em `processo_malhas.py`, o `adaptador.py` e os trechos novos de `cubo_rhi.py` e dos dois arquivos de teste. Não reli as partes desses arquivos que não mudaram desde o lote 7.
- Execução: dois worktrees temporários no rascunho da sessão (`s03-t08-0b` e `s03-t08-e`), **já removidos** (conferido com `git worktree list`; os worktrees do líder não foram tocados; nenhum processo sobrando no sistema). Testes gráficos só em `xvfb-run` com desenho por software. Sondas no rascunho, fora do repositório. Nada instalado, nenhum commit, nenhum push, nenhum PR alterado.
- Arquivo real: aberto no lugar, só leitura, **quatro vezes**: uma medição oficial e três rodadas de sonda com uma peça lenta forçada por variável de ambiente (duas no código novo, uma no antigo). Nada copiado nem enviado.
- Rede: `git fetch` e leitura de PRs e do log do CI com `gh`.
- Máquina: 16 núcleos, 23 GB, Linux. **Nada foi medido por mim no Windows**; o que sei do Windows vem do CI do PR 37.

### Resultados das execuções
| Execução | Resultado |
|---|---|
| Suíte inteira na ponta (`acb3444`), tela virtual, com os lentos | **107 passam, 6 pulam** (4 por falta do modelo de 1 milhão, 1 da T06 pesada, 1 emenda do R2). P1 a P18 todos |
| Suíte na ponta sem tela (como o CI roda) | 95 passam, 18 pulam: igual ao `linux` do GitHub. Os 12 a mais são os que precisam de tela, **entre eles os dois P17** |
| Suíte no `s03-t08-0b` (`80ce5b2`), tela virtual | 89 passam, 9 pulam, **7 falhas esperadas**, nenhuma passagem inesperada |
| P13 a P18 no `80ce5b2`, com `--runxfail` e `OBIM_FORCAR_GUARDAS=1` | 9 falham, cada um na afirmação do seu defeito (§1.1); 1 passa (P16 "só caixa", que é regressão) |
| Arquivo real, `medir.py`, tela virtual | abrir 42,9 s; 14.804 / 6; 8.595.714 triângulos em 93 lotes; pico pai 1.051 MB + filho 5.745 MB = **6.796 MB**; 0 caixas; 0 filhos sobrando; atraso máximo 418 ms (desenho por software, não vale como meta) |
| CI do PR 37 (mesmo commit `acb3444`) | `linux` verde (95/18), `windows` verde (94/19), `appimage` verde; `macos` vermelho só por tempo (§2.2, macOS) |

## 1. Item 1: T08-0b (oráculo P13 a P18): APROVADO
Conteúdo aprovado: `tests/test_viewport_processo.py` `3868070047` e `tests/test_viewport_adaptador.py` `5caa1029b4` (no `80ce5b2`). Diff de 261 linhas, só nos dois arquivos permitidos.

### 1.1 Os casos cobrem o §4 item 5?
Sim. Rodei os casos no código antigo sem a marca de falha esperada, para ver se cada um falha pelo motivo certo (uma falha esperada "estrita" aceita qualquer erro, até erro do próprio teste):

| Caso | O que exige | Como falha no código antigo |
|---|---|---|
| P13 | 12 cópias do **mesmo** item mapeado, `tamanho_bloco=1`: concluído, 12 caixas, tempo de uma única espera | "precisou reiniciar mais de 20 vezes" (a sonda B do lote 7) |
| P14 | produto sem geometria com id menor fica em `sem_malha`; só a lenta vira caixa | `simplificadas: [69, 81]` (a sonda do §1.4 item 1) |
| P15 | caixa dentro de 1 cm: 4 paredes do modelo de paredes e aberturas, perfil retangular com posição própria, `Position` vazio | cubo de 0,5 m; no retângulo com posição própria, caixa deslocada cerca de 1 m |
| P16 | `deslocamento` não gravável em todo lote, com reinício e só caixa | "lote 0: deslocamento gravável" |
| P17 | troca de janela: sinal emitido, carga recomeça, mesmos 7.200 triângulos | "a cena voltou com 0 triângulos" e "não emitiu contexto_perdido" |
| P18 | filho da caixa falha na peça: ela vai para `sem_malha`, nenhum cubo na origem | `sem_malha: []` |

- **P13 usa a mesma conta do P5** (`dt12 <= dt1 + 0,5 x limite + 3 s`), como pedi. As 12 cópias são mesmo da mesma família (`_gerar_mapeadas`: um único item mapeado para todas as lentas).
- **Nenhum número foi afrouxado.** O diff só acrescenta; a única linha alterada é a de importação. P1 a P12 e os testes da T05 estão intactos.

### 1.2 As guardas são seguras?
Sim. As três só **ligam** testes; nenhuma desliga exigência.
- `requer_caixa_falha` procura o texto do gancho em `processo_malhas.py`; `requer_reabertura` procura o sinal no viewport. Sem o recurso, o caso pula; com o recurso, roda.
- `OBIM_FORCAR_GUARDAS=1` só força os casos a rodar mesmo sem o recurso. Ninguém ganha nada definindo a variável.
- A falha esperada é estrita: quando a T08-E entra, o caso passa, a marca vira erro e obriga a tirá-la. Foi o que aconteceu.

### 1.3 Observações (não bloqueiam)
1. **P17 não roda no GitHub.** Ele pula quando não há contexto gráfico, e o passo "Testes" do CI roda sem tela nos dois sistemas. A correção do §1.6 só é verificada por máquina com tela virtual. Cartão pequeno no §3.2.
2. **P15 testa 4 das 21 paredes** (pedi "as paredes"). Aceito pelo tempo do teste; cobri as 21 por sonda, de duas formas: direto na função da caixa (21 de 21 pelo caminho dos pontos, desvio 0) e de ponta a ponta com as 21 lentas (21 caixas, desvio 0, 27 s).
3. **P18 só exercita a falha de uma peça dentro do filho da caixa.** A queda do filho inteiro (o defeito original) não tem caso. Sondei: as três peças foram para `sem_malha` com motivo, estado "concluido", regra de ouro vale. No código antigo o P18 falha porque o gancho não existe, não porque veja o cubo na origem; isso é inevitável e está certo.
4. Depois que a T08-E estiver no `main`, as guardas `requer_caixa_falha` e `requer_reabertura` não protegem mais nada e só podem esconder um caso se alguém apagar o recurso. Tirar as duas no cartão do §3.2.
5. `_gerar_defeito` é importado e não é usado. Sem peso.

## 2. Item 2: T08-E (correções): APROVADO
Conteúdo aprovado (no `acb3444`): `carregador.py` `8cb8d89d4a`, `processo_malhas.py` `b70b131e01`, `cubo_rhi.py` `f4e4eb2008`, `adaptador.py` `856aecab50`, `medir.py` `95702b4629`, `tests/test_viewport_processo.py` `7c00eb3774`, `tests/test_viewport_adaptador.py` `3448e88868`. Diff de 156 linhas (114 a mais, 42 a menos). A mesclagem do `main` (`acb3444`) não trouxe nenhuma edição à mão (`git show --remerge-diff` vazio).

### 2.1 Cada correção resolve o que achei?
| Achado do lote 7 | Correção | Conferido por |
|---|---|---|
| §1.3 item 1: `deslocamento` gravável | cópia protegida em `_tratar`; o valor guardado para os reinícios é o protegido | P16 (os dois modelos) |
| §1.4 item 1: peça errada acusada | modo isolado com um iterador por peça; o filho avisa a peça em curso (`atual`) e o pai acusa essa | P14; sonda nova com **queda** em vez de lentidão: a sem geometria fica em `sem_malha` ("o conversor não achou geometria nesta peça"), a que caiu vira caixa |
| §1.4 item 2: família só no bloco; teto de 20 | irmãs procuradas no arquivo inteiro; o teto passou a contar só reinícios seguidos sem condenar peça | P13; sonda com 21 peças lentas **diferentes**: concluído, 21 caixas (antes: erro perto de 10) |
| §1.4 item 3: cubo na origem | peça sem caixa calculada vai para `sem_malha` com o motivo; falha de uma peça não derruba as outras | P18; sonda com o filho da caixa caindo inteiro |
| §1.4 item 4: sólido extrudado | aceita curva indexada só de trechos retos, posição própria do perfil e `Position` vazio; arco continua no cubo | P15 (3 modelos); sondas das 21 paredes: desvio de 59,75 m no código antigo, 0 no novo |
| §1.6 item 1: modelo some em silêncio | o viewport zera a caixa da cena e emite `contexto_perdido`; o adaptador reabre com o mesmo caminho e opções, fora do desenho. `liberar_apos_envio=True` continua padrão | P17; sonda trocando de janela **no meio** da carga: 1 sinal, a carga recomeça, 36.000 de 36.000 triângulos |
| macOS: `pico_memoria_mb(ident)` | `/proc` só no Linux; fora dele `ps`; `ru_maxrss` em bytes no macOS | CI do PR 37: o P11 passa no `macos` |
| Obs. 7 do §1.4 (se coubesse): um lote por peça | agrupamento por 0,2 s | sonda: 13 lotes onde havia 1.002; no arquivo real 609 onde havia 2.050 |

### 2.2 Os dois pontos do implementador e o macOS
- **(a) macOS, residente atual em vez do pico: aceito.** É mais brando do que parece: filho que termina normalmente informa o próprio pico na mensagem final (agora na unidade certa). O `ps` só vale para filho que foi morto (limite, queda ou cancelamento); aí o número do macOS fica subestimado. O macOS é experimental e não tem meta de memória.
- **(b) peças do agrupamento de 0,2 s perdidas quando a seguinte trava: aceito.** O pai só dá a peça por resolvida quando recebe o lote; o que se perde é refeito no reinício (no máximo 0,2 s de trabalho por reinício). Sonda com 3 peças lentas, duas vizinhas: nenhuma peça saiu duas vezes, 7.200 triângulos como na referência, numeração dos lotes em ordem.
- **`macos` continua vermelho no PR 37, mas só por tempo:** P3 (percentil 95 de 40 ms contra 33) e R1a (38,8 ms contra 33). É a oscilação já conhecida do executor; o P11 não falha mais. Não bloqueia.

### 2.3 Novos defeitos? Nenhum que bloqueie. Observações
1. **Custo do iterador por peça, medido no arquivo real** (o lote 7 pedia "medindo o custo"; a medição relatada de 41,6 s não entra no modo isolado, então não mede isso).
   - Sonda: uma peça com atraso forçado de 60 s e limite de 3 s. Com 3 s, três móveis do próprio arquivo também estouram de verdade, nas duas versões.
   - Código antigo: 91,5 s, 21 caixas, 2.050 lotes. Código novo: **149,9 s**, 288 caixas, 609 lotes. Nos dois: 14.804 / 6, regra de ouro, nenhum filho sobrando.
   - No modo isolado o novo gasta cerca de 30 a 55 ms por peça (o antigo, 2 a 18 ms): perto de **30 s a mais por trecho de 1.000 peças** onde houver peça lenta. No modelo de 3.000 paredes do teste a diferença é de 1 ms por peça.
   - **Aceito no protótipo:** só acontece quando alguma peça estoura o limite, e a alternativa era acusar a peça errada. Registrar para a S04: no modo isolado, usar blocos menores ou manter um iterador só e confirmar sozinha apenas a peça acusada (opção ii do lote 7).
2. **O teto não limita mais o número de peças lentas diferentes.** Antes, cerca de 10 e a abertura terminava em erro. Agora termina sempre, mas cada peça lenta diferente custa o limite mais três reaberturas do arquivo (no arquivo real, perto de 3 s cada) e o trecho refeito peça por peça. Com muitas peças lentas diferentes a abertura fica longa, embora cancelável e com progresso. **Aceito:** é o que pedi ("não punir cópias") e é melhor do que erro. Registrar para a S04: um orçamento total (tempo ou número de peças condenadas) com pergunta ao usuário.
3. **Ainda existe um caminho para caixa na origem:** em `_caixa_produto`, se a posição do objeto não puder ser lida, a conta segue com posição zero. Precisa de um arquivo com posição defeituosa **e** peça lenta. Correção de duas linhas: nesse caso falhar, e a peça vai para `sem_malha`. Cartão do §3.2.
4. **Modo isolado que falha com tudo já resolvido** (filho que cai depois da última peça): `min()` de lista vazia, e a carga termina em "erro" com tudo entregue. Vem da B2. Uma linha (`if not pend: continue`). Cartão do §3.2.
5. **Reabertura automática, para a S04:** a câmera volta ao enquadramento inicial (o usuário perde o ponto de vista); a ligação do sinal é por função anônima (se o adaptador for destruído antes do viewport, o sinal chama objeto morto); se a carga anterior não cancelar em 5 s, sai o erro "tente de novo" e o modelo fica fora da tela. Sondei fechar e destruir a janela depois da carga: nenhum sinal, nenhuma recarga, nenhum filho. Nada disso aparece no protótipo de uma janela só.
6. **Desvio de processo, aceito e a registrar no LOG:** o diff da T08-E mexe em `tests/` e em `medir.py`, fora dos "arquivos permitidos" do cartão. Conferi linha a linha: nos testes só saem as marcas de falha esperada (e um comentário que deixou de valer); em `medir.py`, uma linha do macOS (acréscimo 7 do cartão). Nenhuma afirmação mudou. Da próxima vez, quem tira as marcas é o agente do oráculo.
7. A cópia dos lotes em `_tratar` (obs. 3 do §1.3 do lote 7) ficou, porque o oráculo exige dados próprios. Certo.
8. `est["reinicios"]` ficou sem uso. Sem peso.

### 2.4 Conferência dos PRs 31 a 34
Os ramos receberam mesclagens do `main` desde o lote 7. Comparei o conteúdo revisado então (`0c1104b`, `5c4dff5`, `8637942`, `7e1624c`) com as pontas de hoje em `prototypes/`, nos testes do viewport e no relatório da T08: **nenhuma diferença**. O que eu revi é o que está lá.

## 3. Item 3: ordem de merge

### 3.1 Recomendação: um único merge, o do PR 37
A ordem 31, 32, 33, 34, 0b, E está certa como ordem, mas tem três custos:
- o CI só roda em PR que aponta para o `main` e **não roda quando um PR é só reapontado**. As verificações ficam presas ao commit: hoje só as pontas dos PRs 34 (`d0a6b34`) e 40 (`acb3444`) têm `linux` e `windows` verdes; os PRs 31, 32, 33 e 39 não têm nenhuma execução e precisariam de um envio novo cada um (o `windows` leva perto de 19 minutos por vez);
- entre um merge e outro o `main` ficaria com o código reprovado no lote 7 (31 e 32 sem a correção);
- são seis pedidos de ok ao PO, porque tudo é T3.

O PR 37 (ramo `rascunho-t08`) é o **mesmo commit** `acb3444` da ponta que revisei, já tem `linux`, `windows` e `appimage` verdes, e mescla sem conflito com o `main` de hoje (`ba8f42b`). Proponho:
1. O PO dá o ok (§4).
2. O líder tira o PR 37 de rascunho, troca o título, e faz o merge **com commit de mesclagem (sem "squash")**, para o histórico guardar um commit por cartão. O repositório permite esse tipo de merge (conferido com `gh`). **Atenção:** o merge automático está ligado no projeto; ao tirar do rascunho, garantir que ele **não** esteja armado no PR 37 antes do ok do PO (hoje não está).
   - Sobre a regra das 400 linhas: o PR 37 soma cerca de 1.070 linhas contra o `main`, mas é só o recipiente. Cada cartão ficou abaixo de 400 e foi revisto sozinho (31: 313 a mais; 32: 295; 33: 112; 34: 62; 0b: 261; E: 114).
3. O líder fecha os PRs 31, 32, 33, 34, 39 e 40 com a nota "entrou pelo PR 37".
4. **Condição:** o commit do PR 37 tem de continuar `acb3444`. Se algo for enviado ao ramo, ou se o GitHub pedir atualização com o `main` e isso mudar algum arquivo de `prototypes/` ou `tests/`, as impressões digitais do §1 e do §2 têm de bater; se não baterem, volta para o lote.

Se o PO preferir a fila de seis, a ordem é a do pedido (31, 32, 33, 34, 39, 40), um por vez, cada um reapontado para o `main`, com `linux` e `windows` verdes no próprio PR e sem parar no meio.

### 3.2 Cartões a abrir depois do merge
- **T08-G (T3 pequeno, menos de 30 linhas; entra no próximo lote Opus do módulo):** §2.3 itens 3 e 4; tirar as guardas `requer_caixa_falha` e `requer_reabertura` (§1.3 item 4) e o import sem uso. Os testes, por agente de oráculo.
- **CI do P17 (T1):** rodar `tests/test_viewport_adaptador.py` no passo de desenho que já existe (tela virtual no Linux; WARP no Windows), informativo como o do cubo. É o que falta para ver a reabertura no Windows.
- **T26b continua pendente** (lote 7, §3.1). Esbarrei nela: uma sonda minha gerou um modelo depois de criar a aplicação Qt, em pt_BR, e o arquivo saiu com vírgula decimal (600 peças sem geometria). O `conftest.py` dos testes força `LC_ALL=C`, por isso a suíte não vê.
- **Para a S04 (registrar no ADR-004 ou no cartão de integração):** §2.3 itens 1, 2 e 5.

## 4. Pergunta ao PO
**Você autoriza o merge do PR 37, de uma vez, com tudo o que falta da T08 (os conteúdos dos PRs 31, 32, 33, 34, 39 e 40)?**
- **Recomendo sim.** É exatamente o conteúdo que revisei e aprovei, já está verde no Linux e no Windows, e evita deixar o `main` por algumas horas com o código que reprovei no lote 7.
- Se preferir um por vez, também funciona: são seis autorizações e cerca de duas horas de espera dos testes.

## 5. Para o líder
1. Registrar no LOG: T08-0b e T08-E aprovadas no lote 8; o desvio do §2.3 item 6.
2. Abrir os cartões do §3.2.
3. Este arquivo foi escrito **sem commit**, na pasta principal, no ramo `estado-lote7` (árvore limpa antes).

## 6. Depois do relatório (2026-10-12)
- O PO respondeu **"sim"** à pergunta do §4, no chat.
- Feito na mesma sessão: PR 37 tirado de rascunho, título trocado, merge com commit de mesclagem travado no commit `acb3444` (merge `2681962`). As sete impressões digitais do §2 batem no `main`.
- PRs 31, 32, 33, 34, 39 e 40 fechados com a nota "entrou pelo PR 37". Nenhum PR aberto.
- O CI do `main` para o `2681962` estava rodando quando este trecho foi escrito: **o líder confere o resultado**.
- Falta ao líder: LOG, BOARD e os cartões do §3.2. Este arquivo continua sem commit.
