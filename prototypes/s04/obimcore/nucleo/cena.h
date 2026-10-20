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
constexpr size_t BYTES_SUBLOTE = size_t(8) << 20;  // C (T30a2): teto de bytes de vértices e índices por sub-lote
constexpr int BYTES_VERTICE = 28;  // pos f4x3, normal f4x3, cor u1x4 (DTYPE_VERTICE em prototypes/formato_malha.py; tests/test_formato_malha.py confere)

struct Objeto {  // uma linha de DTYPE_OBJETO de prototypes/formato_malha.py
  int32_t id_step; std::string guid; uint32_t pi, ni, pv, nv; float cmin[3], cmax[3];  // pi/ni: índices; pv/nv: vértices (deslocamentos)
};
struct Dados {  // imutável depois de publicado (atualizar() troca o ponteiro, nunca edita o conteúdo)
  std::vector<unsigned char> v; std::vector<uint32_t> i; std::vector<Objeto> objs; int64_t seq = 0;
  bool nao_partido = false, peca_maior_que_c = false;  // T30a2: nao_partido = sub-lote > C de um lote de entrada que não ladrilha (sem fronteira de peça); peca_maior_que_c = sub-lote > C de uma só peça, em lote que ladrilha
  double desl[3] = {0, 0, 0}, cmin[3] = {1e30, 1e30, 1e30}, cmax[3] = {-1e30, -1e30, -1e30};  // deslocamento do lote (T09) e caixa dos vértices
};
struct Vista { const unsigned char* p = nullptr; size_t n = 0; };  // memória EMPRESTADA (do numpy): quem chama a mantém viva e imóvel durante a chamada; nada é guardado
struct LoteBruto { Vista v, i, o; double desl[3] = {0, 0, 0}; };    // v: vértices (28 bytes cada), i: índices u4, o: DTYPE_OBJETO empacotado (n = objetos), desl: deslocamento
struct Cursor { size_t n = 0; int64_t ger = -1; };  // o que a thread de desenho já tirou da fila (a placa é uma visão da fila)
// Contadores de totais() (T30a2; T30b1 os leva ao Python em Estatisticas::nao_partidos e ::pecas_maiores_que_c). Definição: contam os sub-lotes ATUAIS da cena,
// recalculados a cada chamada (nunca acumulados), então acompanham as trocas.
//  - nao_partidos: sub-lotes com Dados::nao_partido. É o sub-lote que sobrou inteiro de um lote de entrada que não ladrilha (sem fronteira de peça) e passa de C.
//  - pecas_maiores_que_c: sub-lotes com Dados::peca_maior_que_c. É o sub-lote de uma só peça maior que C, vindo de um lote que ladrilha.
//  Depois de `sem` (atualizar/remover): as marcas só valem enquanto o sub-lote refeito ainda passa de C. Sub-lote que cai para C ou menos sai da conta
//  (nao_partidos nem pecas_maiores_que_c o contam mais); peça maior que C removida leva o sub-lote com ela e pecas_maiores_que_c cai; sub-lote refeito
//  marcado como peça única só segue contado se restar exatamente uma peça. limpar() zera os dois. Lote novo entra pelas mesmas regras de preparar().
struct Totais { size_t lotes = 0, triangulos = 0, vertices = 0, bytes = 0, nao_partidos = 0, pecas_maiores_que_c = 0; };  // bytes: memória da cópia compacta (T10); lotes: sub-lotes
// Instantâneo coerente (T30b1): ponteiros dos lotes, ger_ e ver_ do MESMO instante, tirados numa chamada só sob DadosCena::m_ (o motor lê sem segurar Motor::m_).
struct Instantaneo { std::vector<std::shared_ptr<Dados>> lotes; int64_t ger = 0, ver = 0; };

class DadosCena {
 public:
  int64_t adicionar_lote(const LoteBruto& lote);  // valida, copia e calcula a caixa fora do mutex; só o push é sob mutex (a ponte chama SEM o bloqueio do interpretador)
  // T09: remove, em todos os lotes, os objetos com GlobalId em `guids` OU em `lote_novo->o`, e acrescenta `lote_novo` (nullptr: só remove). Devolve a
  // sequência (sempre nova, estritamente crescente). Erro: std::invalid_argument e a cena fica intacta. Escolha (achado 4): lote com deslocamento
  // diferente do primeiro da cena é RECUSADO; `limpar()` zera a cena e libera o deslocamento.
  int64_t atualizar(const LoteBruto* lote_novo, std::set<std::string> guids);
  // ger_ muda só em limpar() (a placa recomeça do zero); atualizar/remover mudam só ver_ (T30b1: o reenvio por posição é do motor, T30b2).
  void limpar();
  int64_t geracao() { std::lock_guard<std::mutex> l(m_); return ger_; }
  std::shared_ptr<Dados> proximo(Cursor& c);  // próximo lote ainda não visto (nullptr se não há); devolve nullptr se a geração mudou: quem chama zera a placa
  bool caixa(double mn[3], double mx[3]);     // false se a cena está vazia
  Totais totais();
  Instantaneo instantaneo() { std::lock_guard<std::mutex> l(m_); return {lotes_, ger_, ver_}; }  // T30b1: o único caminho que lê ponteiros, ger_ e ver_ juntos
  std::vector<std::shared_ptr<Dados>> lotes() { return instantaneo().lotes; }  // T10: instantâneo imutável para a seleção (mutex só na cópia dos ponteiros)
  std::shared_ptr<Dados> lote(int64_t seq);   // lote `seq` (T09/T10; a ponte monta a tabela de objetos); std::invalid_argument se desconhecido ou já limpo
 private:
  std::vector<std::shared_ptr<Dados>> preparar(const LoteBruto& lote);  // valida e copia (sem o mutex), partindo em sub-lotes de até C; não publica; sempre ≥ 1
  void recalcular_caixa();                            // com m_
  std::mutex m_; std::vector<std::shared_ptr<Dados>> lotes_; int64_t seq_ = 0, ger_ = 0, ver_ = 0;  // ger_: sobe só em limpar(); ver_: sobe a cada mudança (atualizar refaz se mudou)
  double cmin_[3] = {1e30, 1e30, 1e30}, cmax_[3] = {-1e30, -1e30, -1e30};
};
}  // namespace obim
