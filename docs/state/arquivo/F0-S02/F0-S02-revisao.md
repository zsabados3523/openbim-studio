<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Revisão da S02 (CI Windows e Linux, app esqueleto, instalador e AppImage)
Data: 2026-10-15 · Cartões: F0-S02-R1 (seções 1 e 2), R2 (seção 3) e R3 (seções 4 a 6 e lista final). Roteiro: `PROPOSTA_REVISAO_F0.md` §3 e §3.2. Status: **R1, R2 e R3 prontas; PO aceitou a S02 em 2026-10-15; lote Opus 30 feito (1 aprovado, 4 reprovados; correções de texto aplicadas, ver o fim)**.

## Resumo de 5 linhas para o PO
1. A S02 entregou o que o plano pede: o programa esqueleto abre um IFC no Windows e no Linux, instalado por você sem terminal (roteiro cumprido em 2026-10-11), com instalador de 309 MB e AppImage de 389 MB (meta 600 MB) e ADR-005 aceito.
2. **Uma meta não foi atingida:** build incremental do Windows, cerca de 16 min contra a meta de 10. Você aceitou em 2026-10-11 com revisão na S04. Pela regra D8 ela fica registrada com a meta original e será reavaliada no portão F0 (S10).
3. O MP4 do vídeo de aceite não foi feito (plano B: capturas e GIF funcionam) e o instalador não é assinado (aviso do Windows).
4. Bloqueia só o primeiro lançamento público, não a F0: o cartão T23 (fixar peça do appimagetool, oferta de código-fonte, tela "Sobre", parecer jurídico humano).
5. **Perguntas:** (a) aceita a S02 com essas ressalvas? Recomendo sim. (b) Você quer o vídeo em MP4? Recomendo não por ora. (c) Você já marcou o job `appimage` como obrigatório na proteção do `main`? É ação sua.

## 1. Aceite contra o plano (`v2/03`, F0-S02)
| # | Critério de `v2/03` | Evidência | Atendido |
|---|---|---|---|
| 1 | CI Windows e Linux obrigatórios (falha bloqueia merge): build, testes, artefato a cada merge | Regra no GitHub (S02-T09, `LOG.md` 2026-10-10); artefatos `openbim-ci-linux` e `openbim-ci-windows`; run 38653866732: `linux`, `windows` e `appimage` verdes. `instalador-windows` ficou verde, mas **não montou o instalador** nesse run (14 s, passos pulados: o PR não mexia no empacotamento) | **Sim, com exceção (D8):** meta original "artefato instalável a cada merge"; desde o PR 91 o instalador do Windows só é montado quando o empacotamento muda (ok do PO, 2026-10-14). O AppImage segue a cada merge |
| 2 | macOS melhor esforço, não bloqueia | Job `macos` no `ci.yml`; hoje **vermelho** nos PRs 93 e 97 (run 38653866732), sem bloquear. Causa não investigada | Sim (não bloqueia); **vermelho a investigar** |
| 3 | Teste prático de gravação de vídeo sem tela | Plano B: capturas e GIF (`arquivo/F0-S02/F0-S02-video.md`); MP4 não feito; PO decidiu em 2026-10-15 que capturas e GIF substituem o MP4 | **Sim, com exceção (D8):** meta original "vídeo" |
| 4 | App esqueleto: janela com menu, abre IFC por menu ou arrastar-e-soltar, mostra contagem, viewport da S03 | `app/openbim_app/main_window.py`, `ifc_summary.py`, `tests/test_main_window.py`, `test_ifc_summary.py`; roteiro do PO nos dois sistemas; viewport da S03 no `main` | Sim |
| 5 | Pacotes: instalador Windows e AppImage | `packaging/windows/` (NSIS) e `packaging/linux/`; 309 MB e 389 MB no CI; DMG não feito (opcional no plano) | Sim |
| 6 | Metas: build limpo ≤ 60 min, incremental ≤ 10 min, instalador ≤ 600 MB | Ver seção 2 | **Parcial** (incremental do Windows) |
| 7 | Aceite do PO: instala no Windows e no Linux sem terminal e abre um IFC | PO executou `docs/acceptance/F0-S02.md` nos dois sistemas em 2026-10-11 (`LOG.md`) | Sim |
| 8 | Decisão produzida: ADR-005 | `docs/adr/ADR-005-dependencias-e-build.md`, "aceito" em 2026-10-11 | Sim |

