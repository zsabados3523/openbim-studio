// SPDX-License-Identifier: AGPL-3.0-or-later
// Malha por elemento, C++ PURO: nenhum include de Python. Implementação em malha.cpp; a ponte (ponte_malha.cpp) só converte os tipos.
#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
namespace ifcopenshell { class file; }
namespace obim {
struct Malha {
    std::vector<double> pos;   // x,y,z por vértice
    std::vector<int32_t> idx;  // 3 por triângulo
    std::array<double, 6> caixa{0, 0, 0, 0, 0, 0};
    std::array<double, 4> cor{0.8, 0.8, 0.8, 1.0};  // sem estilo: cinza neutro
};
// Uma malha por GlobalId (repetidos contam uma vez; sem geometria: vazia). TODA falha vira std::invalid_argument (a ponte a vê como ValueError).
// O arquivo é só emprestado durante a chamada; ela não toca em Python, então a ponte pode soltar o bloqueio do interpretador.
std::map<std::string, Malha> malhas_do_arquivo(ifcopenshell::file* f, const std::vector<std::string>& guids);
}  // namespace obim
