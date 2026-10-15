<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Lote Opus 31: revisão da S03 (resultado)
Data: 2026-10-15 · Revisor: Opus (contexto fechado; não escreveu nada da S03 nem da revisão) · Pedido: `docs/state/LOTE_OPUS_31.md`
Lido: `reports/F0-S03-revisao.md`, `reports/F0-S03.md`, `reports/F0-S03-T08.md`, `reports/F0-S03-T08-D.md`, `v2/03` (F0-S03), `PROPOSTA_REVISAO_F0.md` §2, §3 e §3.3, `cards/F0-S03-T28.md`. Para conferir as citações da revisão, abri só os trechos que ela cita (`tests/test_viewport_selecao.py:240`, `processo_malhas.py:320`, `ci.yml`, `medir.py`) e procurei os números em `LOG.md` e `PO.md`.

## Resumo
Os cinco itens estão **REPROVADOS**, todos por falhas de texto e de citação, não de código nem de medida. A revisão é honesta: mostra as três metas não atingidas e não esconde nada. Mas cita a fonte errada para os números da placa real, deixa de fora parte do que `v2/03` pede, dá como aprovada pelo PO uma exceção que ele ainda não aprovou e esquece uma pendência (memória final na S04). O cartão T28 não garante que a medição no Windows use mesmo a placa real. Tudo cabe numa correção pequena (um cartão R4 com menos de 150 linhas, só texto), sem reabrir código.

## Item 1. R1, seção 1 (os 7 critérios e as evidências): REPROVADO
1. `F0-S03-revisao.md:17`, `:18`, `:20` e `:23`: os números da placa real (36,6 s, 60 FPS, 6,2 e 6,8 GB, 62 ms) são atribuídos a `F0-S03.md` e `F0-S03-T08-D.md`. A T08-D não tem nenhum deles (dá 44,7 s e 6.933 MB em desenho por software, linha 25); a T08 dá 42 s e 312 ms. A fonte primária é `LOG.md:97` (e `PO.md:101`). Correção: citar `LOG.md:97` em cada uma dessas linhas e dizer "execução única na tela real, Linux, placa real, 8 fios, bloco 1.000". Melhor ainda: gravar a linha JSON de `medir.py` daquela execução num relatório (`reports/F0-S03-T08-D.md`, seção nova "Medida na tela real") para a evidência não depender só do LOG.
2. `F0-S03-revisao.md:17` e `:18`: registrar que foi **uma só execução**. Pela regra do §3 passo 1 a evidência existe, mas é fraca; anotar "1 execução" na coluna Evidência.
3. `F0-S03-revisao.md:15-23`: faltam os pedidos de `v2/03` (linha 34) que não estão na tabela de metas, mas são do aceite da fatia: (a) desenho por D3D11 no Windows e Vulkan ou OpenGL no Linux; (b) QRhi isolado atrás de interface própria e versão do Qt fixada; (c) leitura de geometria pelo iterador multithread do IfcOpenShell; (d) orbitar, arrastar e aproximar. Acrescentar uma linha para cada, com evidência (arquivo e linha, ou relatório do lote Opus que aprovou), ou "não atendido" se não houver.
4. `F0-S03-revisao.md:19`: a seleção medida é por **caixas** (desde a T08-D o pai não guarda triângulos; ver cartão T06b, atualização de 2026-10-12). Escrever "seleção por caixa, precisão de triângulo na S04 (T10)" na evidência, para o 7 a 12 ms não parecer seleção por triângulo.
5. `F0-S03-revisao.md:20`: o 6,2 GB "maior soma" está no limite e acima da meta; manter "Não atingida" (está certo), e acrescentar que em desenho por software o mesmo padrão dá 6,9 GB (T08-D:25), para mostrar a faixa.

