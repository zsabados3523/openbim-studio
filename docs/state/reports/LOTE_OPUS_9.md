<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Lote Opus 9: especificação da F0-S04 (ponte Python↔C++, híbrido contra C++ puro)
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-12 · Pedido: `docs/state/LOTE_OPUS_9.md`
- Classe: TA (plano da fatia, esqueletos de ADR) e T3 (especificação da ponte, das threads e dos oráculos).
- Este arquivo **é** a especificação. Os cartões do §4 são abertos pelo líder a partir dele; os esqueletos do §5 viram `docs/adr/ADR-001` e `ADR-004` no último cartão.

## Resumo para o PO
1. **O que a S04 decide:** se o programa pode ser metade Python (janelas, comandos) e metade C++ (desenho 3D, geometria), ou se o núcleo precisa ser todo em C++. É a decisão mais cara do projeto: C++ puro custa de 20% a 40% a mais de calendário.
2. **Boa notícia, medida hoje:** o Python já entrega ao C++ o **endereço do modelo na memória**, por uma função pública do próprio IfcOpenShell. Não é preciso truque nem cópia. Falta provar isso com um módulo C++ nosso, nos dois sistemas (primeiros cartões).
3. **Outra boa notícia:** criar uma parede e gerar o desenho dela leva cerca de **2 milésimos de segundo** pelo Python (a meta é 200). Mil paredes: menos de 3 segundos (a meta é 20). A velocidade de edição não deve ser o problema.
4. **O risco de verdade é outro:** enquanto o Python trabalha num lote em segundo plano, a janela inteira fica parada por até **quase 1 segundo** de cada vez. Testei também um componente feito em C++ colocado dentro da janela Python: **trava do mesmo jeito**. Para o 3D não congelar, ele precisa ser desenhado por uma linha de execução própria do C++, separada da janela. É a maior parte do trabalho da fatia, e tem uma sonda barata antes para confirmar que funciona.
5. **Plano em etapas com parada cedo:** a etapa 1 (4 cartões) responde sozinha à pergunta "o modelo é o mesmo dos dois lados?". Se a resposta for não, paramos ali e levamos a você, sem gastar o resto. A etapa 2 começa por outra sonda de parada (o desenho 3D em linha própria).
6. **Tamanho:** 19 cartões, 3 a 4 lotes de revisão do Opus. Estimativa: 30 a 55 pontos de cota semanal no total (perto de uma semana de cota); em calendário, **2 a 3 semanas**, contando os testes no Windows, as revisões e as suas respostas.
7. **Preciso de duas respostas suas** (§7): como ler a regra "até 3 vezes mais lento", e autorização para acrescentar três pacotes de desenvolvimento ao ambiente.

## 0. Como este lote foi feito
- Lido: os documentos do pedido, `prototypes/cpp_probe*`, a interface de `prototypes/viewport_qrhi/`, `environment.yml`, o CI, os cartões pendentes da S03 (T08-G, T27, T26b) e os cabeçalhos instalados do IfcOpenShell 0.9.0 (`ifcparse/file.h`).
- Executado, tudo no rascunho da sessão e fora do repositório: três sondas em Python sem janela e sem Qt; e uma sonda com janela, **só em tela virtual** (`xvfb-run`, desenho por software), com um módulo C++ mínimo (nanobind + Qt, sem IfcOpenShell) compilado no rascunho. Nada instalado, nenhum commit, nenhum push, nenhum arquivo do PO aberto.
- **Não compilei C++ contra o IfcOpenShell:** o ambiente local não tem os cabeçalhos de `zlib` e `libxml2` (a sonda 3b os instala na hora, no CI), e instalar pede o seu ok.
- Cota: semana em 32% usados no início (68% restantes, acima dos 25% exigidos).

### 0.1 Fatos conferidos no ambiente (linux-64, uma execução, máquina de 16 núcleos)
São indicações para orientar a especificação. **Não são o oráculo** e não fecham meta nenhuma.

| # | Fato | Como vi |
|---|---|---|
| F1 | `ifcopenshell.file` **é** o objeto que embrulha o C++ (`ifcopenshell::file *`), e `f.file_pointer()` devolve o endereço dele, igual a `int(f.this)` | sonda; `file_file_pointer(file self) -> size_t` no módulo |
| F2 | O módulo Python liga nas bibliotecas compartilhadas do pacote (`libifcopenshell.parse.so.0.9`, `.geometry`, `.plugin`), as mesmas que um C++ nosso ligaria | `ldd` |
| F3 | PySide6 liga nas bibliotecas Qt do ambiente (`libQt6Widgets.so.6` em `lib/`): um Qt só é possível. `shiboken6.wrapInstance` existe (é como um componente C++ entra numa janela PySide6) | `ldd`; import |
| F4 | Os cabeçalhos do QRhi estão no `qt6-main` (`QtGui/6.11.2/QtGui/rhi/qrhi.h`, `qrhiwidget.h`, CMake `Qt6GuiPrivate`). Fecha um "não verificado" do ADR-005 §11 no Linux | `find` |
| F5 | nanobind 3.1.0 está no ambiente; **pybind11 não está** | import |
| F6 | Modelo quase vazio, 200 paredes com tipo de 3 camadas: criar 1,0 ms (p95 1,1) + malha 0,6 ms (p95 0,7); editar propriedade 0,08 ms; trocar a geometria e refazer a malha 1,1 ms; 1.000 paredes em 2,7 s; desfazer funciona | sonda |
| F7 | **Lote em thread Python trava a thread principal.** Durante `ifcopenshell.api`: espera mediana 40 ms, p95 214 ms, máxima 228 a 489 ms (ideal 5 ms). Só `create_shape`: 10 ms. Python puro: 10 ms. **Não é o coletor de lixo:** com ele desligado a máxima foi 1.111 ms, e com `gc.freeze()` 495 ms. Sobra chamada longa que segura o bloqueio, ou a própria disputa pelo bloqueio | sondas |
| F8 | O mesmo lote **fatiado na thread principal** (fatias de 8 ms): fatia máxima 17 ms, total 3,9 s | sonda |
| F9 | **Componente C++ na thread da janela trava junto.** Componente Qt em C++ (temporizador de 16 ms e pintura, tudo em C++), embutido por `wrapInstance` numa janela PySide6. Parado: 62 quadros por segundo, intervalo máximo 17 ms. Com o lote `ifcopenshell.api` numa thread Python: **15 quadros por segundo, intervalo máximo de 467 a 990 ms**; com um método de evento da janela escrito em Python: 9 por segundo. Com uma chamada C que segura o bloqueio por 0,75 s: paradas de 0,7 a 0,96 s. Ou seja, no PySide6 a entrega de eventos da thread da janela depende do bloqueio do interpretador, mesmo para componente C++ | sonda em tela virtual |

