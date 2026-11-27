// SPDX-License-Identifier: AGPL-3.0-or-later
#ifdef __FAST_MATH__
#error "obimvisib proibe -ffast-math (__FAST_MATH__)"
#endif
#if defined(_MSC_VER) && defined(_M_FP_FAST)
#error "obimvisib proibe /fp:fast (_M_FP_FAST)"
#endif
#if defined(_MSC_VER) && !defined(_M_FP_PRECISE)
#error "obimvisib exige /fp:precise (_M_FP_PRECISE)"
#endif

#include "pares.h"
#include "recorte_interno.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace obim::visib {
namespace {

constexpr int64_t kMaxTotalCels = 100'000'000;
constexpr int64_t kI64Min = std::numeric_limits<int64_t>::min();
constexpr int64_t kI64Max = std::numeric_limits<int64_t>::max();

// Clampa coordenada para [0, dim - 1] sem UB em +inf/NaN (diverge de int64(inf) -> 0 no Python).
inline int64_t cel_clamp(double v, double mn, double g, int64_t dim) noexcept {
    const double f = std::floor((v - mn) / g);
    if (std::isnan(f) || f <= 0.0) return 0;
    const double hi = static_cast<double>(dim - 1);
    return (f >= hi) ? (dim - 1) : static_cast<int64_t>(f);
}

inline int64_t calc_span(int64_t lo, int64_t hi) {
    if (hi < lo) {
        if (static_cast<uint64_t>(lo) - static_cast<uint64_t>(hi) > 1ULL) {
            throw std::invalid_argument("intervalo de celula invalido");
        }
        return 0;
    }
    const uint64_t diff = static_cast<uint64_t>(hi) - static_cast<uint64_t>(lo);
    if (diff >= static_cast<uint64_t>(kI64Max)) {
        throw std::invalid_argument("estouro em largura ou altura de celula");
    }
    return static_cast<int64_t>(diff + 1ULL);
}

inline void check_cel_coord(int64_t x, int64_t y, int64_t nx) {
    bool ok_mul = true;
    if ((y == -1 && nx == kI64Min) || (nx == -1 && y == kI64Min)) {
        ok_mul = false;
    } else if (y > 0 && nx != 0) {
        ok_mul = (nx > 0) ? (y <= kI64Max / nx) : (nx >= kI64Min / y);
    } else if (y < 0 && nx != 0) {
        ok_mul = (nx > 0) ? (y >= kI64Min / nx) : (nx >= kI64Max / y);
    }
    if (!ok_mul) throw std::invalid_argument("estouro em indice de celula");
    const int64_t row = y * nx;
    if ((x > 0) ? (row > kI64Max - x) : (row < kI64Min - x)) {
        throw std::invalid_argument("estouro em indice de celula");
    }
}

}  // namespace

