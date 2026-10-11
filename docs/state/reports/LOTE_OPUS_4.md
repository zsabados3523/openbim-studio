# Lote Opus 4: especificação da S03-T05 e amostra de revisão do viewport (T03, T04)
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-11 · Pedido: commit `81c8afb`
- Itens: 1) especificação e oráculo da S03-T05 (T3) · 2) revisão por amostragem das T2 S03-T03 e S03-T04
- Cartão produzido: `docs/state/cards/F0-S03-T05.md`

## Resumo para o PO
1. **A S03 fica em Python.** O gerador de malhas do IfcOpenShell já é C++ com várias threads por dentro; chamado pelo Python ele abriu o modelo de 1 milhão de triângulos em **11 a 13 s** (meta: 60 s) usando **menos de 1 GB** (meta: 6 GB). Não precisa de módulo C++ nosso agora, e o ADR-005 proíbe começar algo que dependa da ponte antes das provas da S04.
2. **Há um limite que o Python não resolve:** enquanto o IfcOpenShell calcula um elemento, a janela fica parada. Em elementos simples isso é imperceptível (até 17 ms). Em um elemento pesado a janela para pelo tempo dele: medi 0,2 s numa parede com 150 aberturas e 0,7 s com 500. A T05 **mede e mostra** isso; quem resolve é a S04 (ponte C++) e o ADR-004 (threads).
3. O contrato de dados entre "quem gera a malha" e "quem desenha" foi escrito de modo que a S04 possa trocar o gerador por C++ sem mexer no viewport, e comparar os dois com os mesmos números.
4. O oráculo tem testes com números fixos: contagem de triângulos, mesmo resultado com 1 e N threads, cancelamento, erros, e atraso máximo da janela (200 ms; 33 ms em 95% do tempo).
5. **Revisão de T03 e T04: aprovadas.** O código cumpre os cartões. Mas a interface atual do viewport **não aguenta** a T05 nem a T06 como está; a especificação diz o que acrescentar (nada é removido).
6. Achado mais importante da revisão: **o desenho 3D nunca roda no CI** (os testes pulam nos três sistemas). Hoje não há nenhuma prova de que desenha no Windows, que é meta do portão. Recomendo um cartão próprio para isso.
7. Duas perguntas ao PO no fim (seção 5), as duas com recomendação.

## 0. Como este lote foi feito (limites e ressalvas)
- Lido: só a lista do pedido. **Uma exceção, declarada:** consultei com `grep` as linhas do `pytest` em `.github/workflows/ci.yml` para saber se o CI desenha (não desenha: usa `QT_QPA_PLATFORM=offscreen` nos três sistemas). **Segunda exceção, para não aprovar a T03 no escuro:** `git log --stat` dos commits da T03 e da T04 e um `grep` por "Vulkan" em `LOG.md` e `BOARD.md`, para achar o relato pedido no critério 4 da T03. Sem rede.
- **Medições:** feitas por mim com scripts descartáveis (fora do repositório, porque só posso criar dois arquivos). Ambiente: máquina do PO, Linux, 16 CPUs lógicas, ifcopenshell 0.9.0, Python 3.12.15, PySide6 6.11.2. A sonda de atraso era a thread principal dormindo 2 ms e medindo quanto acordou atrasada (sem Qt). **Valem como ordem de grandeza; a T05 tem de repetir tudo com script versionado.** Nada foi medido no Windows.
- Não li `F0-S03-plano.md` nem o resto de `BOARD.md` e `LOG.md` (fora do contexto fechado). Onde isso importa, está marcado "confirmar com o líder".

## 1. Especificação T05

### 1.1 Decisão: Python com `ifcopenshell.geom.iterator`, sem C++ nosso na S03
**Decisão.** A T05 usa `ifcopenshell.geom.iterator(settings, arquivo, num_threads, include=...)` dentro de **uma thread de trabalho Python**. Nenhum módulo C++ próprio, nenhum processo separado.

**Por quê.**
1. **Regra já escrita:** ADR-005 §7.1: "Enquanto isso não passar, nenhuma tarefa que dependa da ponte C++/Python começa" (provas 1 a 3 da S04). Um módulo nanobind que recebe o modelo é exatamente isso.
2. **As metas do portão são atingidas com folga** no modelo sintético (tabela abaixo).
3. **Não contamina a S04:** a T05 não compartilha o modelo entre Python e C++, não mede "custo da ponte" e entrega um contrato de dados (1.3) que um gerador C++ pode produzir igual. A S04 ganha uma linha de base "Python puro" comparável.
4. `v2/03` S03 diz "tesselação via IfcOpenShell C++ (iterador de geometria multithread)". O iterador chamado pelo Python **é** esse código C++. Leio a frase como atendida; como é interpretação de documento, vai como pergunta ao PO (seção 5).

**Medido** (`corpus/modelo-grande-1m.ifc`, 74 MB, 83.334 paredes, 1.000.008 triângulos):

