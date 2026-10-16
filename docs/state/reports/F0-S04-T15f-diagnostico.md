# F0-S04-T15f: diagnóstico da instabilidade do caso `lote`

Autor: sonnet (skills systematic-debugging e verification-before-completion). Data: 2026-10-16. Só diagnóstico: nenhum teste, `medir_s04.py`, fluxo B, meta ou régua foi alterado. Sondas e scripts ficaram fora do repositório (scratchpad).
**Resultado em uma linha (corrigido após a revisão do lote 43): o `lote` completo NÃO caiu em 58 execuções no Linux, mas o mecanismo suspeito (H1) foi reproduzido no Linux com uma sonda pequena, só com Qt/PySide. Ele é compatível com a queda do Windows; não está provado que seja o mesmo evento. Só o CI do Windows confirma. H2 e H3 foram descartadas com medida; H4 e a "janela sem quadros" seguem abertas.**

## 1. O que o CI do Windows realmente mostrou (logs lidos com `gh`, só leitura)
- Tentativa 1 (job `windows-viewport-a`): `test_t15b_m5_na_forma[2]` reprovou com uma única mensagem: "rodada 0: janela de 1 s com 0 quadros". Os outros 11 testes passaram; a mediana e a regra dos 200 ms não reprovaram, então foi **uma rodada só** (a rodada 0 da forma 2: a régua recebe primeiro as rodadas com postador de mouse, depois as de controle; é a 1ª rodada com postador nessa forma). Os testes todos levaram 145 s no Windows (cerca de 70 s no Linux).
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

Margens medidas. Origem dos números de rodadas: cada execução tem 12 rodadas; 58 x 12 = 696 seria o total contando a execução avulsa inicial, mas as margens abaixo foram recalculadas dos dados brutos só dos três grupos da tabela (32 + 15 + 10 = 57 execuções x 12 = **684 rodadas**; a avulsa foi só checada pelo analisador). As sondas internas (`poster_vivo`, `_bombear`) existem apenas nas 15 execuções com carga: 180 rodadas.
- Quadros por janela de 1 s: **mínimo 62** (a régua exige 20). Maior intervalo entre quadros: 26 ms normal, 29 ms com carga e 26 ms com depuração (a régua aceita 100 ms de mediana). A carga não tirou a viewport do ritmo; ela alonga o lote (3,8 a 6,2 s contra 2,2 a 2,8 s) mas não faz faltar quadro.
- "Janela surda" (maior intervalo do pulso de 10 ms, no controle, que é o que a regra de parada lê): forma 1 mediana 340 ms (máx 863); forma 2 mediana 786 ms (máx 829). Com carga: forma 1 mediana 161 ms (máx 814); forma 2 mediana **1.482 ms** (máx 2.169). A regra de parada só dispara se **as duas** formas passarem de 1 s: não disparou em nenhuma das 58, porque a forma 1 ficou sempre abaixo. Mesmo assim, com carga a forma 2 sozinha já passa de 1 s: a margem dessa regra depende da máquina.

