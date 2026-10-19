// SPDX-License-Identifier: AGPL-3.0-or-later
// Ponte nanobind da viewport (S04-T14b; antes misturada em viewport.cpp, cena.cpp e malha.cpp). Só ADAPTA tipos: o motor, a cena e a seleção são C++ puro
// (nucleo/). Posse: o Python é o dono; os arrays do numpy são EMPRESTADOS (`Emprestado` os prende até o retorno) e o C++ nunca guarda o endereço.
// O bloqueio do interpretador é solto em torno das chamadas ao núcleo (que nunca toca em objeto Python); erros do núcleo: std::invalid_argument = ValueError.
#include <nanobind/nanobind.h>
#include <nanobind/eval.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>
#include "nucleo/motor.h"
namespace nb = nanobind;
using namespace obim;

namespace {
// Confere dtype exato, 1 dimensão e memória contígua; devolve ponteiro e quantidade de elementos. Só TypeError/ValueError.
Vista vetor(nb::handle a, nb::handle ref, const char* nome) {
  if (!nb::hasattr(a, "dtype") || !nb::hasattr(a, "flags") || !nb::hasattr(a, "ctypes"))
    throw nb::type_error((std::string(nome) + ": esperado um array do numpy").c_str());
  if (!a.attr("dtype").equal(ref)) throw nb::type_error((std::string(nome) + ": dtype diferente do formato do carregador").c_str());
  if (nb::cast<int>(a.attr("ndim")) != 1) throw nb::value_error((std::string(nome) + ": esperado vetor de 1 dimensão").c_str());
  if (!nb::cast<bool>(a.attr("flags").attr("c_contiguous"))) throw nb::value_error((std::string(nome) + ": memória não contígua").c_str());
  return {reinterpret_cast<const unsigned char*>(nb::cast<uintptr_t>(a.attr("ctypes").attr("data"))), nb::cast<size_t>(a.attr("size"))};
}

template <class T> nb::object numpy_de(std::vector<T>&& v, size_t cols) {  // cols == 0: vetor de 1 dimensão; senão (n, cols); o numpy fica dono
  auto* dono = new std::vector<T>(std::move(v));
  nb::capsule limpa(dono, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
  size_t forma[2] = {cols ? dono->size() / cols : dono->size(), cols};
  return nb::cast(nb::ndarray<nb::numpy, T>(dono->data(), cols ? 2 : 1, forma, limpa));
}

struct Emprestado { nb::object va, ia, oo; LoteBruto b; };  // referências próprias: os arrays não morrem durante a chamada (nem sem o bloqueio)

Emprestado emprestar_lote(nb::handle lote) {  // LoteMalha (Python) -> LoteBruto (C++ puro); a validação de dtype/contiguidade é toda daqui
  for (const char* c : {"vertices", "indices"})
    if (!nb::hasattr(lote, c)) throw nb::type_error("lote sem vertices/indices (esperado LoteMalha)");
  struct Tipos { nb::object vert, ind, obj; };  // montados UMA vez (achado 10); vazam de propósito (nunca destruídos depois do Python)
  static const Tipos* t = [] {
    nb::object dt = nb::module_::import_("numpy").attr("dtype");
    return new Tipos{dt(nb::eval("[('pos','<f4',(3,)),('normal','<f4',(3,)),('cor','u1',(4,))]")), dt("<u4"),
                     dt(nb::eval("[('id_step','<i4'),('guid','S22'),('primeiro_indice','<u4'),('n_indices','<u4'),('primeiro_vertice','<u4'),('n_vertices','<u4'),('caixa_min','<f4',(3,)),('caixa_max','<f4',(3,))]"))};
  }();
  Emprestado e;
  e.va = lote.attr("vertices"); e.ia = lote.attr("indices");
  e.b.v = vetor(e.va, t->vert, "vertices");
  e.b.i = vetor(e.ia, t->ind, "indices");
  e.oo = nb::hasattr(lote, "objetos") ? nb::object(lote.attr("objetos")) : nb::object();
  if (e.oo.is_valid() && !e.oo.is_none()) e.b.o = vetor(e.oo, t->obj, "objetos");
  if (nb::hasattr(lote, "deslocamento")) {  // deslocamento do lote (achado 4); sem o atributo: zeros
    nb::object de = lote.attr("deslocamento");
    if (!de.is_none()) {
      std::vector<double> x;
      try { x = nb::cast<std::vector<double>>(nb::module_::import_("numpy").attr("asarray")(de, "float64").attr("ravel")().attr("tolist")()); }
      catch (const nb::python_error&) { throw nb::type_error("deslocamento: esperados 3 números"); }
      if (x.size() != 3) throw nb::value_error("deslocamento: esperados 3 números");
      std::copy(x.begin(), x.end(), e.b.desl);
    }
  }
  return e;
}

std::optional<double> numero(nb::handle o) { return o.is_none() ? std::nullopt : std::optional<double>(nb::cast<double>(o)); }
}  // namespace

void registrar_viewport(nb::module_& m) {
  m.def("agora", &agora_ms, "relógio do C++ (ms, steady_clock), o mesmo de Cena.relogio()");
  nb::class_<Viewport>(m, "Cena")
      .def(nb::init<bool>(), nb::arg("gl"))
      .def("viewport_ptr", &Viewport::viewport_ptr).def("iniciar", &Viewport::iniciar).def("viva", &Viewport::viva)
      .def("parar", [](Viewport& v) { nb::gil_scoped_release lib; v.parar(); })
      .def("adicionar_lote", [](Viewport& v, nb::object lote) { Emprestado e = emprestar_lote(lote); nb::gil_scoped_release lib; return v.adicionar_lote(e.b); }, nb::arg("lote"))
      .def("limpar", &Viewport::limpar).def("relogio", &Viewport::relogio)
      .def("objetos", [](Viewport& v, int64_t seq) {  // tabela de objetos do lote `seq` (T09/T10)
        std::shared_ptr<Dados> d = v.lote(seq);
        std::vector<int32_t> id; std::vector<uint32_t> pi, ni, pv, nv; std::vector<float> cx; std::vector<std::string> guid;
        for (auto& o : d->objs) {
          id.push_back(o.id_step); pi.push_back(o.pi); ni.push_back(o.ni); pv.push_back(o.pv); nv.push_back(o.nv); guid.push_back(o.guid);
          cx.insert(cx.end(), o.cmin, o.cmin + 3); cx.insert(cx.end(), o.cmax, o.cmax + 3);
        }
        nb::dict r;
        r["guid"] = guid; r["id_step"] = numpy_de(std::move(id), 0); r["primeiro_indice"] = numpy_de(std::move(pi), 0);
        r["n_indices"] = numpy_de(std::move(ni), 0); r["primeiro_vertice"] = numpy_de(std::move(pv), 0);
        r["n_vertices"] = numpy_de(std::move(nv), 0); r["caixa"] = numpy_de(std::move(cx), 6);
        r["deslocamento"] = numpy_de(std::vector<double>(d->desl, d->desl + 3), 0);  // do lote (T09)
        return r;
      }, nb::arg("sequencia"))
      .def("capturar", [](Viewport& v) {
        std::tuple<int, int, std::string> r; { nb::gil_scoped_release lib; r = v.capturar(); }
        return nb::make_tuple(std::get<0>(r), std::get<1>(r), nb::bytes(std::get<2>(r).data(), std::get<2>(r).size()));
      })
      .def("camera", [](Viewport& v) {
        Camera c = v.camera(); nb::dict d;
        d["alvo"] = nb::make_tuple(c.alvo[0], c.alvo[1], c.alvo[2]); d["distancia"] = c.distancia; d["azimute"] = c.azimute; d["elevacao"] = c.elevacao;
        return d;
      })
      .def("definir_camera", [](Viewport& v, nb::object alvo, nb::object distancia, nb::object azimute, nb::object elevacao) {
        std::optional<std::array<double, 3>> a;
        if (!alvo.is_none()) { auto t = nb::cast<std::vector<double>>(alvo); if (t.size() != 3) throw nb::value_error("alvo = 3 números"); a = {t[0], t[1], t[2]}; }
        const auto d = numero(distancia), az = numero(azimute), el = numero(elevacao);
        v.definir_camera(a, d, az, el);
      }, nb::arg("alvo") = nb::none(), nb::arg("distancia") = nb::none(), nb::arg("azimute") = nb::none(), nb::arg("elevacao") = nb::none())
      .def("orbitar", &Viewport::orbitar, nb::arg("dx"), nb::arg("dy")).def("mover", &Viewport::mover, nb::arg("dx"), nb::arg("dy"))
      .def("aproximar", &Viewport::aproximar, nb::arg("fator")).def("enquadrar", &Viewport::enquadrar)
      .def("animar_orbita", &Viewport::animar_orbita, nb::arg("graus_por_s")).def("parar_animacao", &Viewport::parar_animacao)
      .def("atualizar", [](Viewport& v, nb::object lote_novo, nb::object guids) {
        std::set<std::string> rem;  // tudo é validado ANTES de mudar a cena
        if (!nb::isinstance<nb::list>(guids) && !nb::isinstance<nb::tuple>(guids)) throw nb::type_error("guids_remover: esperada uma lista de textos");
        for (nb::handle g : guids) { if (!nb::isinstance<nb::str>(g)) throw nb::type_error("guids_remover: esperados textos"); rem.insert(nb::cast<std::string>(g)); }
        std::optional<Emprestado> e; if (!lote_novo.is_none()) e = emprestar_lote(lote_novo);
        int64_t seq; { nb::gil_scoped_release lib; seq = v.atualizar(e ? &e->b : nullptr, std::move(rem)); }
        return seq;
      }, nb::arg("lote_novo").none(), nb::arg("guids_remover"))
      .def("selecionar", [](Viewport& v, double x, double y) -> nb::object {
        std::optional<std::string> r; { nb::gil_scoped_release lib; r = v.selecionar(x, y); }
        return r ? nb::object(nb::str(r->c_str())) : nb::none();
      }, nb::arg("x"), nb::arg("y"))
      .def("definir_escala_teste", &Viewport::definir_escala_teste, nb::arg("r"))
      .def("estatisticas", [](Viewport& v) {
        const Estatisticas s = v.estatisticas(); nb::dict r;
        r["bytes_copia"] = s.bytes_copia; r["lotes"] = s.lotes; r["triangulos"] = s.triangulos; r["vertices"] = s.vertices; r["fatias_enviadas"] = s.fatias_enviadas;
        r["triangulos_na_placa"] = s.triangulos_na_placa; r["contextos"] = s.contextos;
        r["superficies_soltas"] = s.superficies_soltas; r["solturas_atrasadas"] = s.solturas_atrasadas;
        return r;
      })
      .def("registros", [](Viewport& v, int64_t desde) {  // T32a (ramo descartável): colunas do anel de instrumentação, mais "proximo" (índice do próximo registro)
        int64_t prox = 0; const std::vector<RegQuadro> rs = v.registros(desde, prox); nb::dict r;
        auto col = [&](const char* nome, auto f) { std::vector<double> x; x.reserve(rs.size()); for (auto& q : rs) x.push_back(double(f(q))); r[nome] = x; };
        col("idx", [](auto& q) { return q.idx; }); col("t_env_ini", [](auto& q) { return q.t_env_ini; }); col("t_env_fim", [](auto& q) { return q.t_env_fim; });
        col("t_apres", [](auto& q) { return q.t_apres; }); col("bytes_v", [](auto& q) { return q.bytes_v; }); col("bytes_i", [](auto& q) { return q.bytes_i; });
        col("ped_v", [](auto& q) { return q.ped_v; }); col("ped_i", [](auto& q) { return q.ped_i; }); col("n_create", [](auto& q) { return q.n_create; });
        col("t_create_ms", [](auto& q) { return q.t_create_ms; }); col("motivo", [](auto& q) { return q.motivo; }); col("ger", [](auto& q) { return q.ger; });
        col("ver", [](auto& q) { return q.ver; }); col("seq_placa", [](auto& q) { return q.seq_placa; }); col("tri_placa", [](auto& q) { return q.tri_placa; });
        col("chamadas", [](auto& q) { return q.chamadas; });
        r["proximo"] = prox;
        return r;
      }, nb::arg("desde"))
      .def("perder_contexto", &Viewport::perder_contexto).def("info", &Viewport::info)
      .def("desenho_por_software", &Viewport::desenho_por_software).def("aviso", &Viewport::aviso);
}
