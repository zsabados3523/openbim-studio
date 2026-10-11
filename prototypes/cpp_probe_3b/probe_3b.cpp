// SPDX-License-Identifier: AGPL-3.0-or-later
// Sonda 3b (ADR-005): o cabeçalho pesado ifcparse/file.h compila e liga nas
// bibliotecas compartilhadas do pacote conda-forge, e abre um IFC de verdade.
#include <ifcparse/file.h>
#include <iostream>

int main(int argc, char** argv) {
    if (argc < 2) { std::cerr << "uso: probe_3b arquivo.ifc\n"; return 2; }
    ifcopenshell::file f(argv[1], false);
    if (!f.good()) { std::cerr << "falha ao abrir\n"; return 1; }
    std::cout << "esquema=" << f.schema()->name()
              << " entidades=" << f.bounds() << "\n";
    return 0;
}
