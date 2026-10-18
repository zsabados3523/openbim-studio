<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_57: resultado

**CONCLUÍDO** (planejamento, classe TA). Nada foi implementado, medido nem escolhido. Este texto **especifica** as opções; a escolha é do PO (cartão T20, fase 1, e cartão T22). Autor: Opus. Pela regra 6 do `CLAUDE.md`, a revisão da implementação e do oráculo que nascerem daqui deve ser feita por **outra sessão Opus**, não por quem escreveu este planejamento.

Li só o contexto fechado do pedido: `reports/F0-S04-T21.md`, `reports/F0-S04-T22.md`, `reports/F0-S04.md`, os cartões T20, T21 e T22, `v2/03` (S03 e S04), ADR-004, ADR-005 §10, `carregador.py`, `processo_malhas.py`, `fluxo_a/CONTRATO.md` e `nucleo/motor.h`. **Não li** `cena.h`/`cena.cpp`, `formato_malha.py`, as sondas, o cartão T12, o lote 9 §2.2, IFC do PO nem dados brutos. Tudo o que depende deles está marcado "não lido" e o tamanho dos cartões dessas partes é estimativa.

Convenções: "medido" = número de relatório; "pelo código" = leitura do código citado, sem medida; **estimativa** = conta feita aqui sobre números medidos, nunca medida; **teto** = o máximo que a aritmética permite, não uma previsão de ganho. Meta de memória: pico somado (pai + maior filho, conta A do T21) **< 6.000 MB**; abrir **≤ 60 s** (na placa real, que é o oficial); saída igual.

## 0. Resumo para o PO (5 linhas)
1. Memória do arquivo pesado: falta tirar mais de 0,9 GB (contando a pior das três aberturas oficiais). A maior parte está no processo que gera o 3D, e cerca de 1,4 GB dela parece ficar "presa" de partes anteriores quando chega a parte mais pesada.
2. Para a memória, recomendo começar o processo do 3D de novo, limpo, logo antes da parte mais pesada, sem mudar a ordem nem o resultado. Antes de mexer no programa, um teste de uns 20 minutos com o seu arquivo, em tela virtual, mostra se isso basta.
3. Trocar o comprimento de uma parede demora porque, pelo código, a tela joga fora o desenho inteiro e o reenvia aos poucos. No arquivo detalhado são cerca de 400 quadros, e a cena some e volta a cada troca.
4. Para isso, recomendo reenviar à placa de vídeo só o pedaço que mudou. Antes, um teste com modelos sintéticos, sem nenhum arquivo seu, confirma a causa.
5. Nenhuma opção mexe em meta, régua, limite ou teste. Mudar a forma de medir ou a meta continua sendo só decisão sua, e eu não recomendo isso.

## 1. Erros e contradições nos relatórios e cartões
1. **Cartão T20, "Causa conhecida".** O cartão diz que uma peça leva o processo filho a 3,9 GB. O T21 §6.3 diz que o nexo "o pico vem da peça mais pesada" é **hipótese**. O 3,9 GB do cartão é igual ao pico do filho com 1 fio (3.913 MB), que teve 2 peças simplificadas. O texto do cartão deve passar a "hipótese".
2. **Classe da fase 1.** O cartão T20 diz "Fase 1 (T1, opus planeja)"; o pedido e este lote são TA. Alinhar o cartão.
3. **T21 §5 pode não valer para o carregador.** São três sinais:
   - Com 8 fios e bloco 1.000, nenhum bloco calcula por mais de 16,3 s (§4). Mas as peças 2 e 3 levam 28,4 s cada "sozinhas". Se fossem convertidas como no passe, algum bloco duraria 28 s ou mais.
   - O passe tem 8.818.146 triângulos e 14.804 peças com malha. O carregador tem 8.595.714 triângulos e 6 peças sem malha em todas as aberturas (§1).
   - O próprio T21 diz que o passe usa "um iterador próprio".

   Hipótese: o passe usa configuração diferente da de `processo_malhas._converter`, que tem `use-world-coords`, `weld-vertices` falso, a biblioteca `hybrid-cgal-simple-opencascade` e exclui `IfcFeatureElementSubtraction` e `IfcSpace`. Até conferir isso, os 3,0 GB e os 28 s por peça **não se transferem** ao carregador. Teste de custo zero: comparar as configurações da sonda com as do `_converter` (é só ler o código).