**Leituras:** F1 torna a ponte simples. F6 engana: está 100 vezes dentro da meta porque o modelo é pequeno e a medição para antes da tela (ADR-005 §6 já alertava para "número bom que não prova nada"); as metas têm de ser medidas com modelo carregado e até o quadro na tela (§2.1). F7 e F9 são o risco central: **não basta escrever a viewport em C++; ela não pode ser desenhada pela thread da janela.** Isso define o §1.4 (regra 5) e a etapa 2.

## 1. Item 1.1: os dois fluxos

### 1.1 O fluxo mínimo, igual nos dois
Roteiro R (os passos são os mesmos em A e em B; cada passo é uma transação):
1. Abrir o modelo de base (§2.1) já com a cena na tela.
2. Criar o tipo de parede `PAR15` com conjunto de 3 camadas (2 cm, 11 cm, 2 cm), uma vez.
3. Criar **200 paredes**, uma por transação: `IfcWall` com GlobalId, tipo atribuído, uso do conjunto de camadas, contida no pavimento, posição própria (grade de 50 por linha, passo de 5 m e 4 m), representação `Body` (sólido extrudado de 4,0 × 0,15 × 2,8 m) e `Axis`. Depois de cada uma, a viewport mostra a parede.
4. Editar as 200: (a) mudar `Name` e `Pset_WallCommon.FireRating`, e o painel de propriedades mostra o valor novo; (b) mudar o comprimento para 5,0 m (troca da representação), e a viewport troca a malha.
5. Lote: criar **1.000 paredes** numa transação só, com a câmera girando sozinha.
6. Desfazer o passo 5 (as 1.000 somem da cena) e refazer.
7. Gravar o IFC.

"Com camadas" quer dizer camadas como **dado** (conjunto de camadas e seu uso), com um sólido só. Geometria por camada e encontros de parede são da F2.

### 1.2 O que é comum e o que é diferente
Para a comparação "até 3 vezes" ser justa e para os cartões caberem em 400 linhas, A e B **compartilham o núcleo C++** e diferem só na camada de edição e na casca da janela.

| Parte | Fluxo A (híbrido) | Fluxo B (C++ puro) |
|---|---|---|
| Núcleo `obimcore` (C++): malha por elemento, cena, viewport QRhi com thread de desenho própria, seleção, relógio de quadros | o mesmo código, carregado como módulo Python | o mesmo código, ligado no executável |
| Edição do modelo | `ifcopenshell.api` (Python) | IfcOpenShell C++ direto (entidades IFC4 montadas à mão) |
| Transações e desfazer | `begin_transaction`/`end_transaction`/`undo` do ifcopenshell-python | lista própria de criados e alterados, o mínimo para o passo 6 |
| Janela e painel de propriedades | PySide6 | Qt Widgets em C++ |
| Onde fica | `prototypes/s04/fluxo_a/` | `prototypes/s04/fluxo_b/` |

Núcleo em `prototypes/s04/obimcore/`. Linhas de código (meta "registrar") contam **por pasta**: núcleo, A e B separados.

**Abrir arquivo grande continua como na S03** (processo separado, `carregador.py`). A S04 trata de **edição dentro do processo**. O núcleo recebe os lotes da abertura pela mesma porta que recebe as malhas das edições.

### 1.3 nanobind ou pybind11: **nanobind**
- Já está no ambiente (3.1.0), tem ficha de licença e sonda feita no Linux (`prototypes/cpp_probe/`, 2,4 s de build). pybind11 exigiria instalar (ok do PO) e repetir ficha e sonda.
- A ponte é estreita (§1.4): poucas funções, endereços e vetores numéricos. Nenhum recurso exclusivo do pybind11 faz falta.
- **Falta provar:** nanobind + OCCT + Qt com o MSVC no Windows (ADR-005 §7.1, prova 7). É o cartão T03.
- **Saída:** se o T03 falhar no Windows por defeito do nanobind (e não do nosso CMake) depois das tentativas de regra, o Opus reespecifica com pybind11 e o PO autoriza a instalação. A interface do §1.4 não muda.

### 1.4 Como o C++ recebe o mesmo `ifcopenshell.file` sem cópia
**Mecanismo.** A função C++ recebe o **objeto Python** do arquivo, chama `file_pointer()` nele e converte o número em `ifcopenshell::file*`. Não depende do interior do SWIG. O tipo é conferido antes (`isinstance` de `ifcopenshell.file`), e número zero é erro.

**Regras de posse e de vida (valem como contrato; o oráculo testa cada uma):**
1. **O Python é o dono.** O C++ pega emprestado só durante a chamada, segurando uma referência ao objeto Python até retornar.
2. **O C++ nunca guarda** o endereço do arquivo nem ponteiros de entidades entre chamadas. O que fica guardado no núcleo é só dado nosso: malhas, caixas e o GlobalId (texto) de cada peça. Nunca id de linha STEP nem `express::base`.
3. **Um escritor por vez.** Quem escreve no modelo é uma thread só (a do comando). O C++ lê o modelo **apenas dentro de uma chamada feita por essa thread**: enquanto a chamada dura, o escritor está parado nela, então ninguém escreve.
4. **Bloqueio do interpretador:** toda função do núcleo que lê o modelo ou gera malha **solta o bloqueio** durante o trabalho pesado e não toca em objeto Python nesse trecho. Entrada e saída convertem dados com o bloqueio.
5. **O desenho tem thread própria, criada e mantida pelo C++** (F9): uma janela Qt nativa do núcleo, desenhada com QRhi por essa thread e embutida na janela principal por contêiner de janela. Ela nunca lê o modelo, nunca chama Python e nunca espera a thread da janela para desenhar. Recebe malhas prontas por uma fila protegida e as envia à placa no próprio quadro. A animação de câmera usada nas medições roda nela. **Esta regra depende da sonda T05**; se a sonda reprovar, vale o risco 4 do §6.
6. Fechar ou destruir o arquivo no Python com malhas dele ainda na cena é permitido: a cena não aponta para o arquivo.
7. **Uma trava do modelo, no lado Python.** O comando a segura da abertura da transação até o retorno de `Cena.atualizar`. Qualquer outra thread Python que leia o modelo (painel de propriedades, seleção) só lê com essa trava; se não conseguir de imediato, mostra o valor anterior e tenta depois. Motivo: quando o C++ solta o bloqueio dentro de `malhas`, outra thread Python pode rodar, e a leitura pelo ifcopenshell não é passiva (há cache de identidade).
8. **Entrada do usuário:** os eventos de mouse e teclado chegam pela thread da janela, que pode ficar parada durante um lote (F9). A thread de desenho mantém o 3D vivo, mas a resposta ao mouse durante o lote é medida à parte (M5b, §2.3) e é assunto do ADR-004.

