<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_70: revisão do PR 243 (T23e, instalador) e dos oráculos dos PRs 245, 246 e 247 (V1 e P1) (F0-S04)
Pedido do líder (2026-10-21), **classe T3, revisão Opus em lote, esforço médio**. Responda **aprovado ou reprovado com lista numerada** por PR. Escreva só `docs/state/lotes/LOTE_OPUS_70/resultado.md` (num worktree seu, sem commit; informe o caminho); não implemente, não faça merge, não leia `~/openbim-medicao` nem IFC. **Você é uma sessão nova: não escreveu nenhum destes** (os oráculos dos PRs 245 a 247 foram escritos pelo Opus do lote 69, outra sessão; confira que você não está revendo trabalho seu e diga isso no resultado).

## Contexto fechado
Cartões `docs/state/arquivo/F0-S04/cartoes/F0-S04-T23e.md` (no main), `F0-S04-V1.md`, `F0-S04-V1b.md`, `F0-S04-P1.md` (PR 244 / main), `LOTE_OPUS_69/resultado.md` (PR 244 / main), `docs/adr/ADR-004-processos-threads-e-trava.md` (§5.1), `ADR-001`. Código nos ramos remotos (`git fetch origin`; `git diff origin/main...<ramo>`):
- **PR 243** `s04-t23e-instalador` (T23e): `packaging/windows/` (`gzip -9` → `-6`; o NSIS guarda `env.tgz` sem recomprimir, `SetCompress off` só nessa linha; `/SOLID` saiu), relatório `reports/F0-S04-T23e.md`. Medida em 3 rodadas seguidas (a mesma execução 39596204251): instalador pronto em 12 min 35 s, 12 min 07 s e 9 min 14 s (antes 14 min 30 s a 19 min 02 s); trabalho `instalador-windows` de cerca de 10 a 13 min para 4 a 7 min; teste do instalador e R1-j passaram nas 3. Conteúdo idêntico (SHA-256 do tar descompactado) medido pelo implementador no Linux, com amostra. **Risco declarado:** o NSIS não roda no Linux; só o CI Windows confirmou `SetCompress off` sem `/SOLID`. Tamanho do instalador e tempo de instalação não foram lidos do log.
- **PR 245** `s04-v1-oraculo-mista` (`tests/test_s04_v1_mista_oraculo.py`, 393 linhas), **PR 246** (`test_s04_v1_veredito_oraculo.py` + `test_s04_p1_obimcore_oraculo.py`), **PR 247** (`test_s04_p1_trava_oraculo.py`, 301 linhas): oráculos do V1 (forma mista) e do P1 (porta única do modelo), com marcadores `@AINDA_NAO` (xfail strict) onde a implementação ainda não existe. O lote 69 relata: 4 passam hoje, 28 xfail strict; referências temporárias (fora do repositório) fazem V1 14/14 e P1 18/18; 8 mutantes pegos.

## Pontos
1. **243:** (a) o conteúdo instalado é idêntico? a evidência basta (tar descompactado igual com amostra) ou pede mais antes do merge? (b) `SetCompress off` sem `/SOLID` é seguro no NSIS (o instalador instala e roda)? o CI mostrou isso nas 3 rodadas (R1-j + teste do instalador); (c) nenhum teste removido ou com limite maior; nomes dos checks obrigatórios intactos; (d) tamanho do instalador e tempo de instalação: pedir a leitura antes do merge ou aceitar? Aprovar para mesclar?
2. **245, 246, 247:** cada exigência do cartão V1 e do P1 e do ADR-004 §5.1 (regras 2 a 5 e critérios 1 a 8) tem teste que a prova? há caso afrouxado ou redundante? os marcadores `AINDA_NAO` estão no padrão do T30d3 e só nos casos que dependem da implementação? o que roda em tela virtual? o que o CI passa a rodar e quanto custa? Algum teste que pode ficar vermelho por XPASS(strict) quando a implementação entrar de forma parcial?
3. **Ordem de merge** e quem tira os marcadores (autor do oráculo, em commit próprio, quando a implementação entrar).

## Entrega
Veredito por PR; respostas; perguntas ao PO (só o que é dele); resumo de 5 linhas em português simples, sem siglas; linha do LOG. Retorno final em caveman. Não aprove provisoriamente.