4. **Mesma peça, dois tempos.** O ADR-004 §2 dá 11,5 s para a maior peça (lote 6) e o T21 §5 dá 15,1 s "sozinha". Os métodos são diferentes. Nenhum dos dois é o tempo dela dentro do carregador.
5. **"Por que o limite de 20 s só atuou com 1 fio" tem candidato no código** (pelo código, não medido). Em `carregador._executar` (linhas 395 a 414), `ultimo` volta a zero a **cada mensagem** do filho. O limite mede **silêncio do filho**, não o tempo de cada peça. Com 2 fios ou mais, as outras peças mandam `feitos` e o relógio volta a zero; com 1 fio, o silêncio é o tempo da própria peça. Isso vira restrição para as opções do item 1 (§2.6).
6. **T22, previsão da sintética de 41.600.** Ver 25 quadros contra 25,2 previstos é impossível se 50,4 MiB fossem mandados a no máximo 2 MiB por quadro: seriam pelo menos 26. A conta provável (estimativa):
   - O vértice tem 28 bytes (`motor.h`, linhas 191 a 193). Com 3 vértices por triângulo e 12 bytes de índices, dá cerca de 96 bytes por triângulo.
   - 502 mil triângulos dão cerca de 46,0 MiB. A cópia de 50,4 MiB deve incluir a tabela de objetos, cerca de 110 bytes por peça vezes 41.600 (estimativa), que não vai à placa.
   - Refeita, a previsão é cerca de 23 quadros contra 25 vistos. A sintética de 3.000 fica em 1,7 contra 3; o 25 MB em 22,9 contra 24; o detalhado em 402,9 contra 405.
   - Todos ficam de 1 a 2 quadros acima. A hipótese 1 continua de pé, mas a coluna "previsto" do T22 deve usar só os bytes de vértices e índices. Confirmar quando alguém ler `cena.*`.
7. **Dois limites por quadro, não um.** `motor.h` tem `ORCAMENTO_BYTES` = 2 MiB (linha 57) **e** `ORCAMENTO_TEMPO` = 4 ms (linhas 58 e 205). O T22 só fala do primeiro. O comentário da linha 16 diz "~4 ms", o da linha 57 diz "~1 ms no software".
8. **Pai na placa e em software.** O pai fica em cerca de 960 MB na placa real (`F0-S04.md`) e em 1.019 a 1.093 MB em software (T21). As contas abaixo usam o maior.
9. **Formato.** O `LOTE_OPUS_56/resultado.md`, dado como modelo, não tem a linha SPDX que o pedido exige. Este arquivo tem.
10. **"Saída igual (T12)".** O cartão T20 cita o T12, mas o cartão T12 não está no contexto. O oráculo do item 1 (§2.3 a §2.5) propõe uma conferência própria das malhas. Quem escrever o oráculo confere se ela cobre o critério exato do T12.

## 2. Item 1: memória ao abrir o arquivo pesado

### 2.1 O que os números permitem afirmar
**Quanto falta tirar** (pico somado, MB; para ficar abaixo de 6.000, é preciso tirar *mais* do que o valor abaixo):

| fios / bloco | fonte | mediana → falta | pior → falta | abrir |
|---|---|---|---|---|
| 8 / 1.000 (padrão, oficial) | placa real, 3 rodadas (6.841; 6.906; 6.743) | 6.841 → **841** | 6.906 → **906** | 40,5 s |
| 8 / 1.000 | software (T21) | 6.815 → 815 | 6.875 → 875 | 48,2 s |
| 4 / 1.000 | placa real, 1 rodada | 6.381 → 381 | — | 47,1 s |
| 4 / 1.000 | software | 6.480 → 480 | 6.568 → 568 | 54,4 s |
| 8 / 250 | software | 6.264 → 264 | 6.295 → 295 | 55,8 s |

**Permitem afirmar (medido):**
- O filho é o grosso: 5.734 MB residente com 8 fios e bloco 1.000.
- A base depois de abrir e listar é 915 MB de anônima.
- O bloco 6 começa com 2.331 MB e chega a 5.614 MB (+3.283 MB em 16,3 s).
- Do bloco 7 ao 14 sobram 1.214 a 1.340 MB acima da base.
- Só o bloco 1 já deixa 923 MB acima da base, enviando 87 MB.
- Com 1 fio, o pico do filho é 3.913 MB nos três blocos (com 2 peças simplificadas).
- O bloco pesa no pico: com 8 fios, o filho tem 5.207, 5.734 e 6.764 MB nos blocos 250, 1.000 e 4.000.
- Nenhuma das 12 combinações cumpre as duas metas.

**Não permitem afirmar:**
- Que a peça mais pesada está no bloco 6.
- Que a sobra é do alocador e não dado vivo.
- Que os números por peça do §5 valem dentro do carregador (§1 item 3).
- Qualquer número no Windows.

**Coincidência compatível, não prova.** A base mais a peça mais pesada sozinha dá 915 + 2.959 = 3.874 MB. O pico do filho com 1 fio é 3.913 MB, 1% acima.

**Teto da família "começar limpo"** (aritmética): o máximo que se tira do filho reiniciando a memória antes do bloco 6 é o que ele tinha acima da base ao começar esse bloco, **1.416 MB** (2.331 − 915).

Se o bloco 6 crescer o mesmo +3.283 MB a partir da base, o pico somado ficaria em cerca de 915 + 3.283 + 55 (diferença entre residente e anônima) + 1.076 (pai) ≈ **5.330 MB**. É **estimativa**, porque não se sabe se, num processo novo, o bloco cresce o mesmo.

