// SPDX-License-Identifier: AGPL-3.0-or-later
// Executável do ORÁCULO da S04-T14a (item "construção concorrente", tests/test_s04_fluxo_b_paredes.py): T threads C++ criam o PRIMEIRO `Paredes` do processo ao mesmo tempo (sem aquecer
// na thread principal) e já usam o modelo. A ponte Python não alcança isto (o construtor nanobind segura o GIL), então o caso é em C++ puro. O implementador não edita este arquivo.
// Uso: fluxo_b_frio <threads> [paredes]. Imprime `FRIO ok <threads>` ao fim; queda do processo ou impasse = falha (o teste mede código de saída e prazo).
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <string>
#include <thread>
#include <vector>
#include "paredes.h"
int main(int argc, char** argv) {
    const int T = argc > 1 ? std::atoi(argv[1]) : 4, N = argc > 2 ? std::atoi(argv[2]) : 20;
    std::atomic<int> pronto{0}, falhas{0};
    std::vector<std::thread> ths;
    for (int t = 0; t < T; ++t) ths.emplace_back([&] {
        try {
            ++pronto;
            while (pronto < T) std::this_thread::yield();  // largada juntas
            fluxo_b::Paredes p;  // o 1o do processo, em paralelo com os outros
            p.criar_tipo("PAR", {0.02, 0.11, 0.02});
            const auto ws = p.criar_paredes_lote("PAR", 4.25, 2.8, 0.15, N);
            const std::string w = "IfcWall";
            if (int(ws.size()) < N || p.contar(&w) != N || p.pode_desfazer() != 2) ++falhas;
        } catch (const std::exception& e) { std::fprintf(stderr, "thread falhou: %s\n", e.what()); ++falhas; }
    });
    for (auto& th : ths) th.join();
    if (falhas) { std::fprintf(stderr, "FRIO falhou em %d thread(s)\n", falhas.load()); return 1; }
    std::printf("FRIO ok %d\n", T);
    return 0;
}
