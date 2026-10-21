<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# ADR-001: Stack (híbrido Python + C++ ou C++ puro), ponte, pythonocc e Rust
- Status: **proposto; direção decidida pelo PO** (2026-10-21, no chat: "manter a estrutura híbrida; C++ puro rejeitado como não necessário"). O texto deste ADR ainda depende da aprovação do PO pelo resumo de 5 linhas. Passa a "aceito" só com essa aprovação **e** com a medição de fechamento da S04 (§7, itens A1 e A2).
- Autor: opus (cartão F0-S04-T19, classe TA, lote Opus 68) · Data: 2026-10-21
- Base: especificação da S04 (`docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_9/resultado.md` §1 a §6: casos R1, metas M1 a M7, regra de leitura §3, esqueleto §5.1); `v2/03` F0-S04 e §3; ADR-005 §7.1 e §10; relatórios `docs/state/reports/F0-S04.md` (medição oficial de 2026-10-17), `F0-S04-T21`, `T22`, `T24`, `T29-placa-memoria` (e `-2`), `T29e-ensaio`, `T30-placa`, `T30c-dados-reais`, `T23`, `F0-S04-threads.md`; lotes Opus 57, 62, 65 e 66; `PO.md` (decisões de 17 e 18/10).
- Escopo: o tema "Stack, ponte, papel do pythonocc, Rust" de `v2/03 §3`. Threads e trava do modelo ficam no ADR-004. Não muda `v2/` nem `CLAUDE.md`.

## Resumo para o PO (5 linhas)
1. O programa fica como planejado: janelas e comandos em Python, desenho 3D e cálculo das peças num núcleo próprio em C++, os dois lendo o mesmo modelo na memória, sem cópia, no Windows e no Linux.
2. As metas de velocidade ao criar e editar paredes passam com folga de 2,6 vezes ou mais; o que reprovou em 17/10 (memória do arquivo pesado e troca de parede em arquivo real) estava no núcleo C++ e no processo de abertura, partes iguais nos dois caminhos, e foi corrigido lá.
3. Na sua placa de vídeo a memória do arquivo pesado ficou em 5,96 gigabytes no pior de 6 aberturas (meta 6,0: passa por só 42 megabytes) e a troca de parede ficou abaixo de 83 milésimos de segundo (meta 200).
4. Escrever tudo em C++ não resolveria nenhuma meta que falhou e custaria de 20% a 40% a mais de calendário; por isso fica rejeitado, como você decidiu.
5. Ainda faltam: a medição final completa na placa, conferir que os arquivos simples e detalhado não pioraram, o Windows com placa real, e o teste automático do Windows, que caiu de 34 para 17 minutos mas não chegou aos 10.

## 1. Contexto
`v2/03` (F0-S04) manda construir o mesmo fluxo de duas formas e decidir a stack com números:
- **A (híbrido):** PySide6 e `ifcopenshell.api` editam; o módulo C++ `obimcore` (nanobind) recebe o mesmo `ifcopenshell.file`, sem cópia, e faz malha e desenho.
- **B (C++ puro):** o mesmo fluxo com IfcOpenShell C++ e Qt Widgets.

Regra de decisão de `v2/03`: o híbrido é aprovado se atinge as metas absolutas, mesmo que seja mais lento que o B. Só a falha estável em compartilhar o modelo sem cópia manda para o C++ puro. O lote 9 §3 detalha a leitura: M1 a M5 atingidas nos dois sistemas; M6 é acompanhamento (decisão do PO em 2026-10-12: só pesa se alguma meta absoluta ficar com menos de 2 vezes de folga).

A e B **compartilham o núcleo C++** (malha, cena, viewport com thread de desenho própria, seleção, relógio); diferem só na camada de edição e na casca da janela (lote 9 §1.2). Por isso uma falha no núcleo vale para os dois.