## 2. Metas com a meta original ao lado (D8)
| Meta original | Linux | Windows | Situação | Quem aprovou |
|---|---|---|---|---|
| Build limpo ≤ 60 min | testes 66 a 81 s no início da S02; AppImage 170 a 182 s | 939 a 1207 s (≈ 16 a 20 min) no início da S02 | Atingida | — |
| Build incremental ≤ 10 min | `linux` 81 s com cache no fim da S02; **17 min 27 s** no run 38653866732 | 995 s com cache, 939 s sem (≈ 16 min) no fim da S02; **28 min 29 s** no run 38653866732 | **Não atingida no Windows e, hoje, nem no Linux** | PO, 2026-10-11, opção 1: aceitar e rever na S04. Motivo: o tempo é criar o ambiente conda e o do instalador, não compilar |
| Instalador ≤ 600 MB | 389 MB | 309 MB | Atingida | — |
| Instalação ≤ 5 min / abertura ≤ 10 s (ADR-005, teste 7) | n/d | verificado pelo CI (116 s com duas instalações) | Atingida no executor do CI | — |

Run 38653866732 (PR 93, 2026-10-14, lido no GitHub): `windows` 28 min 29 s (ambiente ~5 min, testes ~6 min, passos novos da S04 ~15 min) e `linux` 17 min 27 s (passos da S04 ~10 min). O aumento vem dos passos da S04, não da S02. Falta definir o que "build incremental" significa (pergunta ao PO, cartão `F0-S02-T25`).

Mudança de 2026-10-14 (ok do PO, PR 91 e 95): o instalador roda em job próprio e só quando o empacotamento muda. Isso tira o instalador do CI de um PR comum, mas o job `windows` ficou mais longo por causa da S04 e **a meta original não foi resolvida**; a reavaliação com a meta de 10 minutos continua no portão F0 (S10). Registrado também em `arquivo/F0-S02/F0-S02-metricas.md`.

Pré-requisito de release (separado da fatia): cartão **T23** (6 itens, não iniciado). Detalhe na seção 3.

## 3. Pendências abertas (cartão R2)
| # | Pendência | Estado conferido | Destino | Dono |
|---|---|---|---|---|
| 1 | Peça "runtime" do appimagetool sem versão e sha256 fixos | Aberto (T23 item 1; `arquivo/F0-S02/F0-S02-appimage.md`) | Fica na T23; bloqueia só release | Líder (T23) |
| 2 | T23 como pré-requisito de release no plano | PO aprovou em 2026-10-15; consta em `v2/03` (linha 31, cartão `F0-PLANO-T01`) | Feito | — |
| 3 | T21 (instalador não apaga arquivos do usuário) | **No `main`**: `packaging/windows/test_installer.sh` linhas 44 e 46 | Quadro corrigido | — |
| 4 | T22 (parênteses no inventário) | **No `main`**: `tests/test_license_inventory.py:112` | Quadro corrigido | — |
| 5 | T24 (seletor nativo no AppImage) | **No `main`**: `packaging/linux/AppRun` linhas 11 a 14; passo 15 do roteiro | Quadro corrigido | — |
| 6 | Roteiro de aceite atualizado | `docs/acceptance/F0-S02.md` tem o passo 15 (T24); o teste de arquivos do usuário (T21) é automático, não é passo do PO | Aceito | — |
| 7 | Revisão do tempo do Windows na S04 | Cartão `F0-S02-T25` criado a pedido do PO em 2026-10-15 (conversa própria) | Antes de medir, o PO define o que conta como "build incremental"; reavaliar na S10 com a meta original (D8) | Líder (T25) |
| 8 | Trava do ambiente do instalador pelo `.lock` (A3) e mesmo critério no AppImage (A4) | Abertas em `PO.md` | Seguem abertas | PO |
| 9 | Vídeo MP4 | PO respondeu em 2026-10-15: capturas e GIF substituem | Fechado | — |
| 10 | Job `appimage` obrigatório na proteção do `main` | PO respondeu em 2026-10-15: já é obrigatório | Fechado | — |
| 11 | macOS vermelho | Job falha nos PRs 93 e 97, não bloqueia | Investigar até o portão F0 (S10), data limite 2026-10-31 se o PO quiser cartão; sem cartão ainda | Líder |

Licenças dos pacotes × tabela da S01: o inventário (`scripts/license_inventory.py`) compara **cada pacote** com a lista de licenças permitidas do ADR-009 §4. Nos jobs de teste (`linux`, `windows`, `macos`) ele só informa (`--informativo`); **quem reprova é a montagem dos pacotes** (`build_appimage.sh:60` e `build_installer.sh:64`). No Windows essa checagem só roda quando o empacotamento ou as dependências mudam (`ci.yml` linha 387); exceções por nome: `ucrt`, `vc14_runtime`, `vcomp14` (e as do código: `OCCT-exception-1.0`, `Qt-GPL-exception-1.0`). Não existe comparação pacote a pacote com as 23 linhas da tabela mestre; a tabela cobre o que escolhemos, o inventário cobre o que vai no pacote. **Limite conhecido:** um pacote com licença permitida, mas ausente da tabela da S01, passa sem aviso (pergunta ao PO: aceita esse limite? Recomendo sim). A lista de pacotes de um run não foi baixada nesta revisão (baixar arquivo pede ok). Linha do Qt Shader Tools: adicionada na S01-R2; as travas do ambiente não trazem `qt6-shadertools`.

