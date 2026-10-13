// SPDX-License-Identifier: AGPL-3.0-or-later
// Viewport C++ (S04-T07; LOTE_OPUS_9 §1.4 regra 5, LOTE_OPUS_11 achados 3, 5 e 9). Janela Qt nativa (QWindow) desenhada com QRhi por
// thread própria do C++, embutida numa janela PySide6 por contêiner de janela. Contratos:
//  - A thread nunca chama Python, nunca espera a thread da janela e nunca lê QPointer: ela só usa o `Motor` (estado compartilhado,
//    com mutex) e o QWindow/QOffscreenSurface crus que a `Janela` entrega em `ligar`. A vida da thread está presa à da janela:
//    ~Janela, SurfaceAboutToBeDestroyed e aboutToQuit param a thread (e esperam). A janela é a dona da QOffscreenSurface.
//  - Recursos da placa são criados e destruídos NA thread de desenho. Nenhum método da janela é sobrescrito em Python.
//  - Ritmo de 60 quadros/s; no Windows, timeBeginPeriod(1) (passo de relógio de 1 ms em vez de 15,6 ms; achado 5).
//  - Perda de dispositivo (FrameOpDeviceLost ou `perder_contexto`): a QRhi é recriada na thread e a cópia compacta é reenviada.
// A cena completa (fila de lotes com orçamento por quadro) é da T08; aqui cada quadro envia no máximo 1 lote (regra da S03).
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/tuple.h>
#include <QGuiApplication>
#include <QMatrix4x4>
#include <QOffscreenSurface>
#include <QPlatformSurfaceEvent>
#include <QPointer>
#include <QThread>
#include <QWidget>
#include <QWindow>
#include <rhi/qrhi.h>
#include <rhi/qrhi_platform.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <tuple>
#ifdef Q_OS_WIN
#  define WIN32_LEAN_AND_MEAN
#  define NOMINMAX
#  include <windows.h>
#  include <timeapi.h>
#endif
namespace nb = nanobind;
using Rel = std::chrono::steady_clock;
static double agora_ms() { return std::chrono::duration<double, std::milli>(Rel::now().time_since_epoch()).count(); }

