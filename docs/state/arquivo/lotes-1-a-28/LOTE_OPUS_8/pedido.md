# Pedido do lote Opus 8: re-revisão da T08-0b e da T08-E (curto)

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-12 pelo líder (sonnet). Cota semanal: ver `QUOTA.md` (mínimo de 25% restante). Lote anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_7/resultado.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR **simples, sem siglas**, com recomendação. **Nenhum teste gráfico pode abrir janela na tela real; use `xvfb-run` (comando em `docs/dev-setup.md`).** O arquivo real do PO (`../openbim-studio-referencia/ifc/biblioteca-3pav-ifc4.ifc`) é só leitura: nunca copiar nem enviar a serviço online.

**Contexto fechado.** `git fetch` e leia o seu relatório `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_7/resultado.md` (§1.3, §1.4, §1.6, §4). Já estão no `main` (aprovados por você no lote 7): PRs 28 (oráculo), 30 (biblioteca híbrida) e 35 (vírgula decimal). Faltam e são o alvo deste lote, empilhados: PR 31 `s03-t08-b1`, PR 32 `s03-t08-b2`, PR 33 `s03-t08-c`, PR 34 `s03-t08-d` (todos com o conteúdo já revisado por você no lote 7, mais as correções abaixo) e dois novos:
- **T08-0b** (`s03-t08-0b`, commit `80ce5b2`): oráculo complementar P13 a P18 (cartão `docs/state/arquivo/F0-S03/cartoes/F0-S03-T08-0b.md`), escrito por um agente diferente do implementador, com `xfail` estrito até a T08-E.
- **T08-E** (`s03-t08-e`, commit `f3560a6` mais a mesclagem do `main`): correções do §4 item 6 (cartão `docs/state/arquivo/F0-S03/cartoes/F0-S03-T08-E.md`).
Diffs: `git diff origin/s03-t08-d...origin/s03-t08-0b` e `git diff origin/s03-t08-0b...origin/s03-t08-e`.

### Item 1 (obrigatório, T3): T08-0b
Os casos P13 a P18 cobrem o que você pediu no §4 item 5? Algum afrouxa número? As guardas (`requer_caixa_falha`, `requer_reabertura`, `OBIM_FORCAR_GUARDAS`) são seguras? Aprovado ou reprovado com lista.

### Item 2 (obrigatório, T3): T08-E
Cada correção resolve o que você achou (§1.3 item 1; §1.4 itens 1 a 4; §1.6 item 1; macOS)? As sondas do lote 7 voltam limpas? Novos defeitos? Dois pontos do implementador: (a) no macOS o pico do filho é o residente atual, não o pico; (b) no modo isolado, peças já convertidas no agrupamento de 0,2 s se perdem se a seguinte travar (são refeitas). Medição relatada: arquivo real 41,6 s, 14.804/6, 0 simplificadas, 0 filhos sobrando; suíte `tests` 107 passam, 6 pulam. Aprovado ou reprovado com lista.

### Item 3: ordem de merge
Confirmar a ordem 31, 32, 33, 34, 0b, E (cada um com `linux` e `windows` verdes) ou indicar outra. Resultado do CI nos dois sistemas da ponta (PR de rascunho): ver a tabela no fim deste arquivo, preenchida pelo líder.

## Arquivos que você pode criar ou editar
`docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_8/resultado.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 8
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: item 1 (T08-0b), item 2 (T08-E), item 3 (ordem)
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".

## Resultado do CI da ponta (preenchido pelo líder, 2026-10-12)
Rascunho PR 37 (ponta = `s03-t08-e` com o `main`): `linux` verde, `windows` verde, `appimage` verde; `macos` vermelho (não bloqueia). PRs 39 (T08-0b) e 40 (T08-E) abertos, empilhados.
