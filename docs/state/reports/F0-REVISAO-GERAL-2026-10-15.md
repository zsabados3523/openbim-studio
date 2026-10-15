<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Revisão geral da F0: organização, plano, código, testes e documentos

Data: 2026-10-15 · Pedido do PO (Rafael): revisão de reorganização completa, não só das fatias, incluindo pastas e arquivos. · Base: `main` em `d45d8c1` e o ramo do PR 97 (estado mais novo de `docs/state`). · Método: levantamento do repositório e cinco revisões por tema (arquitetura, testes e CI, segurança, erros, casos-limite), com os achados principais conferidos à mão no código. · Status: **PROPOSTA. Nada foi corrigido.** Cada achado vira um cartão; o PO escolhe quais executar.

Regras respeitadas: `v2/` e `CLAUDE.md` não foram alterados (as mudanças neles aparecem como cartões para aprovação do PO). As revisões de fatia (S01, S02, S03, no PR 97) não são repetidas aqui: este relatório olha o que cruza as fatias.

## Resumo para o PO (5 linhas)
1. **A base está sólida em segurança e empacotamento**, mas o programa de verdade (`app/`) ainda não mostra o 3D: as provas vivem em `prototypes/` e há **duas visualizações 3D** (uma em Python da S03, outra em C++ da S04) sem decisão escrita de qual é o caminho do produto.
2. **Três pontos do plano foram trocados sem registro formal:** a geometria roda em processo separado (o plano diz "processo único"), o caminho C++ processa as peças uma por vez (o plano pede várias ao mesmo tempo) e a S04 não tem nenhum número oficial medido. A regra do projeto é "nunca contornar em silêncio".
3. **Os testes passam, mas alguns pulam sem avisar:** cerca de 10 testes da S03 que precisam de tela nunca rodam no CI, e mais de 40 podem virar "pulados" se alguém renomear um arquivo.
4. **Os documentos de controle cresceram mais que o produto:** 1,27 MB de documentos contra cerca de 0,5 MB de código; 31 pedidos ao Opus espalhados em duas pastas; 104 cartões numa pasta só; 92 ramos no GitHub (57 já mesclados).
5. **Recomendação:** retomar a S04 (a pausa D1 já cumpriu a condição), arrumar os testes que pulam em silêncio e reorganizar `docs/state` numa só passada, nessa ordem.

## Como ler
Gravidade: **CRÍTICO** (pode perder trabalho do usuário ou derrubar o portão) · **ALTO** (precisa resolver antes da F1) · **MÉDIO** (resolver nesta fase) · **BAIXO** (resolver quando mexer no arquivo) · **BOM** (o que está certo e deve ser mantido).
Cada cartão traz: título, por quê, esforço (P até 1 dia; M até 1 semana; G mais que 1 semana), dono (Sonnet escreve código; Opus revisa; PO decide).
Os cartões usam o prefixo `F0-RG-` (revisão geral). Nenhum cartão foi criado em `docs/state/cards/` ainda: isso acontece só depois da escolha do PO.

---

## Parte A. Divergências entre o que existe e o plano (`v2/`)

Lista completa. "Já registrada" = o PO já aceitou como exceção; fica aqui só para a reavaliação do portão (regra D8).

