# Lote Opus 10: revisão da etapa 1 da S04 (T02 oráculo, T03 módulo, T04 malhas)
- Revisor: opus, contexto fechado e só leitura. Data: 2026-10-12.
- Material lido: CLAUDE.md, `arquivo/lotes-1-a-28/LOTE_OPUS_9/resultado.md`, cartões F0-S04-T02 a T04 e o diff `origin/main...origin/s04-t04` (oráculo, `prototypes/s04/obimcore/*`, `ci.yml`).
- Conferências feitas em modo só leitura: cabeçalhos instalados do IfcOpenShell 0.9 (`iterator.h`, `kernel_registry.h`, `logger.h`) e o `geom/main.py`; registros do CI do PR 53 e o estado dos PRs 51, 52 e 53, com `gh`.
- Não leu o `carregador.py`; frase "mesmas opções da S03" para o líder conferir (achado 21). **Conferido pelo líder: confere** (`processo_malhas.py` linhas 162-163: `use-world-coords` ligado, `weld-vertices` desligado; biblioteca híbrida em `carregador.py`).
- Cobre só T02, T03 e T04. T05 e T16, previstos para o lote 10, não estavam no material recebido.

## Resumo para o PO (5 linhas)
1. A ligação entre a parte em Python e a parte em C++ funciona nos dois sistemas: os dois lados enxergam o mesmo modelo, sem cópia. Foram 19 testes verdes no Linux e 19 no Windows, nenhum pulado.
2. Ainda não posso aprovar a junção. O conjunto de testes tem três falhas de construção: deixa de conferir coisas que diz conferir. A correção é pequena, uma rodada.
3. Achamos um problema na biblioteca de geometria: quando várias linhas de execução fazem desenho de peças ao mesmo tempo, o programa cai cerca de 1 vez em 10. A equipe pôs uma fila (uma peça de cada vez). Aceito como solução provisória; não atrasa nenhuma meta.
4. A causa provável é um registro de mensagens compartilhado. Peço um cartão pequeno para confirmar isso e, se possível, tirar a fila.
5. Não recomendo, por enquanto, gerar as peças em um programa separado. Fica como plano B, registrado na decisão sobre linhas de execução.

## Veredito por PR
| PR | Conteúdo | Veredito |
|---|---|---|
| 51 (T02, oráculo) | R1-a a R1-i | **REPROVADO**: achados 1, 2 e 3 (parte do oráculo) |
| 52 (T03, módulo) | contém o 51 (pilha) | **REPROVADO** por herdar o 51. O código C++ do T03 está **aprovado sem mudanças** |
| 53 (T04, malhas) | contém tudo | **REPROVADO**: achados 1 e 2, e o 3 (oráculo e `calcular` em `malha.cpp`). Fora o achado 3, o código do T04 está aprovado |

**Como fechar:**
- Fechar os PRs 51 e 52 como substituídos e corrigir no ramo do 53.
- A pilha de PRs desrespeitou a regra "PR de T3 direto para o main, sem pilha" (achado 19). O 52 compila sozinho (verde), então não há dano técnico.
- O conteúdo aprovado é o atual mais **exatamente** as mudanças descritas nos achados 1 a 3. Elas pedem uma conferência curta do Opus só sobre essa diferença, junto com a revisão do T05 e do T16 neste mesmo lote, sem abrir sessão nova.
- Qualquer outra mudança nos arquivos C++ volta ao lote.
- **Limite de tamanho:** o oráculo T02 já tem exatamente 400 linhas (182 + 218). As correções exigem compactar o que existe ou abrir o cartão **S04-T02b** ("correções do oráculo R1", mesmos arquivos permitidos), feito pelo agente de oráculo e nunca pelo implementador.

## Achados
Severidades: **B** = bloqueante, **I** = importante (cartão ou próximo cartão), **M** = menor.

