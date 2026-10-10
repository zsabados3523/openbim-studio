# Relatório F0-S02-T16: sonda C++ mínima

1. Testei no Linux local, sem instalar nada, com o ambiente openbim.
2. Os cabeçalhos do IfcOpenShell (ifcparse e ifcgeom) existem: SIM.
3. Existem bibliotecas para ligar: SIM, mas com nome novo (libifcopenshell.parse/geometry), não libIfcParse.
4. São compartilhadas (.so); não há versão estática.
5. O módulo Python usa essas mesmas bibliotecas, não leva cópia própria: SIM.
6. Na versão 0.9 o código C++ usa o espaço de nomes ifcopenshell::file; vale lembrar no teste 5 (S04).
7. Criei o módulo nanobind com OCCT e Qt6 Core: caixa 2x3x4 dá volume 24, teste passou.
8. Tempos: build limpo 2,4 s; incremental 0,9 s (muito abaixo dos limites).
9. Faltam: CI Linux/Windows (não existem ainda) e o teste do R1 (T3, S04).
10. Detalhes e comandos: docs/research/2026-10-10-sonda-cpp.md.