## Item 2. R1, seção 2 (as três exceções): REPROVADO
1. `F0-S03-revisao.md:30` (E3), coluna "Quem aprovou": "o PO viu na revisão" não é aprovação, e a pergunta (c) ainda está sem resposta. Trocar por "Líder, 2026-10-12 (`LOG.md:108`), tarefa T2; **aprovação do PO pendente (pergunta c)**".
2. `F0-S03-revisao.md:30` (E3): a meta de 16 ms vinha do cartão T06b, mas o cartão não foi atualizado com a troca. Acrescentar nota de atualização em `cards/F0-S03-T06b.md` (linha 5, mesmo formato das outras) dizendo "limite do teste: 100 ms desde 2026-10-12; 16 ms vira meta de acompanhamento (E3)".
3. `F0-S03-revisao.md:28` (E1), coluna "Medido": dizer de onde vem cada número: 6,2 GB e 6,8 GB = placa real (`LOG.md:97`); 6,9 GB = software (T08-D:25); 833 MB = 1 milhão de triângulos (`LOG.md:87`).
4. `F0-S03-revisao.md:28` (E1), coluna "Motivo": está incompleto. A T08-D (linhas 10 e 11) mostra que o motivo principal é **uma peça só** (a mobília MOB_CAF_001 leva o filho a 3,9 GB) e que 6 GB só sai com 1 ou 2 fios, acima de 60 s. Escrever isso; "soma do filho com o pai" sozinho engana.
5. `F0-S03-revisao.md:29` (E2): conferir se `PO.md` tem a resposta do PO de 2026-10-12 ao "atingido no Linux, provado em software no Windows" e citar a linha. Se não tiver, registrar lá (o PO decidiu; só falta escrever).

## Item 3. R2, seção 3 (destino das pendências e proposta do teste de tempo): REPROVADO
1. `F0-S03-revisao.md:34-43`: falta a pendência **"valor final da memória na S04"** (`F0-S03.md:21`, ponto 2). Acrescentar linha com cartão (qual cartão da S04 decide), dono e data. Hoje só aparece dentro da E1, sem dono.
2. `F0-S03-revisao.md:38` (T27): o §3 passo 2 pede data e dono. Pôr prazo ("antes do fim da S04" ou data) além do dono.
3. `F0-S03-revisao.md:42` (lote 8 §2.3): `F0-S03.md:23` fala em "iterador por peça, reabertura da janela"; a revisão fala em "iterador por peça, orçamento de peças lentas, seleção por triângulo". Ligar cada item a um cartão (T16, T16b, T10, T27) e citar o relatório que fechou cada um. "Iterador por peça" não tem cartão nomeado.
4. Pendência que não aparece: `F0-S03-T08-D.md:39-40` (placa perdida: lotes liberados não voltam, `lotes_perdidos`). No Windows a troca de tela ou de driver é mais comum. Acrescentar linha com destino "verificar no roteiro T28" e registro do custo.
5. `F0-S03-revisao.md:45` (proposta do teste de tempo): a ideia é boa; especificar para o PO decidir sobre algo concreto: (a) aquecer uma vez, rodar 7 vezes, testar a **mediana** contra 100 ms no CI; (b) imprimir mediana e maior valor no registro do teste, para acompanhar a tendência; (c) 16 ms como aviso só na máquina do PO (Linux), sem falhar; (d) a medição de Windows real fica na T28. Deixar claro que a máquina do PO é Linux e não cobre o Windows.

