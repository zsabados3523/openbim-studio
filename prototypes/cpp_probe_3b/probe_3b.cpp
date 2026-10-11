// SPDX-License-Identifier: AGPL-3.0-or-later
// Sonda 3b (ADR-005): o cabeçalho pesado ifcparse/file.h compila e liga nas
// bibliotecas compartilhadas do pacote conda-forge, e abre um IFC de verdade.
#include <ifcparse/file.h>
#include <iostream>

int main(int argc, char** argv) {
    if (argc < 2) { std::cerr << "uso: probe_3b arquivo.ifc\n"; return 2; }
    const std::string caminho = argv[1];
    std::cerr << "esquema IFC4 registrado: "
              << (ifcopenshell::schema_by_name("IFC4") != nullptr ? "sim" : "nao") << "\n";
    // Duas formas de abrir; a primeira que funcionar vale (a segunda é o caminho padrão da biblioteca).
    ifcopenshell::file a(caminho, false);
    std::cerr << "abrir(caminho, false): codigo " << static_cast<int>(a.good().value()) << "\n";
    ifcopenshell::file b(caminho);
    std::cerr << "abrir(caminho): codigo " << static_cast<int>(b.good().value()) << "\n";
    ifcopenshell::file& f = (a.good().value() == ifcopenshell::file_open_status::SUCCESS) ? a : b;
    if (f.good().value() != ifcopenshell::file_open_status::SUCCESS) {
        std::cerr << "falha ao abrir\n";
        return 1;
    }
    size_t n = 0;
    for (auto it = f.begin(); it != f.end(); ++it) ++n;
    std::cout << "esquema=" << f.schema()->name() << " entidades=" << n << "\n";
    return 0;
}
