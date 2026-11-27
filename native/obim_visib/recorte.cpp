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

// Semantica de np.maximum: preserva bits do NaN de entrada; em empate (+0/-0) devolve b.
// Limitacao: em n grande com empates +0/-0 (ou NaNs distintos) em hi, o resultado
// do Python depende do np.argsort instavel de Hhi e pode divergir nos bits.
inline double max_f(double a, double b) noexcept {
    if (std::isnan(a)) {
        return a;
    }
    if (std::isnan(b)) {
        return b;
    }
    return (a > b) ? a : b;
}

// Semantica de np.minimum: preserva bits do NaN de entrada; em empate (+0/-0) devolve b.
inline double min_f(double a, double b) noexcept {
    if (std::isnan(a)) return a;
    if (std::isnan(b)) return b;
    return (a < b) ? a : b;
}

// No maximo acumulado por grupo, o NaN mais recente (b) prevalece sobre h.
inline double max_acum(double h, double b) noexcept {
    if (std::isnan(b)) {
        return b;
    }
    if (std::isnan(h)) {
        return h;
    }
    return (h > b) ? h : b;
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
                hi_cur = max_acum(hi_cur, hi);
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
            hi_cur = max_acum(hi_cur, it.hi);
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
    auto out = unir_vetores(
        he.ptr, he.s0,
        hlo.ptr, hlo.s0,
        hhi.ptr, hhi.s0,
        static_cast<size_t>(he.n)
    );
    out.he.shrink_to_fit();
    out.hlo.shrink_to_fit();
    out.hhi.shrink_to_fit();
    return out;
}

template Intervalos<int32_t> unir_intervalos<int32_t>(View1D<int32_t>, View1D<double>, View1D<double>);
template Intervalos<int64_t> unir_intervalos<int64_t>(View1D<int64_t>, View1D<double>, View1D<double>);

