<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# ADR-001: Stack híbrido Python + C++ e a ponte entre os dois

Status: aceito

## Contexto
O programa precisa de interface e comandos fáceis de escrever e de mudar (Python, PySide6, `ifcopenshell.api`) e de malha 3D, cena e desenho rápidos (C++). A pergunta era se vale manter as duas linguagens ou escrever tudo em C++.

Para decidir, o mesmo fluxo foi construído de duas formas:
- **A (híbrido):** PySide6 e `ifcopenshell.api` editam o modelo; o módulo C++ `obimcore` (ligado por nanobind) recebe o mesmo objeto `ifcopenshell.file`, sem cópia, e faz malha e desenho. Código em `prototypes/s04/fluxo_a/`.
- **B (C++ puro):** o mesmo fluxo com IfcOpenShell em C++ e Qt Widgets. Código em `prototypes/s04/fluxo_b/`.

As duas formas compartilham o núcleo C++ (malha, cena, viewport com thread de desenho própria, seleção). Por isso uma falha do núcleo vale para as duas.

Regra de decisão adotada: o híbrido é aprovado se atinge as metas absolutas, mesmo sendo mais lento que o B. Só uma falha estável em compartilhar o modelo sem cópia mandaria para o C++ puro.

## Opções
1. **Híbrido:** Python para interface, comandos e regras; C++ para malha, cena e desenho.
2. **C++ puro no núcleo**, Python só para complementos e regras.
3. **Híbrido com os comandos de edição em processo separado.** Só valeria se a tela travasse nas opções 1 e 2; não travou.

## Números medidos
Linux de referência: Intel Core i5-12600KF, 23 GB, NVIDIA RTX 3070, tela real. Windows: só o CI do GitHub, com desenho por software (WARP), máquina compartilhada; serve de verificação, não de medida oficial. Base sintética de 3.000 paredes.

| Meta | Alvo | Linux (mediana / p95) | Windows (mediana / p95) |
|---|---|---|---|
| Mesmo modelo sem cópia (casos R1-a a R1-j de `tests/test_s04_ponte.py`) | todos passam | passam, também dentro do AppImage | passam, também dentro do instalador |
| Criar 1 parede e atualizar a tela | p95 < 200 ms | 33,1 / 49,7 ms | 28,5 / 59,8 ms |
| Editar propriedade e refletir no painel | p95 < 50 ms | 0,7 / 2,4 ms | 2,2 / 3,5 ms |
| Lote de 1.000 paredes | < 20 s | 2,16 s | 5,83 s |
| Tela não congela durante o lote | maior intervalo entre quadros < 200 ms | 17,3 ms | 32,1 ms |
| Troca de geometria de uma parede em IFC real de 25 MB e em IFC detalhado | p95 < 200 ms | 48,9 e 49,6 ms (antes da correção: 399 e 6.749 ms) | não medido |
| Abrir o arquivo pesado (cerca de 1 milhão de triângulos) | pico somado de memória < 6.000 MB e abrir em até 60 s | 5.858 MB e 52 s (pior de 6 aberturas: 5.958 MB) | não medido |

Outros números: o módulo `obimcore` compila em 21,7 s (limpo) e 5,6 s (incremental) no Linux, e 87,5 s e 16,9 s no Windows. Pacotes: AppImage de 390 MB e instalador de 311 MB (limite de 600 MB). O fluxo A é cerca de 16 vezes mais lento que o B no lote de 1.000 paredes (2,15 s contra cerca de 0,13 s), mas fica 9 vezes dentro do limite.

## Decisão
- **Stack:** híbrido (opção 1). C++ puro fica rejeitado: as metas que falharam numa primeira medição (memória do arquivo pesado, troca de parede em arquivo real) estavam no núcleo C++ e no processo de abertura, comuns às duas formas, e foram corrigidas lá. Escrever tudo em C++ não teria evitado nenhuma, e custaria de 20% a 40% a mais de calendário.
- **Ponte:** nanobind. O C++ recebe o objeto Python do arquivo e usa `file_pointer()`. O Python é o dono do modelo; o C++ não guarda ponteiro do arquivo nem de entidade entre chamadas e solta o bloqueio do interpretador no trabalho pesado.
- **pythonocc:** fora do ambiente base e fora da ponte de produção.
- **Rust:** não por enquanto. Reavaliar só se o diário de transações (ADR-002) ficar mais de 10 vezes fora da meta.
- **Abertura de arquivo:** processo auxiliar descartável, com bloco de 250 peças e um reinício planejado (detalhes no ADR-004).

## Consequências
- O fluxo B fica congelado como referência de comparação: não vira produto nem recebe recurso novo.
- O `obimcore` é o módulo nativo do produto; hoje mora em `prototypes/s04/obimcore/` e será movido para `native/obimcore/`. A camada de edição parte do fluxo A.
- O núcleo C++ é o mesmo para qualquer casca de interface: um defeito de desempenho do desenho se corrige uma vez.
- A folga de memória do arquivo pesado é pequena (42 MB, 0,7%): qualquer mudança no carregador ou no processo auxiliar exige medir o arquivo pesado de novo.

## O que nos faria mudar de ideia
- Os casos R1-d, R1-e, R1-f ou R1-g falharem de forma estável em algum sistema, ou um pacote novo do IfcOpenShell sem biblioteca compartilhada ou sem `file_pointer()`: tenta-se o plano B do ADR-005 (compilar o IfcOpenShell); se também falhar, C++ puro.
- Uma medição nova reprovar as metas de edição por causa da camada Python e não do núcleo.
- A janela ficar surda por mais de 1 s em operação comum, sem solução pelas formas do ADR-004.

## O que ficou em aberto
- Windows com placa de vídeo real: não medido.
- Custo da ponte por chamada: não medido como prova separada.
- Tempo de CI do Windows: cerca de 12 minutos, contra a meta de 10.
- Custo real da diferença entre A e B: o B medido é mínimo (desfazer simplificado, sem a camada `api`), então a diferença verdadeira deve ser maior que a medida.
- Fluxo B em IFC real: não será medido, o núcleo é comum.
