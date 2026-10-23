<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Painel do projeto OpenBIM Studio

Para o PO. Uma página para saber **onde estamos, o que está decidido, o que entra onde e o que falta decidir**. Atualizado em 2026-10-23 (S04 pronta, esperando o seu aceite; S05 em andamento; plano `v2/02` na Revisão 3). O líder atualiza no fim de cada sessão. Detalhes: `docs/state/BOARD.md` (quadro), `docs/state/PO.md` (decisões), `v2/02_plano_mestre_v2.md` (plano).

## Resumo: onde estamos e o que preciso de você
**Onde estamos:** Fase 0 (provas técnicas). S01, S02 e S03 estão aceitas. A S04 (ponte entre Python e C++) está pronta: você já aceitou a arquitetura e a forma das threads. A S05 (desfazer e gravar sem perder dados) está em andamento. Os documentos de acompanhamento ficaram em dois: este painel, para você, e o quadro, para a máquina.

**O que preciso de você:**
1. Aceite da S04 pelo roteiro `docs/acceptance/S04.md` (AppImage e instalador). Quando puder; depois a S04 vira "Fechada".
2. Desenhos de tela: as imagens da pasta `design/` (seção 6, item 3).
3. Sem prazo: as perguntas menores da seção 6.

## 1. Em que fase estamos
**Fase 0 (provas técnicas), com a S04 pronta e a S05 em andamento.** Das 10 fatias, 3 estão aceitas por você (S01, S02, S03). A S04 (ponte entre Python e C++) chegou ao fim técnico em 23/10: você aceitou o híbrido (ADR-001) e a forma mista das threads (ADR-004), e na sua placa todas as metas passaram; falta só o seu aceite pelo roteiro `docs/acceptance/S04.md`. A S05 (desfazer, refazer e gravar sem perder dados) começou: plano e 12 cartões prontos, respostas P1 a P6 aprovadas por você (P6: o mapa foi juntado a este painel). Ainda não existe programa para usar.
**Cota (Claude Pro; `QUOTA.md`):** o registro de cota está em `docs/state/QUOTA.md`; as últimas linhas dizem o uso mais recente.

## 2. Plano principal (as 7 fases)
**Atenção aos prazos:** a tabela abaixo ainda mostra a faixa antiga. O escopo cresceu um pouco com as decisões de 13/10, mas os prazos **não foram recalculados**: serão refeitos depois da medição da Fase 0 (portão S10), com a velocidade real. Se a faixa subir mais de 30%, cortamos escopo primeiro; os candidatos são fundações, importar padrões e a biblioteca de itens de detalhe.

| Fase | O que entrega | Prazo estimado (acumulado) | Situação |
|---|---|---|---|
| **F0** Provas técnicas | Decidir se a arquitetura funciona (Python + C++), instaladores, testes automáticos | 2 a 4 meses | **Em andamento** |
| **F1** Visualizador (v0.1) | Abrir IFC, navegar em 3D, árvore, propriedades, medir, cortes, salvar sem perder dados, instalador | 4 a 8 meses | Não iniciada |
| **F2** Modelagem básica (v0.2) | Desenhar casa: níveis, eixos, paredes, piso, forro, rodapé, pilares, vigas, portas, janelas, desenho 2D de detalhe, editar, desfazer | 8 a 16 meses | Não iniciada |
| **F3** Documentação essencial (v0.3, "Planta Legal") | Ambientes, plantas e cortes, cotas, texto, pranchas com carimbo, importar padrões, PDF, quadro de áreas | 11 a 22 meses | Não iniciada |
| **F4** Modelagem residencial completa (v0.5) | Telhado, escada, guarda-corpo, terreno, bibliotecas, tipos por script | 14 a 29 meses | Não iniciada |
| **F5** Documentação executiva (v0.8) | Fachadas, cortes múltiplos, nuvem de revisão, tabelas, DXF, religar referências | 18 a 36 meses | Não iniciada |
| **F6** Estabilização e **1.0** | Desempenho, manual, tutoriais, instalador assinado, testes com arquitetos reais | **21 a 42 meses** | Não iniciada |

Portões (você decide se passa): F0 (go ou não go da arquitetura), F1 (roteiro de 30 min com 3 IFCs), F2 (casa de 60 m² em até 2 h), v0.3 (planta, corte e quadro de áreas em 1 dia), F4 (sobrado com telhado de 4 águas e escada), F5 (projeto legal + 5 pranchas executivas), 1.0 (um projeto real seu, sem outro programa, 8 h sem travar).

## 3. Plano ramificado: a Fase 0 em fatias
Pense numa obra: antes de levantar a casa, provamos que o terreno e as fundações aguentam.