| Configuração | Tempo total (abrir + malhas) | Pico de memória | Maior parada da thread principal |
|---|---|---|---|
| 1 thread, iterador único | 53,0 s | 812 MB | 84 ms no `initialize`; ~0,4 s ao destruir o iterador |
| 4 threads, iterador único | ~20 s | 837 MB | 240 ms ao destruir o iterador |
| 8 threads, iterador único | 11,1 s | 854 a 892 MB | 104 ms no `initialize`; **395 ms ao destruir o iterador** |
| 16 threads, iterador único | ~9,5 s | 875 MB | 304 ms ao destruir |
| 8 threads, blocos de 4.000 produtos (`include=`) | 12,9 s | **485 MB** | **93 ms** (`initialize` de cada bloco); destruir: 17 ms |
| 8 threads, blocos de 1.000 | 16,8 s | 465 MB | 86 ms |
| 1 thread, blocos de 4.000 | 54,3 s | 461 MB | 72 ms |

Outros fatos medidos, que a especificação usa:
- **Abrir o arquivo** (`ifcopenshell.open`, ~1,1 s) não segura a thread principal (parada ≤ 8 ms). Só o arquivo aberto ocupa ~460 MB.
- **Durante a iteração** em elementos simples: parada máxima 13 a 17 ms; mediana ~12 ms (disputa do bloqueio do interpretador, o GIL, com o laço Python do trabalhador).
- **`initialize()` segura o GIL** por 72 a 105 ms, **a cada iterador criado**, neste arquivo.
- **Destruir o iterador segura o GIL** por tempo proporcional ao que ele processou (o iterador guarda todos os resultados até morrer: é a diferença 850 MB contra 485 MB).
- **`next()` segura o GIL enquanto espera o próximo elemento.** Com 20 paredes simples e 1 parede com 150 aberturas: `next()` mais demorado 0,18 a 0,20 s, parada da thread principal 180 a 204 ms (1 e 8 threads). Com 500 aberturas: `next()` 0,68 s, parada **682 ms**. A parada é igual ao tempo do elemento mais lento. **Isto não tem conserto em Python** (seção 1.8, risco R1).
- **Ordem:** com N threads os produtos saem em outra ordem; o conjunto de IDs é o mesmo.
- **O iterador padrão devolve também `IfcOpeningElement` e `IfcSpace`** (medido). A referência 1.000.008 só vale porque o modelo sintético tem apenas paredes.
- Com `include=` de uma parede, as aberturas dela continuam sendo descontadas (72 triângulos nos dois modos, parede com 3 aberturas).
- Ajustes: com o padrão (`weld-vertices` ligado) a caixa tem 8 vértices e **nenhuma normal**; com `weld-vertices=False` tem 24 vértices e 24 normais. `use-world-coords=True` devolve os vértices já na posição final. Contagem e tempo não mudam (12,7 s).
- A cor vem em `geometry.materials[k].diffuse` (medido: 0,9; 0,9; 0,9 para produto sem estilo) e `geometry.material_ids` (um por triângulo).

**Uma thread de trabalho só chega perto do limite** (53 s de 60 s). A meta de 60 s depende de ter núcleos; a T07 deve informar o número de núcleos de cada máquina medida.

### 1.2 Arquitetura
```
thread de trabalho (Python)                           thread da interface (Qt)
CarregadorMalhas: abre o IFC, lista produtos,   fila    temporizador: tira no máximo 1 lote
blocos -> iterador(include=bloco, num_threads) -------> por quadro -> Viewport.adicionar_lote
monta LoteMalha (numpy) e põe na fila (limitada)        -> envia à placa no próximo desenho
```
1. **`CarregadorMalhas`** (Python puro, **sem Qt**, testável sem tela). Recebe o **caminho** do arquivo e abre o IFC dentro da thread de trabalho.
2. **Lista de produtos** feita pelo carregador: `IfcProduct` com `Representation` preenchida, **menos** `IfcFeatureElementSubtraction` (aberturas) e `IfcSpace`; ordenada pelo número da entidade (id STEP). As classes excluídas são parâmetro.
3. **Blocos:** a lista é cortada em blocos de `tamanho_bloco` produtos (padrão 4.000). Um iterador por bloco, com `include=`. `tamanho_bloco=0` significa um iterador só para tudo (modo de comparação).
4. **Ajustes fixos do iterador:** `use-world-coords=True`, `weld-vertices=False`, biblioteca `opencascade`, o resto no padrão. Unidade de saída: metros (padrão do iterador).
5. **Ordem estável:** dentro de cada bloco o carregador junta os produtos e **ordena por id STEP** antes de montar o lote. Assim a saída não depende do número de threads.
6. **Todo o trabalho pesado em numpy acontece na thread de trabalho** (converter, deslocar, colorir). A thread da interface só entrega o lote ao viewport.
7. **Fila limitada** (`fila_max`, padrão 4 lotes): se a interface não consome, o trabalhador espera. É o que limita a memória.
8. **`num_threads` padrão:** `max(1, os.cpu_count() - 1)`. É parâmetro e vai escrito no resumo.
9. **Posse do modelo:** enquanto a carga roda, **só a thread de trabalho toca no `ifcopenshell.file`**. Depois do fim (e só depois) o arquivo fica disponível em `carregador.arquivo` para a interface, evitando abrir duas vezes. Nenhum objeto do IfcOpenShell (forma, geometria, iterador) entra em lote ou atravessa threads.