### 2.2 Testes baratos, antes de qualquer código de produto (comuns às opções)
Todos são T2 (só sonda, como o T21). Rodam em tela virtual, porque o filho não desenha; o tempo de software fica cerca de 19% acima da placa. Os que abrem o arquivo pesado precisam do ok e do horário do PO, numa só sessão com `flock`, e usam `sonda_memoria.py`.

- **T1-0 (custo zero, sem abrir nada).** Comparar a configuração do iterador do "passe" da sonda com a do `_converter` (§1 item 3). Se forem diferentes, o §5 do T21 deixa de valer para o carregador.
- **T1-1 (1 abertura, 8 fios e bloco 1.000).** A sonda grava, para cada `feitos`, o instante, o número do bloco e a posição do id entre as 10 peças mais pesadas. Grava só a posição e os segundos, nunca o id. Responde de uma vez:
  - em que bloco estão as 10 peças (T21 §6.3);
  - o tempo de cada uma dentro do carregador;
  - o maior silêncio do filho em cada bloco (§1 item 5).

  Com 1 fio basta uma abertura extra, se o líder quiser fechar o item 5.
- **T1-2 (3 a 4 aberturas, 1 rodada cada, sem código).** Só variáveis de ambiente da glibc, documentadas em `mallopt(3)`: `MALLOC_ARENA_MAX=1` e `=2`, `MALLOC_TRIM_THRESHOLD_` baixo e `MALLOC_MMAP_THRESHOLD_` fixo. Mede o pico somado, a sobra acima da base e o tempo.
  - Se a sobra cai para perto de zero, ela é do alocador (Linux).
  - Se não cai, é dado vivo ou cache do conversor.
  - As variáveis passam também ao pai, porque o filho herda o ambiente. A conclusão sobre a 1-A usa só os números do filho, porque a mudança de produto só tocaria nele.
- **T1-3 (2 a 3 aberturas, protótipo da opção 1-B sem tocar no produto).** A sonda chama `processo_malhas.entrada` em sequência. Primeiro um filho com os ids dos blocos 1 a 5, depois um filho **novo** com os ids do bloco 6 em diante. Passa o `desl` do primeiro filho e respeita a fronteira de bloco. Mede o pico de cada filho, a soma honesta, o tempo e a saída.
  - Chamando `entrada` direto, os lotes crus recomeçam `indice` e mudam `feitos` e `total` (quem os renormaliza é o `_tratar` do carregador). Por isso a comparação com a abertura normal é só de vértices, índices, objetos e `desl`.
  - Depende do T1-1 dizer onde está o bloco pesado.
  - Para passar, precisa de: menos de 6.000 MB e 60 s ou menos no pesado, **e** os outros arquivos de referência sem piora (§2.4, oráculo 8).

Custo total estimado: 8 a 10 aberturas de cerca de 50 s, ou seja 15 a 20 minutos de máquina parada (**estimativa**).

### 2.3 Opção 1-A: devolver ao sistema a memória do filho entre blocos (alocador)
1. **O que muda.** Só em `processo_malhas.py`, dentro do filho e nunca no pai:
   - no início, `mallopt` por `ctypes` com o que o T1-2 provar;
   - depois de cada bloco (após `del it` e `emitir`), `malloc_trim(0)`.

   É só Linux. No Windows não há equivalente provado: `_heapmin` e `HeapCompact` são **não verificados**. Trocar o alocador por biblioteca nova (jemalloc, mimalloc) é dependência nova: fica fora (ADR-005 e ok do PO para instalar). **Classe T3** (processo filho, memória, fios).
2. **Números.** Teto de 1.416 MB no filho, só se o T1-2 mostrar que a sobra é do alocador **e** que o bloco 6 reaproveita a memória devolvida. O T1-2 é a medida; sem ele, nenhum ganho pode ser dito.
3. **Risco.**
   - Tempo: limitar as áreas de memória com 8 fios pode serializar a alocação (não medido).
   - Windows sem prova (T28): no Windows a meta ficaria sem solução conhecida.
   - Saída: o alocador não muda o cálculo (pelo código), mas o oráculo confere.
   - Não toca em `limite_peca_s` nem nos fios.
4. **Custo.** 1 cartão T3 de implementação (cerca de 40 a 80 linhas) e 1 de oráculo (cerca de 150 linhas), de outro agente.
5. **Teste antes.** T1-2, sem código, com o arquivo do PO, em tela virtual.
6. **Oráculo.**
   - As malhas por peça (id, GlobalId, bytes de vértices, índices e cores) e o `desl` são iguais aos do carregador atual, em IFC públicos e sintéticos no CI e no pesado na máquina do PO.
   - `simplificadas` e `sem_malha` não mudam (0 e as mesmas 6 no pesado, com 8 fios).
   - Nenhum ajuste de alocador vale no pai.
   - No Windows a chamada não existe ou não faz nada, e os testes do CI passam.
   - Medida oficial: 3 rodadas na placa real, mediana e pior ao lado (D8).
   - Os três arquivos de referência são remedidos sem piora (oráculo 8 da 1-B).
7. **Recomendação.** Fica como complemento ou plano B da 1-B, não como opção principal, porque só vale no Linux.