| # | O que o plano diz | O que existe | Evidência | Situação |
|---|---|---|---|---|
| A1 | S02: o app esqueleto "mostra contagem de elementos **e a viewport do S03**" (`v2/03:26`) | O centro da janela ainda é o texto "A viewport 3D entra na fatia S03"; o teste confirma esse texto | `app/openbim_app/main_window.py:29-31`, `tests/test_main_window.py:37` | **Nova** → RG-05 |
| A2 | Arquitetura: "**processo único**" e "a mesma instância de `ifcopenshell.file` compartilhada sem cópia" (`v2/02 §5`, linhas 58 e 92) | A S03 abre o modelo num processo filho e, com `manter_arquivo`, abre de novo no principal: duas cópias. Decisão veio do lote Opus 6 (D3), sem ADR e sem mudar `v2/` | `prototypes/viewport_qrhi/carregador.py:385-387`, `processo_malhas.py:2` | **Nova** → RG-01 |
| A3 | S03: tesselação "via iterador de geometria **multithread**" (`v2/03:33`) | O caminho C++ (o do produto) trava um peça-por-vez no processo todo, com 1 thread. Motivo válido (a biblioteca caiu em ~10% das rodadas), mas não foi registrado como meta não atingida | `prototypes/s04/obimcore/nucleo/malha.cpp:28-40` | **Nova** → RG-01 |
| A4 | S03: QRhi (parte semipública do Qt) "isolado atrás de interface própria" | No Python, isolado (bom). No C++, `motor.h` inclui `<rhi/qrhi.h>` no mesmo arquivo da interface pública `obim::Viewport`; tudo que usa a viewport compila contra a parte semipública | `prototypes/s04/obimcore/nucleo/motor.h:30-31`, `ponte_viewport.cpp:11` | **Nova** → RG-08 |
| A5 | S04: saída "ADR-001 (stack) com números"; metas M1 a M6 | S04 pausada (D1); nenhuma meta medida oficialmente; ADR-001 e ADR-004 não existem | `docs/adr/` só tem 005 e 009; `BOARD.md` linha da S04 | **Nova** → RG-02 |
| A6 | `v2/02 §5`: o módulo nativo do produto é o `obimcore` | `obimcore` mora em `prototypes/`, cujo LEIA-ME diz "descartável"; mesmo assim o CI bloqueia o merge se ele não compilar | `prototypes/README.md:3`, `.github/workflows/ci.yml:123-153` | **Nova** → RG-15 |
| A7 | `v2/02 §6.5`: gravar é atômico (arquivo temporário, depois renomear) | O fluxo A grava direto por cima do arquivo final | `prototypes/s04/fluxo_a/fluxo_a.py:358` | Esperado (S05 não começou), mas tem de entrar no cartão da S05 → RG-06 |
| A8 | S08: "≥ 20 arquivos públicos com manifesto"; a F0 "começa só com IFCs públicos" e alimenta S03 e S06 | `corpus/` só tem o LEIA-ME; o benchmark da S03 usou modelo sintético (aceito pelo PO, lote 4) | `corpus/README.md`; `BOARD.md` linha S08 | Parcialmente registrada → RG-22 |
| A9 | ADR-008 (estratégia de testes) sai da S08 | Não existe; a estratégia real são ~15 chaves `OBIM_S04_*_OBRIGATORIO` espalhadas | `tests/*.py`; `ci.yml:144` | **Nova** → RG-03, RG-12 |
| A10 | S02: build incremental ≤ 10 min | Windows ~28 min e Linux ~17 min no run 38653866732 (lote Opus 30) | `reports/F0-S02-metricas.md` | Já registrada; T25 em andamento (PR 98) |
| A11 | S03: memória < 6 GB; Windows com placa real; seleção < 100 ms | 6,8 GB (E1); Windows só em máquina virtual (T28); teste afrouxado de 16 para 100 ms (E3) | `reports/F0-S03-revisao.md` | Já registradas (T20, T28) |
| A12 | S01: espelho Codeberg | Adiado pelo PO | `PO.md` P6 | Já registrada |
| A13 | `v2/04 §3.1`: lote Opus = 2 a 4 itens do mesmo módulo; "uma sessão opus por fase" para planejar | 31 lotes em 5 dias, vários com 1 item | `reports/LOTE_OPUS_1..31.md` | **Nova** → RG-20 |
| A14 | `v2/04 §8` e `reports/README.md`: relatório **semanal** (`semana-AAAA-MM-DD.md`) com cota | Nenhum relatório semanal existe; `QUOTA.md` tem números `?` nos dias 13 e 14/10 | `docs/state/reports/`, `QUOTA.md` | **Nova**: ameaça a calibração da S10 → RG-20 |
| A15 | `CLAUDE.md`: "revisão reprovada 2 vezes → reescrever o cartão" | T12 foi reprovada 3 vezes sem reescrita (registrado como "falhas novas a cada leitura") | `LOG.md`, 2026-10-14, S04-T12 lote 27 | **Nova** → RG-21 |
| A16 | `CLAUDE.md`: diff máximo de 400 linhas | Exceções repetidas (434, 501, 520, 529, 650 linhas) | `LOG.md` 2026-10-14 | **Nova**: a regra está virando exceção → RG-21 |
| A17 | `v2/04 §4`: estado em disco "mínimo"; `CLAUDE.md` ≤ 100 linhas | `CLAUDE.md` tem 70 linhas (ok); `docs/state` tem ~200 arquivos e ~1 MB | ver Parte C | **Nova** → RG-16 a RG-19 |
| A18 | `CLAUDE.md` cita os planos antigos na raiz | Foram para `docs/arquivo/` (D2) | `CLAUDE.md`, `PO.md` A8 | Já registrada (A8 aberta) → RG-24 |
| A19 | S04: "registrar linhas de código e tempo de agente para o mesmo fluxo" | Ainda não registrado (cartão T18 é esqueleto) | `cards/F0-S04-T18.md` | Esperado; entra no RG-02 |

---

## Parte B. Achados de código, testes, segurança e erros (por gravidade)

### CRÍTICO

**B1. A geometria do caminho do produto roda dentro do programa, sem vigia e sem limite de tempo.**
`obimcore.malhas` chama a biblioteca de geometria (OCCT) no mesmo processo da janela, com o bloqueio do modelo seguro (`ponte_malha.cpp:30-31`, `malha.cpp:30,40`, `fluxo_a.py:156-161,207`). A S03 tinha resolvido isso com um processo filho vigiado e limite de 20 s por peça. Uma parede ruim no IFC de um cliente pode travar ou derrubar o programa com o trabalho não salvo. Somado ao B5 (gravação por cima), um travamento na hora errada perde a sessão e o arquivo.
Cartão: RG-01 (decisão de arquitetura) e RG-06 (gravação).

