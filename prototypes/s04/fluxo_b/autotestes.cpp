// SPDX-License-Identifier: AGPL-3.0-or-later
// Autotestes do executável do fluxo B (S04-T14c; CONTRATO.md, Parte 2): código movido do main.cpp, sem mudança de comportamento.
#include "autotestes.h"
#include "janela.h"
#include <ifcparse/schemas/Ifc4.h>
#include <QJsonArray>
#include <algorithm>
#include <atomic>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <locale.h>
#include <memory>
#ifdef _WIN32
#  ifndef WIN32_LEAN_AND_MEAN
#    define WIN32_LEAN_AND_MEAN
#  endif
#  ifndef NOMINMAX
#    define NOMINMAX
#  endif
#  include <windows.h>
#  include <psapi.h>
#endif
using namespace fluxo_b;
namespace fs = std::filesystem;
using J = QJsonObject;
namespace {
void resultado(const J& j) { std::cout << "RESULTADO " << QJsonDocument(j).toJson(QJsonDocument::Compact).toStdString() << std::endl; }
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
bool fluxo_b::autoteste(const std::vector<std::string>& a) {
    if (!a.empty() && a[0] == "--versao") {  // antes de qualquer modelo: o esquema IFC4 registrado por código, sem depender de ligação especial nem de Python
        const bool reg = ifcopenshell::schema_by_name("IFC4") == &Ifc4::get_schema();
        QJsonArray libs;
        for (auto& l : bibliotecas()) libs.append(QString::fromStdString(l));
        resultado(J{{"ifcopenshell", OBIM_IFC_VERSAO}, {"qt", QT_VERSION_STR}, {"registro_ifc4", reg}, {"bibliotecas", libs}});
        return true;
    }
    if (a.size() >= 2 && a[0] == "--autoteste") {  // antes do QApplication (que mexeria na localidade do processo)
        const std::string& k = a[1];
        auto num = [&](size_t i) { return std::stoi(a.at(i)); };
        resultado(k == "ler" ? t_ler() : k == "localidade" ? t_localidade(num(2), num(3), a.at(4)) : k == "corrida" ? t_corrida(num(2), a.at(3)) : k == "memoria" ? t_memoria(num(2)) : throw std::invalid_argument("autoteste desconhecido: " + k));
        return true;
    }
    return false;
}