**Interface mínima do módulo `obimcore`** (nomes em português, como no protótipo; o implementador não acrescenta funções sem voltar ao lote):
| Função | Faz |
|---|---|
| `versao()` | versão e build do IfcOpenShell vistos **na compilação**, mais os do OCCT e do Qt |
| `endereco(arquivo)` | endereço que o C++ enxerga |
| `contar(arquivo, classe)` | contagem por classe, com subtipos; `classe=None` conta tudo |
| `ler_nome(arquivo, guid)` / `definir_nome(arquivo, guid, nome)` | leitura e escrita de um atributo pelo C++ |
| `bibliotecas_carregadas()` | caminhos das bibliotecas do processo cujo nome contém `ifcopenshell`, `TKernel` ou `Qt6Core` (Linux: `/proc/self/maps`; Windows: lista de módulos do processo) |
| `malhas(arquivo, guids)` | malha de cada elemento (posições, índices, cor, caixa), sem bloqueio durante a conta; devolve vetores numpy |
| `Cena.atualizar(arquivo, criados, alterados, apagados)` | gera as malhas dentro do C++ e as põe na fila da viewport; devolve um número de sequência |
| `Cena.adicionar_lote(...)` | porta de entrada dos lotes da abertura (formato do `carregador.py`) |
| `Cena.viewport_ptr()` | endereço do componente Qt (o contêiner da janela de desenho), para `shiboken6.wrapInstance` |
| `Cena.relogio()` | tempos dos quadros apresentados e a sequência incluída em cada um, **registrados no C++** |
| `Cena.selecionar(x, y)` | GlobalId sob o cursor, com precisão de triângulo |

**Como o fluxo A liga as partes:** o comando roda `begin_transaction` … `end_transaction` e chama `Cena.atualizar`. **Cada comando anota ele mesmo** os GlobalIds que criou, alterou e apagou, numa lista guardada ao lado da transação (trocar propriedade ou representação não mexe na entidade da parede, então não dá para deduzir do ifcopenshell). Desfazer e refazer chamam `atualizar` com as mesmas listas trocadas. Tirar essas listas de dentro da transação do ifcopenshell é trabalho da S05, não daqui.

### 1.5 Como isso é provado nos dois sistemas
Casos do oráculo R1 (cartão T02). Todos rodam em `linux` e `windows` do CI, **bloqueando o merge**. Vêm do ADR-005 §7 e §7.1, com os nomes da 0.9.

| Caso | Exige |
|---|---|
| R1-a | `obimcore.versao()` = versão **e build** que o Python informa em execução |
| R1-b | `endereco(f)` = `f.file_pointer()`. Vale por construção; fica como sentinela, **não** como prova |
| R1-c | contagens pelo C++ = pelo Python (paredes e total) em 3 arquivos: IFC2x3, IFC4 e IFC4.3 |
| R1-d | o Python cria um elemento e o C++ conta sem reabrir; o C++ muda um nome e o Python lê o nome novo; o Python desfaz e o C++ vê o desfeito. **Esta é a prova de "mesmo modelo"** |
| R1-e | `bibliotecas_carregadas()`: **um** caminho para cada núcleo (IfcOpenShell `parse` e `geometry`, OCCT `TKernel`, Qt6Core), depois de importar `ifcopenshell`, `PySide6` e `obimcore` nas duas ordens |
| R1-f | R1-c e R1-d 1.000 vezes, fechando e reabrindo: 0 diferenças, 0 quedas; memória do processo não cresce mais de 10% entre a volta 100 e a 1.000 |
| R1-g | posse: fechar e destruir o arquivo no Python antes e depois de chamadas ao C++ e com malhas na cena, 1.000 vezes, em subprocesso; código de saída 0. Passar algo que não é arquivo: erro Python limpo, sem queda |
| R1-h | threads: 4 threads Python chamando `malhas` em arquivos **diferentes** ao mesmo tempo, e uma thread chamando `malhas` enquanto a principal conta tempo; 0 diferenças contra a referência, e a principal não espera mais de 50 ms (prova a regra 4). Mais um caso da regra 7: a principal lê atributos do **mesmo** arquivo, com a trava, enquanto outra thread roda `malhas` em laço, 1.000 voltas: 0 diferenças, 0 quedas |
| R1-i | `malhas` contra `ifcopenshell.geom.create_shape` do Python: mesmo número de triângulos, caixa e volume iguais a 1e-6 relativo, em 200 elementos sorteados com semente fixa de 3 arquivos |
| R1-j | dentro do pacote: R1-a, R1-d, R1-e e R1-i rodam no AppImage e no instalador do Windows (cartão T17) |

## 2. Item 1.2: metas e oráculo

### 2.1 Regras de medição (valem para todas)
- **Modelo de base:** nunca vazio. Oficial: o sintético de 3.000 paredes (`scripts/gerar_modelo_grande.py --paredes 3000`, que gera sempre o mesmo arquivo) já aberto e na tela. Informativo: `corpus/modelo-grande-1m.ifc`. O arquivo real do PO só se ele listar no chat.
- **Ponta a ponta:** o cronômetro começa na chamada do comando e termina no **quadro apresentado** que contém a mudança, lido do relógio do C++ (`Cena.relogio()` casa sequência com quadro). No painel de propriedades, termina quando o texto novo está no componente e o evento de pintura foi processado.
- **Estatística:** 200 repetições; relatar mediana, p95 e máximo. O portão é o p95. As 5 primeiras ficam no conjunto.
- **Mesmo programa de medição nos dois fluxos:** A e B aceitam o mesmo arquivo de roteiro e escrevem o mesmo JSON de resultado (`medicao.json`: um registro por passo, com os tempos brutos). Um script só (`medir_s04.py`) lê os dois e monta a tabela.
- **Sem janela na tela real:** tudo em `xvfb-run` (comando de `docs/dev-setup.md`), desenho por software. Uma execução em tela real só com ok do PO no chat, ao final (§7, nota).

