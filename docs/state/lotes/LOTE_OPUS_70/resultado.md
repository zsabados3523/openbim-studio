<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_70: resultado (revisão do PR 243, T23e, e dos oráculos dos PRs 245, 246 e 247, V1 e P1; opus, esforço médio, 2026-10-21)
**Independência.** Sou uma sessão nova. Não escrevi o T23e nem os oráculos: os oráculos são do Opus do lote 69 (outra sessão), e o lote 69 não é trabalho meu. Li o pedido (`s04-lote-70-pedido`), os cartões T23e (main), V1, V1b e P1 e o `LOTE_OPUS_69/resultado.md` (PR 244), o ADR-004 §5 e §5.1 e os diffs `origin/main...<ramo>` dos PRs 243, 245, 246 e 247. Também li os logs dos trabalhos do CI pelo `gh api`. Não li `~/openbim-medicao` nem IFC.
Construí o `obimcore` só no rascunho da sessão. A referência de `sessao_modelo.py` e os mutantes descritos abaixo foram meus e temporários: ficaram no rascunho, e a cópia posta em `app/` foi apagada. Os quatro oráculos copiados para `tests/` também foram apagados. `git status` limpo, salvo este arquivo. Nada de commit, push ou merge.

## Veredito por PR
| PR | Veredito |
|---|---|
| 243 (T23e, instalador) | **APROVADO** (conteúdo do ramo em `398006f`). A errata do relatório fica registrada aqui (§1, E1 e E2) e não bloqueia. |
| 245 (oráculo V1, forma mista) | **REPROVADO**: 1 item (§2.1). |
| 246 (oráculo V1 veredito e P1 obimcore) | **REPROVADO**: 2 itens (§2.2). |
| 247 (oráculo P1, trava) | **REPROVADO**: 1 item (§2.3). |
Os três reprovados pedem só casos **a mais** (nada afrouxado, nenhum caso removido). O contrato dos cartões V1 e P1 não muda, então os implementadores podem começar já em ramo próprio.

