<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F1-D3D11: um dispositivo D3D11 por processo (herdeiro do F0-S04-T07e)
- Classe: **T3** (threads, desenho, ponte C++) · Tamanho: M · Oráculo: opus · Implementa: sonnet · Revisa: opus, em lote
- Origem: decisão do PO em 2026-10-22 (adiar à F1). `reports/F0-S04-T07c.md` (causa e 300 voltas).
## Objetivo
No Windows com desenho por software (WARP), destruir o dispositivo D3D11 na thread de desenho trava de vez em cerca de 1 de cada 110 a 300 voltas do caso `destruir janela` (`~QRhi` → `d3d10warp!UMContext::Flush`/`FlushAllResources`). A thread presa segura uma trava global do WARP: qualquer dispositivo novo do processo (`D3D11CreateDevice` → `OpenAdapter10_2`) fica parado também, então abandonar a thread depois de 5 s (T07e) só evita o congelamento ao sair. A correção de fundo é **não criar e destruir um dispositivo por viewport**: um dispositivo (ou pool) por processo, reaproveitado entre viewports.
## Critérios de aceite (rascunho)
1. Laço de ≥ 1.000 voltas de `destruir janela` no Windows do CI sem nenhuma trava (hoje 1 em 300).
2. `paradas_atrasadas` continua 0 em operação normal; os testes do viewport A e B passam sem edição.
3. Sem regressão de memória do pesado nem de tempo (M2b, T29).
## Fora de escopo
Windows com placa real (T28) e outros sistemas.
## Próximo passo
Entra na F1 depois do portão da F0; cartão a detalhar com o ADR-004.
