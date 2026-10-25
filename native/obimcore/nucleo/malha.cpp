// SPDX-License-Identifier: AGPL-3.0-or-later
// Malha por elemento no mundo, C++ PURO: sem Python; a ponte é ponte_malha.cpp.
// Opções do viewport Python (coordenadas do mundo, sem soldar vértices) e a biblioteca "híbrida". O arquivo é emprestado (regra 1) e nada dele é guardado
// depois do retorno (regra 2). Quem chama deixa o escritor parado (regra 3).
#include "malha.h"
#include <ifcparse/file.h>
#include <ifcparse/express.h>
#include <ifcgeom/iterator.h>
#include <ifcgeom/kernel_registry.h>
#include <ifcgeom/representation.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace ifcopenshell::geom;

namespace obim {
namespace {

constexpr const char* BIBLIOTECA = "hybrid-cgal-simple-opencascade";  // a mesma de carregador.py

// Uma passada por vez no processo (sem o bloqueio do interpretador, que está solto): com 4 threads em arquivos diferentes a
// biblioteca de geometria derrubou o processo em ~10% das rodadas (medido); serializada, 0 em 55. Travar só a construção não bastou.
std::mutex uma_geometria_por_vez;

// Só C++ puro (sem objeto Python). Lê o modelo; o escritor está parado na chamada (regra 3).
// Uma passada = um iterador sobre o conjunto de peças (cada peça uma vez).
void passada(ifcopenshell::file* f, const std::set<int>& ids, std::map<std::string, Malha>& saida) {
    std::lock_guard<std::mutex> trava(uma_geometria_por_vez);
    settings s;
    s.get<settings::UseWorldCoords>().value = true;
    s.get<settings::WeldVertices>().value = false;
    std::vector<filter_function> filtros{[&ids](const express::base& b) { return ids.count(b.id()) > 0; }};
    iterator it(kernels::construct(f, BIBLIOTECA, s), s, f, filtros, 1);
    if (!it.initialize()) return;
    do {
        std::unique_ptr<element> el = it.get();
        auto* te = dynamic_cast<triangulation_element*>(el.get());
        if (!te) continue;
        const triangulation& t = te->geometry();
        Malha& m = saida[te->guid()];
        const int base = (int)(m.pos.size() / 3);
        m.pos.insert(m.pos.end(), t.verts().begin(), t.verts().end());
        for (int i : t.faces()) m.idx.push_back(base + i);
        if (!t.materials().empty() && t.materials()[0]) {
            const auto& st = *t.materials()[0];
            const auto& c = st.get_color();
            if (std::isfinite(c.r()) && std::isfinite(c.g()) && std::isfinite(c.b()))
                m.cor = {c.r(), c.g(), c.b(), st.has_transparency() ? 1.0 - st.transparency : 1.0};
        }
    } while (it.next());
    for (auto& [g, m] : saida) {
        if (m.pos.empty()) continue;
        for (int k = 0; k < 3; ++k) { m.caixa[k] = 1e300; m.caixa[3 + k] = -1e300; }
        for (size_t i = 0; i < m.pos.size(); ++i) {
            m.caixa[i % 3] = std::min(m.caixa[i % 3], m.pos[i]);
            m.caixa[3 + i % 3] = std::max(m.caixa[3 + i % 3], m.pos[i]);
        }
    }
}

// GlobalIds repetidos no pedido contam uma vez só: uma passada, um resultado por GlobalId.
std::map<std::string, Malha> calcular(ifcopenshell::file* f, const std::vector<std::string>& guids) {
    std::set<int> ids;
    std::map<std::string, Malha> saida;
    for (const auto& g : guids) {
        if (saida.count(g)) continue;
        express::base b = f->instance_by_guid(g);
        if (!b) throw std::invalid_argument("GlobalId inexistente: " + g);
        ids.insert(b.id());
        saida[g];  // entrada vazia para quem não tem geometria
    }
    passada(f, ids, saida);
    return saida;
}

}  // namespace

std::map<std::string, Malha> malhas_do_arquivo(ifcopenshell::file* f, const std::vector<std::string>& guids) {
    try {
        return calcular(f, guids);
    } catch (const std::exception& e) {
        throw std::invalid_argument(e.what());
    } catch (...) {  // p.ex. Standard_Failure do OCCT, que não deriva de std::exception
        throw std::invalid_argument("erro desconhecido na geração da malha");
    }
}
}  // namespace obim
