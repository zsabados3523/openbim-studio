# Lote Opus 30 (pedido): revisão da S02
- Escopo: um módulo só (S02). Itens 1 a 5 da lista numerada no fim de `docs/state/reports/F0-S02-revisao.md`.
- Contexto fechado: `reports/F0-S02-revisao.md`, `reports/F0-S02-metricas.md`, `reports/F0-S02.md`, `reports/F0-S02-appimage.md`, `v2/03` S02, `PROPOSTA_REVISAO_F0.md` §3.2, `docs/adr/ADR-005-dependencias-e-build.md` (seção 3.2). O Opus não lê o resto do repositório.
- Saída: aprovado ou reprovado, lista numerada, gravada em `reports/LOTE_OPUS_30.md`.
- Condição de abertura: `get_usage` com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9); só depois do lote 29 (S01). O Opus não revisa o que ele mesmo escreveu: ADR-005 final e os lotes 2 e 3 foram dele; aqui ele confere processo e evidências.
- Estado: **pedido pronto, não aberto**. Uso não verificado.
