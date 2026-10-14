// SPDX-License-Identifier: AGPL-3.0-or-later
// Paredes IFC4 em C++ puro (S04-T13; CONTRATO.md; LOTE_OPUS_9 §1.1, §4 etapa 3): entidades montadas à mão (no C++ não há camada `api`). Diário de desfazer: cada mutação
// (`criar` ou `alterar`) guarda o suficiente para voltar e para refazer com os MESMOS números de linha (referências por número, não por ponteiro).
#include "paredes.h"
#include <ifcparse/express.h>
#include <ifcparse/global_id.h>
#include <algorithm>
#include <clocale>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <stdexcept>
namespace fluxo_b {
using ifcopenshell::file;
using express::base;
using Bases = std::vector<base>;
namespace {
const ifcopenshell::schema_definition& S() { return *ifcopenshell::schema_by_name("IFC4"); }
std::string gid() { return std::string(ifcopenshell::global_id()); }
Valor enu(const char* tipo, const char* v) { auto* e = S().declaration_by_name(tipo)->as_enumeration_type(); return ifcopenshell::enumeration_reference(e, e->lookup_enum_offset(v)); }
bool pos(double x) { return std::isfinite(x) && x > 0; }
[[noreturn]] void erro(const std::string& m) { throw std::invalid_argument(m); }
std::string texto(const base& e, int i) { std::string s = e.get_attribute_value(i); return s; }
Bases lista(const base& e, int i) { Bases b = e.get_attribute_value(i); return b; }
base ref(const base& e, int i) { base b = e.get_attribute_value(i); return b; }
struct LocalC {  // número com ponto decimal mesmo com a localidade do processo em pt_BR; devolve a localidade como estava
    std::string velha;
    LocalC() { const char* l = std::setlocale(LC_NUMERIC, nullptr); velha = l ? l : "C"; std::setlocale(LC_NUMERIC, "C"); }
    ~LocalC() { std::setlocale(LC_NUMERIC, velha.c_str()); }
};
}  // namespace
base Paredes::cru(const char* classe, Atributos a) { base e = f_->create(S().declaration_by_name(classe)); for (auto& [i, v] : a) aplicar(e, i, v); return e; }
Paredes::Paredes() : f_(std::make_unique<file>(ifcopenshell::schema_by_name("IFC4"))) {
    base origem = cru("IfcCartesianPoint", {{0, Reais{0, 0, 0}}}), dz = cru("IfcDirection", {{0, Reais{0, 0, 1}}}), dx = cru("IfcDirection", {{0, Reais{1, 0, 0}}});
    base wcs = cru("IfcAxis2Placement3D", {{0, origem}, {1, dz}, {2, dx}});
    base wcs2 = cru("IfcAxis2Placement2D", {{0, cru("IfcCartesianPoint", {{0, Reais{0, 0}}})}, {1, cru("IfcDirection", {{0, Reais{1, 0}}})}});
    base modelo = cru("IfcGeometricRepresentationContext", {{1, "Model"}, {2, int64_t{3}}, {3, 1e-5}, {4, wcs}}), plano = cru("IfcGeometricRepresentationContext", {{1, "Plan"}, {2, int64_t{2}}, {3, 1e-5}, {4, wcs2}});
    base corpo = cru("IfcGeometricRepresentationSubContext", {{0, "Body"}, {1, "Model"}, {6, modelo}, {8, enu("IfcGeometricProjectionEnum", "MODEL_VIEW")}});
    base eixo = cru("IfcGeometricRepresentationSubContext", {{0, "Axis"}, {1, "Plan"}, {6, plano}, {8, enu("IfcGeometricProjectionEnum", "GRAPH_VIEW")}});
    Bases un;
    for (auto [u, n] : {std::pair{"AREAUNIT", "SQUARE_METRE"}, {"VOLUMEUNIT", "CUBIC_METRE"}, {"LENGTHUNIT", "METRE"}}) un.push_back(cru("IfcSIUnit", {{1, enu("IfcUnitEnum", u)}, {3, enu("IfcSIUnitName", n)}}));
    Bases cadeia{cru("IfcProject", {{0, gid()}, {2, "Projeto"}, {7, Bases{modelo, plano}}, {8, cru("IfcUnitAssignment", {{0, un}})}})};
    for (auto [c, n] : {std::pair{"IfcSite", "Terreno"}, {"IfcBuilding", "Edificio"}, {"IfcBuildingStorey", "Pavimento 1"}}) cadeia.push_back(cru(c, {{0, gid()}, {2, n}}));
    for (size_t i = 1; i < cadeia.size(); ++i) cru("IfcRelAggregates", {{0, gid()}, {4, cadeia[i - 1]}, {5, Bases{cadeia[i]}}});
    corpo_ = corpo.id(), eixo_ = eixo.id(), pav_ = cadeia.back().id(), origem_ = origem.id(), dirz_ = dz.id(), dirx_ = dx.id();
}
void Paredes::aplicar(const base& e0, int idx, const Valor& v) {
    base e = e0;
    std::visit([&](const auto& x) {
        using T = std::decay_t<decltype(x)>;
        size_t i = size_t(idx);
        if constexpr (std::is_same_v<T, std::monostate>) e.unset_attribute_value(i);
        else if constexpr (std::is_same_v<T, Ref>) e.set_attribute_value(i, por_id(x.id));
        else if constexpr (std::is_same_v<T, Refs>) { Bases l; for (auto r : x) l.push_back(por_id(r.id)); e.set_attribute_value(i, l); }
        else if constexpr (std::is_same_v<T, Rotulo>) { base t = f_->create(x.tipo); t.set_attribute_value(0, x.texto); e.set_attribute_value(i, t); }
        else e.set_attribute_value(i, x);
    }, v);
}
Valor Paredes::ler(const base& e, int idx) const {
    auto a = e.get_attribute_value(size_t(idx));
    switch (a.type()) {
        case ifcopenshell::Argument_STRING: { std::string s = a; return s; }
        case ifcopenshell::Argument_DOUBLE: { double d = a; return d; }
        case ifcopenshell::Argument_ENTITY_INSTANCE: { base b = a; return b.id() ? Valor(Ref(b)) : Valor(Rotulo{&b.declaration(), texto(b, 0)}); }
        case ifcopenshell::Argument_AGGREGATE_OF_ENTITY_INSTANCE: return Valor(lista(e, idx));
        case ifcopenshell::Argument_AGGREGATE_OF_AGGREGATE_OF_DOUBLE: { Reais2 r = a; return r; }
        default: return {};
    }
}
void Paredes::mutar() {  // o gancho de teste: a k-ésima mutação do próximo comando de edição falha ANTES de mexer
    if (falha_ativa_ && ++mutacoes_ == falha_ativa_) throw std::runtime_error("falha injetada na mutação " + std::to_string(mutacoes_));
}
base Paredes::criar(const char* classe, Atributos a) {
    mutar();
    const auto* d = S().declaration_by_name(classe);
    base e = f_->create(d);
    reg_.passos.push_back({true, e.id(), d, std::move(a), 0, {}, {}});  // registrado antes dos atributos: um erro no meio ainda desfaz a entidade
    for (auto& [i, v] : reg_.passos.back().attrs) aplicar(e, i, v);
    return e;
}
void Paredes::alterar(const base& e, int idx, Valor novo) { mutar(); reg_.passos.push_back({false, e.id(), nullptr, {}, idx, ler(e, idx), novo}); aplicar(e, idx, novo); }
void Paredes::desfazer_passos(const Registro& r) {  // do último para o primeiro: restaura o que mudou e remove o que nasceu
    for (auto p = r.passos.rbegin(); p != r.passos.rend(); ++p) p->criado ? f_->remove_entity(por_id(p->id)) : aplicar(por_id(p->id), p->idx, p->antes);
}
void Paredes::refazer_passos(const Registro& r) {  // 1o cria todas (mesmos números), depois põe os atributos: referências adiante também valem
    for (auto& p : r.passos) if (p.criado) f_->create(p.decl, int(p.id));
    for (auto& p : r.passos) { if (p.criado) for (auto& [i, v] : p.attrs) aplicar(por_id(p.id), i, v); else aplicar(por_id(p.id), p.idx, p.depois); }
}
template <class F> Lista Paredes::transacao(F&& corpo) {  // uma transação = um registro; erro (de entrada ou injetado) = volta tudo
    falha_ativa_ = std::exchange(falha_, 0), mutacoes_ = 0, reg_ = {}, em_curso_ = {};
    int g0 = g_;
    try { corpo(); } catch (...) { falha_ativa_ = 0, g_ = g0; desfazer_passos(reg_); reg_ = {}; throw; }
    falha_ativa_ = 0;
    for (const Lista* l : {&em_curso_.criados, &em_curso_.alterados, &em_curso_.apagados})
        for (auto& g : *l) if (std::find(reg_.guids.begin(), reg_.guids.end(), g) == reg_.guids.end()) reg_.guids.push_back(g);
    reg_.alterados = em_curso_.alterados, reg_.geometria = em_curso_.geometria, ultimo_ = std::move(em_curso_);
    historico_.push_back(std::move(reg_)), refazer_.clear();
    return historico_.back().guids;
}
base Paredes::achar(const std::string& g) const { try { return f_->instance_by_guid(g); } catch (...) { return {}; } }
base Paredes::achar_wall(const std::string& g) const {
    base e = achar(g);
    if (!e || !e.declaration().is("IfcWall")) erro("alvo inexistente ou que não é uma parede: " + g);
    return e;
}
base Paredes::achar_tipo(const std::string& nome) const { for (auto& t : f_->instances_by_type("IfcWallType")) if (texto(t, 2) == nome) return t; return {}; }
void Paredes::relacionar(const char* classe, const base& alvo, const Bases& novos) {
    for (auto& r : f_->instances_by_type(classe)) {
        if (ref(r, 5) != alvo) continue;
        Bases todos = lista(r, 4);
        return todos.insert(todos.end(), novos.begin(), novos.end()), alterar(r, 4, todos);
    }
    criar(classe, {{0, gid()}, {4, novos}, {5, alvo}});
}
Lista Paredes::criar_tipo(const std::string& nome, const std::vector<double>& camadas) {
    return transacao([&] {
        if (nome.empty() || camadas.empty() || !std::all_of(camadas.begin(), camadas.end(), pos)) erro("tipo inválido: nome vazio ou camada ausente, zero, negativa ou não finita");
        if (achar_tipo(nome)) erro("já existe um tipo com o nome " + nome);
        Bases cams;
        for (size_t i = 0; i < camadas.size(); ++i)
            cams.push_back(criar("IfcMaterialLayer", {{0, criar("IfcMaterial", {{0, nome + " camada " + std::to_string(i + 1)}})}, {1, camadas[i]}}));
        base conj = criar("IfcMaterialLayerSet", {{0, cams}, {1, nome}});
        base t = criar("IfcWallType", {{0, gid()}, {2, nome}, {9, enu("IfcWallTypeEnum", "NOTDEFINED")}});
        criar("IfcRelAssociatesMaterial", {{0, gid()}, {4, Bases{t}}, {5, conj}});
        em_curso_.criados = {texto(t, 0)};
    });
}
Lista Paredes::criar_paredes_lote(const std::string& tipo, double c, double h, double e, int n) {
    return transacao([&] {
        base t = achar_tipo(tipo), conj;
        if (!t || !pos(c) || !pos(h) || !pos(e) || n < 1) erro("parede inválida: tipo inexistente, medida não positiva ou quantidade menor que 1");
        for (auto& s : f_->instances_by_type("IfcMaterialLayerSet")) if (texto(s, 1) == tipo) conj = s;
        base corpo = por_id(corpo_), eixo = por_id(eixo_), dz = por_id(dirz_), dx = por_id(dirx_), origem = por_id(origem_);
        Bases ws;
        for (int k = 0; k < n; ++k) {
            int g = g_ + k;
            base pl = criar("IfcLocalPlacement", {{1, criar("IfcAxis2Placement3D", {{0, criar("IfcCartesianPoint", {{0, Reais{(g % 50) * 5.0, (g / 50) * 4.0, 0.0}}})}, {1, dz}, {2, dx}})}});
            base curva = criar("IfcIndexedPolyCurve", {{0, criar("IfcCartesianPointList2D", {{0, Reais2{{0, 0}, {0, e}, {c, e}, {c, 0}, {0, 0}}}})}});
            base perfil = criar("IfcArbitraryClosedProfileDef", {{0, enu("IfcProfileTypeEnum", "AREA")}, {2, curva}});
            base sol = criar("IfcExtrudedAreaSolid", {{0, perfil}, {1, criar("IfcAxis2Placement3D", {{0, origem}, {1, dz}, {2, dx}})}, {2, dz}, {3, h}});
            base rb = criar("IfcShapeRepresentation", {{0, corpo}, {1, "Body"}, {2, "SweptSolid"}, {3, Bases{sol}}});
            base ca = criar("IfcIndexedPolyCurve", {{0, criar("IfcCartesianPointList2D", {{0, Reais2{{0, 0}, {c, 0}}}})}});
            base ra = criar("IfcShapeRepresentation", {{0, eixo}, {1, "Axis"}, {2, "Curve2D"}, {3, Bases{ca}}});
            base w = criar("IfcWall", {{0, gid()}, {2, "Parede"}, {5, pl}, {6, criar("IfcProductDefinitionShape", {{2, Bases{rb, ra}}})}});
            base uso = criar("IfcMaterialLayerSetUsage", {{0, conj}, {1, enu("IfcLayerSetDirectionEnum", "AXIS2")}, {2, enu("IfcDirectionSenseEnum", "POSITIVE")}, {3, 0.0}});
            criar("IfcRelAssociatesMaterial", {{0, gid()}, {4, Bases{w}}, {5, uso}});
            ws.push_back(w);
        }
        g_ += n;
        relacionar("IfcRelDefinesByType", t, ws);
        relacionar("IfcRelContainedInSpatialStructure", por_id(pav_), ws);
        for (auto& w : ws) em_curso_.criados.push_back(texto(w, 0));
        em_curso_.geometria = em_curso_.criados;
    });
}
Lista Paredes::editar_propriedades(const std::string& alvo, const std::string* nome, const Chaves& props) {
    return transacao([&] {
        base w = achar_wall(alvo);
        if (nome && nome->empty()) erro("nome vazio");
        for (auto& [chave, v] : props) { auto p = chave.find('.'); if (p == std::string::npos || p == 0 || p + 1 == chave.size()) erro("propriedade fora do formato Pset.Prop: " + chave); }
        if (nome) alterar(w, 2, *nome);
        const auto* rotulo = S().declaration_by_name("IfcLabel");
        for (auto& [chave, v] : props) {
            std::string pset = chave.substr(0, chave.find('.')), prop = chave.substr(chave.find('.') + 1);
            Valor valor = Rotulo{rotulo, v};
            base ps, pr;
            for (auto& r : f_->instances_by_reference(int(w.id())))
                if (r.declaration().is("IfcRelDefinesByProperties") && texto(ref(r, 5), 2) == pset) ps = ref(r, 5);
            if (ps) for (auto& p : lista(ps, 4)) if (texto(p, 0) == prop) pr = p;
            if (pr) { alterar(pr, 2, valor); continue; }
            base nova = criar("IfcPropertySingleValue", {{0, prop}, {2, valor}});
            if (ps) { Bases todas = lista(ps, 4); todas.push_back(nova); alterar(ps, 4, todas); continue; }
            ps = criar("IfcPropertySet", {{0, gid()}, {2, pset}, {4, Bases{nova}}});
            criar("IfcRelDefinesByProperties", {{0, gid()}, {4, Bases{w}}, {5, ps}});
        }
        em_curso_.alterados = {alvo};
    });
}
Lista Paredes::mudar_comprimento(const std::string& alvo, double c) {
    return transacao([&] {
        base w = achar_wall(alvo);
        if (!pos(c)) erro("comprimento inválido");
        base ps = ref(w, 6);
        if (!ps) erro("a parede não tem representação");
        std::vector<std::pair<base, Reais2>> listas;  // (lista de pontos, pontos) do Body e do Axis; todos os pontos com x > 0 passam a x = c
        bool corpo = false;
        for (auto& r : lista(ps, 2)) {
            Bases itens = lista(r, 3);
            if (itens.size() != 1) continue;
            base cv = itens[0], l;
            if (texto(r, 1) == "Body") {
                if (!cv.declaration().is("IfcExtrudedAreaSolid")) erro("o Body da parede não é um sólido extrudado");
                cv = ref(ref(cv, 0), 2), corpo = true;
            }
            if (!cv.declaration().is("IfcIndexedPolyCurve")) erro("curva da parede não reconhecida");
            l = ref(cv, 0);
            Reais2 pts = l.get_attribute_value(0);
            for (auto& p : pts) if (p[0] > 0) p[0] = c;
            listas.emplace_back(l, pts);
        }
        if (!corpo) erro("a parede não tem representação Body extrudada");
        for (auto& [l, pts] : listas) alterar(l, 0, pts);
        em_curso_.alterados = em_curso_.geometria = {alvo};
    });
}
Lista Paredes::voltar(bool desfazer) {
    auto &de = desfazer ? historico_ : refazer_, &para = desfazer ? refazer_ : historico_;
    ultimo_ = {};
    if (de.empty()) return {};
    Registro reg = std::move(de.back());
    de.pop_back();
    std::vector<bool> antes;
    for (auto& g : reg.guids) antes.push_back(bool(achar(g)));
    desfazer ? desfazer_passos(reg) : refazer_passos(reg);
    for (size_t i = 0; i < reg.guids.size(); ++i) {
        base e = achar(reg.guids[i]);
        if (e && !antes[i]) ultimo_.criados.push_back(reg.guids[i]);
        if (!e && antes[i]) ultimo_.apagados.push_back(reg.guids[i]);
        if (e && e.declaration().is("IfcProduct") && ref(e, 6) && (std::find(reg.geometria.begin(), reg.geometria.end(), reg.guids[i]) != reg.geometria.end() || !antes[i])) ultimo_.geometria.push_back(reg.guids[i]);
    }
    ultimo_.alterados = reg.alterados;
    Lista guids = reg.guids;
    return para.push_back(std::move(reg)), guids;
}
int Paredes::contar(const std::string* classe) const {
    if (!classe) { int n = 0; for (auto it = f_->begin(); it != f_->end(); ++it) ++n; return n; }
    const ifcopenshell::declaration* d = nullptr;
    try { d = S().declaration_by_name(*classe); } catch (...) {}
    if (!d) erro("classe IFC inexistente: " + *classe);
    return int(f_->instances_by_type(d).size());
}
void Paredes::gravar(const std::string& arquivo) const {
    namespace fs = std::filesystem;
    LocalC local;
    fs::path p(std::u8string(arquivo.begin(), arquivo.end()));
    if (p.has_parent_path()) fs::create_directories(p.parent_path());
    std::ofstream o(p, std::ios::binary);
    if (!o) throw std::runtime_error("não consegui gravar " + arquivo);
    o << *f_;
}
}  // namespace fluxo_b
