<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_58: especificação da 1-B com bloco 250 (memória do arquivo pesado) e da troca de geometria abaixo de 200 ms no detalhado (F0-S04-T20 e T22)
Pedido do líder (2026-10-18), **classe TA (planejamento), esforço médio. O Opus especifica; ninguém implementa neste lote.** Módulo: viewport e ponte, S04. Escreva só `docs/state/lotes/LOTE_OPUS_58/resultado.md`; não edite nenhum outro arquivo, **não escolha a opção pelo PO e não implemente**. Pergunte ao PO, em lista, o que for ambiguidade; não invente.

## Regra do PO (2026-10-17): padrão rigoroso
Nenhuma opção pode afrouxar meta, régua, limite ou teste existente (metas de `v2/03` S03/S04, juiz de metas, `limite_peca_s`, 60 s, 6,0 GB, 200 ms, M5). **O orçamento por quadro da tela (2 MiB e 4 ms, `ORCAMENTO_BYTES` e `ORCAMENTO_TEMPO`) é limite existente (PO, 2026-10-18, A21): mudar só com ok do PO**, e só aparece como "decisão do PO" com o impacto. Opção que só passa porque uma peça deixou de ser desenhada, uma caixa substituiu a malha ou a saída mudou não vale. Mudar métrica ou meta (opções C, D, E do lote 57) está fora de pauta (PO, 2026-10-18).

## Contexto fechado (só leitura; nada fora desta lista)
Relatórios: `docs/state/reports/F0-S04-T24.md` (inclui §13, tela real), `docs/state/reports/F0-S04-T25.md` (inclui §9, 25 MB em tela virtual, e §10, tela real), `docs/state/reports/F0-S04-T21.md`, `docs/state/reports/F0-S04-T22.md`, `docs/state/lotes/LOTE_OPUS_57/resultado.md`. Código: `prototypes/s04/obimcore/nucleo/motor.h` (`ORCAMENTO_BYTES`, `enviar`), `prototypes/viewport_qrhi/carregador.py`, `prototypes/viewport_qrhi/processo_malhas.py`. **Dados do PO (IFC) não entram no contexto**: só os números dos relatórios; não abra `../openbim-studio-referencia/`. Nenhum nome de peça ou arquivo do PO existe nos relatórios; não procure.

## Padrão de evidência (lição das reprovações anteriores)
Toda causa vem com número. Hipótese vem marcada "hipótese" com o teste que a confirma. Estimativa vem marcada "estimativa". Não invente ganho. Windows não foi medido (T28): diga o que vale só pelo desenho.

## Item 1: especificar a implementação T3 da 1-B com bloco 250 (memória do arquivo pesado)
Fato novo (tela real, 2026-10-18, `reports/F0-S04-T24.md` §13): 1-B com bloco 250 (filho novo antes do bloco 22) deu pico somado 5.867 / 5.894 MB (mediana / pior; **abaixo de 6.000 nas 3 rodadas**) e 52,3 / 52,7 s (dentro de 60 s). Controles: normal bloco 250 6.176 / 6.327 MB; normal bloco 1.000 6.713 / 6.809 MB; 1-B bloco 1.000 6.345 / 6.395 MB (todos acima). Em tela virtual a mesma configuração deu 5.970 / 6.022 MB e 60,6 s (não cumpria).
O que o especificador tem de tratar:
1. **O que muda no produto** (`carregador.py`, `processo_malhas.py`, ponte): bloco padrão de 1.000 para 250 e o reinício do filho antes do bloco que contém as peças pesadas. **Como o produto sabe qual é o bloco do reinício** sem conhecer o arquivo de antemão (a sonda usou a posição medida: bloco 22 de 250). Opções de regra (por exemplo, por número de triângulos acumulados, por memória do filho, por contagem de blocos), cada uma com o que os números permitem afirmar e o que não.
2. **Folga:** 106 MB na pior rodada (1,8% da meta) e 7,3 a 7,7 s no tempo. Dispersão entre dias já vista de cerca de 0,1 GB. Que margem de segurança o desenho pode criar **sem afrouxar a meta** (a meta continua 6.000 MB e 60 s, pela pior rodada).
3. **Saída não é byte a byte igual** (T24 §5 e §13): nem duas aberturas normais coincidem (`hash_fluxo`). **O oráculo tem de ser por peça** (por exemplo, triângulos por peça, caixa com tolerância, contagens), não byte a byte. As duas peças com **224.439 triângulos no carregador (8 fios) contra 335.655 no passe do T21 (1 fio)** (T24 §4, causa em hipótese: fios): como o oráculo trata isso, e qual teste separa a causa.
4. **Limite de 20 s por peça (`limite_peca_s`):** ele mede o **silêncio do filho** entre mensagens, não o tempo de cada peça (lote 57, achado 5). Folga medida em tela virtual de 3,6 a 6,7 s no bloco pesado; na tela real, o maior silêncio não foi medido. Como o reinício e o bloco 250 mudam isso; que medida falta.
5. **Windows (T28) não medido:** a 1-B funciona nos dois sistemas só pelo desenho (processo novo devolve a memória ao terminar); diga o que o T28 tem de medir.
6. **Threads (ADR-004), M5, saída igual do T12:** o que a mudança pode quebrar e o teste que prova que não.
7. Cartões de ≤ 400 linhas (diff máximo do projeto), classe (T3: revisão Opus em lote, oráculo por outro agente), **oráculo proposto** (quem escreve, o que verifica), **teste mínimo barato antes de investir** (diga se precisa de arquivo do PO, ok e horário, ou se roda sintético em tela virtual), riscos.

