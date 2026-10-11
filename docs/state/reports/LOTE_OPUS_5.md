# Lote Opus 5: revisão da S03-T05 (três partes) e amostra da T06 e da T25
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-11 · Pedido: commit `fde5b55`
- Itens: 1) revisão T3 da S03-T05, PRs 16 (Parte 0), 18 (Parte A) e 19 (Parte B) · 2) amostra de revisão da S03-T06 e da S03-T25
- Ramos lidos: `origin/s03-t05-p0` (`f1348f0`), `origin/s03-t05-a` (`55f482a`), `origin/s03-t05-b` (`bfdb400`), `origin/fix-locale` (`c71cfd6`, já no `main` como `4a8b39d`)

## Resumo para o PO
1. **As três partes da T05 estão reprovadas**, mas por defeitos pequenos e bem localizados. O desenho geral está certo e os números se confirmam: eu mesmo repeti as medições e deu **1.000.008 triângulos, abrir em 13,0 s, 870 MB de memória, atraso máximo de 133 ms**. Nada pede refazer; são correções de poucas linhas cada.
2. **Defeito que você veria:** fechar a janela enquanto o modelo carrega **derruba o programa** (falha de segmentação, 3 vezes em 3 ensaios de sair com a carga em andamento). Com o cancelamento ligado ao fechamento, sai limpo (2 em 2).
3. **Outro que você veria:** ao aproximar a câmera de uma ponta do modelo, **o fundo do modelo some** (o plano de corte distante é calculado a partir do ponto errado).
4. **Um teste meu estava mal calibrado, e o implementador ainda abriu um furo na medição.** O teste do "elemento pesado" (R2) quase sempre mede 3 a 20 ms quando a parada real é de 180 a 200 ms, porque a primeira amostra da sonda é jogada fora e é nela que a parada cai (9 de 10 execuções). Corrijo a especificação aqui (seção 1.1).
5. **Achado fora da T05, mais grave que tudo acima:** com o programa em português do Brasil, o IfcOpenShell **grava números com vírgula** e o IFC sai corrompido (`2799,9999999999995.`). A correção já aceita (PR 17) só arruma os testes; o programa de verdade continua exposto. Precisa de cartão antes de qualquer gravação de IFC.
6. **T06 aprovada** contra o cartão dela, com pendência importante: depois de carregar um IFC, o clique ainda testa o cubo escondido e devolve um objeto que não está na tela.
7. **T25 reprovada por falta de registro**, não por código: o relatório no `main` ainda diz "passo escrito, ainda não executado". Não há no repositório o resultado por sistema que o cartão exige.
8. Uma pergunta ao PO no fim (limite de 400 linhas), com recomendação.

## 0. Como este lote foi feito
- Lido: os três diffs, o `git show` do PR 17 e os arquivos da lista do pedido. **Exceções declaradas:** `grep` em `LOG.md` e `BOARD.md` (do ramo `s03-lote5`) por "T05", "T06", "T25" e "400", para não levantar pergunta já decidida e para achar o resultado da T25; leitura de `tests/test_viewport_selecao.py`, `tests/test_viewport_qrhi.py` e dos dois passos da T25 em `ci.yml`, sem os quais a amostra do item 2 seria no escuro.
- **Sem rede** (fora o `git fetch` pedido). **Não vi o estado do CI**: o líder precisa confirmar `linux` e `windows` verdes em cada PR.
- Tudo o que afirmo com número foi **executado por mim** nesta máquina (Linux, 16 CPUs lógicas, carga média 3 durante as medições), com scripts descartáveis fora do repositório. Toda janela abriu só em `xvfb-run -a -s "-screen 0 1280x1024x24"` com `LIBGL_ALWAYS_SOFTWARE=1` (Mesa llvmpipe). Nenhuma janela na tela real.
- **Não reproduzi** a linha "placa real" do relatório da Parte B (exigiria janela na tela do PO) nem nada no Windows.
- Conferências rápidas que passaram: os três arquivos do oráculo estão **idênticos** entre a Parte 0 e a Parte B (congelados de fato); os testes da T03, T04 e T06 não foram tocados; os quatro `.qsb` têm as seis variantes (GLSL 100es/120/150, **HLSL 50**, MSL 12, SPIR-V), então o par `malha` tem como desenhar em Direct3D 11; `REUSE.toml` cobre os `.qsb` e os PNG.