## 1. PR 243 (T23e)
Evidência lida dos logs (`gh api repos/zsabados3523/openbim-studio/actions/jobs/<id>/logs`). Esses logs existem: o relatório diz que não estavam disponíveis, e estavam. Trabalhos do `instalador-windows`: 119211520438, 119326087613 e 119341818979 (execução 39596204251, tentativas 1 a 3). Base no main: 119212165759 (execução 39596128352).
| Medida | main (antes) | T23e, rodadas 1 / 2 / 3 | Critério |
|---|---|---|---|
| `build_installer.sh` inteiro | 338 s | 83 / 89 / 56 s (`tar\|gzip` 33 / 38 / 25 s; `makensis` 5 / 6 / 4 s) | ganho ≥ 60 s: sim, nas 3 |
| Instalador | 310.596.916 B | 313.805.997 / 313.802.994 / 313.805.914 B (**+1,03%**) | ≤ +5%: sim |
| Instalação no teste do instalador | 47 s (3 vezes) | 15 a 16 s | não piorar mais que 15 s: **melhorou 31 s** |
| Instalação no R1-j | 43 s | 11 / 11 / 8 s | — |
| Ambiente descompactado / destino instalado | 904M / 910 MB | 904M / 910 MB | igual |
| Licenças | 169 com arquivo, 8 sem | 169 com arquivo, 8 sem | igual |
| R1-j e teste do instalador | verdes | verdes nas 3 | sim |
(a) **Conteúdo idêntico: a evidência basta.** O gzip, em qualquer nível, e o NSIS com `SetCompress off` não perdem nada. O SHA-256 do fluxo do tar cobre nomes, conteúdo e metadados de todos os arquivos do ambiente. O CI confirma pelos tamanhos iguais (904M e 910 MB), pela mesma contagem de licenças e pelo R1-j verde. O resto do pacote (~7 MB) continua em LZMA, só que não sólido: também sem perda. Não foi produzida a lista literal "arquivo + hash" do instalado antes e depois (critério 1 ao pé da letra). Ela não acrescenta nada: o ambiente é refeito pela trava a cada execução, e a mudança não toca em nenhum byte de entrada.
(b) **`SetCompress off` sem `/SOLID` é seguro.** Com `/SOLID`, o `SetCompress` não vale por arquivo, por isso tirar o `/SOLID` está certo. A prova de que o `env.tgz` foi guardado sem recompressão é direta: o `makensis` leva 4 a 6 s para 298 MB, antes eram ~150 s de LZMA, e o instalador ficou com o tamanho do `env.tgz` mais ~16 MB. O instalador instala, abre, reinstala e desinstala sem sobras nas 3 rodadas. `SetCompress auto` volta logo depois da linha. Sobra um custo: sem `/SOLID`, o dicionário LZMA de 64 MB vale por arquivo, só para ~7 MB. É irrelevante.
(c) **Nenhum teste removido nem com limite maior.** O diff toca só `packaging/windows/build_installer.sh`, `openbim-studio.nsi` e o relatório. O `ci.yml` está idêntico ao do main, então os checks obrigatórios seguem os mesmos. `scripts/conferir_ci_windows.py` rodou aqui: "ok". O limite de 600 MB do passo não mudou.
(d) **Tamanho e tempo de instalação: lidos acima. Não precisa pedir nada antes do merge.**
Errata do relatório `F0-S04-T23e.md` (registrada aqui, não bloqueia):
- E1. "Nenhum outro CI ao mesmo tempo" é falso na rodada 1. A tentativa 1 (12:00 a 12:37) correu junto com o main 39596128352 (12:01 a 12:37), e no começo também com as execuções 39593797600 e 39589194369. As rodadas 2 (15:50 a 16:21) e 3 (16:21 a 16:57) correram sozinhas. Isso não muda o veredito: o tempo do script roda numa máquina própria e caiu de 338 s para 56 a 89 s em todas as rodadas.
- E2. Os números de tamanho e de instalação estão na tabela acima. O relatório diz "não medidos" porque achou que o log estava indisponível.
O líder pode corrigir o relatório depois, numa tarefa T0, com estes números.

## 2. Oráculos (PRs 245, 246, 247)
Rodei no Linux, sob `xvfb-run -a`, com o `obimcore` do main (0f86eec) no rascunho e as chaves `OBIM_S04_V1_OBRIGATORIO=1` e `OBIM_S04_P1_OBRIGATORIO=1` ligadas: **4 passaram, 28 em falha esperada, 0 pulos, 18 s**. Isso bate com o lote 69. Do jeito do passo geral do CI (`pytest tests`, sem `obimcore`, sem chave): 2 passaram, 12 pularam, 18 em falha esperada, 9 s. O ensaio do V1 roda sem `obimcore` e entra nesse passo.
Validei a trava contra uma referência minha de `sessao_modelo.py`, escrita sem ver a do lote 69: **11 de 11**, ou seja, o oráculo não tem defeito que reprove uma implementação correta. Com os mutantes: "leitor fura a preferência do escritor" foi pego; "espera com limite que deixa `esperando_escrever` sujo" foi pego; "**qualquer thread entra no C++ se houver um leitor**" **não foi pego** (§2.3). O mutante "escritor entra sem esperar `em_uso_cpp`" também não foi pego, mas é equivalente: pelo contrato, `em_uso_cpp > 0` só acontece com a própria thread dentro de `ler()` ou durante o empréstimo, cuja saída já espera.
Os marcadores seguem o padrão do T30d3: `AINDA_NAO = pytest.mark.xfail(strict=True, reason=...)` e um `@AINDA_NAO` por teste. Estão só nos casos que dependem da implementação. Os quatro sem marcador passam hoje: critério 1 por sha256, ambiente, regra 9 e caminho do arquivo no `obimcore`. Quando falta ambiente com a chave ligada, o teste sem marcador falha, e o xfail não esconde isso: está bem desenhado.

