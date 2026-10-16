// SPDX-License-Identifier: AGPL-3.0-or-later
// Janela Qt Widgets do fluxo B (S04-T14c; CONTRATO.md, Parte 2): viewport do núcleo (C++ puro) + painel de propriedades (QLabel) + pulso de 10 ms da thread da janela.
// O painel só lê o modelo com `try_lock` (regra 4): trava ocupada devolve o último texto mostrado. Nada de Python.
#pragma once
#include "malha.h"
#include "motor.h"
#include "paredes.h"
#include <ifcparse/express.h>
#include <QApplication>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QMainWindow>
#include <QPaintEvent>
#include <QTimer>
#include <fstream>
#include <sstream>
namespace fluxo_b {
inline double agora() { return obim::agora_ms(); }  // o relógio do núcleo: o mesmo de Viewport::relogio()
inline std::string id_thread() { std::ostringstream o; o << std::this_thread::get_id(); return o.str(); }
inline std::string txt(const express::base& e, int i) { auto a = e.get_attribute_value(size_t(i)); if (a.type() != ifcopenshell::Argument_STRING) return ""; std::string s = a; return s; }
// Texto do painel (mesmo do fluxo A). Trava ocupada: `ultimo`, sem tocar no modelo.
inline std::string painel_do(Paredes& p, const std::string& guid, const std::string& ultimo) {
    if (guid.empty()) return "(nada selecionado)";
    std::unique_lock<std::mutex> l(p.trava(), std::try_to_lock);
    if (!l) return ultimo;
    auto* f = p.arquivo();
    express::base e;
    try { e = f->instance_by_guid(guid); } catch (...) {}
    if (!e) return "(nada selecionado)";
    std::string fogo = "-";
    for (auto& r : f->instances_by_reference(int(e.id()))) {
        express::base ps = r.get_attribute_value(5);
        if (!r.declaration().is("IfcRelDefinesByProperties") || txt(ps, 2) != "Pset_WallCommon") continue;
        std::vector<express::base> hp = ps.get_attribute_value(4);
        for (auto& pr : hp) if (txt(pr, 0) == "FireRating") { express::base v = pr.get_attribute_value(2); fogo = txt(v, 0); }
    }
    return e.declaration().name() + "\nNome: " + txt(e, 2) + "\nGlobalId: " + guid + "\nResistência ao fogo: " + fogo;
}
struct Etiqueta : QLabel {  // uma linha JSON por pintura (--painel-log): o oráculo confere que o texto novo foi pintado antes de t_painel_ms
    std::ofstream log;
    void paintEvent(QPaintEvent* e) override {
        if (log.is_open()) log << QJsonDocument(QJsonObject{{"t_ms", agora()}, {"texto", text()}}).toJson(QJsonDocument::Compact).toStdString() << std::endl;
        QLabel::paintEvent(e);
    }
};
struct Tela {
    obim::Viewport vp;
    QMainWindow win;
    Etiqueta* rotulo = new Etiqueta;
    QTimer pulso;
    std::vector<double> pulsos;  // o pulso de 10 ms da thread da janela (prova de que ela segue tratando eventos durante o lote)
    Tela(bool gl, const std::string& arq_log) : vp(gl) {
        if (!arq_log.empty()) rotulo->log.open(arq_log, std::ios::binary);
        auto *centro = new QWidget, *cont = reinterpret_cast<QWidget*>(vp.viewport_ptr());
        auto* lay = new QHBoxLayout(centro);
        cont->setMinimumSize(640, 480);
        rotulo->setText("(nada selecionado)"), rotulo->setMinimumWidth(260), rotulo->setAlignment(Qt::AlignTop | Qt::AlignLeft);
        lay->addWidget(cont, 1), lay->addWidget(rotulo);
        win.setCentralWidget(centro);
        pulso.setTimerType(Qt::PreciseTimer), pulso.setInterval(10);
        QObject::connect(&pulso, &QTimer::timeout, [this] { pulsos.push_back(agora()); });
        pulso.start(), vp.iniciar(), win.show();
        if (!aguardar([&] { return !vp.relogio().empty(); }, 10000)) {  // o destrutor não roda se o construtor lança: parar o motor antes de a janela e o contêiner morrerem
            vp.parar();
            throw std::runtime_error("a viewport não apresentou o primeiro quadro em 10 s");
        }
    }
    ~Tela() { vp.parar(); }
    QWidget* cont() { return reinterpret_cast<QWidget*>(vp.viewport_ptr()); }
    template <class P> bool aguardar(P pronto, double ms) {  // trata os eventos da janela (só nesta thread) até `pronto` valer ou passar `ms`
        const auto fim = std::chrono::steady_clock::now() + std::chrono::duration<double, std::milli>(ms);
        for (;;) {
            QApplication::processEvents();
            if (pronto()) return true;
            if (std::chrono::steady_clock::now() >= fim) return false;
            std::this_thread::sleep_for(std::chrono::microseconds(500));
        }
    }
    void mostrar(const std::string& t) { rotulo->setText(QString::fromStdString(t)), rotulo->repaint(), QApplication::processEvents(); }  // repaint: pintura síncrona, antes de t_painel_ms
};
}  // namespace fluxo_b