namespace {
const unsigned char QSB_VERT[] = {
#include "malha_vert.inc"
};
const unsigned char QSB_FRAG[] = {
#include "malha_frag.inc"
};
constexpr int BYTES_VERTICE = 28;  // pos f4x3, normal f4x3, cor u1x4 (DTYPE_VERTICE da S03)

struct Dados {  // cópia compacta de um lote (vive no C++; a placa é reenviada a partir dela)
  std::vector<unsigned char> v; std::vector<uint32_t> i; int64_t seq = 0;
};
struct Camera { double alvo[3] = {0, 0, 0}, distancia = 3.2, azimute = -45, elevacao = 30; };

class Motor {
 public:
  std::atomic<bool> exposta{false}, soltar{false}, perder{false}, parar_{false};
  std::atomic<int> larg{1}, alt{1}, contextos{0}, tri_placa{0};
  explicit Motor(bool gl) : gl_(gl) {}
  ~Motor() { parar(); }
  void ligar(QWindow* w, QOffscreenSurface* fb) { std::lock_guard<std::mutex> l(m_); win_ = w; fb_ = fb; fmt_ = w->format(); }
  void desligar() { parar(); std::lock_guard<std::mutex> l(m_); win_ = nullptr; fb_ = nullptr; }
  void iniciar() {  // só na thread da janela
    { std::lock_guard<std::mutex> l(m_); if (!win_ || th_.joinable()) return; parar_ = false; rodando_ = true; }
    th_ = std::thread([this] { laco(); });
  }
  void parar() {  // espera a thread; idempotente; só na thread da janela
    parar_ = true;
    if (th_.joinable()) th_.join();
    std::lock_guard<std::mutex> l(m_); rodando_ = false;
  }
  bool viva() { std::lock_guard<std::mutex> l(m_); return rodando_; }
  void soltar_superficie() {  // SurfaceAboutToBeDestroyed: a thread solta a swapchain e confirma (espera curta)
    std::unique_lock<std::mutex> l(m_);
    exposta = false;
    if (!rodando_) return;
    solto_ = false; soltar = true;
    cv_.wait_for(l, std::chrono::seconds(3), [&] { return solto_ || !rodando_; });
  }
  // --- cena (thread da janela / Python) ---
  int64_t adicionar(std::shared_ptr<Dados> d) {
    std::lock_guard<std::mutex> l(m_);
    d->seq = ++seq_; lotes_.push_back(d);
    const auto* p = d->v.data();
    for (size_t k = 0; k + BYTES_VERTICE <= d->v.size(); k += BYTES_VERTICE) {
      float f[3]; std::memcpy(f, p + k, 12);
      for (int a = 0; a < 3; ++a) { cmin_[a] = (std::min)(cmin_[a], double(f[a])); cmax_[a] = (std::max)(cmax_[a], double(f[a])); }
    }
    return d->seq;
  }
  void limpar() {
    std::lock_guard<std::mutex> l(m_); lotes_.clear(); ++geracao_;
    for (int a = 0; a < 3; ++a) { cmin_[a] = 1e30; cmax_[a] = -1e30; }
  }
  Camera camera() { std::lock_guard<std::mutex> l(m_); return cam_; }
  void definir(const Camera& c) { std::lock_guard<std::mutex> l(m_); cam_ = c; }
  nb::dict estatisticas() {
    std::lock_guard<std::mutex> l(m_);
    size_t tri = 0, vert = 0;
    for (auto& d : lotes_) { tri += d->i.size() / 3; vert += d->v.size() / BYTES_VERTICE; }
    nb::dict r;
    r["lotes"] = lotes_.size(); r["triangulos"] = tri; r["vertices"] = vert;
    r["triangulos_na_placa"] = tri_placa.load(); r["contextos"] = contextos.load();
    return r;
  }
  std::vector<std::tuple<double, int64_t>> relogio() {
    std::lock_guard<std::mutex> l(mq_);
    std::vector<std::tuple<double, int64_t>> r;
    for (size_t k = n_ > anel_.size() ? n_ - anel_.size() : 0; k < n_; ++k) r.push_back(anel_[k % anel_.size()]);
    return r;
  }
  std::tuple<int, int, std::string> capturar() {  // pede à thread o próximo quadro e espera (sem o bloqueio do interpretador)
    std::unique_lock<std::mutex> l(m_);
    if (!rodando_) throw std::runtime_error("viewport parada: não há quadro para capturar");
    cap_pronta_ = false; cap_pedida_ = true;
    if (!cv_.wait_for(l, std::chrono::seconds(8), [&] { return cap_pronta_ || !rodando_; }) || !cap_pronta_) {
      cap_pedida_ = false; throw std::runtime_error("captura sem quadro (janela escondida ou thread parada)");
    }
    return {cap_w_, cap_h_, std::move(cap_)};
  }
  std::string info() { std::lock_guard<std::mutex> l(m_); return info_; }