## Item 2: especificar como a troca de geometria chega a menos de 200 ms no detalhado (M2b)
Fato novo (tela real, 2026-10-18, `reports/F0-S04-T25.md` §10): o detalhado abre com 13 lotes, 11 acima de 2 MiB, soma 805,7 MiB (maior 285,4 MiB); as 422 paredes estão só em dois lotes (**24,24 MiB com 244 paredes e 68,27 MiB com 178**). A troca de comprimento levou 404 quadros e cerca de 6,8 s (6.775 ms mediana), com pedaços iguais ao reenvio forçado da cena inteira (razão 1,000 em 120 de 120 pares) e a placa chegando a 0 triângulos. O tamanho do lote tocado não mudou o tempo que se vê (404 quadros mesmo com lote de 1.152 bytes). No 25 MB: 413 / 443 ms e 24 quadros (T22: 399 ms).
**Conta (estimativa, não medida; `reports/F0-S04-T25.md` §10.4):** reenviar só o lote tocado de 24,24 MiB a 2 MiB por quadro leva cerca de 12,1 quadros, cerca de 202 ms a 16,7 ms por quadro (196 ms a 16,2 ms); o de 68,27 MiB, cerca de 34 quadros, cerca de 570 ms. **A 2-A sozinha (reenviar só o lote tocado) não chega a 200 ms por essa conta.** O Opus deve conferir a conta e dizer se ela está certa e o que ela deixa de fora (o quadro a mais visto em todos os tamanhos, o lote novo, o limite de 4 ms).
O que o especificador tem de tratar:
1. **Opções que chegam a menos de 200 ms sem mudar o orçamento de 2 MiB e 4 ms:** 2-G (esconder a peça antiga e mandar só a faixa de índices/lote novo), lotes menores no carregador, faixa de índices por peça, e qualquer outra que o Opus ache (inclusive outras formas de "não limpar a placa"). Para cada uma: o que muda e a classe, o que cada número permite afirmar e o que NÃO permite, risco (M5, saída igual, T12, threads do ADR-004, Windows), custo em cartões de ≤ 400 linhas, **teste mínimo barato antes de investir**, oráculo proposto (outro agente escreve).
2. **2-B (subir o orçamento):** só como "decisão do PO" com o impacto no M5 e no ritmo dos quadros; sem recomendação para fechar a tarefa.
3. **Por lote tocado:** o que cada opção faz com lote de 24 MiB e com lote de 68 MiB (e com o de 285 MiB, que não tem parede mas pode ter em outro arquivo).
4. **O que a sonda T25 não mede** e que o teste barato precisa medir (início e fim do envio por quadro dentro do C++; bytes por quadro; lote escolhido; parede em lote de outro tamanho; mover, apagar e desfazer).
5. Quais testes baratos valem para os dois itens (arquivo do PO só com ok e horário dele; sintético em tela virtual quando bastar).

## O que o Opus entrega no `resultado.md`
1. Por item, a especificação pedida, **2 a 3 opções** onde houver escolha, cada uma com os campos acima, **uma recomendação por item** (o PO decide) e o que NÃO vale.
2. **Erros e contradições** que achar nos relatórios T24, T25, T21 e T22 (como no lote 57).
3. **Ordem sugerida entre os itens** e se algum teste barato serve aos dois.
4. **Lista de perguntas ao PO** (só o que é decisão dele).
5. **Resumo de 5 linhas em português simples, sem siglas**, para o PO escolher.
6. O que registrar no LOG.
O Opus não escolhe a opção pelo PO e não implementa; não revisa o que ele mesmo escreveu em tarefa (oráculo e implementação seguem em subagentes diferentes).
