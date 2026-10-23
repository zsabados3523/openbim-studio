<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_77: revisão do ADR-004 com os números do V1 (PR 271, cartão F0-S04-T19)
- Revisor: opus (médio), contexto fechado; não escreveu o texto revisto. Data: 2026-10-23.
- Lido: diff do ramo `s04-t19-adr004` contra `main` (ADR-004 e LOG); `reports/F0-S04-V1.md`, `reports/F0-S04-T07c.md`, `cards/F0-S04/F0-S04-T07e.md`, `cards/F1-D3D11-dispositivo-unico.md`, `LOG.md` (linhas de 2026-10-21 a 2026-10-23); `reports/F0-S04-M1F.md` (ramo `s04-m1f-relatorio`, PR 273, aberto); `docs/acceptance/S04-medicao-oficial.md` (busca por N1 a N4).

## Veredito: REPROVADO (2 correções só de texto; números sem divergência)

### Conferência dos números (pedido 1)
1. V1m, Linux local, placa e Windows: todos os valores, limites e margens da tabela do §5.1 batem com `F0-S04-V1.md` (3_parede, 4_controle_1s, 4_controle_forma2, 4_mouse_forma2, 4_surda, 5_m5_*, 6_longo; leitura da pesada do Windows 5,9/2,6/10,0, 258,7/293,3/307,0, 26,5/26,0/31,5, malha 289,46). Nenhuma divergência.
2. V1b (1.018 / 1.082 com mouse; 984 / 985 controle; `spatial.assign_container`) e V1c (165,5 / 176,7; controle 92,5 / 93,7; pesada 19,2 / -32,3 / 113,5 contra 106,0 e 1.000; lote 124,59 contra 124,25, 0,3%; 13,77 contra 14,39; 127,9; 16,6 a 16,8; fatia 119 a 130, antes 639 a 668): batem com o relatório e com o LOG. Commits 7960f51 (PR 250) e 60c9106 (PR 261) conferidos no `main`.
3. WARP: 1 em 112 (T07c §2), 1 em 300 (T07c §7, LOG 2026-10-22), PR 262 mesclado (b290531 no `main`), pilha `~QRhi` → `d3d10warp`, trava global, decisão do PO de 2026-10-22 e aceite de 1.000 voltas do F1-D3D11: batem. Lote 72 "sem divergência nas 3 máquinas": bate com o LOG.
4. Resumo ao PO, linhas 1 a 4: "18,6 a 26,5 contra 102 a 145", "cerca de 0,17 s", "1% a 4%", "0,3% aceito em 23/10", "1 vez em 300": corretos.

### Status e decisões (pedidos 2 e 3)
5. Nada diz "aceito" como estado atual; Status, §5.1, §6 e §8 dizem "validada pelo V1; aguarda aprovação do PO". Ok.
6. Nenhuma meta afrouxada; nenhuma decisão do PO inventada (as três citadas, 2026-10-22 V1c, 2026-10-22 T07e/F1 e 2026-10-23 ruído, estão no LOG). Ressalvas presentes: margens de 1,0% a 4,3% (e 16,9% no Windows), 0,3% aceito como ruído, V1c só no Linux em tela virtual, Windows só informativo, risco do WARP aberto até o F1-D3D11. Ok.

### Correções obrigatórias (texto)
7. **Resumo ao PO, linha 5**, diz que N1 a N4 "esperam a medição final na sua placa". Errado: o roteiro `S04-medicao-oficial.md` não mede N1 a N4, e a M1F (rodada em 2026-10-23) diz que eles "seguem sem medida". Trocar por algo como: "seguem sem medida; a medição final na placa não os mede; dependem de cartões próprios (T04b e os que usam 2B/2C)".
8. **§2, "Situação em 2026-10-23"**, diz que a M1F "ainda vai acontecer; até lá nenhum número N1 a N4 entra". Corrigir para: a M1F foi feita em 2026-10-23 (`reports/F0-S04-M1F.md`, PR 273) e não mede N1 a N4; eles continuam condição dos cartões que dependem deles (como já está no §8). Mesmo ajuste na linha nova do LOG ("M1F por fazer").

### Sugestões da M1F (pedido 4; não bloqueiam)
9. §2.1 / §6: forma 2 na placa depois do V1c, controle 70 a 124 ms (antes 698 a 765) e M5b mediana 12,5 a 13,7 ms; a mista não foi medida na M1F, então "na placa os números da mista são de antes da divisão" continua verdadeiro; vale dizer isso com a fonte.
10. §5.1 / §8: forma 1 na placa segue com pulso 1.148 a 1.604 ms (surda > 1 s) e a parede pesada na forma 2 fica em 200,7 a 205,3 ms contra o portão de 102,4: reforça por que a 4A não é volta automática e por que a mista usa a forma 1 na geometria.
11. §9, gatilho de memória: a M1F mediu o pesado com bloco 1.000 em **6.354 MB** (acima de 6.000) e com bloco 250 em **5.858 MB** (abaixo). O gatilho "acima de 6.000 MB em qualquer abertura oficial nova" fica ambíguo; deixar claro que vale para a configuração final (bloco 250 com 1 reinício planejado) e registrar o 6.354 do bloco 1.000 como esperado.
12. §2.1: M2b em IFC real agora atingido (49,6 ms no detalhado, antes 6.749; 48,9 no `casa25`, antes 399); M5 17,3 ms; abertura do pesado 52,2 s; 8 fios. Só se o ADR quiser a linha "M1F" ao lado da S04.
13. §10: a M1F confirma `exec` soltando o bloqueio em `ifcopenshell.open` e não em `file.write` (igual ao §2.1); pode citar como reconfirmado.

