# Perguntas e decisões do PO

> Duas partes: **Regras em vigor** (curta; o que vale hoje) e **Abertas** (o que espera o PO). O histórico de respostas está em `arquivo/PO-historico.md`. Cada pergunta traz a recomendação do líder. Sem resposta, vale a recomendação como decisão assumida, registrada aqui. Atualizado: 2026-10-18.

## Regras em vigor (2026-10-14)
- **Opus:** abrir sessão só com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9). A exceção de cota de 13/10 **encerrou** em 14/10 09:00Z. Quem abre: o líder, como subagente, conforme o `CLAUDE.md` item 6. **Exceção de 2026-10-15 (PO):** lotes 29, 30 e 31 podem abrir sem checar o uso, só desta vez.
- **S04 retomada (2026-10-15):** a pausa da D1 acabou; o PO mandou retomar a S04 no dia 2026-10-15 (confirmado por ele no chat em 2026-10-18).
- **Cota (decisão do PO, 2026-10-18, no chat):** o PO usou a redefinição de limite em 2026-10-17 (~20h); a nota "piso de 25% atingido, sem lote Opus até 21/10" foi superada. Valem a regra de abertura do Opus (semanal acima de 25% restante, janela abaixo de 70%) e a autorização do PO. Números em `QUOTA.md`.
- **Esforço dos subagentes (decisão do PO, 2026-10-18, no chat):** sonnet e opus passam a rodar em esforço médio (antes: alto no sonnet), pois o alto estourava a janela de 5 h; haiku no padrão. `CLAUDE.md` item 7.
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
| A1 | (Feita em 2026-10-17: ver a decisão abaixo.) | — |
| A2 | ADR-001 e ADR-004 com números (cartão T19) e a nota sobre a interface `atualizar(lote_novo, guids_remover)` | Decidir ao fim da S04, com a medição do critério de custo de manutenção (P6) |
| A3 | Travar o ambiente do instalador (`packaging/runtime-environment.yml`) pela mesma trava `.lock` | Sim |
| A4 | Aplicar ao AppImage o mesmo critério do instalador (roda só quando o empacotamento muda) | Sim, depois de ver o PR 91 funcionando |
| A5 | Se os testes de tempo do Windows continuarem a oscilar: dar folga aos limites (muda metas) | Preferir medir pela mediana de várias rodadas; folga só com a meta original registrada (D8) |
| A6 | Quando e a quem enviar o convite de revisão externa; wireframes da S09; 8 testes no Revit | Decidir depois das revisões S01 a S03 |
| A9 | Confirmar que as exceções de ausência acabaram | Sim |
| A10 | Passar os números do `/usage` de 13 e 14/10 para `QUOTA.md` | Informar janela e semana, antes e depois |
| A11 | D5: nomes dos colegas de estágio para testar e momento | Sem prazo; combinar antes da F1 |
| A16 | (Respondida em 2026-10-17: ver a decisão abaixo.) | — |
| A17 | (Respondida em 2026-10-17: ver a decisão abaixo.) | — |
| A18 | (Respondida em 2026-10-17: ver a decisão abaixo.) | — |
| A15 | SINAPI: o PO informou (2026-10-15) que o uso gratuito é permitido, mas software que automatiza processos ou buscas precisa de autorização da CAIXA. Confirmar o texto e pedir a autorização formal | Consulta formal à CAIXA como requisito da F5; texto fica em `docs/research/2026-10-10-sinapi-termos.md` |
| A19 | Lote 57: liberar o arquivo pesado para os testes T1-1, T1-2 e T1-3 (tela virtual, 15 a 20 min de máquina parada, numa só sessão), e na mesma sessão o simples, o detalhado (só para conferir que nada piora) e o de 25 MB (só para contar lotes)? O detalhado não abre em tela virtual: a conferência dele e a contagem dos lotes dele ficam para a sessão na placa real. Qual horário? **Aguarda PO.** | Opus: sim, todos, na mesma sessão |
| A20 | Lote 57: autoriza rodar primeiro os testes baratos e só escolher a opção depois? **Aguarda PO.** | Opus: sim; hoje nenhuma opção tem número que mostre que fecha a meta |
| A21 | Lote 57: o orçamento por quadro da tela (2 MiB e 4 ms, que protegem o ritmo dos quadros) conta como "limite existente" pela sua regra? **Aguarda PO.** | Opus: sim, conta; com isso a opção 2-B só entra com o seu ok |
| A22 | Lote 57: opções C (mudar a forma de medir), D (mudar a meta por tamanho de cena) e E (aceitar e registrar o M2b como não atingido): considerar agora? **Aguarda PO.** | Opus: não decidir agora; esperar o teste sintético T2-0 e a opção 2-A (e não recomenda nenhuma das três) |
| A23 | Lote 57: a medida da memória no Windows continua no T28, como hoje? **Aguarda PO.** | Opus: sim; a opção escolhida tem de funcionar pelo desenho nos dois sistemas, o que favorece a 1-B sobre a 1-A |

