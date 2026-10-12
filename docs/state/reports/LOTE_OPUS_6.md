<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Lote Opus 6: re-revisão das correções da T05, especificação da T08 e da T26
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-12 · Pedido: `docs/state/LOTE_OPUS_6.md`
- Revisado: `5a832bc` (P0b) e `c730f5a` (C1), no ramo `origin/s03-t05-b`. PRs 16 (`f1348f0`), 18 (`55f482a`) e 19 (`ee1f35f`).
- Veredito: **as correções estão APROVADAS no conteúdo. Os três PRs, do jeito que estão montados hoje, estão REPROVADOS** (16 e 18 não contêm as correções; o 19 mistura arquivos de estado e falta 1 teste pequeno). Remontar é trabalho mecânico do líder e não pede nova rodada minha (regra no §1.5).

## Resumo para o PO
1. **As correções do lote 5 funcionam.** Rodei tudo numa tela virtual: 48 testes passam. Os testes novos acusam os dois defeitos no código antigo e passam no código corrigido. Não achei defeito novo que bloqueie.
2. **Mas os PRs 16 e 18 ainda apontam para o código antigo.** As duas correções foram gravadas só no ramo do PR 19. Se o 16 ou o 18 entrassem hoje, entraria a versão reprovada. O líder precisa levar cada correção para o ramo certo (§1.5).
3. **Achado grande para a T08:** trocando a biblioteca de geometria por outra que já vem no IfcOpenShell (a "híbrida"), o seu arquivo real inteiro converte em **cerca de 27 s, contra 370 s**. Sai o mesmo número de peças (14.804); numa amostra de 4.000 conferi peça a peça: caixas e cores iguais em todas. A máquina de café cai de 26 s para 1,5 s.
4. **O processo separado continua necessário.** Mesmo com a biblioteca rápida, uma peça do arquivo (um móvel com 1,6 milhão de triângulos) leva 11 s e travaria a janela nesse tempo.
5. **A memória é o risco que sobra.** Essa mesma peça faz a conversão chegar a 6,2 a 7,2 GB. A meta de 6 GB pode não ser atingida com este arquivo. A T08 mede; se não der, eu trago opções e você decide.
6. **A ponte C++ continua desnecessária.** O tempo está dentro da biblioteca de geometria, que já é C++. A leitura da malha em Python fica 17 vezes mais rápida com uma troca de 4 linhas.
7. **Vírgula decimal (T26):** reproduzi de novo. Pior do que eu tinha dito: o arquivo estragado **reabre sem erro, com números errados**. A correção é uma linha logo depois de criar a aplicação, e a interface continua em português.

## 0. Como este lote foi feito
- Lido: o pedido, `LOTE_OPUS_5.md`, os dois commits, os cartões C1, P0b, T08 e T26, o relatório da T07 e o código inteiro de `carregador.py`, `adaptador.py`, `cubo_rhi.py` e `medir.py` em `c730f5a`.
- Execução: worktree temporário `../openbim-studio-wt-lote6` em `c730f5a`, já removido. Testes gráficos só em `xvfb-run` com desenho por software. Sondas no rascunho da sessão, fora do repositório. Nada instalado, nenhum commit.
- Arquivo real `biblioteca-3pav-ifc4.ifc`: só lido, no lugar. Nada foi copiado nem enviado.
- Rede: `git fetch` e leitura dos PRs com `gh pr list` e `gh pr view` (só leitura).
- Máquina: 16 núcleos, 23 GB, Linux. IfcOpenShell 0.9.0, PySide6 6.11.2, Python 3.12. **Nada foi medido no Windows.**

## 1. Item 1: re-revisão de P0b e C1

### 1.1 Resultados dos testes
| Execução | Resultado |
|---|---|
| Suíte do viewport em tela virtual, com os lentos (modelo de 1 milhão) | **48 passam, 1 pula (teste pesado da T06), 1 "falha esperada que passou" (R2 de 200 ms)** |
| Testes novos contra o código **antigo** (`5a832bc`) | **2 falham, como devem:** O11 com espera de 1e-9 s (trava) e V4 depois de arrastar (canto a 203,5 m, plano "longe" a 162,9 m) |
| R2 e O11 repetidos 8 vezes | sempre passam; atraso de 168 a 195 ms contra `next()` de 172 a 193 ms (razão 0,92 a 1,07; o teste exige 0,5) |
| R1 no modelo de 1 milhão, agora com a primeira amostra | sem viewport: máx. 84 ms, p95 7,5 ms · com viewport: máx. 131 ms, p95 12,6 ms (limites 200 e 33) |

### 1.2 P0b (`5a832bc`, os três arquivos de teste): **APROVADO**
| Emenda do lote 5 §1.1 | Situação |
|---|---|
| 1. Manter a primeira amostra e chamar `iniciar()` dentro do laço de eventos | Feito, em R1 e em R2 |
| 2. O1 e O8 exigem nenhuma exceção na thread | Feito. Conferi que o gancho substituído é mesmo chamado |
| 3. O11: `obter(timeout)` sempre volta, para 0, 1e-9, 0,01 e 0,05 | Feito. Falha no código antigo; a thread do teste não pendura o CI |
| 4. V4: a cena cabe depois de arrastar | Feito, com os dois arrastos que pedi. Falha no código antigo |
| 5. R2 demonstra o fenômeno (atraso ≥ 0,5 × `next()`) | Feito. Estável em 8 repetições |
| 6. Números de R1 e R2 visíveis sem `-s` | Feito |

