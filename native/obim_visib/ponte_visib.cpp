// SPDX-License-Identifier: AGPL-3.0-or-later
// Ponte Python/C++ minima (esqueleto N1) do modulo `_obimvisib`.
#ifdef __FAST_MATH__
#error "obimvisib proibe -ffast-math (__FAST_MATH__)"
#endif
#if defined(_MSC_VER) && defined(_M_FP_FAST)
#error "obimvisib proibe /fp:fast (_M_FP_FAST)"
#endif
#if defined(_MSC_VER) && !defined(_M_FP_PRECISE)
#error "obimvisib exige /fp:precise (_M_FP_PRECISE)"
#endif

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