### 2.2 Cada meta de v2/03 virou o quê
| Meta (v2/03) | Medição | Portão | Onde roda |
|---|---|---|---|
| M1. Mesmo modelo sem cópia, nos dois sistemas | R1-a a R1-j (§1.5) | todos passam | CI `linux` e `windows`, bloqueia |
| M2. Criar 1 parede com camadas e atualizar a viewport < 200 ms (p95) | passo 3 do roteiro, ponta a ponta. M2b (acréscimo): passo 4b, trocar a geometria, mesma meta | p95 < 200 ms | CI nos dois (software) e máquina do PO em tela virtual |
| M3. Editar propriedade e refletir na interface < 50 ms | passo 4a, até o painel pintado | p95 < 50 ms | idem |
| M4. Lote de 1.000 paredes < 20 s | passo 5, até o quadro com as 1.000 | < 20 s | idem |
| M5. Viewport não congela em operação Python longa: 20 FPS ou mais | durante o passo 5, com a câmera girando pela **thread de desenho do C++**: quadros apresentados por janela de 1 s e maior intervalo entre quadros, do relógio do C++ | toda janela de 1 s com 20 quadros ou mais **e** maior intervalo < 200 ms | ver §2.3 |
| M6. Híbrido até 3× mais lento que o C++ puro | razão das medianas A÷B em M2, M2b, M3 e M4, mesma máquina, mesma sessão, 3 rodadas alternadas | ver pergunta 1 (§7) | máquina do PO (tela virtual) e CI, informativo no CI |
| M7. Linhas de código e tempo de agente | linhas por pasta (núcleo, A, B), sem comentários e sem linhas vazias, por script; por cartão: sessões, número de retornos FALHA, pontos de cota | registrar | relatório final |

**Saída igual (acréscimo, para o B não ganhar gravando menos):** os IFCs gravados no passo 7 por A e por B têm de ser equivalentes: mesmas contagens por classe; para cada parede, mesmas espessuras de camada, mesmo tipo, mesmo pavimento, e volume e caixa iguais a 1e-6 pelo `ifcopenshell.geom`; os dois passam em `ifcopenshell.validate`. GlobalIds e ids de linha podem diferir.

### 2.3 M5 em detalhe (é o ponto frágil)
- **O que precisa ser verdade:** desenhar um quadro não pode pedir o bloqueio do interpretador **nem passar pela thread da janela** (F9). Por isso viewport, câmera, seleção e relógio ficam no C++, com thread de desenho própria.
- **Três formas de rodar o lote Python, todas medidas** (cartão T15), porque a escolha é do ADR-004:
  1. lote em **thread Python**, viewport com thread de desenho própria (o desenho do §1.4);
  2. lote **fatiado na thread principal** (fatias de 8 ms entre eventos do Qt), mesma viewport;
  3. referência: a forma 1 com a viewport **Python** da S03 (espera-se que reprove; mostra o tamanho do problema).
- **M5b, resposta ao usuário durante o lote (acréscimo; registrar, sem portão):** atraso entre um evento de mouse sintético posto na fila da janela e o seu tratamento, nas formas 1 e 2. É o que o arquiteto sente ao tentar girar o modelo durante uma operação longa; a thread de desenho sozinha não resolve isso (regra 8).
- **Conferências obrigatórias no mesmo cartão:** (i) `QApplication.exec()` do PySide6 solta o bloqueio enquanto espera eventos (medir, não supor); (ii) achar a causa do F7, que **não** é o coletor de lixo: medir por função da API quanto tempo cada chamada segura o bloqueio, testar `sys.setswitchinterval` menor, e dizer se o módulo do IfcOpenShell solta o bloqueio em alguma chamada (ele importa a função para isso); (iii) nenhum método da janela de desenho é sobrescrito em Python; sinais para Python só fora do caminho do quadro.
- **Desenho por software engana o FPS absoluto.** No CI e em tela virtual a cena de M5 é pequena (as paredes do roteiro, janela de 640×480), porque o que se testa é independência do Python, não a placa. Critério no CI: o mesmo de cima **e** maior intervalo durante o lote ≤ 3× o maior intervalo com o programa parado.
- **Número oficial com placa real:** uma execução na máquina Linux do PO, com o modelo de 3.000 paredes, só com o ok dele. Windows: só WARP no CI (a VM do PO não tem placa real; risco já registrado para a S10).

### 2.4 Quem escreve o quê
- **Especificação dos oráculos:** este documento (§1.5, §2.2, §2.3).
- **Oráculos (testes):** subagente sonnet **de oráculo**, diferente do implementador, um cartão por oráculo (T02, T06, T12). Entram atrás de guardas que só **ligam** casos (padrão da T08-0). Marcas de falha esperada são tiradas pelo agente de oráculo, nunca pelo implementador (lição do lote 8 §2.3 item 6).
- **Revisão:** Opus, em lote, de cada oráculo e de cada implementação T3, antes do merge.
- **CI, nos dois sistemas, bloqueando:** compilar o núcleo, o fluxo B e o módulo; R1; saída igual; M2 a M5 em software. A sonda do "teste 2" passa a reprovar (ADR-005 §7.1, prova 10). macOS: compila e roda, não bloqueia.

## 3. Regra de leitura do resultado
- **Híbrido aprovado:** M1 a M5 atingidas nos dois sistemas. M6 conforme a resposta à pergunta 1.
- **M1 reprovada de forma estável** (R1-d, R1-e, R1-f ou R1-g): primeiro o plano B do ADR-005 §10 item 1 (compilar o IfcOpenShell nós mesmos, com ok do PO); se também reprovar, vale v2/03: **C++ puro no núcleo, Python só para plugins e regras**. Parar e levar ao PO.
- **M5 reprovada nas formas 1 e 2:** parar e levar ao PO com opções (por exemplo, comandos de edição em processo separado). Não é automaticamente C++ puro: a regra de v2/03 só manda trocar de stack pela falha de compartilhamento.
- **M2, M3 ou M4 reprovadas:** parar e levar ao PO. Pelos números do F6, é improvável.

## 4. Item 1.3: cartões
Todos com diff de até 400 linhas (arquivos de trava não contam). "Oráculo" = subagente diferente do implementador. P/M/G aqui é o tamanho do **cartão**: P até 150 linhas, M até 300, G perto de 400. O precedente em Python (viewport 420 linhas, câmera 78, seleção 203) mostra que o desenho em C++ não cabe em dois cartões: por isso a etapa 2 tem seis.

