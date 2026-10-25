// SPDX-License-Identifier: AGPL-3.0-or-later
// Câmera da viewport. Ver camera.h.
#include "camera.h"
#include <algorithm>
#include <cmath>

namespace obim {
namespace {
constexpr double PI = 3.14159265358979323846, MEIO_FOV = 22.5 * PI / 180;  // a projeção do viewport.cpp é perspective(45 graus vertical)
void limitar(Camera& c) { c.distancia = std::clamp(c.distancia, 0.1, 10000.0); c.elevacao = std::clamp(c.elevacao, -89.0, 89.0); }
}  // namespace

Camera ControleCamera::ler() { std::lock_guard<std::mutex> l(m_); return c_; }

void ControleCamera::modificar(const std::function<void(Camera&)>& f) { std::lock_guard<std::mutex> l(m_); fila_.clear(); f(c_); }

void ControleCamera::enfileirar(Entrada e) { std::lock_guard<std::mutex> l(m_); fila_.push_back(e); }

void ControleCamera::animar(double graus_por_s) { std::lock_guard<std::mutex> l(m_); taxa_ = graus_por_s; ult_ = std::chrono::steady_clock::now(); }

Camera ControleCamera::aplicar(int alt_px, double aspecto, const double* bmin, const double* bmax) {
  std::lock_guard<std::mutex> l(m_);
  Camera& c = c_;
  for (const Entrada& e : fila_) {
    switch (e.tipo) {
      case Entrada::Orbitar: c.azimute -= 0.5 * e.a; c.elevacao = std::clamp(c.elevacao + 0.5 * e.b, -89.0, 89.0); break;  // 0,5 grau por pixel
      case Entrada::Aproximar: c.distancia = std::clamp(c.distancia / e.a, 0.1, 10000.0); break;
      case Entrada::Mover: {  // o modelo anda junto com o mouse: 1 pixel do mouse = 1 pixel da imagem no plano do alvo
        const double az = c.azimute * PI / 180, el = c.elevacao * PI / 180, ppx = 2 * c.distancia * std::tan(MEIO_FOV) / (std::max)(alt_px, 1);
        const double dir[3] = {-std::sin(az), std::cos(az), 0}, cima[3] = {-std::sin(el) * std::cos(az), -std::sin(el) * std::sin(az), std::cos(el)};
        for (int k = 0; k < 3; ++k) c.alvo[k] += (-e.a * dir[k] + e.b * cima[k]) * ppx;
        break;
      }
      case Entrada::Enquadrar: {  // cada canto da caixa precisa caber: distancia >= |lado|/tan(meio campo) + profundidade do canto (perspectiva)
        if (!bmin) break;  // cena vazia: nada a enquadrar
        const double az = c.azimute * PI / 180, el = c.elevacao * PI / 180, tv = std::tan(MEIO_FOV), th = tv * aspecto;
        const double dir[3] = {-std::sin(az), std::cos(az), 0}, cima[3] = {-std::sin(el) * std::cos(az), -std::sin(el) * std::sin(az), std::cos(el)};
        const double para[3] = {std::cos(el) * std::cos(az), std::cos(el) * std::sin(az), std::sin(el)};  // do alvo para a câmera
        for (int k = 0; k < 3; ++k) c.alvo[k] = (bmin[k] + bmax[k]) / 2;
        double dist = 0;
        for (int m = 0; m < 8; ++m) {
          double x = 0, y = 0, z = 0;
          for (int k = 0; k < 3; ++k) { const double o = ((m >> k) & 1 ? bmax[k] : bmin[k]) - c.alvo[k]; x += o * dir[k]; y += o * cima[k]; z += o * para[k]; }
          dist = (std::max)(dist, (std::max)(std::abs(x) / th, std::abs(y) / tv) + z);
        }
        c.distancia = dist * 1.05;  // folga de 5%
        break;
      }
    }
    limitar(c);
  }
  fila_.clear();
  if (taxa_ != 0) {
    const auto agora = std::chrono::steady_clock::now();
    c.azimute += taxa_ * std::chrono::duration<double>(agora - ult_).count(); ult_ = agora;
  }
  return c;
}
}  // namespace obim
