# F0-S04-T15f: diagnóstico da instabilidade do caso `lote`

Autor: sonnet (skills systematic-debugging e verification-before-completion). Data: 2026-10-16. Só diagnóstico: nenhum teste, `medir_s04.py`, fluxo B, meta ou régua foi alterado. Sondas e scripts ficaram fora do repositório (scratchpad).
**Resultado em uma linha: NÃO REPRODUZIU no Linux em 58 execuções (696 rodadas medidas). A causa não foi localizada. Duas hipóteses do cartão (H1 em parte, H2) foram descartadas com medida; as outras duas ficam em aberto porque dependem do Windows.**

## 1. O que o CI do Windows realmente mostrou (logs lidos com `gh`, só leitura)
- Tentativa 1 (job `windows-viewport-a`): `test_t15b_m5_na_forma[2]` reprovou com uma única mensagem: "rodada 0: janela de 1 s com 0 quadros". Os outros 11 testes passaram; a mediana e a regra dos 200 ms não reprovaram, então foi **uma rodada só** (a rodada 0 da forma 2, a primeira com o postador de mouse nessa forma). Os testes todos levaram 145 s no Windows (cerca de 70 s no Linux).
- Tentativa 2: o subprocesso caiu com 3221226356 (0xC0000374, corrupção de heap). Antes de cair imprimiu **uma única linha**, "forma 1 controle: quadros maior 33 ms, pulso maior 693 ms". Em `lote.main` a linha só sai **depois** de a rodada terminar e de o `desfazer` e o `esperar 300 ms` dela terminarem. Logo a 1ª rodada (forma 1, controle, sem postador de mouse) e o primeiro `desfazer` de 1000 paredes **já tinham passado**. A queda foi na 2ª rodada: forma 1 com postador de mouse (a fase parada de 2 s, o início da thread do postador e do filtro de eventos, o lote inteiro na thread `lote-forma-1` com a thread da janela em `QEventLoop`, o `join`, o `_bombear`, o `resumo`) ou no `desfazer`/`esperar` dessa mesma rodada. Em relação à 1ª rodada, o que há de novo na 2ª é o postador, o filtro e três threads Python ao mesmo tempo. Cuidado: corrupção de heap costuma ser detectada numa alocação ou liberação posterior, não onde a escrita errada aconteceu; o defeito pode estar antes.
- O stderr dessa queda só tem a mensagem "No stream support: lark" (ruído antigo). **Não há pilha de threads**: o subprocesso só arma `faulthandler.dump_traceback_later` (para travamento), não `faulthandler.enable()`, e o ambiente do CI não define `PYTHONFAULTHANDLER`. Não sei se o faulthandler do Python captura o 0xC0000374 no Windows (não testado aqui). A asserção de `caso()` já imprime o fim do stdout e do stderr do subprocesso, e foi dela que saiu o log acima.
- Linux local (implementador da T15e): 8 erros de fixture uma só vez, sem log. **Não reproduzido.** Sem log, aqueles 8 erros podem ter sido queda, `TypeError` ou limite de tempo; a margem de 0 ms contra 5000 ms do `_bombear` (seção 3) torna o `TypeError` improvável, mas não o descarta.

## 2. Reprodução no Linux (sempre sob `xvfb-run -a`; mesmos argumentos da fixture `med`: `lote 300 1000 3`)
Cada execução = 12 rodadas (2 formas x 3 repetições x com e sem postador de mouse). `PYTHONFAULTHANDLER=1`, stdout, stderr e código de saída guardados por execução.