### 2.4 Opção 1-B: processo filho novo antes do bloco pesado, na mesma fronteira de bloco (**recomendada**)
1. **O que muda.** O carregador (`carregador._ler` e `_rodar`) passa a rodar o arquivo em **dois ou mais filhos em sequência**, cada um com uma faixa contínua de ids que **começa numa fronteira de bloco**. Os blocos ficam iguais aos de hoje, e daí o fluxo de lotes, o `desl` e o silêncio que o vigia vê.
   - O código já aceita isso: `params["ids"]` em modo normal (`processo_malhas.py:171-175`, `carregador.py:306-309`) e `params["desl"]` (linha 183).
   - Onde reiniciar, em duas variantes a decidir pelo T1-1 e pelo T1-3:
     - **B1**: antes do bloco que tem uma peça marcada como pesada por uma medida tirada só do IFC, sem geometria, já na listagem. Exemplo de medida: a contagem de coordenadas e faces da representação, com os itens mapeados.
     - **B2**: depois de um bloco, se a memória atual do filho passar da base mais um limiar novo. O pai lê a memória pelo sistema, como o `pico_memoria_mb` já faz.

   **Classe T3** (vigia, processo auxiliar, fios). É coerente com o ADR-004 1C (processo auxiliar descartável).
2. **Números.**
   - Teto: 1.416 MB no filho (§2.1). Estimativa de pico somado: cerca de 5.330 MB, se o bloco 6 crescer o mesmo num filho novo.
   - Custo de tempo: cada filho a mais abre e lista de novo, 3,5 + 0,3 s em software (medido, §3 do T21). Com 1 reinício, cerca de 48,2 + 3,8 ≈ 52 s em software; na placa, cerca de 44 s se a leitura custar o mesmo (**estimativa**). Com 3 reinícios, cerca de 59,6 s em software (**estimativa**, apertado).
   - Não permitem afirmar: que a medida do IFC acerta as peças pesadas (B1), nem quantos reinícios a B2 faria.
3. **Risco.**
   - **(a) Filhos simultâneos.** Se dois filhos rodarem ao mesmo tempo, a conta "pai + maior filho" deixa de ser honesta. Os filhos têm de ser estritamente em sequência.
   - **(b) Vigia.** Os reinícios planejados não podem gastar `max_espera_s`, `seguidos` nem `acusadas`, e não podem abrir o modo isolado.
   - **(c) Peça pesada sozinha.** Isolar a peça pesada num filho só dela pode fazer o vigia de 20 s disparar, porque ninguém mais manda mensagem (§1 item 5). Ela viraria caixa e a saída mudaria. Por isso a fronteira é de bloco, nunca de peça.
   - **(d) Tempo.** O processo novo pode deixar a primeira peça mais lenta (não medido).
   - **(e) Windows.** O fim do processo devolve a memória nos dois sistemas (pelo desenho), mas o Windows não foi medido (T28).
   - **(f) Arquivo.** A foto do arquivo (`foto_arquivo`) já é conferida a cada filho.
4. **Custo.**
   - 1 cartão T2 de sonda (T1-1 e T1-3, cerca de 150 a 250 linhas).
   - 1 cartão T3 de implementação (cerca de 150 a 250 linhas, com a medida de peso na mensagem `inicio`, se B1).
   - 1 cartão de oráculo (cerca de 200 a 300 linhas, outro agente).
   - Total: 3 cartões.
5. **Teste antes.** T1-1 e depois T1-3, com o arquivo do PO, em tela virtual. Se o T1-3 der menos de 6.000 MB **e** 60 s ou menos em software, a opção merece o cartão de implementação. Se der menos de 6.000 MB mas passar de 60 s em software, só a placa decide (com ok do PO).
6. **Oráculo.**
   1. Saída igual: o fluxo de lotes é igual **byte a byte** ao do carregador atual quando o reinício cai na fronteira de bloco (índice do lote, vértices, índices, objetos, `desl`). Vale em IFC públicos e sintéticos do CI, com reinício forçado por um gancho de teste, e no pesado na máquina do PO.
   2. `simplificadas`, `sem_malha` e `produtos_total` iguais aos de hoje.
   3. Nenhum filho começa antes de o anterior terminar (instantes de início e de fim de cada filho).
   4. Os valores padrão de `limite_peca_s` (20), `limite_abrir_s` (600), `max_pecas_condenadas` (20) e `max_espera_s` (120) não mudam. Um reinício planejado não altera `espera` nem `acusadas`.
   5. Os ganchos `OBIM_TESTE_*` (peça lenta, matar filho, falhar caixa, matar no fim) seguem iguais com reinícios.
   6. Cancelar durante um reinício entrega "cancelado" sem filho sobrando.
   7. Medida oficial: 3 rodadas na placa real (ok do PO), mediana e pior ao lado. A conta A e a conta B são ambas relatadas.
   8. Nada piora nos outros arquivos de referência. A mudança vale para todo arquivo, e a B1 ou a B2 também podem disparar no detalhado. O simples, o detalhado e o pesado são remedidos com todas as metas de abrir de `F0-S04.md`:
      - abrir em 60 s ou menos;
      - pico somado abaixo de 6,0 GB;
      - atraso máximo do mouse abaixo de 200 ms (hoje 13,3; 45,0 e 62,8 ms);
      - cerca de 60 quadros por segundo;
      - nenhuma peça simplificada e nenhum filho sobrando.

      Os números de hoje ficam ao lado.