## 3. As hipóteses
- **H1 (o postador de mouse constrói `QMouseEvent` fora da thread da janela): REPRODUZIDA no Linux com uma sonda pequena; compatível com a queda do Windows, não provado que seja o mesmo evento.**
  - Achado do revisor Opus (lote 43, sondas em `scratchpad/l43/`, só Qt/PySide, sem `obimcore`): uma thread Python constrói um `QMouseEvent` e chama `postEvent` na janela, enquanto a thread da janela roda um `QEventLoop` com filtro Python (o padrão de `posta()` em `lote.py`, linhas 146-160). A glibc acusa "malloc(): unaligned tcache chunk detected" (abort) ou falha de segmentação (139), a mesma classe do 0xC0000374 do Windows. Com o ponteiro do X se mexendo (`QCursor.setPos` a cada 1 ms), 20 s, 1 postador a cerca de 5.000 eventos/s:

    | Variante | Quedas |
    |---|---|
    | evento construído na thread do postador, dispositivo primário | 3 de 3 (com depuração de memória: 3 de 3) |
    | idem, com `del ev` logo após `postEvent` | 3 de 3 |
    | idem, com `QPointingDevice` próprio | 3 de 3 |
    | **eventos construídos antes, na thread da janela; o postador só chama `postEvent`** | **0 de 3** (cerca de 114 mil postados) |
    | construir e postar na própria thread da janela | 0 de 3 (2,2 milhões de eventos) |

    Sem o ponteiro se mexendo é mais raro (1 de 6 com 1 postador; 2 de 3 com 2). O que liga e desliga o sintoma é **construir o `QMouseEvent` fora da thread da janela**: o construtor lê e escreve estado guardado no dispositivo (o 2º evento herda o `globalLastPosition` do 1º). O mecanismo exato dentro do Qt/PySide não foi achado (sem gdb).
  - Conferência por amostragem (esta correção): rodei `sonda_corrida.py mexe 20 primario 1` do revisor 2 vezes sob `xvfb-run -a`: 2 de 2 quedas (1 abort "unaligned tcache chunk", 1 falha de segmentação). Confere com a tabela dele.
  - Cuidado com o alcance: a sonda posta cerca de 100 vezes mais rápido que o `lote.py` (1 evento a cada 20 ms) e mexe o ponteiro, coisa que o `lote.py` não faz. Uma taxa de queda de uns 0,2% por execução seria compatível com 0 quedas em 58. Por isso "mecanismo reproduzível e compatível com a queda", e não "causa provada".
  - O que eu medi antes e **não** prova nada sobre H1: (1) `poster.is_alive()` False em 180 de 180 rodadas e `join` em no máximo 5 ms (só diz que o postador termina; não diz que ele é seguro); (2) `shiboken6.ownedByPython(ev)` True antes e False depois de `postEvent` (o Qt assume o objeto, mas o risco é na **construção** do evento, não na posse); (3) um teste de estresse com 3 threads x 100.000 eventos, 900.000 postados e 900.000 tratados, 0 erro. Esse estresse **não exercitava o perigo**: postava em rajada (pausa de 0,5 ms a cada 50 eventos), formando fila grande, e sem o ponteiro se mexendo; o revisor repetiu esse ritmo e também deu 0 de 3. O perigo aparece quando a janela entrega em dia, como no `lote.py`. Portanto "900.000 eventos, 0 erro" não é evidência a favor nem contra H1.
- **H2 (`_bombear(..., 5000)` devolve False sem avisar, `m[2]` fica None, TypeError em `resumo()`): não ocorreu; margem enorme.** Nas 180 rodadas sondadas o `_bombear` voltou `True` em **0 ms** (o limite é 5.000 ms) e 0 eventos ficaram sem tratamento. Continua sendo um defeito de robustez real do código (o resultado não é conferido), mas ele não explica a queda de heap (não é um acesso de memória).
- **H3 (troca da forma 1 para a 2 deixa algo vivo): sem sinal.** 58 execuções passaram pelas duas formas, com e sem carga, sem erro. A queda do Windows aconteceu ainda na forma 1 (2ª rodada do programa), então a troca de forma não explica aquela queda.
- **H4 (oscilação do runner estoura a régua de 1 s):** o Linux sob carga **não** estourou (62 quadros por janela contra o mínimo de 20, mesmo com o lote durando o dobro). No Windows não dá para medir aqui. **Possibilidade aberta (lote 43):** o "0 quadros em 1 s" da tentativa 1 pode ser um efeito precoce do mesmo defeito do postador (H1), e não só lentidão do runner; o dado disponível não separa as duas. Observação sobre o Windows: no CI a viewport pode depender mais da thread da janela do que no Linux (aqui os quadros seguem a 60 por segundo mesmo com a thread da janela parada 0,74 s dentro de `spatial.assign_container`); uma única operação passando de 1 s no runner lento já faz uma janela de 1 s sem quadro. É uma explicação possível para a tentativa 1, **não provada**.

