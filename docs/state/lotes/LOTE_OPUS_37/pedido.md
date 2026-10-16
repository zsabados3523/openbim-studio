# LOTE_OPUS_37: pedido (S04-T14c parte 3, PR 135; revisão independente, contexto fechado)

Revisar dois commits do ramo `s04-t14c-2-autotestes` que respondem à falha do Windows (run 38838633409, job 116773315921, windows-fluxo-b: 18 ok, 2 falhas):
- b8bda05 (oráculo, LOTE_OPUS_35): `rodar` em `tests/s04_fluxo_b_janela_aux.py` decodifica UTF-8 (`errors="replace"`); o teste `--versao` exige 1 TKernel e 1 `geometry_kernel_opencascade`.
- 6110468 (implementação): ramo `--versao` de `prototypes/s04/fluxo_b/autotestes.cpp` cria uma parede e gera a malha antes de `bibliotecas()`.

Julgar: (1) causa do TKernel e se a régua nova não afrouxa e prova "uma cópia de cada núcleo" (riscos no Windows); (2) decodificação UTF-8 sem esconder falha; (3) mudança mínima e correta no `autotestes.cpp`; (4) diff ≤400 linhas e `ci.yml` só acrescenta; (5) rodar `tests/test_s04_fluxo_b_janela.py` 2 vezes sob xvfb-run. Saída: APROVADO ou REPROVADO com lista numerada.
