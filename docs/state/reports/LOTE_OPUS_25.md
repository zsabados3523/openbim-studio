# Lote Opus 25: PR 87 (T14a) e PR 82 (T11c, diff novo)

## (A) PR 87, T14a: REPROVADO
Verificado pelo Opus (módulo compilado no scratchpad; 50 passaram, 1 falhou = guarda do ci.yml): localidade POSIX (RAII, ordem), `ler` completo, `Ifc4::get_schema()` funciona sem `import ifcopenshell` e sem `--no-as-needed`, trava + GIL corretos (argumentos convertidos antes de soltar; destrutores destravam antes de retomar o GIL), `apoio()` preguiçoso e rollback, `abrir()`, `gid()`, itens 5/7/8 do lote 22, propriedade Python/C++; carga com 10 threads sem impasse. `tests/s04_fluxo_b_t14a_aux.py` fora da lista do cartão: aceitável (precedente `s04_fluxo_b_aux.py`); registrar no LOG junto com a alteração do CONTRATO.md.
1. **paredes.cpp:58-61 `contexto()` (bloqueia, implementador).** Quando a base não tem o contexto "Plan" (ou "Model"), o B cria o `IfcGeometricRepresentationContext` mas não o põe em `IfcProject.RepresentationContexts`: B grava `[Model]`, A grava `[Model, Plan]`. Correção: com diário ligado e pai recém-criado, achar o `IfcProject` e `alterar(projeto, 7, contextos_atuais + pai)` (ou criar a lista); desfazer/refazer valem. Opcional: procurar o subcontexto antes de criar o pai.
   - Oráculo (outro agente): `tests/test_s04_fluxo_b_paredes.py:338` `orfas` exclui `IfcRepresentationContext`; `:340` `assinar` não compara `IfcProject.RepresentationContexts`. Incluir os dois; conferir no marco "fim" que a lista volta ao que era.
2. **Prova de CI inexistente (bloqueia o merge).** O `ci.yml` do main e do PR 87 não tem o passo "Fluxo B, paredes em C++" (perdido no conflito; volta com o PR 82). O ramo `_WIN32` do `LocalC` nunca foi compilado e o oráculo da T14a nunca rodou no CI. Só aprovar com CI linux e windows verdes rodando o oráculo da T14a de forma obrigatória.
3. **Guarda do ci.yml (líder).** A expressão exige `OBIM_S04_T14A_OBRIGATORIO=1` numa linha e `test_s04_fluxo_b_paredes.py` na linha seguinte. Após o PR 82: no `ci.yml`, linha própria `export OBIM_S04_T14A_OBRIGATORIO=1` logo antes do `pytest`, nos dois jobs (ou afrouxar a expressão).
4. Opcional `paredes.cpp:36`: `newlocale(LC_NUMERIC_MASK, "C", 0)` deixa outras categorias em "C"; usar `duplocale(uselocale(0))` como base.
5. Opcional `paredes.cpp:33`: `_configthreadlocale` pode devolver -1; lançar `runtime_error`.
6. Opcional `ponte.cpp:16`: recusar `bool` em `espera`.
7. Nota T14c: instâncias em threads diferentes dividem estado global do IfcOpenShell (Logger estático).

## (B) PR 82, T11c (diff novo): APROVADO no conteúdo
Guarda `conj is not None and conj.is_a("IfcMaterialLayerSet")` (`fluxo_a.py:269-270`) correta; `test_t11c_tipo_sem_conjunto_de_camadas` cobre os casos; 9 casos t11c passam. Condição de merge: CI linux e windows verdes (3 testes antigos de tempo da janela falharam por ~10–25 ms sem relação com o diff).