Nenhum número foi afrouxado. Observação de processo, não bloqueia: o commit também gravou três arquivos em `docs/state/`, fora dos arquivos permitidos do cartão.

### 1.3 C1, parte do carregador (`carregador.py` em `c730f5a`): **APROVADO**
| Defeito | Situação | Como conferi |
|---|---|---|
| A-1 `obter(timeout)` trava | Corrigido | 2.000 chamadas com 1e-9 s voltam em 0,011 s; O11 passa |
| A-2 cancelar depois do fim | Corrigido | com 3 lotes na fila, o resumo sai "cancelado" e avisa "3 lote(s) descartado(s)"; se tudo já foi consumido, continua "concluido" |
| A-3 `arquivo` antes do fim | Corrigido | só é publicado com estado "concluido", logo antes de liberar o resumo; em erro fica `None` |
| A-4 texto do erro quando `initialize()` falha | Corrigido | lido no diff |
| A-5 `deslocamento` gravável | Corrigido | lido no diff |
| A-6 aviso de cor | Não feito (era opcional) | — |

Observações que **não bloqueiam** (entram na T08, que reescreve este trecho):
1. `ifcopenshell.get_log()` esvazia o registro ao ser lido (medi: 124 caracteres na primeira chamada, 0 na segunda). As linhas que o A-4 anexa ao motivo deixam de aparecer em `mensagens` do resumo. A informação não se perde, só muda de lugar.
2. Ao cancelar depois do fim, o resumo diz "cancelado", mas `arquivo` continua publicado. É coerente o bastante: o arquivo foi lido inteiro; quem recebe é avisado de que faltam lotes.

### 1.4 C1, parte do viewport (`cubo_rhi.py`, `adaptador.py`, `medir.py`, README, teste do adaptador)
| Defeito | Situação | Como conferi |
|---|---|---|
| B-1 plano "longe" pelo centro da cena | Corrigido | V4 novo passa e falha no código antigo |
| B-2 memória no Windows | **Corrigido no papel, não demonstrado** | os tipos estão declarados, mas o teste mínimo no Windows que pedi não foi criado |
| B-3 liberar recursos ao trocar de contexto | Corrigido | sonda: mudei o widget de janela e depois o número de amostras. O Qt chamou `releaseResources`, os 3 lotes foram reenviados (6, 12 e 18 buffers), a imagem ficou igual e não houve aviso de recurso vazado nem queda |
| B-4 retorno de `aguardar()` | Corrigido | `cancelar()` devolve falso e `abrir()` emite `erro` sem começar outra carga |
| B-5 cancelar ao fechar | Corrigido | ligado a `aboutToQuit` |
| B-6 README com os shaders de malha | Corrigido | — |
| B-8 teste do adaptador | Feito | passa sem tela, com viewport falso |
| 1.1-1 em `medir.py` | Feito | — |

Observações que **não bloqueiam**:
1. Quando `abrir()` desiste (B-4), ninguém emite `terminou` para a carga velha. A interface pode ficar "carregando". A T08 resolve na raiz: cancelar passa a encerrar o processo em menos de 1 s.
2. Com uma peça de 160 s, fechar o programa ainda espera 5 s e depois mata a thread no meio do C++. Mesmo remédio na T08.

### 1.5 Veredito por PR
| PR | Como está hoje | O que eu aprovo |
|---|---|---|
| **16** (oráculo, `f1348f0`) | **REPROVADO**: não contém o P0b | Os três arquivos de teste **iguais aos de `c730f5a`** |
| **18** (carregador, `55f482a`) | **REPROVADO**: ainda tem o A-1 (trava) | `carregador.py` **igual ao de `c730f5a`** |
| **19** (viewport, `ee1f35f`) | **REPROVADO**: lista abaixo | O código de `prototypes/viewport_qrhi/` e `tests/test_viewport_adaptador.py` **iguais aos de `c730f5a`** |

**Lista do PR 19:**
1. Falta o teste mínimo do B-2: `pico_memoria_mb() > 0`, sem tela, rodando no Linux e no Windows. É o único jeito de o B-2 ficar provado antes da medição no Windows. Ele vai num **PR próprio, pequeno** (teste de script de medição, classe T1), para o PR 19 ficar exatamente com o conteúdo que aprovo.
2. O PR carrega cinco commits de estado e documentos (`43ea6d0`, `d1b94f1`, `3520b40`, `ed7abd8`, `ee1f35f`). `BOARD.md` e `LOG.md` **conflitam com o `main`** (conferi com uma mesclagem de ensaio). Levar para um PR só de estado.
3. Nenhum código das partes A, B e C1 rodou no CI até hoje. O CI só dispara em PR para o `main`, e o único PR nessa condição (16) tem os testes pulando por falta do carregador. O Windows nunca executou este código.