### ALTO

**B2. Duas visualizações 3D com lógica duplicada, e o caminho do produto depende da descartável.**
Câmera, seleção e formato dos vértices (28 bytes) existem em Python (`prototypes/viewport_qrhi/camera.py`, `selecao.py`, `cubo_rhi.py:42`) e em C++ (`nucleo/camera.*`, `selecao.*`, `motor.h`). O fluxo A importa o formato da S03 (`fluxo_a.py:206`); o C++ copia o mesmo formato por comentário (`cena.h:18`, `malha.cpp:26`). Se um lado mudar, o outro quebra sem aviso. Cartão: RG-04.

**B3. Testes da S03 que precisam de tela nunca rodam no CI.**
Seleção por clique, imagem da câmera e malhas V1 a V4 pulam quando não há tela (`tests/test_viewport_selecao.py:140,282`, `test_viewport_camera.py:123`, `test_viewport_malha.py:64`, `test_viewport_adaptador.py:83`, `test_viewport_responsivo.py:129`). Só `test_viewport_qrhi.py` ganha tela virtual, num passo que não bloqueia (`ci.yml:85-101`). Conferido. Cartão: RG-03.

**B4. Testes que pulam por "o código existe?" e pulos que ignoram a chave de obrigatório.**
Cerca de 45 testes de oráculo da S03 ligam só se `importlib.util.find_spec(...)` acha o módulo ou se um parâmetro existe (`test_viewport_carregador.py:30-39`, `test_viewport_processo.py:40-45`, `test_s04_abertura.py:74`, `test_localidade.py:19-20`): renomear um arquivo transforma todos em "pulado" e o CI fica verde. Três pulos diretos ignoram a chave de obrigatório (`test_s04_ponte.py:90`, `test_s04_viewport_b.py:40`, `test_s04_fluxo_b_paredes.py:272,633`); os dois últimos dependem da localidade pt_BR, criada num passo que não bloqueia (`ci.yml:67-71`). O passo geral roda `pytest -q` sem `-rs`, então os pulos nem aparecem (`ci.yml:77`). Cartão: RG-03.

**B5. Gravar escreve direto por cima do arquivo real.** `fluxo_a.py:358`. Sem arquivo temporário nem troca atômica, uma queda ou disco cheio deixa `Casa.ifc` cortado. É protótipo, mas o padrão vai ser copiado. Cartão: RG-06.

**B6. Modelos georreferenciados perdem precisão no caminho C++.** O lote do fluxo A usa deslocamento zero e grava as posições em float32 (`fluxo_a.py:211,222`). Coordenadas UTM do Brasil (Y perto de 7,4 milhões de metros) viram degraus de cerca de 0,5 m: tremor, seleção errada. A S03 já calcula um deslocamento (`processo_malhas.py:174-178`). Conferido. Cartão: RG-07.

**B7. A regra do teste de tempo aprovada pelo PO ("aquecer, 7 rodadas, mediana contra 100 ms") não existe no código.** Cada teste usa uma régua diferente: pior de 5 rodadas (`test_s04_viewport.py:32,81`), mediana de 50 consultas numa rodada (`test_s04_selecao.py:371`), mediana com teto de 3× e um limite **mais apertado no CI que na máquina do PO** (`tests/s04_fluxo_aux.py:96-102`). Há também dependência da ordem dos testes, documentada em `test_s04_fluxo_a.py:326`. Cartão: RG-09.

**B8. O ambiente que vai dentro do instalador e do AppImage não é travado.** O ambiente de desenvolvimento usa trava com conferência de cada pacote; o que é entregue ao usuário é resolvido de novo a cada build (`packaging/runtime-environment.yml:8-15`, `ci.yml:421,536-543`): só 5 pacotes fixos, ~300 soltos. Já houve uma mudança sem aviso (x264, `build_installer.sh:41-42`). Isso é a pergunta A3 do `PO.md`, ainda aberta. Cartão: RG-10.

**B9. O atalho do Windows falha calado.** O atalho usa `pythonw.exe` (sem janela de texto); se algo falhar ao abrir, nada aparece e não há registro. O teste do instalador usa `python.exe`, então não pega (`openbim-studio.nsi:92,94`, `OpenBIM-Studio.pyw:20-22`, `test_installer.sh:34`). Cartão: RG-11.

**B10. O programa não grava nenhum registro de erros.** Não há `logging`, `sys.excepthook` nem `faulthandler` no app (`app/openbim_app/main.py:9-19`). Se der erro, o PO não tem arquivo para mandar. Cartão: RG-11.

**B11. Reinstalar com o programa aberto pode deixar uma instalação quebrada.** O instalador não confere se o app está rodando; apaga o que consegue, falha nos arquivos em uso e desfaz pela metade (`openbim-studio.nsi:69-88`). Cartão: RG-13.

