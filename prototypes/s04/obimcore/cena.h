// SPDX-License-Identifier: AGPL-3.0-or-later
// Dados da cena (S04-T08; LOTE_OPUS_12 §4 a-e). Fila de lotes, cópia compacta (a ÚNICA cópia: a placa é reenviada a partir dela), sequência
// e caixa. Mutex próprio (`m_`), nunca o bloqueio do interpretador; sem Qt. A thread de desenho só usa `Cursor`, `proximo`, `geracao` e `caixa`.
#pragma once
#include <nanobind/nanobind.h>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
namespace nb = nanobind;

namespace obim {
constexpr int BYTES_VERTICE = 28;  // pos f4x3, normal f4x3, cor u1x4 (DTYPE_VERTICE da S03)

struct Objeto {  // uma linha de DTYPE_OBJETO do carregador.py
  int32_t id_step; std::string guid; uint32_t pi, ni, pv, nv; float cmin[3], cmax[3];  // pi/ni: índices; pv/nv: vértices (deslocamentos)
};
struct Dados {  // imutável depois de publicado (atualizar() troca o ponteiro, nunca edita o conteúdo)
  std::vector<unsigned char> v; std::vector<uint32_t> i; std::vector<Objeto> objs; int64_t seq = 0;
  double desl[3] = {0, 0, 0}, cmin[3] = {1e30, 1e30, 1e30}, cmax[3] = {-1e30, -1e30, -1e30};  // deslocamento do lote (T09) e caixa dos vértices
};
struct Cursor { size_t n = 0; int64_t ger = -1; };  // o que a thread de desenho já tirou da fila (a placa é uma visão da fila)
struct Totais { size_t lotes = 0, triangulos = 0, vertices = 0; };

class DadosCena {
 public:
  int64_t adicionar_lote(nb::object lote);  // Python (com o bloqueio): valida, copia e calcula a caixa SEM ele e fora do mutex; só o push é sob mutex
  // T09: remove, em todos os lotes, os objetos com GlobalId em `guids` OU em `lote_novo.objetos`, e acrescenta `lote_novo` (None: só remove). Devolve a
  // sequência (sempre nova, estritamente crescente). Erro: TypeError/ValueError e a cena fica intacta. Escolha (achado 4): lote com deslocamento
  // diferente do primeiro da cena é RECUSADO (ValueError); `limpar()` zera a cena e libera o deslocamento.
  int64_t atualizar(nb::object lote_novo, nb::object guids);
  void limpar();
  int64_t geracao() { std::lock_guard<std::mutex> l(m_); return ger_; }
  std::shared_ptr<Dados> proximo(Cursor& c);  // próximo lote ainda não visto (nullptr se não há); devolve nullptr se a geração mudou: quem chama zera a placa
  bool caixa(double mn[3], double mx[3]);     // false se a cena está vazia
  Totais totais();
  nb::dict objetos(int64_t seq);              // tabela de objetos do lote `seq` (T09/T10)
 private:
  std::shared_ptr<Dados> preparar(nb::object lote);  // valida e copia (sem o mutex); não publica
  void recalcular_caixa();                            // com m_
  std::mutex m_; std::vector<std::shared_ptr<Dados>> lotes_; int64_t seq_ = 0, ger_ = 0, ver_ = 0;  // ver_: sobe a cada mudança (atualizar refaz se mudou)
  double cmin_[3] = {1e30, 1e30, 1e30}, cmax_[3] = {-1e30, -1e30, -1e30};
};
}  // namespace obim
