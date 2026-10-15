# Revisão Opus: F0-RG-14 (CI enxuto, PR 120) e olhada no F0-RG-12 parte 1 (PR 119)

- Data: 2026-10-15
- PR: #120, ramo do PR em `1c2db44`; #119 em `b2b7a08` (só olhada, sem bloquear)
- Cartões: F0-RG-14 e F0-RG-12 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md`
- Revisor: Opus (não escreveu nada destas tarefas)
- Diff revisado: `.github/workflows/ci.yml` (+37 −65), só esse arquivo
- `v2/` e `CLAUDE.md`: não mudam (conferido no diff contra `main`).
- Como foi conferido: leitura do diff e do `ci.yml` inteiro do ramo, com cada passo que tem `|` olhado sob `-e` e `pipefail`. Também foram lidos o ADR-005 (seções 3.1, 7.1 e 9.1) e o oráculo `tests/test_s04_ponte.py` (R1-a a R1-e), para saber se a retirada das sondas deixa algo sem cobertura.

## PR 120: veredito APROVADO (a mesclagem continua dependendo do CI obrigatório verde)

1. **Nomes dos checks obrigatórios: iguais.** Nenhuma chave de job mudou. `linux`, `windows` (job de junção), `instalador-windows` e `appimage` estão como no `main`, e os jobs do Windows que alimentam a junção também.
2. **Nada passou a "passar calado".** Nenhum `|| true` novo e nenhum `continue-on-error` novo. Os dois passos retirados eram `continue-on-error`, então nunca bloquearam nada. O que muda vai no sentido de falhar mais, não menos:
   - **(a) Módulo obimcore** (Linux e `windows-viewport-a`): o passo já tinha `set -e`. Com `pipefail`, `build.sh | tee` agora derruba o passo quando o build falha, em vez de seguir com o código do `tee`. É o defeito declarado no PR, e a correção está certa.
   - **(b) Instalador Windows:** `build_installer.sh ... | tail -n 45 | tee -a` escondia a falha do build do instalador. Agora ela derruba o passo. O `tail` lê tudo antes de escrever, então não há corte de canal (SIGPIPE).
   - **(c) Corte de canal com `pipefail`:** os três `... | grep -q` (`conda env list`, `locale -a`, lista de arquivos do PR) foram trocados por leitura de variável. Sem isso, o `grep -q` que fecha cedo poderia fazer o produtor morrer por SIGPIPE e derrubar o passo por engano. Os demais canais no arquivo (`grep | head -n 1` dentro de `$(...)` em atribuição, `tail | sed`, `echo | sha256sum`, `diff <(...)`) não mudam o código de saída do passo.
3. **Sondas do ADR-005 (teste 2 e sonda 3b): retirada justificada.** O que elas provavam está coberto, e com mais força, por passos que **bloqueiam** nos dois sistemas e rodam em todo PR:
   - **Sonda 3b** (C++ inclui `ifcparse/file.h`, liga pelo `IfcOpenShellConfig.cmake` e abre um IFC): o passo "Módulo obimcore" faz exatamente isso com o código de produto, no Linux e no `windows-viewport-a`.
   - **Teste 2** (o módulo Python liga nas bibliotecas compartilhadas, sem cópia embutida): coberto pelo oráculo R1. R1-a confere versão e build iguais. R1-b confere o mesmo registro de esquemas IFC4 dos dois lados, o que só é possível com uma cópia do núcleo. R1-d mostra o Python e o C++ vendo as mesmas mudanças. R1-e confere uma cópia de cada núcleo. Um pacote que passasse a embutir cópia própria ou biblioteca estática quebraria R1-b ou R1-d, ou seja, bloqueia o merge. É o objetivo do item 10 da seção 7.1 do ADR-005, cumprido por outro caminho.
   - Os scripts continuam no repositório (`scripts/sonda_ifcopenshell.py`, `prototypes/cpp_probe_3b/`) e `docs/dev-setup.md` continua válido.
4. **Passos informativos:** "Gravação do roteiro" agora sempre sai com 0 e escreve "gravou" ou "FALHOU" no resumo. Antes já era `continue-on-error`, então o efeito sobre o merge é o mesmo, e a falha fica visível no resumo. A trava do ambiente e a sonda da thread de desenho só ganharam uma linha no resumo.
5. **CI:** a conferir no próprio PR. Este PR muda o shell de quase todos os passos (`-l` com `pipefail` também vale para os scripts de ativação do conda), e só o CI verde nos quatro obrigatórios prova que nada quebrou por isso.

### Recomendado (não bloqueia)

6. **Texto do ADR-005 desatualizado.** O item 10 da seção 7.1 ("os passos teste 2 e sonda do CI passam a reprovar") e a nota da linha do teste 2 ("passa a bloquear na S04") descrevem passos que deixam de existir. Pela regra do projeto, o ADR é do Rafael. Sugestão de nota para o cartão F0-RG-24 ou para a próxima revisão do ADR: "cumprido pelo passo bloqueante do obimcore e pelo oráculo R1 (R1-a, R1-b, R1-d, R1-e); sondas retiradas do CI no RG-14".
7. **Conflito com o PR 119.** Os dois mexem no `ci.yml`, em linhas vizinhas: o passo do obimcore e o do fluxo B. Quem mesclar por último deve trazer o `main` e conferir que o resultado tem `pipefail` **e** `OBIM_CI=1` nos mesmos passos.

## PR 119 (RG-12 parte 1): olhada rápida, sem bloqueio

Nada preocupa no sentido de testes passarem calados hoje.
- `CHAVES_S04` tem exatamente as 15 chaves que os testes leem. Conferido com `grep` em `tests/`. A única de fora é `OBIM_S04_T14_OBRIGATORIO`, de propósito, porque a T14 não existe.
- As chaves são ligadas no `conftest.py` antes de qualquer módulo de teste ser importado, e os subprocessos do oráculo herdam o ambiente.
- Uma chave definida à mão vence (`setdefault`).
- `pytest.ini` não esconde configuração antiga: não há `pyproject.toml`, `setup.cfg` nem `tox.ini` com seção do pytest. `--strict-markers` só falha alto, e hoje só há marcadores do próprio pytest.
- Passos que antes ligavam só algumas chaves agora ligam todas. Isso só pode fazer falhar mais, nunca pular mais.

Recomendado: um teste sentinela que compare `CHAVES_S04` com as chaves `OBIM_S04_*_OBRIGATORIO` citadas em `tests/` (fora a T14). Hoje, apagar uma chave da lista faria os testes daquela etapa voltarem a pular no CI. O `-rs` mostra o pulo, mas não derruba o job.
