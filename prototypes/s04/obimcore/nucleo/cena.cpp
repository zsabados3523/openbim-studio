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

bool acima_de_c(const Dados& d) { return d.v.size() + d.i.size() * 4 > BYTES_SUBLOTE; }  // bytes de vértices + índices passam do tamanho C do sub-lote

// Cópia de `d` sem os objetos de `rem` (nullptr se nenhum está no lote). Mantém a sequência e o deslocamento; descarta índices e vértices dos removidos
// e renumera o resto (qualquer lote serve: não supõe que cada objeto só use os seus vértices).
std::shared_ptr<Dados> sem(const Dados& d, const std::set<std::string>& rem) {
  size_t tocados = 0;
  for (auto& o : d.objs) if (rem.count(o.guid)) ++tocados;  // olha a tabela antes de alocar: lote sem removido não aloca `morto` nem `usado`
  if (!tocados) return nullptr;
  std::vector<char> morto(d.i.size(), 0);
  for (auto& o : d.objs) if (rem.count(o.guid)) std::fill(morto.begin() + o.pi, morto.begin() + o.pi + o.ni, 1);
  const size_t nv = d.v.size() / BYTES_VERTICE; std::vector<char> usado(nv, 0);
  for (size_t k = 0; k < d.i.size(); ++k) if (!morto[k]) usado[d.i[k]] = 1;
  std::vector<uint32_t> pv(nv + 1, 0), pi(d.i.size() + 1, 0);  // somas parciais: posição nova de cada vértice e de cada índice
  for (size_t k = 0; k < nv; ++k) pv[k + 1] = pv[k] + usado[k];
  for (size_t k = 0; k < d.i.size(); ++k) pi[k + 1] = pi[k] + !morto[k];
  auto r = std::make_shared<Dados>(); r->seq = d.seq; std::copy(d.desl, d.desl + 3, r->desl);
  // capacidade exata: bytes_copia não pode depender de como o vetor cresce (GCC dobra, MSVC cresce 1,5 vez)
  r->v.reserve(size_t(pv[nv]) * BYTES_VERTICE); r->i.reserve(pi[d.i.size()]); r->objs.reserve(d.objs.size() - tocados);
  for (size_t k = 0; k < nv;) {  // vértices usados, em trechos contínuos
    if (!usado[k]) { ++k; continue; }
    size_t e = k; while (e < nv && usado[e]) ++e;
    r->v.insert(r->v.end(), d.v.begin() + k * BYTES_VERTICE, d.v.begin() + e * BYTES_VERTICE); k = e;
  }
  for (size_t k = 0; k < d.i.size(); ++k) if (!morto[k]) r->i.push_back(pv[d.i[k]]);
  for (Objeto o : d.objs) {
    if (rem.count(o.guid)) continue;
    const uint32_t a = pi[o.pi], b = pi[o.pi + o.ni], c = pv[o.pv], e = pv[o.pv + o.nv];
    o.pi = a; o.ni = b - a; o.pv = c; o.nv = e - c; caixa_do_objeto(*r, o); r->objs.push_back(std::move(o));
  }
  caixa_de(*r);
  const bool grande = acima_de_c(*r);  // o lote só encolhe: as marcas valem enquanto ele passar de C
  r->nao_partido = d.nao_partido && grande; r->peca_maior_que_c = d.peca_maior_que_c && grande && r->objs.size() == 1;
  return r;
}

// Índice k da entrada: memcpy, pois a ponte aceita array desalinhado (só confere contiguidade).
uint32_t indice(const unsigned char* p, size_t k) { uint32_t x; std::memcpy(&x, p + k * 4, 4); return x; }

const Dados* referencia(const std::vector<std::shared_ptr<Dados>>& ls) {  // o primeiro lote com geometria dá o deslocamento da cena (marcadores vazios não)
  for (auto& d : ls) if (!d->v.empty()) return d.get();
  return nullptr;
}
}  // namespace