**B12. Caminhos com acento e espaço não têm teste.** Nenhum teste abre ou grava `C:\Users\João\Documentos\Residência.ifc`; o teste do instalador usa pasta sem espaço, mas a pasta padrão tem espaço (`test_installer.sh:6`, `openbim-studio.nsi:11`). Para um programa brasileiro, é o caso comum. Cartão: RG-13.

### MÉDIO

- **B13.** O bloqueio do modelo é só combinação: o C++ lê o modelo com o interpretador solto e sem trava própria (`malha.cpp:74`, `ponte_malha.cpp:27-31`); `executar_roteiro` já lê sem a trava (`fluxo_a.py:388`). Na F1, um painel ou um salvamento automático sem a trava vira travamento aleatório. → RG-01.
- **B14.** `motor.h` tem 425 linhas e faz tudo (threads, três placas de vídeo, envio à GPU, captura, mensagens do Windows, ganchos de teste), com estado público alterado de fora (`motor.h:60-334`). → RG-08.
- **B15.** Lógica de produto escondida nos testes: validação do IFC pelas regras EXPRESS, assinatura de modelo e geração por API estão em `tests/s04_*_aux.py` (~950 linhas), em parte sem teste próprio; mais de 15 testes mexem em `sys.path` para achar os protótipos. → RG-12.
- **B16.** Sem arquivo de configuração do pytest (sem `pytest.ini`, sem marcadores registrados, sem `xfail_strict`). → RG-12.
- **B17.** CI: jobs `linux` e `windows` são cópias de ~170 linhas e já divergiram (Linux sem limite de tempo no job, REUSE só no Linux); passos informativos que ninguém lê; um passo que bloqueia depende do `xvfb` instalado num passo que não bloqueia (`ci.yml:91,138`); `pipefail` desligado com `shell: bash -el {0}`, então `build.sh | tee` esconde a falha do build e o erro aparece adiante com texto enganoso (`ci.yml:131,133,427`, conferido). → RG-14 (depois do PR 98).
- **B18.** Ferramentas de base sem versão fixa: `miniforge-version: latest` (`ci.yml:45,219,412,474,543`); NSIS fixo por versão mas sem conferência do arquivo. → RG-10.
- **B19.** `.gitignore` só bloqueia `corpus/*`; um IFC do PO copiado por engano para outra pasta iria para o GitHub público, sem volta. Faltam `*.ifc`, `*.ifczip`, `*.obim` com exceção para `docs/acceptance/amostras/casa-simples.ifc`. → RG-10.
- **B20.** Todo erro ao abrir vira "o arquivo não é um IFC válido": arquivo travado por outro programa, OneDrive não baixado, falta de memória (`ifc_summary.py:30-33`). Erros depois de abrir escapam sem aviso (`ifc_summary.py:34`). → RG-11.
- **B21.** A trava do processo filho não guarda o motivo da queda (código de saída perdido em `carregador.py:403-405`; `os._exit(3)` sem mensagem em `processo_malhas.py:266-268`; erro engolido em `carregador.py:453-457`). → RG-11.
- **B22.** O processo de geometria mede a memória, mas não limita (`carregador.py:382-408`); o app lê o IFC na thread da janela (`ifc_summary.py:27`, marcado "TEMPORÁRIO"); soltar arquivo grande trava o app e o Explorador do Windows; com vários arquivos soltos, só o primeiro abre, sem aviso (`main_window.py:102-108`). → RG-05.
- **B23.** O carregador relê o arquivo do disco a cada nova tentativa e na perda da placa; se o arquivo mudou no meio (OneDrive sincronizou), mistura versões (`carregador.py:363,452`, `adaptador.py:50-52`). → RG-04.
- **B24.** Reinstalar ignora pasta escolhida pelo usuário (falta `InstallDirRegKey`, `openbim-studio.nsi:11`); o ambiente é copiado e não realocado, e o teste roda na mesma máquina do build, então um caminho de build gravado dentro dos arquivos passaria (`build_installer.sh:23,93`, não confirmado); caminhos longos (>260 caracteres) não conferidos. → RG-13.
- **B25.** Sem placa de vídeo (máquina virtual, área de trabalho remota) a viewport C++ fica preta e o erro só aparece em `info()`; não há troca automática para desenho por software (`motor.h:151,306-309`). AppImage só testado em modo extraído; falta de `libfuse2` não é pega (`test_appimage.sh:13`). → RG-13.
- **B26.** Histórico de desfazer sem limite de memória (`fluxo_a.py:60`, 100 000 passos). → RG-06.
- **B27.** Configuração espalhada: tempos-limite no construtor, ganchos de teste lidos no código de produto (`processo_malhas.py:110,146,212,348`), prefixos diferentes (`OBIM_` e `OPENBIM_`). → RG-12.
- **B28.** Exceções do C++ achatadas: falta de memória chega ao Python como `ValueError`; erro do OCCT perde o texto (`malha.cpp:88-91`). → RG-08.

