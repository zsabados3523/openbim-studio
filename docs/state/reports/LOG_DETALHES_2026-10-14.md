<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Texto completo das linhas longas do LOG (até 2026-10-14)

O `LOG.md` guarda no máximo ~600 caracteres por linha. Aqui está o texto original das linhas que foram encurtadas em 2026-10-14. Chave: data e tarefa.

## 2026-10-10 | S02-T10/T11
2026-10-10 | S02-T10/T11 | ACHADO DE LICENÇA: o AppImage (e o ambiente Windows) trazia ffmpeg (compilação GPL) com x264/x265 e ~60 pacotes de vídeo/áudio/aceleração, puxados pelo vtk (dependência do occt). Nada disso é usado. Nova poda por pacote (scripts/prune_packages.py) remove vtk, viskores, ffmpeg e o que só eles exigem (139 pacotes). Verificado no Linux: selftest OK, ifcopenshell.geom.create_shape OK; AppImage 565 MB -> 390 MB. No Windows o NSIS falhou por tamanho (~1,67 GB sem compressão); a poda deve resolver. Itens para o opus (lote 2): confirmar a poda e que nada GPL foi distribuído antes (AppImage anterior não foi publicado, só artefato local).

## 2026-10-11 | S02-T18
2026-10-11 | S02-T18 | Correções do instalador Windows escritas (ainda sem CI): desinstalador só apaga env/app/licenses e arquivos conhecidos (arquivos do usuário sobrevivem; pasta só some se vazia); atalho com pythonw -I; limpeza de env/app antes de reinstalar por cima; AddSize 2,4 GB, mensagem de extração e limpeza em falha; textos LGPL-3/LGPL-2.1/GPL-3/exceção do OCCT em licenses; TKIVtk*.dll apagadas; prune com --esperado=occt; NSIS 3.12 (build h4c425fd_1) e reuse 6.2.0 fixados; runtime-environment.yml movido para packaging/. test_installer.sh: ambiente sujo, -I, troca de DLL, reinstalar por cima, arquivo do usuário sobrevive, instalação ≤300 s e abertura ≤10 s.

## 2026-10-11 | F0-S03-T05
2026-10-11 | F0-S03-T05 | FEITA nas 3 partes (subagentes sonnet; revisão do líder: suíte 60 passam offscreen, 68 em Xvfb): PRs 16 (oráculo), 18 (carregador) e 19 (viewport e medição). Metas do portão da S03 atingidas na máquina do PO com 1.000.008 triângulos: abrir 13,5 s (meta 60), 833 MB (meta 6 GB), atraso máx 118 ms, p95 9,8 ms, 60 FPS com placa real. Sem merge: T3 aguarda lote Opus 5 (docs/state/LOTE_OPUS_5.md) e ok do PO. Incidente: uma janela de teste abriu ~15 s na tela do PO antes da instrução do Xvfb ser aplicada (memória do projeto atualizada). PR 17 corrige localidade pt_BR nos testes.

## 2026-10-11 | Lote opus 5
2026-10-11 | Lote opus 5 | T05 partes 0, A e B REPROVADAS (defeitos A-1 obter(timeout) pode travar; B-1 plano longe corta o fundo após arrastar; mais ajustes pequenos; testes e medidas fiéis). T06 APROVADA. T25 REPROVADA só por falta de evidência registrada. CORREÇÃO de registro: o LOG/BOARD diziam 'metas do portão atingidas': são metas da T05 (13,5 s, 833 MB, atraso 118 ms, 60 FPS placa real); o portão da S03 só se decide na T07 (IFC real e Windows). Achado fora da T05: IFC gravado com vírgula em pt_BR (cartão T3 F0-S03-T26). Cartões abertos: T05-P0b, T05-C1, T25-C1, T06b, T26. Exceção de tamanho (Parte 0 com 711 linhas, Parte B ~418): recomendada pelo opus, aguarda ok do PO.

## 2026-10-13 | Lote opus 12
2026-10-13 | Lote opus 12 | REPROVADO com correções autorizadas (reports/LOTE_OPUS_12.md): T05+limite 5 min aprovados; T06 oráculo com R1-e falso e rodadas não relatadas (mudanças 1 e 2, pelo agente de oráculo); T07 viewport.cpp aprovado sem mudança; travamento da sonda no Windows = intermitente aberto (45 min, 1 vez, 2 reruns limpos); cartões T07b e T06b abertos; T08 recebe a lista. Registro de processo: PR junta T05, T06, T07 (pilha, já registrado no lote 10); oráculo 402 e T07 ~408 linhas (>400); CMake/ponte.cpp/ci.yml fora dos arquivos permitidos (aceitos). Gatilho: novo estouro da sonda ou viewport antes do T07b → fazer 9.a primeiro.

## 2026-10-13 | Lote opus 13
2026-10-13 | Lote opus 13 | REPROVADO com correções autorizadas (reports/LOTE_OPUS_13.md): a correção do tamanho da swapchain D3D11 (cubo azul cortado no Windows, defeito real do C++ achado pelo oráculo) quebra com escala fracionária e após `soltar`; troca para o padrão do QRhi (3 linhas em `quadros()`); diagnóstico do oráculo sai. Registro: os commits de diagnóstico no oráculo foram feitos pelo agente de investigação por ordem do líder (não pelo implementador); a correção em C++ entrou depois do lote 12 sem revisão (aceita só com a mudança 1). T07b passa a ser o próximo cartão logo após o merge do PR 62, antes da T08; sonda só informativa tem o mesmo padrão antigo (`sonda_desenho.cpp:105`).

## 2026-10-13 | Lote opus 14
2026-10-13 | Lote opus 14 | REPROVADO com correção autorizada (reports/LOTE_OPUS_14.md): T07b, T06b e T08 aprovados, exceto corrida entre `limpar()` e o envio em fatias (mudança 1: 3 linhas em `cena.cpp`/`viewport.cpp`; opcional 2 em `adicionar_lote`). Régua do caso de orçamento mudada pelo líder (de ≤50 ms absoluto para envio ≤50 ms e cena estável ≤3× a mediana): aceita pelo Opus, número oficial de 50 ms na máquina do PO. Sonda: `faulthandler` baixado para 180 s (opção b), travamento segue intermitente aberto. Registro: `tests/test_s04_viewport_b.py` fora do arquivo único permitido e `tests/test_s04_viewport.py` com 447 linhas (aceitos). Cartão T06c aberto; T09 recebe os achados 4, 5, 6, 10; T12 os 7 e 8.