### Etapa 1: o modelo é o mesmo dos dois lados? (portão interno)
| ID | Cartão | Classe | Tam. | Depende | Arquivos permitidos | Aceite |
|---|---|---|---|---|---|---|
| S04-T01 | Ambiente de compilação travado | T2 | P | pergunta 2 | `environment.yml`, arquivos de trava linux-64 e win-64, `ci.yml`, `docs/dev-setup.md`, `prototypes/cpp_probe_3b/run.sh` | `zlib`, `libxml2-devel`, `libboost-devel` com versão; build do `ifcopenshell` travado; trava gerada por `conda list --explicit --md5` **em cada sistema, no próprio CI** (sem ferramenta nova) e guardada no repositório; o CI cria o ambiente pela trava; a sonda 3b compila **sem instalar nada na hora**; `Qt6GuiPrivate` achado pelo CMake nos dois sistemas (fecha o F4 no Windows) |
| S04-T02 | Oráculo R1 (R1-a a R1-i) | T3, oráculo | M | T01 | `tests/test_s04_ponte.py`, `tests/s04_aux.py` | casos do §1.5 atrás da guarda "módulo existe"; 3 arquivos de teste gerados por script (2x3, 4, 4.3), sem baixar nada |
| S04-T03 | Módulo `obimcore` mínimo | T3 | M | T02 | `prototypes/s04/obimcore/` (CMake, `ponte.cpp`, `build.sh`), `ci.yml` | funções `versao`, `endereco`, `contar`, `ler_nome`, `definir_nome`, `bibliotecas_carregadas`; R1-a a R1-g verdes em `linux` e `windows`; MSVC em Release; tempos de build limpo e incremental anotados |
| S04-T04 | Malha por elemento no C++ | T3 | M | T03 | `prototypes/s04/obimcore/malha.cpp`, CMake | `malhas(arquivo, guids)` com o bloqueio solto; R1-h e R1-i verdes nos dois; mesma biblioteca de geometria "híbrida" e mesmas opções da S03 |

**Armadilhas conhecidas da etapa 1** (vão para os cartões):
1. `ifcopenshell::file(const char*, bool)` não abre arquivo; usar `std::string` (sonda 3b).
2. As bibliotecas de esquema se registram ao carregar: no Linux, `-Wl,--no-as-needed`. A sonda 3b só liga IFC4 e IFC2x3; o R1-c precisa também de `parse_schema_ifc4x3_add2`. Dentro do módulo Python os esquemas já vêm carregados pelo `ifcopenshell`: importar `ifcopenshell` **antes** de `obimcore`, e o R1-e testa as duas ordens.
3. Windows: gerador do Visual Studio (`-A x64`), modo Release sempre, `Library/lib` do conda no caminho do ligador; nunca o MinGW do runner.
4. Windows: o `.pyd` precisa achar as DLLs do ambiente; a partir do Python 3.8 o `PATH` não vale para isso. Usar `os.add_dll_directory` ou importar `ifcopenshell` e `PySide6` antes. Um erro aqui aparece como "módulo não encontrado", não como DLL faltando.
5. Ligar pelo `IfcOpenShellConfig.cmake` do pacote (ADR-005 §7.1 item 3). Não copiar cabeçalho, não compilar fonte do IfcOpenShell.
6. Localidade: o processo de teste roda com `LC_ALL=C` pelo `conftest.py`; os casos que criam `QApplication` chamam a correção da T26.
7. Cada arquivo C++ que inclui `ifcparse/file.h` custa de 4 a 6 s de compilação (até 19 s no Windows): poucos arquivos incluem esse cabeçalho.

**Fora de escopo da etapa 1:** viewport, Qt Widgets, gravar IFC pelo C++, transações, desempenho.

**Portão interno:** com T03 e T04 verdes nos dois sistemas e revistos (lote 10), M1 está respondida, salvo o pacote (R1-j). Se reprovar, aplica-se o §3 e **nada da etapa 2 começa**.

### Etapa 2: núcleo de desenho em C++
| ID | Cartão | Classe | Tam. | Depende | Arquivos permitidos | Aceite |
|---|---|---|---|---|---|---|
| S04-T05 | **Sonda da thread de desenho** (segundo portão interno) | T3 | P | T01 | `prototypes/s04/sonda_desenho/` (CMake, um `.cpp`, um `.py`), `ci.yml` (passo informativo) | janela Qt nativa desenhada com QRhi por thread do C++ (basta limpar a tela mudando de cor e registrar o tempo de cada quadro), embutida numa janela PySide6; repetir o F9: com o lote `ifcopenshell.api` numa thread Python e com a chamada C de 0,75 s, **maior intervalo entre quadros < 50 ms** em tela virtual no Linux e no desenho por software do Windows (CI); redimensionar, esconder, mostrar e fechar a janela 20 vezes sem queda; relatório curto com os números |
| S04-T06 | Oráculo da viewport C++ e do relógio | T3, oráculo | M | T05 | `tests/test_s04_viewport.py` | em tela virtual: viewport dentro de janela PySide6; imagem com as cores esperadas; um Qt só (R1-e com a janela aberta); `relogio()` crescente e casando sequência com quadro; intervalo máximo com o bloqueio preso (caso do T05); trocar de janela, esconder e destruir sem queda; perda de contexto: a cena volta com os mesmos triângulos e **a mesma câmera**; reaproveita os casos da S03 que se aplicam |
| S04-T07 | Viewport, parte 1: janela de desenho, pipeline e encaixe | T3 | G | T06 | `prototypes/s04/obimcore/viewport.*`, shaders da S03 reutilizados | janela com thread própria (desenho aprovado no T05), pipeline de malha com as cores da S03, `viewport_ptr`, captura de imagem para teste; nenhum método sobrescrito em Python |
| S04-T08 | Viewport, parte 2: cena, fila de lotes, relógio, perda de contexto | T3 | G | T07 | `prototypes/s04/obimcore/cena.*` | `Cena`, `adicionar_lote` (formato do `carregador.py`), `relogio`; envio à placa em fatias por quadro (regra da S03); a cena guarda **uma** cópia compacta de posições e índices no C++ e, depois de perda de contexto, reenvia sozinha |
| S04-T09 | Câmera e substituição de malha | T3 | M | T08 | `prototypes/s04/obimcore/camera.*`, `cena.*` | orbitar, mover, aproximar e enquadrar no C++ (entrada vinda da thread da janela por fila); animação de órbita para as medições; `Cena.atualizar` troca e remove malhas por GlobalId e devolve a sequência |
| S04-T10 | Seleção por triângulo e memória | T3 | M | T08 | `prototypes/s04/obimcore/selecao.*` | `selecionar` com precisão de triângulo em menos de 100 ms no modelo de 1 milhão (caixas por objeto primeiro, triângulos só dos candidatos, sobre a cópia compacta); memória da cópia medida e relatada; casos do oráculo de seleção da S03 valem aqui |

