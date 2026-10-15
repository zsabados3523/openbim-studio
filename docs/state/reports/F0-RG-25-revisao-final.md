# F0-RG-25: revisão final da noite de 2026-10-15

- Data: 2026-10-15, cerca de 07:00 (UTC).
- Revisor: Opus, em sessão própria. Não escreveu nem revisou nada desta noite antes.
- Escopo: PRs 99 a 118 mesclados; PRs ainda abertos 101, 105, 108, 111, 119 e 120.
- Base da comparação: `5eea601` (main antes da noite) contra o main atual `0c5ac8c`.
- Como foi conferido: `git log` e `git diff` no repositório; leitura dos testes e do `ci.yml`; logs do CI do main (execução 38686770934) e do PR 111 (execução 38687437819); relatórios Opus da noite no ramo do PR 111. Nenhum teste foi rodado aqui: esta máquina não tem o ambiente `openbim`.
- Nada de código foi mudado por esta revisão.

## Resumo para o Rafael (5 linhas)

1. Os documentos do plano (`v2/`) e o `CLAUDE.md` não foram tocados. O CI continua exigindo `linux`, `windows`, `instalador-windows` e `appimage`; nenhum passo obrigatório virou opcional.
2. O main está **vermelho**. Causa principal: dois PRs (103 e 113) mesclaram sem conflito de texto, mas um importa coisas que o outro apagou. O PR 111 conserta (CI dele ficou verde). Ele espera a sua palavra.
3. Há uma segunda falha no main: um teste de seleção feita ao mesmo tempo que a limpeza da cena (`test_s04_selecao_c.py`) falhou uma vez no Windows e passou na rodada seguinte. Isso não é "teste instável"; pode ser defeito real. Não foi tratado esta noite.
4. A nova régua de tempo respeita a sua regra (mediana de 7 rodadas contra 100 ms), mas ficou mais frouxa que a régua antiga em três pontos que você não decidiu (item 6).
5. A reorganização de `docs/state` não perdeu nada. Faltam as linhas da noite no `LOG.md` e dois cartões abertos ficaram na pasta de arquivo.

## Itens

### Aprovados

**1. APROVADO: `v2/` e `CLAUDE.md` intactos.** `git log 5eea601..origin/main -- v2 CLAUDE.md` não mostra nenhum commit. Os PRs abertos 119 e 120 também não tocam neles.

**2. APROVADO: o CI não ficou mais frouxo.**
- Os quatro jobs da regra de bloqueio existem com os mesmos nomes. O job `windows` agora só junta o resultado de 4 jobs paralelos (`windows-testes`, `windows-viewport-a`, `windows-viewport-b`, `windows-fluxo-b`) e falha se qualquer um falhar (`ci.yml`, job `windows`). O job `windows-sonda` fica fora, mas ele já era informativo.
- Nenhum passo obrigatório ganhou `continue-on-error` ou `|| true`. Os `|| true` novos estão em `locale-gen`, mas o passo confere depois e falha se a localidade não existir.
- Dois passos do Linux que eram informativos passaram a bloquear: a localidade pt_BR e os testes de tela da S03 com tela virtual. Isso é mais rígido, não mais frouxo.
- O job `appimage` passou a montar o AppImage de verdade (`OBIM_EXIGIR_FUSE=1`) e a criar o ambiente pela trava. Também mais rígido.
- PR 120 (aberto): tira só passos informativos (sondas do ADR-005) e liga `pipefail` (um erro no meio de um encadeamento passa a falhar o passo). Mais rígido.
- PR 119 (aberto): troca a lista longa de chaves por uma chave só, `OBIM_CI=1`. Conferi: a lista nova em `tests/obrigatorio.py` cobre todas as chaves que o CI ligava antes (inclui T13, T14A e T16).

