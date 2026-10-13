<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE OPUS 19: revisão do PR 77 (F0-S04-T11b)
Revisor opus, só leitura, 2026-10-13. **APROVADO, com recomendações; nenhum achado bloqueante.** Vale para o conteúdo exato (HEAD 1fa501b), com `linux` e `windows` verdes.

## Achados do lote 18: situação
1 (validade do IFC) fechado: `.lower() == "error"` e `express_rules=True`, caso de controle prova que o filtro antigo não via nada. 2 (tempos por fora) fechado: `obimcore.agora()` antes e depois, cada `t_quadro_ms` é entrada real de `relogio()`, M3 com texto do QLabel e evento de pintura. 3 (caminhos de erro) fechado: 7 comandos com falha no meio, 10 combinações depois do commit, falhas em desfazer/refazer. 4 (rollback) fechado e correto: conferido no ifcopenshell (file.py:557-588) que `ifc.undo()` depois do commit desfaz exatamente a transação que falhou. 5 (CONTRATO.md:14) fechado. 6 (desfazer de propriedade sem reenvio) fechado. 8 só a parte combinada (`executar_detalhado` seguro com duas threads). 9 fechado; `round(Depth, 6)` não esconde erro de unidade.

## Recomendações
1. [oráculo] `self._refazer.clear()` (fluxo_a.py:197) sem teste: sequência "desfazer → comando que falha depois do commit → refazer" ressuscitaria a transação que falhou. Acrescentar caso.
2. [código] fluxo_a.py:196: depois do `ifc.undo()` a transação que falhou fica em `ifc.future`; descartar com `self.ifc.future.pop()`.
3. [código] fluxo_a.py:196 e 325: se `undo()`/`redo()` do ifcopenshell levantar `UndoSystemError`, as pilhas ficam fora de passo; registrar como limite conhecido.
4. [contrato] Caminho de volta supõe que `Cena.atualizar` faz tudo ou nada; anotar no CONTRATO.md ou ADR-001.
5. [processo] O resto do achado 8 do lote 18 (`_ult_guid` 172, `_c_selecionar` 362, `_bombear` 98, contagem da base 386) vai ao cartão F0-S04-T15 (incluir `fluxo_a.py` nos arquivos permitidos).
6. [processo] Achados 7 e 10 do lote 18 (reenvio/fragmentação no modelo de 1 milhão, M2b informativa, `lotes_`, interface `atualizar` no ADR-001; recomendações 1 e 2 do lote 17 em viewport.cpp:431) vão ao cartão F0-S04-T12 e a um cartão do clique; deslocamento zero (fluxo_a.py:222) também (precisão float32 em bases georreferenciadas).
7. [código] fluxo_a.py:253: arredondamento absoluto de 6 casas na unidade do projeto; em pés corta precisão real; aceitável no protótipo.
8. [código] fluxo_a.py:289: `schema == "IFC2X3"` não pega esquemas mais antigos; conferir `OuterCurve.is_a("IfcIndexedPolyCurve")`.
9. [código] fluxo_a.py:171: `dict(det)` é cópia rasa; usar cópia profunda.
10. [oráculo] Nenhum teste confere que `selecionado` volta ao valor de antes depois de uma falha (188, 198).
11. [processo] Diff ~585 linhas (≈500 de oráculo); `ci.yml` fora dos arquivos permitidos: aceitos pelo precedente dos lotes 14 e 18.

## Para o PO
Se uma operação dá erro no meio ou no fim, o programa volta o modelo e o desenho exatamente ao que eram, sem perder o desfazer. Desfazer uma troca de nome não redesenha mais tudo. O teste confere tempos e arquivo salvo por fora. Pendências anotadas para os próximos cartões.
