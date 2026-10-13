<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE OPUS 20: revisão do PR 78 (F0-S04-T16, inclui S03-T08-G)
Revisor opus, só leitura, 2026-10-13. **REPROVADO** (3 bloqueantes). Sondas rodadas no scratchpad com ifcopenshell 0.9.0; nada editado no repositório.

## Bloqueantes
1. A suposição "o iterador entrega as peças em ordem crescente de id" é falsa (carregador.py:348, 357, 313). Com threads=1 a ordem segue a representação, não o id; com threads=4 é embaralhada. Sonda `s25.ifc` (25 paredes normais com ids menores e representações criadas depois da peça lenta; lenta com id 37 entregue na posição 0; atraso 4 s, limite 1 s, bloco 1000): **ramo** termina em "erro" ("precisou reiniciar mais de 20 vezes"), 19 de 26 peças, 26 s; **main** conclui 26 de 26, 1 caixa, 2,6 s. Mecanismo: a candidata é a menor pendente não anunciada (parede normal), a confirmação sozinha passa, a linha 357 devolve None, a rodada seguinte trava de novo na mesma lenta; cada rodada resolve uma parede e `seguidos` nunca volta a zero. Correções possíveis: (a) dividir as pendentes não anunciadas ao meio e confirmar cada metade com um iterador (~log n filhos); (b) voltar a um iterador por peça só para as não anunciadas depois da primeira confirmação que não reproduz; (c) limitar as confirmações pelo orçamento em qualquer caso. A opção (ii) do lote 7 não dizia como escolher a acusada (lacuna da especificação).
2. O orçamento não protege esse laço (carregador.py:320): `_estourou` só é consultado no modo normal. Entra junto com a correção do item 1.
3. Lacuna do oráculo: `_gerar_layout` (tests/test_s04_abertura.py) exige ids crescentes e cria as representações na mesma ordem; nenhum caso tem ordem do iterador diferente da ordem dos ids. Caso pedido: montado como `s25.ifc` (representação compartilhada ou criada antes; a lenta entregue antes de peças de id menor); esperado "concluido", só a lenta vira caixa, no máximo poucas reaberturas.

## Recomendações
4. A contagem do orçamento inclui as cópias (carregador.py:342, `len(est["simp"])`): uma peça "membro" lenta leva 285 cópias e estoura o limite de 20 de uma vez; contar só as acusadas confirmadas (decisão do líder: sim).
5. O orçamento de tempo estoura com ~2 peças lentas: cada uma custa três esperas (normal, isolado, confirmação ≈ 60 s no padrão) contra duas no main. Avisar o PO.
6. Critério (b): o teste b2 compara com o normal em threads=1 (o normal real usa até 8) e não mede o custo das confirmações; medir no arquivo do PO.
7. Peça sem geometria dentro de um bloco cortado vira caixa, não "sem malha" (carregador.py:321): bate com o cartão; registrar.
8. Motivo com jargão em processo_malhas.py:262 ("o iterador não devolveu geometria"); um bloco com muitas peças sem geometria custa uma reabertura por peça, fora de `seguidos` e do orçamento.
9. Textos desatualizados: docstring de processo_malhas.py:310 ("cubo de 0,5 m"), carregador.py:362 ("maior id avisado"); pré-existente em :274.
10. Correto: S03-T08-G (posição ilegível vai para sem_malha; sem pendentes depois de queda a carga segue), corte por bloco, texto do resumo em português simples, limpeza das guardas nos testes P17/P18, filhos sempre mortos no `finally`.

## Para o PO
A mudança deixa a abertura mais barata quando aparece peça lenta, mas há um defeito: num arquivo em que a ordem interna das peças não é a ordem de criação, o programa acusa peças erradas uma a uma. No teste do Opus a abertura terminou em erro com 7 peças faltando, e a versão atual abre o mesmo arquivo certo em 2,6 s. Precisa de correção e de um teste novo antes de entrar. As cópias de uma peça lenta não devem contar para o limite de 20 peças.
