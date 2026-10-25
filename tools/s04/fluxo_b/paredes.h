// SPDX-License-Identifier: AGPL-3.0-or-later
// Paredes IFC4 em C++ puro (contrato em CONTRATO.md). Sem nanobind e sem Qt: a ponte é ponte.cpp; a janela Qt usa esta classe.
// O modelo é um ifcopenshell::file próprio. Toda mutação passa por `criar` ou `alterar` (o diário): é o ponto do gancho de falha, do rollback e do desfazer/refazer.
// Escritor único: `trava()` é do chamador (a ponte e a janela); os comandos não a pegam sozinhos. `abrir` troca o modelo por um IFC4 (unidade e pavimento da base).
#pragma once
#include <ifcparse/file.h>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>
namespace fluxo_b {
using Lista = std::vector<std::string>;
using Chaves = std::vector<std::pair<std::string, std::string>>;  // "Pset.Prop" -> valor texto, na ordem dada
struct Ref { unsigned id; Ref(const express::base& b) : id(b.id()) {} };  // referência por número de linha: o refazer recria a entidade com o mesmo número
struct Rotulo { const ifcopenshell::declaration* tipo; std::string texto; };  // valor de tipo declarado em linha, ex.: IfcLabel('R60')
using Reais = std::vector<double>;
using Reais2 = std::vector<Reais>;
using Inteiros = std::vector<int64_t>;
using Textos = std::vector<std::string>;
using Refs = std::vector<Ref>;
// Valor de atributo portável (monostate = nulo). `int64_t` e não `int`: é o inteiro que a biblioteca do IfcOpenShell instancia (long no Linux, long long no Windows).
struct Valor : std::variant<std::monostate, std::string, double, int64_t, Ref, Refs, Rotulo, Reais, Reais2, ifcopenshell::enumeration_reference, bool, boost::logic::tribool, Inteiros, Textos> {
    using variant::variant;
    Valor(const char* s) : variant(std::string(s)) {}  // sem isto, const char* viraria bool
    Valor(const express::base& b) : variant(Ref(b)) {}  // base tem operator bool: sem isto viraria número
    Valor(const std::vector<express::base>& v) : variant(Refs(v.begin(), v.end())) {}
};
using Atributos = std::vector<std::pair<int, Valor>>;  // só os índices dados; o resto fica nulo (e os derivados `*`)
struct ModeloOcupado : std::runtime_error { using std::runtime_error::runtime_error; };  // `espera=0` e a trava está com outro comando
struct Ultimo { Lista criados, alterados, apagados, geometria; };
class Paredes {
  public:
    Paredes();
    Lista criar_tipo(const std::string& nome, const std::vector<double>& camadas_m);
    Lista criar_parede(const std::string& tipo, double comprimento, double altura, double espessura) { return criar_paredes_lote(tipo, comprimento, altura, espessura, 1); }
    Lista criar_paredes_lote(const std::string& tipo, double comprimento, double altura, double espessura, int quantidade);
    Lista editar_propriedades(const std::string& alvo, const std::string* nome, const Chaves& propriedades);
    Lista mudar_comprimento(const std::string& alvo, double comprimento);
    Lista desfazer() { return voltar(true); }
    Lista refazer() { return voltar(false); }
    const Ultimo& ultimo() const { return ultimo_; }
    int pode_desfazer() const { return int(historico_.size()); }
    int pode_refazer() const { return int(refazer_.size()); }
    int contar(const std::string* classe) const;  // com subtipos; nulo = tudo; std::invalid_argument se a classe não existe
    void gravar(const std::string& arquivo) const;
    void definir_falha(int k) { falha_ = k; }
    void abrir(const std::string& arquivo);  // troca o modelo pelo IFC4 dado (std::invalid_argument se não abre; o anterior fica intacto) e zera pilhas, ultimo, grade e gancho
    int produtos_base() const { return produtos_base_; }  // IfcProduct com representação logo depois do abrir
    ifcopenshell::file* arquivo() { return f_.get(); }  // A janela lê o modelo (malha e painel) com a trava do chamador; vale até o próximo `abrir`
    Lista copiar_atributo(unsigned destino, unsigned origem, const std::string& atributo);  // gancho de teste: um comando que passa por `ler`
    std::mutex& trava() { return trava_; }
    std::unique_lock<std::mutex> pegar(bool esperar);  // espera a trava ou, sem esperar, lança ModeloOcupado na hora
  private:
    struct Passo { bool criado; unsigned id; const ifcopenshell::declaration* decl; Atributos attrs; int idx; Valor antes, depois; };
    struct Registro { std::vector<Passo> passos; Lista guids, alterados, geometria; };
    template <class F> Lista transacao(F&& corpo);
    express::base contexto(const char* tipo, const char* ident, const char* vista, bool diario);  // o subcontexto da base ou, se faltar, criado (com o contexto pai)
    express::base apoio(unsigned& id, const char* classe, const Reais& v);  // ponto/direção compartilhado: o 1o comando que precisa cria (no diário), os outros reaproveitam
    double un(double metros) const { return esc_ == 1.0 ? metros : std::round(metros / esc_ * 1e6) / 1e6; }  // metros -> unidade do projeto
    express::base cru(const char* classe, Atributos attrs);  // sem diário: só o esqueleto do modelo
    express::base criar(const char* classe, Atributos attrs);
    void alterar(const express::base& e, int idx, Valor novo);
    void mutar();
    Valor ler(const express::base& e, int idx) const;
    void aplicar(const express::base& e, int idx, const Valor& v);
    void desfazer_passos(const Registro& r);
    void refazer_passos(const Registro& r);
    Lista voltar(bool desfazer);
    express::base por_id(unsigned id) const { return f_->instance_by_id(int(id)); }
    express::base achar(const std::string& guid) const;  // nulo se não existe
    express::base achar_id(unsigned id) const;  // nulo se não existe
    express::base pavimento() const;  // o IfcBuildingStorey de menor Name (nulo se não há)
    express::base achar_wall(const std::string& guid) const;
    express::base achar_tipo(const std::string& nome) const;
    void relacionar(const char* classe, const express::base& alvo, const std::vector<express::base>& novos);  // acrescenta à relação do alvo (ou cria a 1a)
    std::unique_ptr<ifcopenshell::file> f_;
    std::vector<Registro> historico_, refazer_;
    Registro reg_;
    Ultimo ultimo_, em_curso_;
    unsigned origem_ = 0, dirz_ = 0, dirx_ = 0;  // apoio compartilhado das paredes (ver `apoio`)
    std::mutex trava_;
    double esc_ = 1.0;  // tamanho da unidade de comprimento do projeto em metros
    int g_ = 0, falha_ = 0, falha_ativa_ = 0, mutacoes_ = 0, produtos_base_ = 0;  // g_: contador da grade (desfazer não o devolve)
};
}  // namespace fluxo_b
