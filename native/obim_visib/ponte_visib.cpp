// SPDX-License-Identifier: AGPL-3.0-or-later
// Ponte Python/C++ minima (esqueleto N1) do modulo `_obimvisib`.
#include <nanobind/nanobind.h>

#ifndef OBIM_VISIB_FLAGS_FP
#  define OBIM_VISIB_FLAGS_FP ""
#endif

namespace {

const char* versao() { return "1"; }

const char* flags_fp() { return OBIM_VISIB_FLAGS_FP; }

double somar(double a, double b) { return a + b; }

}  // namespace

NB_MODULE(_obimvisib, m) {
    m.def("versao", &versao);
    m.def("flags_fp", &flags_fp);
    m.def("somar", &somar);
}
