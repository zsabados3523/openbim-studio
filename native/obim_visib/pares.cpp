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

#include "pares.h"
#include "recorte_interno.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace obim::visib {
namespace {

constexpr int64_t kMaxTotalCels = 100'000'000;
constexpr int64_t kMaxCelLocal = 50'000'000;
constexpr double kMaxNsubD = 100'000'000.0;
constexpr int64_t kI64Min = std::numeric_limits<int64_t>::min();
constexpr int64_t kI64Max = std::numeric_limits<int64_t>::max();

struct TriCel { int64_t t, ix, iy; };

inline Intervalos<int64_t> finalizar_intervalos(Intervalos<int64_t>&& raw) {
    if (raw.he.size() <= 1) {
        if (raw.he.size() == 1) raw.hhi[0] = max_f(raw.hlo[0], raw.hhi[0]);
        return std::move(raw);
    }
    const int64_t n = static_cast<int64_t>(raw.he.size());
    return unir_intervalos(View1D<int64_t>{raw.he.data(), n, 1}, View1D<double>{raw.hlo.data(), n, 1}, View1D<double>{raw.hhi.data(), n, 1});
}

inline void emitir_tris_aresta(
    const ArestaCache& ac, std::vector<int64_t>& tris_e, const MalhaClipViews& mv,
    double tol_z, double d_eps, double eps, std::vector<ParLoHi>& buf_grupo, Intervalos<int64_t>& out
) {
    if (tris_e.empty()) return;
    std::sort(tris_e.begin(), tris_e.end());
    tris_e.erase(std::unique(tris_e.begin(), tris_e.end()), tris_e.end());
    buf_grupo.clear();
    for (int64_t t : tris_e) recortar_aresta_tri(ac, t, mv, tol_z, d_eps, eps, buf_grupo);
    emitir_grupo_aresta(ac.e, buf_grupo, out);
}

template <typename Fn>
inline int64_t prox_fatia(Fn&& w_at, int64_t i0, int64_t n, int64_t lim, int64_t* sum_out = nullptr) {
    int64_t sum = 0, i1 = i0;
    if (i1 < n) {
        const int64_t w0 = w_at(i1);
        if (w0 > lim) { sum = w0; ++i1; }
        else {
            while (i1 < n && sum <= lim - w_at(i1)) { sum += w_at(i1); ++i1; }
        }
    }
    if (sum_out) *sum_out = sum;
    return i1;
}

inline int64_t calc_nsub(double span, double step) {
    const double q = std::ceil(span / step);
    if (std::isnan(q) || q <= 1.0) return 1;
    if (!std::isfinite(q) || q > kMaxNsubD) {
        throw std::invalid_argument("numero de subsegmentos excede o limite");
    }
    return static_cast<int64_t>(q);
}

// Clampa coordenada para [0, dim - 1] sem UB em +inf/NaN (diverge de int64(inf) -> 0 no Python).
inline int64_t cel_clamp(double v, double mn, double g, int64_t dim) noexcept {
    const double f = std::floor((v - mn) / g);
    if (std::isnan(f) || f <= 0.0) return 0;
    const double hi = static_cast<double>(dim - 1);
    return (f >= hi) ? (dim - 1) : static_cast<int64_t>(f);
}

inline int64_t calc_span(int64_t lo, int64_t hi) {
    if (hi < lo) {
        if (static_cast<uint64_t>(lo) - static_cast<uint64_t>(hi) > 1ULL) {
            throw std::invalid_argument("intervalo de celula invalido");
        }
        return 0;
    }
    const uint64_t diff = static_cast<uint64_t>(hi) - static_cast<uint64_t>(lo);
    if (diff >= static_cast<uint64_t>(kI64Max)) {
        throw std::invalid_argument("estouro em largura ou altura de celula");
    }
    return static_cast<int64_t>(diff + 1ULL);
}

inline void check_cel_coord(int64_t x, int64_t y, int64_t nx) {
    bool ok_mul = true;
    if ((y == -1 && nx == kI64Min) || (nx == -1 && y == kI64Min)) {
        ok_mul = false;
    } else if (y > 0 && nx != 0) {
        ok_mul = (nx > 0) ? (y <= kI64Max / nx) : (nx >= kI64Min / y);
    } else if (y < 0 && nx != 0) {
        ok_mul = (nx > 0) ? (y >= kI64Min / nx) : (nx >= kI64Max / y);
    }
    if (!ok_mul) throw std::invalid_argument("estouro em indice de celula");
    const int64_t row = y * nx;
    if ((x > 0) ? (row > kI64Max - x) : (row < kI64Min - x)) {
        throw std::invalid_argument("estouro em indice de celula");
    }
}

}  // namespace

