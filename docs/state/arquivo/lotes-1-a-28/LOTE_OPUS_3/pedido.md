# Pedido do lote Opus 3: correções do lote 2 e ADR-005 final

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-11 pelo líder (sonnet). Cota semanal usada: 12% (restam 88%, acima do mínimo de 25%). Lote anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_2/resultado.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR claro, com recomendação.

**Contexto fechado.** Leia SOMENTE: este arquivo; `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_2/resultado.md` (os defeitos que você apontou); cartões `docs/state/arquivo/F0-S02/cartoes/F0-S02-T15.md`, `T17`, `T18`, `T19`, `T20`; `packaging/` (tudo); `.github/workflows/ci.yml`; `scripts/license_inventory.py`, `scripts/prune_packages.py`, `scripts/sonda_ifcopenshell.py`; `tests/test_license_inventory.py`; `docs/adr/ADR-005-dependencias-e-build.md`, `docs/adr/ADR-009-licencas-e-conteudo.md`; `docs/state/reports/F0-S02*.md`; `prototypes/cpp_probe_3b/` (sonda 3b já passou no CI; resultado em `F0-S02-sonda.md` e ADR-005 linha 3b). Não use rede. Não é parecer jurídico; diga isso.

### Item 1 (obrigatório): conferir as correções do AppImage (T17) e do instalador (T18)
Para cada defeito do lote 2 (7 do AppImage, 4 do instalador, 1 do CI): corrigido ou não, com evidência. Aprovado ou reprovado com lista numerada. Pendências já conhecidas e aceitas pelo líder: pinar o "runtime" do appimagetool; itens 8 a 10 do relatório do lote 2 (oferta de fonte por 3 anos, tabela de fontes por pacote, tela "Sobre > Licenças") vão para um cartão "antes do primeiro release". Confirme se essa decisão é aceitável.

### Item 2: amostra de T19 e T20
T19 (teste 2 no Windows: 4 de 4 "sim"; sonda 3b) e T20 (inventário de licenças rigoroso, exceções presas à versão). Os resultados batem com as conclusões? As exceções de versão fixa (tbb-devel, ucrt, vc14_runtime, vcomp14, cgal-cpp) são aceitáveis? A troca do MKL pelo OpenBLAS cobre a obrigação?

### Item 3: ADR-005 final (T15) 
Com os números medidos (instalador Windows 309 MB em ~1004 s; AppImage 389 MB; Linux ~94 s), transforme o esboço em decisão: status "proposto, aguardando o PO". Registre o que a S04 deve provar (risco R1) e o que continua em aberto (compilação incremental no Windows ~16 min contra meta de 10 min, aceita pelo PO para revisão na S04).

## Arquivos que você pode criar ou editar
`docs/adr/ADR-005-dependencias-e-build.md` · `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_3/resultado.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 3
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: item 1 e 2: aprovado/reprovado e defeitos; item 3: arquivo
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".
