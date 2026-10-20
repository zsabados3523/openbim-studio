<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_64: resultado (revisão dos PRs 204, 210 e 211: T30a2 corrigido, T30a3, T30d2)
Revisor: Opus, esforço médio, contexto fechado (pedido; lote 63 inteiro, em especial §1 sobre o 204 e §3 ponto 4; cartões T30a2, T30a3, T30d2; ramos remotos `s04-t30a2-sublotes` 710ad57, `s04-t30a3-dados-lote` a97da0e, `s04-t30d2-oraculo` 5d837cf, contra `origin/main` 5ebf0d5). Não escrevi nenhum dos três. Não li `~/openbim-medicao` nem nenhum IFC. Nada foi mesclado, enviado ou editado fora deste arquivo.

## 0. O que rodei (worktree temporário no rascunho, já removido; `build.sh` em pasta temporária; `QT_QPA_PLATFORM=offscreen` e `xvfb-run`)
Testes: `test_s04_t30d2_sublotes_oraculo.py`, `test_s04_t30a1_sem_oraculo.py`, `test_s04_cena.py`, `test_formato_malha.py` (27 ao todo).
| build | resultado |
|---|---|
| `main` + 210 + 211 (estado depois dos 2 primeiros merges) | **24 passam, 2 xfail, 1 pulado** (contadores, T30b). Os 2 xfail são `teto` e `sequencias`, pelo motivo certo (sem sub-lotes). Bits pelo acessor passam (1 sub-lote = entrada exata). `bytes_copia` do T30d1: +2.757 (igual ao lote 63). Sub-lotes no caso de 24 MiB: 1 |
| `main` + 204 + 210 + 211, **com** os marcadores | **2 falham por XPASS(strict)** (`teto` e `sequencias`), 24 passam, 1 pulado. O "13 passam" do pedido só vale **depois** de tirar os 2 marcadores |
| idem, contando os 2 XPASS como passa | 14 do T30d2: 13 passam, 1 pulado (contadores). T30d1 adaptado: passa. `test_s04_cena.py` e `test_formato_malha.py`: passam sem edição |

Números medidos com o 204: `bytes_copia` do lote de 30.000 cubos (3 sub-lotes): subiu 27.570.000, esperado 27.570.000 (**exato**, zero de sobra). Pico de memória ao adicionar 72,3 MB: subiu 76,9 MB (limite lote + C + 16 MiB = 97,1 MB; sobra de cerca de 4,6 MB acima do lote, que é a tabela de objetos temporária). No `main` sem 204: subiu 73,5 MB.

CI (`gh pr checks`, só leitura): 204 (710ad57), 210 (a97da0e) e 211 (5d837cf) com `linux` e `windows` verdes (e os demais jobs). Nenhum dos três tem mesclagem automática armada. Atenção: o verde do 204 foi rodado sobre uma base anterior à entrada do PR 199 no `main`, então não vale como prova para a ordem do §2 ponto 4.

Sonda do acessor (210), nos dois builds: `dtype == DTYPE_VERTICE` (28 bytes), `writeable` falso nos dois arrays, `<u4`; `ValueError` para sequência 0, −1, maior que a última e depois de `limpar()`. O "segmentation fault" no fim da sonda é o mesmo do lote 63 (sonda sem `parar()`), aparece com e sem o PR.

## 1. Veredito por PR

