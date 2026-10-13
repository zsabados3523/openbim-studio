// SPDX-License-Identifier: AGPL-3.0-or-later
// Ponte nanobind do módulo `fluxo_b_paredes` (S04-T13): só tradução de tipos; a lógica está em paredes.cpp. Medidas em metros, GlobalIds em texto.
// Entrada inválida (std::invalid_argument) vira ValueError; falha injetada (std::runtime_error) vira RuntimeError.
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include "paredes.h"
namespace nb = nanobind;
using namespace nb::literals;
using fluxo_b::Paredes;
NB_MODULE(fluxo_b_paredes, m) {
    nb::class_<Paredes>(m, "Paredes")
        .def(nb::init<>())
        .def("criar_tipo", &Paredes::criar_tipo, "nome"_a, "camadas_m"_a)
        .def("criar_parede", &Paredes::criar_parede, "tipo"_a, "comprimento"_a, "altura"_a, "espessura"_a)
        .def("criar_paredes_lote", &Paredes::criar_paredes_lote, "tipo"_a, "comprimento"_a, "altura"_a, "espessura"_a, "quantidade"_a)
        .def("editar_propriedades", [](Paredes& p, const std::string& alvo, std::optional<std::string> nome, nb::object props) {
            fluxo_b::Chaves chaves;  // na ordem do dicionário Python
            if (!props.is_none()) for (auto [k, v] : nb::cast<nb::dict>(props)) chaves.emplace_back(nb::cast<std::string>(k), nb::cast<std::string>(v));
            return p.editar_propriedades(alvo, nome ? &*nome : nullptr, chaves);
        }, "alvo"_a, "nome"_a = nb::none(), "propriedades"_a = nb::none())
        .def("mudar_comprimento", &Paredes::mudar_comprimento, "alvo"_a, "comprimento"_a)
        .def("desfazer", &Paredes::desfazer)
        .def("refazer", &Paredes::refazer)
        .def("ultimo", [](const Paredes& p) {
            const auto& u = p.ultimo();
            nb::dict d;
            d["criados"] = u.criados, d["alterados"] = u.alterados, d["apagados"] = u.apagados, d["geometria"] = u.geometria;
            return d;
        })
        .def("pode_desfazer", &Paredes::pode_desfazer)
        .def("pode_refazer", &Paredes::pode_refazer)
        .def("contar", [](const Paredes& p, std::optional<std::string> classe) { return p.contar(classe ? &*classe : nullptr); }, "classe"_a = nb::none())
        .def("gravar", &Paredes::gravar, "arquivo"_a)
        .def("definir_falha", &Paredes::definir_falha, "k"_a);
}
