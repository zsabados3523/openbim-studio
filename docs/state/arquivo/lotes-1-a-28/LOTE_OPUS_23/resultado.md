# Lote Opus 23: PR 82 (T11c) e PR 83 (T12)
(Medições em /tmp/.../scratchpad: bench.py, probe.py; sem janela.)

## (A) PR 82, T11c: REPROVADO
Certo: 1 uso + 1 relação por parede; rollback e `_g` intactos; desfazer/refazer/apagar ok; oráculo distingue o código antigo.
**Motivo: custo quadrático.** `type.assign_type([w])` por parede refaz `set(rel.RelatedObjects)` e regrava a lista; a transação guarda cópia de cada versão. Lote de 1000: com 200 paredes do tipo, PR 82 12,3 s (main 4,7 s; alternativa 5,3 s), desfazer 4,1 s, memória 449 MB (alt. 122 MB); com 3000 paredes do tipo, 69,6 s (main 5,7 s; alt. 5,9 s). M4 no CI Linux 2,23 s → 7,79 s.
1. **fluxo_a.py:269 (bloqueia, implementador).** Antes do laço: `conj = E.get_material(tipo, should_inherit=False)`; por parede: `api("material.assign_material", self.ifc, products=[w], type="IfcMaterialLayerSetUsage", material=conj)`; depois do laço, uma chamada `type.assign_type` com todas as paredes (`should_map_representations=False`). Validado em cópia: 26 passaram/15 pulados, t11c e sentinelas do B passam.
2. CONTRATO.md:21 e cartão T11c: custo cai na M4 e nos passos 6a/6b, não em M2/M2b (líder e oráculo).
3. Oráculo: sentinela de escala (mesmo lote de 300 com 0 e ~2000 paredes do tipo; razão <2; sem prescrever número de chamadas). Medido 5,7× no PR 82, 1,1× na alternativa.

## (B) PR 83, T12: REPROVADO
Certo: réguas virtual e estrita, M6 informativo, `primeiro_quadro`, comparação de pares nunca aprova sem casar.
Aprova meta não atingida (provado): NaN em M2/M3, tempos negativos, 1 repetição em vez de 200.
1. **medir_s04.py:131-146 (bloqueia).** Tempo NaN/infinito/negativo e ordem errada (`t0<=t_comando<=t_quadro`, `t_painel>=t0`) → rc 2; ordenar `t` antes do `np.diff`.
2. **medir_s04.py `_calcular` 149-154 (bloqueia).** Exigir n≥200 em 3, 4a, 4b (ou n do roteiro_r.json) e `len(criados)==quantidade` no 5b; senão rc 2. Oráculo (`test_s04_metas.py:48`): reps=200 por padrão, casos n=1, NaN, negativo, lote de 10 → rc 2.
3. **Conflito com a T11c (bloqueia no segundo merge).** `MATERIAL` fora da contagem (`medir_s04.py:20-23,246`; `test_s04_metas.py:16,244`) deve sair quando a T11c entrar.
4. `_camadas` (233-236): espessura em unidade crua; usar `calculate_unit_scale`; oráculo com variante em mm.
5. `_conferir_par`/main: KeyError/TypeError/IFC ilegível → rc 2, não traceback rc 1.
6. M7: assimetria Python (uma instrução por linha) × C++ (não normalizado); registrar também a contagem crua; detalhes `1'000` e `u8R"(...)"`.
7. `primeiro_quadro` nunca usada pela ferramenta; no 5b conferir `primeiro_quadro(relogio, sequencia) <= t_quadro_ms`.
8. Oráculo: casos de valor inválido; mutações FireRating/tipo/pavimento/nome; caso só da regra "3× intervalo parado" na estrita; unidade mm.
9. Régua estrita: avisar/rc 2 se `base.produtos` < 3000.

Ordem sugerida: corrigir e mesclar a T11c; depois, no PR 83, tirar a exceção de material junto com os itens 1 e 2.