SubsegCelsOut subseg_cels(
    View2D<double> a, View2D<double> d, View1D<int64_t> nsub,
    double mn_x, double mn_y, double cg, int64_t Wc, int64_t Hc
) {
    if (a.n0 != d.n0 || a.n0 != nsub.n) throw std::invalid_argument("a, d e nsub devem ter o mesmo comprimento");
    if (a.n1 != 3 || d.n1 != 3) throw std::invalid_argument("a e d devem ter 3 colunas");
    if (Wc <= 0 || Hc <= 0 || !std::isfinite(cg) || cg <= 0.0 || !std::isfinite(mn_x) || !std::isfinite(mn_y)) {
        throw std::invalid_argument("parametros de grade invalidos");
    }

    int64_t total = 0;
    for (int64_t i = 0; i < nsub.n; ++i) {
        const int64_t n = nsub(i);
        if (n < 0) throw std::invalid_argument("nsub nao pode ser negativo");
        if (n > kI64Max - total || total + n > kMaxTotalCels) {
            throw std::invalid_argument("total de subsegmentos excede o limite");
        }
        total += n;
    }

    SubsegCelsOut out;
    out.total = total;
    if (total == 0) return out;

    const size_t sz = static_cast<size_t>(total);
    if (sz > std::numeric_limits<size_t>::max() / (3 * sizeof(double))) {
        throw std::invalid_argument("estouro na alocacao de subsegmentos");
    }
    out.s_l.resize(sz); out.t0_s.resize(sz); out.t1_s.resize(sz);
    out.sa_flat.resize(sz * 3); out.sb_flat.resize(sz * 3);
    out.sx0.resize(sz); out.sx1.resize(sz); out.sy0.resize(sz); out.sy1.resize(sz);

    size_t pos = 0;
    for (int64_t i = 0; i < nsub.n; ++i) {
        const int64_t n = nsub(i);
        if (n == 0) continue;
        const double ax = a(i, 0), ay = a(i, 1), az = a(i, 2);
        const double dx = d(i, 0), dy = d(i, 1), dz = d(i, 2);
        const double dn = static_cast<double>(n);
        for (int64_t k = 0; k < n; ++k) {
            const double t0 = static_cast<double>(k) / dn, t1 = static_cast<double>(k + 1) / dn;
            const double sa0 = ax + t0 * dx, sa1 = ay + t0 * dy, sa2 = az + t0 * dz;
            const double sb0 = ax + t1 * dx, sb1 = ay + t1 * dy, sb2 = az + t1 * dz;
            out.s_l[pos] = i; out.t0_s[pos] = t0; out.t1_s[pos] = t1;
            const size_t p3 = pos * 3;
            out.sa_flat[p3] = sa0; out.sa_flat[p3 + 1] = sa1; out.sa_flat[p3 + 2] = sa2;
            out.sb_flat[p3] = sb0; out.sb_flat[p3 + 1] = sb1; out.sb_flat[p3 + 2] = sb2;
            out.sx0[pos] = cel_clamp(min_f(sa0, sb0), mn_x, cg, Wc);
            out.sx1[pos] = cel_clamp(max_f(sa0, sb0), mn_x, cg, Wc);
            out.sy0[pos] = cel_clamp(min_f(sa1, sb1), mn_y, cg, Hc);
            out.sy1[pos] = cel_clamp(max_f(sa1, sb1), mn_y, cg, Hc);
            ++pos;
        }
    }
    return out;
}

