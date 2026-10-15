# Revisão Opus: F0-RG-09 parte 2 (régua do intervalo máximo do viewport, PR 118)

- Data: 2026-10-15
- PR: #118, ramo do PR em `d496259`
- Cartão: F0-RG-09 (achado B7); regra recomendada em `F0-RG-09-parte1-revisao-opus.md`
- Revisor: Opus. **Atenção:** a regra implementada foi recomendada por este mesmo revisor. O código foi escrito por outra sessão; a regra em si fica para o Rafael ver (seção "Onde a regra ficou mais frouxa").
- Diff revisado: `tests/test_s04_viewport.py` (+12 −6)
- `v2/` e `CLAUDE.md`: não mudam neste PR.
- Como foi conferido: leitura do diff e de `c_intervalo`; a função `veredito` do PR rodada fora do CI com o teste da régua e 8 mutações; cenários de desempenho piorado rodados contra ela.

## Veredito: APROVADO (a mesclagem continua dependendo do CI obrigatório verde)

## O que está certo

1. **Implementa a recomendação.** Uma rodada de aquecimento por fase (rodada 0 roda e é descartada antes de medir quadros e batimento), 7 rodadas medidas, reprova com mediana dos maiores intervalos >= 100 ms, reprova com 2 ou mais rodadas acima de 200 ms. Mediana < 50 ms e razão lote/parado < 3 continuam como eram.
2. **A regra do Rafael continua valendo.** A mediana de 7 contra 100 ms está no código. Na prática a conferência de 50 ms, que já existia, é mais apertada e pega antes.
3. **O teste ainda falha quando o desempenho piora de verdade** (rodado contra a função do PR):
   - travamento real (750 ms em todas as rodadas): reprova por mediana, por picos e por razão;
   - mediana de 110 ms sem picos: reprova;
   - 2 picos (300 e 250 ms) com o resto normal: reprova.
4. **Mutações:** tirar a mediana de 50 ms, tirar a regra dos picos, mudar para "1 pico reprova" ou "3 picos reprovam" e tirar a contagem de rodadas: todas quebram o teste da régua.
5. **Controle de sensibilidade mantido:** o batimento da janela (>= 500 ms nas fases C e D) só é medido nas 7 rodadas que contam.

## Onde a regra ficou mais frouxa (para o Rafael ver)

Nenhum ponto fica mais frouxo que a decisão do Rafael (mediana de 7 contra 100 ms). Ficou mais frouxo que a regra antiga do lote Opus 11, que reprovava qualquer rodada com intervalo >= 100 ms:
- **(a)** Um pico isolado acima de 200 ms em 7 rodadas agora passa (antes reprovava).
- **(b)** Rodadas entre 100 e 200 ms passam em qualquer número, desde que a mediana fique abaixo de 50 ms. Exemplo conferido: 3 rodadas de 150 ms e 4 de 30 ms passam. Antes reprovavam. Uma pausa de 150 ms se vê na tela, então recomendo (não bloqueia) acrescentar "reprova se 3 ou mais rodadas passarem de 100 ms".
- **(c)** A falha desta noite no PR 109 (rodadas de 305 e 656 ms na mesma fase) **continua reprovando** com a regra nova (2 picos). Ou seja, a regra nova não teria evitado aquela falha; ela evita só o caso de um pico único.

## Observações (não bloqueiam)

4. Tirar a conferência de 100 ms não quebra o teste da régua, porque a de 50 ms já cobre. Está certo manter a linha (é a regra do Rafael escrita no código).
5. Tirar a razão lote/parado também não quebra o teste da régua. Isso já era assim antes deste PR; um caso com mediana de 45 ms na fase C e 10 ms na A cobriria.
6. O caso com rodadas extras de aquecimento deixa o teste uns 10 s mais longo no CI; o limite de 900 s do caso sobra.