### BAIXO
- B29. O nome do arquivo pode virar HTML na tela (`main_window.py:80`, falta `PlainText`); nomes com `%2`/`%3` corrompem a barra de status (`main_window.py:82-86`). → RG-05.
- B30. AppRun não usa o modo isolado do Python (`-E -s`), ao contrário do Windows (`AppRun:7-10,19`). → RG-13.
- B31. A janela de medidas de 4096 quadros cobre só ~68 s e perde dados calada (`motor.h:333`). → RG-08.
- B32. Pequenos erros de texto de erro (`f"..." or "erro desconhecido"` nunca usa o "ou", `carregador.py:259`); `_pronto.set()` fora de `finally` (`carregador.py:260-271`). → RG-04.
- B33. O teste de "soltar arquivo" solta um arquivo que não existe e passa pelo caminho de erro (`test_main_window.py`). → RG-05.
- B34. Scripts de licença (`scripts/prune_packages.py`, `collect_package_licenses.py`) só testados de ponta a ponta, no job que roda quando o empacotamento muda. → RG-12.

### BOM (manter)
- **CI seguro:** ações fixas por código de versão, permissão só de leitura, sem gatilhos perigosos, sem segredos; `appimagetool` conferido por soma (`ci.yml:27,30,39,182,546-547`).
- **Instalador cuidadoso:** instala só para o usuário, não mexe no PATH, recusa pasta com arquivos de outra pessoa, só apaga o que criou, testa que arquivos do usuário sobrevivem (`openbim-studio.nsi:24-64`, `test_installer.sh:42-48`).
- **Portão de licenças:** lista de permitidas que exclui GPL-2.0 somente; exceções amarradas a nome e versão; roda bloqueando nos dois pacotes (`scripts/license_inventory.py`).
- **Threads do C++ bem desenhadas:** ordem de travas documentada e respeitada, cena imutável trocada inteira, a thread de desenho nunca toca no Python (`motor.h`, `cena.cpp`).
- **Vigia do processo filho da S03:** um canal por filho, limites por peça e na abertura, limpeza garantida, peça que falha vira caixa e aparece na lista (`carregador.py:382-428`).
- **Oráculos fortes:** testes por comportamento, o próprio juiz é testado (`test_s04_fluxo_b_paredes.py:84`, `test_s04_viewport.py:86`).
- **Localidade:** um só lugar cria o app e corrige a vírgula decimal; o filho confere de novo (`localidade.py`, `processo_malhas.py:132-136`); o `LC_ALL=C` do `conftest.py` não esconde o teste da T26 (ele roda em subprocesso limpo).

---

## Parte C. Organização de pastas e arquivos (pedido do PO)

Números (ramo do PR 97): `docs/` + `v2/` = 226 arquivos e 1,27 MB; código (app, protótipos, testes, scripts, empacotamento) ≈ 0,5 MB. Só os relatórios dos lotes Opus somam 330 KB; os cartões, 158 KB.

**C1. [ALTO] Pedidos e resultados do Opus em dois lugares e numa lista plana.** Pedidos 1 a 9 e 29 a 31 em `docs/state/`; resultados 1 a 31 (mais o 10b) em `docs/state/reports/`, misturados com relatórios de fatia, de tarefa, do dia e de inventário. `reports/README.md` descreve tipos que não existem (`semana-*`, `portao-F0`) e não descreve os que existem.

**C2. [ALTO] 104 cartões numa pasta só, sem status no cartão.** O status só vive no `BOARD.md`, cujas células guardam história ("REPROVADA no lote 2... APROVADA no lote 3..."). Fatias fechadas (S01, S02, S03) continuam misturadas com as abertas.

**C3. [MÉDIO] Cinco lugares contam o andamento:** `BOARD.md`, `LOG.md`, `PO.md`, `docs/PAINEL_DO_PROJETO.md` e a seção de transparência do README. O PAINEL está parado em 13/10 e diz que a S04 está "na reta final" (está pausada). `PO.md` tem 151 linhas misturando regras em vigor, perguntas abertas e todo o histórico.

**C4. [MÉDIO] LEIA-MEs desatualizados:** `tests/README.md` diz "Vazio nesta fase" (há 31 arquivos de teste); `packaging/README.md` diz que o job `windows` monta o instalador (é o `instalador-windows`); `prototypes/README.md` diz "tudo descartável" (o `obimcore` é o produto, A6).

**C5. [MÉDIO] Testes nomeados pela tarefa, não pelo assunto.** `test_s04_*.py` e chaves como `OBIM_S04_T11C_OBRIGATORIO` deixam de fazer sentido quando a tarefa fecha; na F1 ninguém saberá o que a T11C testava.

**C6. [MÉDIO] 92 ramos no GitHub;** 57 já estão no `main` e podem ser apagados sem perda; os outros 34 parecem ter sido mesclados por "squash" (o GitHub não reconhece) e precisam de conferência um a um. Apagar ramo é "apagar dados": precisa do seu ok. Ligar no GitHub "apagar ramo depois do merge" evita voltar a acumular.