| Fatia | O que é | Situação |
|---|---|---|
| S01 | Repositório, licenças, pesquisa | **Feita** |
| S02 | Testes automáticos Windows + Linux e programa esqueleto | **Feita** (você aceitou) |
| S03 | Protótipo de visualização 3D | **Feita** (você aprovou o portão) |
| **S04** | **Ponte entre Python e C++ (decide a arquitetura)** | **Pronta; aguarda o seu aceite** (roteiro `docs/acceptance/S04.md`) |
| **S05** | Desfazer, refazer e gravar o par `.ifc` + `.obim` | **Em andamento** (plano em `cards/F0-S05/README.md`; P1 a P6 aprovadas) |
| S06 | Planta e corte automáticos (HLR) | Não iniciada |
| S07 | Tipo paramétrico por script | Não iniciada |
| S08 | Corpus de modelos de teste | Contínua |
| **S09** | **Interface com você (entrevista e desenhos de tela)** | **Entrevista feita e aceita (15/10, com um ajuste); faltam os desenhos de tela** |
| S10 | Calibração e portão da F0 | Não iniciada |

### S04: o que ficou feito (fechamento em 2026-10-23; `reports/F0-S04-fechamento.md`)
| Tema | Resultado |
|---|---|
| Ponte, janela 3D, fluxos A e B, abertura de arquivos grandes, threads (T01 a T17) | Feitos; módulo `obimcore` dentro do AppImage e do instalador do Windows (310,6 MB) |
| Memória do arquivo pesado (T20, T29) | Atingida na placa: 5.858 MB contra 6.000 (bloco 250 e um reinício planejado); folga de 42 MB no pior caso já visto |
| Troca de geometria em IFC real, M2b (T22 a T30) | Atingida: cerca de 49 ms nos dois arquivos reais (antes 399 e 6.749 ms) |
| Threads (T15, T19, V1) | Você aceitou a forma mista (ADR-004); ADR-001 híbrido aceito |
| Teste automático do Windows (T23) | Cerca de 12 min (meta 10 min mantida para a F1; você aceitou) |
| Teste automático do Linux (T23L, PR 275) | 9:15 de mediana, antes 39:31 |
| Aberto, com cartão | Trava rara sem placa compatível no Windows (F1); T28 (Windows com placa real, seu); 4 números do ADR-004 sem medida; T04b (pausado) |

### S05: cartões (plano de 23/10; `cards/F0-S05/README.md`)
| Cartão | O que é | Situação |
|---|---|---|
| T01 | Organização: quadro, mapa e painel | Feita (23/10) |
| T01b | Juntar o mapa no painel e atualizar o CLAUDE.md (P6) | Feita (23/10) |
| T02 | Sondas do ifcopenshell (só números) | Pronta |
| T03 | ADR-002, rascunho (Opus) | Depende de T02 |
| T04 | Transação única IFC + lateral, desfazer, prova das 10.000 | Depende de T03 |
| T05 | Diário de transações e recuperação depois da queda | Depende de T04 |
| T06 | Gravação atômica de um arquivo | Depende de T03 |
| T07 | Gravação do par com diário | Depende de T04, T06 |
| T08 a T09 | Limite de memória do desfazer; autosave na pasta local | Depois de T05 e T07 |
| T10 | Medição das metas (5 ms em 50 MB) | Depende de T04, T05, T07, T08 |
| T11 | Protótipo de merge (não é portão) | Depende de T04, T05 |
| T12 | Fechamento: ADR-002 com números e roteiro seu | Depende de T10, T11 |

### Lotes do Opus
Lotes 52 a 77 (módulo no AppImage e no instalador, reduções de memória e de M2b, ADR-001 e ADR-004, fechamento da S04) estão em `docs/state/lotes/` e resumidos no `LOG.md`. Para a S05 estão previstos 5 lotes (A a E) no README da fatia.

## 4. O que entra onde (ferramentas)
**F1** (ver): navegar em 3D, **voar (botão direito do mouse mais W, A, S, D)**, atalhos configuráveis, cubo de vistas, enquadrar, selecionar, filtro por classe, navegador do projeto e árvore, propriedades, ocultar/isolar, transparência, cor por propriedade, **"Por que não vejo isto?" (versão mínima)**, caixa e plano de corte, medir, salvar sem perdas, instalador. Antes da F1: **testes de comportamento básico de janela e navegação** (cartão F1-PRE-T01).

