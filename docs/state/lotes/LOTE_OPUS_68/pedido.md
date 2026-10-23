<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_68: ADR-001 e ADR-004 com números (T19, classe TA, F0-S04)
Pedido do líder (2026-10-21), **classe TA, Opus, esforço médio**. Você escreve os dois ADR; o PO aprova depois por um resumo de 5 linhas. Escreva SÓ: `docs/adr/ADR-001-*.md` (crie se não existir; olhe `docs/adr/README.md`, `v2/` e `docs/state/arquivo/` para o nome e o formato certos), `docs/adr/ADR-004-processos-threads-e-trava.md` (atualize) e `docs/state/lotes/LOTE_OPUS_68/resultado.md`. Sem commit, sem push, sem merge; informe os caminhos absolutos. Não leia `~/openbim-medicao` nem IFC (os números estão nos relatórios do repositório).

## Decisões do PO (2026-10-21, no chat)
1. **ADR-001: manter a estrutura híbrida** (Python + núcleo em C++); C++ puro rejeitado como não necessário.
2. **ADR-004: forma mista**, ideia do PO (a validar contra os números): **forma 1** (thread Python à parte) para os **cálculos de geometria**; **forma 2** (fatias na thread da janela) para os **comandos longos**. Teoria dele: melhor tempo de resposta sem sacrificar nenhuma das duas implementações. Decisão anterior (17/10, `PO.md`): "reforçar a forma 1".
Seu trabalho: escrever os ADR com os números reais; **avaliar a forma mista contra os dados e dizer com honestidade se os números a sustentam, onde ela é só hipótese e o que ainda falta medir** (se faltar medida, escreva-a como condição de aceite de um cartão de validação, não como fato). Não afrouxe meta nem régua.

## Contexto fechado (leia)
`docs/state/arquivo/F0-S04/cartoes/F0-S04-T19.md`; `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_9/resultado.md` (§1 a §6: casos R1 a R13, metas M1 a M6); `docs/adr/ADR-004-processos-threads-e-trava.md` e `ADR-005-dependencias-e-build.md` (§7.1); `docs/state/reports/F0-S04.md` (tabelas) e `F0-S04-threads.md` (formas 1 e 2, Linux local, Windows e placa real); `F0-S04-T21.md`, `T22.md`, `T24.md`, `T29-placa-memoria.md` e `-2.md`, `T29e-ensaio.md`, `T30-placa.md`, `T30c-dados-reais.md`, `T23.md`; `lotes/LOTE_OPUS_57`, `62`, `65`, `66` (`resultado.md`); `docs/state/PO.md` (decisões de 17/10).
Números novos desde o relatório de 17/10 (todos na placa real RTX 3070 do PO, `reports/`): memória do arquivo pesado 5.863 e 5.958 MB (pior) contra 6.000 (bloco 250 + reinício planejado, T29/T29e); abertura 51 s; troca de parede (M2b) mediana 33 a 49 ms, pior 82,8 ms contra 200 (T-2: sub-lotes de até 8 MiB, T30); CI do Windows de 34 para 17 min, meta de 10 min não atingida (T23; decisão do PO: seguir (a) instalador, depois (b) dividir testes). Forma 1: mouse atrasa 0,7 a 0,95 s (mediana) com lote de 1.000 peças, passa a parede de 150 aberturas; forma 2: mouse 13 ms (mediana), parede de 150 aberturas ~200 ms contra limiar de 101,6 ms.

## Entrega
1. ADR-001 e ADR-004 prontos para o PO (números, decisão, o que ficou aberto, consequências, o que deixa de valer). 2. `resultado.md`: avaliação da forma mista (sustentada / parcialmente / não, com os números), lista de cartões necessários (ex.: validação da forma mista com os mesmos critérios, implementação, T3 com oráculo e revisão Opus), perguntas ao PO (só o que é dele), **resumo de 5 linhas em português simples, sem siglas**, linha do LOG. Retorno final em caveman com os caminhos absolutos. Não aprove provisoriamente.