Interface mínima do carregador (nomes obrigatórios, o oráculo usa):
```python
CarregadorMalhas(caminho, threads=None, tamanho_bloco=4000, fila_max=4,
                 excluir=("IfcFeatureElementSubtraction", "IfcSpace"))
.iniciar() -> None            # cria a thread e volta na hora
.obter(timeout=0.0)           # -> LoteMalha | ResumoCarga | None (None = nada pronto)
.cancelar() -> None           # não bloqueia
.aguardar(timeout=None) -> bool   # True se a thread terminou
.arquivo                      # ifcopenshell.file depois do fim; None antes
.lotes_produzidos             # int: lotes já montados pelo trabalhador (entregues ou na fila)
```
`obter` devolve lotes em ordem (`indice_lote` 0, 1, 2…) e, por último, **exatamente um** `ResumoCarga`, em qualquer desfecho.

### 1.3 Contrato de dados
**`LoteMalha`** (imutável; só numpy e tipos simples; os vetores são donos da própria memória e contíguos):

| Campo | Tipo | Conteúdo |
|---|---|---|
| `indice_lote` | int | 0, 1, 2… na ordem de entrega |
| `vertices` | vetor estruturado, 28 bytes por vértice: `pos` 3×float32, `normal` 3×float32, `cor` 4×uint8 (RGBA) | `pos` em metros, já na posição do mundo **menos** `deslocamento`; `normal` unitária; `cor` de 0 a 255 |
| `indices` | uint32, 3 por triângulo | relativos aos vértices **deste** lote |
| `objetos` | vetor estruturado, uma linha por produto, em ordem de id STEP: `id_step` int32, `guid` 22 bytes, `primeiro_indice` e `n_indices` uint32, `primeiro_vertice` e `n_vertices` uint32, `caixa_min` e `caixa_max` 3×float32 | um produto nunca é dividido entre lotes; as faixas são contíguas, sem buraco e sem sobreposição |
| `deslocamento` | 3×float64 | igual em todos os lotes da mesma carga; posição real = `pos + deslocamento` |
| `produtos_feitos`, `produtos_total` | int | progresso |

Regras:
1. **Deslocamento:** centro da caixa do primeiro lote, calculado em float64 e arredondado ao metro; subtraído **antes** de converter para float32. Sem isso, projetos com coordenadas de mapa (milhões de metros) tremem na tela.
2. **Cor:** por vértice, a do material do triângulo (`diffuse` × 255, arredondado; alfa = 255 × (1 − transparência), se houver). Triângulo sem material (`material_ids` = −1): cinza 204, 204, 204, 255. Se um vértice servir a triângulos de cores diferentes, ele é duplicado. A transparência é carregada mas **desenhada opaca** na S03.
3. **Normal:** a do iterador. Se um produto vier sem normais, calcular a normal de cada face e separar os vértices.
4. **Tamanho do lote:** um lote por bloco; se passar de 8 MB de vértices, fecha e abre outro (sempre em fronteira de produto).
5. Produto sem triângulos não entra em `objetos`; entra em `sem_malha` do resumo.

**`ResumoCarga`** (sempre o último item): `estado` (`"concluido"`, `"cancelado"` ou `"erro"`), `erro` (texto ou `None`), `produtos_total`, `produtos_com_malha`, `triangulos`, `vertices`, `lotes`, `sem_malha` (lista de `(id_step, guid, classe, motivo)`), `tempos` (`abrir_s`, `listar_s`, `geometria_s`, `total_s`), `threads`, `tamanho_bloco`, `mensagens` (até 50 linhas de `ifcopenshell.get_log()`).

**Cancelamento**
1. `cancelar()` só levanta um sinal e volta. O trabalhador confere o sinal depois de cada `next()` e enquanto espera vaga na fila (espera em fatias de 50 ms).
2. Ao cancelar: para de chamar `next()`, descarta o bloco em andamento (nunca entrega lote parcial), solta o iterador e entrega `ResumoCarga(estado="cancelado")`.
3. Depois de `cancelar()`, `obter()` não devolve mais nenhum `LoteMalha`: só o resumo.
4. O iterador não tem "cancelar": o atraso do cancelamento é o do `next()` em curso mais a destruição do iterador do bloco. Medido: destruir um iterador de bloco de 4.000 produtos levou até 17 ms; parar um iterador único depois de 5.000 produtos e destruí-lo, 23 ms. Com um elemento lento, é o tempo desse elemento.
5. Nova carga com outra em andamento: o adaptador cancela, espera terminar, chama `Viewport.limpar()` e começa. Proibido matar a thread à força.

