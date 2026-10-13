// SPDX-License-Identifier: AGPL-3.0-or-later
// Sonda da thread de desenho (S04-T05). Uma janela Qt nativa (QWindow) desenhada com QRhi por uma thread do C++;
// a thread nunca chama Python nem espera a thread da janela para desenhar (regra 5 do lote 9). Limpa a tela mudando de
// cor e registra o instante de cada quadro APRESENTADO (depois de endFrame). Nenhum método da janela é sobrescrito em Python.
// Construir (ambiente openbim ativo):
//   cmake -S . -B build -DOBIM_SAIDA=<pasta> -DCMAKE_PREFIX_PATH=$CONDA_PREFIX && cmake --build build --config Release
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <QGuiApplication>
#include <QOffscreenSurface>
#include <QPointer>
#include <QPlatformSurfaceEvent>
#include <QWindow>
#include <rhi/qrhi.h>
#include <rhi/qrhi_platform.h>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>
namespace nb = nanobind;
using Rel = std::chrono::steady_clock;
static double agora_ms() { return std::chrono::duration<double, std::milli>(Rel::now().time_since_epoch()).count(); }

// Janela nativa. Os eventos chegam pela thread da janela e só mexem em variáveis atômicas; a thread de desenho as lê.
class Janela : public QWindow {
 public:
  std::atomic<bool> exposta{false}, soltar{false}, rodando{false};
  std::atomic<int> larg{1}, alt{1};
  std::mutex m; std::condition_variable cv; bool solto = false;
  explicit Janela(bool gl) {
#ifdef Q_OS_WIN
    if (!gl) setSurfaceType(QSurface::Direct3DSurface);
#endif
    if (gl) { setSurfaceType(QSurface::OpenGLSurface); setFormat(QSurfaceFormat::defaultFormat()); }
  }
  void atualiza() { const qreal d = devicePixelRatio(); larg = (std::max)(1, int(width() * d)); alt = (std::max)(1, int(height() * d)); }
 protected:
  void exposeEvent(QExposeEvent*) override { atualiza(); exposta = isExposed(); }
  void resizeEvent(QResizeEvent*) override { atualiza(); }
  bool event(QEvent* e) override {
    if (e->type() == QEvent::PlatformSurface &&
        static_cast<QPlatformSurfaceEvent*>(e)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed) {
      // A superfície vai sumir: a thread de desenho solta a swapchain e confirma (espera curta; sem thread, segue).
      std::unique_lock<std::mutex> l(m);
      solto = false; soltar = true; exposta = false;
      if (rodando) cv.wait_for(l, std::chrono::seconds(3), [&] { return solto; });
    }
    return QWindow::event(e);
  }
};

