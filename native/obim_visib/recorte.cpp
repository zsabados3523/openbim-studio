// SPDX-License-Identifier: AGPL-3.0-or-later
#include "recorte.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

namespace obim::visib {
namespace {

inline double max_f(double a, double b) noexcept {
    if (std::isnan(a) || std::isnan(b)) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    return (a >= b) ? a : b;
}

inline bool lo_less(double li, double lj) noexcept {
    const bool ni = std::isnan(li);
    const bool nj = std::isnan(lj);
    if (ni || nj) {
        return !ni && nj;
    }
    return li < lj;
}

template <typename EInt>
struct ItemIntervalo {
    EInt e;
    double lo;
    double hi;
};

template <typename EInt>
Intervalos<EInt> unir_vetores(
    const EInt* he_ptr,
    int64_t he_s0,
    const double* hlo_ptr,
    int64_t hlo_s0,
    const double* hhi_ptr,
    int64_t hhi_s0,
    size_t n
) {
    Intervalos<EInt> out;
    if (n == 0) {
        return out;
    }
    if (n == 1) {
        out.he.push_back(he_ptr[0]);
        out.hlo.push_back(hlo_ptr[0]);
        out.hhi.push_back(max_f(hlo_ptr[0], hhi_ptr[0]));
        return out;
    }

    auto at_e = [&](size_t i) noexcept -> EInt {
        return he_ptr[static_cast<int64_t>(i) * he_s0];
    };
    auto at_lo = [&](size_t i) noexcept -> double {
        return hlo_ptr[static_cast<int64_t>(i) * hlo_s0];
    };
    auto at_hi = [&](size_t i) noexcept -> double {
        return hhi_ptr[static_cast<int64_t>(i) * hhi_s0];
    };

    bool ja_ordenado = true;
    EInt prev_e = at_e(0);
    double prev_lo = at_lo(0);
    for (size_t i = 1; i < n; ++i) {
        const EInt cur_e = at_e(i);
        const double cur_lo = at_lo(i);
        if (cur_e < prev_e || (cur_e == prev_e && lo_less(cur_lo, prev_lo))) {
            ja_ordenado = false;
            break;
        }
        prev_e = cur_e;
        prev_lo = cur_lo;
    }

    out.he.reserve(n);
    out.hlo.reserve(n);
    out.hhi.reserve(n);

    if (ja_ordenado) {
        EInt e_cur = at_e(0);
        double lo_ini = at_lo(0);
        double hi_cur = at_hi(0);
        for (size_t k = 1; k < n; ++k) {
            const EInt e = at_e(k);
            const double lo = at_lo(k);
            const double hi = at_hi(k);
            if (e != e_cur || lo > hi_cur + 1e-9) {
                out.he.push_back(e_cur);
                out.hlo.push_back(lo_ini);
                out.hhi.push_back(max_f(lo_ini, hi_cur));
                e_cur = e;
                lo_ini = lo;
                hi_cur = hi;
            } else {
                hi_cur = max_f(hi_cur, hi);
            }
        }
        out.he.push_back(e_cur);
        out.hlo.push_back(lo_ini);
        out.hhi.push_back(max_f(lo_ini, hi_cur));
        return out;
    }

    std::vector<ItemIntervalo<EInt>> itens(n);
    for (size_t i = 0; i < n; ++i) {
        itens[i] = {at_e(i), at_lo(i), at_hi(i)};
    }
    std::stable_sort(
        itens.begin(), itens.end(),
        [](const ItemIntervalo<EInt>& a, const ItemIntervalo<EInt>& b) noexcept {
            if (a.e != b.e) {
                return a.e < b.e;
            }
            return lo_less(a.lo, b.lo);
        }
    );

    EInt e_cur = itens[0].e;
    double lo_ini = itens[0].lo;
    double hi_cur = itens[0].hi;
    for (size_t k = 1; k < n; ++k) {
        const auto& it = itens[k];
        if (it.e != e_cur || it.lo > hi_cur + 1e-9) {
            out.he.push_back(e_cur);
            out.hlo.push_back(lo_ini);
            out.hhi.push_back(max_f(lo_ini, hi_cur));
            e_cur = it.e;
            lo_ini = it.lo;
            hi_cur = it.hi;
        } else {
            hi_cur = max_f(hi_cur, it.hi);
        }
    }
    out.he.push_back(e_cur);
    out.hlo.push_back(lo_ini);
    out.hhi.push_back(max_f(lo_ini, hi_cur));
    return out;
}

}  // namespace

template <typename EInt>
Intervalos<EInt> unir_intervalos(
    View1D<EInt> he,
    View1D<double> hlo,
    View1D<double> hhi
) {
    if (he.n != hlo.n || he.n != hhi.n) {
        throw std::invalid_argument("He, Hlo e Hhi devem ter o mesmo comprimento");
    }
    return unir_vetores(
        he.ptr, he.s0,
        hlo.ptr, hlo.s0,
        hhi.ptr, hhi.s0,
        static_cast<size_t>(he.n)
    );
}

template Intervalos<int32_t> unir_intervalos<int32_t>(View1D<int32_t>, View1D<double>, View1D<double>);
template Intervalos<int64_t> unir_intervalos<int64_t>(View1D<int64_t>, View1D<double>, View1D<double>);

}  // namespace obim::visib
