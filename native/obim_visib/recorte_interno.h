// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include <cmath>

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

}  // namespace obim::visib