**Armadilhas conhecidas da etapa 2:**
1. Acordar o desenho a partir de outra thread só por fila ou chamada enfileirada do Qt; nunca chamar método de componente Qt direto de outra thread.
2. Criar e destruir os recursos da placa **na thread de desenho**; o fechamento da janela espera essa thread terminar (senão, queda ao sair).
3. QRhi é semi-público: tudo atrás de `viewport.*`, versão do Qt fixa (R13).
4. Contêiner de janela nativa tem limitações conhecidas de empilhamento e foco; os casos "esconder, mostrar, trocar de janela" do T05 e do T06 existem por isso.
5. Windows no CI usa desenho por software (WARP); Linux, tela virtual com Mesa por software. Nada de janela na tela real.
6. O relógio marca o quadro **apresentado** (depois do fim do quadro), não o pedido de desenho.

**Fora de escopo da etapa 2:** materiais e texturas, transparência, planos de corte, culling, níveis de detalhe, snaps.

Sobre os itens herdados da S03 que caem nesta etapa:
- **Seleção por triângulo** (relatório da S03, ponto 3): T10. Alternativa a registrar no ADR-004 se a memória não fechar: seleção por imagem de identificadores desenhada pela placa.
- **Reabertura da janela** (lote 8 §2.3 item 5): com a cópia no C++ (T08), a cena reenvia sozinha depois da perda de contexto, sem reabrir o arquivo e sem mexer na câmera. Os três defeitos listados no lote 8 (câmera, ligação por função anônima, espera de 5 s) deixam de existir no caminho novo; o oráculo T06 cobre os três.
- **Memória final** (relatório da S03, ponto 2): medir de novo o modelo de 1 milhão e, se o PO listar, o arquivo real, agora com a cópia no C++ e sem as cópias do Python (T10). O número entra no ADR-004 e a meta final é proposta ao PO no relatório da fatia. Até lá vale a decisão de 2026-10-12.

### Etapa 3: os dois fluxos e as medições
| ID | Cartão | Classe | Tam. | Depende | Arquivos permitidos | Aceite |
|---|---|---|---|---|---|---|
| S04-T11 | Fluxo A: comandos e janela (PySide6 + `ifcopenshell.api`) | T3 | M | T09 | `prototypes/s04/fluxo_a/` | roteiro R inteiro por arquivo de roteiro; transações do ifcopenshell; trava do modelo (regra 7); lista de GlobalIds por comando; `Cena.atualizar` depois de cada transação, de desfazer e de refazer; grava `medicao.json`; localidade numérica "C" depois de criar a aplicação (lição da T26) |
| S04-T12 | Oráculo das metas e da saída igual | T3, oráculo | M | T09 | `tests/test_s04_metas.py`, `prototypes/s04/medir_s04.py` | lê `medicao.json` de A e de B; aplica §2.2 e §2.3; compara os IFCs do passo 7; conta linhas por pasta |
| S04-T13 | Fluxo B, parte 1: paredes em C++ | T3 | G | T04 | `prototypes/s04/fluxo_b/paredes.*`, teste | biblioteca que cria tipo, camadas, parede, posição e representações e edita nome, propriedade e comprimento, com lista para desfazer; IFC gravado passa na "saída igual" contra um IFC de referência feito pelo Python |
| S04-T14 | Fluxo B, parte 2: janela Qt Widgets e medição | T3 | M | T09, T13 | `prototypes/s04/fluxo_b/main.cpp`, `janela.*` | mesmo roteiro, mesmo `medicao.json`; lote em thread C++ |
| S04-T15 | Threads e bloqueio do interpretador | T3 | M | T11, T12 | `prototypes/s04/fluxo_a/lote.py`, `docs/state/reports/F0-S04-threads.md` | as 3 formas do §2.3 medidas; M5b; conferências (i), (ii), (iii) respondidas com número; recomendação para o ADR-004 |

**Armadilhas conhecidas da etapa 3:** (1) no C++ não existe a camada `api`: o T13 monta as entidades IFC4 à mão, e a "saída igual" é o que impede esquecer relação ou unidade; (2) GlobalIds novos em toda parede, nunca reaproveitados; (3) gravar número sempre com ponto decimal (T26); (4) A e B medem com o **mesmo** relógio do núcleo; (5) o lote do fluxo A não lê o painel nem toca em componente Qt fora da thread da janela.
**Fora de escopo da etapa 3:** encontros de parede, aberturas, geometria por camada, oplog próprio, gravação atômica do par, arquivo `.obim` (tudo da S05 ou da F2).

### Etapa 4: herança da S03, pacote e fecho
| ID | Cartão | Classe | Tam. | Depende | Arquivos permitidos | Aceite |
|---|---|---|---|---|---|---|
| S04-T16 | Abertura: orçamento de peças lentas e modo isolado mais barato | T3 (oráculo por subagente) | M | — (independente; pode andar em paralelo com a etapa 1) | `prototypes/viewport_qrhi/carregador.py`, `processo_malhas.py`; testes pelo agente de oráculo | (a) orçamento total: ao passar de N peças condenadas **ou** de T segundos gastos em esperas (padrão 20 peças ou 120 s), a carga para de usar o modo isolado: dali em diante, quando um bloco estoura o limite, todas as peças ainda pendentes **daquele bloco** viram caixa de uma vez (os blocos seguintes continuam no modo normal), e o resumo avisa em português simples quantas foram; a pergunta ao usuário fica para a F1; (b) modo isolado com **um** iterador para o bloco e confirmação sozinha só da peça acusada (opção ii do lote 7), com o custo por peça medido: alvo de até 2× o modo normal (hoje 30 a 55 ms contra 2 a 18 ms); P13, P14 e P18 continuam verdes; (c) inclui o cartão **S03-T08-G** já aberto |
| S04-T17 | Módulo dentro do AppImage e do instalador | T2, revisão Opus obrigatória | M | T04 | `packaging/`, `ci.yml` | R1-j nos dois pacotes; runtime do Visual C++ do instalador igual ou mais novo que o do compilador; `multiprocessing.freeze_support()` nos pontos de entrada (lote 7 §1.3 item 5); tamanho dos pacotes e inventário de licenças refeitos |
| S04-T18 | Tempos de build com C++ e relatório da fatia | T1 | P | todos | `docs/state/reports/F0-S04.md`, `docs/acceptance/` | tabela meta × medido por sistema; build limpo e incremental (ADR-005 prova 9; o incremental do Windows volta ao PO se seguir acima de 10 min); M7; vídeo ou capturas do roteiro; roteiro de aceite do PO |
| S04-T19 | ADR-001 e ADR-004 com números | TA | — | T18 | `docs/adr/ADR-001-*.md`, `ADR-004-*.md` | Opus, em lote; resumo de 5 linhas para o PO |