ExpandirCelsOut expandir_celulas(
    View1D<int64_t> ix0, View1D<int64_t> ix1,
    View1D<int64_t> iy0, View1D<int64_t> iy1, int64_t nx
) {
    if (ix0.n != ix1.n || ix0.n != iy0.n || ix0.n != iy1.n) {
        throw std::invalid_argument("ix0, ix1, iy0 e iy1 devem ter o mesmo comprimento");
    }

    int64_t total = 0;
    for (int64_t i = 0; i < ix0.n; ++i) {
        const int64_t x0 = ix0(i), x1 = ix1(i), y0 = iy0(i), y1 = iy1(i);
        const int64_t w = calc_span(x0, x1);
        const int64_t h = calc_span(y0, y1);
        if (w == 0 || h == 0) continue;
        if (h > kI64Max / w) throw std::invalid_argument("estouro no tamanho da caixa de celulas");
        const int64_t prod = w * h;
        if (prod > kI64Max - total || total + prod > kMaxTotalCels) {
            throw std::invalid_argument("total de celulas excede o limite");
        }
        total += prod;
        for (int64_t y : {y0, y1}) {
            for (int64_t x : {x0, x1}) check_cel_coord(x, y, nx);
        }
    }

    ExpandirCelsOut out;
    if (total == 0) return out;
    out.obj.resize(static_cast<size_t>(total));
    out.cel.resize(static_cast<size_t>(total));

    size_t pos = 0;
    for (int64_t i = 0; i < ix0.n; ++i) {
        const int64_t x0 = ix0(i), x1 = ix1(i), y0 = iy0(i), y1 = iy1(i);
        if (x1 < x0 || y1 < y0) continue;
        const int64_t w = static_cast<int64_t>(static_cast<uint64_t>(x1) - static_cast<uint64_t>(x0)) + 1;
        const int64_t h = static_cast<int64_t>(static_cast<uint64_t>(y1) - static_cast<uint64_t>(y0)) + 1;
        for (int64_t dy = 0; dy < h; ++dy) {
            const int64_t row = (y0 + dy) * nx;
            for (int64_t dx = 0; dx < w; ++dx) {
                out.obj[pos] = i;
                out.cel[pos] = row + (x0 + dx);
                ++pos;
            }
        }
    }
    return out;
}