## 2. Opções
1. **Híbrido, como em `v2/02 §5`** (Python para interface, comandos e regras; C++ para malha, cena e desenho).
2. **C++ puro no núcleo**, Python só para complementos e regras.
3. **Híbrido com os comandos de edição em processo separado** (só se M5 falhasse nas formas 1 e 2; não falhou: M5 ficou entre 16,7 e 17,8 ms nas duas formas, `F0-S04-threads.md`).

## 3. Números medidos
Linux oficial = máquina do PO, Intel Core i5-12600KF, 23 GB, NVIDIA GeForce RTX 3070, driver 580.178.04, tela real, desenho por software falso. Windows = só o CI do GitHub, desenho por software (WARP), máquina compartilhada; nunca conta como oficial.

### 3.1 Metas da S04 (base sintética de 3.000 paredes; `reports/F0-S04.md`, 2026-10-17; mediana / p95 em ms)
| Meta | Alvo | Linux, placa real | Windows, WARP | Situação |
|---|---|---|---|---|
| M1. Mesmo modelo sem cópia (R1-a a R1-j) | todos passam | passam, também dentro do AppImage | passam, também dentro do instalador | atingida |
| M2. Criar 1 parede e atualizar a tela | p95 < 200 | 32,9 / 49,7 | 28,5 / 59,8 | atingida |
| M3. Editar propriedade e refletir no painel | p95 < 50 | 0,74 / 1,47 | 2,2 / 3,5 | atingida |
| M4. Lote de 1.000 paredes | < 20 s | 2,15 s | 5,83 s | atingida |
| M5. Tela não congela no lote | janela de 1 s com 20 quadros ou mais; maior intervalo < 200 ms | maior intervalo 17,9 ms | 32,1 ms | atingida |
| M6. Razão A ÷ B em M2, M2b, M3, M4 | acompanhamento | 1,00 / 0,995 / 0,313 / 16,2; folga mínima 3,04 | 0,92 / 1,44 / 1,44 / 19,3; folga mínima 2,63 | registrada; não pesa (folga ≥ 2 nos dois) |
| Saída igual (A e B gravam o mesmo IFC) | juiz estrito | aprovado | — (juiz roda na máquina do PO) | atingida |
| M7. Linhas sem comentários e sem linhas vazias | registrar | `obimcore` 1.259; fluxo A 1.013; fluxo B 1.278 | — | registrada; tempo de agente **não medido** |

### 3.2 Troca de geometria de uma parede (M2b, alvo p95 < 200 ms; vale também para parede vinda do arquivo, A30)
| Caso | 2026-10-17 (oficial) | Depois da T-2 (sub-lotes de até 8 MiB e reenvio só do sub-lote trocado), placa real, 2026-10-20 (`T30-placa`) |
|---|---|---|
| Sintética 3.000 | 49,3 / 65,9 (máx 82,8) | mediana 32,7; pior 49,7 (parede do arquivo) e 82,8 (parede criada) |
| 25 MB | 399 / 414,6 | mediana 32,6; pior 49,6 e 81,6 |
| Detalhado | 6.749 / 6.764 | mediana 48,9; pior 65,2 e 78,4 |
Leitura: a troca passou a custar 2 a 3 quadros em qualquer tamanho; o p95 de qualquer caso fica abaixo do pior valor, 82,8 ms. Em dados reais, nenhuma parede caiu em sub-lote acima de 8 MiB nos três arquivos do PO (`T30c-dados-reais`). Medido pela sonda `sonda_m2b`, não pela medição oficial completa (ver A1).

