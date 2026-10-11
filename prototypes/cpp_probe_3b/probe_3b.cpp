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
    // Atenção: file(const char*, bool) NÃO abre arquivo (cai no construtor de memória); use std::string.
    ifcopenshell::file f(caminho);
    std::cerr << "abrir(caminho): codigo " << static_cast<int>(f.good().value()) << "\n";
    if (f.good().value() != ifcopenshell::file_open_status::SUCCESS) {
        std::cerr << "falha ao abrir\n";
        return 1;
    }
    size_t n = 0;
    for (auto it = f.begin(); it != f.end(); ++it) ++n;
    std::cout << "esquema=" << f.schema()->name() << " entidades=" << n << "\n";
    return 0;
}
