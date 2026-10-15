<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Lote Opus 7: revisão da pilha da T08 (PRs 28 a 34) e da T26 (PR 35)
- Autor: opus (papel Arquiteto/Revisor crítico) · Data: 2026-10-12 · Pedido: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_7/pedido.md`
- Revisado: `s03-t08-0` `9c9e3ef`, `s03-t08-a` `88fc505`, `s03-t08-b1` `0c1104b`, `s03-t08-b2` `5c4dff5`, `s03-t08-c` `8637942`, `s03-t08-d` `7e1624c`, `s03-t26` `d275a78`.
- Veredito curto: **1 aprovado, 2 aprovados no conteúdo (um espera ajuste de montagem, outro espera o anterior), 4 reprovados com correções curtas (um deles só no teste).** Nada entra no `main` hoje sem os passos do §4.

| PR | Cartão | Veredito |
|---|---|---|
| 28 | T08-0 (oráculo) | **Conteúdo APROVADO.** Como está montado não entra: conflito em `LOG.md` (§1.1) |
| 30 | T08-A (biblioteca híbrida) | **APROVADO** |
| 31 | T08-B1 (processo separado) | **REPROVADO**, 1 item (§1.3) |
| 32 | T08-B2 (limite por peça e caixa) | **REPROVADO**, 4 itens (§1.4) |
| 33 | T08-C (medição) | **Conteúdo APROVADO**; só entra depois do 32 |
| 34 | T08-D (memória) | **REPROVADO**, 1 item (§1.6) |
| 35 | T26 (vírgula decimal) | **Programa APROVADO; teste L3 REPROVADO** (falha no Windows do GitHub). Emenda exata no §2.2 |

## Resumo para o PO
1. **O que foi medido está certo.** Abri o seu arquivo real mais uma vez, em tela virtual: 42 s, 14.804 peças com malha e 6 sem, nenhuma virou caixa, nenhum processo sobrou. Bate com os relatórios. A suíte inteira passa na ponta da pilha (88 testes).
2. **A parte que troca a biblioteca (PR 30) está aprovada.** É ela que leva de 6 minutos para menos de 1.
3. **O limite de 20 s por peça tem três defeitos** que só aparecem quando alguma peça estoura o limite (no seu arquivo, com a biblioteca nova, nenhuma estoura). Dois deles nasceram da minha própria especificação, não de erro de quem implementou:
   - uma peça **sem geometria** pode ser acusada no lugar da peça lenta e aparecer como caixa laranja com o aviso errado;
   - peças lentas **repetidas pelo prédio** (a mesma poltrona em vários andares) são esperadas de novo a cada trecho do arquivo; com mais de 10 repetições espalhadas, a abertura termina em erro.
4. **A economia de memória (PR 34) tem um efeito colateral silencioso.** Se a janela 3D muda de lugar (outra janela, outro monitor com outra placa), **o modelo some da tela sem aviso**. Reproduzi: 5 pedaços na tela, 0 depois. A economia pode ficar; o sumiço calado não. A correção é o programa reabrir o arquivo sozinho.
5. **Vírgula decimal (PR 35): a correção funciona nos dois sistemas.** O passo que você autorizou no GitHub rodou e criou o português do Brasil na máquina de teste; os 8 testes rodaram no Linux. No Windows um teste falha, mas é o **teste** que está errado (erro meu na especificação): ele exigia número em formato brasileiro numa máquina configurada em inglês. A emenda está escrita no §2.2.
6. **O processo separado nunca rodou no Windows.** Os testes automáticos do GitHub só rodam em PR que aponta para o `main`, e os PRs 30 a 34 apontam um para o outro. Antes de qualquer merge da pilha, o líder abre um PR de rascunho da ponta para o `main`, só para ver Linux e Windows verdes.
7. **Não há pergunta para você.** Próximo passo: o líder abre um cartão de correção e um de testes novos; eu revejo só essa diferença no lote 8.

## 0. Como este lote foi feito
- Lido: o pedido, `arquivo/lotes-1-a-28/LOTE_OPUS_6/resultado.md` §2 e §3, `PO.md`, LOG, os dois relatórios de medição, os sete diffs, e por inteiro `carregador.py`, `processo_malhas.py`, `medir.py`, `adaptador.py`, `__main__.py` e o oráculo `test_viewport_processo.py`.
- Execução: três worktrees temporários no rascunho da sessão (ponta da pilha, B1 e T26), **já removidos**. Testes gráficos só em `xvfb-run` com desenho por software. Sondas no rascunho, fora do repositório. Nada instalado, nenhum commit, nenhum push, nenhum PR aberto.
- Arquivo real: aberto **uma vez**, só leitura, no lugar. Nada copiado nem enviado.
- Rede: `git fetch` e leitura de PRs e de logs do CI com `gh`.
- Máquina: 16 núcleos, 23 GB, Linux. **Nada foi medido por mim no Windows**; o que sei do Windows vem do log do CI do PR 35.

### Resultados das execuções
| Execução | Resultado |
|---|---|
| Suíte inteira na ponta (`7e1624c`), tela virtual, com os lentos | **88 passam, 6 pulam** (4 por falta do modelo de 1 milhão, 1 da T06 pesada, 1 emenda do R2). P1 a P12 todos, inclusive o P6 |
| Suíte inteira no B1 (`0c1104b`) | 84 passam, 10 pulam (P4, P5, P6 e P8 esperam o B2) |
| P3 (janela com peça de 3 s) | atraso máximo 15,5 ms, p95 0,3 ms (limites 200 e 33) |
| T26 local (`d275a78`), pt_BR de verdade | 8 de 8 passam; suíte inteira 75 passam |
| Arquivo real, `medir.py`, tela virtual | abrir 42,2 s; 14.804 / 6; 8.595.714 triângulos em 93 lotes; pico pai 1.063 MB + filho 5.783 MB = **6.846 MB**; maior soma ao mesmo tempo 6.450 MB; 0 caixas; 0 filhos sobrando; atraso máximo 409 ms (desenho por software, não vale como meta) |

Os números do relatório da T08-D (44,7 s, 6.933 MB, 411 ms) se repetem. A decisão do PO sobre a memória ("atingida na prática", valor final na S04) continua bem apoiada.

## 1. Item 1: pilha da T08

### 1.1 PR 28, T08-0 (oráculo): conteúdo APROVADO
**Resposta ao ponto (h):** o oráculo transcreve o §2.4 com fidelidade. Conferi caso a caso P1 a P12, as duas formas de peça lenta e as guardas.
- **Nenhum número da T05 foi afrouxado.** Fora o arquivo novo, o PR muda 3 linhas em `test_viewport_carregador.py` e 3 em `test_viewport_responsivo.py`, todas atrás de `TEM_PROCESSO`. Os PRs 30 a 34 não tocam em nenhum teste (`git diff --stat` vazio em `tests/`).
- **As duas emendas só valem com o processo.** O10 recebe `manter_arquivo=True` só se `TEM_PROCESSO`; o teste do fenômeno do GIL é pulado e o `xfail` do teste de 200 ms sai, os dois só se `TEM_PROCESSO`. Sem o processo, tudo fica como estava.

Lista:
1. **Montagem.** O ramo traz uma linha em `docs/state/LOG.md` (commit `9c9e3ef`) que **conflita com o `main`**; o GitHub marca o PR como "em conflito". É o mesmo problema do PR 19 no lote 6: arquivo de estado dentro de PR de código. Tirar o `LOG.md` do ramo.
2. Aprovo este conteúdo exato (confere-se com `git`): `tests/test_viewport_processo.py` `3b534c2cf4`, `tests/test_viewport_carregador.py` `6537b05de9`, `tests/test_viewport_responsivo.py` `fb60259d24`. Se algum precisar sair diferente, volta para o lote.
3. **Lacunas, todas da minha especificação e não do autor do oráculo.** Não reprovam o 28; viram o cartão de oráculo T08-0b (§4):
   - cópias da mesma família em **blocos diferentes** (o P5 só tem as duas no mesmo bloco);
   - produto **sem geometria** com id menor que o da peça lenta;
   - caixa de **sólido extrudado**;
   - `deslocamento` não gravável depois de passar pelo canal;
   - lotes perdidos na troca de contexto gráfico;
   - o P2 não vê o caso do §1.3 item 2 (filho que carrega o Qt por causa do módulo principal). A parte "separador decimal é ponto" do P2 roda com `LC_ALL=C` e por isso passa por construção; serve de registro, não de prova.
4. O P4 exige 15 s para três partidas de processo filho. No Linux leva 4 a 5 s. No executor Windows do GitHub ninguém mediu ainda (ver §1.7).

### 1.2 PR 30, T08-A: APROVADO
`carregador.py` `e4ed12993c`. D1 e D2 como especificados; 11 linhas. O oráculo congelado da T05 passa sem alteração.
- Observação sem peso: o `.copy()` das posições é redundante (o vetor pronto do IfcOpenShell já é uma cópia).

### 1.3 PR 31, T08-B1: REPROVADO (1 item)
O desenho segue o D3 ponto a ponto: contexto "spawn" também no Linux, um `Pipe` de mão única por filho, o pai fecha a ponta de escrita, nada de `multiprocessing.Queue`, contrapressão pelo canal, matar e esperar no cancelamento, pico do filho lido antes de matar, tabela de todos os produtos no `inicio`, peça maior que o lote dividida, `manter_arquivo` abrindo só depois do fim. Cancelar leva menos de 1 s (P7 e P10).

Lista:
1. **`deslocamento` chega gravável ao pai** (sonda: `vertices`, `indices` e `objetos` protegidos; `deslocamento` gravável). A proteção posta no filho se perde na passagem pelo canal, e `_tratar` só protege de novo os outros três. Isso desfaz o A-5, aprovado na T05. Correção: cópia protegida do `deslocamento` em `_tratar`, e o valor guardado para as reinicializações também protegido.

Observações que **não bloqueiam** (entram no mesmo cartão de correção ou no de seguimento):

2. **O filho carrega o Qt quando o programa é iniciado como script.** O "spawn" recarrega o módulo principal no filho. `medir.py` importa PySide6 no topo, então o filho de uma medição carrega 7 bibliotecas do Qt (sonda: 96 MB contra 65 MB sem Qt). Ele não cria aplicação Qt, e o efeito na memória medida é de uns 30 MB. `python -m viewport_qrhi` e `python -m openbim_app` **não** são afetados (conferi no código do Python: módulo principal de nome `__main__` de pacote não é recarregado). Remédio: importar o Qt dentro da função em `medir.py`. Vai no cartão do §3.1.
3. `_tratar` copia cada lote recebido (8 MB) antes de proteger. A cópia é desnecessária; basta proteger. Custo pequeno, na thread leitora.
4. `mensagens` e os tempos de filhos mortos se perdem; só o último filho informa. Informativo.
5. Nenhum ponto de entrada chama `multiprocessing.freeze_support()`. Só importa quando o filho for usado dentro do instalador do Windows (risco 2 do lote 6). Registrar no cartão de integração da S04.

**Ponto (g), `pico_memoria_mb(ident)` no Windows:** a leitura está correta no papel (o `Process.sentinel` é o identificador do processo com acesso total, e os tipos estão declarados). O P11 a exercita no Windows. **Mas o P11 nunca rodou lá**, porque este PR nunca passou pelo CI. Ver §1.7.

### 1.4 PR 32, T08-B2: REPROVADO (4 itens)
O que está certo: fase "convertendo" anunciada antes de criar o iterador; modo isolado com 1 thread só nos pendentes; caixa calculada num filho sem a biblioteca de geometria; cor laranja; `simplificadas` no resumo; regra de ouro mantida; teto de 20 reinícios; queda do filho tratada como peça lenta. P4, P5, P6 e P8 passam.

**Os itens 1 e 2 nascem da minha especificação D4. Não contam como falha do implementador para o escalonamento.**

1. **Peça errada acusada. Ponto (a): é pior do que "uma espera extra".**
   - Sonda: 3 peças normais, 1 parede defeituosa sem geometria (id 69) e 1 peça lenta (id 81).
   - Sem lentidão: a 69 aparece em `sem_malha`, como deve.
   - Com a lenta e limite de 1 s: a 69 vira **caixa laranja**, entra em `simplificadas` com "passou do limite de 1 s", some de `sem_malha`, e o resumo diz "2 peça(s) foram mostradas como caixa".
   - Causa: o D4 supôs que, com 1 thread, a peça em espera é sempre o menor id pendente. O iterador pula em silêncio os produtos sem geometria, então o menor id pendente pode ser um deles.
   - Correção, a escolher no cartão: (i) no modo isolado, um iterador por peça, medindo o custo; ou (ii) confirmar a acusada sozinha num filho antes de trocá-la por caixa. Em qualquer das duas, produto sem geometria termina em `sem_malha` com o motivo verdadeiro.
2. **A regra da mesma família só vale dentro do bloco em curso.**
   - Sonda A: 2 cópias em 2 blocos. As duas esperaram o limite inteiro (1,0 s cada), em vez de a segunda virar caixa sem espera.
   - Sonda B: 12 cópias em 12 blocos. A carga terminou em **`erro`** ("precisou reiniciar mais de 20 vezes"), com 10 de 12 peças.
   - Cada peça lenta custa 2 reinícios (o rápido e o isolado), então o teto de 20 significa cerca de 10 peças lentas por arquivo.
   - Correção: ao condenar uma peça, todas as peças **ainda não resolvidas do arquivo inteiro** com o mesmo item mapeado viram caixa sem nova tentativa (o pai já tem a tabela completa). Rever a contagem do teto para não punir cópias.
3. **Ponto (b): cubo na origem.** Se o filho da caixa cai ou estoura, a peça vira um cubo de 0,5 m no ponto zero do mundo, não na posição do objeto. Num modelo com coordenadas grandes, isso estica a caixa da cena e estraga o enquadramento. Correção: nesse caso a peça vai para `sem_malha` com motivo claro (a regra de ouro continua valendo), ou o cubo vai para o centro do primeiro lote. Prefiro a primeira.
4. **Ponto (c): o caminho do sólido extrudado não funciona nas paredes comuns.**
   - Sonda no modelo de paredes e aberturas do próprio oráculo: **as 21 paredes** caíram no cubo de 0,5 m, com desvio de 2,75 m (uma delas 59,75 m).
   - Causa (conferida): o perfil das 21 é `IfcArbitraryClosedProfileDef` com curva `IfcIndexedPolyCurve`, que é o que a API do IfcOpenShell grava; o código só aceita retângulo e `IfcPolyline`.
   - Lido no código, sem sonda: o retângulo ignora a posição própria do perfil, e `Position` vazio derruba a peça inteira no cubo.
   - O D4.1 pedia a extrusão. Correção: aceitar a curva indexada (só trechos retos), a posição do perfil e `Position` vazio, com um caso no oráculo exigindo 1 cm. Qualquer outro perfil continua no cubo.

Observações que **não bloqueiam**:

5. **Ponto (d):** `produtos_feitos` e `indice_lote` reescritos pelo pai. **Aceito.** Com vários filhos por carga só o pai pode numerar. `produtos_feitos` agora cresce a cada lote (antes repetia o valor do bloco), o que é melhor para a barra de progresso.
6. **Ponto (e):** a linha extra "N peça(s) ... porque o conversor caiu nelas". **Aceita.** Separa bem os dois motivos.
7. No modo isolado cada peça sai num lote próprio. Um bloco de 1.000 pendentes vira 1.000 lotes e 1.000 chamadas de desenho. Agrupar por tempo (por exemplo a cada 0,2 s) no cartão de correção, se couber.
8. Exceção do iterador no meio de um bloco ainda marca o resto do bloco como "sem malha" (comportamento herdado da T05). Agora que existe o modo isolado, o certo é mandar esses pendentes para ele. Registrar para a S04.

### 1.5 PR 33, T08-C (T2): conteúdo APROVADO
`medir.py` `26eb3fd9a4` e `F0-S03-T08.md` `497a79328b`.
- O D5 está implementado como especificado: pico somado = pico do pai + maior pico entre os filhos; conferência pelo `RUSAGE_CHILDREN`; soma amostrada a cada 0,25 s só como informação (no Windows ela sai zero, o que está dito no código).
- O relatório é fiel: repeti a medição e os números batem. As duas metas não atingidas foram levadas ao PO com opções, sem contorno.
- Só entra depois do 32, porque está empilhado nele.
- Observação: as duas imagens da comparação lado a lado ficaram em `/tmp/t08-imgs/` e somem ao reiniciar a máquina. Se o PO ainda não olhou, gerar de novo.

### 1.6 PR 34, T08-D: REPROVADO (1 item)
O que está certo: o limite de 8 fios por padrão e a liberação de vértices e índices depois do envio à placa (o Qt copia os dados no envio; a imagem não muda). O ganho medido (pai de 1,7 para 1,05 GB) se repete.

1. **Ponto (f): a troca de contexto gráfico apaga o modelo em silêncio.**
   - Sonda, a mesma do lote 6 (mudar o widget de janela), agora com o padrão novo: antes 5 lotes e 3 cores na imagem; depois **0 lotes e 1 cor**, `lotes_perdidos=5`. Com `liberar_apos_envio=False`: 5 lotes antes e depois.
   - Ninguém é avisado: só um contador muda. A caixa da cena fica com o valor antigo. Isso desfaz, na configuração padrão, o B-3 que aprovei no lote 6, e nenhum teste percebe.
   - **Resposta:** a troca de memória por reenvio é aceitável no protótipo; o silêncio não é.
   - Correção mínima: o viewport emite um sinal quando perde lotes e zera a caixa da cena; o `AdaptadorCarga` reabre o arquivo sozinho (ele já sabe o caminho e as opções). Um teste em tela virtual com a sonda acima.
   - **Manter `liberar_apos_envio=True` como padrão.** É com ele que saiu o número de memória que o PO aceitou.

Observações:

2. O comentário de `adicionar_lote` ainda diz que a seleção usa `pos` e `indices` do lote. Com a liberação ela só tem as caixas e os ids. Consequência para a S04: a seleção precisa vir da placa ou das caixas, não dos triângulos guardados no programa. Registrar no ADR-004.

### 1.7 O Windows bloqueia a pilha
Os PRs 30 a 34 **não têm nenhuma execução de CI**: o fluxo só dispara em PR para o `main`. O PR 28 rodou, mas com os testes do processo pulando pela guarda. Então "spawn", o canal, matar o filho, o `sentinel` do ponto (g) e os tempos do P4 e do P7 **nunca rodaram no Windows**. Pedi o PR de rascunho no lote 6 (§1.5) e ele não foi aberto.

**Pré-condição para qualquer merge da pilha, inclusive o 28:** um PR de rascunho da ponta (`s03-t08-d`, e depois com a correção) para o `main`, com `linux` e `windows` verdes. Fazer **agora**, antes do cartão de correção, para que o que o Windows mostrar entre no mesmo cartão. Se o Windows pedir mudança em teste, volta para o lote.

## 2. Item 2: T26 (PR 35)

### 2.1 Programa: APROVADO
`localidade.py` `7bbaa25af9`, `main.py` `6ef282831c`, `ci.yml` `562eccf7fc`, `dev-setup.md` `008d1bac7d`.
- As quatro funções são as do §3.2. A correção vem na linha seguinte à criação da aplicação. O `--selftest` passa a exigir o separador certo. `QApplication(` só aparece em `localidade.py`.
- **O passo do CI autorizado pelo PO rodou.** O aviso do job `linux` diz "localidade pt_BR: criada", e o resumo foi de 67 para **75 testes passando** (os 8 da T26 rodaram de verdade, não pularam).
- **No Windows a correção também funciona:** o canário L1w, o L2, o L4 e o L5 passaram lá (73 passam, 1 falha). Isso responde a metade do risco 4 do lote 6: o IfcOpenShell do Windows enxerga a vírgula forçada, e a correção a desfaz. Se o Qt troca a localidade sozinho no Windows continua sem verificação (o L1 é só do Linux).
- O filho da T08 confere e corrige o separador ao iniciar (`processo_malhas.entrada`), como pedia o item 4 do §3.2.

Observações que não bloqueiam:
1. `localidade.py` importa o Qt no topo. Quando a gravação de IFC existir (S05), ela vai chamar `garantir_numerico_c()` de um módulo que não deveria depender do Qt. Separar então as três funções puras num módulo sem Qt.
2. O `pytest -q` do CI não mostra o motivo dos testes pulados. No Linux há o aviso do passo; no Windows, se um dia a localidade com vírgula faltar, os testes pulam sem ninguém ver. Trocar por `pytest -q -rs` num cartão pequeno.
3. O `sudo update-locale` do passo é desnecessário; inofensivo.

### 2.2 Oráculo: REPROVADO em 1 item (L3), com emenda exata
- **O job `windows`, obrigatório, está vermelho:** `assert '1,234.50' == '1.234,50'` em `test_l3_interface_continua_brasileira`. No `macos` falha igual.
- **O erro é meu (§3.3 do lote 6).** No Windows e no macOS o Qt formata pelo idioma do sistema, não pela localidade do C que o teste força. A máquina do GitHub está em inglês. O programa está certo; o teste exigia o impossível.
- L1, L1w, L2, L4, L5 e L6: aprovados como estão.

**Emenda que aprovo, exata** (testada aqui nos dois ramos do `if`: 8 de 8 passam). Fora do Linux, o L3 passa a comparar com um processo **sem** a correção: a correção não pode mudar o que a interface mostra.

```diff
--- a/tests/localidade_aux.py
+++ b/tests/localidade_aux.py
@@ -69,6 +69,13 @@ def caso(nome, tmp):
         QApplication([])
         r["depois"] = ponto_decimal()
         r["texto"] = texto_ifc().to_string()
+    elif nome == "l3ref":  # interface SEM a correção: é com ela que o L3 compara fora do Linux
+        from PySide6.QtCore import QLocale
+        from PySide6.QtWidgets import QApplication
+
+        QApplication([])
+        r["fmt"] = QLocale().toString(1234.5, "f", 2)
+        r["nome_qt"] = QLocale().name()
     elif nome == "l1w":  # força à mão, sem a correção e sem Qt
         r["nome"] = forcar_virgula()
         r["ponto"] = ponto_decimal()
--- a/tests/test_localidade.py
+++ b/tests/test_localidade.py
@@ -19,6 +19,7 @@ AUX = Path(__file__).resolve().parent / "localidade_aux.py"
 TEM_MODULO = (APP / "openbim_app" / "localidade.py").exists()
 AGUARDA = pytest.mark.skipif(not TEM_MODULO, reason="aguarda S03-T26: localidade.py")
 WIN = sys.platform == "win32"
+LINUX = sys.platform.startswith("linux")
 
 
 def ambiente(pt_br=True):
@@ -105,11 +106,14 @@ def test_l2_gravacao_identica_a_processo_em_c(canario_windows_ok, referencia):
 @AGUARDA
 def test_l3_interface_continua_brasileira(canario_windows_ok):
     r = caso("l3")
-    assert r["fmt"] == "1.234,50"
-    assert r["nome_qt"] == "pt_BR"
     assert r["numerico_ok"]
-    if not WIN:  # datas e textos não mudam: as categorias seguem a do ambiente, só a numérica vira C
+    if LINUX:  # no Linux o Qt segue o ambiente (pt_BR): valores exatos; datas e textos não mudam
+        assert r["fmt"] == "1.234,50"
+        assert r["nome_qt"] == "pt_BR"
         assert "pt_BR" in r["time"] and "pt_BR" in r["ctype"], r
+    else:  # Windows e macOS: o Qt segue o idioma do sistema; a correção não pode mudar o que a interface mostra
+        ref = caso("l3ref")
+        assert (r["fmt"], r["nome_qt"]) == (ref["fmt"], ref["nome_qt"]), (r, ref)
 
 
 @AGUARDA
```

**Regra para o líder, sem nova rodada minha:** quem aplica é um subagente de oráculo (não o implementador da T26). O PR 35 entra quando (a) o diff dos dois arquivos de teste contra `d275a78` for exatamente o de cima, (b) os outros quatro arquivos continuarem com as impressões digitais do §2.1 e (c) `linux` e `windows` estiverem verdes. **Se o Windows continuar vermelho depois da emenda, ou se qualquer outra linha precisar mudar, volta para o lote.**

O `macos` também falha no R1a (p95 de 96 ms contra 33). É a oscilação de tempo já conhecida, sem relação com a T26, e não bloqueia.

## 3. Item 3: seguimento (dois cartões a abrir)

### 3.1 Cartão T26b: localidade nos protótipos (T1, depois do merge da pilha)
- Arquivos: `prototypes/viewport_qrhi/__main__.py` e `prototypes/viewport_qrhi/medir.py`.
- O quê: logo depois de criar o `QApplication`, `locale.setlocale(locale.LC_NUMERIC, "C")`. Os protótipos não importam `openbim_app`; é a linha direta.
- No mesmo cartão, em `medir.py`: levar os imports do PySide6 e do `cubo_rhi` para dentro das funções que usam, para o filho não carregar o Qt (§1.3 item 2).
- Aceite: um caso em subprocesso, com pt_BR e sem `LC_ALL`, que importa `medir`, cria a aplicação pelo caminho do script e confere o ponto decimal; e a sonda do filho sem Qt.
- Menos de 30 linhas.

### 3.2 Cartão para a S05: aviso ao abrir IFC já estragado (T2, especificar na S05)
- Sinal do estrago: ponto cartesiano com mais de 3 coordenadas, direção com mais de 3 razões, ou linha de lista de pontos 3D com tamanho diferente de 3. O esquema proíbe os três, e é exatamente o que a vírgula produz (um ponto de 3 vira 5 ou 6; um de 2 vira 4).
- Onde: no processo filho, na fase "listando", por amostra (os primeiros 2.000 pontos bastam para o aviso; a contagem completa fica para o relatório).
- O quê: mensagem em português simples no resumo da carga ("este arquivo parece ter sido gravado com vírgula decimal; as medidas podem estar erradas") e a contagem. **Não consertar sozinho:** `2799,9999.,0,5.` não diz onde cada número termina.
- Oráculo: o arquivo estragado do L1 da T26 dispara o aviso; os modelos da T05 não disparam.

## 4. Para o líder
1. **Agora:** PR de rascunho da ponta da pilha para o `main`, só para ver `linux` e `windows` (§1.7). Não mesclar. **Atenção:** o GitHub não roda os testes de um PR em conflito, e `s03-t08-d` carrega a mesma linha de `LOG.md` que deixa o PR 28 em conflito (os testes do 28 são das 14:28 UTC; o `main` andou às 15:34 UTC). Abrir o rascunho de um ramo descartável igual a `s03-t08-d` com o `docs/state/LOG.md` do `main`, ou fazer antes o passo 2 e reempilhar.
2. **PR 28:** tirar o `LOG.md` do ramo e conferir as três impressões digitais (§1.1). Entra depois do rascunho verde.
3. **PR 30:** entra depois do 28, com `linux` e `windows` verdes. Os dois são T3: pelo `CLAUDE.md`, o PO dá o ok antes do merge.
4. **PR 35:** aplicar a emenda do §2.2 por subagente de oráculo; entra pela regra do §2.2. É T3 já revisada: o merge segue a regra do `CLAUDE.md` (o PO aprova antes).
5. **Cartão de oráculo T08-0b (T3, subagente diferente do implementador):** casos novos em `tests/test_viewport_processo.py`, atrás das guardas que já existem ou de guardas novas:
   - P13: cópias da mesma família em blocos diferentes. 12 cópias com `tamanho_bloco=1`: estado "concluido", 12 em `simplificadas`, e tempo total de uma única espera (mesma conta do P5);
   - P14: produto sem geometria com id menor que o da peça lenta: ele fica em `sem_malha`, só a lenta em `simplificadas`;
   - P15: caixa de sólido extrudado dentro de 1 cm, com as paredes do modelo de paredes e aberturas e uma parede de perfil retangular;
   - P16: `deslocamento` não gravável em todo lote, inclusive nos de caixa e nos de reinício;
   - P17 (tela virtual): depois de mudar o widget de janela com a liberação ligada, o sinal é emitido, a carga recomeça sozinha e a cena volta com o mesmo número de triângulos;
   - P18: filho da caixa que falha (gancho de teste novo): a peça vai para `sem_malha` e a regra de ouro vale.
6. **Cartão de correção T08-E (T3, em cima do `s03-t08-d`, menos de 400 linhas):** §1.3 item 1, §1.4 itens 1 a 4 e §1.6 item 1. Se couberem, as observações 3 do §1.3 e 7 do §1.4. Se passar de 400 linhas, separar a parte do viewport (§1.6) num T08-F.
7. **Ordem de merge:** rascunho verde → 28 → 30. Os PRs 31, 32, 33 e 34 esperam o T08-E e entram juntos, na ordem, **depois** de eu rever o T08-E e o T08-0b no lote 8. O lote 8 tem contexto pequeno: os dois diffs e o resultado do CI nos dois sistemas.
8. **Escalonamento:** registrar no LOG que as reprovações dos itens 1 e 2 do §1.4 e a do L3 vêm da especificação do Opus. Não contam como falha do sonnet.
9. `LOG.md` conflita também entre a pilha e o `s03-t26` e entre a pilha e o `estado-t08a`. Manter arquivos de estado só no PR de estado.
10. Este arquivo foi escrito **sem commit**, na pasta principal, no ramo `estado-t08a` (árvore limpa antes).

## 5. Perguntas ao PO
Nenhuma. As decisões já tomadas (biblioteca híbrida, limite de 20 s, memória "atingida na prática", passo do pt_BR no GitHub) continuam valendo e não precisam ser revistas por causa deste lote.