FiltrarArestasZOut filtrar_arestas_mapa_z(
    View2D<double> a, View2D<double> d, View2D<double> z_full,
    double mn_x, double mn_y, double g, double tol_z
) {
    if (a.n0 != d.n0) throw std::invalid_argument("a e d devem ter o mesmo comprimento");
    if (a.n1 != 3 || d.n1 != 3) throw std::invalid_argument("a e d devem ter 3 colunas");
    if (z_full.n0 <= 0 || z_full.n1 <= 0) throw std::invalid_argument("z_full deve ser nao-vazio");
    if (!std::isfinite(g) || g <= 0.0 || !std::isfinite(mn_x) || !std::isfinite(mn_y)) {
        throw std::invalid_argument("parametros de grade invalidos");
    }
    const double step_g = 0.999 * g;
    if (!(step_g > 0.0)) throw std::invalid_argument("passo de grade invalido");

    const int64_t H = z_full.n0, W = z_full.n1;
    FiltrarArestasZOut out;
    out.ek_idx.reserve(static_cast<size_t>(a.n0));

    for (int64_t e = 0; e < a.n0; ++e) {
        const double ax = a(e, 0), ay = a(e, 1), az = a(e, 2);
        const double dx = d(e, 0), dy = d(e, 1), dz = d(e, 2);
        const int64_t nsub = calc_nsub(max_f(std::abs(dx), std::abs(dy)), step_g);
        const double dn = static_cast<double>(nsub);
        bool edge_kept = false, in_hid = false;
        double t0_hid = 0.0;

        for (int64_t k = 0; k < nsub; ++k) {
            const double t0 = static_cast<double>(k) / dn;
            const double t1 = static_cast<double>(k + 1) / dn;
            const double sa0 = ax + t0 * dx, sa1 = ay + t0 * dy, sa2 = az + t0 * dz;
            const double sb0 = ax + t1 * dx, sb1 = ay + t1 * dy, sb2 = az + t1 * dz;
            const int64_t sx0 = cel_clamp(min_f(sa0, sb0), mn_x, g, W);
            const int64_t sx1 = cel_clamp(max_f(sa0, sb0), mn_x, g, W);
            const int64_t sy0 = cel_clamp(min_f(sa1, sb1), mn_y, g, H);
            const int64_t sy1 = cel_clamp(max_f(sa1, sb1), mn_y, g, H);
            const double z_min_4 = min_f(
                min_f(z_full(sy0, sx0), z_full(sy0, sx1)),
                min_f(z_full(sy1, sx0), z_full(sy1, sx1))
            );
            if (max_f(sa2, sb2) >= z_min_4 - tol_z) {
                edge_kept = true;
                if (in_hid) {
                    out.hid.he.push_back(e);
                    out.hid.hlo.push_back(t0_hid);
                    out.hid.hhi.push_back(t0);
                    in_hid = false;
                }
            } else if (!in_hid) {
                t0_hid = t0;
                in_hid = true;
            }
        }
        if (in_hid) {
            out.hid.he.push_back(e);
            out.hid.hlo.push_back(t0_hid);
            out.hid.hhi.push_back(1.0);
        }
        if (edge_kept) out.ek_idx.push_back(e);
    }
    return out;
}

