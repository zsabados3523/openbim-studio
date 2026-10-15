// SPDX-License-Identifier: AGPL-3.0-or-later
// Dados da cena (S04-T08; LOTE_OPUS_12 §4 a-e). Fila de lotes, cópia compacta (a ÚNICA cópia: a placa é reenviada a partir dela), sequência
// e caixa. Mutex próprio (`m_`), nunca o bloqueio do interpretador; sem Qt. A thread de desenho só usa `Cursor`, `proximo`, `geracao` e `caixa`.
// C++ PURO (T14b): nenhuma linha daqui conhece Python; a ponte (ponte_viewport.cpp) valida os arrays do numpy e entrega `LoteBruto`.
// Erros: std::invalid_argument (a ponte os vê como ValueError). Ordem de mutexes: `Motor::m_` (motor.h) ANTES de `DadosCena::m_`, nunca o contrário.
#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <vector>

namespace obim {
constexpr int BYTES_VERTICE = 28;  // pos f4x3, normal f4x3, cor u1x4 (DTYPE_VERTICE em prototypes/formato_malha.py; tests/test_formato_malha.py confere)

struct Objeto {  // uma linha de DTYPE_OBJETO de prototypes/formato_malha.py
  int32_t id_step; std::string guid; uint32_t pi, ni, pv, nv; float cmin[3], cmax[3];  // pi/ni: índices; pv/nv: vértices (deslocamentos)
};
struct Dados {  // imutável depois de publicado (atualizar() troca o ponteiro, nunca edita o conteúdo)
  std::vector<unsigned char> v; std::vector<uint32_t> i; std::vector<Objeto> objs; int64_t seq = 0;
  double desl[3] = {0, 0, 0}, cmin[3] = {1e30, 1e30, 1e30}, cmax[3] = {-1e30, -1e30, -1e30};  // deslocamento do lote (T09) e caixa dos vértices
};
struct Vista { const unsigned char* p = nullptr; size_t n = 0; };  // memória EMPRESTADA (do numpy): quem chama a mantém viva e imóvel durante a chamada; nada é guardado
struct LoteBruto { Vista v, i, o; double desl[3] = {0, 0, 0}; };    // v: vértices (28 bytes cada), i: índices u4, o: DTYPE_OBJETO empacotado (n = objetos), desl: deslocamento
struct Cursor { size_t n = 0; int64_t ger = -1; };  // o que a thread de desenho já tirou da fila (a placa é uma visão da fila)
struct Totais { size_t lotes = 0, triangulos = 0, vertices = 0, bytes = 0; };  // bytes: memória da cópia compacta (T10)

class DadosCena {
 public:
  int64_t adicionar_lote(const LoteBruto& lote);  // valida, copia e calcula a caixa fora do mutex; só o push é sob mutex (a ponte chama SEM o bloqueio do interpretador)
  // T09: remove, em todos os lotes, os objetos com GlobalId em `guids` OU em `lote_novo->o`, e acrescenta `lote_novo` (nullptr: só remove). Devolve a
  // sequência (sempre nova, estritamente crescente). Erro: std::invalid_argument e a cena fica intacta. Escolha (achado 4): lote com deslocamento
  // diferente do primeiro da cena é RECUSADO; `limpar()` zera a cena e libera o deslocamento.
  int64_t atualizar(const LoteBruto* lote_novo, std::set<std::string> guids);
  void limpar();
  int64_t geracao() { std::lock_guard<std::mutex> l(m_); return ger_; }
  std::shared_ptr<Dados> proximo(Cursor& c);  // próximo lote ainda não visto (nullptr se não há); devolve nullptr se a geração mudou: quem chama zera a placa
  bool caixa(double mn[3], double mx[3]);     // false se a cena está vazia
  Totais totais();
  std::vector<std::shared_ptr<Dados>> lotes() { std::lock_guard<std::mutex> l(m_); return lotes_; }  // T10: instantâneo imutável para a seleção (mutex só na cópia dos ponteiros)
  std::shared_ptr<Dados> lote(int64_t seq);   // lote `seq` (T09/T10; a ponte monta a tabela de objetos); std::invalid_argument se desconhecido ou já limpo
 private:
  std::shared_ptr<Dados> preparar(const LoteBruto& lote);  // valida e copia (sem o mutex); não publica
  void recalcular_caixa();                            // com m_
  std::mutex m_; std::vector<std::shared_ptr<Dados>> lotes_; int64_t seq_ = 0, ger_ = 0, ver_ = 0;  // ver_: sobe a cada mudança (atualizar refaz se mudou)
  double cmin_[3] = {1e30, 1e30, 1e30}, cmax_[3] = {-1e30, -1e30, -1e30};
};
}  // namespace obim