1. **(B) O R1-e não testa as ordens de importação pedidas.**
   - `_importar` sempre importa `ifcopenshell` antes da lista e `obimcore` sempre por último. Assim, o caso `"PySide6,ifcopenshell"` é idêntico ao `"ifcopenshell,PySide6"`.
   - Nunca se testa o PySide6 carregado antes do IfcOpenShell, que é a ordem real do aplicativo. Também nunca se testa o `obimcore` carregado antes do Qt, que é onde apareceria uma segunda cópia do Qt6Core.
   - O R1-e é caso de estabilidade da M1 (§3).
   - **Ação (agente de oráculo):** `_importar` passa a obedecer a ordem dada, aceitando `obimcore` na lista. Casos mínimos: `PySide6,ifcopenshell,obimcore` · `ifcopenshell,obimcore,PySide6` · `ifcopenshell,PySide6,obimcore`.
   - O `__init__` já importa o IfcOpenShell primeiro, e isso é aceito: "obimcore antes do IfcOpenShell" não existe como ordem.
2. **(B) O R1-i compara bibliotecas de geometria diferentes.**
   - `aux.referencia` chama `create_shape` com a biblioteca padrão, que no 0.9 é `"opencascade"` (`geom/main.py`, linha 488). O C++ usa `hybrid-cgal-simple-opencascade`.
   - Hoje passa porque os modelos são extrusões simples. Um C++ com a biblioteca errada também passaria, então o aceite do T04 não é conferido.
   - **Ação (agente de oráculo):** passar `geometry_library="hybrid-cgal-simple-opencascade"` na referência (nome aceito pelo Python, linha 173).
3. **(B) GlobalId repetido é recalculado só para alimentar a carga do teste.**
   - O `calcular` faz uma passada por repetição e joga o resultado fora. Essa semântica existe só porque o R1-h monta a carga com `todos * k`. É implementação moldada ao teste, e deixaria um contrato estranho para o `Cena.atualizar` (T08/T09).
   - **Ação:** (a) Agente de oráculo: o caso "principal não espera" usa um modelo maior gerado por script (`scripts/gerar_modelo_grande.py --paredes 3000`, o modelo oficial do §2.1) e uma chamada com GlobalIds únicos de pelo menos 150 ms. (b) Implementador, depois: `calcular` elimina repetidos e faz uma passada só.
4. **(I) A fila de geometria, provisória.** Ver "Recomendação sobre o mutex".
5. **(I) Buraco que a fila não cobre.**
   - O mutex só protege o próprio `obimcore`. Um `ifcopenshell.geom.create_shape` ou `geom.iterator` chamado de outra thread Python pode rodar junto com o `malhas`, porque o bloqueio do interpretador está solto.
   - **Ação:** acrescentar a **regra 9** ao §1.4: "geometria dentro do processo só pelo `obimcore`; nenhuma thread Python chama `ifcopenshell.geom` enquanto o editor estiver aberto". Oráculo do caso antes do T11. A regra entra no ADR-004.
6. **(I) Falta a prova mais forte de que existe uma cópia só do IfcOpenShell.**
   - No Windows o R1-e depende só da lista que o próprio módulo informa (não há `/proc/self/maps`).
   - Teste barato: comparar o endereço de `IfcParse::schema_by_name("IFC4")` no C++ com `int(ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC4").this)` no Python. Iguais = um registro de esquemas só.
   - **Autorizado** acrescentar o campo `registro_ifc4` no dicionário de `versao()`. Não é função nova. Fazer antes do T17 (o R1-j repete o teste dentro do pacote).
7. **(I) O R1-a é circular.**
   - O CMake e o teste leem o mesmo JSON do `conda-meta`. `qVersion() in texto` é satisfeito pelo próprio `qt_execucao`. A versão do Qt na compilação nunca é comparada com a da execução.
   - **Ação:** comparar o macro de versão do cabeçalho (`ifcparse/parse.h` cita `IFCOPENSHELL_VERSION`; conferir como é definido) com `ifcopenshell_wrapper.version()`; comparar `versao()["qt"]` com o `qVersion()` do PySide6.
   - No pacote do T17 não existe `conda-meta`, então o build passaria a ser **pulado**. O T17 precisa gravar o build no pacote.
8. **(I) Teste pulado parece verde.**
   - Hoje, conferido: Linux 19 passed e Windows 19 passed, 0 pulados. Mas o passo dedicado do CI não falha se `malhas` sumir ou se o R1-a pular.
   - **Ação:** variável de ambiente no passo (ex.: `OBIM_S04_OBRIGATORIO=1`) transforma pulo em falha. Fica na T02b se o tamanho couber; senão no próximo PR que mexer no `ci.yml`.