**Regra para o líder remontar sem nova rodada minha** (não é aprovação provisória: aprovo conteúdo exato, que se confere com `git`):
- Ramo do PR 16: `git diff c730f5a -- tests/test_viewport_carregador.py tests/test_viewport_malha.py tests/test_viewport_responsivo.py` tem de sair **vazio**. Impressões digitais: `52d874da85`, `b7cc7c84c3`, `28a1708433`.
- Ramo do PR 18: o mesmo para `prototypes/viewport_qrhi/carregador.py` (`99e993eda4`).
- Ramo do PR 19: o mesmo para `cubo_rhi.py` (`f576918683`), `adaptador.py` (`a119538a5c`), `medir.py` (`bffc6bbf16`), `README.md` (`c6a020e409`) e `tests/test_viewport_adaptador.py` (`d4d2868c0a`). Sem nenhum arquivo de `docs/state/` e sem o teste do item 1, que vai em PR próprio.
- Os jobs `linux` e `windows` verdes em cada PR quando ele apontar para o `main`. Recomendo abrir antes um PR de rascunho do ramo completo para o `main`, só para ver os dois jobs com tudo junto, **antes** de congelar o oráculo no `main`.
- **Se qualquer um desses arquivos precisar sair diferente, volta para o lote Opus.** Isso inclui o caso de o teste do B-2 falhar no Windows: aí `medir.py` muda, e a mudança é minha para revisar.

## 2. Item 2: especificação da T08

### 2.1 O que medi no arquivo real (sem interface, só conversão)
**Peças lentas, sozinhas, 1 thread** (o tipo delas é "conjunto de faces poligonais", ou seja, já são malha):
| Peça | Triângulos | opencascade (atual) | cgal | cgal-simple |
|---|---|---|---|---|
| Máquina de café | 224 mil | 25,8 s | 18,2 s | **1,5 s** |
| Poltrona | 52 mil | 6,8 s | 4,1 s | **0,7 s** |
| Montante (exemplo comum) | 12 | 0,13 s | 0,12 s | 0,04 s |

A máquina de café sozinha levou 26 s aqui, não os 160 s da T07. A diferença deve vir da disputa entre as 15 threads naquela medição. Não investiguei.

**Bibliotecas, primeiros 4.000 produtos, 15 threads:**
| Biblioteca | Tempo | Com malha | Observação |
|---|---|---|---|
| `opencascade` (atual) | 33,9 s | 3.998 de 3.998 | referência |
| `cgal` | 29,2 s | 3.998 | ganho pequeno |
| `cgal-simple` | 3,3 s | 3.984 | **perde 14 peças: as paredes e lajes com abertura** |
| `hybrid-cgal-simple-opencascade` | **3,4 s** | 4.000 de 4.000 | caixas iguais (1 mm) em todas; **cores iguais em todas**; área igual (1 %) em todas menos 1 móvel; número de triângulos igual em 3.935; as 14 peças com abertura iguais |

**O oráculo congelado da T05 passa sem alteração com a híbrida.** Troquei só o nome da biblioteca em `carregador.py` num worktree temporário e rodei em tela virtual: 28 passam, mais os 4 lentos do modelo de 1 milhão; as receitas de cor e de defeito e as contagens continuam exatas. O R2 continua em 183 ms (o elemento lento tem recorte e cai na `opencascade`).

**Modelo inteiro com a híbrida (14.810 produtos):**
| Medida | Blocos de 4.000 | Blocos de 1.000 | T07 (opencascade) |
|---|---|---|---|
| Conversão | 27,3 s | 31,4 s | 370 s |
| Com malha / triângulos | 14.804 / 8.595.714 | igual | 14.804 / 8.620.328 |
| (no modelo inteiro comparei só a contagem, não peça a peça) | | | |
| Passo mais longo | 11,5 s | 10,5 s | 178 s |
| Pico de memória do processo | 7,2 GB | 6,2 GB | 12,2 GB (com interface) |

O passo de 11 s é **uma peça só**: o móvel `MOB_CAF_001`, com 1.598.734 triângulos (19 % do modelo). É ela que causa o pico de memória.

**Outras medidas:**
- Abrir o arquivo: 3,2 s e **1,28 GB**. Aberto numa thread, a thread principal parou no máximo 67 ms.
- Ler a malha pelos vetores prontos (`verts_buffer`, `faces_buffer`, `normals_buffer`, `material_ids_buffer`) em vez das tuplas: **0,12 s contra 2,08 s** nos mesmos 2,2 milhões de triângulos, com soma de controle igual. Na peça gigante o pico cai de 4,2 para 3,6 GB.
- Passar lotes entre processos por canal comum: 40 lotes de 12,6 MB em 1,7 s; receber cada um custa 4 ms (mediana) e 31 ms (máximo).
- Ordem de saída do iterador: **com 1 thread, sempre crescente por id; com 15 threads, fora de ordem** (1.141 inversões em 4.000).
- Peça lenta fabricada (grade de 120 × 120 faces poligonais, 1,4 MB): 2,99 s com `opencascade`, 0,15 s com a híbrida.

