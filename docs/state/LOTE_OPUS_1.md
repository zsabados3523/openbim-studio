# Pedido do lote Opus 1: licenças e dependências

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-10 pelo líder (sonnet). Antes de abrir: cota semanal restante > 25%.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do projeto OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR claro, sem jargão, com recomendação.

**Contexto fechado.** Leia SOMENTE estes arquivos e nada mais do repositório:
1. `docs/state/LOTE_OPUS_1.md` (este)
2. `docs/research/2026-10-10-licencas-tabela-mestre.md`
3. `docs/research/2026-10-10-licencas-grupo-a.md`, `-grupo-b.md`, `-grupo-c.md`, `-grupo-d.md`
4. `docs/research/2026-10-10-sinapi-termos.md`
5. `docs/research/2026-10-10-dependencias-disponibilidade.md`
6. `v2/05_politica_pesquisa_e_ip.md` (§3 e §4) e `v2/02_plano_mestre_v2.md` (§5 e §12)
7. `docs/state/cards/F0-S01-T11.md`, `F0-S01-T12.md`, `F0-S02-T02.md`
8. `docs/adr/README.md`

Não é parecer jurídico; diga isso nos textos. Não use rede. Não edite outros arquivos além dos listados em "Arquivos que você pode criar".

### Item 1: revisar a tabela mestre de licenças (F0-S01-T11)
Dê **aprovado** ou **reprovado com lista numerada de defeitos**. Responda, uma a uma, às quatro pendências da tabela:
1. OCCT: LGPL-2.1-only + Open CASCADE Exception 1.0 com AGPL v3 por ligação dinâmica. Compatível? Sob que condições?
2. libdxfrw: licença disputada (README/cabeçalhos "GPL-2.0-or-later"; COPYING e API "GPL-2.0"). Fica fora ou entra? (Alternativa já escolhida: ezdxf, MIT.)
3. Relink da LGPL (Qt, IfcOpenShell, OCCT, pythonocc): o que o empacotamento precisa garantir (instalador Windows e AppImage)?
4. WiX e o Open Source Maintenance Fee; termos do conda-forge e do canal `defaults`; exceção do PyInstaller.
Aponte também qualquer linha da tabela que você discorde (compatibilidade ou condição).
Saída: `docs/research/2026-10-10-licencas-revisao-opus.md`.

### Item 2: escrever o ADR-009, licenças e política de conteúdo (F0-S01-T12)
Só depois do item 1. Siga o cartão e o formato de `docs/adr/README.md`. Inclua: AGPL-3.0-or-later (decidido pelo PO), regras de compatibilidade, política de conteúdo (ABNT, NBR 15965, AsBEA, SINAPI, TCPO), como fiscalizar (REUSE/SPDX no CI) e "o que nos faria mudar de ideia". Posicionamento: núcleo geral, Brasil como primeiro pacote regional (decisão do PO de 2026-10-10). Resumo de 5 linhas em pt-BR no fim.
Saída: `docs/adr/ADR-009-licencas-e-conteudo.md`.

### Item 3: esboço do ADR-005, dependências, build e empacotamento (F0-S02-T02)
Siga o cartão. É esboço: **decisão pendente**, com plano de testes numerados (cada um com meta), opção provisória recomendada para o ambiente de desenvolvimento e resumo de 5 linhas. Use a ficha de disponibilidade e as licenças do grupo D (incluindo a escolha MSI/WiX vs NSIS e AppImage). Diga qual teste prova que IfcOpenShell C++ e Python compartilham versão e ABI (risco R1), e o que fazer se o conda-forge não trouxer cabeçalhos do IfcOpenShell. Metas da S02: build limpo ≤ 60 min, incremental ≤ 10 min, instalador ≤ 600 MB.
Saída: `docs/adr/ADR-005-dependencias-e-build.md` (status: esboço).

### Item 4 (opcional, só se a cota permitir): conferir a classificação
Leia `docs/state/BOARD.md` e os 27 cartões em `docs/state/cards/`. Diga se alguma tarefa deveria ser T3 ou se o limite de 400 linhas está em risco. Lista curta numerada. Saída: seção final de `docs/state/reports/LOTE_OPUS_1.md`.

## Arquivos que você pode criar
`docs/research/2026-10-10-licencas-revisao-opus.md` · `docs/adr/ADR-009-licencas-e-conteudo.md` · `docs/adr/ADR-005-dependencias-e-build.md` · `docs/state/reports/LOTE_OPUS_1.md`

## Formato da resposta final no chat
```
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 1
RESUMO: <≤ 8 linhas em pt-BR simples>
EVIDENCIAS: <arquivos criados; item 1 aprovado/reprovado e defeitos>
PERGUNTA_PO: <se houver, com recomendação>
```
Depois, o PO volta ao líder (sonnet) com "Leia docs/state e continue".