std::vector<std::shared_ptr<Dados>> DadosCena::preparar(const LoteBruto& L) {
  const Vista &V = L.v, &I = L.i, &O = L.o;
  if (I.n % 3) throw std::invalid_argument("indices: o número de índices não é múltiplo de 3");
  const char* erro = nullptr;
  for (size_t k = 0; k < I.n; ++k) if (indice(I.p, k) >= V.n) { erro = "indices: índice maior ou igual ao número de vértices"; break; }
  std::vector<Objeto> objs; objs.reserve(O.n);
  for (size_t k = 0; !erro && k < O.n; ++k) {
    const unsigned char* p = O.p + k * BYTES_OBJETO; Objeto o;
    std::memcpy(&o.id_step, p + O_ID, 4); std::memcpy(&o.pi, p + O_PI, 4); std::memcpy(&o.ni, p + O_NI, 4);
    std::memcpy(&o.pv, p + O_PV, 4); std::memcpy(&o.nv, p + O_NV, 4); std::memcpy(o.cmin, p + O_MIN, 12); std::memcpy(o.cmax, p + O_MAX, 12);
    o.guid = std::string(reinterpret_cast<const char*>(p + O_GUID), strnlen(reinterpret_cast<const char*>(p + O_GUID), N_GUID));  // construtor: capacidade = tamanho (assign sobre string vazia dobra para 30)
    if (uint64_t(o.pi) + o.ni > I.n || uint64_t(o.pv) + o.nv > V.n) { erro = "objetos: faixa fora do lote"; break; }
    objs.push_back(std::move(o));
  }
  if (erro) throw std::invalid_argument(erro);
  // Partível: as peças, na ordem da tabela, ladrilham índices e vértices (sem sobra, sem salto) e cada peça só aponta para os próprios vértices.
  bool partivel = !objs.empty(); uint64_t pi = 0, pv = 0;
  for (auto& o : objs) {
    if (o.pi != pi || o.pv != pv) { partivel = false; break; }
    for (uint32_t k = 0; k < o.ni; ++k) if (const uint32_t x = indice(I.p, o.pi + k); x < o.pv || x - o.pv >= o.nv) { partivel = false; break; }  // lê direto da entrada
    if (!partivel) break;
    pi += o.ni; pv += o.nv;
  }
  if (partivel && (pi != I.n || pv != V.n)) partivel = false;
  struct Grupo { size_t a, b; };  // peças [a, b) de um sub-lote
  std::vector<Grupo> gs;
  if (!partivel) gs.push_back({0, objs.size()});
  else {
    size_t a = 0, bytes = 0;
    for (size_t k = 0; k < objs.size(); ++k) {
      const size_t p = size_t(objs[k].nv) * BYTES_VERTICE + size_t(objs[k].ni) * 4;
      if (bytes && bytes + p > BYTES_SUBLOTE) { gs.push_back({a, k}); a = k; bytes = 0; }  // corte na fronteira de peça
      bytes += p;
    }
    gs.push_back({a, objs.size()});
  }
  std::vector<std::shared_ptr<Dados>> r;
  for (auto& g : gs) {
    auto d = std::make_shared<Dados>(); std::copy(L.desl, L.desl + 3, d->desl);
    size_t i0 = 0, v0 = 0, i1 = I.n, v1 = V.n;  // sem partir: o lote inteiro
    if (partivel) {  // faixa das peças [a, b): começa na peça a e termina onde começa a peça b (ou no fim do lote)
      i0 = objs[g.a].pi; v0 = objs[g.a].pv;
      if (g.b < objs.size()) { i1 = objs[g.b].pi; v1 = objs[g.b].pv; }
    }
    d->v.assign(V.p + v0 * BYTES_VERTICE, V.p + v1 * BYTES_VERTICE); d->i.resize(i1 - i0);
    for (size_t k = i0; k < i1; ++k) d->i[k - i0] = indice(I.p, k) - uint32_t(v0);  // sem partir: v0 = 0 e é a cópia pura
    caixa_de(*d); d->objs.reserve(g.b - g.a);  // capacidade exata da tabela (o push_back dobraria e inflaria bytes_copia)
    for (size_t k = g.a; k < g.b; ++k) {
      Objeto o = std::move(objs[k]); o.pi -= uint32_t(i0); o.pv -= uint32_t(v0);
      caixa_do_objeto(*d, o);  // pelos triângulos; sem geometria: NaN, nunca [0,0,0,0,0,0]
      d->objs.push_back(std::move(o));
    }
    if (acima_de_c(*d)) {  // lote que não ladrilha e cabe em C fica inteiro, sem marca
      if (partivel) d->peca_maior_que_c = true; else d->nao_partido = true;
    }
    r.push_back(std::move(d));
  }
  return r;
}