9. **(I) Desvio consciente: as funções curtas mantêm o bloqueio do interpretador.**
   - `versao`, `endereco`, `ler_nome`, `definir_nome` e `bibliotecas_carregadas` mantêm o bloqueio. **Aceito**, e é até melhor: ficam atômicas para as outras threads Python (regra 7).
   - `contar` percorre o modelo inteiro com o bloqueio preso. Medir no modelo de 1 milhão (T10 ou T15): se passar de 5 ms, soltar.
   - Registrar no ADR-004 como emenda da regra 4: "o que dura menos de ~1 ms mantém o bloqueio".
10. **(I) Peça sem geometria devolve caixa `[0,0,0,0,0,0]`.** Confunde-se com peça na origem e atrapalha a seleção do T10. `caixa` e `cor` saem com forma (1,6) e (1,4). **Ação no T08/T09:** usar NaN (ou omitir) e vetores de uma dimensão.
11. **(I) Exceções fora de `std::exception`.** `malhas` só pega `std::exception`. A `Standard_Failure` do OCCT não deriva dela, e a mensagem se perde. **Ação:** `catch (...)` com mensagem genérica (pode ir junto com o achado 3). Registrar no ADR-004: um erro grave da geometria **derruba o programa inteiro** durante uma edição, porque não há isolamento como na abertura da S03.
12. **(I) Os modelos de teste não têm eixo (`Axis`) nem abertura.** Se o iterador entregar o eixo, o `malhas` o juntaria à malha (concatena por GlobalId). Sem abertura, o caminho de booleana (CGAL) não é exercitado. **Ação (oráculo, T02b se couber; senão T06 ou T12):** algumas paredes com `Axis` e uma com abertura.
13. **(M) `definir_nome` escreve fora do desfazer do Python.** Nota para a S05 e o T13. No fluxo A o C++ nunca escreve: a função é só do oráculo.
14. **(M) O `__init__.py` é gerado pelo `build.sh`, sem arquivo versionado.** Correto (importa o IfcOpenShell primeiro e chama `add_dll_directory`). O T17 vai precisar dele. **Ação no T07 ou T17:** virar arquivo versionado, copiado pelo build. Tirar `Library/mingw-w64/bin` se não for necessário.
15. **(M) MSVC sem `/utf-8`.** Há literal com acento. Acrescentar `/utf-8` no próximo cartão que mexer no CMake.
16. **(M) Nome do passo no CI** diz "R1-a a R1-g", mas roda R1-a a R1-i. Corrigir o texto.
17. **(M) Tempos de build do PR 53** só ficam no resumo do CI, que expira. Copiar para o cartão T03 e para o relatório da fatia. Linux: limpo 16,7 s, incremental 5,0 s. Windows: limpo 42,0 s, incremental 10,6 s.
18. **(M) O R1-f mudou a regra de memória.** A especificação pede crescimento abaixo de 10% entre as voltas 100 e 1.000; o oráculo compara o que o módulo acrescenta contra a mesma volta em Python puro. **Aceito por escrito.** O IfcOpenShell cresce ~0,7 MB por reabertura; entra no ADR-001 como risco de sessão longa.
19. **(M) Processo.** A pilha de PRs desrespeitou a regra; registrar no LOG.
20. **(M) Nome com acento.** Falta teste de ida e volta (ex.: "Ação ç") entre Python e C++. Fazer na T02b se couber, senão no T06.
21. **(M) Conferência do líder.** Opções do `malhas` (coordenadas do mundo, `WeldVertices=false`, biblioteca híbrida) batem com o `carregador.py`/`processo_malhas.py` da S03? **Conferido: sim.**
22. **(M) macOS.** As 3 falhas são testes de tempo da S03 (`test_viewport_carregador`, `processo`, `responsivo`), não da S04. O `obimcore` nem é compilado no macOS. Informativo.

**O que está bom e fica registrado:**
- `emprestar`: confere o tipo (rejeita entidade, que também tem `file_pointer`), trata o zero e segura a referência pelo parâmetro `nb::object` durante a chamada inteira, inclusive com o bloqueio solto (regra 1).
- Nada guardado entre chamadas (regra 2): o único estado global é o mutex.
- Posse da malha: `get()` devolve `unique_ptr` (conferido no `iterator.h`). Os vetores passam ao numpy por cápsula, sem cópia e sem vazamento.
- Bloqueio solto sem tocar em Python: a conversão da saída é feita com o bloqueio de volta.
- R1-d é a prova certa de "mesmo modelo" (criar, renomear pelo C++, desfazer). R1-g cobre bem os objetos que não são arquivo.