### 3.3 Abertura do arquivo pesado (meta herdada da S03: pico somado < 6,0 GB e abrir ≤ 60 s; régua A28: 5 aberturas, ou 3 em dois dias, vale a pior)
| Medida | 2026-10-17 (oficial, bloco 1.000) | 2026-10-21, placa real, bloco 250 e reinício planejado do processo auxiliar (T29) |
|---|---|---|
| Pico somado (pai + maior filho) | 6.841 MB | 1ª série: 5.863 / 5.874 / 5.861; 2ª série: 5.895 / 5.785 / **5.958** (pior das 6) |
| Abrir | 40,5 s | 50,84 a 51,67 s |
| Maior atraso da janela | 62,8 ms | 45,0 a 62,7 ms |
| Peças simplificadas / filhos sobrando | 0 / 0 | 0 / 0 |
- As 6 aberturas foram no mesmo dia, em dois `main` seguidos (o módulo nativo não mudou). Pela régua A28 (5 aberturas, vale a pior) a meta **passa**, com folga de **42 MB** (0,7%).
- Ensaio em tela virtual do mesmo dia (`T29e`): uma das 3 aberturas deu 6.028 MB. Não é oficial, mas mostra que a folga é da ordem da variação entre rodadas (até 100 MB entre dias, T24).
- A memória está no processo auxiliar de abertura (caminho da S03), igual para A e para B.

### 3.4 Ponte, build e pacote
| Item | Número | Fonte |
|---|---|---|
| nanobind com GCC (conda-forge) e MSVC | compila e passa R1 nos dois | T03; CI |
| Módulo `obimcore`, build limpo / incremental | Linux 21,7 s / 5,6 s; Windows 87,5 s / 16,9 s | `F0-S04.md` |
| Cadeia de testes do Windows no CI (meta 10 min, ADR-005 §10 item 7) | 34 min 05 s → mediana 17 min 08 s (pior 17 min 13 s) em 3 rodadas; **não atingida** | `T23` |
| Pacotes | AppImage 390 MB; instalador 310,6 MB (meta ≤ 600 MB) | `F0-S04.md` |
| Custo da ponte por chamada (ADR-005 §7.1 prova 5) | **não medido** como prova separada | — |
| pythonocc | fora do ambiente (`environment.yml`) e fora dos protótipos | leitura do repositório |

## 4. Análise
- **M1, o único critério que manda para o C++ puro, passou** nos dois sistemas e dentro dos dois pacotes. Não houve queda intermitente em R1-f ou R1-g.
- **As três reprovações de 17/10 não eram do Python.** A memória do pesado é do processo auxiliar de abertura; a troca de parede em arquivo real era o reenvio da cena inteira no motor de desenho C++, comum a A e B (lote 57 §5). As duas foram corrigidas no código comum (T29 e T30). O C++ puro não teria evitado nenhuma: o fluxo B usa o mesmo motor e o mesmo processo de abertura.
- **M6 não pesa:** a menor folga sobre uma meta absoluta é 3,04 no Linux e 2,63 no Windows, acima de 2. O fluxo A é 16 vezes mais lento que o B no lote de 1.000 paredes (2,15 s contra cerca de 0,13 s), mas fica 9 vezes dentro dos 20 s.
- **Custo de fazer:** a camada de edição em Python tem 1.013 linhas contra 1.278 do B, que é um B mínimo (desfazer simplificado, sem a camada `api`); a diferença real deve ser maior que a medida. O C++ puro custa de 20% a 40% a mais de calendário (`v2/03`, portão).
- **Build:** compilar o módulo leva 17 s no Windows; a cadeia de 17 min é dominada por criar o ambiente e rodar testes, que o C++ puro também teria (hipótese: os testes do B não foram medidos à parte no CI).
- **Rust:** não. O gatilho de `v2/03` (oplog da S05 mais de 10 vezes fora da meta) é da S05.

## 5. Decisão
| Pergunta | Decisão |
|---|---|
| Stack | **Híbrido** (opção 1): Python para interface, comandos e regras; `obimcore` em C++ para malha, cena, desenho e seleção. C++ puro rejeitado como não necessário (PO, 2026-10-21) |
| Ponte | nanobind; o C++ recebe o objeto Python do arquivo e usa `file_pointer()`; regras de posse e de vida do lote 9 §1.4 (1 a 6) |
| pythonocc | fora do ambiente base e fora da ponte de produção (`v2/02 §5`); nada na S04 precisou dele |
| Rust | não na F0; reavaliar só pelo gatilho da S05 |
| Abertura de arquivo | processo auxiliar descartável (caminho da S03), com bloco de 250 peças e reinício planejado (detalhe no ADR-004) |

