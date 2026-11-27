// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include <cstdint>
#include <vector>

namespace obim::visib {

template <typename T>
struct View1D {
    const T* ptr = nullptr;
    int64_t n = 0;
    int64_t s0 = 1;

    inline T operator()(int64_t i) const noexcept { return ptr[i * s0]; }
};

template <typename T>
struct View2D {
    const T* ptr = nullptr;
    int64_t n0 = 0;
    int64_t n1 = 0;
    int64_t s0 = 0;
    int64_t s1 = 1;

    inline T operator()(int64_t i, int64_t j) const noexcept { return ptr[i * s0 + j * s1]; }
};

template <typename EInt>
struct Intervalos {
    std::vector<EInt> he;
    std::vector<double> hlo;
    std::vector<double> hhi;
};

template <typename EInt>
Intervalos<EInt> unir_intervalos(
    View1D<EInt> he,
    View1D<double> hlo,
    View1D<double> hhi
);

Intervalos<int64_t> filtrar_e_recortar(
    View1D<int64_t> pe, View1D<int64_t> pt,
    View2D<double> a, View2D<double> b, View2D<double> d,
    View1D<int64_t> ea, View1D<int64_t> eb, View2D<int64_t> tv,
    View2D<double> A, View1D<double> gx, View1D<double> gy,
    View2D<double> nx_, View2D<double> ny_, View2D<double> cc_,
    View1D<double> tx0, View1D<double> tx1, View1D<double> ty0, View1D<double> ty1, View1D<double> tzmax,
    View1D<double> ex0, View1D<double> ex1, View1D<double> ey0, View1D<double> ey1, View1D<double> ezmin,
    int64_t nt_all, double tol_z, double d_eps
);

}  // namespace obim::visib
