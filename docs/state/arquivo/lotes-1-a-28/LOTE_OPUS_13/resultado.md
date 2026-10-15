# Lote Opus 13: conferência curta do PR 62 (o que veio depois do lote 12)
Revisor: opus, só leitura, 2026-10-13. Conferiu os commits 660110e (oráculo), ad67934 e 7bbbfde (diagnóstico) e 71ef907 (correção em C++); leu `viewport.cpp` inteiro e `qsize.h`/`qhighdpiscaling_p.h` do Qt 6.11.2.

## Veredito: REPROVADO na forma atual; vira APROVADO sem nova sessão Opus com 5 condições
(a) mudanças 1 e 2 exatamente como abaixo; (b) linux e windows verdes numa rodada **sem a espera de 1,5 s**; (c) relatório `docs/state/reports/F0-S04-T07.md` com as 5 rodadas × 4 fases dos dois sistemas (maior intervalo, p99, nº acima de 33 ms) tiradas dessa rodada final (condição do lote 12, ainda aberta); (d) LOG registra os itens 6 e 7; (e) nenhuma outra mudança em C++.

## Achados
1. (B) A correção em `quadros()` tem caminho de queda e devolve o defeito com escala fracionária. Causa raiz do defeito original: o código antigo comparava `surfacePixelSize()` com `larg/alt` (os dois são o tamanho da janela), nunca olhava `currentPixelSize()`; no GL o framebuffer acompanha a janela, no D3D11 o backbuffer tem tamanho fixo. A correção do implementador (aspecto e viewport do backbuffer real) está certa, mas o contador: `larg/alt` truncam (`int(width()*dpr)`) e o Qt arredonda; com escala 125% ou 150% e largura ímpar nunca casam → (i) `tentativas` chega a 5 e nunca mais refaz a swapchain (defeito volta); (ii) após `soltar` (troca de pai), `g.pronta` falso mas `!casa && tentativas<5` falso → segue a `beginFrame` com swapchain destruída (queda provável). O CI roda com escala 1 e não pega. Ação: mudança 1.
2. (I) Diagnóstico do oráculo deve sair: 412 linhas (>400), prints/PNG não aparecem em CI verde, PIL é dependência nova, e o `yield 1500` pode **mascarar** o defeito (o verde atual do Windows foi com essa espera). Ação: mudança 2.
3. (ok) Mudanças 1 a 6 do lote 12 aplicadas como descritas; oráculo fechava em 400 no 660110e.
4. (I) Mesma classe: `soltar_superficie`/troca de pai = caminho de queda do 1(ii); perda de contexto sem risco; `capturar` lê o backbuffer (se velho, 3 cubos "certos" enquanto o DXGI estica) → o caso `trocar` precisa conferir o tamanho da captura contra o contêiner; troca de monitor com escala diferente pode não gerar `resizeEvent` (a mudança 1 cobre, decide por `surfacePixelSize()`); `sonda_desenho.cpp:105` tem o padrão antigo (M, só registrar).
5. (I) GL: mudança 1 inofensiva. Redimensionar durante o desenho: aspecto, viewport e alvo saem do mesmo `currentPixelSize()` no quadro; coerente. Ler o tamanho do `QWindow` na thread de desenho é corrida formal (prática dos exemplos do QRhi), aceita, registrar no T07b. No máximo 1 `ResizeBuffers` por redimensionamento. Achado 5 do lote 11 (~30 → ~17 ms) **fecha** quando a rodada final confirmar.
6. (I) Risco novo: agora a swapchain é redimensionada a cada redimensionamento real: exercita a hipótese (a) do lote 12 (impasse no Windows ao criar, redimensionar ou destruir a swapchain com a thread da janela esperando sem bombear mensagens). **T07b é o próximo cartão logo após o merge, antes da T08.** Gatilho do lote 12 continua.
7. (M) Processo: os commits de diagnóstico mexeram no oráculo e todos têm o mesmo autor; registrar quem fez (**fez o agente de investigação, por ordem do líder, só para diagnóstico: não foi o implementador**). A correção em C++ entrou depois do lote 12 sem revisão; aceita aqui só com a mudança 1.
8. (M) `faulthandler` da sonda dispara aos 240 s mas o passo de 5 min inclui o cmake: se o build no Windows passar de ~50 s, mover o build para fora do passo ou baixar o `faulthandler` para 180 s (T07b).

