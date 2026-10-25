// SPDX-License-Identifier: AGPL-3.0-or-later
// Seleção por triângulo. Raio do pixel a partir da câmera JÁ APLICADA e do tamanho real do backbuffer; caixas por objeto
// primeiro, triângulos (Möller–Trumbore) só dos candidatos, sobre a cópia compacta da cena. Puro: sem Qt, sem Python, sem mutex (quem chama segura os
// `shared_ptr<Dados>`, imutáveis depois de publicados). Mesma convenção de projeção do viewport.cpp: perspectiva de 45 graus VERTICAL, Z para cima.
#pragma once
#include "camera.h"
#include "cena.h"
#include <memory>
#include <optional>
#include <string>
#include <vector>
namespace obim {
struct Raio { double o[3], d[3]; double tmin = 0; };  // origem, direção (unitária) e distância inicial (plano perto do desenho)
// (x, y) em pixels FÍSICOS do backbuffer, origem no canto superior esquerdo, y para baixo; larg e alt > 0. `perto`: plano de recorte do desenho (0 = sem recorte);
// o raio só vale a partir dele (distância medida ao longo do raio = perto / cos do ângulo com o eixo da câmera).
Raio raio_do_pixel(const Camera& c, int larg, int alt, double x, double y, double perto = 0);
// GlobalId do objeto cujo triângulo o raio acerta primeiro; nullopt se nenhum (ou se o mais perto é geometria sem objeto).
std::optional<std::string> selecionar(const std::vector<std::shared_ptr<Dados>>& lotes, const Raio& r);
}  // namespace obim