### PR 204 (T30a2 corrigido, sub-lotes): **APROVADO**
Conteúdo aprovado: exatamente 710ad57 (`cena.cpp` e `cena.h`, +79 −29). Só entra do jeito do §4 (junto com a retirada dos marcadores, no mesmo CI).
Itens do lote 63:
- **Item 1 (índices desalinhados): resolvido.** Todas as leituras da entrada passam por `indice()` com `memcpy` (validação, teste de "partível" e cópia renumerada). Nenhum `reinterpret_cast` sobre `I.p`. O comentário "numpy: alinhado" saiu. Não há cópia temporária dos índices antes de partir. O oráculo item 8 passa com deslocamento de 2 bytes.
- **Item 2 (dois casos): resolvido.** `nao_partido` só em lote que não ladrilha e passa de C; `peca_maior_que_c` só em sub-lote de lote que ladrilha e passa de C. Conferi que, no lote que ladrilha, um sub-lote só passa de C se tiver uma peça só (o corte é feito antes de somar a peça que estoura, e o grupo começa vazio). `Totais` soma os dois.
- **Item 3 (marcas velhas no `sem`): resolvido.** As marcas são recalculadas pelo resultado: valem só se o lote refeito ainda passar de C (e, para a peça, se ainda tiver 1 peça). Como o lote só encolhe, isso é igual a recalcular do zero, com a ressalva da sugestão 1.

Novo no diff, conferido:
- **Limite C:** `>` estrito nos dois lugares (agrupar e marcar) e com a mesma conta (nv × 28 + ni × 4). Lote de exatamente C fica inteiro (oráculo: 2 peças de 4 MiB = 1 sub-lote; 10.280 cubos = 1; 10.281 = 2).
- **Fronteira de peça:** o corte só cai entre peças, e só quando as peças ladrilham índices e vértices em ordem, sem sobra e cada uma só aponta para os próprios vértices; assim nenhum índice de sub-lote sai dos vértices dele. A renumeração (`indice − v0`) não pode dar negativo por causa disso.
- **Sequência devolvida:** a do último sub-lote, em `adicionar_lote` e em `atualizar`; um só `++ver_` por chamada; todos os sub-lotes entram sob um único `DadosCena::m_`. O deslocamento é conferido antes de mudar qualquer coisa; erro de índice ou de faixa sai de `preparar` antes do mutex (oráculo item 7 passa nas duas vias).
- **`ger_`:** intocado; só sobe quando `sem` refaz um lote, como antes.
- **`bytes_copia`:** exato (§0). A tabela de cada sub-lote tem `reserve` exato; o vetor temporário de objetos morre antes do retorno; os textos de GlobalId são movidos, com a capacidade original.
- Diff: 108 linhas. Arquivos dentro do permitido. Testes não tocados.

Sugestões (não bloqueiam):
1. `cena.cpp`, `sem`: um lote não partido que, depois de remoções, fica com 1 peça maior que C continua contado como `nao_partido`, não como `pecas_maiores_que_c`. Está certo pela definição (é um lote de entrada que não ladrilhou), mas escrever isso no cartão T30b, na definição dos contadores, para a medida dos dados reais não confundir os dois.
2. `cena.cpp`, `preparar`: o vetor temporário `objs` guarda a tabela inteira (80 bytes por peça mais o texto) até o fim. Cabe na folga (medido: +4,6 MB num lote de 72 MB). Só mexer se a medida dos dados reais mostrar tabela grande.

### PR 210 (T30a3, acessor `dados_lote`): **APROVADO**
Conteúdo aprovado: exatamente a97da0e (só `ponte_viewport.cpp`, +11).
- Mexe **só na ponte**; nada no núcleo, nenhuma mudança de comportamento da cena.
- Devolve **cópias**: os bytes são copiados para um `bytes` do Python e o `numpy.frombuffer` sobre ele dá arrays **só de leitura** (conferido). Mudar a cena depois não mexe neles, e eles não podem ser escritos.
- **`ValueError`** em sequência desconhecida ou limpa (vem do `lote(seq)`, como em `objetos(seq)`; conferido nos 4 casos do §0).
- **Vida do buffer:** sem risco. O `shared_ptr` do lote fica vivo durante a cópia, o lote é imutável depois de publicado, e nada do C++ fica guardado no array.
- **Mutex:** sem risco de bloqueio. Ele segura o bloqueio do interpretador e pega o `DadosCena::m_` só no `lote(seq)`, igual ao `objetos(seq)` que já existe; nenhuma thread do núcleo segura o `m_` esperando o interpretador.
- **Contrato de formato:** mantido. O dtype é montado por lista de tuplas, sem um terceiro `nb::eval`, e sai igual ao `DTYPE_VERTICE` (conferido); `test_formato_malha.py` passa sem edição.