Sobre o T16(a): o valor padrão do orçamento é proposta minha; o PO vê o efeito no relatório da fatia e pode mudar. A regra de ouro da S03 continua (toda peça termina com malha, com caixa ou em "sem malha" com motivo).

Já abertos e independentes da S04: **S03-T27** (teste da reabertura no passo de desenho do CI) e **S03-T26b** (feito, PR 42). O T27 continua útil enquanto a viewport Python existir.

### 4.1 Ordem e lotes do Opus
```
T01 → T02 → T03 → T04 ───────────────(lote 10: portão interno)
T01 → T05 (sonda do desenho) ────────(lote 10)
T16 (em paralelo) ───────────────────(lote 10)
T06 → T07 → T08 → T09, T10 ──────────(lote 11)
T13 (depois do T04) ─────────────────(lote 11 ou 12)
T11, T12 → T14 → T15 ────────────────(lote 12)
T17 (depois do T04) ─────────────────(lote 12)
T18 → T19 ───────────────────────────(lote 12 ou 13)
```
- **Lote 10:** T02, T03, T04, T05, T16 (com T08-G). Responde M1 e diz se a thread de desenho própria funciona. É o ponto de parada barato.
- **Lote 11:** T06 a T10 (se passar de 4 itens grandes, dividir em dois lotes do mesmo módulo).
- **Lote 12:** T11 a T15 e T17; o T19 no mesmo lote se a cota permitir, senão lote 13.
- Um implementador por vez. T16 e T13 são os únicos candidatos a segundo implementador em paralelo, e só com a janela de 5 h abaixo de 60%.
- Todo PR de T3 aponta para o `main` (para o CI rodar nos dois sistemas) e espera o lote e o ok do PO. Arquivos de estado só em PR de estado.

## 5. Item 1.4: esqueletos dos ADRs
Formato de v2/03 §3: contexto, opções, números medidos, decisão, consequências, o que nos faria mudar de ideia, resumo de 5 linhas.

### 5.1 ADR-001: stack (híbrido ou C++ puro), ponte, pythonocc, Rust
| Pergunta | Número que entra | De onde vem |
|---|---|---|
| O modelo é o mesmo dos dois lados, sem cópia, nos dois sistemas e dentro dos pacotes? | R1-a a R1-j: passa ou não, por sistema; voltas sem queda | T03, T04, T17 |
| Quantas cópias de cada núcleo no processo? | 1 ou mais, por sistema | R1-e |
| O híbrido atinge as metas absolutas? | M2, M2b, M3, M4: mediana, p95, máximo, por sistema | T12 |
| A viewport fica viva durante uma operação Python longa? | M5 e M5b nas 3 formas | T15 |
| Quanto mais lento que o C++ puro? | razão A÷B por meta | T12 |
| Quanto custa fazer cada um? | linhas por pasta (núcleo, A, B); sessões, falhas e cota por cartão | T18 |
| Quanto custa a ponte por chamada? | tempo de `contar` e de `malhas` por elemento contra o Python puro e o C++ puro (ADR-005 prova 5) | T04, T12 |
| nanobind serviu nos dois compiladores? | build limpo e incremental; defeitos achados | T03 |
| Quanto custa compilar? | limpo e incremental por sistema, com o núcleo inteiro | T18 |
| Papel do pythonocc | fora do ambiente base e fora da ponte (v2/02 §5); confirmar que nada na S04 precisou dele | T18 |
| Rust | não, salvo o gatilho de v2/03 (oplog da S05 mais de 10× fora da meta) | S05 |

Opções a comparar: (1) híbrido como em v2/02; (2) C++ puro no núcleo, Python só para plugins e regras; (3) híbrido com os comandos de edição em processo separado (só se M5 falhar).
O que nos faria mudar de ideia: pacote novo do IfcOpenShell com biblioteca estática ou sem `file_pointer`; queda intermitente em R1-f ou R1-g; M5 só atingível com a forma 2 e fatias que deixem os comandos lentos; M5b mostrando a janela surda por mais de 1 s em operações comuns.

### 5.2 ADR-004: threads (interface, geometria, entrada e saída, bloqueio do interpretador)
| Pergunta | Número que entra | De onde vem |
|---|---|---|
| Quem pode escrever no modelo e quando o C++ pode ler? | regras 1 a 8 do §1.4, confirmadas ou corrigidas; R1-g e R1-h | T03, T04 |
| Onde roda o desenho? | F9 (componente na thread da janela: paradas de até 0,99 s) contra a thread própria: maior intervalo entre quadros parado e com o bloqueio preso, por sistema | T05, T07 |
| Em que thread roda um comando Python longo? | M5 nas 3 formas: quadros por segundo mínimos e maior intervalo | T15 |
| O usuário consegue mexer na tela durante o lote? | M5b: atraso de evento nas formas 1 e 2 | T15 |
| O que causa as paradas vistas no F7? | tempo de bloqueio por função da API; efeito do intervalo de troca | T15 |
| `exec()` do PySide6 solta o bloqueio? | sim ou não, medido | T15 |
| Abertura: processo separado continua? | números da S03, mais o custo do modo isolado novo e o orçamento | T16 |
| Seleção: de onde vem o triângulo? | tempo de clique e memória da cópia no C++ | T10 |
| Memória final | pico por processo no modelo de 1 milhão e, se listado, no arquivo real | T10 |
| Elemento muito pesado ainda para a janela? (decisão do PO pós-lote 4) | atraso máximo ao editar a parede de 150 aberturas, com a malha feita fora do bloqueio | T15 |
| Perda de contexto gráfico | reenvio pela cena: tempo e câmera preservada | T06, T08 |