**3. APROVADO, com nota: nenhum teste foi afrouxado em silêncio pela RG-03 (PR 103).**
- 24 testes novos; 1 removido: `test_r2_demonstra_o_fenomeno_do_gil`. Ele pulava sempre desde a emenda T08-0 (só rodava sem o processo separado, que existe desde então). A remoção está explicada no PR. É caso de oráculo congelado, mas estava morto.
- As guardas que faziam o teste pular quando o módulo faltava viraram importação direta ou `assert`: módulo ausente agora falha na coleta. Os pulos que sobraram são de plataforma (Windows sem localidade) ou de teste pesado só na sua máquina; todos aparecem no log (`-rs`) e na linha "N PULADOS" do resumo.
- Nota: no Windows os testes de tela da S03 ainda pulam (rodam sem tela). O PR 103 diz isso e deixa para a RG-14. Hoje esse pulo aparece no resumo, mas não falha.

**4. APROVADO: o conserto do PR 111 está certo e é mínimo.** Ele só tira, de `tests/test_viewport_queda_registro.py`, a importação de `requer_a` e `requer_limite` e os quatro decoradores. Conferi no repositório inteiro: nenhum outro arquivo usa esses nomes. `_tempo_carga` e `mapeadas1` continuam existindo em `test_viewport_processo.py`. Com o PR 111 mesclado, não sobra teste que pula calado nem importação quebrada. O CI do PR 111 (que testa o PR já junto com o main) passou em todos os jobs.

**5. APROVADO: docs/state reorganizado sem perda (PRs 112 e 116).**
- Só 2 arquivos sumiram sem ser movidos: `LOTE_OPUS_30.md` e `LOTE_OPUS_31.md`. O texto deles está em `lotes/LOTE_OPUS_30/pedido.md` e `lotes/LOTE_OPUS_31/pedido.md`, só com os caminhos atualizados (conferido com `diff`).
- Procurei todos os links e caminhos entre crases em `docs/`, `tests/` e na raiz. Nenhum aponta para arquivo movido. Os 39 que não existem são padrões (`grupo-*`), arquivos que um cartão ainda vai criar, ou caminhos antigos que já eram assim antes da noite.
- O painel (`docs/PAINEL_DO_PROJETO.md`) bate com o quadro: S01 a S03 feitas, S04 pausada, S09 esperando o seu aceite.

### Atenção para o Rafael (decisões suas)

**6. ATENÇÃO: a régua de tempo nova (PRs 117 e 118) cumpre a sua regra, mas afrouxa pontos que você não decidiu.**

A sua decisão (PO-historico, 2026-10-15): "aquecer, 7 rodadas, mediana contra 100 ms". Isso está no código (`tests/test_s04_viewport.py`, função `veredito`): 1 rodada de aquecimento descartada, 7 medidas, reprova se a mediana passar de 100 ms. Também ficou a conferência antiga de mediana contra 50 ms, que é mais apertada. **Nesse ponto, respeita.**

Mas a régua antiga reprovava **qualquer** rodada acima de 100 ms. A nova deixa passar:
- (a) uma rodada isolada de qualquer tamanho, até uma parada de vários segundos, desde que só uma passe de 200 ms. Não há teto para uma rodada só;
- (b) várias rodadas entre 100 e 200 ms, desde que a mediana fique abaixo de 50 ms. Exemplo conferido pelo outro revisor: 3 rodadas de 150 ms e 4 de 30 ms passam. Uma pausa de 150 ms se vê na tela;
- (c) no PR 117, o valor máximo isolado do tempo de seleção (meta M3, limite 50 ms) subiu de 150 para 250 ms no CI. A mediana e a regra da sua máquina (p95 < 50 ms) não mudaram.

Problema de processo: a regra do PR 118 foi **recomendada e depois revisada pelo mesmo Opus** (o relatório dele mesmo avisa isso). O `CLAUDE.md` diz que o Opus nunca revisa o que ele mesmo escreveu na tarefa. Por isso a minha leitura independente:
- (a) e (c) são razoáveis para a máquina do CI, que tem pausas que a sua não tem;
- (b) e a falta de teto para uma rodada só enfraquecem o teste.

Recomendação: aceitar a régua e pedir um cartão pequeno que acrescente duas travas: "reprova se 3 ou mais rodadas passarem de 100 ms" e "reprova se qualquer rodada passar de 1 segundo". Escolha sua: aceitar assim, aceitar com as duas travas (recomendado) ou voltar à régua antiga.

