<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_71: revisão das implementações do V1 (PR 250) e do P1 (PR 251) (opus, esforço médio, 2026-10-21)
**Independência.** Não escrevi as implementações, que são do sonnet (V1 d653422; P1 82b52c6), nem os oráculos, que são dos lotes 69 e 70 e de outro Opus. Revisei os oráculos no lote 70. Naquele lote usei estas mesmas implementações só para rodar os oráculos.

**O que foi revisto.** Ramos `origin/s04-v1-impl` (head ca5cb57) e `origin/s04-p1-impl` (head 3f9bbc9), pelo `git diff origin/main...<ramo>`, contra os cartões V1 e P1 do main, o ADR-004 §5 e §5.1 e o que achei nos oráculos.

**Como rodei.** O worktree ficou um tempo no V1 com os arquivos do P1 por cima; voltou ao main depois. O `obimcore` com o C++ do P1 foi compilado só no rascunho. Os mutantes foram aplicados e desfeitos um a um. Nada de commit, push ou merge.

## Veredito
| PR | Veredito |
|---|---|
| 251 (P1) | **APROVADO** (3f9bbc9). Mesclar quando `linux` e `windows` estiverem verdes; ainda estavam pendentes quando conferi. |
| 250 (V1) | **Código APROVADO** como está (ca5cb57), sem mudança pedida. **REPROVADO para merge agora, 1 item** (§1). |

## Evidência (Linux, `xvfb-run -a`, `OBIM_CI=1` e as chaves V1, P1 e T15 ligadas; V1 e P1 juntos)
| Conjunto | Resultado |
|---|---|
| Oráculos V1 (15) e P1 (21) | 36 de 36, **3 de 3 execuções**, 0 pulos (~49 s) |
| `tests/test_s04_ponte.py` | 21 de 21 (rodado junto com os oráculos: 57 de 57) |
| T15a, T15b, T15d, T15e, T15g | 46 de 46 |
| `test_s04_fluxo_a.py` e `test_s04_fluxo_a_camera_selecao.py` | 54 de 54 |

Mutantes na implementação: **11 de 11 reprovam o oráculo**.
- V1:
  - chamada Qt na thread de geometria (`invokeMethod` no lugar de `emit`);
  - malha na thread da janela;
  - sem `join`;
  - `4_controle_1s` com `<=`;
  - erro da geometria engolido.
- P1:
  - sem preferência do escritor;
  - reentrada não detectada;
  - empréstimo que não espera o C++;
  - porta frouxa (outra thread entra com o escritor ativo);
  - espera esgotada que deixa `esperando_escrever` sujo;
  - C++ sem `_obimcore_sair` no erro (recompilado).

## Pontos de risco pedidos
**V1**
- Formas 1 e 2, `fluxo_a.py`, `main`, `main_pesada` e o `__main__` estão intactos (critério 1 por sha256, verde). Em `medir` mudaram só as 2 linhas permitidas.
- Despacho por tabela `{1, 2, "mista"}`: uma forma desconhecida dá `KeyError` e não cai mais calada na forma 2.
- Thread de geometria sem Qt: só `malhas`, o relógio `agora`, `get_ident` e `emit`. `Aviso` (QObject) e `QEventLoop` são criados na janela.
- O sinal é ligado com `QueuedConnection` antes do `th.start()` e desligado depois do `join`.
- O erro sobe na janela, e os embrulhos voltam no `finally`.
- `veredito_mista` não traz número novo: 1.000, 200, 100/200, 3 × max(33,3; parado), 0,5 × `malha_ms` e mediana pelo `numpy.median`, como o ADR e o oráculo.
- `main_mista` segue a ordem do cartão: por forma, controle e depois com mouse, com desfazer e espera de 300 ms; na parte pesada, `mover` alternando ±0,01 e o lote longo alternado.
- Arquivos permitidos respeitados: `lote.py` só com acréscimos antes do `__main__`; CONTRATO com 6 linhas (limite 10); 2 linhas no `ci.yml`, depois do T15g, no `linux` e no `windows`. O passo temporário de medição no Windows não está no diff.

**P1**
- Trava sem "quase":
  - `Condition` com contagem de leitores por thread;
  - preferência do escritor (`_esperando` entra antes da espera e sai num `finally`, também no tempo esgotado e no `ValueError`);
  - reentrada detectada antes de qualquer espera, com qualquer `espera`;
  - empréstimo só na thread do escritor, sem aninhar, e a saída espera `em_uso_cpp == 0`;
  - `Escrita.arquivo` só para o escritor fora do empréstimo.
  O `RLock` do `Condition` é só a guarda interna, não a trava de leitura e escrita.
