// SPDX-License-Identifier: AGPL-3.0-or-later
// Seleção por triângulo (S04-T10). Ver selecao.h.
#include "selecao.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace obim {
namespace {
constexpr double PI = 3.14159265358979323846, MEIO_FOV = 22.5 * PI / 180, EPS_BARI = 1e-7;  // EPS_BARI: sem frestas entre triângulos vizinhos (arredondamento)
struct Cand { double t; const Dados* d; uint32_t pi, ni; const std::string* guid; };

// Entrada do raio na caixa (método das lajes); false se não cruza. A caixa é engordada um pouco: objeto plano tem espessura zero.
bool caixa_raio(const Raio& r, const double* inv, const float* mn, const float* mx, double& ent) {
  double diag = 0;
  for (int a = 0; a < 3; ++a) diag += double(mx[a] - mn[a]) * (mx[a] - mn[a]);
  const double folga = 1e-5 * std::sqrt(diag) + 1e-6;
  double t0 = r.tmin, t1 = 1e300;
  for (int a = 0; a < 3; ++a) {
    double ta = (mn[a] - folga - r.o[a]) * inv[a], tb = (mx[a] + folga - r.o[a]) * inv[a];
    if (ta > tb) std::swap(ta, tb);
    if (ta > t0) t0 = ta;
    if (tb < t1) t1 = tb;
    if (t0 > t1) return false;
  }
  ent = t0; return true;
}

// Möller–Trumbore, dupla face. Devolve a distância (> 0) ou -1.
inline double triangulo(const Raio& r, const float* a, const float* b, const float* c) {
  double e1[3], e2[3], tv[3];
  for (int k = 0; k < 3; ++k) { tv[k] = r.o[k] - a[k]; e1[k] = double(b[k]) - a[k]; e2[k] = double(c[k]) - a[k]; }
  const double p[3] = {r.d[1] * e2[2] - r.d[2] * e2[1], r.d[2] * e2[0] - r.d[0] * e2[2], r.d[0] * e2[1] - r.d[1] * e2[0]};
  const double det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2];
  const double n1 = e1[0] * e1[0] + e1[1] * e1[1] + e1[2] * e1[2], n2 = e2[0] * e2[0] + e2[1] * e2[1] + e2[2] * e2[2];
  if (det * det <= 1e-24 * n1 * n2) return -1;  // raio paralelo ao plano (ou triângulo degenerado)
  const double inv = 1.0 / det, u = (tv[0] * p[0] + tv[1] * p[1] + tv[2] * p[2]) * inv;
  if (u < -EPS_BARI || u > 1 + EPS_BARI) return -1;
  const double q[3] = {tv[1] * e1[2] - tv[2] * e1[1], tv[2] * e1[0] - tv[0] * e1[2], tv[0] * e1[1] - tv[1] * e1[0]};
  const double v = (r.d[0] * q[0] + r.d[1] * q[1] + r.d[2] * q[2]) * inv;
  if (v < -EPS_BARI || u + v > 1 + EPS_BARI) return -1;
  const double t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * inv;
  return t > r.tmin ? t : -1;
}
}  // namespace

Raio raio_do_pixel(const Camera& c, int larg, int alt, double x, double y, double perto) {
  const double az = c.azimute * PI / 180, el = c.elevacao * PI / 180, tv = std::tan(MEIO_FOV), th = tv * double(larg) / alt;
  const double para[3] = {std::cos(el) * std::cos(az), std::cos(el) * std::sin(az), std::sin(el)};  // do alvo para a câmera
  const double dir[3] = {-std::sin(az), std::cos(az), 0}, cima[3] = {-std::sin(el) * std::cos(az), -std::sin(el) * std::sin(az), std::cos(el)};
  const double nx = (2 * x / larg - 1) * th, ny = (1 - 2 * y / alt) * tv;
  Raio r; double n = 0;
  for (int k = 0; k < 3; ++k) { r.o[k] = c.alvo[k] + c.distancia * para[k]; r.d[k] = -para[k] + nx * dir[k] + ny * cima[k]; n += r.d[k] * r.d[k]; }
  n = std::sqrt(n);
  for (double& v : r.d) v /= n;
  const double cosang = -(r.d[0] * para[0] + r.d[1] * para[1] + r.d[2] * para[2]);  // d . frente (frente = -para): o plano perto é perpendicular ao eixo
  r.tmin = perto > 0 && cosang > 1e-9 ? perto / cosang : 0;
  return r;
}

std::optional<std::string> selecionar(const std::vector<std::shared_ptr<Dados>>& lotes, const Raio& r) {
  static const std::string SEM_OBJETO;
  double inv[3];
  for (int a = 0; a < 3; ++a) inv[a] = r.d[a] != 0 ? 1.0 / r.d[a] : 1e300;
  std::vector<Cand> cands;  // 1) caixas por objeto
  for (auto& d : lotes) {
    if (d->i.empty()) continue;
    double ent;
    if (d->objs.empty()) {  // lote sem tabela de objetos: uma peça só, sem GlobalId (oclui, mas não é selecionável)
      const float mn[3] = {float(d->cmin[0]), float(d->cmin[1]), float(d->cmin[2])}, mx[3] = {float(d->cmax[0]), float(d->cmax[1]), float(d->cmax[2])};
      if (caixa_raio(r, inv, mn, mx, ent)) cands.push_back({ent, d.get(), 0, uint32_t(d->i.size()), &SEM_OBJETO});
      continue;
    }
    for (auto& o : d->objs)
      if (o.ni && o.nv && caixa_raio(r, inv, o.cmin, o.cmax, ent)) cands.push_back({ent, d.get(), o.pi, o.ni, &o.guid});
  }
  std::sort(cands.begin(), cands.end(), [](const Cand& a, const Cand& b) { return a.t < b.t; });
  double melhor = 1e300; const std::string* guid = nullptr;  // 2) triângulos só dos candidatos, do mais perto para o mais longe
  for (const Cand& c : cands) {
    if (c.t > melhor) break;  // este e todos os seguintes entram na caixa depois do melhor acerto
    const unsigned char* base = c.d->v.data(); const uint32_t* ind = c.d->i.data() + c.pi;
    for (uint32_t k = 0; k + 2 < c.ni; k += 3) {
      const auto* A = reinterpret_cast<const float*>(base + size_t(ind[k]) * BYTES_VERTICE);
      const auto* B = reinterpret_cast<const float*>(base + size_t(ind[k + 1]) * BYTES_VERTICE);
      const auto* C = reinterpret_cast<const float*>(base + size_t(ind[k + 2]) * BYTES_VERTICE);
      const double t = triangulo(r, A, B, C);
      if (t > 0 && t < melhor) { melhor = t; guid = c.guid; }
    }
  }
  if (!guid || guid->empty()) return std::nullopt;
  return *guid;
}
}  // namespace obim