### 2.1 PR 245 (`test_s04_v1_mista_oraculo.py`): REPROVADO
1. **A regra 2 do §5.1 ("o resultado volta por sinal enfileirado do Qt") e o item 1 do cartão (`QEventLoop.exec()` mais o sinal `QueuedConnection`) não têm teste que os prove.** Uma espera do tipo `while th.is_alive(): app.processEvents(); time.sleep(...)` passa em todos os casos. A regra 2 só conta pulsos e mouses. A regra 5 ignora o `SignalInstance.emit` em vez de contá-lo, e só olha construção fora da janela. O erro e o composto não olham o mecanismo. A espera ocupada muda o que o V1 mede (disputa do bloqueio do interpretador e uso de processador), então precisa de teste. Pedido, só acréscimos:
   - em `_perfil`, contar o `SignalInstance.emit` feito na thread `lote-geometria` e exigir pelo menos 1 por pedido de geometria (`len(geometria)`), no ensaio e no caso de erro;
   - pelo espião de `QEventLoop`, que já existe, registrar a construção na thread da janela durante o comando, ou o `exec`, e exigir pelo menos 1 por pedido;
   - no caminho de sucesso, que hoje só é olhado no erro, exigir também que nenhuma `lote-geometria` fique viva depois de `medir` (o `join` do cartão).

### 2.2 PR 246: REPROVADO
1. **`test_s04_v1_veredito_oraculo.py`: os 8 casos sintéticos não provam o critério 5 nem as fronteiras que o próprio cabeçalho anuncia.** Rodei mutantes da conta independente contra os 8 casos, e **nenhum foi pego**:
   - (a) M5 aceitando 1 rodada acima de 200 ms, a tolerância da régua do T15b. É justamente a "interseção" que o lote 69 §6.3 dá por resolvida, e o ADR pede "maior intervalo < 200" em toda rodada;
   - (b) sem a exigência de 20 quadros ou mais por janela (todos os casos usam 40 e 41);
   - (c) sem a regra "mediana ≤ 3 × max(33,3; parado)";
   - (d) `<=` no lugar de `<` no 200 e no limite do M5;
   - (e) `4_controle_1s` com `<=` 1.000;
   - (f) `4_surda` com `<` 1.000.
   O `test_v1_main_mista` compara o veredito com dados reais, mas só pega isso por acaso. Pedido: acrescentar casos sintéticos que virem cada regra sozinha e atualizar a sentinela de `ok`:
   - uma rodada da mista a 210 ms com as outras a 30 (reprova só `5_m5_mista`);
   - uma janela com 19 quadros (reprova);
   - estrito, maior 150 e parado 17, com 150 > 3 × 33,3 (reprova só pelo 3×);
   - maior exatamente 200 numa rodada (reprova);
   - mediana exatamente 100 fora do estrito (reprova);
   - controle da mista com mediana exatamente 1.000 e pior rodada da forma 2 ≥ 1.000 (reprova só `4_controle_1s`);
   - `pulso_maior_ms` exatamente 1.000 numa rodada (passa `4_surda`).
2. **`test_s04_p1_obimcore_oraculo.py`: a armadilha do cartão P1 "`_obimcore_sair` depois de `emprestar` falhar (tipo errado devolvido) também conta" não tem teste.** O único caso de erro é o GlobalId inválido, que falha na geometria, depois do empréstimo. Se o C++ esquecer o `_obimcore_sair` nesse outro caminho, `em_uso_cpp` fica preso em 1 e a saída do empréstimo espera para sempre: é um travamento no produto. Pedido: uma sessão falsa (classe Python que não é `ifcopenshell.file`, com `_obimcore_entrar` que devolve `object()` e `_obimcore_sair` que conta) e `obimcore.malhas(falsa, leves)`. Esperado: `TypeError` e `_obimcore_sair` chamado exatamente 1 vez. Também convém um `_obimcore_entrar` que levanta erro: a exceção sobe igual e `_obimcore_sair` não é chamado.
**Ordem: o CI `linux` do 246 está vermelho hoje** porque o arquivo importa `test_s04_v1_mista_oraculo` (`ModuleNotFoundError` na coleta), e esse arquivo só entra no 245. Não é defeito de conteúdo: o 246 só entra depois do 245, com o main trazido para o ramo e o CI verde.

