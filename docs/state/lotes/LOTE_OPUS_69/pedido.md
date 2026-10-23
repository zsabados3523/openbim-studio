<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_69: especificação e oráculo dos cartões V1 (forma mista), V1b (`--ifc`) e P1 (porta única do modelo) (F0-S04, T19 aprovado)
Pedido do líder (2026-10-21), **classe T3 (especificação e oráculo pelo Opus; implementação depois por sonnet; revisão Opus em lote depois)**, esforço médio. O PO aprovou em 2026-10-21 o ADR-001 e o ADR-004 (forma mista condicionada ao V1) e mandou seguir com V1, V1b e P1.

## O que escrever (e só isto; no seu worktree, sem commit, sem push, sem merge; informe os caminhos absolutos)
1. Cartões `docs/state/arquivo/F0-S04/cartoes/F0-S04-V1.md`, `F0-S04-V1b.md`, `F0-S04-P1.md` no formato de `docs/state/cards/README.md` (diff máximo 400 linhas; se algum passar, divida em cartões a/b e diga a ordem). Cada cartão: especificação fechada (arquivos permitidos, proibido, critérios de aceite com números), classe, quem implementa, ordem e dependências.
2. O **oráculo** de V1 e de P1 como arquivos de teste novos em `tests/` (nomes `test_s04_v1_*_oraculo.py`, `test_s04_p1_*_oraculo.py`), com marcadores `@AINDA_NAO` (xfail strict) onde a implementação ainda não existe, no padrão do T30d2/T30d3 (veja `tests/test_s04_t30d3_reenvio_oraculo.py`); o implementador não os edita e quem tira os marcadores é o autor do oráculo (você ou outro autor, como o líder decidir). V1 mede protótipo (forma "mista" em `prototypes/s04/fluxo_a/lote.py`): o oráculo cobre a parte determinística (formas 1 e 2 e `fluxo_a.py` intactos, regras 2 a 5 do ADR-004 §5.1: malha só na thread de geometria com o bloqueio solto, resultado por sinal enfileirado, "modelo ocupado" sem reentrada, nenhum objeto Qt fora da thread da janela) e deixa os números do §5.1 (itens 2 a 8) como critérios de MEDIÇÃO do cartão (não de teste automático). P1 é a porta única do modelo (decisão 3C do ADR-004 §5): oráculo da trava de leitura e escrita e da conferência pelo `obimcore` (regras 3 e 4).
3. `docs/state/lotes/LOTE_OPUS_69/resultado.md`: o que cada cartão pede, ordem de execução sugerida, o que roda em tela virtual e o que exige a placa (V1 pede UMA sessão na placa, já liberada pelo PO de forma permanente no chat), dúvidas ao PO (só o que é dele), resumo de 5 linhas em português simples, linha do LOG. V1b só depois do V1 e **precisa de arquivo do PO** (não está liberado ainda: peça a liberação com os nomes do menor arquivo suficiente; o líder pergunta ao PO).

## Contexto fechado (leia)
`docs/adr/ADR-004-processos-threads-e-trava.md` (§5, §5.1 inteiro, §6, §8), `docs/adr/ADR-001-stack-hibrido-e-ponte.md`; `docs/state/reports/F0-S04-threads.md`; `prototypes/s04/fluxo_a/lote.py`, `CONTRATO.md`, `fluxo_a.py` (régua, A29: não muda); `prototypes/s04/obimcore/` (como o bloqueio do interpretador é solto); `docs/state/lotes/LOTE_OPUS_9/resultado.md` (§1.4, §2.3, §5.1); `tests/test_s04_t15*_*.py` (o padrão dos testes do T15 e suas réguas); `docs/state/cards/README.md`. Regras: ambiente de testes gráficos só em `xvfb-run` (nunca na tela real); não leia `~/openbim-medicao` nem IFC.

## Entrega
Cartões, oráculos, `resultado.md`. Retorno final em caveman com os caminhos absolutos. Não aprove provisoriamente.