### 2.2 Decisões
**D1. Biblioteca (resposta ao item c).** O padrão da malha de visualização passa a ser `hybrid-cgal-simple-opencascade`. Ela tenta a rápida e cai na atual quando há recorte de abertura. `CarregadorMalhas` ganha o parâmetro `biblioteca=`; `"opencascade"` continua disponível.
- Curiosidade a registrar: `has_geometry_library()` responde falso para o nome da híbrida, mas o iterador aceita e ela consta na lista oficial de nomes.
- Licença: o CGAL já está registrado na tabela de licenças (vem compilado dentro do IfcOpenShell). Não entra pacote novo.
- Vale só para a malha do visualizador. Cortes e linhas ocultas (fases futuras) decidem a própria biblioteca.

**D2. Leitura por vetores prontos.** `_produto_para_numpy` usa os quatro `*_buffer` com `np.frombuffer` (posições e normais em float64, faces e materiais em int32).

**D3. Processo separado (resposta ao item a).**
- Módulo novo `processo_malhas.py`, sem Qt. Função de entrada no nível do módulo. Contexto `multiprocessing.get_context("spawn")` **também no Linux**: mesmo comportamento nos dois sistemas e nenhuma cópia de processo depois que o Qt criou threads.
- **A interface pública de `CarregadorMalhas` não muda** (`iniciar`, `cancelar`, `aguardar`, `obter`, `arquivo`, `lotes_produzidos`). A thread interna vira "leitora e vigia": cria o filho, lê as mensagens e alimenta a mesma fila limitada de hoje.
- Canal: `ctx.Pipe(duplex=False)`, **um por filho**. O pai fecha a ponta de escrita logo depois de `start()`. **Não usar `multiprocessing.Queue`:** a documentação do Python avisa que matar um processo que usa a fila pode corrompê-la, e o pai, que guarda a ponta de escrita, ficaria esperando para sempre.
- Mensagens: tuplas `(tipo, dados)` com os vetores numpy. Tipos: `fase`, `inicio`, `lote`, `feitos` (ids concluídos, **um aviso para cada produto**), `sem_malha`, `fim` (tempos e pico de memória do filho).
- **O pai não tem o arquivo aberto.** Por isso `inicio` traz, para **todos** os produtos, `(id_step, guid, classe, nome, família)`, onde família é o id do item mapeado (ou nenhum). É daí que o pai tira os dados de uma peça cujo filho foi morto e a lista de cópias da mesma família.
- **Peça maior que um lote.** Um produto cujos vértices passam de 8 MB é dividido em vários lotes de até 8 MB, com o mesmo `id_step` em cada um (uma linha de `objetos` por pedaço). `produtos_com_malha` conta ids distintos. O limite vira o parâmetro `max_bytes_lote`. Motivo: a peça de 1,6 milhão de triângulos do arquivo real daria um lote de cerca de 150 MB, que custa tempo à interface três vezes (receber, copiar e enviar à placa). O cartão de integração da seleção (T06 com T05) passa a juntar as linhas de mesmo id.
- **Sem memória compartilhada.** O custo medido do canal comum é desprezível perto do limite de 33 ms, e memória compartilhada deixa sobra quando o filho é morto. Se a medição da T08 reprovar o atraso, o remédio já autorizado é `send_bytes` por vetor.
- Contrapressão: a leitora bloqueia na fila cheia, o canal enche e o filho espera. Nenhum limite novo.
- Cancelar e fechar: o pai mata o filho (`kill()`, depois `join(2)`), fecha o canal e monta o resumo "cancelado". O filho só lê o arquivo, então matar é seguro.
- Filho órfão: `daemon=True`; se o envio falhar por canal quebrado, o filho sai.
- `arquivo`: durante a carga só o filho abre o IFC. Parâmetro novo `manter_arquivo` (padrão falso). Com verdadeiro, o pai abre o arquivo **depois que o filho terminou** e antes de liberar o resumo, para os picos de memória não se somarem.
- Localidade: o filho nunca cria Qt e confere no início que o separador decimal é ponto (ver T26).

