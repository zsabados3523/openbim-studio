# Lote Opus 26: PR 90 (T14b) e PR 87 (T14a, diff novo)

## (A) PR 90, T14b: APROVADO (nada bloqueia)
Verificado: camada pura sem Python (grep, includes do alvo, `nm -u` vazio); comportamento idêntico (27 entradas com mesma exceção/mensagem nas duas versões); ordem de mutexes inalterada; propriedade (`Emprestado` vive mais que o GIL solto; nada guardado de numpy; retornos int64/optional<string>); conversões antes de soltar o GIL (contador em outra thread anda durante lote de ~1M triângulos); carga de 6 threads sem impasse; 139 testes passam, 1 de tempo oscila (já oscilava; PR mais rápido com -O3); CI linux/windows verdes.
Opcionais: (1) CMakeLists.txt:12-13 visibilidade hidden no núcleo (módulo exporta 39 símbolos `obim::`, +22%); (2) nucleo/motor.h:47-48 guardar `NOMINMAX`/`WIN32_LEAN_AND_MEAN` com `#ifndef` (aviso C4005); (3) nota: `selecionar` solta o GIL também no erro; (4) nota T14c: destruir o `Viewport` antes da `QApplication` (segfault na coleta final já existente); (5) diff 529 linhas: exceção aceita.

## (B) PR 87, T14a: APROVADO no conteúdo (itens 1, 4, 5, 6); merge BLOQUEADO até a prova de CI
Oráculo: 55 passam, 1 falha (guarda do ci.yml). Condição de merge, nesta ordem: PR 82 entra; líder põe `export OBIM_S04_T14A_OBRIGATORIO=1` em linha própria antes do `pytest` do fluxo B (linux e windows); CI verde com o oráculo da T14a rodando de verdade. A aprovação vale só para este conteúdo; qualquer mudança em `paredes.cpp`/`ponte.cpp` para consertar o Windows volta ao Opus.
Opcionais: `estado()` do teste de falha (test_s04_fluxo_b_paredes.py:561-564) incluir `contextos_do_projeto`; registrar no CONTRATO que base sem `IfcProject` não atualiza a lista.