Sugestões (não bloqueiam):
1. O dtype é montado a cada chamada. É barato e só para teste; se o acessor sair do teste um dia, guardar como os outros (`static`).
2. `"<u4"` supõe máquina little-endian. Windows e Linux em x86 e ARM são; basta uma linha no comentário.

### PR 211 (T30d2, oráculo dos sub-lotes): **APROVADO**
Conteúdo aprovado: 5d837cf, **mais**, no momento do §4, um commit do **autor do oráculo** (nunca o implementador do T30a2) que mude **só** isto em `tests/test_s04_t30d2_sublotes_oraculo.py`:
- apagar a linha `AINDA_NAO = pytest.mark.xfail(...)`;
- apagar as duas linhas `@AINDA_NAO` (antes de `test_teto_...` e de `test_sequencias_...`);
- na docstring, trocar a linha "`@AINDA_NAO` (xfail estrito) = o `main` de hoje não parte lotes; ..." por "Sub-lotes: passam desde o T30a2 (PR 204)."

Nada mais. O líder confere com `git diff 5d837cf -- tests/` (4 linhas). Diff do 211: 385 linhas (370 + 15), abaixo de 400; CI `linux` e `windows` verdes no próprio PR (no Windows, os casos rodam com `Cena(True)`, OpenGL; passou assim).

As 11 exigências, uma a uma (nenhuma afrouxada):
1. **T30d1 adaptado:** tabela da chamada = concatenação de `objetos(q)` da faixa; contagem de lotes pelas faixas mais 1 por marcador; em cada sub-lote as faixas começam em 0 e são contíguas; com 1 sub-lote, as faixas têm de ser **exatamente** as da forma canônica, como antes. Nenhum número mudou (tamanhos, casos, limites, `bytes_copia` seguem iguais; medido +2.757 nos dois builds). Duas conferências ficaram **mais** duras: a sequência do marcador agora tem de ser exatamente a anterior + 1 (antes só "maior"), e a contagem esperada soma 1 por marcador em vez de copiar o que a cena diz.
2. **Sequência:** seguidas (lotes ganhos = largura da faixa), crescentes, marcador = 1, `atualizar` com lote novo maior que C devolve a do último (a união da faixa tem de ser a entrada inteira) e o GlobalId removido some. `@AINDA_NAO`.
3. **Teto:** todos os casos do cartão (exatamente C, C + 1 peça, 10.280 e 10.281 cubos, gigante sozinha, no início, no meio e no fim, vértice compartilhado e tabela fora de ordem, cada um abaixo e acima de C), número de sub-lotes igual ao mínimo, sub-lote maior que C só com 1 peça ou lote inteiro. `@AINDA_NAO`.
4. **União igual à entrada:** pelas tabelas sempre; em bits, por GlobalId, pelo acessor do 210 (guarda: pula sem ele).
5. **Desenho:** igual pixel a pixel à cena partida pelo Python (4 × 7.750 cubos, cada um abaixo de C) e depois de `perder_contexto()`; mais a câmera enquadrada igual.
6. **Honestidade:** nenhum quadro com sequência ≥ S antes de a placa ter todos os triângulos da chamada.
7. **Erros atômicos:** 4 lotes ruins (índice fora, faixa fora, deslocamento diferente, índices não múltiplos de 3) pelas duas vias, `ValueError`, cena igual (lotes, triângulos, vértices, `bytes_copia`, tabela do lote 1) e nenhuma sequência publicada pela metade.
8. **Desalinhados:** 12.000 cubos (parte) e 50 (não parte), mesmo número de sub-lotes e mesma união.
9. **`bytes_copia`:** lote de 30.000 cubos (cerca de 23 MiB); soma dos sub-lotes igual à entrada e diferença dentro de ±64 KiB (medido: 0).
10. **Contadores:** com guarda até o T30b (pula hoje, sem afrouxar o número esperado de cada caso).
11. **Memória:** só Linux (pula fora dele e se `/proc/self/clear_refs` faltar); limite lote + C + 16 MiB. A medida roda em subprocesso, então o pico é só do caso.

