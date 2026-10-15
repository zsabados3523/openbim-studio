<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE OPUS 15: revisão do PR 69 (ramo s04-t09)
Itens: F0-S04-T06c (oráculo) e F0-S04-T09 (câmera e substituição de malha). Revisor opus, só leitura, 2026-10-13. Veredito: **T06c APROVADO; T09 APROVADO com recomendações; nenhum achado bloqueante.** PR 69 mesclado pelo líder (linux, windows e appimage verdes; macOS informativo).

## Resumo dos vereditos
- T06c: casos (a) subida de 1 milhão de triângulos com pausas e conferência de que a grade velha some, (b) e (c) dtypes e erros (ValueError) presentes e fiéis. Arquivo de 399 linhas.
- T09: câmera na thread de desenho (fila da thread da janela, animação por relógio, parada imediata); `Cena.atualizar` por GlobalId com sequência estritamente crescente; deslocamento por lote recusado se diferente do primeiro; achados 4, 5, 6 e 10 do lote 14 tratados de verdade (deslocamento, create() falso repete, swapchain perdida recria a QRhi, dtypes uma vez). Regras de posse e ordem dos mutex sem inversão.

## Achados (todos recomendações)
1. **Forte, antes da T11/T12.** Trocar uma malha reenvia a cena inteira à placa (cena.cpp:150; viewport.cpp:189): o modelo pisca e o tempo até o quadro novo cresce com a cena (~40 MB, ~20 quadros, >300 ms no modelo de 1 milhão), o que pesa na M2b (p95 < 200 ms). Ação: medir M2b na T12 com 3.000 paredes; se passar de 200 ms ou piscar, substituição por lote (manter buffers antigos até o lote refeito estar na placa).
2. A interface `atualizar(lote_novo, guids_remover)` diverge de LOTE_OPUS_9 §1.4 (`atualizar(arquivo, criados, alterados, apagados)`). Registrar a escolha no LOG antes da T11: aceitar e anotar o custo no ADR-001, ou cartão pequeno com a forma da especificação por cima.
3. Corrida na inicialização dos dtypes estáticos (cena.cpp:75-78): `static` local roda código Python sob a trava de inicialização; risco de travamento mútuo com duas threads. Ação: montar em `registrar_viewport` ou soltar o bloqueio antes.
4. `Fim::Perdido` e `create()` falso sem caso no oráculo: gancho de teste estilo `perder_contexto`; caso "cena volta com a mesma câmera e `contextos` sobe".
5. Entradas não finitas (NaN/infinito) em orbitar, mover, animar_orbita e definir_camera envenenam a câmera: recusar com ValueError.
6. Fila da câmera cresce sem limite com a janela escondida: anotar ou fundir entradas do mesmo tipo.
7. O aviso do `create()` apaga o nome do backend em `info()`: restaurar ou campo próprio.
8. Lacunas do oráculo (para agente de oráculo): (a) `atualizar` concorrente com `adicionar_lote`/`limpar`; (b) `atualizar` que remove objeto da grade de 1 milhão no meio da subida; (c) `atualizar` com deslocamento diferente (hoje só `adicionar_lote`); (d) enquadrar com cena vazia; (e) T12 deve medir "primeiro quadro com sequência ≥ S", pois a sequência cai a 0 durante o reenvio.
9. Processo, aceito: T09 mexeu em viewport.cpp, CMake e ci.yml, fora dos "arquivos permitidos", inevitável e atribuído pelo lote 14. Diff de implementação ~240 linhas C++; oráculo 399.

## Para o PO
Câmera no motor de desenho, giro automático por relógio, troca por código e os três defeitos do lote anterior corrigidos. Atenção: cada troca de peça manda o modelo inteiro de novo à placa; em modelo grande pode piscar e estourar 200 ms. Medir na etapa de medições.