### Execuções de referência (Parte B, `bfdb400`)
| O que | Resultado |
|---|---|
| Oráculo + legado + T06, com tela virtual (xcb) | 37 passam, 5 pulam (lentos), 1 `xpass` (R2) |
| Suíte inteira, sem tela (como o CI) | 60 passam, 13 pulam, 1 `xpass` (R2) |
| O2 lento, `tamanho_bloco` 4000 e 0 | passam: 1.000.008 triângulos, 83.334 produtos, `sem_malha` vazio (bloco 4000: abrir 1,07 s, listar 0,33 s, geometria 11,0 s) |
| R1a M1M / R1b M1M (lentos) | atraso máx. 100,1 ms, p95 8,3 ms / máx. 107,4 ms, p95 9,4 ms |
| `medir.py`, threads padrão (15), bloco 4000, janela 640x480 | abrir **12,97 s**, 1º lote visível 2,17 s, pico **870 MB**, atraso máx. **132,8 ms**, p95 **9,2 ms**, 21 lotes, 65 MB na placa, 17,3 FPS (por software) |
| Só o carregador, sem janela | 15 threads: 12,6 s · **1 thread: 61,9 s** |
| R2, seis execuções seguidas | **6 de 6 `xpass`**; atraso medido 9, 177, 7, 15, 21 e 23 ms; `next()` mais longo 181 a 198 ms |

## 1. Item 1: revisão da S03-T05

### 1.1 Parte 0 (oráculo, PR 16): **REPROVADA**
A transcrição das tabelas está fiel: **nenhum limite foi afrouxado** (7.200, 21.600, 1.000.008, 83.334, 36.000, 15 lotes, 50 ms, 2 s, 200 ms, 33 ms, `1e-6`, `1e-5`, `1e-3`, razão 10.000, todos conferidos um a um). O que reprova é um furo na **medição** e um erro **meu** na especificação do R2.