7. **Recomendação.** É a opção recomendada para o item 1, se o T1-3 a confirmar. Funciona nos dois sistemas pelo desenho, não muda nada que se vê e reaproveita um caminho que o código já tem.

### 2.5 Opção 1-C: gerar a peça pesada por partes (por item da representação)
1. **O que muda.** Para as peças marcadas como pesadas, o filho converte cada item da representação separadamente e junta as malhas, em vez de um iterador para o produto inteiro. Isso muda `processo_malhas._bloco` e pede uma regra para a ordem dos vértices e para a cor por item. **Classe T3.**
2. **Números.** Ataca os cerca de 3,0 GB da peça. Mas esse número vem do §5, que pode não valer para o carregador (§1 item 3). Não se sabe quantos itens a peça tem nem quanto pesa o maior. **Nenhum ganho pode ser dito.**
3. **Risco.**
   - Alto para a saída igual: recortes, booleanas, transformação de itens mapeados e materiais por item podem dar malha diferente.
   - O tempo pode subir.
   - O vigia passa a ver outra cadência de mensagens.
4. **Custo.** 3 a 4 cartões (sonda da estrutura, conversão por item, junção e oráculo).
5. **Teste antes.**
   - Uma sonda abre o pesado sem geometria e conta, para as 3 peças mais pesadas: número de itens, tipos e fração das coordenadas no maior item. Só números.
   - Depois, um ensaio da peça por itens contra a peça inteira, comparando triângulos, coordenadas e o pico.
   - Usa o arquivo do PO, em tela virtual.
6. **Oráculo.** As malhas por peça são iguais às do carregador atual, além dos itens 2 a 8 da 1-B.
7. **Recomendação.** Só se 1-B e 1-A não bastarem.

### 2.6 O que não vale (padrão do PO)
- **Fios e bloco sozinhos.** Já medidos; nenhuma combinação passa.
- **As linhas de 1 fio.** Têm 2 caixas e 8 filhos.
- **Filhos ao mesmo tempo contados pela conta A.**
- **Isolar a peça pesada num filho só dela.** Arrisca a caixa pelo vigia.
- **Mudar `limite_peca_s`, 60 s ou 6,0 GB.**
- **Mudar a biblioteca de geometria da peça pesada.** Pode mudar a malha; só entraria provando que a saída fica igual.
- **"Outra forma de abrir o arquivo" como opção principal.** O teto é de cerca de 0,9 GB, mal cobre os 0,91 GB que faltam, e não há caminho medido nem verificado.
- **O pai (cerca de 1,07 GB).** Fica fora do contexto: o código da tela não foi lido.

## 3. Item 2: tempo de trocar a geometria em IFC real

### 3.1 O que os números permitem afirmar
**Medido:**
- Na placa: 49,2 ms (sintética de 3.000), 399,4 ms (25 MB) e 6.748,3 ms (detalhado).
- A espera do quadro é 74%, 97% e 99,6% do total; os cálculos somam menos de 25 ms.
- Os quadros vistos são 3, 24 e 405, a 16,2 a 16,6 ms cada.
- A sequência **volta atrás** em todas as trocas e nunca na criação de parede.
- Criar uma parede nas mesmas cenas, que só acrescenta um lote, mede 32,8 ms (25 MB) e 48,9 ms (detalhado) na placa.

**Pelo código** (`motor.h`, linhas 198 e 202 a 203): `seq_placa_` só volta a zero quando a geração da cena muda ou quando a placa é recriada. Quando a geração muda, `g.lotes.clear()` apaga o que está na placa, e o desenho (linha 287) só mostra `g.lotes`.

Junto com a queda da sequência medida, o mecanismo da hipótese 1 fica **muito provável**. Se ele vale, a cena **some e volta aos poucos** a cada troca: cerca de 6,7 s no detalhado. Isso é **não medido**.

**Não permitem afirmar:**
- Que todo o tempo vem do reenvio. Falta a prova de quantidade.
- O tamanho dos lotes da cena.
- O efeito em mover, apagar, desfazer e refazer. Pelo contrato eles também tiram ou trocam peças, então devem pagar o mesmo, mas isso é não medido.
- O fluxo B em IFC real (não medido).
- O M5 com cena grande (`lote.py` não tem `--ifc`; lacuna do `F0-S04.md`).

**Estimativa do tamanho dos lotes**, a partir dos "pedaços por troca": cada lote gera pelo menos 2 pedaços (vértices e índices), mais um a cada 2 MiB.
- Detalhado: 1.179 ≈ 2L + 403, ou seja cerca de 390 lotes de cerca de 2 MiB.
- 25 MB: cerca de 210 lotes de cerca de 0,2 MiB.