| Condição | Execuções | Quedas | TypeError / erro Python | Janela com menos de 20 quadros | Falha da régua M5 ou da parada | Sem falha |
|---|---|---|---|---|---|---|
| Normal (2 execuções ao mesmo tempo na máquina) | 32 | 0 | 0 | 0 | 0 | 32 |
| Carga: execução presa a 4 núcleos (`taskset 0-3`) + 4 laços ocupados nos mesmos núcleos | 15 | 0 | 0 | 0 | 0 | 15 |
| Depuração de memória (glibc `malloc.check=3` + `perturb=165` + `libc_malloc_debug` + `PYTHONMALLOC=debug`; 2 ao mesmo tempo) | 10 | 0 | 0 | 0 | 0 | 10 |
| Execução avulsa inicial (checagem do script) | 1 | 0 | 0 | 0 | 0 | 1 |
| **Total** | **58** | **0** | **0** | **0** | **0** | **58** |

Além disso, o teste da T15b inteiro (`OBIM_CI=1 OBIM_S04_T15_OBRIGATORIO=1 pytest tests/test_s04_t15b_formas.py`, que também roda o caso `trava`, com troca de forma 1 para 2 no mesmo processo) foi executado 3 vezes em sequência: **12 passaram, 0 falharam, 0 pulos, nas 3** (69 a 70 s cada). Cada uma contém mais uma execução do caso `lote`, fora da tabela.

Em todas as da tabela: código de saída 0, stderr sem nada além do ruído "lark" e do aviso de localidade.

Margens medidas (684 rodadas dos três grupos; mais as sondas em 180 rodadas com carga):
- Quadros por janela de 1 s: **mínimo 62** (a régua exige 20). Maior intervalo entre quadros: 26 ms normal, 29 ms com carga e 26 ms com depuração (a régua aceita 100 ms de mediana). A carga não tirou a viewport do ritmo; ela alonga o lote (3,8 a 6,2 s contra 2,2 a 2,8 s) mas não faz faltar quadro.
- "Janela surda" (maior intervalo do pulso de 10 ms, no controle, que é o que a regra de parada lê): forma 1 mediana 340 ms (máx 863); forma 2 mediana 786 ms (máx 829). Com carga: forma 1 mediana 161 ms (máx 814); forma 2 mediana **1.482 ms** (máx 2.169). A regra de parada só dispara se **as duas** formas passarem de 1 s: não disparou em nenhuma das 58, porque a forma 1 ficou sempre abaixo. Mesmo assim, com carga a forma 2 sozinha já passa de 1 s: a margem dessa regra depende da máquina.

## 3. As hipóteses
- **H1 (postador de mouse mexe em Qt fora da thread da janela / continua vivo depois): descartada no que dá para provar no Linux.**
  - Sonda em `lote.py` (cópia, fora do repositório): depois de `poster.join(5)`, `poster.is_alive()` deu **False em 180 de 180** rodadas; o `join` levou no máximo 5 ms; 0 eventos de mouse sem tratamento.
  - Posse do evento: `shiboken6.ownedByPython(ev)` vale True antes de `QCoreApplication.postEvent` e **False depois** (o Qt assume o objeto). Então o Python não libera um evento que ainda está na fila do Qt.
  - Estresse: 3 threads postando 100.000 `QMouseEvent` cada (300.000 por execução), thread da janela em `QEventLoop`, com depuração de memória: 3 execuções, 900.000 eventos postados e 900.000 tratados, 0 erro. Nada indica corrupção de memória por postar evento de outra thread no Linux.
  - Fica em aberto: o mesmo no Windows (outro alocador e outro Qt).