**Correções exigidas**
1. **A sonda joga fora a primeira amostra** (`np.array(atrasos[1:] ...)` em `_medir`). O §1.5 manda medir "de `iniciar()` até o resumo". Qualquer parada que comece antes do primeiro disparo de 5 ms cai inteira na amostra descartada. Provado: no MAB a parada real é de 180 a 194 ms (sonda sem Qt, 5 de 5, com 1 e com 15 threads). Repeti o caminho exato do teste R2 em 10 processos, imprimindo a amostra descartada: em **9 de 10** a parada (191 a 204 ms) estava na amostra descartada e o teste viu 3 a 15 ms; em 1 de 10 o teste viu 188 ms. Sob `pytest`: 5 de 6 perdidas. O mesmo furo esconderia um carregador que abrisse o arquivo dentro de `iniciar()`, na thread da interface. **Correção:** ligar a sonda, deixar rodar ~100 ms **antes** de `iniciar()` (aquecimento), limpar a lista e contar **todas** as amostras a partir de `iniciar()`. Vale para R1a, R1b e R2.
2. **R2 não informa nada como eu o especifiquei** (erro meu, não do implementador). Com 150 aberturas a parada fica em 180 a 200 ms, colada no limite de 200 ms: dá `xpass` quando deveria mostrar o problema. **Emenda ao §1.5 (R2):** o R2 passa a usar um modelo próprio, **MAB400**: igual ao MAB, mas a parede pesada mede 60 m × 7,0 m × 0,3 m e tem **400 aberturas em 8 filas de 50** (mesmo passo de 1,1 m na horizontal e 0,8 m na vertical, mesma abertura). Medido nesta máquina, 3 vezes: `next()` mais longo de **514 a 515 ms** (150 aberturas: 181 a 198 ms; 500 em 5 filas de 100: 630 a 661 ms, coerente com o 0,7 s do lote 4). O teste confere primeiro, como exigência dura, que o `next()` mais longo é **≥ 300 ms** (se não for, falha pedindo revisão do modelo). A exigência "atraso ≤ 200 ms" continua `xfail` **não estrito**. O4 e O3 continuam no MAB de 150.
3. **O5:** falta conferir que os índices de cada produto ficam dentro da faixa de vértices **dele** (`primeiro_vertice` até `primeiro_vertice + n_vertices`). Hoje só confere `ix.max() < len(v)` por lote. A T06 depende disso para destacar um objeto. Duas linhas; a implementação já passa.
4. **O8, "nenhuma exceção na thread":** `aguardar()` devolve verdadeiro também se a thread morreu com exceção. Capturar com `threading.excepthook` e exigir lista vazia.
5. **O9 pode passar sem testar nada** em máquina lenta (se em 1 s o trabalhador produziu menos de 3 lotes, uma fila sem limite também passa). Esperar `lotes_produzidos` chegar a 3 (limite 60 s), dormir 1 s e exigir `== 3`.
6. **V3, "estatísticas zeradas":** decido que vale para **todas**, inclusive `buffers_criados` (contador desde o último `limpar()`; reenvio por troca de contexto pode aumentá-lo). Acrescentar ao teste. Hoje `limpar()` não zera (vi 480 depois de 40 ciclos).
7. **Casos novos, para os defeitos das partes A e B não voltarem:**
   - **V6 (plano distante):** M600 enquadrado; depois azimute 0, elevação 5, alvo = `(x_max + 2, centro_y, centro_z)` da caixa, distância 2; desenhar. Passa se o canto mais distante da caixa está a **≤ `camera.longe`** e `longe / perto ≤ 10.000`.
   - **V7 (adaptador):** com tela, `AdaptadorCarga.abrir(M600)` até o sinal `terminou`: `estado == "concluido"`, `estatisticas()["triangulos"] == 7.200`, `pendentes` zerado depois de alguns quadros. Hoje **nenhum teste** passa pelo adaptador.
   - **V8 (sair com carga em andamento):** em subprocesso, com tela: abrir M3000 pelo adaptador e chamar `QApplication.quit()` após o primeiro lote. Passa se o **código de saída é 0**.
   - **V9 (clique com lotes):** depois de `adicionar_lote`, `pick()` no centro da tela **não** devolve `1` (o cubo escondido).

**Escolhas do implementador onde o §1.5 não define: avaliação**
| Escolha | Avaliação |
|---|---|
| V4 lê `camera.perto` e `camera.longe` | Aceita. `Camera` é parte pública da T04 e o §1.4 diz que os planos são dela |
| O7, "depois de `cancelar()` só o resumo sai" (exatamente um item) | Aceita. É a leitura mais dura e bate com "exatamente um `ResumoCarga`" do §1.2 |
| R2 mede o `next()` mais longo num iterador separado, 1 thread, na thread principal | Aceita. Conferi que com 1, 4 e 15 threads o `next()` mais longo é o mesmo (191 a 194 ms) |
| Parametrizações extras (O5 também com bloco 200; O2 com 4000 e 0; R1b com M3000 e M1M) | Aceitas. O5 com bloco 200 é mais dura que a tabela |
| V5 roda os testes antigos em subprocesso | Aceita, com ressalva: sem tela os dois que desenham pulam, então no CI o V5 só prova "não quebrou a importação". A prova de "sem alteração" é o diff, que conferi |