## 6. Item 1.5: riscos, saídas e cota
| # | Risco | Sinal | Saída |
|---|---|---|---|
| 1 | Modelo não é o mesmo, ou há duas cópias de um núcleo | R1-d ou R1-e reprovam | §3: plano B do ADR-005 (compilar o IfcOpenShell), depois C++ puro. Parar e levar ao PO |
| 2 | Funciona, mas cai de vez em quando | R1-f ou R1-g com falha intermitente | conta como "não estável" de v2/03: mesmo caminho do risco 1. Não repetir até passar |
| 3 | nanobind não compila com o MSVC | T03 vermelho no `windows` | até 5 tentativas (regra do CLAUDE.md); depois pybind11 com reespecificação e ok do PO |
| 4 | Thread de desenho própria não funciona embutida no PySide6 (em algum dos dois sistemas) | T05 reprova | plano B: componente C++ na thread da janela e **todo lote fatiado** (forma 2; o F8 indica fatia máxima de 17 ms). Isso atende o número de M5 mas não o "bloqueio liberado" ao pé da letra, e qualquer operação Python que não se fatie trava a tela: **levar ao PO antes de seguir**, com a opção 3 do ADR-001 ao lado |
| 5 | M5 reprova mesmo com thread de desenho | T15 | forma 2; se as duas falharem, opção 3 do ADR-001, ao PO |
| 6 | Fluxo B consome a cota (C++ escrito à mão é longo) | T13 com 2 falhas | reduzir B ao mínimo que mede M2, M3 e M4 (sem desfazer e sem painel completo) e registrar no relatório que a contagem de linhas de B ficou subestimada |
| 7 | Build do Windows fica longo demais com C++ | T18 | cache do ambiente pronto e instalador só quando o pacote muda (ADR-005 §10 item 7); o PO decide |
| 8 | Poda do pacote tira algo que a geometria usa | R1-j reprova em R1-i | o pacote volta, com inventário e tamanho novos (ADR-005 §10 item 8) |
| 9 | Placa real no Windows continua sem medição | — | já aceito pelo PO; segue para a S10 |

**Cota.** Base medida: a sessão 6b (fecho da S03: cerca de 12 subagentes e dois lotes Opus) custou 8 pontos da semana, ou seja, perto de meio ponto por cartão pequeno de Python e 2 pontos por lote. Na S04 multiplico por 2 a 3: é C++ (mais tentativas de compilação), cada tentativa espera cerca de 19 minutos do Windows no CI, e todos os cartões são maiores que os da T08. Faixas em pontos da cota semanal:

| Tamanho do cartão | Custo estimado | Cartões |
|---|---|---|
| P | 0,5 a 1 | T01, T05, T18 |
| M | 1 a 2 | T02, T03, T04, T06, T09, T10, T11, T12, T14, T15, T16, T17 |
| G | 2 a 3 | T07, T08, T13 |
| Lote Opus | 2 a 4 cada | lotes 10, 11, 12 (e 13, se preciso); T19 dentro de um deles |

Soma: cerca de 30 a 55 pontos, **perto de uma semana de cota** (o orçamento semanal é 70 de sonnet e 20 de Opus). Em calendário, 2 a 3 semanas, porque os lotes do Opus dependem de você abrir a sessão, o CI do Windows é lento e há duas paradas de decisão. Só a etapa 1 com a sonda T05 e o lote 10: 8 a 14 pontos. É estimativa sem histórico de C++ neste projeto; o custo real por cartão entra no M7 e na calibração da S10.

## 7. Perguntas ao PO
**1. Como ler a regra "até 3 vezes mais lento que o C++ puro"?** Os documentos se contradizem: a tabela de v2/03 põe "até 3× e dentro das metas absolutas" como meta para aprovar o híbrido, e a regra de decisão logo abaixo diz que o híbrido é aprovado se atingir as metas absolutas, **mesmo que seja mais lento**. Exemplo do conflito: parede em 10 ms no híbrido e 2 ms no C++ (5 vezes mais lento, mas 20 vezes dentro da meta de 200 ms).
- **Recomendo:** o portão são as metas absolutas; o "3×" vira número de acompanhamento, registrado no ADR-001, que só pesa na decisão se alguma meta absoluta ficar com menos de 2× de folga.

**2. Posso acrescentar ao ambiente de desenvolvimento os arquivos de desenvolvimento de três bibliotecas que já usamos (`zlib`, `libxml2-devel`, `libboost-devel`), do mesmo canal conda-forge, e guardar a lista travada de pacotes dos dois sistemas?** Sem eles o C++ não compila na sua máquina; hoje o CI os instala na hora, sem versão fixa. Não entra programa novo nem muda o instalador.
- **Recomendo sim.**

Nota, sem pergunta agora: ao final da fatia vou pedir **uma** execução na tela real do Linux para o número oficial de quadros por segundo (como na S03). Antes disso, tudo roda em tela virtual.

## 8. Para o líder
1. Registrar as respostas do PO em `PO.md`; abrir os cartões do §4 a partir deste arquivo (objetivo, arquivos permitidos, aceite, armadilhas e fora de escopo já estão aqui; "ler antes" = este arquivo, mais ADR-005 §7.1 para a etapa 1 e `LOTE_OPUS_8.md` §2.3 para o T16); começar por T01 e, em paralelo se a janela permitir, T16.
2. `BOARD.md`: S04 com 19 cartões, 3 a 4 lotes previstos; T08-G passa a fazer parte do S04-T16.
3. Regra para todos os cartões: nenhum teste gráfico na tela real (`xvfb-run` de `docs/dev-setup.md`); PR de T3 direto para o `main`, sem pilha, para o CI rodar no Windows.
4. Os números do §0.1 são sondas de uma execução. Não citar como resultado de meta. As sondas ficaram no rascunho da sessão e não entram no repositório; o T05 e o T15 as refazem como código do projeto.
5. Este arquivo foi escrito **sem commit**, na pasta principal, no ramo `estado-s03-relatorio` (árvore limpa antes).

## 9. Depois do relatório (2026-10-12)
O PO respondeu no chat **"pode seguir com suas recomendações"**. Ficam decididas as duas perguntas do §7:
1. **Regra do "3 vezes":** o portão do híbrido são as metas absolutas (M1 a M5). A razão contra o C++ puro (M6) é número de acompanhamento, registrado no ADR-001; só pesa na decisão se alguma meta absoluta ficar com menos de 2× de folga.
2. **Ambiente:** autorizado acrescentar `zlib`, `libxml2-devel` e `libboost-devel` (conda-forge) ao ambiente de desenvolvimento e guardar a lista travada de pacotes dos dois sistemas. Vale para esses três pacotes, dentro do cartão S04-T01; qualquer outro pacote pede novo ok.

Nada foi instalado nesta sessão: a instalação é feita pelo S04-T01. Falta ao líder: copiar as duas respostas para `PO.md`, atualizar LOG, BOARD e QUEUE_OPUS, e abrir os cartões (§8). Este arquivo continua sem commit.
