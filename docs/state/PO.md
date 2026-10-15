# Perguntas e decisões do PO

> Três partes: **Regras em vigor** (curta; o que vale hoje), **Abertas** (o que espera o PO) e **Histórico de respostas** (ordem cronológica; só consulta). Cada pergunta traz a recomendação do líder. Sem resposta, vale a recomendação como decisão assumida, registrada aqui. Atualizado: 2026-10-14.

## Regras em vigor (2026-10-14)
- **Opus:** abrir sessão só com semanal acima de 25% restante e janela de 5 h abaixo de 70% (D9). A exceção de cota de 13/10 **encerrou** em 14/10 09:00Z. Quem abre: o líder, como subagente, conforme o `CLAUDE.md` item 6. **Exceção de 2026-10-15 (PO):** lotes 29, 30 e 31 podem abrir sem checar o uso, só desta vez.
- **S04 pausada (D1):** nenhuma T3 nova na S04 (T14c, T15 em diante) até as revisões de S01, S02 e S03 e as respostas D1 a D8. Só terminam PR 83 (T12).
- **Escopo da 1.0 (D3):** versão mínima **inclui detalhes 2D**. DXF e fachadas são candidatos a adiar na sessão de escopo. Prazo de 21 a 42 meses não é recalculado antes da medição da F0.
- **Planos antigos (D2):** estão em `docs/arquivo/`. O `CLAUDE.md` ainda os cita pela raiz; mudar isso exige cartão aprovado pelo PO.
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
| A8 | Ajustar `CLAUDE.md` para os planos em `docs/arquivo/` (cartão de mudança, aprovação do PO) | Cartão T0 pequeno, só trocar os caminhos |
| A9 | Confirmar que as exceções de ausência acabaram | Sim |
| A10 | Passar os números do `/usage` de 13 e 14/10 para `QUOTA.md` | Informar janela e semana, antes e depois |
| A11 | D5: nomes dos colegas de estágio para testar e momento | Sem prazo; combinar antes da F1 |
| A12 | ~~D6~~ **Respondida em 2026-10-15:** o PO aceita o parecer da IA como aceite da S01 | — |
| A16 | ~~S02~~ **Respondida em 2026-10-15:** aceita a S02; build incremental do Windows deve seguir (cartão S02-T25); capturas e GIF substituem o MP4; `appimage` já é obrigatório; T23 entra no plano (cartão F0-PLANO-T01, aguarda aprovação do texto) | — |
| A17 | ~~Texto do F0-PLANO-T01~~ **Aprovado em 2026-10-15** e aplicado em `v2/03` | — |
| A13 | Aceite do resumo da entrevista S09 (`docs/research/2026-10-13-entrevista-s09-resumo.md`) | Ler e aceitar antes dos wireframes |
| A14 | ~~ReportLab~~ **Respondida em 2026-10-15:** PO confirma BSD (pypi.org/project/reportlab); veredito passou a "Sim, com condição" (sem pyRXP) | — |
| A15 | SINAPI: o PO informou (2026-10-15) que o uso gratuito é permitido, mas software que automatiza processos ou buscas precisa de autorização da CAIXA. Confirmar o texto e pedir a autorização formal | Consulta formal à CAIXA como requisito da F5; texto fica em `docs/research/2026-10-10-sinapi-termos.md` |

## Histórico de respostas

### 2026-10-15: exceção de cota do Opus (PO: "Pode executar o opus sem preocupação dessa vez")
O limite está sendo descontado dos créditos de uso do projeto. Vale **para esta vez**: o líder pode abrir os lotes Opus 29, 30 e 31 (revisões de S01, S02 e S03) sem checar semanal e janela. Depois volta a regra de D9. Também: o cartão S02-T25 passa a outro subagente.

### 2026-10-15: plano da T23
Cartão F0-PLANO-T01 aprovado; texto aplicado em `v2/03`.

