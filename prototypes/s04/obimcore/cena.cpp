// SPDX-License-Identifier: AGPL-3.0-or-later
// Dados da cena (S04-T08). Ver cena.h.
#include "cena.h"
#include <nanobind/eval.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <set>

namespace obim {
namespace {
constexpr size_t BYTES_OBJETO = 66, O_PI = 26, O_NI = 30, O_PV = 34, O_NV = 38, O_MIN = 42, O_MAX = 54;  // DTYPE_OBJETO empacotado (sem alinhamento)
struct Vista { const unsigned char* p = nullptr; size_t n = 0; };

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

void caixa_de(Dados& d) {  // caixa dos vértices (pura, sem Python)
  for (size_t k = 0; k < d.v.size() / BYTES_VERTICE; ++k) {
    float f[3]; std::memcpy(f, d.v.data() + k * BYTES_VERTICE, 12);
    for (int a = 0; a < 3; ++a) { d.cmin[a] = (std::min)(d.cmin[a], double(f[a])); d.cmax[a] = (std::max)(d.cmax[a], double(f[a])); }
  }
}

// Cópia de `d` sem os objetos de `rem` (nullptr se nenhum está no lote). Mantém a sequência e o deslocamento; descarta índices e vértices dos removidos
// e renumera o resto (qualquer lote serve: não supõe que cada objeto só use os seus vértices).
std::shared_ptr<Dados> sem(const Dados& d, const std::set<std::string>& rem) {
  std::vector<char> morto(d.i.size(), 0); bool algum = false;
  for (auto& o : d.objs) if (rem.count(o.guid)) { algum = true; std::fill(morto.begin() + o.pi, morto.begin() + o.pi + o.ni, 1); }
  if (!algum) return nullptr;
  const size_t nv = d.v.size() / BYTES_VERTICE; std::vector<char> usado(nv, 0);
  for (size_t k = 0; k < d.i.size(); ++k) if (!morto[k]) usado[d.i[k]] = 1;
  std::vector<uint32_t> pv(nv + 1, 0), pi(d.i.size() + 1, 0);  // somas parciais: posição nova de cada vértice e de cada índice
  for (size_t k = 0; k < nv; ++k) pv[k + 1] = pv[k] + usado[k];
  for (size_t k = 0; k < d.i.size(); ++k) pi[k + 1] = pi[k] + !morto[k];
  auto r = std::make_shared<Dados>(); r->seq = d.seq; std::copy(d.desl, d.desl + 3, r->desl);
  for (size_t k = 0; k < nv; ++k) if (usado[k]) r->v.insert(r->v.end(), d.v.begin() + k * BYTES_VERTICE, d.v.begin() + (k + 1) * BYTES_VERTICE);
  for (size_t k = 0; k < d.i.size(); ++k) if (!morto[k]) r->i.push_back(pv[d.i[k]]);
  for (Objeto o : d.objs) {
    if (rem.count(o.guid)) continue;
    const uint32_t a = pi[o.pi], b = pi[o.pi + o.ni], c = pv[o.pv], e = pv[o.pv + o.nv];
    o.pi = a; o.ni = b - a; o.pv = c; o.nv = e - c; r->objs.push_back(std::move(o));
  }
  caixa_de(*r);
  return r;
}

const Dados* referencia(const std::vector<std::shared_ptr<Dados>>& ls) {  // o primeiro lote com geometria dá o deslocamento da cena (marcadores vazios não)
  for (auto& d : ls) if (!d->v.empty()) return d.get();
  return nullptr;
}
}  // namespace

std::shared_ptr<Dados> DadosCena::preparar(nb::object lote) {
  for (const char* c : {"vertices", "indices"})
    if (!nb::hasattr(lote, c)) throw nb::type_error("lote sem vertices/indices (esperado LoteMalha)");
  struct Tipos { nb::object vert, ind, obj; };  // montados UMA vez (achado 10); vazam de propósito (nunca destruídos depois do Python)
  static const Tipos* t = [] {
    nb::object dt = nb::module_::import_("numpy").attr("dtype");
    return new Tipos{dt(nb::eval("[('pos','<f4',(3,)),('normal','<f4',(3,)),('cor','u1',(4,))]")), dt("<u4"),
                     dt(nb::eval("[('id_step','<i4'),('guid','S22'),('primeiro_indice','<u4'),('n_indices','<u4'),('primeiro_vertice','<u4'),('n_vertices','<u4'),('caixa_min','<f4',(3,)),('caixa_max','<f4',(3,))]"))};
  }();
  nb::object va = lote.attr("vertices"), ia = lote.attr("indices");  // referências próprias: os arrays não morrem sem o bloqueio
  const Vista V = vetor(va, t->vert, "vertices");
  const Vista I = vetor(ia, t->ind, "indices");
  Vista O; nb::object oo = nb::hasattr(lote, "objetos") ? nb::object(lote.attr("objetos")) : nb::object();
  if (oo.is_valid() && !oo.is_none()) O = vetor(oo, t->obj, "objetos");
  auto d = std::make_shared<Dados>();
  if (nb::hasattr(lote, "deslocamento")) {  // deslocamento do lote (achado 4); sem o atributo: zeros
    nb::object de = lote.attr("deslocamento");
    if (!de.is_none()) {
      std::vector<double> x;
      try { x = nb::cast<std::vector<double>>(nb::module_::import_("numpy").attr("asarray")(de, "float64").attr("ravel")().attr("tolist")()); }
      catch (const nb::python_error&) { throw nb::type_error("deslocamento: esperados 3 números"); }
      if (x.size() != 3) throw nb::value_error("deslocamento: esperados 3 números");
      std::copy(x.begin(), x.end(), d->desl);
    }
  }
  if (I.n % 3) throw nb::value_error("indices: o número de índices não é múltiplo de 3");
  const char* erro = nullptr;
  {  // a única cópia; nenhum objeto Python aqui dentro (os arrays estão presos por `va`/`ia`)
    nb::gil_scoped_release livre;
    d->v.assign(V.p, V.p + V.n * BYTES_VERTICE); d->i.resize(I.n); std::memcpy(d->i.data(), I.p, I.n * 4);
    caixa_de(*d);
    for (uint32_t x : d->i) if (x >= V.n) { erro = "indices: índice maior ou igual ao número de vértices"; break; }
    for (size_t k = 0; !erro && k < O.n; ++k) {
      const unsigned char* p = O.p + k * BYTES_OBJETO; Objeto o;
      std::memcpy(&o.id_step, p, 4); std::memcpy(&o.pi, p + O_PI, 4); std::memcpy(&o.ni, p + O_NI, 4);
      std::memcpy(&o.pv, p + O_PV, 4); std::memcpy(&o.nv, p + O_NV, 4); std::memcpy(o.cmin, p + O_MIN, 12); std::memcpy(o.cmax, p + O_MAX, 12);
      o.guid.assign(reinterpret_cast<const char*>(p + 4), strnlen(reinterpret_cast<const char*>(p + 4), 22));
      if (uint64_t(o.pi) + o.ni > I.n || uint64_t(o.pv) + o.nv > V.n) { erro = "objetos: faixa fora do lote"; break; }
      if (!o.ni || !o.nv) for (int a = 0; a < 3; ++a) o.cmin[a] = o.cmax[a] = std::nanf("");  // sem geometria: NaN, nunca [0,0,0,0,0,0]
      d->objs.push_back(std::move(o));
    }
  }
  if (erro) throw nb::value_error(erro);
  return d;
}

void DadosCena::recalcular_caixa() {
  for (int a = 0; a < 3; ++a) { cmin_[a] = 1e30; cmax_[a] = -1e30; }
  for (auto& d : lotes_) for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], d->cmin[a]); cmax_[a] = (std::max)(cmax_[a], d->cmax[a]); }
}

