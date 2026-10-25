// SPDX-License-Identifier: AGPL-3.0-or-later
// Autotestes do executável do fluxo B (CONTRATO.md, Parte 2, "Autotestes"): sem janela, uma linha `RESULTADO {json}` no stdout.
#pragma once
#include <string>
#include <vector>
namespace fluxo_b {
// `--versao` ou `--autoteste ler|localidade|corrida|memoria ...`: roda, escreve o RESULTADO e devolve true; outro argumento: false (nada feito). Exceção do autoteste sobe para o main.
bool autoteste(const std::vector<std::string>& a);
}  // namespace fluxo_b