**Erros de geometria**
| Situação | Comportamento |
|---|---|
| Arquivo não existe, não é IFC ou não abre | `estado="erro"`, `erro` preenchido, nenhum lote; nenhuma exceção escapa da thread |
| Produto que o iterador não devolve (falha ou geometria vazia) | A carga continua. O carregador compara "produtos do bloco" com "produtos devolvidos": a diferença vai para `sem_malha` com motivo |
| `initialize()` devolve falso, ou exceção no meio de um bloco | Os produtos restantes do bloco vão para `sem_malha` (motivo com o texto do erro); a carga segue no bloco seguinte |
| Queda do processo dentro do OCCT (falha de segmentação) | **Não tratado** na S03: derruba o programa. Só isolamento em outro processo resolve; fica como risco (1.8, R6) |
Regra de ouro: `produtos_com_malha + len(sem_malha) == produtos_total` quando `estado="concluido"`. Nada some em silêncio.

### 1.4 O que a interface `Viewport` precisa ganhar
Tudo é **acréscimo**; `set_mesh` e `grab_image` continuam como estão (os testes das T03/T04 não mudam).

| Método novo | Contrato |
|---|---|
| `limpar() -> None` | Remove todos os lotes e solta os buffers da placa |
| `adicionar_lote(lote) -> None` | Só na thread da interface. Custo proporcional **a este lote**: cria 1 buffer de vértices e 1 de índices para ele; **nunca reenvia nem recria os lotes anteriores**. O envio acontece no próximo desenho, no máximo 1 lote por quadro. Guarda a referência do lote (a T06 precisa de `objetos`, `pos` e `indices` na memória) |
| `enquadrar() -> None` | Ajusta alvo, distância e os planos perto/longe da câmera à caixa de tudo que foi adicionado |
| `estatisticas() -> dict` | `lotes`, `triangulos`, `vertices`, `bytes_gpu`, `buffers_criados` (o oráculo usa) |

Desenho (continua em **um único arquivo** de baixo nível):
1. Par de shaders novo (`malha.vert`, `malha.frag`): posição, normal, cor (`UNormByte4`); luz simples presa à câmera, `cor × (0,35 + 0,65 × |normal · direção da câmera|)`. O valor absoluto tolera face virada ao contrário.
2. **Sem descarte de faces de trás** nesse pipeline (a ordem dos vértices de um IFC não é garantida).
3. Uma chamada de desenho por lote. Com blocos de 4.000 o modelo de 1 milhão dá ~21 lotes. O custo em Python por quadro cresce com o **número de lotes**, nunca com o número de produtos: proibido desenhar produto a produto.
4. Perto/longe: `longe = (distância ao centro + raio da cena) × 1,1`; `perto = max(longe / 10.000, 0,05)`, recalculados a cada quadro.

**T06 (seleção), para mostrar que o contrato aguenta; não implementar agora:** clique → raio da câmera → teste contra `caixa_min/caixa_max` de `objetos` (83 mil caixas em numpy) → teste de triângulos só dos candidatos → devolve `id_step` e `guid`. Destaque = redesenhar a faixa `primeiro_indice, n_indices` daquele lote com outra cor. Não exige ID por vértice. Se a T06 preferir uma passada de IDs na placa, a tabela `objetos` também serve para montar o atributo.

### 1.5 Oráculo
**Regra de processo.** O oráculo é esta seção. Os testes são escritos **antes** da implementação, num PR só de testes ("Parte 0" do cartão), transcrevendo estas tabelas sem afrouxar número; depois ficam **congelados**: os arquivos de teste não estão nos "arquivos permitidos" das partes A e B. O opus confere a transcrição **antes do merge da Parte 0** (pode ser no mesmo lote que revisa a parte A). Mudar limite ou remover teste = voltar ao opus.

Arquivos: `tests/test_viewport_carregador.py` (O1 a O10), `tests/test_viewport_responsivo.py` (R1, R2), `tests/test_viewport_malha.py` (V1 a V5).
Modelos de teste gerados no próprio teste (nada baixado): **M600** = `gerar(saida, paredes=600, por_andar=200)` de `scripts/gerar_modelo_grande.py`; **M3000** = 3.000 paredes; **MAB** = 20 paredes simples + 1 parede com 150 aberturas + 1 `IfcSpace` com geometria; **M1M** = `corpus/modelo-grande-1m.ifc`, só local.
Testes "lentos" (M1M): rodam só com `OBIM_TESTES_LENTOS=1` e com o arquivo presente e de SHA-256 começando por `0d4639449d5a18f1`; senão **pulam com mensagem**. O relatório da T05 tem de trazer a saída deles executados.