### 2.3 PR 247 (`test_s04_p1_trava_oraculo.py`): REPROVADO
1. **A porta do C++ não é testada com "OUTRA thread enquanto um leitor segura `ler()`".** O contrato manda `TravaNaoSegura` nesse caso: a thread que chama não segura a porta e não há empréstimo. O mutante "qualquer thread entra se houver leitor" passou 11 de 11. O risco: o leitor sai com o C++ de outra thread ainda lendo, e um escritor entra, porque o contrato não manda o escritor esperar `em_uso_cpp`. Pedido: thread A dentro de `ler()`, thread B sem porta chama `_obimcore_entrar()`. Esperado: `TravaNaoSegura`, com `estado()` igual antes e depois.
Recomendação que não bloqueia: o cartão diz "reentrada com `espera=None` tem de falhar na hora". O teste usa 0 e 0,5 s para não travar o pytest. Um caso com `None`, rodado numa thread com `join(2)`, cobre isso sem risco.

### 2.4 Respostas do ponto 2
- **Exigência por exigência.**
  - Cobertas: regras 2 (comportamento), 3, 4 e 5 do §5.1; erro na geometria; composto; critério 1 (intactos); critérios 3, 4 e 6 pelo veredito; P1 com várias leituras, escritor exclusivo, preferência do escritor, reentrada, exceção, empréstimo, a porta do C++ (salvo §2.3), a saída do empréstimo esperando o C++, carga de 2 escritores e 4 leitores com 200 e 400 voltas, R1-h pela sessão abaixo de 50 ms e a regra 9.
  - Faltam: §2.1 (mecanismo do sinal), §2.2 itens 1 e 2, §2.3.
  - Fora do oráculo, com razão: a regra 1 (comando curto direto, que fica para o I1); a regra 6 (ordem das travas: o revisor lê no diff que o C++ não pega a trava do modelo); os critérios 2, 7 e 8, que são medição do cartão; o M5 da parte "pesada" (o cartão liga o critério 5 só à parte "lote"; não vejo risco, porque o M5 mede a thread de desenho em C++).
- **Afrouxado ou redundante:** nenhum caso afrouxado. A régua M5 do veredito é mais dura que a do T15b, como o ADR manda; o problema é só que ela não é provada (§2.2). Há pouca redundância: o ensaio roda as regras num só subprocesso, e o caso real repete as regras 3 e 4 com o modelo de verdade, o que é útil.
- **Tela virtual:** os casos `ensaio`, `real` e `main` do V1 rodam em subprocesso sob `xvfb-run -a` no Linux; no Windows, só com `CI` ou `OBIM_S04_TELA_VIRTUAL=1`; nunca na tela real. Os dois do P1 não abrem janela.
- **O que o CI passa a rodar e quanto custa:**
  - Já com o merge dos oráculos, sem a implementação, o passo geral `pytest tests` do `linux` e do `windows-testes` coleta os quatro arquivos e roda o ensaio do V1 em subprocesso. São ~9 s no Linux local. No Windows não medi; estimo de 15 a 30 s, na fila crítica (17 a 18 min).
  - Com a implementação e as linhas próprias de cada cartão, são ~46 s por job no Linux (lote 69) e o ensaio roda **duas vezes** por job: no passo geral e na linha própria.
  - Sugestão ao líder, que é decisão de guarda e não de oráculo: na linha própria rodar só os casos com `obimcore`, ou deixar o geral pular o V1 no Windows. Mexer só na guarda não muda o oráculo.
  - **Não vi o `windows-testes` dos PRs 245 e 247 terminar.** Estava pendente quando conferi pela última vez. Precisa estar verde antes do merge.
