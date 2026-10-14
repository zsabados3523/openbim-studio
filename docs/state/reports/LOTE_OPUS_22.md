# Lote Opus 22: S04-T13 (PR 79, fluxo B parte 1, paredes em C++)

**Veredito: APROVADO.** Itens 1 a 4 obrigatórios na especificação da T14 (antes de threads ou executável Qt). Itens 5 a 9 opcionais.
Oráculo não rodou localmente (ambiente `openbim` sem a trava da S04-T01: zlib); evidência = CI verde em linux e windows.

Pontos verificados e corretos: transação/rollback (`paredes.cpp:217-227`); `desfazer_passos`/`refazer_passos` (210-216); `ler` para os tipos atuais (59-69); proteção de `setlocale` (26-30, 362); "saída igual" vs fluxo A (diferenças aceitas: 1 UsageDeMaterial por parede, origem/direções compartilhadas, `mudar_comprimento` no lugar, regra de `ultimo()["geometria"]`); Windows `int64_t`, UTF-8, IFC4; propriedade Python/C++ ok; sem corrida (tudo com GIL). Diff: 434 linhas fora dos testes (exceção já registrada).

## Lista numerada
1. **Obrigatório T14.** `paredes.cpp:26-30/362` LocalC: `setlocale` é do processo; entre threads/instâncias pode terminar em "C". Usar localidade por thread (POSIX `newlocale`/`uselocale` RAII; Windows `_configthreadlocale`).
2. **Obrigatório antes de comando novo com `alterar`.** `paredes.cpp:59-69` `ler`: `default: return {}` apaga em silêncio INT, BOOL, ENUMERATION, AGGREGATE_OF_DOUBLE etc. Tratar esses tipos; lançar `std::logic_error` no não suportado.
3. **Obrigatório T14.** Esquema IFC4 só registrado por efeito colateral (`--no-as-needed`/`import ifcopenshell`). Chamar `Ifc4::get_schema()` explicitamente.
4. **Obrigatório T14.** Se soltar o GIL, `Paredes` precisa de `std::mutex` (escritor único, "trava ocupada" como no fluxo A).
5. Opcional. `voltar` (338-342): só tirar o registro da pilha depois de aplicar.
6. Opcional. `aplicar` com `Rotulo` cria `IfcLabel` por aplicação: medir RSS em 10.000 edições.
7. Opcional. `gravar` (365-367): conferir `o.flush(); if(!o) throw`.
8. Opcional. CMake sem `-DOBIM_SAIDA`: `FATAL_ERROR`.
9. Opcional. Oráculo: "100 instâncias" não mede vazamento; medir memória na T14 (implementador não edita o oráculo).

Observação: ambiente local do PO não compila o fluxo B (zlib) até atualizar com a trava; instalar pede ok do PO.