| # | Teste | Passa se |
|---|---|---|
| O1 | Contagem, M600, threads padrão | `triangulos == 7.200`; `produtos_com_malha == 600`; `sem_malha == []`; `estado == "concluido"`; soma dos `n_indices` de todos os lotes `== 21.600` |
| O2 | Contagem de referência, M1M (lento) | `triangulos == 1.000.008`; `produtos_com_malha == 83.334`; `sem_malha == []`; com `tamanho_bloco=4000` e com `0` |
| O3 | 1 thread contra 4 threads, em M600 e em MAB | Mesma sequência de lotes: `objetos` idênticos (ids, guids, faixas), `indices` idênticos, `cor` idêntica, `pos` e `normal` iguais com tolerância `1e-6`. E `tamanho_bloco` 0, 200 e 4000: por produto, mesmo número de triângulos e mesma caixa (tolerância `1e-5`) |
| O4 | Filtro e aberturas, MAB | Só paredes nos lotes (21 produtos); nenhuma abertura, nenhum espaço. A parede com aberturas tem o mesmo número de triângulos que o iterador simples dá para ela (calculado no teste) e mais de 12 |
| O5 | Invariantes de cada lote, M600 | Tipos e tamanhos da tabela 1.3; vetores contíguos e donos da memória; todo índice `< n_vertices`; faixas de `objetos` contíguas, sem sobreposição, cobrindo tudo; `id_step` crescente entre lotes e dentro deles; normais com comprimento `1 ± 1e-3`; cada caixa contém os vértices do seu produto; `deslocamento` igual em todos os lotes. **Posição:** para as paredes de índice 0, 1 e 599, `caixa + deslocamento` = `[x0, x0+3] × [y0, y0+0,15] × [z0, z0+2,8]` com `x0, y0, z0` da fórmula do gerador (`colunas = 14`), tolerância `1e-3` |
| O6 | Cor (receita conferida: `style.add_style`, `style.add_surface_style` com `IfcSurfaceStyleShading` vermelho, `style.assign_representation_styles`) | Parede sem estilo: todos os vértices `(230, 230, 230, 255)`, aceitando ±1 por canal (arredondamento de 0,9 × 255). Parede com estilo de superfície vermelho puro: `(255, 0, 0, 255)` |
| O7 | Cancelamento, M3000, `tamanho_bloco=200` | Cancelar logo após o primeiro lote: `cancelar()` volta em `< 50 ms`; a thread termina em `< 2 s`; `estado == "cancelado"`; triângulos entregues `< 36.000`; nenhum `LoteMalha` sai de `obter()` depois de `cancelar()`; em seguida uma carga nova do mesmo arquivo dá `36.000` |
| O8 | Erros | Caminho inexistente e arquivo de texto qualquer: `estado == "erro"`, `erro` não vazio, só o resumo sai, nenhuma exceção na thread. Modelo com 2 paredes boas e 1 defeituosa. **Receita conferida neste lote:** `IfcWall` cuja representação "Body" é um `IfcExtrudedAreaSolid` com `IfcRectangleProfileDef` de `XDim = 0` (o iterador simples não a devolve; o teste confere isso primeiro e **falha**, não pula, se um dia passar a devolver). Vale "não devolvido **ou** devolvido com 0 triângulos": os outros produtos saem certos, o defeituoso está em `sem_malha`, e `produtos_com_malha + len(sem_malha) == produtos_total` |
| O9 | Fila limitada, M3000, `tamanho_bloco=200`, `fila_max=2` | Sem ninguém consumindo por 1 s, `lotes_produzidos <= 3` (2 na fila e 1 na mão); ao consumir, termina com `36.000` e `lotes_produzidos == 15` |
| O10 | Vida dos dados, M600 | Guardar os lotes, apagar o carregador, forçar o coletor de lixo: os vetores continuam legíveis e com a mesma soma de verificação. `carregador.arquivo` é `None` durante a carga e um `ifcopenshell.file` depois |
| R1 | Janela responsiva, modelo uniforme. M3000 no CI (sem tela, `QApplication` offscreen); M1M local (lento) | **Sonda:** `QTimer` de 5 ms (preciso) na thread da interface; atraso = intervalo real − 5 ms. Janela de medição: de `iniciar()` até o resumo recebido **e o carregador destruído**. Um temporizador da interface (16 ms) tira no máximo 1 lote por disparo. **R1a (parte A, roda no CI):** o consumidor só guarda o lote numa lista. **R1b (parte B, precisa de tela; sem tela pula):** o consumidor chama `adicionar_lote` num viewport visível, e o tempo gasto ali conta. Os dois passam se **atraso máximo ≤ 200 ms** e **percentil 95 ≤ 33 ms**, com threads padrão e `tamanho_bloco=4000` |
| R2 | Janela com elemento lento, MAB | A carga termina certa (O4). O teste grava o atraso máximo e o tempo do `next()` mais longo. A exigência "atraso máximo ≤ 200 ms" fica marcada como **falha esperada** (`xfail`, não estrito), motivo "R1 do lote Opus 4: `next()` segura o GIL". Esperado: atraso ≈ tempo do elemento (medido 0,18 a 0,20 s). **Proibido** fazer este teste passar com truque (lista em 1.8) |
| V1 | Desenho, M600 (precisa de tela; sem tela pula com mensagem) | Depois da carga e de `enquadrar()`: `estatisticas()["triangulos"] == 7.200`; a imagem tem pelo menos 3 tons diferentes; entre 5% e 95% dos pixels não são fundo |
| V2 | Envio incremental | `buffers_criados == 2 × lotes`; adicionar um lote não muda os buffers dos anteriores |
| V3 | `limpar()` | Estatísticas zeradas; imagem só com a cor de fundo |
| V4 | Profundidade | Com M600 enquadrado, `longe / perto ≤ 10.000` |
| V5 | Legado | `tests/test_viewport_qrhi.py` e `tests/test_viewport_camera.py` passam **sem alteração** |