### Resumo para o PO (pedido 5; 5 linhas)
1. O texto da decisão sobre as linhas de trabalho do programa está com os números certos: conferi um por um contra as medições, sem diferença.
2. Ele não diz que a decisão está aprovada; diz que passou no teste e espera o seu ok, e conta as folgas pequenas, o 0,3% que você aceitou e o risco no Windows sem placa.
3. Há um erro de texto: ele diz que quatro números antigos serão medidos na medição final da placa, mas essa medição já foi feita hoje e não mede esses quatro.
4. Pedi para corrigir essa frase em dois lugares; depois disso o texto pode ir para você aprovar.
5. Sugeri também acrescentar os números novos da medição de hoje, como a memória do arquivo pesado (5,86 GB na configuração final), mas isso não impede a aprovação.

## Rodada 2 (2026-10-23; ramo em ec1edc3; ADR-004 em f8ec6b9, ADR-001 em ec1edc3)
Lido: diff de eaf3d0d a ec1edc3 (ADR-004, ADR-001, LOG); `reports/F0-S04-M1F.md` (origin/s04-m1f-relatorio), `reports/F0-S04-T23d.md`, `F0-S04-V1.md`; LOG e cartões em origin/main e origin/s04-t23d-registro.

### Veredito: APROVADO, com uma condição de ordem de merge (item 6)
1. ADR-004, itens 7 e 8: corrigidos (resumo, linha 5, e §2 "Situação em 2026-10-23"); a linha do LOG não diz mais "M1F por fazer". Ok.
2. ADR-004, sugestões 9 a 13: entraram, com números iguais aos da M1F (forma 2 controle 70 a 124, antes 698 a 765; M5b 12,5 a 13,7; forma 1 1.148 / 1.507 / 1.604; parede 204,8 / 102,4 / 200,7 a 205,3; M2b 49,6 e 48,9, antes 6.749 e 399; M5 17,3; pesado bloco 250 52,2 s, 5.858 (pior 5.859), 61,7 ms; bloco 1.000 6.354; 8 fios; `exec` em `open` e não em `write`). O gatilho de memória do §9 agora fala da configuração final. Ok.
3. ADR-001, §3.1 a §3.3: todos os números batem com a M1F (M2 a M7, M6 4,02, M7 1.407 / 1.170 / 1.278; passo 9: 49,7 / 49,6, 1,4, 2,71 / 2,61, 17,6 / 16,8; abertura: 52,5 / 52,2 / 52,5, 5.859 / 5.858 / 5.821, 6.337 a 6.358, simples 1,80 s / 968 MB, detalhado 23,4 s / 5.011 MB). O pior pico de 5.958 MB (folga de 42 MB) também confere.
4. ADR-001, §3.4 e A6: 11:58 de mediana (pior 12:16) em 3 rodadas, 11 partes, antes 17:48: bate com o T23d. A5 (165,5 e 176,7) bate com o V1c.
5. Status e §7: nada diz "aceito" ("aguarda aprovação do PO"). A1 FEITA está correto. A2 continua ABERTO, e com razão: a M1F só rodou o bloco 250 no pesado. Nenhuma meta foi afrouxada; a de 10 min continua "não atingida".
6. **Condição:** o ADR-001 cita a decisão do PO de aceitar cerca de 12 min (2026-10-23) e o cartão `F1-CI-cadeia-instalador.md`, mas os dois só existem no ramo `s04-t23d-registro`; não estão no `main` nem no PR 271. A decisão é real (está no LOG desse ramo), não foi inventada. O ramo `s04-t23d-registro` precisa entrar no `main` antes do PR 271, senão a referência fica quebrada.
7. Sugestão: o §3.4 dá 17:08 como mediana do T23 e o A6 dá "antes 17:48", que é a base do T23d. As duas fontes estão certas, mas medem coisas diferentes; uma frase curta explicaria a diferença.
8. Sugestão: a linha 3 do resumo diz "passou em tudo". Melhor "passou em todas as metas", porque o bloco 1.000 deu 6,35 GB (esperado) e o M3 teve um máximo de 64,5 ms (a meta vale para o p95).
9. Sugestão: o A5 pode citar o M5 em IFC real da M1F (17,6 e 16,8 ms; não é durante operação longa).
10. Cosmético (ADR-004 §10): a linha "Reconfirmado, sai da dúvida" está dentro da lista "Não verificado"; ficaria melhor tirá-la de lá ou mudá-la para o §2.1.

### Resumo do ADR-001 para o PO (5 linhas)
1. A estrutura do programa continua como você decidiu: janelas e comandos em Python, desenho 3D e cálculo das peças em C++.
2. A medição final na sua placa (23/10) passou em todas as metas: trocar uma parede nos seus arquivos reais leva cerca de 50 milésimos de segundo (meta 200; antes chegava a quase 7 segundos).
3. O arquivo pesado abriu em 52 segundos com 5,86 gigabytes (meta 6,0); o pior caso já visto foi 5,96, então a folga é pequena e precisa de vigilância.
4. O teste automático do Windows caiu de 18 para cerca de 12 minutos; você aceitou esse tempo em 23/10, e a meta de 10 minutos ficou para a fase 1.
5. Ainda falta medir os arquivos simples e detalhado na configuração nova de memória e testar no Windows com placa de vídeo de verdade; o texto aguarda a sua aprovação.
