// SPDX-License-Identifier: AGPL-3.0-or-later
// Viewport C++ (S04-T07; LOTE_OPUS_9 §1.4 regra 5, LOTE_OPUS_11 achados 3, 5 e 9). Janela Qt nativa (QWindow) desenhada com QRhi por
// thread própria do C++, embutida numa janela PySide6 por contêiner de janela. Contratos:
//  - A thread nunca chama Python, nunca espera a thread da janela e nunca lê QPointer: ela só usa o `Motor` (estado compartilhado,
//    com mutex) e o QWindow/QOffscreenSurface crus que a `Janela` entrega em `ligar`. A vida da thread está presa à da janela:
//    ~Janela, SurfaceAboutToBeDestroyed e aboutToQuit param a thread (e esperam). A janela é a dona da QOffscreenSurface.
//  - Recursos da placa são criados e destruídos NA thread de desenho. Nenhum método da janela é sobrescrito em Python.
//  - Windows (T07b, LOTE_OPUS_12 achado 9): nenhuma espera da thread da janela pela de desenho fica sem bombear mensagens (`esperar_ate`,
//    `parar`, `soltar_superficie`, `capturar`); o `join` só vem depois do sinal `terminou_` do fim de `laco()`. Se a soltura da swapchain
//    estourar 3 s, a swapchain é marcada perdida: a thread nunca mais a toca e `solturas_atrasadas` sobe.
//  - Ritmo de 60 quadros/s; no Windows, timeBeginPeriod(1) (passo de relógio de 1 ms em vez de 15,6 ms; achado 5).
//  - Perda de dispositivo (FrameOpDeviceLost ou `perder_contexto`): a QRhi é recriada na thread e a cópia compacta é reenviada.
//  - Cena (T08): fila de lotes, cópia compacta, sequência e caixa vivem em `cena.*` (mutex próprio). Aqui só o envio à placa: orçamento por quadro
//    (`ORCAMENTO_BYTES`, ~4 ms), lotes grandes partidos em fatias; a sequência de um quadro = maior prefixo contínuo de lotes já NA placa.
#include "camera.h"
#include "cena.h"
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
#include "selecao.h"
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
using namespace obim;
constexpr size_t ORCAMENTO_BYTES = 2u << 20;  // por quadro (cabe em ~1 ms no software); lote maior é partido em fatias
constexpr auto ORCAMENTO_TEMPO = std::chrono::milliseconds(4);

