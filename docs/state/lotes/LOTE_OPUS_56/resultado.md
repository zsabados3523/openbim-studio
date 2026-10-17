# LOTE_OPUS_56: resultado

**APROVADO** (conteúdo do pedido 155 no HEAD `eff0ef6`). O merge continua preso ao CI: a execução `39064438868`, no mesmo commit, ainda estava rodando quando este lote fechou (ver item 5). Não é aprovação provisória: o conteúdo está aprovado por inteiro, e o que falta é só a prova do CI, que a autorização permanente já exige antes de qualquer merge.

Revisor: Opus, independente (não escreveu nada desta tarefa). O que revisei:
- ramo `s04-t17b-impl`, HEAD `eff0ef6` (merge de `origin/main` = `eb852f1`, que traz o pedido 156); `git merge-base origin/main HEAD` = `eb852f1`, ou seja, o ramo está em dia com o `main`;
- `git diff origin/main...HEAD`: 8 arquivos, +132 −11 = **143 linhas** (abaixo de 400);
- comparação com o conteúdo que os lotes 54 e 55 leram (`7d91aac`);
- CI: `gh pr checks 155` e `gh run list --branch s04-t17b-impl`, só leitura.

Ensaio do revisor (sem tela, sem instalar nem baixar nada, sem tocar a worktree do implementador): rodei o mesmo comando da linha nova do CI, `out="$(bash packaging/windows/test_instalador_ponte.sh --autoteste)"` com o Python do ambiente `openbim`: código 0, última linha `ok`, e a conferência `[ "$(echo "$out" | tail -n 1)" = ok ]` passou.

## Achados

### Item 1: o diff do 155 é só a implementação
1. **Confirmado** (OK).
   - O diff contra `origin/main` não toca `packaging/windows/ponte_no_pacote_win.py`, `packaging/windows/test_instalador_ponte.sh` nem `tests/`. Os 8 arquivos são: `ci.yml`, `THIRD_PARTY.md`, `docs/dev-setup.md`, o cartão T17, `packaging/README.md`, `LGPL-COMO-TROCAR.md`, `OpenBIM-Studio.pyw` e `build_installer.sh`.
   - O oráculo que está no `main` (pedido 156) é igual ao de `7d91aac`, menos o cabeçalho de `test_instalador_ponte.sh` (linhas 18 a 24), que agora descreve a regra em vigor: PATH herdado, prefixo de desenvolvimento, mesmo nome, importada pelo pacote, núcleo e nome 8.3. Isso fecha o achado 8 do lote 55. O cabeçalho bate com a `classificar`.
   - O implementador não mexeu no oráculo neste pedido.

### Item 2: a linha nova do CI no job `linux`
2. **Correta, e não enfraquece nada** (OK).
   - Está no job `linux` (entre a "Sonda", que é informativa, e o "REUSE"). Não tem `if:` nem `continue-on-error`. O `linux` é obrigatório e roda em todo pedido (não tem `detecta`).
   - Falha fechada pelos dois lados. Se o autoteste sair com código diferente de 0, o `bash -e` derruba o passo já na atribuição `out="$(...)"`. Se sair com 0 sem `ok` na última linha, a conferência derruba.
   - O `--autoteste` do script faz `exec python -I ponte_no_pacote_win.py autoteste`. O `main` do auxiliar imprime `ok` só sem erros e devolve 1 com erros. Os casos cobertos são os pedidos no lote 54: antivírus só avisa; PATH, prefixo, mesmo nome, importada, núcleo e 8.3 sem resolver reprovam; 8.3 resolvido, Windows, `vcomp140` e `concrt140`; tabela de importação fabricada; `freeze_no_pyw`.
   - Recomendação (BAIXA, sem bloqueio): quando o autoteste falha, o `bash -e` sai antes do `echo "$out"`, e as linhas `ERRO:` (que vão para a saída padrão) não aparecem no log. O passo reprova certo, mas sem dizer qual caso falhou. Numa tarefa futura de CI: `set +e; out="$(... 2>&1)"; rc=$?; echo "$out"`, e reprovar se `rc` não for 0 ou se a última linha não for `ok`.

### Item 3: as notas do cartão
3. **Certas** (OK), com uma ressalva de texto (BAIXA).
   - A nota do achado 20 não cita mais `packaging/licenses-texts/`. Os arquivos fora da lista são só `THIRD_PARTY.md` e `docs/dev-setup.md`, e isso confere com o diff.
   - A nota do tamanho dá antes 309 664 248 bytes (`dbee8ee`, execução 39048216714) e depois 310 600 792 bytes (execução 39058071304), +936 544. Os números batem com o lote 55, e a conta está certa. A descrição do pedido 155 traz os mesmos números, o que atende o critério 4 do cartão e o achado 11 (iii) do lote 55.
   - Ressalva: "tamanho final, último run verde do pedido 155" era verdade quando a nota foi escrita. A execução nova (`39064438868`, no commit que vai ao `main`) vai gerar outro instalador, com variação esperada de dezenas de KB (o lote 55 viu 64 864 bytes entre execuções). O pacote é o mesmo, então isso **não** pede releitura. Basta o líder, depois do CI verde, anotar o número da execução nova no LOG ou trocar no cartão "tamanho final" por "medido na execução 39058071304". Não bloqueia.

