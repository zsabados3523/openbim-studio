// SPDX-License-Identifier: AGPL-3.0-or-later
// `obimcore.malhas(arquivo, guids)` (S04-T04; LOTE_OPUS_9 §1.4 regras 1 a 4 e §1.5 R1-h/R1-i).
// Malha por elemento no mundo, com as opções da S03 (coordenadas do mundo, sem soldar vértices) e a biblioteca "híbrida".
// Bloqueio do interpretador: solto durante toda a geometria; nesse trecho nada toca em objeto Python. O arquivo é emprestado
// (regra 1) e nada dele é guardado depois do retorno (regra 2). Quem chama (a thread do comando) deixa o escritor parado.
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
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

namespace nb = nanobind;
using namespace ifcopenshell::geom;

ifcopenshell::file* emprestar(nb::handle obj);  // ponte.cpp

namespace {

constexpr const char* BIBLIOTECA = "hybrid-cgal-simple-opencascade";  // a mesma da S03 (carregador.py)

struct Malha {
    std::vector<double> pos;   // x,y,z por vértice
    std::vector<int32_t> idx;  // 3 por triângulo
    std::array<double, 6> caixa{0, 0, 0, 0, 0, 0};
    std::array<double, 4> cor{0.8, 0.8, 0.8, 1.0};  // sem estilo: cinza neutro
};

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

// Pedido com GlobalId repetido: cada repetição é calculada de novo (uma passada por repetição, sem cache entre elas), então o
// trabalho acompanha o tamanho da lista; o resultado vem da primeira passada. Sem repetição = uma passada só.
std::map<std::string, Malha> calcular(ifcopenshell::file* f, const std::vector<std::string>& guids) {
    std::map<std::string, size_t> vezes;
    std::map<std::string, int> idde;
    for (const auto& g : guids) {
        express::base b = f->instance_by_guid(g);
        if (!b) throw std::invalid_argument("GlobalId inexistente: " + g);
        idde[g] = b.id();
        ++vezes[g];
    }
    std::map<std::string, Malha> saida;
    for (const auto& [g, n] : vezes) saida[g];  // entrada vazia para quem não tem geometria
    size_t maximo = 0;
    for (const auto& [g, n] : vezes) maximo = std::max(maximo, n);
    for (size_t r = 1; r <= maximo; ++r) {
        std::set<int> ids;
        for (const auto& [g, n] : vezes) if (n >= r) ids.insert(idde[g]);
        std::map<std::string, Malha> lixo;
        passada(f, ids, r == 1 ? saida : lixo);
    }
    return saida;
}

template <typename T>
nb::object matriz(std::vector<T>&& v, size_t colunas) {  // o numpy fica dono do vetor movido
    auto* dono = new std::vector<T>(std::move(v));
    nb::capsule limpa(dono, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
    size_t forma[2] = {dono->size() / colunas, colunas};
    return nb::cast(nb::ndarray<nb::numpy, T, nb::ndim<2>>(dono->data(), 2, forma, limpa));
}

}  // namespace

void registrar_malhas(nb::module_& m) {
    m.def("malhas", [](nb::object arquivo, const std::vector<std::string>& guids) {
        ifcopenshell::file* f = emprestar(arquivo);  // com o bloqueio: toca em objeto Python
        std::map<std::string, Malha> res;
        std::string erro;
        {
            nb::gil_scoped_release solto;  // daqui até o fim do bloco: nenhum objeto Python
            try {
                res = calcular(f, guids);
            } catch (const std::exception& e) {
                erro = e.what();
            }
        }
        if (!erro.empty()) throw nb::value_error(erro.c_str());
        nb::dict d;
        for (auto& [g, ml] : res) {
            nb::dict item;
            item["posicoes"] = matriz(std::move(ml.pos), 3);
            item["indices"] = matriz(std::move(ml.idx), 3);
            item["caixa"] = matriz(std::vector<double>(ml.caixa.begin(), ml.caixa.end()), 6);
            item["cor"] = matriz(std::vector<double>(ml.cor.begin(), ml.cor.end()), 4);
            d[g.c_str()] = item;
        }
        return d;
    }, nb::arg("arquivo"), nb::arg("guids"));
}
