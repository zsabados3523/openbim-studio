// SPDX-License-Identifier: AGPL-3.0-or-later
// Ponte nanobind de `obimcore.malhas(arquivo, guids)` (separada da geometria em nucleo/malha.cpp, C++ puro). Só adapta tipos:
// empresta o arquivo (com o bloqueio), SOLTA o bloqueio durante toda a geometria (nesse trecho nada toca em objeto Python) e monta os arrays do numpy.
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include "nucleo/malha.h"
#include <ifcparse/file.h>

namespace nb = nanobind;

ifcopenshell::file* emprestar(nb::handle obj);  // ponte.cpp

namespace {
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
        // Com a SessaoModelo (ADR-004 §5.1 regra 3): confere a trava COM o bloqueio (o erro de _obimcore_entrar sobe como está) e chama
        // _obimcore_sair com o bloqueio de volta, em todo caminho. O C++ nunca pega a trava do modelo. O caminho do ifcopenshell.file não muda.
        nb::object sessao;
        nb::object alvo = arquivo;  // fica referenciado até o fim
        if (!PyObject_IsInstance(arquivo.ptr(), nb::module_::import_("ifcopenshell.ifcopenshell_wrapper").attr("file").ptr()) &&
            nb::hasattr(arquivo, "_obimcore_entrar")) {
            sessao = arquivo;
            alvo = sessao.attr("_obimcore_entrar")();
        }
        std::map<std::string, obim::Malha> res;
        try {
            ifcopenshell::file* f = emprestar(alvo);  // com o bloqueio: toca em objeto Python
            nb::gil_scoped_release solto;  // daqui até o fim do bloco: nenhum objeto Python (falha = std::invalid_argument = ValueError)
            res = obim::malhas_do_arquivo(f, guids);
        } catch (...) {
            if (sessao.is_valid()) sessao.attr("_obimcore_sair")();
            throw;
        }
        if (sessao.is_valid()) sessao.attr("_obimcore_sair")();
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