void DadosCena::recalcular_caixa() {
  for (int a = 0; a < 3; ++a) { cmin_[a] = 1e30; cmax_[a] = -1e30; }
  for (auto& d : lotes_) for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], d->cmin[a]); cmax_[a] = (std::max)(cmax_[a], d->cmax[a]); }
}

int64_t DadosCena::adicionar_lote(const LoteBruto& lote) {
  auto ds = preparar(lote);
  std::lock_guard<std::mutex> l(m_);  // só o essencial sob o mutex: todos os sub-lotes entram juntos, com sequências seguidas e um único ++ver_
  if (auto* r = referencia(lotes_); r && lote.v.n && !std::equal(ds[0]->desl, ds[0]->desl + 3, r->desl)) throw std::invalid_argument("deslocamento diferente do primeiro lote da cena");
  for (auto& d : ds) {
    d->seq = ++seq_; lotes_.push_back(d);
    for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], d->cmin[a]); cmax_[a] = (std::max)(cmax_[a], d->cmax[a]); }
  }
  ++ver_;
  return seq_;  // sequência do último sub-lote
}

int64_t DadosCena::atualizar(const LoteBruto* lote_novo, std::set<std::string> rem) {  // `rem` já validado pela ponte: tudo é checado ANTES de mudar a cena
  std::vector<std::shared_ptr<Dados>> novos;
  if (lote_novo) { novos = preparar(*lote_novo); for (auto& d : novos) for (auto& o : d->objs) rem.insert(o.guid); }
  int64_t seq = 0; bool desl_ruim = false;
  {  // refazer os lotes tocados é cópia pura: sem Python
    for (;;) {
      std::vector<std::shared_ptr<Dados>> ls; int64_t ver;
      { std::lock_guard<std::mutex> l(m_); ls = lotes_; ver = ver_; }
      bool mudou = false;
      for (auto& d : ls) if (auto r = sem(*d, rem)) { d = r; mudou = true; }  // fora do mutex: o desenho e o Python não esperam
      std::lock_guard<std::mutex> l(m_);
      if (ver != ver_) continue;  // alguém mudou a cena no meio: refaz com o estado novo
      if (auto* r = referencia(ls); r && lote_novo && lote_novo->v.n && !std::equal(novos[0]->desl, novos[0]->desl + 3, r->desl)) { desl_ruim = true; break; }
      if (novos.empty()) novos.push_back(std::make_shared<Dados>());  // marcador vazio: leva a sequência até a placa (prefixo contínuo)
      for (auto& n : novos) { n->seq = seq = ++seq_; ls.push_back(n); }  // sub-lotes com sequências seguidas; devolve a do último
      lotes_ = std::move(ls); ++ver_;
      if (mudou) recalcular_caixa();  // T30b2: a troca NÃO sobe ger_ (o motor reenvia por posição, comparando ponteiros); só limpar() sobe
      else for (auto& n : novos) for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], n->cmin[a]); cmax_[a] = (std::max)(cmax_[a], n->cmax[a]); }
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
  for (auto& d : lotes_) { t.nao_partidos += d->nao_partido; t.pecas_maiores_que_c += d->peca_maior_que_c; t.triangulos += d->i.size() / 3; t.vertices += d->v.size() / BYTES_VERTICE;
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
