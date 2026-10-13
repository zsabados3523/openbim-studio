<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE OPUS 17: revisão do PR 73 (ramo s04-t10c, F0-S04-T10c)
Revisor opus, só leitura, 2026-10-13. **APROVADO, sem achados bloqueantes.** Condição: `linux` e `windows` verdes (o Windows é a única prova do caminho D3D11/WARP com QT_SCALE_FACTOR real).

## Achados 1–7 do lote 16
1. Escala de tela: FECHADO (viewport.cpp:427-433; pixels lógicos × dpr, faixa [0, larg/r); raio em coordenada contínua; oráculo cobre 1,0/1,25/1,5/2,0 simulada e 1,25/1,5/2 real).
2. Câmera e tamanho em sincronia: FECHADO (viewport.cpp:291, mutex folha `mc_` depois do `endFrame`).
3. Caixa pelos triângulos: FECHADO (cena.cpp:43-50, usado em `preparar` e `sem`; custo de poucos ms; NaN sem geometria).
4. Raio a partir de `perto`: FECHADO (tmin = perto/cos θ; selecao.cpp:56-57; consistente com GL e D3D11).
5. Registro no ADR-004: ABERTO, fora do escopo (não existe ADR-004 ainda).
6. `bytes_copia` com GlobalId: FECHADO (cena.cpp:190).
7. Lacunas (a)–(h) do oráculo: FECHADO (tests/test_s04_selecao_c.py).
D3D11: sem regressão visível.

## Recomendações (nenhuma bloqueante)
1. Desalinhamento momentâneo escala × backbuffer (viewport.cpp:76, 360, 367-368, 429): ler `dpr_` na thread de desenho junto com `currentPixelSize()`; tratar `QEvent::DevicePixelRatioChange`.
2. Escala fracionária no Windows (viewport.cpp:431): backbuffer pode ficar 1 px menor; limitar px/py a [0, larg-1] em vez de ValueError.
3. `definir_escala_teste` fica público (viewport.cpp:436-439, 460): marcar interno ao promover a viewport.
4. cena.cpp:190: `capacity() > 15` vale em libstdc++ e MSVC; na libc++ (macOS) conta 23 B a mais por objeto; alternativa portátil: ver se `data()` aponta para dentro da string.
5. Lacunas: troca de escala durante a sessão; triângulo que atravessa o plano perto; `c_redim` aceita qualquer resultado durante o redimensionamento.
6. Achado 5 do lote 16: registrar no ADR-004 quando existir.

## Para o PO
O clique acerta a peça certa também com a tela do Windows em 125%, 150% ou 200%; peças coladas demais na câmera, que não aparecem, não são escolhidas; a busca segue abaixo de 100 ms no modelo de 1 milhão. Restam ajustes pequenos (clique logo após trocar a janela de monitor).