**F2** (modelar): desfazer/refazer e recuperação, novo projeto com modelo brasileiro, níveis, eixos, paredes com camadas e junções, **Piso** (laje e piso numa ferramenta só), **Forro** e **Rodapé** (depois das portas; por contorno e por parede), pilar, viga, porta, janela, snaps, digitar medida, cotas temporárias, mover, copiar, girar, espelhar, alinhar, aparar, atalhos de duas letras, tipos e propriedades, navegador organizável em pastas, favoritos, e **desenho 2D de detalhe (linha, região preenchida e itens de uma biblioteca pequena nossa)**, ainda antes da F3.

**F3** (documentar): ambientes e áreas, plantas e cortes automáticos, gráfico por categoria e hachuras, cotas que acompanham o desenho (linear, alinhada e de nível), tag de ambiente, **texto simples**, tag por atributo (sem criar família nova), "Por que não vejo isto?" completo, folha por modelo de folha, pranchas com carimbo (campo livre "revisão"), PDF, quadro de áreas, **importar padrões de outro projeto (escolhendo quais)**, versão mínima de referências quebradas (lista e contagem), forro e rodapé "por ambiente".

**F4** (completar): telhado, escada, guarda-corpo, terreno, revestimentos por ambiente (só o que não for piso), componentes de biblioteca, tipos por script, **fundações (candidatas; só o elemento, sem cálculo)**, tags por categoria, quadro de esquadrias e de materiais, legendas.

**F5** (executivo): fachadas, cortes múltiplos, planta de cobertura, **nuvem de revisão**, símbolos, tabelas na prancha, DXF, **religar referências quebradas**, IFC para outros programas.

**Fora da 1.0 (2.0 ou depois):** cota que move a parede, chamada e vista de detalhe, controle completo de revisões (letra, data, tabela), vista mestre estilo ArchiCAD, análises (solar, iluminação, energia, estrutural; possíveis como plugin opcional), editor gráfico de famílias, colaboração em tempo real, macOS com garantia.

## 5. O que está decidido
- **Produto:** programa aberto (AGPL), Windows e Linux obrigatórios, macOS "melhor esforço, sem garantia"; Brasil como primeiro pacote regional; sem conta, nuvem ou telemetria.
- **Arquivos:** IFC limpo + arquivo lateral `.obim` (vistas, pranchas, cotas); pacote `.obimpack` para enviar.
- **Interface:** híbrida (navegador e propriedades à Revit; caixa de ferramentas e favoritos à ArchiCAD); vistas independentes como no Revit; abas de vistas; navegador e propriedades em abas no mesmo painel; atalhos de duas letras configuráveis (TR, AL, MM, MI, RR, CC, TG, WA).
- **Escopo (13/10), já aplicado ao plano `v2/02` (Revisão 3):** detalhes 2D e nuvem de revisão entram na 1.0; texto simples na F3; importar padrões com seleção na F3; referências quebradas mínimas na F3; Piso unificado, forro e rodapé na F2; fundações candidatas da F4 (só o elemento); telhado e escada na F4; voar no 3D e "Por que não vejo isto?" na F1; navegador organizável em pastas; atalhos de duas letras (uma letra só como opção em Preferências); tags por atributo; folha por modelo de folha; análises fora do núcleo. Prazos **não recalculados** até a medição da F0.
- **Processo:** testes escritos por agente diferente do que escreve o código; revisão do Opus para partes críticas; tudo registrado em `docs/state/` (relatórios, lotes Opus e LOG).
- **Metas da S04:** padrão rigoroso mantido; todas atingidas na placa em 23/10, sem afrouxar. Mudar métrica ou meta só aparece como decisão sua, com a meta original ao lado. O portão da F0 é reavaliado com as metas originais.
- **CI do Windows (23/10):** cerca de 12 min aceito por você; meta de 10 min passa à F1 (`cards/F1-CI-cadeia-instalador.md`).
- **S05 (23/10):** P1 a P5 aprovadas como recomendadas (comparação por conteúdo sem `ifcdiff`; `.obim` mínimo provisório; 5 ms = edição pequena em memória com desfazer, modelo sintético de 50 MB; diário na hora com escrita forçada a cada 2 s; "Recuperar o trabalho de HH:MM?" sem gravar por cima do `Casa.ifc`; autosave a cada 5 min).
- **Documentos (23/10, P6):** o quadro (para a máquina) e este painel (para você) ficam; o mapa foi juntado ao painel e apagado.
- **Transparência:** texto no README sobre quem faz e como; revisão externa será convidada quando você decidir.

