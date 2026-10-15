<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Lote Opus 5: revisão da S03-T05 (partes 0, A e B) e amostra de T06 e T25
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-11 · Pedido: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_5/pedido.md`
- Ramos revisados: `origin/s03-t05-p0` (`f1348f0`), `origin/s03-t05-a` (`55f482a`), `origin/s03-t05-b` (`bfdb400`); `origin/fix-locale` já está no `main`
- Veredito: **Parte 0 REPROVADA · Parte A REPROVADA · Parte B REPROVADA · T06 APROVADA · T25 REPROVADA (falta registrar o resultado)**. Os defeitos que bloqueiam são poucos e pequenos (cerca de 60 linhas no total). Nenhum invalida as medições.

## Resumo para o PO
1. **O carregador e o viewport funcionam.** Rodei tudo de novo numa tela virtual: 34 testes passam e 1 dá "falha esperada que passou" (R2, explicado no item 1.1). O modelo de 1 milhão de triângulos deu 1.000.008 triângulos com os dois tamanhos de bloco, em 12,7 s e 11,4 s.
2. **Mesmo assim, não aprovo o merge ainda.** Achei 2 defeitos reais que os testes não pegaram. (a) Uma função do carregador pode travar a janela para sempre num caso raro. Reproduzi. O programa em si não usa esse caminho, mas os testes usam. (b) Depois de arrastar a vista para o lado, o fundo do modelo pode sumir, cortado pelo plano "longe". Também reproduzi. A correção dos dois é de 1 a 3 linhas cada.
3. **As metas medidas na T05 foram atingidas** (abrir 13,5 s, 833 MB, atraso 118 ms). Mas **o portão da S03 ainda não está decidido.** Quem decide é a T07, com o seu IFC real e com o Windows. O LOG e o BOARD dizem "metas do portão atingidas", e isso precisa ser corrigido.
4. **Achado sério fora da T05:** com o computador em português, o IfcOpenShell **grava IFC corrompido** dentro do programa. Ele escreve `2799,9999` com vírgula no lugar do ponto. Reproduzi. O PR 17 só esconde isso nos testes. Como "IFC limpo" é a missão, isso vira cartão T3 próprio.
5. **Duas partes passam do limite de 400 linhas:** a Parte 0 tem 711 e a Parte B cerca de 418. Isso pede decisão sua (pergunta no fim).

## 0. Como este lote foi feito
- Lido: o pedido, `arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md`, os cartões T05, T06 e T25, o relatório da T05 (ramo B), `selecao.py` e os diffs dos três ramos. Também consultei, para checar evidências, `LOG.md`, `BOARD.md`, `PO.md`, `REUSE.toml` e trechos de `ci.yml`, de `test_viewport_qrhi.py`, de `test_viewport_selecao.py` e do README do protótipo.
- **Exceção declarada:** usei `gh pr view 18` uma vez (só leitura da descrição do PR) antes de lembrar que o pedido diz "sem rede". Não houve outro acesso à rede.
- Execução: o worktree `../openbim-studio-wt-lote5` foi tirado do ramo B (que contém 0 e A) e removido no fim. Os testes gráficos rodaram só em Xvfb com llvmpipe. Scripts de sonda ficaram no rascunho da sessão, fora do repositório. Nada foi instalado, nenhum commit foi feito.
- Resultados:
  - offscreen: 16 passam, 9 pulam com mensagem, R2 xpass.
  - Xvfb com `OBIM_TESTES_LENTOS=1`, incluindo T03 e T04: **34 passam, 1 xpass**.
    - O2: 1.000.008 triângulos com bloco 4000 (12,7 s) e com bloco 0 (11,4 s).
    - R1a M1M: máx. 79 ms, p95 7,9 ms. R1b M1M: máx. 149 ms, p95 8,7 ms.
    - R2: atraso 178 ms; `next()` mais longo 186 ms.
  - T06 em Xvfb: 7 passam, 1 pula (o teste pesado). `reuse lint` passa (186/186).
  - Os `.qsb` de malha foram refeitos com o `qsb` local e **saíram iguais byte a byte**. Eles contêm HLSL, GLSL e MSL.

## 1. Item 1: S03-T05

### 1.1 Parte 0 (oráculo): **REPROVADA**
**Fidelidade:** todos os números do §1.5 estão transcritos **sem afrouxar**: 7.200 / 21.600, 1.000.008 / 83.334, 1e-6 / 1e-5, 230±1 e vermelho exato, 50 ms / 2 s / 36.000, fila ≤ 3 e 15 lotes, 200 / 33 ms, 7.200 e 5–95 %, `longe/perto ≤ 10.000`. As receitas de MAB, cor e defeito estão conferidas.

**Escolhas onde o §1.5 não define (todas aceitas):**
- **V3 "zeradas"** sem `buffers_criados`: aceito. Fica definido que `buffers_criados` é contador acumulado desde que o widget nasceu (é diagnóstico). V2 continua valendo, porque cada teste usa um widget novo.
- **V4 acessando `camera.perto/longe`**: aceito; são atributos públicos da `Camera` da T04.
- **O7 "só o resumo sai"** (exatamente 1 item, e ele é o resumo): aceito. É mais estrito que o §1.5 e coerente com o §1.2 ("exatamente um `ResumoCarga`").
- **R2 medido num iterador separado**: aceito. O carregador não expõe o tempo do `next()`, e o fenômeno é o mesmo.
- **Parametrizações extras** (O5 com bloco 200, O8 em dois modos, O3 nos dois modelos): aceitas; só deixam o teste mais estrito.
- **R2 `xfail` não estrito: está certo.** O limite de 200 ms coincide com o tempo do elemento (178 a 200 ms), então o resultado oscila entre xfail e xpass. "Estrito" faria o CI piscar. O defeito é do **meu** desenho no lote 4: o teste registra o número, mas não demonstra o fenômeno (ver item 5 da lista abaixo).

**Defeitos (o oráculo é congelado no merge; corrigir antes, enquanto é barato):**
1. **Afrouxamento pequeno em R1 (e em `medir.py`): `atrasos[1:]` descarta a primeira amostra.** É justamente ela que contém o custo de `iniciar()`. Um `iniciar()` que abrisse o arquivo na thread da interface (1,1 s no M1M) passaria despercebido, e o O10 também não pega isso. Correção: ligar a sonda, chamar `iniciar()` via `QTimer.singleShot(0, ...)` já dentro do laço de eventos e **manter todas as amostras**.
2. **O8 não prova "nenhuma exceção na thread".** `aguardar()` também devolve True quando a thread morreu com exceção. Correção: capturar `threading.excepthook` (via `monkeypatch`) durante O8 e O1 e exigir lista vazia.
3. **Teste novo O11, "`obter(timeout)` sempre volta":** com o trabalhador terminado e a fila vazia, `obter(timeout=t)` volta em `< t + 0,1 s` para `t` em {0, 1e-9, 0,01, 0,05}. Pega o defeito A-1.
4. **V4 só confere a razão `longe/perto`, não que a cena cabe.** Acrescentar: depois de `enquadrar()` e de `camera.mover(-600, 0, 480)` e `mover(0, 400, 480)`, o canto mais distante da caixa da cena fica a menos de `camera.longe`, e o mais próximo a mais de `camera.perto` (ou dentro da caixa). Pega o defeito B-1.
5. **R2 passa a demonstrar o fenômeno** (emenda do §1.5): acrescentar a afirmação, que **passa**, "atraso máximo ≥ 0,5 × `next()` mais longo". Se a S04 resolver o problema do GIL, esse teste falha e avisa. O `xfail` de 200 ms fica como está.
6. **Imprimir os números de R1 e R2 também na mensagem** (`record_property` ou `pytest.fail` com o texto). Hoje eles só aparecem com `-s`. Não bloqueia.

Quem escreve: o mesmo autor da Parte 0, não o implementador de A e B. Os itens 3 a 5 são **emenda minha ao §1.5** e valem como oráculo.

### 1.2 Parte A (`carregador.py`): **REPROVADA**
**O que está certo:**
- Posse do arquivo na thread de trabalho e lista de produtos filtrada e ordenada.
- Blocos com `include=`, ajustes fixos e ordem por id.
- Deslocamento calculado em float64 antes do float32.
- Cor com duplicação de vértice por material, cinza 204 sem material.
- Normais da face quando o produto vem sem normais.
- Lotes de até 8 MB, `sem_malha` com motivo e regra de ouro garantida.
- Cancelamento em fatias de 50 ms, bloco em andamento descartado e iterador destruído.
- Fila limitada, vetores somente leitura em `dataclass(frozen)`, sem Qt.
- **Nenhum objeto do IfcOpenShell entra em lote:** guid vira bytes e classe vira texto.
- Sem truque contra o R2: não há `setswitchinterval` nem processo.

**Defeitos:**
1. **(Alta, bloqueia) `obter(timeout>0)` pode travar para sempre.** Linha 193: quando o tempo restante chega a 0, `min(FATIA_S, 0.0) or None` vira `None`, e `queue.get(timeout=None)` espera para sempre. Se o trabalhador já terminou, nada mais entra na fila e o resumo, que não passa pela fila, nunca sai.
   - **Reproduzido com o relógio real:** `obter(timeout=1e-9)` com o trabalhador terminado não voltou em 2 s.
   - Com `timeout=0,05`, acontece quando a thread perde a vez por mais que o restante entre o cálculo de `fim` e o `get`, por exemplo durante os 70 a 100 ms de GIL do `initialize()`. Nesse caso trava até o próximo lote, ou para sempre se não houver próximo.
   - O adaptador e o R1 usam `timeout=0.0` e por isso estão salvos. Os testes O1 a O10 usam 0,05: há risco de o CI travar raramente.
   - Correção: trocar `or None` por um piso (`max(..., 0.001)`) ou sair do laço quando o restante for ≤ 0.
2. **(Média) Cancelar depois que a carga já terminou descarta lotes e devolve resumo `"concluido"`.** Quem recebe não sabe que faltaram lotes. Correção: se `cancelar()` descartar algum lote, o resumo entregue diz `"cancelado"`, ou ganha o campo `lotes_descartados`.
3. **(Baixa) `arquivo` fica visível antes do fim**, no `finally` antes de `_pronto.set()`, e também no caminho de erro no meio da carga. O §1.2, item 9, diz "depois do fim, e só depois". Correção: publicar logo antes de `_pronto.set()` e só com estado `"concluido"`.
4. **(Baixa) `initialize()` falso** manda o bloco para `sem_malha` com motivo genérico, sem o texto do erro. Correção: anexar as últimas linhas de `ifcopenshell.get_log()` ao motivo, como o §1.3 pede.
5. **(Baixa) `deslocamento` é o mesmo vetor, gravável, em todos os lotes.** Correção: marcar como somente leitura, como os outros vetores.
6. **(Baixa) `_paleta` e `material_ids` com tamanho errado caem em cinza sem aviso.** Correção: registrar o caso em `mensagens` do resumo.
7. **(Informativo) Thread `daemon=True`:** fechar o programa no meio de uma carga mata a thread dentro do C++. Ver B-5.

**Perguntas do pedido:**
- **Corrida de threads:** só o defeito 1. A ordem "lote antes do resumo" está garantida, porque `_pronto` só é ligado depois do último `put`.
- **Vazamento de objeto do IfcOpenShell na fila:** não há.
- **Caso que o oráculo não pega:** defeitos 1 e 2, além de 1.1-1 e 1.1-2.
- **R2 em xpass:** o `xfail` não estrito está certo; ver 1.1.

### 1.3 Parte B (viewport, adaptador, medição): **REPROVADA**
**O que está certo:**
- `adicionar_lote` custa proporcional ao lote (guarda o lote e soma à caixa). O envio é de 2 buffers `Immutable` por lote, **1 lote por quadro**, e os anteriores nunca são recriados (V2).
- Pipeline novo **sem descarte de faces**, com luz pela regra do §1.4 e transparência desenhada opaca.
- 1 chamada de desenho por lote.
- `limpar()` usa `deleteLater`, o que está correto: conferi que os buffers **não** pertencem ao Python (`createdByPython False`), então não há liberação dupla.
- **Reenvio após troca de contexto funciona:** movi o widget para outra janela, o QRhi mudou e os 3 lotes foram reenviados (`buffers_criados` foi de 6 para 12). A imagem continuou correta.
- Adaptador com `QTimer` de 16 ms, 1 lote por disparo e `cancelar → aguardar → limpar` antes de uma nova carga.
- Os T03 e T04 passam sem alteração.

**Defeitos:**
1. **(Média, bloqueia) `longe` usa a distância ao alvo da câmera, não ao centro da cena.** Depois de arrastar a vista, o alvo sai do centro e o fundo do modelo é cortado.
   - Reproduzido com a caixa do M600: depois de um arrasto de 600 px, `longe` = 170 m e o canto mais distante fica a 195 m.
   - A culpa é em parte do meu texto no §1.4, item 4 ("distância ao centro" era ambíguo). **Emenda:** "distância da câmera ao centro da caixa da cena".
   - Correção: 1 linha em `_render_lotes`.
2. **(Média, bloqueia) Memória no Windows em `medir.py` deve quebrar.** `GetCurrentProcess` devolve o pseudo-handle −1 como inteiro de 64 bits, e `GetProcessMemoryInfo` está sem `argtypes`. O ctypes tenta converter o valor para `int` de 32 bits e deve levantar `ArgumentError`.
   - **Não verificado** (sem Windows aqui), mas a T07 depende disso.
   - Correção: declarar `argtypes` (`HANDLE`, `POINTER(PMC)`, `DWORD`) ou usar `K32GetProcessMemoryInfo` com tipos declarados. Teste mínimo no job `windows`: `pico_memoria_mb() > 0`.
3. **(Baixa) Defeito 7 do lote 4 não corrigido, e herdado pelo pipeline novo.** Na troca de QRhi, os buffers antigos dos lotes só são esquecidos, sem `deleteLater` (vazam, porque o dono é o C++). Também não há `releaseResources()`, e o pipeline não é refeito se o alvo mudar com o mesmo QRhi. Correção: em `initialize()`, chamar `_soltar(e)` antes de zerar e implementar `releaseResources()`.
4. **(Baixa) O adaptador ignora o retorno de `aguardar(5 s)`.** Se a thread velha não terminar, duas cargas rodam juntas. Correção: se `aguardar` der False, não começar a nova carga e avisar (sinal de erro).
5. **(Baixa) Sem cancelamento ao fechar a janela.** Correção: ligar `QApplication.aboutToQuit` a `adaptador.cancelar()`.
6. **(Baixa) O README não lista `malha.vert`/`malha.frag` no comando de refazer os `.qsb`.**
7. **(Processo) O diff tem ~418 linhas** (421 − 3 do `conftest.py`, que veio do merge do PR 17 e está fora dos arquivos permitidos da parte; some quando o PR 17 entrar no `main` antes). Ver a pergunta ao PO.
8. **(Processo) Não existe teste do `AdaptadorCarga`:** o R1b usa um consumidor próprio. Pedir no cartão de correção um teste offscreen simples: `abrir` M600, o laço roda até `terminou`, depois `estatisticas()["triangulos"] == 7200` com um viewport falso (sem tela).

**O relatório mede o que o §1.6 pediu?** Sim:
- tempo de abrir com o primeiro lote visível;
- pico de memória;
- atraso máximo e p95;
- 1, 4 e o padrão de threads; blocos 0, 1000 e 4000;
- número de núcleos;
- as três ressalvas;
- R1 local.

Ressalvas:
- (a) a primeira amostra é descartada (ver 1.1-1);
- (b) cada linha é **uma** execução;
- (c) só 1 linha é com placa real; as outras usam llvmpipe, que **disputa as CPUs** com o carregador.

**As metas do portão da S03 foram atingidas?** As exigências **da T05** (critério 10) sim: 13,5 s < 60 s, 833 MB < 6 GB, 118 ms ≤ 200 ms, p95 9,8 ms ≤ 33 ms, na máquina do PO com placa real. **O portão da S03, não está decidido:**
- pela ressalva 1 do §1.6, o "abrir < 60 s" sai da T07 com o IFC real;
- os 60 FPS são indicativos: travados pela sincronia vertical, numa janela de 640x480, com caixas simples;
- nada foi medido no Windows.

**O líder deve corrigir a frase "metas do portão atingidas"** no `LOG.md` (linha da T05) e no `BOARD.md` (S03) para "metas da T05 atingidas; portão depende da T07".

**Dúvidas de política:**
- (a) **1 thread em 66 s: manter assim, só relatar.** O §1.6 não exige nada para 1 thread. A diferença para os 53 s do lote 4 é coerente com o llvmpipe usando os mesmos núcleos. Fica o risco R9: a T07 deve medir numa máquina de 4 núcleos ou na VM Windows.
- (b) **Bloco 0 reprova de propósito e bloco 1000 dá p95 de 72,7 ms: só registrar.** A hipótese mais provável para o bloco 1000 (não verificada) é que o desenho por software de quase 1 milhão de triângulos, a cada um dos 84 lotes, roda na thread da interface (cerca de 60 ms por quadro no llvmpipe). Com placa real deve cair. 4000 continua o padrão. A T07 repete o bloco 1000 com placa real.

### 1.4 O que vira cartão de correção
- **F0-S03-T05-C1 (T3, sonnet; arquivos: `carregador.py` e `prototypes/viewport_qrhi/`; diff estimado < 80 linhas):** A-1, A-2, A-3, A-4, A-5, B-1, B-2, B-3, B-4, B-5, B-6, B-8, mais a parte de `medir.py` em 1.1-1. A-6 é opcional.
- **F0-S03-T05-P0b (autor do oráculo; arquivos: os três testes):** 1.1, itens 1 a 6.
- Ordem: P0b e C1 nos mesmos ramos empilhados. Re-revisão opus **só dos diffs de correção**: 1 item curto num lote futuro, que pode ir junto com outro módulo do viewport.
- **Cartão novo, fora da T05: F0-S0x "localidade numérica no processo do programa" (T3, porque mexe em gravação IFC).**
  - Reproduzido: com `LANG=pt_BR.UTF-8`, depois de criar o `QApplication`, o IfcOpenShell grava `IFCEXTRUDEDAREASOLID(#19,#23,#18,2799,9999999999995.)`. Isso é STEP inválido.
  - Ao reabrir esse arquivo, o carregador dá "concluido" com 6 de 6 produtos em `sem_malha`. A regra de ouro segura e nada some em silêncio, mas o arquivo está estragado.
  - O PR 17 (`LC_ALL=C` no `conftest.py`) só esconde o problema nos testes. A leitura não é afetada: conferi que um IFC correto abre igual em pt_BR.
  - Correção provável: forçar `LC_NUMERIC=C` no processo do app (antes e depois de criar o `QApplication`), mais um teste que grava em pt_BR e confere que não há vírgula decimal.
  - Precisa entrar antes de qualquer gravação de IFC pelo programa (S05).

## 2. Item 2: amostra de T06 e T25

### 2.1 T06 (seleção por clique): **APROVADA** contra o próprio cartão
- Testes passam (sem tela 6 e 2 pulos; Xvfb 7 e 1 pulo). O README registra mediana de 5,6 ms e máximo de 14,9 ms no modelo de 1 milhão (meta: 100 ms).
- **Escala:** as caixas são testadas de uma vez em numpy (83 mil caixas, poucos milissegundos), e depois os candidatos são ordenados com parada antecipada. No modelo sintético isso escala bem, porque cada parede é a própria caixa.
  - **Pior caso não medido:** um raio que atravessa muitas caixas sem acertar triângulo faz um laço em Python por candidato, cerca de 20 µs cada; dezenas de milhares de candidatos chegariam a segundos. Exemplos: caixas grandes de `IfcSpace`, lajes com vazios, paredes em L.
  - A T07, ou o cartão de integração, deve medir com o IFC real.
- **Risco com a malha em lotes da T05 (vira cartão de integração, T2):**
  1. No modo de lotes, `pick` cai na malha do cubo (`_selecao` é `None`), então o clique não seleciona nada que esteja na tela.
  2. `malha_de_ifc` usa o iterador padrão, que devolve `IfcOpeningElement` e `IfcSpace`: um clique dentro de um cômodo selecionaria o espaço.
  3. Usa `guid` como id; o contrato da T05 é `id_step`, mais `guid`.
  4. Usa float32 em coordenadas de mundo, sem deslocamento: em modelo georreferenciado (coordenadas na casa dos milhões) a precisão cai para a casa dos decímetros.
  5. Duplica a malha (36 MB a mais com 1 milhão de triângulos).
  - **Correção:** construir a estrutura de seleção a partir de `lote.objetos` (caixas prontas), `vertices["pos"]` e `indices` de cada lote, no espaço do lote, como o §1.4 previa. Destaque pela faixa `primeiro_indice/n_indices`.

### 2.2 T25 (desenho no CI): **REPROVADA** (falta evidência registrada; o passo em si está correto)
- O relatório `docs/state/arquivo/F0-S03/F0-S03-ci-desenho.md` no `main` ainda diz **"passo escrito, ainda não executado"**. O `LOG.md` não tem linha da T25, e não há número de execução, aviso do CI nem PNG registrado. Sem rede, não consigo conferir. **A conclusão "Windows desenhou com WARP, Linux com Mesa" não está sustentada no repositório.** O critério 1 do cartão (resultado por sistema) não está cumprido no papel.
- **"≥ 3 cores" é prova fraca.** Um quadro com fundo e duas cores de lixo passaria. Pedir:
  - (a) fração de pixels fora do fundo entre 5 % e 95 % e pixel central diferente do fundo, como no V1;
  - (b) imprimir `rhi.driverInfo()` (nome do dispositivo), porque `backendName()` diz "D3D11" ou "OpenGL", mas não diz se é WARP ("Microsoft Basic Render Driver") ou llvmpipe.
- **WARP:** `QSG_RHI_PREFER_SOFTWARE_RENDERER` e `QSG_RHI_BACKEND` são variáveis do Qt Quick; não há garantia de que o `QRhiWidget` as respeite. Num runner sem GPU, o D3D11 padrão provavelmente já cai no adaptador WARP, então "desenhou" deve ser verdade, mas **só o `driverInfo` prova qual adaptador foi usado**.
- **Mesa no Linux:** o passo pode rodar `sudo apt-get install` no runner. O lote 4 tinha dito que isso pedia o ok do PO, e não achei esse ok em `PO.md`. É uma instalação só no runner, descartável, e o cartão permite. Registrar o ok, ou confirmar que o runner já tem o Xvfb e que o `apt-get` não rodou.
- O passo só desenha **o cubo da T03**, não o pipeline de malha da T05 (`UNormByte4`, HLSL de `malha.*`). Acrescentar `tests/test_viewport_malha.py` ao mesmo passo informativo (V1 a V4), com `OBIM_EXIGIR_DESENHO=1`.
- **Correção (T2, cartão F0-S03-T25-C1):** registrar o resultado real (execução, aviso, `driverInfo`, PNG) no relatório e no LOG; reforçar o critério; incluir V1 a V4. Quando o passo ficar estável por 5 execuções, perguntar ao PO se ele vira bloqueante no Windows.

## 3. Para o líder
1. Nada entra no `main` sem os cartões C1 e P0b, a re-revisão opus deles e o seu ok.
2. Corrigir no LOG e no BOARD "metas do portão atingidas" para "metas da T05 atingidas; portão = T07".
3. Abrir os cartões T05-C1, T05-P0b, a integração da seleção com os lotes (T06 × T05), T25-C1 e o da localidade numérica (T3).
4. O BOARD diz "T25 feita": mudar para "passo informativo no main; resultado a registrar".
5. Este arquivo foi escrito **sem commit** na pasta principal (ramo `main`, árvore limpa antes). Mover para um ramo de trabalho antes de commitar.

## 4. Perguntas ao PO
1. **Limite de 400 linhas.** A Parte 0 tem 711 linhas de teste e a Parte B cerca de 418 (das quais 33 são o relatório). Dividir a Parte 0 por arquivo não resolve, porque um único arquivo já tem 402 linhas, e o oráculo foi pensado para ser congelado inteiro.
   - **Recomendo aceitar como exceção registrada no LOG:** "oráculo congelado da T05 e relatório de medição da Parte B fora do limite".
   - Alternativa: dividir a Parte 0 em 3 PRs e tirar o `medir.py` e o relatório da Parte B para um PR próprio. Isso custa mais uma rodada sem ganho de qualidade.
2. **Localidade numérica (IFC gravado com vírgula em pt_BR).** Abrir agora um cartão T3 para isso, antes da S05? **Recomendo sim.** É barato, e o risco atinge exatamente a promessa de "IFC limpo".