É **estimativa**; o T2-0 mede.

### 3.2 Testes baratos, antes de qualquer código de produto
- **T2-0 (só a sonda, T2, cena sintética, tela virtual, sem arquivo do PO).**
  - O que muda: só `prototypes/s04/sondas/sonda_m2b.py`, fora das pastas do M7.
  - Cenas: as sintéticas de 3.000 e de 41.600.
  - Durante uma troca, a sonda lê `estatisticas()` a cada quadro: `fatias_enviadas`, `triangulos_na_placa`, `lotes`, `bytes_copia` e `contextos`.
  - Compara com um reenvio completo forçado pelo gancho `perder_contexto()`.
  - **Hipótese 1 provada nos contadores** se, na troca:
    - `triangulos_na_placa` cai para perto de zero e volta;
    - as fatias e os quadros da troca batem com os do reenvio forçado;
    - `contextos` não sobe (a placa não foi recriada).
  - Também dá o número e o tamanho dos lotes, que decidem entre 2-A e 2-G.
  - Os quadros contados valem em software; os milissegundos, não.
- **T2-1 (ensaio de quantidade; ramo descartável que nunca vai ao `main`; classe T3).** O cartão T22 diz que editar o módulo C++ vira T3, mesmo num ramo descartável. Tratar como T2 seria rebaixar a classe, o que exige linha do líder no LOG.
  - `ORCAMENTO_BYTES` com 4 e 8 MiB e `ORCAMENTO_TEMPO` com 8 e 16 ms, na sintética de 41.600 e na de 3.000.
  - Previsão da hipótese 1 (estimativa): de cerca de 25 quadros para cerca de 13 e cerca de 7.
  - Se a queda for proporcional, a hipótese 1 fica provada também no tempo.
  - Na mesma variante se mede o M5 (sintética de 3.000) e se tira a curva da opção 2-B.
  - Rodar no 25 MB e no detalhado na placa só com ok e horário do PO.

### 3.3 Opção 2-A: não limpar a placa na troca; reenviar só os lotes que mudaram (**recomendada**)
1. **O que muda.**
   - Em `cena.h`/`cena.cpp` (não lidos): `atualizar` dá **identidade estável** a cada lote. A troca reconstrói só o lote que tinha a peça antiga (sem ela) e acrescenta o lote novo.
   - Em `motor.h` (`enviar`, linhas 201 a 227): sai o "limpa tudo" ao mudar de geração. Os lotes da placa são comparados pela identidade; quem não mudou fica, quem mudou ou é novo é reenviado com o orçamento atual, e quem saiu é solto.
   - `limpar()` e a perda de contexto seguem reenviando tudo (comportamento de hoje).
   - A sequência continua "maior prefixo contínuo de lotes já na placa". A régua do M2b não muda: o fluxo mede quando o quadro mostra a sequência do comando, e com 2-A esse quadro já tem a cena inteira.
   - Vale para os dois fluxos, porque `motor.h` é C++ puro e também está no fluxo B (linhas 3 e 4).
   - **Classe T3** (módulo C++, thread de desenho, mutexes).
2. **Números.**
   - Referência medida do caminho "só acrescentar" na placa: 32,8 ms (25 MB) e 48,9 ms (detalhado). **Não** é previsão da 2-A, que também refaz o lote antigo.
   - Estimativa: se o lote antigo tem cerca de 2 MiB (§3.1), soma 1 a 2 quadros, e o detalhado ficaria em cerca de 75 a 110 ms.
   - As paredes trocadas no roteiro foram criadas pelo próprio roteiro (provável; `roteiro_r.json` não lido) e ficam em lotes pequenos. Por isso o oráculo **tem** de editar também uma peça que veio do arquivo aberto, num lote grande.
3. **Risco.**
   - Ordem dos mutexes: `Motor::m_` → `DadosCena::m_` → `mc_` (ADR-004 §5) e a thread de desenho nunca toca no Python. É preciso mantê-las.
   - Um lote "sem a peça" com o mesmo id e conteúdo diferente pode desenhar dado velho, se a identidade for mal feita.
   - A seleção (`cena_.lotes()`) e a caixa da cena têm de acompanhar.
   - D3D11 e WARP no Windows: só o CI mede.
   - O M5 não deve piorar, porque se envia menos. A saída igual do IFC (juiz) não é tocada.
   - Tamanho dos cartões: estimativa, porque `cena.*` não foi lido.
