<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-RG-27: diagnóstico (fase 1) do teste de seleção em outra thread
Data: 2026-10-15. Nada de código de produção ou de teste foi mudado. Sem push.

## Conclusão
**Defeito do próprio teste, não corrida no C++.** O teste olha o relógio ANTES de chamar `selecionar`, mas a leitura da cena acontece DEPOIS, e entre as duas coisas a thread pode ficar parada. Se ela fica parada justo na virada de uma rodada para a seguinte, devolve o objeto novo, que é legítimo, e o teste o chama de "removido".

## Frequência medida
- Linux, `obimcore` compilado do `origin/main` (226a876), 4 execuções em paralelo: **4 falhas em 52 (7,7 %)**. Uma execução isolada antes disso passou.
- As 4 falhas têm a mesma cara do CI: `['removido', '…72', '…73']`, `…62/…63`, `…72/…73`, `…76/…77`. Em todas, o que voltou é o objeto **seguinte** (g+1), nunca o removido (g).
- Windows: **não medido** (precisa do CI; push proibido nesta fase). Para compilar no Linux foi preciso apontar zlib e libxml2 por links simbólicos numa pasta temporária (fora do repositório).

## O que acontece, passo a passo (tests/test_s04_selecao_c.py)
1. Rodada k (linhas 220-228): `adicionar_lote(k)`, espera 40 ms, `limpar()` (`ret`), espera 120 ms, grava `fim`.
2. A thread de seleção (linhas 198-205) faz `t0 = perf_counter()` e só depois chama `c.selecionar`. Entre as duas linhas ela pode perder a vez (trava do interpretador Python a cada 5 ms, ou o sistema parando a thread).
3. A thread de seleção grava `t0` um pouco antes de `fim`. A thread principal grava `fim` e, na linha seguinte, já faz `adicionar_lote(k+1)`.
4. A thread de seleção volta, lê a cena, que já tem o objeto k+1, e devolve `g(k+1)`.
5. A conferência (linha 239) usa só o início da chamada: `ret < t0 < fim` e `r is not None` → marca "removido". Mas `g(k+1)` ainda não existia quando `t0` foi gravado. O resultado é correto; a régua é que está torta.
6. Assimetria no próprio teste: a conferência "sumiu" (linha 240) exige a chamada INTEIRA dentro da janela (`add < t0 and t1 < ini`). A "removido" olha só `t0`. O contador de controle (linha 241) também.
7. A conferência "troca" (linha 237) tem o mesmo defeito, em escala menor: tolera `g(k+1)` mas não `g(k+2)`, e uma parada de 15 ms ou mais basta.

## C++ lido: sem janela de corrida
- `limpar` (cena.cpp:119): esvazia a lista de lotes e sobe a geração sob `DadosCena::m_`.
- `lotes()` (cena.h:42): copia os ponteiros sob o mesmo `m_`. Os lotes são imutáveis depois de publicados. A cópia é um retrato exato de um instante.
- `Viewport::selecionar` (motor.h:427-432): pega só `mc_` (trava-folha, para ler câmera e tamanho), solta, e chama `lotes()`. Não toca em `Motor::m_`, então a regra "Motor antes de DadosCena" nem entra em jogo.
- Consequência: uma chamada que COMEÇA depois de `limpar()` voltar nunca vê lote antigo. Só pode devolver None ou algo adicionado depois, que é o que ocorreu.

## Prova por experimento (cópia do teste fora do repositório, C++ intocado)
Pus uma pausa artificial de 30 ms entre `t0` e a chamada, só depois do primeiro `limpar`. Resultado: **4 de 4 execuções falham** com a mesma assinatura, `removido g → g+1`, seis vezes seguidas, sem mexer em uma linha do C++. Com a pausa na fase de troca, é a conferência "troca" que falha (`g+2`). A falha do CI é a mesma coisa, só que a pausa vem do sistema.

## Opções de conserto
**A (recomendada), só o teste, cerca de 3 a 6 linhas.** Julgar pela chamada inteira, como "sumiu" já faz: "removido" só vale se `ret < t0` e o resultado não pode ter vindo de objeto adicionado depois do início da chamada (aceitar `g(k+1)` se `t1 > add` da rodada seguinte; mesma folga para `g(k+2)` em "troca"); contar o controle do mesmo jeito. Continua rígido para o que importa: depois de `limpar()`, qualquer objeto da rodada k ou anterior é erro. Risco: é mexer em teste de oráculo de tarefa T3; precisa de especificação e revisão Opus, e do PO aceitar que isto CORRIGE a régua e não a afrouxa (o cartão proíbe afrouxar). Aceitação: 50 de 50 no Linux e no Windows, mais a pausa artificial do experimento passando.
**B, prova forte, cerca de 20 a 30 linhas, mexe na ponte.** `selecionar` passa a devolver também o número da geração/sequência do retrato que usou, e o teste confere contra isso, sem relógio. Risco maior: muda a interface do módulo e dos testes que a usam; só vale se o PO quiser esse nível de prova.
Nenhuma das duas mexe na lógica de trava do C++, porque não há defeito lá.

## Pendências
- Windows não medido (precisa do CI no cartão da fase 2).
- Registro no LOG fica para o líder.