**Só registrar (não bloqueia):** em O7, "triângulos entregues < 36.000" é sempre verdade (só 1 lote consumido) · `m600`, `m3000` e `mab` são importados de um arquivo de teste para outro, então cada modelo é gerado mais de uma vez por rodada; mover para `tests/conftest.py` (autorizo incluir esse arquivo na Parte 0) · O2 não confere `estado == "concluido"` · nenhum teste usa coordenadas de mapa (eu testei à mão: paredes em x = 7.000.000,25 m saem exatas, deslocamento arredondado ao metro: **correto**).

### 1.2 Parte A (`carregador.py`, PR 18): **REPROVADA**
Cumpre a arquitetura do §1.2 e o contrato do §1.3: arquivo aberto na thread de trabalho, lista de produtos com as exclusões, blocos com `include=`, ordenação por id, ajustes fixos, fila limitada, deslocamento em float64 antes do float32, cor por material com duplicação de vértice, normal recalculada quando falta, lote de até 8 MB em fronteira de produto, `sem_malha` com motivo, um resumo em qualquer desfecho. **Nenhum objeto do IfcOpenShell entra em lote** (tudo é cópia numpy; `guid` é texto). Não importa Qt. Não achei corrida entre a thread de trabalho e a interface além dos itens abaixo. 325 linhas.

**Correções exigidas (2)**
1. **`obter()` com `timeout` pode travar para sempre** (linha 193: `min(FATIA_S, max(0.0, fim - agora)) or None`). Quando o resto do prazo dá exatamente 0, a expressão vira `None` e a chamada passa a ser `fila.get()` **sem prazo**. Se nenhum lote chegar mais, não volta. Provado com relógio controlado: `obter(timeout=0.05)` não voltou em 3 s. A janela é de microssegundos por chamada, mas os testes fazem milhares de chamadas com `timeout`. O adaptador usa `timeout=0.0` e não é afetado. **Correção:** resto ≤ 0 → `get_nowait()`; nunca chamar `get` sem prazo.
2. **`deslocamento` é o mesmo vetor, gravável, em todos os lotes** (linhas 280 e 125). Quebra o "imutável" do §1.3: quem alterar um altera todos, e o trabalhador ainda o usa. Marcar como só leitura (como já é feito com `vertices`, `indices` e `objetos`).

**O `xfail` não estrito do R2 está certo?** Sim, mantém. Estrito quebraria o CI toda vez que desse `xpass`. O que estava errado é o teste dar `xpass` (itens 1 e 2 da Parte 0), não a marca. Enquanto isso o critério 5 do cartão ("R2 aparece como falha esperada") **não está cumprido**: 6 de 6 `xpass`.

**Recomendado (não é exigência do §1.3; aproveitar a mesma correção):** conferir o sinal de cancelamento também depois de abrir o arquivo e depois de listar os produtos. Hoje só é conferido após o primeiro produto; num arquivo grande isso são segundos sem olhar o sinal (abrir em si não tem como interromper).

**Só registrar:** `arquivo` é atribuído no fim de `_rodar`, um instante antes de o resumo ficar pronto, e a linha 292 repete a 291; nada mais toca o arquivo depois disso, então não há uso simultâneo: só limpar a linha repetida · ao cancelar, o resumo conta lotes montados que não foram entregues · `cancelar()` depois do fim natural devolve `estado == "concluido"` sem os lotes que estavam na fila; o adaptador deve tratar "eu cancelei" como verdade · `_paleta` engole qualquer exceção e pinta de cinza sem avisar; deveria ir para `mensagens` · a thread é `daemon`: sem Qt, sair com a carga em andamento terminou com código 0 (2 de 2), o problema aparece com Qt (Parte B, item 2) · a conversão `geo.verts` (tupla) → numpy é um motivo provável de 1 thread levar 61,9 s contra os 53 a 54 s que medi no lote 4 sem converter (o outro é a máquina estar em uso: carga média 3 a 3,8 durante esta medição); há ganho barato, **não fazer agora**.

