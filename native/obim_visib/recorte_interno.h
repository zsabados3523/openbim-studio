// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "recorte.h"

#include <cmath>
#include <cstdint>
#include <vector>

namespace obim::visib {

// Semantica de np.maximum: preserva bits do NaN de entrada; em empate (+0/-0) devolve b.
inline double max_f(double a, double b) noexcept {
    if (std::isnan(a)) return a;
    if (std::isnan(b)) return b;
    return (a > b) ? a : b;
}

// Semantica de np.minimum: preserva bits do NaN de entrada; em empate (+0/-0) devolve b.
inline double min_f(double a, double b) noexcept {
    if (std::isnan(a)) return a;
    if (std::isnan(b)) return b;
    return (a < b) ? a : b;
}

struct ParLoHi {
    double lo;
    double hi;
};

struct MalhaClipViews {
    View2D<double> a, b, d;
    View1D<int64_t> ea, eb;
    View2D<int64_t> tv;
    View2D<double> A;
    View1D<double> gx, gy;
    View2D<double> nx_, ny_, cc_;
    View1D<double> tx0, tx1, ty0, ty1, tzmax;
    View1D<double> ex0, ex1, ey0, ey1, ezmin;
};

struct ArestaCache {
    int64_t e;
    double p0x, p0y, a_z, bx, by, bz, dx, dy, dz, len2d;
    double ex0, ex1, ey0, ey1, ezmin;
    int64_t eav, ebv;
};

inline bool passa_aabb_z(const ArestaCache& ac, int64_t t, const MalhaClipViews& mv, double tol_z) noexcept {
    return mv.tzmax(t) > ac.ezmin + tol_z
        && mv.tx1(t) >= ac.ex0 && mv.tx0(t) <= ac.ex1
        && mv.ty1(t) >= ac.ey0 && mv.ty0(t) <= ac.ey1;
}

void validar_malha_views(const MalhaClipViews& mv);
ArestaCache carregar_aresta(int64_t e, const MalhaClipViews& mv) noexcept;
void recortar_aresta_tri(
    const ArestaCache& ac, int64_t t, const MalhaClipViews& mv,
    double tol_z, double d_eps, double eps, std::vector<ParLoHi>& buf_grupo
);
void emitir_grupo_aresta(int64_t e, std::vector<ParLoHi>& buf, Intervalos<int64_t>& out);

}  // namespace obim::visib