- **H2 (`_bombear(..., 5000)` devolve False sem avisar, `m[2]` fica None, TypeError em `resumo()`): não ocorreu; margem enorme.** Nas 180 rodadas sondadas o `_bombear` voltou `True` em **0 ms** (o limite é 5.000 ms) e 0 eventos ficaram sem tratamento. Continua sendo um defeito de robustez real do código (o resultado não é conferido), mas nada indica que seja a causa da queda de heap, que não passa por esse ponto.
- **H3 (troca da forma 1 para a 2 deixa algo vivo): sem sinal.** 58 execuções passaram pelas duas formas, com e sem carga, sem erro. A queda do Windows aconteceu ainda na forma 1 (2ª rodada do programa), então a troca de forma não explica aquela queda.
- **H4 (oscilação do runner estoura a régua de 1 s):** o Linux sob carga **não** estourou (62 quadros por janela contra o mínimo de 20, mesmo com o lote durando o dobro). No Windows não dá para medir aqui. Observação sobre o Windows: no CI a viewport pode depender mais da thread da janela do que no Linux (aqui os quadros seguem a 60 por segundo mesmo com a thread da janela parada 0,74 s dentro de `spatial.assign_container`); uma única operação passando de 1 s no runner lento já faz uma janela de 1 s sem quadro. É uma explicação possível para a tentativa 1, **não provada**.

## 4. Causa mais provável
Não há causa provada. O que se sabe: (a) a queda de heap do Windows aconteceu no começo da execução, na 2ª rodada (a 1ª rodada com o postador de mouse) ou logo depois dela, e nada parecido apareceu em 58 execuções no Linux, nem com depuração de memória; (b) a "janela sem quadros" é de uma rodada só entre 12 num runner que roda tudo na metade da velocidade. A explicação mais barata para (b) é lentidão do runner, e para (a) alguma peça específica do Windows (alocador/CRT, D3D11, ou o que a 2ª rodada traz de novo: o postador de mouse, o filtro de eventos e a 3ª thread Python), que o Linux não exercita do mesmo jeito. Isso é uma suspeita, não um fato.

## 5. Proposta de correção/medida (≤5 linhas; nada foi feito)
1. Cartão pequeno (T1/T2) em `lote.py`: marcar cada passo no stdout com `flush` ("antes do postador", "depois do lote", "depois do join", "depois do bombear", "antes/depois do desfazer") para o log do CI mostrar em que ponto da rodada 2 caiu; conferir `poster.join` e o retorno de `_bombear` e falhar com mensagem clara (resolve o TypeError latente, que hoje é só robustez).
2. Ligar o `faulthandler` no subprocesso (`PYTHONFAULTHANDLER=1` no job, em `ci.yml`, ou `faulthandler.enable()` no `__main__` do oráculo): se ele pegar o 0xC0000374, dá a thread e a linha que o cartão pede. Guardar stdout e stderr inteiros como artefato só ajuda depois dos marcadores do item 1; sozinho não traria nada além do que a asserção já imprime. `ci.yml`: **precisa do OK do PO**.
3. Se a queda voltar, um teste mínimo no CI que repita só o trecho suspeito (postador de mouse postando eventos enquanto uma thread Python mexe no IFC, em laço) para separar "postador" de "lote".
4. Não mexer em limite, régua nem meta por causa disso.

## 6. O que falta saber
- Em que ponto da rodada 2 (forma 1 com postador de mouse) o Windows cai: início do postador, lote com as três threads, `join`/`_bombear`, ou o `desfazer` dessa rodada (os marcadores do item 1 respondem).
- Se a "janela sem quadros" do Windows vem de a viewport D3D11 depender da thread da janela (medir o maior intervalo de quadros e o pulso na forma 2 no Windows, no log do CI).
- Se a taxa é de 1 em 12 rodadas ou menos: no Windows houve 2 defeitos distintos em 3 tentativas da mesma rodada do CI, mas o T15b passou em 6 ou mais rodadas antes; sem mais dados não dá para estimar a taxa.

## 7. Limites desta medida
Linux apenas (llvmpipe, xcb sob Xvfb). Nunca na tela real. Dois processos ao mesmo tempo nos lotes "normal" e "depuração" (não é máquina ociosa). O lote "carga" ficou em 4 núcleos de 16. Alocador do Windows, D3D11 e WARP não foram exercitados. Não é "estável": são 0 ocorrências em 58 execuções, e a falha original nem foi vista no Linux uma única vez com log guardado.
