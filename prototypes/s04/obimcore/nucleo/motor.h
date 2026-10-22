// SPDX-License-Identifier: AGPL-3.0-or-later
// Viewport C++ (S04-T07; LOTE_OPUS_9 §1.4 regra 5, LOTE_OPUS_11 achados 3, 5 e 9). Janela Qt nativa (QWindow) desenhada com QRhi por
// thread própria do C++, embutida numa janela PySide6 por contêiner de janela. C++ PURO (T14b): só Qt e std, nenhum include de Python;
// um executável Qt sem Python liga este arquivo. A ponte é ponte_viewport.cpp. Posse: o Python é o dono do `Viewport` e dos arrays que
// entrega (só emprestados durante a chamada); o C++ nunca guarda endereço do Python. Mutexes: `Motor::m_` ANTES de `DadosCena::m_` (cena.h). Contratos:
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
#pragma once
#include "camera.h"
#include "cena.h"
#include <QGuiApplication>
#include <QMatrix4x4>
#include <QOffscreenSurface>
#include <QPlatformSurfaceEvent>
#include <QPointer>
#include <QResizeEvent>
#include <QScreen>
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
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include "selecao.h"
#include <stdexcept>
#include <thread>
#include <tuple>
#ifdef Q_OS_WIN
#  define WIN32_LEAN_AND_MEAN
#  define NOMINMAX
#  include <windows.h>
#  include <d3d11.h>
#  include <timeapi.h>
#endif
namespace obim {
using Rel = std::chrono::steady_clock;
double agora_ms();  // motor.cpp
extern const unsigned char QSB_VERT[], QSB_FRAG[]; extern const size_t QSB_VERT_N, QSB_FRAG_N;  // motor.cpp (QSB da S03, embutidos pelo CMake)
struct Estatisticas { size_t bytes_copia, lotes, triangulos, vertices; int64_t fatias_enviadas; int triangulos_na_placa, contextos, superficies_soltas, solturas_atrasadas, paradas_atrasadas; size_t nao_partidos, pecas_maiores_que_c; int64_t geracao; };
constexpr size_t ORCAMENTO_BYTES = 2u << 20;  // por quadro (cabe em ~1 ms no software); lote maior é partido em fatias
constexpr auto ORCAMENTO_TEMPO = std::chrono::milliseconds(4);
constexpr auto LIMITE_PARAR = std::chrono::seconds(5);  // T07e: espera máxima de Motor::parar() pela thread de desenho (depois, abandono controlado)

class Motor : public std::enable_shared_from_this<Motor> {  // a thread de desenho guarda um shared_ptr do Motor (T07e): o abandono não deixa ponteiro solto
 public:
  std::atomic<bool> exposta{false}, soltar{false}, perder{false}, parar_{false}, perdida_{false}, terminou_{true};
  std::atomic<int> contextos{0}, tri_placa{0}, superficies_soltas{0}, solturas_atrasadas{0}, paradas_atrasadas{0}, trava_ms_{0};  // trava_ms_: gancho de teste (travar_desenho_teste)
  std::atomic<bool> abandonada_{false};  // a thread atual estourou LIMITE_PARAR e foi solta (detach); só a própria thread termina o que falta
  std::atomic<int64_t> fatias_{0};
  // T10c: o que o último quadro APRESENTADO usou (câmera aplicada, tamanho real do backbuffer, plano perto), gravado junto, sob um só mutex folha (`mc_`),
  // depois do endFrame; a seleção lê tudo de uma vez (nunca câmera de um quadro com tamanho de outro).
  struct Quadro { Camera c; int larg = 0, alt = 0; double perto = 0.05; bool ok = false; };
  std::mutex mc_; Quadro quadro_;
  std::atomic<double> dpr_{1.0}, escala_teste_{0.0};  // dpr_: devicePixelRatio da janela (atualizado na thread da janela); escala_teste_ > 0 o substitui (gancho de teste)
  DadosCena cena_;  // fila de lotes, cópia compacta, sequência e caixa (T08); o Python entra direto, com mutex próprio
  explicit Motor(bool gl) : gl_(gl) {}
  ~Motor() {  // pode rodar NA thread de desenho (último dono = o shared_ptr dela): aí não há join de si mesma
    if (th_.get_id() == std::this_thread::get_id()) th_.detach(); else parar();
  }
  void ligar(QWindow* w, QOffscreenSurface* fb) { std::lock_guard<std::mutex> l(m_); win_ = w; fb_ = fb; fmt_ = w->format(); }
  void desligar() { parar(); std::lock_guard<std::mutex> l(m_); win_ = nullptr; fb_ = nullptr; }
  void iniciar() {  // qualquer thread (th_m_ guarda th_)
    { std::lock_guard<std::mutex> l(m_); if (!win_) return; }
    std::lock_guard<std::mutex> lt(th_m_);
    if (th_.joinable()) return;
    if (abandonada_) { if (!terminou_) return; abandonada_ = false; }  // thread abandonada ainda presa: não inicia outra por cima
    parar_ = false; perdida_ = false; terminou_ = false;
    { std::lock_guard<std::mutex> l(m_); rodando_ = true; }
    th_ = std::thread([self = shared_from_this()] { self->laco(); });
  }
  void parar() {  // espera a thread; idempotente; qualquer thread. Bombeia mensagens até `terminou_`; só então faz o join.
    parar_ = true;
    if (abandonada_) return;  // thread já abandonada (e ainda presa): nada a esperar, nem a contar de novo
    const auto fim = Rel::now() + LIMITE_PARAR;
    while (!terminou_) {
      if (Rel::now() >= fim) { abandonar(); return; }
      bombear(); std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
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
  Estatisticas estatisticas() {
    std::lock_guard<std::mutex> l(m_);  // Motor::m_ e, dentro de totais(), DadosCena::m_: sempre nesta ordem
    const Totais t = cena_.totais();
    return {t.bytes, t.lotes, t.triangulos, t.vertices, fatias_.load(), tri_placa.load(), contextos.load(), superficies_soltas.load(), solturas_atrasadas.load(), paradas_atrasadas.load(), t.nao_partidos, t.pecas_maiores_que_c, t.ger};
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
  bool software() const { return software_.load(); }  // true: sem placa de vídeo compatível, o desenho está sendo feito por software (F0-RG-13)
  std::string aviso() const {  // texto pronto para mostrar ao usuário; vazio quando a placa de vídeo é usada
    return software_.load() ? "Sem placa de vídeo compatível: o desenho está sendo feito por software e fica mais lento." : "";
  }

 private:
  void abandonar() {  // T07e: a thread de desenho não saiu em LIMITE_PARAR (no Windows com WARP, `~QRhi` pode parar para sempre): solta a thread, conta uma vez
    { std::lock_guard<std::mutex> lt(th_m_); if (th_.joinable()) th_.detach(); }
    if (abandonada_.exchange(true)) return;
    ++paradas_atrasadas;
    std::lock_guard<std::mutex> l(m_);
    rodando_ = false; info_ += " | AVISO: a thread de desenho não terminou em 5 s e foi abandonada (vazamento controlado)"; cv_.notify_all();
  }
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
  struct L { std::unique_ptr<QRhiBuffer> vb, ib; quint32 n = 0; };
  struct Pend { std::shared_ptr<Dados> d; L e; size_t voff = 0, ioff = 0; size_t pos = 0; };  // lote em envio, em fatias; `pos`: posição dele na cena
  struct Slot { std::shared_ptr<Dados> d; L e; };  // o que está (ou ficou pronto) na placa numa posição da cena
  struct Gpu {  // a ordem importa: o destruidor libera de baixo para cima e a QRhi por último
    std::unique_ptr<QRhi> rhi; std::unique_ptr<QRhiSwapChain> sc; std::unique_ptr<QRhiRenderBuffer> ds;
    std::unique_ptr<QRhiRenderPassDescriptor> rp; std::unique_ptr<QRhiBuffer> ub; std::unique_ptr<QRhiShaderResourceBindings> srb;
    std::unique_ptr<QRhiGraphicsPipeline> pipe; bool pronta = false;
    // T30b2: a placa é uma visão POR POSIÇÃO do instantâneo da cena. `pos`: o que o desenho usa (completo); `prontos`: versões novas já completas à espera da
    // entrada atômica; `pend`: a que está sendo enviada. Tudo some junto com a placa: a perda de contexto reenvia tudo.
    std::vector<Slot> pos; std::map<size_t, Slot> prontos; Pend pend; int64_t ger = -1;
  };
  bool criar(Gpu& g) {
    QRhi::Flags fl;  // renderizador por software só com a variável do Qt (o CI a liga no WARP)
    if (qEnvironmentVariableIntValue("QSG_RHI_PREFER_SOFTWARE_RENDERER") != 0) fl |= QRhi::PreferSoftwareRenderer;
    QWindow* w; QOffscreenSurface* fb; QSurfaceFormat fmt;
    { std::lock_guard<std::mutex> l(m_); w = win_; fb = fb_; fmt = fmt_; }
    if (!w) return false;
    auto abrir = [&](QRhi::Flags f) {
      if (gl_) { QRhiGles2InitParams p; p.fallbackSurface = fb; p.window = w; p.format = fmt; g.rhi.reset(QRhi::create(QRhi::OpenGLES2, &p, f)); }
#ifdef Q_OS_WIN
      else { QRhiD3D11InitParams p; g.rhi.reset(QRhi::create(QRhi::D3D11, &p, f)); }
#endif
    };
    software_ = false;  // sem aviso velho se a criação falhar
    abrir(fl);
    bool refeito = false;
#ifdef Q_OS_WIN
    if (!g.rhi && !gl_ && !fl.testFlag(QRhi::PreferSoftwareRenderer)) { abrir(fl | QRhi::PreferSoftwareRenderer); refeito = true; }  // sem placa (máquina virtual, área de trabalho remota): WARP; no OpenGL o Qt ignora o pedido
#endif
    if (!g.rhi) return false;
    const QRhiDriverInfo di = g.rhi->driverInfo();  // o aviso só vale quando o dispositivo de fato é de software
    const QString nome = di.deviceName;
    software_ = refeito || di.deviceType == QRhiDriverInfo::CpuDevice || nome.contains("llvmpipe", Qt::CaseInsensitive) ||
                nome.contains("softpipe", Qt::CaseInsensitive) || nome.contains("SwiftShader", Qt::CaseInsensitive) ||
                nome.contains("Microsoft Basic Render", Qt::CaseInsensitive);
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
    g.pipe->setShaderStages({{QRhiShaderStage::Vertex, sh(QSB_VERT, QSB_VERT_N)}, {QRhiShaderStage::Fragment, sh(QSB_FRAG, QSB_FRAG_N)}});
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
  // T30b2: compara o instantâneo da cena com a placa, por posição. Lote novo (posição além da placa) e sub-lote trocado (mesma posição, ponteiro diferente) são
  // reenviados; os demais não. Fila: novos antes dos trocados. Sem trocado no plano, cada novo entra ao completar (prefixo contínuo, como antes). Com trocado, o
  // lote novo e os trocados entram JUNTOS, no quadro em que o último completa, e só então a sequência da placa avança (nunca duas paredes nem nenhuma).
  void enviar(Gpu& g, QRhiResourceUpdateBatch* rub) {  // orçamento por quadro; sempre da cópia compacta; só lotes COMPLETOS entram no desenho
    const Instantaneo s = cena_.instantaneo();  // uma chamada só, sem segurar Motor::m_ (ordem Motor::m_ → DadosCena::m_ → mc_ intocada)
    if (s.ger != g.ger || s.lotes.size() < g.pos.size()) {  // limpar() (ou perda de contexto): a placa volta a zero e tudo é reenviado
      g.pos.clear(); g.prontos.clear(); g.pend = {}; g.ger = s.ger; tri_placa = 0; seq_placa_ = 0;
    }
    const size_t n = s.lotes.size();
    auto vigente = [&](size_t q, const auto& d) { return q < n && s.lotes[q] == d; };  // falso = troca repetida: a versão preparada ficou velha
    for (auto it = g.prontos.begin(); it != g.prontos.end();) it = vigente(it->first, it->second.d) ? std::next(it) : g.prontos.erase(it);
    if (g.pend.d && !vigente(g.pend.pos, g.pend.d)) g.pend = {};
    std::vector<size_t> fila; bool trocado = false;  // novos primeiro, depois os trocados
    auto falta = [&](size_t p) { return !g.prontos.count(p) && !(g.pend.d && g.pend.pos == p); };
    for (size_t p = g.pos.size(); p < n; ++p) if (falta(p)) fila.push_back(p);
    for (size_t p = 0; p < g.pos.size(); ++p) if (s.lotes[p] != g.pos[p].d) { trocado = true; if (falta(p)) fila.push_back(p); }
    size_t gasto = 0; const auto t0 = Rel::now();
    auto prox = fila.begin();
    while (gasto < ORCAMENTO_BYTES && Rel::now() - t0 < ORCAMENTO_TEMPO) {
      Pend& p = g.pend;
      if (!p.d) {
        if (prox == fila.end()) break;
        const size_t q = *prox++; const auto& d = s.lotes[q];
        if (d->i.empty()) { g.prontos[q] = {d, {}}; continue; }  // lote sem triângulos: já "na placa"
        p.pos = q; p.voff = p.ioff = 0; p.e.n = quint32(d->i.size());
        p.e.vb.reset(g.rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::VertexBuffer, quint32(d->v.size())));
        p.e.ib.reset(g.rhi->newBuffer(QRhiBuffer::Immutable, QRhiBuffer::IndexBuffer, quint32(d->i.size() * 4)));
        if (!p.e.vb->create() || !p.e.ib->create()) {  // achado 5: o lote NÃO se perde; continua pendente e repete no quadro seguinte
          --prox; p = {}; { std::lock_guard<std::mutex> l(m_); info_ = "AVISO: create() de buffer falhou; repetindo no quadro seguinte"; } break;
        }
        p.d = d;
      }
      const bool vert = p.voff < p.d->v.size();  // primeiro os vértices, depois os índices
      const size_t total = vert ? p.d->v.size() : p.d->i.size() * 4, off = vert ? p.voff : p.ioff, un = vert ? BYTES_VERTICE : 4;
      const size_t m = (std::min)(total - off, (ORCAMENTO_BYTES - gasto) / un * un);  // fatia em múltiplo de `un`: o quadro nunca passa de ORCAMENTO_BYTES
      if (!m) break;
      const unsigned char* dados = vert ? p.d->v.data() : reinterpret_cast<const unsigned char*>(p.d->i.data());
      rub->uploadStaticBuffer(vert ? p.e.vb.get() : p.e.ib.get(), quint32(off), quint32(m), dados + off);
      (vert ? p.voff : p.ioff) += m; gasto += m; ++fatias_;
      if (p.voff == p.d->v.size() && p.ioff == p.d->i.size() * 4) { g.prontos[p.pos] = {std::move(p.d), std::move(p.e)}; p = {}; }  // completo, ainda fora do desenho
    }
    // Entrada: sem trocado, o prefixo contínuo de novos prontos; com trocado, tudo de uma vez e só quando nada falta.
    const bool tudo = trocado && prox == fila.end() && !g.pend.d;
    auto entrar = [&](Slot&& sl, size_t q) {
      const int novo = int(sl.d->i.size() / 3);
      if (q == g.pos.size()) { tri_placa += novo; g.pos.push_back(std::move(sl)); }
      else { tri_placa += novo - int(g.pos[q].d->i.size() / 3); g.pos[q] = std::move(sl); }
      seq_placa_ = (std::max)(seq_placa_, g.pos.back().d->seq);  // sequência = a do último lote que a placa tem por inteiro
    };
    if (tudo) { for (auto& [q, sl] : g.prontos) entrar(std::move(sl), q); g.prontos.clear(); }
    else if (!trocado) {
      for (auto it = g.prontos.find(g.pos.size()); it != g.prontos.end(); it = g.prontos.find(g.pos.size())) { entrar(std::move(it->second), it->first); g.prontos.erase(it); }
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
      for (auto& sl : g.pos) {
        auto& e = sl.e; if (!e.n) continue;
        const QRhiCommandBuffer::VertexInput vi(e.vb.get(), 0);
        cb->setVertexInput(0, 1, &vi, e.ib.get(), 0, QRhiCommandBuffer::IndexUInt32);
        cb->drawIndexed(e.n);
      }
      QRhiResourceUpdateBatch* rub2 = nullptr;
      if (pedida && !rb) { rb = std::make_unique<QRhiReadbackResult>(); rub2 = g.rhi->nextResourceUpdateBatch(); rub2->readBackTexture(QRhiReadbackDescription(), rb.get()); }
      cb->endPass(rub2);
      const auto fim = g.rhi->endFrame(g.sc.get());
      if (fim == QRhi::FrameOpDeviceLost) return Fim::Perdido;
      { std::lock_guard<std::mutex> l(mc_); quadro_ = {c, alvo.width(), alvo.height(), perto, true}; }  // T10c: câmera, tamanho e perto do quadro apresentado
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
  void ociosa(Gpu& g) {  // T07e: antes de destruir a QRhi, a GPU fica ociosa (o `Flush` final do WARP não encontra trabalho em voo)
    g.rhi->finish();
#ifdef Q_OS_WIN
    if (!gl_) if (auto* nh = static_cast<const QRhiD3D11NativeHandles*>(g.rhi->nativeHandles())) if (nh->context) {
      auto* cx = static_cast<ID3D11DeviceContext*>(nh->context); cx->ClearState(); cx->Flush();
    }
#endif
  }
  void laco() {
#ifdef Q_OS_WIN
    timeBeginPeriod(1);
#endif
    try {
      for (int falhas = 0; !parar_;) {
        auto gp = std::make_unique<Gpu>(); Gpu& g = *gp;  // destruído ao sair do bloco, NESTA thread (salvo o abandono: ver abaixo)
        if (!criar(g)) {
          { std::lock_guard<std::mutex> l(m_); info_ = "ERRO: QRhi não pôde ser criada"; }
          if (++falhas >= 3) break;  // `rodando` vira falso: viva() informa
          std::this_thread::sleep_for(std::chrono::milliseconds(100)); continue;
        }
        falhas = 0;
        const Fim fim = quadros(g);
        if (fim == Fim::Parar) ociosa(g);
        if (fim == Fim::Parar && trava_ms_ > 0) std::this_thread::sleep_for(std::chrono::milliseconds(trava_ms_.exchange(0)));  // gancho de teste: finge o travamento do `~QRhi`; não olha `parar_`
        if (fim == Fim::Parar && abandonada_) { (void)gp.release(); break; }  // ninguém mais espera: janela e superfície podem não existir; a placa vaza de propósito
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
  std::atomic<bool> software_{false};
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
    m_->dpr_ = devicePixelRatio();
    QObject::connect(this, &QWindow::screenChanged, this, [this](QScreen*) { m_->dpr_ = devicePixelRatio(); });
    m_->ligar(this, fb_);  // fb_ é filha desta janela: some junto, depois da thread
    // A saída do programa para a thread antes de a QGuiApplication sumir (caso "sair" do oráculo).
    QObject::connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, this, [m = m_] { m->parar(); });
  }
  ~Janela() override { m_->desligar(); }  // para e ESPERA a thread de desenho antes de a janela deixar de existir
 protected:
  void exposeEvent(QExposeEvent*) override { m_->exposta = isExposed(); m_->dpr_ = devicePixelRatio(); }
  void resizeEvent(QResizeEvent* e) override { m_->dpr_ = devicePixelRatio(); QWindow::resizeEvent(e); }
  bool event(QEvent* e) override {
    if (e->type() == QEvent::PlatformSurface && static_cast<QPlatformSurfaceEvent*>(e)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed)
      m_->soltar_superficie();
    return QWindow::event(e);
  }
 private:
  std::shared_ptr<Motor> m_; QOffscreenSurface* fb_;
};

class Viewport {  // o Qt é dono do contêiner (depois de posto num layout); esta classe só guarda o Motor e um ponteiro fraco. Erros: std::invalid_argument / std::runtime_error
 public:
  explicit Viewport(bool gl) : m_(std::make_shared<Motor>(gl)) {
    if (!QGuiApplication::instance()) throw std::runtime_error("crie a QApplication antes da Cena");
    cont_ = QWidget::createWindowContainer(new Janela(m_, gl), nullptr);
  }
  ~Viewport() {
    m_->parar();
    if (cont_ && !cont_->parent()) { if (QThread::currentThread() == cont_->thread()) delete cont_.data(); else cont_->deleteLater(); }
  }
  uintptr_t viewport_ptr() const { return reinterpret_cast<uintptr_t>(cont_.data()); }
  void iniciar() { m_->iniciar(); }
  void parar() { m_->parar(); }
  bool viva() { return m_->viva(); }
  int64_t adicionar_lote(const LoteBruto& lote) { return m_->cena_.adicionar_lote(lote); }  // valida/copia sem o mutex do Motor
  void limpar() { m_->cena_.limpar(); }
  std::shared_ptr<Dados> lote(int64_t seq) { return m_->cena_.lote(seq); }
  std::vector<std::tuple<double, int64_t>> relogio() { return m_->relogio(); }
  std::tuple<int, int, std::string> capturar() { return m_->capturar(); }
  Camera camera() { return m_->cam_.ler(); }
  void definir_camera(const std::optional<std::array<double, 3>>& alvo, std::optional<double> distancia, std::optional<double> azimute, std::optional<double> elevacao) {
    m_->cam_.modificar([&](Camera& c) {
      if (alvo) std::copy(alvo->begin(), alvo->end(), c.alvo);
      if (distancia) c.distancia = std::clamp(*distancia, 0.1, 10000.0);
      if (azimute) c.azimute = *azimute;
      if (elevacao) c.elevacao = std::clamp(*elevacao, -89.0, 89.0);
    });
  }
  // T09: da thread da janela; só enfileiram (a thread de desenho aplica, na ordem). dx, dy em pixels do mouse.
  void orbitar(double dx, double dy) { m_->cam_.enfileirar({Entrada::Orbitar, dx, dy}); }
  void mover(double dx, double dy) { m_->cam_.enfileirar({Entrada::Mover, dx, dy}); }
  void aproximar(double fator) {
    if (!(fator > 0) || std::isinf(fator)) throw std::invalid_argument("fator deve ser maior que zero");
    m_->cam_.enfileirar({Entrada::Aproximar, fator, 0});
  }
  void enquadrar() { m_->cam_.enfileirar({Entrada::Enquadrar, 0, 0}); }
  void animar_orbita(double graus_por_s) { m_->cam_.animar(graus_por_s); }  // por relógio, não por quadro
  void parar_animacao() { m_->cam_.animar(0); }
  int64_t atualizar(const LoteBruto* lote_novo, std::set<std::string> guids_remover) { return m_->cena_.atualizar(lote_novo, std::move(guids_remover)); }
  Estatisticas estatisticas() { return m_->estatisticas(); }
  // T10/T10c: (x, y) em pixels LÓGICOS (os do mouse do Qt); o pixel físico do backbuffer é lógico * devicePixelRatio. Câmera, tamanho e `perto` vêm juntos do último
  // quadro apresentado; trabalha sobre cópia imutável dos dados (nenhum mutex do Motor é pedido).
  std::optional<std::string> selecionar(double x, double y) {
    Motor::Quadro q; { std::lock_guard<std::mutex> l(m_->mc_); q = m_->quadro_; }
    double r = m_->escala_teste_.load(); if (!(r > 0)) r = m_->dpr_.load();
    const double px = x * r, py = y * r;
    if (!q.ok || !std::isfinite(x) || !std::isfinite(y) || q.larg <= 0 || q.alt <= 0 || x < 0 || y < 0 || px >= q.larg || py >= q.alt) throw std::invalid_argument("selecionar: ponto fora da janela");
    return obim::selecionar(m_->cena_.lotes(), raio_do_pixel(q.c, q.larg, q.alt, px, py, q.perto));
  }
  void definir_escala_teste(double r) {  // gancho de teste: usa r (> 0) no lugar do devicePixelRatio real
    if (!std::isfinite(r) || r <= 0) throw std::invalid_argument("escala deve ser maior que zero");
    m_->escala_teste_ = r;
  }
  void travar_desenho_teste(int ms) {  // gancho de teste: na próxima parada, a thread dorme `ms` antes de destruir a placa (finge o travamento do WARP)
    if (ms < 0) throw std::invalid_argument("ms deve ser zero ou maior");
    m_->trava_ms_ = ms;
  }
  void perder_contexto() { m_->perder = true; }  // gancho de teste: simula FrameOpDeviceLost
  std::string info() { return m_->info(); }
  bool desenho_por_software() { return m_->software(); }  // F0-RG-13: true quando não há placa de vídeo compatível
  std::string aviso() { return m_->aviso(); }  // texto para mostrar ao usuário; vazio com placa de vídeo
 private:
  std::shared_ptr<Motor> m_; QPointer<QWidget> cont_;
};
}  // namespace obim