### 2026-10-15: revisão da S02
Aceita a S02. Seguir a questão do build incremental do Windows (cartão S02-T25, medir primeiro). Capturas e GIF substituem o MP4. `appimage` já é obrigatório no `main`. T23 entra no plano (cartão F0-PLANO-T01).

### 2026-10-15: revisão da S01
1. Aceita o parecer da IA sobre a tabela de licenças (aceite da S01; D6 cumprida).
2. SINAPI: uso gratuito do banco de dados, mas automação (busca, processos em software) exige autorização da CAIXA. Registrado na ficha; vira requisito da F5.
3. ReportLab é BSD (PyPI). Aplicado na tabela: "Sim, com condição" (sem pyRXP).
4. Uso do Opus: o PO informa que o uso está parado por enquanto porque o projeto está gastando os créditos iniciais; **sem percentuais**. Lote 29 segue na fila.

### Perguntas iniciais P1 a P7 (todas respondidas em 2026-10-10)

| # | Pergunta | Recomendação do líder | Resposta do PO |
|---|---|---|---|
| P1 | Quais os percentuais de `/usage` (janela de 5 h e semana), antes e depois desta sessão, para a primeira linha de QUOTA.md? | Informar os quatro números; se não anotou o "antes", informar só o "depois" | 2026-10-10: janela 22%→29%; semana 2%→3% (registrado em QUOTA.md) |
| P2 | Licença AGPL v3 "somente" ou "ou qualquer versão posterior"? (06 diz só "AGPL v3"; o texto vai nos cabeçalhos dos arquivos) | "Ou posterior" (AGPL-3.0-or-later): é o padrão recomendado pela FSF e mais flexível. O ADR-009 confirma | 2026-10-10: **ou posterior** (AGPL-3.0-or-later) |
| P3 | Posso ler páginas públicas na internet (arquivos LICENSE, páginas de pacotes) na sessão 2, sem baixar nem instalar nada? | Sim. Download e instalação continuam pedindo ok um a um | 2026-10-10: **sim**; PO pediu haiku para a leitura das páginas. Haiku busca e transcreve; sonnet interpreta e escreve a ficha |
| P4 | Aprova a estrutura de pastas proposta (`app/`, `prototypes/`, `packaging/`, `corpus/`, `tests/`, `docs/`, `.github/workflows/`) e o texto da licença AGPL ficar fora do limite de 400 linhas? | Sim aos dois | 2026-10-10: **aprovado** (estrutura e LICENSE fora do limite de 400) |
| P5 | No app esqueleto da S02, a área da viewport será só um painel reservado (a viewport real é a S03). Ok? | Sim | 2026-10-10: **ok** (painel reservado) |
| P6 | Posso rodar `git init` local na sessão 2? As contas no GitHub e no Codeberg e a criação do repositório vazio são suas; eu guio passo a passo | Sim; criar as contas antes da sessão 2 | 2026-10-10: **git init local autorizado**; contas e repositório remoto ainda a cargo do PO |
| P7 | Qual o hardware da sua máquina Linux e da Windows (CPU, RAM, placa de vídeo, sistema)? (pergunta E de 06) | Informar até a S03; o padrão é 4 núcleos, 16 GB, vídeo integrado recente | 2026-10-10: Linux nativo; Windows via VM. CPU i5-12600KF, GPU RTX 3070, 24 GB RAM |

## Respostas do lote Opus 1 (2026-10-10, confirmadas pelo PO neste chat)
| # | Pergunta | Resposta |
|---|---|---|
| L1 | Aprovar o ADR-009? | **Sim** (aceito) |
| L2 | WiX fora; instalador Windows parte do NSIS? | **Sim** |
| L3 | Cartão novo na S02 (sonda C++) e arquivos gerados fora do limite de 400 linhas (S02-T03, S02-T06)? | **Sim** |
| L4 | Líder ajusta `v2/05` §3? | **Sim** (feito em 2026-10-10; conferência no lote 2) |
| L5 | Páginas de termos do conda-forge e do SINAPI no navegador | Opcional, aberto |

