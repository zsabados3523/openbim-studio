# LOTE_OPUS_76: resultado (revisor opus, effort médio, 2026-10-22) — PR 261, cabeça b13f4fa

**APROVADO.** Revisado só o que mudou depois do lote 73 (e05bd93, 9786da1, merge b13f4fa).

1. Oráculo V1c em pytest filho: os 5 casos de antes (a com 2 modelos, b_constante, b_chamadas com n=1000/1001/250, c, d) só mudaram o prefixo `test_` para `caso_`; nenhum assert, número, parametrização ou caso mudou; SUBLOTE=100, N=1000, base 300. De fora: 1 teste por caso (5), cada um roda o filho com OBIM_S04_V1C_DENTRO=1 e o env de fora (OBRIGATORIO passa junto).
2. Propagação: só aprova com código 0 e última linha com " passed" sem skipped/xfail/xpass/error; tudo-pulado no filho vira `pular` (falha com OBRIGATORIO); qualquer outra coisa (inclusive "no tests ran", código 5, e pulo parcial) é falha. Filho executa de fato: local com OBRIGATORIO=1, 5 passam em ~22 s, 0 pulos.
3. Defeito de propósito (SUBLOTE_CONTAINER = 10**6, chamada única, injetado por plugin fora do repositório): b_constante, b_chamadas, c e d reprovam (ex.: "assert 1 >= 10"); mesmo quadro do lote 73 (o caso a compara com a própria chamada única, então passa nesse defeito, como antes).
4. T15c: `assign_container` continua com n exato (`pf[nome]["n"] == n`), agora ceil(1000/SUBLOTE_CONTAINER) = 10 lido dentro do teste; os outros 5 números intactos. Nada afrouxado; a coleta não importa mais fluxo_a (7 testes coletados).
5. ci.yml: diff contra origin/main (b290531) = só as 2 linhas do V1c (Linux e Windows), antes da linha do T07e; nenhuma linha do T07e perdida.

Observação (não bloqueia, fica para quando mexer de novo): o veredito lê a última linha de stdout+stderr do filho; texto solto em stderr no fim (vi "No stream support: No module named 'lark'" quando o ifcopenshell é importado fora da captura) faz um filho verde contar como falha. O erro é para o lado seguro (falso vermelho, nunca falso verde). Melhor ler só a última linha do stdout.