 private:
  struct L { std::unique_ptr<QRhiBuffer> vb, ib; quint32 n; };
  struct Gpu {  // a ordem importa: o destruidor libera de baixo para cima e a QRhi por último
    std::unique_ptr<QRhi> rhi; std::unique_ptr<QRhiSwapChain> sc; std::unique_ptr<QRhiRenderBuffer> ds;
    std::unique_ptr<QRhiRenderPassDescriptor> rp; std::unique_ptr<QRhiBuffer> ub; std::unique_ptr<QRhiShaderResourceBindings> srb;
    std::unique_ptr<QRhiGraphicsPipeline> pipe; std::vector<L> lotes; bool pronta = false;
  };
  bool criar(Gpu& g) {
    QRhi::Flags fl = QRhi::PreferSoftwareRenderer;
    QWindow* w; QOffscreenSurface* fb; QSurfaceFormat fmt;
    { std::lock_guard<std::mutex> l(m_); w = win_; fb = fb_; fmt = fmt_; }
    if (!w) return false;
    if (gl_) { QRhiGles2InitParams p; p.fallbackSurface = fb; p.window = w; p.format = fmt; g.rhi.reset(QRhi::create(QRhi::OpenGLES2, &p, fl)); }
#ifdef Q_OS_WIN
    else { QRhiD3D11InitParams p; g.rhi.reset(QRhi::create(QRhi::D3D11, &p, fl)); }
#endif
    if (!g.rhi) return false;
    { std::lock_guard<std::mutex> l(m_); info_ = std::string(g.rhi->backendName()) + " | " + g.rhi->driverInfo().deviceName.toStdString(); }
    g.sc.reset(g.rhi->newSwapChain()); g.sc->setWindow(w); g.sc->setFlags(QRhiSwapChain::UsedAsTransferSource);
    g.ds.reset(g.rhi->newRenderBuffer(QRhiRenderBuffer::DepthStencil, QSize(), 1, QRhiRenderBuffer::UsedWithSwapChainOnly));
    g.sc->setDepthStencil(g.ds.get());
    g.rp.reset(g.sc->newCompatibleRenderPassDescriptor()); g.sc->setRenderPassDescriptor(g.rp.get());
    g.ub.reset(g.rhi->newBuffer(QRhiBuffer::Dynamic, QRhiBuffer::UniformBuffer, 80));
    if (!g.ub->create()) return false;
    g.srb.reset(g.rhi->newShaderResourceBindings());
    g.srb->setBindings({QRhiShaderResourceBinding::uniformBuffer(0, QRhiShaderResourceBinding::VertexStage, g.ub.get())});
    if (!g.srb->create()) return false;
    auto sh = [](const unsigned char* b, size_t n) { return QShader::fromSerialized(QByteArray(reinterpret_cast<const char*>(b), qsizetype(n))); };
    g.pipe.reset(g.rhi->newGraphicsPipeline());
    g.pipe->setShaderStages({{QRhiShaderStage::Vertex, sh(QSB_VERT, sizeof QSB_VERT)}, {QRhiShaderStage::Fragment, sh(QSB_FRAG, sizeof QSB_FRAG)}});
    QRhiVertexInputLayout lay;
    lay.setBindings({QRhiVertexInputBinding(BYTES_VERTICE)});
    lay.setAttributes({{0, 0, QRhiVertexInputAttribute::Float3, 0}, {0, 1, QRhiVertexInputAttribute::Float3, 12},
                       {0, 2, QRhiVertexInputAttribute::UNormByte4, 24}});
    g.pipe->setVertexInputLayout(lay); g.pipe->setShaderResourceBindings(g.srb.get());
    g.pipe->setRenderPassDescriptor(g.rp.get());
    g.pipe->setDepthTest(true); g.pipe->setDepthWrite(true);  // sem descarte de faces de trás, como na S03
    if (!g.pipe->create()) return false;
    ++contextos; consumido_ = 0; tri_placa = 0; geracao_vista_ = -1;
    return true;
  }
  void enviar_um(Gpu& g, QRhiResourceUpdateBatch* rub) {  // no máximo 1 lote por quadro; sempre da cópia compacta
    std::shared_ptr<Dados> d;
    { std::lock_guard<std::mutex> l(m_);
      if (geracao_vista_ != geracao_) { g.lotes.clear(); consumido_ = 0; tri_placa = 0; geracao_vista_ = geracao_; }
      if (consumido_ < lotes_.size()) d = lotes_[consumido_++]; }
    if (!d || d->i.empty()) return;
    L e; e.n = quint32(d->i.size());
    e.vb.reset(g.rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer, quint32(d->v.size())));
    e.ib.reset(g.rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::IndexBuffer, quint32(d->i.size() * 4)));
    if (!e.vb->create() || !e.ib->create()) return;
    rub->uploadStaticBuffer(e.vb.get(), 0, quint32(d->v.size()), d->v.data());
    rub->uploadStaticBuffer(e.ib.get(), 0, quint32(d->i.size() * 4), d->i.data());
    tri_placa += int(d->i.size() / 3); seq_placa_ = (std::max)(seq_placa_, d->seq);
    g.lotes.push_back(std::move(e));
  }
  enum class Fim { Parar, Perdido };
  Fim quadros(Gpu& g) {
    auto prox = Rel::now();
    std::unique_ptr<QRhiReadbackResult> rb;  // captura em andamento (o resultado chega depois do fim do quadro)
    while (!parar_) {
      prox += std::chrono::milliseconds(16);
      std::this_thread::sleep_until(prox);
      if (soltar) {  // a superfície vai ser destruída: libera a swapchain NESTA thread e confirma
        g.pronta = false; g.sc->destroy(); rb.reset();
        std::lock_guard<std::mutex> l(m_); solto_ = true; soltar = false; cv_.notify_all();
        continue;
      }
      if (perder) { perder = false; return Fim::Perdido; }
      if (!exposta) { prox = Rel::now(); continue; }
      const QSize alvo(larg, alt);
      if (!g.pronta || g.sc->surfacePixelSize() != alvo) { g.pronta = g.sc->createOrResize(); if (!g.pronta) continue; }
      auto r = g.rhi->beginFrame(g.sc.get());
      if (r == QRhi::FrameOpSwapChainOutOfDate) { g.pronta = g.sc->createOrResize(); continue; }
      if (r == QRhi::FrameOpDeviceLost) return Fim::Perdido;
      if (r != QRhi::FrameOpSuccess) continue;
      QRhiResourceUpdateBatch* rub = g.rhi->nextResourceUpdateBatch();
      enviar_um(g, rub);
      Camera c; double bmin[3], bmax[3]; bool pedida;
      { std::lock_guard<std::mutex> l(m_); c = cam_; std::copy(cmin_, cmin_ + 3, bmin); std::copy(cmax_, cmax_ + 3, bmax); pedida = cap_pedida_; }
      const double az = c.azimute * 3.14159265358979323846 / 180, el = c.elevacao * 3.14159265358979323846 / 180;
      const QVector3D alvo3(float(c.alvo[0]), float(c.alvo[1]), float(c.alvo[2]));
      const QVector3D pos = alvo3 + float(c.distancia) * QVector3D(float(std::cos(el) * std::cos(az)), float(std::cos(el) * std::sin(az)), float(std::sin(el)));
      double longe = 20000, perto = 0.05;
      if (bmin[0] <= bmax[0]) {  // perto/longe pela caixa da cena a cada quadro (como a S03)
        const QVector3D centro(float(bmin[0] + bmax[0]) / 2, float(bmin[1] + bmax[1]) / 2, float(bmin[2] + bmax[2]) / 2);
        const double raio = std::sqrt(std::pow(bmax[0] - bmin[0], 2) + std::pow(bmax[1] - bmin[1], 2) + std::pow(bmax[2] - bmin[2], 2)) / 2;
        longe = ((pos - centro).length() + raio) * 1.1; perto = (std::max)(longe / 10000.0, 0.05);
      }
      QMatrix4x4 proj, vista;
      proj.perspective(45.0f, float(alvo.width()) / float(alvo.height()), float(perto), float(longe));
      vista.lookAt(pos, alvo3, QVector3D(0, 0, 1));
      const QMatrix4x4 mvp = g.rhi->clipSpaceCorrMatrix() * proj * vista;
      const QVector3D frente = (alvo3 - pos).normalized();
      const float luz[4] = {frente.x(), frente.y(), frente.z(), 0.0f};
      rub->updateDynamicBuffer(g.ub.get(), 0, 64, mvp.constData());
      rub->updateDynamicBuffer(g.ub.get(), 64, 16, luz);
      QRhiCommandBuffer* cb = g.sc->currentFrameCommandBuffer();
      cb->beginPass(g.sc->currentFrameRenderTarget(), QColor(30, 30, 40), {1.0f, 0}, rub);
      cb->setGraphicsPipeline(g.pipe.get());
      cb->setViewport({0, 0, float(alvo.width()), float(alvo.height())});
      cb->setShaderResources();
      for (auto& e : g.lotes) {
        const QRhiCommandBuffer::VertexInput vi(e.vb.get(), 0);
        cb->setVertexInput(0, 1, &vi, e.ib.get(), 0, QRhiCommandBuffer::IndexUInt32);
        cb->drawIndexed(e.n);
      }
      QRhiResourceUpdateBatch* rub2 = nullptr;
      if (pedida && !rb) { rb = std::make_unique<QRhiReadbackResult>(); rub2 = g.rhi->nextResourceUpdateBatch(); rub2->readBackTexture(QRhiReadbackDescription(), rb.get()); }
      cb->endPass(rub2);
      const auto fim = g.rhi->endFrame(g.sc.get());
      if (fim == QRhi::FrameOpDeviceLost) return Fim::Perdido;
      const double t = agora_ms();  // quadro apresentado (armadilha 6)
      { std::lock_guard<std::mutex> l(mq_); anel_[n_++ % anel_.size()] = {t, seq_placa_}; }
      if (rb && !rb->data.isEmpty()) {
        QImage im(reinterpret_cast<const uchar*>(rb->data.constData()), rb->pixelSize.width(), rb->pixelSize.height(),
                  rb->format == QRhiTexture::BGRA8 ? QImage::Format_ARGB32 : QImage::Format_RGBA8888);
        if (g.rhi->isYUpInFramebuffer()) im = im.flipped(Qt::Vertical);
        im = im.convertToFormat(QImage::Format_RGBA8888);
        std::lock_guard<std::mutex> l(m_);
        cap_w_ = im.width(); cap_h_ = im.height();
        cap_.assign(reinterpret_cast<const char*>(im.constBits()), size_t(im.sizeInBytes()));
        cap_pedida_ = false; cap_pronta_ = true; rb.reset(); cv_.notify_all();
      }
    }
    return Fim::Parar;
  }
  void laco() {
#ifdef Q_OS_WIN
    timeBeginPeriod(1);
#endif
    try {
      for (int falhas = 0; !parar_;) {
        Gpu g;  // destruído ao sair do bloco, NESTA thread
        if (!criar(g)) {
          { std::lock_guard<std::mutex> l(m_); info_ = "ERRO: QRhi não pôde ser criada"; }
          if (++falhas >= 3) break;  // `rodando` vira falso: viva() informa
          std::this_thread::sleep_for(std::chrono::milliseconds(100)); continue;
        }
        falhas = 0;
        if (quadros(g) == Fim::Parar) break;
      }
    } catch (const std::exception& e) {
      std::lock_guard<std::mutex> l(m_); info_ = std::string("ERRO: ") + e.what();
    } catch (...) {
      std::lock_guard<std::mutex> l(m_); info_ = "ERRO: exceção desconhecida";
    }
#ifdef Q_OS_WIN
    timeEndPeriod(1);
#endif
    std::lock_guard<std::mutex> l(m_); rodando_ = false; cv_.notify_all();
  }
  bool gl_;
  std::mutex m_, mq_; std::condition_variable cv_; std::thread th_;
  QWindow* win_ = nullptr; QOffscreenSurface* fb_ = nullptr; QSurfaceFormat fmt_;
  bool rodando_ = false, solto_ = false, cap_pedida_ = false, cap_pronta_ = false;
  std::vector<std::shared_ptr<Dados>> lotes_; int64_t seq_ = 0, geracao_ = 0, geracao_vista_ = -1, seq_placa_ = 0; size_t consumido_ = 0;
  double cmin_[3] = {1e30, 1e30, 1e30}, cmax_[3] = {-1e30, -1e30, -1e30};
  Camera cam_; std::string info_, cap_; int cap_w_ = 0, cap_h_ = 0;
  std::array<std::tuple<double, int64_t>, 4096> anel_{}; size_t n_ = 0;
};