## Decisões já tomadas (06 §1)
10 posicionamento geral, Brasil como primeiro pacote regional (2026-10-10) · 1 corte da 1.0 · 2 Claude Pro, sonnet líder · 3 corpus do PO depois da F0 · 4 PO testa Windows e Linux, Mac melhor esforço · 5 IFC limpo + `.obim` lateral · 6 AGPL v3 · 7 sem gasto extra · 8 par `.ifc` + `.obim` com `.obimpack` para envio · 9 pset `OBIM_Projeto` aceito.

## Padrões assumidos (06 §2, sem resposta ainda)
C hospedagem GitHub + espelho Codeberg · D interface híbrida (confirmar na S09) · F gravação IFC4 e exportação IFC2x3 como critério de portão · G SignPath na v0.3 · H nome provisório "OpenBIM Studio" · I sem IA embutida na 1.0 · J consulta à CAIXA (SINAPI) só na F5.

## Decisões do PO após o lote Opus 2 (2026-10-11)
- Mesa fora do AppImage: manter fora; testar em máquina virtual sem aceleração no roteiro T14 (se não abrir, o Mesa volta).
- Download dos textos oficiais (exceção do OCCT, LGPL-3, LGPL-2.1, GPL-3) para o repositório: autorizado (uma vez, para esses quatro).
- Artefatos do CI: guarda de 7 dias; tratados como builds de teste.
- Build incremental do Windows (~16 min contra meta de 10): **opção 1, aceitar agora e revisitar na S04** (2026-10-11).
- Autorização permanente para ramos de trabalho, PR e merge de T0 a T2 aprovadas: registrada no `CLAUDE.md` (2026-10-11).
- Licenças do Windows (2026-10-11): trocar MKL por OpenBLAS no ambiente de runtime; aceitar `ucrt`, `vc14_runtime` e `vcomp14` (runtimes redistribuíveis da Microsoft) por exceção nomeada e amarrada à versão; incluir `BSD-3-Clause-Clear` na lista de permitidas.

## Decisões do PO após o lote Opus 4 (2026-10-11)
- S03: aceitar que a janela pare pelo tempo de um elemento muito pesado (0,2 s numa parede com 150 aberturas); solução fica para a S04/ADR-004.
- S03: a leitura de v2/03 "tesselação via IfcOpenShell C++" está atendida pelo iterador C++ do IfcOpenShell chamado do Python (sem módulo C++ nosso na S03).
- Modelo grande da S03: sintético por script; IFC real do PO só na T07, com arquivo indicado no chat.

## Decisões do PO após o lote Opus 6 (2026-10-12)
- S03/T08: biblioteca de geometria "híbrida" como padrão da visualização (comparação lado a lado antes de fechar a T08). Limite de 20 s por peça (peça lenta vira caixa laranja). Aprovado.
- T26: passo no job Linux do GitHub que cria a localidade pt_BR, só na máquina descartável. Aprovado.
- Tamanho: exceção aceita para o oráculo da T05 e o relatório da Parte B (>400 linhas).

## Decisões do PO após a T08-D (2026-10-12)
- Meta de memória de 6 GB: aceita "atingida na prática" para o arquivo real de 8,6 milhões de triângulos (maior soma ao mesmo tempo 6,2 GB com placa real; conta conservadora 6,8 GB). O valor final da meta é decidido na S04 com o modelo real e revisão do Opus. Windows: a VM do PO não tem placa real; vale só o teste automático (software) e o roteiro funcional.
- Execução única na tela real autorizada e feita (Linux, placa real): abrir 36,6 s, atraso máximo 62 ms, 60 FPS.

## Decisão do PO após o relatório da S03 (2026-10-12)
- Portão da S03 dado como atingido (Linux com placa real; Windows em software). Risco registrado: placa de vídeo real e Intel integrada no Windows só medidas num computador físico, antes do portão final da F0 (S10).

