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

}  // namespace obim::visib