class Motor {
 public:
  std::atomic<bool> exposta{false}, soltar{false}, perder{false}, parar_{false}, perdida_{false}, terminou_{true};
  std::atomic<int> contextos{0}, tri_placa{0}, superficies_soltas{0}, solturas_atrasadas{0};
  std::atomic<int64_t> fatias_{0};
  std::atomic<int> larg_{0}, alt_{0};  // tamanho real do backbuffer do último quadro (T10: a seleção usa o mesmo)
  DadosCena cena_;  // fila de lotes, cópia compacta, sequência e caixa (T08); o Python entra direto, com mutex próprio
  explicit Motor(bool gl) : gl_(gl) {}
  ~Motor() { parar(); }
  void ligar(QWindow* w, QOffscreenSurface* fb) { std::lock_guard<std::mutex> l(m_); win_ = w; fb_ = fb; fmt_ = w->format(); }
  void desligar() { parar(); std::lock_guard<std::mutex> l(m_); win_ = nullptr; fb_ = nullptr; }
  void iniciar() {  // qualquer thread (th_m_ guarda th_)
    { std::lock_guard<std::mutex> l(m_); if (!win_) return; }
    std::lock_guard<std::mutex> lt(th_m_);
    if (th_.joinable()) return;
    parar_ = false; perdida_ = false; terminou_ = false;
    { std::lock_guard<std::mutex> l(m_); rodando_ = true; }
    th_ = std::thread([this] { laco(); });
  }
  void parar() {  // espera a thread; idempotente; qualquer thread. Bombeia mensagens até `terminou_`; só então faz o join.
    parar_ = true;
    while (!terminou_) { bombear(); std::this_thread::sleep_for(std::chrono::milliseconds(1)); }
    { std::lock_guard<std::mutex> lt(th_m_); if (th_.joinable()) th_.join(); }
    std::lock_guard<std::mutex> l(m_); rodando_ = false;
  }
  bool viva() { std::lock_guard<std::mutex> l(m_); return rodando_; }
  void soltar_superficie() {  // SurfaceAboutToBeDestroyed: a thread solta a swapchain e confirma (espera curta)
    std::unique_lock<std::mutex> l(m_);
    exposta = false;
    if (!rodando_) return;
    solto_ = false; soltar = true;
    if (!esperar_ate(l, std::chrono::seconds(3), [&] { return solto_ || !rodando_; })) {
      perdida_ = true; ++solturas_atrasadas;  // a thread nunca mais toca nesta swapchain (corrida mínima com o fim da soltura: aceita)
    }
  }
  // --- cena (thread da janela / Python) ---
  ControleCamera cam_;  // entradas da thread da janela só enfileiram; a thread de desenho aplica (camera.h)
  nb::dict estatisticas() {
    std::lock_guard<std::mutex> l(m_);
    const Totais t = cena_.totais();
    nb::dict r;
    r["bytes_copia"] = t.bytes; r["lotes"] = t.lotes; r["triangulos"] = t.triangulos; r["vertices"] = t.vertices; r["fatias_enviadas"] = fatias_.load();
    r["triangulos_na_placa"] = tri_placa.load(); r["contextos"] = contextos.load();
    r["superficies_soltas"] = superficies_soltas.load(); r["solturas_atrasadas"] = solturas_atrasadas.load();
    return r;
  }
  std::vector<std::tuple<double, int64_t>> relogio() {
    std::vector<std::tuple<double, int64_t>> r; size_t n;
    auto copia = std::make_unique<decltype(anel_)>();
    { std::lock_guard<std::mutex> l(mq_); *copia = anel_; n = n_; }  // o mutex só cobre a cópia do anel; a conversão para lista fica fora dele
    for (size_t k = n > copia->size() ? n - copia->size() : 0; k < n; ++k) r.push_back((*copia)[k % copia->size()]);
    return r;
  }
  std::tuple<int, int, std::string> capturar() {  // pede à thread o próximo quadro e espera (sem o bloqueio do interpretador)
    std::unique_lock<std::mutex> l(m_);
    if (!rodando_) throw std::runtime_error("viewport parada: não há quadro para capturar");
    cap_pronta_ = false; cap_pedida_ = true;
    if (!esperar_ate(l, std::chrono::seconds(8), [&] { return cap_pronta_ || !rodando_; }) || !cap_pronta_) {
      cap_pedida_ = false; throw std::runtime_error("captura sem quadro (janela escondida ou thread parada)");
    }
    return {cap_w_, cap_h_, std::move(cap_)};
  }
  std::string info() { std::lock_guard<std::mutex> l(m_); return info_; }