4. **Custo.** 3 cartões (estimativa): cena com identidade de lote, cerca de 200 a 300 linhas; motor com a comparação, cerca de 150 a 250 linhas; oráculo de outro agente, cerca de 250 a 350 linhas.
5. **Teste antes.** T2-0 (sintético, sem o PO).
6. **Oráculo.** Especificado por um Opus que não seja o revisor final; testes por um sonnet diferente do implementador.
   1. Durante uma troca, a cada quadro, `triangulos_na_placa` ≥ triângulos da cena − triângulos da peça antiga. A cena nunca se esvazia.
   2. As fatias de uma troca ficam no máximo nas dos lotes reconstruídos e do novo.
   3. A captura depois da troca é igual, pixel a pixel, à captura depois de `perder_contexto()` (reenvio completo da cópia), com a mesma câmera.
      - Para isso ser determinístico, a 2-A **mantém na placa a mesma ordem de desenho da cópia compacta**. Ordem diferente pode mudar pixels em triângulos sobrepostos.
      - Ninguém afrouxa esse teste depois.
   4. São testadas uma parede criada pelo roteiro **e** uma peça de lote grande do arquivo aberto.
   5. Mover, apagar, desfazer, refazer, limpar e perda de contexto no meio de uma troca; a seleção acerta a peça nova e nunca a antiga.
   6. Os mesmos casos no fluxo B e nos jobs do Windows.
   7. Guarda de diff: a medição do M2b (`fluxo_a.py`, `medir_s04.py`, juiz) não muda.
   8. O M5 e o juiz estrito do T12 continuam passando.
   9. Medida na placa (ok do PO): M2b em 3 rodadas no 25 MB e no detalhado, com a meta de 200 ms ao lado.
7. **Recomendação.** É a opção recomendada para o item 2, depois do T2-0.

### 3.4 Opção 2-B: subir o orçamento por quadro
1. **O que muda.** `ORCAMENTO_BYTES` e, para valer, também `ORCAMENTO_TEMPO` (`motor.h:57-58`). **Classe T3.**
2. **Números.**
   - Estimativa, se a hipótese 1 valer e escalar em linha reta: para o detalhado ficar abaixo de 200 ms, o orçamento precisa de cerca de 100 MiB por quadro. Para o 25 MB, de 6 a 8 MiB.
   - Nada medido sobre o tempo de quadro com esses valores.
3. **Risco.**
   - Os dois limites existem para proteger o ritmo dos quadros. O M5 hoje dá 17,9 ms (meta abaixo de 200), mas não foi medido com cena grande.
   - A cena continua sumindo e voltando, só que mais rápido.
   - Cena duas vezes maior volta a estourar.
   - Cópias temporárias maiores no lote de envio (estimativa).
   - **Pela regra do PO, mexer nesses limites pede o ok dele** (pergunta 3).
4. **Custo.** 1 cartão de implementação e 1 cartão para criar o `--ifc` em `lote.py` (sem ele o M5 com cena real não é medido).
5. **Teste antes.** T2-1.
6. **Oráculo.** M5 em cena real (com o `--ifc` novo); M2b; captura igual à do reenvio completo.
7. **Recomendação.** Não recomendada como solução. Ataca o sintoma e depende de afrouxar um limite interno.

### 3.5 Opção 2-G (nova): esconder a peça antiga sem reenviar o lote dela
1. **O que muda.** Na troca, a placa só zera a faixa de índices da peça antiga no lote existente, que vira triângulos degenerados, e recebe o lote novo. Uma compactação depois, dentro do orçamento atual, refaz o lote.
   - É preciso confirmar se o QRhi aceita atualizar buffer `Immutable` (não verificado).
   - **Classe T3.**
2. **Números.** Envia só os índices da peça. Não há medida.
3. **Risco.** Mais complexa que a 2-A: a compactação em segundo plano, a seleção e a caixa da cena mudam. Muitos buracos aumentam o custo de desenho em software.
4. **Custo.** 3 a 4 cartões.
5. **Teste antes.** O tamanho dos lotes do T2-0. A 2-G só se justifica se os lotes forem grandes demais para a 2-A.
6. **Oráculo.** O mesmo da 2-A, mais: a compactação respeita o orçamento e o M5.
7. **Recomendação.** Plano B da 2-A.

### 3.6 "Reenvio em fatias com prioridade para o lote tocado": não vale sozinho
Enquanto a placa for limpa na troca, mandar o lote tocado primeiro não adianta. A sequência é "maior prefixo contínuo" (linha 223), e o quadro só conta quando todos os lotes anteriores voltaram. Para "ganhar", seria preciso mudar o que a sequência significa, e o quadro mostraria a peça nova com a cena incompleta. **Isso é a opção C disfarçada.** Só faz sentido dentro da 2-A, onde já não há o que reenviar.

### 3.7 Decisões do PO (C, D, E): só impacto, sem recomendação
- **C. Medir quando a peça nova aparece.**
  - Muda a régua do lote 9 §2.2.
  - Com o código de hoje, o número passaria a valer com a cena incompleta (§3.6). A tela some e volta e o número não mostraria isso.
  - Deixa de dar para comparar com a medição oficial da S04.
- **D. Meta por tamanho de cena.**
  - Muda `v2/03` (é do PO).
  - Aceitaria cerca de 6,7 s no detalhado.
  - O ADR-001 registraria o híbrido aprovado com meta mudada.
- **E. Manter e registrar.**
  - O M2b em IFC real fica "não atingido" no portão.
  - Pela regra da S04, a falha apontaria para o C++ puro. Mas o desenho é o mesmo C++ nos dois fluxos (pelo código), então o C++ puro não resolveria; o fluxo B em IFC real não foi medido.
  - Deixa o portão ambíguo.

