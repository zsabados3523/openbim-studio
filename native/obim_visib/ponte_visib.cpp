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
using Arr2D = nb::ndarray<const double, nb::ndim<2>, nb::device::cpu>;
using Arr1I = nb::ndarray<const int64_t, nb::ndim<1>, nb::device::cpu>;
using Arr2I = nb::ndarray<const int64_t, nb::ndim<2>, nb::device::cpu>;

template <typename T>
obim::visib::View1D<T> v1(const nb::ndarray<const T, nb::ndim<1>, nb::device::cpu>& arr) {
    return {arr.data(), static_cast<int64_t>(arr.shape(0)), arr.stride(0)};
}

template <typename T>
obim::visib::View2D<T> v2(const nb::ndarray<const T, nb::ndim<2>, nb::device::cpu>& arr) {
    return {
        arr.data(),
        static_cast<int64_t>(arr.shape(0)),
        static_cast<int64_t>(arr.shape(1)),
        arr.stride(0),
        arr.stride(1),
    };
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

nb::tuple py_filtrar_e_recortar(
    Arr1I pe, Arr1I pt,
    Arr2D a, Arr2D b, Arr2D d,
    Arr1I ea, Arr1I eb, Arr2I tv,
    Arr2D A, Arr1D gx, Arr1D gy,
    Arr2D nx_, Arr2D ny_, Arr2D cc_,
    Arr1D tx0, Arr1D tx1, Arr1D ty0, Arr1D ty1, Arr1D tzmax,
    Arr1D ex0, Arr1D ex1, Arr1D ey0, Arr1D ey1, Arr1D ezmin,
    int64_t nt_all, double tol_z, double d_eps
) {
    obim::visib::Intervalos<int64_t> res;
    {
        nb::gil_scoped_release solto;
        res = obim::visib::filtrar_e_recortar(
            v1(pe), v1(pt),
            v2(a), v2(b), v2(d),
            v1(ea), v1(eb), v2(tv),
            v2(A), v1(gx), v1(gy),
            v2(nx_), v2(ny_), v2(cc_),
            v1(tx0), v1(tx1), v1(ty0), v1(ty1), v1(tzmax),
            v1(ex0), v1(ex1), v1(ey0), v1(ey1), v1(ezmin),
            nt_all, tol_z, d_eps
        );
    }
    return empacotar_intervalos(std::move(res));
}

}  // namespace

NB_MODULE(_obimvisib, m) {
    m.def("versao", &versao);
    m.def("flags_fp", &flags_fp);
    m.def("somar", &somar);
    m.def("unir_intervalos", &py_unir_intervalos,
          nb::arg("He").noconvert(), nb::arg("Hlo").noconvert(), nb::arg("Hhi").noconvert());
    m.def("filtrar_e_recortar", &py_filtrar_e_recortar,
          nb::arg("pe").noconvert(), nb::arg("pt").noconvert(),
          nb::arg("a").noconvert(), nb::arg("b").noconvert(), nb::arg("d").noconvert(),
          nb::arg("ea").noconvert(), nb::arg("eb").noconvert(), nb::arg("tv").noconvert(),
          nb::arg("A").noconvert(), nb::arg("gx").noconvert(), nb::arg("gy").noconvert(),
          nb::arg("nx_").noconvert(), nb::arg("ny_").noconvert(), nb::arg("cc_").noconvert(),
          nb::arg("tx0").noconvert(), nb::arg("tx1").noconvert(), nb::arg("ty0").noconvert(),
          nb::arg("ty1").noconvert(), nb::arg("tzmax").noconvert(),
          nb::arg("ex0").noconvert(), nb::arg("ex1").noconvert(), nb::arg("ey0").noconvert(),
          nb::arg("ey1").noconvert(), nb::arg("ezmin").noconvert(),
          nb::arg("nt_all"), nb::arg("tol_z"), nb::arg("d_eps"));
}