Marcadores `@AINDA_NAO` que existem: **2**, os dos itens 2 e 3. Quem tira: o autor do oráculo T30d2, no commit acima, no momento do §4. As guardas (acessor, contadores, Linux) **não** são marcadores e ficam.

Sugestões (não bloqueiam; podem ir no mesmo commit do autor do oráculo **só se** o líder aceitar passar de 4 para algumas linhas, senão no T30b):
1. `c_desenho`: depois de `limpar()` e das 4 chamadas, `cheia()` pode ser verdade ainda com a placa velha (antes de a thread de desenho ver o `limpar`). A espera de 800 ms torna isso improvável, mas, se acontecer, a imagem "partida pelo Python" seria a mesma da primeira e o teste passaria sem provar nada. Mais firme: esperar um quadro com sequência ≥ a devolvida pela última das 4 chamadas (`quadros(c)`, como em `c_honestidade`) e só então `cheia()`.
2. O cartão T30a3 pede `ValueError` em sequência desconhecida ou limpa; o oráculo não confere. Conferi à mão (§0). Acrescentar no oráculo do T30b.

## 2. Respostas aos pontos 1 a 5

### Ponto 1 (204): itens 1 a 3 do lote 63 resolvidos; nada novo que bloqueie
Ver §1. Limite C, fronteira de peça, sequência devolvida, `ger_` e `bytes_copia` conferidos no código e medidos. Duas sugestões, nenhuma bloqueia.

### Ponto 2 (210): sim aos quatro
Só a ponte; cópias só de leitura; `ValueError` em sequência inexistente ou limpa; sem risco de vida do buffer nem de bloqueio de mutex. Aprovado sem mudar o contrato de formato: `test_formato_malha.py` passa e o dtype sai igual.

### Ponto 3 (211): 11 exigências cobertas, nenhuma afrouxada
O item 11 só roda no Linux (pula nos outros). A adaptação do T30d1 não mudou nenhum número; duas conferências ficaram mais duras. Marcadores: 2 (itens 2 e 3), tirados pelo autor do oráculo no §4. **Correção ao pedido:** com 204 e 210 e os marcadores ainda no arquivo, o resultado não é "13 passam": são 2 falhas por XPASS(strict). Os 13 só valem com os marcadores tirados. Isso decide a ordem.

### Ponto 4 (ordem de merge): 210 → 211 → 204 com a retirada dos marcadores no mesmo CI
1. **PR 210** primeiro. Sozinho no `main` não muda nada do que já existe (o acessor é novo).
2. **PR 211** depois. Com 210 no `main`: 24 passam, 2 xfail, 1 pulado (§0). O T30d1 adaptado vale com e sem sub-lotes.
3. **PR 204** por último, **nunca antes dos oráculos**. Diferente do lote 63, não dá para o 204 entrar sozinho: no `main` de hoje ele deixa o T30d1 (do PR 199, já mesclado) vermelho (medido no lote 63 contra 0e52319; a correção 710ad57 não muda a divisão, e o T30d1 sem adaptar supõe 1 lote por chamada), e depois do 211 ele deixa os 2 marcados vermelhos por XPASS(strict). Então:
   - o líder mescla o `main` (com 210 e 211) no ramo `s04-t30a2-sublotes`;
   - o **autor do oráculo T30d2**, em commit próprio nesse mesmo ramo, tira os 2 marcadores (só as linhas do §1);
   - o implementador do T30a2 não toca no arquivo de teste;
   - com `linux` e `windows` verdes nesse commit, merge do 204, e o líder confere que o diff do PR é 710ad57 + o merge do `main` + as 4 linhas do teste.

   Assim o mesmo CI mostra a implementação e o oráculo sem marcador passando juntos.