## Item 4. R2, cartão T28 (cobre o risco do Windows com placa real?): REPROVADO
1. `cards/F0-S03-T28.md:9-10`: falta exigir prova de que a placa real foi usada. Acrescentar critério: o relatório anota o nome da placa, o driver e a linha "RHI backend" (deve ser D3D11, não desenho por software). Sem isso a medição pode cair em software sem ninguém ver.
2. `cards/F0-S03-T28.md:5`: "e, se houver, num com Intel integrada". A meta de `v2/03:42` exige Intel integrada. Acrescentar: "se não houver máquina com Intel integrada, essa parte fica **não atendida** e vai ao PO como exceção, com opções" (ex.: pedir emprestado, máquina de terceiros, aceitar risco).
3. `cards/F0-S03-T28.md:9`: o PO não programa e o benchmark hoje roda com Python do ambiente conda. Instalar o Miniforge no Windows físico é ferramenta nova (pede ok do PO). Escrever no roteiro como o programa chega à máquina (instalador da S02 com `medir.py`, ou ambiente conda com ok do PO), passo a passo.
4. `cards/F0-S03-T28.md:10`: `medir.py` (linhas 171-172) mede abrir, memória, atraso e FPS, mas **não mede a seleção**. Com "sem código novo" (linha 2), a seleção fica sem medida. Escolher: rodar `tests/test_viewport_selecao.py` no Windows físico e anotar, ou permitir uma mudança pequena em `medir.py` (passa a ser T2, com outro arquivo permitido).
5. Acrescentar aos critérios: (a) 3 execuções por máquina, anotar a mediana; (b) memória total da máquina (com 8 GB, 6,9 GB não cabe); (c) os dois modelos: o de 1 milhão de triângulos (o que a meta pede) e o arquivo do PO; (d) cancelar a leitura e conferir que não sobra processo filho (no Windows o processo separado nasce de outro jeito); (e) minimizar, trocar de monitor ou suspender e ver o que acontece (item 3.4 acima).
6. `cards/F0-S03-T28.md:3`: pôr o cartão no `BOARD.md` com prazo (antes do portão da F0) e dono (PO).

## Item 5. R3 (coerência dos documentos e números de teste): REPROVADO
1. `F0-S03-revisao.md:58`: 169 de 332 testes pulam no Linux e 171 no Windows (mais da metade). O §3 passo 4 pede a suíte verde com contagem; precisa também dizer **quais testes da S03 pulam** e por quê (falta de tela, falta do arquivo do PO), e quais rodam no passo de desenho (`ci.yml:93-95` roda só `tests/test_viewport_qrhi.py`). Explicar a diferença de 2 testes entre Linux (163) e Windows (161).
2. `F0-S03-revisao.md:58`: o run citado é do PR 93 de 2026-10-14, antes das correções desta revisão. Citar também o run do `main` depois do merge da revisão.
3. `F0-S03.md:7-14`: o §3.3 pede as exceções no mesmo lugar das metas. Elas foram para uma seção separada (linha 26-27). Na própria tabela: linha 12, coluna Situação, escrever "**não atingida** (exceção E1, aceita pelo PO)"; linha 11, acrescentar "limite do teste 100 ms; ver E3"; linha 14 já diz "parcial" (pôr "E2, cartão T28").
4. `F0-S03.md:13`: a linha "Janela não trava, 62 ms" não diz de onde vem, e `F0-S03-T08.md:12` diz o contrário (312 ms, não atingida). Citar `LOG.md:97` e dizer "tela real; em tela virtual 300 ms".
5. `F0-S03.md:29-30`: "Decisão pedida ao PO" continua escrita como pergunta aberta, mas o PO respondeu em 2026-10-12. Acrescentar a resposta com data.
6. `LOG.md:106` diz "T26b pendente", mas `LOG.md:102` e `BOARD.md:89` dizem FEITA (PR 42). Não reescrever o LOG; acrescentar uma linha de correção.
7. `F0-S03-revisao.md:47-55`: a seção não cita `LOG.md` nem `PO.md`, que o §3 passo 3 manda conferir. Acrescentar as duas linhas (os itens 5.6 e 2.5 acima são os achados).
8. `F0-S03-revisao.md:5`: atualizar o status para "lote Opus 31 feito, reprovado com correções" depois de aplicar.

## O que está certo e fica
- As três metas não atingidas estão ditas com clareza, sem maquiar (E1, E2, E3).
- T08-G conferida no código (`processo_malhas.py:320`); T27 conferida como aberta (`ci.yml` não roda o teste do adaptador).
- O comentário do teste (`tests/test_viewport_selecao.py:240`) diz a troca de 16 para 100 ms e o motivo.
- Não usar a S03 para prever a S04 (seção 6): correto.
