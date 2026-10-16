# LOTE_OPUS_36: resultado (F0-S04-T14d, revisão Opus independente)
**APROVADO.** Base: `git diff origin/main` em 531fa63 (fluxo_a.py +9/-1, CONTRATO.md 1 linha, ci.yml 2 linhas).
1. Regra = B. `_camera` (fluxo_a.py:379-382) marca `_t_cam = self._relogio()` DEPOIS de o método da Cena voltar, só para enquadrar/orbitar/camera_mover/aproximar e só com `cena`; `_c_camera` (:392) marca depois de `definir_camera`. `animar_orbita`/`parar_animacao` não marcam (fora de escopo, O5, igual ao B). `_c_selecionar` (:371-372) espera, dentro do próprio comando, 2 entradas de `self.cena.relogio()` com t >= `_t_cam`, 10 s, e levanta `TimeoutError` sem chamar `Cena.selecionar`; idêntico a main.cpp:145-146. `self._relogio` = `obimcore.agora` com janela (mesmo relógio de `relogio()`).
2. `janela=False`: `_t_cam` nunca muda (guarda `cena is not None`) e `_c_selecionar` volta `[]` antes da espera. Sem mudança.
3. Travas: `selecionar` e os comandos de câmera estão em LIVRES (sem `self.trava`); a espera não segura trava nenhuma, então não há deadlock nem reordenação. `_bombear` só chama `processEvents` na thread principal; em outra thread só consulta `relogio()` e dorme 0,5 ms (os quadros vêm da thread de desenho). Tempos de M2..M5 não tocados; só o `ms_total` do 3c cresce.
4. Testes: `git diff origin/main --stat -- tests` = só o oráculo novo (149 linhas); nada existente editado; `tests/s04_fluxo_aux.py` intacto.
5. Mutantes (cópia no scratchpad, oráculo intocado): M1 "espera 1 quadro" = 5 falham de 9 (os 5 de contagem de quadros); M2 "marca só enquadrar" (sem `camera` nem os outros 3) = 6 falham de 9. Ambos reprovados.
6. ci.yml: só acrescenta `tests/test_s04_fluxo_a_camera_selecao.py` às listas `OBIM_CI=1` do linux (:131) e do windows (:292), logo após `test_s04_fluxo_a.py`; nada some.
7. Execução: `OBIM_S04_T11_OBRIGATORIO=1 xvfb-run -a pytest tests/test_s04_fluxo_a_camera_selecao.py tests/test_s04_fluxo_a.py`, 2 vezes: 53 passaram, 1 pulado (sentinela de escala, test_s04_fluxo_a.py:329, só com T11C), 57 s e 56 s. Os 9 do oráculo passaram nas 2.
## Pendências (não bloqueiam a aprovação; são critério de aceite 3, só no CI)
P1 (baixa). `tests/test_s04_fluxo_b_janela.py` (comparação A x B, inclusive 3c) não rodou aqui: executável `fluxo_b_janela` ausente localmente (16 pulados). Conferir no CI que roda verde.
P2 (baixa). Conferir no log do CI que o oráculo novo RODA (não pula) no linux e no windows (WARP).
## Observação (sem ação)
O1. `_t_cam` é atribuído/lido sem trava entre threads; é um float único e a leitura velha só faz esperar quadros que já existem ou existirão. Aceitável, mesmo modelo do B.
