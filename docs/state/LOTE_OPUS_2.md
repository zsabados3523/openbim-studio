# Pedido do lote Opus 2: licenças e empacotamento (dependências e distribuição)

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-10 pelo líder (sonnet). Antes de abrir: cota semanal restante > 25%. Lote anterior: `docs/state/reports/LOTE_OPUS_1.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR claro, com recomendação.

**Contexto fechado.** Leia SOMENTE estes arquivos:
1. Este arquivo.
2. Item 1: `docs/research/2026-10-10-licencas-tabela-mestre.md` (versão 2), `docs/research/2026-10-10-licencas-revisao-opus.md` (a sua revisão anterior), `THIRD_PARTY.md`, `docs/state/reports/F0-S01.md`, e a lista de componentes em `v2/03_fase0_especificacao.md` (S01).
3. Item 2: `v2/05_politica_pesquisa_e_ip.md` (§3) e `docs/adr/ADR-009-licencas-e-conteudo.md`.
4. Item 3: `packaging/linux/` (todos os arquivos), `packaging/README.md`, `docs/research/2026-10-10-appimage-p1.md`, `docs/state/reports/F0-S02-appimage.md`, `docs/adr/ADR-009-licencas-e-conteudo.md` (§5.3), `docs/adr/ADR-005-dependencias-e-build.md` (testes 7 e 8).
5. Item 4: `docs/research/2026-10-10-sonda-cpp.md`, `prototypes/cpp_probe/`, `docs/state/reports/F0-S02-sonda.md`, `docs/adr/ADR-005-dependencias-e-build.md`.
6. Item 5 (se houver cota): `.github/workflows/ci.yml`, `scripts/license_inventory.py`, `REUSE.toml`, `docs/state/cards/F0-S02-T06.md`.

Não use rede. Não é parecer jurídico; diga isso nos textos. Só crie os arquivos listados abaixo.

### Item 1: conferir a correção da tabela mestre (F0-S01-T11)
Você reprovou a versão 1 por 12 defeitos. O líder aplicou os 12 na versão 2, sem nova pesquisa. Dê **aprovado** ou **reprovado com lista numerada**; confira defeito por defeito (1 a 12) e confira `THIRD_PARTY.md` e `docs/state/reports/F0-S01.md` (que ficaram fora do lote 1). Atenção especial ao identificador SPDX da exceção do OCCT, que ficou "de memória".
Saída: seção no final de `docs/research/2026-10-10-licencas-revisao-opus.md`.

### Item 2: conferir o ajuste de `v2/05` §3
O líder editou `v2/05` §3 (linhas novas: LGPL-2.1-only como biblioteca, GPL-3 ou posterior, nota corrigida da libdxfrw). Aprovado ou reprovado, e confira se o texto bate com o ADR-009.
Saída: seção no relatório do lote (arquivo abaixo).

### Item 3: **revisão obrigatória** do AppImage P1 (F0-S02-T10)
Confira, contra o ADR-009 §5.3 e o ADR-005 testes 7 e 8: bibliotecas LGPL em arquivos separados (sem Qt estático, modo pasta); nenhum travamento contra troca (o `AppRun` fixa `PYTHONHOME`: isso atrapalha a troca?); pasta `licenses/` e textos; `LGPL-COMO-TROCAR.md` (as instruções funcionam?); `FONTES.md` (oferta de código-fonte da versão exata) e a nota `REMOVIDOS.md` da poda de vtk/viskores (os avisos de licença do que foi removido ainda precisam ficar?). Verifique se a poda deixa algum aviso incompleto e o resíduo `libTKIVtk*` do OCCT. Aprovado ou reprovado com lista numerada. Dê um parecer curto sobre o fato de o appimagetool vir de uma tag móvel (`continuous`) sem checksum.
Saída: seção no relatório do lote.

### Item 4: amostra de revisão da sonda C++ (F0-S02-T16)
Pergunta: as conclusões do teste 2 (cabeçalhos e bibliotecas compartilhadas `libifcopenshell.*` presentes; módulo Python liga nelas) e do teste 3 (módulo nanobind + OCCT + Qt compila em 2,4 s limpo / 0,9 s incremental no Linux) fecham esses dois testes do ADR-005? A descoberta de que a API C++ da 0.9 usa `ifcopenshell::file` (e não `IfcParse::IfcFile`) muda o teste 5 (prova do risco R1, S04, T3)? Atualize o ADR-005 (resultados parciais; status continua esboço) e diga o que a S04 deve provar.
Saída: ADR-005 atualizado + seção no relatório do lote.

### Item 5 (opcional, só se a cota permitir): amostra do CI e do inventário de licenças (F0-S02-T06)
Leia o workflow, o script de inventário e o `REUSE.toml`. O CI ainda não rodou (o push está bloqueado por autenticação); aponte riscos que o primeiro run provavelmente mostrará, e se a exceção do `tbb-devel` (metadado vazio; pacote irmão Apache-2.0) é aceitável.
Saída: seção no relatório do lote.

## Arquivos que você pode criar ou editar
`docs/research/2026-10-10-licencas-revisao-opus.md` (só acrescentar seção) · `docs/adr/ADR-005-dependencias-e-build.md` (atualizar resultados) · `docs/state/reports/LOTE_OPUS_2.md` (novo)

## Formato da resposta final no chat
```
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 2
RESUMO: <≤ 8 linhas em pt-BR simples>
EVIDENCIAS: <arquivos; item 1, 2 e 3: aprovado/reprovado e defeitos>
PERGUNTA_PO: <se houver, com recomendação>
```
Depois, o PO volta ao líder (sonnet) com "Leia docs/state e continue".