 private:
  static void bombear() {  // Windows: atende mensagens enviadas (SendMessage) por outras threads, sem retirar nada da fila
#ifdef Q_OS_WIN
    MSG msg; PeekMessageW(&msg, nullptr, 0, 0, PM_NOREMOVE | PM_QS_SENDMESSAGE);
#endif
  }
  template <class P> bool esperar_ate(std::unique_lock<std::mutex>& l, std::chrono::milliseconds total, P pred) {  // espera curta (≤10 ms) + bombeio
    const auto fim = Rel::now() + total;
    while (!pred()) {
      if (Rel::now() >= fim) return false;
      cv_.wait_for(l, std::chrono::milliseconds(10), pred);
#ifdef Q_OS_WIN
      if (!pred()) { l.unlock(); bombear(); l.lock(); }  // sem o mutex: o tratador da mensagem pode voltar ao Motor
#endif
    }
    return true;
  }
  struct L { std::unique_ptr<QRhiBuffer> vb, ib; quint32 n; };
  struct Pend { std::shared_ptr<Dados> d; L e; size_t voff = 0, ioff = 0; };  // lote em envio, em fatias
  struct Gpu {  // a ordem importa: o destruidor libera de baixo para cima e a QRhi por último
    std::unique_ptr<QRhi> rhi; std::unique_ptr<QRhiSwapChain> sc; std::unique_ptr<QRhiRenderBuffer> ds;
    std::unique_ptr<QRhiRenderPassDescriptor> rp; std::unique_ptr<QRhiBuffer> ub; std::unique_ptr<QRhiShaderResourceBindings> srb;
    std::unique_ptr<QRhiGraphicsPipeline> pipe; std::vector<L> lotes; bool pronta = false;
    Cursor cur; Pend pend;  // o que a fila já entregou e o lote pela metade (somem junto com a placa: a perda de contexto reenvia tudo)
  };
  bool criar(Gpu& g) {
    QRhi::Flags fl;  // renderizador por software só com a variável do Qt (o CI a liga no WARP)
    if (qEnvironmentVariableIntValue("QSG_RHI_PREFER_SOFTWARE_RENDERER") != 0) fl |= QRhi::PreferSoftwareRenderer;
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
    ++contextos; tri_placa = 0; seq_placa_ = 0;
    return true;
  }
  void enviar(Gpu& g, QRhiResourceUpdateBatch* rub) {  // orçamento por quadro; sempre da cópia compacta; só lotes COMPLETOS entram em `lotes`
    const int64_t ger = cena_.geracao();
    if (ger != g.cur.ger) { g.lotes.clear(); g.pend = {}; g.cur = Cursor{0, ger}; tri_placa = 0; seq_placa_ = 0; }  // limpar(): a placa volta a zero
    size_t gasto = 0; const auto t0 = Rel::now();
    while (gasto < ORCAMENTO_BYTES && Rel::now() - t0 < ORCAMENTO_TEMPO) {
      Pend& p = g.pend;
      if (!p.d) {
        if (!(p.d = cena_.proximo(g.cur))) break;
        if (p.d->i.empty()) { seq_placa_ = p.d->seq; p = {}; continue; }  // lote sem triângulos: já "na placa"
        p.e.n = quint32(p.d->i.size());
        p.e.vb.reset(g.rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer, quint32(p.d->v.size())));
        p.e.ib.reset(g.rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::IndexBuffer, quint32(p.d->i.size() * 4)));
        if (!p.e.vb->create() || !p.e.ib->create()) {  // achado 5: o lote NÃO se perde; volta à fila e repete no quadro seguinte
          --g.cur.n; p = {}; { std::lock_guard<std::mutex> l(m_); info_ = "AVISO: create() de buffer falhou; repetindo no quadro seguinte"; } return;
        }
      }
      const bool vert = p.voff < p.d->v.size();  // primeiro os vértices, depois os índices
      const size_t total = vert ? p.d->v.size() : p.d->i.size() * 4, off = vert ? p.voff : p.ioff, un = vert ? BYTES_VERTICE : 4;
      const size_t n = (std::min)(total - off, (std::max)(un, (ORCAMENTO_BYTES - gasto) / un * un));
      const unsigned char* dados = vert ? p.d->v.data() : reinterpret_cast<const unsigned char*>(p.d->i.data());
      rub->uploadStaticBuffer(vert ? p.e.vb.get() : p.e.ib.get(), quint32(off), quint32(n), dados + off);
      (vert ? p.voff : p.ioff) += n; gasto += n; ++fatias_;
      if (p.voff == p.d->v.size() && p.ioff == p.d->i.size() * 4) {  // completo: entra no desenho e a sequência avança (prefixo contínuo)
        tri_placa += int(p.d->i.size() / 3); seq_placa_ = p.d->seq; g.lotes.push_back(std::move(p.e)); p = {};
      }
    }
  }
  enum class Fim { Parar, Perdido };
  Fim quadros(Gpu& g) {
    auto prox = Rel::now();
    std::unique_ptr<QRhiReadbackResult> rb;  // captura em andamento (o resultado chega depois do fim do quadro)
    while (!parar_) {
      prox += std::chrono::milliseconds(16);
      const auto now = Rel::now();
      if (prox < now) prox = now;  // sem rajada para recuperar quadros atrasados
      std::this_thread::sleep_until(prox);
      if (perdida_) {  // soltura estourou 3 s: a swapchain nunca mais é tocada (nem createOrResize); com a superfície de volta, `laco` a abandona e recria a QRhi (achado 6)
        rb.reset(); soltar = false;
        if (exposta) return Fim::Perdido;
        continue;
      }
      if (soltar) {  // a superfície vai ser destruída: libera a swapchain NESTA thread e confirma
        g.pronta = false; g.sc->destroy(); rb.reset(); ++superficies_soltas;
        if (gl_) g.rhi->makeThreadLocalNativeContextCurrent();  // GL: o contexto não fica atual numa janela prestes a ser destruída
        std::lock_guard<std::mutex> l(m_); solto_ = true; soltar = false; cv_.notify_all();
        continue;
      }
      if (perder) { perder = false; return Fim::Perdido; }
      if (!exposta) { prox = Rel::now(); continue; }
      // O que vale é o tamanho REAL do backbuffer; refaz a swapchain quando ele diverge do tamanho atual da superfície (padrão do QRhi).
      if (g.sc->surfacePixelSize().isEmpty()) { prox = Rel::now(); continue; }
      if (!g.pronta || g.sc->currentPixelSize() != g.sc->surfacePixelSize()) { g.pronta = g.sc->createOrResize(); if (!g.pronta) continue; }
      auto r = g.rhi->beginFrame(g.sc.get());
      if (r == QRhi::FrameOpSwapChainOutOfDate) { g.pronta = g.sc->createOrResize(); continue; }
      if (r == QRhi::FrameOpDeviceLost) return Fim::Perdido;
      if (r != QRhi::FrameOpSuccess) continue;
      QRhiResourceUpdateBatch* rub = g.rhi->nextResourceUpdateBatch();
      enviar(g, rub);
      bool pedida; double bmin[3], bmax[3];
      { std::lock_guard<std::mutex> l(m_); pedida = cap_pedida_; }
      const bool com_caixa = cena_.caixa(bmin, bmax);
      const QSize alvo = g.sc->currentPixelSize();  // tamanho real do backbuffer
      larg_ = alvo.width(); alt_ = alvo.height();
      const Camera c = cam_.aplicar(alvo.height(), double(alvo.width()) / (std::max)(alvo.height(), 1), com_caixa ? bmin : nullptr, com_caixa ? bmax : nullptr);
      if (!pedida) rb.reset();  // `capturar` desistiu: descarta a leitura pendente
      const double az = c.azimute * 3.14159265358979323846 / 180, el = c.elevacao * 3.14159265358979323846 / 180;
      const QVector3D alvo3(float(c.alvo[0]), float(c.alvo[1]), float(c.alvo[2]));
      const QVector3D pos = alvo3 + float(c.distancia) * QVector3D(float(std::cos(el) * std::cos(az)), float(std::cos(el) * std::sin(az)), float(std::sin(el)));
      double longe = 20000, perto = 0.05;
      if (com_caixa) {  // perto/longe pela caixa da cena a cada quadro (como a S03)
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
        if (cap_pedida_) {
          cap_w_ = im.width(); cap_h_ = im.height();
          cap_.assign(reinterpret_cast<const char*>(im.constBits()), size_t(im.sizeInBytes()));
          cap_pedida_ = false; cap_pronta_ = true; cv_.notify_all();
        }
        rb.reset();
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
        const Fim fim = quadros(g);
        if (perdida_.exchange(false)) (void)g.sc.release();  // swapchain perdida: vaza de propósito, nunca é destruída
        if (fim == Fim::Parar) break;
      }
    } catch (const std::exception& e) {
      std::lock_guard<std::mutex> l(m_); info_ = std::string("ERRO: ") + e.what();
    } catch (...) {
      std::lock_guard<std::mutex> l(m_); info_ = "ERRO: exceção desconhecida";
    }
#ifdef Q_OS_WIN
    timeEndPeriod(1);
#endif
    { std::lock_guard<std::mutex> l(m_); rodando_ = false; cv_.notify_all(); }
    terminou_ = true;  // ÚLTIMA coisa: depois disto a thread da janela pode fazer o join
  }
  bool gl_;
  std::mutex m_, mq_, th_m_; std::condition_variable cv_; std::thread th_;
  QWindow* win_ = nullptr; QOffscreenSurface* fb_ = nullptr; QSurfaceFormat fmt_;
  bool rodando_ = false, solto_ = false, cap_pedida_ = false, cap_pronta_ = false;
  int64_t seq_placa_ = 0;  // só a thread de desenho toca
  std::string info_, cap_; int cap_w_ = 0, cap_h_ = 0;
  std::array<std::tuple<double, int64_t>, 4096> anel_{}; size_t n_ = 0;
};

