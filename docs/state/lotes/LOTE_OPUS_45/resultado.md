# LOTE_OPUS_45: resultado (S04-T15g, oráculo): REPROVADO
Revisor: Opus independente. Ramo `s04-t15g-cartao`, commit 37a7ef0 (+ ajuste do cartão do líder). Saídas e mutantes no scratchpad `l45/`.

Execuções: `lote.py` de hoje 6 falham e 1 passa (controle sem postador); correção de referência 7 de 7 (44 s); mutante B (constrói no postador guardando a referência forte) reprova regra 1, regra 2 e queda (134): guardar a referência não resolve. Medições do autor: hoje 20 de 20 e 20 de 20 falham (13+9 quedas, 7+11 eventos perdidos); referência 0 de 40.

## Problemas
1. **(bloqueia) O oráculo contradiz a regra 4 nova do cartão** (`faulthandler.enable()` no INÍCIO de `medir`, `__main__` intacto): a trava estática (linha 236) procura `faulthandler.enable()` depois de `if __name__ == "__main__":`. O hash trava só a função `main()`, não o bloco `__main__`; a referência foi feita pelo cartão antigo e passa 7 de 7. O mutante A (cumpre o cartão novo) tem 6 passando e 1 reprovado. Nada confere `faulthandler` em `medir`.
2. A docstring (item 4) ainda diz que o `__main__` liga o `faulthandler` e que "fora de `medir` e do `__main__`" o `lote.py` fica igual: tem de dizer "no início de `medir`" e "o `__main__` não muda".
3. O bloco `__main__` de `lote.py` não está travado: o "nada mais" do cartão não é cobrado ali.
4. Honestidade da taxa: o comentário "cair = código 134/139" e o item 3 da docstring escondem que ~35 a 55% das falhas de hoje não são quedas, são saída 0 com eventos perdidos (`RuntimeError` "_bombear" ou `TypeError` em `resumo`). Escrever os dois modos com os números.

## Corretos
Espião determinístico (thread, instante, identidade, ordem); teste de queda sem espião; regras 2 e 3 com mensagens; nenhuma régua ou constante afrouxada; as travas deixam espaço para a correção mínima; as 6 decisões fora do cartão são aceitáveis (ressalva: o piso de 3.001 eventos = 60 s não tem medição que o justifique).

## Recomendações
1. Trava: `inspect.getsource(lote.medir)` contém `faulthandler.enable()` e ele vem antes de `QEventLoop()`; travar por hash o bloco `__main__` (o de 128af53); opcional: em `c_espiao`, `faulthandler.disable()` antes de cada `_medir` e gravar `faulthandler.is_enabled()` depois, com e sem mouse.
2. Depois de corrigir: mutante A deve dar 7 de 7; mutante sem `faulthandler` reprova só o teste 7; a referência passa a ter o `faulthandler` em `medir`.
3. Windows (riscos, não fatos): `ponteiro` conta disparos do relógio, não movimento real; QTimer de 1 ms pode disparar a ~15,6 ms e `ponteiro >= 1000` em 15 s reprovar correção certa. Sugestão: `Qt.PreciseTimer` e contar só disparos em que `QCursor.pos()` mudou; piso a calibrar no 1º CI do Windows. Tetos `s < 12` e 40 s têm folga mas não foram medidos no Windows.
4. Piso de 3.001 (60 s): basear na maior duração real de uma rodada do caso `lote` no CI do Windows, ou subir o piso (os 30.001 da referência servem).
5. Custo no CI: ~44 s no Linux; o arquivo em `tests/` também é coletado pelo passo genérico `pytest -q -rs tests` (roda 2 vezes por job). Aceitável.
6. `faulthandler.enable()` no Windows pode imprimir avisos de exceções tratadas: só ruído em stderr.