## 6. Consequências
- O fluxo B fica como **prova congelada** em `prototypes/s04/fluxo_b/`: não vira produto, não recebe recurso novo; serve de referência de M6 se o núcleo mudar.
- `obimcore` sai de `prototypes/` para o produto (cartão RG-15), com o fluxo A como base da camada de edição.
- Toda chamada da ponte segue o lote 9 §1.4: o Python é o dono, o C++ não guarda ponteiro do arquivo nem de entidade entre chamadas, e solta o bloqueio do interpretador no trabalho pesado.
- O núcleo C++ é o mesmo para qualquer casca: um defeito de desempenho do desenho se corrige uma vez.
- A folga de 42 MB na memória é um risco aberto (§7, A3): qualquer mudança no processo de abertura volta a medir o pesado na placa.

## 7. O que ficou aberto
| # | Ponto | Situação | Quem fecha |
|---|---|---|---|
| A1 | Medição oficial completa da S04 (juiz estrito, roteiro inteiro) depois de T29 e T30 | não refeita; os números de §3.2 e §3.3 são de sondas | medição de fechamento da S04, na placa, com ok e horário do PO |
| A2 | Condição A25: com bloco 250, os arquivos simples e detalhado não podem piorar na medida oficial | **não medido** (T29 só mediu o pesado) | mesma sessão do A1 |
| A3 | Folga de 42 MB na memória do pesado | passa pela régua A28; ensaio virtual com 6.028 MB em 1 de 3 | vigiar: toda mudança no carregador ou no processo auxiliar remede o pesado (5 aberturas, vale a pior) |
| A4 | Windows com placa real | não medido | cartão F0-S03-T28 (PO) |
| A5 | Tela e mouse durante operação longa em IFC real (M5 e M5b) | não medidos (`lote.py` não aceita IFC) | cartão de validação do ADR-004 |
| A6 | Cadeia do Windows no CI: 17 min contra 10 | não atingida | PO decidiu (21/10): (a) cartão do instalador, depois (b) dividir os quatro trabalhos de teste; ADR-005 §10 item 7 |
| A7 | Custo da ponte por chamada e tempo de agente (M7) | não medidos | registrar na S10 (calibração); não decide a stack |
| A8 | Fluxo B em IFC real | não medido | não será medido: o núcleo é comum (§4) |

## 8. O que deixa de valer
- A pergunta "híbrido ou C++ puro" do portão da F0 (`v2/03`, linha "S04 falha → C++ puro") fica respondida pelo híbrido, salvo os gatilhos do §9.
- O "número a bater" de 6,8 GB citado no ADR-004 §7: o número vigente do pesado é o de §3.3 (pior 5.958 MB).
- Os números de M2b em IFC real de 17/10 (399 ms e 6.749 ms) deixam de descrever o programa; ficam só como histórico.

## 9. O que nos faria mudar de ideia
- R1-d, R1-e, R1-f ou R1-g reprovando de forma estável em algum sistema ou pacote, ou um pacote novo do IfcOpenShell sem biblioteca compartilhada ou sem `file_pointer()`: plano B do ADR-005 §10 item 1; se também reprovar, C++ puro, levando ao PO.
- A medição de fechamento (A1) reprovando M2 a M5 por causa da camada Python (e não do núcleo comum).
- Folga de M6 abaixo de 2 vezes em alguma meta absoluta, em medição nova.
- Janela surda por mais de 1 s em operação comum que nenhuma das formas do ADR-004 resolva (lote 9 §5.1).
- O oplog da S05 mais de 10 vezes fora da meta: abre a linha opcional de Rust.

## 10. Não verificado
- Windows com placa real; outra máquina Linux; RAM menor que 23 GB.
- O tamanho real da diferença de custo entre A e B (o B medido é mínimo).
- Que a cadeia de testes do C++ puro seria tão longa quanto a do híbrido (hipótese do §4).