class Desenho {
 public:
  explicit Desenho(bool gl) : gl_(gl), j_(new Janela(gl)) {
    if (gl_) { fb_.reset(QRhiGles2InitParams::newFallbackSurface()); }  // na thread da janela, como o Qt pede
    j_->resize(320, 240);
  }
  ~Desenho() { parar(); }  // a janela pertence ao Qt (contêiner); não é apagada aqui
  uintptr_t janela() const { return reinterpret_cast<uintptr_t>(static_cast<QWindow*>(j_.data())); }
  void iniciar() { if (th_.joinable()) return; j_->rodando = true; parar_ = false; th_ = std::thread([this] { laco(); }); }
  void parar() {
    if (!th_.joinable()) return;
    nb::gil_scoped_release lib;  // a thread de desenho nunca pega o GIL, mas quem espera não deve segurá-lo
    parar_ = true; th_.join();
    if (j_) j_->rodando = false;
  }
  std::vector<double> quadros() { std::lock_guard<std::mutex> l(mq_); return q_; }
  std::string info() { std::lock_guard<std::mutex> l(mq_); return info_; }
  bool viva() const { return th_.joinable() && !falhou_; }
 private:
  void laco() {
    std::unique_ptr<QRhi> rhi;
    std::unique_ptr<QRhiSwapChain> sc;
    std::unique_ptr<QRhiRenderPassDescriptor> rp;
    QRhi::Flags fl = QRhi::PreferSoftwareRenderer;
    if (gl_) {
      QRhiGles2InitParams p; p.fallbackSurface = fb_.get(); p.window = j_.data(); p.format = j_->format();
      rhi.reset(QRhi::create(QRhi::OpenGLES2, &p, fl));
    }
#ifdef Q_OS_WIN
    else { QRhiD3D11InitParams p; rhi.reset(QRhi::create(QRhi::D3D11, &p, fl)); }
#endif
    if (!rhi) { falhou_ = true; std::lock_guard<std::mutex> l(mq_); info_ = "ERRO: QRhi::create falhou"; return; }
    { std::lock_guard<std::mutex> l(mq_);
      info_ = std::string(rhi->backendName()) + " | " + rhi->driverInfo().deviceName.toStdString(); }
    sc.reset(rhi->newSwapChain()); sc->setWindow(j_.data());
    rp.reset(sc->newCompatibleRenderPassDescriptor()); sc->setRenderPassDescriptor(rp.get());
    bool pronta = false;
    auto prox = Rel::now();
    const double t0 = agora_ms();
    while (!parar_) {
      prox += std::chrono::milliseconds(16);  // 60 quadros por segundo; o intervalo medido inclui o custo do quadro
      std::this_thread::sleep_until(prox);
      if (j_->soltar) {  // a superfície vai ser destruída: libera os recursos da swapchain NESTA thread e confirma
        if (pronta) { sc->destroy(); pronta = false; }
        std::lock_guard<std::mutex> l(j_->m); j_->solto = true; j_->soltar = false; j_->cv.notify_all();
        continue;
      }
      if (!j_->exposta) { prox = Rel::now(); continue; }
      const QSize alvo(j_->larg, j_->alt);
      if (!pronta || sc->surfacePixelSize() != alvo) { pronta = sc->createOrResize(); if (!pronta) continue; }
      auto r = rhi->beginFrame(sc.get());
      if (r == QRhi::FrameOpSwapChainOutOfDate) { pronta = sc->createOrResize(); continue; }
      if (r != QRhi::FrameOpSuccess) continue;
      const float h = float(std::fmod((agora_ms() - t0) / 3000.0, 1.0));
      QRhiCommandBuffer* cb = sc->currentFrameCommandBuffer();
      cb->beginPass(sc->currentFrameRenderTarget(), QColor::fromHsvF(h, 0.7f, 0.9f), {1.0f, 0});
      cb->endPass();
      rhi->endFrame(sc.get());
      const double t = agora_ms();  // quadro apresentado (armadilha 6)
      std::lock_guard<std::mutex> l(mq_); q_.push_back(t);
    }
    // Destruir os recursos da placa na thread de desenho (armadilha 2): sc, rp, rhi saem de escopo aqui.
    sc.reset(); rp.reset(); rhi.reset();
  }
  bool gl_;
  QPointer<Janela> j_;
  std::unique_ptr<QOffscreenSurface> fb_;
  std::thread th_;
  std::atomic<bool> parar_{false}, falhou_{false};
  std::mutex mq_; std::vector<double> q_; std::string info_;
};

NB_MODULE(_sonda_desenho, m) {
  nb::class_<Desenho>(m, "Desenho")
      .def(nb::init<bool>(), nb::arg("gl"))
      .def("janela", &Desenho::janela).def("iniciar", &Desenho::iniciar).def("parar", &Desenho::parar)
      .def("quadros", &Desenho::quadros).def("info", &Desenho::info).def("viva", &Desenho::viva);
  m.def("agora", &agora_ms, "relógio do C++ (ms, steady_clock)");
  // Chamada C que segura o GIL por `s` segundos (o "0,75 s" do F9).
  m.def("segurar_gil", [](double s) { std::this_thread::sleep_for(std::chrono::duration<double>(s)); });
}