// Janela nativa. Os eventos chegam pela thread da janela e só mexem em atômicos do Motor.
class Janela : public QWindow {
 public:
  Janela(std::shared_ptr<Motor> m, bool gl) : m_(std::move(m)), fb_(new QOffscreenSurface(nullptr, this)) {
#ifdef Q_OS_WIN
    if (!gl) setSurfaceType(QSurface::Direct3DSurface);
#endif
    if (gl) { setSurfaceType(QSurface::OpenGLSurface); setFormat(QSurfaceFormat::defaultFormat()); fb_->setFormat(QSurfaceFormat::defaultFormat()); fb_->create(); }
    resize(320, 240);
    m_->ligar(this, fb_);  // fb_ é filha desta janela: some junto, depois da thread
    // A saída do programa para a thread antes de a QGuiApplication sumir (caso "sair" do oráculo).
    QObject::connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, this, [m = m_] { m->parar(); });
  }
  ~Janela() override { m_->desligar(); }  // para e ESPERA a thread de desenho antes de a janela deixar de existir
 protected:
  void atualiza() { const qreal d = devicePixelRatio(); m_->larg = (std::max)(1, int(width() * d)); m_->alt = (std::max)(1, int(height() * d)); }
  void exposeEvent(QExposeEvent*) override { atualiza(); m_->exposta = isExposed(); }
  void resizeEvent(QResizeEvent*) override { atualiza(); }
  bool event(QEvent* e) override {
    if (e->type() == QEvent::PlatformSurface && static_cast<QPlatformSurfaceEvent*>(e)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed)
      m_->soltar_superficie();
    return QWindow::event(e);
  }
 private:
  std::shared_ptr<Motor> m_; QOffscreenSurface* fb_;
};