## 4. Coerência dos documentos
| # | Onde | Divergência | Ação |
|---|---|---|---|
| 1 | `BOARD.md`, T21, T22, T24 | "Feita no ramo, aguarda CI", mas estão no `main` | Corrigido |
| 2 | `arquivo/F0-S02/F0-S02-video.md` | Tabela "a confirmar no 1º run" velha | Corrigido (preenchida com o run 38653866732 no lote 30) |
| 3 | `reports/F0-S02.md` item 2 | Dizia "quatro jobs"; agora há `instalador-windows`; macOS vermelho e tempos velhos (lote 30) | Corrigido |
| 4 | `arquivo/F0-S02/F0-S02-metricas.md` | Não registrava a mudança de 2026-10-14 | Nota acrescentada |
| 5 | `docs/PAINEL_DO_PROJETO.md` | S02 "Feita": correto | Nenhuma |
| 6 | `CLAUDE.md` | Cita planos antigos pela raiz | Não editado (A8) |

## 5. Testes
Run `38653866732` (PR 93 com o `main`, 2026-10-14): `linux`, `windows`, `appimage` e `instalador-windows` verdes; `macos` falhou (não bloqueia). Suíte principal: Linux 163 passam, 169 pulam, 0 falham; Windows 161 passam, 171 pulam, 0 falham. Há outros blocos de teste em passos separados que **não** entram nessa contagem (Linux: 2, 21, 128 e 61 testes; Windows: 2, 21, 127 + 1 pulado e 61).

## 6. Qualidade e plano
- Arquivos de empacotamento e testes de CI da S02 não foram reescritos; nada foi simplificado além das 4 correções da seção 4.
- **Velocidade (P2):** a S02 é fatia de integração (empacotamento, CI) e levou de 2026-10-10 a 2026-10-11 de trabalho, mas o CI do Windows consome 15 a 28 min por execução (28 min no run 38653866732, com os passos da S04). Não serve para prever a S04; calendário não recalculado.
- **O que muda no plano:** nada em `v2/` sem cartão aprovado; dois pedidos ao PO: T23 no plano (item 2) e a resposta às perguntas do resumo.

## Lista numerada para o lote Opus (preencher: aprovado ou reprovado)
1. R1, seção 1: os 8 critérios estão certos, com evidência suficiente? → REPROVADO (texto corrigido: critérios 1 e 3 viraram "Sim, com exceção (D8)")
2. R1, seção 2: a tabela de metas registra corretamente a meta original e a exceção do incremental do Windows (D8)? → REPROVADO (texto corrigido: run 38653866732 acrescentado; Linux também não atinge)
3. R2, seção 3: o destino de cada pendência é adequado (T23, T21/T22/T24 no `main`, macOS)? → APROVADO (item 7 e macOS ajustados)
4. R2: a afirmação "o inventário cobre o que vai no pacote; a tabela cobre o que escolhemos" é correta e suficiente? → REPROVADO (parágrafo de licenças reescrito; limite conhecido virou pergunta ao PO)
5. R3: as 4 correções de coerência e a contagem de testes estão corretas? → REPROVADO (macOS e tempos corrigidos; blocos de teste citados)

## Respostas do PO (2026-10-15)
1. Aceita a S02. 2. Quer seguir a questão do build incremental do Windows (cartão `F0-S02-T25`). 3. Capturas e GIF substituem o MP4. 4. O job `appimage` já é obrigatório no `main`. 5. T23 entra no plano (cartão `F0-PLANO-T01`, texto a aprovar).


## Resultado do lote Opus 30 (2026-10-15)
Relatório completo: `lotes/LOTE_OPUS_30/resultado.md`. 1 aprovado e 4 reprovados, todos por texto; nenhum erro de código nem de decisão. As recomendações 1 a 10 foram aplicadas nesta revisão e em `F0-S02.md`, `F0-S02-video.md` e `F0-S02-metricas.md`. A 11 (tempos antigos no ADR-005 §3.2) vai ao PO como nota; o ADR não foi editado. A 4 (definir "build incremental") é pergunta ao PO, junto do cartão `F0-S02-T25`. Sem novo lote Opus.
