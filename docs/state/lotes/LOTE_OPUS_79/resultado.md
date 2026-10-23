# Resultado do lote 79: REPROVADO (PR 283, rascunho ed8e2b7)
Conferiu: linhas de `file.py` 0.9.0 e `fluxo_a.py`, números do T02 (salvo o item 2), os 8 itens do T03 sem contradição com P1 a P5, G1 a G6, M1, M2 e v2/02 §6; 10.000 operações não baixou.
Problemas (14):
1. Memória §4.6 e resumo: contas com Python em vez de JSON x 12; "no mínimo 106" falso (certo: cerca de 83; criar parede cerca de 1.616; posição cerca de 11.570).
2. "8 a 12 vezes" deve ser "7 a 12" (posição 7,0); erro herdado do relatório do T02.
3. §8: "coberto pelos tipos do oráculo" é falso; `api/alignment/_get_segment_endpoint.py:43` e `:89` chamam `begin_transaction` e `discard_transaction` e derrubam a sentinela. Exigir conferência `arquivo.transaction is t._tx` e `HistoricoQuebrado`; caso no T04.
4. Ordem do fim normal incompatível entre §4.2 e §4.4: codificar, `end_transaction`, lateral, resumo, `anotar`.
5. Sem ação definida: `rollback` falhando dentro do `discard_transaction`; `anotar` falhando depois do `end_transaction`.
6. Tabela E1 a E8 com buracos: primeira gravação sem `.bak`; destino mudado por outro programa; falha com o programa vivo depois do `gravacao.json`; `gravacao.json` apagado por último; `gravacao.json` de outro caminho; `LadoId` provisório x definitivo.
7. `gravacao_par.py` recebe a pasta por parâmetro; modo sem carimbo para o autosave; pular `.bak` sem destino antigo.
8. Só o T09 liga `ao_concluir`; a ordem ao abrir precisa de dono.
9. Regra de sorteio do T04 não garante os pisos (505, 1.057, semente 3 dá 968; cerca de 3.830 criar; cerca de 0,83 GB); modelo sem pset.
10. R4: `IfcPolyline` não existe no modelo gerado (usar `CoordList` de `IfcCartesianPointList2D` ou `Coordinates` de `IfcCartesianPoint`).
11. R2: granularidade de `diferencas` ambígua.
12. T06: valores de `motivo` ausentes do §4.8.
13. Resumo linha 1: "pasta do programa" deve ser "pasta do programa no seu computador".
14. §8: listar G5 (conferir começo e fim do IFC sem reabrir) como escolha sem número.
Ajustes de cartões: T04 (`fora_do_historico`, transação aninhada), T05 (sem ligação ao par, ordem codificar/anotar), T07 (gancho, pasta por parâmetro, carimbo, sem carimbo, estados), T09 (liga `ao_concluir`, dono da ordem ao abrir), T08 nada.
Correção: autor aplicou os 14 itens e os ajustes de cartão no commit 9a171ec (diff 221 a mais, 2 a menos), acrescentando `Historico(..., codificar=None, anotar=None)`, estados E9 e E10 e nova regra de sorteio (peso 3 para criar parede, lote de 2 a 4). Faltam: nova revisão do lote 79 sobre as correções (aguarda janela de 5 h abaixo de 70%) e o aceite do PO. Fator "7 a 12" corrigido no relatório do T02 (PR 282).