## 4. Ordem sugerida entre os itens
1. **Já, sem o PO:** T1-0 (ler código) e T2-0 (sintético, tela virtual). Nenhum precisa de arquivo do PO.
2. **Uma sessão autorizada pelo PO** (arquivo pesado, em tela virtual): T1-1, T1-2 e T1-3. Na mesma liberação, se o PO quiser, mede-se o número e o tamanho dos lotes do **25 MB** para a 2-A, com a mesma sonda do T2-0. O 25 MB roda em software (436 ms no T22).
   - O detalhado **não** roda em tela virtual: o T22 viu `TimeoutError` na abertura em software, e o cartão T22 manda parar sem tocar em `OBIM_QUADRO_MS`.
   - A contagem de lotes do detalhado fica para a sessão na placa real (passo 5).
3. **Item 2 primeiro na implementação (2-A).** O diagnóstico se fecha sem o PO, o efeito esperado é grande, e o resultado pesa no ADR-001.
4. **Depois o item 1 (1-B)**, com o T1-3 em mãos. Os dois mexem em módulos diferentes (tela C++ e processo filho do carregador). Podem andar em paralelo, mas com 1 implementador por vez, conforme a regra do projeto.
5. **No fim, uma sessão na placa real** (ok e horário do PO): memória e abrir em 3 rodadas, e M2b no 25 MB e no detalhado.

Não há teste que meça os dois itens. O que se divide é a sessão com os arquivos do PO.

Se, depois dos testes, nenhuma opção de um item fechar a meta, a regra do `v2/03` vale: **parar e levar ao PO com opções**.

## 5. Efeito nos ADRs
- **ADR-001** (ainda não existe):
  - O M2b em IFC real parece um problema do desenho C++ comum aos dois fluxos (`motor.h:3-4`), não do Python. Não deveria pesar contra o híbrido.
  - Sugestão: o ADR-001 espera o T2-0 (e, se der, a 2-A) ou registra isso como ponto aberto.
  - A memória do pesado é do caminho da S03 (processo auxiliar), que os dois fluxos usariam do mesmo jeito (estimativa).
- **ADR-004:** a 1-B reforça a decisão 1C. A 2-A precisa manter a ordem de travas do §5.
- **ADR-005 §10:** nada muda se a 1-A usar só a glibc. Alocador novo é dependência nova.

## 6. Perguntas ao PO (só o que é decisão dele)
1. **Libera o arquivo pesado** para os testes T1-1, T1-2 e T1-3 (em tela virtual, cerca de 15 a 20 min de máquina parada, numa só sessão)? Na mesma sessão, libera também:
   - o **simples** e o **detalhado**, para conferir que nada piora neles;
   - o **25 MB**, só para contar os lotes?

   O detalhado não abre em tela virtual. A conferência dele e a contagem dos lotes dele ficam para a sessão na placa real. Qual horário? **Recomendação:** sim, todos, na mesma sessão.
2. **Autoriza rodar primeiro os testes baratos e só escolher a opção depois?** **Recomendação:** sim. Hoje nenhuma opção tem número que mostre que fecha a meta.
3. **O orçamento por quadro da tela** (2 MiB e 4 ms, que protegem o ritmo dos quadros) **conta como "limite existente"** pela sua regra? **Recomendação:** sim, conta. Com isso a 2-B só entra com o seu ok.
4. **As opções C, D e E** (mudar a forma de medir, mudar a meta, ou aceitar e registrar): quer considerá-las agora? **Recomendação:** não decidir agora. Esperar o T2-0 e a 2-A. (Não recomendo nenhuma das três.)
5. **Windows:** a medida da memória no Windows continua no T28, como hoje? **Recomendação:** sim. A opção escolhida tem de funcionar pelo desenho nos dois sistemas, o que favorece a 1-B sobre a 1-A.

## 7. O que registrar no LOG
- "Lote opus 57 | CONCLUÍDO (TA) | Planejamento do T20 fase 1 e do T22.
  - Item 1: opções 1-A (alocador, só Linux), **1-B recomendada** (filho novo na fronteira de bloco, antes do bloco pesado) e 1-C (peça por partes).
  - Item 2: **2-A recomendada** (reenviar só os lotes que mudaram), 2-B (orçamento; pede ok do PO) e 2-G (esconder a peça antiga). C, D e E só como decisão do PO, com impacto.
  - Testes antes de investir: T1-0 a T1-3 (arquivo do PO, tela virtual) e T2-0 e T2-1 (sintéticos).
  - 10 contradições listadas no §1: o 'causa conhecida' do T20, o §5 do T21 que pode não valer para o carregador, o vigia de 20 s que mede silêncio, a previsão de 41.600 do T22 e os dois limites por quadro."
- Corrigir no cartão T20: o "causa conhecida" passa a hipótese e a classe da fase 1 passa a TA (§1 itens 1 e 2). É tarefa de texto, com o ok do líder.
