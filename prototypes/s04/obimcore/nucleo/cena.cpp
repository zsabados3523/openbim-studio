// SPDX-License-Identifier: AGPL-3.0-or-later
// Dados da cena (S04-T08). Ver cena.h.
#include "cena.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace obim {
namespace {
constexpr size_t BYTES_OBJETO = 66, O_ID = 0, O_GUID = 4, N_GUID = 22, O_PI = 26, O_NI = 30, O_PV = 34, O_NV = 38, O_MIN = 42, O_MAX = 54;  // DTYPE_OBJETO de prototypes/formato_malha.py, empacotado (sem alinhamento); tests/test_formato_malha.py confere
void caixa_de(Dados& d) {  // caixa dos vértices (pura, sem Python)
  for (size_t k = 0; k < d.v.size() / BYTES_VERTICE; ++k) {
    float f[3]; std::memcpy(f, d.v.data() + k * BYTES_VERTICE, 12);
    for (int a = 0; a < 3; ++a) { d.cmin[a] = (std::min)(d.cmin[a], double(f[a])); d.cmax[a] = (std::max)(d.cmax[a], double(f[a])); }
  }
}

// Caixa do objeto pelos TRIÂNGULOS dele (vértices apontados por seus índices), nunca pela tabela do carregador (T10c achado 3). Sem geometria: NaN.
void caixa_do_objeto(const Dados& d, Objeto& o) {
  if (!o.ni || !o.nv) { for (int a = 0; a < 3; ++a) o.cmin[a] = o.cmax[a] = std::nanf(""); return; }
  for (int a = 0; a < 3; ++a) { o.cmin[a] = 1e30f; o.cmax[a] = -1e30f; }
  for (uint32_t k = 0; k < o.ni; ++k) {
    float f[3]; std::memcpy(f, d.v.data() + size_t(d.i[o.pi + k]) * BYTES_VERTICE, 12);
    for (int a = 0; a < 3; ++a) { o.cmin[a] = (std::min)(o.cmin[a], f[a]); o.cmax[a] = (std::max)(o.cmax[a], f[a]); }
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
    o.pi = a; o.ni = b - a; o.pv = c; o.nv = e - c; caixa_do_objeto(*r, o); r->objs.push_back(std::move(o));
  }
  caixa_de(*r);
  return r;
}

const Dados* referencia(const std::vector<std::shared_ptr<Dados>>& ls) {  // o primeiro lote com geometria dá o deslocamento da cena (marcadores vazios não)
  for (auto& d : ls) if (!d->v.empty()) return d.get();
  return nullptr;
}
}  // namespace

std::shared_ptr<Dados> DadosCena::preparar(const LoteBruto& L) {
  const Vista &V = L.v, &I = L.i, &O = L.o;
  auto d = std::make_shared<Dados>(); std::copy(L.desl, L.desl + 3, d->desl);
  if (I.n % 3) throw std::invalid_argument("indices: o número de índices não é múltiplo de 3");
  const char* erro = nullptr;
  {  // a única cópia (a ponte prende os arrays do numpy até o retorno e chama sem o bloqueio do interpretador)
    d->v.assign(V.p, V.p + V.n * BYTES_VERTICE); d->i.resize(I.n); std::memcpy(d->i.data(), I.p, I.n * 4);
    caixa_de(*d);
    for (uint32_t x : d->i) if (x >= V.n) { erro = "indices: índice maior ou igual ao número de vértices"; break; }
    for (size_t k = 0; !erro && k < O.n; ++k) {
      const unsigned char* p = O.p + k * BYTES_OBJETO; Objeto o;
      std::memcpy(&o.id_step, p + O_ID, 4); std::memcpy(&o.pi, p + O_PI, 4); std::memcpy(&o.ni, p + O_NI, 4);
      std::memcpy(&o.pv, p + O_PV, 4); std::memcpy(&o.nv, p + O_NV, 4); std::memcpy(o.cmin, p + O_MIN, 12); std::memcpy(o.cmax, p + O_MAX, 12);
      o.guid.assign(reinterpret_cast<const char*>(p + O_GUID), strnlen(reinterpret_cast<const char*>(p + O_GUID), N_GUID));
      if (uint64_t(o.pi) + o.ni > I.n || uint64_t(o.pv) + o.nv > V.n) { erro = "objetos: faixa fora do lote"; break; }
      caixa_do_objeto(*d, o);  // pelos triângulos; sem geometria: NaN, nunca [0,0,0,0,0,0]
      d->objs.push_back(std::move(o));
    }
  }
  if (erro) throw std::invalid_argument(erro);
  return d;
}

void DadosCena::recalcular_caixa() {
  for (int a = 0; a < 3; ++a) { cmin_[a] = 1e30; cmax_[a] = -1e30; }
  for (auto& d : lotes_) for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], d->cmin[a]); cmax_[a] = (std::max)(cmax_[a], d->cmax[a]); }
}

int64_t DadosCena::adicionar_lote(const LoteBruto& lote) {
  auto d = preparar(lote);
  std::lock_guard<std::mutex> l(m_);  // só o essencial sob o mutex
  if (auto* r = referencia(lotes_); r && !d->v.empty() && !std::equal(d->desl, d->desl + 3, r->desl)) throw std::invalid_argument("deslocamento diferente do primeiro lote da cena");
  d->seq = ++seq_; lotes_.push_back(d); ++ver_;
  for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], d->cmin[a]); cmax_[a] = (std::max)(cmax_[a], d->cmax[a]); }
  return d->seq;
}

int64_t DadosCena::atualizar(const LoteBruto* lote_novo, std::set<std::string> rem) {  // `rem` já validado pela ponte: tudo é checado ANTES de mudar a cena
  std::shared_ptr<Dados> novo;
  if (lote_novo) { novo = preparar(*lote_novo); for (auto& o : novo->objs) rem.insert(o.guid); }
  int64_t seq = 0; bool desl_ruim = false;
  {  // refazer os lotes tocados é cópia pura: sem Python
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
  if (desl_ruim) throw std::invalid_argument("deslocamento diferente do primeiro lote da cena");
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
    t.bytes += d->v.capacity() + d->i.capacity() * 4 + d->objs.capacity() * sizeof(Objeto);
    for (auto& o : d->objs) if (o.guid.capacity() > 15) t.bytes += o.guid.capacity() + 1; }  // texto do GlobalId fora do std::string (T10c achado 6)
  return t;
}

std::shared_ptr<Dados> DadosCena::lote(int64_t seq) {
  std::lock_guard<std::mutex> l(m_);
  for (auto& x : lotes_) if (x->seq == seq) return x;
  throw std::invalid_argument("sequência de lote desconhecida (ou já limpa)");
}
}  // namespace obim
