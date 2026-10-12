// SPDX-License-Identifier: AGPL-3.0-or-later
// Ponte Python/C++ (S04-T03; LOTE_OPUS_9 §1.4). Regras de posse e de vida:
//  1. O Python é o dono do arquivo; o C++ pega emprestado só durante a chamada (o objeto Python fica referenciado até o retorno).
//  2. O C++ nunca guarda o endereço do arquivo nem ponteiros de entidades entre chamadas.
//  3. Só a thread do comando chama; as funções curtas mantêm o bloqueio, `malhas` (malha.cpp) o solta na geometria.
// Único arquivo que inclui ifcparse/file.h (custo de compilação alto).
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <ifcparse/file.h>
#include <ifcparse/express.h>
#include <Standard_Version.hxx>
#include <QtCore/QtGlobal>
#include <string>
#include <set>
#include <vector>
#include <cstdint>
#include <fstream>
#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  define NOMINMAX
#  include <windows.h>
#  include <psapi.h>
#endif

namespace nb = nanobind;

ifcopenshell::file* emprestar(nb::handle obj);  // definida abaixo
void registrar_malhas(nb::module_& m);  // malha.cpp

// Confere o tipo (ifcopenshell.file, e não uma entidade, que também tem file_pointer()), chama file_pointer() e
// devolve o ponteiro emprestado. Zero ou tipo errado vira erro Python limpo.
ifcopenshell::file* emprestar(nb::handle obj) {  // fora do namespace anônimo: malha.cpp também empresta
    nb::object tipo = nb::module_::import_("ifcopenshell.ifcopenshell_wrapper").attr("file");
    int ok = PyObject_IsInstance(obj.ptr(), tipo.ptr());
    if (ok < 0) throw nb::python_error();
    if (!ok) throw nb::type_error("esperado um ifcopenshell.file");
    nb::object n = nb::borrow(obj).attr("file_pointer")();
    unsigned long long end = PyLong_AsUnsignedLongLong(n.ptr());
    if (PyErr_Occurred()) throw nb::python_error();
    if (end == 0) throw nb::value_error("arquivo sem endereço (fechado ou inválido)");
    return reinterpret_cast<ifcopenshell::file*>(static_cast<uintptr_t>(end));
}

namespace {

express::entity achar(ifcopenshell::file* f, const std::string& guid) {
    express::base b = f->instance_by_guid(guid);
    if (!b) throw nb::value_error(("GlobalId inexistente: " + guid).c_str());
    return express::entity(b.data_weak());
}

}  // namespace

NB_MODULE(_obimcore, m) {
    registrar_malhas(m);
    m.def("versao", [] {
        nb::dict d;
        d["ifcopenshell"] = OBIM_IFC_VERSAO;
        d["ifcopenshell_build"] = OBIM_IFC_BUILD;
        d["occt"] = OCC_VERSION_STRING_EXT;
        d["qt"] = QT_VERSION_STR;
        d["qt_execucao"] = qVersion();
        d["registro_ifc4"] = reinterpret_cast<uintptr_t>(ifcopenshell::schema_by_name("IFC4"));
        return d;
    });
    m.def("endereco", [](nb::object f) { return static_cast<uintptr_t>(reinterpret_cast<uintptr_t>(emprestar(f))); }, nb::arg("arquivo"));
    m.def("contar", [](nb::object f, nb::object classe) -> size_t {
        ifcopenshell::file* p = emprestar(f);
        if (classe.is_none()) {
            size_t n = 0;
            for (auto it = p->begin(); it != p->end(); ++it) ++n;
            return n;
        }
        if (!nb::isinstance<nb::str>(classe)) throw nb::type_error("classe deve ser texto ou None");
        try {
            const auto* decl = p->schema()->declaration_by_name(nb::cast<std::string>(classe));  // lança se não existir
            return p->instances_by_type(decl).size();  // inclui subtipos
        } catch (const std::exception& e) {
            throw nb::value_error(e.what());
        }
    }, nb::arg("arquivo"), nb::arg("classe").none());
    m.def("ler_nome", [](nb::object f, const std::string& guid) -> nb::object {
        auto e = achar(emprestar(f), guid);
        auto v = e.get("Name");
        if (v.isNull()) return nb::none();
        return nb::str(static_cast<std::string>(v).c_str());
    }, nb::arg("arquivo"), nb::arg("guid"));
    m.def("definir_nome", [](nb::object f, const std::string& guid, const std::string& nome) {
        auto e = achar(emprestar(f), guid);
        e.set_attribute_value("Name", nome);
    }, nb::arg("arquivo"), nb::arg("guid"), nb::arg("nome"));
    m.def("bibliotecas_carregadas", [] {
        std::vector<std::string> todos;
#ifdef _WIN32
        HMODULE mods[4096];
        DWORD n = 0;
        if (EnumProcessModules(GetCurrentProcess(), mods, sizeof(mods), &n))
            for (DWORD i = 0; i < n / sizeof(HMODULE); ++i) {
                wchar_t w[MAX_PATH * 2];
                DWORD len = GetModuleFileNameW(mods[i], w, MAX_PATH * 2);
                if (!len) continue;
                int sz = WideCharToMultiByte(CP_UTF8, 0, w, len, nullptr, 0, nullptr, nullptr);
                std::string s(sz, '\0');
                WideCharToMultiByte(CP_UTF8, 0, w, len, s.data(), sz, nullptr, nullptr);
                todos.push_back(s);
            }
#else
        std::ifstream mapa("/proc/self/maps");
        for (std::string linha; std::getline(mapa, linha);) {
            size_t pos = linha.find('/');  // o caminho começa na primeira barra, depois das colunas
            if (pos != std::string::npos) todos.push_back(linha.substr(pos));
        }
#endif
        std::vector<std::string> saida;
        std::set<std::string> vistos;
        for (auto& c : todos) {
            size_t b = c.find_last_of("/\\");
            std::string nome = c.substr(b == std::string::npos ? 0 : b + 1);
            for (auto& ch : nome) ch = (char)std::tolower((unsigned char)ch);
            bool serve = nome.find("ifcopenshell") != std::string::npos || nome.find("tkernel") != std::string::npos ||
                         nome.find("qt6core") != std::string::npos;
            if (serve && vistos.insert(c).second) saida.push_back(c);
        }
        nb::list l;
        for (auto& s : saida) l.append(nb::str(s.c_str()));
        return l;
    });
}