**D4. Limite por peça (resposta ao item b).**
- Parâmetro `limite_peca_s`, padrão **20 s** (`None` desliga). A maior peça legítima medida levou 11,5 s.
- **Modo rápido:** blocos com várias threads. A vigia mede o tempo desde a última mensagem do filho na fase "convertendo". Passou do limite: mata o filho. As fases "abrindo" e "listando" têm limite próprio e largo (`limite_abrir_s`, padrão 600 s).
- **A fase "convertendo" começa antes de criar o iterador de cada bloco.** A primeira peça é convertida dentro de `initialize()` (medi: na peça gigante sozinha, quase todo o tempo e a memória aparecem ali, e o laço depois leva 0,2 s). No modo isolado isso vale para toda peça que estiver na vez.
- Com várias threads não dá para saber qual peça travou (a ordem de saída não é a do pedido). Por isso os produtos pendentes do bloco vão para o **modo isolado**: um filho novo, **1 thread**, só os pendentes. Com 1 thread a ordem é crescente por id (medido), então a peça em espera é sempre o menor id pendente e o limite vale por peça de verdade.
- Estourou no modo isolado: mata o filho, a peça vira **caixa**, e o próximo filho isolado continua sem ela. Terminados os pendentes, volta o modo rápido no bloco seguinte.
- **Mesma família:** produtos pendentes que usam o mesmo item mapeado de uma peça lenta viram caixa sem nova tentativa (senão cada cópia custaria outro limite).
- **Queda do filho** (falha dentro da biblioteca de geometria) é tratada igual: pendentes para o modo isolado, e a peça da vez vira caixa com motivo "o conversor caiu". Ganho de robustez que hoje não existe.
- Teto: 20 reinícios por carga. Passou disso, o resumo sai com estado "erro".
- **A caixa** é calculada num filho, nunca no processo da interface, sem a biblioteca de geometria:
  1. pontos da representação (listas de pontos e pontos cartesianos), levados pelo item mapeado e pela posição do objeto, na unidade do arquivo convertida para metros; limite de 5 s. Isso é exato para peças que já são malha, como as três do arquivo real. Para sólido extrudado, somar aos pontos do perfil os mesmos pontos deslocados pela profundidade na direção da extrusão;
  2. qualquer outro tipo de item, falha ou estouro: cubo de 0,5 m na posição do objeto.
  A caixa é um lote normal de 12 triângulos, cor laranja `(255, 140, 0, 255)`, para a pessoa ver que é substituta.
- **Resumo:** campo novo `simplificadas`, lista de `(id_step, guid, classe, nome, motivo, segundos)`. Essas peças contam em `produtos_com_malha`. A regra de ouro continua: `produtos_com_malha + len(sem_malha) == produtos_total`. `mensagens` ganha uma linha em português simples: "N peça(s) foram mostradas como caixa porque passaram de 20 s".
- Bloco padrão passa a **1.000**: custa 4 s a mais no arquivo real, baixa o pico em 1 GB e reduz os pendentes de um reinício.

**D5. Como medir memória (resposta ao item e).**
- O pico do pai **não inclui** o filho. Sem instalar `psutil`.
- **Número da meta: pico somado = pico do pai + maior pico entre os filhos.** É a conta conservadora (os dois picos podem não coincidir no tempo) e não perde picos curtos.
  - Pico de cada filho: o próprio filho informa em `fim`. Para filho que vai ser morto, a vigia lê o pico **antes** de matar. Linux: `VmHWM` em `/proc/<pid>/status`. Windows: `PeakWorkingSetSize` de `GetProcessMemoryInfo` com o identificador do processo filho (a função do B-2, agora recebendo o identificador).
  - No Linux, `RUSAGE_CHILDREN` serve de conferência.
- Número secundário, só informativo: maior soma amostrada (pai + filho vivo) a cada 0,25 s.
- Estimativa honesta: só o filho chegou a 6,2 GB com blocos de 1.000 e leitura por tuplas. Com D2 deve cair cerca de 0,5 GB. O pai soma perto de 1 GB (malhas e cópias para a placa). **A meta está em risco neste arquivo por causa de uma única peça.** Se a medição não atingir: parar e levar ao PO com opções. Não contornar.

**D6. Ponte C++: continua desnecessária.** Dos 27 s, a parte em Python era cerca de 10 s. Com D2 a leitura bruta cai 17 vezes (medido); o total em Python deve ficar em 1 a 2 s (**estimativa**: não medi a função inteira com os vetores prontos). O resto está dentro da biblioteca de geometria, que já é C++. O travamento da janela se resolve com o processo. Reavaliar só se a T08 não atingir as metas de tempo.

### 2.3 Riscos
1. **Peça gigante.** Mesmo dividida em lotes de 8 MB (D3), a peça de 1,6 milhão de triângulos chega em cerca de 20 lotes seguidos. O critério de atraso é medido justamente neste arquivo; se reprovar, parar e reportar.
2. **"spawn" reimporta o módulo principal.** Todo ponto de entrada precisa de `if __name__ == "__main__":`, e o aplicativo precisa de `multiprocessing.freeze_support()`. No AppImage e no instalador do Windows o filho precisa achar o interpretador certo. Vira item do teste dos pacotes (um "eco" pelo filho no `--selftest`).
3. **Diferença de malha entre bibliotecas:** 0,3 % menos triângulos no total e 1 móvel em 4.000 com área diferente em mais de 1 %. Não olhei a aparência. A T08 inclui uma captura de tela lado a lado do arquivo real para o PO.
4. **Cada reinício reabre o arquivo** (3 a 4 s neste arquivo). Com limite de 20 s, cada peça lenta custa cerca de 45 s. Aceitável porque é raro.
5. `create_shape` e o cálculo da caixa dependem de funções utilitárias do IfcOpenShell (posição do objeto, transformação do item mapeado, escala da unidade). O implementador confirma que existem na 0.9.0 antes de usar. Se não existirem, parar e reportar.