Sobre os limites de R1: 33 ms é um quadro a 30 FPS (meta do portão); 200 ms é o teto adotado neste lote para "a janela não travou". Referência medida (sonda sem Qt): com blocos, máximo 93 ms e percentil 99 de 15 ms; com iterador único, 395 ms (**reprova**, de propósito: o teste distingue os dois desenhos). Se R1 reprovar no CI por máquina lenta, **reportar; não afrouxar**.

### 1.6 Metas do portão da S03 que a T05 mede
Script versionado de medição (parte B), em M1M, na máquina do PO, com tela. Relatório `docs/state/reports/F0-S03-T05.md` com a tabela:

| Medida | Como | Exigência na T05 |
|---|---|---|
| Tempo de abrir | Do pedido de carga até o último lote enviado à placa e um quadro completo desenhado; sem cache. Informar também o tempo até o primeiro lote visível | **< 60 s** com threads padrão. Informar também com 1 thread (sem exigência; referência 53 s) |
| Memória | Pico do processo: `resource.getrusage` no Linux; no Windows, `GetProcessMemoryInfo` (`PeakWorkingSetSize`) via `ctypes`. **Sem instalar `psutil`** | **< 6 GB** (referência: 0,5 GB só malhas; com viewport, estimativa < 1 GB) |
| Atraso da janela | Sonda de R1 | máximo ≤ 200 ms, percentil 95 ≤ 33 ms |
| Comparação | `tamanho_bloco` 0, 1000, 4000; threads 1, 4, padrão | Só relatar |

Ressalvas que o relatório da T05 deve repetir:
1. O modelo sintético tem 74 MB (não ~100 MB) e geometria barata (caixas, sem aberturas). **O veredito de "< 60 s" do portão não sai dele.** Sai da T07 e do IFC real do PO, na máquina dele. Aqui ele é piso de regressão.
2. FPS (≥ 30) e seleção (< 100 ms) são da T07 e da T06.
3. Windows: os testes O e R rodam no CI (não precisam de placa). Os V e a medição com tela **não rodam no CI hoje** (item 2, defeito 1).

### 1.7 Divisão do trabalho (limite de 400 linhas)
Não cabe em um PR. Três PRs, nesta ordem (detalhe no cartão):
- **Parte 0:** os três arquivos de teste do oráculo (pulando o que ainda não existe). **Não entra no `main` antes de o opus conferir a transcrição e o PO dar o ok**; enquanto isso, a parte A é desenvolvida contra o ramo da Parte 0, e as duas podem ir ao mesmo lote de revisão.
- **Parte A (T3):** `CarregadorMalhas`, `LoteMalha`, `ResumoCarga`. Sem Qt. Fecha O1 a O10, R1a e R2.
- **Parte B (T3, por causa das threads com a interface):** métodos novos do `Viewport`, shaders, adaptador com temporizador, script de medição, relatório. Fecha V1 a V5, R1b e a tabela 1.6.

