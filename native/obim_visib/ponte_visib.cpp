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
#include <nanobind/ndarray.h>

#include "recorte.h"

#include <cstddef>
#include <cstdint>
#include <vector>

#ifndef OBIM_VISIB_FLAGS_FP
#  define OBIM_VISIB_FLAGS_FP ""
#endif

namespace nb = nanobind;

namespace {

const char* versao() { return "1"; }

const char* flags_fp() { return OBIM_VISIB_FLAGS_FP; }

double somar(double a, double b) { return a + b; }

using Arr1R = nb::ndarray<nb::ro, nb::ndim<1>, nb::device::cpu>;
using Arr1D = nb::ndarray<const double, nb::ndim<1>, nb::device::cpu>;

template <typename T>
obim::visib::View1D<T> v1(const nb::ndarray<const T, nb::ndim<1>, nb::device::cpu>& arr) {
    return {arr.data(), static_cast<int64_t>(arr.shape(0)), arr.stride(0)};
}

template <typename T>
nb::object vetor_numpy(std::vector<T>&& v) {
    auto* dono = new std::vector<T>(std::move(v));
    nb::capsule limpa(dono, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
    size_t forma[1] = {dono->size()};
    return nb::cast(nb::ndarray<nb::numpy, T, nb::ndim<1>>(dono->data(), 1, forma, limpa));
}

template <typename EInt>
nb::tuple empacotar_intervalos(obim::visib::Intervalos<EInt>&& res) {
    return nb::make_tuple(
        vetor_numpy(std::move(res.he)),
        vetor_numpy(std::move(res.hlo)),
        vetor_numpy(std::move(res.hhi))
    );
}

nb::tuple py_unir_intervalos(Arr1R he_arr, Arr1D hlo_arr, Arr1D hhi_arr) {
    const auto dt = he_arr.dtype();
    const obim::visib::View1D<double> vlo = v1(hlo_arr);
    const obim::visib::View1D<double> vhi = v1(hhi_arr);
    const int64_t n = static_cast<int64_t>(he_arr.shape(0));
    const int64_t s0 = he_arr.stride(0);

    if (dt == nb::dtype<int64_t>()) {
        obim::visib::Intervalos<int64_t> res;
        {
            nb::gil_scoped_release solto;
            obim::visib::View1D<int64_t> vhe{static_cast<const int64_t*>(he_arr.data()), n, s0};
            res = obim::visib::unir_intervalos(vhe, vlo, vhi);
        }
        return empacotar_intervalos(std::move(res));
    }
    if (dt == nb::dtype<int32_t>()) {
        obim::visib::Intervalos<int32_t> res;
        {
            nb::gil_scoped_release solto;
            obim::visib::View1D<int32_t> vhe{static_cast<const int32_t*>(he_arr.data()), n, s0};
            res = obim::visib::unir_intervalos(vhe, vlo, vhi);
        }
        return empacotar_intervalos(std::move(res));
    }
    throw nb::type_error("He deve ter dtype int32 ou int64");
}

}  // namespace

NB_MODULE(_obimvisib, m) {
    m.def("versao", &versao);
    m.def("flags_fp", &flags_fp);
    m.def("somar", &somar);
    m.def("unir_intervalos", &py_unir_intervalos,
          nb::arg("He").noconvert(), nb::arg("Hlo").noconvert(), nb::arg("Hhi").noconvert());
}
