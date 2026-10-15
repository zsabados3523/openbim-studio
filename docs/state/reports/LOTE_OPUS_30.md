<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Lote Opus 30: revisão da S02 (resultado)
Data: 2026-10-15 · Revisor: Opus (subagente, contexto fechado) · Pedido: `docs/state/LOTE_OPUS_30.md` · Objeto: lista numerada no fim de `reports/F0-S02-revisao.md`.

**Limite desta revisão.** Eu escrevi a versão final do ADR-005 e revisei a S02 nos lotes Opus 2 e 3. Por isso **não julgo de novo o mérito** dessas decisões (conda-forge, poda, NSIS, AppImage, correções T17 e T18). Aqui confiro só o processo e as evidências da revisão. Abertura sem checar o uso: permitida pela exceção do PO de 2026-10-15 (`PO.md`, lotes 29 a 31).

## O que conferi fora dos relatórios
- **Execução do CI 38653866732** (PR 93, 2026-10-14), lida no GitHub, só leitura:
  - `windows`: **28 min 29 s** (23:24:23 a 23:52:52). Criar o ambiente ~5 min; testes ~6 min; os passos novos da S04 (módulo obimcore ~3 min, viewport C++ ~7,5 min, fluxo B ~3,5 min, sonda ~1 min) somam ~15 min.
  - `linux`: **17 min 27 s** (não 81 s). Os passos da S04 somam ~10 min.
  - `instalador-windows`: verde, mas **não montou nada**: 14 s, e todos os passos do instalador foram "pulados" porque o PR não mexia no empacotamento.
  - `appimage`: 2 min 50 s, verde. `macos`: vermelho.
  - Contagem da suíte principal: Linux "163 passed, 169 skipped"; Windows "161 passed, 171 skipped". Confere. Há mais blocos de teste em passos separados (Linux 2, 21, 128 e 61 testes; Windows 2, 21, 127 + 1 pulado e 61), que a revisão não cita.
- Linhas citadas como evidência: `packaging/windows/test_installer.sh` 44 e 46, `packaging/linux/AppRun` 11 a 14 e `tests/test_license_inventory.py` 112 existem e dizem o que a revisão afirma.
- Inventário de licenças: nos jobs `linux`, `windows` e `macos` ele roda com `--informativo` (só lista, **não reprova**); quem reprova é a montagem do AppImage e a do instalador (`build_appimage.sh` linha 60, `build_installer.sh` linha 64), sobre o ambiente que vai no pacote.
- T23 já consta do plano: `v2/03` linha 31 (aprovada pelo PO em 2026-10-15).

## Respostas aos itens 1 a 5
1. **REPROVADO.** Os 8 critérios são os do plano, mas o critério 1 usa como evidência "`instalador-windows` verde" numa execução em que o instalador **não foi montado**. Desde o PR 91 o Windows não gera instalador "a cada merge", como pede `v2/03`; o PO aprovou a mudança, mas pela regra D8 isso é uma exceção e precisa da meta original ao lado. O critério 3 também ficou velho: o PO já aceitou capturas e GIF no lugar do MP4.
2. **REPROVADO.** A meta original (incremental de 10 min) está registrada, com o motivo e quem aprovou, e a volta ao portão (S10) está escrita: essa parte da D8 está certa. Mas os números estão velhos. A tabela fala em ~16 min no Windows e 81 s no Linux; a execução 38653866732 mediu **~28 min no Windows e ~17 min no Linux**. Ou seja, o Linux hoje **também** passa de 10 min, e isso não aparece. A frase "encurta o CI de um PR comum" é verdadeira só para o instalador; o job `windows` ficou mais longo por causa da S04.
3. **APROVADO.** O destino de cada pendência é adequado: T23 (agora no plano), T21, T22 e T24 conferidos no `main` nas linhas citadas, macOS como cartão pequeno, A3 e A4 com o PO. Ajustes de texto na lista de recomendações (itens 5 e 6).
4. **REPROVADO.** A ideia está certa (a tabela da S01 cobre o que escolhemos; o inventário cobre o que vai no pacote), mas a frase "o inventário do CI falha se vier uma licença fora da lista" é imprecisa: nos jobs de teste ele só informa; quem reprova é a montagem dos pacotes. E não diz que, desde o PR 91, a checagem rigorosa do Windows só roda quando o empacotamento ou as dependências mudam (`ci.yml` linha 387). Falta também dizer, como limite aceito ou não pelo PO, que um pacote com licença permitida mas fora da tabela da S01 passa sem aviso.
5. **REPROVADO.** A contagem de testes confere. Mas duas das quatro correções ficaram incompletas: (a) `reports/F0-S02.md` item 2 ainda diz que o CI está verde em `macos` (está vermelho) e dá "Linux ~90 s, Windows 12 a 17 min" (hoje ~17 e ~28 min); (b) `reports/F0-S02-video.md` ainda diz "conferir no próximo run", e a execução 38653866732 já rodou o passo "Gravação do roteiro" com sucesso no Linux e no Windows. A frase "a suíte cobre o repositório inteiro" omite os blocos de teste dos passos separados.

