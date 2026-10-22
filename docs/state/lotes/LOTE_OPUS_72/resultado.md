# LOTE_OPUS_72: resultado (revisor opus, effort médio, 2026-10-22)
**APROVADO.** Números e veredito conferidos contra os brutos (script independente recalculou `veredito_mista`; `pulso_maior_ms` direto dos pulsos: 33 rodadas por máquina, 0 divergências; `ok` verdadeiro nas 6 partes: Linux local, placa e Windows, lote e pesada). Correções só de texto, sem nova revisão:
1. Critérios 3 e 6 (Linux): "máx. do intervalo" → "maior atraso do mouse" (`M5b.max_ms`).
2. Windows: margem de `4_mouse_forma2` 1,6% (não 1,5%); M5 de 67,5% a 67,6%.
3. "Margens apertadas": a explicação "empate com a forma 2" vale só para `4_controle_forma2` e `4_mouse_forma2`; `4_surda` do Windows tem limite absoluto (978,3 ms contra 1.000, nas rodadas com mouse: 887,9 / 941,2 / 978,3), risco ligado ao T28 (ADR-004 §9).
4. Placa: registrar máquina parada, horário autorizado pelo PO e o mesmo `obimcore` do Linux.
5. Tirar "Rascunho." do topo.
6. Frase "interpretação": reescrita como medida direta (t1−t0 do controle: forma 2 2.228 / 2.297 / 2.275 ms; mista 2.263 / 2.231 / 2.197 ms).
## Para o ADR-004 passar a "aceito"
(a) merge deste relatório; (b) atualizar ADR §5.1 e §10 com os números do V1 (hoje o §10 diz que nenhum número da forma mista existe); (c) item 8 (V1b, IFC real com `--ifc`): medir, ou o PO declara por escrito que não bloqueia; (d) revisão Opus do texto atualizado por quem não o escreveu (§8); (e) aprovação do PO. N1 a N4 não bloqueiam. M1F só bloqueia se o PO ligar a ele.