namespace {

inline void aplicar_corte(
    double s, double r, double& lo, double& hi, double fail_val, bool eq_fail
) noexcept {
    if (s > 1e-12) {
        lo = max_f(lo, r / s);
    } else if (s < -1e-12) {
        hi = min_f(hi, r / s);
    } else if (eq_fail ? (r >= 0.0) : (r > 0.0)) {
        hi = fail_val;
    }
}

struct ParLoHi {
    double lo;
    double hi;
};

void emitir_grupo_aresta(int64_t e, std::vector<ParLoHi>& buf, Intervalos<int64_t>& out) {
    const size_t m = buf.size();
    if (m == 0) return;
    if (m > 1) {
        bool ord = true;
        for (size_t i = 1; i < m && ord; ++i) ord = !lo_less(buf[i].lo, buf[i - 1].lo);
        if (!ord) {
            std::stable_sort(buf.begin(), buf.end(), [](const ParLoHi& x, const ParLoHi& y) noexcept {
                return lo_less(x.lo, y.lo);
            });
        }
    }
    double lo_ini = buf[0].lo;
    double hi_cur = buf[0].hi;
    for (size_t k = 1; k < m; ++k) {
        if (buf[k].lo > hi_cur + 1e-9) {
            out.he.push_back(e);
            out.hlo.push_back(lo_ini);
            out.hhi.push_back(max_f(lo_ini, hi_cur));
            lo_ini = buf[k].lo;
            hi_cur = buf[k].hi;
        } else {
            hi_cur = max_acum(hi_cur, buf[k].hi);
        }
    }
    out.he.push_back(e);
    out.hlo.push_back(lo_ini);
    out.hhi.push_back(max_f(lo_ini, hi_cur));
    buf.clear();
}

struct MalhaClipViews {
    View2D<double> a, b, d;
    View1D<int64_t> ea, eb;
    View2D<int64_t> tv;
    View2D<double> A;
    View1D<double> gx, gy;
    View2D<double> nx_, ny_, cc_;
    View1D<double> tx0, tx1, ty0, ty1, tzmax;
    View1D<double> ex0, ex1, ey0, ey1, ezmin;
};

struct ArestaCache {
    int64_t e;
    double p0x, p0y, a_z, bx, by, bz, dx, dy, dz, len2d;
    int64_t eav, ebv;
};

inline ArestaCache carregar_aresta(int64_t e, const MalhaClipViews& mv) noexcept {
    const double dx = mv.d(e, 0);
    const double dy = mv.d(e, 1);
    return {
        e, mv.a(e, 0), mv.a(e, 1), mv.a(e, 2),
        mv.b(e, 0), mv.b(e, 1), mv.b(e, 2),
        dx, dy, mv.d(e, 2), std::hypot(dx, dy), mv.ea(e), mv.eb(e),
    };
}

inline void recortar_aresta_tri(
    const ArestaCache& ac, int64_t t, const MalhaClipViews& mv,
    double tol_z, double d_eps, double eps, std::vector<ParLoHi>& buf_grupo
) {
    const int64_t tv0 = mv.tv(t, 0), tv1 = mv.tv(t, 1), tv2 = mv.tv(t, 2);
    const bool a_sh = (ac.eav == tv0) || (ac.eav == tv1) || (ac.eav == tv2);
    const bool b_sh = (ac.ebv == tv0) || (ac.ebv == tv1) || (ac.ebv == tv2);
    const double Ax = mv.A(t, 0), Ay = mv.A(t, 1), Az = mv.A(t, 2);
    const double gxt = mv.gx(t), gyt = mv.gy(t);

    if (a_sh || b_sh) {
        if (a_sh && ac.bz >= Az + gxt * (ac.bx - Ax) + gyt * (ac.by - Ay) - tol_z) return;
        if (b_sh && ac.a_z >= Az + gxt * (ac.p0x - Ax) + gyt * (ac.p0y - Ay) - tol_z) return;
    }

    double lo = 0.0, hi = 1.0;
    aplicar_corte(ac.dx, mv.tx0(t) - eps - ac.p0x, lo, hi, -1.0, false);
    aplicar_corte(-ac.dx, ac.p0x - mv.tx1(t) - eps, lo, hi, -1.0, false);
    aplicar_corte(ac.dy, mv.ty0(t) - eps - ac.p0y, lo, hi, -1.0, false);
    aplicar_corte(-ac.dy, ac.p0y - mv.ty1(t) - eps, lo, hi, -1.0, false);
    if (!((hi - lo) * ac.len2d > 1e-5)) return;

    for (int ii = 0; ii < 3; ++ii) {
        const double nx_i = mv.nx_(t, ii), ny_i = mv.ny_(t, ii);
        aplicar_corte(
            nx_i * ac.dx + ny_i * ac.dy,
            d_eps - (nx_i * ac.p0x + ny_i * ac.p0y + mv.cc_(t, ii)),
            lo, hi, -1.0, false
        );
    }
    if (!((hi - lo) * ac.len2d > 1e-5)) return;

    const double G0 = Az + gxt * (ac.p0x - Ax) + gyt * (ac.p0y - Ay) - ac.a_z - tol_z;
    aplicar_corte(gxt * ac.dx + gyt * ac.dy - ac.dz, -G0, lo, hi, -1.0, true);
    if ((hi - lo) * ac.len2d > 1e-5) buf_grupo.push_back({lo, hi});
}

}  // namespace