## 4. Causa mais provável
Suspeita principal: construir `QMouseEvent` na thread do postador (H1), que no Linux reproduz corrupção de heap em sonda pequena. É a única causa com mecanismo reproduzido; não está provado que a queda do Windows seja esse evento. O que se sabe do Windows: a queda foi na 2ª rodada do programa (a 1ª com postador, que é o que ela traz de novo, junto com o filtro de eventos e a 3ª thread Python) ou no `desfazer` dela, e a "janela sem quadros" ocorreu numa rodada com postador. Não ficou provado que o `lote` completo caia no Linux (0 em 58, o que é compatível com uma taxa baixa). Para a "janela sem quadros" continuam abertas lentidão do runner e efeito precoce do mesmo defeito.

## 5. Proposta de correção (nada foi feito; vira cartão T15g, T3, oráculo e implementação em agentes diferentes, revisão Opus em lote)
**Principal:** em `lote.py` (`medir`, bloco do postador), construir os `QMouseEvent` na thread da janela antes de t0 (pré-alocar com folga; falhar com mensagem clara se acabarem). O postador só chama `postEvent(janela, eventos[k])` no instante agendado e continua sendo a 3ª thread, com o atraso contado do AGENDADO. Trocar o dispositivo ou apagar a referência (`del ev`) NÃO basta (medido). Alternativa (o postador pede à thread da janela, por fila do Qt, que construa e poste) muda o que se mede e exige aval do dono do oráculo.
Secundário: marcadores de passo no stdout com `flush` e `faulthandler.enable()` no `__main__` do subprocesso do oráculo (ou `PYTHONFAULTHANDLER=1` no job; `ci.yml` pede OK do PO). Se o faulthandler pega o 0xC0000374 no Windows é incógnita.
Recomendações do lote 43 (resumo):
1. Regressão primeiro: transformar a `sonda_corrida.py` (1 postador, ponteiro mexendo, 20 s) num teste que hoje falha no Linux sob `xvfb-run -a` (no Windows só no CI), escrito pelo agente do oráculo, sem afrouxar M5 nem limites.
2. Aplicar a correção principal acima.
3. Junto: conferir `poster.join(5)` com `is_alive()` e o retorno de `_bombear(...)`, falhando com mensagem clara.
4. `faulthandler.enable()` e marcadores (secundários, acima).
5. Aceite: 0 quedas em 10 ou mais execuções no Linux com a correção e falha reproduzível sem ela (mutante = voltar a construir no postador); repetir as 30 ou mais execuções do `lote`; no CI do Windows, várias rodadas verdes seguidas, com números, nunca "estável".
6. Achado lateral: procurar outros lugares (testes e protótipos) que construam `QMouseEvent`/`QPointerEvent` fora da thread da janela.
Não mexer em limite, régua nem meta por causa disso.

## 6. O que falta saber
- Se a queda do Windows é o mesmo evento da sonda (só o CI do Windows com a correção e os marcadores responde) e em que ponto da rodada 2 ela cai.
- Se a "janela sem quadros" do Windows vem de a viewport D3D11 depender da thread da janela (medir o maior intervalo de quadros e o pulso na forma 2 no Windows, no log do CI).
- Se a taxa é de 1 em 12 rodadas ou menos: no Windows houve 2 defeitos distintos em 3 tentativas da mesma rodada do CI, mas o T15b passou em 6 ou mais rodadas antes; sem mais dados não dá para estimar a taxa.

## 7. Limites desta medida
Linux apenas (llvmpipe, xcb sob Xvfb). Nunca na tela real. Dois processos ao mesmo tempo nos lotes "normal" e "depuração" (não é máquina ociosa). O lote "carga" ficou em 4 núcleos de 16. Alocador do Windows, D3D11 e WARP não foram exercitados. Não é "estável": são 0 quedas do `lote` completo em 58 execuções (compatível com uma taxa baixa, ver seção 3), e a falha original nunca foi vista no Linux com log guardado. A sonda pequena do revisor posta cerca de 100 vezes mais rápido que o `lote.py` e mexe o ponteiro do X.
