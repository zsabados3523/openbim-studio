# Lote Opus 32 (resultado): F0-RG-27 fase 2
Data: 2026-10-15. Revisor independente (não escreveu diagnóstico, especificação nem teste). Commit revisado: 370c8b9.

## Veredito: APROVADO
Nenhum item bloqueante. Itens 1 a 4 abaixo são observações (baixa gravidade); o item 3 vira tarefa só se a falha aparecer.

## 1. A causa está certa?
Sim. Conferido no C++:
- `DadosCena::limpar` (cena.cpp:119) esvazia `lotes_` sob `m_`; `lotes()` (cena.h:42) copia os ponteiros sob o mesmo `m_`; `Dados` é imutável depois de publicado (`atualizar` troca o ponteiro, `sem()` faz cópia).
- `Viewport::selecionar` (motor.h:427-432) só pega `mc_` (folha) para câmera e tamanho, solta, e chama `lotes()`. Não toca `Motor::m_`: a ordem "Motor antes de DadosCena" não entra.
- `selecao.cpp` não guarda estado entre chamadas (o único `static` é a string vazia constante).
- `adicionar_lote` publica de forma síncrona (o `push_back` acontece antes de voltar). A "reenvio" da perda de contexto só refaz a placa a partir de `lotes_`; não devolve lote à cena. Não há replay entre `adicionar_lote` e `limpar`.
- Logo: chamada cujo retrato é tirado depois de `limpar()` voltar só vê lote publicado depois; `g(k+1)` só existe depois de `fim` (gravado antes de `adicionar_lote(k+1)`). Nenhuma corrida real encontrada.

## 2. A régua nova é tão estrita quanto a velha para defeitos reais?
Sim. A única resposta a mais aceita é `g(k+1)` numa chamada que terminou depois de `fim`; esse objeto não pode ter vindo de retrato anterior a `fim`, então nenhum defeito real devolve exatamente isso. Mutações numa cópia do teste no scratchpad (C++ real, proxy Python em volta do `Viewport`; régua velha e nova calculadas na mesma execução; 2 execuções cada):
| Mutação | Nova | Velha |
|---|---|---|
| limpar atrasado (volta já, limpa 30 ms depois) | reprova 2/2 (`removido g(k)→g(k)`) | reprova 2/2 |
| cache velho (2 chamadas depois de limpar devolvem g(k)) | reprova 2/2 | reprova 2/2 |
| lote anterior reaparece (devolve g(k-1)) | reprova 2/2 | reprova 2/2 |
| k+2 devolvido depois de limpar | reprova 2/2 | reprova 2/2 |
| k+1 numa chamada que acaba antes de `fim` | reprova 2/2 | reprova 2/2 |
| controle: pausa de 30 ms entre t0 e a chamada (sem defeito) | **aprova 2/2** (n_apos_limpar 58-59) | reprova 2/2 (`g→g+1`) |
| sem mutação | aprova 2/2 | aprova 2/2 |
Total: 10 de 10 execuções com defeito reprovadas pela régua nova (5 tipos); falso alarme da régua velha eliminado (2 de 2).
`n_apos_limpar`: o conjunto novo (`ret < t0 e t1 < fim`) é subconjunto do velho e são justamente as chamadas julgadas sem exceção. Mudança segura e mais estrita.

## 3. Conferência "troca" (só folga de k+1)
Aceitável para o portão agora. Para falhar, a thread precisa ficar parada 15 ms ou mais entre `t0` e o retrato. Medido no Linux sem mutação (3 execuções, cerca de 1 milhão de chamadas na fase de troca cada): duração máxima de chamada 6,0 a 6,2 ms, nenhuma acima de 10 ms. No Windows não medido. Se aparecer no CI, o conserto é o mesmo princípio (julgar pela chamada inteira: aceitar `gs[j]` de `j = ks(t0)` até `ks(t1)+1`), e não é afrouxamento pelo mesmo argumento. Segue a regra do cartão: se aparecer, volta ao PO, já com este conserto proposto.

## 4. Especificação e argumento
Clara, executável e certa ao recusar `add` da rodada seguinte como limite (cartão, regra 3). O argumento "não é afrouxamento" é válido e as mutações acima o confirmam.

## Lista numerada (observações, nenhuma bloqueia)
1. Baixa, teste linha 352: o controle `n_apos_limpar >= 20` soma as 20 rodadas e a contagem real é de milhões (cena vazia, chamada de microssegundos); o piso é quase vazio. Já era assim antes; reforço opcional futuro: exigir chamadas julgadas em cada rodada.
2. Baixa, cartão linha 19: "já existia antes do fim da chamada" fica mais exato como "só passou a existir depois de `fim`, durante a chamada". Ajuste de texto opcional.
3. Baixa, teste linha 237: risco residual da "troca" (item 3 acima); vira tarefa só se falhar no CI.
4. Informativo, `ponte_viewport.cpp:73`: `limpar` não solta a trava do Python antes de pegar `DadosCena::m_`. Sem impasse hoje (ninguém segura `m_` esperando a trava do Python); registrar se a ponte mudar.
Aceite pendente: 50 de 50 no Windows, pelo CI, antes do merge.