Intervalos<int64_t> filtrar_e_recortar(
    View1D<int64_t> pe, View1D<int64_t> pt,
    View2D<double> a, View2D<double> b, View2D<double> d,
    View1D<int64_t> ea, View1D<int64_t> eb, View2D<int64_t> tv,
    View2D<double> A, View1D<double> gx, View1D<double> gy,
    View2D<double> nx_, View2D<double> ny_, View2D<double> cc_,
    View1D<double> tx0, View1D<double> tx1, View1D<double> ty0, View1D<double> ty1, View1D<double> tzmax,
    View1D<double> ex0, View1D<double> ex1, View1D<double> ey0, View1D<double> ey1, View1D<double> ezmin,
    int64_t nt_all, double tol_z, double d_eps
) {
    Intervalos<int64_t> out;
    if (pe.n != pt.n) throw std::invalid_argument("pe e pt devem ter o mesmo comprimento");
    const int64_t ne = a.n0, nt = A.n0;
    if (a.n1 != 3 || b.n0 != ne || b.n1 != 3 || d.n0 != ne || d.n1 != 3 ||
        ea.n != ne || eb.n != ne || ex0.n != ne || ex1.n != ne ||
        ey0.n != ne || ey1.n != ne || ezmin.n != ne ||
        tv.n0 != nt || tv.n1 != 3 || A.n1 != 3 || gx.n != nt || gy.n != nt ||
        nx_.n0 != nt || nx_.n1 != 3 || ny_.n0 != nt || ny_.n1 != 3 ||
        cc_.n0 != nt || cc_.n1 != 3 || tx0.n != nt || tx1.n != nt ||
        ty0.n != nt || ty1.n != nt || tzmax.n != nt) {
        throw std::invalid_argument("dimensoes inconsistentes para arrays de entrada");
    }
    if (pe.n == 0 || nt_all <= 0) return out;
    if (nt_all < nt) {
        throw std::invalid_argument("nt_all deve ser maior ou igual ao numero de triangulos");
    }
    if (ne > 0 && nt > 0 && (ne - 1) > (std::numeric_limits<int64_t>::max() - (nt - 1)) / nt_all) {
        throw std::invalid_argument("chave e*nt_all+t estoura int64");
    }

    std::vector<int64_t> chaves;
    chaves.reserve(static_cast<size_t>(pe.n));
    for (int64_t k = 0; k < pe.n; ++k) {
        const int64_t e = pe(k), t = pt(k);
        if (e < 0 || e >= ne || t < 0 || t >= nt) {
            throw std::out_of_range("indice de aresta ou triangulo fora dos limites");
        }
        if (tzmax(t) > ezmin(e) + tol_z &&
            tx1(t) >= ex0(e) && tx0(t) <= ex1(e) &&
            ty1(t) >= ey0(e) && ty0(t) <= ey1(e)) {
            chaves.push_back(e * nt_all + t);
        }
    }
    if (chaves.empty()) return out;

    std::sort(chaves.begin(), chaves.end());
    chaves.erase(std::unique(chaves.begin(), chaves.end()), chaves.end());

    const MalhaClipViews mv{
        a, b, d, ea, eb, tv, A, gx, gy, nx_, ny_, cc_,
        tx0, tx1, ty0, ty1, tzmax, ex0, ex1, ey0, ey1, ezmin
    };
    const double eps = std::abs(d_eps);
    const size_t cap = std::min<size_t>(chaves.size(), 4096);
    out.he.reserve(cap);
    out.hlo.reserve(cap);
    out.hhi.reserve(cap);

    std::vector<ParLoHi> buf_grupo;
    buf_grupo.reserve(64);
    ArestaCache ac{};
    ac.e = -1;
    for (int64_t ch : chaves) {
        const int64_t e = ch / nt_all, t = ch % nt_all;
        if (e != ac.e) {
            if (!buf_grupo.empty()) emitir_grupo_aresta(ac.e, buf_grupo, out);
            ac = carregar_aresta(e, mv);
        }
        recortar_aresta_tri(ac, t, mv, tol_z, d_eps, eps, buf_grupo);
    }
    if (!buf_grupo.empty()) emitir_grupo_aresta(ac.e, buf_grupo, out);
    out.he.shrink_to_fit();
    out.hlo.shrink_to_fit();
    out.hhi.shrink_to_fit();
    return out;
}

}  // namespace obim::visib