## Decisões do PO após o lote Opus 9 (2026-10-12)
- Regra do "3 vezes mais lento": o portão do híbrido são as metas absolutas (M1 a M5). A razão contra o C++ puro (M6) é número de acompanhamento, registrado no ADR-001; só pesa se alguma meta absoluta ficar com menos de 2× de folga.
- Ambiente: autorizado acrescentar `zlib`, `libxml2-devel` e `libboost-devel` (conda-forge) e guardar a lista travada de pacotes dos dois sistemas (cartão S04-T01). Qualquer outro pacote pede novo ok.
- Regra do processo: o líder abre o lote Opus como subagente e mescla T3 aprovada com testes verdes (CLAUDE.md, item 6 e 3, editado pelo PO).

## Decisões do PO sobre catálogo de ferramentas e entrevista S09 (2026-10-12)
- "Pode seguir com as recomendações" nas 5 decisões do catálogo (`docs/design/catalogo-ferramentas-f1-f2.md`): telhado e escada na F4 (o plano v2/02 prevalece); pavimento com uma única ação (mudar a cota); manter a meta de 30 s de recuperação com aviso honesto; PO testa à mão os 6 comportamentos antes da F2-S04 e F2-S08; nomes nossos em português ("Modo A/B", cubo de vistas, ajustes salvos).
- Entrevista S09: só anotações (sem áudio). Programa mais usado pelo PO: Revit (já usou ArchiCAD); referência de atalhos e navegação 3D = Revit.

## Exceção de ausência do PO (2026-10-12, pedida no chat)
- O PO vai ficar longe do computador e pediu que o desenvolvimento siga sozinho; "se precisar de autorização, abra esse período como exceção". Valor: o líder segue as próprias recomendações nas decisões que normalmente pediria ao PO, **dentro** da autorização permanente do CLAUDE.md. Continuam do PO e ficam na fila `PO.md` (o líder para essa frente e segue com outra): ADR, meta do portão, escopo, licença, regras do processo e CLAUDE.md, instalar ferramenta nova, baixar arquivo, cota extra, apagar dados, credenciais, `main` direto, execução na tela real, meta de F0 não atingida. Lotes Opus só com uso semanal >25% restante e janela <60%.

## Exceção de ausência do PO (2026-10-13, nova, pedida no chat)
- O PO vai ficar longe de novo (estágio) e pediu que o desenvolvimento siga sozinho, abrindo este período como exceção. Valem as mesmas regras da exceção de 2026-10-12 (acima): o líder segue as próprias recomendações, dentro da autorização permanente do CLAUDE.md; ficam na fila e **param essa frente** (o líder segue com outra) as decisões de ADR, meta do portão, escopo, licença, regras do processo e CLAUDE.md, instalar ferramenta nova, baixar arquivo, cota extra, apagar dados, credenciais, `main` direto, execução na tela real e meta de F0 não atingida. Lotes Opus só com uso semanal >25% restante e janela <60%.
- Perguntas guardadas para a volta: as 6 decisões do catálogo de anotação (`docs/design/catalogo-ferramentas-f3-anotacao.md`, seção 4), partes 2 e 3 da entrevista da S09, desenho de UI do PO (pasta `design/`).

## Decisões do PO (2026-10-13): transparência e macOS
- **macOS: "melhor esforço, sem garantia".** O build de macOS segue experimental, sem teste manual e sem bloquear merge. Isso **deve constar no aviso aos usuários**: README (feito no rascunho de transparência), página de download e instalador/notas de versão, em pt-BR e inglês. Nenhum texto pode prometer suporte a macOS.
- Pedido do PO após ler críticas da comunidade OSArch a programas feitos com IA: (1) texto de transparência no README (aplicado ao README.md e README.en.md com o ok do PO em 2026-10-13); (2) cartão `F1-PRE-T01` de comportamento básico de janela e navegação com testes de regressão, antes da Fase 1; (3) pacote e convite para revisão humana externa em `docs/review/` (**nada enviado; o PO decide quando e para quem**); (4) este registro do macOS. Nenhuma resposta ou publicação em fórum em nome do PO.