### Item 4: o restante do diff é o que os lotes 54 e 55 aprovaram
4. **Confirmado** (OK).
   - `git diff 7d91aac HEAD`, sem contar os dois arquivos do oráculo (já tratados no item 1), mostra só duas mudanças:
     - a linha nova do autoteste no `ci.yml` (item 2);
     - as duas notas do cartão (item 3).
   - Não mudou nada em: `build_installer.sh` (`OBIMCORE_DIR` obrigatório, R-ABI com as duas travas e o ambiente real, cópia do `vcruntime140*`, prova 7 já na montagem, licenças do nanobind e do robin_map, nota do `INVENTARIO.md`); `ci.yml` (cache com `lookup-only` e `fail-on-cache-miss`, `needs: windows-viewport-a`, `timeout-minutes: 75`, `detecta` com `prototypes/s04/obimcore/`, `tests/` e `.github/actions/`, trava de 600 MB, passo R1-j); `.pyw` (`freeze_support()` dentro do guarda `__main__`); `packaging/README.md`; `THIRD_PARTY.md`; `LGPL-COMO-TROCAR.md`; `docs/dev-setup.md`.
   - O merge do `main` em `eff0ef6` não teve conflito e não trouxe mudança nesses arquivos além do que já estava no `main`.

### Item 5: o CI do último commit
5. **Ainda rodando** (pendente; não é achado contra o conteúdo).
   - A execução `39064438868`, no commit `eff0ef6` (evento `pull_request`), estava `in_progress` com cerca de 2 minutos. Os jobs `linux`, `windows-testes`, `windows-viewport-a`, `windows-viewport-b`, `windows-fluxo-b`, `windows-sonda` e `macos` estavam pendentes.
   - Os jobs `windows`, `instalador-windows` e `appimage` ainda nem aparecem, porque esperam outros jobs (`needs`).
   - Pela execução anterior (`39058071304`), a execução inteira leva uns 36 min.
   - O `macos` vermelho não bloqueia (está vermelho também no `main` e é experimental).
   - **O líder só mescla quando:**
     - a. os 4 jobs obrigatórios (`linux`, `windows`, `appimage` e `instalador-windows`) estiverem verdes nesta execução, no commit `eff0ef6`;
     - b. o log do `linux` mostrar o passo "Autoteste do oráculo do instalador Windows" com `ok`;
     - c. o log do `instalador-windows` mostrar:
       - `instalador=true`;
       - o cache `obimcore-win-39064438868` encontrado;
       - o passo "R1-j, o módulo dentro do instalador" verde, com o prefixo `C:\Users\runneradmin\miniconda3` impresso, o `MpOAV.dll` como único AVISO, 9 passed, os filhos spawn com `valor=42 isolado=1` e a prova 7 com runtime ≥ ligador;
       - depois disso, o "Teste do instalador" verde.
   - Se algum desses itens faltar ou vier diferente (por exemplo, um AVISO novo ou o runner com um compilador 14.52 reprovando a prova 7), o líder não mescla e leva o caso ao Opus ou ao PO. **Nunca afrouxar o teste.**
   - Quase todas as condições do item c, quando quebram, já derrubam o job sozinhas. A exceção é "o `MpOAV.dll` como único AVISO": um AVISO novo não reprova o job, e só quem lê o log o vê. Por isso o líder lê o log do R1-j **antes** de mesclar. Hoje o pedido 155 está sem mesclagem automática (`autoMergeRequest: null`), e deve continuar assim até essa leitura.
   - Se o CI ficar verde do jeito descrito, não precisa de nova revisão do Opus: o conteúdo exato é este.

## O que registrar no LOG
- "Lote opus 56 | APROVADO | T17b, conferência final do pedido 155 (`eff0ef6`, 143 linhas, só a implementação). O oráculo está no `main` pelo pedido 156 e é igual ao de `7d91aac`, mais o cabeçalho corrigido (fecha o achado 8 do lote 55). O resto do diff é igual ao que os lotes 54 e 55 leram, mais: o autoteste do oráculo no job `linux` (fecha o achado 5 do lote 55) e as notas do cartão (fecham o achado 11 do lote 55). Merge só com `linux`, `windows`, `appimage` e `instalador-windows` verdes na execução 39064438868 (ou numa seguinte, no mesmo commit), autoteste `ok` e R1-j do instalador verde."
- Depois do merge: o número da execução e o tamanho do instalador dessa execução (é a medida que fica valendo; a variação esperada é de dezenas de KB). Resumo curto ao PO, como manda a regra do T3.
- Recomendações para depois (sem bloqueio), juntar com as que já estão abertas:
  - item 2 deste lote: o passo do autoteste deve mostrar as linhas `ERRO:` quando falhar;
  - lote 55, achados 6 e 7: 8.3 antes do ramo do Windows; pasta atual de trabalho na lista; contagem de arquivos lidos pela `importados`;
  - autoteste do `test_appimage_ponte.sh` no CI;
  - lote 54, itens 21 e 22: R1-j em pasta com acento e espaço; cartão da prova 6; tarefa de texto do segundo titular do nanobind, dos comentários antigos do `ci.yml` e do `CLAUDE.md` com 4 jobs obrigatórios.

---
## Resposta do líder (2026-10-17)
Aprovado condicionado: o pedido 155 só é mesclado com `linux`, `windows`, `appimage` e `instalador-windows` verdes e depois da leitura do log do R1-j do instalador (o único aviso aceito é `MpOav.dll`). Sem mesclagem automática ligada.