int64_t DadosCena::adicionar_lote(nb::object lote) {
  auto d = preparar(lote);
  std::lock_guard<std::mutex> l(m_);  // só o essencial sob o mutex
  if (auto* r = referencia(lotes_); r && !d->v.empty() && !std::equal(d->desl, d->desl + 3, r->desl)) throw nb::value_error("deslocamento diferente do primeiro lote da cena");
  d->seq = ++seq_; lotes_.push_back(d); ++ver_;
  for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], d->cmin[a]); cmax_[a] = (std::max)(cmax_[a], d->cmax[a]); }
  return d->seq;
}

int64_t DadosCena::atualizar(nb::object lote_novo, nb::object guids) {
  std::set<std::string> rem;  // tudo é validado ANTES de mudar a cena
  if (!nb::isinstance<nb::list>(guids) && !nb::isinstance<nb::tuple>(guids)) throw nb::type_error("guids_remover: esperada uma lista de textos");
  for (nb::handle g : guids) { if (!nb::isinstance<nb::str>(g)) throw nb::type_error("guids_remover: esperados textos"); rem.insert(nb::cast<std::string>(g)); }
  std::shared_ptr<Dados> novo;
  if (!lote_novo.is_none()) { novo = preparar(lote_novo); for (auto& o : novo->objs) rem.insert(o.guid); }
  int64_t seq = 0; bool desl_ruim = false;
  {
    nb::gil_scoped_release livre;  // refazer os lotes tocados é cópia pura: sem Python
    for (;;) {
      std::vector<std::shared_ptr<Dados>> ls; int64_t ver;
      { std::lock_guard<std::mutex> l(m_); ls = lotes_; ver = ver_; }
      bool mudou = false;
      for (auto& d : ls) if (auto r = sem(*d, rem)) { d = r; mudou = true; }  // fora do mutex: o desenho e o Python não esperam
      std::lock_guard<std::mutex> l(m_);
      if (ver != ver_) continue;  // alguém mudou a cena no meio: refaz com o estado novo
      if (auto* r = referencia(ls); novo && r && !novo->v.empty() && !std::equal(novo->desl, novo->desl + 3, r->desl)) { desl_ruim = true; break; }
      if (!novo) novo = std::make_shared<Dados>();  // marcador vazio: leva a sequência até a placa (prefixo contínuo)
      novo->seq = seq = ++seq_; ls.push_back(novo); lotes_ = std::move(ls); ++ver_;
      if (mudou) { ++ger_; recalcular_caixa(); }  // a placa recomeça da cópia compacta (como limpar()); só acrescentar não precisa
      else for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], novo->cmin[a]); cmax_[a] = (std::max)(cmax_[a], novo->cmax[a]); }
      break;
    }
  }
  if (desl_ruim) throw nb::value_error("deslocamento diferente do primeiro lote da cena");
  return seq;
}