### 2.4 Oráculo (resposta ao item d)
Arquivo novo `tests/test_viewport_processo.py`, escrito por um subagente diferente do implementador. Todos sem tela, salvo indicação.

**Peça lenta fabricada, de dois jeitos:**
- **Atraso injetado (determinístico, roda no CI):** o filho lê a variável `OBIM_TESTE_PECA_LENTA="<guid>=<segundos>[,<guid>=<segundos>]"` e dorme esse tempo ao receber a peça, antes de anunciá-la como feita. `OBIM_TESTE_MATAR_FILHO="<guid>"` faz o filho sair com código 3 nessa peça. As duas só valem se a variável existir.
- **Lentidão real (teste lento, local):** grade de 120 × 120 faces poligonais, gerada no próprio teste, **como único produto do arquivo**. Assim a lentidão acontece dentro de `initialize()`, caminho que o atraso injetado não exercita.
- **As peças de P4 e P5 são malha (conjunto de faces) atrás de um item mapeado**, como as três do arquivo real. Só assim a caixa por pontos é exata e o teste de 1 cm faz sentido.
- **Guardas de ativação, no estilo da T05:** `requer_processo` (liga quando existir `processo_malhas.py`) e `requer_limite` (liga quando `CarregadorMalhas` aceitar `limite_peca_s`). Sem elas, a suíte ficaria vermelha entre um cartão e outro.

| # | Caso | Exige |
|---|---|---|
| P1 | Modelos de 600 e 3.000 paredes pelo processo | mesmos números do O1 e do O3 da T05; a suíte O1 a O11 passa **sem alteração**, salvo as emendas abaixo |
| P2 | Diagnóstico do filho | `PySide6` não está carregado no filho; separador decimal é ponto; o carregador usa o contexto "spawn" |
| P3 | Janela responsiva com peça de 3 s injetada, `limite_peca_s=None` | atraso máximo ≤ 200 ms e p95 ≤ 33 ms (mesma sonda do R1); a peça chega com a malha inteira |
| P4 | Peça de 5 s injetada, `limite_peca_s=1.0` | termina em ≤ 15 s com estado "concluido"; `simplificadas` tem exatamente esse id, com motivo de limite e segundos ≥ 1,0; a peça tem 12 triângulos; a caixa bate em 1 cm com a de uma carga sem injeção; todas as outras peças têm os mesmos triângulos; regra de ouro vale |
| P5 | Duas cópias do mesmo item mapeado, lentas | as duas em `simplificadas`; tempo total ≤ tempo do P4 medido na mesma execução + 0,5 × limite + 3 s (a segunda cópia não é esperada de novo) |
| P6 | Lentidão real (lento, local) | com `biblioteca="opencascade"` e limite de 1 s a grade vira caixa; com a híbrida sai com 28.800 triângulos e não é simplificada |
| P7 | Cancelar durante peça de 30 s | `aguardar(2.0)` verdadeiro em menos de 1 s; resumo "cancelado"; `multiprocessing.active_children()` vazio |
| P8 | Filho que cai numa peça | estado "concluido"; a peça em `simplificadas` com motivo de queda; as outras iguais |
| P9 | Consumidor parado | depois de 1 s, `lotes_produzidos` ≤ `fila_max` + 2 |
| P10 | Adaptador com peça de 30 s | `cancelar()` verdadeiro em menos de 1 s |
| P11 | Medição | `pico_memoria_mb() > 0` e o pico lido de um filho vivo > 0, no Linux e no Windows |
| P12 | Peça maior que o lote (`max_bytes_lote` de 64 kB e a grade de 120 × 120) | nenhum lote passa do limite por mais de 1 triângulo; a soma dá 28.800 triângulos; o mesmo `id_step` aparece em várias linhas; `produtos_com_malha == 1` |

P1, P2, P3, P7, P9, P10, P11 e P12 usam `requer_processo`. P4, P5, P6 e P8 usam `requer_limite`.

**Emendas ao oráculo da T05, autorizadas aqui (as duas só valem com `requer_processo` ligado; antes disso os testes ficam como hoje):**
1. O10 passa a criar o carregador com `manter_arquivo=True`.
2. `test_r2_demonstra_o_fenomeno_do_gil` deixaria de passar, e é esse o aviso planejado: com o processo, ele é pulado e o `xfail` sai de `test_r2_atraso_maximo_com_elemento_lento`, que passa a ser teste comum (≤ 200 ms). Na T08-A (ainda sem processo) nada muda: medi 183 ms com a híbrida.
3. Com a híbrida o oráculo congelado passou inteiro (§2.1). Mesmo assim, se algum número congelado mudar na implementação: **parar e reportar**. O implementador não edita o oráculo.

**Aceite com o arquivo real (máquina do PO e VM Windows, fora do CI):** abrir tudo em menos de 60 s; pico somado abaixo de 6 GB; atraso máximo abaixo de 200 ms; 14.804 peças com malha e 6 sem; lista de `simplificadas` no relatório; nenhum processo filho sobrando depois de cancelar e de fechar.