## 6. O que ainda precisa decidir (com recomendação)
| # | Decisão | Quando | Recomendação |
|---|---|---|---|
| 1 | ~~Aprovar a atualização do plano (`v2/02`) com as 14 mudanças de escopo~~ | **Resolvido (13/10)** | Aprovado; plano na Revisão 3. **Prazos não recalculados**: refazer a faixa de 21 a 42 meses depois da medição da F0 (S10) |
| 2 | **Aceite da entrevista** (resumo, respostas, híbrido): você disse "de acordo" | Feito | Wireframes podem começar |
| 3 | **Wireframes** (desenhos de tela): quando você mandar as imagens da pasta `design/` | Quando puder | Mandar as imagens que já fez; o líder cruza com o catálogo |
| 4 | ~~**ADR-004** e **ADR-001**~~ | **Resolvido (23/10)** | Híbrido e forma mista aceitos por você |
| 5 | ~~Execução na tela real do Linux (medida oficial)~~ | **Resolvido (17/10)** | Feita, 18:25 a 19:04. O Windows com placa real segue pendente (T28, dono: você, antes da entrega final) |
| 6 | ~~**Meta do portão F0**: 3 metas não atingidas~~ | **Resolvido (23/10)** | Todas atingidas na placa sem afrouxar; o portão da F0 usa as metas originais |
| 7 | **Quando e para quem enviar o convite de revisão externa** | Quando quiser | Depois da S04 fechada |
| 8 | ~~Navegador do projeto: pastas livres ou categorias fixas~~ | **Resolvido (13/10)** | Pastas livres + agrupamentos prontos (F1-S03 e F2-S10) |
| 9 | ~~"Por que não vejo isto?" na F1 em versão mínima~~ | **Resolvido (13/10)** | Sim (F1-S05; versão completa na F3) |
| 10 | **8 testes no Revit** (cota alinhada, tag de porta, quadro de esquadrias etc.) | Antes da F2-S08 e da F3 | Fazer quando estiver com o programa aberto |
| 11 | **Cota que move a parede** (versão futura) e **chamada de detalhe** (depois da 1.0) | Já decidido como "depois" | Reabrir só se mudar de ideia |
| 12 | **Pendências menores sem prazo:** assinatura do instalador, placa de vídeo real no Windows (risco da S10), cartão T23 da S02 (antes do primeiro release) | S10 e F1 | Só informar |
| 13 | **Detalhes da fatia de desenho 2D** (F2-S11): tamanho e se a biblioteca de itens vira fatia própria | No planejamento da F2 | O líder propõe na hora de planejar |
| 14 | **Refazer a faixa de prazo (21 a 42 meses)** | Depois da S10 (medição da F0) | Só então; sem chutar números antes |
| 15 | ~~Opções do lote 57~~ | **Resolvido** | Escolhidas e feitas (T29, T30) |
| 16 | ~~Cartão T23 da S04~~ | **Resolvido (23/10)** | Cerca de 12 min aceito; resto na F1 |
| 17 | **Aceite da S04** pelo roteiro `docs/acceptance/S04.md` (AppImage e instalador) | Quando puder | Conferir o roteiro; depois a S04 vira Fechada |
| 20 | ~~**P6: quadro, mapa e painel**~~ | **Resolvido (23/10)** | Manter quadro e painel; mapa juntado ao painel e apagado (`reports/F0-S05-T01-organizacao.md`) |
| 18 | **Texto do `CLAUDE.md`** (RG-28) e **limpeza de ramos antigos no GitHub** | Quando puder | Aprovar o texto exato; apagar ramos só com a sua palavra |
| 19 | **Perguntas menores abertas em `PO.md`:** confirmar que as exceções de ausência acabaram (A9), ambiente do instalador pela trava (A3), critério do instalador para o AppImage (A4), folga nos testes de tempo do Windows (A5), `/usage` para o registro de cota (A10), nomes dos colegas de estágio (A11), autorização da CAIXA para o SINAPI na F5 (A15) | Sem prazo | Ver a recomendação de cada uma em `PO.md` |

## 7. O plano de revisão (de onde veio a pausa da S04)
**A ideia:** antes de continuar a parte mais difícil (a S04), conferir se S01, S02 e S03 estão realmente certas, e organizar os riscos. As revisões terminaram em 15/10 e a S04 voltou a andar.
**O que você decidiu (14 e 15/10):** pausar a S04 até as revisões terminarem (D1); mover os 3 planos antigos para `docs/arquivo/` (D2, feito); detalhes 2D ficam na 1.0, com DXF e fachadas como candidatos a adiar (D3); exceções de portão sempre registram a meta original (D8).
**O que foi feito:** S01, S02 e S03 revisadas e aceitas por você em 15/10; 25 cartões de revisão geral (RG-01 a RG-25), quase todos mesclados; uma revisão final independente do Opus concluiu que o CI não ficou mais frouxo e que nada se perdeu na reorganização.
**O que falta:** texto do `CLAUDE.md` do cartão RG-28, que espera a sua aprovação (seção 6, item 18); limpeza dos ramos antigos no GitHub, só com a sua palavra.