### 1.3 Parte B (viewport, adaptador, medição, PR 19): **REPROVADA**
**O que confere com o §1.4:** `adicionar_lote` tem custo proporcional ao lote (uma caixa, uma entrada na lista; os anteriores não são tocados; V2 passa); pipeline `malha` **sem descarte de faces**; luz `0,35 + 0,65 × |normal · direção|`; uma chamada de desenho por lote; **no máximo 1 lote enviado por quadro**; adaptador com `QTimer` de 16 ms tirando 1 lote por disparo; cor em `UNormByte4`; transparência desenhada opaca. **Reenvio após troca de contexto funciona:** movi o widget para outra janela-mãe, o `QRhi` mudou, os 3 lotes foram reenviados (`buffers_criados` 6 → 12) e a imagem voltou igual; `setSampleCount(4)` também desenhou certo; 40 ciclos de carregar e `limpar()` sem queda e sem crescimento de memória. Quando o resumo chega, **0 de 21** lotes estavam pendentes de envio, então a janela do R1b cobre os envios.

**Correções exigidas**
1. **O plano distante corta o modelo.** `cubo_rhi.py:357` usa a distância da câmera ao **alvo**; o §1.4 item 4 diz distância ao **centro da cena**. Depois de mover ou aproximar, os dois diferem. Medido em M600: câmera a 2 m de uma ponta, `longe = 45,7 m`, canto mais distante a **65,5 m** (pela fórmula certa seriam 78,1 m). O V4 não pega porque logo após `enquadrar()` alvo e centro coincidem.
2. **Fechar durante a carga derruba o processo.** Sair com a carga em andamento: **falha de segmentação, código 139, 3 de 3** (2 por `QApplication.quit()`, 1 pelo fim do script com a thread viva). Ligando `aboutToQuit` a `AdaptadorCarga.cancelar()`: código 0, 2 de 2. Corrigir no adaptador (e no `__main__`): cancelar e esperar a thread ao sair e ao fechar o widget.
3. **`abrir()` com outra carga em andamento** espera na thread da interface (`aguardar(timeout=5.0)`): medi **398 ms** de janela parada com `tamanho_bloco=0`. E, se a thread antiga não terminar em 5 s (arquivo grande ainda abrindo, elemento pesado), **começa a nova assim mesmo**, com duas cargas vivas; o §1.3 diz "espera terminar". Não bloquear a interface além de uma fatia curta e nunca iniciar a nova com a antiga viva (esperar pelo próprio temporizador).
4. **O clique devolve um objeto que não está na tela.** Com M600 desenhado, `pick()` no centro devolve `1`: é o cubo escondido. Integrar a seleção aos lotes é cartão novo (item 2), mas a Parte B não pode deixar resposta errada: com lotes na tela, `pick()` devolve `None` e `clicado` não emite id até lá.
5. **`medir.py`:** (a) mesmo descarte da primeira amostra; (b) reimplementa o consumidor em vez de usar `AdaptadorCarga`, então o caminho que o programa usa nunca foi medido nem testado: usar o adaptador; (c) no Windows, `GetProcessMemoryInfo` é chamado sem `argtypes` e recebe um identificador de 64 bits como inteiro Python: **provável erro em tempo de execução, não verificado** (nada rodou no Windows). Declarar `argtypes`.
6. `limpar()` zera `buffers_criados` (decisão 6 da Parte 0).
7. **Relatório `F0-S03-T05.md`:** faltam a saída do O2 (critério 3 do cartão) e os números do R2 (critério 5) · a linha "placa real" não diz como nem por quem foi medida; o `LOG.md` registra uma janela aberta por engano na tela do PO na mesma sessão, e **suponho** que venha daí: o líder confirma e escreve no relatório · a explicação do p95 de 72,7 ms com bloco 1000 ("mais envios disputam a interface") não se sustenta com 4,6 envios por segundo; a causa provável são 84 `initialize()` de ~90 ms cada, um por bloco (§1.1 do lote 4): corrigir ou marcar como hipótese · o relatório precisa de nova rodada depois da correção da sonda.
8. **Tamanho:** 418 linhas acrescentadas (385 de código e 33 de relatório) e 4 removidas, sem contar as 3 do `conftest.py` que vieram do `main`, os `.qsb` e os PNG. Passa de 400 e vai crescer com as correções. Ver pergunta ao PO.

