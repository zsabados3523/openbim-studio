// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "recorte_interno.h"

#include <cstdint>
#include <vector>

namespace obim::visib {

struct SubsegCelsOut {
    std::vector<int64_t> s_l, sx0, sx1, sy0, sy1;
    std::vector<double> t0_s, t1_s, sa_flat, sb_flat;
    int64_t total = 0;
};

struct ExpandirCelsOut {
    std::vector<int64_t> obj, cel;
};

struct FiltrarArestasZOut {
    std::vector<int64_t> ek_idx;
    Intervalos<int64_t> hid;
};

struct ProcessarCelsOut {
    Intervalos<int64_t> iv;
    int64_t t_ini_py = 0;
    int64_t t_fim_py = 0;
};

SubsegCelsOut subseg_cels(
    View2D<double> a, View2D<double> d, View1D<int64_t> nsub,
    double mn_x, double mn_y, double cg, int64_t Wc, int64_t Hc
);

ExpandirCelsOut expandir_celulas(
    View1D<int64_t> ix0, View1D<int64_t> ix1,
    View1D<int64_t> iy0, View1D<int64_t> iy1, int64_t nx
);

FiltrarArestasZOut filtrar_arestas_mapa_z(
    View2D<double> a, View2D<double> d, View2D<double> z_full,
    double mn_x, double mn_y, double g, double tol_z
);

ProcessarCelsOut processar_celulas_e_recortar(
    View1D<int64_t> t_s, View1D<int64_t> iy_s, View1D<int64_t> ix0_s, View1D<int64_t> ix1_s,
    View1D<int64_t> ek_idx, View1D<double> zf_flat, bool filtrar_zf,
    double mn_x, double mn_y, double cg, int64_t Wc, int64_t Hc,
    const MalhaClipViews& mv, double tol_z, double d_eps, bool usar_subgrade,
    int64_t lim_t_bloco = 2000000, int64_t lim_e_bloco = 400000, int64_t lim_denso_pares = 20000000
);

}  // namespace obim::visib
