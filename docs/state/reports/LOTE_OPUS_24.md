# Lote Opus 24 (2ª leitura do lote 23): PR 82 (T11c) e PR 83 (T12)
Ambos REPROVADOS (2ª reprovação de cada: cartões reescritos, ver abaixo). Só leitura; benchmarks sem janela (valem as razões; tracemalloc ligado).

## (A) PR 82 — REPROVADO (1 linha + 1 caso de oráculo)
Confirmado: custo linear (lote 300 com 0/2000 paredes do tipo: razão 1,05; ~1,2× constante sobre o main), 1000 usos e 1001 relações, rollback/desfazer/refazer/apagar/`_g` ok, sentinela de escala boa, exceção de material saiu do fluxo B.
1. **fluxo_a.py:262 e :269 (bloqueia).** `E.get_material(tipo)` pode ser `None` ou `IfcMaterial` simples. Com None cria `IfcMaterialLayerSet` vazio por parede (IFC inválido); com IfcMaterial falha com AssertionError. No main funciona (`map_material_usages` pula). Correção: só chamar `assign_material` quando `conj is not None and conj.is_a("IfcMaterialLayerSet")`. Oráculo novo: `test_t11c_tipo_sem_conjunto_de_camadas` (tipo sem material e com IfcMaterial: N paredes, 0 usos novos, IFC válido).

## (B) PR 83 — REPROVADO
Itens 1, 2, 4, 5, 6, 7, 8, 9 do lote 23 conferidos. Decisões do agente: "sequência tardia/nunca = rc 2" correto; "N e lote do roteiro" correto; rede de segurança em `main` aceitável mas deve imprimir traceback; "menos repetições = inválido, mais não" ERRADO.
1. **medir_s04.py:213 (bloqueia).** 200 reps a 250 ms + 300 extras a 20 ms → rc 0. Correção: `len(reps) != n` → rc 2; oráculo: casos 201 e 500.
2. **medir_s04.py:253-257 `_m5` (bloqueia).** Quadros duplicados no relógio (cada tempo 2×) → rc 0. Correção: tempo repetido no relógio do 4c/5b → rc 2; oráculo: caso.
3. **:219-227.** `sequencia` ≤0 torna `primeiro_quadro` trivial: exigir inteiro ≥1. `criados` com GlobalIds repetidos passa: exigir `len(set(criados)) == lote`.
4. **:162-163 e :498-503.** `10**400` no JSON → OverflowError/traceback: `_num` com try, OverflowError → falso. Rede de segurança imprime também `traceback.format_exc()` em stderr após "ENTRADA INVÁLIDA:".
5. Resíduo: duração zero (`t_quadro = t0`) aprova; registrar como limite conhecido (opcional: exigir `t_quadro_ms > t0_ms`).
6. **Item 3 do lote 23 (exceção de material):** TODO em `test_s04_metas.py:27`; acrescentar TODO em `medir_s04.py:21-24`. **Bloqueia o merge do 83.** PR 83 só mescla depois do 82; no mesmo PR saem `MATERIAL` em `medir_s04.py:24,379`, `bx.MATERIAL` em `test_s04_metas.py:367`, e entra caso "uma relação de material a menos em B → saída diferente".

Ordem: PR 82 (A1 + oráculo, CI verde, merge); PR 83 com rebase sobre o main, B1–B4 + item 6, releitura curta pelo Opus só do diff dessas correções.