- **XPASS estrito com implementação parcial: sim, e é esperado.** Cada teste vira XPASS e fica vermelho assim que a sua parte funciona. Exemplos:
  - o V1 com a mista funcionando e o composto ainda faltando: o ensaio inteiro dá erro e tudo fica em falha esperada; com o composto pronto, os testes que já passam ficam vermelhos;
  - `test_v1_main_mista[lote]` e `[pesada]` saem separados;
  - o P1 com `sessao_modelo.py` pronto e o C++ ainda não: os 10 testes da trava viram XPASS, e os 6 do `obimcore` seguem em falha esperada.
  Por isso o autor do oráculo tira os marcadores **por teste**, não por arquivo, e no mesmo ramo da implementação, antes do merge. O PR de implementação fica vermelho até esse commit, e isso é o desenho, não defeito. Não vejo XPASS que possa vir de outro PR: o critério 1 congela só o que o V1b não toca.

## 3. Ordem de merge e marcadores
1. **243** a qualquer momento (aprovado; independe do resto; CI da última execução verde).
2. **244** (cartões e lote 69, só texto).
3. Um Opus no papel de autor do oráculo, que não sou eu, aplica §2.1, §2.2 e §2.3. São acréscimos pequenos, ~60 a 90 linhas no total, e cada PR continua com ≤ 400 linhas. Depois, uma revisão Opus curta desses acréscimos, que pode ir num lote com outra coisa do mesmo módulo. Só então os merges, nesta ordem:
   - **245**;
   - **246**, com o main trazido para o ramo depois do 245 e o CI verde;
   - **247**, que independe dos outros.
4. Os implementadores do V1 e do P1 podem começar já, em ramo próprio: o contrato não muda.
5. **Marcadores:** quem tira é o autor do oráculo, em commit próprio, no ramo da implementação, só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`, teste por teste. Cuidado: `test_s04_v1_veredito_oraculo.py` **importa** `AINDA_NAO` do arquivo da mista. Apagar a definição no arquivo da mista quebra a coleta do outro. Os marcadores do V1 saem dos dois arquivos no mesmo commit, e a definição fica até o último sair, ou a linha do import também pode ser editada. Depois, o lote Opus revisa a implementação antes do merge (T3).

## 4. Perguntas ao PO
Nenhuma. Tudo aqui é técnico e cabe ao líder. As perguntas do lote 69 (arquivo do V1b e horário da placa) continuam de pé.

## 5. Resumo para o PO (5 linhas, sem siglas)
1. A mudança que acelera a montagem do instalador do Windows está aprovada: o programa instalado é o mesmo, o instalador cresceu só 1% e a instalação ficou mais rápida (de 47 para 16 segundos).
2. A montagem em si caiu de mais de 5 minutos para cerca de 1 minuto e meio.
3. Os testes automáticos das próximas duas tarefas (a forma mista e a porta única do modelo) estão bons no geral, mas pedi alguns casos a mais antes de entrarem.
4. Sem esses casos, três erros possíveis passariam sem ninguém ver; um deles poderia deixar o programa parado.
5. Não preciso de nenhuma decisão sua agora; o trabalho de programar as duas tarefas pode começar em paralelo.

## 6. Linha do LOG
`2026-10-21 | F0-S04-T23e, V1, P1 | LOTE_OPUS_70 (opus, médio, T3 revisão) | PR 243 APROVADO (script 338 s -> 56-89 s; instalador +1,03%; instalação 47 s -> 15-16 s; errata do relatório: rodada 1 com outro CI ao mesmo tempo); PR 245 REPROVADO 1 item (mecanismo do sinal enfileirado sem teste); PR 246 REPROVADO 2 itens (6 mutantes do veredito não pegos; _obimcore_sair no erro do empréstimo sem teste; ordem: depois do 245); PR 247 REPROVADO 1 item (outra thread com leitor ativo); oráculos hoje 4 passam, 28 em falha esperada, 0 pulos; referência da trava do revisor 11/11 | docs/state/lotes/LOTE_OPUS_70/resultado.md`
