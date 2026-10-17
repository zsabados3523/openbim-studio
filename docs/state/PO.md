# Perguntas e decisões do PO

> Duas partes: **Regras em vigor** (curta; o que vale hoje) e **Abertas** (o que espera o PO). O histórico de respostas está em `arquivo/PO-historico.md`. Cada pergunta traz a recomendação do líder. Sem resposta, vale a recomendação como decisão assumida, registrada aqui. Atualizado: 2026-10-15.

## Regras em vigor (2026-10-14)
- **Opus:** abrir sessão só com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9). A exceção de cota de 13/10 **encerrou** em 14/10 09:00Z. Quem abre: o líder, como subagente, conforme o `CLAUDE.md` item 6. **Exceção de 2026-10-15 (PO):** lotes 29, 30 e 31 podem abrir sem checar o uso, só desta vez.
- **S04 pausada (D1):** nenhuma T3 nova na S04 (T14c, T15 em diante) até as revisões de S01, S02 e S03 e as respostas D1 a D8. Só terminam PR 83 (T12).
- **Escopo da 1.0 (D3):** versão mínima **inclui detalhes 2D**. DXF e fachadas são candidatos a adiar na sessão de escopo. Prazo de 21 a 42 meses não é recalculado antes da medição da F0.
- **Planos antigos (D2):** estão em `docs/arquivo/`; `CLAUDE.md` atualizado (F0-RG-24, aprovado pelo PO em 2026-10-15).
- **Exceção de portão (D8):** toda exceção registra a meta original e o motivo; o portão F0 (S10) é reavaliado com as metas originais.
- **macOS:** melhor esforço, sem garantia, nunca prometido em texto ao usuário (2026-10-13).
- **Nada em fórum ou convite externo em nome do PO** sem ordem dele (2026-10-13).
- **Só o PO decide:** ADR, meta do portão, escopo, licença, regras do processo e `CLAUDE.md`, instalar ferramenta nova, baixar arquivo, cota extra, apagar dados, credenciais, `main` direto, execução na tela real, meta da F0 não atingida.
- **Exceções de ausência do PO (12, 13 e 13/10 noite):** válidas só enquanto o PO estava fora. Ele voltou e respondeu D1 a D9 em 14/10; tratadas como encerradas (confirmar, item A9).

## Abertas (esperam o PO)
| # | Pergunta | Recomendação do líder |
|---|---|---|
| A1 | Rodada única na tela real do Linux para os números oficiais da S04 (M1 a M6), quando PR 83 e T14c entrarem | Sim, depois que a D1 acabar |
| A2 | ADR-001 e ADR-004 com números (cartão T19) e a nota sobre a interface `atualizar(lote_novo, guids_remover)` | Decidir ao fim da S04, com a medição do critério de custo de manutenção (P6) |
| A3 | Travar o ambiente do instalador (`packaging/runtime-environment.yml`) pela mesma trava `.lock` | Sim |
| A4 | Aplicar ao AppImage o mesmo critério do instalador (roda só quando o empacotamento muda) | Sim, depois de ver o PR 91 funcionando |
| A5 | Se os testes de tempo do Windows continuarem a oscilar: dar folga aos limites (muda metas) | Preferir medir pela mediana de várias rodadas; folga só com a meta original registrada (D8) |
| A6 | Quando e a quem enviar o convite de revisão externa; wireframes da S09; 8 testes no Revit | Decidir depois das revisões S01 a S03 |
| A7 | Atualizar o ambiente local (`zlib`, `libxml2`) para compilar o fluxo B na máquina do PO (instalar pede ok) | Sim, quando a D1 acabar |
| A9 | Confirmar que as exceções de ausência acabaram | Sim |
| A10 | Passar os números do `/usage` de 13 e 14/10 para `QUOTA.md` | Informar janela e semana, antes e depois |
| A11 | D5: nomes dos colegas de estágio para testar e momento | Sem prazo; combinar antes da F1 |
| A15 | SINAPI: o PO informou (2026-10-15) que o uso gratuito é permitido, mas software que automatiza processos ou buscas precisa de autorização da CAIXA. Confirmar o texto e pedir a autorização formal | Consulta formal à CAIXA como requisito da F5; texto fica em `docs/research/2026-10-10-sinapi-termos.md` |

- **Entrevista S09 (A13), aceita pelo PO em 2026-10-15,** com um ajuste: depois dos eixos vem a estrutura, e as paredes não precisam ficar presas a eixos; a ordem do fluxo é hábito, não obrigação. Wireframes podem começar quando o PO mandar as imagens.
- **IFC real do PO (D4), 2026-10-15:** o PO quer usar um IFC real dele nos testes. Fica fora do repositório (`../openbim-studio-referencia/`); só abrir quando o PO listar o arquivo no chat.

- **Regras de parada da T15 (2026-10-16):** (a) janela surda por mais de 1 s no lote de 1.000 paredes nas duas formas (medida no controle) e (b) parede com 150 aberturas parando a janela mais da metade do tempo do cálculo do desenho = parar e levar ao PO. Resultado da T15d: nenhuma disparou; a escolha entre as formas é apertada (relatório `reports/F0-S04-threads.md`).
- **Atribuição nos commits e pedidos (2026-10-16):** manter `Co-Authored-By` do Claude nos commits; pedidos sem "Generated with Claude Code". Títulos de pedido: `F0-S04-T15c: o que faz`.
- **Entrevista com o PO (grill-me) para toda feature nova ou dúvida de comportamento (2026-10-15/16),** não para correções internas.
- **Rodada oficial na tela real do Linux (A1):** só com ok e horário do PO, depois da T15d (feita). Pendente.

## Histórico
Todas as respostas e decisões anteriores do PO (2026-10-10 a 2026-10-15) estão em `arquivo/PO-historico.md`. Resposta nova: registrar aqui só se virar regra em vigor ou pergunta aberta; o resto vai para o histórico.