### 2.5 Divisão em cartões (o limite de 400 linhas não cabe num só)
| Cartão | Conteúdo | Classe | Tamanho estimado |
|---|---|---|---|
| T08-0 | Oráculo P1 a P11 e as emendas | T3 (oráculo) | 300 a 400 |
| T08-A | D1 e D2 em `carregador.py` | T3 | < 40 |
| T08-B1 | D3: `processo_malhas.py`, leitora e vigia, cancelar, divisão de peça gigante | T3 | 300 a 400 (se passar, separar a divisão de peça num B1b) |
| T08-B2 | D4: modo isolado, caixa, `simplificadas` | T3 | 250 a 350 |
| T08-C | D5 em `medir.py`, medição no arquivo real (Linux e Windows), relatório | T2 | < 150 |

Ordem: 0, A, B1, B2, C. **A T08-A sozinha já leva a conversão de 370 s para cerca de 30 s.** Vale medir logo depois dela.

## 3. Item 3: especificação da T26

### 3.1 O que medi (`LANG=pt_BR.UTF-8`, sem `LC_ALL`, Qt sem tela)
| Momento | Localidade numérica | O que o IfcOpenShell grava |
|---|---|---|
| Início do Python | `C` | `IFCCARTESIANPOINT((2799.9999,0.5,1.E-07))` |
| Depois de criar o `QApplication` | `pt_BR.UTF-8` | `IFCCARTESIANPOINT((2799,9999.,0,5.,1.E-07))` |
| Depois de `locale.setlocale(locale.LC_NUMERIC, "C")` | `C` | correto de novo, inclusive numa segunda thread |

- **O arquivo estragado reabre sem erro.** O ponto de 3 coordenadas volta com 5: `(2799.0, 9999.0, 0.0, 5.0, 1e-07)`. É corrupção silenciosa.
- `to_string()` sofre do mesmo jeito.
- **Variável de ambiente não resolve:** com `LC_ALL=pt_BR.UTF-8` e `LC_NUMERIC=C` juntos, a vírgula volta. `LC_ALL` vence.
- `LC_ALL=C` também não serve para o programa: o Qt reclama, troca sozinho para `C.UTF-8`, e a interface perde o português.
- Depois da correção a interface continua brasileira: `QLocale` responde `pt_BR`, formata `1.234,50`, e uma caixa numérica mostra `1,50`. Datas e textos não mudam.
- Evidência extra: minha primeira sonda do B-3 gerou o modelo de 600 paredes depois de criar o `QApplication` e saiu com **0 lotes**. Foi este defeito.

### 3.2 Especificação
**Onde.** Módulo novo `app/openbim_app/localidade.py`:
- `fixar_numerico_c()`: chama `locale.setlocale(locale.LC_NUMERIC, "C")`. Só a categoria numérica.
- `numerico_ok()`: verdadeiro se o separador decimal do processo é ponto.
- `garantir_numerico_c()`: se `numerico_ok()` for falso, corrige e devolve verdadeiro (para quem chamou registrar um aviso).
- `criar_aplicacao(argv)`: **único lugar do programa que cria o `QApplication`**; chama `fixar_numerico_c()` na linha seguinte.

**Quando.**
1. Logo depois de criar o `QApplication`, antes de qualquer janela, thread ou uso do IfcOpenShell. O cartão dizia "antes e depois"; **só depois adianta**, porque é o construtor do Qt que troca a localidade. É o remédio que a própria documentação do Qt indica.
2. Imediatamente antes de toda gravação de IFC e de `.obim`: `garantir_numerico_c()`. Hoje o programa não grava IFC. Fica como regra para a S05: toda gravação passa por uma função única que chama a garantia.
3. `prototypes/viewport_qrhi/__main__.py` e `medir.py`: a mesma linha depois do `QApplication`.
4. O filho da T08 confere `numerico_ok()` ao iniciar.
5. `main.py` passa a usar `criar_aplicacao`, e o `--selftest` passa a exigir `numerico_ok()`.

**O `conftest.py` fica como está** (`LC_ALL=C`): ele protege os testes que criam `QApplication` por conta própria. Por isso os testes da T26 rodam **em subprocesso, com `LC_ALL` removido do ambiente**; senão herdariam o `C` e não provariam nada.

