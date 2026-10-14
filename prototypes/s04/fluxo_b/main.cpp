// SPDX-License-Identifier: AGPL-3.0-or-later
// Executável do fluxo B (S04-T14c; CONTRATO.md, Parte 2): roteiro R na janela Qt Widgets sobre `Paredes` e o núcleo C++ puro, `medicao.json` igual ao do fluxo A, autotestes sem janela. Sem Python.
// Só `criar_paredes_lote` roda numa std::thread (do comando); os outros comandos, o painel e a pintura ficam na thread da janela, que segue tratando eventos durante o lote.
#include "janela.h"
#include <ifcparse/schemas/Ifc4.h>
#include <QJsonArray>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <locale.h>
#include <map>
#include <set>
#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  define NOMINMAX
#  include <windows.h>
#  include <psapi.h>
#endif
using namespace fluxo_b;
namespace fs = std::filesystem;
using J = QJsonObject;
namespace {
QJsonArray arr(const Lista& v) { QJsonArray a; for (auto& s : v) a.append(QString::fromStdString(s)); return a; }
void resultado(const J& j) { std::cout << "RESULTADO " << QJsonDocument(j).toJson(QJsonDocument::Compact).toStdString() << std::endl; }
struct Lote { std::vector<unsigned char> v, o; std::vector<uint32_t> i; };
// Malha chapada como a do fluxo A: 3 vértices por triângulo, normal da face, cor do estilo; sem geometria o GlobalId fica fora. `incl` = os que entraram.
bool montar(ifcopenshell::file* f, const Lista& guids, Lote& L, obim::LoteBruto& b, Lista& incl) {
    auto mal = obim::malhas_do_arquivo(f, guids);
    auto poe = [](std::vector<unsigned char>& d, const void* p, size_t n) { d.insert(d.end(), (const unsigned char*)p, (const unsigned char*)p + n); };
    for (auto& g : guids) {
        const obim::Malha& m = mal.at(g);
        if (m.idx.empty()) continue;
        const uint32_t pv = uint32_t(L.v.size() / obim::BYTES_VERTICE);
        float lo[3] = {1e30f, 1e30f, 1e30f}, hi[3] = {-1e30f, -1e30f, -1e30f};
        unsigned char cor[4];
        for (int c = 0; c < 4; ++c) cor[c] = (unsigned char)std::clamp(std::nearbyint(m.cor[c] * 255), 0.0, 255.0);
        for (size_t k = 0; k + 2 < m.idx.size(); k += 3) {
            double p[3][3], u[3], w[3], n[3];
            for (int a = 0; a < 3; ++a) for (int c = 0; c < 3; ++c) p[a][c] = m.pos[3 * size_t(m.idx[k + a]) + c];
            for (int c = 0; c < 3; ++c) u[c] = p[1][c] - p[0][c], w[c] = p[2][c] - p[0][c];
            n[0] = u[1] * w[2] - u[2] * w[1], n[1] = u[2] * w[0] - u[0] * w[2], n[2] = u[0] * w[1] - u[1] * w[0];
            const double l = std::max(std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]), 1e-12);
            for (int a = 0; a < 3; ++a) {
                float pf[3], nf[3];
                for (int c = 0; c < 3; ++c) pf[c] = float(p[a][c]), nf[c] = float(n[c] / l), lo[c] = std::min(lo[c], pf[c]), hi[c] = std::max(hi[c], pf[c]);
                poe(L.v, pf, 12), poe(L.v, nf, 12), poe(L.v, cor, 4), L.i.push_back(uint32_t(L.v.size() / obim::BYTES_VERTICE - 1));
            }
        }
        const uint32_t nv = uint32_t(L.v.size() / obim::BYTES_VERTICE) - pv;
        unsigned char r[66] = {};  // DTYPE_OBJETO empacotado: id_step 0, GlobalId, índices e vértices (começam juntos), caixa
        std::memcpy(r + 4, g.data(), std::min<size_t>(22, g.size())), std::memcpy(r + 26, &pv, 4), std::memcpy(r + 30, &nv, 4), std::memcpy(r + 34, &pv, 4), std::memcpy(r + 38, &nv, 4);
        std::memcpy(r + 42, lo, 12), std::memcpy(r + 54, hi, 12), poe(L.o, r, 66), incl.push_back(g);
    }
    if (incl.empty()) return false;
    b.v = {L.v.data(), L.v.size() / obim::BYTES_VERTICE}, b.i = {reinterpret_cast<const unsigned char*>(L.i.data()), L.i.size()}, b.o = {L.o.data(), L.o.size() / 66};
    return true;
}
struct Det { Lista guids, criados, alterados, apagados, geometria; int64_t seq = -1; double t0 = 0, t_cmd = 0, t_painel = -1; std::string thread_cmd; };
struct Fluxo {
    Paredes P;
    Tela* t = nullptr;
    fs::path saida;
    std::string sel, painel = "(nada selecionado)", ult, arq_ifc;
    std::map<std::string, Lista> passos;  // GlobalIds criados por passo (alvo {"passo": id})
    // Trava do modelo da abertura da transação até Cena.atualizar voltar (regra 7); a cena só recebe a malha do que mudou. Pilha vazia (desfazer/refazer): nada a enviar.
    template <class F> void editar(Det& d, F&& corpo) {
        {
            auto l = P.pegar(true);
            d.guids = corpo();
            const Ultimo& u = P.ultimo();
            d.criados = u.criados, d.alterados = u.alterados, d.apagados = u.apagados, d.geometria = u.geometria;
            if (!d.guids.empty()) {
                Lote L; obim::LoteBruto b; Lista incl;
                const bool tem = montar(P.arquivo(), d.geometria, L, b, incl);
                d.seq = t->vp.atualizar(tem ? &b : nullptr, std::set<std::string>(d.apagados.begin(), d.apagados.end()));
            }
        }
        d.t_cmd = agora();
    }
    std::string alvo(const QJsonObject& c, int r) {
        QJsonValue a = c["alvo"];
        if (a.isString()) return a.toString() == "ultimo" ? ult : a.toString().toStdString();
        const Lista& l = passos[a.toObject()["passo"].toString().toStdString()];
        const int k = a.toObject().contains("k") ? a.toObject()["k"].toInt() : r;
        if (k < 0 || k >= int(l.size())) throw std::invalid_argument("alvo inválido: o passo não criou tantos elementos");
        return l[k];
    }
    Det executar(const QJsonObject& c, int r) {
        const std::string nome = c["cmd"].toString().toStdString();
        auto s = [&](const char* k) { return c[k].toString().toStdString(); };
        auto n = [&](const char* k) { return c[k].toDouble(); };
        Det d;
        d.t0 = agora();
        if (nome == "criar_tipo") {
            std::vector<double> cam;
            for (auto x : c["camadas_m"].toArray()) cam.push_back(x.toDouble());
            editar(d, [&] { return P.criar_tipo(s("nome"), cam); });
        } else if (nome == "criar_parede") editar(d, [&] { return P.criar_parede(s("tipo"), n("comprimento"), n("altura"), n("espessura")); });
        else if (nome == "criar_paredes_lote") {  // o comando inteiro (modelo, malhas, lote, atualizar) na thread do comando; a janela só trata eventos até ela terminar
            std::atomic<bool> fim{false};
            std::exception_ptr ex;
            std::thread th([&] {
                d.thread_cmd = id_thread();
                try { editar(d, [&] { return P.criar_paredes_lote(s("tipo"), n("comprimento"), n("altura"), n("espessura"), c["quantidade"].toInt()); }); } catch (...) { ex = std::current_exception(); }
                fim = true;
            });
            t->aguardar([&] { return fim.load(); }, 1e12);
            th.join();
            if (ex) std::rethrow_exception(ex);
        } else if (nome == "editar_propriedades") {
            const std::string a = alvo(c, r);
            const bool tem = c["nome"].isString();
            std::string nm = c["nome"].toString().replace("{r}", QString::number(r)).toStdString();
            Chaves ch;
            for (auto& k : c["propriedades"].toObject().keys()) ch.emplace_back(k.toStdString(), c["propriedades"].toObject()[k].toString().toStdString());
            sel = a;
            editar(d, [&] { return P.editar_propriedades(a, tem ? &nm : nullptr, ch); });
            painel = painel_do(P, sel, painel), t->mostrar(painel), d.t_painel = agora();
        } else if (nome == "mudar_comprimento") editar(d, [&] { return P.mudar_comprimento(alvo(c, r), n("comprimento")); });
        else if (nome == "desfazer" || nome == "refazer") {
            editar(d, [&] { return nome == "desfazer" ? P.desfazer() : P.refazer(); });
            if (!sel.empty()) painel = painel_do(P, sel, painel), t->mostrar(painel);
        } else if (nome == "abrir") {
            auto l = P.pegar(true);
            auto* f = P.arquivo();
            Lista todos;
            for (auto& e : f->instances_by_type(f->schema()->declaration_by_name("IfcProduct"))) if (!e.get_attribute_value(6).isNull()) todos.push_back(txt(e, 0));
            for (size_t i = 0; i < todos.size(); i += 500) {  // em blocos de 500, como o fluxo A
                Lote L; obim::LoteBruto b; Lista incl;
                if (montar(f, Lista(todos.begin() + i, todos.begin() + std::min(i + 500, todos.size())), L, b, incl)) d.seq = t->vp.adicionar_lote(b), d.guids.insert(d.guids.end(), incl.begin(), incl.end());
            }
        } else if (nome == "gravar") P.gravar((saida / s("arquivo")).string()), arq_ifc = (saida / s("arquivo")).string();
        else if (nome == "selecionar") {
            auto xy = [&](const char* k, int dim) { return c[k].isString() ? dim / 2.0 : c[k].toDouble(); };
            auto g = t->vp.selecionar(xy("x", t->cont()->width()), xy("y", t->cont()->height()));
            sel = g ? *g : "", d.guids = g ? Lista{*g} : Lista{};
            painel = painel_do(P, sel, painel), t->mostrar(painel);
        } else if (nome == "esperar") t->aguardar([] { return false; }, n("ms"));
        else if (nome == "enquadrar") t->vp.enquadrar();
        else if (nome == "animar_orbita") t->vp.animar_orbita(n("graus_por_s"));
        else if (nome == "parar_animacao") t->vp.parar_animacao();
        else if (nome == "orbitar") t->vp.orbitar(n("dx"), n("dy"));
        else if (nome == "camera_mover") t->vp.mover(n("dx"), n("dy"));
        else if (nome == "aproximar") t->vp.aproximar(n("fator"));
        else throw std::invalid_argument("comando desconhecido: " + nome);
        if (d.t_cmd == 0) d.t_cmd = agora();
        if (!d.guids.empty()) ult = d.guids.back();
        return d;
    }
};
double pct(std::vector<double> v, double q) {  // percentil linear (o padrão do numpy)
    std::sort(v.begin(), v.end());
    const double k = q / 100 * double(v.size() - 1);
    const size_t a = size_t(k);
    return a + 1 < v.size() ? v[a] + (v[a + 1] - v[a]) * (k - double(a)) : v[a];
}
J metas(const std::map<std::string, QJsonArray>& R) {  // M2, M2b, M3, M4 e M5 dos tempos brutos (a mesma conta do fluxo A); M1 e M6 ficam para o medir_s04
    auto ser = [&](const char* id, const char* fim) { std::vector<double> v; for (auto x : R.at(id)) v.push_back(x.toObject()[fim].toDouble() - x.toObject()["t0_ms"].toDouble()); return v; };
    auto meta = [&](const char* id, std::vector<double> v, double lim) { return J{{"passo", id}, {"n", int(v.size())}, {"mediana_ms", pct(v, 50)}, {"p95_ms", pct(v, 95)}, {"max_ms", *std::max_element(v.begin(), v.end())}, {"limite_ms", lim}, {"ok", pct(v, 95) < lim}}; };
    auto tempos = [&](const char* id) { std::vector<double> v; for (auto x : R.at(id)[0].toObject()["relogio"].toArray()) v.push_back(x.toArray()[0].toDouble()); return v; };
    auto maior = [](const std::vector<double>& v) { double m = 0; for (size_t i = 1; i < v.size(); ++i) m = std::max(m, v[i] - v[i - 1]); return m; };
    const J lote = R.at("5b")[0].toObject();
    const double ini = lote["t0_ms"].toDouble(), fim = lote["t_quadro_ms"].toDouble();
    std::vector<double> t = tempos("5b"), tp = tempos("4c"), lim{ini};
    lim.insert(lim.end(), t.begin(), t.end()), lim.push_back(fim);
    QJsonArray jan;
    int mn = 1 << 30;
    for (int k = 0; k < int((fim - ini) / 1000); ++k) { int q = int(std::count_if(t.begin(), t.end(), [&](double x) { return x >= ini + 1000 * k && x < ini + 1000 * (k + 1); })); jan.append(q), mn = std::min(mn, q); }
    const double mi = maior(lim), par = tp.size() > 1 ? maior(tp) : 0.0;
    const bool ok = mn >= 20 && (jan.size() || double(t.size()) >= 20 * (fim - ini) / 1000) && mi < 200 && mi <= 3 * std::max(33.3, par);
    return J{{"M2", meta("3", ser("3", "t_quadro_ms"), 200)}, {"M2b", meta("4b", ser("4b", "t_quadro_ms"), 200)}, {"M3", meta("4a", ser("4a", "t_painel_ms"), 50)}, {"M4", meta("5b", ser("5b", "t_quadro_ms"), 20000)},
             {"M5", J{{"passo", "5b"}, {"n", int(t.size())}, {"limite_ms", 200}, {"quadros_por_janela_min", jan.size() ? QJsonValue(mn) : QJsonValue()}, {"janelas", jan}, {"maior_intervalo_ms", mi}, {"maior_intervalo_parado_ms", par}, {"ok", ok}}},
             {"M1", QJsonValue()}, {"M6", QJsonValue()}};
}
int roteiro(int argc, char** argv, const std::map<std::string, std::string>& o) {
    auto opc = [&](const char* k) { auto i = o.find(k); return i == o.end() ? std::string() : i->second; };
    QJsonParseError pe;
    std::ifstream in(opc("--roteiro"), std::ios::binary);
    const QJsonDocument doc = in ? QJsonDocument::fromJson(QByteArray::fromStdString(std::string(std::istreambuf_iterator<char>(in), {})), &pe) : QJsonDocument();
    if (!doc.isObject() || !doc.object()["passos"].isArray()) { std::cerr << "roteiro ausente ou inválido: " << opc("--roteiro") << std::endl; return 2; }
    Fluxo F;
    F.saida = opc("--saida").empty() ? "saida_fluxo_b" : opc("--saida");
    if (!opc("--base").empty()) {
        try { F.P.abrir(opc("--base")); } catch (const std::exception& e) { std::cerr << "base inválida (só IFC4): " << e.what() << std::endl; return 2; }
    }
    fs::create_directories(F.saida);
    QApplication app(argc, argv);
    setlocale(LC_NUMERIC, "C");  // o Qt pode ter posto a vírgula decimal (a biblioteca é imune, mas o processo fica como o fluxo A)
#ifdef _WIN32
    const char* padrao = "d3d11";
#else
    const char* padrao = "gl";
#endif
    std::string rhi = opc("--rhi");
    if (rhi.empty()) rhi = std::getenv("RHI") ? std::getenv("RHI") : padrao;
    std::map<std::string, QJsonArray> R;
    QJsonArray passos;
    const std::string base = opc("--base");
    Tela T(rhi != "d3d11", opc("--painel-log"));
    F.t = &T;
    for (auto pv : doc.object()["passos"].toArray()) {
        const QJsonObject p = pv.toObject();
        const std::string id = p["id"].toString().toStdString(), cmd = p["cmd"].toString().toStdString();
        QJsonArray reps;
        for (int r = 0; r < (p.contains("n") ? p["n"].toInt() : 1); ++r) {
            Det d = F.executar(p, r);
            double tq = d.t_cmd;
            if (d.seq >= 0 && (!d.geometria.empty() || !d.apagados.empty() || cmd == "abrir")) {  // espera o 1o quadro apresentado com a sequência do comando
                double a = -1;
                if (!T.aguardar([&] { for (auto& [tt, sq] : T.vp.relogio()) if (tt >= d.t0 && sq >= d.seq) a = a < 0 ? tt : std::min(a, tt); return a >= 0; }, 10000)) throw std::runtime_error("nenhum quadro com a sequência " + std::to_string(d.seq) + " em 10 s");
                tq = std::max(a, d.t_cmd);
            }
            J x{{"r", r}, {"guids", arr(d.guids)}, {"criados", arr(d.criados)}, {"alterados", arr(d.alterados)}, {"apagados", arr(d.apagados)}, {"geometria", arr(d.geometria)}, {"sequencia", d.seq >= 0 ? QJsonValue(qint64(d.seq)) : QJsonValue()},
                {"t0_ms", d.t0}, {"t_comando_ms", d.t_cmd}, {"t_quadro_ms", tq}, {"ms_total", tq - d.t0}, {"triangulos_cena", int(T.vp.estatisticas().triangulos)}};
            if (d.t_painel >= 0) x["t_painel_ms"] = d.t_painel;
            if (cmd == "esperar" || cmd == "criar_paredes_lote") {
                QJsonArray rl;
                for (auto& [tt, sq] : T.vp.relogio()) if (tt >= d.t0 && tt <= tq) rl.append(QJsonArray{tt, qint64(sq)});
                x["relogio"] = rl;
            }
            if (cmd == "criar_paredes_lote") {  // lote em thread C++: ids das duas threads e o pulso da janela durante o passo
                QJsonArray pz;
                for (double pt : T.pulsos) if (pt >= d.t0 && pt <= tq) pz.append(pt);
                x["thread"] = J{{"comando", QString::fromStdString(d.thread_cmd)}, {"janela", QString::fromStdString(id_thread())}}, x["pulso_janela_ms"] = pz;
            }
            reps.append(x);
            Lista& lc = F.passos[id];
            lc.insert(lc.end(), d.criados.begin(), d.criados.end());
            T.aguardar([] { return true; }, 0);  // entre repetições, nunca dentro de transação
        }
        passos.append(J{{"id", QString::fromStdString(id)}, {"cmd", QString::fromStdString(cmd)}, {"reps", reps}});
        R[id] = reps;
    }
    const fs::path med = fs::absolute(F.saida / "medicao.json");
#ifdef _WIN32
    const char* plataforma = "win32";
#else
    const char* plataforma = "linux";
#endif
    J m{{"fluxo", "B"}, {"versao", 1}, {"plataforma", plataforma}, {"rhi", QString::fromStdString(rhi)}, {"base", J{{"arquivo", base.empty() ? QJsonValue() : QJsonValue(QString::fromStdString(base))}, {"produtos", F.P.produtos_base()}}},
        {"passos", passos}, {"metas", metas(R)}, {"arquivo_medicao", QString::fromStdString(med.string())}, {"arquivo_ifc", F.arq_ifc.empty() ? QJsonValue() : QJsonValue(QString::fromStdString(fs::absolute(F.arq_ifc).string()))}};
    std::ofstream(med, std::ios::binary) << QJsonDocument(m).toJson(QJsonDocument::Compact).toStdString();
    std::cout << "MEDICAO " << med.string() << std::endl;
    return 0;
}
}  // namespace
// ---------- autotestes (sem janela; uma linha `RESULTADO {json}`) ----------
namespace {
Lista bibliotecas() {  // as bibliotecas do núcleo carregadas no processo (o oráculo confere que não há Python e que cada núcleo vem de uma cópia só)
    Lista todos, saida;
#ifdef _WIN32
    HMODULE mods[4096];
    DWORD n = 0;
    if (EnumProcessModules(GetCurrentProcess(), mods, sizeof(mods), &n))
        for (DWORD i = 0; i < n / sizeof(HMODULE); ++i) { wchar_t w[MAX_PATH * 2]; if (DWORD len = GetModuleFileNameW(mods[i], w, MAX_PATH * 2)) todos.push_back(QString::fromWCharArray(w, int(len)).toStdString()); }
#else
    std::ifstream mapa("/proc/self/maps");
    for (std::string linha; std::getline(mapa, linha);) if (auto p = linha.find('/'); p != std::string::npos) todos.push_back(linha.substr(p));
#endif
    for (auto& c : todos) {
        std::string nome = fs::path(c).filename().string();
        for (auto& ch : nome) ch = (char)std::tolower((unsigned char)ch);
        if ((nome.find("ifcopenshell") != std::string::npos || nome.find("tkernel") != std::string::npos || nome.find("qt6core") != std::string::npos) && std::find(saida.begin(), saida.end(), c) == saida.end()) saida.push_back(c);
    }
    return saida;
}
long rss_kb() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS pm;
    return GetProcessMemoryInfo(GetCurrentProcess(), &pm, sizeof pm) ? long(pm.WorkingSetSize / 1024) : -1;
#else
    std::ifstream st("/proc/self/status");
    for (std::string l; std::getline(st, l);) if (l.rfind("VmRSS:", 0) == 0) return std::stol(l.substr(6));
    return -1;
#endif
}
std::string linha_do(Paredes& p, const fs::path& tmp, int id) {  // a linha `#id=...` do modelo gravado: o valor do atributo em texto STEP
    p.gravar(tmp.string());
    std::ifstream in(tmp);
    for (std::string l; std::getline(in, l);) if (l.rfind("#" + std::to_string(id) + "=", 0) == 0) return l;
    return "";
}
J t_ler() {  // `ler` pelo desfazer/refazer de `copiar_atributo` em cada tipo de atributo (um IFC4 mínimo escrito à mão); o derivado (`*`) tem de levantar logic_error
    const fs::path dir = fs::temp_directory_path() / ("obim_ler_" + std::to_string(long(agora()))), arq = dir / "ler.ifc";
    fs::create_directories(dir);
    std::ofstream(arq) << "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\nFILE_NAME('ler.ifc','',(''),(''),'','','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
        "#1=IFCWALL('00000000000000000000A1',$,'A',$,$,$,$,$,.SOLIDWALL.);\n#2=IFCWALL('00000000000000000000B2',$,'B',$,$,$,$,$,.PARTITIONING.);\n#3=IFCCARTESIANPOINT((1.,2.,3.));\n#4=IFCCARTESIANPOINT((4.,5.));\n"
        "#5=IFCMATERIAL('m',$,$);\n#6=IFCMATERIALLAYER(#5,0.1,.T.,$,$,$,3);\n#7=IFCMATERIALLAYER(#5,0.3,.F.,$,$,$,7);\n#8=IFCPOLYLINE((#3,#4));\n#9=IFCPOLYLINE((#4,#3,#4));\n"
        "#10=IFCCOMPOSITECURVESEGMENT(.CONTINUOUS.,.T.,#8);\n#11=IFCCOMPOSITECURVESEGMENT(.DISCONTINUOUS.,.F.,#9);\n#12=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,$,$);\n"
        "#13=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('x','Model',*,*,*,*,#12,$,.MODEL_VIEW.,$);\n#14=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('y','Model',*,*,*,*,#12,$,.MODEL_VIEW.,$);\nENDSEC;\nEND-ISO-10303-21;\n";
    struct Caso { const char* nome; int d, o; const char* attr; };
    J casos;
    Paredes p;
    for (Caso c : {Caso{"STRING", 1, 2, "Name"}, {"DOUBLE", 6, 7, "LayerThickness"}, {"INTEGER", 6, 7, "Priority"}, {"LOGICAL", 6, 7, "IsVentilated"}, {"BOOLEAN", 10, 11, "SameSense"}, {"ENUMERATION", 1, 2, "PredefinedType"},
                   {"ENTITY", 10, 11, "ParentCurve"}, {"AGGREGATE_OF_DOUBLE", 3, 4, "Coordinates"}, {"AGGREGATE_OF_ENTITY", 8, 9, "Points"}}) {
        p.abrir(arq.string());
        const std::string antes = linha_do(p, dir / "x.ifc", c.d);
        p.copiar_atributo(c.d, c.o, c.attr);
        const std::string depois = linha_do(p, dir / "x.ifc", c.d);
        p.desfazer();
        const std::string des = linha_do(p, dir / "x.ifc", c.d);
        p.refazer();
        casos[c.nome] = J{{"antes", QString::fromStdString(antes)}, {"depois_alterar", QString::fromStdString(depois)}, {"apos_desfazer", QString::fromStdString(des)}, {"apos_refazer", QString::fromStdString(linha_do(p, dir / "x.ifc", c.d))}};
    }
    bool lancou = false;
    p.abrir(arq.string());
    try { p.copiar_atributo(13, 14, "WorldCoordinateSystem"); } catch (const std::invalid_argument&) { throw; } catch (const std::logic_error&) { lancou = true; }
    fs::remove_all(dir);
    return J{{"casos", casos}, {"nao_suportado", J{{"lancou", lancou}}}};
}
J t_localidade(int T, int N, const fs::path& pasta) {  // T threads gravam N modelos com a vírgula decimal ligada no PROCESSO; uma sonda formata `%.2f` sem parar
    const char* nome = nullptr;
    for (const char* c : {"pt_BR.UTF-8", "pt_BR.utf8", "Portuguese_Brazil.1252", "pt_BR"}) if (setlocale(LC_NUMERIC, c)) { nome = c; break; }
    if (!nome) return J{{"localidade", QJsonValue()}};
    auto virgula = [] { return localeconv()->decimal_point[0] == ','; };
    const bool v0 = virgula();
    { Paredes aquece; aquece.criar_tipo("PAR", {0.02}); }  // um modelo antes das threads: a primeira construção inicializa estáticos do IfcOpenShell, que não aguentam duas threads (travou sem isto)
    std::atomic<bool> parar{false}, erro{false};
    std::atomic<int> pronto{0}, total{0}, com{0};
    auto largar = [&] { ++pronto; while (pronto < T + 1) std::this_thread::yield(); };
    std::thread sonda([&] {
        volatile double x = 1.5;
        char b[32];
        largar();
        while (!parar) { std::snprintf(b, sizeof b, "%.2f", double(x)), ++total, com += std::strchr(b, ',') != nullptr, std::this_thread::yield(); }
    });
    std::vector<std::thread> ths;
    for (int t = 0; t < T; ++t) ths.emplace_back([&, t] {
        try {
            largar();
            for (int i = 0; i < N; ++i) {
                Paredes q;
                q.criar_tipo("PAR", {0.02, 0.11, 0.02});
                auto ws = q.criar_paredes_lote("PAR", 4.25, 2.8, 0.15, 3);
                q.mudar_comprimento(ws[0], 5.5);
                q.gravar((pasta / ("g_" + std::to_string(t) + "_" + std::to_string(i) + ".ifc")).string());
            }
        } catch (...) { erro = true; }
    });
    for (auto& th : ths) th.join();
    parar = true, sonda.join();
    if (erro) throw std::runtime_error("uma thread de gravação falhou");
    QJsonArray arqs;
    for (int t = 0; t < T; ++t) for (int i = 0; i < N; ++i) arqs.append(QString::fromStdString((pasta / ("g_" + std::to_string(t) + "_" + std::to_string(i) + ".ifc")).string()));
    return J{{"localidade", nome}, {"virgula_no_processo", v0}, {"sondas", J{{"total", total.load()}, {"com_virgula", com.load()}}}, {"arquivos", arqs}, {"decimal_depois", QString(QChar(localeconv()->decimal_point[0]))}};
}
J t_corrida(int K, const fs::path& pasta) {  // lote de 60 na thread do comando; a thread principal lê o painel e tenta um 2o escritor com espera=0
    auto novo = [] { auto p = std::make_unique<Paredes>(); p->criar_tipo("PAR", {0.02, 0.11, 0.02}); return p; };
    auto ref = novo();
    ref->criar_paredes_lote("PAR", 4.25, 2.8, 0.15, 60), ref->gravar((pasta / "ref.ifc").string());
    QJsonArray its;
    const std::string parede = "IfcWall";
    for (int i = 0; i < K; ++i) {
        auto p = novo();
        std::atomic<int> estado{0};  // 1 = a thread tem a trava; 2 = o 2o escritor já tentou (só então o lote anda); 3 = terminou
        std::string tid;
        std::thread th([&] { tid = id_thread(); { auto l = p->pegar(true); estado = 1; while (estado < 2) std::this_thread::yield(); p->criar_paredes_lote("PAR", 4.25, 2.8, 0.15, 60); } estado = 3; });
        while (estado < 1) std::this_thread::yield();
        bool ocupado = false;
        int leituras = 0;
        double maior = 0;
        std::string texto = "(sem leitura)";
        do {
            const double a = agora();
            texto = painel_do(*p, "alvo", texto), ++leituras, maior = std::max(maior, agora() - a);
            try { auto l = p->pegar(false); p->editar_propriedades(std::string(22, '0'), nullptr, {}); } catch (const ModeloOcupado&) { ocupado = true; } catch (const std::invalid_argument&) {}
            if (estado == 1) estado = 2;
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        } while (estado < 3);
        th.join();
        const std::string arq = (pasta / ("it_" + std::to_string(i) + ".ifc")).string();
        p->gravar(arq);
        its.append(J{{"thread_comando", QString::fromStdString(tid)}, {"thread_principal", QString::fromStdString(id_thread())}, {"ocupado", ocupado}, {"modelo_tocado", p->contar(nullptr) != ref->contar(nullptr)}, {"leituras", leituras},
                     {"maior_leitura_ms", maior}, {"paredes", p->contar(&parede)}, {"arquivo", QString::fromStdString(arq)}});
    }
    return J{{"iteracoes", its}};
}
J t_memoria(int N) {  // N edições de nome com desfazer a cada 10 (o histórico não pode vazar)
    Paredes p;
    p.criar_tipo("PAR", {0.02, 0.11, 0.02});
    const std::string w = p.criar_parede("PAR", 4, 2.8, 0.15)[0];
    const long a = rss_kb();
    for (int i = 0; i < N; ++i) { std::string nm = "P" + std::to_string(i); p.editar_propriedades(w, &nm, {}); if (i % 10 == 9) p.desfazer(); }
    return J{{"rss_kb_inicio", qint64(a)}, {"rss_kb_fim", qint64(rss_kb())}};
}
}  // namespace
int main(int argc, char** argv) {
    std::vector<std::string> a(argv + 1, argv + argc);
    std::map<std::string, std::string> o;
    for (size_t i = 0; i + 1 < a.size(); ++i) if (a[i].rfind("--", 0) == 0) o[a[i]] = a[i + 1];
    try {
        if (!a.empty() && a[0] == "--versao") {  // antes de qualquer modelo: o esquema IFC4 registrado por código, sem depender de ligação especial nem de Python
            const bool reg = ifcopenshell::schema_by_name("IFC4") == &Ifc4::get_schema();
            QJsonArray libs;
            for (auto& l : bibliotecas()) libs.append(QString::fromStdString(l));
            resultado(J{{"ifcopenshell", OBIM_IFC_VERSAO}, {"qt", QT_VERSION_STR}, {"registro_ifc4", reg}, {"bibliotecas", libs}});
            return 0;
        }
        if (a.size() >= 2 && a[0] == "--autoteste") {  // antes do QApplication (que mexeria na localidade do processo)
            const std::string& k = a[1];
            auto num = [&](size_t i) { return std::stoi(a.at(i)); };
            resultado(k == "ler" ? t_ler() : k == "localidade" ? t_localidade(num(2), num(3), a.at(4)) : k == "corrida" ? t_corrida(num(2), a.at(3)) : k == "memoria" ? t_memoria(num(2)) : throw std::invalid_argument("autoteste desconhecido: " + k));
            return 0;
        }
        return roteiro(argc, argv, o);
    } catch (const std::exception& e) { std::cerr << "erro: " << e.what() << std::endl; return 1; }
}