**Só registrar:** `releaseResources()` do `QRhiWidget` não foi implementado e os buffers antigos são só esquecidos na troca de contexto (achado 7 do lote 4 continua aberto; nos meus ensaios não falhou) → T07 · `enquadrar()` no fim da carga recoloca a câmera mesmo se o usuário já a moveu · `tobytes()` copia cada lote uma vez a mais antes do envio (até 8 MB, ~2 ms) · `enquadrar()` limita a distância a 10 km.

### 1.4 Metas e as duas dúvidas de política
**As exigências da T05 (§1.6) estão atingidas e eu as reproduzi** em tela virtual: abrir 12,97 s (< 60 s), 870 MB (< 6 GB), atraso máximo 132,8 ms (≤ 200), p95 9,2 ms (≤ 33). Os 13,5 s / 833 MB / 118 ms do relatório são coerentes com isso.
**Mas "metas do portão da S03 atingidas" (texto do `LOG.md` e do `BOARD.md`) está forte demais** e deve ser corrigido para "exigências da T05 atingidas": o modelo é sintético, de 74 MB e só caixas; os 60 FPS vieram de janela 640x480 e são o teto da sincronia vertical; nada foi medido no Windows; a seleção medida é a do cubo. O veredito do portão sai da T07, com IFC real do PO, como o próprio relatório da Parte B diz nas ressalvas.

- **(a) 1 thread acima de 60 s: manter assim.** O §1.6 não exige nada para 1 thread. Mas o número é pior do que eu tinha: **61,9 s só o carregador, sem janela** (máquina em uso, carga média 3 a 3,8). O risco R9 (máquina com 2 a 4 núcleos) fica mais forte. Encaminhar à T07: medir com `--threads 3` como aproximação de um notebook de 4 núcleos.
- **(b) Bloco 0 e bloco 1000: só registrar.** Bloco 0 reprovar (367 ms) é o que o teste tem de fazer: distingue os dois desenhos. Bloco 1000 com p95 de 72,7 ms confirma 4000 como padrão; fica para a T07 e o risco R7.
- **Limite do meu próprio oráculo, para a S04 saber:** o percentil 95 é por **amostra**, não por tempo. Uma parada de 90 ms conta como 1 amostra, igual a uma de 5 ms. Com 21 blocos são ~21 paradas de ~90 ms (estimativa: ~1,9 s de 13 s, perto de 14% do **tempo**) e o p95 continua em 9 ms. A frase "33 ms em 95% do tempo" que escrevi ao PO no lote 4 não é o que o teste mede. Não mudo o limite agora; recomendo que `medir.py` passe a imprimir também "% do tempo em paradas acima de 33 ms", só como registro.

## 2. Item 2: amostra da T06 e da T25

### 2.1 S03-T06 (seleção por clique): **APROVADA** contra o cartão
Os quatro critérios estão cumpridos. Rodei: testes sem tela e com tela passam; o teste pesado (M1M) deu **mediana 5,5 ms, máximo 14,8 ms** (meta < 100 ms), 83.334 objetos. A matemática (raio pela inversa de projeção × vista, caixas, Möller-Trumbore de dupla face, parada antecipada pela ordem de entrada) está correta.