## Recomendações (numeradas)
1. Seção 1, critério 1: trocar para "Sim, com exceção (D8)": meta original "artefato instalável a cada merge"; hoje o instalador Windows só é montado quando o empacotamento muda (PR 91, ok do PO em 2026-10-14); o AppImage segue a cada merge. Tirar `instalador-windows` como prova de instalador gerado nesse run.
2. Seção 1, critério 3: registrar a resposta do PO de 2026-10-15 (capturas e GIF substituem o MP4) e marcar como "Sim, com exceção (D8)", meta original "vídeo".
3. Seção 2 e `F0-S02-metricas.md`: acrescentar uma linha com a execução 38653866732 (Windows ~28 min, Linux ~17 min), dizer de onde vem o aumento (passos da S04) e marcar o incremental como **não atingido também no Linux**. Manter a meta original de 10 min ao lado.
4. Cartão S02-T25: antes de medir, levar ao PO uma pergunta objetiva sobre **o que conta como "build incremental"** (o job inteiro do CI ou só recompilar depois de mudar um arquivo na máquina de quem programa), com recomendação. Hoje os números comparam coisas diferentes. Isso é definição de meta: decide o PO.
5. Seção 3, item 7: apontar para o cartão S02-T25 (já criado pelo PO), não "sem cartão". Itens 2, 9 e 10: registrar as respostas do PO de 2026-10-15 (T23 no plano, GIF no lugar do MP4, `appimage` já obrigatório).
6. Seção 3, item 11 (macOS vermelho): dar data e dono, mesmo que seja "investigar até a S10", como pede o roteiro (`PROPOSTA_REVISAO_F0.md` §3, passo 2).
7. Parágrafo de licenças: reescrever dizendo onde o inventário reprova (só na montagem dos pacotes) e onde só informa (jobs de teste); dizer quando a checagem do Windows roda; e registrar como limite conhecido que não há comparação pacote a pacote com a tabela da S01, perguntando ao PO se aceita.
8. `reports/F0-S02.md` item 2 e seção 6 da revisão: corrigir macOS (vermelho) e os tempos atuais.
9. `reports/F0-S02-video.md`: preencher as linhas do CI com o resultado da execução 38653866732.
10. Seção 5: citar os blocos de teste dos passos separados (ou dizer que não estão na contagem), em vez de "a suíte cobre o repositório inteiro".
11. O ADR-005 §3.2 também traz os tempos antigos (~16 min). Mudar ADR é decisão do PO: levar a ele uma nota de atualização, sem editar o ADR por conta própria.
12. Depois das correções 1 a 10 (só texto, cabem num cartão T0 pequeno), basta o líder conferir; não precisa de novo lote Opus, porque nada aqui muda código nem decisão.