void DadosCena::limpar() {
  std::lock_guard<std::mutex> l(m_); lotes_.clear(); ++ger_; ++ver_;
  for (int a = 0; a < 3; ++a) { cmin_[a] = 1e30; cmax_[a] = -1e30; }
}

std::shared_ptr<Dados> DadosCena::proximo(Cursor& c) {
  std::lock_guard<std::mutex> l(m_);
  if (c.ger != ger_) return nullptr;  // limpar() no meio do quadro: quem chama zera a placa no próximo quadro
  return c.n < lotes_.size() ? lotes_[c.n++] : nullptr;
}

bool DadosCena::caixa(double mn[3], double mx[3]) {
  std::lock_guard<std::mutex> l(m_);
  std::copy(cmin_, cmin_ + 3, mn); std::copy(cmax_, cmax_ + 3, mx);
  return cmin_[0] <= cmax_[0];
}

Totais DadosCena::totais() {
  std::lock_guard<std::mutex> l(m_); Totais t; t.lotes = lotes_.size();
  for (auto& d : lotes_) { t.triangulos += d->i.size() / 3; t.vertices += d->v.size() / BYTES_VERTICE;
    t.bytes += d->v.capacity() + d->i.capacity() * 4 + d->objs.capacity() * sizeof(Objeto); }
  return t;
}

nb::dict DadosCena::objetos(int64_t seq) {
  std::shared_ptr<Dados> d;
  { std::lock_guard<std::mutex> l(m_); for (auto& x : lotes_) if (x->seq == seq) d = x; }
  if (!d) throw nb::value_error("sequência de lote desconhecida (ou já limpa)");
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
}
}  // namespace obim
