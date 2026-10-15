# Pedido do lote Opus 9: especificação da S04 (ponte Python↔C++, híbrido vs C++ puro)

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-12 pelo líder (sonnet). Antes de abrir: cota semanal restante > 25% (ver `QUOTA.md`). Lote anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_8/resultado.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR **simples, sem siglas**, com recomendação. **Nenhum teste gráfico pode abrir janela na tela real; use `xvfb-run` (comando em `docs/dev-setup.md`).** Arquivos do PO fora do repositório (`../openbim-studio-referencia/`) só de leitura, nunca copiar nem enviar a serviço online.

**Contexto fechado.** `git fetch` e leia: `v2/03_fase0_especificacao.md` (S04, metas e regra de decisão; S03 para o que já existe), `v2/02_plano_mestre_v2.md` (arquitetura), `docs/adr/ADR-005-dependencias-e-build.md` (build, sonda C++ da fatia 3b), `docs/state/reports/F0-S03.md` (relatório final da S03), `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_7/resultado.md` §3 e `arquivo/lotes-1-a-28/LOTE_OPUS_8/resultado.md` §2.3 (itens que vão para a S04), `docs/state/PO.md` e `CLAUDE.md`. Código existente: `prototypes/cpp_probe*`, `prototypes/viewport_qrhi/`.

### Item 1 (obrigatório, TA/T3): especificar a S04
1. **Os dois fluxos** (A híbrido PySide6 + `ifcopenshell.api` + módulo C++; B C++ puro) com o mesmo fluxo mínimo: 200 paredes criadas e editadas e a viewport atualizada. Escolher nanobind ou pybind11 para o módulo (com a sonda de build que já existe), como o C++ recebe o mesmo `ifcopenshell.file` sem cópia, e como isso é provado nos dois sistemas.
2. **Metas e oráculo:** transformar cada meta de v2/03 (compartilhar o modelo sem cópia; parede com camadas < 200 ms p95; editar propriedade < 50 ms; 1.000 paredes < 20 s; viewport com 20 FPS ou mais durante lote Python (GIL liberado); híbrido ≤ 3× o C++ puro; linhas de código e tempo de agente registrados) em testes ou medições reproduzíveis, quem escreve o oráculo (agente diferente do implementador) e o que roda no CI nos dois sistemas.
3. **Divisão em cartões** de até 400 linhas, classe (T3 onde há ponte, threads, transações), ordem e dependências, incluindo o que sai da S03: seleção por triângulo, orçamento de peças lentas, iterador por peça mais barato, reabertura da janela (lote 8 §2.3), memória final.
4. **ADR-001 (stack) e ADR-004 (threads):** esqueleto com as perguntas que a S04 precisa responder e os números que vão entrar.
5. **Riscos e saídas:** o que fazer se o híbrido falhar (regra de v2/03), custo de cota estimado em fatias P/M/G.

## Arquivos que você pode criar ou editar
`docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_9/resultado.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 9
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: especificação (item 1.1 a 1.5)
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".