**7. ATENÇÃO: o main está vermelho; o que falta para ficar verde.** Execução 38686770934, commit `0c5ac8c`:
- `linux` e `windows-testes`: a coleta dos testes quebra. `tests/test_viewport_queda_registro.py:14` importa `requer_a` e `requer_limite`, que o PR 103 apagou de `test_viewport_processo.py`. O PR 113 foi testado antes do 103 entrar e o 103 antes do 113 entrar; cada um passou sozinho. **Conserto: mesclar o PR 111.** Você precisa dar o ok, porque o conserto foi feito sem a sua palavra e a mesclagem automática dele está desligada.
- `windows-viewport-b`: 212 passaram e 1 falhou: `tests/test_s04_selecao_c.py:352`, `test_selecionar_em_outra_thread_durante_atualizar_e_limpar`. A seleção devolveu um objeto que já tinha sido removido da cena. Esse mesmo job passou na execução do PR 111, logo depois. Uma falha que aparece às vezes num teste de duas tarefas ao mesmo tempo costuma ser defeito real de sincronização, não azar da máquina. Não posso afirmar a causa só pelo log. **Recomendação:** depois de mesclar o 111, rodar o CI do main de novo; passando ou não, abrir um cartão crítico (classe T3) para investigar esse teste. Não marcar o teste como "pode falhar".
- `macos` vermelho, como já era; não bloqueia.
- Os PRs 119 e 120 estão vermelhos pela mesma quebra da coleta: o CI deles testa junto com o main. Devem ficar verdes depois do 111 entrar e de cada um trazer o main de novo.

**8. ATENÇÃO: a noite não está registrada no `LOG.md`.** O `BOARD.md` diz "andamento de cada um: `LOG.md` e os PRs", mas o `LOG.md` não tem nenhuma linha RG. A regra do `CLAUDE.md` é uma linha por tarefa concluída ou escalada, e registrar cada escalonamento. Também faltam: o choque 103/113, o conserto sem a sua palavra e a autorrevisão do item 6. Recomendação: um cartão simples para o líder escrever essas linhas a partir dos relatórios.

**9. ATENÇÃO: dois cartões abertos ficaram na pasta de arquivo.** `F0-S03-T27` e `F0-S03-T28` estão no quadro como abertos, mas os arquivos estão em `docs/state/arquivo/F0-S03/cartoes/`, que é a pasta das fatias fechadas. Não se perdem, mas confundem. Recomendação: mover para `docs/state/cards/F0-S03/` no próximo cartão de documentos.

**10. ATENÇÃO: onde guardar os relatórios Opus.** O `CLAUDE.md` (autorização 6) manda gravar o relatório do lote Opus em `docs/state/reports/`. A reorganização criou `docs/state/lotes/` para isso, e as revisões desta noite foram para `reports/` (PR 111). Funciona, mas as duas regras não batem. Só você muda o `CLAUDE.md`. Recomendação: decidir uma pasta só; eu sugiro `lotes/` para lotes e `reports/` para revisões de um PR.

**11. ATENÇÃO: o PR 103 mexeu em testes de oráculo e entrou sem revisão Opus.** Ele mudou arquivos de oráculo congelados (por exemplo `test_viewport_carregador.py` e `test_viewport_processo.py`). Neste caso a mudança deixou os testes **mais** rígidos e eu não achei número afrouxado (item 3). Mas a regra diz que quem implementa não edita oráculo. Recomendação: aceitar o que entrou e deixar escrito que mudar só a guarda (pular ou falhar) não muda o oráculo.

### Reprovado

**12. REPROVADO: o estado final da noite não está pronto para seguir.** O main vermelho (item 7) e o registro faltando (item 8) impedem chamar a noite de concluída. Nenhum dos dois pede mudança de regra: o primeiro precisa do seu ok para o PR 111; o segundo é só escrever.

## PRs abertos e o que esperam

| PR | O que é | Espera |
|---|---|---|
| 111 | Conserto do main e revisões Opus da noite | Seu ok para mesclar (item 7) |
| 101 | Rascunho do ADR-004 | Sua decisão |
| 105 | Instalador Windows (programa aberto, acento no caminho) | CI e revisão |
| 108 | Relatório Opus da RG-07 | Só documento |
| 119, 120 | Organização dos testes; CI mais enxuto | Main verde (PR 111), depois trazer o main |