**C7. [BAIXO] Mistura de idiomas nos nomes de arquivo de código:** `ifc_summary.py`, `main_window.py`, `license_inventory.py`, `prune_packages.py`, `collect_package_licenses.py`, `test_env_smoke.py` em inglês; o resto em português (`localidade.py`, `carregador.py`, `gerar_modelo_grande.py`). Falta uma regra.

**C8. [BAIXO] `scripts/` mistura quatro coisas:** ferramentas de licença do CI, ajudantes do empacotamento, geradores de modelo e uma sonda. `docs/acceptance/F0-S09-roteiro-entrevista.md` é roteiro de entrevista (pesquisa), não roteiro de aceite. Relatórios avulsos de um dia (`RELATORIO_DO_DIA_2026-10-14.md`, `INVENTARIO_ESTADO_2026-10-14.md`, `LOG_DETALHES_2026-10-14.md`) já cumpriram o papel.

**C9. [BAIXO] A pasta local do PO tem um `AGENTS.md` que não está no repositório** (mesmo tamanho do `CLAUDE.md`). Se for cópia, pode divergir sem ninguém ver.

### Estrutura proposta
Mudanças só de lugar e nome (nada é apagado; o histórico do Git guarda tudo). Os caminhos citados no `CLAUDE.md` e em `v2/04 §4` mudam juntos, por cartão aprovado pelo PO (RG-24).

```
docs/state/
  BOARD.md          só o que está aberto: uma linha por cartão, status curto, sem história
  PO.md             só "regras em vigor" + "perguntas abertas"
  LOG.md            uma linha por evento (como hoje)
  QUOTA.md  QUEUE_OPUS.md
  cards/
    F0-S04/  F0-S05/ ...      uma pasta por fatia aberta
  lotes/
    LOTE_OPUS_29/pedido.md + resultado.md      pedido e resultado juntos
  reports/          só relatórios de fatia, de portão e semanais (README atualizado)
  arquivo/
    F0-S01/ F0-S02/ F0-S03/   cartões e relatórios das fatias fechadas
    lotes-1-a-28/             pedidos e resultados antigos
    PO-historico.md           o histórico que sai do PO.md
    avulsos/                  relatório do dia, inventário, detalhes do log
docs/PAINEL_DO_PROJETO.md     para o PO; atualizado no fim de cada sessão (regra que já existe)
```

Para o código, depois da decisão do RG-01 e do RG-02 (não antes):
```
src/obim/              pacote Python do produto (app, sessão do modelo, formato da geometria, qualidade)
native/obimcore/       módulo C++ do produto (interface pública sem QRhi; o resto em .cpp)
tests/unit/  tests/oraculo/  tests/f0/   (f0 = provas congeladas, ligadas por uma chave só)
prototypes/f0/         provas congeladas numa etiqueta do Git "f0-portao", com o comando para rodar de novo
```

---

## Parte D. Cartões propostos

Ordem = ordem recomendada. "Depende de" evita conflito com o trabalho em andamento: **PR 98** (T25, mexe no `ci.yml`) e **PR 97** (revisões, mexe em `docs/state`).