- **Entrevista S09 (A13), aceita pelo PO em 2026-10-15,** com um ajuste: depois dos eixos vem a estrutura, e as paredes não precisam ficar presas a eixos; a ordem do fluxo é hábito, não obrigação. Wireframes podem começar quando o PO mandar as imagens.
- **IFC real do PO (D4), 2026-10-15:** o PO quer usar um IFC real dele nos testes. Fica fora do repositório (`../openbim-studio-referencia/`); só abrir quando o PO listar o arquivo no chat.

- **Regras de parada da T15 (2026-10-16):** (a) janela surda por mais de 1 s no lote de 1.000 paredes nas duas formas (medida no controle) e (b) parede com 150 aberturas parando a janela mais da metade do tempo do cálculo do desenho = parar e levar ao PO. Resultado da T15d: nenhuma disparou; a escolha entre as formas é apertada (relatório `reports/F0-S04-threads.md`).
- **Atribuição nos commits e pedidos (2026-10-16):** manter `Co-Authored-By` do Claude nos commits; pedidos sem "Generated with Claude Code". Títulos de pedido: `F0-S04-T15c: o que faz`.
- **Entrevista com o PO (grill-me) para toda feature nova ou dúvida de comportamento (2026-10-15/16),** não para correções internas.
- **A7 respondida (2026-10-17):** o PO deu o ok e o ambiente local ganhou `zlib` 1.3.2 e `libxml2-devel` 2.15.4 (versões da trava); a compilação do fluxo B na máquina do PO funciona. Pendência fechada.
- **IFC do PO e carga pesada (2026-10-17):** o PO liberou os 3 IFC dele e o de 25 MB (fora do repositório, `../openbim-studio-referencia/`) para o ensaio da medição oficial e permitiu rodar a carga pesada. O ensaio rodou só em tela virtual; só números, nunca nomes de peças, entram nos relatórios.
- **Rodada oficial na tela real do Linux (A1), feita em 2026-10-17** (18:25 a 19:04, RTX 3070): números em `reports/F0-S04.md`. Decisões do PO no chat, no mesmo dia: manter as metas e as réguas rigorosas, não afrouxar nada; (1) memória do arquivo pesado acima de 6,0 GB (6,84 GB): manter a meta, registrar o número e abrir cartão para reduzir (T21, etapa 1 do T20); (2) M2b em IFC real acima de 200 ms (399 ms e 6.749 ms): abrir cartão de análise do que pesa no quadro com modelos reais, antes de mexer em meta ou régua (T22); (3) forma 2 reprova a parede de 150 aberturas: reforça a forma 1 (thread à parte), decisão formal no T19 (ADR-001 e ADR-004); (4) sem capturas das threads e da parede, não refazer. Abertas: A16 a A18 e a decisão do T19.
- **A16, A17 e A18 respondidas (2026-10-17), todas com a recomendação do líder:** (A16) manter a meta de 10 min do build incremental do Windows, sem folga, e abrir cartão para encurtar: `F0-S04-T23`, rascunho em `cards/F0-S04/` com 3 perguntas suas (como contar os 10 min; Linux em cartão irmão; o que fazer se o CI sozinho parar em 15 a 17 min); (A17) T21 primeiro (o pesado) e T22 em paralelo (o simples, o detalhado e o de 25 MB), ambos T2 de só medir e analisar; (A18) roteiro de aceite da S04 escrito depois da decisão do T19.

- **A corrigir nos relatórios (lote 57, 2026-10-18; nada foi corrigido ainda).** O Opus achou 10 contradições nos cartões e relatórios do T20, T21 e T22 (texto completo em `lotes/LOTE_OPUS_57/resultado.md` §1): (1) cartão T20: "causa conhecida" (peça leva o filho a 3,9 GB) deve passar a hipótese; (2) cartão T20: a fase 1 está como T1 mas é TA; (3) T21 §5 pode não valer para o carregador (passe e carregador com contagens de triângulos e peças diferentes; configuração do passe talvez diferente do `_converter`); (4) a mesma peça aparece com dois tempos (11,5 s no ADR-004 e 15,1 s no T21), por métodos diferentes; (5) o limite de 20 s do carregador mede silêncio do filho, não o tempo de cada peça (explica por que só atuou com 1 fio); (6) T22: a previsão da sintética de 41.600 está errada (25 quadros vistos contra 25,2 previstos é impossível com 2 MiB por quadro; a coluna "previsto" deve usar só vértices e índices); (7) a tela tem dois limites por quadro (2 MiB e 4 ms), e o T22 cita só o primeiro; (8) o pai usa cerca de 960 MB na placa e 1.019 a 1.093 MB em software; (9) o `LOTE_OPUS_56/resultado.md` não tem a linha de licença que o pedido exige; (10) o cartão T20 cita o T12, que não estava no contexto do lote.

## Histórico
Todas as respostas e decisões anteriores do PO (2026-10-10 a 2026-10-15) estão em `arquivo/PO-historico.md`. Resposta nova: registrar aqui só se virar regra em vigor ou pergunta aberta; o resto vai para o histórico.
