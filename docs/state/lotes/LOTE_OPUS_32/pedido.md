# Lote Opus 32 (pedido): revisão da fase 2 do F0-RG-27
- Escopo: um item (T3), a régua nova do caso `c_threads` em `tests/test_s04_selecao_c.py` (commit 370c8b9, ramo `rg-27-diagnostico`).
- Contexto fechado: `cards/F0-RG-27.md` (seção "Fase 2: especificação (Opus)"), `reports/F0-RG-27-diagnostico.md`, `git diff origin/main..HEAD -- tests/test_s04_selecao_c.py`, o teste (linhas 190 a 352), `prototypes/s04/obimcore/nucleo/cena.cpp`, `cena.h`, `motor.h` (selecionar, limpar), `selecao.cpp`, `ponte_viewport.cpp`.
- Perguntas: (1) a causa está certa ou há corrida real no C++; (2) a régua nova pega todo defeito real que a velha pegava (mínimo 3 mutações); (3) o risco da conferência "troca" é aceitável; (4) a especificação é clara e o "não é afrouxamento" vale.
- Regra do PO: o teste não pode ser afrouxado, pulado nem desligado.
- Saída: aprovado ou reprovado, lista numerada, em `lotes/LOTE_OPUS_32/resultado.md`. O revisor não escreveu nada desta tarefa.