### 1.8 Riscos para a S04 que a T05 não resolve nem esconde
| # | Risco | O que a T05 faz | Quem resolve |
|---|---|---|---|
| R1 | **O invólucro Python do IfcOpenShell segura o GIL em `initialize()`, em `next()` e ao destruir o iterador.** A janela para pelo tempo do elemento mais lento (0,2 s com 150 aberturas; 0,7 s com 500). Vale para **qualquer** chamada longa ao IfcOpenShell feita de uma thread Python | Mede e publica (teste R2 como falha esperada; números no relatório) | S04, prova 4 ("regra do bloqueio do interpretador") e meta "FPS ≥ 20 durante lote"; ADR-004. A S04 deve usar **a mesma sonda** de R1 |
| R2 | Disputa do GIL pelo laço Python do trabalhador: atraso mediano ~12 ms durante a carga | Mede (percentil 95) | S04: gerador C++ que monta o lote sem o GIL |
| R3 | A T05 **copia** a malha (bytes → numpy → placa). Isso não é o "sem cópia" da S04 (que trata do modelo) e não mede "custo da ponte" (prova 5) | Deixa escrito; os números são "linha de base Python puro" | S04. O contrato `LoteMalha` é neutro: um gerador C++ pode preencher os mesmos vetores e ser comparado com o mesmo script |
| R4 | A T05 nunca usa o `ifcopenshell.file` em duas threads ao mesmo tempo | Regra de posse (1.2, item 9). **Não serve de evidência** para as provas 2 e 4 da S04 | S04 |
| R5 | O iterador guarda todos os resultados até ser destruído (850 MB contra 485 MB) | Contorna com blocos e relata os dois números | S04 e ADR-004 decidem se o gerador C++ faz igual |
| R6 | Queda dentro do OCCT derruba o programa inteiro | Não trata | ADR-004 (processo separado é uma opção; decisão de arquitetura, não da T05) |
| R7 | Blocos com `include=` podem perder reaproveitamento de geometria repetida entre blocos e custam ~0,08 s de `initialize` cada | Relata `tamanho_bloco` 0, 1000 e 4000; **não medido em modelo real** | T07, com o IFC do PO |
| R8 | Ordem de saída muda com o número de threads | Ordena por id | Qualquer código da S04 não pode depender da ordem |
| R9 | Com 1 thread, 53 s de 60 s. Máquina com 2 a 4 núcleos (notebook com vídeo Intel) pode reprovar | Relata por número de threads | T07 e portão |
| R10 | Nada medido no Windows | Testes O e R no CI do Windows | T07 |

**Proibido na T05** (seria esconder o problema ou invadir a S04): processo separado (`multiprocessing`, `subprocess`); C++, nanobind, `ctypes` sobre o IfcOpenShell; mexer em `sys.setswitchinterval`; rodar o iterador na thread da interface com `processEvents`; alterar o invólucro do IfcOpenShell; matar thread à força; afrouxar limite do oráculo; marcar como falha esperada qualquer teste além do R2.

## 2. Item 2: amostra de revisão da S03-T03 (QRhiWidget) e da S03-T04 (Camera)
### Veredito: **APROVADAS** (as duas), contra os próprios cartões
Conferido: `prototypes/viewport_qrhi/` inteiro, os dois arquivos de teste, a ficha. Rodei os testes: **com tela (xcb): 9 de 9 passam**; **sem tela (offscreen): 7 passam, 2 pulam** com mensagem clara, como o cartão pede.
- **A ficha se sustenta?** Sim, com uma ressalva. `QRhiWidget` em Python puro desenha de fato (comprovado nesta máquina, OpenGL). A afirmação "o risco diminui porque QRhiWidget é API pública" vale para a janela; o desenho continua usando as classes `QRhi*`, sem garantia entre versões. A mitigação (Qt fixo, um único arquivo de baixo nível) está aplicada no código. **Ressalva:** está comprovado em **uma** máquina e **um** backend (defeito 1).
- **A `Camera` se sustenta?** Sim. Conferi a matemática: eixos, matriz de vista, projeção no padrão OpenGL com a correção `clipSpaceCorrMatrix`, limites de elevação e de distância, sentido do arrasto. Os testes cobrem o que o cartão pede.
- **A interface `Viewport` aguenta a T05 e a T06?** **Como está, não.** Com os acréscimos da seção 1.4, sim, e sem remover nada. A seleção da T06 funciona por objeto com a tabela `objetos` do lote; não precisa de ID por triângulo.

Nenhum item abaixo é descumprimento dos critérios de aceite dos cartões; por isso não reprovam. São pendências com dono.