| Cartão | Título | Por quê | Gravidade | Esforço | Dono | Depende de |
|---|---|---|---|---|---|---|
| **F0-RG-01** | ADR-004 rascunho: processo único ou processo de geometria; uma ou várias peças ao mesmo tempo; trava do modelo | Resolve A2, A3, B1, B13. Hoje nenhum caminho cumpre "sem cópia" **e** "várias peças ao mesmo tempo" | CRÍTICO | M | Opus escreve (TA); PO decide | — |
| **F0-RG-02** | Retomar a S04 e medir M1 a M6 oficialmente, depois ADR-001 | A condição da pausa D1 (revisões S01 a S03 e respostas D1 a D8) já foi cumprida. Sem ADR-001 as duas visualizações continuam sendo mantidas | ALTO | G | Sonnet mede; Opus revisa; PO decide | RG-01 (em paralelo) |
| **F0-RG-03** | Testes que pulam em silêncio | Rodar os testes de tela da S03 com tela virtual num passo que bloqueia; trocar os pulos por "o código existe?" por importação direta; levar os 3 pulos diretos para a chave de obrigatório; `-rs` e contagem de pulos no resumo; localidade pt_BR bloqueando no Linux | ALTO | P | Sonnet; revisão Sonnet | PR 98 |
| **F0-RG-04** | Um só formato de geometria entre Python e C++ | Formato dos vértices num módulo só, com teste que confere o lado C++; congelar câmera e seleção do Python; tirar o fluxo A da dependência da S03; tornar públicas as funções que o processo filho usa; motivo de queda do filho; foto do arquivo (tamanho, data, soma) passada a cada filho | ALTO | M | Sonnet; Opus revisa (ponte é T3) | RG-01 |
| **F0-RG-05** | Viewport dentro do app esqueleto | Cumpre A1: uma "sessão do modelo" com um único `ifcopenshell.file`; viewport no centro; abrir fora da thread da janela; avisar quando só o primeiro arquivo solto abre; texto simples no rótulo; teste que solta um IFC real | ALTO | M | Sonnet; Opus revisa (threads é T3) | RG-01, RG-02 |
| **F0-RG-06** | Requisitos de gravação para o cartão da S05 | Gravar em temporário e trocar (atômico), cópia `.bak`, mesma identificação no par `.ifc`/`.obim`, limite de memória do desfazer. Vira texto no cartão da S05, não código agora | ALTO | P | Opus (especificação T3) | — |
| **F0-RG-07** | Deslocamento da cena no caminho C++ | Calcular um deslocamento ao abrir e usar em todos os lotes (B6); teste com coordenadas UTM | ALTO | P | Sonnet; Opus revisa | — |
| **F0-RG-08** | Separar `motor.h` e esconder o QRhi | Interface pública sem QRhi (A4); `motor.h` dividido (B14); exceções com tipo e texto certos (B28); aviso de estouro da janela de medidas (B31); checagem no CI de que `rhi/` aparece num arquivo só | ALTO | M | Sonnet; Opus revisa (T3) | RG-02 |
| **F0-RG-09** | Uma régua só para os testes de tempo | Implementa a regra aprovada (aquecer, 7 rodadas, mediana contra o limite, teto rígido); mesma régua nos três lugares; CI nunca mais apertado que a máquina do PO; testes de tempo em processo próprio | ALTO | M | Sonnet; Opus revisa a regra | RG-03 |
| **F0-RG-10** | Travar o que é entregue ao usuário | Trava do ambiente do instalador e do AppImage (responde A3 do `PO.md`); Miniforge e NSIS com versão e soma fixas; `.gitignore` bloqueando `*.ifc`, `*.ifczip`, `*.obim` | ALTO | P | Sonnet; Opus confere a trava | PR 98; **ok do PO** (A3) |
| **F0-RG-11** | Registro de erros para o PO poder mandar | Arquivo de registro na pasta do usuário, captura de erros e quedas, menu "Ajuda > Abrir pasta de registros"; atalho do Windows mostra mensagem se falhar ao abrir; teste com `pythonw`; mensagens de erro certas ao abrir (arquivo travado, OneDrive, memória) | ALTO | P | Sonnet; revisão Sonnet | — |
| **F0-RG-12** | Organizar os testes | `pytest.ini` com marcadores registrados; uma chave `OBIM_CI=1` no lugar das ~15; lógica de produto dos ajudantes para o código (validação, assinatura); testes pelo assunto em vez da tarefa; testes unitários dos scripts de licença; um lugar para a configuração | MÉDIO | M | Sonnet; Opus revisa (oráculos) | RG-03 |
| **F0-RG-13** | Instalador e AppImage em casos reais | Conferir app aberto antes de reinstalar; lembrar a pasta escolhida; teste com acento e espaço no caminho (usuário "João", pasta "Residência"); teste sem o ambiente de build; caminho mais longo; aviso visível e troca para desenho por software sem placa; teste do AppImage sem extrair; modo isolado no AppRun | MÉDIO | M | Sonnet; Opus revisa (instalador já passou por Opus) | PR 98 |
| **F0-RG-14** | CI enxuto | Um job só com variação para Linux e Windows, mantendo os nomes `linux` e `windows` exigidos; `pipefail` ligado; tela virtual e localidade em passos que bloqueiam; tirar as sondas cujo ADR já fechou (testes 2 e 3b do ADR-005); cada passo informativo escreve uma linha no resumo | MÉDIO | M | Sonnet; revisão Sonnet | **PR 98** (T25 mexe no mesmo arquivo) |
| **F0-RG-15** | `obimcore` sai de `prototypes/` | Mover para `native/obimcore/` e ajustar o CI; LEIA-ME de `prototypes/` diz o que é prova congelada | MÉDIO | P | Sonnet | RG-02 |
| **F0-RG-16** | Reorganizar `docs/state` | Estrutura da Parte C: cartões por fatia, pedidos e resultados do Opus juntos, fatias fechadas em `arquivo/`, `reports/` só com relatório de fatia, portão e semana; LEIA-MEs novos | MÉDIO | P | Sonnet (só move arquivo e corrige links); revisão Sonnet | **PR 97**; RG-24 |
| **F0-RG-17** | `BOARD.md` e `PO.md` curtos | `BOARD.md` só com o que está aberto e status de uma palavra; histórico do `PO.md` para `arquivo/PO-historico.md` | MÉDIO | P | Sonnet | RG-16 |
| **F0-RG-18** | PAINEL e LEIA-MEs em dia | `PAINEL_DO_PROJETO.md` atualizado (está em 13/10); `tests/`, `packaging/`, `prototypes/`, `reports/` com texto certo | MÉDIO | P | Haiku escreve; Sonnet confere | RG-16 |
| **F0-RG-19** | Limpar ramos no GitHub | Apagar os 57 ramos já mesclados; conferir os 34 restantes um a um; ligar "apagar ramo depois do merge" | MÉDIO | P | Sonnet prepara a lista; **PO autoriza** (apagar dados) | — |
| **F0-RG-20** | Medição de cota e relatório semanal de volta | Preencher ou marcar de vez os `?` do `QUOTA.md`; um relatório semanal curto (feito, próximo, cota, fila Opus); lotes Opus com 2 a 4 itens como diz `v2/04`. Sem isso a calibração da S10 não tem base | MÉDIO | P | Sonnet; PO informa o uso | — |
| **F0-RG-21** | Regras de limite de diff e de reprovação | Escolher: (a) cumprir de novo as 400 linhas e a reescrita após 2 reprovações, ou (b) mudar a regra com número novo. Hoje elas valem só no papel | MÉDIO | P | Opus propõe; **PO decide** (regra do processo, mexe no `CLAUDE.md`) | — |
| **F0-RG-22** | Corpus público mínimo (S08) | Lista de IFCs públicos com licença e manifesto para baixar (cada download com ok do PO), para S06 e para os testes de abertura com arquivos reais | MÉDIO | P | Haiku pesquisa; Sonnet escreve manifestos; **ok do PO** para baixar | — |
| **F0-RG-23** | Regra de idioma dos nomes no código | Decidir: tudo em português (a maioria hoje; recomendado) ou inglês. Renomear só quando mexer no arquivo | BAIXO | P | **PO decide**; Sonnet aplica | — |
| **F0-RG-24** | Ajustes no `CLAUDE.md` e no `v2/` (aprovação do PO) | (1) caminhos dos planos antigos (A8 aberta); (2) caminhos novos de `docs/state` (RG-16); (3) `v2/02 §5` depois do ADR-004 (processo único ou não); (4) `v2/04 §4` com a estrutura nova | MÉDIO | P | Sonnet escreve o texto; **PO aprova** | RG-01, RG-16 |
| **F0-RG-25** | Revisão completa por Opus antes da S10 | Pedido do PO (`QUEUE_OPUS.md`). Este relatório é a primeira passada; a do Opus confere as correções e o portão com as metas originais (D8) | — | M | Opus | RG-01 a RG-14 |