**O `pick` em CPU com caixas por objeto escala?** Para o caso do modelo sintético, sim. Fora dele, medi os limites:
| Caso | Tempo |
|---|---|
| 83 mil objetos pequenos, raio que acerta | 5,8 ms |
| Raio que atravessa caixas folgadas sem acertar triângulo (objeto em L, peça girada, cobertura) | ~38 µs por caixa: 1.000 → 38 ms; **5.000 → 189 ms**; 20.000 → 754 ms |
| **Um** objeto com 1 milhão de triângulos (terreno, peça importada) | **218 ms** |
Ou seja: passa do limite de 100 ms com objeto único muito grande ou com milhares de caixas folgadas no caminho. Não é o caso de uma casa; é o caso de modelo real grande. Precisa de grade ou árvore por objeto grande; decidir na T07, com IFC real.

**Risco com os lotes da T05: há, e é concreto.**
1. **Não está integrado.** Depois de `adicionar_lote`, o clique testa o cubo escondido (Parte B, item 4).
2. `malha_de_ifc` usa o iterador padrão: **aberturas e espaços entram na seleção** (são invisíveis e ficam na frente de janelas e paredes). Com os lotes isso some, porque o carregador filtra.
3. `Malha` guarda outra cópia dos triângulos (36 bytes por triângulo) e em float32 **sem deslocamento**: com coordenadas de mapa perde precisão. O `LoteMalha` já traz `objetos` com caixa e faixas, `pos` e `indices`.

**Encaminhamento:** cartão novo (T2, antes da T07): `pick` sobre `LoteMalha.objetos` de todos os lotes, devolvendo `id_step` e `guid`, sem `Malha` própria; medir os três casos da tabela.

### 2.2 S03-T25 (desenho no CI): **REPROVADA** (falta o resultado; o código do passo não tem defeito)
1. **O critério 1 do cartão ("resultado por sistema") não está no repositório.** `docs/state/reports/F0-S03-ci-desenho.md` no `main` diz "passo escrito, ainda não executado no CI". Não achei linha de resultado em `LOG.md`. Sem rede não leio o CI. Do que está escrito, **a conclusão "desenha no Windows com WARP e no Linux com Mesa" não está sustentada**. Correção: atualizar o relatório com o número da execução, o veredito de cada sistema e o que o registro imprimiu.
2. **"Usou WARP" não é verificável hoje.** `QSG_RHI_BACKEND` e `QSG_RHI_PREFER_SOFTWARE_RENDERER` são variáveis do Qt Quick (o próprio relatório admite a dúvida), e o teste só imprime o nome do backend. Imprimir também o dispositivo: `rhi.driverInfo().deviceName` existe no PySide6 instalado (aqui devolveu "Mesa llvmpipe (LLVM 23.1.2, 256 bits)"). No Windows do runner deve aparecer "Microsoft Basic Render Driver"; se aparecer, a afirmação fica provada.
3. **"≥ 3 cores" prova que o quadro não é uniforme, não que é o cubo.** Passaria com lixo na leitura da imagem. Reforço barato: o pixel do canto é exatamente a cor de fundo (30, 30, 40) e pelo menos duas das cores conhecidas das faces aparecem.
4. **O que a conclusão vale, quando estiver registrada:** que o caminho Direct3D 11 do Qt, com os nossos shaders em HLSL e a correção de espaço de recorte, desenha. **Não vale** como prova de placa real, de driver de fabricante nem de desempenho. A meta de Windows do portão continua dependendo de medição na máquina ou VM do PO (T07).
5. O passo só roda `tests/test_viewport_qrhi.py` (o cubo). Depois do merge da T05, incluir `tests/test_viewport_malha.py`, para o pipeline dos lotes (atributo `UNormByte4`, sem descarte de faces) ser desenhado em Direct3D 11 também.

