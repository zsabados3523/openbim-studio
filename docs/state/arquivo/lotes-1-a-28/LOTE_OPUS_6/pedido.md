# Pedido do lote Opus 6: re-revisão das correções da T05 e especificação da T08 e da T26

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-12 pelo líder (sonnet). Cota semanal usada: 22% (restante 78%, acima do mínimo de 25%). Lote anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_5/resultado.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR **simples, sem siglas**, com recomendação. **Regra de execução: nenhum teste gráfico pode abrir janela na tela real; use `xvfb-run` (ver `docs/dev-setup.md`).**

**Contexto fechado.** `git fetch` e leia:
- Seu relatório anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_5/resultado.md` (defeitos A-1, B-1 etc.).
- Correções feitas: `git show 5a832bc` (P0b, testes do oráculo) e `git show c730f5a` (C1, carregador e viewport). Estão nos PRs 16, 18 e 19, ainda sem merge.
- Medição com arquivo real: `docs/state/arquivo/F0-S03/F0-S03-T07-linux.md` (ramo `s03-t05-b`). O arquivo real é `../openbim-studio-referencia/ifc/biblioteca-3pav-ifc4.ifc` (só leitura, nunca copiar nem enviar a serviço online).
- Cartões: `docs/state/arquivo/F0-S03/cartoes/F0-S03-T08.md`, `F0-S03-T26.md`.

### Item 1 (obrigatório, T3): re-revisar as correções P0b e C1
Cada defeito do lote 5 foi corrigido? As correções criaram defeito novo? Para cada PR (16, 18, 19): aprovado ou reprovado, com lista numerada. **Nada entra no `main` sem o seu aprovado.**

### Item 2: especificar a T08 (conversão sem travar a interface)
Achado: 3 peças do arquivo real (máquina de café ~160 s, poltrona ~20 s, montante ~5 s; todas "item mapeado") prendem o Python e travam a interface por até 215 s. Abrir 405 s e pico de 12 GB contra metas de 60 s e 6 GB. Especifique: (a) processo separado (Windows usa "spawn": como passar malhas de volta sem copiar demais?); (b) limite de tempo por peça e o que vira (caixa simples), como listar no resumo; (c) comparar bibliotecas de geometria do IfcOpenShell; (d) oráculo e testes com uma peça lenta fabricada; (e) como medir memória. Diga se a ponte C++ continua desnecessária.

### Item 3: especificar a T26 (vírgula decimal em pt_BR)
Onde e quando fixar `LC_NUMERIC=C` no programa, como testar, riscos.

## Arquivos que você pode criar ou editar
`docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_6/resultado.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 6
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: item 1 (PRs 16, 18, 19 aprovados/reprovados), item 2 (especificação T08), item 3 (especificação T26)
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".
