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

## Atualização 2026-10-11 (cartão S02-T19)
- **Teste 2 no Windows (CI): 4 de 4 "sim".** Cabeçalhos `ifcparse` presentes; DLLs separadas (`ifcopenshell.parse.dll`, `.geometry.dll`, `.plugin.dll`); o `_ifcopenshell_wrapper.cp312-win_amd64.pyd` importa essas DLLs, sem cópia embutida. O teste 2 do ADR-005 fecha nos dois sistemas. Como reproduzir: `python scripts/sonda_ifcopenshell.py` (roda também no CI, Linux e Windows).
- **Sonda 3b: passou nos dois sistemas (CI, run 38165289002).** Programa que inclui `ifcparse/file.h`, liga pelo `IfcOpenShellConfig.cmake` e abre `casa-simples.ifc` (IFC4, 87 entidades). Linux: limpo 4,8 s, incremental 4,2 s. Windows (MSVC): limpo 19,4 s, incremental 5,7 s. Cabeçalhos pesados não são problema de tempo. Precisa, no ambiente de desenvolvimento, de `zlib`, `libxml2-devel` e `libboost-devel`; ver `prototypes/cpp_probe_3b/run.sh`. Vale lembrar para a S04: no Windows usar o MSVC, não o MinGW do runner.

