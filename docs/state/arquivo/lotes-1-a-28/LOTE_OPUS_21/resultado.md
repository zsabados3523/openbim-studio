# Lote Opus 21: releitura T16b (PR 78, ramo s04-t16 em 13009b5)

**APROVADO**, condição: Windows verde no CI antes do merge (auto-merge garante).
Rodado sob xvfb: test_s04_abertura 18 passaram (97 s); viewport_processo + carregador 37 passaram, 3 pularam. Modo isolado razão 1,00/1,01 (alvo ≤2×); d1 3,9–4,0 s (teto ~8 s; antes erro em 26 s); d2 6,5 s; sonda 300 paredes + 1 lenta ~4,5 s.
Itens reprovados no lote 20 (ordem do iterador, orçamento do laço, oráculo com layout fora da ordem de id, cópias fora da contagem, textos): todos corrigidos. Sem defeitos novos bloqueantes.

Recomendações (não bloqueiam):
1. `carregador.py:169,366,506-507`: `_feitos` nunca lido; remover.
2. `processo_malhas.py:201-209`: enviar `sem_malha` logo após cada peça no modo uma-peça (senão se perde se o filho morrer).
3. `carregador.py:334-336`: custo do modo uma-peça não medido (pior caso 30–55 s como no main); medir no arquivo do PO.
4. `carregador.py:323-326`: motivo próprio para o teto de 20 reinícios.
5. Cabeçalho do oráculo (`tests/test_s04_abertura.py:32-35`) desatualizado; só o agente de oráculo edita.
6. Diff 552+/65-, sendo 458 de oráculo: exceção registrar no LOG.
7. macOS falhou (não bloqueia); conferir se tem relação.