Esforço total aproximado: cartões P ≈ 11 dias de agente; M ≈ 8 semanas de agente; G (RG-02) é a S04 que já estava no plano. Muito disso pode correr em paralelo depois do RG-01.

### Dependências
- RG-04, RG-05 dependem do RG-01 (sem saber se há processo separado, não dá para unificar o formato nem ligar a viewport ao app).
- RG-05, RG-08, RG-15 dependem do RG-02 (precisa saber qual visualização fica).
- RG-03, RG-10, RG-13, RG-14 mexem no `ci.yml`: esperar o PR 98 (T25) mesclar.
- RG-16 e RG-17 mexem em `docs/state`: esperar o PR 97 mesclar.
- RG-24 junta todas as mudanças de texto no `CLAUDE.md` e no `v2/` numa só aprovação.

---

## Parte E. Veredito

**Saúde geral.** A F0 entregou bem o que é infraestrutura: CI nos dois sistemas, instalador cuidadoso, portão de licenças e oráculos de teste sérios. O risco maior não é um defeito pontual, é a **distância entre o plano e o que foi construído**: três escolhas de arquitetura (processo separado, uma peça por vez, duas visualizações) foram tomadas em lotes de revisão e nunca voltaram ao plano nem a um ADR, enquanto o `app/` continua sem o 3D. Junto vem o crescimento do controle (documentos, lotes, ramos) mais rápido que o produto.

**As 3 ações, se só der para fazer 3:**
1. **RG-01 + RG-02:** decidir a arquitetura com números (ADR-004, medir a S04, ADR-001). Tudo o mais depende disso.
2. **RG-03:** fazer os testes falharem quando não rodam. É barato e protege tudo o que já foi aprovado.
3. **RG-16 + RG-17 + RG-19:** reorganizar `docs/state` e limpar os ramos numa só passada, para o projeto voltar a caber na cabeça de quem chega.

**Confiança.**
- Divergências A1 a A6 e B1, B3, B6, B17: **alta** (conferidas no código).
- B7 (régua dos testes de tempo) e B8 (trava do instalador): **alta** (lidas no código e no `PO.md`).
- B11, B24, B25 (instalador e AppImage em máquinas reais): **média**; parte é dedução, sem execução. Um teste no Windows do PO aumentaria a confiança.
- Números de tamanho da Parte C: **alta** (contagem do Git); a estrutura proposta é **recomendação**, não verdade.

**Pior cenário encontrado.** O caminho C++ do produto chama a biblioteca de geometria dentro do programa, sem vigia e sem limite de tempo, e a gravação escreve por cima do arquivo. Quando a F1 trouxer edição, uma parede problemática no IFC de um cliente pode travar o programa no meio de um salvamento e perder a sessão e o arquivo ao mesmo tempo. O RG-01 e o RG-06 existem para impedir isso antes de virar produto.