ProcessarCelsOut processar_celulas_e_recortar(
    View1D<int64_t> t_s, View1D<int64_t> iy_s, View1D<int64_t> ix0_s, View1D<int64_t> ix1_s,
    View1D<int64_t> ek_idx, View1D<double> zf_flat, bool filtrar_zf,
    double mn_x, double mn_y, double cg, int64_t Wc, int64_t Hc,
    const MalhaClipViews& mv, double tol_z, double d_eps, bool usar_subgrade,
    int64_t lim_t_bloco, int64_t lim_e_bloco, int64_t lim_denso_pares
) {
    if (t_s.n != iy_s.n || t_s.n != ix0_s.n || t_s.n != ix1_s.n)
        throw std::invalid_argument("t_s, iy_s, ix0_s e ix1_s devem ter o mesmo comprimento");
    if (Wc <= 0 || Hc <= 0 || Wc > kI64Max / Hc || !std::isfinite(cg) || cg <= 0.0 ||
        !std::isfinite(mn_x) || !std::isfinite(mn_y) || lim_t_bloco <= 0 || lim_e_bloco <= 0)
        throw std::invalid_argument("parametros de grade ou bloco invalidos");
    const double step_c = 0.999 * cg;
    if (!(step_c > 0.0)) throw std::invalid_argument("passo de grade invalido");
    validar_malha_views(mv);
    if (filtrar_zf && zf_flat.n < Wc * Hc) throw std::invalid_argument("zf_flat menor que Wc * Hc");

    const int64_t n_spans = t_s.n, n_ek = ek_idx.n, ne = mv.a.n0, nt = mv.A.n0;
    std::vector<int64_t> nsub_c(static_cast<size_t>(n_ek)), w_s(static_cast<size_t>(n_spans));
    for (int64_t ie = 0; ie < n_ek; ++ie) {
        const int64_t e = ek_idx(ie);
        if (e < 0 || e >= ne) throw std::out_of_range("indice de aresta fora dos limites");
        nsub_c[static_cast<size_t>(ie)] = calc_nsub(max_f(std::abs(mv.d(e, 0)), std::abs(mv.d(e, 1))), step_c);
    }
    for (int64_t si = 0; si < n_spans; ++si) {
        const int64_t t = t_s(si), x0 = ix0_s(si), x1 = ix1_s(si), iy = iy_s(si);
        if (t < 0 || t >= nt) throw std::out_of_range("indice de triangulo fora dos limites");
        const int64_t w = calc_span(x0, x1);
        if (w > 0 && (iy < 0 || iy >= Hc || x0 < 0 || x1 >= Wc))
            throw std::out_of_range("coordenada de celula fora dos limites");
        w_s[static_cast<size_t>(si)] = w;
    }
    if (n_spans == 0 || n_ek == 0) return {Intervalos<int64_t>{}, n_spans, n_spans};

    const double eps = std::abs(d_eps);
    Intervalos<int64_t> out;
    std::vector<TriCel> buf_tc;
    std::vector<int64_t> cont, ini_cel, pos_cel, tri_por_cel, cels_e, tris_e;
    std::vector<double> cell_tzmax;
    std::vector<ParLoHi> buf_grupo;
    cels_e.reserve(64); tris_e.reserve(256); buf_grupo.reserve(64);

    int64_t t0 = 0;
    while (t0 < n_spans) {
        int64_t sum_w = 0;
        const int64_t t1 = prox_fatia([&](int64_t i) { return w_s[static_cast<size_t>(i)]; }, t0, n_spans, lim_t_bloco, &sum_w);
        const size_t mark = out.he.size();
        buf_tc.clear();
        buf_tc.reserve(std::min<size_t>(static_cast<size_t>(sum_w), 4'000'000));
        int64_t bx0 = kI64Max, bx1 = kI64Min, by0 = kI64Max, by1 = kI64Min;
        for (int64_t si = t0; si < t1; ++si) {
            const int64_t x0 = ix0_s(si), x1 = ix1_s(si);
            if (x1 < x0) continue;
            const int64_t t = t_s(si), iy = iy_s(si), row_glob = iy * Wc;
            const double tzm = mv.tzmax(t);
            for (int64_t ix = x0; ix <= x1; ++ix) {
                if (filtrar_zf && !(tzm >= zf_flat(row_glob + ix) - 1e-9)) continue;
                buf_tc.push_back({t, ix, iy});
                bx0 = std::min(bx0, ix); bx1 = std::max(bx1, ix);
                by0 = std::min(by0, iy); by1 = std::max(by1, iy);
            }
        }
        if (buf_tc.empty()) { t0 = t1; continue; }

        const int64_t Wl = bx1 - bx0 + 1, Hl = by1 - by0 + 1, ncel_l = Wl * Hl;
        if (ncel_l > kMaxCelLocal) throw std::invalid_argument("grade local excede o limite");
        cont.assign(static_cast<size_t>(ncel_l), 0);
        cell_tzmax.assign(static_cast<size_t>(ncel_l), -std::numeric_limits<double>::infinity());
        for (const auto& tc : buf_tc) {
            const size_t c = static_cast<size_t>((tc.iy - by0) * Wl + (tc.ix - bx0));
            cont[c] += 1;
            cell_tzmax[c] = max_f(cell_tzmax[c], mv.tzmax(tc.t));
        }
        ini_cel.resize(static_cast<size_t>(ncel_l));
        int64_t acum = 0;
        bool tem_cel_densa = false;
        for (size_t c = 0; c < static_cast<size_t>(ncel_l); ++c) {
            const int64_t cnt = cont[c];
            if (cnt >= 128) tem_cel_densa = true;
            ini_cel[c] = acum;
            acum += cnt;
        }
        pos_cel = ini_cel;
        tri_por_cel.resize(buf_tc.size());
        for (const auto& tc : buf_tc) {
            const size_t c = static_cast<size_t>((tc.iy - by0) * Wl + (tc.ix - bx0));
            tri_por_cel[static_cast<size_t>(pos_cel[c]++)] = tc.t;
        }

        const bool checar_densa = usar_subgrade && tem_cel_densa;
        for (int64_t e0 = 0, e1; e0 < n_ek; e0 = e1) {
            e1 = checar_densa ? prox_fatia([&](int64_t i) { return nsub_c[static_cast<size_t>(i)]; }, e0, n_ek, lim_e_bloco) : n_ek;
            int64_t dense_pair_sum = 0;
            for (int64_t ie = e0; ie < e1; ++ie) {
                const int64_t e = ek_idx(ie), nsub = nsub_c[static_cast<size_t>(ie)];
                const ArestaCache ac = carregar_aresta(e, mv);
                const double dn = static_cast<double>(nsub);
                cels_e.clear();
                for (int64_t k = 0; k < nsub; ++k) {
                    const double kt0 = static_cast<double>(k) / dn, kt1 = static_cast<double>(k + 1) / dn;
                    const double sa0 = ac.p0x + kt0 * ac.dx, sa1 = ac.p0y + kt0 * ac.dy, sa2 = ac.a_z + kt0 * ac.dz;
                    const double sb0 = ac.p0x + kt1 * ac.dx, sb1 = ac.p0y + kt1 * ac.dy, sb2 = ac.a_z + kt1 * ac.dz;
                    const int64_t sx0 = std::max(cel_clamp(min_f(sa0, sb0), mn_x, cg, Wc), bx0);
                    const int64_t sx1 = std::min(cel_clamp(max_f(sa0, sb0), mn_x, cg, Wc), bx1);
                    const int64_t sy0 = std::max(cel_clamp(min_f(sa1, sb1), mn_y, cg, Hc), by0);
                    const int64_t sy1 = std::min(cel_clamp(max_f(sa1, sb1), mn_y, cg, Hc), by1);
                    if (sx1 < sx0 || sy1 < sy0) continue;
                    const double zmin_sub = min_f(sa2, sb2);
                    for (int64_t cy = sy0; cy <= sy1; ++cy) {
                        const int64_t row = (cy - by0) * Wl;
                        for (int64_t cx = sx0; cx <= sx1; ++cx) {
                            const int64_t c = row + (cx - bx0);
                            if (cont[static_cast<size_t>(c)] > 0 && cell_tzmax[static_cast<size_t>(c)] > zmin_sub + tol_z) cels_e.push_back(c);
                        }
                    }
                }
                if (cels_e.empty()) continue;
                std::sort(cels_e.begin(), cels_e.end());
                cels_e.erase(std::unique(cels_e.begin(), cels_e.end()), cels_e.end());
                tris_e.clear();
                for (int64_t c : cels_e) {
                    const int64_t cnt = cont[static_cast<size_t>(c)];
                    if (cnt == 0) continue;
                    if (checar_densa && cnt >= 128) {
                        dense_pair_sum = (cnt > kI64Max - dense_pair_sum) ? kI64Max : (dense_pair_sum + cnt);
                        if (dense_pair_sum >= lim_denso_pares) {
                            out.he.resize(mark); out.hlo.resize(mark); out.hhi.resize(mark);
                            return {finalizar_intervalos(std::move(out)), t0, t1};
                        }
                    }
                    const int64_t beg = ini_cel[static_cast<size_t>(c)], end = beg + cnt;
                    for (int64_t idx = beg; idx < end; ++idx) {
                        const int64_t t = tri_por_cel[static_cast<size_t>(idx)];
                        if (passa_aabb_z(ac, t, mv, tol_z)) tris_e.push_back(t);
                    }
                }
                emitir_tris_aresta(ac, tris_e, mv, tol_z, d_eps, eps, buf_grupo, out);
            }
        }
        t0 = t1;
    }
    return {finalizar_intervalos(std::move(out)), n_spans, n_spans};
}

}  // namespace obim::visib
