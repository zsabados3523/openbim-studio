// SPDX-License-Identifier: AGPL-3.0-or-later
// Câmera da viewport. Estado, fila de entradas e animação. Sem Qt e sem Python.
// A thread da janela só ENFILEIRA (mutex próprio, folha: nunca se pede outro mutex dentro dele); a thread de desenho APLICA, na ordem,
// uma vez por quadro, com o tamanho real do backbuffer. Nenhuma entrada se perde. A animação de órbita é por relógio (steady_clock), não por quadro.
#pragma once
#include <chrono>
#include <deque>
#include <functional>
#include <mutex>
namespace obim {
struct Camera { double alvo[3] = {0, 0, 0}, distancia = 3.2, azimute = -45, elevacao = 30; };  // Z para cima, graus
struct Entrada { enum Tipo { Orbitar, Mover, Aproximar, Enquadrar } tipo; double a = 0, b = 0; };  // Orbitar/Mover: (dx, dy) em pixels; Aproximar: fator

class ControleCamera {
 public:
  Camera ler();                                           // o estado JÁ APLICADO
  void modificar(const std::function<void(Camera&)>& f);  // definir_camera: atômico; descarta as entradas ainda não aplicadas (a posição dada vale)
  void enfileirar(Entrada e);
  void animar(double graus_por_s);                        // 0 para na hora
  // Thread de desenho, uma vez por quadro. alt_px e aspecto: do backbuffer; bmin/bmax: caixa da cena (nullptr se vazia). Devolve o estado novo.
  Camera aplicar(int alt_px, double aspecto, const double* bmin, const double* bmax);
 private:
  std::mutex m_; Camera c_; std::deque<Entrada> fila_; double taxa_ = 0; std::chrono::steady_clock::time_point ult_;
};
}  // namespace obim
