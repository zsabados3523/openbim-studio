# Proposta de alteração do CLAUDE.md (para o PO colar)

Feita pelo líder em 2026-10-12, a pedido do PO. O líder não edita o `CLAUDE.md`: quem cola é o PO.

## O que trocar na seção "Autorização permanente do PO"

**Item 3, substituir por:**

3. Pode dar merge do PR quando `linux` e `windows` estiverem verdes e o PR for só de tarefa T0, T1 ou T2 já aprovada em cartão. **T3: também pode, desde que o conteúdo exato tenha sido aprovado pelo Opus (ver 6) e `linux` e `windows` estejam verdes; avisar o PO em seguida com resumo curto. ADR, meta do portão e qualquer coisa que mexa em licença, regras do processo ou este `CLAUDE.md` o PO aprova antes.**

**Item 4, substituir por:**

4. Pode rodar subagentes sonnet e haiku conforme o cartão. Opus: ver 6.

**Acrescentar, depois do item 5:**

6. **Lote Opus pelo líder (PO, 2026-10-12).** O líder abre o lote Opus como subagente (`model: opus`, contexto fechado, mesma saída aprovado/reprovado com lista numerada), sem pedir ok, lê o relatório, aplica as recomendações e grava o relatório inteiro em `docs/state/reports/`. Antes de abrir confere o uso (`get_usage`): semanal com mais de 25% restante e janela de 5 h abaixo de 60%; senão espera a renovação. Resumo curto ao PO depois, em pt-BR simples e sem siglas. Continuam do PO: decisões de meta, ADR, escopo, licença e regras. O Opus nunca revisa o que ele mesmo escreveu na tarefa; oráculo e implementação seguem em subagentes diferentes.

## Como aplicar
Abra `CLAUDE.md`, troque os itens 3 e 4 pelos textos acima e cole o item 6 no fim da seção. Depois avise "regra aplicada" no chat.