## Recomendação sobre o mutex (fila de geometria)
**Aceitar como provisório: sim.**
- Correto do jeito que foi feito: o bloqueio do interpretador é solto antes de pegar o mutex, sem Python dentro dele, então não há impasse. Ordem com a trava da regra 7: sempre "trava do modelo, depois mutex".
- Impacto nas metas: M2, M2b, M3, M4 praticamente nenhum (comandos já rodam em série numa thread; se a M4 precisar de velocidade, o paralelismo certo é dentro de **uma** passada, `num_threads` do iterador). M5 nenhum (a thread de desenho não faz geometria). M1: o risco 2 do §6 não dispara; a queda acontece com o bloqueio solto e sem objeto Python, ou seja, é segurança de threads da geometria, não da ponte.
- Honestidade: o R1-h de 4 threads hoje prova "sem queda e sem diferença com a geometria em fila", não geometria simultânea.
- **Causa provável (cabeçalhos):** `kernels::construct` e o construtor de `iterator` usam por padrão `ifcopenshell::logger::root()`, um registro de mensagens **global do processo**, com "produto atual" e mensagens que apontam para entidades do arquivo. Passadas simultâneas disputam esse estado; explica por que "travar só a construção não bastou". O registro global também acumula mensagens que apontam para arquivos destruídos (risco de ponteiro solto em sessão longa).
- **Cartão novo, S04-T04b (T3, tamanho P, não bloqueia o portão):** (a) um `ifcopenshell::logger` local por passada, passado a `construct` e ao `iterator`; repetir o experimento de 4 threads **sem** o mutex, 200 rodadas ou mais. (b) Reproduzir em C++ puro, sem Python (4 threads, 4 arquivos), com rastro da queda se houver ferramenta já instalada; nada de instalar ferramenta nova. (c) Se resolver: tirar o mutex e acrescentar o caso ao oráculo; se não: manter o mutex, registrar no ADR-004 e abrir aviso público ao projeto IfcOpenShell (pesquisa pública-só).
- **Processo separado para as malhas das edições: não agora.** Quebra a premissa "mesmo modelo, sem cópia" e soma latência à M2. Plano B no ADR-004, com a regra 9 (achado 5) e o achado 11. Gatilho para rever: queda da geometria durante edição no T11 ou T15, ou o T04b mostrar algo além de queda por simultaneidade.

## Portão interno: "o modelo é o mesmo dos dois lados?"
**Ainda não fechado. Tudo o que foi medido aponta para sim.**
- R1-a, b, c, d, f, g, h e i verdes no Linux e no Windows, 19 de 19 em cada um, sem pulo.
- Falta só o R1-e cobrir de verdade as ordens de importação (achado 1), caso de estabilidade da M1.
- Com a T02b verde nos dois sistemas e a conferência curta da diferença, a resposta passa a **sim** (salvo o R1-j, que é do T17).
- O portão **não está reprovado**, então o T05 (sonda de desenho, depende só do T01) pode seguir.

## Riscos para o T05 e a etapa 2
1. **T05:** sem dependência destes PRs nem do mutex. A sonda não usa o IfcOpenShell.
2. **T08/T09 (`Cena.atualizar`):** gerar a malha **dentro da chamada da thread do comando** (uma thread C++ de fundo lendo o modelo violaria a regra 3). Herdar a eliminação de repetidos (3), a caixa em NaN e os vetores de uma dimensão (10). Testar de novo "fechar o arquivo com malhas na cena" com a `Cena` real (o R1-g usa só uma lista).
3. **Etapa 2 inteira:** o módulo hoje liga o Qt6Core; com Gui/GuiPrivate o R1-e precisa ser repetido com a janela aberta (previsto no T06), nas ordens corrigidas. O registro global de mensagens (4) é risco de memória em sessão longa. Uma queda na geometria derruba o editor com o trabalho do usuário (11): pesa no ADR-004 e na gravação segura da S05.
4. **T11:** a trava da regra 7 só existe no lado Python e o C++ não consegue conferir. Sugestão: em modo de teste, o fluxo A confere `trava.locked()` antes de cada chamada ao `obimcore`.
