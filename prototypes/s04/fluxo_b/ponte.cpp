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
namespace {
// Toda chamada converte os argumentos COM o GIL, solta o GIL e só então pega a trava do modelo (nunca ao contrário: impasse). `espera`: None espera a vez; 0 falha na hora com ModeloOcupado (antes de validar).
bool esperar(const nb::object& espera) {
    if (espera.is_none()) return true;
    if (!nb::isinstance<nb::int_>(espera) && !nb::isinstance<nb::float_>(espera)) throw std::invalid_argument("espera: só None (esperar a vez) ou 0 (não esperar)");
    if (nb::cast<double>(espera) != 0.0) throw std::invalid_argument("espera: só None (esperar a vez) ou 0 (não esperar)");
    return false;
}
template <class F> auto escrever(Paredes& p, const nb::object& espera, F&& f) {
    bool e = esperar(espera);
    nb::gil_scoped_release solta;
    auto trava = p.pegar(e);
    return f();
}
template <class F> auto ler(Paredes& p, F&& f) { nb::gil_scoped_release solta; auto trava = p.pegar(true); return f(); }  // as leituras esperam o comando em curso: nunca o veem pela metade
}  // namespace
NB_MODULE(fluxo_b_paredes, m) {
    nb::exception<fluxo_b::ModeloOcupado>(m, "ModeloOcupado", PyExc_RuntimeError);
    nb::class_<Paredes>(m, "Paredes")
        .def(nb::init<>())
        .def("criar_tipo", [](Paredes& p, const std::string& nome, const std::vector<double>& camadas, nb::object espera) { return escrever(p, espera, [&] { return p.criar_tipo(nome, camadas); }); },
             "nome"_a, "camadas_m"_a, "espera"_a = nb::none())
        .def("criar_parede", [](Paredes& p, const std::string& tipo, double c, double h, double e, nb::object espera) { return escrever(p, espera, [&] { return p.criar_parede(tipo, c, h, e); }); },
             "tipo"_a, "comprimento"_a, "altura"_a, "espessura"_a, "espera"_a = nb::none())
        .def("criar_paredes_lote", [](Paredes& p, const std::string& tipo, double c, double h, double e, int n, nb::object espera) { return escrever(p, espera, [&] { return p.criar_paredes_lote(tipo, c, h, e, n); }); },
             "tipo"_a, "comprimento"_a, "altura"_a, "espessura"_a, "quantidade"_a, "espera"_a = nb::none())
        .def("editar_propriedades", [](Paredes& p, const std::string& alvo, std::optional<std::string> nome, nb::object props, nb::object espera) {
            fluxo_b::Chaves chaves;  // na ordem do dicionário Python
            if (!props.is_none()) for (auto [k, v] : nb::cast<nb::dict>(props)) chaves.emplace_back(nb::cast<std::string>(k), nb::cast<std::string>(v));
            return escrever(p, espera, [&] { return p.editar_propriedades(alvo, nome ? &*nome : nullptr, chaves); });
        }, "alvo"_a, "nome"_a = nb::none(), "propriedades"_a = nb::none(), "espera"_a = nb::none())
        .def("mudar_comprimento", [](Paredes& p, const std::string& alvo, double c, nb::object espera) { return escrever(p, espera, [&] { return p.mudar_comprimento(alvo, c); }); }, "alvo"_a, "comprimento"_a, "espera"_a = nb::none())
        .def("desfazer", [](Paredes& p, nb::object espera) { return escrever(p, espera, [&] { return p.desfazer(); }); }, "espera"_a = nb::none())
        .def("refazer", [](Paredes& p, nb::object espera) { return escrever(p, espera, [&] { return p.refazer(); }); }, "espera"_a = nb::none())
        .def("abrir", [](Paredes& p, const std::string& arquivo, nb::object espera) { escrever(p, espera, [&] { return p.abrir(arquivo), 0; }); }, "arquivo"_a, "espera"_a = nb::none())
        .def("copiar_atributo", [](Paredes& p, unsigned destino, unsigned origem, const std::string& atributo, nb::object espera) { return escrever(p, espera, [&] { return p.copiar_atributo(destino, origem, atributo); }); },
             "destino"_a, "origem"_a, "atributo"_a, "espera"_a = nb::none())
        .def("ultimo", [](Paredes& p) {
            fluxo_b::Ultimo u = ler(p, [&] { return p.ultimo(); });
            nb::dict d;
            d["criados"] = u.criados, d["alterados"] = u.alterados, d["apagados"] = u.apagados, d["geometria"] = u.geometria;
            return d;
        })
        .def("pode_desfazer", [](Paredes& p) { return ler(p, [&] { return p.pode_desfazer(); }); })
        .def("pode_refazer", [](Paredes& p) { return ler(p, [&] { return p.pode_refazer(); }); })
        .def("produtos_base", [](Paredes& p) { return ler(p, [&] { return p.produtos_base(); }); })
        .def("contar", [](Paredes& p, std::optional<std::string> classe) { return ler(p, [&] { return p.contar(classe ? &*classe : nullptr); }); }, "classe"_a = nb::none())
        .def("gravar", [](Paredes& p, const std::string& arquivo) { ler(p, [&] { return p.gravar(arquivo), 0; }); }, "arquivo"_a)
        .def("definir_falha", [](Paredes& p, int k) { ler(p, [&] { return p.definir_falha(k), 0; }); }, "k"_a);
}
