# LOTE_OPUS_38: resultado (S04-T15a) — APROVADO

Revisor: Opus, contexto fechado, não escreveu nada da tarefa. Ramo `s04-t15a`, commit a919488.

## Verificações
1. Pontos do cartão: corretos. Comando com trava: `detalhe()` + `_publicar_ultimo` dentro do `try`, antes do `release` (fluxo_a.py:184-187). Livre: só com `acquire(blocking=False)`, solta logo, nunca espera (172-178). `_c_selecionar` só chama `_cont` na thread da janela (390-393); fora dela usa `_tam`, que só a thread da janela grava (`_bombear` 105, a cada processEvents; `_c_selecionar` 392). `t_painel_ms` só com `janela=False` ou na thread da janela (190-193). Contagem da base com `with self.trava` e solta antes do 1º comando (428-429).
2. Deadlock: nenhum. `_publicar_ultimo` não pega a trava; nenhum caminho pega a trava duas vezes; `_bombear` (inclusive a espera de 2 quadros da T14d) nunca roda com a trava presa; fora da thread da janela a espera só lê `cena.relogio()` (C++), sem Qt.
3. Mudanças declaradas: mesmas chaves no detalhe, em `ultimo` e no `medicao.json`; `t_comando_ms` fica microssegundos mais cedo (antes do `release`); `t0 <= t_comando <= t_quadro` continua (`_quadro` usa `max(min, t_cmd)`); M2/M2b/M4/M5 mudam só na ordem de microssegundos, M3 igual (roteiro roda na thread da janela). `medir_s04.py` não muda.
4. Testes antigos intocados (`--stat -- tests`: só o oráculo novo, +246). `ci.yml`: +1 linha no `linux` e +1 no `windows`, logo após a linha do `test_s04_fluxo_a.py`; nada removido. `CONTRATO.md`: +4 linhas.
5. Tamanho: 355 inserções, 26 remoções (≤400).
6. Execuções (xvfb-run, offscreen, obimcore do scratchpad): oráculo com `OBIM_S04_T15_OBRIGATORIO=1` 2x: 10/10, 0 pulos. `OBIM_CI=1` fluxo_a + metas + camera_selecao: 201 passaram, 2 pulos previstos. Extra: `test_s04_fluxo_b_janela.py` 20/20.
   Mutantes (cópias no scratchpad): M1 `ultimo` publicado depois do `release` -> 5 falhas; M2 livre com `acquire()` que espera -> 1 falha (10 s); M3 `_cont.width()` em qualquer thread -> 1 falha. Os 3 reprovados.

## Observações (não bloqueiam)
1. [menor] fluxo_a.py:193 `pub.update(t_painel_ms=...)` acrescenta a chave ao dict já publicado em `ultimo` depois de soltar a trava (só na thread da janela ou sem janela). Leitor de outra thread pode ver `ultimo` sem `t_painel_ms` por um instante; nada lê esse campo de `ultimo` hoje. Aceitar ou citar no CONTRATO na T15b.
2. [informativo] `_tam` só se renova via `_bombear`/`_c_selecionar` na thread da janela; laço de eventos por fora (`app.exec()`, `processEvents` direto) não o renova até o próximo `_bombear`. Hoje todo bombeamento do fluxo A passa por `_bombear`.
3. [informativo, T15b] Roteiro rodado em outra thread com janela não terá `t_painel_ms` no passo 4a: `_metas` M3 (fluxo_a.py:461) e `medir_s04.py:189` dariam KeyError. É o comportamento pedido; tratar na T15b.

## Para o PO
A correção deixa o fluxo A seguro quando outra linha de execução mexe no modelo ao mesmo tempo, sem travar a janela e sem números de tempo falsos. Testes novos e antigos verdes; três defeitos plantados de propósito foram pegos.
