# Pedido do lote Opus 4: especificação da T05 (malhas do IFC em threads) e amostra do viewport

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-11 pelo líder (sonnet). Antes de abrir: cota semanal restante > 25% (última informada: 14% usados). Lote anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_3/resultado.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR claro, com recomendação.

**Contexto fechado.** Leia SOMENTE: este arquivo; `v2/03_fase0_especificacao.md` (S03 e S04); `docs/adr/ADR-005-dependencias-e-build.md` (§7.1, provas da S04); `docs/research/2026-10-11-viewport-qrhi.md`; `docs/state/arquivo/F0-S03/cartoes/F0-S03-T0*.md`; `prototypes/viewport_qrhi/`; `tests/test_viewport_*.py`; `scripts/gerar_modelo_grande.py`; `corpus/README.md`. Não use rede (exceto, se necessário, a documentação pública do IfcOpenShell, citando a fonte). Só crie os arquivos listados.

### Item 1 (obrigatório, T3): especificação e oráculo da S03-T05
Tarefa: gerar as malhas (triângulos) dos produtos do IFC em várias linhas de execução (threads) e entregá-las ao viewport sem travar a janela. Decidir e especificar:
1. **Como:** `ifcopenshell.geom.iterator` com `num_threads` (Python) é suficiente na S03, ou a S03 já precisa de C++ (módulo nanobind, como na sonda 3b)? A S04 compara híbrido e C++ puro; a S03 deve usar o caminho mais barato que não contamine essa comparação. Considere o GIL, a vida útil dos objetos e o consumo de memória.
2. **Contrato de dados:** formato da malha entregue ao viewport (vértices, índices, id do produto, cor), em lotes; cancelamento; erros de geometria; o que a interface `Viewport.set_mesh` precisa ganhar.
3. **Oráculo:** testes objetivos (contagem de triângulos igual à referência `1.000.008` do `corpus/README.md`; mesmos resultados com 1 e N threads; janela responsiva, medida como atraso máximo do laço de eventos), e as metas do portão da S03 que a T05 mede (abrir ~100 MB < 60 s; RAM < 6 GB).
4. **Riscos** para a S04 (ponte Python↔C++) que a T05 não deve resolver nem esconder.
Saída: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md` (seção "Especificação T05"), e o cartão `docs/state/arquivo/F0-S03/cartoes/F0-S03-T05.md` reescrito com critérios de aceite medíveis (classe T3).

### Item 2: amostra de revisão de T03 e T04 (1 em 3 das T2)
O `QRhiWidget` em Python puro e a classe `Camera`: conclusões da ficha e do código se sustentam? A interface `Viewport` aguenta a T05 e a T06 (seleção por clique, que precisa de IDs por triângulo ou por objeto)? Aprovado ou reprovado com lista numerada.

## Arquivos que você pode criar ou editar
`docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md` (novo) · `docs/state/arquivo/F0-S03/cartoes/F0-S03-T05.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 4
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: item 1: arquivos; item 2: aprovado/reprovado e defeitos
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".