- O C++ nunca pega a trava do modelo: chama `_obimcore_entrar` e `_obimcore_sair`, que pegam e soltam o `Condition` com o bloqueio do interpretador e antes do mutex da geometria. A ordem do §5 não muda.
- `_obimcore_sair` é chamado em todo caminho depois de entrar: no sucesso, num `catch (...)` com o bloqueio de volta (o `gil_scoped_release` sai do escopo antes) e quando o `emprestar` falha (teste da sessão falsa). Se `_obimcore_entrar` falhar, não há saída a fazer.
- O caminho do `ifcopenshell.file` está intacto (R1-a a R1-i verdes).
- Nenhum `nb::eval` novo. `ponte_malha.cpp` tem 17 linhas mudadas (limite 30); `ponte.cpp` ganhou 1 linha de comentário (limite 2); `sessao_modelo.py` tem 136 linhas (limite 180), sem Qt e sem importar o `obimcore`.
- Diff total de cada PR ≤ 400.

## 1. PR 250: item que bloqueia o merge
1. **Falta a medição e o relatório que o cartão V1 põe no mesmo PR.**
   - O cartão lista `docs/state/reports/F0-S04-V1.md` nos arquivos permitidos.
   - O "Próximo passo" diz: medição no Linux local e no Windows (com o passo temporário do CI, que sai antes do merge), sessão na placa com o PO, e "lote Opus revisa (implementação e relatório) antes do merge".
   - Hoje o PR tem só o código. O código está aprovado e não precisa mudar.
   - Duas saídas, à escolha do líder:
     - (a) seguir o cartão: medir, escrever o relatório e trazer só o relatório a um lote Opus curto;
     - (b) dividir o cartão em "V1 código" (este PR, pode entrar já) e "V1 medição" (relatório e passo temporário), registrando a mudança no LOG.
   - Recomendo **(b)**: o código já está provado pelo oráculo, a sessão na placa depende do horário do PO, e o V1b e a medição precisam do `main_mista` no main.

## 2. Observações que não bloqueiam
- P1, `ponte_malha.cpp`: o teste `PyObject_IsInstance(arquivo, ifcopenshell_wrapper.file)` compara com a classe do SWIG. O `ifcopenshell.file` do Python não é instância dela, então quem decide de fato é o `hasattr(_obimcore_entrar)`. Hoje o resultado é o mesmo, porque o `ifcopenshell.file` não tem esse atributo e o R1 está verde. Numa próxima mudança, comparar com `ifcopenshell.file` deixaria a intenção clara.
- P1: se `_obimcore_sair` falhar dentro do `catch`, a exceção original se perde. Só acontece com um defeito na própria sessão; aceitável.
- V1: o `_composto` solta a trava entre os passos. O cartão sabe disso: serve só para medir, não é modelo para o I1.
- Custo no CI: as linhas próprias somam ~47 s (V1) e ~2 s (P1) por job no Linux. O ensaio do V1 roda também no passo geral, como já dito no lote 70.

## 3. `ci.yml`: conflito e ordem de merge
- Os blocos não se sobrepõem: P1 nas linhas ~122 e ~365, V1 nas ~155 e ~379. `git merge-tree --write-tree origin/s04-v1-impl origin/s04-p1-impl` termina **sem conflito**.
- Ordem: **251 primeiro**, que está pronto. Depois o 250, trazendo o main ao ramo e com o CI verde, quando o item 1 for resolvido.
- CI ainda pendente nos dois PRs (`linux`, `windows-testes` e `viewport`) quando conferi. Os trabalhos `instalador-windows`, `windows-obimcore`, `windows-fluxo-b` e `macos` já estavam verdes.

## 4. Resumo para o PO (3 linhas)
1. A "porta única" do modelo está aprovada: um painel não lê mais o modelo no meio de uma edição, e os testes pegam todos os 11 erros plantados de propósito.
2. A forma mista está correta e aprovada no código; falta só medir na sua placa de vídeo e escrever o relatório, que o cartão manda junto.
3. Recomendo ao líder pôr o código no programa já e deixar a medição numa tarefa própria; isso não pede decisão sua.

## 5. Linha do LOG
`2026-10-21 | F0-S04-V1, P1 | LOTE_OPUS_71 (opus, médio, T3 revisão da implementação) | PR 251 (P1) APROVADO em 3f9bbc9; PR 250 (V1) código APROVADO em ca5cb57, merge reprovado por 1 item (falta medição e relatório no mesmo PR, como manda o cartão; recomendo dividir o cartão em código e medição, com registro no LOG); oráculos 36/36 em 3 de 3, ponte 21/21, T15 46/46, fluxo A 54/54; 11 de 11 mutantes pegos; ci.yml sem conflito, ordem 251 e depois 250 | docs/state/lotes/LOTE_OPUS_71/resultado.md`