// Janela nativa. Os eventos chegam pela thread da janela e só mexem em atômicos do Motor.
class Janela : public QWindow {
 public:
  Janela(std::shared_ptr<Motor> m, bool gl) : m_(std::move(m)), fb_(new QOffscreenSurface(nullptr, this)) {
#ifdef Q_OS_WIN
    if (!gl) setSurfaceType(QSurface::Direct3DSurface);
#endif
    if (gl) {  // o formato do GL tem de pedir profundidade e stencil (24/8, como o antigo adjustedFormat); o padrão do Qt pode não ter buffer de profundidade no framebuffer da janela
      QSurfaceFormat f = QSurfaceFormat::defaultFormat(); f.setDepthBufferSize(24); f.setStencilBufferSize(8);
      setSurfaceType(QSurface::OpenGLSurface); setFormat(f); fb_->setFormat(f); fb_->create();
    }
    resize(320, 240);
    m_->ligar(this, fb_);  // fb_ é filha desta janela: some junto, depois da thread
    // A saída do programa para a thread antes de a QGuiApplication sumir (caso "sair" do oráculo).
    QObject::connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, this, [m = m_] { m->parar(); });
  }
  ~Janela() override { m_->desligar(); }  // para e ESPERA a thread de desenho antes de a janela deixar de existir
 protected:
  void exposeEvent(QExposeEvent*) override { m_->exposta = isExposed(); }
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
  int64_t adicionar_lote(nb::object lote) { return m_->cena_.adicionar_lote(lote); }  // valida/copia sem o bloqueio e sem o mutex do Motor
  void limpar() { m_->cena_.limpar(); }
  nb::dict objetos(int64_t seq) { return m_->cena_.objetos(seq); }
  std::vector<std::tuple<double, int64_t>> relogio() { return m_->relogio(); }
  nb::tuple capturar() { std::tuple<int, int, std::string> r; { nb::gil_scoped_release lib; r = m_->capturar(); }
    return nb::make_tuple(std::get<0>(r), std::get<1>(r), nb::bytes(std::get<2>(r).data(), std::get<2>(r).size())); }
  nb::dict camera() {
    Camera c = m_->cam_.ler(); nb::dict d;
    d["alvo"] = nb::make_tuple(c.alvo[0], c.alvo[1], c.alvo[2]); d["distancia"] = c.distancia; d["azimute"] = c.azimute; d["elevacao"] = c.elevacao;
    return d;
  }
  void definir_camera(nb::object alvo, nb::object distancia, nb::object azimute, nb::object elevacao) {
    std::vector<double> t; if (!alvo.is_none()) { t = nb::cast<std::vector<double>>(alvo); if (t.size() != 3) throw nb::value_error("alvo = 3 números"); }
    const double dist = distancia.is_none() ? 0 : nb::cast<double>(distancia), az = azimute.is_none() ? 0 : nb::cast<double>(azimute), el = elevacao.is_none() ? 0 : nb::cast<double>(elevacao);
    m_->cam_.modificar([&](Camera& c) {
      if (!t.empty()) std::copy(t.begin(), t.end(), c.alvo);
      if (!distancia.is_none()) c.distancia = std::clamp(dist, 0.1, 10000.0);
      if (!azimute.is_none()) c.azimute = az;
      if (!elevacao.is_none()) c.elevacao = std::clamp(el, -89.0, 89.0);
    });
  }
  // T09: da thread da janela; só enfileiram (a thread de desenho aplica, na ordem). dx, dy em pixels do mouse.
  void orbitar(double dx, double dy) { m_->cam_.enfileirar({Entrada::Orbitar, dx, dy}); }
  void mover(double dx, double dy) { m_->cam_.enfileirar({Entrada::Mover, dx, dy}); }
  void aproximar(double fator) {
    if (!(fator > 0) || std::isinf(fator)) throw nb::value_error("fator deve ser maior que zero");
    m_->cam_.enfileirar({Entrada::Aproximar, fator, 0});
  }
  void enquadrar() { m_->cam_.enfileirar({Entrada::Enquadrar, 0, 0}); }
  void animar_orbita(double graus_por_s) { m_->cam_.animar(graus_por_s); }  // por relógio, não por quadro
  void parar_animacao() { m_->cam_.animar(0); }
  int64_t atualizar(nb::object lote_novo, nb::object guids_remover) { return m_->cena_.atualizar(lote_novo, guids_remover); }
  nb::dict estatisticas() { return m_->estatisticas(); }
  // T10: thread da janela. Câmera já aplicada + tamanho do último quadro; trabalha sobre cópia imutável dos dados (nenhum mutex do Motor é pedido).
  nb::object selecionar(double x, double y) {
    const int w = m_->larg_, h = m_->alt_;
    if (!std::isfinite(x) || !std::isfinite(y) || w <= 0 || h <= 0 || x < 0 || y < 0 || x >= w || y >= h) throw nb::value_error("selecionar: ponto fora da janela");
    const Camera c = m_->cam_.ler(); const auto lotes = m_->cena_.lotes(); std::optional<std::string> r;
    { nb::gil_scoped_release lib; r = obim::selecionar(lotes, raio_do_pixel(c, w, h, x, y)); }
    return r ? nb::object(nb::str(r->c_str())) : nb::none();
  }
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
      .def("adicionar_lote", &Cena::adicionar_lote, nb::arg("lote")).def("limpar", &Cena::limpar).def("objetos", &Cena::objetos, nb::arg("sequencia")).def("relogio", &Cena::relogio)
      .def("capturar", &Cena::capturar).def("camera", &Cena::camera)
      .def("definir_camera", &Cena::definir_camera, nb::arg("alvo") = nb::none(), nb::arg("distancia") = nb::none(),
           nb::arg("azimute") = nb::none(), nb::arg("elevacao") = nb::none())
      .def("orbitar", &Cena::orbitar, nb::arg("dx"), nb::arg("dy")).def("mover", &Cena::mover, nb::arg("dx"), nb::arg("dy"))
      .def("aproximar", &Cena::aproximar, nb::arg("fator")).def("enquadrar", &Cena::enquadrar)
      .def("animar_orbita", &Cena::animar_orbita, nb::arg("graus_por_s")).def("parar_animacao", &Cena::parar_animacao)
      .def("atualizar", &Cena::atualizar, nb::arg("lote_novo").none(), nb::arg("guids_remover"))
      .def("selecionar", &Cena::selecionar, nb::arg("x"), nb::arg("y")).def("estatisticas", &Cena::estatisticas).def("perder_contexto", &Cena::perder_contexto).def("info", &Cena::info);
}
