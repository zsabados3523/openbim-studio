<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Painel do projeto OpenBIM Studio

Para o PO. Uma página para saber **onde estamos, o que está decidido, o que entra onde e o que falta decidir**. Atualizado em 2026-10-13 (plano `v2/02` na Revisão 3, com as 14 mudanças de escopo que você aprovou). O líder atualiza no fim de cada sessão. Detalhes: `docs/state/BOARD.md` (quadro), `docs/state/PO.md` (decisões), `v2/02_plano_mestre_v2.md` (plano).

## 1. Em que fase estamos
**Fase 0 (provas técnicas), perto do meio.** Das 10 fatias, 3 estão concluídas (S01, S02, S03), a S04 está na reta final do trabalho, e a S09 (interface com você) tem a entrevista feita e espera os desenhos. Ainda não existe programa utilizável.

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
| Fatia | O que é | Situação |
|---|---|---|
| S01 | Repositório, licenças, pesquisa | **Feita** |
| S02 | Testes automáticos Windows + Linux e programa esqueleto | **Feita** (você aceitou) |
| S03 | Protótipo de visualização 3D | **Feita** (você aprovou o portão) |
| **S04** | **Ponte entre Python e C++ (decide a arquitetura)** | **Em andamento** (ver abaixo) |
| S05 | Desfazer, refazer e gravar o par `.ifc` + `.obim` | Não iniciada (depende da S04) |
| S06 | Planta e corte automáticos (HLR) | Não iniciada |
| S07 | Tipo paramétrico por script | Não iniciada |
| S08 | Corpus de modelos de teste | Contínua |
| **S09** | **Interface com você (entrevista e desenhos de tela)** | **Entrevista feita; falta o seu aceite e os desenhos** |
| S10 | Calibração e portão da F0 | Não iniciada |

### Dentro da S04 (19 pequenas tarefas)
| Tarefa | O que é | Situação |
|---|---|---|
| T01 a T04 | Ambiente de compilação e a ponte básica | Feitas |
| T05 a T08 | Janela 3D em C++ dentro do Python, desenho e captura | Feitas |
| T09 | Câmera e troca de peças | Feita |
| T10, T10c | Clique com precisão de triângulo e escala de tela | Feitas |
| T11, T11b | Fluxo A: comandos em Python (criar, mover, desfazer) | Feitas |
| T13 | Fluxo B: paredes escritas em C++ | Em teste e revisão |
| T16 | Abertura de arquivos grandes (peças lentas) | Em correção (revisão reprovou uma vez) |
| T12 | Medições oficiais e comparação A × B | Próxima |
| T14, T15 | Fluxo B com janela Qt; threads | Depois |
| T17 | Módulo dentro do instalador | Pendente |
| T18, T19 | Relatório da fatia e **decisões de arquitetura (ADR-001 e ADR-004), com você** | Final |

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
- **Processo:** testes escritos por agente diferente do que escreve o código; revisão do Opus para partes críticas; tudo registrado em `docs/state/reports/`.
- **Transparência:** texto no README sobre quem faz e como; revisão externa será convidada quando você decidir.

## 6. O que ainda precisa decidir (com recomendação)
| # | Decisão | Quando | Recomendação |
|---|---|---|---|
| 1 | ~~Aprovar a atualização do plano (`v2/02`) com as 14 mudanças de escopo~~ | **Resolvido (13/10)** | Aprovado; plano na Revisão 3. **Prazos não recalculados**: refazer a faixa de 21 a 42 meses depois da medição da F0 (S10) |
| 2 | **Aceite da entrevista** (resumo, respostas, híbrido): você disse "de acordo" | Feito | Wireframes podem começar |
| 3 | **Wireframes** (desenhos de tela): quando você mandar as imagens da pasta `design/` | Quando puder | Mandar as imagens que já fez; o líder cruza com o catálogo |
| 4 | **ADR-001** (híbrido Python + C++ ou C++ puro) e **ADR-004** (threads) | No fim da S04 (T19) | Decidir com os números das medições |
| 5 | **Execução na tela real do Linux** (medida oficial de quadros) | Fim da S04 | Autorizar uma execução |
| 6 | **Meta do portão F0** (se a meta de desempenho não for atingida: opções) | S10 | Decidir só se acontecer |
| 7 | **Quando e para quem enviar o convite de revisão externa** | Quando quiser | Depois da S04 fechada |
| 8 | ~~Navegador do projeto: pastas livres ou categorias fixas~~ | **Resolvido (13/10)** | Pastas livres + agrupamentos prontos (F1-S03 e F2-S10) |
| 9 | ~~"Por que não vejo isto?" na F1 em versão mínima~~ | **Resolvido (13/10)** | Sim (F1-S05; versão completa na F3) |
| 10 | **8 testes no Revit** (cota alinhada, tag de porta, quadro de esquadrias etc.) | Antes da F2-S08 e da F3 | Fazer quando estiver com o programa aberto |
| 11 | **Cota que move a parede** (versão futura) e **chamada de detalhe** (depois da 1.0) | Já decidido como "depois" | Reabrir só se mudar de ideia |
| 12 | **Pendências menores sem prazo:** assinatura do instalador, placa de vídeo real no Windows (risco da S10), T23 antes do primeiro release | S10 e F1 | Só informar |
| 13 | **Detalhes da fatia de desenho 2D** (F2-S11): tamanho e se a biblioteca de itens vira fatia própria | No planejamento da F2 | O líder propõe na hora de planejar |
| 14 | **Refazer a faixa de prazo (21 a 42 meses)** | Depois da S10 (medição da F0) | Só então; sem chutar números antes |