| # | Gravidade | Achado | Destino |
|---|---|---|---|
| 1 | **Alta** | **O desenho nunca é verificado no CI.** Os três jobs rodam `pytest` com `QT_QPA_PLATFORM=offscreen`; os dois testes que desenham pulam. Não existe evidência de que desenha no **Windows (Direct3D 11)**, que é meta do portão, nem com Vulkan. **Por que não reprova a T03:** o cartão dela se contradiz (a linha de oráculo diz "e, no CI, no Windows"; o critério 2 manda pular sem tela; "Fora de escopo" lista "CI Windows"). O implementador seguiu os critérios de aceite; o furo é do cartão e do plano | **Cartão novo (T2)**: fazer ao menos o job `windows` desenhar um quadro (plataforma `windows` em vez de offscreen só para esses testes; o runner costuma ter Direct3D por software: **não verificado**) e falhar se pular. No Linux exigiria servidor de tela virtual no runner = ferramenta nova = ok do PO |
| 2 | Média | `perto=0,05` e `longe=20.000` fixos: razão de 400.000. No modelo de 1 milhão (≈1.250 m de altura), visto de 1 km, a precisão de profundidade fica na casa de 1 m: faces vão piscar | T05 parte B (1.4, item 4; teste V4) |
| 3 | Média | Não há "enquadrar": a câmera nasce a 3,2 m da origem. Um modelo real abre fora da vista | T05 parte B (`enquadrar`) |
| 4 | Média | `set_mesh` troca tudo de uma vez, formato fixo de 6 números, sem normal, sem identificação do produto; `_subir_malha` recria os buffers e faz duas cópias extras (`ascontiguousarray` + `tobytes`). Bom para o cubo; para carga em lotes daria custo quadrático e engasgos | T05 parte B (`adicionar_lote`) |
| 5 | Média | Descarte de faces de trás ligado (anti-horário). Malha de IFC não garante a ordem dos vértices: apareceriam buracos | T05 parte B (pipeline novo sem descarte) |
| 6 | Baixa | Sem iluminação: um modelo de cor única vira uma mancha chapada, e o teste "imagem não uniforme" não distinguiria malha certa de errada | T05 parte B (shader com luz; teste V1) |
| 7 | Baixa | `initialize()` só refaz o pipeline se o `QRhi` mudar. Se mudar o alvo de desenho (amostras, formato) com o mesmo `QRhi`, o pipeline fica com a descrição antiga; e os buffers antigos são só esquecidos, não liberados | Corrigir quando a parte B mexer no arquivo |
| 8 | Baixa | `test_set_mesh_troca_malha` confere atributos internos (`_vertices`, `_indices`). Isso amarra a implementação; a T05 tem de manter `set_mesh` intacto. Cada teste que pula sem tela espera 5 s antes (10 s por rodada no CI) | Manter; registrar |
| 9 | Processo | A ficha ainda diz "Revisado por: — (aguarda revisão sonnet)". O relato do critério 4 da T03 (backend padrão; Vulkan) **existe** (`LOG.md`, linha da T03: "padrão no Linux = OpenGL; Vulkan funciona via setApi") e **eu reproduzi** nesta máquina: padrão = OpenGL, Vulkan desenha o cubo. Só não está no README do protótipo | Líder: preencher o "Revisado por" da ficha e copiar a frase para o README |
| 10 | Informativo | "Python puro aguenta 1 milhão de triângulos a 30 FPS" **ainda não foi medido** (é a T07). O desenho atual custa uma chamada por quadro, então a aposta é razoável desde que o número de chamadas de desenho continue pequeno (regra 1.4, item 3) | T07 |
| 11 | Informativo | "Qt fixo em 6.11.2": confere com o instalado; não pude ler o `environment.yml` (fora do contexto) para ver se a versão está travada lá | Confirmar com o líder |

## 3. O que este lote não fez
- Não escreveu os arquivos de teste (só os dois arquivos permitidos). A transcrição é a Parte 0 do cartão.
- Não mediu nada no Windows, nem com tela, nem com viewport: só o carregamento em Python.
- Não leu documentação externa do IfcOpenShell; tudo o que afirmo sobre o iterador foi **observado** na versão 0.9.0 instalada. Outra versão pode se comportar diferente (a versão está travada pelo ADR-005).
- Números do oráculo conferidos na máquina: posições das paredes 0, 1 e 599 de M600 (O5), 7.200 triângulos (O1), cor (0,9; 0,9; 0,9) e vermelho (1; 0; 0) (O6), receita do produto defeituoso (O8). Curiosidade para a S06: um perfil com pontos colineares **não** falha; devolve 6 triângulos degenerados. Geometria ruim pode passar calada pelo iterador.

## 4. Para o líder
1. Os dois arquivos deste lote estão **sem commit** no ramo `s03-t02`.
2. Atualizar `BOARD.md` e `LOG.md`: T05 reespecificada como T3 em três partes; T03 e T04 aprovadas na amostra; abrir cartão para o defeito 1.
3. As partes A e B da T05 são T3: revisão opus em lote e ok do PO antes do merge.
4. Registrar em `docs/adr/` (ADR-004, quando for aberto) os fatos da tabela 1.1 e o risco R1.

## 5. Perguntas ao PO
**Respondidas pelo PO no chat em 2026-10-11: "Sim para as duas perguntas".** O líder deve copiar para `docs/state/PO.md`.
1. **Aceitar, na S03, que a janela pare pelo tempo de um elemento muito pesado** (0,2 s numa parede com 150 aberturas; raro em casa, possível em modelo grande), deixando a solução para a S04? **Recomendo sim.** As alternativas são: (a) módulo C++ agora, que o ADR-005 proíbe antes das provas da S04; (b) gerar as malhas em outro processo, que resolve a parada mas custa mais memória, mais código e decide por tabela uma questão de arquitetura que é do ADR-004.
2. **Confirmar a leitura de `v2/03` S03:** "tesselação via IfcOpenShell C++" está atendida usando o iterador C++ do IfcOpenShell chamado pelo Python (sem módulo C++ nosso na S03)? **Recomendo sim**; o C++ nosso entra na S04, que existe para comparar os dois caminhos.