class Cena {  // objeto Python: só guarda o Motor e ponteiros fracos; o Qt é dono do contêiner (depois de posto num layout)
 public:
  explicit Cena(bool gl) : m_(std::make_shared<Motor>(gl)) {
    if (!QGuiApplication::instance()) throw std::runtime_error("crie a QApplication antes da Cena");
    cont_ = QWidget::createWindowContainer(new Janela(m_, gl), nullptr);
  }
  ~Cena() {
    m_->parar();
    if (cont_ && !cont_->parent()) { if (QThread::currentThread() == cont_->thread()) delete cont_.data(); else cont_->deleteLater(); }
  }
  uintptr_t viewport_ptr() const { return reinterpret_cast<uintptr_t>(cont_.data()); }
  void iniciar() { m_->iniciar(); }
  void parar() { nb::gil_scoped_release lib; m_->parar(); }
  bool viva() { return m_->viva(); }
  int64_t adicionar_lote(nb::object lote) {
    auto d = std::make_shared<Dados>();
    auto bytes = [&](const char* campo) { nb::bytes b = nb::cast<nb::bytes>(lote.attr(campo).attr("tobytes")()); return std::string(b.c_str(), b.size()); };
    const std::string v = bytes("vertices"), i = bytes("indices");
    if (v.size() % BYTES_VERTICE || i.size() % 12) throw nb::value_error("lote com tamanho inválido (vértice 28 bytes, índices uint32 em triângulos)");
    d->v.assign(v.begin(), v.end()); d->i.resize(i.size() / 4); std::memcpy(d->i.data(), i.data(), i.size());
    return m_->adicionar(d);
  }
  void limpar() { m_->limpar(); }
  std::vector<std::tuple<double, int64_t>> relogio() { return m_->relogio(); }
  nb::tuple capturar() { std::tuple<int, int, std::string> r; { nb::gil_scoped_release lib; r = m_->capturar(); }
    return nb::make_tuple(std::get<0>(r), std::get<1>(r), nb::bytes(std::get<2>(r).data(), std::get<2>(r).size())); }
  nb::dict camera() {
    Camera c = m_->camera(); nb::dict d;
    d["alvo"] = nb::make_tuple(c.alvo[0], c.alvo[1], c.alvo[2]); d["distancia"] = c.distancia; d["azimute"] = c.azimute; d["elevacao"] = c.elevacao;
    return d;
  }
  void definir_camera(nb::object alvo, nb::object distancia, nb::object azimute, nb::object elevacao) {
    Camera c = m_->camera();
    if (!alvo.is_none()) { auto t = nb::cast<std::vector<double>>(alvo); if (t.size() != 3) throw nb::value_error("alvo = 3 números"); std::copy(t.begin(), t.end(), c.alvo); }
    if (!distancia.is_none()) c.distancia = std::clamp(nb::cast<double>(distancia), 0.1, 10000.0);
    if (!azimute.is_none()) c.azimute = nb::cast<double>(azimute);
    if (!elevacao.is_none()) c.elevacao = std::clamp(nb::cast<double>(elevacao), -89.0, 89.0);
    m_->definir(c);
  }
  nb::dict estatisticas() { return m_->estatisticas(); }
  void perder_contexto() { m_->perder = true; }  // gancho de teste: simula FrameOpDeviceLost
  std::string info() { return m_->info(); }
 private:
  std::shared_ptr<Motor> m_; QPointer<QWidget> cont_;
};
}  // namespace

void registrar_viewport(nb::module_& m) {
  m.def("agora", &agora_ms, "relógio do C++ (ms, steady_clock), o mesmo de Cena.relogio()");
  nb::class_<Cena>(m, "Cena")
      .def(nb::init<bool>(), nb::arg("gl"))
      .def("viewport_ptr", &Cena::viewport_ptr).def("iniciar", &Cena::iniciar).def("parar", &Cena::parar).def("viva", &Cena::viva)
      .def("adicionar_lote", &Cena::adicionar_lote, nb::arg("lote")).def("limpar", &Cena::limpar).def("relogio", &Cena::relogio)
      .def("capturar", &Cena::capturar).def("camera", &Cena::camera)
      .def("definir_camera", &Cena::definir_camera, nb::arg("alvo") = nb::none(), nb::arg("distancia") = nb::none(),
           nb::arg("azimute") = nb::none(), nb::arg("elevacao") = nb::none())
      .def("estatisticas", &Cena::estatisticas).def("perder_contexto", &Cena::perder_contexto).def("info", &Cena::info);
}