SubsegCelsOut subseg_cels(
    View2D<double> a, View2D<double> d, View1D<int64_t> nsub,
    double mn_x, double mn_y, double cg, int64_t Wc, int64_t Hc
) {
    if (a.n0 != d.n0 || a.n0 != nsub.n) throw std::invalid_argument("a, d e nsub devem ter o mesmo comprimento");
    if (a.n1 != 3 || d.n1 != 3) throw std::invalid_argument("a e d devem ter 3 colunas");
    if (Wc <= 0 || Hc <= 0 || !std::isfinite(cg) || cg <= 0.0 || !std::isfinite(mn_x) || !std::isfinite(mn_y)) {
        throw std::invalid_argument("parametros de grade invalidos");
    }

    int64_t total = 0;
    for (int64_t i = 0; i < nsub.n; ++i) {
        const int64_t n = nsub(i);
        if (n < 0) throw std::invalid_argument("nsub nao pode ser negativo");
        if (n > kI64Max - total || total + n > kMaxTotalCels) {
            throw std::invalid_argument("total de subsegmentos excede o limite");
        }
        total += n;
    }

    SubsegCelsOut out;
    out.total = total;
    if (total == 0) return out;

    const size_t sz = static_cast<size_t>(total);
    if (sz > std::numeric_limits<size_t>::max() / (3 * sizeof(double))) {
        throw std::invalid_argument("estouro na alocacao de subsegmentos");
    }
    out.s_l.resize(sz); out.t0_s.resize(sz); out.t1_s.resize(sz);
    out.sa_flat.resize(sz * 3); out.sb_flat.resize(sz * 3);
    out.sx0.resize(sz); out.sx1.resize(sz); out.sy0.resize(sz); out.sy1.resize(sz);

    size_t pos = 0;
    for (int64_t i = 0; i < nsub.n; ++i) {
        const int64_t n = nsub(i);
        if (n == 0) continue;
        const double ax = a(i, 0), ay = a(i, 1), az = a(i, 2);
        const double dx = d(i, 0), dy = d(i, 1), dz = d(i, 2);
        const double dn = static_cast<double>(n);
        for (int64_t k = 0; k < n; ++k) {
            const double t0 = static_cast<double>(k) / dn, t1 = static_cast<double>(k + 1) / dn;
            const double sa0 = ax + t0 * dx, sa1 = ay + t0 * dy, sa2 = az + t0 * dz;
            const double sb0 = ax + t1 * dx, sb1 = ay + t1 * dy, sb2 = az + t1 * dz;
            out.s_l[pos] = i; out.t0_s[pos] = t0; out.t1_s[pos] = t1;
            const size_t p3 = pos * 3;
            out.sa_flat[p3] = sa0; out.sa_flat[p3 + 1] = sa1; out.sa_flat[p3 + 2] = sa2;
            out.sb_flat[p3] = sb0; out.sb_flat[p3 + 1] = sb1; out.sb_flat[p3 + 2] = sb2;
            out.sx0[pos] = cel_clamp(min_f(sa0, sb0), mn_x, cg, Wc);
            out.sx1[pos] = cel_clamp(max_f(sa0, sb0), mn_x, cg, Wc);
            out.sy0[pos] = cel_clamp(min_f(sa1, sb1), mn_y, cg, Hc);
            out.sy1[pos] = cel_clamp(max_f(sa1, sb1), mn_y, cg, Hc);
            ++pos;
        }
    }
    return out;
}

ExpandirCelsOut expandir_celulas(
    View1D<int64_t> ix0, View1D<int64_t> ix1,
    View1D<int64_t> iy0, View1D<int64_t> iy1, int64_t nx
) {
    if (ix0.n != ix1.n || ix0.n != iy0.n || ix0.n != iy1.n) {
        throw std::invalid_argument("ix0, ix1, iy0 e iy1 devem ter o mesmo comprimento");
    }

    int64_t total = 0;
    for (int64_t i = 0; i < ix0.n; ++i) {
        const int64_t x0 = ix0(i), x1 = ix1(i), y0 = iy0(i), y1 = iy1(i);
        const int64_t w = calc_span(x0, x1);
        const int64_t h = calc_span(y0, y1);
        if (w == 0 || h == 0) continue;
        if (h > kI64Max / w) throw std::invalid_argument("estouro no tamanho da caixa de celulas");
        const int64_t prod = w * h;
        if (prod > kI64Max - total || total + prod > kMaxTotalCels) {
            throw std::invalid_argument("total de celulas excede o limite");
        }
        total += prod;
        for (int64_t y : {y0, y1}) {
            for (int64_t x : {x0, x1}) check_cel_coord(x, y, nx);
        }
    }

    ExpandirCelsOut out;
    if (total == 0) return out;
    out.obj.resize(static_cast<size_t>(total));
    out.cel.resize(static_cast<size_t>(total));

    size_t pos = 0;
    for (int64_t i = 0; i < ix0.n; ++i) {
        const int64_t x0 = ix0(i), x1 = ix1(i), y0 = iy0(i), y1 = iy1(i);
        if (x1 < x0 || y1 < y0) continue;
        const int64_t w = static_cast<int64_t>(static_cast<uint64_t>(x1) - static_cast<uint64_t>(x0)) + 1;
        const int64_t h = static_cast<int64_t>(static_cast<uint64_t>(y1) - static_cast<uint64_t>(y0)) + 1;
        for (int64_t dy = 0; dy < h; ++dy) {
            const int64_t row = (y0 + dy) * nx;
            for (int64_t dx = 0; dx < w; ++dx) {
                out.obj[pos] = i;
                out.cel[pos] = row + (x0 + dx);
                ++pos;
            }
        }
    }
    return out;
}

}  // namespace obim::visib