### Ponto 5 (para o cartão T30b): o que o oráculo ainda não cobre
1. **Contadores no Python:** `nao_partidos` e `pecas_maiores_que_c` em `Estatisticas` (`motor.h`) e uma linha em `ponte_viewport.cpp` (estatísticas). Com isso, o teste do item 10 deixa de pular sozinho (é guarda, não marcador; ninguém edita). Escrever a definição dos dois (sugestão 1 do 204), inclusive o que acontece depois de `sem`. E pôr no oráculo do T30b: os contadores **depois de remover peças** (peça maior que C removida faz `pecas_maiores_que_c` cair; lote não partido que cai para C ou menos sai da conta).
2. **Reenvio por posição:** trocar uma peça de um lote grande refaz **só** o sub-lote dela; os outros sub-lotes do mesmo lote de entrada ficam com os mesmos bits (pelo `dados_lote`) e a mesma sequência; quadros por troca, captura no quadro de S, troca repetida e apagar em no máximo 2 quadros (lote 62 §6.4).
3. **Instantâneo e `ger_`** (lote 63 §3 ponto 1): troca não sobe `ger_`; `limpar()` sobe; ponteiros, `ger_` e `ver_` tirados juntos sob `DadosCena::m_`. Oráculo por outro agente.
4. **Sugestões do 211:** espera por sequência no `c_desenho` e `ValueError` do `dados_lote`.
5. **Arquivos permitidos e tamanho:** como no lote 63 §3 ponto 1 (`cena.h`/`cena.cpp` só para `ger_` e instantâneo, `motor.h`, uma linha da ponte). Se passar de 400 linhas, dividir (T30b1 cena, T30b2 motor) antes, sem pedir exceção.
6. **Medida dos dados reais** (lote 63 §3 ponto 2) continua fora do T30b: vai à sonda do T30c, agora possível com o 204 no `main`, com a regra de decisão já escrita lá.

## 3. Perguntas ao PO
Nenhuma. Nada aqui muda meta, escopo, licença ou regra do processo.

## 4. Resumo para o PO (5 linhas, sem siglas)
1. A divisão do desenho em pedaços de até 8 megas foi consertada e está aprovada: a leitura de memória ficou segura e os dois casos de "pedaço grande" agora são contados separados.
2. A ferramenta de teste que deixa conferir os dados de cada pedaço, byte a byte, está aprovada; ela não muda nada no programa.
3. O teste novo que confere a divisão está aprovado e cobre os 11 pontos pedidos, sem afrouxar nenhum número.
4. A memória extra da divisão é zero e o pico ficou bem abaixo do limite.
5. Ordem de entrada: primeiro a ferramenta de teste, depois o teste, e por último a divisão, junto com a retirada das duas marcas de "ainda não" pelo autor do teste.

## 5. Linha do LOG
`2026-10-20 | F0-S04-T30a2, T30a3, T30d2 | LOTE_OPUS_64 (opus, médio) | 204 APROVADO (710ad57; índices por memcpy em toda leitura da entrada, nao_partido e peca_maior_que_c separados e recalculados no sem; bytes_copia exato, 27.570.000 = soma dos sub-lotes; pico +76,9 MB para lote de 72,3 MB), 210 APROVADO (a97da0e; só a ponte, cópias só de leitura, ValueError em sequência desconhecida/limpa, dtype igual sem terceiro nb::eval), 211 APROVADO (5d837cf + commit do autor do oráculo tirando só AINDA_NAO, os 2 @AINDA_NAO e a linha da docstring); 11 exigências cobertas, T30d1 sem número mudado e 2 conferências mais duras; com 204 e marcadores = 2 XPASS(strict), o "13 passam" do pedido só vale sem eles; merge 210 → 211 → 204 (main mesclado no ramo do 204 + commit do autor do oráculo no mesmo CI); 204 não entra antes dos oráculos; T30b ganha contadores no Python (e depois de sem), reenvio por posição com bits por dados_lote, ger_ e instantâneo, espera por sequência no c_desenho e ValueError do dados_lote | docs/state/lotes/LOTE_OPUS_64/resultado.md`