## Mudanças autorizadas (exatas)
**Mudança 1 (implementador sonnet; só `viewport.cpp`, só `quadros()`):** remover `int tentativas = 0;` e todas as linhas com `tentativas`/`casa`/`esperado` (~200 a 207); no lugar: 
`// O que vale é o tamanho REAL do backbuffer; refaz a swapchain quando ele diverge do tamanho atual da superfície (padrão do QRhi).`
`if (g.sc->surfacePixelSize().isEmpty()) { prox = Rel::now(); continue; }`
`if (!g.pronta || g.sc->currentPixelSize() != g.sc->surfacePixelSize()) { g.pronta = g.sc->createOrResize(); if (!g.pronta) continue; }`
Linha ~226: `const QSize alvo = g.sc->currentPixelSize();  // tamanho real do backbuffer`. `larg/alt` e `atualiza()` ficam (remoção é do T07b). Nada mais em C++.
**Mudança 2 (agente de oráculo, nunca o implementador; só `tests/test_s04_viewport.py`, só `c_trocar` e `test_trocar_...`):** reverter por inteiro os dois commits de diagnóstico (sai `res["img0"]`, `yield 1500`, `fundo`, `res["diag"]`, o print `DIAG`, o bloco PIL/PNG); no lugar: `img = captura(c)` e `res.update(viva=c.viva(), cls=classificar(img), tam=list(img.shape), cont=[cont.width(), cont.height()], dpr=cont.devicePixelRatioF())`; no teste, asserção de tamanho no padrão de `test_imagem` (altura ≈ `round(cont[1]*dpr)`, largura ≈ `round(cont[0]*dpr)`, ±2, com mensagem). Arquivo ≤400 linhas; se a asserção não couber, vai ao T06b e só a reversão entra agora.

## Cartões
**T07b** acrescentar: (i) próximo cartão logo após o merge, antes da T08; (j) o 9.b ("swapchain perdida, nunca mais tocar") também impede o `createOrResize` do novo laço de tamanho; (k) remover `larg/alt`/`atualiza()` se ficarem sem uso, ou empacotar num atômico; (l) item 8 (tempo do build na sonda); (m) `sonda_desenho.cpp:105` só se a sonda voltar a ser usada.
**T06b** acrescentar: (g) asserção de tamanho da captura contra o contêiner em `trocar` (se não couber agora), e depois de cada redimensionamento; (h) uma rodada do caso `trocar` com `QT_SCALE_FACTOR=1.25` nos dois sistemas (pega o achado 1); (i) `superficies_soltas ≥ 1` em `trocar`.

## Resumo para o PO (5 linhas)
1. A correção do cubo azul cortado no Windows achou a causa certa: a imagem era desenhada num tamanho e a tela tinha outro.
2. Do jeito que foi escrita, falha em telas com escala de 125% ou 150%, comuns em notebooks com Windows: o corte volta e o programa pode fechar ao trocar a vista de janela.
3. Autorizo uma troca pequena de 3 linhas, o modo padrão recomendado pelo próprio Qt, e a retirada das linhas de diagnóstico do teste, que podiam esconder o defeito.
4. Aplicado isso, com os dois sistemas verdes e os números anotados no relatório, a junção sai sem nova revisão minha.
5. Logo depois vem a proteção contra travamento no Windows (T07b), antes da fila de lotes (T08), porque agora esse caminho é mais usado.