### 3.3 Oráculo (`tests/test_localidade.py`, mais um script auxiliar)
Cada caso roda num subprocesso com `QT_QPA_PLATFORM=offscreen` e localidade com vírgula. No Linux: `pt_BR.UTF-8`. No Windows: forçar com `locale.setlocale(locale.LC_NUMERIC, ...)` usando o nome que o sistema aceitar.
| # | Caso | Exige |
|---|---|---|
| L1 | Canário: `QApplication` criado **sem** a correção | no Linux, separador vira vírgula e o texto do IFC contém `2799,9`. Prova que o teste enxerga o defeito. Se parar de reproduzir, o teste falha e avisa |
| L1w | Canário do Windows: forçar a localidade com vírgula à mão, sem a correção | o texto gravado pelo IfcOpenShell contém a vírgula. Prova que ele enxerga a mesma localidade que o Python. **Se não contiver, pular L2 a L5 no Windows com mensagem em destaque** (senão passariam sem provar nada) |
| L2 | `criar_aplicacao` e gravação de um IFC com 2799.9999999999995, 0.5, 1e-7 e -0.001 | as linhas das entidades são **idênticas** às de um processo em localidade `C`; ao reabrir, o ponto tem 3 coordenadas com os valores exatos |
| L3 | Interface depois da correção | `QLocale().toString(1234.5, "f", 2) == "1.234,50"`; categorias de data e de texto inalteradas |
| L4 | Outra biblioteca desfaz a correção (`setlocale(LC_ALL, "")`) | `garantir_numerico_c()` devolve verdadeiro e a gravação seguinte sai correta |
| L5 | Gravação numa thread secundária | correta |
| L6 | `python -m openbim_app --selftest` em pt_BR | imprime OK e sai com 0; em `app/`, `QApplication(` só aparece em `localidade.py` |

**Se a localidade com vírgula não existir na máquina: pular com mensagem em destaque, nunca passar em silêncio.** O executor Linux do GitHub provavelmente não tem `pt_BR` (ver pergunta 2).

Classe T3. Arquivos permitidos: `app/openbim_app/localidade.py` (novo), `app/openbim_app/main.py`, `prototypes/viewport_qrhi/__main__.py`, `prototypes/viewport_qrhi/medir.py`, `tests/test_localidade.py` e seu script auxiliar (novos), um parágrafo em `docs/dev-setup.md`, e `.github/workflows/ci.yml` só se o PO autorizar a pergunta 2. Estimativa: menos de 150 linhas. Oráculo escrito por subagente diferente do implementador; revisão no lote 7.

### 3.4 Riscos
1. **A localidade é do processo inteiro e trocá-la não é segura com threads rodando.** Por isso a correção é feita uma vez, no início. A garantia antes de gravar só mexe se achar o valor errado.
2. **Outra biblioteca pode desfazer** (diálogos nativos, impressão, bibliotecas gráficas carregadas depois). Cobre-se com a garantia antes de gravar e com o L4.
3. **Números mostrados ao usuário têm de vir do `QLocale`**, nunca de funções do C. Regra a registrar em `docs/dev-setup.md`.
4. **Windows:** acredito que o Qt não troca a localidade do C nesse sistema, mas **não verifiquei**. A correção é inofensiva lá, e o teste força a vírgula para provar.
5. **Arquivos já estragados** reabrem sem erro. Fora do escopo da T26; proponho um cartão futuro (S05) para avisar ao abrir quando um ponto tiver mais de 3 coordenadas.
6. **`QCoreApplication` (sem interface) não foi verificado.** `criar_aplicacao` cobre o caso do programa.
7. macOS deve se comportar como o Linux; não testado.
8. Empacotamento: o `AppRun` não deve definir `LC_ALL`.

## 4. Para o líder
1. Remontar os três ramos conforme o §1.5, criar o teste do B-2 e separar o estado num PR próprio.
2. Abrir os cartões T08-0, A, B1, B2 e C, e completar o T26 com o §3.
3. `CLAUDE.md` cita a pasta `../openbim-studio-referencias/`; a pasta real é `../openbim-studio-referencia/`. Mexer no `CLAUDE.md` pede o ok do PO.
4. O pedido manda ver `docs/dev-setup.md` para o `xvfb-run`, mas o arquivo no `main` não fala dele. Sugiro registrar o comando: `env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 <comando>`.
5. Este arquivo foi escrito **sem commit**, na pasta principal, no ramo `lote6-estado` (árvore limpa antes).

## 5. Perguntas ao PO
> **Respostas do PO no chat, em 2026-10-12: SIM para as três.** (1) biblioteca híbrida como padrão da visualização, com comparação lado a lado antes de fechar a T08; (2) passo que cria a localidade pt_BR no job Linux do GitHub, só na máquina descartável; (3) limite de 20 s por peça. O líder registra em `PO.md` e no LOG.

1. **Trocar a biblioteca de geometria da visualização pela "híbrida"?** O seu arquivo real cai de 370 s para cerca de 27 s, com as mesmas peças. O desenho pode mudar um pouco em poucas peças (1 móvel em 4.000 nas minhas contas). **Recomendo sim**, com uma comparação lado a lado para você olhar antes de fechar a T08.
2. **Posso pedir ao líder um passo nos testes automáticos do GitHub (Linux) que cria o "português do Brasil" na máquina de teste?** É uma máquina descartável do GitHub, nada é instalado no seu computador. Sem isso, o teste da vírgula só roda na sua máquina e no Windows. **Recomendo sim.**
3. **Limite por peça de 20 s?** Peça que passar disso aparece como uma caixa laranja e entra numa lista no fim da carga. No seu arquivo, com a biblioteca nova, nenhuma peça passaria (a mais lenta leva 11 s). **Recomendo 20 s.**