### 2.3 Achado fora do escopo: localidade (PR 17, já no `main`)
A correção do PR 17 (`LC_ALL=C` em `tests/conftest.py`) está certa **para os testes**. Mas o problema é do programa, e ela o tira da vista:
- **Reproduzido:** processo em `pt_BR.UTF-8`, depois de criar o `QApplication`, `LC_NUMERIC` vira `pt_BR` e o IfcOpenShell grava `#21=IFCEXTRUDEDAREASOLID(#16,#20,#15,2799,9999999999995.);` em vez de `2799.9999999999995`. O arquivo abre, mas a parede não gera geometria (`sem_malha`). **É corrupção silenciosa de IFC.**
- **Ler** um IFC correto com Qt em `pt_BR` funcionou (coordenadas exatas). O defeito é na **gravação**.
- Reproduzido **só no Linux**. No Windows o Qt pode não mexer na localidade do processo do mesmo jeito: **não verificado**.
- Não há `setlocale` em `app/`, `prototypes/` nem `scripts/`.
- **Encaminhamento (prioridade alta, classe T3 por ser gravação de IFC):** cartão para fixar `LC_NUMERIC` em "C" logo depois de criar o `QApplication` no programa e nos protótipos, com teste em subprocesso que roda em `pt_BR`, grava um número não inteiro e confere o ponto. Esse teste não pode herdar o `LC_ALL=C` do `conftest.py`. Detalhe: `LC_ALL=C` faz o Qt avisar que trocou para `C.UTF-8`; usar `C.UTF-8` direto.

## 3. Decisão
| Item | Veredito | Correções exigidas |
|---|---|---|
| T05 Parte 0 (PR 16) | **REPROVADA** | 7 (seção 1.1) |
| T05 Parte A (PR 18) | **REPROVADA** | 2 (seção 1.2), mais 1 recomendada |
| T05 Parte B (PR 19) | **REPROVADA** | 8 (seção 1.3) |
| T06 | **APROVADA** | nenhuma; 1 cartão novo |
| T25 | **REPROVADA** | 5 (seção 2.2), a principal é registrar o resultado |
Nada da T05 entra no `main`. É a primeira reprovação de cada parte (a regra de reescrever o cartão vale na segunda).

## 4. Para o líder
1. Este arquivo está no ramo `s03-lote5` (commit do próprio lote; sem PR aberto).
2. Ordem das correções: Parte 0 primeiro (quem escreve não é o subagente das partes A e B), depois A, depois B. As três voltam juntas ao próximo lote Opus; a Parte 0 corrigida muda o que A e B têm de passar.
3. Corrigir em `LOG.md` e `BOARD.md` a frase "metas do portão da S03 atingidas" (seção 1.4).
4. Cartões novos: localidade no programa (2.3, alta) · seleção sobre os lotes (2.1) · correções da T25 (2.2).
5. Confirmar o CI dos PRs (não vi) e registrar a emenda do R2 (1.1, item 2) como alteração do §1.5 do lote 4.
6. O PO já respondeu à pergunta da seção 5 (sim às duas recomendações). Antes de os subagentes começarem: ajustar o cartão `F0-S03-T05.md` (exceção da Parte 0; Parte B em B1 e B2) e copiar a resposta para `PO.md` e `LOG.md`.

## 5. Pergunta ao PO
**Respondida pelo PO no chat em 2026-10-11: "ok pode seguir com as recomendações".** Ficam valendo: (1) exceção ao limite de 400 linhas para a Parte 0 da T05 (só testes do oráculo); (2) Parte B dividida em B1 (viewport, shaders e adaptador) e B2 (medição e relatório), cada uma abaixo de 400 linhas. O líder copia para `docs/state/PO.md`, registra no `LOG.md` e ajusta o cartão `F0-S03-T05.md`.

**Limite de 400 linhas por PR na T05.** A Parte 0 tem **711** linhas (só o arquivo do carregador tem 402; dividir por arquivo não resolve) e vai crescer com os casos novos. A Parte B tem **418** e também vai crescer. O erro de origem é meu: defini as partes no lote 4 sem estimar o tamanho.
**Recomendo:** (1) abrir exceção para a **Parte 0**, registrada no `LOG.md`: é só teste, transcrito de tabelas, e eu confiro linha por linha de qualquer modo; (2) **dividir a Parte B** em B1 (viewport, shaders e adaptador) e B2 (medição e relatório), cada uma abaixo de 400, sem exceção.