## Decisões do PO (2026-10-13): catálogo de anotação (F3/F4)
1. **Detalhes 2D entram na 1.0:** linha de detalhe (D1), região preenchida (D2), texto (T1) e itens/componentes de detalhe 2D (D3, com biblioteca pequena própria, sem copiar de outro programa). Chamada e vista de detalhe (D4) ficam para depois da 1.0. "1.0" = o marco F6 do plano (faixa publicada de 21 a 42 meses).
2. **Nuvem de revisão entra na 1.0** (só a nuvem, para indicar o que corrigir). Controle de revisões completo (letra, data, tabela) fica para versão seguinte; o carimbo tem campo livre "revisão".
3. **Texto simples sobe para a F3** (junto da tag de ambiente).
4. **Cota que comanda (cadeado):** versão futura.
5. **Importar padrões de outro projeto** entra na F3, com **seleção do que importar** (filtrar quais padrões: modelos de vista, estilos de linha e de texto, carimbo), em vez de tudo de uma vez.
6. **Referências quebradas:** versão mínima (lista e contagem) adiantada para a F3.
- Efeito: o catálogo da F3/F4 e o escopo da 1.0 (v2/02) devem ser atualizados; a fatia de detalhes 2D ganha lugar no plano (a definir, antes da F3). Escopo é decisão do PO: registrada aqui.

## Entrevista S09 (2026-10-13): partes 1 a 3 feitas
- Resumo, fluxos, ferramentas prioritárias, atalhos, dores e "não pode perder" em `docs/research/2026-10-13-entrevista-s09-resumo.md`. **Aguarda o aceite do PO** (roteiro, seção 7: o resumo reflete o que disse; respostas da seção 4; decisão D híbrida). Só depois começam os desenhos de tela (wireframes).
- Novas decisões do PO a registrar no plano: (a) **atalhos de duas letras** como padrão de fábrica (TR, AL, MM mover, MI espelhar, RR girar, CC copiar, TG tag, WA parede), configuráveis; (b) **tags por atributo sem criar família por atributo**; (c) **"Por que não vejo isto?"** (explicar por que um elemento não aparece); (d) **folha a partir de modelo de folha**; (e) **análises (solar, energia etc.) fora do núcleo**, como plugins opcionais.

## Decisões do PO (2026-10-13): piso, forro, rodapé e fundações
1. **Laje e piso viram uma só ferramenta, chamada "Piso"** (ficha M8 do catálogo F1/F2). O tipo de piso tem camadas (estrutura e acabamento); não há ferramenta separada de acabamento; o quadro de área por tipo de piso lê do tipo.
2. **Forro e rodapé são essenciais e entram** (fichas M8b e M8c). Proposta de fase: **F2**, depois da F2-S07 (rodapé depende de paredes e portas). O plano `v2/02` hoje põe forro na F4 e não tem rodapé: mudança de escopo a aprovar (ver `docs/design/mudancas-de-escopo-2026-10-13.md`).
3. **Fundações (sapata, bloco, estaca) entram na Fase 4 como candidatas** (resumo T3 no catálogo F1/F2). Só o desenho do elemento, sem cálculo estrutural; a confirmar com o PO.
4. **Telhado e escada continuam na F4** (nada na F2).
- Pendentes de resposta do PO: como as teclas de uma e de duas letras convivem (pergunta 6 do catálogo F1/F2) e se forro e rodapé ficam na F2 depois da S07 ou só com os ambientes na F3 (pergunta 7).

## 2026-10-13: respostas às 4 perguntas do catálogo (PO: "de acordo com as recomendações")
1. Atalhos: padrão de fábrica só de duas letras; conjunto de uma letra opcional em Preferências (Medir troca de código; FO=Forro, RD=Rodapé).
2. Forro e rodapé na F2 depois da F2-S07 (por contorno e por parede); "por ambiente" na F3.
3. Fundações só como elemento, sem cálculo estrutural (F4, candidatas).
4. Atualizar `v2/02` numa única revisão com as 14 mudanças de escopo; **não** recalcular 21–42 meses antes da medição da F0.

## 2026-10-13 (noite): exceção de ausência até o PO voltar
PO: "vou ficar fora do computador até amanhã, pode continuar sem mim. Você tem minha autorização até eu voltar." Vale o mesmo regime das exceções de 12 e 13/10: o líder segue as próprias recomendações dentro da autorização permanente; continuam com o PO (a frente para e o líder passa a outra): ADR, meta do portão, escopo, licença, regras do processo e CLAUDE.md, instalar ferramenta nova, baixar arquivo, cota extra, apagar dados, credenciais, `main` direto, execução na tela real, meta da F0 não atingida. Opus só com semanal >25% restante e janela <70%.

## 2026-10-13 (noite): exceção de cota do Opus (PO)
PO: "Abra como exceção usar o opus dessa vez porque o limite semanal reinicia amanhã e quero aproveitar o máximo possível do limite. Após reiniciar esse limite semanal mantemos essa regra." Vale só até a renovação semanal (2026-10-14 09:00Z): o líder pode abrir lotes Opus mesmo com semanal ≤25% restante. Depois da renovação volta a regra de mais de 25% restante. A regra da janela de 5 h (<70%) segue valendo, salvo nova ordem do PO.

## 2026-10-14: CI do Windows mais rápido (PO: "Você tem meu ok")
O teste do instalador (~10 min por PR) passa a rodar só em push no `main`/tag ou quando o PR mexe em empacotamento/ambiente/CI. Recomendação do líder, aprovada pelo PO. Pendente de sugestão do agente (a decidir pelo PO depois): travar o ambiente do instalador (`packaging/runtime-environment.yml`) pela mesma trava `.lock`, para builds novos do conda-forge não quebrarem o instalador sem aviso (líder recomenda: sim).

## 2026-10-14: respostas à proposta de revisão da F0 (`PROPOSTA_REVISAO_F0.md`)
1. **D1:** pausar as T3 que faltam na S04 (T14c, T15 em diante) e terminar só o que já está aprovado (PR 83, T12). Vale até as revisões de S01, S02 e S03 e as respostas D1 a D8.
2. **D2:** sim. Planos antigos movidos para `docs/arquivo/`. O `CLAUDE.md` ainda cita os caminhos da raiz: ajuste só por cartão aprovado pelo PO.
3. **D3:** 1.0 mínima **incluindo detalhes 2D** (essenciais para o fluxo BIM). DXF e fachadas seguem como candidatos a adiar na sessão de escopo; confirma a decisão de 13/10.
4. **D4:** sim, IFC real do PO antes de fechar a S04 (só nos testes da máquina do PO).
5. **D5:** arquitetos de teste = colegas do estágio do PO (entendem de ferramenta). Nomes e momento: a combinar, sem prazo.
6. **D6:** sim, o PO lê o resumo de 5 linhas da S01.
7. **D7:** arquivo de entrega fica para o ADR-003 (S05).
8. **D8:** sim. Toda exceção de portão registra a meta original e o motivo; o portão F0 (S10) é reavaliado com as metas originais.
9. **D9:** abrir Opus só com semanal >25% restante e janela de 5 h **<70%** (mantido). A exceção de cota de 13/10 está encerrada.

- **2026-10-15, S03 (Rafael):** "aceito o plano", mas a memória abaixo de 6,0 GB precisa ser tratada (cartão da S04 a definir). O teste no Windows com placa de vídeo (T28) pode esperar até antes da entrega final; o PO não tem Windows instalado na máquina. Sem resposta explícita sobre a E3 (limite 100 ms) e sobre a regra da mediana: seguem como pergunta.
